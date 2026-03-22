from __future__ import annotations

import httpx

from tests.conftest import make_client


def test_proxy_passes_through_429_and_retry_after():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            429,
            headers={"content-type": "application/json", "retry-after": "30"},
            json={"detail": "slow_down"},
        )

    with make_client(transport=httpx.MockTransport(handler)) as client:
        response = client.get("/proxy/upsim/err429", headers={"X-API-Key": "test-key"})

    assert response.status_code == 429
    assert response.headers["retry-after"] == "30"
    assert response.json() == {"detail": "slow_down"}
