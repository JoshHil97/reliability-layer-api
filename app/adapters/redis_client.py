from __future__ import annotations

from redis.asyncio import Redis


def create_redis_client(redis_url: str) -> Redis:
    return Redis.from_url(redis_url, encoding="utf-8", decode_responses=True)


async def close_redis(client: Redis | None) -> None:
    if client is not None:
        await client.aclose()
