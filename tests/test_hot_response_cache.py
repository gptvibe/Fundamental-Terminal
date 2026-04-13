from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from types import SimpleNamespace

import app.services.hot_cache as hot_cache_module
from app.api.handlers import _shared as shared_handlers
from app.api.schemas.common import CompanyPayload, DataQualityDiagnosticsPayload, RefreshState
from app.api.schemas.financials import CompanyFinancialsResponse
from app.services.hot_cache import SharedHotResponseCache, shared_hot_response_cache


def test_hot_cache_skips_company_missing_payloads(monkeypatch) -> None:
    monkeypatch.setattr(shared_hot_response_cache, "_redis", None)
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


def test_hot_cache_keeps_real_company_payloads(monkeypatch) -> None:
    monkeypatch.setattr(shared_hot_response_cache, "_redis", None)
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


def test_shared_hot_cache_invalidates_matching_tags(monkeypatch) -> None:
    monkeypatch.setattr(shared_hot_response_cache, "_redis", None)
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
    monkeypatch.setattr(shared_hot_response_cache, "_redis", None)
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
    monkeypatch.setattr(shared_hot_response_cache, "_redis", None)
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

    cache = SharedHotResponseCache()
    metrics = asyncio.run(cache.snapshot_metrics())

    assert metrics["backend"] == "local"
    assert metrics["backend_mode"] == "local_memory_fallback"
    assert metrics["backend_details"]["fallback_active"] is True
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
    caplog.set_level(logging.WARNING, logger="app.services.hot_cache")

    cache = SharedHotResponseCache()

    assert cache.backend == "local"
    messages = [record.message for record in caplog.records]
    assert any('"event":"shared_hot_cache.local_fallback"' in message and '"operation":"startup_connect"' in message for message in messages)
    assert any('"event":"shared_hot_cache.backend"' in message and '"startup_reason":"redis_connect_failed"' in message for message in messages)


def test_shared_hot_cache_runtime_read_fallback_updates_metrics(monkeypatch, caplog) -> None:
    monkeypatch.setattr(SharedHotResponseCache, "_build_redis_client", lambda self: SimpleNamespace())
    cache = SharedHotResponseCache()
    monkeypatch.setattr(cache, "_read_remote", lambda *_args, **_kwargs: (_ for _ in ()).throw(hot_cache_module.RedisError("read failed")))
    monkeypatch.setattr(cache, "_record_remote_metric", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cache, "_snapshot_remote_metrics", lambda: {"overall": {}})
    caplog.set_level(logging.WARNING, logger="app.services.hot_cache")

    cached = asyncio.run(cache.get("financials:ON", route="financials"))
    metrics = asyncio.run(cache.snapshot_metrics())

    assert cached is None
    assert metrics["backend"] == "redis"
    assert metrics["backend_mode"] == "redis_with_local_fallbacks"
    assert metrics["backend_details"]["fallback_events_total"] >= 1
    assert metrics["backend_details"]["last_fallback_reason"] == "redis_read_failed"
    assert any('"event":"shared_hot_cache.local_fallback"' in record.message and '"operation":"read"' in record.message for record in caplog.records)
