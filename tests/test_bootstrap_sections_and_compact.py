"""Tests for bootstrap endpoint sections parameter and compact mode."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

import app.main as main_module
import app.api.handlers._shared as _shared_handlers
try:
    from app.api.handlers import company_overview as _company_overview_handlers
except Exception:
    _company_overview_handlers = None

from app.api.schemas.common import CompanyPayload, RefreshState, DataQualityDiagnosticsPayload
from app.api.schemas.financials import CompanyFinancialsResponse
from app.main import app
from app.services.sec_edgar import FilingMetadata
from app.services.hot_cache import shared_hot_response_cache


def _patch_main_and_shared(monkeypatch, name: str, value) -> None:
    monkeypatch.setattr(main_module, name, value)
    if hasattr(_shared_handlers, name):
        monkeypatch.setattr(_shared_handlers, name, value)
    if _company_overview_handlers is not None and hasattr(_company_overview_handlers, name):
        monkeypatch.setattr(_company_overview_handlers, name, value)


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
        id=1,
        ticker=snapshot.company.ticker,
        cik=snapshot.company.cik,
        name=snapshot.company.name,
        sector=snapshot.company.sector,
        market_sector=snapshot.company.market_sector,
        market_industry=snapshot.company.market_industry,
        cache_state="fresh",
        last_checked=datetime.now(timezone.utc),
    )


def _financials_payload(snapshot):
    return CompanyFinancialsResponse(
        company=_company_payload(snapshot),
        ticker=snapshot.company.ticker,
        latest_statements=[],
        statements={},
        price_history=[],
        refresh=RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None),
        diagnostics=DataQualityDiagnosticsPayload(),
    )


def _brief_payload(snapshot):
    return SimpleNamespace(
        company=_company_payload(snapshot),
        schema_version="v1",
        generated_at=datetime.now(timezone.utc),
        as_of=None,
        refresh=RefreshState(triggered=False),
        build_state="ready",
        build_status="Ready",
        available_sections=[],
        section_statuses=[],
        filing_timeline=[],
        stale_summary_cards=[],
        snapshot=SimpleNamespace(summary=SimpleNamespace()),
        what_changed=SimpleNamespace(
            activity_overview=SimpleNamespace(facts=[]),
            changes=SimpleNamespace(facts=[]),
            earnings_summary=SimpleNamespace(),
        ),
        business_quality=SimpleNamespace(summary=SimpleNamespace()),
        capital_and_risk=SimpleNamespace(
            capital_structure=SimpleNamespace(),
            capital_markets_summary=SimpleNamespace(),
            governance_summary=SimpleNamespace(facts=[]),
            ownership_summary=SimpleNamespace(facts=[]),
            equity_claim_risk_summary=SimpleNamespace(),
        ),
        valuation=SimpleNamespace(models=SimpleNamespace(), peers=SimpleNamespace()),
        monitor=SimpleNamespace(activity_overview=SimpleNamespace(facts=[])),
    )


def test_bootstrap_with_sections_parameter(monkeypatch):
    """Test that sections parameter filters which data is loaded."""
    monkeypatch.setattr(shared_hot_response_cache, "_redis", None)
    monkeypatch.setattr(shared_hot_response_cache, "_redis_async", None)
    monkeypatch.setattr(shared_hot_response_cache, "_redis_configured", False)
    shared_hot_response_cache.clear_sync()
    
    snapshot = _snapshot()
    _patch_main_and_shared(monkeypatch, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    _patch_main_and_shared(monkeypatch, "_build_company_financials_response", lambda *_args, **_kwargs: _financials_payload(snapshot))
    _patch_main_and_shared(monkeypatch, "_build_company_research_brief_response", lambda *_args, **_kwargs: _brief_payload(snapshot))
    
    client = TestClient(app)
    
    # Test requesting only company_summary section
    response = client.get("/api/companies/AAPL/workspace-bootstrap?sections=company_summary")
    
    assert response.status_code == 200
    payload = response.json()
    assert payload["company"]["ticker"] == "AAPL"
    # The sections should be resolved to the full list based on company_summary
    assert len(payload["requested_sections"]) > 0


def test_bootstrap_compact_mode_reduces_payload(monkeypatch):
    """Test that compact mode suppresses large facts arrays."""
    monkeypatch.setattr(shared_hot_response_cache, "_redis", None)
    monkeypatch.setattr(shared_hot_response_cache, "_redis_async", None)
    monkeypatch.setattr(shared_hot_response_cache, "_redis_configured", False)
    shared_hot_response_cache.clear_sync()
    
    snapshot = _snapshot()
    
    def _build_brief_with_facts(*_args, **_kwargs):
        brief = _brief_payload(snapshot)
        # Add large facts arrays
        brief.what_changed.activity_overview.facts = [{"text": "Large facts array"}] * 100
        brief.what_changed.changes.facts = [{"text": "More facts"}] * 50
        brief.capital_and_risk.governance_summary.facts = [{"text": "Gov facts"}] * 30
        brief.capital_and_risk.ownership_summary.facts = [{"text": "Ownership facts"}] * 40
        brief.monitor.activity_overview.facts = [{"text": "Monitor facts"}] * 20
        brief.stale_summary_cards = [{"key": "stale1", "title": "Stale", "value": "data"}]
        return brief
    
    _patch_main_and_shared(monkeypatch, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    _patch_main_and_shared(monkeypatch, "_build_company_financials_response", lambda *_args, **_kwargs: _financials_payload(snapshot))
    _patch_main_and_shared(monkeypatch, "_build_company_research_brief_response", _build_brief_with_facts)
    
    client = TestClient(app)
    
    # Test with compact mode enabled
    response_compact = client.get("/api/companies/AAPL/workspace-bootstrap?include_overview_brief=true&compact=true")
    assert response_compact.status_code == 200
    payload_compact = response_compact.json()
    
    # Compact mode should have is_compact=true
    assert payload_compact["is_compact"] is True
    
    # Facts arrays should be empty in compact mode
    if payload_compact.get("brief"):
        if payload_compact["brief"].get("what_changed"):
            assert payload_compact["brief"]["what_changed"]["activity_overview"]["facts"] == []
            assert payload_compact["brief"]["what_changed"]["changes"]["facts"] == []


def test_bootstrap_source_freshness_payload(monkeypatch):
    """Test that source_freshness payload is populated."""
    monkeypatch.setattr(shared_hot_response_cache, "_redis", None)
    monkeypatch.setattr(shared_hot_response_cache, "_redis_async", None)
    monkeypatch.setattr(shared_hot_response_cache, "_redis_configured", False)
    shared_hot_response_cache.clear_sync()
    
    snapshot = _snapshot()
    _patch_main_and_shared(monkeypatch, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    _patch_main_and_shared(monkeypatch, "_build_company_financials_response", lambda *_args, **_kwargs: _financials_payload(snapshot))
    _patch_main_and_shared(monkeypatch, "_build_company_research_brief_response", lambda *_args, **_kwargs: _brief_payload(snapshot))
    
    client = TestClient(app)
    
    response = client.get("/api/companies/AAPL/workspace-bootstrap?include_overview_brief=true")
    assert response.status_code == 200
    payload = response.json()
    
    # Check source_freshness
    assert "source_freshness" in payload
    freshness = payload["source_freshness"]
    assert "financials_stale" in freshness
    assert "brief_stale" in freshness
    assert "ownership_stale" in freshness


def test_bootstrap_warnings_payload(monkeypatch):
    """Test that warnings are populated when appropriate."""
    monkeypatch.setattr(shared_hot_response_cache, "_redis", None)
    monkeypatch.setattr(shared_hot_response_cache, "_redis_async", None)
    monkeypatch.setattr(shared_hot_response_cache, "_redis_configured", False)
    shared_hot_response_cache.clear_sync()
    
    snapshot = _snapshot()
    
    def _build_brief_with_issues(*_args, **_kwargs):
        brief = _brief_payload(snapshot)
        brief.build_state = "partial"
        brief.build_status = "Research brief partially complete"
        brief.stale_summary_cards = [{"key": "stale1", "title": "Stale Data", "value": "Old"}]
        return brief
    
    def _build_financials_empty(*_args, **_kwargs):
        payload = _financials_payload(snapshot)
        payload.latest_statements = []  # Empty to trigger warning
        return payload
    
    _patch_main_and_shared(monkeypatch, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    _patch_main_and_shared(monkeypatch, "_build_company_financials_response", _build_financials_empty)
    _patch_main_and_shared(monkeypatch, "_build_company_research_brief_response", _build_brief_with_issues)
    
    client = TestClient(app)
    
    response = client.get("/api/companies/AAPL/workspace-bootstrap?include_overview_brief=true")
    assert response.status_code == 200
    payload = response.json()
    
    # Check warnings
    assert "warnings" in payload
    warnings = payload["warnings"]
    
    # Should have warnings for partial brief and missing financial statements
    warning_codes = {w["code"] for w in warnings}
    assert "brief_partial" in warning_codes or "no_financial_statements" in warning_codes


def test_bootstrap_backward_compatibility_with_legacy_flags(monkeypatch):
    """Test that legacy include_* flags still work."""
    monkeypatch.setattr(shared_hot_response_cache, "_redis", None)
    monkeypatch.setattr(shared_hot_response_cache, "_redis_async", None)
    monkeypatch.setattr(shared_hot_response_cache, "_redis_configured", False)
    shared_hot_response_cache.clear_sync()
    
    snapshot = _snapshot()
    _patch_main_and_shared(monkeypatch, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    _patch_main_and_shared(monkeypatch, "_build_company_financials_response", lambda *_args, **_kwargs: _financials_payload(snapshot))
    _patch_main_and_shared(monkeypatch, "_build_company_research_brief_response", lambda *_args, **_kwargs: _brief_payload(snapshot))
    
    client = TestClient(app)
    
    # Test with legacy flags
    response = client.get("/api/companies/AAPL/workspace-bootstrap?include_overview_brief=true")
    assert response.status_code == 200
    payload = response.json()
    
    # Should have brief data
    assert payload["brief"] is not None

    _patch_main_and_shared(monkeypatch, "_normalize_ticker", lambda ticker: ticker.upper())


def test_bootstrap_with_sections_parameter(monkeypatch):
    """Test that sections parameter filters which data is loaded."""
    _install_common_overrides(monkeypatch, {})
    snapshot = _snapshot()
    
    # Track which sections were requested
    requested_sections = []
    original_build_brief = _shared_handlers._build_company_research_brief_response
    
    def _track_brief_build(*_args, **_kwargs):
        requested_sections.append("brief")
        return SimpleNamespace(
            company=_company_payload(snapshot),
            schema_version="v1",
            generated_at=datetime.now(timezone.utc),
            as_of=None,
            refresh=RefreshState(triggered=False),
            build_state="ready",
            build_status="Ready",
            available_sections=[],
            section_statuses=[],
            filing_timeline=[],
            stale_summary_cards=[],
            snapshot=SimpleNamespace(summary=SimpleNamespace()),
            what_changed=SimpleNamespace(
                activity_overview=SimpleNamespace(facts=[]),
                changes=SimpleNamespace(facts=[]),
                earnings_summary=SimpleNamespace(),
            ),
            business_quality=SimpleNamespace(summary=SimpleNamespace()),
            capital_and_risk=SimpleNamespace(
                capital_structure=SimpleNamespace(),
                capital_markets_summary=SimpleNamespace(),
                governance_summary=SimpleNamespace(facts=[]),
                ownership_summary=SimpleNamespace(facts=[]),
                equity_claim_risk_summary=SimpleNamespace(),
            ),
            valuation=SimpleNamespace(models=SimpleNamespace(), peers=SimpleNamespace()),
            monitor=SimpleNamespace(activity_overview=SimpleNamespace(facts=[])),
        )
    
    def _track_financials_build(*_args, **_kwargs):
        requested_sections.append("financials")
        return SimpleNamespace(
            company=_company_payload(snapshot),
            ticker="AAPL",
            latest_statements=[],
            statements={},
            price_history=[],
            refresh=RefreshState(triggered=False),
        )
    
    _patch_main_and_shared(monkeypatch, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    _patch_main_and_shared(monkeypatch, "_build_company_research_brief_response", _track_brief_build)
    _patch_main_and_shared(monkeypatch, "_build_company_financials_response", _track_financials_build)
    
    client = TestClient(app)
    
    # Test requesting only company_summary section
    requested_sections.clear()
    response = client.get("/api/companies/AAPL/workspace-bootstrap?sections=company_summary")
    
    assert response.status_code == 200
    payload = response.json()
    assert payload["company"]["ticker"] == "AAPL"
    assert payload["requested_sections"] == ["company_summary", "recent_filings", "recent_events"]


def test_bootstrap_compact_mode_reduces_payload(monkeypatch):
    """Test that compact mode suppresses large facts arrays."""
    _install_common_overrides(monkeypatch, {})
    snapshot = _snapshot()
    
    def _build_brief_with_facts(*_args, **_kwargs):
        return SimpleNamespace(
            company=_company_payload(snapshot),
            schema_version="v1",
            generated_at=datetime.now(timezone.utc),
            as_of=None,
            refresh=RefreshState(triggered=False),
            build_state="ready",
            build_status="Ready",
            available_sections=[],
            section_statuses=[],
            filing_timeline=[{"form": "10-K", "period_end": "2025-09-30"}],
            stale_summary_cards=[{"key": "test", "title": "Test", "value": "123"}],
            snapshot=SimpleNamespace(summary=SimpleNamespace()),
            what_changed=SimpleNamespace(
                activity_overview=SimpleNamespace(facts=[{"text": "Large facts array"}] * 100),
                changes=SimpleNamespace(facts=[{"text": "More facts"}] * 50),
                earnings_summary=SimpleNamespace(),
            ),
            business_quality=SimpleNamespace(summary=SimpleNamespace()),
            capital_and_risk=SimpleNamespace(
                capital_structure=SimpleNamespace(),
                capital_markets_summary=SimpleNamespace(),
                governance_summary=SimpleNamespace(facts=[{"text": "Gov facts"}] * 30),
                ownership_summary=SimpleNamespace(facts=[{"text": "Ownership facts"}] * 40),
                equity_claim_risk_summary=SimpleNamespace(),
            ),
            valuation=SimpleNamespace(models=SimpleNamespace(), peers=SimpleNamespace()),
            monitor=SimpleNamespace(activity_overview=SimpleNamespace(facts=[{"text": "Monitor facts"}] * 20)),
        )
    
    def _build_financials(*_args, **_kwargs):
        return SimpleNamespace(
            company=_company_payload(snapshot),
            ticker="AAPL",
            latest_statements=[],
            statements={},
            price_history=[],
            refresh=RefreshState(triggered=False),
        )
    
    _patch_main_and_shared(monkeypatch, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    _patch_main_and_shared(monkeypatch, "_build_company_research_brief_response", _build_brief_with_facts)
    _patch_main_and_shared(monkeypatch, "_build_company_financials_response", _build_financials)
    
    client = TestClient(app)
    
    # Test with compact mode enabled
    response_compact = client.get("/api/companies/AAPL/workspace-bootstrap?include_overview_brief=true&compact=true")
    assert response_compact.status_code == 200
    payload_compact = response_compact.json()
    
    # Compact mode should have is_compact=true
    assert payload_compact["is_compact"] is True
    
    # Facts arrays should be empty in compact mode
    if payload_compact.get("brief"):
        if payload_compact["brief"].get("what_changed"):
            assert payload_compact["brief"]["what_changed"]["activity_overview"]["facts"] == []
            assert payload_compact["brief"]["what_changed"]["changes"]["facts"] == []
        if payload_compact["brief"].get("capital_and_risk"):
            assert payload_compact["brief"]["capital_and_risk"]["governance_summary"]["facts"] == []
            assert payload_compact["brief"]["capital_and_risk"]["ownership_summary"]["facts"] == []


def test_bootstrap_source_freshness_payload(monkeypatch):
    """Test that source_freshness payload is populated."""
    _install_common_overrides(monkeypatch, {})
    snapshot = _snapshot()
    
    def _build_brief(*_args, **_kwargs):
        return SimpleNamespace(
            company=_company_payload(snapshot),
            schema_version="v1",
            generated_at=datetime.now(timezone.utc),
            as_of=None,
            refresh=RefreshState(triggered=False, reason="fresh"),
            build_state="ready",
            build_status="Ready",
            available_sections=[],
            section_statuses=[],
            filing_timeline=[],
            stale_summary_cards=[],
            snapshot=SimpleNamespace(summary=SimpleNamespace()),
            what_changed=SimpleNamespace(
                activity_overview=SimpleNamespace(facts=[]),
                changes=SimpleNamespace(facts=[]),
                earnings_summary=SimpleNamespace(),
            ),
            business_quality=SimpleNamespace(summary=SimpleNamespace()),
            capital_and_risk=SimpleNamespace(
                capital_structure=SimpleNamespace(),
                capital_markets_summary=SimpleNamespace(),
                governance_summary=SimpleNamespace(facts=[]),
                ownership_summary=SimpleNamespace(facts=[], refresh=RefreshState(triggered=True, reason="stale")),
                equity_claim_risk_summary=SimpleNamespace(),
            ),
            valuation=SimpleNamespace(models=SimpleNamespace(), peers=SimpleNamespace()),
            monitor=SimpleNamespace(activity_overview=SimpleNamespace(facts=[])),
        )
    
    def _build_financials(*_args, **_kwargs):
        return SimpleNamespace(
            company=_company_payload(snapshot),
            ticker="AAPL",
            latest_statements=[],
            statements={},
            price_history=[],
            refresh=RefreshState(triggered=False, reason="fresh"),
        )
    
    _patch_main_and_shared(monkeypatch, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    _patch_main_and_shared(monkeypatch, "_build_company_research_brief_response", _build_brief)
    _patch_main_and_shared(monkeypatch, "_build_company_financials_response", _build_financials)
    
    client = TestClient(app)
    
    response = client.get("/api/companies/AAPL/workspace-bootstrap?include_overview_brief=true")
    assert response.status_code == 200
    payload = response.json()
    
    # Check source_freshness
    assert "source_freshness" in payload
    freshness = payload["source_freshness"]
    assert "financials_stale" in freshness
    assert "brief_stale" in freshness
    assert "ownership_stale" in freshness
    
    # Ownership should be marked stale
    assert freshness["ownership_stale"] is True


def test_bootstrap_warnings_payload(monkeypatch):
    """Test that warnings are populated when appropriate."""
    _install_common_overrides(monkeypatch, {})
    snapshot = _snapshot()
    
    def _build_brief_with_issues(*_args, **_kwargs):
        return SimpleNamespace(
            company=_company_payload(snapshot),
            schema_version="v1",
            generated_at=datetime.now(timezone.utc),
            as_of=None,
            refresh=RefreshState(triggered=False),
            build_state="partial",
            build_status="Research brief partially complete",
            available_sections=[],
            section_statuses=[],
            filing_timeline=[],
            stale_summary_cards=[
                {"key": "stale1", "title": "Stale Data", "value": "Old"}
            ],
            snapshot=SimpleNamespace(summary=SimpleNamespace()),
            what_changed=SimpleNamespace(
                activity_overview=SimpleNamespace(facts=[]),
                changes=SimpleNamespace(facts=[]),
                earnings_summary=SimpleNamespace(),
            ),
            business_quality=SimpleNamespace(summary=SimpleNamespace()),
            capital_and_risk=SimpleNamespace(
                capital_structure=SimpleNamespace(),
                capital_markets_summary=SimpleNamespace(),
                governance_summary=SimpleNamespace(facts=[]),
                ownership_summary=SimpleNamespace(facts=[]),
                equity_claim_risk_summary=SimpleNamespace(),
            ),
            valuation=SimpleNamespace(models=SimpleNamespace(), peers=SimpleNamespace()),
            monitor=SimpleNamespace(activity_overview=SimpleNamespace(facts=[])),
        )
    
    def _build_financials(*_args, **_kwargs):
        return SimpleNamespace(
            company=_company_payload(snapshot),
            ticker="AAPL",
            latest_statements=[],  # Empty to trigger warning
            statements={},
            price_history=[],
            refresh=RefreshState(triggered=False),
        )
    
    _patch_main_and_shared(monkeypatch, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    _patch_main_and_shared(monkeypatch, "_build_company_research_brief_response", _build_brief_with_issues)
    _patch_main_and_shared(monkeypatch, "_build_company_financials_response", _build_financials)
    
    client = TestClient(app)
    
    response = client.get("/api/companies/AAPL/workspace-bootstrap?include_overview_brief=true")
    assert response.status_code == 200
    payload = response.json()
    
    # Check warnings
    assert "warnings" in payload
    warnings = payload["warnings"]
    
    # Should have warnings for partial brief and missing financial statements
    warning_codes = {w["code"] for w in warnings}
    assert "brief_partial" in warning_codes
    assert "no_financial_statements" in warning_codes
    
    # Check warning severity
    for warning in warnings:
        if warning["code"] == "brief_partial":
            assert warning["severity"] in ["warning", "info"]
        if warning["code"] == "no_financial_statements":
            assert warning["severity"] == "warning"


def test_bootstrap_backward_compatibility_with_legacy_flags(monkeypatch):
    """Test that legacy include_* flags still work."""
    _install_common_overrides(monkeypatch, {})
    snapshot = _snapshot()
    
    def _build_brief(*_args, **_kwargs):
        return SimpleNamespace(
            company=_company_payload(snapshot),
            schema_version="v1",
            generated_at=datetime.now(timezone.utc),
            as_of=None,
            refresh=RefreshState(triggered=False),
            build_state="ready",
            build_status="Ready",
            available_sections=[],
            section_statuses=[],
            filing_timeline=[],
            stale_summary_cards=[],
            snapshot=SimpleNamespace(summary=SimpleNamespace()),
            what_changed=SimpleNamespace(
                activity_overview=SimpleNamespace(facts=[]),
                changes=SimpleNamespace(facts=[]),
                earnings_summary=SimpleNamespace(),
            ),
            business_quality=SimpleNamespace(summary=SimpleNamespace()),
            capital_and_risk=SimpleNamespace(
                capital_structure=SimpleNamespace(),
                capital_markets_summary=SimpleNamespace(),
                governance_summary=SimpleNamespace(facts=[]),
                ownership_summary=SimpleNamespace(facts=[]),
                equity_claim_risk_summary=SimpleNamespace(),
            ),
            valuation=SimpleNamespace(models=SimpleNamespace(), peers=SimpleNamespace()),
            monitor=SimpleNamespace(activity_overview=SimpleNamespace(facts=[])),
        )
    
    def _build_financials(*_args, **_kwargs):
        return SimpleNamespace(
            company=_company_payload(snapshot),
            ticker="AAPL",
            latest_statements=[],
            statements={},
            price_history=[],
            refresh=RefreshState(triggered=False),
        )
    
    def _build_earnings(*_args, **_kwargs):
        return SimpleNamespace(earnings_summary=[], refresh=RefreshState(triggered=False))
    
    _patch_main_and_shared(monkeypatch, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    _patch_main_and_shared(monkeypatch, "_build_company_research_brief_response", _build_brief)
    _patch_main_and_shared(monkeypatch, "_build_company_financials_response", _build_financials)
    _patch_main_and_shared(monkeypatch, "company_earnings_summary", lambda *_args, **_kwargs: _build_earnings())
    
    client = TestClient(app)
    
    # Test with legacy flags
    response = client.get("/api/companies/AAPL/workspace-bootstrap?include_overview_brief=true&include_earnings_summary=true")
    assert response.status_code == 200
    payload = response.json()
    
    # Should have brief and earnings data
    assert payload["brief"] is not None
    assert payload["earnings_summary"] is not None
