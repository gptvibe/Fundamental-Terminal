from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import BackgroundTasks

import app.main as main_module


def test_company_charts_returns_bootstrap_payload_for_uncached_ticker_when_inline_refresh_is_unavailable(monkeypatch):
    monkeypatch.setattr(main_module, "_resolve_cached_company_snapshot", lambda session, ticker: None)
    monkeypatch.setattr(
        main_module,
        "_trigger_refresh",
        lambda background_tasks, ticker, reason: main_module.RefreshState(
            triggered=True,
            reason=reason,
            ticker=ticker,
            job_id="job-charts-bootstrap",
        ),
    )

    response = main_module.company_charts("acme", BackgroundTasks(), as_of=None, session=object())

    assert response.build_state == "building"
    assert response.build_status == "No persisted company snapshot is available yet. A refresh has been queued to build the first charts dashboard."
    assert response.company is None
    assert response.summary.primary_score.label == "Growth"
    assert response.legend.items[0].label == "Reported"
    assert response.cards.revenue.empty_state is not None


def test_company_charts_queues_refresh_for_uncached_ticker_instead_of_refreshing_inline(monkeypatch):
    trigger_calls: list[tuple[str, str]] = []

    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda session, ticker: None)
    monkeypatch.setattr(
        main_module,
        "_trigger_refresh",
        lambda background_tasks, ticker, reason: (
            trigger_calls.append((ticker, reason))
            or main_module.RefreshState(triggered=True, reason=reason, ticker=ticker, job_id="job-charts-missing")
        ),
    )

    response = main_module.company_charts("ACME", BackgroundTasks(), as_of=None, session=object())

    assert response.build_state == "building"
    assert response.build_status == "No persisted company snapshot is available yet. A refresh has been queued to build the first charts dashboard."
    assert response.refresh.triggered is True
    assert response.refresh.job_id == "job-charts-missing"
    assert trigger_calls == [("ACME", "missing")]


def test_company_charts_returns_persisted_payload_when_snapshot_exists(monkeypatch):
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
        last_checked=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )
    refresh = main_module.RefreshState(triggered=False, reason="fresh", ticker="ACME", job_id=None)
    persisted_payload = main_module.CompanyChartsDashboardResponse(
        company=main_module._serialize_company(snapshot),
        title="Growth Outlook",
        build_state="ready",
        build_status="Charts dashboard ready.",
        summary=main_module.CompanyChartsSummaryPayload(
            headline="Growth Outlook",
            primary_score=main_module.CompanyChartsScoreBadgePayload(key="growth", label="Growth", score=91, tone="positive"),
            secondary_badges=[
                main_module.CompanyChartsScoreBadgePayload(key="quality", label="Quality", score=88, tone="positive"),
            ],
            thesis="Revenue and cash generation have compounded cleanly through the latest reported period.",
        ),
        factors=main_module.CompanyChartsFactorsPayload(
            primary=main_module.CompanyChartsFactorValuePayload(key="growth", label="Growth", score=91, normalized_score=0.91, tone="positive"),
            supporting=[
                main_module.CompanyChartsFactorValuePayload(key="quality", label="Quality", score=88, normalized_score=0.88, tone="positive"),
            ],
        ),
        legend=main_module.CompanyChartsLegendPayload(
            items=[
                main_module.CompanyChartsLegendItemPayload(key="actual", label="Reported", style="solid", tone="actual"),
                main_module.CompanyChartsLegendItemPayload(key="forecast", label="Forecast", style="dashed", tone="forecast"),
            ]
        ),
        cards=main_module.CompanyChartsCardsPayload(
            revenue=main_module.CompanyChartsCardPayload(
                key="revenue",
                title="Revenue",
                series=[
                    main_module.CompanyChartsSeriesPayload(
                        key="revenue_actual",
                        label="Revenue",
                        unit="usd",
                        chart_type="line",
                        series_kind="actual",
                        points=[
                            main_module.CompanyChartsSeriesPointPayload(
                                period_label="FY2025",
                                fiscal_year=2025,
                                value=6200,
                                series_kind="actual",
                            )
                        ],
                    )
                ],
            )
        ),
        forecast_methodology=main_module.CompanyChartsMethodologyPayload(
            version="company_charts_dashboard_v9",
            label="Deterministic projection with empirical stability overlay",
            summary="Forecasts extend reported trends with guarded assumptions.",
            disclaimer="Forecast values are projections and not reported results.",
        ),
        payload_version="company_charts_dashboard_v9",
        refresh=refresh,
        diagnostics=main_module._build_data_quality_diagnostics(),
        **main_module._empty_provenance_contract(),
    )

    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda session, ticker: snapshot)
    monkeypatch.setattr(main_module, "_snapshot_last_checked_is_fresh", lambda stored_snapshot: True)
    monkeypatch.setattr(
        main_module,
        "get_company_charts_dashboard_snapshot",
        lambda *args, **kwargs: SimpleNamespace(
            payload=persisted_payload.model_dump(mode="json"),
            last_checked=datetime(2026, 4, 11, tzinfo=timezone.utc),
        ),
    )

    response = main_module.company_charts("ACME", BackgroundTasks(), as_of=None, session=object())

    assert response.build_state == "ready"
    assert response.build_status == "Charts dashboard ready."
    assert response.company is not None
    assert response.company.ticker == "ACME"
    assert response.summary.primary_score.score == 91
    assert response.cards.revenue.series[0].points[0].series_kind == "actual"
    assert response.legend.items[1].label == "Forecast"


