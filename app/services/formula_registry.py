from __future__ import annotations

from dataclasses import dataclass
from typing import Any


FORMULA_REGISTRY_VERSION = "formula_registry_v1"
DERIVED_METRICS_FORMULA_VERSION = "sec_metrics_v3"
DERIVED_METRICS_MART_FORMULA_VERSION = "sec_metrics_mart_v2"
MODEL_OUTPUT_FORMULA_VERSION = "model_output_v1"

DERIVED_METRIC_KEYS = [
    "revenue_growth",
    "gross_margin",
    "operating_margin",
    "fcf_margin",
    "roic_proxy",
    "leverage_ratio",
    "current_ratio",
    "share_dilution",
    "sbc_burden",
    "buyback_yield",
    "dividend_yield",
    "working_capital_days",
    "accrual_ratio",
    "cash_conversion",
    "segment_concentration",
    "net_interest_margin",
    "provision_burden",
    "asset_quality_ratio",
    "cet1_ratio",
    "tier1_capital_ratio",
    "total_capital_ratio",
    "core_deposit_ratio",
    "uninsured_deposit_ratio",
    "tangible_book_value_per_share",
    "roatce",
]

MODEL_DEFAULT_INPUT_FIELDS: dict[str, list[str]] = {
    "dcf": [
        "free_cash_flow",
        "operating_cash_flow",
        "capex",
        "cash_and_short_term_investments",
        "current_debt",
        "long_term_debt",
        "weighted_average_diluted_shares",
        "shares_outstanding",
        "latest_price",
    ],
    "reverse_dcf": [
        "revenue",
        "free_cash_flow",
        "operating_cash_flow",
        "capex",
        "shares_outstanding",
        "weighted_average_diluted_shares",
        "latest_price",
    ],
    "roic": [
        "operating_income",
        "income_tax_expense",
        "pretax_income",
        "stockholders_equity",
        "current_debt",
        "long_term_debt",
        "cash_and_short_term_investments",
    ],
    "ratios": [
        "revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "operating_cash_flow",
        "free_cash_flow",
        "total_assets",
        "total_liabilities",
        "current_assets",
        "current_liabilities",
        "interest_expense",
    ],
    "piotroski": [
        "net_income",
        "operating_cash_flow",
        "total_assets",
        "current_assets",
        "current_liabilities",
        "shares_outstanding",
        "long_term_debt",
        "gross_profit",
        "revenue",
    ],
    "altman_z": [
        "total_assets",
        "total_liabilities",
        "current_assets",
        "current_liabilities",
        "retained_earnings",
        "operating_income",
        "revenue",
        "shares_outstanding",
        "weighted_average_diluted_shares",
        "latest_price",
    ],
}

MODEL_DEFAULT_SOURCE_PERIODS: dict[str, list[str]] = {
    "dcf": ["latest annual period plus trailing annual history"],
    "reverse_dcf": ["latest annual period plus trailing annual history", "latest market snapshot"],
    "roic": ["latest and previous annual periods"],
    "ratios": ["latest comparable filing and previous comparable filing"],
    "piotroski": ["latest annual filing and prior annual filings"],
    "altman_z": ["latest annual filing", "latest market snapshot"],
}

MODEL_DEFAULT_PROXY_FLAGS: dict[str, list[str]] = {
    "dcf": ["starting_cash_flow_proxied", "capital_structure_proxied", "share_count_proxied"],
    "reverse_dcf": ["starting_fcf_margin_proxied", "capital_structure_proxied", "share_count_proxied"],
    "roic": ["cash_balance_missing_uses_gross_capital_proxy"],
    "ratios": ["period_annualization_for_quarterly_stock_flow_ratios"],
    "piotroski": ["criteria_marked_unavailable_when_inputs_missing"],
    "altman_z": ["partial_when_required_factors_missing"],
}

