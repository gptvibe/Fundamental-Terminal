from __future__ import annotations

from dataclasses import dataclass
from typing import Any


FORMULA_REGISTRY_VERSION = "formula_registry_v1"
DERIVED_METRICS_FORMULA_VERSION = "sec_metrics_v4"
DERIVED_METRICS_MART_FORMULA_VERSION = "sec_metrics_mart_v2"
MODEL_OUTPUT_FORMULA_VERSION = "model_output_v1"

_NESTED_MODEL_OUTPUT_PREFIXES = ("values", "intrinsic_value")

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
    "capital_allocation": [
        "dividends",
        "share_buybacks",
        "debt_changes",
        "stock_based_compensation",
        "latest_price",
        "shares_outstanding",
        "weighted_average_diluted_shares",
    ],
    "dupont": [
        "net_income",
        "revenue",
        "total_assets",
        "total_liabilities",
        "stockholders_equity",
    ],
    "residual_income": [
        "total_assets",
        "total_liabilities",
        "stockholders_equity",
        "net_income",
        "net_income_loss",
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
    "capital_allocation": ["latest three annual filings", "latest market snapshot"],
    "dupont": ["latest annual filing or trailing four comparable quarters", "previous comparable filing"],
    "residual_income": ["latest annual filing plus trailing annual history", "latest market snapshot"],
}

MODEL_DEFAULT_PROXY_FLAGS: dict[str, list[str]] = {
    "dcf": ["starting_cash_flow_proxied", "capital_structure_proxied", "share_count_proxied"],
    "reverse_dcf": ["starting_fcf_margin_proxied", "capital_structure_proxied", "share_count_proxied"],
    "roic": ["cash_balance_missing_uses_gross_capital_proxy"],
    "ratios": ["period_annualization_for_quarterly_stock_flow_ratios"],
    "piotroski": ["criteria_marked_unavailable_when_inputs_missing"],
    "altman_z": ["partial_when_required_factors_missing"],
    "capital_allocation": ["share_count_proxied", "market_cap_proxy_used", "missing_cash_return_components"],
    "dupont": ["ttm_bridge_used_when_annual_unavailable", "average_balance_sheet_proxy_used"],
    "residual_income": ["book_equity_proxy_from_stockholders_equity", "share_count_proxied"],
}

MODEL_DEFAULT_MISSING_INPUT_BEHAVIOR: dict[str, str] = {
    "dcf": "Downgrades to partial/proxy/insufficient_data depending on missing FCF, capital-structure, and share-count inputs.",
    "reverse_dcf": "Returns unsupported/insufficient_data when required market or statement inputs are missing; uses proxy flags when fallback inputs are used.",
    "roic": "Returns insufficient_data when annual trend coverage is too thin; marks missing fields and proxy usage in output quality.",
    "ratios": "Per-ratio values become null when numerator or denominator inputs are missing; model status reflects aggregate coverage.",
    "piotroski": "Each criterion becomes unavailable when missing inputs prevent comparison; score scales by available criteria count.",
    "altman_z": "Missing factors yield partial output with z_score_approximate set to null.",
    "capital_allocation": "Missing capital-return fields reduce confidence and can null shareholder-yield outputs when market-cap inputs are unavailable.",
    "dupont": "Returns insufficient_data when neither annual nor rolling comparable-quarter coverage is available; partial output leaves DuPont factors null.",
    "residual_income": "Returns insufficient_data when book equity, net income, or share-count inputs are missing; proxy use is disclosed in data-quality fields.",
}

