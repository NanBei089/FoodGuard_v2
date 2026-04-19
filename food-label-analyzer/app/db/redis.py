from __future__ import annotations

from redis.asyncio import Redis, from_url

from app.core.config import get_settings

"""Redis 客户端与常用缓存操作。"""

_redis_client: Redis | None = None


async def get_redis() -> Redis:
    """返回进程级 Redis 客户端。"""
    global _redis_client
    if _redis_client is None:
        settings = get_settings()
        _redis_client = from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


async def close_redis() -> None:
    """关闭 Redis 连接。"""
    global _redis_client
    if _redis_client is None:
        return
    await _redis_client.aclose()
    _redis_client = None


async def set_with_ttl(key: str, value: str, ttl_seconds: int) -> None:
    """写入带过期时间的字符串值。"""
    client = await get_redis()
    await client.set(key, value, ex=ttl_seconds)


async def get_value(key: str) -> str | None:
    """读取字符串值。"""
    client = await get_redis()
    return await client.get(key)


async def get_ttl(key: str) -> int:
    """读取 key 剩余 TTL。"""
    client = await get_redis()
    return await client.ttl(key)


async def exists(key: str) -> bool:
    """判断 key 是否存在。"""
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
