from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class SecSicProfile:
    market_sector: str | None
    market_industry: str | None


_EMPTY_PROFILE = SecSicProfile(market_sector=None, market_industry=None)

_SIC_EXACT_MAP: dict[int, SecSicProfile] = {
    1311: SecSicProfile("Energy", "Oil & Gas"),
    1389: SecSicProfile("Energy", "Oil & Gas Services"),
    2834: SecSicProfile("Healthcare", "Biotechnology & Pharmaceuticals"),
    2836: SecSicProfile("Healthcare", "Biotechnology & Pharmaceuticals"),
    3571: SecSicProfile("Technology", "Computer Hardware"),
    3576: SecSicProfile("Technology", "Computer Hardware"),
    3577: SecSicProfile("Technology", "Computer Hardware"),
    3663: SecSicProfile("Technology", "Communications Equipment"),
    3674: SecSicProfile("Technology", "Semiconductors"),
    3679: SecSicProfile("Technology", "Semiconductors"),
    3841: SecSicProfile("Healthcare", "Medical Devices"),
    3842: SecSicProfile("Healthcare", "Medical Devices"),
    3845: SecSicProfile("Healthcare", "Medical Devices"),
    4512: SecSicProfile("Industrials", "Airlines"),
    4812: SecSicProfile("Communication Services", "Telecom & Media"),
    4833: SecSicProfile("Communication Services", "Broadcasting & Streaming"),
    6021: SecSicProfile("Financials", "Banks"),
    6022: SecSicProfile("Financials", "Banks"),
    6035: SecSicProfile("Financials", "Banks"),
    6199: SecSicProfile("Financials", "Capital Markets"),
    6211: SecSicProfile("Financials", "Capital Markets"),
    6282: SecSicProfile("Financials", "Asset Management"),
    6311: SecSicProfile("Financials", "Insurance"),
    6331: SecSicProfile("Financials", "Insurance"),
    6798: SecSicProfile("Real Estate", "REITs"),
    7370: SecSicProfile("Technology", "Software"),
    7371: SecSicProfile("Technology", "Software"),
    7372: SecSicProfile("Technology", "Software"),
    7373: SecSicProfile("Technology", "Software"),
    7374: SecSicProfile("Technology", "Software"),
    7377: SecSicProfile("Technology", "Software"),
    7389: SecSicProfile("Technology", "IT Services"),
}

_DESCRIPTION_KEYWORDS: tuple[tuple[tuple[str, ...], SecSicProfile], ...] = (
    (("semiconductor", "semiconductors"), SecSicProfile("Technology", "Semiconductors")),
    (("software", "prepackaged software", "computer programming"), SecSicProfile("Technology", "Software")),
    (("it services", "information technology", "data processing", "cloud"), SecSicProfile("Technology", "IT Services")),
    (("biotechnology", "pharmaceutical", "pharmaceuticals", "drug"), SecSicProfile("Healthcare", "Biotechnology & Pharmaceuticals")),
    (("medical device", "surgical", "diagnostic", "medical instruments"), SecSicProfile("Healthcare", "Medical Devices")),
    (("bank", "banking", "commercial bank", "national commercial bank"), SecSicProfile("Financials", "Banks")),
    (("insurance", "insurer"), SecSicProfile("Financials", "Insurance")),
    (("asset management", "investment advice", "broker", "brokerage", "capital markets", "security brokers"), SecSicProfile("Financials", "Capital Markets")),
    (("reit", "real estate investment trust"), SecSicProfile("Real Estate", "REITs")),
    (("real estate", "property", "commercial property"), SecSicProfile("Real Estate", "Real Estate Services")),
    (("oil", "petroleum", "gas", "drilling", "pipeline", "energy"), SecSicProfile("Energy", "Oil & Gas")),
    (("telecommunications", "telephone", "wireless", "communications"), SecSicProfile("Communication Services", "Telecom & Media")),
    (("broadcast", "streaming", "cable", "media", "publishing"), SecSicProfile("Communication Services", "Media")),
    (("airline", "air transportation", "air freight"), SecSicProfile("Industrials", "Airlines")),
    (("aerospace", "defense"), SecSicProfile("Industrials", "Aerospace & Defense")),
    (("machinery", "industrial machinery", "transportation equipment"), SecSicProfile("Industrials", "Industrial Equipment")),
    (("retail", "apparel", "specialty stores", "automotive retail"), SecSicProfile("Consumer Discretionary", "Retail & Consumer Services")),
    (("restaurant", "hotel", "lodging", "casino", "leisure"), SecSicProfile("Consumer Discretionary", "Leisure & Consumer Services")),
    (("food", "beverage", "grocery", "tobacco", "household"), SecSicProfile("Consumer Staples", "Food, Beverage & Staples")),
    (("utility", "utilities", "electric", "water supply"), SecSicProfile("Utilities", "Utilities")),
    (("chemical", "chemicals", "fertilizer"), SecSicProfile("Materials", "Chemicals & Materials")),
    (("metal", "steel", "mining", "paper"), SecSicProfile("Materials", "Materials")),
)


