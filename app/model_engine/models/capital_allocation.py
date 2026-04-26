from __future__ import annotations

from app.model_engine.types import CompanyDataset
from app.model_engine.utils import annual_series, json_number, safe_divide, status_explanation, status_from_data_quality, trust_summary
from app.services.share_count_selection import shares_for_market_cap

MODEL_NAME = "capital_allocation"
MODEL_VERSION = "1.3.0"


def compute(dataset: CompanyDataset) -> dict[str, object]:
    annuals = annual_series(dataset, limit=3)
    if not annuals:
        return {
            "status": "insufficient_data",
            "model_status": "insufficient_data",
            "explanation": status_explanation("insufficient_data"),
            "reason": "Annual statements unavailable",
        }

    total_dividends = 0.0
    total_buybacks = 0.0
    total_debt_change = 0.0
    total_sbc = 0.0
    rows: list[dict[str, object]] = []
    periods_used = len(annuals)

    missing_fields: set[str] = set()
    proxy_used = False
    market_snapshot = dataset.market_snapshot
    latest_price = market_snapshot.latest_price if market_snapshot is not None else None

    for point in reversed(annuals):
        data = point.data or {}
        dividends = abs(float(data.get("dividends") or 0))
        buybacks = abs(float(data.get("share_buybacks") or 0))
        debt_change = float(data.get("debt_changes") or 0)
        sbc = float(data.get("stock_based_compensation") or 0)

        if data.get("dividends") is None:
            missing_fields.add("dividends")
        if data.get("share_buybacks") is None:
            missing_fields.add("share_buybacks")
        if data.get("debt_changes") is None:
            missing_fields.add("debt_changes")
        if data.get("stock_based_compensation") is None:
            missing_fields.add("stock_based_compensation")

        total_dividends += dividends
        total_buybacks += buybacks
        total_debt_change += debt_change
        total_sbc += sbc

        rows.append(
            {
                "period_end": point.period_end.isoformat(),
                "dividends": json_number(dividends),
                "buybacks": json_number(buybacks),
                "debt_change": json_number(debt_change),
                "stock_based_compensation": json_number(sbc),
                "net_shareholder_distribution": json_number(dividends + buybacks - sbc),
            }
        )

    shareholder_distribution = total_dividends + total_buybacks - total_sbc
    annualized_shareholder_distribution = safe_divide(shareholder_distribution, periods_used)
    market_cap_denominator, denominator_method, market_cap_proxy_used, share_source = _latest_market_cap(annuals[0], latest_price, missing_fields)
    proxy_used = proxy_used or market_cap_proxy_used

    shareholder_yield = safe_divide(annualized_shareholder_distribution, market_cap_denominator)
    cumulative_shareholder_distribution_ratio = safe_divide(shareholder_distribution, market_cap_denominator)
    net_payout_mix = {
        "dividends_share": json_number(safe_divide(total_dividends, total_dividends + total_buybacks)),
        "buybacks_share": json_number(safe_divide(total_buybacks, total_dividends + total_buybacks)),
    }

    can_directional = total_dividends > 0 or total_buybacks > 0 or total_sbc > 0 or total_debt_change != 0
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
        "shareholder_yield": json_number(shareholder_yield),
        "net_shareholder_distribution": json_number(shareholder_distribution),
        "annualized_shareholder_distribution": json_number(annualized_shareholder_distribution),
        "cumulative_shareholder_distribution_ratio": json_number(cumulative_shareholder_distribution_ratio),
        "debt_financing_signal": json_number(total_debt_change),
        "capital_return_mix": net_payout_mix,
        "shareholder_yield_basis": {
            "method": denominator_method,
            "metric_definition": "annualized_net_shareholder_distribution_divided_by_market_cap",
            "numerator_horizon_years": periods_used,
            "numerator_periods_used": periods_used,
            "annualized_shareholder_distribution": json_number(annualized_shareholder_distribution),
            "cumulative_shareholder_distribution": json_number(shareholder_distribution),
            "market_cap_denominator": json_number(market_cap_denominator),
            "latest_price": json_number(latest_price),
            "market_cap_horizon_years": 1 if market_cap_denominator is not None else None,
            "market_cap_observations_used": 1 if market_cap_denominator is not None else 0,
            "share_count_periods_used": 1 if market_cap_denominator is not None else 0,
            "market_cap_share_source": share_source,
            "market_cap_share_source_is_proxy": market_cap_proxy_used,
        },
        "series": rows,
        "missing_required_fields_last_3y": sorted(missing_fields),
    }


def _latest_market_cap(
    latest_annual: object,
    latest_price: float | None,
    missing_fields: set[str],
) -> tuple[float | None, str | None, bool, str | None]:
    if latest_price in (None, 0):
        missing_fields.add("latest_price")
        return None, None, True, None

    data = getattr(latest_annual, "data", {}) or {}
    share_selection = shares_for_market_cap(data)
    if share_selection.source != "shares_outstanding":
        missing_fields.add("shares_outstanding")
    if share_selection.source is None:
        missing_fields.add("weighted_average_diluted_shares")
        return None, None, True, None

    method = "latest_market_cap" if not share_selection.is_proxy else "latest_market_cap_proxy_shares"
    return abs(float(latest_price) * float(share_selection.value)), method, share_selection.is_proxy, share_selection.source
