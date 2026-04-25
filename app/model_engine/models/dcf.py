from __future__ import annotations

from app.model_engine.calculation_versions import DCF_CALCULATION_VERSION
from app.model_engine.types import CompanyDataset
from app.model_engine.utils import (
    annual_series,
    growth_rate,
    json_number,
    latest_non_null,
    missing_fields_last_n_years,
    safe_divide,
    statement_value,
    status_explanation,
    status_from_data_quality,
    trust_summary,
    valuation_applicability,
)
from app.services.risk_free_rate import get_latest_risk_free_rate

MODEL_NAME = "dcf"
MODEL_VERSION = "2.4.0"
CALCULATION_VERSION = DCF_CALCULATION_VERSION

EQUITY_RISK_PREMIUM = 0.05
BASE_COMPANY_RISK_PREMIUM = 0.01
MAX_GROWTH_RATE = 0.15
MIN_GROWTH_RATE = -0.10
PROJECTION_YEARS = 5
CASH_FLOW_BASIS = "free_cash_flow_to_firm_proxy"
DISCOUNT_RATE_BASIS = "proxy_wacc"
EQUITY_VALUE_BASIS = "equity_value"
ENTERPRISE_VALUE_PROXY_BASIS = "enterprise_value_proxy"

# Sector-based additional risk premiums layered on top of ERP.
# Positive values increase the discount rate; negative values reduce it.
_SECTOR_RISK_PREMIUM: dict[str, float] = {
    "utilities": -0.010,
    "consumer staples": -0.005,
    "healthcare": 0.000,
    "industrials": 0.005,
    "real estate": -0.005,
    "energy": 0.010,
    "materials": 0.010,
    "consumer discretionary": 0.010,
    "communication services": 0.010,
    "information technology": 0.015,
    "technology": 0.015,
}


def _sector_risk_premium(dataset: CompanyDataset) -> float:
    """Return sector-specific risk adjustment (delta on top of base ERP)."""
    for field in (dataset.market_sector, dataset.sector):
        if field:
            key = field.lower().strip()
            premium = _SECTOR_RISK_PREMIUM.get(key)
            if premium is not None:
                return premium
    return 0.0  # default: no adjustment

REQUIRED_VALUATION_FIELDS = [
    "free_cash_flow",
    "shares_outstanding",
    "weighted_average_diluted_shares",
]


def _historical_fcf_growth_rates(historical_fcfs: list[float]) -> list[float]:
    """Return growth rates that stay directionally correct across negative FCF periods.

    ``growth_rate()`` normalizes by ``abs(previous)`` so the direction remains intuitive
    when free cash flow is negative or flips sign. A move from -100 to -50 is positive
    growth, and a move from -50 to 50 remains a positive sign-flip improvement. Periods
    with a zero prior base are skipped because percentage growth is undefined there.
    """

    growth_rates: list[float] = []
    for index in range(1, len(historical_fcfs)):
        normalized_growth = growth_rate(historical_fcfs[index], historical_fcfs[index - 1])
        if normalized_growth is not None:
            growth_rates.append(normalized_growth)
    return growth_rates


