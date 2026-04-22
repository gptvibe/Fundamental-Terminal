from __future__ import annotations

import asyncio
import json
import time

from app.services.proxy_parser import ExecCompRow

from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

import app.main as main_module
from app.api.schemas.common import CompanyPayload, DataQualityDiagnosticsPayload
from app.api.schemas.financials import CompanyFinancialsResponse
from app.main import RefreshState, app
from app.services.beneficial_ownership import BeneficialOwnershipNormalizedParty, BeneficialOwnershipNormalizedReport
from app.services.hot_cache import shared_hot_response_cache
from app.services.sec_edgar import FilingMetadata


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


def _company_payload(snapshot) -> CompanyPayload:
    return CompanyPayload(
        ticker=snapshot.company.ticker,
        cik=snapshot.company.cik,
        name=snapshot.company.name,
        sector=snapshot.company.sector,
        market_sector=snapshot.company.market_sector,
        market_industry=snapshot.company.market_industry,
        cache_state=snapshot.cache_state,
        last_checked=snapshot.last_checked,
    )


def _financials_payload(snapshot) -> CompanyFinancialsResponse:
    return CompanyFinancialsResponse(
        company=_company_payload(snapshot),
        financials=[],
        price_history=[],
        refresh=RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None),
        diagnostics=DataQualityDiagnosticsPayload(),
    )


def _brief_payload(snapshot):
    return main_module._empty_company_brief_response(
        refresh=RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None),
        as_of=None,
    ).model_copy(update={"company": _company_payload(snapshot)})


class _FakeEdgarClient:
    def __init__(self, filings: dict[str, FilingMetadata]):
        self._filings = filings

    def get_submissions(self, cik: str):
        return {"cik": cik}

    def build_filing_index(self, submissions: dict):
        return self._filings

    def get_filing_document_text(self, cik: str, accession_number: str, document_name: str):
        return (
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_number.replace('-', '')}/{document_name}",
            "<html><body>Proxy placeholder document.</body></html>",
        )

    def close(self):
        return None


def _install_common_overrides(monkeypatch, filings: dict[str, FilingMetadata]):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda *_args, **_kwargs: _snapshot())
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(main_module, "_trigger_refresh", lambda *_args, **_kwargs: RefreshState(triggered=True, reason="missing", ticker="AAPL", job_id="job-1"))
    monkeypatch.setattr(
        main_module,
        "get_company_proxy_cache_status",
        lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"),
    )
    monkeypatch.setattr(main_module, "_serialize_company", lambda *_args, **_kwargs: {
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
    })
    monkeypatch.setattr(main_module, "EdgarClient", lambda: _FakeEdgarClient(filings))
    monkeypatch.setattr(main_module, "get_company_beneficial_ownership_reports", lambda *_args, **_kwargs: [])

    cached_filing_events = []
    cached_capital_events = []
    for item in filings.values():
        form = (item.form or "").upper()
        if form == "8-K":
            cached_filing_events.append(
                SimpleNamespace(
                    accession_number=item.accession_number,
                    form=form,
                    filing_date=item.filing_date,
                    report_date=item.report_date,
                    items=item.items,
                    item_code=(item.items or "").split(",")[0].strip() or None,
                    category=main_module._classify_filing_event(item.items, item.primary_doc_description),
                    primary_document=item.primary_document,
                    primary_doc_description=item.primary_doc_description,
                    source_url=main_module._build_filing_document_url("0000320193", item.accession_number, item.primary_document),
                    summary=item.primary_doc_description or "Current report with event-driven disclosure.",
                    key_amounts=[],
                    exhibit_references=["99.1"] if "99.1" in (item.primary_doc_description or "") else [],
                )
            )

        if form in main_module.REGISTRATION_FORMS or form.startswith("NT "):
            cached_capital_events.append(
                SimpleNamespace(
                    accession_number=item.accession_number,
                    form=form,
                    filing_date=item.filing_date,
                    report_date=item.report_date,
                    primary_document=item.primary_document,
                    primary_doc_description=item.primary_doc_description,
                    source_url=main_module._build_filing_document_url("0000320193", item.accession_number, item.primary_document),
                    summary=item.primary_doc_description or "Registration or prospectus filing.",
                    event_type="Late Filing Notice" if form.startswith("NT ") else "Registration",
                    security_type=None,
                    offering_amount=None,
                    shelf_size=None,
                    is_late_filer=form.startswith("NT "),
                )
            )

    monkeypatch.setattr(main_module, "get_company_filing_events", lambda *_args, **_kwargs: cached_filing_events)
    monkeypatch.setattr(main_module, "get_company_capital_markets_events", lambda *_args, **_kwargs: cached_capital_events)


def test_events_route_classifies_item_codes(monkeypatch):
    filings = {
        "0001": FilingMetadata(
            accession_number="0001",
            form="8-K",
            filing_date=date(2026, 3, 1),
            report_date=date(2026, 2, 28),
            primary_document="a8k.htm",
            primary_doc_description="Item 9.01 Financial Statements and Exhibits. Exhibit 99.1 furnished.",
            items="2.02,9.01",
        )
    }
    _install_common_overrides(monkeypatch, filings)

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/events")

    assert response.status_code == 200
    payload = response.json()
    assert payload["events"]
    assert payload["events"][0]["category"] == "Earnings"
    assert payload["events"][0]["form"] == "8-K"
    assert payload["events"][0]["exhibit_references"] == ["99.1"]


def test_filing_events_alias_route_returns_events(monkeypatch):
    filings = {
        "0001": FilingMetadata(
            accession_number="0001",
            form="8-K",
            filing_date=date(2026, 3, 1),
            report_date=date(2026, 2, 28),
            primary_document="a8k.htm",
            primary_doc_description="",
            items="2.02",
        )
    }
    _install_common_overrides(monkeypatch, filings)

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/filing-events")

    assert response.status_code == 200
    payload = response.json()
    assert payload["events"]
    assert payload["events"][0]["form"] == "8-K"


def test_filing_events_summary_endpoint_returns_aggregates(monkeypatch):
    filings = {
        "0001": FilingMetadata(
            accession_number="0001",
            form="8-K",
            filing_date=date(2026, 3, 1),
            report_date=date(2026, 2, 28),
            primary_document="a8k.htm",
            primary_doc_description="Earnings release for $100,000,000 revenue.",
            items="2.02",
        )
    }
    _install_common_overrides(monkeypatch, filings)

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/filing-events/summary")

    assert response.status_code == 200
    payload = response.json()
    summary = payload["summary"]
    assert summary["total_events"] >= 1
    assert summary["unique_accessions"] >= 1
    assert "Earnings" in summary["categories"] or "Other" in summary["categories"]


def test_capital_markets_alias_route_returns_filings(monkeypatch):
    filings = {
        "0008": FilingMetadata(
            accession_number="0008",
            form="S-3",
            filing_date=date(2026, 3, 22),
            report_date=date(2026, 3, 22),
            primary_document="s3.htm",
            primary_doc_description="Shelf registration statement for up to $300,000,000 of common stock.",
            items=None,
        )
    }
    _install_common_overrides(monkeypatch, filings)

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/capital-markets")

    assert response.status_code == 200
    payload = response.json()
    assert payload["filings"]
    assert payload["filings"][0]["form"] == "S-3"


def test_capital_markets_summary_endpoint_returns_aggregates(monkeypatch):
    filings = {
        "0009": FilingMetadata(
            accession_number="0009",
            form="NT 10-Q",
            filing_date=date(2026, 3, 23),
            report_date=date(2026, 3, 23),
            primary_document="nt10q.htm",
            primary_doc_description="Notification of inability to timely file quarterly report.",
            items=None,
        )
    }
    _install_common_overrides(monkeypatch, filings)

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/capital-markets/summary")

    assert response.status_code == 200
    payload = response.json()
    summary = payload["summary"]
    assert summary["total_filings"] >= 1
    assert summary["late_filer_notices"] >= 1