MODEL_DEFAULT_MISSING_INPUT_BEHAVIOR: dict[str, str] = {
    "dcf": "Downgrades to partial/proxy/insufficient_data depending on missing FCF, capital-structure, and share-count inputs.",
    "reverse_dcf": "Returns unsupported/insufficient_data when required market or statement inputs are missing; uses proxy flags when fallback inputs are used.",
    "roic": "Returns insufficient_data when annual trend coverage is too thin; marks missing fields and proxy usage in output quality.",
    "ratios": "Per-ratio values become null when numerator or denominator inputs are missing; model status reflects aggregate coverage.",
    "piotroski": "Each criterion becomes unavailable when missing inputs prevent comparison; score scales by available criteria count.",
    "altman_z": "Missing factors yield partial output with z_score_approximate set to null.",
}


@dataclass(frozen=True, slots=True)
class FormulaMetadata:
    formula_id: str
    formula_version: str
    human_readable_formula: str
    input_fields: list[str]
    source_periods: list[str]
    proxy_fallback_flags: list[str]
    missing_input_behavior: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "formula_id": self.formula_id,
            "formula_version": self.formula_version,
            "human_readable_formula": self.human_readable_formula,
            "input_fields": list(self.input_fields),
            "source_periods": list(self.source_periods),
            "proxy_fallback_flags": list(self.proxy_fallback_flags),
            "missing_input_behavior": self.missing_input_behavior,
        }


_DERIVED_METRIC_FORMULAS: dict[str, FormulaMetadata] = {
    key: FormulaMetadata(
        formula_id=f"derived_metric.{key}.{DERIVED_METRICS_FORMULA_VERSION}",
        formula_version=DERIVED_METRICS_FORMULA_VERSION,
        human_readable_formula=(
            f"Derived metric '{key}' computed from canonical filing fields with cadence-aware semantics "
            "(quarterly annualization for select metrics, annual direct period values, or TTM aggregation)."
        ),
        input_fields=["statement.data", "price_history (when price-derived metric)", "share_count selection"],
        source_periods=["current period", "previous comparable period when required", "TTM rolling window when cadence=ttm"],
        proxy_fallback_flags=[
            "missing_price_context",
            "segment_data_unavailable",
            "low_metric_coverage",
            "bank_metric_inputs_partial",
            "ttm_missing_quarter",
            "ttm_restatement_ambiguity",
        ],
        missing_input_behavior="Returns null metric_value and sets quality flags/proxy markers when required inputs are unavailable.",
    )
    for key in DERIVED_METRIC_KEYS
}

