"""Tests for macro providers: Treasury HQM, Census, BLS, and BEA."""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

import app.services.macro_providers.treasury_hqm as hqm_module
import app.services.macro_providers.census_provider as census_module
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


def test_hqm_provider_suppresses_traceback_for_expected_http_failures(caplog, monkeypatch):
    request = httpx.Request("GET", "https://home.treasury.gov/sites/default/files/interest-rates/hqmYieldCurveData.csv")
    response = httpx.Response(status_code=404, request=request)

    def _raise_http_error(_client):
        raise httpx.HTTPStatusError("not found", request=request, response=response)

    monkeypatch.setattr(hqm_module, "_fetch_hqm_csv_with_fallback", _raise_http_error)

    result = hqm_module.fetch_hqm_snapshot(http_client=object())

    assert result.status == "unavailable"
    assert "Traceback" not in caplog.text


# ---------------------------------------------------------------------------
# Census provider tests
# ---------------------------------------------------------------------------

CENSUS_M3_JSON = [
    ["data_type_code", "category_code", "time_slot_id", "seasonally_adj", "cell_value", "time", "us"],
    ["VS", "MTM", "0", "yes", "605401", "2025-10", "1"],
    ["VS", "MTM", "0", "yes", "610055", "2025-12", "1"],
    ["NO", "MTM", "0", "yes", "605000", "2025-10", "1"],
    ["NO", "MTM", "0", "yes", "619137", "2025-12", "1"],
    ["UO", "MTM", "0", "yes", "1493279", "2025-10", "1"],
    ["UO", "MTM", "0", "yes", "1528230", "2025-12", "1"],
    ["TI", "MTM", "0", "yes", "947012", "2025-10", "1"],
    ["TI", "MTM", "0", "yes", "949081", "2025-12", "1"],
]

CENSUS_RETAIL_JSON = [
    ["data_type_code", "category_code", "seasonally_adj", "cell_value", "time", "us"],
    ["SM", "44X72", "yes", "731051", "2025-10", "1"],
    ["SM", "44X72", "yes", "734685", "2025-12", "1"],
]


