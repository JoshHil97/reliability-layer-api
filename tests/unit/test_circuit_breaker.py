from __future__ import annotations

import pytest

from app.core.circuit_breaker import BreakerConfig, BreakerState, CircuitBreaker


@pytest.mark.asyncio
async def test_breaker_opens_after_threshold():
    now = {"value": 0.0}
    breaker = CircuitBreaker(
        BreakerConfig(failure_threshold=2, reset_timeout_s=5.0),
        clock=lambda: now["value"],
    )

    assert await breaker.allow() is True
    await breaker.on_failure()
    assert await breaker.state() == BreakerState.CLOSED

    await breaker.on_failure()
    assert await breaker.state() == BreakerState.OPEN
    assert await breaker.allow() is False


@pytest.mark.asyncio
async def test_breaker_half_open_then_closes_on_success():
    now = {"value": 0.0}
    breaker = CircuitBreaker(
        BreakerConfig(failure_threshold=1, reset_timeout_s=5.0),
        clock=lambda: now["value"],
    )

    await breaker.on_failure()
    assert await breaker.state() == BreakerState.OPEN

    now["value"] = 5.0
    assert await breaker.allow() is True
    assert await breaker.state() == BreakerState.HALF_OPEN

    await breaker.on_success()
    assert await breaker.state() == BreakerState.CLOSED
