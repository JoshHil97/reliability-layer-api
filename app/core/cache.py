from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Protocol

from redis.asyncio import Redis


def _normalise_params(params: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    return sorted((str(key), str(value)) for key, value in params)


def cache_key(
    method: str,
    url: str,
    params: Iterable[tuple[str, str]],
    body: bytes | None,
) -> str:
    digest = hashlib.sha256()
    digest.update(method.upper().encode())
    digest.update(b"|")
    digest.update(url.encode())
    digest.update(b"|")
    digest.update(json.dumps(_normalise_params(params)).encode())
    digest.update(b"|")
    digest.update(body or b"")
    return f"rl:cache:{digest.hexdigest()}"


@dataclass(frozen=True)
class CacheEntry:
    status_code: int
    headers: dict[str, str]
    body_b64: str
    stored_at: float

    @classmethod
    def from_parts(
        cls,
        *,
        status_code: int,
        headers: Mapping[str, str],
        body: bytes,
    ) -> CacheEntry:
        return cls(
            status_code=status_code,
            headers=dict(headers),
            body_b64=base64.b64encode(body).decode(),
            stored_at=time.time(),
        )

    @property
    def body(self) -> bytes:
        return base64.b64decode(self.body_b64.encode())

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, payload: str) -> CacheEntry:
        data = json.loads(payload)
        return cls(**data)


class ValueStore(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, ttl_s: int) -> None: ...


class InMemoryValueStore:
    def __init__(self) -> None:
        self._values: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        async with self._lock:
            entry = self._values.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at <= time.monotonic():
                self._values.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        async with self._lock:
            self._values[key] = (value, time.monotonic() + ttl_s)


class RedisValueStore:
    def __init__(self, client: Redis) -> None:
        self._client = client

    async def get(self, key: str) -> str | None:
        return await self._client.get(key)

    async def set(self, key: str, value: str, ttl_s: int) -> None:
        await self._client.set(key, value, ex=ttl_s)


class ResponseCache:
    def __init__(self, store: ValueStore) -> None:
        self._store = store

    async def get_fresh(self, key: str) -> CacheEntry | None:
        payload = await self._store.get(f"{key}:fresh")
        if payload is None:
            return None
        return CacheEntry.from_json(payload)

    async def get_stale(self, key: str) -> CacheEntry | None:
        payload = await self._store.get(f"{key}:stale")
        if payload is None:
            return None
        return CacheEntry.from_json(payload)

    async def set(self, key: str, entry: CacheEntry, *, ttl_s: int, stale_ttl_s: int) -> None:
        if ttl_s > 0:
            await self._store.set(f"{key}:fresh", entry.to_json(), ttl_s)
        if stale_ttl_s > 0:
            await self._store.set(f"{key}:stale", entry.to_json(), stale_ttl_s)


def build_cache_store(redis_client: Redis | None) -> ValueStore:
    if redis_client is not None:
        return RedisValueStore(redis_client)
    return InMemoryValueStore()
