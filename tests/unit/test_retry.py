from __future__ import annotations

import httpx

from app.core.retry import RetryPolicy, backoff_with_jitter, should_retry


def test_retryable_status_for_get():
    response = httpx.Response(503)
    assert should_retry("GET", None, response)


def test_post_requires_idempotency_key():
    response = httpx.Response(503)
    assert not should_retry("POST", None, response, {})
    assert should_retry("POST", None, response, {"Idempotency-Key": "abc123"})


def test_timeout_exception_is_retryable_for_get():
    request = httpx.Request("GET", "http://upstream.local/ok")
    exc = httpx.ReadTimeout("timeout", request=request)
    assert should_retry("GET", exc, None)


def test_backoff_with_jitter_uses_cap():
    delay = backoff_with_jitter(
        RetryPolicy(base_delay_s=0.5, max_delay_s=1.0),
        attempt=3,
        rng=lambda: 1.0,
    )
    assert delay == 1.0
