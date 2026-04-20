from __future__ import annotations

from contextvars import ContextVar

from app.config import settings
from app.model_engine.types import CompanyDataset
from app.model_engine.utils import (
    ANNUAL_FORMS,
    average,
    book_equity,
    json_number,
    latest_annual_statement,
    latest_statement,
    previous_comparable_statement,
    safe_divide,
    status_explanation,
    statement_value,
)

MODEL_NAME = "dupont"
MODEL_VERSION = "1.1.1"

ALLOWED_MODES = {"auto", "annual", "ttm"}
_DUPONT_MODE_OVERRIDE: ContextVar[str | None] = ContextVar("dupont_mode_override", default=None)


def compute(dataset: CompanyDataset) -> dict[str, object]:
    mode = _get_mode()

    if mode == "annual":
        basis, metrics = _compute_annual(dataset)
    elif mode == "ttm":
        basis, metrics = _compute_ttm(dataset)
    else:
        basis, metrics = _compute_annual(dataset)
        if metrics is None:
            basis, metrics = _compute_ttm(dataset)

    if metrics is None:
        return {"status": "insufficient_data", "model_status": "insufficient_data", "explanation": status_explanation("insufficient_data"), "reason": "Need annual filing or four comparable periods for DuPont"}

    net_profit_margin, asset_turnover, equity_multiplier, average_assets, average_equity, current = metrics
    status = "supported" if all(value is not None for value in (net_profit_margin, asset_turnover, equity_multiplier)) else "partial"

    return {
        "status": status,
        "model_status": status,
        "explanation": status_explanation(status),
        "period_end": current.period_end.isoformat(),
        "filing_type": current.filing_type,
        "basis": basis,
        "net_profit_margin": json_number(net_profit_margin),
        "asset_turnover": json_number(asset_turnover),
        "equity_multiplier": json_number(equity_multiplier),
        "return_on_equity": json_number(
            None if None in (net_profit_margin, asset_turnover, equity_multiplier) else net_profit_margin * asset_turnover * equity_multiplier
        ),
        "average_assets": json_number(average_assets),
        "average_equity": json_number(average_equity),
    }


def _sum_field(points: list, key: str) -> float | None:
    values = [statement_value(point, key) for point in points]
    numeric = [_number(value) for value in values if value is not None]
    if not numeric:
        return None
    return float(sum(numeric))


def _number(value) -> float | None:
    if value is None:
        return None
    return float(value)


def _period_duration_days(point) -> int:
    return (point.period_end - point.period_start).days


def _is_standalone_quarter(point) -> bool:
    return 70 <= _period_duration_days(point) <= 110


def _standalone_quarter_window(dataset: CompanyDataset, current):
    comparable = [point for point in dataset.financials if point.filing_type == current.filing_type]
    window = comparable[:4]
    if len(window) < 4:
        return None
    if not all(_is_standalone_quarter(point) for point in window):
        return None

    for earlier, later in zip(window[1:], window):
        gap_days = (later.period_end - earlier.period_end).days
        if not 70 <= gap_days <= 110:
            return None
    return window


def _latest_annual_before(dataset: CompanyDataset, period_end):
    for point in dataset.financials:
        if point.filing_type in ANNUAL_FORMS and point.period_end < period_end:
            return point
    return None


def _same_fiscal_coverage(left, right) -> bool:
    return (
        left.period_end.month == right.period_end.month
        and abs(left.period_end.day - right.period_end.day) <= 7
        and abs(_period_duration_days(left) - _period_duration_days(right)) <= 14
    )


def _prior_year_same_period(dataset: CompanyDataset, current):
    for point in dataset.financials:
        if point.statement_id == current.statement_id:
            continue
        if point.filing_type != current.filing_type:
            continue
        if point.period_end >= current.period_end:
            continue
        if _same_fiscal_coverage(point, current):
            return point
    return None


