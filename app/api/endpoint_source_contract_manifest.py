from __future__ import annotations

from app.api.source_contracts import ConfidencePenaltyRule, SourceContract, UIDisclosureRequirement


EndpointKey = tuple[str, str]

_RULE_PERSISTED_DATA_GATING = ConfidencePenaltyRule(
    rule_id="persisted_data_gating",
    applies_when="The endpoint reads from a cached or persisted slice that can be missing, stale, or partially refreshed.",
    effect="Treat the payload as lower confidence until refresh completes and surface stale-or-missing diagnostics.",
)

_RULE_DERIVED_ANALYTICS = ConfidencePenaltyRule(
    rule_id="derived_from_official_inputs",
    applies_when="The endpoint computes analytics from cached official inputs instead of returning a direct upstream payload.",
    effect="Carry forward upstream gaps and quality flags into the response confidence surface.",
)

_RULE_OFFICIAL_FALLBACK = ConfidencePenaltyRule(
    rule_id="approved_official_fallback",
    applies_when="The primary official feed is unavailable and the route can substitute an approved official or persisted official-derived fallback.",
    effect="Keep the payload available, but disclose the fallback path and lower trust messaging until the primary feed recovers.",
)

_RULE_COMMERCIAL_FALLBACK = ConfidencePenaltyRule(
    rule_id="commercial_fallback_present",
    applies_when="Yahoo-backed price or market-profile inputs influence the payload.",
    effect="Add a commercial fallback confidence flag and require explicit UI fallback disclosure.",
)

_RULE_STRICT_OFFICIAL_MODE = ConfidencePenaltyRule(
    rule_id="strict_official_mode",
    applies_when="STRICT_OFFICIAL_MODE is enabled for a surface that can otherwise include Yahoo-backed inputs.",
    effect="Drop fallback-backed fields or sections and add strict-official confidence messaging.",
)

_RULE_SYNTHETIC_FIXTURE = ConfidencePenaltyRule(
    rule_id="synthetic_fixture_suite",
    applies_when="Model evaluation runs are backed by deterministic synthetic fixtures instead of historical cached market data.",
    effect="Mark the run as regression-only and prevent users from confusing it with live historical-source validation.",
)

_DISCLOSURE_OFFICIAL_ONLY = UIDisclosureRequirement(
    requirement_id="official_public_only",
    applies_when="The surface renders issuer fundamentals, filings, ownership, governance, or macro context without commercial fallback inputs.",
    presentation="inline_note",
    message="Label the surface as sourced from official/public inputs or internal derivations of them.",
)

_DISCLOSURE_DERIVED_ANALYTICS = UIDisclosureRequirement(
    requirement_id="derived_analytics_note",
    applies_when="The surface computes analytics from persisted official inputs rather than returning raw upstream records.",
    presentation="inline_note",
    message="Explain that the values are derived in-house from persisted official inputs and inherit upstream confidence flags.",
)

_DISCLOSURE_OFFICIAL_FALLBACK = UIDisclosureRequirement(
    requirement_id="official_fallback_note",
    applies_when="An approved official or persisted official-derived fallback path is active for the surface.",
    presentation="inline_note",
    message="Explain which approved official fallback path supplied the current response when the primary feed is unavailable.",
)

_DISCLOSURE_COMMERCIAL_FALLBACK = UIDisclosureRequirement(
    requirement_id="commercial_fallback_badge",
    applies_when="Yahoo-backed price or market-profile inputs contribute to the payload.",
    presentation="badge",
    message="Show a visible commercial fallback badge whenever Yahoo-backed inputs are present.",
)

_DISCLOSURE_STRICT_OFFICIAL_MODE = UIDisclosureRequirement(
    requirement_id="strict_official_mode_notice",
    applies_when="STRICT_OFFICIAL_MODE removes fallback-backed fields or disables a price-sensitive section.",
    presentation="banner",
    message="Explain that the suppressed data requires a commercial fallback that is disabled in strict official mode.",
)

_DISCLOSURE_SYNTHETIC_FIXTURE = UIDisclosureRequirement(
    requirement_id="synthetic_fixture_notice",
    applies_when="The latest model-evaluation run is backed by the deterministic fixture suite.",
    presentation="banner",
    message="Disclose that the evaluation result is a regression fixture and not a live historical-source run.",
)


