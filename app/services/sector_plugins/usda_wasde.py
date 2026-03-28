from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, datetime, timezone
from html import unescape
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

from app.source_registry import SourceUsage
from app.services.sector_plugins.base import (
    SectorChart,
    SectorChartPoint,
    SectorChartSeries,
    SectorDetailView,
    SectorPluginDefinition,
    SectorPluginResult,
    SectorRefreshPolicy,
    build_detail_row,
    build_http_client,
    build_metric,
    keyword_relevance,
    parse_float,
    unavailable_plugin_result,
)

USDA_SOURCE_ID = "usda_wasde"
USDA_PAGE_URL = "https://www.usda.gov/oce/commodity/wasde"
USDA_DESCRIPTION = "Official USDA WASDE crop outlook for agriculture- and input-sensitive companies."
USDA_KEYWORDS = (
    "agriculture",
    "agricultural",
    "fertilizer",
    "seed",
    "grain",
    "crop",
    "farming",
    "farm",
    "protein",
    "livestock",
    "meat",
    "food products",
    "dairy",
)
USDA_CORN_REPORT = "U.S. Feed Grain and Corn Supply and Use  1/"
USDA_SOY_REPORT = "U.S. Soybeans and Products Supply and Use (Domestic Measure)  1/"


def _relevance(sector: str | None, market_sector: str | None, market_industry: str | None) -> list[str]:
    return keyword_relevance(
        keywords=USDA_KEYWORDS,
        sector=sector,
        market_sector=market_sector,
        market_industry=market_industry,
    )


def _discover_xml_url(page_html: str) -> str | None:
    match = re.search(r'href="([^"]*wasde\d{4}\.xml)"', page_html, flags=re.IGNORECASE)
    if match is None:
        return None
    return urljoin(USDA_PAGE_URL, match.group(1))


def _normalize_period(report_month: str | None) -> str | None:
    if not report_month:
        return None
    try:
        parsed = datetime.strptime(report_month.strip(), "%B %Y")
    except ValueError:
        return report_month.strip() or None
    return date(parsed.year, parsed.month, 1).isoformat()


def _report_by_title(root: ET.Element, title: str) -> ET.Element | None:
    for report in root.iter("Report"):
        if report.attrib.get("sub_report_title") == title:
            return report
    return None


def _extract_metric_entries(report: ET.Element) -> dict[str, list[dict[str, object]]]:
    metrics: dict[str, list[dict[str, object]]] = defaultdict(list)
    for element in report.iter():
        label_key = next(
            (
                key
                for key in element.attrib
                if key.startswith("attribute") and key != "attribute_group"
            ),
            None,
        )
        if label_key is None:
            continue
        label = unescape(str(element.attrib.get(label_key) or "")).strip()
        if not label:
            continue
        for year_group in element.iter():
            year_key = next((key for key in year_group.attrib if key.startswith("market_year")), None)
            if year_key is None:
                continue
            year_label = str(year_group.attrib.get(year_key) or "").strip()
            if not year_label:
                continue
            for month_group in year_group.iter():
                month_key = next((key for key in month_group.attrib if key.startswith("forecast_month")), None)
                if month_key is None:
                    continue
                forecast_month = str(month_group.attrib.get(month_key) or "").strip()
                cell_value = None
                for cell in month_group.iter("Cell"):
                    value_key = next((key for key in cell.attrib if key.startswith("cell_value")), None)
                    if value_key is not None:
                        cell_value = parse_float(cell.attrib.get(value_key))
                        break
                if cell_value is None:
                    continue
                metrics[label].append(
                    {
                        "year": year_label,
                        "forecast_month": forecast_month,
                        "value": cell_value,
                    }
                )
    return metrics


def _metric_by_prefix(metrics: dict[str, list[dict[str, object]]], prefix: str) -> list[dict[str, object]]:
    for label, values in metrics.items():
        if unescape(label).strip().lower().startswith(prefix.lower()):
            return values
    return []


def _latest_current_and_prior(entries: list[dict[str, object]]) -> tuple[dict[str, object], dict[str, object]]:
    if not entries:
        return {}, {}
    latest = entries[-1]
    latest_year = str(latest.get("year") or "")
    prior_same_year = next(
        (entry for entry in reversed(entries[:-1]) if str(entry.get("year") or "") == latest_year),
        {},
    )
    return latest, prior_same_year or (entries[-2] if len(entries) > 1 else {})


def _series_points(entries: list[dict[str, object]]) -> tuple[SectorChartPoint, ...]:
    by_year: dict[str, dict[str, object]] = {}
    for entry in entries:
        by_year[str(entry.get("year") or "")] = entry
    return tuple(
        SectorChartPoint(label=year_label, value=parse_float(entry.get("value")))
        for year_label, entry in by_year.items()
    )


