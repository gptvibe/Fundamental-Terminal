from __future__ import annotations

from datetime import datetime, timezone

from app.contracts.common import CompanyPayload, DataQualityDiagnosticsPayload, RefreshState
from app.contracts.company_charts import (
    CompanyChartsAssumptionItemPayload,
    CompanyChartsAssumptionsCardPayload,
    CompanyChartsCardPayload,
    CompanyChartsCardsPayload,
    CompanyChartsComparisonCardPayload,
    CompanyChartsDashboardResponse,
    CompanyChartsLegendItemPayload,
    CompanyChartsLegendPayload,
    CompanyChartsMethodologyPayload,
    CompanyChartsProjectionStudioPayload,
    CompanyChartsSeriesPayload,
    CompanyChartsSeriesPointPayload,
    CompanyChartsSummaryPayload,
    CompanyChartsWhatIfPayload,
)
from app.services.company_charts_spec import (
    CHART_SPEC_SCHEMA_VERSION,
    build_company_charts_spec,
    deserialize_company_charts_spec,
    serialize_company_charts_spec,
)


def _metric_card(key: str, title: str) -> CompanyChartsCardPayload:
    return CompanyChartsCardPayload(
        key=key,
        title=title,
        series=[
            CompanyChartsSeriesPayload(
                key=f"{key}_actual",
                label="Reported",
                unit="usd",
                chart_type="line",
                series_kind="actual",
                stroke_style="solid",
                points=[
                    CompanyChartsSeriesPointPayload(
                        period_label="FY2025",
                        fiscal_year=2025,
                        period_end=datetime(2025, 12, 31, tzinfo=timezone.utc).date(),
                        value=100.0,
                        series_kind="actual",
                    )
                ],
            )
        ],
    )


def _response() -> CompanyChartsDashboardResponse:
    return CompanyChartsDashboardResponse(
        company=CompanyPayload(
            ticker="ACME",
            cik="0000001",
            name="Acme Corp",
            sector="Technology",
            market_sector="Technology",
            market_industry="Software",
            strict_official_mode=True,
            cache_state="fresh",
        ),
        title="Growth Outlook",
        build_state="ready",
        build_status="Charts dashboard ready.",
        summary=CompanyChartsSummaryPayload(
            headline="Growth Outlook",
            thesis="Reported and projected values stay distinct.",
            source_badges=["Official filings"],
        ),
        legend=CompanyChartsLegendPayload(
            title="Actual vs Forecast",
            items=[
                CompanyChartsLegendItemPayload(key="actual", label="Reported", style="solid", tone="actual"),
                CompanyChartsLegendItemPayload(key="forecast", label="Forecast", style="dashed", tone="forecast"),
            ],
        ),
        cards=CompanyChartsCardsPayload(
            revenue=_metric_card("revenue", "Revenue"),
            revenue_growth=_metric_card("revenue_growth", "Revenue Growth"),
            profit_metric=_metric_card("profit_metric", "Profit Metrics"),
            cash_flow_metric=_metric_card("cash_flow_metric", "Cash Flow Metrics"),
            eps=_metric_card("eps", "EPS"),
            growth_summary=CompanyChartsComparisonCardPayload(),
            forecast_assumptions=CompanyChartsAssumptionsCardPayload(
                items=[CompanyChartsAssumptionItemPayload(key="method", label="Method", value="Driver-based")]
            ),
            forecast_calculations=CompanyChartsAssumptionsCardPayload(
                key="forecast_calculations",
                title="Forecast Calculations",
                items=[CompanyChartsAssumptionItemPayload(key="formula", label="Formula", value="Prior x (1 + growth)")]
            ),
            revenue_outlook_bridge=_metric_card("revenue_outlook_bridge", "Revenue Outlook Bridge"),
            margin_path=_metric_card("margin_path", "Margin Path"),
            fcf_outlook=_metric_card("fcf_outlook", "FCF Outlook"),
        ),
        forecast_methodology=CompanyChartsMethodologyPayload(
            version="company_charts_dashboard_v9",
            label="Driver-based integrated forecast",
            summary="Forecasts are generated from official inputs.",
            disclaimer="Forecast values are projections.",
            confidence_label="Forecast stability: Moderate stability",
        ),
        projection_studio=CompanyChartsProjectionStudioPayload(),
        what_if=CompanyChartsWhatIfPayload(),
        payload_version="company_charts_dashboard_v9",
        refresh=RefreshState(triggered=False, reason="fresh", ticker="ACME", job_id=None),
        diagnostics=DataQualityDiagnosticsPayload(),
        provenance=[],
        as_of="2026-04-23",
        last_refreshed_at=datetime(2026, 4, 23, tzinfo=timezone.utc),
        confidence_flags=[],
    )


def test_dashboard_response_populates_chart_spec() -> None:
    response = _response()

    assert response.chart_spec is not None
    assert response.chart_spec.schema_version == CHART_SPEC_SCHEMA_VERSION
    assert response.chart_spec.available_modes == ["outlook", "studio"]
    assert response.chart_spec.outlook.primary_card_order == [
        "revenue",
        "revenue_growth",
        "profit_metric",
        "cash_flow_metric",
        "eps",
    ]
    assert response.chart_spec.outlook.secondary_card_order == [
        "revenue_outlook_bridge",
        "margin_path",
        "fcf_outlook",
    ]
    assert response.chart_spec.outlook.detail_card_order == [
        "forecast_assumptions",
        "forecast_calculations",
    ]
    assert response.chart_spec.studio is not None


def test_chart_spec_serializer_round_trips() -> None:
    response = _response()
    spec = build_company_charts_spec(response)
    serialized = serialize_company_charts_spec(spec)
    round_trip = deserialize_company_charts_spec(serialized)

    assert round_trip == spec
