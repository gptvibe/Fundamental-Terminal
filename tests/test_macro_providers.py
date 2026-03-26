"""Tests for macro providers: Treasury HQM, BLS, BEA."""
from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import app.services.macro_providers.treasury_hqm as hqm_module
import app.services.macro_providers.bls_provider as bls_module
import app.services.macro_providers.bea_provider as bea_module


# ---------------------------------------------------------------------------
# HQM provider tests
# ---------------------------------------------------------------------------

HQM_CSV_SAMPLE = (
    "Date,0.5,1,1.5,2,3,4,5,6,7,8,9,10,15,20,25,30,40,50,60,70,80,90,100\n"
    "01/01/2026,4.1,4.2,4.3,4.4,4.5,4.6,4.7,4.8,4.9,5.0,5.1,5.2,5.3,5.4,5.5,5.6,5.7,5.8,5.9,6.0,6.1,6.2,6.3\n"
    "12/01/2025,3.9,4.0,4.1,4.2,4.3,4.4,4.5,4.6,4.7,4.8,4.9,5.0,5.1,5.2,5.3,5.4,5.5,5.6,5.7,5.8,5.9,6.0,6.1\n"
)


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")


class _FakeHttp:
    def __init__(self, response: _FakeResponse):
        self._response = response

    def get(self, _url: str, **_kwargs):
        return self._response

    def post(self, _url: str, **_kwargs):
        return self._response


def test_hqm_provider_parses_30y_yield():
    client = _FakeHttp(_FakeResponse(HQM_CSV_SAMPLE))
    result = hqm_module.fetch_hqm_snapshot(http_client=client)
    assert result.status == "ok"
    assert result.hqm_30y is not None
    # Row 1: "30" column = 5.6 (percent); stored as decimal 0.056
    assert abs(result.hqm_30y - 0.056) < 0.001
    # Date is Jan 2026, which is the latest row
    assert result.observation_date is not None
    assert result.observation_date.year == 2026


def test_hqm_provider_returns_unavailable_on_http_error():
    client = _FakeHttp(_FakeResponse("", status_code=500))
    result = hqm_module.fetch_hqm_snapshot(http_client=client)
    assert result.status == "unavailable"
    assert result.hqm_30y is None


def test_hqm_provider_falls_back_when_primary_url_404(monkeypatch):
    class _HttpByUrl:
        def get(self, url: str, **_kwargs):
            if "system/files/276" in url:
                return _FakeResponse("", status_code=404)
            return _FakeResponse(HQM_CSV_SAMPLE, status_code=200)

    result = hqm_module.fetch_hqm_snapshot(http_client=_HttpByUrl())
    assert result.status == "ok"
    assert result.hqm_30y is not None
    assert "interest-rates/hqmYieldCurveData.csv" in result.source_url


def test_hqm_provider_returns_unavailable_on_empty_body():
    client = _FakeHttp(_FakeResponse(""))
    result = hqm_module.fetch_hqm_snapshot(http_client=client)
    # Empty body should return unavailable or at least not raise
    assert result.status in ("unavailable", "partial")


# ---------------------------------------------------------------------------
# BLS provider tests
# ---------------------------------------------------------------------------

BLS_RESPONSE_JSON = {
    "status": "REQUEST_SUCCEEDED",
    "Results": {
        "series": [
            {
                "seriesID": "CUSR0000SA0",
                "data": [
                    {"year": "2026", "period": "M02", "value": "318.2", "footnotes": [{}]},
                    {"year": "2026", "period": "M01", "value": "317.0", "footnotes": [{}]},
                    {"year": "2025", "period": "M02", "value": "308.4", "footnotes": [{}]},
                ],
            },
            {
                "seriesID": "LNS14000000",
                "data": [
                    {"year": "2026", "period": "M02", "value": "4.1", "footnotes": [{}]},
                    {"year": "2026", "period": "M01", "value": "4.2", "footnotes": [{}]},
                ],
            },
        ]
    },
}


class _FakeJsonResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")


class _FakeHttpJson:
    def __init__(self, payload: dict):
        self._payload = payload

    def post(self, _url: str, **_kwargs):
        return _FakeJsonResponse(self._payload)


def test_bls_provider_parses_cpi_and_unemployment():
    client = _FakeHttpJson(BLS_RESPONSE_JSON)
    results = bls_module.fetch_bls_series(http_client=client)
    assert len(results) >= 1
    cpi = next((r for r in results if r.series_id == "CUSR0000SA0"), None)
    assert cpi is not None
    # label from BLS_SERIES definition
    assert "CPI" in cpi.label
    # YoY: (318.2 - 308.4) / 308.4 ≈ 3.18 (percentage points or decimal)
    assert cpi.value is not None
    # Value should be a non-zero positive number (YoY CPI change)
    assert cpi.value > 0


def test_bls_provider_returns_empty_on_http_error():
    class _BadHttp:
        def post(self, _url: str, **_kwargs):
            raise RuntimeError("network error")

    results = bls_module.fetch_bls_series(http_client=_BadHttp())
    # On network error the provider returns stubs with status="unavailable"
    assert all(r.status == "unavailable" for r in results)


def test_bls_provider_retries_after_transient_exception(monkeypatch):
    monkeypatch.setattr(
        bls_module,
        "settings",
        SimpleNamespace(
            sec_user_agent="test-agent",
            sec_timeout_seconds=5,
            market_max_retries=2,
            market_retry_backoff_seconds=0.0,
        ),
    )

    class _FlakyHttp:
        def __init__(self):
            self.calls = 0

        def post(self, _url: str, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("temporary network error")
            return _FakeJsonResponse(BLS_RESPONSE_JSON)

    client = _FlakyHttp()
    results = bls_module.fetch_bls_series(http_client=client)
    assert client.calls == 2
    assert any(r.status == "ok" for r in results)


# ---------------------------------------------------------------------------
# BEA provider tests
# ---------------------------------------------------------------------------

def test_bea_provider_returns_stubs_without_fred_key(monkeypatch):
    monkeypatch.setattr(
        bea_module,
        "settings",
        SimpleNamespace(
            fred_api_key=None,
            sec_user_agent="test-agent",
            sec_timeout_seconds=5,
            market_max_retries=1,
            market_retry_backoff_seconds=0.0,
        ),
    )
    results = bea_module.fetch_bea_series()
    # All should be unavailable stubs when no FRED key
    assert all(r.status == "unavailable" for r in results)
    assert len(results) >= 1


def test_bea_provider_fetches_gdp_via_fred(monkeypatch):
    monkeypatch.setattr(
        bea_module,
        "settings",
        SimpleNamespace(
            fred_api_key="fake-key",
            sec_user_agent="test-agent",
            sec_timeout_seconds=5,
            market_max_retries=1,
            market_retry_backoff_seconds=0.0,
        ),
    )

    fred_response = {
        "observations": [
            {"date": "2025-10-01", "value": "2.8"},
            {"date": "2025-07-01", "value": "3.0"},
            {"date": "2025-04-01", "value": "3.1"},
        ]
    }

    class _FakeFredHttp:
        def get(self, _url: str, **_kwargs):
            return _FakeJsonResponse(fred_response)

    results = bea_module.fetch_bea_series(http_client=_FakeFredHttp())
    gdp = next((r for r in results if "GDP" in r.series_id or "gdp" in r.label.lower()), None)
    assert gdp is not None
    assert gdp.status == "ok"
    assert gdp.value == pytest.approx(2.8, abs=0.01)
