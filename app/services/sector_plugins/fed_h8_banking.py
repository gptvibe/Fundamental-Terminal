from __future__ import annotations

from datetime import datetime, timezone
import re

from app.config import settings
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
    parse_float,
    unavailable_plugin_result,
)

FRED_OBSERVATIONS_URL = "https://api.stlouisfed.org/fred/series/observations"
H8_SOURCE_ID = "federal_reserve_h8"
H8_DESCRIPTION = "Federal Reserve H.8 weekly banking-system balance-sheet context for bank and savings institution issuers."

# Weekly H.8 (seasonally adjusted) aggregate series for all commercial banks.
H8_SERIES: tuple[tuple[str, str, str], ...] = (
    ("TOTLL", "Loans and leases", "billions_usd"),
    ("DPSACBW027SBOG", "Deposits", "billions_usd"),
    ("SBCACBW027SBOG", "Securities in bank credit", "billions_usd"),
    ("CASACBW027SBOG", "Cash assets", "billions_usd"),
)

_H8_BANKING_KEYWORDS = (
    "bank",
    "banks",
    "banking",
    "savings institution",
    "savings institutions",
    "thrifts",
    "depository",
)


def _extract_sic_candidates(*values: str | None) -> set[int]:
    found: set[int] = set()
    for raw in values:
        text = str(raw or "")
        for match in re.findall(r"\b(\d{4})\b", text):
            try:
                found.add(int(match))
            except ValueError:
                continue
    return found


def _relevance(sector: str | None, market_sector: str | None, market_industry: str | None) -> list[str]:
    reasons: list[str] = []
    for field_name, raw in (
        ("sector", sector or ""),
        ("market sector", market_sector or ""),
        ("industry", market_industry or ""),
    ):
        lowered = raw.lower()
        if any(keyword in lowered for keyword in _H8_BANKING_KEYWORDS):
            reasons.append(f"{field_name}: banking terms")

    for sic in sorted(_extract_sic_candidates(sector, market_sector, market_industry)):
        if 6000 <= sic <= 6199:
            reasons.append(f"sic: {sic}")

    return reasons


