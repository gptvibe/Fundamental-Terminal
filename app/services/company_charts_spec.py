from __future__ import annotations

from typing import Any

from app.contracts.company_charts import (
    CompanyChartsDashboardResponse,
    CompanyChartsSpecPayload,
    CompanyChartsStudioSpecPayload,
    CompanyChartsOutlookSpecPayload,
)


CHART_SPEC_SCHEMA_VERSION = "company_chart_spec_v1"
OUTLOOK_PRIMARY_CARD_ORDER = (
    "revenue",
    "revenue_growth",
    "profit_metric",
    "cash_flow_metric",
    "eps",
)
OUTLOOK_SECONDARY_CARD_ORDER = (
    "revenue_outlook_bridge",
    "margin_path",
    "fcf_outlook",
)
OUTLOOK_COMPARISON_CARD_ORDER = ("growth_summary",)
OUTLOOK_DETAIL_CARD_ORDER = ("forecast_assumptions", "forecast_calculations")
PROJECTION_STUDIO_SUMMARY = "Inspection of projected values, sensitivities, waterfall bridges, and traceable formulas."


def build_company_charts_spec(response: CompanyChartsDashboardResponse) -> CompanyChartsSpecPayload:
    cards = response.cards
    available_modes: list[str] = ["outlook"]
    studio = None
    if response.projection_studio is not None:
        available_modes.append("studio")
        studio = CompanyChartsStudioSpecPayload(
            title="Projection Studio",
            summary=PROJECTION_STUDIO_SUMMARY,
            projection_studio=response.projection_studio,
            what_if=response.what_if,
        )

    return CompanyChartsSpecPayload(
        schema_version=CHART_SPEC_SCHEMA_VERSION,
        payload_version=response.payload_version,
        company=response.company,
        build_state=response.build_state,
        build_status=response.build_status,
        refresh=response.refresh,
        diagnostics=response.diagnostics,
        provenance=response.provenance,
        as_of=response.as_of,
        last_refreshed_at=response.last_refreshed_at,
        source_mix=response.source_mix,
        confidence_flags=response.confidence_flags,
        available_modes=available_modes,
        default_mode="outlook",
        outlook=CompanyChartsOutlookSpecPayload(
            title=response.title,
            summary=response.summary,
            legend=response.legend,
            cards=cards,
            primary_card_order=_present_card_order(cards, OUTLOOK_PRIMARY_CARD_ORDER),
            secondary_card_order=_present_card_order(cards, OUTLOOK_SECONDARY_CARD_ORDER),
            comparison_card_order=_present_card_order(cards, OUTLOOK_COMPARISON_CARD_ORDER),
            detail_card_order=_present_card_order(cards, OUTLOOK_DETAIL_CARD_ORDER),
            methodology=response.forecast_methodology,
            forecast_diagnostics=response.forecast_diagnostics,
            event_overlay=response.event_overlay,
            quarter_change=response.quarter_change,
        ),
        studio=studio,
    )


def serialize_company_charts_spec(spec: CompanyChartsSpecPayload) -> dict[str, Any]:
    return spec.model_dump(mode="json")


def deserialize_company_charts_spec(payload: dict[str, Any] | CompanyChartsSpecPayload | None) -> CompanyChartsSpecPayload | None:
    if payload is None:
        return None
    if isinstance(payload, CompanyChartsSpecPayload):
        return payload
    return CompanyChartsSpecPayload.model_validate(payload)


def _present_card_order(cards: Any, order: tuple[str, ...]) -> list[str]:
    present: list[str] = []
    for key in order:
        card = getattr(cards, key, None)
        if card is not None:
            present.append(key)
    return present
