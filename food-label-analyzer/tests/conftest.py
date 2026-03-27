from __future__ import annotations

import pytest

from app.core.config import Settings, get_settings

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


@pytest.fixture(autouse=True)
def isolate_settings_from_dotenv() -> None:
    original_env_file = Settings.model_config.get("env_file")
    Settings.model_config["env_file"] = None
    get_settings.cache_clear()
    try:
        yield
    finally:
        Settings.model_config["env_file"] = original_env_file
        get_settings.cache_clear()


def clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    get_settings.cache_clear()
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name, raising=False)


def load_required_env(
    monkeypatch: pytest.MonkeyPatch, **overrides: str
) -> dict[str, str]:
    clear_settings_env(monkeypatch)
    values = {**REQUIRED_ENV_VARS, **overrides}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values
