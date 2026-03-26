from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from jose import jwt

from app.core.config import Settings, get_settings
from app.core.error_handlers import register_exception_handlers
from app.core.errors import (
    CooldownError,
    EmailAlreadyExistsError,
    EmailNotVerifiedError,
    TaskNotFoundError,
    TokenExpiredError,
    TokenInvalidError,
)
from app.core.logging import setup_logging
from app.core.security import (
    ACCESS_TOKEN_TYPE,
    ALGORITHM,
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


REQUIRED_ENV_VARS = {
    "APP_SECRET_KEY": "x" * 32,
    "DATABASE_URL": "postgresql+asyncpg://postgres:password@localhost:5432/food_analyzer",
    "DATABASE_SYNC_URL": "postgresql+psycopg://postgres:password@localhost:5432/food_analyzer",
    "MINIO_ACCESS_KEY": "minioadmin",
    "MINIO_SECRET_KEY": "minio-secret",
    "PADDLEOCR_JOB_URL": "https://paddle-ocr.example.com/api/v1/ocr/job",
    "PADDLEOCR_TOKEN": "paddle-token",
    "DEEPSEEK_API_KEY": "deepseek-api-key",
    "SMTP_HOST": "smtp.example.com",
    "SMTP_USERNAME": "smtp-user",
    "SMTP_PASSWORD": "smtp-password",
    "SMTP_FROM_EMAIL": "noreply@example.com",
}


def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name, raising=False)


def _load_required_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    _clear_settings_env(monkeypatch)
    env_values = {**REQUIRED_ENV_VARS, **overrides}
    for key, value in env_values.items():
        monkeypatch.setenv(key, value)


def _build_test_app(monkeypatch: pytest.MonkeyPatch, *, debug: bool) -> FastAPI:
    _load_required_env(monkeypatch, APP_DEBUG=str(debug).lower())

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/resource")
    async def raise_resource_error() -> None:
        raise TaskNotFoundError()

    @app.get("/cooldown")
    async def raise_cooldown_error() -> None:
        raise CooldownError(60)

    @app.get("/validation")
    async def validation_endpoint(page: int) -> dict[str, int]:
        return {"page": page}

    @app.get("/unhandled")
    async def raise_unhandled_error() -> None:
        raise RuntimeError("boom")

    return app


def test_exception_defaults_and_overrides() -> None:
    cooldown = CooldownError(30)
    email_exists = EmailAlreadyExistsError()
    overridden = TaskNotFoundError("Task no longer exists")

    assert cooldown.status_code == 429
    assert cooldown.error_code == 4002
    assert cooldown.detail == {"retry_after_seconds": 30}
    assert email_exists.status_code == 409
    assert email_exists.error_code == 4001
    assert overridden.message == "Task no longer exists"


def test_app_exception_handler_returns_expected_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_test_app(monkeypatch, debug=False)

    with TestClient(app) as client:
        response = client.get("/resource")

    assert response.status_code == 404
    assert response.json() == {
        "code": 4041,
        "message": "分析任务不存在",
        "data": None,
    }


def test_cooldown_exception_returns_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_test_app(monkeypatch, debug=False)

    with TestClient(app) as client:
        response = client.get("/cooldown")

    assert response.status_code == 429
    assert response.json() == {
        "code": 4002,
        "message": "请求过于频繁，请稍后再试",
        "data": {"retry_after_seconds": 60},
    }


def test_email_not_verified_error_uses_403(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_required_env(monkeypatch)
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/email-not-verified")
    async def raise_error() -> None:
        raise EmailNotVerifiedError()

    with TestClient(app) as client:
        response = client.get("/email-not-verified")

    assert response.status_code == 403
    assert response.json() == {
        "code": 4011,
        "message": "邮箱尚未完成验证",
        "data": None,
    }


def test_validation_exception_handler_formats_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    app = _build_test_app(monkeypatch, debug=False)

    with TestClient(app) as client:
        response = client.get("/validation", params={"page": "abc"})

    payload = response.json()
    assert response.status_code == 422
    assert payload["code"] == 4220
    assert payload["message"] == "请求参数错误"
    assert payload["data"]["errors"]
    assert payload["data"]["errors"][0]["field"] == "page"


def test_unhandled_exception_handler_hides_details_when_not_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_test_app(monkeypatch, debug=False)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/unhandled")

    assert response.status_code == 500
    assert response.json() == {
        "code": 5001,
        "message": "服务器内部错误",
        "data": None,
    }


def test_unhandled_exception_handler_shows_details_when_debug(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = _build_test_app(monkeypatch, debug=True)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/unhandled")

    payload = response.json()
    assert response.status_code == 500
    assert payload["code"] == 5001
    assert payload["data"] == {
        "exception_type": "RuntimeError",
        "message": "boom",
    }


def test_setup_logging_console_emits_structlog_output(capsys: pytest.CaptureFixture[str]) -> None:
    setup_logging("INFO", "console")
    capsys.readouterr()

    logger = structlog.get_logger("unit_test_console")
    logger.info("console_message", scope="test")

    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "console_message" in combined
    assert "unit_test_console" in combined
    logging.getLogger().handlers.clear()


def test_setup_logging_json_bridges_stdlib_logging(
    capsys: pytest.CaptureFixture[str],
) -> None:
    setup_logging("WARNING", "json")
    capsys.readouterr()

    stdlib_logger = logging.getLogger("stdlib_bridge")
    stdlib_logger.warning("stdlib_message")

    captured = capsys.readouterr()
    combined = (captured.out + captured.err).strip().splitlines()[-1]
    payload = json.loads(combined)

    assert logging.getLogger().level == logging.WARNING
    assert payload["event"] == "stdlib_message"
    assert payload["level"] == "warning"
    assert payload["logger"] == "stdlib_bridge"
    logging.getLogger().handlers.clear()


def test_hash_password_and_verify_password() -> None:
    password = "StrongPassword123!"
    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed) is True
    assert verify_password("wrong-password", hashed) is False


def test_create_and_decode_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_required_env(monkeypatch)

    token = create_access_token("user-123")
    payload = decode_token(token)

    assert payload["sub"] == "user-123"
    assert payload["type"] == ACCESS_TOKEN_TYPE
    assert payload["exp"] > int(datetime.now(timezone.utc).timestamp())


def test_create_and_decode_refresh_token(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_required_env(monkeypatch)

    token = create_refresh_token("user-456")
    payload = decode_token(token)

    assert payload["sub"] == "user-456"
    assert payload["type"] == REFRESH_TOKEN_TYPE


def test_decode_token_raises_token_invalid_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_required_env(monkeypatch)

    with pytest.raises(TokenInvalidError):
        decode_token("not-a-valid-token")


def test_decode_token_raises_token_expired_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_required_env(monkeypatch)
    settings = get_settings()
    expired_token = jwt.encode(
        {
            "sub": "user-expired",
            "type": ACCESS_TOKEN_TYPE,
            "exp": datetime.now(timezone.utc) - timedelta(seconds=1),
        },
        settings.APP_SECRET_KEY.get_secret_value(),
        algorithm=ALGORITHM,
    )

    with pytest.raises(TokenExpiredError):
        decode_token(expired_token)
