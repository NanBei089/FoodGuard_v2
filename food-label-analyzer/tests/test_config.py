from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings, get_settings


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE_PATH = PROJECT_ROOT / ".env.example"

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


def clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name, raising=False)


def load_required_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> dict[str, str]:
    clear_settings_env(monkeypatch)
    values = {**REQUIRED_ENV_VARS, **overrides}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


def parse_env_example() -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw_line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        parsed[key] = value
    return parsed


def test_settings_loads_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    env = load_required_env(
        monkeypatch,
        APP_ENV="production",
        APP_DEBUG="false",
        USER_MAX_CONCURRENT_TASKS="5",
    )

    settings = Settings()

    assert settings.APP_ENV == "production"
    assert settings.APP_DEBUG is False
    assert settings.DATABASE_URL == env["DATABASE_URL"]
    assert settings.USER_MAX_CONCURRENT_TASKS == 5
    assert settings.MINIO_ACCESS_KEY == "minioadmin"
    assert settings.OLLAMA_EMBEDDING_MODEL == "qwen3-embedding:latest"


def test_required_fields_raise_validation_error_when_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_settings_env(monkeypatch)

    with pytest.raises(ValidationError):
        Settings()


def test_secret_fields_are_stored_as_secret_str(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch)

    settings = Settings()

    assert isinstance(settings.APP_SECRET_KEY, SecretStr)
    assert isinstance(settings.DEEPSEEK_API_KEY, SecretStr)
    assert isinstance(settings.PADDLEOCR_TOKEN, SecretStr)
    assert isinstance(settings.MINIO_SECRET_KEY, SecretStr)
    assert isinstance(settings.SMTP_PASSWORD, SecretStr)
    assert settings.APP_SECRET_KEY.get_secret_value() == REQUIRED_ENV_VARS["APP_SECRET_KEY"]


def test_derived_properties_are_computed_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(
        monkeypatch,
        APP_ENV="development",
        JWT_ACCESS_TOKEN_EXPIRE_MINUTES="45",
        JWT_REFRESH_TOKEN_EXPIRE_DAYS="10",
        MAX_UPLOAD_SIZE_MB="12",
        ALLOWED_IMAGE_TYPES="image/jpeg, image/png, , image/webp ",
        CORS_ORIGINS=" http://localhost:3000, http://localhost:5173 , ",
    )

    settings = Settings()

    assert settings.is_development is True
    assert settings.jwt_access_expire_timedelta == timedelta(minutes=45)
    assert settings.jwt_refresh_expire_timedelta == timedelta(days=10)
    assert settings.max_upload_size_bytes == 12 * 1024 * 1024
    assert settings.allowed_image_types_list == ["image/jpeg", "image/png", "image/webp"]
    assert settings.cors_origins_list == ["http://localhost:3000", "http://localhost:5173"]


def test_cors_origins_list_supports_wildcard(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch, CORS_ORIGINS="*")

    settings = Settings()

    assert settings.cors_origins_list == ["*"]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("APP_SECRET_KEY", "short"),
        ("DATABASE_URL", "postgresql://postgres:password@localhost:5432/food_analyzer"),
        ("DATABASE_SYNC_URL", "postgresql+psycopg2://postgres:password@localhost:5432/food_analyzer"),
        ("REDIS_URL", "http://localhost:6379/0"),
        ("YOLO_CONFIDENCE_THRESHOLD", "1"),
        ("SMTP_PORT", "26"),
        ("MAX_UPLOAD_SIZE_MB", "0"),
    ],
)
def test_validation_rules_reject_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
    field_name: str,
    value: str,
) -> None:
    load_required_env(monkeypatch, **{field_name: value})

    with pytest.raises(ValidationError):
        Settings()


def test_get_settings_uses_cache_until_cleared(monkeypatch: pytest.MonkeyPatch) -> None:
    load_required_env(monkeypatch, APP_SECRET_KEY="a" * 32)

    first = get_settings()

    monkeypatch.setenv("APP_SECRET_KEY", "b" * 32)
    second = get_settings()

    assert first is second
    assert second.APP_SECRET_KEY.get_secret_value() == "a" * 32

    get_settings.cache_clear()
    refreshed = get_settings()

    assert refreshed is not first
    assert refreshed.APP_SECRET_KEY.get_secret_value() == "b" * 32


def test_env_example_keys_match_settings_fields() -> None:
    env_keys = set(parse_env_example())
    settings_keys = set(Settings.model_fields)

    assert env_keys == settings_keys


def test_env_example_contains_expected_defaults() -> None:
    env_values = parse_env_example()

    assert env_values["CHROMADB_COLLECTION_INGREDIENTS"] == "gb2760_a1_grouped"
    assert env_values["CHROMADB_COLLECTION_STANDARDS"] == "gb2760_a1_grouped"
    assert env_values["OLLAMA_EMBEDDING_MODEL"] == "qwen3-embedding:latest"
    assert env_values["USER_MAX_CONCURRENT_TASKS"] == "3"
    assert env_values["YOLO_INPUT_SIZE"] == "640"
    assert env_values["DEEPSEEK_MAX_RETRIES"] == "2"
