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
WORKING_CAPITAL_DAYS_FLOOR = -20.0
WORKING_CAPITAL_DAYS_CAP = 120.0
SALES_TO_CAPITAL_FLOOR = 0.35
SALES_TO_CAPITAL_CAP = 2.50
CAPEX_INTENSITY_FLOOR = 0.02
CAPEX_INTENSITY_CAP = 0.25
DEPRECIATION_RATIO_FLOOR = 0.01
DEPRECIATION_RATIO_CAP = 0.20
SBC_EXPENSE_RATIO_CAP = 0.08
SBC_DILUTION_FLOOR = 0.00
SBC_DILUTION_CAP = 0.04
BUYBACK_RETIREMENT_FLOOR = 0.00
BUYBACK_RETIREMENT_CAP = 0.05
ACQUISITION_DILUTION_CAP = 0.04
CONVERT_DILUTION_CAP = 0.04
DILUTION_CAP = 0.08


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
class _ReinvestmentSchedule:
    working_capital_days: float
    sales_to_capital: float
    capex_intensity: float
    depreciation_ratio: float
    latest_depreciation: float


@dataclass(slots=True)
class _DilutionSchedule:
    starting_shares: float
    sbc_expense_ratio: float
    sbc_dilution_rate: float
    buyback_retirement_rate: float
    acquisition_dilution_rate: float
    convert_dilution_rate: float


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
    reinvestment_schedule = _derive_reinvestment_schedule(history)
    net_income_conversion = _derive_net_income_conversion(history)
    latest_year = int(history[-1]["year"])
    scenario_tweaks = _scenario_tweaks()

    scenarios: dict[str, DriverForecastScenario] = {}
    for scenario_key in SCENARIO_SEQUENCE:
        scenarios[scenario_key] = _project_scenario(
            history,
            revenue_drivers,
            cost_schedule,
            reinvestment_schedule,
            dilution_schedule,
            net_income_conversion=net_income_conversion,
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
        dilution_schedule,
    )
    calculation_rows = _build_calculation_rows(
        revenue_drivers,
        cost_schedule,
        reinvestment_schedule,
        dilution_schedule,
        net_income_conversion,
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
                "shares": _statement_value(statement, "weighted_average_shares_diluted"),
                "total_assets": _statement_value(statement, "total_assets"),
                "current_assets": _statement_value(statement, "current_assets"),
                "current_liabilities": _statement_value(statement, "current_liabilities"),
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


def _derive_reinvestment_schedule(history: list[dict[str, Any]]) -> _ReinvestmentSchedule:
    latest = history[-1]
    capex_intensity = _clip(_median_abs_ratio(history, "capex", "revenue") or 0.05, CAPEX_INTENSITY_FLOOR, CAPEX_INTENSITY_CAP)
    depreciation_ratio = _clip(_median_abs_ratio(history, "depreciation", "revenue") or (capex_intensity * 0.75), DEPRECIATION_RATIO_FLOOR, DEPRECIATION_RATIO_CAP)
    latest_depreciation = abs(latest["depreciation"] or 0.0) or (latest["revenue"] or 0.0) * depreciation_ratio
    return _ReinvestmentSchedule(
        working_capital_days=_working_capital_days(history),
        sales_to_capital=_sales_to_capital(history) or 1.25,
        capex_intensity=capex_intensity,
        depreciation_ratio=depreciation_ratio,
        latest_depreciation=latest_depreciation,
    )


def _derive_dilution_schedule(history: list[dict[str, Any]]) -> _DilutionSchedule | None:
    share_history = [row["shares"] for row in history if row["shares"] is not None and row["shares"] > 0]
    if not share_history:
        return None

    latest = history[-1]
    starting_shares = float(share_history[-1])
    share_growth = _weighted_recent_growth(_historical_growth_rates(share_history))
    sbc_expense_ratio = _clip(_median_abs_ratio(history, "stock_based_compensation", "revenue") or 0.0, 0.0, SBC_EXPENSE_RATIO_CAP)

    explicit_sbc_rate = _clip(max((sbc_expense_ratio * 0.18), max(share_growth or 0.0, 0.0) * 0.65), SBC_DILUTION_FLOOR, SBC_DILUTION_CAP)
    buyback_rate = _clip(max((_median_abs_ratio(history, "share_buybacks", "revenue") or 0.0) * 0.12, max(-(share_growth or 0.0), 0.0) * 0.65), BUYBACK_RETIREMENT_FLOOR, BUYBACK_RETIREMENT_CAP)
    acquisition_rate = _clip((_median_abs_ratio(history, "acquisitions", "revenue") or 0.0) * 0.05, 0.0, ACQUISITION_DILUTION_CAP)

    latest_data = getattr(latest["statement"], "data", None)
    convert_rate = 0.0
    if isinstance(latest_data, dict):
        convert_rate = _clip(
            _as_float(
                latest_data.get("convertible_dilution_rate")
                or latest_data.get("convert_dilution_rate")
                or latest_data.get("convertible_share_dilution")
            )
            or 0.0,
            0.0,
            CONVERT_DILUTION_CAP,
        )
        if convert_rate == 0.0:
            convertible_shares = _as_float(latest_data.get("convertible_shares") or latest_data.get("dilutive_convertible_shares"))
            convert_rate = _clip(_safe_divide(convertible_shares, starting_shares) or 0.0, 0.0, CONVERT_DILUTION_CAP)

    explicit_net = explicit_sbc_rate + acquisition_rate + convert_rate - buyback_rate
    if share_growth is not None:
        gap = share_growth - explicit_net
        if gap > 0:
            explicit_sbc_rate = _clip(explicit_sbc_rate + (gap * 0.7), SBC_DILUTION_FLOOR, SBC_DILUTION_CAP)
        elif gap < 0:
            buyback_rate = _clip(buyback_rate + (abs(gap) * 0.7), BUYBACK_RETIREMENT_FLOOR, BUYBACK_RETIREMENT_CAP)

    return _DilutionSchedule(
        starting_shares=starting_shares,
        sbc_expense_ratio=sbc_expense_ratio,
        sbc_dilution_rate=explicit_sbc_rate,
        buyback_retirement_rate=buyback_rate,
        acquisition_dilution_rate=acquisition_rate,
        convert_dilution_rate=convert_rate,
    )


def _derive_net_income_conversion(history: list[dict[str, Any]]) -> float:
    ratios: list[float] = []
    for row in history:
        operating_income = row["operating_income"]
        net_income = row["net_income"]
        if operating_income in (None, 0) or net_income is None:
            continue
        ratio = net_income / operating_income
        if isfinite(ratio):
            ratios.append(_clip(ratio, -0.8, 1.1))
    return median(ratios) if ratios else 0.78


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
    dilution_schedule: _DilutionSchedule,
    *,
    net_income_conversion: float,
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
    previous_working_capital = previous_revenue * (reinvestment_schedule.working_capital_days / 365.0)
    previous_depreciation = reinvestment_schedule.latest_depreciation
    semi_cost = previous_revenue * cost_schedule.semi_variable_cost_ratio
    fixed_cost = cost_schedule.fixed_cost_base
    shares = dilution_schedule.starting_shares

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
        net_income = operating_income * net_income_conversion

        working_capital_days = _clip(reinvestment_schedule.working_capital_days + tweaks.working_capital_days_shift, WORKING_CAPITAL_DAYS_FLOOR, WORKING_CAPITAL_DAYS_CAP)
        target_working_capital = revenue * (working_capital_days / 365.0)
        delta_working_capital = target_working_capital - previous_working_capital

        sales_to_capital = _clip(reinvestment_schedule.sales_to_capital + tweaks.sales_to_capital_shift, SALES_TO_CAPITAL_FLOOR, SALES_TO_CAPITAL_CAP)
        growth_reinvestment = max(revenue - previous_revenue, 0.0) / sales_to_capital

        maintenance_capex = max(revenue * reinvestment_schedule.capex_intensity, depreciation)
        capex = max(maintenance_capex, depreciation + max(growth_reinvestment, 0.0))
        operating_cash_flow = net_income + depreciation + (revenue * dilution_schedule.sbc_expense_ratio) - delta_working_capital
        free_cash_flow = operating_cash_flow - capex

        net_dilution = _clip(
            dilution_schedule.sbc_dilution_rate
            + tweaks.sbc_shift
            + dilution_schedule.acquisition_dilution_rate
            + dilution_schedule.convert_dilution_rate
            - max(0.0, dilution_schedule.buyback_retirement_rate + tweaks.buyback_shift)
            + tweaks.dilution_shift,
            SHARE_CHANGE_FLOOR,
            DILUTION_CAP,
        )
        shares = max(1e-6, shares * (1.0 + net_dilution))
        eps = _safe_divide(net_income, shares)

        operating_income_values.append(operating_income)
        net_income_values.append(net_income)
        ebitda_values.append(ebitda)
        operating_cash_flow_values.append(operating_cash_flow)
        free_cash_flow_values.append(free_cash_flow)
        capex_values.append(capex)
        diluted_shares_values.append(shares)
        eps_values.append(eps if eps is not None else 0.0)

        previous_revenue = revenue
        previous_working_capital = target_working_capital
        previous_depreciation = depreciation

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
    )


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
            "key": "reinvestment",
            "label": "Reinvestment",
            "value": f"{reinvestment_schedule.working_capital_days:.0f} WC days / {reinvestment_schedule.sales_to_capital:.2f}x sales-to-capital",
            "detail": "Growth is linked to working capital and incremental capital intensity instead of using margin mean reversion alone.",
        },
        {
            "key": "capex_dep",
            "label": "Capex / Depreciation",
            "value": f"{_pct(reinvestment_schedule.capex_intensity)} capex / {_pct(reinvestment_schedule.depreciation_ratio)} D&A",
            "detail": "Maintenance and growth capex are separated through the reinvestment schedule.",
        },
        {
            "key": "dilution",
            "label": "Dilution Bridge",
            "value": f"{_pct(dilution_schedule.sbc_dilution_rate)} SBC / {_pct(dilution_schedule.buyback_retirement_rate)} buybacks",
            "detail": "Share count explicitly models SBC issuance, repurchases, acquisition dilution, and convert dilution when available.",
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
    dilution_schedule: _DilutionSchedule,
    net_income_conversion: float,
    base_scenario: DriverForecastScenario,
) -> list[dict[str, str]]:
    base_margin = _safe_divide(_first_value(base_scenario.operating_income.values), _first_value(base_scenario.revenue.values))
    base_eps = _first_value(base_scenario.eps.values)
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
            "key": "formula_reinvestment",
            "label": "Reinvestment Formula",
            "value": "Delta revenue / sales-to-capital + delta working capital",
            "detail": f"Working capital runs at {reinvestment_schedule.working_capital_days:.0f} days and capex intensity at {_pct(reinvestment_schedule.capex_intensity)}.",
        },
        {
            "key": "formula_fcf",
            "label": "Free Cash Flow Formula",
            "value": "Net income + D&A + SBC - delta working capital - capex",
            "detail": f"SBC expense ratio {_pct(dilution_schedule.sbc_expense_ratio)}; net income conversion {net_income_conversion:.2f}x EBIT.",
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
        f"Bull / Bear next-year EPS {_money(bull_eps)} / {_money(bear_eps)} with explicit dilution.",
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


def _working_capital_days(history: list[dict[str, Any]]) -> float:
    values: list[float] = []
    for row in history:
        revenue = row["revenue"]
        current_assets = row["current_assets"]
        current_liabilities = row["current_liabilities"]
        if revenue in (None, 0) or current_assets is None or current_liabilities is None:
            continue
        values.append(_clip(((current_assets - current_liabilities) / revenue) * 365.0, WORKING_CAPITAL_DAYS_FLOOR, WORKING_CAPITAL_DAYS_CAP))
    return median(values) if values else 12.0


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
    if key == "weighted_average_shares_diluted":
        value = data.get("weighted_average_shares_diluted", data.get("weighted_average_diluted_shares"))
    if key == "free_cash_flow":
        direct_value = _as_float(value)
        if direct_value is not None:
            return direct_value
        operating_cash_flow = _as_float(data.get("operating_cash_flow"))
        capex = _as_float(data.get("capex"))
        if operating_cash_flow is not None and capex is not None:
            return operating_cash_flow - capex
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


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"
