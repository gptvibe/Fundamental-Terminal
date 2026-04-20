from __future__ import annotations

from typing import Any

from app.model_engine.types import CompanyDataset
from app.model_engine.utils import (
    annual_series,
    json_number,
    latest_non_null,
    missing_fields_last_n_years,
    safe_divide,
    status_explanation,
    status_from_data_quality,
    trust_summary,
    valuation_applicability,
)
from app.services.risk_free_rate import get_latest_risk_free_rate

MODEL_NAME = "reverse_dcf"
MODEL_VERSION = "1.2.0"

PROJECTION_YEARS = 5
MIN_SOLVE_GROWTH = -0.35
MAX_SOLVE_GROWTH = 0.55
SOLVE_ITERATIONS = 100
HEATMAP_SHIFTS = (-0.03, -0.015, 0.0, 0.015, 0.03)


def compute(dataset: CompanyDataset) -> dict[str, object]:
    applicability = valuation_applicability(dataset)
    if not applicability["is_supported"]:
        risk_free = get_latest_risk_free_rate(dataset.as_of_date)
        return {
            "status": "unsupported",
            "model_status": "unsupported",
            "explanation": status_explanation("unsupported"),
            "reason": "Reverse DCF is disabled for banks, insurers, REITs, and capital-markets-style financial firms.",
            "applicability": applicability,
            "price_snapshot": _price_snapshot_payload(dataset),
            "assumption_provenance": {
                "risk_free_rate": {
                    "source_name": risk_free.source_name,
                    "tenor": risk_free.tenor,
                    "observation_date": risk_free.observation_date.isoformat(),
                    "rate_used": json_number(risk_free.rate_used),
                },
                "price_snapshot": _price_snapshot_payload(dataset),
            },
        }

    annuals = annual_series(dataset, limit=5)
    if not annuals:
        return {
            "status": "insufficient_data",
            "model_status": "insufficient_data",
            "explanation": status_explanation("insufficient_data"),
            "reason": "Annual financial history unavailable",
            "applicability": applicability,
            "price_snapshot": _price_snapshot_payload(dataset),
        }

    latest = annuals[0]
    revenue = latest.data.get("revenue")
    operating_margin = safe_divide(latest.data.get("operating_income"), revenue)
    fcf_margin = safe_divide(latest.data.get("free_cash_flow"), revenue)
    used_fcf_margin_proxy = False
    fcf_margin_source = "free_cash_flow"
    if fcf_margin is None:
        operating_cash_flow = latest.data.get("operating_cash_flow")
        capex = latest.data.get("capex")
        if operating_cash_flow is not None and capex is not None:
            fcf_margin = safe_divide(float(operating_cash_flow) - abs(float(capex)), revenue)
            used_fcf_margin_proxy = fcf_margin is not None
            if used_fcf_margin_proxy:
                fcf_margin_source = "operating_cash_flow_less_capex"

    shares = latest_non_null(dataset, "shares_outstanding")
    share_count_proxied = False
    share_count_source = "shares_outstanding"
    if shares is None:
        shares = latest_non_null(dataset, "weighted_average_diluted_shares")
        share_count_proxied = shares is not None
        if share_count_proxied:
            share_count_source = "weighted_average_diluted_shares"

    market_snapshot = dataset.market_snapshot
    price = market_snapshot.latest_price if market_snapshot is not None else None

    risk_free = get_latest_risk_free_rate(dataset.as_of_date)
    discount_rate = risk_free.rate_used + 0.055
    terminal_growth = min(0.03, max(0.005, risk_free.rate_used * 0.6))

    can_directional = revenue not in (None, 0) and price not in (None, 0) and shares not in (None, 0)
    missing_fields = missing_fields_last_n_years(
        dataset,
        [
            "revenue",
            "operating_income",
            "free_cash_flow",
            "operating_cash_flow",
            "capex",
            "shares_outstanding",
            "weighted_average_diluted_shares",
            "cash_and_short_term_investments",
            "current_debt",
            "long_term_debt",
        ],
        years=3,
    )

    if not can_directional:
        reason = "Price/revenue/share inputs were insufficient for implied-growth inference"
        if price in (None, 0):
            reason = "Latest cached market price is unavailable; reverse DCF cannot infer implied growth without price."
        return {
            "status": "insufficient_data",
            "model_status": "insufficient_data",
            "explanation": status_explanation("insufficient_data"),
            "reason": reason,
            "applicability": applicability,
            "price_snapshot": _price_snapshot_payload(dataset),
        }

    equity_value = float(price) * float(shares)
    cash_balance, cash_balance_proxied = _cash_balance(dataset)
    current_debt = latest_non_null(dataset, "current_debt")
    long_term_debt = latest_non_null(dataset, "long_term_debt")
    total_debt: float | None = None
    net_debt: float | None = None
    capital_structure_proxied = cash_balance_proxied
    target_value_basis = "enterprise_value"
    target_enterprise_value = equity_value

    if current_debt is not None and long_term_debt is not None:
        total_debt = float(current_debt) + float(long_term_debt)

    if total_debt is not None and cash_balance is not None:
        net_debt = total_debt - float(cash_balance)
        target_enterprise_value = equity_value + net_debt
    else:
        capital_structure_proxied = True
        target_value_basis = "equity_value_fallback"

    implied_fcf_margin = fcf_margin
    if implied_fcf_margin is None:
        return {
            "status": "insufficient_data",
            "model_status": "insufficient_data",
            "explanation": status_explanation("insufficient_data"),
            "reason": "Unable to determine base free-cash-flow margin from cached statements.",
            "applicability": applicability,
            "price_snapshot": _price_snapshot_payload(dataset),
        }

    proxy_used = used_fcf_margin_proxy or capital_structure_proxied or share_count_proxied
    status = status_from_data_quality(
        missing_fields=missing_fields,
        proxy_used=proxy_used,
        can_compute_directional=target_enterprise_value > 0,
    )

    starting_fcf = float(revenue) * float(implied_fcf_margin)
    solved_growth, solve_metadata = _solve_implied_growth(
        target_enterprise_value=target_enterprise_value,
        starting_fcf=starting_fcf,
        discount_rate=discount_rate,
        terminal_growth=terminal_growth,
    )
    solve_metadata["target_value_basis"] = target_value_basis

    grid = []
    for growth_shift in HEATMAP_SHIFTS:
        for margin_shift in HEATMAP_SHIFTS:
            growth = solved_growth + growth_shift
            margin = float(implied_fcf_margin) + margin_shift
            implied_enterprise_value = _enterprise_value_from_growth(
                growth=growth,
                starting_fcf=float(revenue) * margin,
                discount_rate=discount_rate,
                terminal_growth=terminal_growth,
            )
            value_gap = safe_divide(implied_enterprise_value - target_enterprise_value, target_enterprise_value)
            grid.append(
                {
                    "growth": json_number(growth),
                    "margin": json_number(margin),
                    "value_gap": json_number(value_gap),
                }
            )

    return {
        "status": status,
        "model_status": status,
        "explanation": status_explanation(status),
        "confidence_summary": trust_summary(missing_fields=missing_fields, proxy_used=proxy_used),
        "applicability": applicability,
        "price_snapshot": _price_snapshot_payload(dataset),
        "implied_growth": json_number(solved_growth),
        "implied_margin": json_number(implied_fcf_margin),
        "current_operating_margin": json_number(operating_margin),
        "market_cap_proxy": json_number(equity_value),
        "enterprise_value_proxy": json_number(target_enterprise_value),
        "net_debt": json_number(net_debt),
        "solve_metadata": solve_metadata,
        "assumption_provenance": {
            "risk_free_rate": {
                "source_name": risk_free.source_name,
                "tenor": risk_free.tenor,
                "observation_date": risk_free.observation_date.isoformat(),
                "rate_used": json_number(risk_free.rate_used),
            },
            "price_snapshot": _price_snapshot_payload(dataset),
            "target_value": {
                "basis": target_value_basis,
                "equity_value": json_number(equity_value),
                "share_count": json_number(shares),
                "share_count_source": share_count_source,
                "cash": json_number(cash_balance),
                "total_debt": json_number(total_debt),
                "net_debt": json_number(net_debt),
                "enterprise_value": json_number(target_enterprise_value),
            },
            "discount_rate_inputs": {
                "discount_rate": json_number(discount_rate),
                "terminal_growth": json_number(terminal_growth),
            },
            "free_cash_flow_margin": {
                "source": fcf_margin_source,
                "margin": json_number(implied_fcf_margin),
                "operating_cash_flow": json_number(latest.data.get("operating_cash_flow")),
                "capex": json_number(latest.data.get("capex")),
            },
        },
        "heatmap": grid,
        "missing_required_fields_last_3y": missing_fields,
        "input_quality": {
            "starting_fcf_margin_proxied": used_fcf_margin_proxy,
            "capital_structure_proxied": capital_structure_proxied,
            "cash_balance_proxied": cash_balance_proxied,
            "share_count_proxied": share_count_proxied,
        },
    }