_DERIVED_METRIC_DEFINITIONS: dict[str, dict[str, Any]] = {
    "revenue_growth": {
        "formula": "Revenue growth = (current revenue - previous comparable revenue) / previous comparable revenue.",
        "input_fields": ["revenue"],
        "source_periods": ["current comparable period", "previous comparable period"],
        "proxy_fallback_flags": ["low_metric_coverage", "ttm_missing_quarter", "ttm_restatement_ambiguity"],
    },
    "gross_margin": {
        "formula": "Gross margin = gross_profit / revenue.",
        "input_fields": ["gross_profit", "revenue"],
        "source_periods": ["current period", "TTM rolling window when cadence=ttm"],
        "proxy_fallback_flags": ["low_metric_coverage", "ttm_missing_quarter", "ttm_restatement_ambiguity"],
    },
    "operating_margin": {
        "formula": "Operating margin = operating_income / revenue.",
        "input_fields": ["operating_income", "revenue"],
        "source_periods": ["current period", "TTM rolling window when cadence=ttm"],
        "proxy_fallback_flags": ["low_metric_coverage", "ttm_missing_quarter", "ttm_restatement_ambiguity"],
    },
    "fcf_margin": {
        "formula": "Free-cash-flow margin = free_cash_flow / revenue.",
        "input_fields": ["free_cash_flow", "revenue"],
        "source_periods": ["current period", "TTM rolling window when cadence=ttm"],
        "proxy_fallback_flags": ["low_metric_coverage", "ttm_missing_quarter", "ttm_restatement_ambiguity"],
    },
    "roic_proxy": {
        "formula": "ROIC proxy = operating_income x (1 - tax-rate proxy) / (stockholders_equity + debt - cash and short-term investments).",
        "input_fields": [
            "operating_income",
            "income_tax_expense",
            "pretax_income",
            "stockholders_equity",
            "current_debt",
            "long_term_debt",
            "cash_and_short_term_investments",
        ],
        "source_periods": ["current period", "previous comparable period when annualized tax proxy is required"],
        "proxy_fallback_flags": ["low_metric_coverage", "bank_metric_inputs_partial"],
    },
    "leverage_ratio": {
        "formula": "Leverage ratio = (current_debt + long_term_debt) / stockholders_equity.",
        "input_fields": ["current_debt", "long_term_debt", "stockholders_equity"],
        "source_periods": ["current period"],
        "proxy_fallback_flags": ["low_metric_coverage"],
    },
    "current_ratio": {
        "formula": "Current ratio = current_assets / current_liabilities.",
        "input_fields": ["current_assets", "current_liabilities"],
        "source_periods": ["current period"],
        "proxy_fallback_flags": ["low_metric_coverage"],
    },
    "share_dilution": {
        "formula": "Share dilution = (current selected share count - previous comparable selected share count) / previous comparable selected share count.",
        "input_fields": ["weighted_average_diluted_shares", "shares_outstanding"],
        "source_periods": ["current comparable period", "previous comparable period"],
        "proxy_fallback_flags": ["low_metric_coverage", "missing_price_context"],
    },
    "sbc_burden": {
        "formula": "SBC burden = stock_based_compensation / revenue.",
        "input_fields": ["stock_based_compensation", "revenue"],
        "source_periods": ["current period", "TTM rolling window when cadence=ttm"],
        "proxy_fallback_flags": ["low_metric_coverage", "ttm_missing_quarter"],
    },
    "buyback_yield": {
        "formula": "Buyback yield = share_buybacks / market capitalization using the matched price date and selected share count.",
        "input_fields": ["share_buybacks", "price_history.close", "weighted_average_diluted_shares", "shares_outstanding"],
        "source_periods": ["current period", "matched market snapshot on or before period end"],
        "proxy_fallback_flags": ["missing_price_context", "low_metric_coverage"],
    },
    "dividend_yield": {
        "formula": "Dividend yield = dividends / market capitalization using the matched price date and selected share count.",
        "input_fields": ["dividends", "price_history.close", "weighted_average_diluted_shares", "shares_outstanding"],
        "source_periods": ["current period", "matched market snapshot on or before period end"],
        "proxy_fallback_flags": ["missing_price_context", "low_metric_coverage"],
    },
    "working_capital_days": {
        "formula": "Working-capital days = 365 x ((accounts_receivable + inventory - accounts_payable) / revenue).",
        "input_fields": ["accounts_receivable", "inventory", "accounts_payable", "revenue"],
        "source_periods": ["current period", "TTM rolling window when cadence=ttm"],
        "proxy_fallback_flags": ["low_metric_coverage"],
    },
    "accrual_ratio": {
        "formula": "Accrual ratio = (net_income - operating_cash_flow) / total_assets.",
        "input_fields": ["net_income", "operating_cash_flow", "total_assets"],
        "source_periods": ["current period", "TTM rolling window when cadence=ttm"],
        "proxy_fallback_flags": ["low_metric_coverage", "ttm_missing_quarter"],
    },
    "cash_conversion": {
        "formula": "Cash conversion = operating_cash_flow / net_income.",
        "input_fields": ["operating_cash_flow", "net_income"],
        "source_periods": ["current period", "TTM rolling window when cadence=ttm"],
        "proxy_fallback_flags": ["low_metric_coverage", "ttm_missing_quarter"],
    },
    "segment_concentration": {
        "formula": "Segment concentration = largest reported segment revenue / total revenue.",
        "input_fields": ["segment_breakdown", "revenue"],
        "source_periods": ["current period"],
        "proxy_fallback_flags": ["segment_data_unavailable", "low_metric_coverage"],
    },
    "net_interest_margin": {
        "formula": "Net interest margin = net_interest_income / average earning-assets proxy.",
        "input_fields": ["net_interest_income", "average_earning_assets", "total_assets"],
        "source_periods": ["current period", "previous comparable period for average-balance proxy"],
        "proxy_fallback_flags": ["bank_metric_inputs_partial", "low_metric_coverage"],
    },
    "provision_burden": {
        "formula": "Provision burden = provision_for_credit_losses / net_interest_income.",
        "input_fields": ["provision_for_credit_losses", "net_interest_income"],
        "source_periods": ["current period", "TTM rolling window when cadence=ttm"],
        "proxy_fallback_flags": ["bank_metric_inputs_partial", "low_metric_coverage"],
    },
    "asset_quality_ratio": {
        "formula": "Asset quality ratio = nonperforming assets proxy / total assets.",
        "input_fields": ["nonperforming_assets", "allowance_for_credit_losses", "total_assets"],
        "source_periods": ["current period"],
        "proxy_fallback_flags": ["bank_metric_inputs_partial", "low_metric_coverage"],
    },
    "cet1_ratio": {
        "formula": "CET1 ratio = common_equity_tier_1_capital / risk_weighted_assets.",
        "input_fields": ["common_equity_tier_1_capital", "risk_weighted_assets"],
        "source_periods": ["current regulatory period"],
        "proxy_fallback_flags": ["bank_metric_inputs_partial", "low_metric_coverage"],
    },
    "tier1_capital_ratio": {
        "formula": "Tier 1 capital ratio = tier_1_capital / risk_weighted_assets.",
        "input_fields": ["tier_1_capital", "risk_weighted_assets"],
        "source_periods": ["current regulatory period"],
        "proxy_fallback_flags": ["bank_metric_inputs_partial", "low_metric_coverage"],
    },
    "total_capital_ratio": {
        "formula": "Total capital ratio = total_risk_based_capital / risk_weighted_assets.",
        "input_fields": ["total_risk_based_capital", "risk_weighted_assets"],
        "source_periods": ["current regulatory period"],
        "proxy_fallback_flags": ["bank_metric_inputs_partial", "low_metric_coverage"],
    },
    "core_deposit_ratio": {
        "formula": "Core deposit ratio = core_deposits / total_deposits.",
        "input_fields": ["core_deposits", "total_deposits"],
        "source_periods": ["current regulatory period"],
        "proxy_fallback_flags": ["bank_metric_inputs_partial", "low_metric_coverage"],
    },
    "uninsured_deposit_ratio": {
        "formula": "Uninsured deposit ratio = uninsured_deposits / total_deposits.",
        "input_fields": ["uninsured_deposits", "total_deposits"],
        "source_periods": ["current regulatory period"],
        "proxy_fallback_flags": ["bank_metric_inputs_partial", "low_metric_coverage"],
    },
    "tangible_book_value_per_share": {
        "formula": "Tangible book value per share = tangible_common_equity / selected diluted share count.",
        "input_fields": ["tangible_common_equity", "weighted_average_diluted_shares", "shares_outstanding"],
        "source_periods": ["current regulatory period"],
        "proxy_fallback_flags": ["bank_metric_inputs_partial", "missing_price_context"],
    },
    "roatce": {
        "formula": "ROATCE = annualized net income available to common / average tangible common equity.",
        "input_fields": ["net_income", "tangible_common_equity"],
        "source_periods": ["current comparable period", "previous comparable period for average-equity proxy"],
        "proxy_fallback_flags": ["bank_metric_inputs_partial", "ttm_missing_quarter"],
    },
}

