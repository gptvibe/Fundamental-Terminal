from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.services import official_oil_inputs


class _StubResponse:
    def __init__(self, *, json_data=None, status_code: int = 200):
        self._json_data = json_data
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def json(self):
        return self._json_data


class _StubClient:
    def __init__(self, responses):
        self._responses = list(responses)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def get(self, _url: str, params=None):
        return self._responses.pop(0)


def test_fetch_official_oil_inputs_normalizes_spot_and_steo_series(monkeypatch) -> None:
    checked_at = datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        official_oil_inputs,
        "settings",
        SimpleNamespace(
            eia_api_key="demo-key",
            eia_api_base_url="https://api.eia.gov/v2",
            eia_timeout_seconds=30.0,
            freshness_window_hours=24,
            strict_official_mode=True,
        ),
    )
    monkeypatch.setattr(
        official_oil_inputs,
        "build_http_client",
        lambda *, timeout_seconds: _StubClient(
            [
                _StubResponse(
                    json_data={
                        "response": {
                            "data": [
                                {"period": "2026-04-02", "series-description": "Europe Brent Spot Price FOB", "value": "86.25"},
                                {"period": "2026-04-03", "series-description": "Europe Brent Spot Price FOB", "value": "87.10"},
                                {"period": "2026-04-02", "series-description": "Cushing, OK WTI Spot Price FOB", "value": "82.95"},
                                {"period": "2026-04-03", "series-description": "Cushing, OK WTI Spot Price FOB", "value": "83.40"},
                            ]
                        }
                    }
                ),
                _StubResponse(
                    json_data={
                        "response": {
                            "data": [
                                {"period": "2026-04", "series-description": "Brent crude oil spot price", "value": "86.80"},
                                {"period": "2026-05", "series-description": "Brent crude oil spot price", "value": "85.90"},
                                {"period": "2026-04", "series-description": "WTI crude oil spot price", "value": "83.00"},
                                {"period": "2026-05", "series-description": "WTI crude oil spot price", "value": "82.20"},
                            ]
                        }
                    }
                ),
            ]
        ),
    )

    payload = official_oil_inputs.get_official_oil_inputs_payload(now=checked_at)

    assert payload["status"] == "ok"
    assert payload["as_of"] == "2026-05"
    assert payload["last_refreshed_at"] == checked_at.isoformat()
    assert payload["strict_official_mode"] is True
    assert payload["strict_official_compatible"] is True
    assert payload["source_mix"]["official_only"] is True
    assert payload["source_mix"]["source_ids"] == ["eia_petroleum_spot_prices", "eia_steo"]
    assert payload["spot_history"][0]["series_id"] == "wti_spot_history"
    assert payload["spot_history"][0]["latest_value"] == 83.4
    assert payload["short_term_baseline"][1]["series_id"] == "brent_short_term_baseline"
    assert payload["short_term_baseline"][1]["latest_observation_date"] == "2026-05"
    assert payload["long_term_anchor"]["status"] == "not_set"
    assert payload["freshness"]["status"] == "fresh"
    assert [entry["source_id"] for entry in payload["provenance"]] == ["eia_petroleum_spot_prices", "eia_steo"]
    assert "strict_official_mode" in payload["confidence_flags"]


def test_build_official_oil_inputs_freshness_marks_stale_when_window_expires(monkeypatch) -> None:
    monkeypatch.setattr(
        official_oil_inputs,
        "settings",
        SimpleNamespace(
            freshness_window_hours=24,
            strict_official_mode=False,
            eia_api_key="demo-key",
            eia_api_base_url="https://api.eia.gov/v2",
            eia_timeout_seconds=30.0,
        ),
    )
    refreshed_at = datetime(2026, 4, 2, 12, 0, tzinfo=timezone.utc)
    now = refreshed_at + timedelta(hours=25)

    freshness = official_oil_inputs.build_official_oil_inputs_freshness(
        last_refreshed_at=refreshed_at,
        now=now,
        has_data=True,
    )

    assert freshness["status"] == "stale"
    assert freshness["is_stale"] is True
    assert freshness["freshness_deadline"] == (refreshed_at + timedelta(hours=24)).isoformat()
    assert freshness["stale_flags"] == ["official_oil_inputs_stale"]


def test_fetch_official_oil_inputs_returns_official_only_unavailable_payload_without_api_key(monkeypatch) -> None:
    checked_at = datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        official_oil_inputs,
        "settings",
        SimpleNamespace(
            eia_api_key=None,
            eia_api_base_url="https://api.eia.gov/v2",
            eia_timeout_seconds=30.0,
            freshness_window_hours=24,
            strict_official_mode=False,
        ),
    )

    payload = official_oil_inputs.get_official_oil_inputs_payload(now=checked_at)

    assert payload["status"] == "unavailable"
    assert payload["strict_official_compatible"] is True
    assert payload["source_mix"]["official_only"] is True
    assert payload["freshness"]["status"] == "missing"
    assert "eia_api_key_missing" in payload["confidence_flags"]
    assert all(series["status"] == "unavailable" for series in payload["spot_history"])
    assert all(series["status"] == "unavailable" for series in payload["short_term_baseline"])


def test_fetch_official_oil_inputs_reports_partial_when_one_dataset_fails(monkeypatch) -> None:
    checked_at = datetime(2026, 4, 4, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(
        official_oil_inputs,
        "settings",
        SimpleNamespace(
            eia_api_key="demo-key",
            eia_api_base_url="https://api.eia.gov/v2",
            eia_timeout_seconds=30.0,
            freshness_window_hours=24,
            strict_official_mode=False,
        ),
    )
    monkeypatch.setattr(
        official_oil_inputs,
        "build_http_client",
        lambda *, timeout_seconds: _StubClient(
            [
                _StubResponse(
                    json_data={
                        "response": {
                            "data": [
                                {"period": "2026-04-02", "series-description": "Europe Brent Spot Price FOB", "value": "86.25"},
                                {"period": "2026-04-03", "series-description": "Europe Brent Spot Price FOB", "value": "87.10"},
                                {"period": "2026-04-02", "series-description": "Cushing, OK WTI Spot Price FOB", "value": "82.95"},
                                {"period": "2026-04-03", "series-description": "Cushing, OK WTI Spot Price FOB", "value": "83.40"},
                            ]
                        }
                    }
                ),
                _StubResponse(json_data={"unexpected": {}}),
            ]
        ),
    )

    payload = official_oil_inputs.get_official_oil_inputs_payload(now=checked_at)

    assert payload["status"] == "partial"
    assert "official_oil_partial_data" in payload["confidence_flags"]
    assert payload["diagnostics"]["failed_dataset_ids"] == ["steo_baseline"]
    assert payload["spot_history"][0]["status"] == "ok"
    assert payload["short_term_baseline"][0]["status"] == "unavailable"
    assert payload["source_mix"]["official_only"] is True