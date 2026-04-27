from __future__ import annotations

from app.model_engine.types import CompanyDataset
from app.model_engine.utils import (
    annual_series,
    json_number,
    safe_divide,
    status_explanation,
    status_from_data_quality,
    trust_summary,
)
from app.services.risk_free_rate import get_latest_risk_free_rate

MODEL_NAME = "roic"
MODEL_VERSION = "1.2.2"

MIN_INVESTED_CAPITAL_DELTA = 1e-6


def _reinvestment_rate(data: dict[str, object]) -> float | None:
    """Return reinvestment as positive capex outflow magnitude over operating cash flow."""

    operating_cash_flow = data.get("operating_cash_flow")
    capex = data.get("capex")
    if capex is None:
        return None
    return safe_divide(abs(float(capex)), operating_cash_flow)


def compute(dataset: CompanyDataset) -> dict[str, object]:
    annuals = annual_series(dataset, limit=4)
    if len(annuals) < 2:
        return {
            "status": "insufficient_data",
            "model_status": "insufficient_data",
            "explanation": status_explanation("insufficient_data"),
            "reason": "Need at least two annual statements for ROIC trend",
        }

    risk_free = get_latest_risk_free_rate(dataset.as_of_date)
    capital_cost_proxy = risk_free.rate_used + 0.045

    trend: list[dict[str, object]] = []
    roic_values: list[float] = []
    reinvestment_values: list[float] = []
    period_metrics: list[dict[str, float]] = []
    incremental_roic: float | None = None
    proxy_used = False
    missing_fields: set[str] = set()

    for point in reversed(annuals):
        data = point.data or {}
        nopat = None
        if data.get("operating_income") is not None:
            effective_tax = _effective_tax_rate(data)
            nopat = float(data.get("operating_income")) * (1 - effective_tax)
        else:
            missing_fields.add("operating_income")

        invested_capital = None
        equity = data.get("stockholders_equity")
        current_debt = data.get("current_debt")
        long_term_debt = data.get("long_term_debt")
        total_debt = data.get("total_debt")
        if equity is not None:
            debt_component: float | None = None
            if total_debt is not None:
                debt_component = float(total_debt)
                if current_debt is None:
                    proxy_used = True
                    missing_fields.add("current_debt")
                if long_term_debt is None:
                    proxy_used = True
                    missing_fields.add("long_term_debt")
            elif current_debt is not None and long_term_debt is not None:
                debt_component = float(current_debt) + float(long_term_debt)
            else:
                if current_debt is None:
                    missing_fields.add("current_debt")
                if long_term_debt is None:
                    missing_fields.add("long_term_debt")

            if debt_component is not None:
                invested_capital = float(equity) + debt_component
                cash = data.get("cash_and_short_term_investments")
                if cash is not None:
                    invested_capital -= float(cash)
                else:
                    # Keep the gross-capital denominator as a proxy when excess cash is missing,
                    # but surface the missing input and downgrade confidence accordingly.
                    proxy_used = True
                    missing_fields.add("cash_and_short_term_investments")
        else:
            if equity is None:
                missing_fields.add("stockholders_equity")
            if current_debt is None:
                missing_fields.add("current_debt")
            if long_term_debt is None:
                missing_fields.add("long_term_debt")

        roic = safe_divide(nopat, invested_capital)
        if roic is not None:
            roic_values.append(float(roic))
        if nopat is not None and invested_capital is not None:
            period_metrics.append(
                {
                    "nopat": float(nopat),
                    "invested_capital": float(invested_capital),
                }
            )

        # Capex is typically stored as a signed cash-flow outflow, so normalize it to an
        # outflow magnitude before computing the public ``reinvestment_rate`` field.
        reinvestment = _reinvestment_rate(data)
        if reinvestment is not None:
            reinvestment_values.append(float(reinvestment))
        else:
            proxy_used = True

        trend.append(
            {
                "period_end": point.period_end.isoformat(),
                "roic": json_number(roic),
                "reinvestment_rate": json_number(reinvestment),
                "spread_vs_capital_cost": json_number(None if roic is None else float(roic) - capital_cost_proxy),
            }
        )

    if len(period_metrics) >= 2:
        earliest_period = period_metrics[0]
        latest_period = period_metrics[-1]
        delta_nopat = latest_period["nopat"] - earliest_period["nopat"]
        delta_invested_capital = latest_period["invested_capital"] - earliest_period["invested_capital"]
        capital_delta_floor = max(
            abs(latest_period["invested_capital"]),
            abs(earliest_period["invested_capital"]),
            1.0,
        ) * MIN_INVESTED_CAPITAL_DELTA
        if abs(delta_invested_capital) > capital_delta_floor:
            incremental_roic = delta_nopat / delta_invested_capital

    can_directional = bool(roic_values)
    status = status_from_data_quality(
        missing_fields=sorted(missing_fields),
        proxy_used=proxy_used,
        can_compute_directional=can_directional,
    )

    return {
        "status": status,
        "model_status": status,
        "explanation": status_explanation(status),
        "confidence_summary": trust_summary(missing_fields=sorted(missing_fields), proxy_used=proxy_used),
        "roic": json_number(roic_values[-1] if roic_values else None),
        "incremental_roic": json_number(incremental_roic),
        "reinvestment_rate": json_number(reinvestment_values[-1] if reinvestment_values else None),
        "spread_vs_capital_cost_proxy": json_number(None if not roic_values else roic_values[-1] - capital_cost_proxy),
        "capital_cost_proxy": json_number(capital_cost_proxy),
        "trend": trend,
        "assumption_provenance": {
            "risk_free_rate": {
                "source_name": risk_free.source_name,
                "tenor": risk_free.tenor,
                "observation_date": risk_free.observation_date.isoformat(),
                "rate_used": json_number(risk_free.rate_used),
            }
        },
        "missing_required_fields_last_3y": sorted(missing_fields),
    }


def _effective_tax_rate(data: dict[str, object]) -> float:
    pretax_income = data.get("pretax_income")
    if pretax_income is not None and float(pretax_income) > 0:
        tax_rate_proxy = safe_divide(data.get("income_tax_expense"), pretax_income)
        if tax_rate_proxy is not None:
            return max(0.0, min(0.40, float(tax_rate_proxy)))
    return 0.21
