from __future__ import annotations

from app.core.config import Settings


def test_settings_load_upstream_from_env(monkeypatch):
    monkeypatch.setenv("UPSTREAM_UPSIM_BASE_URL", "http://upstream.local")
    monkeypatch.setenv("UPSTREAM_UPSIM_TIMEOUT_S", "2.5")
    monkeypatch.setenv("UPSTREAM_UPSIM_CACHE_TTL_S", "30")
    monkeypatch.setenv("UPSTREAM_UPSIM_STALE_TTL_S", "120")

    settings = Settings.from_env()

    assert "upsim" in settings.upstreams
    assert str(settings.upstreams["upsim"].base_url) == "http://upstream.local/"
    assert settings.upstreams["upsim"].timeout_s == 2.5
    assert settings.upstreams["upsim"].cache_ttl_s == 30
    assert settings.upstreams["upsim"].stale_ttl_s == 120
