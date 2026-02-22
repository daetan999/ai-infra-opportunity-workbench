from __future__ import annotations
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

@dataclass
class CacheItem:
    value: Any
    expires_at: float

class TTLCache:
    def __init__(self, default_ttl_sec: int = 60, max_items: int = 256):
        self.default_ttl_sec = int(default_ttl_sec)
        self.max_items = int(max_items)
        self._store: Dict[str, CacheItem] = {}
        self.hits = 0
        self.misses = 0


    def _prune(self) -> None:
        now = time.time()
        # remove expired
        expired = [k for k, v in self._store.items() if v.expires_at <= now]
        for k in expired:
            self._store.pop(k, None)

        # cap size
        if len(self._store) > self.max_items:
            # remove soonest-expiring first (good enough)
            for k, _ in sorted(self._store.items(), key=lambda kv: kv[1].expires_at)[: len(self._store) - self.max_items]:
                self._store.pop(k, None)

    def get(self, key: str) -> Optional[Any]:
        self._prune()
        item = self._store.get(key)
        if not item:
            self.misses += 1
            return None
        if item.expires_at <= time.time():
            self._store.pop(key, None)
            self.hits += 1
            return None
        return item.value

    def set(self, key: str, value: Any, ttl_sec: Optional[int] = None) -> Any:
        ttl = self.default_ttl_sec if ttl_sec is None else int(ttl_sec)
        self._store[key] = CacheItem(value=value, expires_at=time.time() + ttl)
        self._prune()
        return value

    def get_or_set(self, key: str, fn: Callable[[], Any], ttl_sec: Optional[int] = None) -> Any:
        v = self.get(key)
        if v is not None:
            return v
        return self.set(key, fn(), ttl_sec=ttl_sec)

# Global caches
CHAIN_CACHE = TTLCache(default_ttl_sec=45, max_items=256)
EARNINGS_CACHE = TTLCache(default_ttl_sec=6 * 3600, max_items=512)
PEER_CACHE = TTLCache(default_ttl_sec=30 * 60, max_items=512)  # 30 min
# cache company snapshot longer (changes rarely)
COMPANY_CACHE = TTLCache(default_ttl_sec=12 * 3600, max_items=256)  # 12h

# cache headlines shorter (news moves)
NEWS_CACHE = TTLCache(default_ttl_sec=15 * 60, max_items=256)       # 15m

ALPHA_CACHE = TTLCache(default_ttl_sec=30 * 60, max_items=256)  # 30m


# Gemini debug trace cache (30-min TTL, localhost-only debug endpoint)
GEMINI_TRACE_CACHE = TTLCache(default_ttl_sec=30 * 60, max_items=256)