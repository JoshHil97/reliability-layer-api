from __future__ import annotations

import time

import httpx

from tests.conftest import make_client, make_settings


def test_proxy_serves_stale_on_upstream_500():
    attempts = {"count": 0}
    settings = make_settings(
        upstreams={
            "upsim": {
                "name": "upsim",
                "base_url": "http://upstream.local",
                "timeout_s": 0.05,
                "cache_ttl_s": 1,
                "stale_ttl_s": 60,
            }
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={"message": "cached"},
            )
        return httpx.Response(
            500,
            headers={"content-type": "application/json"},
            json={"message": "broken"},
        )

    with make_client(settings=settings, transport=httpx.MockTransport(handler)) as client:
        first = client.get("/proxy/upsim/ok", headers={"X-API-Key": "test-key"})
        time.sleep(1.05)
        second = client.get("/proxy/upsim/ok", headers={"X-API-Key": "test-key"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json() == {"message": "cached"}
    assert second.headers["x-reliability-layer-cache"] == "stale"
    assert attempts["count"] == 2
