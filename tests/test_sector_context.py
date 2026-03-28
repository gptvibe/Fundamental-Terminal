from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

import app.main as main_module
from app.db import get_db_session
from app.main import RefreshState, app
from app.services.sector_plugins import bts_airlines, eia_power, fhfa_housing, usda_wasde


class _StubResponse:
    def __init__(self, *, json_data=None, text: str = "", status_code: int = 200):
        self._json_data = json_data
        self.text = text
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


def _snapshot(ticker: str = "AAPL"):
    company = SimpleNamespace(
        id=1,
        ticker=ticker,
        cik="0000320193",
        name="Apple Inc.",
        sector="Real Estate",
        market_sector="Real Estate",
        market_industry="Homebuilder",
    )
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=datetime.now(timezone.utc))


def test_eia_power_plugin_parses_retail_sales(monkeypatch):
    monkeypatch.setattr(
        eia_power,
        "settings",
        SimpleNamespace(
            eia_api_key="demo-key",
            eia_api_base_url="https://api.eia.gov/v2",
            eia_timeout_seconds=30.0,
        ),
    )
    monkeypatch.setattr(
        eia_power,
        "build_http_client",
        lambda *, timeout_seconds: _StubClient(
            [
                _StubResponse(
                    json_data={
                        "response": {
                            "data": [
                                {"period": "2025-12", "sectorid": "ALL", "sales": "337715.7", "price": "13.73"},
                                {"period": "2026-01", "sectorid": "ALL", "sales": "355940.1", "price": "14.17"},
                                {"period": "2025-12", "sectorid": "IND", "sales": "84000.0", "price": "8.81"},
                                {"period": "2026-01", "sectorid": "IND", "sales": "85750.0", "price": "8.94"},
                            ]
                        }
                    }
                )
            ]
        ),
    )

    result = eia_power.fetch_plugin()

    assert result.status == "ok"
    assert result.summary_metrics[0].metric_id == "us_total_sales"
    assert result.summary_metrics[0].value == 355940.1
    assert result.charts[0].chart_id == "retail_sales_trend"


def test_fhfa_housing_plugin_parses_national_index(monkeypatch):
    csv_text = "\n".join(
        [
            "hpi_type,hpi_flavor,frequency,level,place_name,place_id,yr,period,index_nsa,index_sa",
            "traditional,purchase-only,monthly,USA or Census Division,United States,USA,2025,12,435.80,435.80",
            "traditional,purchase-only,monthly,USA or Census Division,United States,USA,2026,1,437.20,437.20",
            "traditional,purchase-only,monthly,USA or Census Division,Pacific Division,DV_PAC,2025,1,400.00,400.00",
            "traditional,purchase-only,monthly,USA or Census Division,Pacific Division,DV_PAC,2026,1,420.00,420.00",
            "traditional,purchase-only,monthly,USA or Census Division,Middle Atlantic Division,DV_MAT,2025,1,410.00,410.00",
            "traditional,purchase-only,monthly,USA or Census Division,Middle Atlantic Division,DV_MAT,2026,1,412.00,412.00",
        ]
    )
    monkeypatch.setattr(
        fhfa_housing,
        "build_http_client",
        lambda *, timeout_seconds: _StubClient([_StubResponse(text=csv_text)]),
    )

    result = fhfa_housing.fetch_plugin()

    assert result.status == "ok"
    assert result.summary_metrics[0].label == "National HPI"
    assert result.summary_metrics[0].value == 437.2
    assert result.detail_view is not None
    assert result.detail_view.rows[1].label == "Pacific Division"