def fetch_plugin() -> SectorPluginResult:
    with build_http_client(timeout_seconds=30.0) as client:
        page_response = client.get(USDA_PAGE_URL)
        page_response.raise_for_status()
        xml_url = _discover_xml_url(page_response.text)
        if xml_url is None:
            return unavailable_plugin_result(
                plugin_id="usda_wasde",
                title="Agriculture Outlook",
                description=USDA_DESCRIPTION,
                source_usages=(SourceUsage(source_id=USDA_SOURCE_ID, role="primary"),),
                confidence_flags=("usda_wasde_xml_missing",),
            )
        xml_response = client.get(xml_url)
        xml_response.raise_for_status()

    root = ET.fromstring(xml_response.text)
    corn_report = _report_by_title(root, USDA_CORN_REPORT)
    soy_report = _report_by_title(root, USDA_SOY_REPORT)
    if corn_report is None or soy_report is None:
        return unavailable_plugin_result(
            plugin_id="usda_wasde",
            title="Agriculture Outlook",
            description=USDA_DESCRIPTION,
            source_usages=(SourceUsage(source_id=USDA_SOURCE_ID, role="primary"),),
            confidence_flags=("usda_wasde_report_missing",),
        )

    corn_metrics = _extract_metric_entries(corn_report)
    soy_metrics = _extract_metric_entries(soy_report)
    corn_ending = _metric_by_prefix(corn_metrics, "Ending Stocks")
    corn_price = _metric_by_prefix(corn_metrics, "Avg. Farm Price")
    soy_ending = _metric_by_prefix(soy_metrics, "Ending Stocks")
    soy_price = _metric_by_prefix(soy_metrics, "Avg. Farm Price")
    latest_corn_ending, prior_corn_ending = _latest_current_and_prior(corn_ending)
    latest_corn_price, prior_corn_price = _latest_current_and_prior(corn_price)
    latest_soy_ending, prior_soy_ending = _latest_current_and_prior(soy_ending)
    latest_soy_price, prior_soy_price = _latest_current_and_prior(soy_price)
    report_month = corn_report.attrib.get("Report_Month") or soy_report.attrib.get("Report_Month")
    as_of = _normalize_period(report_month)
    refreshed_at = datetime.now(timezone.utc)

    return SectorPluginResult(
        plugin_id="usda_wasde",
        title="Agriculture Outlook",
        description=USDA_DESCRIPTION,
        status="ok",
        summary_metrics=(
            build_metric(
                metric_id="corn_ending_stocks",
                label="Corn ending stocks",
                unit="million_bushels",
                current=parse_float(latest_corn_ending.get("value")),
                previous=parse_float(prior_corn_ending.get("value")),
                as_of=as_of,
            ),
            build_metric(
                metric_id="corn_avg_farm_price",
                label="Corn avg. farm price",
                unit="usd_per_bushel",
                current=parse_float(latest_corn_price.get("value")),
                previous=parse_float(prior_corn_price.get("value")),
                as_of=as_of,
            ),
            build_metric(
                metric_id="soy_ending_stocks",
                label="Soybean ending stocks",
                unit="million_bushels",
                current=parse_float(latest_soy_ending.get("value")),
                previous=parse_float(prior_soy_ending.get("value")),
                as_of=as_of,
            ),
            build_metric(
                metric_id="soy_avg_farm_price",
                label="Soybean avg. farm price",
                unit="usd_per_bushel",
                current=parse_float(latest_soy_price.get("value")),
                previous=parse_float(prior_soy_price.get("value")),
                as_of=as_of,
            ),
        ),
        charts=(
            SectorChart(
                chart_id="corn_ending_stocks_trend",
                title="Corn ending stocks",
                subtitle="Current USDA marketing-year path",
                unit="million_bushels",
                series=(
                    SectorChartSeries(
                        series_key="corn_ending_stocks",
                        label="Corn",
                        unit="million_bushels",
                        points=_series_points(corn_ending),
                    ),
                ),
            ),
            SectorChart(
                chart_id="soy_ending_stocks_trend",
                title="Soybean ending stocks",
                subtitle="Current USDA marketing-year path",
                unit="million_bushels",
                series=(
                    SectorChartSeries(
                        series_key="soy_ending_stocks",
                        label="Soybeans",
                        unit="million_bushels",
                        points=_series_points(soy_ending),
                    ),
                ),
            ),
        ),
        detail_view=SectorDetailView(
            title="Latest WASDE revision snapshot",
            rows=(
                build_detail_row(
                    label="Corn ending stocks",
                    unit="million_bushels",
                    current=parse_float(latest_corn_ending.get("value")),
                    previous=parse_float(prior_corn_ending.get("value")),
                    as_of=as_of,
                    note="Current projection versus prior WASDE month for the same crop year",
                ),
                build_detail_row(
                    label="Corn avg. farm price",
                    unit="usd_per_bushel",
                    current=parse_float(latest_corn_price.get("value")),
                    previous=parse_float(prior_corn_price.get("value")),
                    as_of=as_of,
                ),
                build_detail_row(
                    label="Soybean ending stocks",
                    unit="million_bushels",
                    current=parse_float(latest_soy_ending.get("value")),
                    previous=parse_float(prior_soy_ending.get("value")),
                    as_of=as_of,
                ),
                build_detail_row(
                    label="Soybean avg. farm price",
                    unit="usd_per_bushel",
                    current=parse_float(latest_soy_price.get("value")),
                    previous=parse_float(prior_soy_price.get("value")),
                    as_of=as_of,
                ),
            ),
        ),
        source_usages=(
            SourceUsage(
                source_id=USDA_SOURCE_ID,
                role="primary",
                as_of=as_of,
                last_refreshed_at=refreshed_at,
            ),
        ),
        as_of=as_of,
        last_refreshed_at=refreshed_at,
    )


PLUGIN = SectorPluginDefinition(
    plugin_id="usda_wasde",
    title="Agriculture Outlook",
    description=USDA_DESCRIPTION,
    refresh_policy=SectorRefreshPolicy(
        cadence_label="Monthly",
        ttl_seconds=24 * 60 * 60,
        notes=("USDA World Agricultural Supply and Demand Estimates release",),
    ),
    relevance_matcher=_relevance,
    fetch=fetch_plugin,
)