def test_company_charts_builds_inline_when_snapshot_missing(monkeypatch):
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
        last_checked=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )
    refresh = main_module.RefreshState(triggered=False, reason="fresh", ticker="ACME", job_id=None)
    generated_payload = main_module.CompanyChartsDashboardResponse(
        company=main_module._serialize_company(snapshot),
        title="Growth Outlook",
        build_state="ready",
        build_status="Charts dashboard ready.",
        summary=main_module.CompanyChartsSummaryPayload(
            headline="Growth Outlook",
            primary_score=main_module.CompanyChartsScoreBadgePayload(key="growth", label="Growth", score=84, tone="positive"),
            thesis="Inline compute produced the first persisted dashboard payload.",
        ),
        factors=main_module.CompanyChartsFactorsPayload(),
        legend=main_module.CompanyChartsLegendPayload(
            items=[
                main_module.CompanyChartsLegendItemPayload(key="actual", label="Reported", style="solid", tone="actual"),
                main_module.CompanyChartsLegendItemPayload(key="forecast", label="Forecast", style="dashed", tone="forecast"),
            ]
        ),
        cards=main_module.CompanyChartsCardsPayload(),
        forecast_methodology=main_module.CompanyChartsMethodologyPayload(
            version="company_charts_dashboard_v9",
            label="Deterministic projection with empirical stability overlay",
            summary="Inline compute",
            disclaimer="Forecast values are projections.",
        ),
        payload_version="company_charts_dashboard_v9",
        refresh=refresh,
        diagnostics=main_module._build_data_quality_diagnostics(),
        **main_module._empty_provenance_contract(),
    )

    class _Session:
        def __init__(self) -> None:
            self.commits = 0

        def commit(self) -> None:
            self.commits += 1

        def execute(self, *_args, **_kwargs):
            return None

    session = _Session()

    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda session, ticker: snapshot)
    monkeypatch.setattr(main_module, "get_company_charts_dashboard_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "recompute_and_persist_company_charts_dashboard", lambda *args, **kwargs: generated_payload)

    response = main_module.company_charts("ACME", BackgroundTasks(), as_of=None, session=session)

    assert response.build_state == "ready"
    assert response.summary.primary_score.score == 84
    assert session.commits == 1


def test_company_charts_rebuilds_when_persisted_snapshot_uses_legacy_hash_payload_version(monkeypatch):
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
        last_checked=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )
    refresh = main_module.RefreshState(triggered=False, reason="fresh", ticker="ACME", job_id=None)
    legacy_payload = main_module.CompanyChartsDashboardResponse(
        company=main_module._serialize_company(snapshot),
        title="Growth Outlook",
        build_state="ready",
        build_status="Charts dashboard ready.",
        summary=main_module.CompanyChartsSummaryPayload(
            headline="Growth Outlook",
            primary_score=main_module.CompanyChartsScoreBadgePayload(key="growth", label="Growth", score=50, tone="neutral"),
        ),
        factors=main_module.CompanyChartsFactorsPayload(),
        legend=main_module.CompanyChartsLegendPayload(),
        cards=main_module.CompanyChartsCardsPayload(),
        forecast_methodology=main_module.CompanyChartsMethodologyPayload(
            version="company_charts_dashboard_v9",
            label="Legacy",
            summary="Legacy",
            disclaimer="Legacy",
        ),
        payload_version="d88d8b0baa706eae51b75c79be97afda",
        refresh=refresh,
        diagnostics=main_module._build_data_quality_diagnostics(),
        **main_module._empty_provenance_contract(),
    )
    rebuilt_payload = main_module.CompanyChartsDashboardResponse.model_validate(
        {
            **main_module._empty_provenance_contract(),
            "company": main_module._serialize_company(snapshot).model_dump(mode="json"),
            "title": "Growth Outlook",
            "build_state": "ready",
            "build_status": "Charts dashboard ready.",
            "summary": {
                "headline": "Growth Outlook",
                "primary_score": {"key": "growth", "label": "Growth", "score": 84, "tone": "positive"},
                "thesis": "Inline compute replaced the legacy payload.",
            },
            "factors": {},
            "legend": {},
            "cards": {},
            "forecast_methodology": {
                "version": "company_charts_dashboard_v9",
                "label": "Current",
                "summary": "Current",
                "disclaimer": "Current",
            },
            "projection_studio": {
                "methodology": None,
                "schedule_sections": [],
                "drivers_used": [],
                "scenarios_comparison": [],
                "sensitivity_matrix": [],
            },
            "payload_version": "company_charts_dashboard_v9",
            "refresh": refresh.model_dump(mode="json"),
            "diagnostics": main_module._build_data_quality_diagnostics().model_dump(mode="json"),
        }
    )

    class _Session:
        def __init__(self) -> None:
            self.commits = 0

        def commit(self) -> None:
            self.commits += 1

        def execute(self, *_args, **_kwargs):
            return None

    session = _Session()

    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda session, ticker: snapshot)
    monkeypatch.setattr(
        main_module,
        "get_company_charts_dashboard_snapshot",
        lambda *args, **kwargs: SimpleNamespace(
            payload=legacy_payload.model_dump(mode="json"),
            last_checked=datetime(2026, 4, 11, tzinfo=timezone.utc),
        ),
    )
    monkeypatch.setattr(main_module, "_trigger_refresh", lambda *_args, **_kwargs: refresh)
    monkeypatch.setattr(main_module, "recompute_and_persist_company_charts_dashboard", lambda *args, **kwargs: rebuilt_payload)

    response = main_module.company_charts("ACME", BackgroundTasks(), as_of=None, session=session)

    assert response.payload_version == "company_charts_dashboard_v9"
    assert response.summary.primary_score.score == 84
    assert response.projection_studio is not None
    assert session.commits == 1


