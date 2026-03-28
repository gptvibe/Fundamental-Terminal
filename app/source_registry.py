from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable, Literal


SourceTier = Literal[
    "official_regulator",
    "official_statistical",
    "official_treasury_or_fed",
    "derived_from_official",
    "commercial_fallback",
    "manual_override",
]

SourceRole = Literal["primary", "supplemental", "derived", "fallback"]


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    source_id: str
    tier: SourceTier
    display_label: str
    url: str
    default_freshness_ttl_seconds: int
    disclosure_note: str


@dataclass(frozen=True, slots=True)
class SourceUsage:
    source_id: str
    role: SourceRole = "primary"
    as_of: date | datetime | str | None = None
    last_refreshed_at: datetime | str | None = None


_REPO_URL = "https://github.com/gptvibe/Fundamental-Terminal"

SOURCE_REGISTRY: dict[str, SourceDefinition] = {
    "sec_edgar": SourceDefinition(
        source_id="sec_edgar",
        tier="official_regulator",
        display_label="SEC EDGAR Filing Archive",
        url="https://www.sec.gov/edgar/search/",
        default_freshness_ttl_seconds=6 * 60 * 60,
        disclosure_note="Official SEC filing archive used for filing metadata, ownership, governance, and event disclosures.",
    ),
    "sec_companyfacts": SourceDefinition(
        source_id="sec_companyfacts",
        tier="official_regulator",
        display_label="SEC Company Facts (XBRL)",
        url="https://data.sec.gov/api/xbrl/companyfacts/",
        default_freshness_ttl_seconds=6 * 60 * 60,
        disclosure_note="Official SEC XBRL companyfacts feed normalized into canonical financial statements.",
    ),
    "us_treasury_daily_par_yield_curve": SourceDefinition(
        source_id="us_treasury_daily_par_yield_curve",
        tier="official_treasury_or_fed",
        display_label="U.S. Treasury Daily Par Yield Curve",
        url="https://home.treasury.gov/resource-center/data-chart-center/interest-rates",
        default_freshness_ttl_seconds=24 * 60 * 60,
        disclosure_note="Official Treasury yield curve used for risk-free rates and macro term-structure context.",
    ),
    "us_treasury_fiscaldata": SourceDefinition(
        source_id="us_treasury_fiscaldata",
        tier="official_treasury_or_fed",
        display_label="U.S. Treasury FiscalData",
        url="https://fiscaldata.treasury.gov/",
        default_freshness_ttl_seconds=24 * 60 * 60,
        disclosure_note="Official Treasury fallback used when the daily par-yield curve feed is unavailable.",
    ),
    "fred": SourceDefinition(
        source_id="fred",
        tier="official_treasury_or_fed",
        display_label="Federal Reserve Economic Data (FRED)",
        url="https://fred.stlouisfed.org/",
        default_freshness_ttl_seconds=24 * 60 * 60,
        disclosure_note="Federal Reserve public macro series used for supplemental rates, inflation, labor, and credit context.",
    ),
    "bls_public_data": SourceDefinition(
        source_id="bls_public_data",
        tier="official_statistical",
        display_label="U.S. Bureau of Labor Statistics",
        url="https://www.bls.gov/data/",
        default_freshness_ttl_seconds=24 * 60 * 60,
        disclosure_note="Official BLS labor and inflation releases used for macro context.",
    ),
    "bea_nipa": SourceDefinition(
        source_id="bea_nipa",
        tier="official_statistical",
        display_label="Bureau of Economic Analysis (NIPA)",
        url="https://www.bea.gov/data/gdp/",
        default_freshness_ttl_seconds=24 * 60 * 60,
        disclosure_note="Official BEA national accounts data used for growth and activity context.",
    ),
    "treasury_hqm_corporate_yield_curve": SourceDefinition(
        source_id="treasury_hqm_corporate_yield_curve",
        tier="official_treasury_or_fed",
        display_label="U.S. Treasury HQM Corporate Bond Yield Curve",
        url="https://home.treasury.gov/resource-center/economic-policy/corporate-bond-yield-curve",
        default_freshness_ttl_seconds=24 * 60 * 60,
        disclosure_note="Official Treasury HQM curve used for credit-sensitive macro and valuation context.",
    ),
    "yahoo_finance": SourceDefinition(
        source_id="yahoo_finance",
        tier="commercial_fallback",
        display_label="Yahoo Finance",
        url="https://finance.yahoo.com/",
        default_freshness_ttl_seconds=60 * 60,
        disclosure_note="Commercial fallback used only for price, volume, and market-profile context; never for core fundamentals.",
    ),
    "ft_derived_metrics_engine": SourceDefinition(
        source_id="ft_derived_metrics_engine",
        tier="derived_from_official",
        display_label="Fundamental Terminal Derived Metrics Engine",
        url=_REPO_URL,
        default_freshness_ttl_seconds=6 * 60 * 60,
        disclosure_note="Internal formulas derived from official filings and labeled supplemental price inputs.",
    ),
    "ft_derived_metrics_mart": SourceDefinition(
        source_id="ft_derived_metrics_mart",
        tier="derived_from_official",
        display_label="Fundamental Terminal Derived Metrics Mart",
        url=_REPO_URL,
        default_freshness_ttl_seconds=6 * 60 * 60,
        disclosure_note="Persisted derived metrics computed from official filings plus labeled market context inputs.",
    ),
    "ft_model_engine": SourceDefinition(
        source_id="ft_model_engine",
        tier="derived_from_official",
        display_label="Fundamental Terminal Model Engine",
        url=_REPO_URL,
        default_freshness_ttl_seconds=6 * 60 * 60,
        disclosure_note="Cached model outputs derived from official filings, Treasury/Fed rates, and labeled price fallbacks.",
    ),
    "ft_peer_comparison": SourceDefinition(
        source_id="ft_peer_comparison",
        tier="derived_from_official",
        display_label="Fundamental Terminal Peer Comparison",
        url=_REPO_URL,
        default_freshness_ttl_seconds=6 * 60 * 60,
        disclosure_note="Peer comparison metrics derived from cached public-company filings, model runs, and labeled price inputs.",
    ),
    "ft_activity_overview": SourceDefinition(
        source_id="ft_activity_overview",
        tier="derived_from_official",
        display_label="Fundamental Terminal Activity Overview",
        url=_REPO_URL,
        default_freshness_ttl_seconds=6 * 60 * 60,
        disclosure_note="Unified activity feed assembled from official SEC disclosures and official macro status signals.",
    ),
    "ft_changes_since_last_filing": SourceDefinition(
        source_id="ft_changes_since_last_filing",
        tier="derived_from_official",
        display_label="Fundamental Terminal Filing Changes Service",
        url=_REPO_URL,
        default_freshness_ttl_seconds=6 * 60 * 60,
        disclosure_note="Latest-versus-prior filing comparison derived from cached SEC statements and amendment history.",
    ),
    "ft_capital_structure_intelligence": SourceDefinition(
        source_id="ft_capital_structure_intelligence",
        tier="derived_from_official",
        display_label="Fundamental Terminal Capital Structure Intelligence",
        url=_REPO_URL,
        default_freshness_ttl_seconds=6 * 60 * 60,
        disclosure_note="Persisted capital structure roll-forwards, maturities, payout mix, and dilution bridges derived from official SEC companyfacts statements.",
    ),
    "manual_override": SourceDefinition(
        source_id="manual_override",
        tier="manual_override",
        display_label="Manual Override",
        url=_REPO_URL,
        default_freshness_ttl_seconds=0,
        disclosure_note="Manually overridden data should be treated as exceptional and disclosed explicitly to users.",
    ),
}

