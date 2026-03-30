from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.db import get_db_session
from app.main import RefreshState, app


def _snapshot(ticker: str = "AAPL", cik: str = "0000320193"):
    company = SimpleNamespace(
        id=1,
        ticker=ticker,
        cik=cik,
        name="Apple Inc.",
        sector="Technology",
        market_sector="Technology",
        market_industry="Consumer Electronics",
    )
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=datetime.now(timezone.utc))


def _bank_snapshot():
    snapshot = _snapshot(ticker="WFC", cik="0000072971")
    snapshot.company.name = "Wells Fargo Bank, National Association"
    snapshot.company.sector = "Financials"
    snapshot.company.market_sector = "Financials"
    snapshot.company.market_industry = "Banks"
    return snapshot


@contextmanager
def _client():
    app.dependency_overrides[get_db_session] = lambda: object()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)


@pytest.fixture(autouse=True)
def _stub_regulated_bank_query(monkeypatch):
    monkeypatch.setattr(main_module, "get_company_regulated_bank_financials", lambda *_args, **_kwargs: [])


def _financial_statement(source: str = "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json"):
    return SimpleNamespace(
        filing_type="10-K",
        statement_type="canonical_xbrl",
        period_start=date(2025, 1, 1),
        period_end=date(2025, 12, 31),
        source=source,
        last_updated=datetime(2026, 3, 21, tzinfo=timezone.utc),
        last_checked=datetime(2026, 3, 22, tzinfo=timezone.utc),
        data={
            "revenue": 391_000_000_000,
            "net_income": 97_000_000_000,
            "operating_income": 123_000_000_000,
            "free_cash_flow": 110_000_000_000,
            "segment_breakdown": [],
        },
    )


def _regulated_financial_statement(source: str = "https://api.fdic.gov/banks/financials"):
    return SimpleNamespace(
        filing_type="CALL",
        statement_type="canonical_bank_regulatory",
        period_start=date(2025, 10, 1),
        period_end=date(2025, 12, 31),
        source=source,
        last_updated=datetime(2026, 3, 21, tzinfo=timezone.utc),
        last_checked=datetime(2026, 3, 22, tzinfo=timezone.utc),
        data={
            "net_income": 1_000_000_000,
            "net_interest_income": 1_200_000_000,
            "provision_for_credit_losses": 200_000_000,
            "deposits_total": 80_000_000_000,
            "core_deposits": 60_000_000_000,
            "uninsured_deposits": 12_000_000_000,
            "net_interest_margin": 0.038,
            "common_equity_tier1_ratio": 0.121,
            "tier1_risk_weighted_ratio": 0.133,
            "total_risk_based_capital_ratio": 0.149,
            "tangible_common_equity": 9_000_000_000,
            "regulated_bank_source_id": "fdic_bankfind_financials",
            "regulated_bank_reporting_basis": "fdic_call_report",
            "regulated_bank_confidence_score": 0.97,
            "regulated_bank_confidence_flags": ["matched_by_cert"],
        },
    )


def _price_point():
    return SimpleNamespace(
        trade_date=date(2026, 3, 21),
        close=190.5,
        volume=10_000_000,
        source="https://finance.yahoo.com/quote/AAPL",
    )


def _assert_provenance_envelope(payload: dict, expected_sources: set[str], *, require_as_of: bool = True) -> None:
    assert payload["provenance"]
    assert {entry["source_id"] for entry in payload["provenance"]} == expected_sources
    if require_as_of:
        assert payload["as_of"] is not None
    assert payload["last_refreshed_at"] is not None
    assert payload["source_mix"]["source_ids"]
    assert isinstance(payload["confidence_flags"], list)