def test_company_charts_what_if_builds_stateless_response_without_db_writes(monkeypatch):
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
        last_checked=datetime(2026, 4, 10, tzinfo=timezone.utc),
    )
    refresh = main_module.RefreshState(triggered=False, reason="fresh", ticker="ACME", job_id=None)
    generated_payload = main_module.CompanyChartsDashboardResponse(
        company=main_module._serialize_company(snapshot),
        title="Growth Outlook",
        build_state="ready",
        build_status="Charts dashboard ready.",
        summary=main_module.CompanyChartsSummaryPayload(
            headline="Growth Outlook",
            primary_score=main_module.CompanyChartsScoreBadgePayload(key="growth", label="Growth", score=84, tone="positive"),
            thesis="Stateless what-if compute updated the projection view.",
        ),
        factors=main_module.CompanyChartsFactorsPayload(),
        legend=main_module.CompanyChartsLegendPayload(),
        cards=main_module.CompanyChartsCardsPayload(),
        forecast_methodology=main_module.CompanyChartsMethodologyPayload(
            version="company_charts_dashboard_v9",
            label="Driver-based integrated forecast",
            summary="What-if compute",
            disclaimer="Forecast values are projections.",
        ),
        what_if=main_module.CompanyChartsWhatIfPayload(
            impact_summary=None,
            overrides_applied=[
                main_module.CompanyChartsWhatIfOverridePayload(
                    key="dso",
                    label="Days Sales Outstanding",
                    unit="days",
                    requested_value=60.0,
                    applied_value=60.0,
                    baseline_value=55.0,
                    min_value=5.0,
                    max_value=150.0,
                    clipped=False,
                    source_detail="SEC-derived dso input",
                    source_kind="sec",
                )
            ],
            overrides_clipped=[],
            driver_control_metadata=[],
        ),
        payload_version="company_charts_dashboard_v9",
        refresh=refresh,
        diagnostics=main_module._build_data_quality_diagnostics(),
        **main_module._empty_provenance_contract(),
    )

    class _Session:
        def __init__(self) -> None:
            self.commits = 0

        def commit(self) -> None:
            self.commits += 1

        def execute(self, *_args, **_kwargs):
            return None

    session = _Session()
    observed_overrides: list[dict[str, float]] = []

    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda session, ticker: snapshot)
    monkeypatch.setattr(
        main_module,
        "build_company_charts_dashboard_response",
        lambda session, company_id, **kwargs: (
            observed_overrides.append(dict(kwargs["what_if_request"].overrides)) or generated_payload
        ),
    )

    response = main_module.company_charts_what_if(
        "ACME",
        main_module.CompanyChartsWhatIfRequest(overrides={"dso": 60.0}),
        BackgroundTasks(),
        as_of=None,
        session=session,
    )

    assert observed_overrides == [{"dso": 60.0}]
    assert response.what_if is not None
    assert response.what_if.overrides_applied[0].key == "dso"
    assert session.commits == 0