_MODEL_SPECIFIC_FORMULAS: dict[tuple[str, str], FormulaMetadata] = {
    (
        "dcf",
        "fair_value_per_share",
    ): FormulaMetadata(
        formula_id=f"model.dcf.fair_value_per_share.{MODEL_OUTPUT_FORMULA_VERSION}",
        formula_version=MODEL_OUTPUT_FORMULA_VERSION,
        human_readable_formula="Fair value per share = (enterprise value - net debt) / selected share count, after discounted projected cash flows and terminal value.",
        input_fields=MODEL_DEFAULT_INPUT_FIELDS["dcf"],
        source_periods=MODEL_DEFAULT_SOURCE_PERIODS["dcf"],
        proxy_fallback_flags=MODEL_DEFAULT_PROXY_FLAGS["dcf"],
        missing_input_behavior=MODEL_DEFAULT_MISSING_INPUT_BEHAVIOR["dcf"],
    ),
    (
        "reverse_dcf",
        "implied_growth",
    ): FormulaMetadata(
        formula_id=f"model.reverse_dcf.implied_growth.{MODEL_OUTPUT_FORMULA_VERSION}",
        formula_version=MODEL_OUTPUT_FORMULA_VERSION,
        human_readable_formula="Implied growth is solved by bisection so discounted projected cash flows match the target enterprise value implied by market inputs.",
        input_fields=MODEL_DEFAULT_INPUT_FIELDS["reverse_dcf"],
        source_periods=MODEL_DEFAULT_SOURCE_PERIODS["reverse_dcf"],
        proxy_fallback_flags=MODEL_DEFAULT_PROXY_FLAGS["reverse_dcf"],
        missing_input_behavior=MODEL_DEFAULT_MISSING_INPUT_BEHAVIOR["reverse_dcf"],
    ),
    (
        "roic",
        "roic",
    ): FormulaMetadata(
        formula_id=f"model.roic.roic.{MODEL_OUTPUT_FORMULA_VERSION}",
        formula_version=MODEL_OUTPUT_FORMULA_VERSION,
        human_readable_formula="ROIC = NOPAT / invested capital, with tax-rate proxying when explicit tax rate is unavailable.",
        input_fields=MODEL_DEFAULT_INPUT_FIELDS["roic"],
        source_periods=MODEL_DEFAULT_SOURCE_PERIODS["roic"],
        proxy_fallback_flags=MODEL_DEFAULT_PROXY_FLAGS["roic"],
        missing_input_behavior=MODEL_DEFAULT_MISSING_INPUT_BEHAVIOR["roic"],
    ),
    (
        "piotroski",
        "score",
    ): FormulaMetadata(
        formula_id=f"model.piotroski.score.{MODEL_OUTPUT_FORMULA_VERSION}",
        formula_version=MODEL_OUTPUT_FORMULA_VERSION,
        human_readable_formula="Piotroski score sums nine binary criteria, with normalized scaling based on available criteria.",
        input_fields=MODEL_DEFAULT_INPUT_FIELDS["piotroski"],
        source_periods=MODEL_DEFAULT_SOURCE_PERIODS["piotroski"],
        proxy_fallback_flags=MODEL_DEFAULT_PROXY_FLAGS["piotroski"],
        missing_input_behavior=MODEL_DEFAULT_MISSING_INPUT_BEHAVIOR["piotroski"],
    ),
    (
        "altman_z",
        "z_score_approximate",
    ): FormulaMetadata(
        formula_id=f"model.altman_z.z_score_approximate.{MODEL_OUTPUT_FORMULA_VERSION}",
        formula_version=MODEL_OUTPUT_FORMULA_VERSION,
        human_readable_formula="Altman Z (1968 public variant) = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5 with annual inputs and market-value equity for X4.",
        input_fields=MODEL_DEFAULT_INPUT_FIELDS["altman_z"],
        source_periods=MODEL_DEFAULT_SOURCE_PERIODS["altman_z"],
        proxy_fallback_flags=MODEL_DEFAULT_PROXY_FLAGS["altman_z"],
        missing_input_behavior=MODEL_DEFAULT_MISSING_INPUT_BEHAVIOR["altman_z"],
    ),
}


def formula_id_for_derived_metric(metric_key: str) -> str:
    key = str(metric_key or "").strip()
    if not key:
        return f"derived_metric.unknown.{DERIVED_METRICS_FORMULA_VERSION}"
    return f"derived_metric.{key}.{DERIVED_METRICS_FORMULA_VERSION}"


def formula_ids_for_derived_metrics(metric_keys: list[str]) -> dict[str, str]:
    return {
        key: formula_id_for_derived_metric(key)
        for key in metric_keys
        if isinstance(key, str) and key.strip()
    }


def _sanitize_output_key(output_key: str) -> str:
    chars = []
    for char in output_key.lower():
        if char.isalnum():
            chars.append(char)
        elif char in {".", "_"}:
            chars.append("_")
    normalized = "".join(chars).strip("_")
    return normalized or "value"


def formula_id_for_model_output(model_name: str, output_key: str) -> str:
    normalized_model = str(model_name or "").strip().lower() or "model"
    normalized_key = _sanitize_output_key(output_key)
    return f"model.{normalized_model}.{normalized_key}.{MODEL_OUTPUT_FORMULA_VERSION}"


def _is_model_output_field(key: str) -> bool:
    excluded = {
        "status",
        "model_status",
        "explanation",
        "confidence_score",
        "confidence_summary",
        "confidence_reasons",
        "status_flags",
        "fields_used",
        "proxy_usage",
        "stale_inputs",
        "sector_suitability",
        "misleading_reasons",
        "calculation_version",
        "model_name",
        "model_version",
    }
    return key not in excluded


