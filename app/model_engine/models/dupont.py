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
    statement_value,
)

MODEL_NAME = "dupont"
MODEL_VERSION = "1.1.0"

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
        return {"status": "insufficient_data", "reason": "Need annual filing or four comparable periods for DuPont"}

    net_profit_margin, asset_turnover, equity_multiplier, average_assets, average_equity, current = metrics

    return {
        "status": "ok" if all(value is not None for value in (net_profit_margin, asset_turnover, equity_multiplier)) else "partial",
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
    comparable = [point for point in dataset.financials if point.filing_type == current.filing_type]
    ttm_points = comparable[:4]
    if len(ttm_points) < 4:
        return "ttm", None

    revenue_total = _sum_field(ttm_points, "revenue")
    net_income_total = _sum_field(ttm_points, "net_income")
    assets_values = [_number(statement_value(point, "total_assets")) for point in ttm_points]
    equity_values = [_number(book_equity(point)) for point in ttm_points]
    average_assets = average(*assets_values)
    average_equity = average(*equity_values)

    net_profit_margin = safe_divide(net_income_total, revenue_total)
    asset_turnover = safe_divide(revenue_total, average_assets)
    equity_multiplier = safe_divide(average_assets, average_equity)

    return "ttm", (
        net_profit_margin,
        asset_turnover,
        equity_multiplier,
        average_assets,
        average_equity,
        ttm_points[0],
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
