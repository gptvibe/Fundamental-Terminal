from __future__ import annotations

import asyncio
from collections import Counter
from fnmatch import fnmatch
import json
import logging
import threading
import time
from types import SimpleNamespace
from typing import Any

import app.main as main_module
import app.services.hot_cache as hot_cache_module
from app.api.handlers import _shared as shared_handlers
from app.api.schemas.common import CompanyPayload, DataQualityDiagnosticsPayload, RefreshState
from app.api.schemas.financials import CompanyFinancialsResponse
from app.observability import begin_request_observation, complete_request_observation, end_request_observation, reset_request_observations, snapshot_request_observations
from app.services.hot_cache import HotCacheLookup, SharedHotResponseCache, shared_hot_response_cache


def _disable_remote(monkeypatch, cache: SharedHotResponseCache) -> None:
    monkeypatch.setattr(cache, "_redis", None)
    monkeypatch.setattr(cache, "_redis_async", None)


def test_hot_cache_emits_request_cache_and_redis_metrics(monkeypatch) -> None:
    reset_request_observations()
    cache = SharedHotResponseCache()
    backend = _FakeRedisBackend()
    sync_client, async_client = backend.make_clients()
    monkeypatch.setattr(cache, "_redis", sync_client)
    monkeypatch.setattr(cache, "_redis_async", async_client)

    async def _exercise() -> None:
        metrics, token = begin_request_observation(
            request_id="req-hot-cache",
            method="GET",
            path="/api/companies/AAPL/overview",
            query_string="",
            request_kind="read",
        )
        try:
            await cache.store("overview:AAPL", route="overview", payload={"ticker": "AAPL"})
            lookup = await cache.get("overview:AAPL", route="overview")
            assert lookup is not None
            complete_request_observation(
                metrics,
                route_path="/api/companies/{ticker}/overview",
                status_code=200,
            )
        finally:
            end_request_observation(token)

    asyncio.run(_exercise())

    snapshot = snapshot_request_observations()
    record = snapshot["records"][0]
    assert record["cache_events"]["hot_response"] == {"hit": 1}
    assert record["redis_call_count"] >= 1


class _FakeRedisBackend:
    def __init__(self) -> None:
        self.kv: dict[str, Any] = {}
        self.hashes: dict[str, dict[Any, Any]] = {}
        self.sets: dict[str, set[Any]] = {}
        self.calls: Counter[str] = Counter()

    def make_clients(self) -> tuple["_FakeSyncRedis", "_FakeAsyncRedis"]:
        return _FakeSyncRedis(self), _FakeAsyncRedis(self)

    def _exists(self, key: str) -> bool:
        return key in self.kv or key in self.hashes or key in self.sets

    def _delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            removed = False
            removed = self.kv.pop(key, None) is not None or removed
            removed = self.hashes.pop(key, None) is not None or removed
            removed = self.sets.pop(key, None) is not None or removed
            deleted += int(removed)
        return deleted

    def _scan(self, match: str | None) -> list[str]:
        keys = set(self.kv) | set(self.hashes) | set(self.sets)
        if match is None:
            return sorted(keys)
        return sorted(key for key in keys if fnmatch(key, match))