_MODEL_EXPLAINABLE_OUTPUTS: dict[str, set[str]] = {
    "dcf": {
        "enterprise_value",
        "equity_value",
        "fair_value_per_share",
        "present_value_of_cash_flows",
        "terminal_value_present_value",
        "net_debt",
        "total_debt",
    },
    "reverse_dcf": {
        "implied_growth",
        "implied_margin",
        "target_enterprise_value",
        "market_cap",
        "net_debt",
        "current_operating_margin",
    },
    "roic": {
        "capital_cost_proxy",
        "incremental_roic",
        "reinvestment_rate",
        "roic",
        "spread_vs_capital_cost_proxy",
    },
    "piotroski": {"score", "score_on_9_point_scale", "normalized_score_ratio"},
    "altman_z": {"market_value_equity", "z_score_approximate"},
    "dupont": {
        "asset_turnover",
        "average_assets",
        "average_equity",
        "equity_multiplier",
        "net_profit_margin",
        "return_on_equity",
    },
    "capital_allocation": {
        "annualized_shareholder_distribution",
        "cumulative_shareholder_distribution_ratio",
        "debt_financing_signal",
        "net_shareholder_distribution",
        "shareholder_yield",
    },
}

_MODEL_NESTED_EXPLAINABLE_OUTPUTS: dict[str, set[str]] = {
    "ratios": {"values"},
    "residual_income": {"intrinsic_value"},
}

