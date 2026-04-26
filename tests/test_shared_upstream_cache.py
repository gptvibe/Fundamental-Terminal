from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
import time

import orjson

import app.services.shared_upstream_cache as shared_upstream_cache_module


class _FakePipeline:
    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis
        self._ops: list[tuple[str, str]] = []

    def get(self, key: str) -> "_FakePipeline":
        self._ops.append(("get", key))
        return self

    def pttl(self, key: str) -> "_FakePipeline":
        self._ops.append(("pttl", key))
        return self

    def execute(self) -> list[object | None]:
        self._redis.pipeline_execute_count += 1
        out: list[object | None] = []
        for op, key in self._ops:
            if op == "get":
                out.append(self._redis.get(key))
            elif op == "pttl":
                out.append(self._redis.pttl(key))
        return out


class _FakeRedis:
    def __init__(self) -> None:
        self._entries: dict[str, tuple[bytes, float | None]] = {}
        self.pipeline_execute_count = 0

    def _purge_if_expired(self, key: str) -> None:
        entry = self._entries.get(key)
        if entry is None:
            return
        _, expires_at = entry
        if expires_at is not None and expires_at <= time.monotonic():
            self._entries.pop(key, None)

    def set(self, key: str, value: object, *, ex: int | None = None, nx: bool = False) -> bool:
        self._purge_if_expired(key)
        if nx and key in self._entries:
            return False
        if isinstance(value, bytes):
            payload = value
        elif isinstance(value, str):
            payload = value.encode("utf-8")
        else:
            payload = bytes(value)
        expires_at = time.monotonic() + float(ex) if ex is not None else None
        self._entries[key] = (payload, expires_at)
        return True

    def get(self, key: str) -> bytes | None:
        self._purge_if_expired(key)
        entry = self._entries.get(key)
        if entry is None:
            return None
        return entry[0]

    def pttl(self, key: str) -> int:
        self._purge_if_expired(key)
        entry = self._entries.get(key)
        if entry is None:
            return -2
        _, expires_at = entry
        if expires_at is None:
            return -1
        return max(0, int((expires_at - time.monotonic()) * 1000.0))

    def exists(self, key: str) -> int:
        self._purge_if_expired(key)
        return 1 if key in self._entries else 0

    def delete(self, key: str) -> int:
        existed = key in self._entries
        self._entries.pop(key, None)
        return 1 if existed else 0

    def pipeline(self, transaction: bool = False) -> _FakePipeline:  # noqa: ARG002
        return _FakePipeline(self)


def _settings(*, max_entries: int = 512, max_bytes: int = 16 * 1024 * 1024) -> SimpleNamespace:
    return SimpleNamespace(
        redis_url="",
        hot_response_cache_namespace="ft:test-hot-cache",
        hot_response_cache_singleflight_lock_seconds=5,
        hot_response_cache_singleflight_wait_seconds=1.0,
        hot_response_cache_singleflight_poll_seconds=0.01,
        hot_response_cache_upstream_local_max_entries=max_entries,
        hot_response_cache_upstream_local_max_bytes=max_bytes,
    )


def test_shared_upstream_cache_coalesces_identical_local_fills(monkeypatch) -> None:
    release_fill = Event()
    fill_count = 0

    monkeypatch.setattr(
        shared_upstream_cache_module,
        "settings",
        _settings(),
    )

    cache = shared_upstream_cache_module.SharedUpstreamCache()
    cache._redis = None

    def _fill_payload() -> tuple[dict[str, object], float]:
        nonlocal fill_count
        fill_count += 1
        assert release_fill.wait(timeout=1.0)
        return ({"value": 42}, 60.0)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(cache.fill_json, "market-profile:AAPL", fill=_fill_payload)
        second_future = executor.submit(cache.fill_json, "market-profile:AAPL", fill=_fill_payload)
        release_fill.set()
        first = first_future.result(timeout=2.0)
        second = second_future.result(timeout=2.0)

    assert fill_count == 1
    assert first == second == {"value": 42}
    assert cache.snapshot_metrics()["singleflight_waits"] >= 1


def test_shared_upstream_cache_ttl_expires_local_entries(monkeypatch) -> None:
    monkeypatch.setattr(shared_upstream_cache_module, "settings", _settings())

    cache = shared_upstream_cache_module.SharedUpstreamCache()
    cache._redis = None
    cache.store_json("k", {"value": 1}, ttl_seconds=0.05)

    assert cache.get_json("k") == {"value": 1}
    time.sleep(0.08)
    assert cache.get_json("k") is None


def test_shared_upstream_cache_local_hit_returns_fresh_object(monkeypatch) -> None:
    monkeypatch.setattr(shared_upstream_cache_module, "settings", _settings())

    cache = shared_upstream_cache_module.SharedUpstreamCache()
    cache._redis = None
    cache.store_json("k", {"nested": {"value": 1}}, ttl_seconds=60.0)

    first = cache.get_json("k")
    assert first == {"nested": {"value": 1}}
    first["nested"]["value"] = 999

    second = cache.get_json("k")
    assert second == {"nested": {"value": 1}}

    metrics = cache.snapshot_metrics()
    assert metrics["local_hits"] >= 2
    assert metrics["redis_hits"] == 0


def test_shared_upstream_cache_redis_hit_uses_pipeline_and_populates_local(monkeypatch) -> None:
    monkeypatch.setattr(shared_upstream_cache_module, "settings", _settings())

    cache = shared_upstream_cache_module.SharedUpstreamCache()
    fake_redis = _FakeRedis()
    cache._redis = fake_redis

    fake_redis.set(cache._entry_key("k"), orjson.dumps({"value": 42}), ex=60)
    first = cache.get_json("k")
    second = cache.get_json("k")

    assert first == {"value": 42}
    assert second == {"value": 42}
    assert fake_redis.pipeline_execute_count >= 1

    metrics = cache.snapshot_metrics()
    assert metrics["redis_hits"] == 1
    assert metrics["local_hits"] >= 1


def test_shared_upstream_cache_lru_eviction_with_entry_cap(monkeypatch) -> None:
    monkeypatch.setattr(shared_upstream_cache_module, "settings", _settings(max_entries=2, max_bytes=1024 * 1024))

    cache = shared_upstream_cache_module.SharedUpstreamCache()
    cache._redis = None

    cache.store_json("k1", {"value": 1}, ttl_seconds=60.0)
    cache.store_json("k2", {"value": 2}, ttl_seconds=60.0)
    assert cache.get_json("k1") == {"value": 1}

    cache.store_json("k3", {"value": 3}, ttl_seconds=60.0)

    assert cache.get_json("k2") is None
    assert cache.get_json("k1") == {"value": 1}
    assert cache.get_json("k3") == {"value": 3}

    metrics = cache.snapshot_metrics()
    assert metrics["evictions"] >= 1
    assert metrics["local_entries"] <= 2