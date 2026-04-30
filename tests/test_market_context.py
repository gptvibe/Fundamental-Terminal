from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

import app.main as main_module
from app.api.handlers import _shared as _shared_handlers
from app.api.handlers import market_context as _market_context_handlers
from app.main import RefreshState, app
import app.services.market_context as market_context_module


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("http error")

    def close(self) -> None:
        return None


class _FakeHttp:
    def __init__(self, responses):
        self._responses = list(responses)

    def get(self, _url: str):
        return self._responses.pop(0)

    def close(self) -> None:
        return None


def _snapshot(ticker: str = "AAPL"):
    company = SimpleNamespace(
        id=1,
        ticker=ticker,
        cik="0000320193",
        name="Apple Inc.",
        sector="Technology",
        market_sector="Technology",
        market_industry="Consumer Electronics",
    )
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=datetime.now(timezone.utc))


def test_market_context_client_returns_partial_without_fred_key(monkeypatch, tmp_path):
    monkeypatch.setattr(
        market_context_module,
        "settings",
        SimpleNamespace(
            sec_user_agent="test-agent",
            sec_timeout_seconds=10,
            market_context_cache_ttl_hours=6,
            fred_api_key=None,
            treasury_yield_curve_csv_url="https://example.test/treasury.csv",
            treasury_max_retries=1,
            treasury_retry_backoff_seconds=0,
            market_max_retries=1,
            market_retry_backoff_seconds=0,
        ),
    )

    client = market_context_module.MarketContextClient(cache_file=tmp_path / "market_context.json")
    client._http = _FakeHttp([_FakeResponse("Date,2 Yr,3 Mo,10 Yr\n03/21/2026,4.00,4.50,4.25\n")])

    snapshot = client.get_market_context()
    assert snapshot.status == "partial"
    assert snapshot.curve_points
    assert snapshot.slope_2s10s.value == pytest.approx(0.0025)
    assert snapshot.provenance["fred"]["status"] == "missing_api_key"


def test_market_context_client_uses_same_day_cache_without_refetch(monkeypatch, tmp_path):
    monkeypatch.setattr(
        market_context_module,
        "settings",
        SimpleNamespace(
            sec_user_agent="test-agent",
            sec_timeout_seconds=10,
            market_context_cache_ttl_hours=6,
            fred_api_key=None,
            treasury_yield_curve_csv_url="https://example.test/treasury.csv",
            treasury_max_retries=1,
            treasury_retry_backoff_seconds=0,
            market_max_retries=1,
            market_retry_backoff_seconds=0,
        ),
    )

    client = market_context_module.MarketContextClient(cache_file=tmp_path / "market_context.json")
    client._http = _FakeHttp([_FakeResponse("Date,2 Yr,3 Mo,10 Yr\n03/21/2026,4.00,4.50,4.25\n")])

    first = client.get_market_context()
    second = client.get_market_context()

    assert first.fetched_at == second.fetched_at
    assert second.slope_2s10s.value == pytest.approx(0.0025)


def test_market_context_client_uses_fred_curve_when_treasury_csv_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(
        market_context_module,
        "settings",
        SimpleNamespace(
            sec_user_agent="test-agent",
            sec_timeout_seconds=10,
            market_context_cache_ttl_hours=6,
            fred_api_key="fred-key",
            treasury_yield_curve_csv_url="https://example.test/treasury.csv",
            treasury_max_retries=1,
            treasury_retry_backoff_seconds=0,
            market_max_retries=1,
            market_retry_backoff_seconds=0,
        ),
    )

    responses = [
        _FakeResponse("", status_code=404),
        _FakeResponse("", status_code=403),
        _FakeResponse('{"observations":[{"date":"2026-03-21","value":"4.80"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-03-21","value":"4.55"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-03-21","value":"4.52"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-03-21","value":"4.50"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-03-21","value":"4.47"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-03-21","value":"4.42"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-03-21","value":"4.30"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-03-21","value":"4.18"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-03-21","value":"4.08"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-03-21","value":"4.05"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-03-21","value":"4.16"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-03-21","value":"4.22"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-03-21","value":"4.48"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-03-21","value":"4.61"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-03-20","value":"1.80"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-02-01","value":"0"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-03-20","value":"2.30"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-02-01","value":"2.90"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-02-01","value":"3.10"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-02-01","value":"2.70"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-02-01","value":"2.80"}]}'),
        _FakeResponse('{"observations":[{"date":"2026-02-01","value":"4.10"}]}'),
    ]

    client = market_context_module.MarketContextClient(cache_file=tmp_path / "market_context.json")
    client._http = _FakeHttp(responses)

    snapshot = client.get_market_context()

    tenors = [point.tenor for point in snapshot.curve_points]
    assert "rrp" in tenors
    assert "4m" in tenors
    assert snapshot.slope_2s10s.value == pytest.approx(0.0004)
    assert snapshot.slope_3m10y.value == pytest.approx(-0.0028)
    assert snapshot.provenance["treasury"]["source_name"] == "Federal Reserve Economic Data (FRED)"