_MODEL_OUTPUT_FORMULA_STRINGS: dict[tuple[str, str], str] = {
    ("dcf", "enterprise_value"): "Enterprise value = present value of projected free cash flows + present value of terminal value.",
    ("dcf", "equity_value"): "Equity value = enterprise value - net debt bridge.",
    ("dcf", "fair_value_per_share"): "Fair value per share = (enterprise value - net debt) / selected share count, after discounted projected cash flows and terminal value.",
    ("dcf", "present_value_of_cash_flows"): "Present value of cash flows = sum(projected free cash flow_t / (1 + discount_rate)^t).",
    ("dcf", "terminal_value_present_value"): "Present value of terminal value = terminal value / (1 + discount_rate)^N.",
    ("dcf", "net_debt"): "Net debt = total debt - cash and short-term investments.",
    ("dcf", "total_debt"): "Total debt = current debt + long-term debt.",
    ("reverse_dcf", "implied_growth"): "Implied growth is solved by bisection so discounted projected cash flows match the target enterprise value implied by market inputs.",
    ("reverse_dcf", "implied_margin"): "Implied margin is the operating margin that balances discounted projected cash flows to the target enterprise value.",
    ("reverse_dcf", "target_enterprise_value"): "Target enterprise value = market capitalization + net debt bridge.",
    ("reverse_dcf", "market_cap"): "Market capitalization = latest price x selected share count.",
    ("reverse_dcf", "net_debt"): "Net debt = total debt - cash and short-term investments.",
    ("reverse_dcf", "current_operating_margin"): "Current operating margin = operating income / revenue.",
    ("roic", "capital_cost_proxy"): "Capital-cost proxy = risk-free rate + fixed equity-risk premium.",
    ("roic", "incremental_roic"): "Incremental ROIC = delta NOPAT / delta invested capital across comparable annual periods.",
    ("roic", "reinvestment_rate"): "Reinvestment rate = capital reinvested / NOPAT proxy.",
    ("roic", "roic"): "ROIC = NOPAT / invested capital, with tax-rate proxying when explicit tax rate is unavailable.",
    ("roic", "spread_vs_capital_cost_proxy"): "ROIC spread = ROIC - capital-cost proxy.",
    ("piotroski", "score"): "Piotroski score = sum of the nine available binary Piotroski criteria.",
    ("piotroski", "score_on_9_point_scale"): "Nine-point Piotroski scale = normalized score ratio x 9.",
    ("piotroski", "normalized_score_ratio"): "Normalized Piotroski score ratio = available positive criteria / available criteria count.",
    ("altman_z", "market_value_equity"): "Market-value equity = latest price x selected share count.",
    ("altman_z", "z_score_approximate"): "Altman Z (1968 public variant) = 1.2xX1 + 1.4xX2 + 3.3xX3 + 0.6xX4 + 1.0xX5.",
    ("dupont", "net_profit_margin"): "Net profit margin = net income / revenue.",
    ("dupont", "asset_turnover"): "Asset turnover = revenue / average total assets.",
    ("dupont", "equity_multiplier"): "Equity multiplier = average total assets / average equity.",
    ("dupont", "return_on_equity"): "Return on equity = net profit margin x asset turnover x equity multiplier.",
    ("dupont", "average_assets"): "Average assets = mean(current total assets, previous comparable total assets).",
    ("dupont", "average_equity"): "Average equity = mean(current book equity, previous comparable book equity).",
    ("capital_allocation", "shareholder_yield"): "Shareholder yield = annualized net shareholder distribution / latest market capitalization.",
    ("capital_allocation", "net_shareholder_distribution"): "Net shareholder distribution = dividends + share buybacks - stock-based compensation.",
    ("capital_allocation", "annualized_shareholder_distribution"): "Annualized shareholder distribution = cumulative net shareholder distribution / periods used.",
    ("capital_allocation", "cumulative_shareholder_distribution_ratio"): "Cumulative shareholder-distribution ratio = cumulative net shareholder distribution / latest market capitalization.",
    ("capital_allocation", "debt_financing_signal"): "Debt-financing signal = cumulative debt_changes across the evaluation window.",
    ("residual_income", "intrinsic_value.book_equity_per_share"): "Book-equity per share = current book equity / selected share count.",
    ("residual_income", "intrinsic_value.pv_residual_income_per_share"): "PV residual-income per share = discounted projected residual-income stream / selected share count.",
    ("residual_income", "intrinsic_value.terminal_value_per_share"): "Terminal value per share = terminal residual-income value / selected share count.",
    ("residual_income", "intrinsic_value.intrinsic_value_per_share"): "Intrinsic value per share = book-equity per share + PV residual-income per share + terminal-value per share.",
    ("residual_income", "intrinsic_value.upside_vs_price"): "Upside vs price = (intrinsic value per share - latest price) / latest price.",
}

