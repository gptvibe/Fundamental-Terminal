from __future__ import annotations

import copy
import json
import math
import time
import uuid
from hashlib import sha256
from threading import Lock
from typing import Any, Callable, TypeVar

from app.config import settings

try:
    import redis
except Exception:  # pragma: no cover - optional dependency
    redis = None


T = TypeVar("T")


class SharedUpstreamCache:
    def __init__(self) -> None:
        self._namespace = f"{settings.hot_response_cache_namespace}:upstream"
        self._redis = self._build_redis_client()
        self._local_entries: dict[str, tuple[float, Any]] = {}
        self._local_entries_lock = Lock()
        self._local_locks: dict[str, tuple[str, float]] = {}
        self._local_locks_guard = Lock()

    def get_json(self, logical_key: str) -> Any | None:
        cached = self._get_local(logical_key)
        if cached is not None:
            return copy.deepcopy(cached)

        if self._redis is None:
            return None

        entry_key = self._entry_key(logical_key)
        try:
            raw_payload = self._redis.get(entry_key)
            if raw_payload is None:
                return None
            payload = json.loads(raw_payload)
            ttl_milliseconds = self._redis.pttl(entry_key)
            if isinstance(ttl_milliseconds, int) and ttl_milliseconds > 0:
                self._store_local(logical_key, payload, ttl_milliseconds / 1000.0)
            return payload
        except Exception:
            return None

    def store_json(self, logical_key: str, payload: Any, *, ttl_seconds: float) -> None:
        normalized_ttl = max(0.0, float(ttl_seconds))
        if normalized_ttl <= 0:
            return

        serialized = json.dumps(payload, separators=(",", ":"))
        self._store_local(logical_key, payload, normalized_ttl)

        if self._redis is None:
            return

        try:
            self._redis.set(self._entry_key(logical_key), serialized, ex=max(1, math.ceil(normalized_ttl)))
        except Exception:
            return

    def fill_json(self, logical_key: str, *, fill: Callable[[], tuple[Any, float]]) -> Any:
        cached = self.get_json(logical_key)
        if cached is not None:
            return cached

        def _wait_for() -> Any | None:
            return self.get_json(logical_key)

        def _fill_now() -> Any:
            payload, ttl_seconds = fill()
            if payload is not None and ttl_seconds > 0:
                self.store_json(logical_key, payload, ttl_seconds=ttl_seconds)
            return payload

        return self.run_singleflight(logical_key, wait_for=_wait_for, fill=_fill_now)

    def run_singleflight(self, logical_key: str, *, wait_for: Callable[[], T | None], fill: Callable[[], T]) -> T:
        cached = wait_for()
        if cached is not None:
            return cached

        lease_token = self._acquire_lock(logical_key)
        if lease_token is not None:
            try:
                cached = wait_for()
                if cached is not None:
                    return cached
                return fill()
            finally:
                self._release_lock(logical_key, lease_token)

        deadline = time.monotonic() + settings.hot_response_cache_singleflight_wait_seconds
        while time.monotonic() < deadline:
            cached = wait_for()
            if cached is not None:
                return cached
            if not self._lock_exists(logical_key):
                lease_token = self._acquire_lock(logical_key)
                if lease_token is not None:
                    try:
                        cached = wait_for()
                        if cached is not None:
                            return cached
                        return fill()
                    finally:
                        self._release_lock(logical_key, lease_token)
            time.sleep(settings.hot_response_cache_singleflight_poll_seconds)

        return fill()

    def clear_local(self) -> None:
        with self._local_entries_lock:
            self._local_entries.clear()
        with self._local_locks_guard:
            self._local_locks.clear()

    def _build_redis_client(self):
        if redis is None:
            return None
        try:
            client = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=False,
                socket_timeout=0.5,
                socket_connect_timeout=0.5,
            )
            client.ping()
            return client
        except Exception:
            return None

    def _get_local(self, logical_key: str) -> Any | None:
        now = time.monotonic()
        with self._local_entries_lock:
            cached = self._local_entries.get(logical_key)
            if cached is None:
                return None
            expires_at, payload = cached
            if expires_at <= now:
                self._local_entries.pop(logical_key, None)
                return None
            return payload

    def _store_local(self, logical_key: str, payload: Any, ttl_seconds: float) -> None:
        with self._local_entries_lock:
            self._local_entries[logical_key] = (time.monotonic() + ttl_seconds, copy.deepcopy(payload))

    def _acquire_lock(self, logical_key: str) -> str | None:
        token = uuid.uuid4().hex
        if self._redis is not None:
            try:
                if self._redis.set(
                    self._lock_key(logical_key),
                    token,
                    nx=True,
                    ex=settings.hot_response_cache_singleflight_lock_seconds,
                ):
                    return token
            except Exception:
                pass

        now = time.monotonic()
        with self._local_locks_guard:
            current = self._local_locks.get(logical_key)
            if current is not None and current[1] > now:
                return None
            self._local_locks[logical_key] = (
                token,
                now + settings.hot_response_cache_singleflight_lock_seconds,
            )
            return token

    def _release_lock(self, logical_key: str, token: str) -> None:
        if self._redis is not None:
            try:
                lock_key = self._lock_key(logical_key)
                current = self._redis.get(lock_key)
                if current is not None and current.decode("utf-8") == token:
                    self._redis.delete(lock_key)
            except Exception:
                pass

        with self._local_locks_guard:
            current = self._local_locks.get(logical_key)
            if current is not None and current[0] == token:
                self._local_locks.pop(logical_key, None)

    def _lock_exists(self, logical_key: str) -> bool:
        if self._redis is not None:
            try:
                return bool(self._redis.exists(self._lock_key(logical_key)))
            except Exception:
                pass

        now = time.monotonic()
        with self._local_locks_guard:
            current = self._local_locks.get(logical_key)
            if current is None:
                return False
            if current[1] <= now:
                self._local_locks.pop(logical_key, None)
                return False
            return True

    def _entry_key(self, logical_key: str) -> str:
        return f"{self._namespace}:entry:{_digest(logical_key)}"

    def _lock_key(self, logical_key: str) -> str:
        return f"{self._namespace}:lock:{_digest(logical_key)}"


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


shared_upstream_cache = SharedUpstreamCache()