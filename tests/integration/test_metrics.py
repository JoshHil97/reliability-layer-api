from __future__ import annotations

from tests.conftest import make_client


def test_metrics_endpoint_exposes_prometheus_text():
    with make_client() as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    assert "rl_requests_total" in response.text
