from __future__ import annotations

from app.model_engine.types import CompanyDataset
from app.model_engine.utils import (
    annual_series,
    book_equity,
    json_number,
    latest_non_null,
    safe_divide,
    statement_value,
    status_explanation,
    status_from_data_quality,
    trust_summary,
    valuation_applicability,
)
from app.services.risk_free_rate import get_latest_risk_free_rate

MODEL_NAME = "residual_income"
MODEL_VERSION = "1.0.0"

# Cost-of-equity assumptions
EQUITY_RISK_PREMIUM = 0.05
FINANCIAL_FIRM_ADDITIONAL_RISK = 0.005   # small size/complexity premium
LONG_RUN_ROE = 0.10                      # fade target (represents CoE at steady state)
TERMINAL_GROWTH_RATE = 0.025             # long-run nominal GDP proxy
PROJECTION_YEARS = 5

REQUIRED_FIELDS = [
    "total_assets",
    "total_liabilities",
    "net_income",
    "shares_outstanding",
]


def compute(dataset: CompanyDataset) -> dict[str, object]:
    applicability = valuation_applicability(dataset)
    risk_free = get_latest_risk_free_rate(dataset.as_of_date)
    coe = risk_free.rate_used + EQUITY_RISK_PREMIUM + FINANCIAL_FIRM_ADDITIONAL_RISK

    # Applicability: RI is *preferred* for financials, but works for all sectors
    is_financial = not applicability["is_supported"]   # DCF rejects these ↔ RI prefers them

    annuals = annual_series(dataset, limit=5)
    if not annuals:
        return {
            "status": "insufficient_data",
            "model_status": "insufficient_data",
            "explanation": status_explanation("insufficient_data"),
            "reason": "Annual financial history unavailable.",
            "applicability": applicability,
            "price_snapshot": _price_snapshot(dataset),
        }

    latest = annuals[0]

    # Book equity
    bv = book_equity(latest)
    if bv is None or bv <= 0:
        # Try stockholders_equity direct field
        bv = float(statement_value(latest, "stockholders_equity") or 0) or None
    if bv is None or bv <= 0:
        return {
            "status": "insufficient_data",
            "model_status": "insufficient_data",
            "explanation": status_explanation("insufficient_data"),
            "reason": "Book equity (total_assets - total_liabilities or stockholders_equity) unavailable.",
            "applicability": applicability,
            "price_snapshot": _price_snapshot(dataset),
        }

    # Net income
    net_income = statement_value(latest, "net_income")
    if net_income is None:
        net_income = statement_value(latest, "net_income_loss")
    if net_income is None:
        return {
            "status": "insufficient_data",
            "model_status": "insufficient_data",
            "explanation": status_explanation("insufficient_data"),
            "reason": "Net income unavailable.",
            "applicability": applicability,
            "price_snapshot": _price_snapshot(dataset),
        }
    net_income = float(net_income)

    # Shares outstanding
    shares = latest_non_null(dataset, "shares_outstanding")
    if shares is None:
        shares = latest_non_null(dataset, "weighted_average_diluted_shares")
    if shares is None or shares <= 0:
        return {
            "status": "insufficient_data",
            "model_status": "insufficient_data",
            "explanation": status_explanation("insufficient_data"),
            "reason": "Shares outstanding unavailable.",
            "applicability": applicability,
            "price_snapshot": _price_snapshot(dataset),
        }

    bv = float(bv)
    shares = float(shares)

    roe = safe_divide(net_income, bv)
    if roe is None:
        roe = 0.0

    # Proxy indicator
    used_proxy = statement_value(latest, "stockholders_equity") is not None and (
        statement_value(latest, "total_assets") is None or statement_value(latest, "total_liabilities") is None
    )

    # Detect multi-year book equity to refine roe average
    historical_roes: list[float] = []
    for point in annuals:
        bv_pt = book_equity(point)
        if bv_pt is None:
            bv_pt_raw = statement_value(point, "stockholders_equity")
            bv_pt = float(bv_pt_raw) if bv_pt_raw is not None else None
        ni_pt = statement_value(point, "net_income") or statement_value(point, "net_income_loss")
        if bv_pt and ni_pt and bv_pt > 0:
            historical_roes.append(float(ni_pt) / float(bv_pt))

    # Use average ROE if available, else single year
    avg_roe = sum(historical_roes) / len(historical_roes) if historical_roes else roe

    # ----- Residual income projection -----
    # Year 0: book equity = bv, ROE = avg_roe
    # Fade ROE linearly toward CoE over PROJECTION_YEARS
    # RI_t = (ROE_t - CoE) × BV_{t-1}
    # BV grows by retained earnings: BV_t = BV_{t-1} + RI_t + CoE × BV_{t-1} × (1 - payout_approx)
    # Simplification: assume dividend payout = 1 - (g/ROE) where g = TERMINAL_GROWTH_RATE
    payout = min(0.8, max(0.0, 1.0 - safe_divide(TERMINAL_GROWTH_RATE, avg_roe or coe) or 0.0))
    retention = 1.0 - payout

    projections: list[dict] = []
    pv_ri_sum = 0.0
    bv_roll = bv
    roe_roll = avg_roe

    for t in range(1, PROJECTION_YEARS + 1):
        # Linear fade of ROE toward CoE
        fade_fraction = t / PROJECTION_YEARS
        roe_t = roe_roll * (1 - fade_fraction) + coe * fade_fraction
        ri_t = (roe_t - coe) * bv_roll
        discount_factor = (1 + coe) ** t
        pv_ri = ri_t / discount_factor
        pv_ri_sum += pv_ri
        projections.append({
            "year": t,
            "book_equity": json_number(bv_roll),
            "roe": json_number(roe_t),
            "residual_income": json_number(ri_t),
            "pv_residual_income": json_number(pv_ri),
        })
        # Roll forward book equity
        bv_roll = bv_roll + roe_t * bv_roll * retention

    # Terminal residual income: Gordon growth in perpetuity
    roe_terminal = LONG_RUN_ROE
    ri_terminal = (roe_terminal - coe) * bv_roll
    terminal_divisor = coe - TERMINAL_GROWTH_RATE
    if terminal_divisor <= 0:
        terminal_divisor = 0.01
    terminal_value = ri_terminal / terminal_divisor / ((1 + coe) ** PROJECTION_YEARS)

    intrinsic_value_equity = bv + pv_ri_sum + terminal_value
    intrinsic_value_per_share = safe_divide(intrinsic_value_equity, shares)

    # Status
    missing_fields_list = [f for f in REQUIRED_FIELDS if latest_non_null(dataset, f) is None]
    status = status_from_data_quality(
        missing_fields=missing_fields_list,
        proxy_used=used_proxy,
        can_compute_directional=True,
    )

    # Price comparison
    price_snap = _price_snapshot(dataset)
    upside: float | None = None
    if (
        intrinsic_value_per_share is not None
        and price_snap.get("latest_price") is not None
        and float(price_snap["latest_price"]) > 0
    ):
        upside = (intrinsic_value_per_share - float(price_snap["latest_price"])) / float(price_snap["latest_price"])

    return {
        "status": "ok" if status == "supported" else status,
        "model_status": status,
        "explanation": status_explanation(status),
        "applicability": applicability,
        "primary_for_sector": is_financial,
        "inputs": {
            "book_equity": json_number(bv),
            "net_income": json_number(net_income),
            "roe": json_number(roe),
            "avg_roe_5y": json_number(avg_roe),
            "cost_of_equity": json_number(coe),
            "terminal_growth_rate": json_number(TERMINAL_GROWTH_RATE),
            "payout_ratio_assumed": json_number(payout),
            "shares_outstanding": json_number(shares),
        },
        "projections": projections,
        "intrinsic_value": {
            "book_equity_per_share": json_number(safe_divide(bv, shares)),
            "pv_residual_income_per_share": json_number(safe_divide(pv_ri_sum, shares)),
            "terminal_value_per_share": json_number(safe_divide(terminal_value, shares)),
            "intrinsic_value_per_share": json_number(intrinsic_value_per_share),
            "upside_vs_price": json_number(upside),
        },
        "price_snapshot": price_snap,
        "data_quality": {
            "missing_fields": missing_fields_list,
            "used_proxy_book_equity": used_proxy,
            "historical_roe_years": len(historical_roes),
        },
        "assumption_provenance": {
            "risk_free_rate": {
                "source_name": risk_free.source_name,
                "tenor": risk_free.tenor,
                "observation_date": risk_free.observation_date.isoformat(),
                "rate_used": json_number(risk_free.rate_used),
            },
            "equity_risk_premium": json_number(EQUITY_RISK_PREMIUM),
            "financial_firm_additional_risk": json_number(FINANCIAL_FIRM_ADDITIONAL_RISK),
            "cost_of_equity": json_number(coe),
        },
        "trust_summary": trust_summary(missing_fields=missing_fields_list, proxy_used=used_proxy),
    }


def _price_snapshot(dataset: CompanyDataset) -> dict:
    if dataset.market_snapshot is None:
        return {"latest_price": None, "price_date": None, "price_source": None}
    ms = dataset.market_snapshot
    return {
        "latest_price": json_number(ms.latest_price),
        "price_date": ms.price_date.isoformat() if ms.price_date else None,
        "price_source": ms.price_source,
    }
