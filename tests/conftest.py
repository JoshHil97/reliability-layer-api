from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.core.cache import InMemoryValueStore
from app.core.config import Settings, UpstreamSettings
from app.core.rate_limit import InMemoryRateLimitStore
from app.main import create_app


def make_settings(**overrides) -> Settings:
    upstreams = overrides.pop(
        "upstreams",
        {
            "upsim": UpstreamSettings(
                name="upsim",
                base_url="http://upstream.local",
                timeout_s=0.05,
                cache_ttl_s=10,
                stale_ttl_s=60,
            )
        },
    )
    defaults = {
        "api_key": "test-key",
        "retry_max_attempts": 3,
        "retry_base_delay_s": 0.0,
        "retry_max_delay_s": 0.0,
        "breaker_failure_threshold": 2,
        "breaker_reset_timeout_s": 1.0,
        "rate_limit_per_minute": 100,
        "rate_limit_window_s": 60,
        "upstreams": upstreams,
    }
    defaults.update(overrides)
    return Settings(**defaults)


def make_client(
    *,
    settings: Settings | None = None,
    transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
) -> TestClient:
    app = create_app(
        settings=settings or make_settings(),
        http_transport=transport,
        cache_store=InMemoryValueStore(),
        rate_limit_store=InMemoryRateLimitStore(),
    )
    return TestClient(app)


@pytest.fixture
def upstream_app() -> FastAPI:
    app = FastAPI()

    @app.get("/ok")
    async def ok(name: str = "world") -> JSONResponse:
        return JSONResponse({"message": f"hello {name}"})

    return app
