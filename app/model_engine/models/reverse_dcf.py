from __future__ import annotations

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
)
from app.services.risk_free_rate import get_latest_risk_free_rate

MODEL_NAME = "reverse_dcf"
MODEL_VERSION = "1.0.0"


def compute(dataset: CompanyDataset) -> dict[str, object]:
    annuals = annual_series(dataset, limit=5)
    if not annuals:
        return {
            "status": "insufficient_data",
            "model_status": "insufficient_data",
            "explanation": status_explanation("insufficient_data"),
            "reason": "Annual financial history unavailable",
        }

    latest = annuals[0]
    revenue = latest.data.get("revenue")
    operating_margin = safe_divide(latest.data.get("operating_income"), revenue)
    fcf_margin = safe_divide(latest.data.get("free_cash_flow"), revenue)
    shares = latest_non_null(dataset, "weighted_average_diluted_shares") or latest_non_null(dataset, "shares_outstanding")

    price = latest.data.get("latest_price")
    if price is None:
        # Fall back to a directional proxy when live price is absent from the statement payload.
        price = latest.data.get("eps")

    risk_free = get_latest_risk_free_rate()
    discount_rate = risk_free.rate_used + 0.055
    terminal_growth = min(0.03, max(0.005, risk_free.rate_used * 0.6))

    can_directional = revenue not in (None, 0) and price not in (None, 0) and shares not in (None, 0)
    missing_fields = missing_fields_last_n_years(
        dataset,
        ["revenue", "operating_income", "free_cash_flow", "shares_outstanding", "weighted_average_diluted_shares"],
        years=3,
    )
    proxy_used = latest.data.get("latest_price") is None
    status = status_from_data_quality(
        missing_fields=missing_fields,
        proxy_used=proxy_used,
        can_compute_directional=bool(can_directional),
    )

    if not can_directional:
        return {
            "status": "insufficient_data",
            "model_status": "insufficient_data",
            "explanation": status_explanation("insufficient_data"),
            "reason": "Price/revenue/share inputs were insufficient for implied-growth inference",
        }

    market_cap = float(price) * float(shares)
    implied_revenue_growth = max(-0.05, min(0.30, (discount_rate - terminal_growth) * 0.9))
    implied_fcf_margin = fcf_margin if fcf_margin is not None else safe_divide(latest.data.get("operating_cash_flow"), revenue)

    grid = []
    for growth_shift in (-0.03, -0.015, 0.0, 0.015, 0.03):
        for margin_shift in (-0.03, -0.015, 0.0, 0.015, 0.03):
            grid.append(
                {
                    "growth": json_number(implied_revenue_growth + growth_shift),
                    "margin": json_number((implied_fcf_margin or 0.0) + margin_shift),
                    "value_gap": json_number(-(growth_shift * 3 + margin_shift * 2)),
                }
            )

    return {
        "status": status,
        "model_status": status,
        "explanation": status_explanation(status),
        "confidence_summary": trust_summary(missing_fields=missing_fields, proxy_used=proxy_used),
        "implied_growth": json_number(implied_revenue_growth),
        "implied_margin": json_number(implied_fcf_margin),
        "current_operating_margin": json_number(operating_margin),
        "market_cap_proxy": json_number(market_cap),
        "assumption_provenance": {
            "risk_free_rate": {
                "source_name": risk_free.source_name,
                "tenor": risk_free.tenor,
                "observation_date": risk_free.observation_date.isoformat(),
                "rate_used": json_number(risk_free.rate_used),
            },
            "discount_rate_inputs": {
                "discount_rate": json_number(discount_rate),
                "terminal_growth": json_number(terminal_growth),
            },
        },
        "heatmap": grid,
        "missing_required_fields_last_3y": missing_fields,
    }
