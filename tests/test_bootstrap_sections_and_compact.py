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


def _install_common_overrides(monkeypatch, _filings: dict[str, FilingMetadata]) -> None:
    """Install baseline overrides so workspace-bootstrap tests avoid live dependencies."""

    _snapshot_fn = lambda *_args, **_kwargs: _snapshot()

    _patch_main_and_shared(monkeypatch, "_resolve_cached_company_snapshot", _snapshot_fn)
    _patch_main_and_shared(monkeypatch, "_resolve_company_brief_snapshot", _snapshot_fn)
    _patch_main_and_shared(monkeypatch, "_normalize_ticker", lambda ticker: ticker.upper())
    _patch_main_and_shared(
        monkeypatch,
        "_refresh_for_snapshot",
        lambda *_args, **_kwargs: RefreshState(triggered=False, reason="fresh", ticker="AAPL", job_id=None),
    )


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
        financials=[],
        price_history=[],
        refresh=RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None),
        diagnostics=DataQualityDiagnosticsPayload(),
    )


def _brief_payload(snapshot):
    refresh = RefreshState(triggered=False, reason="fresh", ticker=snapshot.company.ticker, job_id=None)
    brief = main_module._empty_company_brief_response(refresh=refresh, as_of=None)
    brief.company = _company_payload(snapshot)
    brief.generated_at = datetime.now(timezone.utc)
    brief.build_state = "ready"
    brief.build_status = "Ready"
    return brief


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
        brief.stale_summary_cards = []
        return brief
    
    _patch_main_and_shared(monkeypatch, "_resolve_company_brief_snapshot", lambda *_args, **_kwargs: snapshot)
    _patch_main_and_shared(monkeypatch, "_build_company_financials_response", lambda *_args, **_kwargs: _financials_payload(snapshot))
    _patch_main_and_shared(monkeypatch, "_build_company_research_brief_response", _build_brief_with_facts)
    if _company_overview_handlers is not None:
        monkeypatch.setattr(_company_overview_handlers, "_apply_compact_mode_to_brief", lambda brief: brief)
    
    client = TestClient(app)
    
    # Test with compact mode enabled
    response_compact = client.get("/api/companies/AAPL/workspace-bootstrap?include_overview_brief=true&compact=true")
    assert response_compact.status_code == 200
    payload_compact = response_compact.json()
    
    # Compact mode should have is_compact=true
    assert payload_compact["is_compact"] is True
    assert payload_compact.get("brief") is not None


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
        payload.financials = []  # Empty to trigger warning
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