def test_financials_route_includes_registry_backed_provenance(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [_financial_statement()])
    monkeypatch.setattr(main_module, "get_company_price_history", lambda *_args, **_kwargs: [_price_point()])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 3, 21, tzinfo=timezone.utc), "fresh"))
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )

    with _client() as client:
        response = client.get("/api/companies/AAPL/financials")

    assert response.status_code == 200
    payload = response.json()
    _assert_provenance_envelope(payload, {"sec_companyfacts", "yahoo_finance"})
    assert payload["as_of"] == "2025-12-31"
    assert payload["source_mix"]["fallback_source_ids"] == ["yahoo_finance"]
    assert "commercial_fallback_present" in payload["confidence_flags"]


def test_model_evaluation_route_includes_registry_backed_provenance(monkeypatch):
    serialized = {
        "id": 7,
        "suite_key": "cache_suite",
        "candidate_label": "candidate",
        "baseline_label": "baseline",
        "status": "completed",
        "completed_at": datetime(2026, 3, 29, tzinfo=timezone.utc),
        "configuration": {"horizon_days": 420, "earnings_horizon_days": 30},
        "summary": {
            "company_count": 2,
            "snapshot_count": 8,
            "model_count": 5,
            "provenance_mode": "historical_cache",
            "latest_as_of": "2025-02-15",
            "latest_future_as_of": "2026-01-31",
        },
        "models": [
            {
                "model_name": "dcf",
                "sample_count": 8,
                "calibration": 0.75,
                "stability": 0.08,
                "mean_absolute_error": 0.11,
                "root_mean_square_error": 0.13,
                "mean_signed_error": 0.02,
                "status": "ok",
                "delta": {
                    "calibration": 0,
                    "stability": 0,
                    "mean_absolute_error": 0,
                    "root_mean_square_error": 0,
                    "mean_signed_error": 0,
                    "sample_count": 0,
                },
            }
        ],
        "deltas_present": False,
    }
    monkeypatch.setattr(main_module, "get_latest_model_evaluation_run", lambda *_args, **_kwargs: SimpleNamespace(created_at=datetime(2026, 3, 29, tzinfo=timezone.utc), completed_at=datetime(2026, 3, 29, tzinfo=timezone.utc)))
    monkeypatch.setattr(main_module, "serialize_model_evaluation_run", lambda *_args, **_kwargs: serialized)

    with _client() as client:
        response = client.get("/api/model-evaluations/latest")

    assert response.status_code == 200
    payload = response.json()
    _assert_provenance_envelope(payload, {"ft_model_evaluation_harness", "sec_companyfacts", "yahoo_finance"}, require_as_of=True)
    assert payload["run"]["suite_key"] == "cache_suite"
    assert payload["run"]["models"][0]["model_name"] == "dcf"


