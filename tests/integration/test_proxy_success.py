from __future__ import annotations

import httpx

from tests.conftest import make_client


def test_proxy_success(upstream_app):
    transport = httpx.ASGITransport(app=upstream_app)

    with make_client(transport=transport) as client:
        response = client.get(
            "/proxy/upsim/ok?name=codex",
            headers={"X-API-Key": "test-key", "Accept": "application/json"},
        )

    assert response.status_code == 200
    assert response.json() == {"message": "hello codex"}
    assert response.headers["content-type"].startswith("application/json")
