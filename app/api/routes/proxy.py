from __future__ import annotations

from collections.abc import Mapping

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.core.cache import CacheEntry, ResponseCache, cache_key
from app.core.circuit_breaker import CircuitBreakerRegistry, CircuitOpenError
from app.core.config import Settings, UpstreamSettings, get_settings
from app.core.errors import is_breaker_failure_status, map_upstream_exception_to_status
from app.core.http_client import HttpClient
from app.core.ids import request_id_from_headers
from app.core.metrics import (
    RL_CACHE_EVENTS_TOTAL,
    RL_RATE_LIMIT_REJECTIONS_TOTAL,
    RL_REQUESTS_TOTAL,
    RL_UPSTREAM_LATENCY_SECONDS,
)
from app.core.rate_limit import FixedWindowRateLimiter
from app.core.security import require_api_key

router = APIRouter(tags=["proxy"])

SAFE_FORWARD_HEADERS = {
    "accept",
    "accept-encoding",
    "content-type",
    "idempotency-key",
    "traceparent",
    "tracestate",
    "user-agent",
    "x-request-id",
}

SAFE_RESPONSE_HEADERS = {
    "cache-control",
    "content-type",
    "etag",
    "last-modified",
    "retry-after",
}


def _build_target_url(base_url: str, path: str) -> str:
    if path.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path must be relative to the configured upstream",
        )
    base = base_url.rstrip("/")
    suffix = path.lstrip("/")
    if not suffix:
        return base
    return f"{base}/{suffix}"


def _forward_request_headers(headers: Mapping[str, str], request_id: str) -> dict[str, str]:
    forwarded = {}
    for key, value in headers.items():
        if key.lower() in SAFE_FORWARD_HEADERS:
            forwarded[key] = value
    forwarded.setdefault("X-Request-Id", request_id)
    return forwarded


def _filter_response_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {key: value for key, value in headers.items() if key.lower() in SAFE_RESPONSE_HEADERS}


def _is_cacheable(method: str, upstream: UpstreamSettings) -> bool:
    return method.upper() == "GET" and upstream.cache_enabled


def _cached_response(entry: CacheEntry, *, request_id: str, cache_state: str) -> Response:
    headers = dict(entry.headers)
    headers["X-Reliability-Layer-Cache"] = cache_state
    headers["X-Request-Id"] = request_id
    return Response(content=entry.body, status_code=entry.status_code, headers=headers)


def _error_response(
    status_code: int,
    *,
    request_id: str,
    detail: str,
    retry_after: int | None = None,
) -> JSONResponse:
    headers = {"X-Request-Id": request_id}
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return JSONResponse(status_code=status_code, content={"detail": detail}, headers=headers)


