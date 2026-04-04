from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.models.company import Company
from app.services.sec_sic import resolve_sec_sic_profile

OilExposureType = Literal["upstream", "integrated", "refiner", "midstream", "services", "non_oil"]
OilSupportStatus = Literal["supported", "partial", "unsupported"]


@dataclass(frozen=True, slots=True)
class OilExposureClassification:
    oil_exposure_type: OilExposureType
    oil_support_status: OilSupportStatus
    oil_support_reasons: tuple[str, ...]


def classify_company_oil_exposure(
    company: Company,
    *,
    strict_official_mode: bool,
) -> OilExposureClassification:
    sector = getattr(company, "sector", None)
    if strict_official_mode:
        profile = resolve_sec_sic_profile(None, sector)
        market_sector = profile.market_sector
        market_industry = profile.market_industry
    else:
        market_sector = getattr(company, "market_sector", None)
        market_industry = getattr(company, "market_industry", None)
        if not market_sector and not market_industry:
            profile = resolve_sec_sic_profile(None, sector)
            market_sector = profile.market_sector
            market_industry = profile.market_industry
    return classify_oil_exposure(
        sector=sector,
        market_sector=market_sector,
        market_industry=market_industry,
    )


def classify_oil_exposure(
    *,
    sector: str | None,
    market_sector: str | None,
    market_industry: str | None,
) -> OilExposureClassification:
    normalized_sector = _normalize(sector)
    normalized_market_sector = _normalize(market_sector)
    normalized_market_industry = _normalize(market_industry)
    combined = " ".join(item for item in (normalized_sector, normalized_market_sector, normalized_market_industry) if item)

    reasons: list[str] = []
    if market_sector:
        reasons.append(f"market_sector:{market_sector}")
    if market_industry:
        reasons.append(f"market_industry:{market_industry}")
    if sector:
        reasons.append(f"sector:{sector}")

    if normalized_market_sector != "energy" and not any(token in combined for token in _ENERGY_TOKENS):
        return OilExposureClassification(
            oil_exposure_type="non_oil",
            oil_support_status="unsupported",
            oil_support_reasons=tuple([*reasons, "non_energy_classification"]),
        )

    if any(token in normalized_market_industry for token in ("services", "oilfield")) or any(
        token in normalized_sector for token in ("services", "oilfield")
    ):
        return OilExposureClassification(
            oil_exposure_type="services",
            oil_support_status="unsupported",
            oil_support_reasons=tuple([*reasons, "oilfield_services_not_supported_v1"]),
        )

    if any(token in normalized_market_industry for token in ("pipeline", "midstream", "storage", "transport")):
        return OilExposureClassification(
            oil_exposure_type="midstream",
            oil_support_status="unsupported",
            oil_support_reasons=tuple([*reasons, "midstream_not_supported_v1"]),
        )

    if "refin" in normalized_market_industry or any(token in normalized_sector for token in ("refin", "downstream")):
        return OilExposureClassification(
            oil_exposure_type="refiner",
            oil_support_status="partial",
            oil_support_reasons=tuple([*reasons, "refining_margin_exposure_partial_v1"]),
        )

    if "integrated" in normalized_market_industry or "integrated" in normalized_sector or normalized_market_industry == "oil & gas":
        return OilExposureClassification(
            oil_exposure_type="integrated",
            oil_support_status="supported",
            oil_support_reasons=tuple([*reasons, "integrated_oil_supported_v1"]),
        )

    if any(token in combined for token in ("exploration", "production", "e&p", "upstream", "drilling")):
        return OilExposureClassification(
            oil_exposure_type="upstream",
            oil_support_status="supported",
            oil_support_reasons=tuple([*reasons, "upstream_oil_supported_v1"]),
        )

    return OilExposureClassification(
        oil_exposure_type="non_oil",
        oil_support_status="unsupported",
        oil_support_reasons=tuple([*reasons, "oil_taxonomy_unresolved_v1"]),
    )


def _normalize(value: str | None) -> str:
    return " ".join(str(value or "").strip().lower().split())


_ENERGY_TOKENS = (
    "energy",
    "oil",
    "gas",
    "petroleum",
    "pipeline",
    "refin",
    "drilling",
)