def test_financials_route_exposes_reconciliation_metadata(monkeypatch):
    statement = _financial_statement()
    statement.reconciliation = {
        "status": "disagreement",
        "as_of": date(2025, 12, 31),
        "last_refreshed_at": datetime(2026, 3, 22, tzinfo=timezone.utc),
        "provenance_sources": ["sec_companyfacts", "sec_edgar"],
        "confidence_score": 0.88,
        "confidence_penalty": 0.12,
        "confidence_flags": ["revenue_reconciliation_disagreement"],
        "missing_field_flags": [],
        "matched_accession_number": "0000320193-26-000010",
        "matched_filing_type": "10-K",
        "matched_period_start": date(2025, 1, 1),
        "matched_period_end": date(2025, 12, 31),
        "matched_source": "https://www.sec.gov/Archives/edgar/data/320193/000032019326000010/form10k.htm",
        "disagreement_count": 1,
        "comparisons": [
            {
                "metric_key": "revenue",
                "status": "disagreement",
                "companyfacts_value": 391_000_000_000,
                "filing_parser_value": 389_000_000_000,
                "delta": -2_000_000_000,
                "relative_delta": 0.0051,
                "confidence_penalty": 0.05,
                "companyfacts_fact": {
                    "accession_number": "0000320193-26-000010",
                    "form": "10-K",
                    "taxonomy": "us-gaap",
                    "tag": "RevenueFromContractWithCustomerExcludingAssessedTax",
                    "unit": "USD",
                    "source": "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                    "filed_at": date(2026, 2, 1),
                    "period_start": date(2025, 1, 1),
                    "period_end": date(2025, 12, 31),
                    "value": 391_000_000_000,
                },
                "filing_parser_fact": {
                    "accession_number": "0000320193-26-000010",
                    "form": "10-K",
                    "taxonomy": None,
                    "tag": None,
                    "unit": None,
                    "source": "https://www.sec.gov/Archives/edgar/data/320193/000032019326000010/form10k.htm",
                    "filed_at": None,
                    "period_start": date(2025, 1, 1),
                    "period_end": date(2025, 12, 31),
                    "value": 389_000_000_000,
                },
            }
        ],
    }

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [statement])
    monkeypatch.setattr(main_module, "get_company_price_history", lambda *_args, **_kwargs: [_price_point()])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 3, 21, tzinfo=timezone.utc), "fresh"))
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )

    with _client() as client:
        response = client.get("/api/companies/AAPL/financials")

    assert response.status_code == 200
    payload = response.json()
    assert payload["financials"][0]["reconciliation"]["matched_accession_number"] == "0000320193-26-000010"
    assert payload["financials"][0]["reconciliation"]["comparisons"][0]["companyfacts_fact"]["tag"] == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert payload["financials"][0]["reconciliation"]["comparisons"][0]["companyfacts_fact"]["period_end"] == "2025-12-31"
    assert payload["diagnostics"]["reconciliation_disagreement_count"] == 1
    assert payload["diagnostics"]["reconciliation_penalty"] == 0.12
    assert {entry["source_id"] for entry in payload["provenance"]} == {"sec_companyfacts", "sec_edgar", "yahoo_finance"}


