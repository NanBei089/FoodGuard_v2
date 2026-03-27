from __future__ import annotations

import asyncio
import importlib
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import APIRouter
from fastapi.testclient import TestClient
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import Settings, get_settings
from app.core.errors import TokenInvalidError

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


def test_db_base_mixins_define_expected_columns() -> None:
    from app.db.base import Base, TimeStampMixin, UUIDPrimaryKeyMixin

    class Sample(UUIDPrimaryKeyMixin, TimeStampMixin, Base):
        __tablename__ = "sample_items"
        name: Mapped[str] = mapped_column(String(50), nullable=False)

    columns = Sample.__table__.c

    assert "id" in columns
    assert columns["created_at"].nullable is False
    assert columns["updated_at"].nullable is False
    assert columns["name"].type.length == 50


def test_session_module_creates_engine_and_db_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _load_required_env(monkeypatch)
    session_module = importlib.import_module("app.db.session")
    session_module = importlib.reload(session_module)

    fake_session = AsyncMock()

    class FakeSessionContext:
        async def __aenter__(self):
            return fake_session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    session_module.AsyncSessionLocal = lambda: FakeSessionContext()

    async def consume_success():
        values = []
        async for session in session_module.get_db():
            values.append(session)
        return values

    sessions = asyncio.run(consume_success())

    assert sessions == [fake_session]
    fake_session.commit.assert_awaited_once()
    fake_session.rollback.assert_not_awaited()
    fake_session.close.assert_awaited_once()
    assert session_module.get_engine() is session_module.engine


