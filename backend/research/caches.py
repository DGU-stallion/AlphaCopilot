"""Injectable cache container and shared utilities for research route handlers."""

from __future__ import annotations

import time as _time
from dataclasses import dataclass, field

from fastapi import HTTPException


@dataclass
class ResearchCaches:
    """Injectable cache container for research route handlers.

    Each field holds an in-memory TTL cache used by the route layer.
    Tests can inject their own instance to avoid module-level globals.
    """

    pct_cache: dict = field(default_factory=dict)
    ann_cache: dict = field(default_factory=dict)
    fin_cache: dict = field(default_factory=dict)
    dc_cache: dict = field(default_factory=dict)


# ------------------------------------------------------------------
# Module-level utility functions (moved from router.py)
# ------------------------------------------------------------------


def validate_stock_code(code: str) -> str:
    """Validate and normalise a 6-digit A-share stock code.

    Raises HTTPException(400) on invalid input.
    """
    code = (code or "").strip()
    if not code.isdigit() or len(code) != 6:
        raise HTTPException(400, "代码必须是 6 位数字")
    return code


def cached_lookup(cache: dict, endpoint: str, code: str, ttl: int, fetch):
    """Return a cached value or call *fetch* and store the result.

    Parameters
    ----------
    cache : dict
        The cache dictionary to read from / write to (e.g. ``caches.dc_cache``).
    endpoint : str
        Logical endpoint name used as part of the cache key.
    code : str
        Stock code (or other identifier) used as part of the cache key.
    ttl : int
        Time-to-live in seconds.
    fetch : callable
        Zero-argument callable that produces fresh data on cache miss.
    """
    key = (endpoint, code)
    hit = cache.get(key)
    if hit and _time.time() - hit[0] < ttl:
        return hit[1]
    data = fetch()
    cache[key] = (_time.time(), data)
    return data


# Backward-compatible aliases so existing callers can import the old names.
_validate = validate_stock_code
_cached = cached_lookup