def resolve_sec_sic_profile(sic_code: Any, sic_description: Any) -> SecSicProfile:
    normalized_code = _normalize_sic_code(sic_code)
    if normalized_code is not None:
        exact_match = _SIC_EXACT_MAP.get(normalized_code)
        if exact_match is not None:
            return exact_match

        range_match = _profile_from_code_range(normalized_code)
        if range_match is not None:
            return range_match

    normalized_description = _normalize_text(sic_description)
    if normalized_description:
        for keywords, profile in _DESCRIPTION_KEYWORDS:
            if any(keyword in normalized_description for keyword in keywords):
                return profile

    return _EMPTY_PROFILE


def _normalize_sic_code(value: Any) -> int | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text.isdigit():
        return None
    return int(text)


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _profile_from_code_range(sic_code: int) -> SecSicProfile | None:
    if 1000 <= sic_code <= 1499:
        return SecSicProfile("Materials", "Materials")
    if 1500 <= sic_code <= 1799:
        return SecSicProfile("Industrials", "Construction & Engineering")
    if 2000 <= sic_code <= 2199:
        return SecSicProfile("Consumer Staples", "Food, Beverage & Staples")
    if 2200 <= sic_code <= 2599:
        return SecSicProfile("Consumer Discretionary", "Apparel, Home & Leisure")
    if 2600 <= sic_code <= 2799:
        return SecSicProfile("Materials", "Materials")
    if 2800 <= sic_code <= 2829:
        return SecSicProfile("Materials", "Chemicals & Materials")
    if 2830 <= sic_code <= 2839:
        return SecSicProfile("Healthcare", "Biotechnology & Pharmaceuticals")
    if 2840 <= sic_code <= 2899:
        return SecSicProfile("Materials", "Chemicals & Materials")
    if 2900 <= sic_code <= 2999:
        return SecSicProfile("Energy", "Oil & Gas")
    if 3000 <= sic_code <= 3499:
        return SecSicProfile("Industrials", "Industrial Equipment")
    if 3500 <= sic_code <= 3569:
        return SecSicProfile("Industrials", "Industrial Equipment")
    if 3570 <= sic_code <= 3579:
        return SecSicProfile("Technology", "Computer Hardware")
    if 3600 <= sic_code <= 3669:
        return SecSicProfile("Technology", "Communications Equipment")
    if 3670 <= sic_code <= 3679:
        return SecSicProfile("Technology", "Semiconductors")
    if 3680 <= sic_code <= 3699:
        return SecSicProfile("Technology", "Electronics")
    if 3700 <= sic_code <= 3799:
        return SecSicProfile("Industrials", "Transportation & Aerospace")
    if 3800 <= sic_code <= 3839:
        return SecSicProfile("Industrials", "Instruments & Controls")
    if 3840 <= sic_code <= 3859:
        return SecSicProfile("Healthcare", "Medical Devices")
    if 3860 <= sic_code <= 3999:
        return SecSicProfile("Consumer Discretionary", "Leisure & Consumer Services")
    if 4000 <= sic_code <= 4799:
        return SecSicProfile("Industrials", "Transportation")
    if 4800 <= sic_code <= 4899:
        return SecSicProfile("Communication Services", "Telecom & Media")
    if 4900 <= sic_code <= 4999:
        return SecSicProfile("Utilities", "Utilities")
    if 5000 <= sic_code <= 5199:
        return SecSicProfile("Industrials", "Distributors & Services")
    if 5200 <= sic_code <= 5999:
        return SecSicProfile("Consumer Discretionary", "Retail & Consumer Services")
    if 6000 <= sic_code <= 6799:
        return SecSicProfile("Financials", "Financial Services")
    if 7000 <= sic_code <= 7299:
        return SecSicProfile("Consumer Discretionary", "Leisure & Consumer Services")
    if 7300 <= sic_code <= 7399:
        return SecSicProfile("Technology", "IT Services")
    if 8000 <= sic_code <= 8099:
        return SecSicProfile("Healthcare", "Healthcare Services")
    return None