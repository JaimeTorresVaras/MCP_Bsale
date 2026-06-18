import time
from typing import Any
from config import log

_CACHE: dict[str, tuple[float, Any]] = {}

_CACHE_TTL: dict[str, int] = {
    "offices":        14400,
    "document_types": 14400,
    "price_lists":    14400,
    "products_index": 3600,
}


def _cache_get(key: str) -> Any:
    entry = _CACHE.get(key)
    if entry and time.monotonic() < entry[0]:
        log.info("cache hit: %s", key)
        return entry[1]
    return None


def _cache_set(key: str, value: Any, ttl: int = None) -> None:
    if ttl is None:
        ttl = _CACHE_TTL.get(key, 3600)
    _CACHE[key] = (time.monotonic() + ttl, value)
