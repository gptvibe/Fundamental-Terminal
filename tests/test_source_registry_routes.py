from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.api.schemas.source_registry import SourceRegistryErrorPayload, SourceRegistryHealthPayload
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
    def __init__(self, last_checked_values):
        self._last_checked_values = last_checked_values

    def execute(self, _statement):
        return _FakeScalarResult(self._last_checked_values)


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

    sources = {entry["source_id"]: entry for entry in payload["sources"]}
    assert sources["sec_companyfacts"]["strict_official_mode_state"] == "available"
    assert sources["yahoo_finance"]["strict_official_mode_state"] == "disabled"
    assert "suppressed" in sources["yahoo_finance"]["strict_official_mode_note"].lower()


def test_build_source_registry_health_payload_computes_average_age(monkeypatch):
    now = datetime(2026, 1, 20, 12, 0, tzinfo=timezone.utc)
    session = _FakeHealthSession(
        [
            now - timedelta(hours=2),
            now - timedelta(minutes=30),
            None,
        ]
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