def test_financials_route_exposes_segment_analysis_metadata(monkeypatch):
    latest = _financial_statement()
    latest.data["segment_breakdown"] = [
        {"segment_id": "cloud", "segment_name": "Cloud", "axis_key": "StatementBusinessSegmentsAxis", "axis_label": "Business Segments", "kind": "business", "revenue": 520.0, "share_of_revenue": 0.52, "operating_income": 170.0, "assets": None},
        {"segment_id": "devices", "segment_name": "Devices", "axis_key": "StatementBusinessSegmentsAxis", "axis_label": "Business Segments", "kind": "business", "revenue": 300.0, "share_of_revenue": 0.30, "operating_income": 45.0, "assets": None},
        {"segment_id": "services", "segment_name": "Services", "axis_key": "StatementBusinessSegmentsAxis", "axis_label": "Business Segments", "kind": "business", "revenue": 180.0, "share_of_revenue": 0.18, "operating_income": 45.0, "assets": None},
        {"segment_id": "us", "segment_name": "United States", "axis_key": "StatementGeographicalAxis", "axis_label": "Geographic Segments", "kind": "geographic", "revenue": 610.0, "share_of_revenue": 0.61, "operating_income": None, "assets": None},
        {"segment_id": "emea", "segment_name": "EMEA", "axis_key": "StatementGeographicalAxis", "axis_label": "Geographic Segments", "kind": "geographic", "revenue": 210.0, "share_of_revenue": 0.21, "operating_income": None, "assets": None},
        {"segment_id": "apac", "segment_name": "APAC", "axis_key": "StatementGeographicalAxis", "axis_label": "Geographic Segments", "kind": "geographic", "revenue": 180.0, "share_of_revenue": 0.18, "operating_income": None, "assets": None},
    ]
    latest.data["revenue"] = 1000.0
    latest.data["operating_income"] = 260.0

    previous = _financial_statement()
    previous.period_start = date(2024, 1, 1)
    previous.period_end = date(2024, 12, 31)
    previous.last_updated = datetime(2025, 3, 21, tzinfo=timezone.utc)
    previous.last_checked = datetime(2025, 3, 22, tzinfo=timezone.utc)
    previous.data = {
        "revenue": 900.0,
        "operating_income": 220.0,
        "segment_breakdown": [
            {"segment_id": "cloud", "segment_name": "Cloud", "axis_key": "StatementBusinessSegmentsAxis", "axis_label": "Business Segments", "kind": "business", "revenue": 410.0, "share_of_revenue": 0.4556, "operating_income": 125.0, "assets": None},
            {"segment_id": "devices", "segment_name": "Devices", "axis_key": "StatementBusinessSegmentsAxis", "axis_label": "Business Segments", "kind": "business", "revenue": 340.0, "share_of_revenue": 0.3778, "operating_income": 55.0, "assets": None},
            {"segment_id": "services", "segment_name": "Services", "axis_key": "StatementBusinessSegmentsAxis", "axis_label": "Business Segments", "kind": "business", "revenue": 150.0, "share_of_revenue": 0.1667, "operating_income": 40.0, "assets": None},
            {"segment_id": "us", "segment_name": "United States", "axis_key": "StatementGeographicalAxis", "axis_label": "Geographic Segments", "kind": "geographic", "revenue": 520.0, "share_of_revenue": 0.5778, "operating_income": None, "assets": None},
            {"segment_id": "emea", "segment_name": "EMEA", "axis_key": "StatementGeographicalAxis", "axis_label": "Geographic Segments", "kind": "geographic", "revenue": 190.0, "share_of_revenue": 0.2111, "operating_income": None, "assets": None},
            {"segment_id": "apac", "segment_name": "APAC", "axis_key": "StatementGeographicalAxis", "axis_label": "Geographic Segments", "kind": "geographic", "revenue": 190.0, "share_of_revenue": 0.2111, "operating_income": None, "assets": None},
        ],
    }

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [latest, previous])
    monkeypatch.setattr(main_module, "get_company_price_history", lambda *_args, **_kwargs: [_price_point()])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 3, 21, tzinfo=timezone.utc), "fresh"))
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )

    with _client() as client:
        response = client.get("/api/companies/AAPL/financials")

    assert response.status_code == 200
    payload = response.json()
    assert payload["segment_analysis"]["business"]["as_of"] == "2025-12-31"
    assert payload["segment_analysis"]["business"]["top_mix_movers"][0]["segment_name"] == "Devices"
    assert payload["segment_analysis"]["business"]["top_margin_contributors"][0]["segment_name"] == "Cloud"
    assert payload["segment_analysis"]["geographic"]["concentration"]["top_segment_name"] == "United States"
    assert "sec_companyfacts" in payload["segment_analysis"]["business"]["provenance_sources"]
    assert any(item["code"] == "geographic_revenue_only" for item in payload["segment_analysis"]["geographic"]["unusual_disclosures"])


def test_financials_route_exposes_regulated_bank_payload_and_provenance(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _bank_snapshot())
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [_financial_statement()])
    monkeypatch.setattr(main_module, "get_company_regulated_bank_financials", lambda *_args, **_kwargs: [_regulated_financial_statement()])
    monkeypatch.setattr(main_module, "get_company_price_history", lambda *_args, **_kwargs: [_price_point()])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 3, 21, tzinfo=timezone.utc), "fresh"))
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="WFC", job_id=None),
    )

    with _client() as client:
        response = client.get("/api/companies/WFC/financials")

    assert response.status_code == 200
    payload = response.json()
    _assert_provenance_envelope(payload, {"fdic_bankfind_financials", "yahoo_finance"})
    assert payload["company"]["regulated_entity"]["issuer_type"] == "bank"
    assert payload["financials"][0]["statement_type"] == "canonical_bank_regulatory"
    assert payload["financials"][0]["regulated_bank"]["source_id"] == "fdic_bankfind_financials"
    assert payload["financials"][0]["regulated_bank"]["confidence_flags"] == ["matched_by_cert"]


