from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- App ---
    APP_ENV: str = "development"
    APP_DEBUG: bool = True
    APP_SECRET_KEY: SecretStr
    API_V1_PREFIX: str = "/api/v1"
    FRONTEND_URL: str = "http://localhost:3000"
    SKIP_STARTUP_CHECKS: bool = False
    HEALTH_CHECK_EXTERNAL: bool = True

    # --- Database ---
    DATABASE_URL: str
    DATABASE_SYNC_URL: str

    # --- Redis ---
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # --- MinIO ---
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: SecretStr
    MINIO_USE_SSL: bool = False
    MINIO_BUCKET_NAME: str = "food-analyzer"

    # --- PaddleOCR (在线 API) ---
    PADDLEOCR_JOB_URL: str = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
    PADDLEOCR_TOKEN: SecretStr = SecretStr("")
    PADDLEOCR_MODEL: str = "PaddleOCR-VL-1.5"
    PADDLEOCR_NUTRITION_MODEL: str = "PP-StructureV3"
    PADDLEOCR_OTHER_MODEL: str = "PaddleOCR-VL-1.5"

    # Detection params
    PADDLEOCR_DET_DB_BOX_THRESH: float = 0.5
    PADDLEOCR_DET_DB_UNCLIP_RATIO: float = 1.8
    PADDLEOCR_TEXT_DET_LIMIT_SIDE_LEN: int = 960
    PADDLEOCR_TEXT_DET_LIMIT_TYPE: str = "max"
    PADDLEOCR_TEXT_DET_THESH: float = 0.3

    # Preprocessing
    PADDLEOCR_USE_DOC_ORIENTATION_CLASSIFY: bool = True
    PADDLEOCR_USE_DOC_UNWARPING: bool = True
    PADDLEOCR_USE_TEXTLINE_ORIENTATION: bool = True

    # Table recognition
    PADDLEOCR_USE_TABLE_RECOGNITION: bool = True
    PADDLEOCR_USE_E2E_WIRED_TABLE_REC_MODEL: bool = False
    PADDLEOCR_USE_E2E_WIRELESS_TABLE_REC_MODEL: bool = True

    # Timing
    PADDLEOCR_POLL_INTERVAL_S: float = 5.0
    PADDLEOCR_POLL_TIMEOUT_S: float = 300.0
    PADDLEOCR_REQUEST_TIMEOUT_S: float = 60.0

    # --- DeepSeek ---
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_API_KEY: SecretStr
    DEEPSEEK_MODEL: str = "deepseek-chat"
    DEEPSEEK_TIMEOUT: int = 120
    DEEPSEEK_TEMPERATURE: float = 0.0
    DEEPSEEK_MAX_RETRIES: int = 2
    DEEPSEEK_MAX_TOKENS: int = 600

    # --- Ollama ---
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_EMBEDDING_MODEL: str = "qwen3-embedding:latest"
    OLLAMA_EMBEDDING_TIMEOUT_S: float = 30.0

    # --- ChromaDB ---
    CHROMADB_PATH: str = "./chroma_data"
    CHROMADB_COLLECTION_INGREDIENTS: str = "gb2760_a1_grouped"
    CHROMADB_COLLECTION_STANDARDS: str = "gb2760_a1_grouped"

    # --- YOLO (ultralytics) ---
    YOLO_MODEL_PATH: str = "./models_store/yolo/yolo26s.onnx"
    YOLO_CONFIDENCE_THRESHOLD: float = 0.7
    YOLO_INPUT_SIZE: int = 640
    YOLO_SELECT_TOP_K: int = 5
    YOLO_CROP_PADDING: int = 10

    # --- Scoring Weights ---
    SCORE_WEIGHT_NUTRITION: float = 0.30
    SCORE_WEIGHT_SODIUM: float = 0.25
    SCORE_WEIGHT_ADDITIVES: float = 0.20
    SCORE_WEIGHT_ALLERGENS: float = 0.15
    SCORE_WEIGHT_SUGAR: float = 0.10

    # --- Ingredient Extraction ---
    INGREDIENT_TEXT_LIMIT: int = 500
    INGREDIENT_MIN_TERM_LENGTH: int = 2

    # --- RAG Retrieval ---
    RAG_TOP_K_INGREDIENTS: int = 5
    RAG_TOP_K_STANDARDS: int = 10

    # --- JWT ---
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # --- SMTP ---
    SMTP_HOST: str
    SMTP_PORT: int = 587
    SMTP_USERNAME: str
    SMTP_PASSWORD: SecretStr
    SMTP_FROM_NAME: str = "Food Label Analyzer"
    SMTP_FROM_EMAIL: str
    SMTP_USE_TLS: bool = True

    # --- Verification Code ---
    # DOC-01 does not define explicit variable names for this group yet.

    # --- Task ---
    USER_MAX_CONCURRENT_TASKS: int = 3

    # --- Upload ---
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_IMAGE_TYPES: str = "image/jpeg,image/png,image/webp"

    # --- CORS ---
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # --- Logging ---
    LOG_LEVEL: str = "DEBUG"
    LOG_FORMAT: str = "console"
    SENTRY_DSN: str = ""

    @property
    def is_development(self) -> bool:
        return self.APP_ENV == "development"

    @property
    def jwt_access_expire_timedelta(self) -> timedelta:
        return timedelta(minutes=self.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    @property
    def jwt_refresh_expire_timedelta(self) -> timedelta:
        return timedelta(days=self.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def allowed_image_types_list(self) -> list[str]:
        return [item.strip() for item in self.ALLOWED_IMAGE_TYPES.split(",") if item.strip()]

    @property
    def cors_origins_list(self) -> list[str]:
        if self.CORS_ORIGINS.strip() == "*":
            return ["*"]
        return [item.strip() for item in self.CORS_ORIGINS.split(",") if item.strip()]

    @field_validator("APP_SECRET_KEY")
    @classmethod
    def validate_app_secret_key(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("APP_SECRET_KEY length must be at least 32 characters")
        return value

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if not value.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must start with postgresql+asyncpg://")
        return value

    @field_validator("DATABASE_SYNC_URL")
    @classmethod
    def validate_database_sync_url(cls, value: str) -> str:
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("DATABASE_SYNC_URL must start with postgresql+psycopg://")
        return value

    @field_validator("REDIS_URL")
    @classmethod
    def validate_redis_url(cls, value: str) -> str:
        if not value.startswith("redis://"):
            raise ValueError("REDIS_URL must start with redis://")
        return value

    @field_validator("YOLO_CONFIDENCE_THRESHOLD")
    @classmethod
    def validate_yolo_confidence_threshold(cls, value: float) -> float:
        if not 0 < value < 1:
            raise ValueError("YOLO_CONFIDENCE_THRESHOLD must be between 0 and 1")
        return value

    @field_validator("SMTP_PORT")
    @classmethod
    def validate_smtp_port(cls, value: int) -> int:
        if value not in {25, 465, 587, 2525}:
            raise ValueError("SMTP_PORT must be one of 25, 465, 587, 2525")
        return value

    @field_validator("MAX_UPLOAD_SIZE_MB")
    @classmethod
    def validate_max_upload_size_mb(cls, value: int) -> int:
        if not 1 <= value <= 50:
            raise ValueError("MAX_UPLOAD_SIZE_MB must be between 1 and 50")
        return value


@lru_cache()
def get_settings() -> Settings:
    return Settings()


__all__ = ["Settings", "get_settings"]
