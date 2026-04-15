from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from statistics import fmean, median
from typing import Any


SCENARIO_SEQUENCE = ("base", "bull", "bear")
SCENARIO_LABELS = {"base": "Base Forecast", "bull": "Bull Forecast", "bear": "Bear Forecast"}
RECENT_GROWTH_WEIGHTS = (0.2, 0.3, 0.5)
TERMINAL_MARKET_GROWTH = 0.03
TERMINAL_PRICE_GROWTH = 0.015
REVENUE_GROWTH_FLOOR = -0.18
REVENUE_GROWTH_CAP = 0.35
PRICE_GROWTH_FLOOR = -0.03
PRICE_GROWTH_CAP = 0.08
SHARE_CHANGE_FLOOR = -0.06
SHARE_CHANGE_CAP = 0.06
VARIABLE_COST_RATIO_FLOOR = 0.20
VARIABLE_COST_RATIO_CAP = 0.90
SEMI_VARIABLE_COST_RATIO_FLOOR = 0.03
SEMI_VARIABLE_COST_RATIO_CAP = 0.25
FIXED_COST_GROWTH_FLOOR = 0.00
FIXED_COST_GROWTH_CAP = 0.08
DSO_FLOOR = 5.0
DSO_CAP = 150.0
DIO_FLOOR = 0.0
DIO_CAP = 180.0
DPO_FLOOR = 0.0
DPO_CAP = 180.0
DEFERRED_REVENUE_DAYS_FLOOR = 0.0
DEFERRED_REVENUE_DAYS_CAP = 120.0
ACCRUED_OPERATING_LIABILITY_DAYS_FLOOR = 0.0
ACCRUED_OPERATING_LIABILITY_DAYS_CAP = 120.0
DEFAULT_DSO = 45.0
DEFAULT_DIO = 0.0
DEFAULT_DPO = 30.0
DEFAULT_DEFERRED_REVENUE_DAYS = 0.0
DEFAULT_ACCRUED_OPERATING_LIABILITY_DAYS = 0.0
COST_OF_REVENUE_RATIO_FLOOR = 0.05
COST_OF_REVENUE_RATIO_CAP = 0.95
SALES_TO_CAPITAL_FLOOR = 0.35
SALES_TO_CAPITAL_CAP = 2.50
CAPEX_INTENSITY_FLOOR = 0.02
CAPEX_INTENSITY_CAP = 0.25
DEPRECIATION_RATIO_FLOOR = 0.01
DEPRECIATION_RATIO_CAP = 0.20
CASH_RATIO_FLOOR = 0.01
CASH_RATIO_CAP = 0.30
DEBT_INTEREST_RATE_CAP = 0.18
CASH_YIELD_CAP = 0.10
OTHER_INCOME_RATIO_FLOOR = -0.08
OTHER_INCOME_RATIO_CAP = 0.08
EFFECTIVE_TAX_RATE_FLOOR = 0.00
EFFECTIVE_TAX_RATE_CAP = 0.35
LOSS_TAX_BENEFIT_CAP = 0.15
DEFAULT_CASH_RATIO = 0.06
DEFAULT_DEBT_INTEREST_RATE = 0.045
DEFAULT_CASH_YIELD = 0.015
DEFAULT_EFFECTIVE_TAX_RATE = 0.21
SBC_EXPENSE_RATIO_CAP = 0.08
SBC_DILUTION_FLOOR = 0.00
SBC_DILUTION_CAP = 0.04
BUYBACK_RETIREMENT_FLOOR = 0.00
BUYBACK_RETIREMENT_CAP = 0.05
ACQUISITION_DILUTION_CAP = 0.04
CONVERT_DILUTION_CAP = 0.04
DILUTION_CAP = 0.08
OPTION_WARRANT_DILUTION_CAP = 0.12
RSU_DILUTION_CAP = 0.06
ACQUISITION_SHARE_ISSUANCE_CAP = 0.06
PROXY_LATENT_DILUTION_CAP = 0.03
PROXY_LATENT_DILUTION_FULL_WEIGHT_OBS = 3.0


@dataclass(slots=True)
class DriverForecastLine:
    years: list[int] = field(default_factory=list)
    values: list[float] = field(default_factory=list)


@dataclass(slots=True)
class DriverForecastScenario:
    key: str
    label: str
    revenue: DriverForecastLine
    revenue_growth: DriverForecastLine
    operating_income: DriverForecastLine
    net_income: DriverForecastLine
    ebitda: DriverForecastLine
    operating_cash_flow: DriverForecastLine
    free_cash_flow: DriverForecastLine
    capex: DriverForecastLine
    diluted_shares: DriverForecastLine
    eps: DriverForecastLine
    bridge: list[_ForecastBridgePoint] = field(default_factory=list)
    share_bridge: list[_ForecastShareBridgePoint] = field(default_factory=list)


@dataclass(slots=True)
class DriverForecastBundle:
    engine_mode: str
    revenue_method: str
    segment_basis: str | None
    scenarios: dict[str, DriverForecastScenario]
    assumption_rows: list[dict[str, str]]
    calculation_rows: list[dict[str, str]]
    highlights: list[str]
    base_next_year_growth: float | None
    bull_next_year_growth: float | None
    bear_next_year_growth: float | None
    base_three_year_cagr: float | None
    bull_three_year_cagr: float | None
    bear_three_year_cagr: float | None
    guidance_anchor: float | None = None
    sensitivity_rows: list[dict[str, str]] = field(default_factory=list)


@dataclass(slots=True)
class _ScenarioTweaks:
    demand_shift: float
    share_shift: float
    price_shift: float
    variable_cost_shift: float
    semi_variable_cost_shift: float
    fixed_cost_growth_shift: float
    working_capital_days_shift: float
    sales_to_capital_shift: float
    sbc_shift: float
    buyback_shift: float
    dilution_shift: float


@dataclass(slots=True)
class _RevenueDrivers:
    mode: str
    segment_basis: str | None
    pricing_growth: float
    market_growth: float
    market_share_change: float
    volume_growth: float
    guidance_anchor: float | None
    backlog_floor_growth: float | None
    capacity_growth_cap: float | None
    utilization_ratio: float | None
    segment_profiles: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class _CostSchedule:
    variable_cost_ratio: float
    semi_variable_cost_ratio: float
    fixed_cost_base: float
    fixed_cost_growth: float
    latest_operating_margin: float


@dataclass(slots=True)
class _OperatingWorkingCapitalSchedule:
    dso: float
    dio: float
    dpo: float
    deferred_revenue_days: float
    accrued_operating_liability_days: float
    cost_of_revenue_ratio: float
    starting_accounts_receivable: float
    starting_inventory: float
    starting_accounts_payable: float
    starting_deferred_revenue: float
    starting_accrued_operating_liabilities: float
    basis_detail: str


@dataclass(slots=True)
class _ReinvestmentSchedule:
    operating_working_capital: _OperatingWorkingCapitalSchedule
    sales_to_capital: float
    capex_intensity: float
    depreciation_ratio: float
    latest_depreciation: float


@dataclass(slots=True)
class _DilutionSchedule:
    starting_basic_shares: float
    starting_diluted_shares: float
    sbc_expense_ratio: float
    annual_rsu_shares: float
    annual_buyback_shares: float
    annual_acquisition_shares: float
    option_warrant_dilution_shares: float
    convertible_dilution_shares: float
    uses_proxy_fallback: bool
    proxy_net_dilution_rate: float
    proxy_latent_dilution_rate: float
    starting_basis: str
    option_basis: str
    rsu_basis: str
    buyback_basis: str
    acquisition_basis: str
    convert_basis: str
    fallback_basis: str


@dataclass(slots=True)
class _ForecastShareBridgePoint:
    year: int
    basic_shares: float
    rsu_shares: float
    acquisition_shares: float
    buyback_retirement_shares: float
    option_warrant_dilution_shares: float
    convertible_dilution_shares: float
    latent_dilution_shares: float
    proxy_net_change_shares: float
    diluted_shares: float
    uses_proxy_fallback: bool


@dataclass(slots=True)
class _BelowLineSchedule:
    starting_cash: float
    starting_debt: float
    target_cash_ratio: float
    debt_interest_rate: float
    cash_yield: float
    other_income_ratio: float
    effective_tax_rate: float
    cash_basis: str
    debt_basis: str
    interest_basis: str
    other_basis: str
    tax_basis: str


@dataclass(slots=True)
class _ForecastBridgePoint:
    year: int
    ebit: float
    interest_expense: float
    interest_income: float
    other_income_expense: float
    pretax_income: float
    taxes: float
    net_income: float
    depreciation: float
    stock_based_compensation: float
    delta_working_capital: float
    operating_cash_flow: float
    capex: float
    free_cash_flow: float
    beginning_cash: float
    ending_cash: float
    beginning_debt: float
    ending_debt: float
    beginning_operating_working_capital: float
    ending_operating_working_capital: float
    accounts_receivable: float
    inventory: float
    accounts_payable: float
    deferred_revenue: float
    accrued_operating_liabilities: float


def build_driver_forecast_bundle(
    statements: list[Any],
    releases: list[Any],
    *,
    horizon_years: int = 3,
) -> DriverForecastBundle | None:
    history = _normalize_statements(statements)
    if len(history) < 3:
        return None

    revenue_history = [row["revenue"] for row in history if row["revenue"] is not None]
    if len(revenue_history) < 2:
        return None

    latest_revenue = history[-1]["revenue"]
    if latest_revenue is None or latest_revenue <= 0:
        return None

    dilution_schedule = _derive_dilution_schedule(history)
    if dilution_schedule is None:
        return None

    revenue_drivers = _derive_revenue_drivers(history, releases)
    cost_schedule = _derive_cost_schedule(history)
    reinvestment_schedule = _derive_reinvestment_schedule(history, cost_schedule)
    below_line_schedule = _derive_below_line_schedule(history)
    latest_year = int(history[-1]["year"])
    scenario_tweaks = _scenario_tweaks()

    scenarios: dict[str, DriverForecastScenario] = {}
    for scenario_key in SCENARIO_SEQUENCE:
        scenarios[scenario_key] = _project_scenario(
            history,
            revenue_drivers,
            cost_schedule,
            reinvestment_schedule,
            below_line_schedule,
            dilution_schedule,
            scenario_key=scenario_key,
            horizon_years=horizon_years,
            latest_year=latest_year,
            tweaks=scenario_tweaks[scenario_key],
        )

    assumption_rows = _build_assumption_rows(
        history,
        revenue_drivers,
        cost_schedule,
        reinvestment_schedule,
        below_line_schedule,
        dilution_schedule,
    )
    calculation_rows = _build_calculation_rows(
        revenue_drivers,
        cost_schedule,
        reinvestment_schedule,
        below_line_schedule,
        dilution_schedule,
        scenarios["base"],
    )
    highlights = _build_highlights(revenue_drivers, scenarios["base"], scenarios["bull"], scenarios["bear"])
    sensitivity_rows = _build_sensitivity_rows(scenarios)

    return DriverForecastBundle(
        engine_mode="driver",
        revenue_method=revenue_drivers.mode,
        segment_basis=revenue_drivers.segment_basis,
        scenarios=scenarios,
        assumption_rows=assumption_rows,
        calculation_rows=calculation_rows,
        highlights=highlights,
        base_next_year_growth=_first_value(scenarios["base"].revenue_growth.values),
        bull_next_year_growth=_first_value(scenarios["bull"].revenue_growth.values),
        bear_next_year_growth=_first_value(scenarios["bear"].revenue_growth.values),
        base_three_year_cagr=_line_cagr(scenarios["base"].revenue.values),
        bull_three_year_cagr=_line_cagr(scenarios["bull"].revenue.values),
        bear_three_year_cagr=_line_cagr(scenarios["bear"].revenue.values),
        guidance_anchor=revenue_drivers.guidance_anchor,
        sensitivity_rows=sensitivity_rows,
    )


