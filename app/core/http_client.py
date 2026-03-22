from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence

import httpx

from app.core.config import Settings
from app.core.metrics import RL_UPSTREAM_RETRIES_TOTAL
from app.core.retry import RetryPolicy, backoff_with_jitter, should_retry


class HttpClient:
    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | httpx.BaseTransport | None = None,
    ) -> None:
        self._settings = settings
        self._client = httpx.AsyncClient(http2=True, transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def request_upstream(
        self,
        *,
        method: str,
        url: str,
        headers: Mapping[str, str],
        params: Sequence[tuple[str, str]],
        content: bytes | None,
        upstream_name: str,
        timeout_s: float,
        retry_on_429: bool = False,
    ) -> httpx.Response:
        policy = RetryPolicy(
            max_attempts=self._settings.retry_max_attempts,
            base_delay_s=self._settings.retry_base_delay_s,
            max_delay_s=self._settings.retry_max_delay_s,
        )
        timeout = httpx.Timeout(
            timeout_s,
            connect=timeout_s,
            read=timeout_s,
            write=timeout_s,
            pool=timeout_s,
        )

        attempt = 1
        while True:
            try:
                response = await self._client.request(
                    method=method,
                    url=url,
                    headers=dict(headers),
                    params=list(params),
                    content=content,
                    timeout=timeout,
                )
            except Exception as exc:
                if attempt >= policy.max_attempts or not should_retry(
                    method,
                    exc,
                    None,
                    headers,
                    retry_on_429=retry_on_429,
                ):
                    raise
                RL_UPSTREAM_RETRIES_TOTAL.labels(
                    upstream=upstream_name,
                    reason=type(exc).__name__,
                ).inc()
                await asyncio.sleep(backoff_with_jitter(policy, attempt))
                attempt += 1
                continue

            if attempt >= policy.max_attempts or not should_retry(
                method,
                None,
                response,
                headers,
                retry_on_429=retry_on_429,
            ):
                return response

            RL_UPSTREAM_RETRIES_TOTAL.labels(
                upstream=upstream_name,
                reason=f"http_{response.status_code}",
            ).inc()
            await asyncio.sleep(backoff_with_jitter(policy, attempt))
            attempt += 1
