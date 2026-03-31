from __future__ import annotations

from app.api.handlers import _shared as shared_handlers
from app.api.schemas.common import CompanyPayload, DataQualityDiagnosticsPayload, RefreshState
from app.api.schemas.financials import CompanyFinancialsResponse


def test_hot_cache_skips_company_missing_payloads() -> None:
    shared_handlers._hot_response_cache.clear()

    payload = CompanyFinancialsResponse(
        company=None,
        financials=[],
        price_history=[],
        refresh=RefreshState(triggered=True, reason="missing", ticker="ON", job_id="job-on"),
        diagnostics=DataQualityDiagnosticsPayload(stale_flags=["company_missing"]),
        confidence_flags=["company_missing"],
    )

    shared_handlers._store_hot_cached_payload("financials:ON", payload)

    assert shared_handlers._get_hot_cached_payload("financials:ON") is None


def test_hot_cache_keeps_real_company_payloads() -> None:
    shared_handlers._hot_response_cache.clear()

    payload = CompanyFinancialsResponse(
        company=CompanyPayload(
            ticker="ON",
            cik="0001097864",
            name="ON SEMICONDUCTOR CORP",
            cache_state="fresh",
        ),
        financials=[],
        price_history=[],
        refresh=RefreshState(triggered=False, reason="fresh", ticker="ON", job_id=None),
        diagnostics=DataQualityDiagnosticsPayload(),
    )

    shared_handlers._store_hot_cached_payload("financials:ON", payload)

    cached = shared_handlers._get_hot_cached_payload("financials:ON")
    assert cached is not None
    assert cached[0]["company"]["ticker"] == "ON"