def _normalize_statements(statements: list[Any]) -> list[dict[str, Any]]:
    history: list[dict[str, Any]] = []
    for statement in sorted(statements, key=lambda item: getattr(item, "period_end", None) or 0):
        period_end = getattr(statement, "period_end", None)
        if period_end is None:
            continue
        history.append(
            {
                "statement": statement,
                "year": period_end.year,
                "period_end": period_end,
                "revenue": _statement_value(statement, "revenue"),
                "operating_income": _statement_value(statement, "operating_income"),
                "net_income": _statement_value(statement, "net_income"),
                "operating_cash_flow": _statement_value(statement, "operating_cash_flow"),
                "free_cash_flow": _statement_value(statement, "free_cash_flow"),
                "capex": _statement_value(statement, "capex"),
                "depreciation": _statement_value(statement, "depreciation_and_amortization"),
                "pretax_income": _statement_value(statement, "pretax_income"),
                "income_tax_expense": _statement_value(statement, "income_tax_expense"),
                "interest_expense": _statement_value(statement, "interest_expense"),
                "interest_income": _statement_value(statement, "interest_income"),
                "other_income_expense": _statement_value(statement, "other_income_expense"),
                "cash_balance": _statement_value(statement, "cash_balance"),
                "basic_shares": _statement_value(statement, "weighted_average_shares_basic"),
                "shares": _statement_value(statement, "weighted_average_shares_diluted"),
                "current_debt": _statement_value(statement, "current_debt"),
                "long_term_debt": _statement_value(statement, "long_term_debt"),
                "total_debt": _statement_value(statement, "total_debt"),
                "debt_issuance": _statement_value(statement, "debt_issuance"),
                "debt_repayment": _statement_value(statement, "debt_repayment"),
                "shares_issued": _statement_value(statement, "shares_issued"),
                "shares_repurchased": _statement_value(statement, "shares_repurchased"),
                "share_price": _statement_value(statement, "share_price"),
                "option_warrant_dilution_shares": _statement_value(statement, "option_warrant_dilution_shares"),
                "options_outstanding": _statement_value(statement, "options_outstanding"),
                "warrants_outstanding": _statement_value(statement, "warrants_outstanding"),
                "option_exercise_price": _statement_value(statement, "option_exercise_price"),
                "warrant_exercise_price": _statement_value(statement, "warrant_exercise_price"),
                "rsu_shares": _statement_value(statement, "rsu_shares"),
                "acquisition_shares_issued": _statement_value(statement, "acquisition_shares_issued"),
                "convertible_dilution_shares": _statement_value(statement, "convertible_dilution_shares"),
                "convertible_conversion_price": _statement_value(statement, "convertible_conversion_price"),
                "convertible_is_dilutive": _statement_value(statement, "convertible_is_dilutive"),
                "gross_profit": _statement_value(statement, "gross_profit"),
                "cost_of_revenue": _statement_value(statement, "cost_of_revenue"),
                "total_assets": _statement_value(statement, "total_assets"),
                "current_assets": _statement_value(statement, "current_assets"),
                "current_liabilities": _statement_value(statement, "current_liabilities"),
                "accounts_receivable": _statement_value(statement, "accounts_receivable"),
                "inventory": _statement_value(statement, "inventory"),
                "accounts_payable": _statement_value(statement, "accounts_payable"),
                "deferred_revenue": _statement_value(statement, "deferred_revenue"),
                "accrued_operating_liabilities": _statement_value(statement, "accrued_operating_liabilities"),
                "stock_based_compensation": _statement_value(statement, "stock_based_compensation"),
                "share_buybacks": _statement_value(statement, "share_buybacks"),
                "acquisitions": _statement_value(statement, "acquisitions"),
                "sga": _statement_value(statement, "sga"),
                "research_and_development": _statement_value(statement, "research_and_development"),
                "segments": _normalize_segments(statement),
            }
        )
    return history


def _normalize_segments(statement: Any) -> list[dict[str, Any]]:
    data = getattr(statement, "data", None)
    payload = data.get("segment_breakdown") if isinstance(data, dict) else None
    if not isinstance(payload, list):
        return []
    normalized: list[dict[str, Any]] = []
    total_revenue = 0.0
    for item in payload:
        revenue = _as_float(item.get("revenue")) if isinstance(item, dict) else None
        if revenue is None or revenue <= 0:
            continue
        total_revenue += revenue
    for item in payload:
        if not isinstance(item, dict):
            continue
        revenue = _as_float(item.get("revenue"))
        if revenue is None or revenue <= 0:
            continue
        share = _as_float(item.get("share_of_revenue"))
        if share is None and total_revenue > 0:
            share = revenue / total_revenue
        segment_id = str(item.get("segment_id") or item.get("segment_name") or "unknown")
        normalized.append(
            {
                "segment_id": segment_id,
                "segment_name": str(item.get("segment_name") or segment_id),
                "kind": str(item.get("kind") or "other"),
                "revenue": revenue,
                "share_of_revenue": share,
                "operating_income": _as_float(item.get("operating_income")),
            }
        )
    return normalized


def _derive_revenue_drivers(history: list[dict[str, Any]], releases: list[Any]) -> _RevenueDrivers:
    guidance_anchor = _latest_guidance_revenue(releases)
    revenue_growth = _historical_growth_rates([row["revenue"] for row in history])
    recent_growth = _weighted_recent_growth(revenue_growth)
    cagr_growth = _cagr([row["revenue"] for row in history[-4:] if row["revenue"] is not None])
    realized_growth = _blend_optional(recent_growth, cagr_growth) or TERMINAL_MARKET_GROWTH
    pricing_growth = _pricing_growth_proxy(history)
    share_trend = _share_shift_proxy(history)
    market_growth = _clip(realized_growth - pricing_growth - share_trend, -0.05, 0.18)
    volume_growth = _clip(market_growth + share_trend, REVENUE_GROWTH_FLOOR, REVENUE_GROWTH_CAP)

    backlog_floor_growth = _backlog_floor_growth(history[-1])
    capacity_growth_cap, utilization_ratio = _capacity_constraint(history[-1], _sales_to_capital(history))
    segment_profiles, segment_basis = _segment_profiles(history, market_growth, pricing_growth)

    mode = "bottom_up_segment" if segment_profiles else "top_down_market_share"
    if guidance_anchor is not None:
        mode = f"{mode}+guidance"
    if backlog_floor_growth is not None:
        mode = f"{mode}+backlog"
    if capacity_growth_cap is not None:
        mode = f"{mode}+capacity"

    return _RevenueDrivers(
        mode=mode,
        segment_basis=segment_basis,
        pricing_growth=pricing_growth,
        market_growth=market_growth,
        market_share_change=share_trend,
        volume_growth=volume_growth,
        guidance_anchor=guidance_anchor,
        backlog_floor_growth=backlog_floor_growth,
        capacity_growth_cap=capacity_growth_cap,
        utilization_ratio=utilization_ratio,
        segment_profiles=segment_profiles,
    )


def _derive_cost_schedule(history: list[dict[str, Any]]) -> _CostSchedule:
    margins = [
        _safe_divide(row["operating_income"], row["revenue"])
        for row in history
        if row["operating_income"] is not None and row["revenue"] not in (None, 0)
    ]
    latest = history[-1]
    latest_revenue = latest["revenue"] or 0.0
    latest_operating_income = latest["operating_income"] or 0.0
    latest_operating_margin = _safe_divide(latest_operating_income, latest_revenue) or (median(margins) if margins else 0.12)

    cost_slopes: list[float] = []
    cost_growths: list[float] = []
    for previous, current in zip(history, history[1:]):
        previous_revenue = previous["revenue"]
        current_revenue = current["revenue"]
        previous_cost = _operating_cost(previous)
        current_cost = _operating_cost(current)
        if previous_revenue is None or current_revenue is None or previous_cost is None or current_cost is None:
            continue
        revenue_delta = current_revenue - previous_revenue
        if revenue_delta > 0:
            slope = _safe_divide(current_cost - previous_cost, revenue_delta)
            if slope is not None:
                cost_slopes.append(_clip(slope, VARIABLE_COST_RATIO_FLOOR, VARIABLE_COST_RATIO_CAP))
        growth = _growth_rate(current_cost, previous_cost)
        if growth is not None:
            cost_growths.append(growth)

    variable_cost_ratio = median(cost_slopes) if cost_slopes else _clip(1.0 - latest_operating_margin - 0.18, VARIABLE_COST_RATIO_FLOOR, VARIABLE_COST_RATIO_CAP)

    operating_expense_ratios = [
        _safe_divide((row["sga"] or 0.0) + (row["research_and_development"] or 0.0), row["revenue"])
        for row in history
        if row["revenue"] not in (None, 0)
    ]
    operating_expense_ratios = [ratio for ratio in operating_expense_ratios if ratio is not None]
    semi_variable_cost_ratio = (
        _clip(median(operating_expense_ratios) * 0.60, SEMI_VARIABLE_COST_RATIO_FLOOR, SEMI_VARIABLE_COST_RATIO_CAP)
        if operating_expense_ratios
        else _clip(max(0.06, (1.0 - latest_operating_margin - variable_cost_ratio) * 0.35), SEMI_VARIABLE_COST_RATIO_FLOOR, SEMI_VARIABLE_COST_RATIO_CAP)
    )

    total_cost_ratio = max(0.35, 1.0 - latest_operating_margin)
    if variable_cost_ratio + semi_variable_cost_ratio > total_cost_ratio - 0.02:
        semi_variable_cost_ratio = _clip(max(0.03, total_cost_ratio - variable_cost_ratio - 0.02), SEMI_VARIABLE_COST_RATIO_FLOOR, SEMI_VARIABLE_COST_RATIO_CAP)

    latest_cost = max(0.0, latest_revenue - latest_operating_income)
    fixed_cost_base = max(0.0, latest_cost - (latest_revenue * variable_cost_ratio) - (latest_revenue * semi_variable_cost_ratio))
    fixed_cost_growth = _clip((_blend_optional(_weighted_recent_growth(cost_growths), 0.03) or 0.03) * 0.5, FIXED_COST_GROWTH_FLOOR, FIXED_COST_GROWTH_CAP)

    return _CostSchedule(
        variable_cost_ratio=variable_cost_ratio,
        semi_variable_cost_ratio=semi_variable_cost_ratio,
        fixed_cost_base=fixed_cost_base,
        fixed_cost_growth=fixed_cost_growth,
        latest_operating_margin=latest_operating_margin,
    )


def _derive_reinvestment_schedule(history: list[dict[str, Any]], cost_schedule: _CostSchedule) -> _ReinvestmentSchedule:
    latest = history[-1]
    capex_intensity = _clip(_median_abs_ratio(history, "capex", "revenue") or 0.05, CAPEX_INTENSITY_FLOOR, CAPEX_INTENSITY_CAP)
    depreciation_ratio = _clip(_median_abs_ratio(history, "depreciation", "revenue") or (capex_intensity * 0.75), DEPRECIATION_RATIO_FLOOR, DEPRECIATION_RATIO_CAP)
    latest_depreciation = abs(latest["depreciation"] or 0.0) or (latest["revenue"] or 0.0) * depreciation_ratio
    return _ReinvestmentSchedule(
        operating_working_capital=_derive_operating_working_capital_schedule(history, cost_schedule),
        sales_to_capital=_sales_to_capital(history) or 1.25,
        capex_intensity=capex_intensity,
        depreciation_ratio=depreciation_ratio,
        latest_depreciation=latest_depreciation,
    )