def test_equity_claim_risk_endpoint_returns_pack(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    monkeypatch.setattr(
        main_module,
        "build_company_equity_claim_risk_response",
        lambda *_args, **_kwargs: main_module.CompanyEquityClaimRiskResponse(
            company=None,
            summary=main_module.EquityClaimRiskSummaryPayload(
                headline="Equity claim risk is elevated because dilution and financing pressure remain active.",
                overall_risk_level="high",
                dilution_risk_level="high",
                financing_risk_level="medium",
                reporting_risk_level="low",
                net_dilution_ratio=0.08,
                shelf_capacity_remaining=250_000_000,
                debt_due_next_twenty_four_months=180_000_000,
                key_points=["ATM activity was detected in recent SEC filings."],
            ),
            refresh=RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
            provenance=[
                main_module.ProvenanceEntryPayload(
                    source_id="ft_equity_claim_risk_pack",
                    source_tier="derived_from_official",
                    display_label="Fundamental Terminal Equity Claim Risk Pack",
                    url="https://github.com/gptvibe/Fundamental-Terminal",
                    default_freshness_ttl_seconds=21600,
                    disclosure_note="Derived dilution and financing risk pack assembled from SEC evidence.",
                    role="derived",
                    as_of="2026-03-23T23:59:59+00:00",
                )
            ],
            as_of="2026-03-23T23:59:59+00:00",
            source_mix=main_module.SourceMixPayload(
                source_ids=["ft_equity_claim_risk_pack", "sec_companyfacts", "sec_edgar"],
                source_tiers=["derived_from_official", "official_regulator"],
                primary_source_ids=["sec_companyfacts"],
                fallback_source_ids=[],
                official_only=True,
            ),
            confidence_flags=["atm_activity_detected"],
        ),
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/equity-claim-risk")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["overall_risk_level"] == "high"
    assert payload["summary"]["headline"].startswith("Equity claim risk is elevated")
    assert payload["source_mix"]["official_only"] is True
    assert payload["confidence_flags"] == ["atm_activity_detected"]


def test_peers_route_returns_default_selected_tickers(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    main_module._hot_response_cache.clear()
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (None, "fresh"))
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )

    observed: dict[str, list[str] | None] = {"selected": None}

    def _fake_build_peer_comparison(
        _session,
        ticker: str,
        selected_tickers: list[str] | None = None,
        as_of=None,
    ):
        observed["selected"] = selected_tickers
        company_snapshot = _snapshot(ticker=ticker).company
        company = SimpleNamespace(**company_snapshot.__dict__, last_checked=datetime.now(timezone.utc))
        return {
            "company": company,
            "peer_basis": "Cached peer universe",
            "available_companies": [
                {
                    "ticker": "AAPL",
                    "name": "Apple Inc.",
                    "sector": "Technology",
                    "market_sector": "Technology",
                    "market_industry": "Consumer Electronics",
                    "last_checked": datetime.now(timezone.utc),
                    "cache_state": "fresh",
                    "is_focus": True,
                },
                {
                    "ticker": "MSFT",
                    "name": "Microsoft",
                    "sector": "Technology",
                    "market_sector": "Technology",
                    "market_industry": "Software",
                    "last_checked": datetime.now(timezone.utc),
                    "cache_state": "fresh",
                    "is_focus": False,
                },
            ],
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
                    "last_checked": datetime.now(timezone.utc),
                    "period_end": date(2025, 12, 31),
                    "price_date": date(2026, 3, 21),
                    "latest_price": 190.0,
                    "pe": 28.0,
                    "ev_to_ebit": 20.0,
                    "price_to_free_cash_flow": 30.0,
                    "roe": 0.24,
                    "revenue_growth": 0.08,
                    "piotroski_score": 8,
                    "altman_z_score": 4.0,
                    "revenue_history": [],
                }
            ],
            "notes": {"ev_to_ebit": "proxy", "price_to_free_cash_flow": "proxy", "piotroski": "score"},
        }

    monkeypatch.setattr(main_module, "build_peer_comparison", _fake_build_peer_comparison)

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/peers")

    assert response.status_code == 200
    payload = response.json()
    assert observed["selected"] == []
    assert payload["selected_tickers"] == ["MSFT"]
    assert payload["peers"]