_RATIO_OUTPUT_FORMULA_STRINGS: dict[str, str] = {
    "asset_turnover": "Asset turnover = revenue / average total assets proxy.",
    "capex_intensity": "Capex intensity = capex / revenue.",
    "cash_conversion": "Cash conversion = operating_cash_flow / net_income.",
    "equity_ratio": "Equity ratio = stockholders_equity / total_assets.",
    "free_cash_flow_growth": "Free-cash-flow growth = (current free_cash_flow - previous comparable free_cash_flow) / previous comparable free_cash_flow.",
    "free_cash_flow_margin": "Free-cash-flow margin = free_cash_flow / revenue.",
    "gross_margin": "Gross margin = gross_profit / revenue.",
    "interest_coverage": "Interest coverage = operating_income / absolute interest_expense.",
    "liabilities_to_assets": "Liabilities to assets = total_liabilities / total_assets.",
    "net_debt_to_fcf": "Net debt to FCF = (current_debt + long_term_debt - cash and short-term investments) / free_cash_flow.",
    "net_income_growth": "Net-income growth = (current net_income - previous comparable net_income) / previous comparable net_income.",
    "net_margin": "Net margin = net_income / revenue.",
    "operating_cash_flow_margin": "Operating-cash-flow margin = operating_cash_flow / revenue.",
    "operating_margin": "Operating margin = operating_income / revenue.",
    "payout_ratio": "Payout ratio = dividends / net_income.",
    "return_on_assets": "Return on assets = net_income / average total assets proxy.",
    "return_on_equity": "Return on equity = net_income / average stockholders_equity proxy.",
    "revenue_growth": "Revenue growth = (current revenue - previous comparable revenue) / previous comparable revenue.",
    "sbc_to_revenue": "SBC to revenue = stock_based_compensation / revenue.",
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
        human_readable_formula=str(definition["formula"]),
        input_fields=list(definition["input_fields"]),
        source_periods=list(definition["source_periods"]),
        proxy_fallback_flags=list(definition["proxy_fallback_flags"]),
        missing_input_behavior="Returns null metric_value and sets quality flags/proxy markers when required inputs are unavailable.",
    )
    for key, definition in _DERIVED_METRIC_DEFINITIONS.items()
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


