from __future__ import annotations

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_health_endpoints():
    app = create_app(settings=Settings(api_key="test-key"))

    with TestClient(app) as client:
        live = client.get("/health/live")
        ready = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json()["ready"] is True
    assert ready.json()["note"] == "redis_optional"
