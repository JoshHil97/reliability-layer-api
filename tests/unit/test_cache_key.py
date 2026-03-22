from __future__ import annotations

from app.core.cache import cache_key


def test_cache_key_is_deterministic_for_query_param_order():
    first = cache_key(
        "GET",
        "http://upstream.local/items",
        [("b", "2"), ("a", "1")],
        b"",
    )
    second = cache_key(
        "GET",
        "http://upstream.local/items",
        [("a", "1"), ("b", "2")],
        b"",
    )

    assert first == second