def test_company_market_context_route_returns_payload(monkeypatch):
    from app.db import get_db_session

    _snapshot_fn = lambda *_args, **_kwargs: _snapshot()
    _refresh_fn = lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None)
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", _snapshot_fn)
    monkeypatch.setattr(_shared_handlers, "_resolve_cached_company_snapshot", _snapshot_fn)
    monkeypatch.setattr(main_module, "_refresh_for_snapshot", _refresh_fn)
    monkeypatch.setattr(_shared_handlers, "_refresh_for_snapshot", _refresh_fn)
    _serialize_company_fn = lambda *_args, **_kwargs: {
            "ticker": "AAPL",
            "cik": "0000320193",
            "name": "Apple Inc.",
            "sector": "Technology",
            "market_sector": "Technology",
            "market_industry": "Consumer Electronics",
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "last_checked_financials": None,
            "last_checked_prices": None,
            "last_checked_insiders": None,
            "last_checked_institutional": None,
            "last_checked_filings": None,
            "cache_state": "fresh",
        }
    monkeypatch.setattr(main_module, "_serialize_company", _serialize_company_fn)
    monkeypatch.setattr(_shared_handlers, "_serialize_company", _serialize_company_fn)
    monkeypatch.setattr(
        _market_context_handlers,
        "get_company_market_context_v2",
        lambda *_args, **_kwargs: {
            "status": "partial",
            "curve_points": [
                {"tenor": "2y", "rate": 0.04, "observation_date": "2026-03-21"},
                {"tenor": "10y", "rate": 0.0425, "observation_date": "2026-03-21"},
            ],
            "slope_2s10s": {"label": "2s10s", "value": 0.0025, "short_tenor": "2y", "long_tenor": "10y", "observation_date": "2026-03-21"},
            "slope_3m10y": {"label": "3m10y", "value": -0.0025, "short_tenor": "3m", "long_tenor": "10y", "observation_date": "2026-03-21"},
            "fred_series": [],
            "provenance": {"treasury": {"status": "ok"}, "fred": {"enabled": False, "status": "missing_api_key"}},
            "fetched_at": "2026-03-22T00:00:00+00:00",
            "rates_credit": [],
            "inflation_labor": [],
            "growth_activity": [{
                "series_id": "bea_pce_total",
                "label": "Personal Consumption Expenditures",
                "source_name": "Bureau of Economic Analysis",
                "source_url": "https://www.bea.gov/data/consumer-spending/main",
                "units": "billions_usd",
                "value": 20015.2,
                "previous_value": 19987.3,
                "change": 27.9,
                "change_percent": 0.0014,
                "observation_date": "2025-12-31",
                "release_date": None,
                "history": [],
                "status": "ok",
            }],
            "cyclical_demand": [{
                "series_id": "census_m3_new_orders_total",
                "label": "Manufacturing New Orders (M3)",
                "source_name": "U.S. Census Bureau Economic Indicators",
                "source_url": "https://api.census.gov/data/timeseries/eits/m3",
                "units": "millions_usd",
                "value": 619137,
                "previous_value": 621859,
                "change": -2722,
                "change_percent": -0.0044,
                "observation_date": "2025-12-31",
                "release_date": None,
                "history": [],
                "status": "ok",
            }],
            "cyclical_costs": [{
                "series_id": "CIU1010000000000I",
                "label": "Employment Cost Index (Total Compensation)",
                "source_name": "U.S. Bureau of Labor Statistics",
                "source_url": "https://www.bls.gov/data/",
                "units": "percent",
                "value": 0.0398,
                "previous_value": 0.034,
                "change": 0.0058,
                "change_percent": 0.1705,
                "observation_date": "2025-12-31",
                "release_date": None,
                "history": [],
                "status": "ok",
            }],
            "relevant_series": [],
            "relevant_indicators": [{
                "series_id": "census_m3_new_orders_total",
                "label": "Manufacturing New Orders (M3)",
                "source_name": "U.S. Census Bureau Economic Indicators",
                "source_url": "https://api.census.gov/data/timeseries/eits/m3",
                "units": "millions_usd",
                "value": 619137,
                "previous_value": 621859,
                "change": -2722,
                "change_percent": -0.0044,
                "observation_date": "2025-12-31",
                "release_date": None,
                "history": [],
                "status": "ok",
            }],
            "sector_exposure": [],
            "hqm_snapshot": None,
        },
    )

    app.dependency_overrides[get_db_session] = lambda: None
    try:
        client = TestClient(app)
        response = client.get("/api/companies/AAPL/market-context")
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "partial"
    assert payload["curve_points"]
    assert payload["provenance_details"]["fred"]["status"] == "missing_api_key"
    assert {entry["source_id"] for entry in payload["provenance"]} == {
        "bea_nipa",
        "bls_public_data",
        "census_eits_m3",
        "us_treasury_daily_par_yield_curve",
    }
    assert payload["as_of"] == "2026-03-21"
    assert payload["last_refreshed_at"].startswith("2026-03-22T00:00:00")
    assert payload["source_mix"]["official_only"] is True
    assert "market_context_partial" in payload["confidence_flags"]
    assert "supplemental_fred_unconfigured" in payload["confidence_flags"]
    assert payload["cyclical_demand"][0]["series_id"] == "census_m3_new_orders_total"
    assert payload["cyclical_costs"][0]["series_id"] == "CIU1010000000000I"
    assert payload["relevant_indicators"][0]["series_id"] == "census_m3_new_orders_total"


