from __future__ import annotations

import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import httpx

IDEMPOTENT_METHODS = {"DELETE", "GET", "HEAD", "OPTIONS", "PUT"}
RETRYABLE_STATUS_CODES = {502, 503, 504}


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_s: float = 0.1
    max_delay_s: float = 1.0


def has_idempotency_key(headers: Mapping[str, str] | None) -> bool:
    if not headers:
        return False
    return any(key.lower() == "idempotency-key" and bool(value) for key, value in headers.items())


def is_retryable_method(method: str, headers: Mapping[str, str] | None = None) -> bool:
    method_upper = method.upper()
    if method_upper in IDEMPOTENT_METHODS:
        return True
    if method_upper in {"PATCH", "POST"}:
        return has_idempotency_key(headers)
    return False


def should_retry(
    method: str,
    exception: Exception | None,
    response: httpx.Response | None,
    headers: Mapping[str, str] | None = None,
    *,
    retry_on_429: bool = False,
) -> bool:
    if not is_retryable_method(method, headers):
        return False

    if exception is not None:
        return isinstance(
            exception,
            (
                httpx.ConnectError,
                httpx.NetworkError,
                httpx.RemoteProtocolError,
                httpx.TimeoutException,
            ),
        )

    if response is None:
        return False

    if response.status_code in RETRYABLE_STATUS_CODES:
        return True
    if response.status_code == 429 and retry_on_429:
        return True
    return False


def backoff_with_jitter(
    policy: RetryPolicy,
    attempt: int,
    *,
    rng: Callable[[], float] = random.random,
) -> float:
    cap = min(policy.max_delay_s, policy.base_delay_s * (2 ** max(attempt - 1, 0)))
    return rng() * cap
