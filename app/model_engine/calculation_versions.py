from __future__ import annotations

DCF_CALCULATION_VERSION = "dcf_ev_bridge_v1"
REVERSE_DCF_CALCULATION_VERSION = "reverse_dcf_ev_target_v1"
PIOTROSKI_CALCULATION_VERSION = "piotroski_ratio_scale_v1"

MODEL_CALCULATION_VERSIONS: dict[str, str] = {
    "dcf": DCF_CALCULATION_VERSION,
    "reverse_dcf": REVERSE_DCF_CALCULATION_VERSION,
    "piotroski": PIOTROSKI_CALCULATION_VERSION,
}


def get_model_calculation_version(model_name: str) -> str | None:
    return MODEL_CALCULATION_VERSIONS.get(model_name.lower())


def has_current_calculation_version(model_name: str, calculation_version: str | None) -> bool:
    expected = get_model_calculation_version(model_name)
    if expected is None:
        return True
    return calculation_version == expected