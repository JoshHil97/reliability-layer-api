from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

RL_REQUESTS_TOTAL = Counter(
    "rl_requests_total",
    "Requests handled by the reliability layer",
    ["upstream", "method", "status"],
)

RL_UPSTREAM_RETRIES_TOTAL = Counter(
    "rl_upstream_retries_total",
    "Retry attempts performed for upstream calls",
    ["upstream", "reason"],
)

RL_UPSTREAM_LATENCY_SECONDS = Histogram(
    "rl_upstream_latency_seconds",
    "Latency of upstream calls in seconds",
    ["upstream", "method"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.2, 0.5, 1, 2, 5),
)

RL_CACHE_EVENTS_TOTAL = Counter(
    "rl_cache_events_total",
    "Cache outcomes for request handling",
    ["upstream", "result"],
)

RL_RATE_LIMIT_REJECTIONS_TOTAL = Counter(
    "rl_rate_limit_rejections_total",
    "Requests rejected by local rate limiting",
    ["scope"],
)

RL_BREAKER_STATE = Gauge(
    "rl_breaker_state",
    "Circuit breaker state by upstream",
    ["upstream", "state"],
)

_BREAKER_STATES = ("closed", "open", "half_open")


def set_breaker_state(upstream: str, state: str) -> None:
    for candidate in _BREAKER_STATES:
        RL_BREAKER_STATE.labels(upstream=upstream, state=candidate).set(
            1 if candidate == state else 0
        )
