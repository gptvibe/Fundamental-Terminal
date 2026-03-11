from __future__ import annotations

from app.model_engine.types import CompanyDataset
from app.model_engine.utils import annual_series, json_number, statement_value

MODEL_NAME = "dcf"
MODEL_VERSION = "1.1.0"

DISCOUNT_RATE = 0.10
TERMINAL_GROWTH_RATE = 0.025
MAX_GROWTH_RATE = 0.15
MIN_GROWTH_RATE = -0.10
PROJECTION_YEARS = 5


def compute(dataset: CompanyDataset) -> dict[str, object]:
    annuals = annual_series(dataset, limit=5)
    annuals_with_fcf = [point for point in annuals if statement_value(point, "free_cash_flow") is not None]
    if not annuals_with_fcf:
        return {"status": "insufficient_data", "reason": "Free cash flow history unavailable"}

    annuals_oldest_first = list(reversed(annuals_with_fcf))
    starting_fcf = float(statement_value(annuals_with_fcf[0], "free_cash_flow"))
    historical_fcfs = [float(statement_value(point, "free_cash_flow")) for point in annuals_oldest_first]

    growth_rates: list[float] = []
    for index in range(1, len(historical_fcfs)):
        previous = historical_fcfs[index - 1]
        current = historical_fcfs[index]
        if previous != 0:
            growth_rates.append((current - previous) / previous)

    assumed_growth = sum(growth_rates) / len(growth_rates) if growth_rates else 0.03
    assumed_growth = max(MIN_GROWTH_RATE, min(MAX_GROWTH_RATE, assumed_growth))

    projected_cash_flows: list[dict[str, object]] = []
    present_value_sum = 0.0
    projected_fcf = starting_fcf
    for year in range(1, PROJECTION_YEARS + 1):
        taper_factor = year / PROJECTION_YEARS
        year_growth = assumed_growth + (TERMINAL_GROWTH_RATE - assumed_growth) * taper_factor
        projected_fcf *= 1 + year_growth
        discount_factor = (1 + DISCOUNT_RATE) ** year
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

    terminal_cash_flow = projected_fcf * (1 + TERMINAL_GROWTH_RATE)
    terminal_value = terminal_cash_flow / (DISCOUNT_RATE - TERMINAL_GROWTH_RATE)
    terminal_present_value = terminal_value / ((1 + DISCOUNT_RATE) ** PROJECTION_YEARS)

    return {
        "status": "ok",
        "base_period_end": annuals_with_fcf[0].period_end.isoformat(),
        "historical_free_cash_flow": [
            {"period_end": point.period_end.isoformat(), "free_cash_flow": json_number(statement_value(point, "free_cash_flow"))}
            for point in annuals_oldest_first
        ],
        "assumptions": {
            "discount_rate": DISCOUNT_RATE,
            "terminal_growth_rate": TERMINAL_GROWTH_RATE,
            "starting_growth_rate": json_number(assumed_growth),
            "projection_years": PROJECTION_YEARS,
        },
        "projected_free_cash_flow": projected_cash_flows,
        "present_value_of_cash_flows": json_number(present_value_sum),
        "terminal_value_present_value": json_number(terminal_present_value),
        "enterprise_value_proxy": json_number(present_value_sum + terminal_present_value),
    }