def test_company_market_context_route_skips_malformed_cached_sections(monkeypatch):
    from app.db import get_db_session

    _snapshot_fn = lambda *_args, **_kwargs: _snapshot()
    _refresh_fn = lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None)
    _serialize_company_fn = lambda *_args, **_kwargs: {
            "ticker": "AAPL",
            "cik": "0000320193",
            "name": "Apple Inc.",
            "sector": "Technology",
            "market_sector": "Technology",
            "market_industry": "Consumer Electronics",
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "last_checked_financials": None,
            "last_checked_prices": None,
            "last_checked_insiders": None,
            "last_checked_institutional": None,
            "last_checked_filings": None,
            "cache_state": "fresh",
        }

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", _snapshot_fn)
    monkeypatch.setattr(_shared_handlers, "_resolve_cached_company_snapshot", _snapshot_fn)
    monkeypatch.setattr(main_module, "_refresh_for_snapshot", _refresh_fn)
    monkeypatch.setattr(_shared_handlers, "_refresh_for_snapshot", _refresh_fn)
    monkeypatch.setattr(main_module, "_serialize_company", _serialize_company_fn)
    monkeypatch.setattr(_shared_handlers, "_serialize_company", _serialize_company_fn)
    monkeypatch.setattr(
        _market_context_handlers,
        "get_company_market_context_v2",
        lambda *_args, **_kwargs: {
            "status": "partial",
            "curve_points": [
                {"tenor": "10y", "rate": "0.0425", "observation_date": "2026-03-21"},
                None,
                {"tenor": "", "rate": 0.04, "observation_date": "2026-03-21"},
            ],
            "slope_2s10s": {"label": "2s10s", "value": "0.0025", "short_tenor": "2y", "long_tenor": "10y", "observation_date": "2026-03-21"},
            "slope_3m10y": {"label": "3m10y", "value": None, "short_tenor": "3m", "long_tenor": "10y", "observation_date": "2026-03-21"},
            "fred_series": [
                {"series_id": "UNRATE", "label": "Unemployment Rate", "category": "labor", "units": "percent", "value": "0.041", "observation_date": "2026-03-01", "state": "ok"},
                "bad-entry",
            ],
            "provenance": {"treasury": {"status": "ok"}, "fred": {"enabled": True, "status": "ok"}},
            "fetched_at": "2026-03-22T00:00:00+00:00",
            "rates_credit": [
                {
                    "series_id": "baa_10y_spread",
                    "label": "BAA Spread",
                    "source_name": "FRED",
                    "source_url": "https://fred.stlouisfed.org/series/BAA10Y",
                    "units": "percent",
                    "value": "0.018",
                    "previous_value": None,
                    "change": None,
                    "change_percent": None,
                    "observation_date": "2026-03-01",
                    "release_date": None,
                    "history": [
                        {"date": "2026-02-01", "value": "0.017"},
                        {"date": None, "value": 0.018},
                        "bad-history",
                    ],
                    "status": "ok",
                },
                "bad-section-entry",
            ],
            "inflation_labor": [],
            "growth_activity": [],
            "cyclical_demand": [],
            "cyclical_costs": [],
            "relevant_series": ["baa_10y_spread", None],
            "relevant_indicators": [
                {
                    "series_id": "baa_10y_spread",
                    "label": "BAA Spread",
                    "source_name": "FRED",
                    "source_url": "https://fred.stlouisfed.org/series/BAA10Y",
                    "units": "percent",
                    "value": 0.018,
                    "previous_value": None,
                    "change": None,
                    "change_percent": None,
                    "observation_date": "2026-03-01",
                    "release_date": None,
                    "history": [],
                    "status": "ok",
                },
                7,
            ],
            "sector_exposure": ["semiconductors", None],
            "hqm_snapshot": "invalid",
        },
    )

    app.dependency_overrides[get_db_session] = lambda: None
    try:
        client = TestClient(app)
        response = client.get("/api/companies/AAPL/market-context")
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["curve_points"] == [{"tenor": "10y", "rate": 0.0425, "observation_date": "2026-03-21"}]
    assert payload["fred_series"] == [{
        "series_id": "UNRATE",
        "label": "Unemployment Rate",
        "category": "labor",
        "units": "percent",
        "value": 0.041,
        "observation_date": "2026-03-01",
        "state": "ok",
    }]
    assert payload["rates_credit"][0]["history"] == [{"date": "2026-02-01", "value": 0.017}]
    assert payload["relevant_series"] == ["baa_10y_spread"]
    assert payload["sector_exposure"] == ["semiconductors"]
    assert payload["hqm_snapshot"] is None


