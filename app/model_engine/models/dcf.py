from __future__ import annotations

from app.model_engine.types import CompanyDataset
from app.model_engine.utils import (
    annual_series,
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
MODEL_VERSION = "2.1.0"

EQUITY_RISK_PREMIUM = 0.05
BASE_COMPANY_RISK_PREMIUM = 0.01
MAX_GROWTH_RATE = 0.15
MIN_GROWTH_RATE = -0.10
PROJECTION_YEARS = 5

REQUIRED_VALUATION_FIELDS = [
    "free_cash_flow",
    "cash_and_short_term_investments",
    "current_debt",
    "long_term_debt",
    "shares_outstanding",
    "weighted_average_diluted_shares",
]


def compute(dataset: CompanyDataset) -> dict[str, object]:
    applicability = valuation_applicability(dataset)
    if not applicability["is_supported"]:
        risk_free = get_latest_risk_free_rate()
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
    risk_free = get_latest_risk_free_rate()

    historical_fcfs: list[float] = []
    used_proxy_fcf = False
    for point in reversed(annuals):
        fcf = statement_value(point, "free_cash_flow")
        if fcf is not None:
            historical_fcfs.append(float(fcf))
            continue
        ocf = statement_value(point, "operating_cash_flow")
        capex = statement_value(point, "capex")
        if ocf is not None and capex is not None:
            historical_fcfs.append(float(ocf) - abs(float(capex)))
            used_proxy_fcf = True

    if not historical_fcfs:
        return {
            "status": "insufficient_data",
            "model_status": "insufficient_data",
            "explanation": status_explanation("insufficient_data"),
            "reason": "Free cash flow history unavailable",
            "applicability": applicability,
            "price_snapshot": _price_snapshot_payload(dataset),
            "input_quality": {
                "starting_cash_flow_proxied": used_proxy_fcf,
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

    growth_rates: list[float] = []
    for index in range(1, len(historical_fcfs)):
        previous = historical_fcfs[index - 1]
        current = historical_fcfs[index]
        if previous != 0:
            growth_rates.append((current - previous) / previous)

    assumed_growth = sum(growth_rates) / len(growth_rates) if growth_rates else 0.03
    assumed_growth = max(MIN_GROWTH_RATE, min(MAX_GROWTH_RATE, assumed_growth))

    discount_rate = risk_free.rate_used + EQUITY_RISK_PREMIUM
    if used_proxy_fcf:
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
    cash = latest_non_null(dataset, "cash_and_short_term_investments")
    if cash is None:
        cash_only = latest_non_null(dataset, "cash_and_cash_equivalents")
        short_term = latest_non_null(dataset, "short_term_investments")
        if cash_only is not None and short_term is not None:
            cash = cash_only + short_term
            used_proxy_fcf = True

    current_debt = latest_non_null(dataset, "current_debt")
    long_term_debt = latest_non_null(dataset, "long_term_debt")
    net_debt: float | None = None
    capital_structure_incomplete = any(item is None for item in (cash, current_debt, long_term_debt))
    if cash is not None and current_debt is not None and long_term_debt is not None:
        net_debt = (current_debt + long_term_debt) - cash

    equity_value = enterprise_value - net_debt if net_debt is not None else enterprise_value

    shares_outstanding = latest_non_null(dataset, "weighted_average_diluted_shares") or latest_non_null(dataset, "shares_outstanding")
    fair_value_per_share = safe_divide(equity_value, shares_outstanding)

    starting_cash_flow_proxied = used_proxy_fcf
    capital_structure_proxied = capital_structure_incomplete
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
                "company_risk_premium": json_number(BASE_COMPANY_RISK_PREMIUM if used_proxy_fcf else 0.0),
            },
            "terminal_assumptions": {
                "terminal_growth_rate": json_number(terminal_growth_rate),
                "projection_years": PROJECTION_YEARS,
            },
        },
        "projected_free_cash_flow": projected_cash_flows,
        "present_value_of_cash_flows": json_number(present_value_sum),
        "terminal_value_present_value": json_number(terminal_present_value),
        "enterprise_value": json_number(enterprise_value),
        "enterprise_value_proxy": json_number(enterprise_value),
        "net_debt": json_number(net_debt),
        "equity_value": json_number(equity_value),
        "fair_value_per_share": json_number(fair_value_per_share),
        "missing_required_fields_last_3y": missing_fields,
        "input_quality": {
            "starting_cash_flow_proxied": starting_cash_flow_proxied,
            "capital_structure_proxied": capital_structure_proxied,
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
