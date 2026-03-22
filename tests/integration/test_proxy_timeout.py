from __future__ import annotations

import httpx

from tests.conftest import make_client


def test_proxy_timeout_retries_are_bounded():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        raise httpx.ReadTimeout("timed out", request=request)

    with make_client(transport=httpx.MockTransport(handler)) as client:
        response = client.get("/proxy/upsim/slow", headers={"X-API-Key": "test-key"})

    assert response.status_code == 504
    assert response.json()["detail"] == "ReadTimeout"
    assert attempts["count"] == 3