def _restore_output_key(normalized_output_key: str) -> str:
    normalized = str(normalized_output_key or "").strip("_")
    if not normalized:
        return "value"

    for prefix in _NESTED_MODEL_OUTPUT_PREFIXES:
        token = f"{prefix}_"
        if normalized.startswith(token):
            return f"{prefix}.{normalized[len(token):]}"

    return normalized


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


def _is_explainable_model_output(model_name: str, output_key: str) -> bool:
    normalized_model = str(model_name or "").strip().lower()
    if output_key in _MODEL_EXPLAINABLE_OUTPUTS.get(normalized_model, set()):
        return True

    for prefix in _MODEL_NESTED_EXPLAINABLE_OUTPUTS.get(normalized_model, set()):
        if output_key.startswith(f"{prefix}."):
            return True

    return False


def formula_ids_for_model_result(model_name: str, result: dict[str, Any]) -> dict[str, str]:
    output: dict[str, str] = {}
    normalized_model = str(model_name or "").strip().lower()
    for key, value in result.items():
        if not _is_model_output_field(key):
            continue
        if key in _MODEL_NESTED_EXPLAINABLE_OUTPUTS.get(normalized_model, set()) and isinstance(value, dict):
            for sub_key in value.keys():
                path = f"{key}.{sub_key}"
                if _is_explainable_model_output(normalized_model, path):
                    output[path] = formula_id_for_model_output(model_name, path)
            continue
        if normalized_model in _MODEL_EXPLAINABLE_OUTPUTS or normalized_model in _MODEL_NESTED_EXPLAINABLE_OUTPUTS:
            if _is_explainable_model_output(normalized_model, key):
                output[key] = formula_id_for_model_output(model_name, key)
            continue
        output[key] = formula_id_for_model_output(model_name, key)
    return output


def _build_model_specific_formulas() -> dict[tuple[str, str], FormulaMetadata]:
    formulas: dict[tuple[str, str], FormulaMetadata] = {}
    all_formula_strings = dict(_MODEL_OUTPUT_FORMULA_STRINGS)
    all_formula_strings.update(
        {
            ("ratios", f"values.{output_key}"): formula
            for output_key, formula in _RATIO_OUTPUT_FORMULA_STRINGS.items()
        }
    )

    for (model_name, output_key), human_formula in all_formula_strings.items():
        formulas[(model_name, output_key)] = FormulaMetadata(
            formula_id=formula_id_for_model_output(model_name, output_key),
            formula_version=MODEL_OUTPUT_FORMULA_VERSION,
            human_readable_formula=human_formula,
            input_fields=list(MODEL_DEFAULT_INPUT_FIELDS.get(model_name, ["model_input_periods", "market_snapshot"])),
            source_periods=list(MODEL_DEFAULT_SOURCE_PERIODS.get(model_name, ["model-selected comparable periods"])),
            proxy_fallback_flags=list(MODEL_DEFAULT_PROXY_FLAGS.get(model_name, ["proxy_output", "partial_inputs"])),
            missing_input_behavior=MODEL_DEFAULT_MISSING_INPUT_BEHAVIOR.get(
                model_name,
                "Returns downgraded status and null output for fields whose required inputs are missing.",
            ),
        )
    return formulas


_MODEL_SPECIFIC_FORMULAS = _build_model_specific_formulas()


def _default_model_formula_metadata(model_name: str, output_key: str, formula_id: str) -> FormulaMetadata:
    normalized_model = str(model_name or "").strip().lower() or "model"
    display_key = output_key.replace("values.", "").replace("intrinsic_value.", "").replace("_", " ")
    return FormulaMetadata(
        formula_id=formula_id,
        formula_version=MODEL_OUTPUT_FORMULA_VERSION,
        human_readable_formula=(
            f"{display_key.title()} computed by {normalized_model} model logic using normalized company inputs, "
            "with status, proxy, and missing-input guards applied by the model engine."
        ),
        input_fields=list(MODEL_DEFAULT_INPUT_FIELDS.get(normalized_model, ["model_input_periods", "market_snapshot"])),
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
        output_key = _restore_output_key("_".join(parts[2:-1]))
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
