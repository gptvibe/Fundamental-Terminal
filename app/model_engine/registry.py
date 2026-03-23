from __future__ import annotations

from app.model_engine.models.altman_z import MODEL_NAME as ALTMAN_Z_NAME, MODEL_VERSION as ALTMAN_Z_VERSION, compute as compute_altman_z
from app.model_engine.models.capital_allocation import (
    MODEL_NAME as CAPITAL_ALLOCATION_NAME,
    MODEL_VERSION as CAPITAL_ALLOCATION_VERSION,
    compute as compute_capital_allocation,
)
from app.model_engine.models.dcf import MODEL_NAME as DCF_NAME, MODEL_VERSION as DCF_VERSION, compute as compute_dcf
from app.model_engine.models.dupont import MODEL_NAME as DUPONT_NAME, MODEL_VERSION as DUPONT_VERSION, compute as compute_dupont
from app.model_engine.models.piotroski import MODEL_NAME as PIOTROSKI_NAME, MODEL_VERSION as PIOTROSKI_VERSION, compute as compute_piotroski
from app.model_engine.models.ratios import MODEL_NAME as RATIOS_NAME, MODEL_VERSION as RATIOS_VERSION, compute as compute_ratios
from app.model_engine.models.reverse_dcf import (
    MODEL_NAME as REVERSE_DCF_NAME,
    MODEL_VERSION as REVERSE_DCF_VERSION,
    compute as compute_reverse_dcf,
)
from app.model_engine.models.roic import MODEL_NAME as ROIC_NAME, MODEL_VERSION as ROIC_VERSION, compute as compute_roic
from app.model_engine.models.residual_income import (
    MODEL_NAME as RESIDUAL_INCOME_NAME,
    MODEL_VERSION as RESIDUAL_INCOME_VERSION,
    compute as compute_residual_income,
)
from app.model_engine.types import ModelDefinition

MODEL_REGISTRY: dict[str, ModelDefinition] = {
    DCF_NAME: ModelDefinition(name=DCF_NAME, version=DCF_VERSION, compute=compute_dcf),
    DUPONT_NAME: ModelDefinition(name=DUPONT_NAME, version=DUPONT_VERSION, compute=compute_dupont),
    PIOTROSKI_NAME: ModelDefinition(name=PIOTROSKI_NAME, version=PIOTROSKI_VERSION, compute=compute_piotroski),
    ALTMAN_Z_NAME: ModelDefinition(name=ALTMAN_Z_NAME, version=ALTMAN_Z_VERSION, compute=compute_altman_z),
    RATIOS_NAME: ModelDefinition(name=RATIOS_NAME, version=RATIOS_VERSION, compute=compute_ratios),
    REVERSE_DCF_NAME: ModelDefinition(name=REVERSE_DCF_NAME, version=REVERSE_DCF_VERSION, compute=compute_reverse_dcf),
    ROIC_NAME: ModelDefinition(name=ROIC_NAME, version=ROIC_VERSION, compute=compute_roic),
    CAPITAL_ALLOCATION_NAME: ModelDefinition(name=CAPITAL_ALLOCATION_NAME, version=CAPITAL_ALLOCATION_VERSION, compute=compute_capital_allocation),
    RESIDUAL_INCOME_NAME: ModelDefinition(name=RESIDUAL_INCOME_NAME, version=RESIDUAL_INCOME_VERSION, compute=compute_residual_income),
}

CORE_MODEL_NAMES = [RATIOS_NAME, RESIDUAL_INCOME_NAME]
