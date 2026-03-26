from __future__ import annotations

import asyncio
import importlib
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.error_handlers import register_exception_handlers
from app.core.errors import (
    CooldownError,
    EmailAlreadyExistsError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    PasswordResetTokenInvalidError,
    TokenInvalidError,
)
from app.core.security import hash_password
from app.models.email_verification import EmailVerification, VerificationType
from app.models.password_reset import PasswordResetToken
from app.models.user import User
from tests.conftest import load_required_env


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


def _build_auth_app(monkeypatch: pytest.MonkeyPatch):
    load_required_env(monkeypatch)
    api_module = importlib.reload(importlib.import_module("app.api.v1.auth"))
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(api_module.router)
    return app, api_module


def test_auth_schemas_normalize_email_and_validate_password(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    schema_module = importlib.reload(importlib.import_module("app.schemas.auth"))

    send_code = schema_module.SendCodeRequest(email="  USER@Example.com ")
    register = schema_module.RegisterRequest(
        email=" Another@Example.com ",
        code="123456",
        password="StrongPass123",
    )

    assert send_code.email == "user@example.com"
    assert register.email == "another@example.com"
    assert schema_module.validate_password_strength("StrongPass123") == "StrongPass123"

    with pytest.raises(ValueError):
        schema_module.validate_password_strength("weakpass")


def test_send_register_code_persists_verification_and_sets_cooldown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_required_env(monkeypatch)
    service_module = importlib.reload(importlib.import_module("app.services.auth_service"))

    fake_db = AsyncMock()
    fake_db.add = Mock()
    fake_db.flush = AsyncMock()
    fake_db.execute = AsyncMock(return_value=_ScalarResult(None))
    fake_redis = AsyncMock()
    fake_redis.exists.return_value = False

    scheduled: list[object] = []

    def fake_create_task(coro):
        scheduled.append(coro)
        return SimpleNamespace()

    monkeypatch.setattr(service_module.asyncio, "create_task", fake_create_task)

    cooldown = asyncio.run(service_module.send_register_code("User@Example.com", fake_db, fake_redis))

    assert cooldown == 60
    assert fake_db.add.call_count == 1
    verification = fake_db.add.call_args.args[0]
    assert isinstance(verification, EmailVerification)
    assert verification.email == "user@example.com"
    assert verification.type == VerificationType.REGISTER
    fake_redis.set.assert_awaited_once_with("cooldown:register:user@example.com", "1", ex=60)
    assert len(scheduled) == 1
    scheduled[0].close()


def test_send_register_code_enforces_cooldown(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    service_module = importlib.reload(importlib.import_module("app.services.auth_service"))

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=_ScalarResult(None))
    fake_redis = AsyncMock()
    fake_redis.exists.return_value = True
    fake_redis.ttl.return_value = 42

    with pytest.raises(CooldownError) as exc_info:
        asyncio.run(service_module.send_register_code("user@example.com", fake_db, fake_redis))

    assert exc_info.value.detail == {"retry_after_seconds": 42}


def test_register_user_marks_verification_used_and_creates_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_required_env(monkeypatch)
    service_module = importlib.reload(importlib.import_module("app.services.auth_service"))
    verification = EmailVerification(
        email="user@example.com",
        code="123456",
        type=VerificationType.REGISTER,
        expired_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    fake_db = AsyncMock()
    fake_db.add = Mock()
    fake_db.flush = AsyncMock()
    fake_db.execute = AsyncMock(
        side_effect=[
            _ScalarResult(verification),
            _ScalarResult(None),
        ]
    )

    asyncio.run(service_module.register_user("user@example.com", "123456", "StrongPass123", fake_db))

    created_user = fake_db.add.call_args.args[0]
    assert isinstance(created_user, User)
    assert created_user.email == "user@example.com"
    assert created_user.password_hash != "StrongPass123"
    assert verification.is_used is True


def test_register_user_translates_integrity_error(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    service_module = importlib.reload(importlib.import_module("app.services.auth_service"))
    verification = EmailVerification(
        email="user@example.com",
        code="123456",
        type=VerificationType.REGISTER,
        expired_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    fake_db = AsyncMock()
    fake_db.add = Mock()
    fake_db.flush = AsyncMock(side_effect=IntegrityError("insert", {}, Exception("dup")))
    fake_db.execute = AsyncMock(
        side_effect=[
            _ScalarResult(verification),
            _ScalarResult(None),
        ]
    )

    with pytest.raises(EmailAlreadyExistsError):
        asyncio.run(service_module.register_user("user@example.com", "123456", "StrongPass123", fake_db))

    fake_db.rollback.assert_not_awaited()


def test_login_user_success_and_error_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    service_module = importlib.reload(importlib.import_module("app.services.auth_service"))
    active_user = User(
        email="user@example.com",
        password_hash=hash_password("StrongPass123"),
        is_verified=True,
        is_active=True,
    )
    active_user.id = uuid.uuid4()

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=_ScalarResult(active_user))
    tokens = asyncio.run(service_module.login_user("user@example.com", "StrongPass123", fake_db))
    assert tokens.token_type == "Bearer"
    assert tokens.access_token
    assert tokens.refresh_token

    fake_db.execute = AsyncMock(return_value=_ScalarResult(None))
    with pytest.raises(InvalidCredentialsError):
        asyncio.run(service_module.login_user("missing@example.com", "StrongPass123", fake_db))

    unverified_user = User(
        email="user@example.com",
        password_hash=hash_password("StrongPass123"),
        is_verified=False,
        is_active=True,
    )
    fake_db.execute = AsyncMock(return_value=_ScalarResult(unverified_user))
    with pytest.raises(EmailNotVerifiedError):
        asyncio.run(service_module.login_user("user@example.com", "StrongPass123", fake_db))


def test_refresh_tokens_rejects_non_refresh_token(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    service_module = importlib.reload(importlib.import_module("app.services.auth_service"))
    monkeypatch.setattr(
        service_module,
        "decode_token",
        lambda token: {"sub": str(uuid.uuid4()), "type": "access"},
    )

    with pytest.raises(TokenInvalidError):
        asyncio.run(service_module.refresh_tokens("bad-token", AsyncMock()))


def test_send_reset_email_does_not_enumerate_unknown_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    load_required_env(monkeypatch)
    service_module = importlib.reload(importlib.import_module("app.services.auth_service"))

    fake_db = AsyncMock()
    fake_db.add = Mock()
    fake_db.flush = AsyncMock()
    fake_db.execute = AsyncMock(return_value=_ScalarResult(None))
    fake_redis = AsyncMock()
    fake_redis.exists.return_value = False

    asyncio.run(service_module.send_reset_email("missing@example.com", fake_db, fake_redis))

    fake_db.add.assert_not_called()
    fake_redis.set.assert_awaited_once_with("cooldown:reset:missing@example.com", "1", ex=60)


def test_reset_password_marks_token_used(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    service_module = importlib.reload(importlib.import_module("app.services.auth_service"))

    user = User(
        email="user@example.com",
        password_hash=hash_password("OldPass123"),
        is_verified=True,
        is_active=True,
    )
    user.id = uuid.uuid4()
    reset_token = PasswordResetToken(
        user_id=user.id,
        token="reset-token",
        expired_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    fake_db = AsyncMock()
    fake_db.flush = AsyncMock()
    fake_db.execute = AsyncMock(
        side_effect=[
            _ScalarResult(reset_token),
            _ScalarResult(user),
        ]
    )

    asyncio.run(service_module.reset_password("reset-token", "StrongPass123", fake_db))

    assert reset_token.is_used is True
    assert user.password_hash != hash_password("OldPass123")


def test_reset_password_raises_dedicated_invalid_token_error(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    service_module = importlib.reload(importlib.import_module("app.services.auth_service"))

    fake_db = AsyncMock()
    fake_db.execute = AsyncMock(return_value=_ScalarResult(None))

    with pytest.raises(PasswordResetTokenInvalidError):
        asyncio.run(service_module.reset_password("bad-token", "StrongPass123", fake_db))


def test_email_service_wrapper_logs_and_swallows_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)
    email_service_module = importlib.reload(importlib.import_module("app.services.email_service"))

    class FailingEmailService:
        async def send_verification_code(self, email: str, code: str) -> None:
            raise RuntimeError("smtp down")

        async def send_password_reset(self, email: str, reset_link: str) -> None:
            raise RuntimeError("smtp down")

    monkeypatch.setattr(email_service_module, "get_email_service", lambda: FailingEmailService())

    asyncio.run(email_service_module.send_verification_email("user@example.com", "123456"))
    asyncio.run(email_service_module.send_reset_email("user@example.com", "reset-token"))


def test_auth_router_login_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    app, api_module = _build_auth_app(monkeypatch)
    fake_db = AsyncMock()

    async def override_db():
        yield fake_db

    async def fake_login_user(email: str, password: str, db) -> object:
        assert email == "user@example.com"
        return api_module.TokenResponse(
            access_token="access",
            refresh_token="refresh",
            token_type="Bearer",
            expires_in=1800,
        )

    app.dependency_overrides[api_module.get_db] = override_db
    monkeypatch.setattr(api_module, "login_user", fake_login_user)

    with TestClient(app) as client:
        response = client.post(
            "/login",
            json={"email": "USER@example.com", "password": "StrongPass123"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["data"]["access_token"] == "access"


def test_auth_router_login_returns_403_for_unverified_email(monkeypatch: pytest.MonkeyPatch) -> None:
    app, api_module = _build_auth_app(monkeypatch)
    fake_db = AsyncMock()

    async def override_db():
        yield fake_db

    async def fake_login_user(email: str, password: str, db) -> object:
        raise EmailNotVerifiedError()

    app.dependency_overrides[api_module.get_db] = override_db
    monkeypatch.setattr(api_module, "login_user", fake_login_user)

    with TestClient(app) as client:
        response = client.post(
            "/login",
            json={"email": "user@example.com", "password": "StrongPass123"},
        )

    assert response.status_code == 403
    assert response.json()["code"] == 4011
