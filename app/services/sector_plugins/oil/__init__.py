"""Oil sector plugin for Fundamental Terminal.

This package groups all oil-specific scenario logic under the sector_plugins
namespace. The oil plugin is disabled by default; set ENABLE_OIL_SCENARIOS=true
to activate it.

Public re-exports keep backward-compatible import paths intact while giving the
plugin its own discoverable namespace under app/services/sector_plugins/oil/.
"""

from __future__ import annotations

from app.services.oil_company_evidence import collect_company_oil_evidence
from app.services.oil_exposure import (
    OilExposureClassification,
    OilExposureType,
    OilSupportStatus,
    classify_company_oil_exposure,
    classify_oil_exposure,
)
from app.services.oil_overlay_engine import (
    OilCurveYearPoint,
    OilOverlayDiscountAssumptions,
    OilOverlayEngineInputs,
    OilOverlayEngineResult,
    OilOverlayModelStatus,
    OilOverlayYearResult,
    compute_oil_fair_value_overlay,
    compute_oil_fair_value_overlay_payload,
)
from app.services.oil_scenario import build_company_oil_scenario_public_payload
from app.services.oil_scenario_overlay import (
    build_company_oil_scenario_overlay_placeholder,
    get_company_oil_scenario_overlay,
    get_company_oil_scenario_overlay_last_checked,
)
from app.services.official_oil_inputs import (
    OfficialOilInputsDTO,
    OfficialOilInputsStatus,
    OfficialOilPointDTO,
    OfficialOilSeriesDTO,
    fetch_official_oil_inputs,
)

__all__ = [
    # Evidence
    "collect_company_oil_evidence",
    # Exposure classification
    "OilExposureClassification",
    "OilExposureType",
    "OilSupportStatus",
    "classify_company_oil_exposure",
    "classify_oil_exposure",
    # Overlay engine
    "OilCurveYearPoint",
    "OilOverlayDiscountAssumptions",
    "OilOverlayEngineInputs",
    "OilOverlayEngineResult",
    "OilOverlayModelStatus",
    "OilOverlayYearResult",
    "compute_oil_fair_value_overlay",
    "compute_oil_fair_value_overlay_payload",
    # Scenario
    "build_company_oil_scenario_public_payload",
    # Overlay persistence
    "build_company_oil_scenario_overlay_placeholder",
    "get_company_oil_scenario_overlay",
    "get_company_oil_scenario_overlay_last_checked",
    # Official inputs
    "OfficialOilInputsDTO",
    "OfficialOilInputsStatus",
    "OfficialOilPointDTO",
    "OfficialOilSeriesDTO",
    "fetch_official_oil_inputs",
]