def _price_snapshot_payload(dataset: CompanyDataset) -> dict[str, object]:
    snapshot = dataset.market_snapshot
    if snapshot is None:
        return {
            "latest_price": None,
            "price_date": None,
            "price_source": None,
            "price_available": False,
        }
    return {
        "latest_price": json_number(snapshot.latest_price),
        "price_date": snapshot.price_date.isoformat() if snapshot.price_date is not None else None,
        "price_source": snapshot.price_source,
        "price_available": snapshot.latest_price is not None,
    }


def _cash_balance(dataset: CompanyDataset) -> tuple[float | None, bool]:
    cash = latest_non_null(dataset, "cash_and_short_term_investments")
    if cash is not None:
        return float(cash), False

    cash_only = latest_non_null(dataset, "cash_and_cash_equivalents")
    short_term = latest_non_null(dataset, "short_term_investments")
    if cash_only is not None and short_term is not None:
        return float(cash_only) + float(short_term), True
    return None, False


def _enterprise_value_from_growth(
    *,
    growth: float,
    starting_fcf: float,
    discount_rate: float,
    terminal_growth: float,
) -> float:
    projected_fcf = starting_fcf
    present_value = 0.0
    for year in range(1, PROJECTION_YEARS + 1):
        taper_factor = year / PROJECTION_YEARS
        year_growth = growth + (terminal_growth - growth) * taper_factor
        projected_fcf *= 1 + year_growth
        present_value += projected_fcf / ((1 + discount_rate) ** year)

    if discount_rate <= terminal_growth:
        return present_value

    terminal_cash_flow = projected_fcf * (1 + terminal_growth)
    terminal_value = terminal_cash_flow / (discount_rate - terminal_growth)
    terminal_present_value = terminal_value / ((1 + discount_rate) ** PROJECTION_YEARS)
    return present_value + terminal_present_value