def test_redis_helpers_use_cached_client(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_required_env(monkeypatch)
    redis_module = importlib.import_module("app.db.redis")
    redis_module = importlib.reload(redis_module)

    fake_client = AsyncMock()
    fake_client.get.return_value = "value"
    fake_client.ttl.return_value = 25
    fake_client.exists.return_value = 1

    monkeypatch.setattr(redis_module, "from_url", lambda *args, **kwargs: fake_client)

    async def exercise() -> None:
        client = await redis_module.get_redis()
        assert client is fake_client
        assert await redis_module.get_redis() is fake_client
        await redis_module.set_with_ttl("key", "value", 30)
        assert await redis_module.get_value("key") == "value"
        assert await redis_module.get_ttl("key") == 25
        assert await redis_module.exists("key") is True
        await redis_module.close_redis()

    asyncio.run(exercise())

    fake_client.set.assert_awaited_once_with("key", "value", ex=30)
    fake_client.get.assert_awaited_once_with("key")
    fake_client.ttl.assert_awaited_once_with("key")
    fake_client.exists.assert_awaited_once_with("key")
    fake_client.aclose.assert_awaited_once()


def test_common_schema_helpers() -> None:
    common_module = importlib.import_module("app.schemas.common")

    response = common_module.success_response({"ok": True}, message="done")
    page_request = common_module.PageRequest(page=2, page_size=10)
    page_response = common_module.PageResponse[str](
        items=["a", "b"], total=21, page=2, page_size=10
    )

    assert response.code == 0
    assert response.message == "done"
    assert response.data == {"ok": True}
    assert page_request.page == 2
    assert page_request.page_size == 10
    assert page_response.total_pages == 3


def test_api_router_registers_expected_v1_prefixes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _load_required_env(monkeypatch)
    captured_prefixes: list[str] = []
    original_include_router = APIRouter.include_router

    def tracking_include_router(self, router, *args, **kwargs):
        captured_prefixes.append(kwargs.get("prefix", ""))
        return original_include_router(self, router, *args, **kwargs)

    monkeypatch.setattr(APIRouter, "include_router", tracking_include_router)

    router_module = importlib.import_module("app.api.router")
    importlib.reload(router_module)

    assert captured_prefixes[:5] == [
        "/auth",
        "/analysis",
        "/reports",
        "/users",
        "/preferences",
    ]


def test_celery_app_registers_analysis_task(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_required_env(monkeypatch)
    celery_module = importlib.import_module("app.tasks.celery_app")
    celery_module = importlib.reload(celery_module)

    assert "analysis.process_image" in celery_module.celery_app.tasks
    if os.name == "nt":
        assert celery_module.celery_app.conf.worker_pool == "solo"
        assert celery_module.celery_app.conf.worker_concurrency == 1


def test_dependencies_get_current_user(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_required_env(monkeypatch)
    dependencies_module = importlib.import_module("app.dependencies")
    dependencies_module = importlib.reload(dependencies_module)

    fake_user = SimpleNamespace(is_active=True)
    fake_result = SimpleNamespace(scalar_one_or_none=lambda: fake_user)
    fake_session = AsyncMock()
    fake_session.execute.return_value = fake_result

    monkeypatch.setattr(
        dependencies_module,
        "decode_token",
        lambda token: {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "type": "access",
        },
    )

    user = asyncio.run(
        dependencies_module.get_current_user(token="token", db=fake_session)
    )
    assert user is fake_user


def test_dependencies_get_current_user_rejects_non_access_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _load_required_env(monkeypatch)
    dependencies_module = importlib.import_module("app.dependencies")
    dependencies_module = importlib.reload(dependencies_module)

    fake_session = AsyncMock()
    monkeypatch.setattr(
        dependencies_module,
        "decode_token",
        lambda token: {
            "sub": "550e8400-e29b-41d4-a716-446655440000",
            "type": "refresh",
        },
    )

    with pytest.raises(TokenInvalidError):
        asyncio.run(
            dependencies_module.get_current_user(token="token", db=fake_session)
        )


def test_dependencies_oauth2_scheme_uses_settings_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _load_required_env(monkeypatch, API_V1_PREFIX="/api/custom")
    dependencies_module = importlib.import_module("app.dependencies")
    dependencies_module = importlib.reload(dependencies_module)

    assert (
        dependencies_module.oauth2_scheme.model.flows.password.tokenUrl
        == "/api/custom/auth/login"
    )


def test_main_health_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_required_env(monkeypatch, SKIP_STARTUP_CHECKS="true")
    main_module = importlib.import_module("app.main")
    main_module = importlib.reload(main_module)
    monkeypatch.setattr(
        main_module,
        "_run_with_timeout",
        AsyncMock(side_effect=["up", "up", "up", "up", "up", "up", "up"]),
    )

    with TestClient(main_module.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 0
    assert payload["message"] == "健康检查完成"
    assert payload["data"]["status"] == "healthy"
    assert payload["data"]["version"] == "1.0.0"
    assert payload["data"]["timestamp"].endswith("Z")
    assert payload["data"]["services"] == {
        "database": "up",
        "redis": "up",
        "minio": "up",
        "yolo_model": "up",
        "chromadb": "up",
        "ollama_embedding": "up",
        "ocr_runtime": "up",
    }
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["X-XSS-Protection"] == "1; mode=block"
    assert main_module.app.title == "Food Label Analyzer API"
    assert main_module.app.docs_url == "/docs"
    assert main_module.app.redoc_url == "/redoc"


def test_main_health_endpoint_supports_request_id_and_hsts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _load_required_env(monkeypatch, SKIP_STARTUP_CHECKS="true")
    main_module = importlib.import_module("app.main")
    main_module = importlib.reload(main_module)
    monkeypatch.setattr(
        main_module,
        "_run_with_timeout",
        AsyncMock(side_effect=["down", "up", "up", "up", "up", "up", "up"]),
    )

    with TestClient(main_module.app, base_url="https://testserver") as client:
        response = client.get("/health", headers={"X-Request-ID": "req-123"})

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "degraded"
    assert response.headers["X-Request-ID"] == "req-123"
    assert (
        response.headers["Strict-Transport-Security"]
        == "max-age=31536000; includeSubDomains"
    )


def test_probe_ocr_runtime_uses_post_and_rejects_invalid_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _load_required_env(monkeypatch, SKIP_STARTUP_CHECKS="true")
    main_module = importlib.import_module("app.main")
    main_module = importlib.reload(main_module)

    calls: list[tuple[str, dict[str, str], dict[str, str]]] = []

    class FakeResponse:
        def __init__(self, status_code: int) -> None:
            self.status_code = status_code

    class FakeAsyncClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url: str, headers: dict[str, str], data: dict[str, str]):
            calls.append((url, headers, data))
            return FakeResponse(405)

    monkeypatch.setattr(
        main_module.httpx, "AsyncClient", lambda *args, **kwargs: FakeAsyncClient()
    )

    with pytest.raises(RuntimeError):
        asyncio.run(main_module._probe_ocr_runtime())

    assert calls == [
        (
            "https://paddle-ocr.example.com/api/v1/ocr/job",
            {"Authorization": "bearer paddle-token"},
            {"model": "PaddleOCR-VL-1.5"},
        )
    ]
