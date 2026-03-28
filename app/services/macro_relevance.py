"""Company macro relevance mapper.

Maps company sector / market_sector / market_industry to a curated subset
of macro series most relevant for that company's business profile.

Returns:
  - relevant_series: list[str] — series_ids to emphasize in UI
  - sector_exposure: list[str] — tags describing this company's macro exposures
"""

from __future__ import annotations

from typing import NamedTuple

UNSUPPORTED_FINANCIAL_KEYWORDS = (
    "bank",
    "banking",
    "insurance",
    "insurer",
    "reit",
    "real estate investment trust",
    "capital market",
    "capital markets",
    "asset management",
    "broker",
    "brokerage",
    "securities",
    "financial services",
    "investment banking",
)


class MacroRelevanceResult(NamedTuple):
    relevant_series: list[str]
    sector_exposure: list[str]


# Relevance definitions by profile tag
_PROFILE_RELEVANCE: dict[str, list[str]] = {
    "technology_hardware": [
        "DGS2", "DGS10", "HQM_30Y",
        "census_m3_shipments_total", "census_m3_new_orders_total", "census_m3_inventories_total",
        "bea_gdp_information", "WPSFD4", "CIU1010000000000I",
    ],
    "technology_software": [
        "DGS2", "DGS10", "HQM_30Y", "CP",                        # rates + credit + corporate profits
        "bea_gdp_information", "CIU1010000000000I", "JTS000000000000000JOL",
    ],
    "financials": [
        "DGS2", "DGS10", "slope_2s10s",                           # yield curve shape
        "HQM_30Y", "BAA10Y",                                       # credit conditions
        "LNS14000000", "CUSR0000SA0",                              # labor/inflation backdrop
        "bea_pce_total",
    ],
    "consumer_discretionary": [
        "CUSR0000SA0", "CUSR0000SA0L1E", "bea_pce_total", "census_retail_sales_total",
        "LNS14000000", "CIU1010000000000I",
    ],
    "consumer_staples": [
        "CUSR0000SA0", "CUSR0000SA0L1E", "bea_pce_total", "census_retail_sales_total",
        "WPSFD4", "CIU1010000000000I",
    ],
    "industrials": [
        "census_m3_shipments_total", "census_m3_new_orders_total", "census_m3_backlog_total", "census_m3_inventories_total",
        "bea_gdp_manufacturing", "WPSFD4", "CIU1010000000000I", "JTS000000000000000JOL",
    ],
    "energy": [
        "DGS10", "bea_pce_total", "WPSFD4", "JTS000000000000000JOL",
    ],
    "utilities": [
        "DGS2", "DGS10", "slope_2s10s",                           # rate sensitivity
        "CUSR0000SA0",                                             # inflation pass-through
    ],
    "real_estate": [
        "DGS2", "DGS10", "HQM_30Y",                               # mortgage-rate proxies
        "slope_2s10s",                                             # curve for refinance env
        "PI", "PCE",                                               # income / consumer activity
    ],
    "healthcare": [
        "CUSR0000SA0", "CUSR0000SA0L1E",                           # inflation (drug costs)
        "bea_gdp_health_care", "CIU1010000000000I", "JTS000000000000000JOL",
    ],
    "materials": [
        "census_m3_shipments_total", "census_m3_inventories_total", "bea_gdp_manufacturing",
        "WPSFD4", "CIU1010000000000I",
    ],
    "communication_services": [
        "DGS10", "bea_pce_total", "census_retail_sales_total",
        "CUSR0000SA0L1E", "CIU1010000000000I",
    ],
    # Default for unknown sectors
    "default": [
        "DGS10", "CUSR0000SA0", "LNS14000000", "bea_pce_total",
    ],
}

_SECTOR_EXPOSURE_TAGS: dict[str, list[str]] = {
    "technology_hardware": ["capex_cycle", "inventory_cycle", "input_cost_sensitive", "rate_sensitive"],
    "technology_software": ["enterprise_spending", "labor_sensitive", "rate_sensitive"],
    "financials": ["yield_curve", "credit_spread", "rate_sensitive", "labor_inflation_backdrop"],
    "consumer_discretionary": ["consumer_spending", "retail_cycle", "inflation_sensitive", "income_sensitive"],
    "consumer_staples": ["consumer_spending", "retail_cycle", "inflation_sensitive", "input_cost_sensitive"],
    "industrials": ["manufacturing_cycle", "order_backlog", "input_cost_sensitive", "labor_sensitive"],
    "energy": ["gdp_sensitive", "rate_sensitive", "consumer_demand"],
    "utilities": ["rate_sensitive", "yield_curve", "inflation_sensitive"],
    "real_estate": ["rate_sensitive", "yield_curve", "income_sensitive", "credit_spread"],
    "healthcare": ["labor_sensitive", "services_demand", "inflation_sensitive"],
    "materials": ["manufacturing_cycle", "inventory_cycle", "input_cost_sensitive", "labor_sensitive"],
    "communication_services": ["growth_sensitive", "consumer_spending"],
    "default": ["rate_sensitive", "gdp_sensitive"],
}


def get_company_macro_relevance(
    *,
    sector: str | None,
    market_sector: str | None,
    market_industry: str | None,
) -> MacroRelevanceResult:
    """Return relevant_series and sector_exposure for a company's classification."""
    profile = _resolve_profile(sector, market_sector, market_industry)
    relevant = _PROFILE_RELEVANCE.get(profile, _PROFILE_RELEVANCE["default"])
    exposure = _SECTOR_EXPOSURE_TAGS.get(profile, _SECTOR_EXPOSURE_TAGS["default"])
    return MacroRelevanceResult(relevant_series=list(relevant), sector_exposure=list(exposure))


def _resolve_profile(
    sector: str | None,
    market_sector: str | None,
    market_industry: str | None,
) -> str:
    """Map sector classification strings to a profile key."""
    raw_values = [
        (sector or "").lower(),
        (market_sector or "").lower(),
        (market_industry or "").lower(),
    ]

    combined = " ".join(raw_values)

    # Financial sector check first
    for keyword in UNSUPPORTED_FINANCIAL_KEYWORDS:
        if keyword in combined:
            return "financials"

    if any(kw in combined for kw in ("semiconductor", "semiconductors", "electronics", "electronic", "computer hardware", "communications equipment", "consumer electronics")):
        return "technology_hardware"
    if any(kw in combined for kw in ("technology", "software", "saas", "cloud", "internet software", "tech")):
        return "technology_software"
    if any(kw in combined for kw in ("consumer discretionary", "retail", "restaurants", "apparel", "leisure", "auto")):
        return "consumer_discretionary"
    if any(kw in combined for kw in ("consumer staples", "food", "beverage", "household", "personal products")):
        return "consumer_staples"
    if any(kw in combined for kw in ("industrial", "aerospace", "defense", "machinery", "transportation", "airlines")):
        return "industrials"
    if any(kw in combined for kw in ("energy", "oil", "gas", "petroleum", "exploration", "refining")):
        return "energy"
    if any(kw in combined for kw in ("utilities", "electric", "gas utility", "water utility")):
        return "utilities"
    if any(kw in combined for kw in ("real estate", "reit", "property")):
        return "real_estate"
    if any(kw in combined for kw in ("health", "pharma", "biotech", "medical", "drug")):
        return "healthcare"
    if any(kw in combined for kw in ("materials", "chemicals", "metals", "mining", "paper")):
        return "materials"
    if any(kw in combined for kw in ("communication", "media", "internet", "publishing", "wireless", "telecom")):
        return "communication_services"

    return "default"
