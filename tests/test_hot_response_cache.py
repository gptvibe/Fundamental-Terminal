from __future__ import annotations

import asyncio
import json
import threading
import time

from app.api.handlers import _shared as shared_handlers
from app.api.schemas.common import CompanyPayload, DataQualityDiagnosticsPayload, RefreshState
from app.api.schemas.financials import CompanyFinancialsResponse
from app.services.hot_cache import shared_hot_response_cache


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