def test_financials_route_serves_raw_cached_json_on_fresh_hit(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    monkeypatch.setattr(shared_hot_response_cache, "_redis", None)
    shared_hot_response_cache.clear_sync()

    payload = CompanyFinancialsResponse(
        company=CompanyPayload(
            ticker="AAPL",
            cik="0000320193",
            name="Apple Inc.",
            sector="Technology",
            market_sector="Technology",
            market_industry="Consumer Electronics",
            cache_state="fresh",
            last_checked=datetime(2026, 3, 27, 18, 0, tzinfo=timezone.utc),
        ),
        financials=[],
        price_history=[],
        refresh=RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
        diagnostics=DataQualityDiagnosticsPayload(),
    )
    expected_bytes = json.dumps(
        payload.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")

    asyncio.run(
        main_module._store_hot_cached_payload(
            "financials:AAPL:asof=latest",
            payload,
            tags=main_module._build_hot_cache_tags(
                ticker="AAPL",
                datasets=("financials", "prices"),
                schema_versions=(main_module.HOT_CACHE_SCHEMA_VERSIONS["financials"],),
                as_of="latest",
            ),
        )
    )

    def _raise_model_validate(_cls, *_args, **_kwargs):
        raise AssertionError("fresh cached hits should bypass model validation")

    monkeypatch.setattr(main_module.CompanyFinancialsResponse, "model_validate", classmethod(_raise_model_validate))
    monkeypatch.setattr(
        main_module,
        "_resolve_cached_company_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("fresh cached hits should not rebuild the payload")),
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/financials")

    assert response.status_code == 200
    assert response.content == expected_bytes
    assert response.headers["content-type"].startswith("application/json")


def test_company_overview_route_populates_hot_cache_on_cold_miss_and_reuses_it_when_warm(monkeypatch):
    monkeypatch.setattr(shared_hot_response_cache, "_redis", None)
    shared_hot_response_cache.clear_sync()
    snapshot = _snapshot()
    build_calls = {"financials": 0, "brief": 0}

    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)

    def _build_financials(*_args, **_kwargs):
        build_calls["financials"] += 1
        return _financials_payload(snapshot)

    def _build_brief(*_args, **_kwargs):
        build_calls["brief"] += 1
        return _brief_payload(snapshot)

    monkeypatch.setattr(main_module, "_build_company_financials_response", _build_financials)
    monkeypatch.setattr(main_module, "_build_company_research_brief_response", _build_brief)

    client = TestClient(app)
    first = client.get("/api/companies/AAPL/overview?financials_view=core_segments")
    assert first.status_code == 200

    def _raise_model_validate(_cls, *_args, **_kwargs):
        raise AssertionError("fresh overview cache hits should bypass model validation")

    monkeypatch.setattr(main_module.CompanyOverviewResponse, "model_validate", classmethod(_raise_model_validate))
    second = client.get("/api/companies/AAPL/overview?financials_view=core_segments")

    assert second.status_code == 200
    assert second.json() == first.json()
    assert build_calls == {"financials": 1, "brief": 1}


def test_company_overview_route_ignores_stale_hot_cache_and_rebuilds_payload(monkeypatch):
    monkeypatch.setattr(shared_hot_response_cache, "_redis", None)
    shared_hot_response_cache.clear_sync()
    snapshot = _snapshot()
    build_calls = {"financials": 0, "brief": 0}

    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(
        main_module,
        "_build_company_financials_response",
        lambda *_args, **_kwargs: build_calls.__setitem__("financials", build_calls["financials"] + 1) or _financials_payload(snapshot),
    )
    monkeypatch.setattr(
        main_module,
        "_build_company_research_brief_response",
        lambda *_args, **_kwargs: build_calls.__setitem__("brief", build_calls["brief"] + 1) or _brief_payload(snapshot),
    )

    stale_payload = main_module.CompanyOverviewResponse(
        company=CompanyPayload(
            ticker="AAPL",
            cik="0000320193",
            name="Cached Apple Inc.",
            sector="Technology",
            market_sector="Technology",
            market_industry="Consumer Electronics",
            cache_state="fresh",
            last_checked=datetime(2026, 3, 27, 18, 0, tzinfo=timezone.utc),
        ),
        financials=_financials_payload(snapshot),
        brief=_brief_payload(snapshot),
    )
    shared_hot_response_cache.store_sync(
        "overview:AAPL:view=core_segments:asof=latest",
        route="overview",
        payload=stale_payload.model_dump(mode="json"),
        tags=main_module._build_hot_cache_tags(
            ticker="AAPL",
            datasets=("financials", "prices", "company_research_brief"),
            schema_versions=(main_module.HOT_CACHE_SCHEMA_VERSIONS["overview"],),
            as_of="latest",
        ),
    )
    entry = shared_hot_response_cache._local_entries["overview:AAPL:view=core_segments:asof=latest"]
    entry.fresh_until = time.time() - 1
    entry.stale_until = time.time() + 60

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/overview?financials_view=core_segments")

    assert response.status_code == 200
    assert response.json()["company"]["name"] == "Apple Inc."
    assert build_calls == {"financials": 1, "brief": 1}


def test_company_workspace_bootstrap_route_populates_hot_cache_on_cold_miss_and_reuses_it_when_warm(monkeypatch):
    monkeypatch.setattr(shared_hot_response_cache, "_redis", None)
    shared_hot_response_cache.clear_sync()
    snapshot = _snapshot()
    build_calls = {"financials": 0, "brief": 0}

    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)

    def _build_financials(*_args, **_kwargs):
        build_calls["financials"] += 1
        return _financials_payload(snapshot)

    def _build_brief(*_args, **_kwargs):
        build_calls["brief"] += 1
        return _brief_payload(snapshot)

    monkeypatch.setattr(main_module, "_build_company_financials_response", _build_financials)
    monkeypatch.setattr(main_module, "_build_company_research_brief_response", _build_brief)

    client = TestClient(app)
    first = client.get("/api/companies/AAPL/workspace-bootstrap?include_overview_brief=true&financials_view=core_segments")
    assert first.status_code == 200

    def _raise_model_validate(_cls, *_args, **_kwargs):
        raise AssertionError("fresh workspace bootstrap cache hits should bypass model validation")

    monkeypatch.setattr(main_module.CompanyWorkspaceBootstrapResponse, "model_validate", classmethod(_raise_model_validate))
    second = client.get("/api/companies/AAPL/workspace-bootstrap?include_overview_brief=true&financials_view=core_segments")

    assert second.status_code == 200
    assert second.json() == first.json()
    assert build_calls == {"financials": 1, "brief": 1}


def test_company_workspace_bootstrap_route_keeps_schema_compatible_when_served_from_hot_cache(monkeypatch):
    monkeypatch.setattr(shared_hot_response_cache, "_redis", None)
    shared_hot_response_cache.clear_sync()
    snapshot = _snapshot()
    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    monkeypatch.setattr(main_module, "_build_company_financials_response", lambda *_args, **_kwargs: _financials_payload(snapshot))
    monkeypatch.setattr(main_module, "_build_company_research_brief_response", lambda *_args, **_kwargs: _brief_payload(snapshot))

    client = TestClient(app)
    first = client.get("/api/companies/AAPL/workspace-bootstrap?include_overview_brief=true&financials_view=core_segments")
    second = client.get("/api/companies/AAPL/workspace-bootstrap?include_overview_brief=true&financials_view=core_segments")

    assert first.status_code == 200
    assert second.status_code == 200
    assert list(second.json()) == [
        "company",
        "financials",
        "brief",
        "earnings_summary",
        "insider_trades",
        "institutional_holdings",
        "errors",
    ]


def test_peers_route_passes_explicit_peer_overrides(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    main_module._hot_response_cache.clear()
    monkeypatch.setattr(main_module, "get_company_price_cache_status", lambda *_args, **_kwargs: (None, "fresh"))
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "_refresh_for_financial_page",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )

    observed: dict[str, list[str] | None] = {"selected": None}

    def _fake_build_peer_comparison(
        _session,
        ticker: str,
        selected_tickers: list[str] | None = None,
        as_of=None,
    ):
        observed["selected"] = selected_tickers
        company_snapshot = _snapshot(ticker=ticker).company
        company = SimpleNamespace(**company_snapshot.__dict__, last_checked=datetime.now(timezone.utc))
        return {
            "company": company,
            "peer_basis": "Cached peer universe",
            "available_companies": [
                {
                    "ticker": "AAPL",
                    "name": "Apple Inc.",
                    "sector": "Technology",
                    "market_sector": "Technology",
                    "market_industry": "Consumer Electronics",
                    "last_checked": datetime.now(timezone.utc),
                    "cache_state": "fresh",
                    "is_focus": True,
                },
                {
                    "ticker": "MSFT",
                    "name": "Microsoft",
                    "sector": "Technology",
                    "market_sector": "Technology",
                    "market_industry": "Software",
                    "last_checked": datetime.now(timezone.utc),
                    "cache_state": "fresh",
                    "is_focus": False,
                },
                {
                    "ticker": "GOOG",
                    "name": "Alphabet",
                    "sector": "Technology",
                    "market_sector": "Technology",
                    "market_industry": "Internet",
                    "last_checked": datetime.now(timezone.utc),
                    "cache_state": "fresh",
                    "is_focus": False,
                },
            ],
            "selected_tickers": ["MSFT", "GOOG"],
            "peers": [
                {
                    "ticker": "AAPL",
                    "name": "Apple Inc.",
                    "sector": "Technology",
                    "market_sector": "Technology",
                    "market_industry": "Consumer Electronics",
                    "is_focus": True,
                    "cache_state": "fresh",
                    "last_checked": datetime.now(timezone.utc),
                    "period_end": date(2025, 12, 31),
                    "price_date": date(2026, 3, 21),
                    "latest_price": 190.0,
                    "pe": 28.0,
                    "ev_to_ebit": 20.0,
                    "price_to_free_cash_flow": 30.0,
                    "roe": 0.24,
                    "revenue_growth": 0.08,
                    "piotroski_score": 8,
                    "altman_z_score": 4.0,
                    "revenue_history": [],
                }
            ],
            "notes": {"ev_to_ebit": "proxy", "price_to_free_cash_flow": "proxy", "piotroski": "score"},
        }

    monkeypatch.setattr(main_module, "build_peer_comparison", _fake_build_peer_comparison)

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/peers?peers=msft,goog")

    assert response.status_code == 200
    payload = response.json()
    assert observed["selected"] == ["MSFT", "GOOG"]
    assert payload["selected_tickers"] == ["MSFT", "GOOG"]


def test_governance_route_filters_proxy_forms(monkeypatch):
    filings = {
        "0002": FilingMetadata(
            accession_number="0002",
            form="DEF 14A",
            filing_date=date(2026, 2, 15),
            report_date=date(2026, 2, 10),
            primary_document="proxy.htm",
            primary_doc_description="Definitive proxy statement",
            items=None,
        ),
        "0003": FilingMetadata(
            accession_number="0003",
            form="10-Q",
            filing_date=date(2026, 2, 1),
            report_date=date(2026, 1, 31),
            primary_document="10q.htm",
            primary_doc_description=None,
            items=None,
        ),
    }
    _install_common_overrides(monkeypatch, filings)
    monkeypatch.setattr(
        main_module,
        "get_company_proxy_statements",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0002",
                form="DEF 14A",
                filing_date=date(2026, 2, 15),
                report_date=date(2026, 2, 10),
                meeting_date=None,
                board_nominee_count=None,
                vote_item_count=0,
                executive_comp_table_detected=False,
                primary_document="proxy.htm",
                source_url="https://www.sec.gov/Archives/edgar/data/1/2/proxy.htm",
                vote_results=[],
            )
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/governance")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["filings"]) == 1
    assert payload["filings"][0]["form"] == "DEF 14A"


def test_governance_route_includes_deterministic_parser_signals(monkeypatch):
    filings = {
        "0002": FilingMetadata(
            accession_number="0002",
            form="DEF 14A",
            filing_date=date(2026, 2, 15),
            report_date=date(2026, 2, 10),
            primary_document="proxy.htm",
            primary_doc_description=None,
            items=None,
        )
    }
    _install_common_overrides(monkeypatch, filings)
    monkeypatch.setattr(
        main_module,
        "get_company_proxy_statements",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0002",
                form="DEF 14A",
                filing_date=date(2026, 2, 15),
                report_date=date(2026, 2, 10),
                meeting_date=date(2026, 5, 20),
                board_nominee_count=9,
                vote_item_count=3,
                executive_comp_table_detected=True,
                primary_document="proxy.htm",
                source_url="https://www.sec.gov/Archives/edgar/data/1/2/proxy.htm",
                vote_results=[
                    SimpleNamespace(
                        proposal_number=1,
                        title="Election of Directors",
                        for_votes=100000,
                        against_votes=5000,
                        abstain_votes=1200,
                        broker_non_votes=9500,
                    )
                ],
            )
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/governance")

    assert response.status_code == 200
    payload = response.json()
    assert payload["filings"][0]["meeting_date"] == "2026-05-20"
    assert payload["filings"][0]["executive_comp_table_detected"] is True
    assert payload["filings"][0]["vote_item_count"] == 3
    assert payload["filings"][0]["board_nominee_count"] == 9
    assert payload["filings"][0]["key_amounts"] == []
    assert payload["filings"][0]["vote_outcomes"][0]["proposal_number"] == 1
    assert payload["filings"][0]["vote_outcomes"][0]["for_votes"] == 100000


def test_governance_summary_endpoint_returns_aggregates(monkeypatch):
    filings = {
        "0002": FilingMetadata(
            accession_number="0002",
            form="DEF 14A",
            filing_date=date(2026, 2, 15),
            report_date=date(2026, 2, 10),
            primary_document="proxy.htm",
            primary_doc_description=None,
            items=None,
        )
    }
    _install_common_overrides(monkeypatch, filings)
    monkeypatch.setattr(main_module, "_load_snapshot_backed_governance_summary_response", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        main_module,
        "get_company_proxy_statements",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0002",
                form="DEF 14A",
                filing_date=date(2026, 2, 15),
                report_date=date(2026, 2, 10),
                meeting_date=date(2026, 5, 20),
                board_nominee_count=9,
                vote_item_count=3,
                executive_comp_table_detected=True,
                primary_document="proxy.htm",
                source_url="https://www.sec.gov/Archives/edgar/data/1/2/proxy.htm",
                vote_results=[
                    SimpleNamespace(
                        proposal_number=1,
                        title="Election of Directors",
                        for_votes=100000,
                        against_votes=5000,
                        abstain_votes=1200,
                        broker_non_votes=9500,
                    )
                ],
            )
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/governance/summary")

    assert response.status_code == 200
    payload = response.json()
    summary = payload["summary"]
    assert summary["total_filings"] == 1
    assert summary["definitive_proxies"] == 1
    assert summary["supplemental_proxies"] == 0
    assert summary["filings_with_meeting_date"] == 1
    assert summary["filings_with_exec_comp"] == 1
    assert summary["filings_with_vote_items"] == 1
    assert summary["latest_meeting_date"] == "2026-05-20"
    assert summary["max_vote_item_count"] == 3


def test_governance_summary_endpoint_prefers_persisted_brief_snapshot(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    refresh = RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None)
    brief_payload = main_module._empty_company_brief_response(refresh=refresh, as_of=None).model_dump(mode="json")
    brief_payload["capital_and_risk"]["governance_summary"]["summary"] = {
        "total_filings": 2,
        "definitive_proxies": 1,
        "supplemental_proxies": 1,
        "filings_with_meeting_date": 2,
        "filings_with_exec_comp": 1,
        "filings_with_vote_items": 2,
        "latest_meeting_date": "2026-05-20",
        "max_vote_item_count": 4,
    }

    monkeypatch.setattr(
        main_module,
        "get_company_research_brief_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(payload=brief_payload),
    )
    monkeypatch.setattr(
        main_module,
        "get_company_proxy_statements",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not query proxy statements when persisted summary exists")),
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/governance/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_filings"] == 2
    assert payload["summary"]["supplemental_proxies"] == 1
    assert payload["summary"]["max_vote_item_count"] == 4


def test_activity_overview_endpoint_prefers_persisted_brief_snapshot(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    refresh = RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None)
    brief_payload = main_module._empty_company_brief_response(refresh=refresh, as_of=None).model_dump(mode="json")
    brief_payload["what_changed"]["activity_overview"]["entries"] = [
        {
            "id": "entry-1",
            "date": "2026-03-21",
            "type": "filing",
            "badge": "8-K",
            "title": "Filed current report",
            "detail": "Persisted activity entry.",
            "href": "/company/AAPL/sec-feed",
        }
    ]
    brief_payload["what_changed"]["activity_overview"]["alerts"] = [
        {
            "id": "alert-1",
            "level": "high",
            "title": "High priority alert",
            "detail": "Persisted activity alert.",
            "source": "sec_edgar",
            "date": "2026-03-21",
            "href": "/company/AAPL/sec-feed",
        }
    ]
    brief_payload["what_changed"]["activity_overview"]["summary"] = {
        "total": 1,
        "high": 1,
        "medium": 0,
        "low": 0,
    }

    monkeypatch.setattr(
        main_module,
        "get_company_research_brief_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(payload=brief_payload),
    )
    monkeypatch.setattr(
        main_module,
        "_load_company_activity_data",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not fan out into per-dataset activity queries")),
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/activity-overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {"total": 1, "high": 1, "medium": 0, "low": 0}
    assert payload["entries"][0]["id"] == "entry-1"
    assert payload["alerts"][0]["id"] == "alert-1"


def test_governance_endpoint_triggers_refresh_when_proxy_cache_missing(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    monkeypatch.setattr(main_module, "get_company_proxy_statements", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_proxy_cache_status", lambda *_args, **_kwargs: (None, "missing"))

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/governance")

    assert response.status_code == 200
    payload = response.json()
    assert payload["filings"] == []
    assert payload["refresh"]["triggered"] is True
    assert payload["refresh"]["reason"] == "missing"


def test_beneficial_ownership_route_flags_amendments(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    monkeypatch.setattr(
        main_module,
        "get_company_beneficial_ownership_reports",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0004",
                form="SC 13D/A",
                base_form="SC 13D",
                filing_date=date(2026, 1, 20),
                report_date=date(2026, 1, 18),
                is_amendment=True,
                primary_document="sc13da.htm",
                primary_doc_description=None,
                source_url="https://www.sec.gov/Archives/edgar/data/1/4/sc13da.htm",
                summary="Beneficial ownership amendment filing.",
                parties=[],
            )
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/beneficial-ownership")

    assert response.status_code == 200
    payload = response.json()
    assert payload["filings"]
    assert payload["filings"][0]["base_form"] == "SC 13D"
    assert payload["filings"][0]["is_amendment"] is True
    assert payload["filings"][0]["parties"] == []


def test_beneficial_ownership_route_includes_cached_party_details(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    monkeypatch.setattr(
        main_module,
        "get_company_beneficial_ownership_reports",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0005",
                form="SC 13D",
                base_form="SC 13D",
                filing_date=date(2026, 3, 16),
                report_date=date(2026, 3, 15),
                is_amendment=False,
                primary_document="sc13d.htm",
                primary_doc_description="",
                source_url="https://www.sec.gov/Archives/edgar/data/1/5/sc13d.htm",
                summary="Beneficial ownership filing.",
                parties=[
                    SimpleNamespace(
                        party_name="Example Capital LP",
                        role="reporting_person",
                        filer_cik="0001234567",
                        shares_owned=2500000.0,
                        percent_owned=8.1,
                        event_date=date(2026, 3, 15),
                        purpose="Item 4 text",
                    )
                ],
            )
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/beneficial-ownership")

    assert response.status_code == 200
    payload = response.json()
    assert payload["filings"]
    party = payload["filings"][0]["parties"][0]
    assert party["party_name"] == "Example Capital LP"
    assert party["filer_cik"] == "0001234567"
    assert party["shares_owned"] == 2500000.0
    assert party["percent_owned"] == 8.1


def test_beneficial_ownership_route_returns_empty_when_cache_missing(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    monkeypatch.setattr(main_module, "get_company_beneficial_ownership_reports", lambda *_args, **_kwargs: [])

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/beneficial-ownership")

    assert response.status_code == 200
    payload = response.json()
    assert payload["filings"] == []
    assert payload["error"] is None


def test_beneficial_ownership_summary_endpoint_aggregates_cached_data(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    monkeypatch.setattr(
        main_module,
        "get_company_beneficial_ownership_reports",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0005",
                form="SC 13D",
                base_form="SC 13D",
                filing_date=date(2026, 3, 16),
                report_date=date(2026, 3, 15),
                is_amendment=False,
                primary_document="sc13d.htm",
                primary_doc_description="",
                source_url="https://www.sec.gov/Archives/edgar/data/1/5/sc13d.htm",
                summary="Beneficial ownership filing.",
                parties=[
                    SimpleNamespace(
                        party_name="Example Capital LP",
                        role="reporting_person",
                        filer_cik="0001234567",
                        shares_owned=2500000.0,
                        percent_owned=8.1,
                        event_date=date(2026, 3, 15),
                        purpose="Item 4 text",
                    )
                ],
            ),
            SimpleNamespace(
                accession_number="0006",
                form="SC 13D/A",
                base_form="SC 13D",
                filing_date=date(2026, 3, 17),
                report_date=date(2026, 3, 16),
                is_amendment=True,
                primary_document="sc13da.htm",
                primary_doc_description="",
                source_url="https://www.sec.gov/Archives/edgar/data/1/6/sc13da.htm",
                summary="Beneficial ownership amendment filing.",
                parties=[
                    SimpleNamespace(
                        party_name="Example Capital LP",
                        role="reporting_person",
                        filer_cik="0001234567",
                        shares_owned=2600000.0,
                        percent_owned=8.5,
                        event_date=date(2026, 3, 16),
                        purpose="Item 4 update",
                    )
                ],
            ),
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/beneficial-ownership/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_filings"] == 2
    assert payload["summary"]["initial_filings"] == 1
    assert payload["summary"]["amendments"] == 1
    assert payload["summary"]["unique_reporting_persons"] == 1
    assert payload["summary"]["max_reported_percent"] == 8.5
    assert payload["summary"]["chains_with_amendments"] == 1
    assert payload["summary"]["amendments_with_delta"] == 1
    assert payload["summary"]["ownership_increase_events"] == 1
    assert payload["summary"]["ownership_decrease_events"] == 0
    assert payload["summary"]["ownership_unchanged_events"] == 0
    assert abs(payload["summary"]["largest_increase_pp"] - 0.4) < 1e-9
    assert payload["summary"]["largest_decrease_pp"] is None


def test_beneficial_ownership_route_includes_amendment_chain_metadata(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    monkeypatch.setattr(
        main_module,
        "get_company_beneficial_ownership_reports",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0007",
                form="SC 13D",
                base_form="SC 13D",
                filing_date=date(2026, 3, 10),
                report_date=date(2026, 3, 9),
                is_amendment=False,
                primary_document="sc13d.htm",
                primary_doc_description="",
                source_url="https://www.sec.gov/Archives/edgar/data/1/7/sc13d.htm",
                summary="Beneficial ownership filing.",
                parties=[
                    SimpleNamespace(
                        party_name="Example Capital LP",
                        role="reporting_person",
                        filer_cik="0001234567",
                        shares_owned=2500000.0,
                        percent_owned=8.1,
                        event_date=date(2026, 3, 9),
                        purpose="Item 4 text",
                    )
                ],
            ),
            SimpleNamespace(
                accession_number="0008",
                form="SC 13D/A",
                base_form="SC 13D",
                filing_date=date(2026, 3, 17),
                report_date=date(2026, 3, 16),
                is_amendment=True,
                primary_document="sc13da.htm",
                primary_doc_description="",
                source_url="https://www.sec.gov/Archives/edgar/data/1/8/sc13da.htm",
                summary="Beneficial ownership amendment filing.",
                parties=[
                    SimpleNamespace(
                        party_name="Example Capital LP",
                        role="reporting_person",
                        filer_cik="0001234567",
                        shares_owned=2600000.0,
                        percent_owned=8.5,
                        event_date=date(2026, 3, 16),
                        purpose="Item 4 update",
                    )
                ],
            ),
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/beneficial-ownership")

    assert response.status_code == 200
    payload = response.json()
    assert payload["filings"]
    amendment = next(item for item in payload["filings"] if item["is_amendment"])
    assert amendment["amendment_sequence"] == 2
    assert amendment["amendment_chain_size"] == 2
    assert amendment["previous_accession_number"] == "0007"
    assert amendment["previous_filing_date"] == "2026-03-10"
    assert amendment["previous_percent_owned"] == 8.1
    assert abs(amendment["percent_change_pp"] - 0.4) < 1e-9
    assert amendment["change_direction"] == "increase"


def test_beneficial_ownership_route_groups_missing_party_rows_by_document_token(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    monkeypatch.setattr(
        main_module,
        "get_company_beneficial_ownership_reports",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0010",
                form="SC 13G/A",
                base_form="SC 13G",
                filing_date=date(2026, 2, 10),
                report_date=date(2026, 2, 9),
                is_amendment=True,
                primary_document="tv0017-appleinc.htm",
                primary_doc_description="",
                source_url="https://www.sec.gov/Archives/edgar/data/1/10/tv0017-appleinc.htm",
                summary="SCHEDULE 13G/A",
                previous_accession_number=None,
                amendment_sequence=None,
                amendment_chain_size=None,
                parties=[],
            ),
            SimpleNamespace(
                accession_number="0011",
                form="SC 13G/A",
                base_form="SC 13G",
                filing_date=date(2026, 3, 10),
                report_date=date(2026, 3, 9),
                is_amendment=True,
                primary_document="tv0017-appleinc.htm",
                primary_doc_description="",
                source_url="https://www.sec.gov/Archives/edgar/data/1/11/tv0017-appleinc.htm",
                summary="SCHEDULE 13G/A",
                previous_accession_number=None,
                amendment_sequence=None,
                amendment_chain_size=None,
                parties=[],
            ),
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/beneficial-ownership")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["filings"]) == 2
    by_accession = {item["accession_number"]: item for item in payload["filings"]}
    earliest = by_accession["0010"]
    latest = by_accession["0011"]

    assert earliest["amendment_sequence"] == 1
    assert earliest["amendment_chain_size"] == 2
    assert latest["amendment_sequence"] == 2
    assert latest["amendment_chain_size"] == 2
    assert latest["previous_accession_number"] == "0010"


def test_institutional_holdings_route_includes_manager_universe_and_amendment_fields(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    monkeypatch.setattr(main_module, "get_company_institutional_holdings_cache_status", lambda *_args, **_kwargs: (None, "fresh"))
    monkeypatch.setattr(
        main_module,
        "get_company_institutional_holdings",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                fund=SimpleNamespace(
                    fund_name="Example Fund",
                    fund_cik="0001234567",
                    fund_manager="Example Capital",
                    manager_query="Example Capital",
                    universe_source="expanded",
                ),
                accession_number="0001000000-26-000001",
                filing_form="13F-HR/A",
                base_form="13F-HR",
                is_amendment=True,
                reporting_date=date(2025, 12, 31),
                filing_date=date(2026, 2, 14),
                shares_held=1000.0,
                market_value=150000.0,
                change_in_shares=100.0,
                percent_change=0.1111,
                portfolio_weight=0.02,
                put_call=None,
                investment_discretion="SOLE",
                voting_authority_sole=900.0,
                voting_authority_shared=50.0,
                voting_authority_none=50.0,
                source="https://www.sec.gov/Archives/edgar/data/1234567/000100000026000001/infotable.xml",
            )
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/institutional-holdings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["institutional_holdings"]
    row = payload["institutional_holdings"][0]
    assert row["fund_cik"] == "0001234567"
    assert row["fund_manager"] == "Example Capital"
    assert row["universe_source"] == "expanded"
    assert row["filing_form"] == "13F-HR/A"
    assert row["base_form"] == "13F-HR"
    assert row["is_amendment"] is True


def test_institutional_holdings_summary_endpoint_returns_counts(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    monkeypatch.setattr(main_module, "get_company_institutional_holdings_cache_status", lambda *_args, **_kwargs: (None, "fresh"))
    monkeypatch.setattr(
        main_module,
        "get_company_institutional_holdings",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                fund=SimpleNamespace(
                    fund_name="Example Fund",
                    fund_cik="0001234567",
                    fund_manager="Example Capital",
                    manager_query="Example Capital",
                    universe_source="curated",
                ),
                accession_number="0001000000-26-000001",
                filing_form="13F-HR",
                base_form="13F-HR",
                is_amendment=False,
                reporting_date=date(2025, 12, 31),
                filing_date=date(2026, 2, 14),
                shares_held=1000.0,
                market_value=150000.0,
                change_in_shares=100.0,
                percent_change=0.1111,
                portfolio_weight=0.02,
                put_call=None,
                investment_discretion="SOLE",
                voting_authority_sole=900.0,
                voting_authority_shared=50.0,
                voting_authority_none=50.0,
                source="https://www.sec.gov/Archives/edgar/data/1234567/000100000026000001/infotable.xml",
            ),
            SimpleNamespace(
                fund=SimpleNamespace(
                    fund_name="Example Fund",
                    fund_cik="0001234567",
                    fund_manager="Example Capital",
                    manager_query="Example Capital",
                    universe_source="curated",
                ),
                accession_number="0001000000-26-000002",
                filing_form="13F-HR/A",
                base_form="13F-HR",
                is_amendment=True,
                reporting_date=date(2025, 9, 30),
                filing_date=date(2025, 11, 15),
                shares_held=900.0,
                market_value=120000.0,
                change_in_shares=-100.0,
                percent_change=-0.1,
                portfolio_weight=0.015,
                put_call=None,
                investment_discretion="SOLE",
                voting_authority_sole=800.0,
                voting_authority_shared=60.0,
                voting_authority_none=40.0,
                source="https://www.sec.gov/Archives/edgar/data/1234567/000100000026000002/infotable.xml",
            ),
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/institutional-holdings/summary")

    assert response.status_code == 200
    payload = response.json()
    summary = payload["summary"]
    assert summary["total_rows"] == 2
    assert summary["unique_managers"] == 1
    assert summary["amended_rows"] == 1
    assert summary["latest_reporting_date"] == "2025-12-31"


def test_serialize_insider_trade_includes_filing_metadata_fields():
    trade = SimpleNamespace(
        insider_name="Jane Doe",
        role="Chief Executive Officer",
        transaction_date=date(2026, 3, 5),
        filing_date=date(2026, 3, 6),
        filing_type="4",
        accession_number="0000320193-26-000001",
        source="https://www.sec.gov/Archives/edgar/data/320193/000032019326000001/xslF345X05/wk-form4.xml",
        action="BUY",
        transaction_code="P",
        shares=12500.0,
        price=182.5,
        value=2_281_250.0,
        ownership_after=950000.0,
        is_10b5_1=False,
    )

    payload = main_module._serialize_insider_trade(trade)

    assert payload.filing_date == date(2026, 3, 6)
    assert payload.filing_type == "4"
    assert payload.accession_number == "0000320193-26-000001"
    assert payload.source and payload.source.startswith("https://www.sec.gov/Archives")


def test_form144_filings_route_returns_cached_rows(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    monkeypatch.setattr(
        main_module,
        "get_company_form144_cache_status",
        lambda *_args, **_kwargs: (datetime.now(timezone.utc), "fresh"),
    )
    monkeypatch.setattr(
        main_module,
        "get_company_form144_filings",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0000123-26-000444",
                form="144",
                filing_date=date(2026, 3, 19),
                report_date=date(2026, 3, 19),
                filer_name="Jane Insider",
                relationship_to_issuer="Officer",
                issuer_name="Apple Inc.",
                security_title="Common Stock",
                planned_sale_date=date(2026, 3, 29),
                shares_to_be_sold=12500.0,
                aggregate_market_value=2_500_000.0,
                shares_owned_after_sale=490000.0,
                broker_name="Alpha Brokerage",
                source_url="https://www.sec.gov/Archives/edgar/data/1/123/x144.xml",
                summary="Form 144 planned sale by Jane Insider.",
            )
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/form-144-filings")

    assert response.status_code == 200
    payload = response.json()
    assert payload["filings"]
    row = payload["filings"][0]
    assert row["form"] == "144"
    assert row["filer_name"] == "Jane Insider"
    assert row["planned_sale_date"] == "2026-03-29"
    assert row["shares_to_be_sold"] == 12500.0


def test_serialize_institutional_holding_includes_filing_metadata_fields():
    fund = SimpleNamespace(fund_name="Example Capital", fund_manager="Example Capital Management")
    holding = SimpleNamespace(
        fund=fund,
        accession_number="0000950123-26-001234",
        reporting_date=date(2025, 12, 31),
        filing_date=date(2026, 2, 14),
        shares_held=1_500_000.0,
        market_value=245_000_000.0,
        change_in_shares=50_000.0,
        percent_change=3.45,
        portfolio_weight=4.2,
        source="https://www.sec.gov/Archives/edgar/data/12345/000095012326001234/form13fInfoTable.xml",
    )

    payload = main_module._serialize_institutional_holding(holding)

    assert payload.accession_number == "0000950123-26-001234"
    assert payload.filing_date == date(2026, 2, 14)
    assert payload.source and payload.source.startswith("https://www.sec.gov/Archives")


def test_activity_feed_endpoint_returns_unified_entries(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    monkeypatch.setattr(main_module, "_load_snapshot_backed_activity_overview_response", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_proxy_statements", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "_load_filings_from_cache",
        lambda *_args, **_kwargs: [
            main_module.FilingPayload(
                accession_number="0000001",
                form="10-K",
                filing_date=date(2026, 3, 10),
                report_date=date(2025, 12, 31),
                primary_document="annual.htm",
                primary_doc_description="Annual report",
                items=None,
                source_url="https://www.sec.gov/Archives/edgar/data/1/1/annual.htm",
            )
        ],
    )
    monkeypatch.setattr(
        main_module,
        "get_company_filing_events",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0000002",
                form="8-K",
                filing_date=date(2026, 3, 12),
                report_date=date(2026, 3, 11),
                items="2.02",
                item_code="2.02",
                category="Earnings",
                primary_document="8k.htm",
                primary_doc_description=None,
                source_url="https://www.sec.gov/Archives/edgar/data/1/2/8k.htm",
                summary="Earnings update.",
                key_amounts=[],
            )
        ],
    )
    monkeypatch.setattr(
        main_module,
        "get_company_proxy_statements",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0000003",
                form="DEF 14A",
                filing_date=date(2026, 3, 9),
                report_date=date(2026, 3, 8),
                meeting_date=None,
                board_nominee_count=None,
                vote_item_count=0,
                executive_comp_table_detected=False,
                primary_document="proxy.htm",
                source_url="https://www.sec.gov/Archives/edgar/data/1/3/proxy.htm",
                vote_results=[],
            )
        ],
    )
    monkeypatch.setattr(
        main_module,
        "get_company_beneficial_ownership_reports",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0000004",
                form="SC 13D",
                base_form="SC 13D",
                filing_date=date(2026, 3, 13),
                report_date=date(2026, 3, 12),
                is_amendment=False,
                primary_document="sc13d.htm",
                primary_doc_description="",
                source_url="https://www.sec.gov/Archives/edgar/data/1/4/sc13d.htm",
                summary="Beneficial ownership filing.",
                parties=[],
            )
        ],
    )
    monkeypatch.setattr(
        main_module,
        "get_company_insider_trades",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                insider_name="Jane Doe",
                role="Chief Executive Officer",
                transaction_date=date(2026, 3, 14),
                filing_date=date(2026, 3, 15),
                filing_type="4",
                accession_number="0000005",
                source="https://www.sec.gov/Archives/edgar/data/1/5/form4.xml",
                action="BUY",
                transaction_code="P",
                shares=1000.0,
                price=180.0,
                value=180000.0,
                ownership_after=500000.0,
                is_10b5_1=False,
            )
        ],
    )
    monkeypatch.setattr(
        main_module,
        "get_company_form144_filings",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0000007",
                form="144",
                filing_date=date(2026, 3, 16),
                report_date=date(2026, 3, 16),
                filer_name="Jane Doe",
                relationship_to_issuer="Officer",
                issuer_name="Apple Inc.",
                security_title="Common Stock",
                planned_sale_date=date(2026, 3, 20),
                shares_to_be_sold=10000.0,
                aggregate_market_value=1820000.0,
                shares_owned_after_sale=490000.0,
                broker_name="Example Broker",
                source_url="https://www.sec.gov/Archives/edgar/data/1/7/x144.xml",
                summary="Form 144 planned sale.",
            )
        ],
    )
    monkeypatch.setattr(
        main_module,
        "get_company_institutional_holdings",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                fund=SimpleNamespace(
                    fund_name="Example Fund",
                    fund_cik="0001234567",
                    fund_manager="Example Capital",
                    manager_query="Example Capital",
                    universe_source="curated",
                ),
                accession_number="0000006",
                filing_form="13F-HR",
                base_form="13F-HR",
                is_amendment=False,
                reporting_date=date(2025, 12, 31),
                filing_date=date(2026, 2, 14),
                shares_held=5000.0,
                market_value=750000.0,
                change_in_shares=500.0,
                percent_change=10.0,
                portfolio_weight=0.02,
                put_call=None,
                investment_discretion="SOLE",
                voting_authority_sole=5000.0,
                voting_authority_shared=0.0,
                voting_authority_none=0.0,
                source="https://www.sec.gov/Archives/edgar/data/1/6/infotable.xml",
            )
        ],
    )
    monkeypatch.setattr(
        main_module,
        "get_company_comment_letters",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0000008",
                filing_date=date(2026, 3, 18),
                description="SEC correspondence regarding disclosure clarity.",
                sec_url="https://www.sec.gov/Archives/edgar/data/1/8/index.html",
            )
        ],
    )
    monkeypatch.setattr(main_module, "get_company_capital_markets_events", lambda *_args, **_kwargs: [])

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/activity-feed")

    assert response.status_code == 200
    payload = response.json()
    assert payload["entries"]
    entry_types = {item["type"] for item in payload["entries"]}
    assert "event" in entry_types
    assert "governance" in entry_types
    assert "ownership-change" in entry_types
    assert "insider" in entry_types
    assert "form144" in entry_types
    assert "institutional" in entry_types
    assert "comment-letter" in entry_types
    form144_entry = next(item for item in payload["entries"] if item["type"] == "form144")
    assert form144_entry["badge"] == "144"
    assert "Planned sale 2026-03-20" in form144_entry["detail"]


def test_alerts_endpoint_surfaces_priority_signals(monkeypatch):
    _install_common_overrides(monkeypatch, {})
    monkeypatch.setattr(main_module, "_load_snapshot_backed_activity_overview_response", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_module, "get_company_financials", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_proxy_statements", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "_load_filings_from_cache", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_filing_events", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "get_company_beneficial_ownership_reports",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0000100",
                form="SC 13D",
                base_form="SC 13D",
                filing_date=date(2026, 3, 16),
                report_date=date(2026, 3, 15),
                is_amendment=False,
                primary_document="sc13d.htm",
                primary_doc_description="",
                source_url="https://www.sec.gov/Archives/edgar/data/1/100/sc13d.htm",
                summary="Beneficial ownership filing.",
                parties=[
                    SimpleNamespace(
                        party_name="Example Capital LP",
                        role="reporting_person",
                        filer_cik="0001234567",
                        shares_owned=2500000.0,
                        percent_owned=12.3,
                        event_date=date(2026, 3, 15),
                        purpose="Item 4 text",
                    )
                ],
            )
        ],
    )
    monkeypatch.setattr(
        main_module,
        "get_company_capital_markets_events",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0000101",
                form="NT 10-Q",
                filing_date=date(2026, 3, 17),
                report_date=date(2026, 3, 17),
                primary_document="nt10q.htm",
                primary_doc_description="",
                source_url="https://www.sec.gov/Archives/edgar/data/1/101/nt10q.htm",
                summary="Late filing notice.",
                event_type="Late Filing Notice",
                security_type=None,
                offering_amount=None,
                shelf_size=None,
                is_late_filer=True,
            )
        ],
    )
    monkeypatch.setattr(
        main_module,
        "get_company_insider_trades",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                insider_name="John Doe",
                role="Chief Financial Officer",
                transaction_date=date(2026, 3, 5),
                filing_date=date(2026, 3, 6),
                filing_type="4",
                accession_number="0000102",
                source="https://www.sec.gov/Archives/edgar/data/1/102/form4.xml",
                action="SELL",
                transaction_code="S",
                shares=2000.0,
                price=170.0,
                value=340000.0,
                ownership_after=100000.0,
                is_10b5_1=False,
            )
        ],
    )
    monkeypatch.setattr(main_module, "get_company_form144_filings", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "get_company_institutional_holdings", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "get_company_comment_letters",
        lambda *_args, **_kwargs: [
            SimpleNamespace(
                accession_number="0000103",
                filing_date=date(2026, 3, 20),
                description="SEC correspondence regarding revenue presentation.",
                sec_url="https://www.sec.gov/Archives/edgar/data/1/103/index.html",
            )
        ],
    )

    client = TestClient(app)
    response = client.get("/api/companies/AAPL/alerts")

    assert response.status_code == 200
    payload = response.json()
    assert payload["alerts"]
    assert payload["summary"]["high"] >= 1
    titles = {item["title"] for item in payload["alerts"]}
    assert "Large beneficial ownership stake reported" in titles
    assert "Late filer notice" in titles
    assert "New SEC comment letter correspondence" in titles


    # ---------------------------------------------------------------------------
    # Executive-compensation endpoint tests
    # ---------------------------------------------------------------------------

    def test_executive_compensation_route_returns_none_source_when_no_cache_and_no_proxy(monkeypatch):
        """With empty cache and no DEF 14A filings the endpoint returns source='none'."""
        _install_common_overrides(monkeypatch, {})
        monkeypatch.setattr(main_module, "get_company_executive_compensation", lambda *_args, **_kwargs: [])

        client = TestClient(app)
        response = client.get("/api/companies/AAPL/executive-compensation")

        assert response.status_code == 200
        payload = response.json()
        assert payload["rows"] == []
        assert payload["fiscal_years"] == []
        assert payload["source"] == "none"
        assert payload["error"] is None


    def test_executive_compensation_route_returns_cached_rows(monkeypatch):
        """When the DB has executive_compensation rows they are returned with source='cached'."""
        _install_common_overrides(monkeypatch, {})
        monkeypatch.setattr(
            main_module,
            "get_company_executive_compensation",
            lambda *_args, **_kwargs: [
                SimpleNamespace(
                    executive_name="Jane Smith",
                    executive_title="Chief Executive Officer",
                    fiscal_year=2025,
                    salary=1_500_000.0,
                    bonus=500_000.0,
                    stock_awards=8_000_000.0,
                    option_awards=None,
                    non_equity_incentive=2_000_000.0,
                    other_compensation=85_000.0,
                    total_compensation=12_085_000.0,
                ),
                SimpleNamespace(
                    executive_name="Bob Lee",
                    executive_title="Chief Financial Officer",
                    fiscal_year=2025,
                    salary=900_000.0,
                    bonus=250_000.0,
                    stock_awards=3_500_000.0,
                    option_awards=None,
                    non_equity_incentive=800_000.0,
                    other_compensation=42_000.0,
                    total_compensation=5_492_000.0,
                ),
            ],
        )

        client = TestClient(app)
        response = client.get("/api/companies/AAPL/executive-compensation")

        assert response.status_code == 200
        payload = response.json()
        assert payload["source"] == "cached"
        assert payload["error"] is None
        assert len(payload["rows"]) == 2
        assert payload["fiscal_years"] == [2025]

        ceo = next(r for r in payload["rows"] if r["executive_name"] == "Jane Smith")
        assert ceo["executive_title"] == "Chief Executive Officer"
        assert ceo["salary"] == 1_500_000.0
        assert ceo["total_compensation"] == 12_085_000.0
        assert ceo["option_awards"] is None


    def test_executive_compensation_route_returns_none_when_cache_missing(monkeypatch):
        """When cache is empty the endpoint remains cache-first and returns source='none'."""
        _install_common_overrides(monkeypatch, {})
        monkeypatch.setattr(main_module, "get_company_executive_compensation", lambda *_args, **_kwargs: [])

        client = TestClient(app)
        response = client.get("/api/companies/AAPL/executive-compensation")

        assert response.status_code == 200
        payload = response.json()
        assert payload["source"] == "none"
        assert payload["error"] is None
        assert payload["rows"] == []
        assert payload["fiscal_years"] == []


