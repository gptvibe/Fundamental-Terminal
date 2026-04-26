from __future__ import annotations

import math
from collections import OrderedDict
import time
import uuid
from dataclasses import dataclass
from hashlib import sha256
from threading import Lock
from typing import Any, Callable, TypeVar

import orjson

from app.config import settings

try:
    import redis
except Exception:  # pragma: no cover - optional dependency
    redis = None


T = TypeVar("T")


@dataclass(slots=True)
class _LocalEntry:
    expires_at: float
    payload_bytes: bytes
    size_bytes: int


class SharedUpstreamCache:
    def __init__(self) -> None:
        self._namespace = f"{settings.hot_response_cache_namespace}:upstream"
        self._redis = self._build_redis_client()
        self._local_max_entries = max(0, int(getattr(settings, "hot_response_cache_upstream_local_max_entries", 512)))
        self._local_max_bytes = max(0, int(getattr(settings, "hot_response_cache_upstream_local_max_bytes", 16 * 1024 * 1024)))
        self._local_entries: OrderedDict[str, _LocalEntry] = OrderedDict()
        self._local_total_bytes = 0
        self._local_entries_lock = Lock()
        self._local_locks: dict[str, tuple[str, float]] = {}
        self._local_locks_guard = Lock()
        self._metrics_lock = Lock()
        self._metrics = {
            "local_hits": 0,
            "redis_hits": 0,
            "misses": 0,
            "evictions": 0,
            "singleflight_waits": 0,
        }

    def get_json(self, logical_key: str) -> Any | None:
        local_payload_bytes = self._get_local_bytes(logical_key)
        if local_payload_bytes is not None:
            self._increment_metric("local_hits")
            return self._deserialize(local_payload_bytes)

        if self._redis is None:
            self._increment_metric("misses")
            return None

        entry_key = self._entry_key(logical_key)
        try:
            raw_payload, ttl_milliseconds = self._redis_get_and_pttl(entry_key)
            if raw_payload is None:
                self._increment_metric("misses")
                return None
            payload_bytes = self._coerce_to_bytes(raw_payload)
            payload = self._deserialize(payload_bytes)
            self._increment_metric("redis_hits")
            if isinstance(ttl_milliseconds, int) and ttl_milliseconds > 0:
                self._store_local_bytes(logical_key, payload_bytes, ttl_milliseconds / 1000.0)
            return payload
        except Exception:
            self._increment_metric("misses")
            return None

    def store_json(self, logical_key: str, payload: Any, *, ttl_seconds: float) -> None:
        normalized_ttl = max(0.0, float(ttl_seconds))
        if normalized_ttl <= 0:
            return

        serialized = orjson.dumps(payload)
        self._store_local_bytes(logical_key, serialized, normalized_ttl)

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

        self._increment_metric("singleflight_waits")
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
            self._local_total_bytes = 0
        with self._local_locks_guard:
            self._local_locks.clear()

    def snapshot_metrics(self) -> dict[str, int]:
        with self._metrics_lock:
            counters = dict(self._metrics)
        with self._local_entries_lock:
            counters["local_entries"] = len(self._local_entries)
            counters["local_bytes"] = self._local_total_bytes
            counters["local_max_entries"] = self._local_max_entries
            counters["local_max_bytes"] = self._local_max_bytes
        return counters

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

    def _get_local_bytes(self, logical_key: str) -> bytes | None:
        now = time.monotonic()
        with self._local_entries_lock:
            entry = self._local_entries.get(logical_key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._delete_local_entry_locked(logical_key)
                return None
            self._local_entries.move_to_end(logical_key)
            return entry.payload_bytes

    def _store_local_bytes(self, logical_key: str, payload_bytes: bytes, ttl_seconds: float) -> None:
        if ttl_seconds <= 0:
            return
        if self._local_max_entries <= 0 or self._local_max_bytes <= 0:
            return

        entry_size = len(payload_bytes)
        if entry_size > self._local_max_bytes:
            return

        now = time.monotonic()
        with self._local_entries_lock:
            if logical_key in self._local_entries:
                self._delete_local_entry_locked(logical_key)
            self._local_entries[logical_key] = _LocalEntry(
                expires_at=now + ttl_seconds,
                payload_bytes=payload_bytes,
                size_bytes=entry_size,
            )
            self._local_total_bytes += entry_size
            self._prune_local_locked(now)

    def _prune_local_locked(self, now: float) -> None:
        for key, entry in list(self._local_entries.items()):
            if entry.expires_at <= now:
                self._delete_local_entry_locked(key)

        evicted = 0
        while self._local_entries and (
            len(self._local_entries) > self._local_max_entries or self._local_total_bytes > self._local_max_bytes
        ):
            _, entry = self._local_entries.popitem(last=False)
            self._local_total_bytes -= entry.size_bytes
            evicted += 1

        if evicted > 0:
            self._increment_metric("evictions", delta=evicted)

    def _delete_local_entry_locked(self, logical_key: str) -> None:
        entry = self._local_entries.pop(logical_key, None)
        if entry is not None:
            self._local_total_bytes -= entry.size_bytes

    def _redis_get_and_pttl(self, entry_key: str) -> tuple[Any | None, int | None]:
        if self._redis is None:
            return None, None

        try:
            pipeline = self._redis.pipeline(transaction=False)
            pipeline.get(entry_key)
            pipeline.pttl(entry_key)
            results = pipeline.execute()
            if isinstance(results, (list, tuple)) and len(results) == 2:
                ttl_value = results[1] if isinstance(results[1], int) else None
                return results[0], ttl_value
        except Exception:
            pass

        raw_payload = self._redis.get(entry_key)
        if raw_payload is None:
            return None, None
        ttl_milliseconds = self._redis.pttl(entry_key)
        return raw_payload, ttl_milliseconds if isinstance(ttl_milliseconds, int) else None

    def _increment_metric(self, name: str, *, delta: int = 1) -> None:
        with self._metrics_lock:
            self._metrics[name] += delta

    @staticmethod
    def _coerce_to_bytes(raw_payload: Any) -> bytes:
        if isinstance(raw_payload, bytes):
            return raw_payload
        if isinstance(raw_payload, bytearray):
            return bytes(raw_payload)
        if isinstance(raw_payload, memoryview):
            return raw_payload.tobytes()
        if isinstance(raw_payload, str):
            return raw_payload.encode("utf-8")
        raise TypeError("Unsupported cache payload type")

    @staticmethod
    def _deserialize(payload_bytes: bytes) -> Any:
        return orjson.loads(payload_bytes)

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