def _derive_operating_working_capital_schedule(history: list[dict[str, Any]], cost_schedule: _CostSchedule) -> _OperatingWorkingCapitalSchedule:
    latest = history[-1]
    direct_cost_ratios: list[float] = []
    dso_values: list[float] = []
    dio_values: list[float] = []
    dpo_values: list[float] = []
    deferred_values: list[float] = []
    accrued_values: list[float] = []

    for row in history:
        revenue = row["revenue"]
        if revenue in (None, 0):
            continue
        resolved_cost_of_revenue = _resolved_cost_of_revenue(row)
        if resolved_cost_of_revenue not in (None, 0):
            direct_cost_ratios.append(_clip(resolved_cost_of_revenue / revenue, COST_OF_REVENUE_RATIO_FLOOR, COST_OF_REVENUE_RATIO_CAP))

    cost_of_revenue_ratio = median(direct_cost_ratios) if direct_cost_ratios else _clip(cost_schedule.variable_cost_ratio, COST_OF_REVENUE_RATIO_FLOOR, COST_OF_REVENUE_RATIO_CAP)

    for row in history:
        revenue = row["revenue"]
        if revenue in (None, 0):
            continue
        resolved_cost_of_revenue = _resolved_cost_of_revenue(row, cost_of_revenue_ratio)
        cash_operating_cost = _historical_cash_operating_cost(row, resolved_cost_of_revenue)

        accounts_receivable = row["accounts_receivable"]
        if accounts_receivable is not None:
            dso_values.append(_clip((accounts_receivable / revenue) * 365.0, DSO_FLOOR, DSO_CAP))

        inventory = row["inventory"]
        if inventory is not None and resolved_cost_of_revenue not in (None, 0):
            dio_values.append(_clip((inventory / resolved_cost_of_revenue) * 365.0, DIO_FLOOR, DIO_CAP))

        accounts_payable = row["accounts_payable"]
        if accounts_payable is not None and resolved_cost_of_revenue not in (None, 0):
            dpo_values.append(_clip((accounts_payable / resolved_cost_of_revenue) * 365.0, DPO_FLOOR, DPO_CAP))

        deferred_revenue = row["deferred_revenue"]
        if deferred_revenue is not None:
            deferred_values.append(_clip((deferred_revenue / revenue) * 365.0, DEFERRED_REVENUE_DAYS_FLOOR, DEFERRED_REVENUE_DAYS_CAP))

        accrued_operating_liabilities = row["accrued_operating_liabilities"]
        if accrued_operating_liabilities is not None and cash_operating_cost not in (None, 0):
            accrued_values.append(
                _clip(
                    (accrued_operating_liabilities / cash_operating_cost) * 365.0,
                    ACCRUED_OPERATING_LIABILITY_DAYS_FLOOR,
                    ACCRUED_OPERATING_LIABILITY_DAYS_CAP,
                )
            )

    dso = median(dso_values) if dso_values else DEFAULT_DSO
    dio = median(dio_values) if dio_values else DEFAULT_DIO
    dpo = median(dpo_values) if dpo_values else DEFAULT_DPO
    deferred_revenue_days = median(deferred_values) if deferred_values else DEFAULT_DEFERRED_REVENUE_DAYS
    accrued_operating_liability_days = median(accrued_values) if accrued_values else DEFAULT_ACCRUED_OPERATING_LIABILITY_DAYS

    latest_revenue = latest["revenue"] or 0.0
    latest_cost_of_revenue = _resolved_cost_of_revenue(latest, cost_of_revenue_ratio) or (latest_revenue * cost_of_revenue_ratio)
    latest_cash_operating_cost = _historical_cash_operating_cost(latest, latest_cost_of_revenue) or max(latest_cost_of_revenue, 0.0)

    starting_accounts_receivable = latest["accounts_receivable"] if latest["accounts_receivable"] is not None else _days_to_balance(latest_revenue, dso)
    starting_inventory = latest["inventory"] if latest["inventory"] is not None else _days_to_balance(latest_cost_of_revenue, dio)
    starting_accounts_payable = latest["accounts_payable"] if latest["accounts_payable"] is not None else _days_to_balance(latest_cost_of_revenue, dpo)
    starting_deferred_revenue = latest["deferred_revenue"] if latest["deferred_revenue"] is not None else _days_to_balance(latest_revenue, deferred_revenue_days)
    starting_accrued_operating_liabilities = (
        latest["accrued_operating_liabilities"]
        if latest["accrued_operating_liabilities"] is not None
        else _days_to_balance(latest_cash_operating_cost, accrued_operating_liability_days)
    )

    basis_detail = "; ".join(
        [
            _schedule_basis("AR", dso_values, DEFAULT_DSO),
            _schedule_basis("Inventory", dio_values, DEFAULT_DIO),
            _schedule_basis("AP", dpo_values, DEFAULT_DPO),
            _schedule_basis("Deferred revenue", deferred_values, DEFAULT_DEFERRED_REVENUE_DAYS),
            _schedule_basis("Accrued operating liabilities", accrued_values, DEFAULT_ACCRUED_OPERATING_LIABILITY_DAYS),
        ]
    )

    return _OperatingWorkingCapitalSchedule(
        dso=dso,
        dio=dio,
        dpo=dpo,
        deferred_revenue_days=deferred_revenue_days,
        accrued_operating_liability_days=accrued_operating_liability_days,
        cost_of_revenue_ratio=cost_of_revenue_ratio,
        starting_accounts_receivable=max(0.0, starting_accounts_receivable),
        starting_inventory=max(0.0, starting_inventory),
        starting_accounts_payable=max(0.0, starting_accounts_payable),
        starting_deferred_revenue=max(0.0, starting_deferred_revenue),
        starting_accrued_operating_liabilities=max(0.0, starting_accrued_operating_liabilities),
        basis_detail=basis_detail,
    )


def _derive_dilution_schedule(history: list[dict[str, Any]]) -> _DilutionSchedule | None:
    diluted_share_history = [row["shares"] for row in history if row["shares"] is not None and row["shares"] > 0]
    basic_share_history = [row["basic_shares"] for row in history if row["basic_shares"] is not None and row["basic_shares"] > 0]
    if not diluted_share_history and not basic_share_history:
        return None

    latest = history[-1]
    starting_basic_shares = float(basic_share_history[-1]) if basic_share_history else float(diluted_share_history[-1])
    starting_diluted_shares = float(diluted_share_history[-1]) if diluted_share_history else starting_basic_shares
    sbc_expense_ratio = _clip(_median_abs_ratio(history, "stock_based_compensation", "revenue") or 0.0, 0.0, SBC_EXPENSE_RATIO_CAP)

    starting_basis = "Basic weighted-average shares" if basic_share_history else "Diluted weighted-average shares fallback"
    latest_share_price, share_price_basis = _latest_share_price(history)

    option_warrant_dilution_shares, option_basis = _derive_option_warrant_dilution_shares(latest, starting_basic_shares, latest_share_price, share_price_basis)
    annual_acquisition_shares, acquisition_basis = _derive_acquisition_share_issuance(history, starting_basic_shares)
    annual_rsu_shares, rsu_basis = _derive_rsu_share_issuance(history, annual_acquisition_shares, starting_basic_shares)
    annual_buyback_shares, buyback_basis = _derive_buyback_retirement_shares(history, latest_share_price, share_price_basis, starting_basic_shares)
    convertible_dilution_shares, convert_basis = _derive_convertible_dilution_shares(latest, starting_basic_shares, latest_share_price, share_price_basis)
    proxy_net_dilution_rate, fallback_basis = _derive_proxy_net_dilution_rate(history, starting_diluted_shares)
    proxy_latent_dilution_rate, proxy_latent_basis = _derive_proxy_latent_dilution_rate(history)

    uses_proxy_fallback = not any(
        value > 0
        for value in (
            option_warrant_dilution_shares,
            annual_rsu_shares,
            annual_buyback_shares,
            annual_acquisition_shares,
            convertible_dilution_shares,
        )
    )
    if uses_proxy_fallback and proxy_latent_basis is not None:
        fallback_basis = f"{fallback_basis}. {proxy_latent_basis}"

    return _DilutionSchedule(
        starting_basic_shares=starting_basic_shares,
        starting_diluted_shares=starting_diluted_shares,
        sbc_expense_ratio=sbc_expense_ratio,
        annual_rsu_shares=annual_rsu_shares,
        annual_buyback_shares=annual_buyback_shares,
        annual_acquisition_shares=annual_acquisition_shares,
        option_warrant_dilution_shares=option_warrant_dilution_shares,
        convertible_dilution_shares=convertible_dilution_shares,
        uses_proxy_fallback=uses_proxy_fallback,
        proxy_net_dilution_rate=proxy_net_dilution_rate,
        proxy_latent_dilution_rate=proxy_latent_dilution_rate,
        starting_basis=starting_basis,
        option_basis=option_basis,
        rsu_basis=rsu_basis,
        buyback_basis=buyback_basis,
        acquisition_basis=acquisition_basis,
        convert_basis=convert_basis,
        fallback_basis=fallback_basis,
    )


def _derive_below_line_schedule(history: list[dict[str, Any]]) -> _BelowLineSchedule:
    latest = history[-1]
    latest_revenue = latest["revenue"] or 0.0
    target_cash_ratio = _clip(_median_abs_ratio(history, "cash_balance", "revenue") or DEFAULT_CASH_RATIO, CASH_RATIO_FLOOR, CASH_RATIO_CAP)

    latest_cash = latest["cash_balance"]
    starting_cash = latest_cash if latest_cash is not None else (latest_revenue * target_cash_ratio)
    cash_basis = "Disclosed cash balance" if latest_cash is not None else "Cash ratio fallback"

    latest_debt = latest["total_debt"]
    if latest_debt is None:
        latest_debt = _sum_non_null(latest["current_debt"], latest["long_term_debt"])
    starting_debt = max(0.0, latest_debt or 0.0)
    debt_basis = (
        "Disclosed debt balance"
        if latest["total_debt"] is not None or latest["current_debt"] is not None or latest["long_term_debt"] is not None
        else "No debt disclosed"
    )

    debt_rates: list[float] = []
    cash_yields: list[float] = []
    other_income_ratios: list[float] = []
    tax_rates: list[float] = []
    derived_other_count = 0
    direct_other_count = 0

    previous_row: dict[str, Any] | None = None
    for row in history:
        interest_expense = _positive_amount(row["interest_expense"])
        average_debt = _average_balance(previous_row["total_debt"] if previous_row is not None else None, row["total_debt"])
        if interest_expense is not None and average_debt not in (None, 0):
            debt_rates.append(_clip(interest_expense / average_debt, 0.0, DEBT_INTEREST_RATE_CAP))

        interest_income = _positive_amount(row["interest_income"])
        average_cash = _average_balance(previous_row["cash_balance"] if previous_row is not None else None, row["cash_balance"])
        if interest_income is not None and average_cash not in (None, 0):
            cash_yields.append(_clip(interest_income / average_cash, 0.0, CASH_YIELD_CAP))

        other_income = row["other_income_expense"]
        if other_income is not None:
            direct_other_count += 1
        else:
            other_income = _derived_other_income_expense(row)
            if other_income is not None:
                derived_other_count += 1
        if row["revenue"] not in (None, 0) and other_income is not None:
            other_income_ratios.append(_clip(other_income / row["revenue"], OTHER_INCOME_RATIO_FLOOR, OTHER_INCOME_RATIO_CAP))

        pretax_income = row["pretax_income"]
        income_tax_expense = row["income_tax_expense"]
        if pretax_income is not None and pretax_income > 0 and income_tax_expense is not None:
            tax_rates.append(_clip(abs(income_tax_expense) / pretax_income, EFFECTIVE_TAX_RATE_FLOOR, EFFECTIVE_TAX_RATE_CAP))

        previous_row = row

    debt_interest_rate = median(debt_rates) if debt_rates else DEFAULT_DEBT_INTEREST_RATE
    cash_yield = median(cash_yields) if cash_yields else DEFAULT_CASH_YIELD
    other_income_ratio = median(other_income_ratios) if other_income_ratios else 0.0
    effective_tax_rate = median(tax_rates) if tax_rates else DEFAULT_EFFECTIVE_TAX_RATE

    interest_basis = "Disclosed interest rates" if debt_rates or cash_yields else "Default cash and debt rates"
    if direct_other_count:
        other_basis = "Disclosed other income or expense"
    elif derived_other_count:
        other_basis = "Residual bridge fallback"
    else:
        other_basis = "Zero other income fallback"
    tax_basis = "Disclosed effective tax rate" if tax_rates else "Default tax rate"

    return _BelowLineSchedule(
        starting_cash=max(0.0, starting_cash),
        starting_debt=starting_debt,
        target_cash_ratio=target_cash_ratio,
        debt_interest_rate=debt_interest_rate,
        cash_yield=cash_yield,
        other_income_ratio=other_income_ratio,
        effective_tax_rate=effective_tax_rate,
        cash_basis=cash_basis,
        debt_basis=debt_basis,
        interest_basis=interest_basis,
        other_basis=other_basis,
        tax_basis=tax_basis,
    )


