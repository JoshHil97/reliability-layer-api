from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from typing import Protocol

from redis.asyncio import Redis


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    current_count: int
    remaining: int
    retry_after_s: int


class RateLimitStore(Protocol):
    async def increment(self, key: str, window_s: int) -> tuple[int, int]: ...


class InMemoryRateLimitStore:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    async def increment(self, key: str, window_s: int) -> tuple[int, int]:
        async with self._lock:
            now = time.monotonic()
            count, expires_at = self._entries.get(key, (0, now + window_s))
            if expires_at <= now:
                count = 0
                expires_at = now + window_s
            count += 1
            self._entries[key] = (count, expires_at)
            ttl = max(1, math.ceil(expires_at - now))
            return count, ttl


class RedisRateLimitStore:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def increment(self, key: str, window_s: int) -> tuple[int, int]:
        count = await self._client.incr(key)
        if count == 1:
            await self._client.expire(key, window_s)
            return count, window_s
        ttl = await self._client.ttl(key)
        if ttl is None or ttl < 0:
            await self._client.expire(key, window_s)
            ttl = window_s
        return count, int(ttl)


class FixedWindowRateLimiter:
    def __init__(self, store: RateLimitStore) -> None:
        self._store = store

    async def check(self, scope: str, *, limit: int, window_s: int) -> RateLimitResult:
        count, ttl = await self._store.increment(f"rl:limit:{scope}", window_s)
        allowed = count <= limit
        remaining = max(0, limit - count)
        retry_after_s = 0 if allowed else ttl
        return RateLimitResult(
            allowed=allowed,
            current_count=count,
            remaining=remaining,
            retry_after_s=retry_after_s,
        )


def build_rate_limit_store(redis_client: Redis | None) -> RateLimitStore:
    if redis_client is not None:
        return RedisRateLimitStore(redis_client)
    return InMemoryRateLimitStore()