def _control_plane_contract() -> SourceContract:
    return SourceContract(
        allowed_source_ids=(),
        fallback_permitted=False,
        strict_official_behavior="not_applicable",
        confidence_penalty_rules=(),
        ui_disclosure_requirements=(),
    )


def _official_only_contract(*source_ids: str) -> SourceContract:
    return SourceContract(
        allowed_source_ids=source_ids,
        fallback_permitted=False,
        strict_official_behavior="official_only",
        confidence_penalty_rules=(_RULE_PERSISTED_DATA_GATING,),
        ui_disclosure_requirements=(_DISCLOSURE_OFFICIAL_ONLY,),
    )


def _official_fallback_contract(*source_ids: str) -> SourceContract:
    return SourceContract(
        allowed_source_ids=source_ids,
        fallback_permitted=True,
        strict_official_behavior="official_only",
        confidence_penalty_rules=(_RULE_PERSISTED_DATA_GATING, _RULE_OFFICIAL_FALLBACK),
        ui_disclosure_requirements=(_DISCLOSURE_OFFICIAL_ONLY, _DISCLOSURE_OFFICIAL_FALLBACK),
    )


def _derived_official_contract(*source_ids: str, fallback_permitted: bool = False) -> SourceContract:
    return SourceContract(
        allowed_source_ids=source_ids,
        fallback_permitted=fallback_permitted,
        strict_official_behavior="official_only",
        confidence_penalty_rules=(_RULE_PERSISTED_DATA_GATING, _RULE_DERIVED_ANALYTICS),
        ui_disclosure_requirements=(_DISCLOSURE_OFFICIAL_ONLY, _DISCLOSURE_DERIVED_ANALYTICS),
    )


def _price_sensitive_contract(*source_ids: str) -> SourceContract:
    return SourceContract(
        allowed_source_ids=source_ids,
        fallback_permitted=True,
        strict_official_behavior="drop_commercial_fallback_inputs",
        confidence_penalty_rules=(
            _RULE_PERSISTED_DATA_GATING,
            _RULE_DERIVED_ANALYTICS,
            _RULE_COMMERCIAL_FALLBACK,
            _RULE_STRICT_OFFICIAL_MODE,
        ),
        ui_disclosure_requirements=(
            _DISCLOSURE_DERIVED_ANALYTICS,
            _DISCLOSURE_COMMERCIAL_FALLBACK,
            _DISCLOSURE_STRICT_OFFICIAL_MODE,
        ),
    )


USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS: dict[EndpointKey, SourceContract] = {
    ("GET", "/api/jobs/{job_id}/events"): _control_plane_contract(),
    ("GET", "/api/companies/search"): _official_only_contract("sec_edgar", "fdic_bankfind_institutions"),
    ("GET", "/api/companies/resolve"): _official_only_contract("sec_edgar"),
    (
        "GET",
        "/api/screener/filters",
    ): _derived_official_contract(
        "ft_screener_backend",
        "ft_derived_metrics_mart",
        "ft_model_engine",
        "sec_companyfacts",
        "sec_edgar",
        "fdic_bankfind_financials",
        "federal_reserve_fr_y9c",
    ),
    (
        "POST",
        "/api/screener/search",
    ): _derived_official_contract(
        "ft_screener_backend",
        "ft_derived_metrics_mart",
        "ft_model_engine",
        "sec_companyfacts",
        "sec_edgar",
        "fdic_bankfind_financials",
        "federal_reserve_fr_y9c",
    ),
    (
        "GET",
        "/api/companies/{ticker}/financials",
    ): _price_sensitive_contract(
        "sec_companyfacts",
        "sec_edgar",
        "fdic_bankfind_financials",
        "federal_reserve_fr_y9c",
        "yahoo_finance",
    ),
    (
        "GET",
        "/api/companies/{ticker}/segment-history",
    ): _derived_official_contract(
        "ft_snapshot_history",
        "sec_companyfacts",
        "sec_edgar",
    ),
    (
        "GET",
        "/api/companies/{ticker}/capital-structure",
    ): _derived_official_contract(
        "ft_capital_structure_intelligence",
        "sec_companyfacts",
        "sec_edgar",
        "fdic_bankfind_financials",
        "federal_reserve_fr_y9c",
    ),
    ("GET", "/api/companies/{ticker}/filing-insights"): _official_only_contract("sec_edgar"),
    (
        "GET",
        "/api/companies/{ticker}/changes-since-last-filing",
    ): _derived_official_contract(
        "ft_changes_since_last_filing",
        "sec_companyfacts",
        "sec_edgar",
        "fdic_bankfind_financials",
        "federal_reserve_fr_y9c",
    ),
    (
        "GET",
        "/api/companies/{ticker}/metrics-timeseries",
    ): _price_sensitive_contract(
        "ft_derived_metrics_engine",
        "sec_companyfacts",
        "sec_edgar",
        "fdic_bankfind_financials",
        "federal_reserve_fr_y9c",
        "yahoo_finance",
    ),
    (
        "GET",
        "/api/companies/{ticker}/metrics",
    ): _price_sensitive_contract(
        "ft_derived_metrics_mart",
        "ft_derived_metrics_engine",
        "sec_companyfacts",
        "sec_edgar",
        "fdic_bankfind_financials",
        "federal_reserve_fr_y9c",
        "yahoo_finance",
    ),
    (
        "GET",
        "/api/companies/{ticker}/metrics/summary",
    ): _price_sensitive_contract(
        "ft_derived_metrics_mart",
        "ft_derived_metrics_engine",
        "sec_companyfacts",
        "sec_edgar",
        "fdic_bankfind_financials",
        "federal_reserve_fr_y9c",
        "yahoo_finance",
    ),
    ("GET", "/api/companies/{ticker}/insider-trades"): _official_only_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/institutional-holdings"): _official_only_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/institutional-holdings/summary"): _official_only_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/form-144-filings"): _official_only_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/earnings"): _official_only_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/earnings/summary"): _official_only_contract("sec_edgar"),
    (
        "GET",
        "/api/companies/{ticker}/earnings/workspace",
    ): _price_sensitive_contract("sec_edgar", "sec_companyfacts", "yahoo_finance"),
    ("GET", "/api/insiders/{ticker}"): _derived_official_contract("sec_edgar"),
    ("GET", "/api/ownership/{ticker}"): _derived_official_contract("sec_edgar"),
    ("POST", "/api/companies/{ticker}/refresh"): _control_plane_contract(),
    (
        "GET",
        "/api/companies/{ticker}/models",
    ): _price_sensitive_contract(
        "ft_model_engine",
        "sec_edgar",
        "sec_companyfacts",
        "fdic_bankfind_financials",
        "federal_reserve_fr_y9c",
        "us_treasury_daily_par_yield_curve",
        "us_treasury_fiscaldata",
        "fred",
        "yahoo_finance",
    ),
    (
        "GET",
        "/api/model-evaluations/latest",
    ): SourceContract(
        allowed_source_ids=(
            "ft_model_evaluation_harness",
            "ft_model_evaluation_fixture",
            "sec_companyfacts",
            "yahoo_finance",
        ),
        fallback_permitted=True,
        strict_official_behavior="drop_commercial_fallback_inputs",
        confidence_penalty_rules=(
            _RULE_PERSISTED_DATA_GATING,
            _RULE_DERIVED_ANALYTICS,
            _RULE_COMMERCIAL_FALLBACK,
            _RULE_STRICT_OFFICIAL_MODE,
            _RULE_SYNTHETIC_FIXTURE,
        ),
        ui_disclosure_requirements=(
            _DISCLOSURE_DERIVED_ANALYTICS,
            _DISCLOSURE_COMMERCIAL_FALLBACK,
            _DISCLOSURE_STRICT_OFFICIAL_MODE,
            _DISCLOSURE_SYNTHETIC_FIXTURE,
        ),
    ),
    (
        "GET",
        "/api/companies/{ticker}/market-context",
    ): _official_fallback_contract(
        "us_treasury_daily_par_yield_curve",
        "us_treasury_fiscaldata",
        "fred",
        "bls_public_data",
        "bea_nipa",
        "bea_gdp_by_industry",
        "census_eits_m3",
        "census_eits_retail_sales",
        "treasury_hqm_corporate_yield_curve",
    ),
    (
        "GET",
        "/api/companies/{ticker}/sector-context",
    ): _official_only_contract(
        "eia_electricity_retail_sales",
        "fhfa_house_price_index",
        "bts_t100_segment_summary",
        "bts_form41_financial_review",
        "usda_wasde",
    ),
    (
        "GET",
        "/api/market-context",
    ): _official_fallback_contract(
        "us_treasury_daily_par_yield_curve",
        "us_treasury_fiscaldata",
        "fred",
        "bls_public_data",
        "bea_nipa",
        "bea_gdp_by_industry",
        "census_eits_m3",
        "census_eits_retail_sales",
        "treasury_hqm_corporate_yield_curve",
    ),
    (
        "GET",
        "/api/companies/{ticker}/peers",
    ): _price_sensitive_contract(
        "ft_peer_comparison",
        "sec_edgar",
        "sec_companyfacts",
        "fdic_bankfind_financials",
        "federal_reserve_fr_y9c",
        "us_treasury_daily_par_yield_curve",
        "us_treasury_fiscaldata",
        "fred",
        "yahoo_finance",
    ),
    (
        "GET",
        "/api/companies/{ticker}/filings",
    ): _official_fallback_contract("sec_edgar", "sec_companyfacts"),
    ("GET", "/api/companies/{ticker}/beneficial-ownership"): _official_only_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/beneficial-ownership/summary"): _derived_official_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/governance"): _official_only_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/governance/summary"): _derived_official_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/executive-compensation"): _official_only_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/capital-raises"): _official_only_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/capital-markets"): _official_only_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/capital-markets/summary"): _derived_official_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/events"): _official_only_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/filing-events"): _official_only_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/filing-events/summary"): _derived_official_contract("sec_edgar"),
    (
        "GET",
        "/api/companies/{ticker}/activity-feed",
    ): _derived_official_contract(
        "ft_activity_overview",
        "sec_edgar",
        "us_treasury_daily_par_yield_curve",
        "us_treasury_fiscaldata",
        "fred",
        fallback_permitted=True,
    ),
    (
        "GET",
        "/api/companies/{ticker}/alerts",
    ): _derived_official_contract(
        "ft_activity_overview",
        "sec_edgar",
        "us_treasury_daily_par_yield_curve",
        "us_treasury_fiscaldata",
        "fred",
        fallback_permitted=True,
    ),
    (
        "GET",
        "/api/companies/{ticker}/activity-overview",
    ): _derived_official_contract(
        "ft_activity_overview",
        "sec_edgar",
        "us_treasury_daily_par_yield_curve",
        "us_treasury_fiscaldata",
        "fred",
        fallback_permitted=True,
    ),
    (
        "POST",
        "/api/watchlist/summary",
    ): _price_sensitive_contract(
        "ft_activity_overview",
        "ft_model_engine",
        "sec_edgar",
        "sec_companyfacts",
        "fdic_bankfind_financials",
        "federal_reserve_fr_y9c",
        "us_treasury_daily_par_yield_curve",
        "us_treasury_fiscaldata",
        "fred",
        "yahoo_finance",
    ),
    ("GET", "/api/filings/{ticker}"): _official_only_contract("sec_edgar"),
    ("GET", "/api/search_filings"): _official_only_contract("sec_edgar"),
    ("GET", "/api/companies/{ticker}/financial-history"): _official_only_contract("sec_companyfacts"),
    ("GET", "/api/companies/{ticker}/financial-restatements"): _derived_official_contract("sec_companyfacts", "sec_edgar"),
    ("GET", "/api/companies/{ticker}/filings/view"): _official_only_contract("sec_edgar"),
}


def get_user_visible_endpoint_source_contract(method: str, path: str) -> SourceContract:
    key = (method.upper(), path)
    try:
        return USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS[key]
    except KeyError as exc:
        raise KeyError(f"missing user-visible endpoint source contract for {method.upper()} {path}") from exc


__all__ = [
    "EndpointKey",
    "USER_VISIBLE_ENDPOINT_SOURCE_CONTRACTS",
    "get_user_visible_endpoint_source_contract",
]