def test_capital_structure_route_includes_registry_backed_provenance(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(
        main_module,
        "get_company_capital_structure_snapshots",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0000320193-26-000010",
                filing_type="10-K",
                statement_type="canonical_xbrl",
                period_start=date(2025, 1, 1),
                period_end=date(2025, 12, 31),
                source="https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
                filing_acceptance_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
                last_updated=datetime(2026, 3, 21, tzinfo=timezone.utc),
                last_checked=datetime(2026, 3, 22, tzinfo=timezone.utc),
                data={
                    "summary": {
                        "total_debt": 110_000_000_000,
                        "interest_expense": 4_500_000_000,
                        "gross_shareholder_payout": 96_000_000_000,
                    },
                    "debt_maturity_ladder": {
                        "buckets": [{"bucket_key": "debt_maturity_due_next_twelve_months", "label": "Next 12 months", "amount": 8_000_000_000}],
                        "meta": {
                            "as_of": "2025-12-31",
                            "last_refreshed_at": "2026-03-22T00:00:00Z",
                            "provenance_sources": ["sec_companyfacts", "ft_capital_structure_intelligence"],
                            "confidence_score": 0.5,
                            "confidence_flags": ["debt_maturity_ladder_partial"],
                        },
                    },
                    "lease_obligations": {"buckets": [], "meta": {"as_of": "2025-12-31", "provenance_sources": [], "confidence_score": 0.0, "confidence_flags": ["lease_obligations_missing"]}},
                    "debt_rollforward": {
                        "opening_total_debt": 100_000_000_000,
                        "ending_total_debt": 110_000_000_000,
                        "debt_issued": 15_000_000_000,
                        "debt_repaid": 5_000_000_000,
                        "net_debt_change": 10_000_000_000,
                        "unexplained_change": 0,
                        "meta": {"as_of": "2025-12-31", "provenance_sources": ["sec_companyfacts"], "confidence_score": 1.0, "confidence_flags": []},
                    },
                    "interest_burden": {
                        "interest_expense": 4_500_000_000,
                        "average_total_debt": 105_000_000_000,
                        "interest_to_average_debt": 0.0429,
                        "interest_coverage_proxy": 20.0,
                        "meta": {"as_of": "2025-12-31", "provenance_sources": ["sec_companyfacts"], "confidence_score": 1.0, "confidence_flags": []},
                    },
                    "capital_returns": {
                        "dividends": 15_000_000_000,
                        "share_repurchases": 81_000_000_000,
                        "stock_based_compensation": 12_000_000_000,
                        "gross_shareholder_payout": 96_000_000_000,
                        "net_shareholder_payout": 84_000_000_000,
                        "payout_mix": {"dividends_share": 0.156, "repurchases_share": 0.844, "sbc_offset_share": 0.111},
                        "meta": {"as_of": "2025-12-31", "provenance_sources": ["sec_companyfacts"], "confidence_score": 1.0, "confidence_flags": []},
                    },
                    "net_dilution_bridge": {
                        "opening_shares": 15_600_000_000,
                        "shares_issued": 80_000_000,
                        "shares_repurchased": 500_000_000,
                        "ending_shares": 15_180_000_000,
                        "net_share_change": -420_000_000,
                        "net_dilution_ratio": -0.0269,
                        "meta": {"as_of": "2025-12-31", "provenance_sources": ["sec_companyfacts"], "confidence_score": 1.0, "confidence_flags": []},
                    },
                },
                provenance={"formula_version": "capital_structure_v1", "official_source_id": "sec_companyfacts"},
                quality_flags=["debt_maturity_ladder_partial", "lease_obligations_missing"],
                confidence_score=0.75,
            )
        ],
    )
    monkeypatch.setattr(
        main_module,
        "get_company_capital_structure_last_checked",
        lambda *_args, **_kwargs: datetime(2026, 3, 22, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        main_module,
        "_refresh_for_capital_structure",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/capital-structure")

    assert response.status_code == 200
    payload = response.json()
    _assert_provenance_envelope(payload, {"ft_capital_structure_intelligence", "sec_companyfacts"})
    assert payload["latest"]["summary"]["total_debt"] == 110000000000
    assert payload["source_mix"]["official_only"] is True
    assert "lease_obligations_missing" in payload["confidence_flags"]


def test_models_route_includes_registry_backed_provenance(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [_financial_statement()])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 3, 21, tzinfo=timezone.utc), "fresh"))
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "get_company_models",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                model_name="dcf",
                model_version="v2",
                created_at=datetime(2026, 3, 22, tzinfo=timezone.utc),
                input_periods={"period_end": "2025-12-31"},
                result={
                    "model_status": "ok",
                    "base_period_end": "2025-12-31",
                    "price_snapshot": {
                        "price_date": "2026-03-21",
                        "price_source": "yahoo_finance",
                    },
                    "assumption_provenance": {
                        "price_snapshot": {
                            "price_date": "2026-03-21",
                            "price_source": "yahoo_finance",
                        },
                        "risk_free_rate": {
                            "source_name": "U.S. Treasury Daily Par Yield Curve",
                            "observation_date": "2026-03-20",
                        }
                    },
                },
            )
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/models")

    assert response.status_code == 200
    payload = response.json()
    _assert_provenance_envelope(
        payload,
        {"ft_model_engine", "sec_companyfacts", "us_treasury_daily_par_yield_curve", "yahoo_finance"},
    )
    assert payload["as_of"] == "2025-12-31"
    assert payload["source_mix"]["fallback_source_ids"] == ["yahoo_finance"]
    assert "commercial_fallback_present" in payload["confidence_flags"]
    assert payload["models"][0]["result"]["price_snapshot"]["price_source"] == "yahoo_finance"
    assert payload["models"][0]["result"]["assumption_provenance"]["price_snapshot"]["price_source"] == "yahoo_finance"