def _ttm_bridge_value(latest_annual, current_ytd, prior_ytd, key: str) -> float | None:
    annual_value = _number(statement_value(latest_annual, key))
    current_value = _number(statement_value(current_ytd, key))
    prior_value = _number(statement_value(prior_ytd, key))
    if None in (annual_value, current_value, prior_value):
        return None
    return annual_value + current_value - prior_value


def _get_mode() -> str:
    override = _DUPONT_MODE_OVERRIDE.get()
    if override in ALLOWED_MODES:
        return override

    raw = getattr(settings, "dupont_mode", "auto")
    value = (raw or "auto").lower()
    return value if value in ALLOWED_MODES else "auto"


def _compute_annual(dataset: CompanyDataset):
    current = latest_annual_statement(dataset)
    if current is None:
        return "annual", None
    previous = previous_comparable_statement(dataset, current)
    current_equity = book_equity(current)
    previous_equity = book_equity(previous) if previous else None
    average_assets = average(statement_value(current, "total_assets"), statement_value(previous, "total_assets") if previous else None)
    average_equity = average(current_equity, previous_equity)
    net_profit_margin = safe_divide(statement_value(current, "net_income"), statement_value(current, "revenue"))
    asset_turnover = safe_divide(statement_value(current, "revenue"), average_assets)
    equity_multiplier = safe_divide(average_assets, average_equity)
    return "annual", (
        net_profit_margin,
        asset_turnover,
        equity_multiplier,
        average_assets,
        average_equity,
        current,
    )


def _compute_ttm(dataset: CompanyDataset):
    # Prefer the latest non-annual filing (e.g., 10-Q) to build a rolling TTM.
    current = next((point for point in dataset.financials if point.filing_type not in ANNUAL_FORMS), None) or latest_statement(dataset)
    if current is None or current.filing_type in ANNUAL_FORMS:
        return "ttm", None
    ttm_points = _standalone_quarter_window(dataset, current)

    if ttm_points is not None:
        revenue_total = _sum_field(ttm_points, "revenue")
        net_income_total = _sum_field(ttm_points, "net_income")
        assets_values = [_number(statement_value(point, "total_assets")) for point in ttm_points]
        equity_values = [_number(book_equity(point)) for point in ttm_points]
        average_assets = average(*assets_values)
        average_equity = average(*equity_values)
    elif current.filing_type == "10-Q":
        # SEC 10-Q income statement lines are often year-to-date values. Bridge through
        # the latest 10-K so the implied Q4 contribution remains in TTM instead of being
        # dropped by summing the latest four 10-Q filings.
        latest_annual = _latest_annual_before(dataset, current.period_end)
        prior_ytd = _prior_year_same_period(dataset, current)
        if latest_annual is None or prior_ytd is None:
            return "ttm", None

        revenue_total = _ttm_bridge_value(latest_annual, current, prior_ytd, "revenue")
        net_income_total = _ttm_bridge_value(latest_annual, current, prior_ytd, "net_income")
        average_assets = average(
            _number(statement_value(current, "total_assets")),
            _number(statement_value(prior_ytd, "total_assets")),
        )
        average_equity = average(
            _number(book_equity(current)),
            _number(book_equity(prior_ytd)),
        )
    else:
        return "ttm", None

    net_profit_margin = safe_divide(net_income_total, revenue_total)
    asset_turnover = safe_divide(revenue_total, average_assets)
    equity_multiplier = safe_divide(average_assets, average_equity)

    return "ttm", (
        net_profit_margin,
        asset_turnover,
        equity_multiplier,
        average_assets,
        average_equity,
        current,
    )


def get_mode() -> str:
    """Expose mode for caching/signature purposes."""
    return _get_mode()


def set_mode_override(mode: str | None):
    normalized = (mode or "").lower()
    return _DUPONT_MODE_OVERRIDE.set(normalized if normalized in ALLOWED_MODES else None)


def reset_mode_override(token) -> None:
    if token is not None:
        try:
            _DUPONT_MODE_OVERRIDE.reset(token)
        except Exception:
            pass
