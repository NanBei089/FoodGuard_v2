from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import chromadb
import httpx
import structlog
import structlog.contextvars
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from minio import Minio
from sqlalchemy import text

from app.api.router import api_router
from app.core.config import Settings, get_settings
from app.core.error_handlers import register_exception_handlers
from app.core.logging import setup_logging
from app.db.redis import close_redis, get_redis
from app.db.session import get_engine
from app.schemas.common import ApiResponse, success_response
from app.schemas.health import HealthCheckResponse, HealthServicesSchema


APP_VERSION = "1.0.0"
HEALTH_TIMEOUT_SECONDS = 2

settings = get_settings()
logger = structlog.get_logger(__name__)


def _redact_url(url: str) -> str:
    parsed = urlsplit(url)
    if not parsed.username and not parsed.password:
        return url

    auth = parsed.username or ""
    auth = f"{auth}:***" if auth else "***"

    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"

    netloc = f"{auth}@{host}" if host else auth
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def _build_config_summary(current_settings: Settings) -> dict[str, str | bool]:
    return {
        "app_env": current_settings.APP_ENV,
        "app_debug": current_settings.APP_DEBUG,
        "database_url": _redact_url(current_settings.DATABASE_URL),
        "redis_url": current_settings.REDIS_URL,
        "minio_endpoint": current_settings.MINIO_ENDPOINT,
        "deepseek_model": current_settings.DEEPSEEK_MODEL,
        "ollama_base_url": current_settings.OLLAMA_BASE_URL,
        "chromadb_path": current_settings.CHROMADB_PATH,
        "yolo_model_path": current_settings.YOLO_MODEL_PATH,
        "log_level": current_settings.LOG_LEVEL,
        "log_format": current_settings.LOG_FORMAT,
    }


def _create_minio_client() -> Minio:
    current_settings = get_settings()
    return Minio(
        endpoint=current_settings.MINIO_ENDPOINT,
        access_key=current_settings.MINIO_ACCESS_KEY,
        secret_key=current_settings.MINIO_SECRET_KEY.get_secret_value(),
        secure=current_settings.MINIO_USE_SSL,
    )


async def _check_database_connection() -> None:
    engine = get_engine()
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    logger.info("database_connection_ok")


async def _check_redis_connection() -> None:
    redis_client = await get_redis()
    await redis_client.ping()
    logger.info("redis_connection_ok")


async def _ensure_minio_bucket() -> None:
    current_settings = get_settings()
    client = _create_minio_client()
    bucket_exists = await asyncio.to_thread(client.bucket_exists, current_settings.MINIO_BUCKET_NAME)
    if bucket_exists:
        logger.info("minio_bucket_exists", bucket=current_settings.MINIO_BUCKET_NAME)
        return

    await asyncio.to_thread(client.make_bucket, current_settings.MINIO_BUCKET_NAME)
    logger.info("minio_bucket_created", bucket=current_settings.MINIO_BUCKET_NAME)


def _check_yolo_model_file() -> None:
    model_path = Path(get_settings().YOLO_MODEL_PATH)
    if model_path.exists():
        logger.info("yolo_model_exists", path=str(model_path))
    else:
        logger.warning("yolo_model_missing", path=str(model_path))


def _check_chromadb_directory() -> None:
    chroma_path = Path(get_settings().CHROMADB_PATH)
    if chroma_path.exists():
        logger.info("chromadb_path_exists", path=str(chroma_path))
    else:
        logger.warning("chromadb_path_missing", path=str(chroma_path))


async def _run_startup_checks() -> None:
    await _check_database_connection()
    await _check_redis_connection()
    await _ensure_minio_bucket()
    _check_yolo_model_file()
    _check_chromadb_directory()


async def _run_with_timeout(check_name: str, probe) -> str:
    try:
        await asyncio.wait_for(probe(), timeout=HEALTH_TIMEOUT_SECONDS)
        return "up"
    except Exception as exc:
        logger.warning("health_probe_failed", service=check_name, error=str(exc))
        return "down"


async def _probe_database() -> None:
    await _check_database_connection()


async def _probe_redis() -> None:
    await _check_redis_connection()