class _FakeSyncRedis:
    def __init__(self, backend: _FakeRedisBackend) -> None:
        self.backend = backend

    def ping(self) -> bool:
        self.backend.calls["sync_ping"] += 1
        return True

    def pipeline(self):
        return _FakeSyncPipeline(self)

    def get(self, key: str):
        self.backend.calls["sync_get"] += 1
        return self.backend.kv.get(key)

    def mget(self, *keys: str):
        self.backend.calls["sync_mget"] += 1
        if len(keys) == 1 and isinstance(keys[0], (list, tuple)):
            keys = tuple(keys[0])
        return [self.backend.kv.get(key) for key in keys]

    def set(self, key: str, value: Any, *, nx: bool = False, ex: int | None = None):
        self.backend.calls["sync_set"] += 1
        if nx and self.backend._exists(key):
            return False
        self.backend.kv[key] = value
        return True

    def hset(self, key: str, *, mapping: dict[Any, Any]):
        self.backend.calls["sync_hset"] += 1
        bucket = self.backend.hashes.setdefault(key, {})
        bucket.update(mapping)
        return len(mapping)

    def hget(self, key: str, field: Any):
        self.backend.calls["sync_hget"] += 1
        return self.backend.hashes.get(key, {}).get(field)

    def hgetall(self, key: str):
        self.backend.calls["sync_hgetall"] += 1
        return dict(self.backend.hashes.get(key, {}))

    def expire(self, key: str, seconds: int):
        self.backend.calls["sync_expire"] += 1
        return self.backend._exists(key)

    def delete(self, *keys: str):
        self.backend.calls["sync_delete"] += 1
        return self.backend._delete(*keys)

    def sadd(self, key: str, *values: Any):
        self.backend.calls["sync_sadd"] += 1
        members = self.backend.sets.setdefault(key, set())
        before = len(members)
        members.update(values)
        return len(members) - before

    def srem(self, key: str, *values: Any):
        self.backend.calls["sync_srem"] += 1
        members = self.backend.sets.setdefault(key, set())
        removed = 0
        for value in values:
            if value in members:
                members.remove(value)
                removed += 1
        if not members:
            self.backend.sets.pop(key, None)
        return removed

    def smembers(self, key: str):
        self.backend.calls["sync_smembers"] += 1
        return set(self.backend.sets.get(key, set()))

    def sinter(self, keys: list[str]):
        self.backend.calls["sync_sinter"] += 1
        if not keys:
            return set()
        sets = [set(self.backend.sets.get(key, set())) for key in keys]
        if not sets:
            return set()
        return set.intersection(*sets)

    def exists(self, key: str):
        self.backend.calls["sync_exists"] += 1
        return int(self.backend._exists(key))

    def scan(self, *, cursor: int = 0, match: str | None = None, count: int = 200):
        self.backend.calls["sync_scan"] += 1
        return 0, self.backend._scan(match)

    def hincrby(self, key: str, field: str, amount: int):
        self.backend.calls["sync_hincrby"] += 1
        bucket = self.backend.hashes.setdefault(key, {})
        current = int(float(bucket.get(field, b"0").decode("utf-8") if isinstance(bucket.get(field), bytes) else bucket.get(field, 0)))
        bucket[field] = str(current + amount).encode("utf-8")
        return current + amount

    def hincrbyfloat(self, key: str, field: str, amount: float):
        self.backend.calls["sync_hincrbyfloat"] += 1
        bucket = self.backend.hashes.setdefault(key, {})
        raw = bucket.get(field, b"0")
        current = float(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        bucket[field] = str(current + amount).encode("utf-8")
        return current + amount


class _FakeAsyncRedis:
    def __init__(self, backend: _FakeRedisBackend) -> None:
        self.backend = backend

    def pipeline(self):
        return _FakeAsyncPipeline(self)

    async def get(self, key: str):
        self.backend.calls["async_get"] += 1
        return self.backend.kv.get(key)

    async def mget(self, *keys: str):
        self.backend.calls["async_mget"] += 1
        if len(keys) == 1 and isinstance(keys[0], (list, tuple)):
            keys = tuple(keys[0])
        return [self.backend.kv.get(key) for key in keys]

    async def set(self, key: str, value: Any, *, nx: bool = False, ex: int | None = None):
        self.backend.calls["async_set"] += 1
        if nx and self.backend._exists(key):
            return False
        self.backend.kv[key] = value
        return True

    async def hset(self, key: str, *, mapping: dict[Any, Any]):
        self.backend.calls["async_hset"] += 1
        bucket = self.backend.hashes.setdefault(key, {})
        bucket.update(mapping)
        return len(mapping)

    async def hget(self, key: str, field: Any):
        self.backend.calls["async_hget"] += 1
        return self.backend.hashes.get(key, {}).get(field)

    async def hgetall(self, key: str):
        self.backend.calls["async_hgetall"] += 1
        return dict(self.backend.hashes.get(key, {}))

    async def expire(self, key: str, seconds: int):
        self.backend.calls["async_expire"] += 1
        return self.backend._exists(key)

    async def delete(self, *keys: str):
        self.backend.calls["async_delete"] += 1
        return self.backend._delete(*keys)

    async def sadd(self, key: str, *values: Any):
        self.backend.calls["async_sadd"] += 1
        members = self.backend.sets.setdefault(key, set())
        before = len(members)
        members.update(values)
        return len(members) - before

    async def srem(self, key: str, *values: Any):
        self.backend.calls["async_srem"] += 1
        members = self.backend.sets.setdefault(key, set())
        removed = 0
        for value in values:
            if value in members:
                members.remove(value)
                removed += 1
        if not members:
            self.backend.sets.pop(key, None)
        return removed

    async def smembers(self, key: str):
        self.backend.calls["async_smembers"] += 1
        return set(self.backend.sets.get(key, set()))

    async def sinter(self, keys: list[str]):
        self.backend.calls["async_sinter"] += 1
        if not keys:
            return set()
        sets = [set(self.backend.sets.get(key, set())) for key in keys]
        if not sets:
            return set()
        return set.intersection(*sets)

    async def exists(self, key: str):
        self.backend.calls["async_exists"] += 1
        return int(self.backend._exists(key))

    async def scan(self, *, cursor: int = 0, match: str | None = None, count: int = 200):
        self.backend.calls["async_scan"] += 1
        return 0, self.backend._scan(match)

    async def hincrby(self, key: str, field: str, amount: int):
        self.backend.calls["async_hincrby"] += 1
        bucket = self.backend.hashes.setdefault(key, {})
        raw = bucket.get(field, b"0")
        current = int(float(raw.decode("utf-8") if isinstance(raw, bytes) else raw))
        bucket[field] = str(current + amount).encode("utf-8")
        return current + amount

    async def hincrbyfloat(self, key: str, field: str, amount: float):
        self.backend.calls["async_hincrbyfloat"] += 1
        bucket = self.backend.hashes.setdefault(key, {})
        raw = bucket.get(field, b"0")
        current = float(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
        bucket[field] = str(current + amount).encode("utf-8")
        return current + amount


class _FakeSyncPipeline:
    def __init__(self, client: _FakeSyncRedis) -> None:
        self._client = client
        self._ops: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str):
        def _queue(*args: Any, **kwargs: Any):
            self._ops.append((name, args, kwargs))
            return self

        return _queue

    def execute(self):
        return [getattr(self._client, name)(*args, **kwargs) for name, args, kwargs in self._ops]


class _FakeAsyncPipeline:
    def __init__(self, client: _FakeAsyncRedis) -> None:
        self._client = client
        self._ops: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []

    def __getattr__(self, name: str):
        def _queue(*args: Any, **kwargs: Any):
            self._ops.append((name, args, kwargs))
            return self

        return _queue

    async def execute(self):
        results = []
        for name, args, kwargs in self._ops:
            results.append(await getattr(self._client, name)(*args, **kwargs))
        return results


def _build_remote_cache(monkeypatch) -> tuple[SharedHotResponseCache, _FakeRedisBackend]:
    backend = _FakeRedisBackend()
    sync_client, async_client = backend.make_clients()
    monkeypatch.setattr(SharedHotResponseCache, "_build_redis_clients", lambda self: (sync_client, async_client))
    return SharedHotResponseCache(), backend


def test_hot_cache_skips_company_missing_payloads(monkeypatch) -> None:
    _disable_remote(monkeypatch, shared_hot_response_cache)
    shared_handlers._hot_response_cache.clear()

    payload = CompanyFinancialsResponse(
        company=None,
        financials=[],
        price_history=[],
        refresh=RefreshState(triggered=True, reason="missing", ticker="ON", job_id="job-on"),
        diagnostics=DataQualityDiagnosticsPayload(stale_flags=["company_missing"]),
        confidence_flags=["company_missing"],
    )

    asyncio.run(shared_handlers._store_hot_cached_payload("financials:ON", payload))

    assert asyncio.run(shared_handlers._get_hot_cached_payload("financials:ON")) is None


def test_hot_cache_skips_workspace_bootstrap_missing_placeholders(monkeypatch) -> None:
    _disable_remote(monkeypatch, shared_hot_response_cache)
    shared_handlers._hot_response_cache.clear()

    missing_refresh = RefreshState(triggered=True, reason="missing", ticker="ON", job_id="job-on")
    payload = main_module.CompanyWorkspaceBootstrapResponse(
        company=None,
        financials=CompanyFinancialsResponse(
            company=None,
            financials=[],
            price_history=[],
            refresh=missing_refresh,
            diagnostics=DataQualityDiagnosticsPayload(stale_flags=["company_missing"]),
            confidence_flags=["company_missing"],
        ),
        brief=main_module._empty_company_brief_response(
            refresh=missing_refresh,
            as_of=None,
        ),
    )

    asyncio.run(shared_handlers._store_hot_cached_payload("workspace_bootstrap:ON:view=core:asof=latest", payload))

    assert asyncio.run(shared_handlers._get_hot_cached_payload("workspace_bootstrap:ON:view=core:asof=latest")) is None


def test_hot_cache_keeps_real_company_payloads(monkeypatch) -> None:
    _disable_remote(monkeypatch, shared_hot_response_cache)
    shared_handlers._hot_response_cache.clear()

    payload = CompanyFinancialsResponse(
        company=CompanyPayload(
            ticker="ON",
            cik="0001097864",
            name="ON SEMICONDUCTOR CORP",
            cache_state="fresh",
        ),
        financials=[],
        price_history=[],
        refresh=RefreshState(triggered=False, reason="fresh", ticker="ON", job_id=None),
        diagnostics=DataQualityDiagnosticsPayload(),
    )

    asyncio.run(shared_handlers._store_hot_cached_payload("financials:ON", payload))

    cached = asyncio.run(shared_handlers._get_hot_cached_payload("financials:ON"))
    assert cached is not None
    assert json.loads(cached.content)["company"]["ticker"] == "ON"


def test_shared_hot_cache_sync_compat_supports_running_event_loop(monkeypatch) -> None:
    cache = SharedHotResponseCache()
    _disable_remote(monkeypatch, cache)

    async def _exercise() -> tuple[object | None, dict[str, dict[str, float]]]:
        await cache.clear()
        cache.store_sync(
            "charts:ON:asof=latest",
            route="charts",
            payload={"company": {"ticker": "ON"}, "build_state": "ready"},
            tags=(cache.build_ticker_tag("ON"), cache.build_dataset_tag("charts_dashboard")),
        )
        lookup = cache.get_sync("charts:ON:asof=latest", route="charts")
        metrics = await cache.snapshot_metrics()
        return lookup, metrics

    lookup, metrics = asyncio.run(_exercise())

    assert lookup is not None
    assert lookup.is_fresh is True
    assert metrics["overall"]["requests"] >= 1
    assert metrics["overall"]["hit_fresh"] >= 1


def test_shared_hot_cache_invalidate_sync_supports_running_event_loop(monkeypatch) -> None:
    cache = SharedHotResponseCache()
    _disable_remote(monkeypatch, cache)

    async def _exercise() -> tuple[dict[str, object], dict[str, dict[str, float]]]:
        await cache.clear()
        cache.store_sync(
            "charts:AMD:asof=latest",
            route="charts",
            payload={"company": {"ticker": "AMD"}, "build_state": "ready"},
            tags=(cache.build_ticker_tag("AMD"), cache.build_dataset_tag("charts_dashboard")),
        )
        result = cache.invalidate_sync(ticker="AMD", dataset="charts_dashboard")
        metrics = await cache.snapshot_metrics()
        return result, metrics

    invalidation, metrics = asyncio.run(_exercise())

    assert invalidation["invalidated_keys"] == 1
    assert metrics["overall"]["invalidation_count"] >= 1
    assert "charts:AMD:asof=latest" not in cache._local_entries


def test_shared_hot_cache_invalidates_matching_tags(monkeypatch) -> None:
    _disable_remote(monkeypatch, shared_hot_response_cache)
    shared_handlers._hot_response_cache.clear()

    payload = CompanyFinancialsResponse(
        company=CompanyPayload(
            ticker="ON",
            cik="0001097864",
            name="ON SEMICONDUCTOR CORP",
            cache_state="fresh",
        ),
        financials=[],
        price_history=[],
        refresh=RefreshState(triggered=False, reason="fresh", ticker="ON", job_id=None),
        diagnostics=DataQualityDiagnosticsPayload(),
    )

    asyncio.run(
        shared_handlers._store_hot_cached_payload(
            "financials:ON:asof=latest",
            payload,
            tags=shared_handlers._build_hot_cache_tags(
                ticker="ON",
                datasets=("financials",),
                schema_versions=(shared_handlers.HOT_CACHE_SCHEMA_VERSIONS["financials"],),
                as_of="latest",
            ),
        )
    )

    invalidation = shared_hot_response_cache.invalidate_sync(ticker="ON", dataset="financials")

    assert invalidation["invalidated_keys"] == 1
    assert asyncio.run(shared_handlers._get_hot_cached_payload("financials:ON:asof=latest")) is None
    metrics = asyncio.run(shared_hot_response_cache.snapshot_metrics())["overall"]
    assert metrics["invalidation_count"] >= 1


def test_shared_hot_cache_tracks_stale_serves(monkeypatch) -> None:
    _disable_remote(monkeypatch, shared_hot_response_cache)
    shared_handlers._hot_response_cache.clear()

    payload = CompanyFinancialsResponse(
        company=CompanyPayload(
            ticker="ON",
            cik="0001097864",
            name="ON SEMICONDUCTOR CORP",
            cache_state="fresh",
        ),
        financials=[],
        price_history=[],
        refresh=RefreshState(triggered=False, reason="fresh", ticker="ON", job_id=None),
        diagnostics=DataQualityDiagnosticsPayload(),
    )

    asyncio.run(
        shared_handlers._store_hot_cached_payload(
            "financials:ON:asof=latest",
            payload,
            tags=shared_handlers._build_hot_cache_tags(
                ticker="ON",
                datasets=("financials",),
                schema_versions=(shared_handlers.HOT_CACHE_SCHEMA_VERSIONS["financials"],),
                as_of="latest",
            ),
        )
    )

    entry = shared_hot_response_cache._local_entries["financials:ON:asof=latest"]
    entry.fresh_until = time.time() - 1
    entry.stale_until = time.time() + 60

    cached = asyncio.run(shared_handlers._get_hot_cached_payload("financials:ON:asof=latest"))

    assert cached is not None
    assert cached.is_fresh is False
    metrics = asyncio.run(shared_hot_response_cache.snapshot_metrics())["overall"]
    assert metrics["stale_served_count"] >= 1
    assert metrics["hit_rate"] > 0


def test_shared_hot_cache_singleflight_coalesces_identical_local_fills(monkeypatch) -> None:
    _disable_remote(monkeypatch, shared_hot_response_cache)
    shared_handlers._hot_response_cache.clear()

    barrier = threading.Barrier(2)
    call_lock = threading.Lock()
    results: list[dict[str, int]] = []
    call_count = 0

    def fill() -> dict[str, int]:
        nonlocal call_count
        with call_lock:
            call_count += 1
            current = call_count
        time.sleep(0.05)
        return {"value": current}

    def worker() -> None:
        barrier.wait()
        results.append(
            asyncio.run(
                shared_hot_response_cache.fill_or_get(
                    "financials:ON:asof=latest",
                    route="financials",
                    tags=(shared_hot_response_cache.build_ticker_tag("ON"),),
                    fill=fill,
                )
            )
        )

    threads = [threading.Thread(target=worker), threading.Thread(target=worker)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert call_count == 1
    assert results == [{"value": 1}, {"value": 1}]
    metrics = asyncio.run(shared_hot_response_cache.snapshot_metrics())["overall"]
    assert metrics["fills"] >= 1
    assert metrics["avg_fill_time_ms"] >= 0
    assert metrics["coalesced_waits"] >= 1


def test_shared_hot_cache_snapshot_reports_local_fallback_details(monkeypatch) -> None:
    monkeypatch.setattr(hot_cache_module, "redis", None)
    monkeypatch.setattr(hot_cache_module, "redis_async", None)

    cache = SharedHotResponseCache()
    metrics = asyncio.run(cache.snapshot_metrics())

    assert metrics["backend"] == "local"
    assert metrics["backend_mode"] == "local_memory_fallback"
    assert metrics["backend_details"]["fallback_active"] is True
    assert metrics["backend_details"]["status"] == "fallback"
    assert "process-local hot-cache fallback" in metrics["backend_details"]["summary"]
    assert "cache reuse" in metrics["backend_details"]["operational_impact"]
    assert metrics["backend_details"]["recommended_checks"][0] == "Verify REDIS_URL."
    assert metrics["backend_details"]["startup_reason"] == "redis_dependency_missing"
    assert metrics["backend_details"]["cross_instance_reuse"] == "disabled"


def test_shared_hot_cache_logs_connect_fallback_on_startup(monkeypatch, caplog) -> None:
    class _FailingRedisClient:
        def ping(self) -> None:
            raise RuntimeError("connection refused")

    class _FakeRedisModule:
        class Redis:
            @staticmethod
            def from_url(*_args, **_kwargs):
                return _FailingRedisClient()

    monkeypatch.setattr(hot_cache_module, "redis", _FakeRedisModule)
    monkeypatch.setattr(hot_cache_module, "redis_async", _FakeRedisModule)
    caplog.set_level(logging.WARNING, logger="app.services.hot_cache")

    cache = SharedHotResponseCache()

    assert cache.backend == "local"
    messages = [record.message for record in caplog.records]
    assert any('"event":"shared_hot_cache.local_fallback"' in message and '"operation":"startup_connect"' in message for message in messages)
    assert any('"event":"shared_hot_cache.backend"' in message and '"startup_reason":"redis_connect_failed"' in message for message in messages)
    assert any('"summary":"Redis was configured, but the app is currently using process-local hot-cache fallback."' in message for message in messages)


def test_shared_hot_cache_runtime_read_fallback_updates_metrics(monkeypatch, caplog) -> None:
    monkeypatch.setattr(SharedHotResponseCache, "_build_redis_clients", lambda self: (SimpleNamespace(), SimpleNamespace()))
    cache = SharedHotResponseCache()
    async def _raise_read(*_args, **_kwargs):
        raise hot_cache_module.RedisError("read failed")

    async def _noop_metric(*_args, **_kwargs):
        return None

    async def _empty_snapshot():
        return {"overall": {}}

    monkeypatch.setattr(cache, "_read_remote_async", _raise_read)
    monkeypatch.setattr(cache, "_record_remote_metric_async", _noop_metric)
    monkeypatch.setattr(cache, "_snapshot_remote_metrics_async", _empty_snapshot)
    caplog.set_level(logging.WARNING, logger="app.services.hot_cache")

    cached = asyncio.run(cache.get("financials:ON", route="financials"))
    metrics = asyncio.run(cache.snapshot_metrics())

    assert cached is None
    assert metrics["backend"] == "redis"
    assert metrics["backend_mode"] == "redis_with_local_fallbacks"
    assert metrics["backend_details"]["fallback_events_total"] >= 1
    assert metrics["backend_details"]["status"] == "degraded"
    assert "fell back to process-local memory" in metrics["backend_details"]["summary"]
    assert metrics["backend_details"]["last_fallback_reason"] == "redis_read_failed"
    assert any('"event":"shared_hot_cache.local_fallback"' in record.message and '"operation":"read"' in record.message for record in caplog.records)
    assert any('"operational_impact":"Cross-instance cache reuse and shared singleflight coordination may be partial until Redis recovers."' in record.message for record in caplog.records)


def test_shared_hot_cache_remote_fresh_hit_uses_single_record_read(monkeypatch) -> None:
    cache, backend = _build_remote_cache(monkeypatch)

    asyncio.run(
        cache.store(
            "financials:ON:asof=latest",
            route="financials",
            payload={"company": {"ticker": "ON", "last_checked": "2026-04-25T00:00:00Z"}, "results": []},
            tags=(cache.build_ticker_tag("ON"), cache.build_dataset_tag("financials")),
        )
    )
    backend.calls.clear()

    lookup = asyncio.run(cache.get("financials:ON:asof=latest", route="financials"))

    assert lookup is not None
    assert lookup.is_fresh is True
    assert json.loads(lookup.content)["company"]["ticker"] == "ON"
    assert backend.calls["async_hgetall"] >= 1
    assert backend.calls["async_get"] == 0
    assert backend.calls["async_mget"] == 0


def test_shared_hot_cache_remote_stale_hit(monkeypatch) -> None:
    cache, _backend = _build_remote_cache(monkeypatch)
    logical_key = "financials:ON:asof=latest"

    asyncio.run(
        cache.store(
            logical_key,
            route="financials",
            payload={"company": {"ticker": "ON"}, "results": []},
            tags=(cache.build_ticker_tag("ON"), cache.build_dataset_tag("financials")),
        )
    )
    record = _backend.hashes[cache._record_key(logical_key)]
    record["fresh_until"] = str(time.time() - 1).encode("utf-8")
    record["stale_until"] = str(time.time() + 60).encode("utf-8")

    lookup = asyncio.run(cache.get(logical_key, route="financials"))

    assert lookup is not None
    assert lookup.is_fresh is False


def test_shared_hot_cache_remote_miss(monkeypatch) -> None:
    cache, backend = _build_remote_cache(monkeypatch)

    lookup = asyncio.run(cache.get("financials:MISS:asof=latest", route="financials"))

    assert lookup is None
    assert backend.calls["async_hgetall"] >= 1
    assert backend.calls["async_mget"] >= 1


def test_shared_hot_cache_remote_fill_or_get(monkeypatch) -> None:
    cache, _backend = _build_remote_cache(monkeypatch)
    calls = 0

    async def _exercise() -> tuple[dict[str, Any], dict[str, Any]]:
        nonlocal calls

        async def fill() -> dict[str, Any]:
            nonlocal calls
            calls += 1
            await asyncio.sleep(0)
            return {"value": calls}

        first = await cache.fill_or_get(
            "financials:ON:asof=latest",
            route="financials",
            tags=(cache.build_ticker_tag("ON"),),
            fill=fill,
        )
        second = await cache.fill_or_get(
            "financials:ON:asof=latest",
            route="financials",
            tags=(cache.build_ticker_tag("ON"),),
            fill=fill,
        )
        return first, second

    first, second = asyncio.run(_exercise())

    assert first == {"value": 1}
    assert second == {"value": 1}
    assert calls == 1


def test_shared_hot_cache_remote_redis_unavailable_falls_back_to_local(monkeypatch) -> None:
    cache, _backend = _build_remote_cache(monkeypatch)

    async def _raise_read(*_args, **_kwargs):
        raise hot_cache_module.RedisError("boom")

    monkeypatch.setattr(cache, "_read_remote_async", _raise_read)

    asyncio.run(
        cache._store_local(
            "financials:ON:asof=latest",
            route="financials",
            content=b'{"value":1}',
            tags=(cache.build_ticker_tag("ON"),),
            stored_at=time.time(),
            fresh_until=time.time() + 60,
            stale_until=time.time() + 120,
            etag='W/"abc"',
            last_modified=None,
        )
    )

    lookup = asyncio.run(cache.get("financials:ON:asof=latest", route="financials"))

    assert lookup is not None
    assert json.loads(lookup.content) == {"value": 1}
    assert cache.backend_mode == "redis_with_local_fallbacks"


def test_shared_hot_cache_closed_event_loop_falls_back_to_local(monkeypatch) -> None:
    cache, _backend = _build_remote_cache(monkeypatch)

    async def _raise_read(*_args, **_kwargs):
        raise RuntimeError("Event loop is closed")

    monkeypatch.setattr(cache, "_read_remote_async", _raise_read)

    asyncio.run(
        cache._store_local(
            "financials:ON:asof=latest",
            route="financials",
            content=b'{"value":1}',
            tags=(cache.build_ticker_tag("ON"),),
            stored_at=time.time(),
            fresh_until=time.time() + 60,
            stale_until=time.time() + 120,
            etag='W/"abc"',
            last_modified=None,
        )
    )

    lookup = asyncio.run(cache.get("financials:ON:asof=latest", route="financials"))

    assert lookup is not None
    assert json.loads(lookup.content) == {"value": 1}
    assert cache.backend_mode == "redis_with_local_fallbacks"


def test_shared_hot_cache_remote_invalidation_by_tag_preserves_other_routes(monkeypatch) -> None:
    cache, _backend = _build_remote_cache(monkeypatch)

    async def _exercise() -> tuple[dict[str, Any], HotCacheLookup | None, HotCacheLookup | None, dict[str, Any]]:
        await cache.store(
            "financials:ON:asof=latest",
            route="financials",
            payload={"company": {"ticker": "ON"}, "results": []},
            tags=(cache.build_ticker_tag("ON"), cache.build_dataset_tag("financials")),
        )
        await cache.store(
            "search:ON",
            route="search",
            payload={"results": [{"ticker": "ON"}]},
            tags=(cache.build_ticker_tag("ON"), cache.build_dataset_tag("search")),
        )
        invalidation = await cache.invalidate(ticker="ON", dataset="financials")
        financials_lookup = await cache.get("financials:ON:asof=latest", route="financials")
        search_lookup = await cache.get("search:ON", route="search")
        metrics = await cache.snapshot_metrics()
        return invalidation, financials_lookup, search_lookup, metrics

    invalidation, financials_lookup, search_lookup, metrics = asyncio.run(_exercise())

    assert invalidation["invalidated_keys"] == 1
    assert financials_lookup is None
    assert search_lookup is not None
    assert metrics["routes"]["financials"]["invalidation_count"] >= 1
