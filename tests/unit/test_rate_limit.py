from __future__ import annotations

import asyncio

import pytest

from app.core.rate_limit import FixedWindowRateLimiter, InMemoryRateLimitStore


@pytest.mark.asyncio
async def test_rate_limiter_enforces_limit_atomically():
    limiter = FixedWindowRateLimiter(InMemoryRateLimitStore())

    results = await asyncio.gather(
        *[limiter.check("client:upsim", limit=3, window_s=60) for _ in range(5)]
    )

    assert sum(result.allowed for result in results) == 3
    assert sum(not result.allowed for result in results) == 2
    assert all(result.retry_after_s >= 0 for result in results)