def _fetch_series(series_id: str) -> list[dict[str, object]]:
    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 14,
    }
    with build_http_client(timeout_seconds=settings.sec_timeout_seconds) as client:
        response = client.get(FRED_OBSERVATIONS_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    observations = payload.get("observations") if isinstance(payload, dict) else None
    if not isinstance(observations, list):
        return []

    rows: list[dict[str, object]] = []
    for item in observations:
        if not isinstance(item, dict):
            continue
        date_raw = str(item.get("date") or "").strip()
        value_raw = str(item.get("value") or "").strip()
        if not date_raw or value_raw in {"", "."}:
            continue
        rows.append(item)

    rows.sort(key=lambda item: str(item.get("date") or ""))
    return rows


def fetch_plugin() -> SectorPluginResult:
    source_usage = SourceUsage(source_id=H8_SOURCE_ID, role="primary")
    if not settings.fred_api_key:
        return unavailable_plugin_result(
            plugin_id="fed_h8_banking",
            title="Federal Reserve H.8 Banking",
            description=H8_DESCRIPTION,
            source_usages=(source_usage,),
            confidence_flags=("fred_api_key_missing",),
        )

    fetched: dict[str, list[dict[str, object]]] = {}
    for series_id, _label, _unit in H8_SERIES:
        fetched[series_id] = _fetch_series(series_id)

    if not any(fetched.values()):
        return unavailable_plugin_result(
            plugin_id="fed_h8_banking",
            title="Federal Reserve H.8 Banking",
            description=H8_DESCRIPTION,
            source_usages=(source_usage,),
            confidence_flags=("fed_h8_no_rows",),
        )

    refreshed_at = datetime.now(timezone.utc)

    def latest_pair(series_id: str) -> tuple[float | None, float | None, str | None]:
        rows = fetched.get(series_id) or []
        latest = rows[-1] if rows else {}
        previous = rows[-2] if len(rows) > 1 else {}
        return (
            parse_float(latest.get("value")),
            parse_float(previous.get("value")),
            str(latest.get("date") or "") or None,
        )

    metric_values = {series_id: latest_pair(series_id) for series_id, _label, _unit in H8_SERIES}
    as_of = max((value[2] for value in metric_values.values() if value[2]), default=None)

    chart_series = []
    for series_id, label, unit in H8_SERIES:
        chart_series.append(
            SectorChartSeries(
                series_key=series_id.lower(),
                label=label,
                unit=unit,
                points=tuple(
                    SectorChartPoint(label=str(row.get("date") or ""), value=parse_float(row.get("value")))
                    for row in (fetched.get(series_id) or [])[-12:]
                ),
            )
        )

    return SectorPluginResult(
        plugin_id="fed_h8_banking",
        title="Federal Reserve H.8 Banking",
        description=H8_DESCRIPTION,
        status="ok",
        summary_metrics=(
            build_metric(
                metric_id="h8_loans_and_leases",
                label="Loans and leases",
                unit="billions_usd",
                current=metric_values["TOTLL"][0],
                previous=metric_values["TOTLL"][1],
                as_of=metric_values["TOTLL"][2],
            ),
            build_metric(
                metric_id="h8_deposits",
                label="Deposits",
                unit="billions_usd",
                current=metric_values["DPSACBW027SBOG"][0],
                previous=metric_values["DPSACBW027SBOG"][1],
                as_of=metric_values["DPSACBW027SBOG"][2],
            ),
            build_metric(
                metric_id="h8_securities",
                label="Securities in bank credit",
                unit="billions_usd",
                current=metric_values["SBCACBW027SBOG"][0],
                previous=metric_values["SBCACBW027SBOG"][1],
                as_of=metric_values["SBCACBW027SBOG"][2],
            ),
            build_metric(
                metric_id="h8_cash_assets",
                label="Cash assets",
                unit="billions_usd",
                current=metric_values["CASACBW027SBOG"][0],
                previous=metric_values["CASACBW027SBOG"][1],
                as_of=metric_values["CASACBW027SBOG"][2],
            ),
        ),
        charts=(
            SectorChart(
                chart_id="h8_balance_sheet_trend",
                title="H.8 commercial banking balance-sheet trend",
                subtitle="Weekly Federal Reserve H.8 release (all commercial banks)",
                unit="billions_usd",
                series=tuple(chart_series),
            ),
        ),
        detail_view=SectorDetailView(
            title="Latest H.8 weekly snapshot",
            rows=(
                build_detail_row(
                    label="Loans and leases",
                    unit="billions_usd",
                    current=metric_values["TOTLL"][0],
                    previous=metric_values["TOTLL"][1],
                    as_of=metric_values["TOTLL"][2],
                ),
                build_detail_row(
                    label="Deposits",
                    unit="billions_usd",
                    current=metric_values["DPSACBW027SBOG"][0],
                    previous=metric_values["DPSACBW027SBOG"][1],
                    as_of=metric_values["DPSACBW027SBOG"][2],
                ),
                build_detail_row(
                    label="Securities in bank credit",
                    unit="billions_usd",
                    current=metric_values["SBCACBW027SBOG"][0],
                    previous=metric_values["SBCACBW027SBOG"][1],
                    as_of=metric_values["SBCACBW027SBOG"][2],
                ),
                build_detail_row(
                    label="Cash assets",
                    unit="billions_usd",
                    current=metric_values["CASACBW027SBOG"][0],
                    previous=metric_values["CASACBW027SBOG"][1],
                    as_of=metric_values["CASACBW027SBOG"][2],
                ),
            ),
        ),
        source_usages=(
            SourceUsage(
                source_id=H8_SOURCE_ID,
                role="primary",
                as_of=as_of,
                last_refreshed_at=refreshed_at,
            ),
        ),
        as_of=as_of,
        last_refreshed_at=refreshed_at,
    )


PLUGIN = SectorPluginDefinition(
    plugin_id="fed_h8_banking",
    title="Federal Reserve H.8 Banking",
    description=H8_DESCRIPTION,
    refresh_policy=SectorRefreshPolicy(
        cadence_label="Weekly",
        ttl_seconds=24 * 60 * 60,
        notes=("Federal Reserve H.8 release (all commercial banks)",),
    ),
    relevance_matcher=_relevance,
    fetch=fetch_plugin,
)
