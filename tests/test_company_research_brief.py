from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from fastapi import BackgroundTasks

import app.main as main_module
from app.services.sec_edgar import CompanyIdentity, FilingMetadata
from app.services.company_research_brief import _statement_value


def test_statement_value_supports_legacy_weighted_share_alias():
    statement = SimpleNamespace(data={"weighted_average_diluted_shares": 388900000})

    assert _statement_value(statement, "weighted_average_shares_diluted") == 388900000


def test_company_brief_returns_bootstrap_payload_for_uncached_ticker(monkeypatch):
    class FakeEdgarClient:
        def resolve_company(self, ticker: str) -> CompanyIdentity:
            assert ticker == "ACME"
            return CompanyIdentity(
                cik="0000123456",
                ticker="ACME",
                name="Acme Corp",
                sector="Technology",
                market_sector="Technology",
                market_industry="Software",
            )

        def get_submissions(self, cik: str):
            assert cik == "0000123456"
            return {"filings": "ok"}

        def build_filing_index(self, submissions):
            assert submissions == {"filings": "ok"}
            return {
                "10-k": FilingMetadata(
                    accession_number="0000123456-26-000001",
                    form="10-K",
                    filing_date=date(2026, 3, 10),
                    report_date=date(2025, 12, 31),
                    primary_doc_description="Annual report",
                )
            }

        def close(self) -> None:
            return None

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda session, ticker: None)
    monkeypatch.setattr(
        main_module,
        "_trigger_refresh",
        lambda background_tasks, ticker, reason: main_module.RefreshState(
            triggered=True,
            reason=reason,
            ticker=ticker,
            job_id="job-bootstrap",
        ),
    )
    monkeypatch.setattr(main_module, "EdgarClient", FakeEdgarClient)

    response = main_module.company_brief("acme", BackgroundTasks(), as_of=None, session=object())

    assert response.build_state == "building"
    assert response.build_status == "Resolving company records and warming the research brief."
    assert response.company is not None
    assert response.company.ticker == "ACME"
    assert response.available_sections == ["snapshot"]
    assert response.section_statuses[0].id == "snapshot"
    assert response.section_statuses[0].state == "ready"
    assert response.filing_timeline[0].form == "10-K"
    assert response.filing_timeline[0].description == "Annual report"


def test_company_brief_returns_partial_payload_when_cached_company_exists_but_brief_missing(monkeypatch):
    snapshot = SimpleNamespace(
        company=SimpleNamespace(
            id=1,
            ticker="ACME",
            cik="0000123456",
            name="Acme Corp",
            sector="Technology",
            market_sector="Technology",
            market_industry="Software",
        ),
        cache_state="fresh",
        last_checked=datetime(2026, 3, 10, tzinfo=timezone.utc),
    )
    latest_statement = SimpleNamespace(
        filing_type="10-K",
        period_end=date(2025, 12, 31),
        data={
            "revenue": 6200,
            "free_cash_flow": 1280,
            "segment_breakdown": [{"segment_name": "Core Platform", "share_of_revenue": 0.661}],
        },
    )
    filing_timeline = [
        main_module.FilingTimelineItemPayload(
            date=date(2025, 12, 31),
            form="10-K",
            description="Annual report",
            accession="0000123456-26-000001",
        )
    ]

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda session, ticker: snapshot)
    monkeypatch.setattr(
        main_module,
        "_refresh_for_snapshot",
        lambda background_tasks, cached_snapshot: main_module.RefreshState(
            triggered=False,
            reason="fresh",
            ticker=cached_snapshot.company.ticker,
            job_id=None,
        ),
    )
    monkeypatch.setattr(main_module, "get_company_research_brief_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        main_module,
        "_trigger_refresh",
        lambda background_tasks, ticker, reason: main_module.RefreshState(
            triggered=True,
            reason=reason,
            ticker=ticker,
            job_id="job-missing-brief",
        ),
    )
    monkeypatch.setattr(main_module, "_visible_financials_for_company", lambda session, company: [latest_statement])
    monkeypatch.setattr(main_module, "_visible_price_history", lambda session, company_id: [SimpleNamespace(), SimpleNamespace()])
    monkeypatch.setattr(main_module, "_load_company_brief_filing_timeline", lambda session, snapshot=None, identity=None: filing_timeline)

    response = main_module.company_brief("ACME", BackgroundTasks(), as_of=None, session=object())

    assert response.build_state == "partial"
    assert response.build_status == "Showing cached company basics while the research brief finishes building."
    assert response.company is not None
    assert response.company.ticker == "ACME"
    assert response.available_sections == ["snapshot"]
    assert response.snapshot.summary.latest_revenue == 6200
    assert response.snapshot.summary.top_segment_name == "Core Platform"
    assert response.section_statuses[1].id == "what_changed"
    assert response.section_statuses[1].state == "partial"
    assert any(card.title == "Revenue" for card in response.stale_summary_cards)