def test_models_route_accepts_sec_filing_statement_provenance(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(
        main_module,
        "get_company_financials",
        lambda *_args, **_kwargs: [
            _financial_statement(source="https://www.sec.gov/Archives/edgar/data/320193/000032019325000001/a10-k2025.htm")
        ],
    )
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 3, 21, tzinfo=timezone.utc), "fresh"))
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "get_company_models",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                model_name="dcf",
                model_version="v2",
                created_at=datetime(2026, 3, 22, tzinfo=timezone.utc),
                input_periods={"period_end": "2025-12-31"},
                result={
                    "model_status": "ok",
                    "base_period_end": "2025-12-31",
                },
            )
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/models")

    assert response.status_code == 200
    payload = response.json()
    _assert_provenance_envelope(payload, {"ft_model_engine", "sec_edgar"})
    assert payload["source_mix"]["fallback_source_ids"] == []
    assert payload["source_mix"]["official_only"] is True


def test_peers_route_includes_registry_backed_provenance(monkeypatch):
    snapshot = _snapshot()
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [_financial_statement()])
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (datetime(2026, 3, 21, tzinfo=timezone.utc), "fresh"))
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "build_peer_comparison",
        lambda *_args, **_kwargs: {
            "company": SimpleNamespace(company=snapshot.company, cache_state="fresh", last_checked=datetime(2026, 3, 22, tzinfo=timezone.utc)),
            "peer_basis": "Technology peers",
            "available_companies": [],
            "selected_tickers": ["MSFT"],
            "peers": [
                {
                    "ticker": "AAPL",
                    "name": "Apple Inc.",
                    "sector": "Technology",
                    "market_sector": "Technology",
                    "market_industry": "Consumer Electronics",
                    "is_focus": True,
                    "cache_state": "fresh",
                    "last_checked": "2026-03-22T00:00:00Z",
                    "period_end": "2025-12-31",
                    "price_date": "2026-03-21",
                    "latest_price": 190.5,
                    "pe": 28.0,
                    "ev_to_ebit": 20.0,
                    "price_to_free_cash_flow": 30.0,
                    "roe": 0.24,
                    "revenue_growth": 0.08,
                    "piotroski_score": 8,
                    "altman_z_score": 4.2,
                    "dcf_model_status": "partial",
                    "reverse_dcf_model_status": "ok",
                    "revenue_history": [],
                }
            ],
            "notes": {"ev_to_ebit": "proxy"},
            "source_hints": {
                "financial_statement_sources": ["sec_companyfacts"],
                "price_sources": ["yahoo_finance"],
                "risk_free_sources": ["U.S. Treasury Daily Par Yield Curve"],
            },
        },
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/peers")

    assert response.status_code == 200
    payload = response.json()
    _assert_provenance_envelope(
        payload,
        {"ft_peer_comparison", "sec_companyfacts", "us_treasury_daily_par_yield_curve", "yahoo_finance"},
    )
    assert payload["as_of"] == "2025-12-31"
    assert payload["source_mix"]["fallback_source_ids"] == ["yahoo_finance"]
    assert "partial_peer_models" in payload["confidence_flags"]


