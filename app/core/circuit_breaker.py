from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from app.core.metrics import set_breaker_state


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(RuntimeError):
    """Raised when a breaker is open and the request must fail fast."""


@dataclass(frozen=True)
class BreakerConfig:
    failure_threshold: int = 5
    reset_timeout_s: float = 20.0
    half_open_max_calls: int = 1


class CircuitBreaker:
    def __init__(
        self,
        config: BreakerConfig,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.config = config
        self._clock = clock
        self._state = BreakerState.CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._half_open_in_flight = 0
        self._lock = asyncio.Lock()

    async def allow(self) -> bool:
        async with self._lock:
            if self._state == BreakerState.CLOSED:
                return True

            if self._state == BreakerState.OPEN:
                if (self._clock() - self._opened_at) >= self.config.reset_timeout_s:
                    self._state = BreakerState.HALF_OPEN
                    self._half_open_in_flight = 0
                else:
                    return False

            if self._state == BreakerState.HALF_OPEN:
                if self._half_open_in_flight >= self.config.half_open_max_calls:
                    return False
                self._half_open_in_flight += 1
                return True

            return False

    async def on_success(self) -> None:
        async with self._lock:
            self._failures = 0
            self._half_open_in_flight = 0
            self._state = BreakerState.CLOSED

    async def on_failure(self) -> None:
        async with self._lock:
            self._failures += 1
            if (
                self._state == BreakerState.HALF_OPEN
                or self._failures >= self.config.failure_threshold
            ):
                self._state = BreakerState.OPEN
                self._opened_at = self._clock()
                self._half_open_in_flight = 0

    async def state(self) -> BreakerState:
        async with self._lock:
            return self._state


class CircuitBreakerRegistry:
    def __init__(self, config: BreakerConfig) -> None:
        self._config = config
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, upstream: str) -> CircuitBreaker:
        breaker = self._breakers.get(upstream)
        if breaker is None:
            breaker = CircuitBreaker(self._config)
            self._breakers[upstream] = breaker
            set_breaker_state(upstream, BreakerState.CLOSED.value)
        return breaker

    async def sync_metrics(self, upstream: str) -> None:
        breaker = self.get(upstream)
        set_breaker_state(upstream, (await breaker.state()).value)