def test_bts_airlines_plugin_combines_t100_and_form41(monkeypatch):
    monkeypatch.setattr(
        bts_airlines,
        "build_http_client",
        lambda *, timeout_seconds: _StubClient(
            [
                _StubResponse(
                    json_data=[
                        {"year": "2024", "passengers": "900000000", "freight_lbs": "44000000000", "load_factor": "81.0"},
                        {"year": "2025", "passengers": "925000000", "freight_lbs": "45500000000", "load_factor": "81.6"},
                    ]
                ),
                _StubResponse(
                    json_data=[
                        {"year": "2025", "quarter": "3", "group_name": "System All Majors", "item_name": "Operating Revenues", "val": "52000000000"},
                        {"year": "2025", "quarter": "4", "group_name": "System All Majors", "item_name": "Operating Revenues", "val": "54000000000"},
                        {"year": "2025", "quarter": "3", "group_name": "System All Majors", "item_name": "Operating Profit (Loss) to Operating Revenue", "val": "0.11"},
                        {"year": "2025", "quarter": "4", "group_name": "System All Majors", "item_name": "Operating Profit (Loss) to Operating Revenue", "val": "0.13"},
                        {"year": "2025", "quarter": "3", "group_name": "Domestic Cargo Majors", "item_name": "Operating Revenues", "val": "2800000000"},
                        {"year": "2025", "quarter": "4", "group_name": "Domestic Cargo Majors", "item_name": "Operating Revenues", "val": "3000000000"},
                        {"year": "2025", "quarter": "3", "group_name": "Domestic Cargo Majors", "item_name": "Operating Profit (Loss) to Operating Revenue", "val": "0.08"},
                        {"year": "2025", "quarter": "4", "group_name": "Domestic Cargo Majors", "item_name": "Operating Profit (Loss) to Operating Revenue", "val": "0.09"},
                    ]
                ),
            ]
        ),
    )

    result = bts_airlines.fetch_plugin()

    assert result.status == "ok"
    assert result.summary_metrics[0].label == "T-100 passengers"
    assert result.summary_metrics[3].label == "System operating margin"
    assert result.charts[2].chart_id == "operating_margin_trend"


def test_usda_wasde_plugin_parses_corn_and_soy_sections(monkeypatch):
    page_html = '<a href="/oce/commodity/wasde/wasde0326.xml">XML</a>'
    xml_text = """
    <Root>
      <Report Name="sr5" Report_Month="March 2026" sub_report_title="U.S. Feed Grain and Corn Supply and Use  1/">
        <attribute1 attribute1="Ending Stocks">
          <m1_year_group market_year1="2024/25 Est."><m1_month_group forecast_month1=""><Cell cell_value1="1540" /></m1_month_group></m1_year_group>
          <m1_year_group market_year1="2025/26 Proj."><m1_month_group forecast_month1="Feb"><Cell cell_value1="1540" /></m1_month_group></m1_year_group>
          <m1_year_group market_year1="2025/26 Proj."><m1_month_group forecast_month1="Mar"><Cell cell_value1="1540" /></m1_month_group></m1_year_group>
        </attribute1>
        <attribute1 attribute1="Avg. Farm Price ($/bu)  4/">
          <m1_year_group market_year1="2024/25 Est."><m1_month_group forecast_month1=""><Cell cell_value1="4.35" /></m1_month_group></m1_year_group>
          <m1_year_group market_year1="2025/26 Proj."><m1_month_group forecast_month1="Feb"><Cell cell_value1="4.20" /></m1_month_group></m1_year_group>
          <m1_year_group market_year1="2025/26 Proj."><m1_month_group forecast_month1="Mar"><Cell cell_value1="4.10" /></m1_month_group></m1_year_group>
        </attribute1>
      </Report>
      <Report Name="sr8" Report_Month="March 2026" sub_report_title="U.S. Soybeans and Products Supply and Use (Domestic Measure)  1/">
        <attribute4 attribute4="Ending Stocks">
          <m1_year_group market_year4="2024/25 Est."><m1_month_group forecast_month4=""><Cell cell_value4="380" /></m1_month_group></m1_year_group>
          <m1_year_group market_year4="2025/26 Proj."><m1_month_group forecast_month4="Feb"><Cell cell_value4="320" /></m1_month_group></m1_year_group>
          <m1_year_group market_year4="2025/26 Proj."><m1_month_group forecast_month4="Mar"><Cell cell_value4="315" /></m1_month_group></m1_year_group>
        </attribute4>
        <attribute4 attribute4="Avg. Farm Price ($/bu)  2/">
          <m1_year_group market_year4="2024/25 Est."><m1_month_group forecast_month4=""><Cell cell_value4="10.10" /></m1_month_group></m1_year_group>
          <m1_year_group market_year4="2025/26 Proj."><m1_month_group forecast_month4="Feb"><Cell cell_value4="10.00" /></m1_month_group></m1_year_group>
          <m1_year_group market_year4="2025/26 Proj."><m1_month_group forecast_month4="Mar"><Cell cell_value4="9.90" /></m1_month_group></m1_year_group>
        </attribute4>
      </Report>
    </Root>
    """
    monkeypatch.setattr(
        usda_wasde,
        "build_http_client",
        lambda *, timeout_seconds: _StubClient([
            _StubResponse(text=page_html),
            _StubResponse(text=xml_text),
        ]),
    )

    result = usda_wasde.fetch_plugin()

    assert result.status == "ok"
    assert result.summary_metrics[0].label == "Corn ending stocks"
    assert result.summary_metrics[2].value == 315.0
    assert result.detail_view is not None
    assert result.detail_view.rows[3].label == "Soybean avg. farm price"