_ROLE_ORDER: dict[SourceRole, int] = {
    "primary": 0,
    "supplemental": 1,
    "derived": 2,
    "fallback": 3,
}

_OFFICIAL_ONLY_TIERS = {
    "official_regulator",
    "official_statistical",
    "official_treasury_or_fed",
    "derived_from_official",
}


def get_source_definition(source_id: str) -> SourceDefinition | None:
    return SOURCE_REGISTRY.get(source_id)


def infer_source_id(source_hint: str | None, *, default: str | None = None) -> str | None:
    if not source_hint:
        return default

    normalized = source_hint.strip().lower()
    if not normalized:
        return default
    if normalized in SOURCE_REGISTRY:
        return normalized
    if "manual override" in normalized or "manual_override" in normalized:
        return "manual_override"
    if "finance.yahoo.com" in normalized or "yahoo_finance" in normalized or normalized == "yahoo":
        return "yahoo_finance"
    if "companyfacts" in normalized:
        return "sec_companyfacts"
    if "sec.gov" in normalized or "edgar" in normalized:
        return "sec_edgar"
    if "fiscaldata" in normalized or "average interest rates" in normalized:
        return "us_treasury_fiscaldata"
    if "hqm" in normalized and "treasury" in normalized:
        return "treasury_hqm_corporate_yield_curve"
    if "fred" in normalized or "stlouisfed.org" in normalized:
        return "fred"
    if "bureau of labor statistics" in normalized or " bls" in normalized or "bls.gov" in normalized:
        return "bls_public_data"
    if "bureau of economic analysis" in normalized or "bea" in normalized or "bea.gov" in normalized:
        return "bea_nipa"
    if "daily par yield curve" in normalized or "treasury yield curve" in normalized or "home.treasury.gov" in normalized:
        return "us_treasury_daily_par_yield_curve"
    return default


