from __future__ import annotations

import httpx

from app.core.circuit_breaker import CircuitOpenError


def map_upstream_exception_to_status(exc: Exception) -> int:
    if isinstance(exc, CircuitOpenError):
        return 503
    if isinstance(exc, httpx.TimeoutException):
        return 504
    if isinstance(exc, (httpx.ConnectError, httpx.NetworkError, httpx.RemoteProtocolError)):
        return 502
    return 502


def is_breaker_failure_status(status_code: int) -> bool:
    return 500 <= status_code <= 599
