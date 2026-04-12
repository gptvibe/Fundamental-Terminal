from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

from fastapi import BackgroundTasks

import app.main as main_module
from app.services.company_research_brief import _statement_value


def test_statement_value_supports_legacy_weighted_share_alias():
    statement = SimpleNamespace(data={"weighted_average_diluted_shares": 388900000})

    assert _statement_value(statement, "weighted_average_shares_diluted") == 388900000


def test_company_brief_returns_bootstrap_payload_for_uncached_ticker(monkeypatch):
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

    response = main_module.company_brief("acme", BackgroundTasks(), as_of=None, session=object())

    assert response.build_state == "building"
    assert response.build_status == "No persisted company snapshot is available yet. A refresh has been queued to build the first brief."
    assert response.company is None
    assert response.available_sections == []
    assert response.filing_timeline == []


def test_company_brief_returns_composite_payload_when_cached_company_exists(monkeypatch):
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
    built_payload = main_module._empty_company_brief_response(
        refresh=main_module.RefreshState(triggered=False, reason="fresh", ticker="ACME", job_id=None),
        as_of=None,
    ).model_copy(
        update={
            "company": main_module._serialize_company(snapshot),
            "build_state": "ready",
            "build_status": "Research brief ready.",
        }
    )
    monkeypatch.setattr(
        main_module,
        "get_company_research_brief_snapshot",
        lambda *args, **kwargs: SimpleNamespace(payload=built_payload.model_dump(mode="json")),
    )
    monkeypatch.setattr(
        main_module,
        "_augment_company_brief_response",
        lambda session, snapshot, payload, refresh, as_of: payload.model_copy(
            update={
                "available_sections": list(main_module.RESEARCH_BRIEF_SECTION_ORDER),
                "section_statuses": main_module._build_research_brief_section_statuses(list(main_module.RESEARCH_BRIEF_SECTION_ORDER), build_state="ready"),
                "filing_timeline": filing_timeline,
                "stale_summary_cards": [
                    main_module.ResearchBriefSummaryCardPayload(
                        key="latest_revenue",
                        title="Revenue",
                        value="$6.2K",
                        detail="2025-12-31",
                    )
                ],
            }
        ),
    )

    response = main_module.company_brief("ACME", BackgroundTasks(), as_of=None, session=object())

    assert response.build_state == "ready"
    assert response.build_status == "Research brief ready."
    assert response.company is not None
    assert response.company.ticker == "ACME"
    assert response.available_sections == list(main_module.RESEARCH_BRIEF_SECTION_ORDER)
    assert response.section_statuses[1].id == "what_changed"
    assert response.section_statuses[1].state == "ready"
    assert any(card.title == "Revenue" for card in response.stale_summary_cards)


def test_company_brief_returns_stale_snapshot_and_queues_background_refresh(monkeypatch):
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
    refresh = main_module.RefreshState(triggered=False, reason="fresh", ticker="ACME", job_id=None)
    built_payload = main_module._empty_company_brief_response(refresh=refresh, as_of=None).model_copy(
        update={
            "company": main_module._serialize_company(snapshot),
            "build_state": "ready",
            "build_status": "Research brief ready.",
        }
    )

    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda session, ticker: snapshot)
    monkeypatch.setattr(
        main_module,
        "get_company_research_brief_snapshot",
        lambda *args, **kwargs: SimpleNamespace(
            payload=built_payload.model_dump(mode="json"),
            last_checked=datetime.now(timezone.utc) - timedelta(hours=main_module.settings.freshness_window_hours + 2),
        ),
    )
    monkeypatch.setattr(main_module, "queue_company_refresh", lambda *_args, **_kwargs: "job-stale")
    monkeypatch.setattr(
        main_module,
        "_augment_company_brief_response",
        lambda session, snapshot, payload, refresh, as_of: payload.model_copy(
            update={
                "refresh": refresh,
                "available_sections": list(main_module.RESEARCH_BRIEF_SECTION_ORDER),
                "section_statuses": main_module._build_research_brief_section_statuses(list(main_module.RESEARCH_BRIEF_SECTION_ORDER), build_state="ready"),
            }
        ),
    )

    response = main_module.company_brief("ACME", BackgroundTasks(), as_of=None, session=object())

    assert response.build_state == "ready"
    assert response.refresh.triggered is True
    assert response.refresh.reason == "stale"
    assert response.refresh.job_id == "job-stale"
    assert response.company is not None
    assert response.company.ticker == "ACME"


def test_company_overview_reuses_shared_snapshot_for_financials_and_brief(monkeypatch):
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
    seen_snapshots: list[tuple[str, object | None]] = []

    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda session, ticker: snapshot)

    def _build_financials(*_args, **kwargs):
        seen_snapshots.append(("financials", kwargs.get("snapshot")))
        return main_module.CompanyFinancialsResponse(
            company=main_module._serialize_company(snapshot),
            financials=[],
            price_history=[],
            refresh=main_module.RefreshState(triggered=False, reason="fresh", ticker="ACME", job_id=None),
            diagnostics=main_module._build_data_quality_diagnostics(),
            **main_module._empty_provenance_contract(),
        )

    def _build_brief(*_args, **kwargs):
        seen_snapshots.append(("brief", kwargs.get("snapshot")))
        return main_module._empty_company_brief_response(
            refresh=main_module.RefreshState(triggered=False, reason="fresh", ticker="ACME", job_id=None),
            as_of=None,
        ).model_copy(update={"company": main_module._serialize_company(snapshot)})

    monkeypatch.setattr(main_module, "_build_company_financials_response", _build_financials)
    monkeypatch.setattr(main_module, "_build_company_research_brief_response", _build_brief)

    response = main_module.company_overview("ACME", BackgroundTasks(), as_of=None, session=object())

    assert response.company is not None
    assert response.company.ticker == "ACME"
    assert response.financials.company is not None
    assert response.financials.company.ticker == "ACME"
    assert response.brief.company is not None
    assert response.brief.company.ticker == "ACME"
    assert seen_snapshots == [("financials", snapshot), ("brief", snapshot)]