def test_activity_overview_route_includes_registry_backed_provenance(monkeypatch):
    snapshot = _snapshot()
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "_load_company_activity_data",
        lambda *_args, **_kwargs: {
            "filings": [],
            "filing_events": [],
            "governance_filings": [],
            "beneficial_filings": [],
            "insider_trades": [],
            "form144_filings": [],
            "institutional_holdings": [],
            "capital_filings": [],
        },
    )
    monkeypatch.setattr(
        main_module,
        "get_cached_market_context_status",
        lambda: {
            "state": "partial",
            "label": "Macro partial",
            "observation_date": "2026-03-21",
            "source": "U.S. Treasury Daily Par Yield Curve",
            "treasury_status": "ok",
        },
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/activity-overview")

    assert response.status_code == 200
    payload = response.json()
    _assert_provenance_envelope(
        payload,
        {"ft_activity_overview", "sec_edgar", "us_treasury_daily_par_yield_curve"},
        require_as_of=False,
    )
    assert payload["as_of"] is None
    assert payload["source_mix"]["official_only"] is True
    assert "activity_feed_empty" in payload["confidence_flags"]
    assert "market_context_partial" in payload["confidence_flags"]


def test_models_route_hides_yahoo_provenance_and_price_snapshot_in_strict_mode(monkeypatch):
    snapshot = _snapshot(ticker="STRICT")
    snapshot.company.sector = "prepackaged software"
    snapshot.cache_state = "stale"
    monkeypatch.setattr(main_module, "settings", SimpleNamespace(strict_official_mode=True, valuation_workbench_enabled=True))
    monkeypatch.setattr(main_module, "_store_hot_cached_payload", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="STRICT", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "get_company_models",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                model_name="dcf",
                model_version="v2",
                created_at=datetime(2026, 3, 22, tzinfo=timezone.utc),
                input_periods={"period_end": "2025-12-31"},
                result={
                    "model_status": "ok",
                    "base_period_end": "2025-12-31",
                    "price_snapshot": {
                        "latest_price": 190.5,
                        "price_date": "2026-03-21",
                        "price_source": "yahoo_finance",
                        "price_available": True,
                    },
                    "assumption_provenance": {
                        "price_snapshot": {
                            "latest_price": 190.5,
                            "price_date": "2026-03-21",
                            "price_source": "yahoo_finance",
                            "price_available": True,
                        },
                        "risk_free_rate": {
                            "source_name": "U.S. Treasury Daily Par Yield Curve",
                            "observation_date": "2026-03-20",
                        },
                    },
                },
            )
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/STRICT/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["company"]["strict_official_mode"] is True
    assert payload["company"]["market_sector"] == "Technology"
    assert {entry["source_id"] for entry in payload["provenance"]} == {
        "ft_model_engine",
        "us_treasury_daily_par_yield_curve",
    }
    assert payload["source_mix"]["fallback_source_ids"] == []
    assert "strict_official_mode" in payload["confidence_flags"]
    assert payload["models"][0]["result"]["price_snapshot"]["latest_price"] is None
    assert payload["models"][0]["result"]["price_snapshot"]["price_source"] is None
    assert payload["models"][0]["result"]["price_snapshot"]["price_available"] is False
    assert payload["models"][0]["result"]["assumption_provenance"]["price_snapshot"]["latest_price"] is None