def formula_ids_for_model_result(model_name: str, result: dict[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    for key, value in result.items():
        if not _is_model_output_field(key):
            continue
        if key == "values" and isinstance(value, dict):
            for sub_key in value.keys():
                path = f"values.{sub_key}"
                output[path] = formula_id_for_model_output(model_name, path)
            continue
        output[key] = formula_id_for_model_output(model_name, key)
    return output


def _default_model_formula_metadata(model_name: str, output_key: str, formula_id: str) -> FormulaMetadata:
    normalized_model = str(model_name or "").strip().lower() or "model"
    return FormulaMetadata(
        formula_id=formula_id,
        formula_version=MODEL_OUTPUT_FORMULA_VERSION,
        human_readable_formula=(
            f"Model output '{output_key}' computed by {normalized_model} model logic using normalized company inputs, "
            "with status, proxy, and missing-input guards applied by the model engine."
        ),
        input_fields=list(MODEL_DEFAULT_INPUT_FIELDS.get(normalized_model, ["model_input_periods", "market_snapshot"])) ,
        source_periods=list(MODEL_DEFAULT_SOURCE_PERIODS.get(normalized_model, ["model-selected comparable periods"])),
        proxy_fallback_flags=list(MODEL_DEFAULT_PROXY_FLAGS.get(normalized_model, ["proxy_output", "partial_inputs"])),
        missing_input_behavior=MODEL_DEFAULT_MISSING_INPUT_BEHAVIOR.get(
            normalized_model,
            "Returns downgraded status and null output for fields whose required inputs are missing.",
        ),
    )


def get_formula_metadata(formula_id: str) -> FormulaMetadata | None:
    fid = str(formula_id or "").strip()
    if not fid:
        return None

    for metadata in _DERIVED_METRIC_FORMULAS.values():
        if metadata.formula_id == fid:
            return metadata

    for metadata in _MODEL_SPECIFIC_FORMULAS.values():
        if metadata.formula_id == fid:
            return metadata

    if fid.startswith("derived_metric.") and fid.count(".") >= 2:
        parts = fid.split(".")
        key = parts[1]
        return FormulaMetadata(
            formula_id=fid,
            formula_version=parts[-1],
            human_readable_formula=f"Derived metric '{key}' computed from filing inputs using cadence-aware metric semantics.",
            input_fields=["statement.data", "price_history (optional)", "share_count selection"],
            source_periods=["current period", "previous comparable period when required"],
            proxy_fallback_flags=["low_metric_coverage", "missing_price_context"],
            missing_input_behavior="Missing inputs produce null metric values with quality flags.",
        )

    if fid.startswith("model.") and fid.count(".") >= 3:
        parts = fid.split(".")
        model_name = parts[1]
        output_key = ".".join(parts[2:-1]).replace("_", ".")
        return _default_model_formula_metadata(model_name, output_key, fid)

    return None


def serialize_formula_metadata(metadata: FormulaMetadata, *, include_details: bool) -> dict[str, Any]:
    payload = {
        "formula_id": metadata.formula_id,
        "formula_version": metadata.formula_version,
        "human_readable_formula": metadata.human_readable_formula,
    }
    if include_details:
        payload.update(
            {
                "input_fields": metadata.input_fields,
                "source_periods": metadata.source_periods,
                "proxy_fallback_flags": metadata.proxy_fallback_flags,
                "missing_input_behavior": metadata.missing_input_behavior,
            }
        )
    return payload


def list_formula_metadata(*, formula_ids: list[str] | None = None, include_details: bool = False) -> list[dict[str, Any]]:
    resolved_ids: list[str]
    if formula_ids is None:
        resolved_ids = sorted(
            {
                *[item.formula_id for item in _DERIVED_METRIC_FORMULAS.values()],
                *[item.formula_id for item in _MODEL_SPECIFIC_FORMULAS.values()],
            }
        )
    else:
        resolved_ids = [item for item in formula_ids if isinstance(item, str) and item.strip()]

    payloads: list[dict[str, Any]] = []
    for fid in resolved_ids:
        metadata = get_formula_metadata(fid)
        if metadata is None:
            continue
        payloads.append(serialize_formula_metadata(metadata, include_details=include_details))
    return payloads