def compute(dataset: CompanyDataset) -> dict[str, object]:
    applicability = valuation_applicability(dataset)
    if not applicability["is_supported"]:
        risk_free = get_latest_risk_free_rate(dataset.as_of_date)
        return {
            "status": "unsupported",
            "model_status": "unsupported",
            "explanation": status_explanation("unsupported"),
            "reason": "DCF is disabled for banks, insurers, REITs, and capital-markets-style financial firms.",
            "applicability": applicability,
            "price_snapshot": _price_snapshot_payload(dataset),
            "input_quality": {
                "starting_cash_flow_proxied": False,
                "capital_structure_proxied": False,
            },
            "assumption_provenance": {
                "risk_free_rate": {
                    "source_name": risk_free.source_name,
                    "tenor": risk_free.tenor,
                    "observation_date": risk_free.observation_date.isoformat(),
                    "rate_used": json_number(risk_free.rate_used),
                }
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

    missing_fields = missing_fields_last_n_years(dataset, REQUIRED_VALUATION_FIELDS, years=3)
    risk_free = get_latest_risk_free_rate(dataset.as_of_date)

    historical_fcfs: list[float] = []
    starting_cash_flow_proxied = False
    for point in reversed(annuals):
        fcf = statement_value(point, "free_cash_flow")
        if fcf is not None:
            historical_fcfs.append(float(fcf))
            continue
        ocf = statement_value(point, "operating_cash_flow")
        capex = statement_value(point, "capex")
        if ocf is not None and capex is not None:
            historical_fcfs.append(float(ocf) - abs(float(capex)))
            starting_cash_flow_proxied = True

    if not historical_fcfs:
        return {
            "status": "insufficient_data",
            "model_status": "insufficient_data",
            "explanation": status_explanation("insufficient_data"),
            "reason": "Free cash flow history unavailable",
            "applicability": applicability,
            "price_snapshot": _price_snapshot_payload(dataset),
            "input_quality": {
                "starting_cash_flow_proxied": starting_cash_flow_proxied,
                "capital_structure_proxied": False,
            },
            "assumption_provenance": {
                "risk_free_rate": {
                    "source_name": risk_free.source_name,
                    "tenor": risk_free.tenor,
                    "observation_date": risk_free.observation_date.isoformat(),
                    "rate_used": json_number(risk_free.rate_used),
                }
            },
        }

    starting_fcf = historical_fcfs[-1]

    growth_rates = _historical_fcf_growth_rates(historical_fcfs)
    assumed_growth = sum(growth_rates) / len(growth_rates) if growth_rates else 0.03
    assumed_growth = max(MIN_GROWTH_RATE, min(MAX_GROWTH_RATE, assumed_growth))

    sector_premium = _sector_risk_premium(dataset)
    discount_rate = risk_free.rate_used + EQUITY_RISK_PREMIUM + sector_premium
    if starting_cash_flow_proxied:
        discount_rate += BASE_COMPANY_RISK_PREMIUM
    terminal_growth_rate = min(0.03, max(0.005, risk_free.rate_used * 0.6))

    projected_cash_flows: list[dict[str, object]] = []
    present_value_sum = 0.0
    projected_fcf = starting_fcf
    for year in range(1, PROJECTION_YEARS + 1):
        taper_factor = year / PROJECTION_YEARS
        year_growth = assumed_growth + (terminal_growth_rate - assumed_growth) * taper_factor
        projected_fcf *= 1 + year_growth
        discount_factor = (1 + discount_rate) ** year
        present_value = projected_fcf / discount_factor
        present_value_sum += present_value
        projected_cash_flows.append(
            {
                "year": year,
                "growth_rate": json_number(year_growth),
                "free_cash_flow": json_number(projected_fcf),
                "present_value": json_number(present_value),
            }
        )

    if discount_rate <= terminal_growth_rate:
        return {
            "status": "insufficient_data",
            "model_status": "insufficient_data",
            "explanation": status_explanation("insufficient_data"),
            "reason": "Discount rate must exceed terminal growth rate",
            "applicability": applicability,
            "price_snapshot": _price_snapshot_payload(dataset),
        }

    terminal_cash_flow = projected_fcf * (1 + terminal_growth_rate)
    terminal_value = terminal_cash_flow / (discount_rate - terminal_growth_rate)
    terminal_present_value = terminal_value / ((1 + discount_rate) ** PROJECTION_YEARS)

    enterprise_value = present_value_sum + terminal_present_value
    cash, cash_balance_proxied = _cash_balance(dataset)

    current_debt = latest_non_null(dataset, "current_debt")
    long_term_debt = latest_non_null(dataset, "long_term_debt")
    total_debt: float | None = None
    net_debt: float | None = None
    if current_debt is not None and long_term_debt is not None:
        total_debt = current_debt + long_term_debt

    shares_outstanding = latest_non_null(dataset, "shares_outstanding") or latest_non_null(dataset, "weighted_average_diluted_shares")
    valuation_bridge = _bridge_enterprise_to_equity(
        enterprise_value=enterprise_value,
        total_debt=total_debt,
        cash_balance=cash,
        shares_outstanding=shares_outstanding,
        cash_balance_proxied=cash_balance_proxied,
    )
    capital_structure_complete = bool(valuation_bridge["net_debt_bridge_applied"])
    capital_structure_proxied = bool(valuation_bridge["capital_structure_proxied"])
    value_basis = str(valuation_bridge["value_basis"])
    net_debt = valuation_bridge["net_debt"]
    equity_value = valuation_bridge["equity_value"]
    fair_value_per_share = valuation_bridge["fair_value_per_share"]

    proxy_used = starting_cash_flow_proxied or capital_structure_proxied
    status = status_from_data_quality(
        missing_fields=missing_fields,
        proxy_used=proxy_used,
        can_compute_directional=enterprise_value > 0,
    )

    confidence = trust_summary(missing_fields=missing_fields, proxy_used=proxy_used)
    status_flags: list[str] = []
    if len(missing_fields) >= 2:
        status_flags.append("partial_inputs")
    if proxy_used:
        status_flags.append("proxy_output")

    return {
        "status": status,
        "model_status": status,
        "explanation": status_explanation(status),
        "status_flags": status_flags,
        "confidence_summary": confidence,
        "applicability": applicability,
        "price_snapshot": _price_snapshot_payload(dataset),
        "base_period_end": annuals[0].period_end.isoformat(),
        "historical_free_cash_flow": [
            {"period_end": point.period_end.isoformat(), "free_cash_flow": json_number(statement_value(point, "free_cash_flow"))}
            for point in reversed(annuals)
        ],
        "assumptions": {
            "discount_rate": json_number(discount_rate),
            "terminal_growth_rate": json_number(terminal_growth_rate),
            "starting_growth_rate": json_number(assumed_growth),
            "projection_years": PROJECTION_YEARS,
            "equity_risk_premium": json_number(EQUITY_RISK_PREMIUM),
            "sector_risk_premium": json_number(sector_premium),
        },
        "assumption_provenance": {
            "risk_free_rate": {
                "source_name": risk_free.source_name,
                "tenor": risk_free.tenor,
                "observation_date": risk_free.observation_date.isoformat(),
                "rate_used": json_number(risk_free.rate_used),
            },
            "price_snapshot": _price_snapshot_payload(dataset),
            "discount_rate_inputs": {
                "risk_free_rate": json_number(risk_free.rate_used),
                "equity_risk_premium": json_number(EQUITY_RISK_PREMIUM),
                "sector_risk_premium": json_number(sector_premium),
                "company_risk_premium": json_number(BASE_COMPANY_RISK_PREMIUM if starting_cash_flow_proxied else 0.0),
                "discount_rate_basis": DISCOUNT_RATE_BASIS,
            },
            "terminal_assumptions": {
                "terminal_growth_rate": json_number(terminal_growth_rate),
                "projection_years": PROJECTION_YEARS,
            },
            "valuation_framework": {
                "cash_flow_basis": CASH_FLOW_BASIS,
                "discount_rate_basis": DISCOUNT_RATE_BASIS,
                "output_value_basis": value_basis,
                "net_debt_bridge_applied": capital_structure_complete,
            },
        },
        "projected_free_cash_flow": projected_cash_flows,
        "present_value_of_cash_flows": json_number(present_value_sum),
        "terminal_value_present_value": json_number(terminal_present_value),
        "enterprise_value": json_number(enterprise_value),
        "enterprise_value_proxy": json_number(enterprise_value) if value_basis == ENTERPRISE_VALUE_PROXY_BASIS else None,
        "total_debt": json_number(total_debt),
        "net_debt": json_number(net_debt),
        "equity_value": json_number(equity_value),
        "fair_value_per_share": json_number(fair_value_per_share),
        "value_basis": value_basis,
        "capital_structure_proxied": capital_structure_proxied,
        "discount_rate_basis": DISCOUNT_RATE_BASIS,
        "missing_required_fields_last_3y": missing_fields,
        "input_quality": {
            "starting_cash_flow_proxied": starting_cash_flow_proxied,
            "capital_structure_proxied": capital_structure_proxied,
            "cash_balance_proxied": cash_balance_proxied,
        },
    }


def _bridge_enterprise_to_equity(
    *,
    enterprise_value: float,
    total_debt: float | None,
    cash_balance: float | None,
    shares_outstanding: float | None,
    cash_balance_proxied: bool,
) -> dict[str, object]:
    capital_structure_complete = total_debt is not None and cash_balance is not None
    net_debt = (total_debt - cash_balance) if capital_structure_complete else None
    value_basis = EQUITY_VALUE_BASIS if capital_structure_complete else ENTERPRISE_VALUE_PROXY_BASIS
    equity_value = (enterprise_value - net_debt) if net_debt is not None else None
    per_share_value = equity_value if equity_value is not None else enterprise_value
    capital_structure_proxied = cash_balance_proxied or not capital_structure_complete
    return {
        "value_basis": value_basis,
        "capital_structure_proxied": capital_structure_proxied,
        "net_debt_bridge_applied": capital_structure_complete,
        "net_debt": net_debt,
        "equity_value": equity_value,
        "fair_value_per_share": safe_divide(per_share_value, shares_outstanding),
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