class _FakeCensusResponse:
    def __init__(self, payload: list, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("HTTP error")


class _FakeCensusHttp:
    def get(self, url: str, **_kwargs):
        if url.endswith("/m3"):
            return _FakeCensusResponse(CENSUS_M3_JSON)
        if url.endswith("/marts"):
            return _FakeCensusResponse(CENSUS_RETAIL_JSON)
        return _FakeCensusResponse([], status_code=404)


def test_census_provider_parses_m3_and_retail_sales():
    results = census_module.fetch_census_series(http_client=_FakeCensusHttp())
    by_id = {result.series_id: result for result in results}

    assert by_id["census_m3_shipments_total"].value == pytest.approx(610055)
    assert by_id["census_m3_new_orders_total"].previous_value == pytest.approx(605000)
    assert by_id["census_m3_backlog_total"].status == "ok"
    assert by_id["census_m3_inventories_total"].observation_date == date(2025, 12, 31)
    assert by_id["census_retail_sales_total"].value == pytest.approx(734685)


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
        self.last_url = None
        self.last_content = None

    def post(self, _url: str, **_kwargs):
        self.last_url = _url
        self.last_content = _kwargs.get("content")
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
            bls_api_base_url="https://api.bls.gov/publicAPI/v2/timeseries/data/",
            bls_api_key="test-bls-key",
            bls_timeout_seconds=5,
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


def test_bls_provider_includes_registration_key_when_configured(monkeypatch):
    monkeypatch.setattr(
        bls_module,
        "settings",
        SimpleNamespace(
            sec_user_agent="test-agent",
            bls_api_base_url="https://api.bls.gov/publicAPI/v2/timeseries/data/",
            bls_api_key="test-bls-key",
            bls_timeout_seconds=5,
            market_max_retries=1,
            market_retry_backoff_seconds=0.0,
        ),
    )

    client = _FakeHttpJson(BLS_RESPONSE_JSON)
    bls_module.fetch_bls_series(http_client=client)

    assert client.last_url == "https://api.bls.gov/publicAPI/v2/timeseries/data/"
    assert client.last_content is not None
    request_body = json.loads(client.last_content)
    assert request_body["registrationkey"] == "test-bls-key"


def test_bls_provider_includes_eci_and_jolts_series():
    payload = {
        "status": "REQUEST_SUCCEEDED",
        "Results": {
            "series": [
                {
                    "seriesID": "CIU1010000000000I",
                    "data": [
                        {"year": "2025", "period": "Q04", "value": "167.4", "footnotes": [{}]},
                        {"year": "2024", "period": "Q04", "value": "161.0", "footnotes": [{}]},
                    ],
                },
                {
                    "seriesID": "JTS000000000000000JOL",
                    "data": [
                        {"year": "2026", "period": "M02", "value": "7760", "footnotes": [{}]},
                        {"year": "2026", "period": "M01", "value": "7700", "footnotes": [{}]},
                    ],
                },
            ]
        },
    }

    results = bls_module.fetch_bls_series(http_client=_FakeHttpJson(payload))
    by_id = {result.series_id: result for result in results}

    assert by_id["CIU1010000000000I"].status == "ok"
    assert by_id["CIU1010000000000I"].section == "cyclical_costs"
    assert by_id["JTS000000000000000JOL"].value == pytest.approx(7760)
    assert by_id["JTS000000000000000JOL"].units == "thousands"


# ---------------------------------------------------------------------------
# BEA provider tests
# ---------------------------------------------------------------------------

def test_bea_provider_returns_stubs_without_api_key(monkeypatch):
    monkeypatch.setattr(
        bea_module,
        "settings",
        SimpleNamespace(
            bea_api_key=None,
            sec_user_agent="test-agent",
            bea_timeout_seconds=5,
        ),
    )
    results = bea_module.fetch_bea_series()
    # All should be unavailable stubs when no BEA key is configured.
    assert all(r.status == "unavailable" for r in results)
    assert len(results) >= 1


def test_bea_provider_fetches_pce_and_gdp_by_industry(monkeypatch):
    monkeypatch.setattr(
        bea_module,
        "settings",
        SimpleNamespace(
            bea_api_key="fake-key",
            bea_api_base_url="https://apps.bea.gov/api/data",
            sec_user_agent="test-agent",
            bea_timeout_seconds=5,
            bea_pce_table_name="T20805",
            bea_pce_line_number="1",
            bea_gdp_by_industry_table_id="1",
        ),
    )

    nipa_response = {
        "BEAAPI": {
            "Results": {
                "Data": [
                    {"TimePeriod": "2025M11", "DataValue": "19987.3"},
                    {"TimePeriod": "2025M12", "DataValue": "20015.2"},
                ]
            }
        }
    }
    gdp_response = {
        "BEAAPI": {
            "Results": {
                "Data": [
                    {"IndustrYDescription": "Manufacturing", "TimePeriod": "2024", "DataValue": "2890.4"},
                    {"IndustrYDescription": "Manufacturing", "TimePeriod": "2025", "DataValue": "2944.1"},
                    {"IndustrYDescription": "Retail trade", "TimePeriod": "2024", "DataValue": "1460.1"},
                    {"IndustrYDescription": "Retail trade", "TimePeriod": "2025", "DataValue": "1483.8"},
                ]
            }
        }
    }

    class _FakeBeaHttp:
        def __init__(self):
            self.calls = 0

        def get(self, _url: str, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                return _FakeJsonResponse(nipa_response)
            return _FakeJsonResponse(gdp_response)

    results = bea_module.fetch_bea_series(http_client=_FakeBeaHttp())
    by_id = {result.series_id: result for result in results}

    assert by_id["bea_pce_total"].status == "ok"
    assert by_id["bea_pce_total"].value == pytest.approx(20015.2, abs=0.01)
    assert by_id["bea_gdp_manufacturing"].value == pytest.approx(2944.1, abs=0.01)
    assert by_id["bea_gdp_retail_trade"].previous_value == pytest.approx(1460.1, abs=0.01)
