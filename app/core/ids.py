from __future__ import annotations

from collections.abc import Mapping
from uuid import uuid4


def request_id_from_headers(headers: Mapping[str, str]) -> str:
    return headers.get("x-request-id") or uuid4().hex
