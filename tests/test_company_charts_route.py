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


def test_company_charts_refreshes_inline_for_uncached_ticker(monkeypatch):
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
            primary_score=main_module.CompanyChartsScoreBadgePayload(key="growth", label="Growth", score=86, tone="positive"),
            thesis="Inline refresh built the first persisted dashboard payload.",
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
            version="company_charts_dashboard_v3",
            label="Deterministic internal projection",
            summary="Inline refresh compute",
            disclaimer="Forecast values are projections.",
        ),
        payload_version="company_charts_dashboard_v3",
        refresh=refresh,
        diagnostics=main_module._build_data_quality_diagnostics(),
        **main_module._empty_provenance_contract(),
    )

    resolve_calls: list[str] = []

    def _resolve_snapshot(session, ticker):
        resolve_calls.append(ticker)
        if len(resolve_calls) == 1:
            return None
        return snapshot

    class _FakeService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def refresh_company(self, *, identifier: str, force: bool, refresh_insider_data: bool, refresh_institutional_data: bool, refresh_beneficial_ownership_data: bool):
            assert identifier == "ACME"
            assert force is False
            assert refresh_insider_data is False
            assert refresh_institutional_data is False
            assert refresh_beneficial_ownership_data is False
            self.calls.append(("refresh", identifier))
            return SimpleNamespace(status="fetched")

        def close(self) -> None:
            self.calls.append(("close", ""))

    service_instances: list[_FakeService] = []

    class _Session:
        def __init__(self) -> None:
            self.commits = 0
            self.expire_calls = 0

        def commit(self) -> None:
            self.commits += 1

        def execute(self, *_args, **_kwargs):
            return None

        def expire_all(self) -> None:
            self.expire_calls += 1

    session = _Session()

    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", _resolve_snapshot)
    monkeypatch.setattr(main_module, "get_company_charts_dashboard_snapshot", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module, "recompute_and_persist_company_charts_dashboard", lambda *args, **kwargs: generated_payload)
    monkeypatch.setattr(main_module, "_trigger_refresh", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("background refresh should not be queued")))
    monkeypatch.setattr(
        main_module,
        "EdgarIngestionService",
        lambda: service_instances.append(_FakeService()) or service_instances[-1],
    )

    response = main_module.company_charts("ACME", BackgroundTasks(), as_of=None, session=session)

    assert response.build_state == "ready"
    assert response.summary.primary_score.score == 86
    assert session.commits == 1
    assert session.expire_calls == 1
    assert resolve_calls == ["ACME", "ACME"]
    assert len(service_instances) == 1
    assert service_instances[0].calls == [("refresh", "ACME"), ("close", "")]


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
            version="company_charts_dashboard_v3",
            label="Deterministic internal projection",
            summary="Forecasts extend reported trends with guarded assumptions.",
            disclaimer="Forecast values are projections and not reported results.",
        ),
        payload_version="company_charts_dashboard_v3",
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
            version="company_charts_dashboard_v3",
            label="Deterministic internal projection",
            summary="Inline compute",
            disclaimer="Forecast values are projections.",
        ),
        payload_version="company_charts_dashboard_v3",
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
