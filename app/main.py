from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.adapters.redis_client import close_redis, create_redis_client
from app.api.routes import health, proxy
from app.core.cache import ResponseCache, ValueStore, build_cache_store
from app.core.circuit_breaker import BreakerConfig, CircuitBreakerRegistry
from app.core.config import Settings
from app.core.http_client import HttpClient
from app.core.logging import configure_logging, install_request_logging
from app.core.rate_limit import FixedWindowRateLimiter, RateLimitStore, build_rate_limit_store


def create_app(
    *,
    settings: Settings | None = None,
    http_transport: Any = None,
    cache_store: ValueStore | None = None,
    rate_limit_store: RateLimitStore | None = None,
) -> FastAPI:
    configure_logging()
    app_settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        redis_client = None
        redis_error = None
        if app_settings.redis_url:
            try:
                redis_client = create_redis_client(app_settings.redis_url)
                await redis_client.ping()
            except Exception as exc:
                redis_error = str(exc)
                await close_redis(redis_client)
                redis_client = None

        app.state.settings = app_settings
        app.state.redis = redis_client
        app.state.redis_error = redis_error
        app.state.http_client = HttpClient(app_settings, transport=http_transport)
        app.state.cache = ResponseCache(cache_store or build_cache_store(redis_client))
        app.state.rate_limiter = FixedWindowRateLimiter(
            rate_limit_store or build_rate_limit_store(redis_client)
        )
        app.state.breakers = CircuitBreakerRegistry(
            BreakerConfig(
                failure_threshold=app_settings.breaker_failure_threshold,
                reset_timeout_s=app_settings.breaker_reset_timeout_s,
                half_open_max_calls=app_settings.breaker_half_open_max_calls,
            )
        )
        yield
        await app.state.http_client.aclose()
        await close_redis(redis_client)

    app = FastAPI(title="Reliability Layer API", lifespan=lifespan)
    install_request_logging(app)
    app.include_router(health.router)
    app.include_router(proxy.router)

    @app.get("/metrics", include_in_schema=False)
    async def metrics() -> Response:
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