def test_company_sector_context_route_returns_payload(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot("KBH"))
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="KBH", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "_serialize_company",
        lambda *_args, **_kwargs: {
            "ticker": "KBH",
            "cik": "0000795266",
            "name": "KB Home",
            "sector": "Real Estate",
            "market_sector": "Real Estate",
            "market_industry": "Homebuilder",
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "last_checked_financials": None,
            "last_checked_prices": None,
            "last_checked_insiders": None,
            "last_checked_institutional": None,
            "last_checked_filings": None,
            "cache_state": "fresh",
            "strict_official_mode": False,
        },
    )
    monkeypatch.setattr(
        main_module,
        "get_company_sector_context",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "matched_plugin_ids": ["fhfa_housing"],
            "plugins": [
                {
                    "plugin_id": "fhfa_housing",
                    "title": "Housing Exposure",
                    "description": "Official FHFA house-price trends for housing- and mortgage-sensitive companies.",
                    "status": "ok",
                    "relevance_reasons": ["industry: homebuilder"],
                    "source_ids": ["fhfa_house_price_index"],
                    "refresh_policy": {"cadence_label": "Monthly", "ttl_seconds": 86400, "notes": []},
                    "summary_metrics": [],
                    "charts": [],
                    "detail_view": {"title": "Latest FHFA housing snapshot", "rows": []},
                    "confidence_flags": [],
                    "as_of": "2026-01",
                    "last_refreshed_at": "2026-03-28T00:00:00Z",
                }
            ],
            "fetched_at": "2026-03-28T00:00:00Z",
            "provenance": [
                {
                    "source_id": "fhfa_house_price_index",
                    "source_tier": "official_statistical",
                    "display_label": "FHFA House Price Index",
                    "url": "https://www.fhfa.gov/data/hpi/datasets",
                    "default_freshness_ttl_seconds": 86400,
                    "disclosure_note": "Official FHFA home-price index used for housing and mortgage exposure context.",
                    "role": "primary",
                    "as_of": "2026-01",
                    "last_refreshed_at": "2026-03-28T00:00:00+00:00",
                }
            ],
            "as_of": "2026-01",
            "last_refreshed_at": "2026-03-28T00:00:00+00:00",
            "source_mix": {
                "source_ids": ["fhfa_house_price_index"],
                "source_tiers": ["official_statistical"],
                "primary_source_ids": ["fhfa_house_price_index"],
                "fallback_source_ids": [],
                "official_only": True,
            },
            "confidence_flags": [],
        },
    )

    app.dependency_overrides[get_db_session] = lambda: None
    try:
        client = TestClient(app)
        response = client.get("/api/companies/KBH/sector-context")
    finally:
        app.dependency_overrides.pop(get_db_session, None)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["matched_plugin_ids"] == ["fhfa_housing"]
    assert payload["plugins"][0]["title"] == "Housing Exposure"
    assert payload["source_mix"]["official_only"] is True
