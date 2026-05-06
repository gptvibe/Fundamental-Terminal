"""Companyfacts normalization utilities and tag mappings."""

from app.services.sec.refresh_orchestrator import (
    CANONICAL_FACTS,
    CAPEX_FACTS,
    DEBT_ISSUANCE_FACTS,
    DEBT_REPAYMENT_FACTS,
    SEGMENT_SUPPLEMENTAL_TAGS,
    SUPPLEMENTAL_CAPITAL_STRUCTURE_FACTS,
    _iter_fact_observations,
    _iter_monetary_observations,
    _iter_ratio_observations,
    _iter_share_observations,
)

__all__ = [
    "CANONICAL_FACTS",
    "SEGMENT_SUPPLEMENTAL_TAGS",
    "CAPEX_FACTS",
    "DEBT_ISSUANCE_FACTS",
    "DEBT_REPAYMENT_FACTS",
    "SUPPLEMENTAL_CAPITAL_STRUCTURE_FACTS",
    "_iter_fact_observations",
    "_iter_monetary_observations",
    "_iter_ratio_observations",
    "_iter_share_observations",
]
