from __future__ import annotations

import asyncio
import io
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from minio import Minio
from minio.error import S3Error

from app.core.config import get_settings
from app.core.errors import StorageServiceError

"""对象存储服务，负责图片与分析产物的上传、删除和签名访问。"""

logger = structlog.get_logger(__name__)

_CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class StorageService:
    """MinIO 封装，屏蔽 bucket 初始化和错误映射细节。"""

    def __init__(self) -> None:
        settings = get_settings()
        self._bucket_name = settings.MINIO_BUCKET_NAME
        self._bucket_ready = False
        self._client = Minio(
            endpoint=settings.minio_client_endpoint,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY.get_secret_value(),
            secure=settings.MINIO_USE_SSL,
        )

    async def ensure_bucket(self) -> None:
        """确保 bucket 已可用。

        Returns:
            None: 初始化成功后会缓存 bucket_ready 状态。
        """
        if self._bucket_ready:
            return
        try:
            exists = await asyncio.to_thread(
                self._client.bucket_exists, self._bucket_name
            )
            if not exists:
                await asyncio.to_thread(self._client.make_bucket, self._bucket_name)
                logger.info("minio_bucket_created", bucket=self._bucket_name)
            else:
                logger.info("minio_bucket_exists", bucket=self._bucket_name)
            self._bucket_ready = True
        except Exception as exc:
            raise self._raise_storage_error("Failed to ensure bucket", exc)

    async def upload_image(
        self,
        file_bytes: bytes,
        user_id: str,
        content_type: str,
    ) -> tuple[str, str]:
        """上传原始图片并返回对象键与签名 URL。"""
        extension = _CONTENT_TYPE_EXTENSIONS.get(content_type)
        if extension is None:
            raise StorageServiceError("Unsupported image content type")

        image_key = self._build_object_key(user_id, extension)
        await self.ensure_bucket()
        try:
            await asyncio.to_thread(
                self._client.put_object,
                self._bucket_name,
                image_key,
                io.BytesIO(file_bytes),
                len(file_bytes),
                content_type=content_type,
            )
            image_url = await self.get_presigned_url(image_key)
            logger.info("image_uploaded", image_key=image_key, size=len(file_bytes))
            return image_key, image_url
        except Exception as exc:
            raise self._raise_storage_error("Failed to upload image", exc)

    async def upload_artifact(
        self, data: bytes, object_key: str, content_type: str
    ) -> str:
        """上传 OCR/表格等中间产物。"""
        await self.ensure_bucket()
        try:
            await asyncio.to_thread(
                self._client.put_object,
                self._bucket_name,
                object_key,
                io.BytesIO(data),
                len(data),
                content_type=content_type,
            )
            return await self.get_presigned_url(object_key)
        except Exception as exc:
            raise self._raise_storage_error("Failed to upload artifact", exc)

    async def get_presigned_url(self, image_key: str, expires: int = 3600) -> str:
        """生成临时可访问的签名 URL。"""
        try:
            return await asyncio.to_thread(
                self._client.get_presigned_url,
                "GET",
                self._bucket_name,
                image_key,
                expires=timedelta(seconds=expires),
            )
        except Exception as exc:
            raise self._raise_storage_error("Failed to create presigned URL", exc)

    async def delete_image(self, image_key: str) -> None:
        """删除对象存储中的图片。"""
        try:
            await asyncio.to_thread(
                self._client.remove_object, self._bucket_name, image_key
            )
            logger.info("image_deleted", image_key=image_key)
        except Exception as exc:
            raise self._raise_storage_error("Failed to delete image", exc)

    def _build_object_key(self, user_id: str, extension: str) -> str:
        """按用户和日期分层构造对象键，降低目录热点并便于排查。"""
        now = datetime.now(timezone.utc)
        return (
            f"uploads/{user_id}/{now.year:04d}/{now.month:02d}/{now.day:02d}/"
            f"{uuid.uuid4()}.{extension}"
        )

    def _raise_storage_error(self, message: str, exc: Exception) -> StorageServiceError:
        """统一记录存储异常并转换为业务层错误。"""
        logger.error(
            "storage_operation_failed",
            message=message,
            exception_type=exc.__class__.__name__,
            exception_message=str(exc),
        )
        if isinstance(exc, S3Error):
            return StorageServiceError(f"{message}: {exc.code}")
        return StorageServiceError(message)


_storage_service: StorageService | None = None


def get_storage_service() -> StorageService:
    """返回进程级单例 StorageService。"""
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service


__all__ = ["StorageService", "get_storage_service"]
