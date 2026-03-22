from __future__ import annotations

import json
import os
import re
from typing import Any

from fastapi import Request
from pydantic import AnyHttpUrl, BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_ALLOWED_METHODS = {"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"}


def _parse_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


class UpstreamSettings(BaseModel):
    name: str
    base_url: AnyHttpUrl
    timeout_s: float = 1.0
    cache_ttl_s: int = 0
    stale_ttl_s: int = 300
    retry_on_429: bool = False
    allowed_methods: set[str] = Field(default_factory=lambda: set(DEFAULT_ALLOWED_METHODS))

    @field_validator("allowed_methods", mode="before")
    @classmethod
    def _normalise_allowed_methods(cls, value: Any) -> set[str]:
        if value in (None, "", []):
            return set(DEFAULT_ALLOWED_METHODS)
        if isinstance(value, str):
            return {item.strip().upper() for item in value.split(",") if item.strip()}
        return {str(item).strip().upper() for item in value if str(item).strip()}

    @property
    def cache_enabled(self) -> bool:
        return self.cache_ttl_s > 0


class Settings(BaseSettings):
    app_name: str = "reliability-layer-api"
    api_key: str | None = "dev-local-key"
    redis_url: str | None = None
    default_timeout_s: float = 1.0
    retry_max_attempts: int = 3
    retry_base_delay_s: float = 0.1
    retry_max_delay_s: float = 1.0
    breaker_failure_threshold: int = 5
    breaker_reset_timeout_s: float = 20.0
    breaker_half_open_max_calls: int = 1
    rate_limit_per_minute: int = 60
    rate_limit_window_s: int = 60
    default_cache_ttl_s: int = 0
    default_stale_ttl_s: int = 300
    upstreams: dict[str, UpstreamSettings] = Field(default_factory=dict)

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    @classmethod
    def from_env(cls) -> Settings:
        settings = cls()
        upstreams = build_upstreams_from_env(
            default_timeout_s=settings.default_timeout_s,
            default_cache_ttl_s=settings.default_cache_ttl_s,
            default_stale_ttl_s=settings.default_stale_ttl_s,
        )
        return settings.model_copy(update={"upstreams": upstreams})


def build_upstreams_from_env(
    *,
    default_timeout_s: float,
    default_cache_ttl_s: int,
    default_stale_ttl_s: int,
) -> dict[str, UpstreamSettings]:
    upstreams: dict[str, UpstreamSettings] = {}
    raw_json = os.getenv("UPSTREAMS_JSON")
    if raw_json:
        payload = json.loads(raw_json)
        if not isinstance(payload, dict):
            msg = "UPSTREAMS_JSON must be a JSON object mapping names to configs"
            raise ValueError(msg)
        for name, config in payload.items():
            if not isinstance(config, dict):
                msg = f"Upstream {name!r} config must be an object"
                raise ValueError(msg)
            upstreams[name.lower()] = UpstreamSettings(name=name.lower(), **config)

    pattern = re.compile(r"^UPSTREAM_([A-Z0-9_]+)_BASE_URL$")
    for env_key, base_url in os.environ.items():
        match = pattern.match(env_key)
        if not match:
            continue
        raw_name = match.group(1)
        name = raw_name.lower()
        upstreams[name] = UpstreamSettings(
            name=name,
            base_url=base_url,
            timeout_s=float(os.getenv(f"UPSTREAM_{raw_name}_TIMEOUT_S", default_timeout_s)),
            cache_ttl_s=int(os.getenv(f"UPSTREAM_{raw_name}_CACHE_TTL_S", default_cache_ttl_s)),
            stale_ttl_s=int(os.getenv(f"UPSTREAM_{raw_name}_STALE_TTL_S", default_stale_ttl_s)),
            retry_on_429=_parse_bool(os.getenv(f"UPSTREAM_{raw_name}_RETRY_ON_429"), False),
            allowed_methods=os.getenv(f"UPSTREAM_{raw_name}_ALLOWED_METHODS"),
        )
    return upstreams


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