def _scenario_tweaks() -> dict[str, _ScenarioTweaks]:
    return {
        "base": _ScenarioTweaks(0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        "bull": _ScenarioTweaks(0.02, 0.01, 0.005, -0.01, -0.005, -0.01, -3.0, 0.20, -0.003, 0.005, -0.002),
        "bear": _ScenarioTweaks(-0.03, -0.01, -0.005, 0.015, 0.008, 0.01, 5.0, -0.20, 0.004, -0.004, 0.003),
    }


def _project_scenario(
    history: list[dict[str, Any]],
    revenue_drivers: _RevenueDrivers,
    cost_schedule: _CostSchedule,
    reinvestment_schedule: _ReinvestmentSchedule,
    below_line_schedule: _BelowLineSchedule,
    dilution_schedule: _DilutionSchedule,
    *,
    scenario_key: str,
    horizon_years: int,
    latest_year: int,
    tweaks: _ScenarioTweaks,
) -> DriverForecastScenario:
    revenue_projection = (
        _bottom_up_revenue_projection(history, revenue_drivers, tweaks, latest_year, horizon_years)
        if revenue_drivers.segment_profiles
        else _top_down_revenue_projection(history, revenue_drivers, tweaks, latest_year, horizon_years)
    )

    previous_revenue = history[-1]["revenue"] or 0.0
    operating_working_capital_schedule = reinvestment_schedule.operating_working_capital
    previous_working_capital = _operating_working_capital_total(
        operating_working_capital_schedule.starting_accounts_receivable,
        operating_working_capital_schedule.starting_inventory,
        operating_working_capital_schedule.starting_accounts_payable,
        operating_working_capital_schedule.starting_deferred_revenue,
        operating_working_capital_schedule.starting_accrued_operating_liabilities,
    )
    previous_depreciation = reinvestment_schedule.latest_depreciation
    semi_cost = previous_revenue * cost_schedule.semi_variable_cost_ratio
    fixed_cost = cost_schedule.fixed_cost_base
    cash_balance = below_line_schedule.starting_cash
    debt_balance = below_line_schedule.starting_debt
    basic_shares = dilution_schedule.starting_basic_shares

    years: list[int] = []
    revenue_values: list[float] = []
    revenue_growth_values: list[float] = []
    operating_income_values: list[float] = []
    net_income_values: list[float] = []
    ebitda_values: list[float] = []
    operating_cash_flow_values: list[float] = []
    free_cash_flow_values: list[float] = []
    capex_values: list[float] = []
    diluted_shares_values: list[float] = []
    eps_values: list[float] = []
    bridge_points: list[_ForecastBridgePoint] = []
    share_bridge_points: list[_ForecastShareBridgePoint] = []

    for year, revenue, revenue_growth in revenue_projection:
        years.append(year)
        revenue_values.append(revenue)
        revenue_growth_values.append(revenue_growth)

        variable_cost_ratio = _clip(cost_schedule.variable_cost_ratio + tweaks.variable_cost_shift, VARIABLE_COST_RATIO_FLOOR, VARIABLE_COST_RATIO_CAP)
        variable_cost = revenue * variable_cost_ratio

        target_semi_ratio = _clip(cost_schedule.semi_variable_cost_ratio + tweaks.semi_variable_cost_shift, SEMI_VARIABLE_COST_RATIO_FLOOR, SEMI_VARIABLE_COST_RATIO_CAP)
        semi_cost = max(0.0, semi_cost * (1.0 + (revenue_growth * 0.55)))
        semi_cost = (semi_cost * 0.55) + ((revenue * target_semi_ratio) * 0.45)

        fixed_cost_growth = _clip(cost_schedule.fixed_cost_growth + tweaks.fixed_cost_growth_shift, FIXED_COST_GROWTH_FLOOR, FIXED_COST_GROWTH_CAP)
        fixed_cost = max(0.0, fixed_cost * (1.0 + fixed_cost_growth))

        operating_income = revenue - variable_cost - semi_cost - fixed_cost
        depreciation = max(0.0, (previous_depreciation * 0.50) + ((revenue * reinvestment_schedule.depreciation_ratio) * 0.50))
        ebitda = operating_income + depreciation

        cost_of_revenue = max(revenue * operating_working_capital_schedule.cost_of_revenue_ratio, variable_cost)
        cash_operating_cost = max(0.0, revenue - operating_income - depreciation)
        working_capital_point = _project_operating_working_capital_point(
            revenue=revenue,
            cost_of_revenue=cost_of_revenue,
            cash_operating_cost=cash_operating_cost,
            schedule=operating_working_capital_schedule,
            days_shift=tweaks.working_capital_days_shift,
        )
        target_working_capital = working_capital_point["total"]
        delta_working_capital = target_working_capital - previous_working_capital

        sales_to_capital = _clip(reinvestment_schedule.sales_to_capital + tweaks.sales_to_capital_shift, SALES_TO_CAPITAL_FLOOR, SALES_TO_CAPITAL_CAP)
        growth_reinvestment = max(revenue - previous_revenue, 0.0) / sales_to_capital

        maintenance_capex = max(revenue * reinvestment_schedule.capex_intensity, depreciation)
        capex = max(maintenance_capex, depreciation + max(growth_reinvestment, 0.0))
        stock_based_compensation = revenue * dilution_schedule.sbc_expense_ratio
        bridge_point = _project_below_line_bridge(
            year=year,
            revenue=revenue,
            ebit=operating_income,
            depreciation=depreciation,
            stock_based_compensation=stock_based_compensation,
            delta_working_capital=delta_working_capital,
            capex=capex,
            opening_cash=cash_balance,
            opening_debt=debt_balance,
            beginning_operating_working_capital=previous_working_capital,
            ending_operating_working_capital=target_working_capital,
            accounts_receivable=working_capital_point["accounts_receivable"],
            inventory=working_capital_point["inventory"],
            accounts_payable=working_capital_point["accounts_payable"],
            deferred_revenue=working_capital_point["deferred_revenue"],
            accrued_operating_liabilities=working_capital_point["accrued_operating_liabilities"],
            schedule=below_line_schedule,
        )
        net_income = bridge_point.net_income
        operating_cash_flow = bridge_point.operating_cash_flow
        free_cash_flow = bridge_point.free_cash_flow

        if dilution_schedule.uses_proxy_fallback:
            proxy_net_dilution = _clip(
                dilution_schedule.proxy_net_dilution_rate
                + tweaks.sbc_shift
                - tweaks.buyback_shift
                + tweaks.dilution_shift,
                SHARE_CHANGE_FLOOR,
                DILUTION_CAP,
            )
            proxy_net_change_shares = max(-basic_shares, basic_shares * proxy_net_dilution)
            basic_shares = max(1e-6, basic_shares + proxy_net_change_shares)
            # Proxy fallback keeps the share-count drift conservative and only adds
            # a latent dilution overlay when filings historically showed diluted
            # shares running above basic shares. The overlay is tightly capped and
            # phased in by the amount of historical support instead of fabricated.
            latent_dilution_shares = max(0.0, basic_shares * dilution_schedule.proxy_latent_dilution_rate)
            diluted_shares = max(1e-6, basic_shares + latent_dilution_shares)
            share_bridge_point = _ForecastShareBridgePoint(
                year=year,
                basic_shares=basic_shares,
                rsu_shares=0.0,
                acquisition_shares=0.0,
                buyback_retirement_shares=0.0,
                option_warrant_dilution_shares=0.0,
                convertible_dilution_shares=0.0,
                latent_dilution_shares=latent_dilution_shares,
                proxy_net_change_shares=proxy_net_change_shares,
                diluted_shares=diluted_shares,
                uses_proxy_fallback=True,
            )
        else:
            rsu_shares = max(0.0, dilution_schedule.annual_rsu_shares + max(0.0, tweaks.sbc_shift * basic_shares))
            acquisition_shares = max(0.0, dilution_schedule.annual_acquisition_shares + max(0.0, tweaks.dilution_shift * basic_shares))
            buyback_retirement_shares = max(0.0, dilution_schedule.annual_buyback_shares + (tweaks.buyback_shift * basic_shares))
            option_warrant_dilution_shares = dilution_schedule.option_warrant_dilution_shares
            convertible_dilution_shares = dilution_schedule.convertible_dilution_shares
            basic_shares = max(1e-6, basic_shares + rsu_shares + acquisition_shares - buyback_retirement_shares)
            diluted_shares = max(1e-6, basic_shares + option_warrant_dilution_shares + convertible_dilution_shares)
            share_bridge_point = _ForecastShareBridgePoint(
                year=year,
                basic_shares=basic_shares,
                rsu_shares=rsu_shares,
                acquisition_shares=acquisition_shares,
                buyback_retirement_shares=buyback_retirement_shares,
                option_warrant_dilution_shares=option_warrant_dilution_shares,
                convertible_dilution_shares=convertible_dilution_shares,
                latent_dilution_shares=0.0,
                proxy_net_change_shares=0.0,
                diluted_shares=diluted_shares,
                uses_proxy_fallback=False,
            )
        eps = _safe_divide(net_income, diluted_shares)

        operating_income_values.append(operating_income)
        net_income_values.append(net_income)
        ebitda_values.append(ebitda)
        operating_cash_flow_values.append(operating_cash_flow)
        free_cash_flow_values.append(free_cash_flow)
        capex_values.append(capex)
        diluted_shares_values.append(diluted_shares)
        eps_values.append(eps if eps is not None else 0.0)
        bridge_points.append(bridge_point)
        share_bridge_points.append(share_bridge_point)

        previous_revenue = revenue
        previous_working_capital = target_working_capital
        previous_depreciation = depreciation
        cash_balance = bridge_point.ending_cash
        debt_balance = bridge_point.ending_debt

    return DriverForecastScenario(
        key=scenario_key,
        label=SCENARIO_LABELS[scenario_key],
        revenue=DriverForecastLine(years=years, values=revenue_values),
        revenue_growth=DriverForecastLine(years=years, values=revenue_growth_values),
        operating_income=DriverForecastLine(years=years, values=operating_income_values),
        net_income=DriverForecastLine(years=years, values=net_income_values),
        ebitda=DriverForecastLine(years=years, values=ebitda_values),
        operating_cash_flow=DriverForecastLine(years=years, values=operating_cash_flow_values),
        free_cash_flow=DriverForecastLine(years=years, values=free_cash_flow_values),
        capex=DriverForecastLine(years=years, values=capex_values),
        diluted_shares=DriverForecastLine(years=years, values=diluted_shares_values),
        eps=DriverForecastLine(years=years, values=eps_values),
        bridge=bridge_points,
        share_bridge=share_bridge_points,
    )


def _project_below_line_bridge(
    *,
    year: int,
    revenue: float,
    ebit: float,
    depreciation: float,
    stock_based_compensation: float,
    delta_working_capital: float,
    capex: float,
    opening_cash: float,
    opening_debt: float,
    beginning_operating_working_capital: float,
    ending_operating_working_capital: float,
    accounts_receivable: float,
    inventory: float,
    accounts_payable: float,
    deferred_revenue: float,
    accrued_operating_liabilities: float,
    schedule: _BelowLineSchedule,
) -> _ForecastBridgePoint:
    ending_cash = opening_cash
    ending_debt = opening_debt
    other_income_expense = revenue * schedule.other_income_ratio

    for _ in range(2):
        average_cash = _average_balance(opening_cash, ending_cash) or 0.0
        average_debt = _average_balance(opening_debt, ending_debt) or 0.0
        interest_expense = average_debt * schedule.debt_interest_rate
        interest_income = average_cash * schedule.cash_yield
        pretax_income = ebit - interest_expense + interest_income + other_income_expense
        taxes = _project_taxes(pretax_income, schedule.effective_tax_rate)
        net_income = pretax_income - taxes
        operating_cash_flow = net_income + depreciation + stock_based_compensation - delta_working_capital
        free_cash_flow = operating_cash_flow - capex
        ending_cash, ending_debt = _roll_forward_cash_and_debt(
            opening_cash,
            opening_debt,
            free_cash_flow,
            revenue,
            schedule.target_cash_ratio,
        )

    average_cash = _average_balance(opening_cash, ending_cash) or 0.0
    average_debt = _average_balance(opening_debt, ending_debt) or 0.0
    interest_expense = average_debt * schedule.debt_interest_rate
    interest_income = average_cash * schedule.cash_yield
    pretax_income = ebit - interest_expense + interest_income + other_income_expense
    taxes = _project_taxes(pretax_income, schedule.effective_tax_rate)
    net_income = pretax_income - taxes
    operating_cash_flow = net_income + depreciation + stock_based_compensation - delta_working_capital
    free_cash_flow = operating_cash_flow - capex
    ending_cash, ending_debt = _roll_forward_cash_and_debt(
        opening_cash,
        opening_debt,
        free_cash_flow,
        revenue,
        schedule.target_cash_ratio,
    )

    return _ForecastBridgePoint(
        year=year,
        ebit=ebit,
        interest_expense=interest_expense,
        interest_income=interest_income,
        other_income_expense=other_income_expense,
        pretax_income=pretax_income,
        taxes=taxes,
        net_income=net_income,
        depreciation=depreciation,
        stock_based_compensation=stock_based_compensation,
        delta_working_capital=delta_working_capital,
        operating_cash_flow=operating_cash_flow,
        capex=capex,
        free_cash_flow=free_cash_flow,
        beginning_cash=opening_cash,
        ending_cash=ending_cash,
        beginning_debt=opening_debt,
        ending_debt=ending_debt,
        beginning_operating_working_capital=beginning_operating_working_capital,
        ending_operating_working_capital=ending_operating_working_capital,
        accounts_receivable=accounts_receivable,
        inventory=inventory,
        accounts_payable=accounts_payable,
        deferred_revenue=deferred_revenue,
        accrued_operating_liabilities=accrued_operating_liabilities,
    )


def _roll_forward_cash_and_debt(
    opening_cash: float,
    opening_debt: float,
    free_cash_flow: float,
    revenue: float,
    target_cash_ratio: float,
) -> tuple[float, float]:
    target_cash = max(0.0, revenue * target_cash_ratio)
    pre_financing_cash = opening_cash + free_cash_flow
    if pre_financing_cash < target_cash:
        debt_draw = target_cash - pre_financing_cash
        return target_cash, opening_debt + debt_draw

    excess_cash = pre_financing_cash - target_cash
    debt_repayment = min(opening_debt, max(0.0, excess_cash))
    ending_debt = max(0.0, opening_debt - debt_repayment)
    ending_cash = pre_financing_cash - debt_repayment
    return max(0.0, ending_cash), ending_debt


def _project_taxes(pretax_income: float, effective_tax_rate: float) -> float:
    if pretax_income >= 0:
        return pretax_income * effective_tax_rate
    return pretax_income * min(effective_tax_rate, LOSS_TAX_BENEFIT_CAP)


def _top_down_revenue_projection(
    history: list[dict[str, Any]],
    revenue_drivers: _RevenueDrivers,
    tweaks: _ScenarioTweaks,
    latest_year: int,
    horizon_years: int,
) -> list[tuple[int, float, float]]:
    latest_revenue = history[-1]["revenue"] or 0.0
    results: list[tuple[int, float, float]] = []
    revenue = latest_revenue
    for index in range(horizon_years):
        demand_growth = _mean_revert(revenue_drivers.market_growth + tweaks.demand_shift, TERMINAL_MARKET_GROWTH, 0.30 + (index * 0.15))
        share_change = _mean_revert(revenue_drivers.market_share_change + tweaks.share_shift, 0.0, 0.40 + (index * 0.15))
        price_growth = _mean_revert(revenue_drivers.pricing_growth + tweaks.price_shift, TERMINAL_PRICE_GROWTH, 0.35 + (index * 0.15))
        revenue_growth = _clip(demand_growth + share_change + price_growth + (max(demand_growth, 0.0) * price_growth), REVENUE_GROWTH_FLOOR, REVENUE_GROWTH_CAP)
        revenue = _apply_revenue_overlays(revenue, revenue_growth, revenue_drivers, index)
        growth = _growth_rate(revenue, latest_revenue if index == 0 else results[-1][1]) or 0.0
        results.append((latest_year + index + 1, revenue, growth))
    return results


def _bottom_up_revenue_projection(
    history: list[dict[str, Any]],
    revenue_drivers: _RevenueDrivers,
    tweaks: _ScenarioTweaks,
    latest_year: int,
    horizon_years: int,
) -> list[tuple[int, float, float]]:
    latest_revenue = history[-1]["revenue"] or 0.0
    segment_revenues = {segment["segment_id"]: float(segment["latest_revenue"]) for segment in revenue_drivers.segment_profiles}
    results: list[tuple[int, float, float]] = []
    for index in range(horizon_years):
        next_segment_revenues: dict[str, float] = {}
        for segment in revenue_drivers.segment_profiles:
            previous_segment_revenue = segment_revenues[segment["segment_id"]]
            demand_growth = _mean_revert(segment["base_growth"] - segment["price_growth"] + tweaks.demand_shift, revenue_drivers.market_growth, 0.30 + (index * 0.12))
            share_change = _mean_revert(segment["share_change"] + tweaks.share_shift, 0.0, 0.40 + (index * 0.15))
            price_growth = _mean_revert(segment["price_growth"] + tweaks.price_shift, TERMINAL_PRICE_GROWTH, 0.35 + (index * 0.15))
            segment_growth = _clip(demand_growth + share_change + price_growth + (max(demand_growth, 0.0) * price_growth), REVENUE_GROWTH_FLOOR, REVENUE_GROWTH_CAP)
            next_segment_revenues[segment["segment_id"]] = previous_segment_revenue * (1.0 + segment_growth)
        raw_total = sum(next_segment_revenues.values())
        adjusted_total = _apply_revenue_overlays(latest_revenue if index == 0 else results[-1][1], _growth_rate(raw_total, latest_revenue if index == 0 else results[-1][1]) or 0.0, revenue_drivers, index)
        if raw_total > 0 and adjusted_total > 0:
            scale = adjusted_total / raw_total
            segment_revenues = {segment_id: value * scale for segment_id, value in next_segment_revenues.items()}
        else:
            segment_revenues = next_segment_revenues
        growth = _growth_rate(adjusted_total, latest_revenue if index == 0 else results[-1][1]) or 0.0
        results.append((latest_year + index + 1, adjusted_total, growth))
    return results


def _apply_revenue_overlays(previous_revenue: float, revenue_growth: float, revenue_drivers: _RevenueDrivers, index: int) -> float:
    growth = revenue_growth
    if index == 0 and revenue_drivers.guidance_anchor is not None:
        guided_growth = _growth_rate(revenue_drivers.guidance_anchor, previous_revenue)
        if guided_growth is not None and 0.5 <= (revenue_drivers.guidance_anchor / previous_revenue) <= 1.6:
            growth = ((growth * 0.35) + (guided_growth * 0.65))
    if index == 0 and revenue_drivers.backlog_floor_growth is not None:
        growth = max(growth, revenue_drivers.backlog_floor_growth)
    if revenue_drivers.capacity_growth_cap is not None:
        growth = min(growth, revenue_drivers.capacity_growth_cap)
    growth = _clip(growth, REVENUE_GROWTH_FLOOR, REVENUE_GROWTH_CAP)
    return previous_revenue * (1.0 + growth)


def _build_assumption_rows(
    history: list[dict[str, Any]],
    revenue_drivers: _RevenueDrivers,
    cost_schedule: _CostSchedule,
    reinvestment_schedule: _ReinvestmentSchedule,
    below_line_schedule: _BelowLineSchedule,
    dilution_schedule: _DilutionSchedule,
) -> list[dict[str, str]]:
    return [
        {
            "key": "revenue_method",
            "label": "Revenue Method",
            "value": revenue_drivers.mode.replace("_", " ").title(),
            "detail": "Top-down market-share logic is used by default and automatically upgrades to bottom-up segment aggregation when segment history is available.",
        },
        {
            "key": "price_volume",
            "label": "Price x Volume",
            "value": f"{_pct(revenue_drivers.pricing_growth)} price / {_pct(revenue_drivers.volume_growth)} volume",
            "detail": "Revenue growth is built from explicit pricing, market growth, and market-share assumptions instead of a single historical extrapolation.",
        },
        {
            "key": "market_share",
            "label": "Market Growth + Share",
            "value": f"{_pct(revenue_drivers.market_growth)} market / {_pct(revenue_drivers.market_share_change)} share",
            "detail": "The top-down path uses market growth plus share change; the bottom-up path applies the same logic at the segment level.",
        },
        {
            "key": "guidance_overlay",
            "label": "Management Guidance",
            "value": _money(revenue_drivers.guidance_anchor),
            "detail": "When earnings releases include revenue guidance, year-one revenue is anchored toward the guided midpoint without using later releases.",
        },
        {
            "key": "cost_schedule",
            "label": "Cost Schedule",
            "value": f"{_pct(1.0 - cost_schedule.variable_cost_ratio)} gross contribution / {_pct(cost_schedule.latest_operating_margin)} EBIT margin",
            "detail": "Operating leverage is driven by separate variable, semi-variable, and fixed cost buckets.",
        },
        {
            "key": "operating_working_capital",
            "label": "Operating Working Capital",
            "value": (
                f"{reinvestment_schedule.operating_working_capital.dso:.0f} DSO / "
                f"{reinvestment_schedule.operating_working_capital.dio:.0f} DIO / "
                f"{reinvestment_schedule.operating_working_capital.dpo:.0f} DPO"
            ),
            "detail": (
                f"Deferred revenue {reinvestment_schedule.operating_working_capital.deferred_revenue_days:.0f} days; "
                f"accrued operating liabilities {reinvestment_schedule.operating_working_capital.accrued_operating_liability_days:.0f} days. "
                f"Excludes cash, short-term investments, short-term debt, current maturities, and other financing items. "
                f"{reinvestment_schedule.operating_working_capital.basis_detail}"
            ),
        },
        {
            "key": "reinvestment",
            "label": "Incremental Capital",
            "value": f"{reinvestment_schedule.sales_to_capital:.2f}x sales-to-capital",
            "detail": "Sales-to-capital sizes positive-growth fixed-capital reinvestment only; delta operating working capital is modeled separately in operating cash flow so the bridge does not double count it.",
        },
        {
            "key": "capex_dep",
            "label": "Capex / Depreciation",
            "value": f"{_pct(reinvestment_schedule.capex_intensity)} capex / {_pct(reinvestment_schedule.depreciation_ratio)} D&A",
            "detail": "Capex is the higher of maintenance capex and depreciation plus positive-growth fixed-capital reinvestment.",
        },
        {
            "key": "below_line_bridge",
            "label": "Below-The-Line Bridge",
            "value": f"{_pct(below_line_schedule.debt_interest_rate)} debt cost / {_pct(below_line_schedule.cash_yield)} cash yield / {_pct(below_line_schedule.effective_tax_rate)} tax",
            "detail": "Pretax income explicitly bridges from EBIT through interest expense, interest income, other income or expense, and taxes instead of using a flat EBIT-to-net conversion.",
        },
        {
            "key": "cash_debt_support",
            "label": "Cash + Debt Support",
            "value": f"{_money(below_line_schedule.starting_cash)} cash / {_money(below_line_schedule.starting_debt)} debt",
            "detail": f"Cash basis: {below_line_schedule.cash_basis}. Debt basis: {below_line_schedule.debt_basis}. Interest basis: {below_line_schedule.interest_basis}. Other basis: {below_line_schedule.other_basis}. Tax basis: {below_line_schedule.tax_basis}.",
        },
        {
            "key": "dilution",
            "label": "Dilution Bridge",
            "value": (
                "Proxy fallback from historical share drift"
                if dilution_schedule.uses_proxy_fallback
                else (
                    f"{_shares(dilution_schedule.starting_basic_shares)} basic + {_shares(dilution_schedule.option_warrant_dilution_shares)} TSM + "
                    f"{_shares(dilution_schedule.annual_rsu_shares)} RSU / SBC + {_shares(dilution_schedule.convertible_dilution_shares)} converts"
                )
            ),
            "detail": (
                f"Fallback basis: {dilution_schedule.fallback_basis}."
                if dilution_schedule.uses_proxy_fallback
                else (
                    f"Starting basis: {dilution_schedule.starting_basis}. Options and warrants: {dilution_schedule.option_basis}. "
                    f"RSU / SBC issuance: {dilution_schedule.rsu_basis}. Buybacks: {dilution_schedule.buyback_basis}. "
                    f"Acquisition issuance: {dilution_schedule.acquisition_basis}. Convertibles: {dilution_schedule.convert_basis}."
                )
            ),
        },
        {
            "key": "history_depth",
            "label": "History Depth",
            "value": f"{len(history)} annual periods",
            "detail": "The driver engine falls back to the older heuristic path when the historical statement set is too thin to support explicit schedules.",
        },
    ]


def _build_calculation_rows(
    revenue_drivers: _RevenueDrivers,
    cost_schedule: _CostSchedule,
    reinvestment_schedule: _ReinvestmentSchedule,
    below_line_schedule: _BelowLineSchedule,
    dilution_schedule: _DilutionSchedule,
    base_scenario: DriverForecastScenario,
) -> list[dict[str, str]]:
    base_revenue = _first_value(base_scenario.revenue.values)
    base_margin = _safe_divide(_first_value(base_scenario.operating_income.values), _first_value(base_scenario.revenue.values))
    base_eps = _first_value(base_scenario.eps.values)
    base_bridge = base_scenario.bridge[0] if base_scenario.bridge else None
    return [
        {
            "key": "formula_revenue",
            "label": "Revenue Formula",
            "value": "Prior revenue x (1 + price + market growth + share)",
            "detail": "Year-one revenue is then overlaid with any point-in-time-safe guidance, backlog floors, and capacity caps.",
        },
        {
            "key": "formula_margin",
            "label": "Operating Income Formula",
            "value": "Revenue - variable costs - semi-variable costs - fixed costs",
            "detail": f"Base variable cost ratio {_pct(cost_schedule.variable_cost_ratio)}; semi-variable cost ratio {_pct(cost_schedule.semi_variable_cost_ratio)}.",
        },
        {
            "key": "formula_pretax",
            "label": "Pretax Income Formula",
            "value": "EBIT - interest expense + interest income + other income or expense",
            "detail": (
                f"Base FY{base_bridge.year}E: EBIT {_money(base_bridge.ebit)}, interest expense {_money(base_bridge.interest_expense)}, interest income {_money(base_bridge.interest_income)}, other {_money(base_bridge.other_income_expense)}, pretax {_money(base_bridge.pretax_income)}."
                if base_bridge is not None
                else f"Interest runs at {_pct(below_line_schedule.debt_interest_rate)} on average debt and cash earns {_pct(below_line_schedule.cash_yield)}."
            ),
        },
        {
            "key": "formula_tax",
            "label": "Tax Formula",
            "value": "Pretax income x effective tax rate",
            "detail": (
                f"Base FY{base_bridge.year}E taxes {_money(base_bridge.taxes)} on pretax income {_money(base_bridge.pretax_income)} at {_pct(below_line_schedule.effective_tax_rate)}."
                if base_bridge is not None
                else f"Effective tax rate {_pct(below_line_schedule.effective_tax_rate)} from {below_line_schedule.tax_basis.lower()}."
            ),
        },
        {
            "key": "formula_reinvestment",
            "label": "Capex Formula",
            "value": "max(maintenance capex, D&A + max(delta revenue, 0) / sales-to-capital)",
            "detail": (
                (
                    f"Base FY{base_bridge.year}E: maintenance capex is the higher of {_money((base_revenue or 0.0) * reinvestment_schedule.capex_intensity)} and D&A {_money(base_bridge.depreciation)}; "
                    f"positive-growth fixed capital uses {reinvestment_schedule.sales_to_capital:.2f}x sales-to-capital. "
                    f"Delta operating working capital {_money(base_bridge.delta_working_capital)} flows through OCF, not capex."
                )
                if base_bridge is not None
                else (
                    f"Maintenance capex uses {_pct(reinvestment_schedule.capex_intensity)} of revenue with a D&A floor; "
                    f"positive-growth fixed capital uses {reinvestment_schedule.sales_to_capital:.2f}x sales-to-capital. "
                    "Delta operating working capital flows through OCF, not capex."
                )
            ),
        },
        {
            "key": "formula_ocf",
            "label": "Operating Cash Flow Formula",
            "value": "Net income + D&A + SBC - delta operating working capital",
            "detail": (
                f"Base FY{base_bridge.year}E: net income {_money(base_bridge.net_income)} + D&A {_money(base_bridge.depreciation)} + SBC {_money(base_bridge.stock_based_compensation)} - delta operating WC {_money(base_bridge.delta_working_capital)} = OCF {_money(base_bridge.operating_cash_flow)}."
                if base_bridge is not None
                else (
                    f"SBC expense ratio {_pct(dilution_schedule.sbc_expense_ratio)}; "
                    f"working-capital schedule {reinvestment_schedule.operating_working_capital.dso:.0f} / "
                    f"{reinvestment_schedule.operating_working_capital.dio:.0f} / "
                    f"{reinvestment_schedule.operating_working_capital.dpo:.0f} days."
                )
            ),
        },
        {
            "key": "formula_fcf",
            "label": "Free Cash Flow Formula",
            "value": "Operating cash flow - capex",
            "detail": (
                f"Base FY{base_bridge.year}E: OCF {_money(base_bridge.operating_cash_flow)} - capex {_money(base_bridge.capex)} = FCF {_money(base_bridge.free_cash_flow)}."
                if base_bridge is not None
                else "Cash and debt balances roll forward from free cash flow after preserving a target cash buffer."
            ),
        },
        {
            "key": "formula_eps",
            "label": "Diluted EPS Formula",
            "value": "Net income / diluted shares",
            "detail": f"Base case next-year EPS {_money(base_eps)} at {_pct(base_margin)} operating margin.",
        },
        {
            "key": "segment_basis",
            "label": "Bottom-Up Basis",
            "value": (revenue_drivers.segment_basis or "Top-down only").replace("_", " ").title(),
            "detail": "When segment, geography, or product disclosures exist, the engine aggregates the forecast bottom-up before applying company-level overlays.",
        },
    ]


def _build_highlights(revenue_drivers: _RevenueDrivers, base: DriverForecastScenario, bull: DriverForecastScenario, bear: DriverForecastScenario) -> list[str]:
    base_margin = _safe_divide(_first_value(base.operating_income.values), _first_value(base.revenue.values))
    bull_eps = _first_value(bull.eps.values)
    bear_eps = _first_value(bear.eps.values)
    return [
        f"Base next-year revenue {_pct(_first_value(base.revenue_growth.values))} via {revenue_drivers.mode.replace('_', ' ')}.",
        f"Base next-year EBIT margin {_pct(base_margin)} from explicit cost buckets.",
        f"Bull / Bear next-year EPS {_money(bull_eps)} / {_money(bear_eps)} after explicit interest, tax, and dilution schedules.",
    ]


def _build_sensitivity_rows(scenarios: dict[str, DriverForecastScenario]) -> list[dict[str, str]]:
    base = scenarios["base"]
    bull = scenarios["bull"]
    bear = scenarios["bear"]
    bull_margin = _safe_divide(_first_value(bull.operating_income.values), _first_value(bull.revenue.values))
    bear_margin = _safe_divide(_first_value(bear.operating_income.values), _first_value(bear.revenue.values))
    return [
        {
            "key": "sensitivity_growth",
            "label": "Growth Sensitivity",
            "value": f"{_pct(_first_value(bear.revenue_growth.values))} to {_pct(_first_value(bull.revenue_growth.values))}",
            "detail": "Bull and bear demand plus share assumptions frame the next-year top-line sensitivity band.",
        },
        {
            "key": "sensitivity_margin",
            "label": "Margin Sensitivity",
            "value": f"{_pct(bear_margin)} to {_pct(bull_margin)}",
            "detail": "Variable, semi-variable, and fixed cost schedules create the operating leverage range across scenarios.",
        },
        {
            "key": "sensitivity_dilution",
            "label": "Dilution Sensitivity",
            "value": f"{_pct(_share_change(base.diluted_shares.values, bear.diluted_shares.values))} bear vs {_pct(_share_change(base.diluted_shares.values, bull.diluted_shares.values))} bull",
            "detail": "SBC, buyback, acquisition, and convert assumptions drive share-count sensitivity into EPS.",
        },
    ]


def _latest_guidance_revenue(releases: list[Any]) -> float | None:
    for release in sorted(
        releases,
        key=lambda item: (
            getattr(item, "filing_acceptance_at", None) or getattr(item, "filing_date", None) or getattr(item, "reported_period_end", None),
            getattr(item, "id", 0),
        ),
        reverse=True,
    ):
        low = _as_float(getattr(release, "revenue_guidance_low", None))
        high = _as_float(getattr(release, "revenue_guidance_high", None))
        if low is not None and high is not None:
            return (low + high) / 2.0
        if low is not None:
            return low
        if high is not None:
            return high
    return None


def _pricing_growth_proxy(history: list[dict[str, Any]]) -> float:
    revenue_growth = _historical_growth_rates([row["revenue"] for row in history])
    margin_changes: list[float] = []
    for previous, current in zip(history, history[1:]):
        previous_margin = _safe_divide(previous["operating_income"], previous["revenue"])
        current_margin = _safe_divide(current["operating_income"], current["revenue"])
        if previous_margin is None or current_margin is None:
            continue
        margin_changes.append(current_margin - previous_margin)
    margin_signal = median(margin_changes) if margin_changes else 0.0
    growth_signal = _weighted_recent_growth(revenue_growth) or TERMINAL_MARKET_GROWTH
    return _clip((growth_signal * 0.18) + (margin_signal * 0.40), PRICE_GROWTH_FLOOR, PRICE_GROWTH_CAP)


def _share_shift_proxy(history: list[dict[str, Any]]) -> float:
    segment_years = [row["segments"] for row in history if row["segments"]]
    if len(segment_years) < 2:
        return 0.0
    shifts: list[float] = []
    for previous, current in zip(segment_years, segment_years[1:]):
        previous_map = {segment["segment_id"]: segment for segment in previous}
        current_map = {segment["segment_id"]: segment for segment in current}
        for segment_id, current_segment in current_map.items():
            previous_segment = previous_map.get(segment_id)
            current_share = current_segment.get("share_of_revenue")
            previous_share = previous_segment.get("share_of_revenue") if previous_segment else None
            if current_share is None or previous_share is None:
                continue
            shifts.append(float(current_share) - float(previous_share))
    return _clip(fmean(shifts), SHARE_CHANGE_FLOOR, SHARE_CHANGE_CAP) if shifts else 0.0


def _backlog_floor_growth(latest: dict[str, Any]) -> float | None:
    statement = latest["statement"]
    data = getattr(statement, "data", None)
    revenue = latest.get("revenue")
    if not isinstance(data, dict) or revenue is None or revenue <= 0:
        return None
    backlog_value = None
    for key in ("order_backlog", "backlog", "remaining_performance_obligations"):
        backlog_value = _as_float(data.get(key))
        if backlog_value is not None:
            break
    if backlog_value is None or backlog_value <= 0:
        return None
    return _clip((backlog_value / revenue) * 0.18, 0.0, 0.20)


def _capacity_constraint(latest: dict[str, Any], sales_to_capital: float | None) -> tuple[float | None, float | None]:
    statement = latest["statement"]
    data = getattr(statement, "data", None)
    if not isinstance(data, dict):
        return None, None

    utilization = None
    for key in ("capacity_utilization", "utilization", "utilization_ratio"):
        utilization = _as_float(data.get(key))
        if utilization is not None:
            if utilization > 1:
                utilization /= 100.0
            break

    capacity = _as_float(data.get("capacity"))
    latest_revenue = latest.get("revenue")
    capex = latest.get("capex")
    if utilization is None and capacity is None:
        return None, None

    capex_ratio = _safe_divide(capex, latest_revenue) or 0.04
    turnover = sales_to_capital or 1.0
    capacity_growth_cap = _clip((capex_ratio * turnover) + (max(0.0, 1.0 - (utilization or 1.0)) * 0.20), 0.02, 0.25)
    return capacity_growth_cap, utilization


def _segment_profiles(history: list[dict[str, Any]], market_growth: float, pricing_growth: float) -> tuple[list[dict[str, Any]], str | None]:
    latest_segments = history[-1]["segments"]
    if len(latest_segments) < 2:
        return [], None
    basis = _preferred_segment_basis(latest_segments)
    profiles: list[dict[str, Any]] = []
    for latest_segment in latest_segments:
        segment_id = latest_segment["segment_id"]
        revenues: list[float] = []
        share_series: list[float] = []
        for row in history:
            match = next((segment for segment in row["segments"] if segment["segment_id"] == segment_id), None)
            if match is None:
                continue
            revenue = _as_float(match.get("revenue"))
            share = _as_float(match.get("share_of_revenue"))
            if revenue is not None:
                revenues.append(revenue)
            if share is not None:
                share_series.append(share)
        if len(revenues) < 2:
            continue
        base_growth = _blend_optional(_weighted_recent_growth(_historical_growth_rates(revenues)), _cagr(revenues[-4:])) or market_growth
        share_change = _weighted_recent_growth([current - previous for previous, current in zip(share_series, share_series[1:])]) or 0.0
        operating_margin = _safe_divide(latest_segment.get("operating_income"), latest_segment.get("revenue")) or 0.0
        profiles.append(
            {
                "segment_id": segment_id,
                "segment_name": latest_segment["segment_name"],
                "kind": latest_segment.get("kind"),
                "latest_revenue": float(latest_segment["revenue"]),
                "base_growth": _clip(base_growth, REVENUE_GROWTH_FLOOR, REVENUE_GROWTH_CAP),
                "price_growth": _clip(pricing_growth + (operating_margin * 0.02), PRICE_GROWTH_FLOOR, PRICE_GROWTH_CAP),
                "share_change": _clip(share_change, SHARE_CHANGE_FLOOR, SHARE_CHANGE_CAP),
            }
        )
    return (profiles, basis) if len(profiles) >= 2 else ([], None)


def _preferred_segment_basis(segments: list[dict[str, Any]]) -> str | None:
    counts: dict[str, int] = {}
    for segment in segments:
        kind = str(segment.get("kind") or "other")
        counts[kind] = counts.get(kind, 0) + 1
    return max(counts.items(), key=lambda item: item[1])[0] if counts else None


def _sales_to_capital(history: list[dict[str, Any]]) -> float | None:
    values: list[float] = []
    for row in history:
        revenue = row["revenue"]
        total_assets = row["total_assets"]
        if revenue is None or total_assets in (None, 0):
            continue
        ratio = revenue / total_assets
        if isfinite(ratio) and ratio > 0:
            values.append(_clip(ratio, SALES_TO_CAPITAL_FLOOR, SALES_TO_CAPITAL_CAP))
    return median(values) if values else None


def _statement_value(statement: Any, key: str) -> float | None:
    data = getattr(statement, "data", None)
    if not isinstance(data, dict):
        return None
    value = data.get(key)
    if key == "weighted_average_shares_basic":
        for alias in ("weighted_average_shares_basic", "weighted_average_basic_shares"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "weighted_average_shares_diluted":
        value = data.get("weighted_average_shares_diluted", data.get("weighted_average_diluted_shares"))
    if key == "shares_issued":
        for alias in ("shares_issued", "common_shares_issued"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "shares_repurchased":
        for alias in ("shares_repurchased", "common_shares_repurchased"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "share_price":
        for alias in ("current_share_price", "market_price", "share_price"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "option_warrant_dilution_shares":
        for alias in ("option_warrant_dilution_shares", "dilutive_option_warrant_shares", "dilutive_option_shares"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "options_outstanding":
        for alias in ("options_outstanding", "employee_stock_options_outstanding", "in_the_money_options_outstanding"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "warrants_outstanding":
        for alias in ("warrants_outstanding", "dilutive_warrants_outstanding", "in_the_money_warrants_outstanding"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "option_exercise_price":
        for alias in ("option_exercise_price", "options_average_exercise_price", "average_option_strike"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "warrant_exercise_price":
        for alias in ("warrant_exercise_price", "warrants_average_exercise_price", "average_warrant_strike"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "rsu_shares":
        for alias in ("rsu_shares", "restricted_stock_units", "unvested_rsu_shares", "stock_award_shares", "dilutive_rsu_shares"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "acquisition_shares_issued":
        for alias in ("acquisition_shares_issued", "shares_issued_for_acquisition", "acquisition_share_issuance"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "convertible_dilution_shares":
        for alias in ("dilutive_convertible_shares", "convertible_shares"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "convertible_conversion_price":
        for alias in ("convertible_conversion_price", "convert_conversion_price", "conversion_price"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "convertible_is_dilutive":
        for alias in ("convertible_is_dilutive", "convert_is_dilutive", "convertible_dilutive"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "free_cash_flow":
        direct_value = _as_float(value)
        if direct_value is not None:
            return direct_value
        operating_cash_flow = _as_float(data.get("operating_cash_flow"))
        capex = _as_float(data.get("capex"))
        if operating_cash_flow is not None and capex is not None:
            return operating_cash_flow - capex
        return None
    if key == "pretax_income":
        for alias in (
            "pretax_income",
            "income_before_tax",
            "income_before_income_taxes",
            "income_before_taxes",
            "earnings_before_tax",
            "pretax_earnings",
        ):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "income_tax_expense":
        for alias in ("income_tax_expense", "provision_for_income_taxes"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "interest_income":
        for alias in ("interest_income", "interest_and_investment_income", "investment_income"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "other_income_expense":
        for alias in (
            "other_income_expense",
            "other_non_operating_income_expense",
            "non_operating_income_expense",
            "other_income",
        ):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "cash_balance":
        for alias in ("cash_and_short_term_investments", "cash_and_cash_equivalents", "cash_equivalents"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "total_debt":
        direct_value = _as_float(data.get("total_debt"))
        if direct_value is not None:
            return direct_value
        current_debt = _as_float(data.get("current_debt"))
        long_term_debt = _as_float(data.get("long_term_debt"))
        return _sum_non_null(current_debt, long_term_debt)
    if key == "gross_profit":
        return _as_float(data.get("gross_profit"))
    if key == "cost_of_revenue":
        direct_value = _as_float(data.get("cost_of_revenue") or data.get("cost_of_goods_sold"))
        if direct_value is not None:
            return direct_value
        revenue = _as_float(data.get("revenue"))
        gross_profit = _as_float(data.get("gross_profit"))
        if revenue is not None and gross_profit is not None:
            return max(0.0, revenue - gross_profit)
        return None
    if key == "deferred_revenue":
        for alias in ("deferred_revenue", "contract_liabilities", "current_contract_liabilities", "deferred_income"):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    if key == "accrued_operating_liabilities":
        for alias in (
            "accrued_operating_liabilities",
            "accrued_liabilities",
            "accrued_expenses",
            "accrued_compensation",
            "other_accrued_liabilities",
        ):
            alias_value = _as_float(data.get(alias))
            if alias_value is not None:
                return alias_value
        return None
    return _as_float(value)


def _operating_cost(row: dict[str, Any]) -> float | None:
    revenue = row["revenue"]
    operating_income = row["operating_income"]
    if revenue is None or operating_income is None:
        return None
    return revenue - operating_income


def _as_float(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if isfinite(numeric) else None


def _growth_rate(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous <= 0:
        return None
    if not isfinite(float(current)) or not isfinite(float(previous)):
        return None
    return (float(current) / float(previous)) - 1.0


def _historical_growth_rates(values: list[float | None]) -> list[float]:
    growths: list[float] = []
    for previous, current in zip(values, values[1:]):
        growth = _growth_rate(current, previous)
        if growth is not None:
            growths.append(growth)
    return growths


def _weighted_recent_growth(growths: list[float]) -> float | None:
    if not growths:
        return None
    window = growths[-len(RECENT_GROWTH_WEIGHTS) :]
    weights = RECENT_GROWTH_WEIGHTS[-len(window) :]
    total_weight = sum(weights)
    if total_weight == 0:
        return None
    return sum(value * weight for value, weight in zip(window, weights)) / total_weight


def _cagr(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    normalized: list[float] = []
    for value in values:
        numeric = _as_float(value)
        if numeric is None or numeric <= 0:
            return None
        normalized.append(numeric)
    return (normalized[-1] / normalized[0]) ** (1.0 / (len(normalized) - 1)) - 1.0


def _blend_optional(*values: float | None) -> float | None:
    cleaned = [float(value) for value in values if isinstance(value, (int, float)) and isfinite(float(value))]
    return fmean(cleaned) if cleaned else None


def _safe_divide(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    normalized_numerator = float(numerator)
    normalized_denominator = float(denominator)
    if not isfinite(normalized_numerator) or not isfinite(normalized_denominator) or normalized_denominator <= 0:
        return None
    return normalized_numerator / normalized_denominator


def _median_abs_ratio(history: list[dict[str, Any]], numerator_key: str, denominator_key: str) -> float | None:
    ratios: list[float] = []
    for row in history:
        numerator = row.get(numerator_key)
        denominator = row.get(denominator_key)
        ratio = _safe_divide(abs(numerator) if numerator is not None else None, denominator)
        if ratio is not None:
            ratios.append(ratio)
    return median(ratios) if ratios else None


def _positive_amount(value: float | None) -> float | None:
    if value is None:
        return None
    return abs(float(value)) if isfinite(float(value)) else None


def _average_balance(opening: float | None, ending: float | None) -> float | None:
    if opening is None and ending is None:
        return None
    if opening is None:
        return ending
    if ending is None:
        return opening
    return (opening + ending) / 2.0


def _derived_other_income_expense(row: dict[str, Any]) -> float | None:
    pretax_income = row.get("pretax_income")
    operating_income = row.get("operating_income")
    if pretax_income is None or operating_income is None:
        return None
    interest_expense = _positive_amount(row.get("interest_expense")) or 0.0
    interest_income = _positive_amount(row.get("interest_income")) or 0.0
    return pretax_income - operating_income + interest_expense - interest_income


def _sum_non_null(*values: float | None) -> float | None:
    present = [float(value) for value in values if value is not None and isfinite(float(value))]
    return sum(present) if present else None


def _latest_share_price(history: list[dict[str, Any]]) -> tuple[float | None, str]:
    for row in reversed(history):
        share_price = row.get("share_price")
        if share_price is not None and share_price > 0:
            return float(share_price), "Disclosed share price"
        repurchase_cash = _positive_amount(row.get("share_buybacks"))
        repurchased_shares = _positive_amount(row.get("shares_repurchased"))
        implied_price = _safe_divide(repurchase_cash, repurchased_shares)
        if implied_price is not None and implied_price > 0:
            return implied_price, "Implied repurchase price"
    return None, "No disclosed share price"


def _clip_share_amount(amount: float | None, starting_basic_shares: float, cap_rate: float) -> float:
    if amount is None or amount <= 0:
        return 0.0
    share_cap = max(1e-6, starting_basic_shares * cap_rate)
    return _clip(float(amount), 0.0, share_cap)


def _treasury_stock_increment(instrument_shares: float | None, strike_price: float | None, share_price: float | None) -> float:
    if instrument_shares is None or instrument_shares <= 0 or share_price is None or share_price <= 0 or strike_price is None:
        return 0.0
    if share_price <= strike_price:
        return 0.0
    repurchased_shares = (float(instrument_shares) * float(strike_price)) / float(share_price)
    return max(0.0, float(instrument_shares) - repurchased_shares)


def _derive_option_warrant_dilution_shares(
    latest: dict[str, Any],
    starting_basic_shares: float,
    latest_share_price: float | None,
    share_price_basis: str,
) -> tuple[float, str]:
    direct_shares = latest.get("option_warrant_dilution_shares")
    if direct_shares is not None and direct_shares > 0:
        return _clip_share_amount(direct_shares, starting_basic_shares, OPTION_WARRANT_DILUTION_CAP), "Direct dilutive option or warrant shares"

    option_increment = _treasury_stock_increment(latest.get("options_outstanding"), latest.get("option_exercise_price"), latest_share_price)
    warrant_increment = _treasury_stock_increment(latest.get("warrants_outstanding"), latest.get("warrant_exercise_price"), latest_share_price)
    total_increment = _clip_share_amount(option_increment + warrant_increment, starting_basic_shares, OPTION_WARRANT_DILUTION_CAP)
    if total_increment > 0:
        return total_increment, f"Treasury stock method using {share_price_basis.lower()}"
    if latest.get("options_outstanding") or latest.get("warrants_outstanding"):
        return 0.0, "Outstanding options or warrants disclosed, but TSM inputs are incomplete"
    return 0.0, "No option or warrant disclosure"


def _derive_acquisition_share_issuance(history: list[dict[str, Any]], starting_basic_shares: float) -> tuple[float, str]:
    direct_values: list[float] = []
    inferred_values: list[float] = []
    for row in history:
        direct_value = row.get("acquisition_shares_issued")
        if direct_value is not None and direct_value > 0:
            direct_values.append(direct_value)
            continue
        shares_issued = row.get("shares_issued")
        acquisitions = row.get("acquisitions")
        if shares_issued is not None and shares_issued > 0 and acquisitions is not None and acquisitions > 0:
            inferred_values.append(shares_issued)
    if direct_values:
        return _clip_share_amount(median(direct_values), starting_basic_shares, ACQUISITION_SHARE_ISSUANCE_CAP), "Direct acquisition share issuance"
    if inferred_values:
        return _clip_share_amount(median(inferred_values), starting_basic_shares, ACQUISITION_SHARE_ISSUANCE_CAP), "Issued shares aligned with acquisition activity"
    return 0.0, "No acquisition share issuance disclosure"


def _derive_rsu_share_issuance(history: list[dict[str, Any]], annual_acquisition_shares: float, starting_basic_shares: float) -> tuple[float, str]:
    direct_values: list[float] = []
    residual_values: list[float] = []
    for row in history:
        direct_value = row.get("rsu_shares")
        if direct_value is not None and direct_value > 0:
            direct_values.append(direct_value)
        shares_issued = row.get("shares_issued")
        acquisition_shares = row.get("acquisition_shares_issued")
        if shares_issued is not None and shares_issued > 0:
            residual_issued = shares_issued - max(acquisition_shares or annual_acquisition_shares, 0.0)
            if residual_issued > 0:
                residual_values.append(residual_issued)
    if direct_values:
        return _clip_share_amount(median(direct_values), starting_basic_shares, RSU_DILUTION_CAP), "Direct RSU or stock-award shares"
    if residual_values:
        return _clip_share_amount(median(residual_values), starting_basic_shares, RSU_DILUTION_CAP), "Residual issued-share bridge after acquisition issuance"
    return 0.0, "No RSU or stock-award share disclosure"


def _derive_buyback_retirement_shares(
    history: list[dict[str, Any]],
    latest_share_price: float | None,
    share_price_basis: str,
    starting_basic_shares: float,
) -> tuple[float, str]:
    direct_values: list[float] = []
    implied_values: list[float] = []
    for row in history:
        direct_value = row.get("shares_repurchased")
        if direct_value is not None and direct_value > 0:
            direct_values.append(direct_value)
            continue
        repurchase_cash = _positive_amount(row.get("share_buybacks"))
        local_share_price = row.get("share_price") or latest_share_price
        if repurchase_cash is not None and local_share_price is not None and local_share_price > 0:
            implied_values.append(repurchase_cash / local_share_price)
    if direct_values:
        return _clip_share_amount(median(direct_values), starting_basic_shares, BUYBACK_RETIREMENT_CAP), "Direct repurchased-share disclosure"
    if implied_values:
        return _clip_share_amount(median(implied_values), starting_basic_shares, BUYBACK_RETIREMENT_CAP), f"Repurchase cash translated into shares using {share_price_basis.lower()}"
    return 0.0, "No explicit repurchased-share disclosure"


def _derive_convertible_dilution_shares(
    latest: dict[str, Any],
    starting_basic_shares: float,
    latest_share_price: float | None,
    share_price_basis: str,
) -> tuple[float, str]:
    direct_shares = latest.get("convertible_dilution_shares")
    latest_data = getattr(latest.get("statement"), "data", None)
    if direct_shares is None and isinstance(latest_data, dict):
        direct_rate = _as_float(
            latest_data.get("convertible_dilution_rate")
            or latest_data.get("convert_dilution_rate")
            or latest_data.get("convertible_share_dilution")
        )
        if direct_rate is not None and direct_rate > 0:
            direct_shares = direct_rate * starting_basic_shares
    if direct_shares is None or direct_shares <= 0:
        return 0.0, "No convertible share disclosure"

    is_dilutive_flag = latest.get("convertible_is_dilutive")
    conversion_price = latest.get("convertible_conversion_price")
    is_dilutive = False
    if is_dilutive_flag is not None:
        is_dilutive = is_dilutive_flag > 0
    elif latest_share_price is not None and conversion_price is not None:
        is_dilutive = latest_share_price > conversion_price
    else:
        is_dilutive = True

    if not is_dilutive:
        return 0.0, "Convertible disclosure present but out of the money"
    return _clip_share_amount(direct_shares, starting_basic_shares, CONVERT_DILUTION_CAP), (
        f"If-converted shares using {share_price_basis.lower()}"
        if latest_share_price is not None and conversion_price is not None
        else "Direct dilutive convertible shares"
    )


def _derive_proxy_net_dilution_rate(history: list[dict[str, Any]], starting_diluted_shares: float) -> tuple[float, str]:
    share_history = [row["shares"] for row in history if row["shares"] is not None and row["shares"] > 0]
    share_growth = _weighted_recent_growth(_historical_growth_rates(share_history))
    sbc_expense_ratio = _clip(_median_abs_ratio(history, "stock_based_compensation", "revenue") or 0.0, 0.0, SBC_EXPENSE_RATIO_CAP)
    sbc_rate = _clip(max((sbc_expense_ratio * 0.18), max(share_growth or 0.0, 0.0) * 0.65), SBC_DILUTION_FLOOR, SBC_DILUTION_CAP)
    buyback_rate = _clip(max((_median_abs_ratio(history, "share_buybacks", "revenue") or 0.0) * 0.12, max(-(share_growth or 0.0), 0.0) * 0.65), BUYBACK_RETIREMENT_FLOOR, BUYBACK_RETIREMENT_CAP)
    acquisition_rate = _clip((_median_abs_ratio(history, "acquisitions", "revenue") or 0.0) * 0.05, 0.0, ACQUISITION_DILUTION_CAP)
    convert_rate = _clip(_safe_divide(_first_non_null_dilution_value(history, "convertible_dilution_shares"), starting_diluted_shares) or 0.0, 0.0, CONVERT_DILUTION_CAP)

    explicit_net = sbc_rate + acquisition_rate + convert_rate - buyback_rate
    if share_growth is not None:
        gap = share_growth - explicit_net
        if gap > 0:
            sbc_rate = _clip(sbc_rate + (gap * 0.7), SBC_DILUTION_FLOOR, SBC_DILUTION_CAP)
        elif gap < 0:
            buyback_rate = _clip(buyback_rate + (abs(gap) * 0.7), BUYBACK_RETIREMENT_FLOOR, BUYBACK_RETIREMENT_CAP)
    return sbc_rate + acquisition_rate + convert_rate - buyback_rate, "Historical diluted-share growth with revenue-scaled SBC, buyback, acquisition, and convert proxies"


def _derive_proxy_latent_dilution_rate(history: list[dict[str, Any]]) -> tuple[float, str | None]:
    spread_rates: list[float] = []
    for row in history:
        diluted_shares = row.get("shares")
        basic_shares = row.get("basic_shares")
        spread_rate = _safe_divide((diluted_shares - basic_shares) if diluted_shares is not None and basic_shares is not None else None, basic_shares)
        if spread_rate is not None and spread_rate > 0:
            spread_rates.append(spread_rate)
    if not spread_rates:
        return 0.0, None

    support_weight = min(1.0, len(spread_rates) / PROXY_LATENT_DILUTION_FULL_WEIGHT_OBS)
    median_spread_rate = median(spread_rates)
    latent_dilution_rate = _clip(median_spread_rate, 0.0, PROXY_LATENT_DILUTION_CAP) * support_weight
    return latent_dilution_rate, (
        "Latent dilution overlay uses the historical median diluted-vs-basic spread, "
        f"capped at {_pct(PROXY_LATENT_DILUTION_CAP)} and weighted by {len(spread_rates)} supporting periods."
    )


def _first_non_null_dilution_value(history: list[dict[str, Any]], key: str) -> float | None:
    for row in reversed(history):
        value = row.get(key)
        if value is not None and value > 0:
            return float(value)
    return None


def _resolved_cost_of_revenue(row: dict[str, Any], fallback_ratio: float | None = None) -> float | None:
    direct_value = row.get("cost_of_revenue")
    if direct_value is not None:
        return max(0.0, float(direct_value))
    revenue = row.get("revenue")
    gross_profit = row.get("gross_profit")
    if revenue is not None and gross_profit is not None:
        return max(0.0, float(revenue) - float(gross_profit))
    if revenue is not None and fallback_ratio is not None:
        return max(0.0, float(revenue) * float(fallback_ratio))
    operating_cost = _operating_cost(row)
    return max(0.0, float(operating_cost)) if operating_cost is not None else None


def _historical_cash_operating_cost(row: dict[str, Any], resolved_cost_of_revenue: float | None) -> float | None:
    revenue = row.get("revenue")
    operating_income = row.get("operating_income")
    depreciation = row.get("depreciation") or 0.0
    if revenue is not None and operating_income is not None:
        return max(0.0, float(revenue) - float(operating_income) - float(depreciation))
    return resolved_cost_of_revenue


def _days_to_balance(base_amount: float | None, days: float) -> float:
    if base_amount is None:
        return 0.0
    return max(0.0, float(base_amount) * (days / 365.0))


def _schedule_basis(label: str, values: list[float], default_days: float) -> str:
    if values:
        return f"{label} median from disclosure"
    if default_days == 0:
        return f"{label} assumed 0 when undisclosed"
    return f"{label} fallback {default_days:.0f} days"


def _operating_working_capital_total(
    accounts_receivable: float,
    inventory: float,
    accounts_payable: float,
    deferred_revenue: float,
    accrued_operating_liabilities: float,
) -> float:
    return accounts_receivable + inventory - accounts_payable - deferred_revenue - accrued_operating_liabilities


def _project_operating_working_capital_point(
    *,
    revenue: float,
    cost_of_revenue: float,
    cash_operating_cost: float,
    schedule: _OperatingWorkingCapitalSchedule,
    days_shift: float,
) -> dict[str, float]:
    accounts_receivable_days = _clip(schedule.dso + days_shift, DSO_FLOOR, DSO_CAP)
    inventory_days = _clip(schedule.dio + days_shift, DIO_FLOOR, DIO_CAP)
    accounts_payable_days = _clip(schedule.dpo - days_shift, DPO_FLOOR, DPO_CAP)
    deferred_revenue_days = _clip(schedule.deferred_revenue_days - days_shift, DEFERRED_REVENUE_DAYS_FLOOR, DEFERRED_REVENUE_DAYS_CAP)
    accrued_operating_liabilities_days = _clip(
        schedule.accrued_operating_liability_days - days_shift,
        ACCRUED_OPERATING_LIABILITY_DAYS_FLOOR,
        ACCRUED_OPERATING_LIABILITY_DAYS_CAP,
    )

    accounts_receivable = _days_to_balance(revenue, accounts_receivable_days)
    inventory = _days_to_balance(cost_of_revenue, inventory_days)
    accounts_payable = _days_to_balance(cost_of_revenue, accounts_payable_days)
    deferred_revenue = _days_to_balance(revenue, deferred_revenue_days)
    accrued_operating_liabilities = _days_to_balance(cash_operating_cost, accrued_operating_liabilities_days)

    return {
        "accounts_receivable": accounts_receivable,
        "inventory": inventory,
        "accounts_payable": accounts_payable,
        "deferred_revenue": deferred_revenue,
        "accrued_operating_liabilities": accrued_operating_liabilities,
        "total": _operating_working_capital_total(
            accounts_receivable,
            inventory,
            accounts_payable,
            deferred_revenue,
            accrued_operating_liabilities,
        ),
    }


def _mean_revert(current: float, target: float, speed: float) -> float:
    normalized_speed = _clip(speed, 0.0, 1.0)
    return current + ((target - current) * normalized_speed)


def _line_cagr(values: list[float]) -> float | None:
    return _cagr(values)


def _first_value(values: list[float]) -> float | None:
    return values[0] if values else None


def _share_change(base_values: list[float], comparison_values: list[float]) -> float | None:
    base = _first_value(base_values)
    comparison = _first_value(comparison_values)
    if base is None or comparison is None or base <= 0:
        return None
    return (comparison / base) - 1.0


def _clip(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _money(value: float | None) -> str:
    if value is None:
        return "N/A"
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:.2f}"


def _shares(value: float | None) -> str:
    if value is None:
        return "N/A"
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.2f}B"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:.0f}"


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"
