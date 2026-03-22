from __future__ import annotations

from app.model_engine.types import CompanyDataset
from app.model_engine.utils import annual_series, json_number, safe_divide, status_explanation, status_from_data_quality, trust_summary

MODEL_NAME = "capital_allocation"
MODEL_VERSION = "1.0.0"


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
    total_market_cap_proxy = 0.0
    rows: list[dict[str, object]] = []

    missing_fields: set[str] = set()
    proxy_used = False

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

        shares = data.get("weighted_average_diluted_shares") or data.get("shares_outstanding")
        if shares and data.get("eps"):
            total_market_cap_proxy += abs(float(shares) * float(data.get("eps")) * 12)
        else:
            proxy_used = True

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

    shareholder_yield = safe_divide(total_dividends + total_buybacks - total_sbc, total_market_cap_proxy)
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
        "net_shareholder_distribution": json_number(total_dividends + total_buybacks - total_sbc),
        "debt_financing_signal": json_number(total_debt_change),
        "capital_return_mix": net_payout_mix,
        "series": rows,
        "missing_required_fields_last_3y": sorted(missing_fields),
    }