@router.api_route(
    "/proxy/{upstream}/{path:path}",
    methods=["DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"],
)
async def proxy(
    upstream: str,
    path: str,
    request: Request,
    api_key: str = Depends(require_api_key),
    settings: Settings = Depends(get_settings),
) -> Response:
    upstream_name = upstream.lower()
    upstream_cfg = settings.upstreams.get(upstream_name)
    if upstream_cfg is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown upstream")

    method = request.method.upper()
    if method not in upstream_cfg.allowed_methods:
        raise HTTPException(
            status_code=status.HTTP_405_METHOD_NOT_ALLOWED,
            detail="Method not allowed for upstream",
        )

    request_id = getattr(request.state, "request_id", request_id_from_headers(request.headers))
    limiter: FixedWindowRateLimiter = request.app.state.rate_limiter
    limit_scope = f"{api_key}:{upstream_name}"
    limit_result = await limiter.check(
        limit_scope,
        limit=settings.rate_limit_per_minute,
        window_s=settings.rate_limit_window_s,
    )
    if not limit_result.allowed:
        RL_RATE_LIMIT_REJECTIONS_TOTAL.labels(scope=upstream_name).inc()
        RL_REQUESTS_TOTAL.labels(upstream=upstream_name, method=method, status="429").inc()
        return _error_response(
            429,
            request_id=request_id,
            detail="rate_limit_exceeded",
            retry_after=limit_result.retry_after_s,
        )

    url = _build_target_url(str(upstream_cfg.base_url), path)
    body = await request.body()
    params = list(request.query_params.multi_items())
    forwarded_headers = _forward_request_headers(request.headers, request_id)

    cache: ResponseCache = request.app.state.cache
    cache_lookup_key: str | None = None
    if _is_cacheable(method, upstream_cfg):
        cache_lookup_key = cache_key(method, url, params, body)
        cached = await cache.get_fresh(cache_lookup_key)
        if cached is not None:
            RL_CACHE_EVENTS_TOTAL.labels(upstream=upstream_name, result="fresh_hit").inc()
            RL_REQUESTS_TOTAL.labels(
                upstream=upstream_name,
                method=method,
                status=str(cached.status_code),
            ).inc()
            return _cached_response(cached, request_id=request_id, cache_state="fresh")
        RL_CACHE_EVENTS_TOTAL.labels(upstream=upstream_name, result="miss").inc()

    breakers: CircuitBreakerRegistry = request.app.state.breakers
    breaker = breakers.get(upstream_name)
    if not await breaker.allow():
        await breakers.sync_metrics(upstream_name)
        if cache_lookup_key is not None:
            stale = await cache.get_stale(cache_lookup_key)
            if stale is not None:
                RL_CACHE_EVENTS_TOTAL.labels(upstream=upstream_name, result="stale_hit").inc()
                RL_REQUESTS_TOTAL.labels(
                    upstream=upstream_name,
                    method=method,
                    status=str(stale.status_code),
                ).inc()
                return _cached_response(stale, request_id=request_id, cache_state="stale")
        RL_REQUESTS_TOTAL.labels(upstream=upstream_name, method=method, status="503").inc()
        return _error_response(
            503,
            request_id=request_id,
            detail="CircuitOpenError",
            retry_after=int(settings.breaker_reset_timeout_s),
        )

    client: HttpClient = request.app.state.http_client
    try:
        with RL_UPSTREAM_LATENCY_SECONDS.labels(upstream=upstream_name, method=method).time():
            upstream_response = await client.request_upstream(
                method=method,
                url=url,
                headers=forwarded_headers,
                params=params,
                content=body or None,
                upstream_name=upstream_name,
                timeout_s=upstream_cfg.timeout_s,
                retry_on_429=upstream_cfg.retry_on_429,
            )
    except Exception as exc:
        await breaker.on_failure()
        await breakers.sync_metrics(upstream_name)
        if cache_lookup_key is not None:
            stale = await cache.get_stale(cache_lookup_key)
            if stale is not None:
                RL_CACHE_EVENTS_TOTAL.labels(upstream=upstream_name, result="stale_hit").inc()
                RL_REQUESTS_TOTAL.labels(
                    upstream=upstream_name,
                    method=method,
                    status=str(stale.status_code),
                ).inc()
                return _cached_response(stale, request_id=request_id, cache_state="stale")
        status_code = map_upstream_exception_to_status(exc)
        RL_REQUESTS_TOTAL.labels(
            upstream=upstream_name,
            method=method,
            status=str(status_code),
        ).inc()
        retry_after = None
        if isinstance(exc, CircuitOpenError):
            retry_after = int(settings.breaker_reset_timeout_s)
        return _error_response(
            status_code,
            request_id=request_id,
            detail=type(exc).__name__,
            retry_after=retry_after,
        )

    if is_breaker_failure_status(upstream_response.status_code):
        await breaker.on_failure()
        await breakers.sync_metrics(upstream_name)
        if cache_lookup_key is not None:
            stale = await cache.get_stale(cache_lookup_key)
            if stale is not None:
                RL_CACHE_EVENTS_TOTAL.labels(upstream=upstream_name, result="stale_hit").inc()
                RL_REQUESTS_TOTAL.labels(
                    upstream=upstream_name,
                    method=method,
                    status=str(stale.status_code),
                ).inc()
                return _cached_response(stale, request_id=request_id, cache_state="stale")
    else:
        await breaker.on_success()
        await breakers.sync_metrics(upstream_name)

    headers = _filter_response_headers(upstream_response.headers)
    headers["X-Request-Id"] = request_id

    if cache_lookup_key is not None and 200 <= upstream_response.status_code < 300:
        entry = CacheEntry.from_parts(
            status_code=upstream_response.status_code,
            headers=headers,
            body=upstream_response.content,
        )
        await cache.set(
            cache_lookup_key,
            entry,
            ttl_s=upstream_cfg.cache_ttl_s,
            stale_ttl_s=upstream_cfg.stale_ttl_s,
        )
        RL_CACHE_EVENTS_TOTAL.labels(upstream=upstream_name, result="store").inc()

    RL_REQUESTS_TOTAL.labels(
        upstream=upstream_name,
        method=method,
        status=str(upstream_response.status_code),
    ).inc()
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=headers,
    )