def _solve_implied_growth(
    *,
    target_enterprise_value: float,
    starting_fcf: float,
    discount_rate: float,
    terminal_growth: float,
) -> tuple[float, dict[str, Any]]:
    def error(growth: float) -> float:
        return _enterprise_value_from_growth(
            growth=growth,
            starting_fcf=starting_fcf,
            discount_rate=discount_rate,
            terminal_growth=terminal_growth,
        ) - target_enterprise_value

    low = MIN_SOLVE_GROWTH
    high = MAX_SOLVE_GROWTH
    low_error = error(low)
    high_error = error(high)

    if low_error == 0:
        return low, {"method": "boundary", "iterations": 0, "residual": 0.0}
    if high_error == 0:
        return high, {"method": "boundary", "iterations": 0, "residual": 0.0}

    if low_error * high_error > 0:
        best_growth = low
        best_residual = abs(low_error)
        for index in range(1, 81):
            candidate = low + (high - low) * (index / 80)
            residual = abs(error(candidate))
            if residual < best_residual:
                best_growth = candidate
                best_residual = residual
        return best_growth, {
            "method": "grid_approximation",
            "iterations": 80,
            "residual": json_number(best_residual),
        }

    for iteration in range(SOLVE_ITERATIONS):
        mid = (low + high) / 2
        mid_error = error(mid)
        if abs(mid_error) <= max(target_enterprise_value * 1e-6, 1e-6):
            return mid, {
                "method": "bisection",
                "iterations": iteration + 1,
                "residual": json_number(abs(mid_error)),
            }
        if low_error * mid_error <= 0:
            high = mid
            high_error = mid_error
        else:
            low = mid
            low_error = mid_error

    solved = (low + high) / 2
    residual = abs(error(solved))
    return solved, {
        "method": "bisection",
        "iterations": SOLVE_ITERATIONS,
        "residual": json_number(residual),
    }
