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
    "technology": [
        "DGS2", "DGS10", "HQM_30Y", "CP",                        # rates + credit + corporate profits
        "A191RL1Q225SBEA",                                         # GDP growth (capex env)
    ],
    "financials": [
        "DGS2", "DGS10", "slope_2s10s",                           # yield curve shape
        "HQM_30Y", "BAA10Y",                                       # credit conditions
        "LNS14000000", "CUSR0000SA0",                              # labor/inflation backdrop
        "A191RL1Q225SBEA",                                         # growth conditions
    ],
    "consumer_discretionary": [
        "CUSR0000SA0", "CUSR0000SA0L1E", "PI", "PCE",             # CPI, core CPI, income, PCE
        "LNS14000000",                                             # unemployment
    ],
    "consumer_staples": [
        "CUSR0000SA0", "CUSR0000SA0L1E", "PI", "PCE",
        "WPSFD4",                                                  # PPI input costs
    ],
    "industrials": [
        "WPSFD4", "A191RL1Q225SBEA",                               # PPI + GDP
        "CP",                                                      # corporate profits
        "LNS14000000", "CES0000000001",                            # labor market
    ],
    "energy": [
        "DGS10", "A191RL1Q225SBEA", "PCE",                        # rates + growth + consumer demand
        "CP",
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
        "A191RL1Q225SBEA", "CP",                                   # growth + profits
        "LNS14000000",                                             # labor (staff costs)
    ],
    "materials": [
        "WPSFD4", "A191RL1Q225SBEA",
        "CP", "CES0000000001",
    ],
    "communication_services": [
        "DGS10", "CP", "PCE",
        "CUSR0000SA0L1E",
    ],
    # Default for unknown sectors
    "default": [
        "DGS10", "CUSR0000SA0", "LNS14000000", "A191RL1Q225SBEA",
    ],
}

_SECTOR_EXPOSURE_TAGS: dict[str, list[str]] = {
    "technology": ["growth_sensitive", "rate_sensitive", "credit_spread"],
    "financials": ["yield_curve", "credit_spread", "rate_sensitive", "labor_inflation_backdrop"],
    "consumer_discretionary": ["consumer_spending", "inflation_sensitive", "income_sensitive"],
    "consumer_staples": ["consumer_spending", "inflation_sensitive", "input_cost_sensitive"],
    "industrials": ["input_cost_sensitive", "gdp_sensitive", "labor_sensitive"],
    "energy": ["gdp_sensitive", "rate_sensitive", "consumer_demand"],
    "utilities": ["rate_sensitive", "yield_curve", "inflation_sensitive"],
    "real_estate": ["rate_sensitive", "yield_curve", "income_sensitive", "credit_spread"],
    "healthcare": ["inflation_sensitive", "labor_sensitive", "gdp_sensitive"],
    "materials": ["input_cost_sensitive", "gdp_sensitive", "labor_sensitive"],
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

    if any(kw in combined for kw in ("technology", "software", "semiconductor", "tech")):
        return "technology"
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