def build_provenance_entries(usages: Iterable[SourceUsage]) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}

    for usage in usages:
        definition = get_source_definition(usage.source_id)
        if definition is None:
            continue

        existing = merged.get(definition.source_id)
        candidate_role = usage.role
        candidate_as_of = _normalize_as_of(usage.as_of)
        candidate_refreshed = _normalize_datetime(usage.last_refreshed_at)

        if existing is None:
            merged[definition.source_id] = {
                "source_id": definition.source_id,
                "source_tier": definition.tier,
                "display_label": definition.display_label,
                "url": definition.url,
                "default_freshness_ttl_seconds": definition.default_freshness_ttl_seconds,
                "disclosure_note": definition.disclosure_note,
                "role": candidate_role,
                "as_of": candidate_as_of,
                "last_refreshed_at": candidate_refreshed,
            }
            continue

        existing_role = existing.get("role")
        if isinstance(existing_role, str) and _ROLE_ORDER.get(candidate_role, 99) < _ROLE_ORDER.get(existing_role, 99):
            existing["role"] = candidate_role

        existing["as_of"] = _newer_as_of(existing.get("as_of"), candidate_as_of)

        existing_refreshed = existing.get("last_refreshed_at")
        if isinstance(existing_refreshed, datetime):
            existing["last_refreshed_at"] = max(existing_refreshed, candidate_refreshed) if candidate_refreshed is not None else existing_refreshed
        elif candidate_refreshed is not None:
            existing["last_refreshed_at"] = candidate_refreshed

    return sorted(
        merged.values(),
        key=lambda item: (
            _ROLE_ORDER.get(str(item.get("role") or "fallback"), 99),
            str(item.get("display_label") or ""),
        ),
    )


def build_source_mix(entries: Iterable[dict[str, object]]) -> dict[str, object]:
    rows = list(entries)
    source_ids = [str(item.get("source_id") or "") for item in rows if item.get("source_id")]
    source_tiers = sorted({str(item.get("source_tier") or "") for item in rows if item.get("source_tier")})
    primary_source_ids = [
        str(item.get("source_id") or "")
        for item in rows
        if item.get("source_id") and str(item.get("role") or "") == "primary"
    ]
    fallback_source_ids = [
        str(item.get("source_id") or "")
        for item in rows
        if item.get("source_id") and str(item.get("source_tier") or "") in {"commercial_fallback", "manual_override"}
    ]
    official_only = bool(rows) and not fallback_source_ids and all(tier in _OFFICIAL_ONLY_TIERS for tier in source_tiers)
    return {
        "source_ids": source_ids,
        "source_tiers": source_tiers,
        "primary_source_ids": primary_source_ids,
        "fallback_source_ids": fallback_source_ids,
        "official_only": official_only,
    }


def _normalize_as_of(value: date | datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc).isoformat()
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value).strip()
    return text or None


def _normalize_datetime(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _newer_as_of(current: object, candidate: str | None) -> str | None:
    current_text = str(current).strip() if current is not None else ""
    if not current_text:
        return candidate
    if not candidate:
        return current_text

    current_dt = _parse_as_of(current_text)
    candidate_dt = _parse_as_of(candidate)
    if current_dt is None or candidate_dt is None:
        return max(current_text, candidate)
    return candidate if candidate_dt >= current_dt else current_text


def _parse_as_of(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass

    try:
        parsed_date = date.fromisoformat(value)
    except ValueError:
        return None
    return datetime(parsed_date.year, parsed_date.month, parsed_date.day, tzinfo=timezone.utc)
