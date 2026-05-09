from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.handlers import source_registry as source_registry_module
from app.api.schemas.source_registry import (
    SourceRegistryErrorPayload,
    SourceRegistryHealthPayload,
    SourceRegistrySloPayload,
    SourceRegistryWorkerQueueHealthPayload,
)
from app.db import get_db_session
from app.main import app


class _FakeScalarResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return self._values


class _FakeRowResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeHealthSession:
    def __init__(self, last_checked_values, status_rows=None, queue_rows=None):
        self._last_checked_values = last_checked_values
        self._status_rows = status_rows or []
        self._queue_rows = queue_rows or []
        self._execute_call_count = 0

    def execute(self, _statement):
        self._execute_call_count += 1
        if self._execute_call_count == 1:
            return _FakeScalarResult(self._last_checked_values)
        if self._execute_call_count == 2:
            return _FakeRowResult(self._status_rows)
        return _FakeRowResult(self._queue_rows)


class _FakeErrorSession:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _statement):
        return _FakeRowResult(self._rows)


@contextmanager
def _client(session):
    app.dependency_overrides[get_db_session] = lambda: session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_source_registry_endpoint_returns_sources_and_health(monkeypatch):
    health_payload = SourceRegistryHealthPayload(
        total_companies_cached=42,
        average_data_age_seconds=3600.0,
        recent_error_window_hours=72,
        sources_with_recent_errors=[
            SourceRegistryErrorPayload(
                source_id="yahoo_finance",
                source_tier="commercial_fallback",
                display_label="Yahoo Finance",
                affected_dataset_ids=["prices"],
                affected_company_count=3,
                failure_count=5,
                last_error="quote timeout",
                last_error_at=datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc),
            )
        ],
        stale_source_count=1,
        sources_with_active_errors_count=1,
        fallback_source_count=1,
        fallback_sources_recently_used_count=1,
        last_successful_refresh_at=datetime(2026, 1, 20, 11, 30, tzinfo=timezone.utc),
        worker_queue=SourceRegistryWorkerQueueHealthPayload(
            available=True,
            status="degraded",
            active_job_count=2,
            stalled_job_count=0,
            datasets_with_failures=1,
            failed_refresh_count=2,
            recent_failed_jobs=1,
        ),
        slos=[
            SourceRegistrySloPayload(
                key="sec_companyfacts_freshness",
                label="SEC companyfacts freshness",
                status="healthy",
                monitored_source_ids=["sec_companyfacts"],
                source_count=1,
                stale_count=0,
                active_error_count=0,
                last_success_at=datetime(2026, 1, 20, 11, 30, tzinfo=timezone.utc),
            ),
            SourceRegistrySloPayload(
                key="fallback_usage",
                label="Fallback usage",
                status="degraded",
                monitored_source_ids=["yahoo_finance"],
                source_count=1,
                stale_count=0,
                active_error_count=1,
                last_success_at=datetime(2026, 1, 20, 11, 0, tzinfo=timezone.utc),
                note="1 fallback source(s) with recent successful refresh.",
            ),
        ],
    )

    monkeypatch.setattr(main_module, "settings", SimpleNamespace(strict_official_mode=True))
    monkeypatch.setattr(main_module, "_build_source_registry_health_payload", lambda *_args, **_kwargs: health_payload)

    with _client(object()) as client:
        response = client.get("/api/source-registry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["strict_official_mode"] is True
    assert payload["generated_at"]
    assert payload["health"]["total_companies_cached"] == 42
    assert payload["health"]["average_data_age_seconds"] == 3600.0
    assert payload["health"]["sources_with_recent_errors"][0]["source_id"] == "yahoo_finance"
    assert payload["health"]["stale_source_count"] == 1
    assert payload["health"]["sources_with_active_errors_count"] == 1
    assert payload["health"]["worker_queue"]["status"] == "degraded"
    assert payload["health"]["slos"][0]["status"] == "healthy"

    sources = {entry["source_id"]: entry for entry in payload["sources"]}
    assert sources["sec_companyfacts"]["strict_official_mode_state"] == "available"
    assert sources["yahoo_finance"]["strict_official_mode_state"] == "disabled"
    assert "suppressed" in sources["yahoo_finance"]["strict_official_mode_note"].lower()
    assert "/api/companies/{ticker}/financials" in sources["sec_companyfacts"]["used_by_paths"]
    assert sources["sec_companyfacts"]["last_success_at"] is None
    assert sources["sec_companyfacts"]["is_stale"] is False


def test_source_registry_endpoint_degrades_when_health_query_fails(monkeypatch):
    monkeypatch.setattr(main_module, "settings", SimpleNamespace(strict_official_mode=False))
    monkeypatch.setattr(
        main_module,
        "_build_source_registry_health_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("pool busy")),
    )

    with _client(object()) as client:
        response = client.get("/api/source-registry")

    assert response.status_code == 200
    payload = response.json()
    assert payload["health"]["total_companies_cached"] == 0
    assert payload["health"]["average_data_age_seconds"] is None
    assert payload["health"]["recent_error_window_hours"] == 72
    assert payload["health"]["sources_with_recent_errors"] == []
    assert payload["health"]["stale_source_count"] == 0
    assert payload["health"]["sources_with_active_errors_count"] == 0
    assert payload["health"]["fallback_source_count"] == 0
    assert payload["health"]["fallback_sources_recently_used_count"] == 0
    assert payload["health"]["last_successful_refresh_at"] is None
    assert payload["health"]["worker_queue"] is None
    assert payload["health"]["slos"] == []


def test_build_source_registry_health_payload_computes_average_age(monkeypatch):
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    session = _FakeHealthSession(
        [
            now - timedelta(hours=2),
            now - timedelta(minutes=30),
            None,
        ],
        status_rows=[
            ("financials", now - timedelta(hours=2), now + timedelta(hours=2), None, now - timedelta(minutes=30)),
            ("prices", now - timedelta(hours=6), now - timedelta(hours=1), "quote timeout", now - timedelta(hours=1)),
        ],
        queue_rows=[
            ("job-1", now - timedelta(minutes=5), 0, None),
            (None, now - timedelta(minutes=20), 1, "quote timeout"),
        ],
    )
    expected_errors = [
        SourceRegistryErrorPayload(
            source_id="sec_edgar",
            source_tier="official_regulator",
            display_label="SEC EDGAR",
            affected_dataset_ids=["filings"],
            affected_company_count=1,
            failure_count=1,
            last_error="filing parse failed",
            last_error_at=now - timedelta(hours=1),
        )
    ]

    monkeypatch.setattr(main_module, "_build_source_registry_error_payloads", lambda *_args, **_kwargs: expected_errors)

    payload = main_module._build_source_registry_health_payload(session, now=now)

    assert payload.total_companies_cached == 2
    assert payload.average_data_age_seconds == 4500.0
    assert payload.recent_error_window_hours == 72
    assert payload.sources_with_recent_errors == expected_errors
    assert payload.stale_source_count == 1
    assert payload.sources_with_active_errors_count == 1
    assert payload.fallback_source_count >= 1
    assert payload.fallback_sources_recently_used_count == 1
    assert payload.last_successful_refresh_at == now - timedelta(hours=2)
    assert payload.worker_queue is not None
    assert payload.worker_queue.status == "degraded"
    assert payload.worker_queue.active_job_count == 1
    assert payload.worker_queue.datasets_with_failures == 1
    assert any(slo.key == "sec_companyfacts_freshness" and slo.status == "healthy" for slo in payload.slos)
    assert any(slo.key == "fallback_usage" and slo.status == "degraded" for slo in payload.slos)


def test_build_source_registry_error_payloads_aggregates_by_source():
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    session = _FakeErrorSession(
        [
            ("filings", 11, 2, "filing parse failed", now - timedelta(hours=4)),
            ("earnings", 12, 1, "earnings feed stale", now - timedelta(hours=1)),
            ("prices", 13, 4, "quote timeout", now - timedelta(hours=2)),
            ("unmapped_dataset", 14, 3, "ignore me", now - timedelta(hours=1)),
        ]
    )

    payloads = main_module._build_source_registry_error_payloads(session, now=now)

    assert [payload.source_id for payload in payloads] == ["sec_edgar", "yahoo_finance"]

    sec_edgar = payloads[0]
    assert sec_edgar.affected_dataset_ids == ["earnings", "filings"]
    assert sec_edgar.affected_company_count == 2
    assert sec_edgar.failure_count == 3
    assert sec_edgar.last_error == "earnings feed stale"
    assert sec_edgar.last_error_at == now - timedelta(hours=1)

    yahoo_finance = payloads[1]
    assert yahoo_finance.affected_dataset_ids == ["prices"]
    assert yahoo_finance.affected_company_count == 1
    assert yahoo_finance.failure_count == 4
    assert yahoo_finance.last_error == "quote timeout"
    assert yahoo_finance.last_error_at == now - timedelta(hours=2)


def test_build_source_registry_status_by_source_aggregates_latest_success_and_stale_state():
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    session = _FakeErrorSession(
        [
            ("financials", now - timedelta(hours=5), now - timedelta(hours=1), None, now - timedelta(minutes=20)),
            ("prices", now - timedelta(minutes=45), now - timedelta(minutes=5), "quote timeout", now - timedelta(minutes=10)),
            ("earnings_models", now - timedelta(hours=2), now - timedelta(hours=3), "model refresh stalled", now - timedelta(minutes=15)),
            ("unknown_dataset", now - timedelta(hours=1), now + timedelta(hours=1), "ignore me", now - timedelta(minutes=5)),
        ]
    )

    payload = source_registry_module._build_source_registry_status_by_source(session, now=now)

    assert payload["sec_companyfacts"]["last_success_at"] == now - timedelta(hours=5)
    assert payload["sec_companyfacts"]["is_stale"] is True
    assert payload["yahoo_finance"]["last_success_at"] == now - timedelta(minutes=45)
    assert payload["yahoo_finance"]["last_error"] == "quote timeout"
    assert payload["yahoo_finance"]["last_error_at"] == now - timedelta(minutes=10)
    assert payload["yahoo_finance"]["is_stale"] is True
    assert payload["ft_model_engine"]["last_error"] == "model refresh stalled"


def test_build_source_registry_usage_paths_maps_sources_to_user_visible_routes():
    payload = source_registry_module._build_source_registry_usage_paths()

    assert "/api/companies/{ticker}/financials" in payload["sec_companyfacts"]
    assert "/api/companies/search" in payload["sec_edgar"]
    assert "/api/source-registry" not in payload["sec_companyfacts"]