async def _probe_minio() -> None:
    current_settings = get_settings()
    await asyncio.to_thread(_create_minio_client().bucket_exists, current_settings.MINIO_BUCKET_NAME)


async def _probe_yolo_model() -> None:
    if not Path(get_settings().YOLO_MODEL_PATH).exists():
        raise FileNotFoundError(get_settings().YOLO_MODEL_PATH)


async def _probe_chromadb() -> None:
    current_settings = get_settings()
    client = chromadb.PersistentClient(path=current_settings.CHROMADB_PATH)
    collection = client.get_collection(name=current_settings.CHROMADB_COLLECTION_INGREDIENTS)
    count = collection.count()
    if count <= 0:
        raise RuntimeError("collection is empty")


async def _probe_ollama_embedding() -> None:
    current_settings = get_settings()
    if not current_settings.HEALTH_CHECK_EXTERNAL:
        return
    async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT_SECONDS) as client:
        response = await client.get(f"{current_settings.OLLAMA_BASE_URL.rstrip('/')}/api/tags")
        response.raise_for_status()


async def _probe_ocr_runtime() -> None:
    current_settings = get_settings()
    if not current_settings.HEALTH_CHECK_EXTERNAL:
        return
    headers: dict[str, str] = {}
    token = current_settings.PADDLEOCR_TOKEN.get_secret_value()
    if token:
        headers["Authorization"] = f"bearer {token}"
    async with httpx.AsyncClient(timeout=HEALTH_TIMEOUT_SECONDS, follow_redirects=True) as client:
        response = await client.post(
            current_settings.PADDLEOCR_JOB_URL,
            headers=headers,
            data={"model": current_settings.PADDLEOCR_MODEL},
        )
        if response.status_code not in {200, 400, 415, 422, 429}:
            raise RuntimeError(
                f"OCR runtime endpoint failed: {current_settings.PADDLEOCR_JOB_URL} "
                f"(HTTP {response.status_code})",
            )


async def _build_health_payload() -> HealthCheckResponse:
    services = HealthServicesSchema(
        database=await _run_with_timeout("database", _probe_database),
        redis=await _run_with_timeout("redis", _probe_redis),
        minio=await _run_with_timeout("minio", _probe_minio),
        yolo_model=await _run_with_timeout("yolo_model", _probe_yolo_model),
        chromadb=await _run_with_timeout("chromadb", _probe_chromadb),
        ollama_embedding=await _run_with_timeout("ollama_embedding", _probe_ollama_embedding),
        ocr_runtime=await _run_with_timeout("ocr_runtime", _probe_ocr_runtime),
    )
    overall = "healthy" if all(value == "up" for value in services.model_dump().values()) else "degraded"
    return HealthCheckResponse(
        status=overall,
        timestamp=datetime.now(timezone.utc),
        version=APP_VERSION,
        services=services,
    )


def _is_https_request(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").lower() == "https"


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging(settings.LOG_LEVEL, settings.LOG_FORMAT)
    logger.info("application_config_summary", **_build_config_summary(settings))

    if settings.SKIP_STARTUP_CHECKS:
        logger.info("startup_checks_skipped")
    else:
        await _run_startup_checks()

    logger.info("application_started")
    try:
        yield
    finally:
        await get_engine().dispose()
        await close_redis()
        logger.info("application_stopped")


app = FastAPI(
    title="Food Label Analyzer API",
    version=APP_VERSION,
    description="Backend infrastructure for nutrition label image upload and analysis.",
    lifespan=lifespan,
    docs_url="/docs" if settings.is_development else None,
    redoc_url="/redoc" if settings.is_development else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or uuid4().hex
    request.state.request_id = request_id
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)
    try:
        response = await call_next(request)
    finally:
        structlog.contextvars.clear_contextvars()
    response.headers["X-Request-ID"] = request_id
    return response


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    if _is_https_request(request):
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


register_exception_handlers(app)
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get(
    "/health",
    response_model=ApiResponse[HealthCheckResponse],
    summary="健康检查",
    description="返回应用及依赖服务的实时健康状态。",
    responses={200: {"description": "健康检查结果"}},
)
async def health() -> ApiResponse[HealthCheckResponse]:
    return success_response(await _build_health_payload(), message="健康检查完成")


__all__ = ["app", "lifespan"]
