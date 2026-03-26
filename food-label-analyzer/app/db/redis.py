from __future__ import annotations

from redis.asyncio import Redis
from redis.asyncio import from_url

from app.core.config import get_settings


_redis_client: Redis | None = None


async def get_redis() -> Redis:
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def close_redis() -> None:
    global _redis_client
    if _redis_client is None:
        return
    await _redis_client.aclose()
    _redis_client = None


async def set_with_ttl(key: str, value: str, ttl_seconds: int) -> None:
    client = await get_redis()
    await client.set(key, value, ex=ttl_seconds)


async def get_value(key: str) -> str | None:
    client = await get_redis()
    return await client.get(key)


async def get_ttl(key: str) -> int:
    client = await get_redis()
    return await client.ttl(key)


async def exists(key: str) -> bool:
    client = await get_redis()
    return bool(await client.exists(key))


__all__ = [
    "close_redis",
    "exists",
    "get_redis",
    "get_ttl",
    "get_value",
    "set_with_ttl",
]