def test_parse_treasury_curve_textview_extracts_2m_and_4m():
        html_payload = """
        <table>
            <tr>
                <th>Date</th><th>1 Mo</th><th>2 Mo</th><th>3 Mo</th><th>4 Mo</th><th>6 Mo</th>
                <th>1 Yr</th><th>2 Yr</th><th>3 Yr</th><th>5 Yr</th><th>7 Yr</th><th>10 Yr</th><th>20 Yr</th><th>30 Yr</th>
            </tr>
            <tr>
                <td>03/21/2026</td><td>4.55</td><td>4.52</td><td>4.50</td><td>4.47</td><td>4.42</td>
                <td>4.30</td><td>4.18</td><td>4.08</td><td>4.05</td><td>4.16</td><td>4.22</td><td>4.48</td><td>4.61</td>
            </tr>
        </table>
        """

        points, obs_date = market_context_module._parse_treasury_curve_textview(html_payload)

        by_tenor = {point.tenor: point.rate for point in points}
        assert obs_date == date(2026, 3, 21)
        assert by_tenor["2m"] == pytest.approx(0.0452)
        assert by_tenor["4m"] == pytest.approx(0.0447)


def test_normalize_percent_decimal_handles_mixed_provider_scales():
    # Already-decimal FRED fallback values should remain unchanged.
    assert market_context_module._normalize_percent_decimal(0.02434, "percent") == pytest.approx(0.02434)
    assert market_context_module._normalize_percent_decimal(0.044, "percent") == pytest.approx(0.044)

    # Percentage-point style provider values should convert to decimals.
    assert market_context_module._normalize_percent_decimal(3.18, "percent") == pytest.approx(0.0318)
    assert market_context_module._normalize_percent_decimal(0.7, "percent") == pytest.approx(0.007)