def test_watchlist_summary_endpoint_normalizes_dedupes_and_ignores_blank_tickers(monkeypatch):
    observed: list[str] = []
    snapshots = {
        "AAPL": _snapshot("AAPL", "0000320193"),
        "MSFT": _snapshot("MSFT", "0000789019"),
        "TSLA": _snapshot("TSLA", "0001318605"),
    }

    monkeypatch.setattr(main_module, "get_company_snapshots_by_ticker", lambda *_args, **_kwargs: snapshots)
    monkeypatch.setattr(
        main_module,
        "get_company_coverage_counts",
        lambda *_args, **_kwargs: {
            snapshots["AAPL"].company.id: {"financial_periods": 0, "price_points": 0},
            snapshots["MSFT"].company.id: {"financial_periods": 0, "price_points": 0},
            snapshots["TSLA"].company.id: {"financial_periods": 0, "price_points": 0},
        },
    )
    monkeypatch.setattr(main_module, "_load_watchlist_summary_preload", lambda *_args, **_kwargs: None)

    def _fake_item(_session, _background_tasks, ticker: str, **_kwargs):
        observed.append(ticker)
        return main_module.WatchlistSummaryItemPayload(
            ticker=ticker,
            name=f"{ticker} Inc.",
            sector="Technology",
            cik="0000000000",
            last_checked=None,
            refresh=RefreshState(triggered=False, reason="fresh", ticker=ticker, job_id=None),
            alert_summary=main_module.AlertsSummaryPayload(total=0, high=0, medium=0, low=0),
            latest_alert=None,
            latest_activity=None,
            coverage=main_module.WatchlistCoveragePayload(financial_periods=0, price_points=0),
        )

    monkeypatch.setattr(main_module, "_build_watchlist_summary_item", _fake_item)

    client = TestClient(app)
    response = client.post(
        "/api/watchlist/summary",
        json={"tickers": [" aapl ", "", "AAPL", " msft ", " ", "MSFT", "tsla"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tickers"] == ["AAPL", "MSFT", "TSLA"]
    assert observed == ["AAPL", "MSFT", "TSLA"]
    assert [item["ticker"] for item in payload["companies"]] == ["AAPL", "MSFT", "TSLA"]


def test_watchlist_summary_endpoint_rejects_more_than_50_tickers():
    client = TestClient(app)
    tickers = [f"T{i}" for i in range(51)]
    response = client.post("/api/watchlist/summary", json={"tickers": tickers})

    assert response.status_code == 422
    assert "maximum of 50" in response.json()["detail"].lower()


def test_watchlist_summary_endpoint_tolerates_activity_data_failures(monkeypatch):
    snap = _snapshot("AAPL", "0000320193")
    monkeypatch.setattr(main_module, "get_company_snapshots_by_ticker", lambda *_args, **_kwargs: {"AAPL": snap})
    monkeypatch.setattr(
        main_module,
        "get_company_coverage_counts",
        lambda *_args, **_kwargs: {snap.company.id: {"financial_periods": 2, "price_points": 3}},
    )
    monkeypatch.setattr(main_module, "_load_watchlist_summary_preload", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(main_module, "_load_company_activity_data", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(main_module, "get_company_research_brief_snapshot", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_module, "get_company_models", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "_visible_price_history", lambda *_args, **_kwargs: [])

    client = TestClient(app)
    response = client.post("/api/watchlist/summary", json={"tickers": ["aapl"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["tickers"] == ["AAPL"]
    assert len(payload["companies"]) == 1

    item = payload["companies"][0]
    assert item["ticker"] == "AAPL"
    assert item["name"] == "Apple Inc."
    assert item["sector"] == "Technology"
    assert item["cik"] == "0000320193"
    assert item["coverage"]["financial_periods"] == 2
    assert item["coverage"]["price_points"] == 3
    assert item["alert_summary"] == {"total": 0, "high": 0, "medium": 0, "low": 0}
    assert item["latest_alert"] is None
    assert item["latest_activity"] is None


def test_watchlist_summary_endpoint_tolerates_snapshot_lookup_failures(monkeypatch):
    observed: list[str] = []

    def _fake_missing(_background_tasks, ticker: str):
        observed.append(ticker)
        return main_module.WatchlistSummaryItemPayload(
            ticker=ticker,
            name=None,
            sector=None,
            cik=None,
            last_checked=None,
            refresh=RefreshState(triggered=True, reason="missing", ticker=ticker, job_id=f"job-{ticker}"),
            alert_summary=main_module.AlertsSummaryPayload(total=0, high=0, medium=0, low=0),
            latest_alert=None,
            latest_activity=None,
            coverage=main_module.WatchlistCoveragePayload(financial_periods=0, price_points=0),
        )

    monkeypatch.setattr(
        main_module,
        "get_company_snapshots_by_ticker",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError("pool busy")),
    )
    monkeypatch.setattr(main_module, "_build_missing_watchlist_summary_item", _fake_missing)

    client = TestClient(app)
    response = client.post("/api/watchlist/summary", json={"tickers": ["AAPL", "MSFT"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["tickers"] == ["AAPL", "MSFT"]
    assert observed == ["AAPL", "MSFT"]
    assert [item["name"] for item in payload["companies"]] == [None, None]


def test_watchlist_summary_endpoint_includes_comment_letter_alerts(monkeypatch):
    snap = _snapshot("AAPL", "0000320193")
    monkeypatch.setattr(main_module, "get_company_snapshots_by_ticker", lambda *_args, **_kwargs: {"AAPL": snap})
    monkeypatch.setattr(
        main_module,
        "get_company_coverage_counts",
        lambda *_args, **_kwargs: {snap.company.id: {"financial_periods": 2, "price_points": 3}},
    )
    monkeypatch.setattr(main_module, "_load_watchlist_summary_preload", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "_load_company_activity_data",
        lambda *_args, **_kwargs: {
            "beneficial_filings": [],
            "capital_filings": [],
            "insider_trades": [],
            "institutional_holdings": [],
            "filings": [],
            "filing_events": [],
            "governance_filings": [],
            "form144_filings": [],
            "comment_letters": [
                main_module.CommentLetterPayload(
                    accession_number="0000000000-26-000001",
                    filing_date=date(2026, 4, 10),
                    description="SEC staff requested additional disclosure detail.",
                    sec_url="https://www.sec.gov/Archives/example-letter",
                )
            ],
        },
    )
    monkeypatch.setattr(main_module, "get_company_research_brief_snapshot", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_module, "get_company_models", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "_visible_price_history", lambda *_args, **_kwargs: [])

    client = TestClient(app)
    response = client.post("/api/watchlist/summary", json={"tickers": ["AAPL"]})

    assert response.status_code == 200
    item = response.json()["companies"][0]
    assert item["alert_summary"] == {"total": 1, "high": 0, "medium": 1, "low": 0}
    assert item["latest_alert"]["source"] == "comment-letters"
    assert item["latest_alert"]["title"] == "New SEC comment letter correspondence"


def test_watchlist_summary_endpoint_includes_research_brief_material_change_digest(monkeypatch):
    snap = _snapshot("AAPL", "0000320193")
    monkeypatch.setattr(main_module, "get_company_snapshots_by_ticker", lambda *_args, **_kwargs: {"AAPL": snap})
    monkeypatch.setattr(
        main_module,
        "get_company_coverage_counts",
        lambda *_args, **_kwargs: {snap.company.id: {"financial_periods": 2, "price_points": 3}},
    )
    monkeypatch.setattr(main_module, "_load_watchlist_summary_preload", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "_load_company_activity_data",
        lambda *_args, **_kwargs: {
            "beneficial_filings": [],
            "capital_filings": [],
            "insider_trades": [],
            "institutional_holdings": [],
            "filings": [],
            "filing_events": [],
            "governance_filings": [],
            "form144_filings": [],
        },
    )
    monkeypatch.setattr(main_module, "get_company_models", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(main_module, "_visible_price_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        main_module,
        "get_company_research_brief_snapshot",
        lambda *_args, **_kwargs: SimpleNamespace(
            payload={
                "what_changed": {
                    "changes": {
                        "summary": {
                            "filing_type": "10-Q",
                            "current_period_end": "2026-03-31",
                            "previous_period_end": "2025-12-31",
                            "high_signal_change_count": 2,
                            "new_risk_indicator_count": 1,
                            "share_count_change_count": 0,
                            "capital_structure_change_count": 1,
                            "comment_letter_count": 0,
                        },
                        "high_signal_changes": [
                            {
                                "title": "Demand language softened",
                                "summary": "Management added softer demand language in MD&A.",
                                "why_it_matters": "Margin and revenue assumptions may need to compress.",
                                "importance": "high",
                                "category": "mda",
                                "signal_tags": ["demand", "margin"],
                            }
                        ],
                    }
                }
            }
        ),
    )

    client = TestClient(app)
    response = client.post("/api/watchlist/summary", json={"tickers": ["AAPL"]})

    assert response.status_code == 200
    item = response.json()["companies"][0]
    assert item["material_change"]["headline"] == "2 high-signal changes since the last filing"
    assert item["material_change"]["new_risk_indicator_count"] == 1
    assert item["material_change"]["capital_structure_change_count"] == 1
    assert item["material_change"]["highlights"][0]["title"] == "Demand language softened"


def test_watchlist_summary_endpoint_tolerates_per_ticker_builder_exceptions(monkeypatch):
    snapshots = {
        "AAPL": _snapshot("AAPL", "0000320193"),
        "MSFT": _snapshot("MSFT", "0000789019"),
    }
    monkeypatch.setattr(main_module, "get_company_snapshots_by_ticker", lambda *_args, **_kwargs: snapshots)
    monkeypatch.setattr(
        main_module,
        "get_company_coverage_counts",
        lambda *_args, **_kwargs: {
            snapshots["AAPL"].company.id: {"financial_periods": 2, "price_points": 3},
            snapshots["MSFT"].company.id: {"financial_periods": 2, "price_points": 3},
        },
    )
    monkeypatch.setattr(main_module, "_load_watchlist_summary_preload", lambda *_args, **_kwargs: None)

    def _fake_item(_session, _background_tasks, ticker: str, **_kwargs):
        if ticker == "MSFT":
            raise RuntimeError("broken ticker payload")
        return main_module.WatchlistSummaryItemPayload(
            ticker=ticker,
            name=f"{ticker} Inc.",
            sector="Technology",
            cik="0000000000",
            last_checked=None,
            refresh=RefreshState(triggered=False, reason="fresh", ticker=ticker, job_id=None),
            alert_summary=main_module.AlertsSummaryPayload(total=0, high=0, medium=0, low=0),
            latest_alert=None,
            latest_activity=None,
            coverage=main_module.WatchlistCoveragePayload(financial_periods=2, price_points=3),
        )

    monkeypatch.setattr(main_module, "_build_watchlist_summary_item", _fake_item)
    monkeypatch.setattr(main_module, "_trigger_refresh", lambda *_args, **_kwargs: RefreshState(triggered=True, reason="missing", ticker="MSFT", job_id="job-2"))

    client = TestClient(app)
    response = client.post("/api/watchlist/summary", json={"tickers": ["AAPL", "MSFT"]})

    assert response.status_code == 200
    payload = response.json()
    assert payload["tickers"] == ["AAPL", "MSFT"]
    assert len(payload["companies"]) == 2

    aapl_item = payload["companies"][0]
    msft_item = payload["companies"][1]
    assert aapl_item["ticker"] == "AAPL"
    assert aapl_item["coverage"] == {"financial_periods": 2, "price_points": 3}
    assert msft_item["ticker"] == "MSFT"
    assert msft_item["name"] is None
    assert msft_item["alert_summary"] == {"total": 0, "high": 0, "medium": 0, "low": 0}


def test_watchlist_summary_endpoint_uses_batched_preload(monkeypatch):
    snap = _snapshot("AAPL", "0000320193")
    monkeypatch.setattr(main_module, "get_company_snapshots_by_ticker", lambda *_args, **_kwargs: {"AAPL": snap})
    monkeypatch.setattr(
        main_module,
        "get_company_coverage_counts",
        lambda *_args, **_kwargs: {snap.company.id: {"financial_periods": 2, "price_points": 3}},
    )
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )
    monkeypatch.setattr(
        main_module,
        "_load_watchlist_summary_preload",
        lambda *_args, **_kwargs: {
            "activity_by_company_id": {
                snap.company.id: {
                    "beneficial_filings": [],
                    "capital_filings": [],
                    "insider_trades": [],
                    "institutional_holdings": [],
                    "filings": [],
                    "filing_events": [],
                    "governance_filings": [],
                    "form144_filings": [],
                    "comment_letters": [],
                }
            },
            "models_by_company_id": {
                snap.company.id: {
                    "dcf": SimpleNamespace(result={"fair_value_per_share": 120.0, "model_status": "ready"}),
                    "roic": SimpleNamespace(result={"roic": 0.18}),
                    "reverse_dcf": SimpleNamespace(result={"implied_growth": 0.07, "status": "ready", "valuation_band_percentile": 0.65}),
                    "capital_allocation": SimpleNamespace(result={"shareholder_yield": 0.03}),
                    "ratios": SimpleNamespace(result={"values": {"net_debt_to_fcf": 1.8}}),
                }
            },
            "latest_prices_by_company_id": {snap.company.id: 100.0},
            "brief_snapshots_by_company_id": {
                snap.company.id: SimpleNamespace(
                    payload={
                        "what_changed": {
                            "changes": {
                                "summary": {
                                    "filing_type": "10-Q",
                                    "high_signal_change_count": 1,
                                },
                                "high_signal_changes": [
                                    {
                                        "title": "Margin pressure",
                                        "summary": "Gross margin compressed year over year.",
                                        "importance": "high",
                                    }
                                ],
                            }
                        }
                    }
                )
            },
        },
    )
    monkeypatch.setattr(
        main_module,
        "_load_company_activity_data",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("should not load per-ticker activity")),
    )
    monkeypatch.setattr(
        main_module,
        "get_company_models",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("should not load per-ticker models")),
    )
    monkeypatch.setattr(
        main_module,
        "_visible_price_history",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("should not load per-ticker prices")),
    )
    monkeypatch.setattr(
        main_module,
        "get_company_research_brief_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("should not load per-ticker brief snapshot")),
    )

    client = TestClient(app)
    response = client.post("/api/watchlist/summary", json={"tickers": ["AAPL"]})

    assert response.status_code == 200
    item = response.json()["companies"][0]
    assert item["ticker"] == "AAPL"
    assert item["fair_value_gap"] == pytest.approx(0.2)
    assert item["roic"] == pytest.approx(0.18)
    assert item["shareholder_yield"] == pytest.approx(0.03)
    assert item["implied_growth"] == pytest.approx(0.07)
    assert item["valuation_band_percentile"] == pytest.approx(0.65)
    assert item["balance_sheet_risk"] == pytest.approx(1.8)
    assert item["material_change"]["headline"] == "1 high-signal change since the last filing"


def test_watchlist_calendar_endpoint_projects_expected_events(monkeypatch):
    aapl_snapshot = _snapshot("AAPL", "0000320193")
    aapl_snapshot.company.id = 1
    msft_snapshot = _snapshot("MSFT", "0000789019")
    msft_snapshot.company.id = 2
    snapshots = {
        "AAPL": aapl_snapshot,
        "MSFT": msft_snapshot,
    }

    financials_by_ticker = {
        "AAPL": [
            SimpleNamespace(filing_type="10-K", period_end=date(2025, 12, 31), filing_acceptance_at=datetime(2026, 3, 1, tzinfo=timezone.utc)),
            SimpleNamespace(filing_type="10-Q", period_end=date(2025, 9, 30), filing_acceptance_at=datetime(2025, 11, 9, tzinfo=timezone.utc)),
            SimpleNamespace(filing_type="10-Q", period_end=date(2025, 6, 30), filing_acceptance_at=datetime(2025, 8, 9, tzinfo=timezone.utc)),
            SimpleNamespace(filing_type="10-Q", period_end=date(2025, 3, 31), filing_acceptance_at=datetime(2025, 5, 10, tzinfo=timezone.utc)),
        ],
        "MSFT": [
            SimpleNamespace(filing_type="10-K", period_end=date(2025, 12, 31), filing_acceptance_at=datetime(2026, 2, 20, tzinfo=timezone.utc)),
        ],
    }
    filing_events_by_company = {
        1: [],
        2: [
            SimpleNamespace(
                accession_number="0002-26-000001",
                item_code="2.02",
                filing_date=date(2026, 5, 20),
                report_date=date(2026, 5, 20),
                summary="8-K Item 2.02: Earnings update.",
                form="8-K",
                items="2.02,9.01",
                category="Earnings",
                source_url="https://www.sec.gov/Archives/example",
            )
        ],
    }

    monkeypatch.setattr(main_module, "_watchlist_calendar_today", lambda: date(2026, 4, 4))
    monkeypatch.setattr(main_module, "get_company_snapshots_by_ticker", lambda *_args, **_kwargs: snapshots)
    monkeypatch.setattr(main_module, "_visible_financials_for_company", lambda _session, company, **_kwargs: financials_by_ticker[company.ticker])
    monkeypatch.setattr(main_module, "get_company_filing_events", lambda _session, company_id, **_kwargs: filing_events_by_company[company_id])

    client = TestClient(app)
    response = client.get("/api/watchlist/calendar", params=[("tickers", "aapl"), ("tickers", "MSFT")])

    assert response.status_code == 200
    payload = response.json()
    assert payload["tickers"] == ["AAPL", "MSFT"]
    assert payload["window_start"] == "2026-04-04"
    assert payload["window_end"] == "2026-07-03"
    assert [item["event_type"] for item in payload["events"]] == ["expected_filing", "expected_filing", "institutional_deadline", "sec_event"]

    expected_filing = payload["events"][0]
    assert expected_filing["ticker"] == "AAPL"
    assert expected_filing["date"] == "2026-05-10"
    assert expected_filing["form"] == "10-Q"

    second_filing = payload["events"][1]
    assert second_filing["ticker"] == "MSFT"
    assert second_filing["date"] == "2026-05-10"
    assert second_filing["form"] == "10-Q"

    deadline = payload["events"][2]
    assert deadline["ticker"] is None
    assert deadline["date"] == "2026-05-15"
    assert deadline["form"] == "13F-HR"

    sec_event = payload["events"][3]
    assert sec_event["ticker"] == "MSFT"
    assert sec_event["date"] == "2026-05-20"
    assert sec_event["form"] == "8-K"


def test_watchlist_calendar_endpoint_rejects_more_than_50_tickers():
    client = TestClient(app)
    params = [("tickers", f"T{i}") for i in range(51)]
    response = client.get("/api/watchlist/calendar", params=params)

    assert response.status_code == 422
    assert "maximum of 50" in response.json()["detail"].lower()
