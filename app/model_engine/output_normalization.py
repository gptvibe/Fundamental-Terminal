from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

from app.model_engine.types import CompanyDataset
from app.model_engine.utils import ANNUAL_FORMS, UNSUPPORTED_FINANCIAL_KEYWORDS, json_number
from app.services.oil_exposure import classify_oil_exposure

MODEL_STATUS_SUPPORTED = "supported"
MODEL_STATUS_PARTIAL = "partial"
MODEL_STATUS_PROXY = "proxy"
MODEL_STATUS_INSUFFICIENT_DATA = "insufficient_data"
MODEL_STATUS_UNSUPPORTED = "unsupported"

_STATUS_NORMALIZATION = {
    "ok": MODEL_STATUS_SUPPORTED,
    "supported": MODEL_STATUS_SUPPORTED,
    "partial": MODEL_STATUS_PARTIAL,
    "proxy": MODEL_STATUS_PROXY,
    "insufficient_data": MODEL_STATUS_INSUFFICIENT_DATA,
    "unsupported": MODEL_STATUS_UNSUPPORTED,
}

_MODEL_FIELDS: dict[str, list[str]] = {
    "altman_z": [
        "total_assets",
        "total_liabilities",
        "current_assets",
        "current_liabilities",
        "retained_earnings",
        "revenue",
        "operating_income",
        "shares_outstanding",
        "weighted_average_diluted_shares",
        "market_snapshot.latest_price",
    ],
    "capital_allocation": [
        "dividends",
        "share_buybacks",
        "debt_changes",
        "stock_based_compensation",
        "weighted_average_diluted_shares",
        "shares_outstanding",
        "eps",
    ],
    "dcf": [
        "free_cash_flow",
        "operating_cash_flow",
        "capex",
        "cash_and_short_term_investments",
        "cash_and_cash_equivalents",
        "short_term_investments",
        "current_debt",
        "long_term_debt",
        "weighted_average_diluted_shares",
        "shares_outstanding",
    ],
    "dupont": [
        "net_income",
        "revenue",
        "total_assets",
        "total_liabilities",
    ],
    "piotroski": [
        "net_income",
        "total_assets",
        "current_assets",
        "current_liabilities",
        "operating_cash_flow",
        "shares_outstanding",
        "long_term_debt",
        "gross_profit",
        "revenue",
    ],
    "ratios": [
        "gross_profit",
        "revenue",
        "operating_income",
        "net_income",
        "operating_cash_flow",
        "free_cash_flow",
        "total_assets",
        "total_liabilities",
        "interest_expense",
        "capex",
        "stock_based_compensation",
        "current_debt",
        "long_term_debt",
        "cash_and_short_term_investments",
        "dividends",
    ],
    "residual_income": [
        "total_assets",
        "total_liabilities",
        "stockholders_equity",
        "net_income",
        "net_income_loss",
        "shares_outstanding",
        "weighted_average_diluted_shares",
        "market_snapshot.latest_price",
    ],
    "reverse_dcf": [
        "revenue",
        "operating_income",
        "free_cash_flow",
        "operating_cash_flow",
        "weighted_average_diluted_shares",
        "shares_outstanding",
        "market_snapshot.latest_price",
    ],
    "roic": [
        "operating_income",
        "income_tax_expense",
        "stockholders_equity",
        "current_debt",
        "long_term_debt",
        "cash_and_short_term_investments",
        "capex",
        "operating_cash_flow",
    ],
}

_MODEL_BASELINE_WARNINGS: dict[str, list[str]] = {
    "altman_z": [
        "Altman Z is calibrated for industrial balance sheets and can mislead for banks, insurers, and asset-light issuers.",
    ],
    "capital_allocation": [
        "Capital allocation signals can mislead when one-off recapitalizations or acquisition financing dominate recent cash uses.",
    ],
    "dcf": [
        "DCF can mislead when normalized cash flow is not representative of the issuer's cycle or competitive position.",
    ],
    "dupont": [
        "DuPont decomposition can mislead when acquisitions, accounting changes, or non-operating items distort the latest period.",
    ],
    "piotroski": [
        "Piotroski is most informative for mature issuers and can understate quality for high-growth or restructuring stories.",
    ],
    "ratios": [
        "Single-period ratios can mislead when recent filings contain unusual items or temporary working-capital swings.",
    ],
    "residual_income": [
        "Residual income can mislead when reported book equity understates intangible economics or capital returns heavily reshape equity.",
    ],
    "reverse_dcf": [
        "Reverse DCF can mislead when the observed market price is temporarily dislocated from fundamentals.",
    ],
    "roic": [
        "ROIC can mislead when invested capital is distorted by acquisitions, leases, or financial-firm balance sheet structure.",
    ],
}


def normalize_model_status(status: str | None) -> str:
    normalized = str(status or "").strip().lower()
    return _STATUS_NORMALIZATION.get(normalized, MODEL_STATUS_INSUFFICIENT_DATA)


def standardize_model_result(
    model_name: str,
    result: dict[str, Any] | None,
    *,
    input_payload: dict[str, Any] | None = None,
    dataset: CompanyDataset | None = None,
    company_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(result or {})
    status = normalize_model_status(str(payload.get("model_status") or payload.get("status") or ""))
    periods = _period_payloads(input_payload, dataset)
    market_snapshot = _market_snapshot_payload(input_payload, dataset)
    context = _company_context(payload, company_context, dataset)
    missing_fields = _missing_fields(payload)
    proxy_usage = _proxy_usage(model_name, payload)
    stale_inputs = _stale_inputs(periods, market_snapshot, payload, input_payload, dataset)
    sector_suitability = _sector_suitability(model_name, payload, context)
    fields_used = _fields_used(model_name, periods, market_snapshot, payload)
    misleading_reasons = _misleading_reasons(
        model_name,
        status=status,
        missing_fields=missing_fields,
        proxy_usage=proxy_usage,
        stale_inputs=stale_inputs,
        sector_suitability=sector_suitability,
    )
    confidence_score, confidence_reasons = _confidence_profile(
        status=status,
        missing_fields=missing_fields,
        proxy_usage=proxy_usage,
        stale_inputs=stale_inputs,
        sector_suitability=sector_suitability,
    )

    payload["status"] = status
    payload["model_status"] = status
    payload["confidence_score"] = json_number(confidence_score)
    payload["confidence_reasons"] = confidence_reasons
    payload["fields_used"] = fields_used
    payload["proxy_usage"] = proxy_usage
    payload["stale_inputs"] = stale_inputs
    payload["sector_suitability"] = sector_suitability
    payload["misleading_reasons"] = misleading_reasons
    payload["confidence_summary"] = _confidence_summary(confidence_score, confidence_reasons)
    payload["status_flags"] = _status_flags(status, missing_fields, proxy_usage, stale_inputs, sector_suitability)
    payload.setdefault("explanation", _status_explanation(status))
    return payload


def _period_payloads(input_payload: dict[str, Any] | None, dataset: CompanyDataset | None) -> list[dict[str, Any]]:
    if isinstance(input_payload, dict):
        periods = input_payload.get("periods")
        if isinstance(periods, list):
            return [period for period in periods if isinstance(period, dict)]

    if dataset is None:
        return []

    return [
        {
            "filing_type": point.filing_type,
            "period_end": point.period_end.isoformat(),
            "last_updated": point.last_updated.isoformat(),
            "data": dict(point.data or {}),
        }
        for point in dataset.financials
    ]


def _market_snapshot_payload(input_payload: dict[str, Any] | None, dataset: CompanyDataset | None) -> dict[str, Any] | None:
    if isinstance(input_payload, dict):
        market_snapshot = input_payload.get("market_snapshot")
        if isinstance(market_snapshot, dict):
            return market_snapshot

    if dataset is None or dataset.market_snapshot is None:
        return None

    return {
        "latest_price": dataset.market_snapshot.latest_price,
        "price_date": dataset.market_snapshot.price_date.isoformat() if dataset.market_snapshot.price_date is not None else None,
        "price_source": dataset.market_snapshot.price_source,
    }


def _company_context(
    result: dict[str, Any],
    company_context: dict[str, Any] | None,
    dataset: CompanyDataset | None,
) -> dict[str, Any]:
    if isinstance(company_context, dict):
        return {
            "sector": company_context.get("sector"),
            "market_sector": company_context.get("market_sector"),
            "market_industry": company_context.get("market_industry"),
            "oil_exposure_type": company_context.get("oil_exposure_type"),
            "oil_support_status": company_context.get("oil_support_status"),
            "oil_support_reasons": company_context.get("oil_support_reasons") or [],
        }

    applicability = result.get("applicability")
    if isinstance(applicability, dict):
        classification = applicability.get("classification")
        if isinstance(classification, dict):
            return {
                "sector": classification.get("sector"),
                "market_sector": classification.get("market_sector"),
                "market_industry": classification.get("market_industry"),
                "oil_exposure_type": classification.get("oil_exposure_type"),
                "oil_support_status": classification.get("oil_support_status"),
                "oil_support_reasons": classification.get("oil_support_reasons") or [],
            }

    if dataset is None:
        return {
            "sector": None,
            "market_sector": None,
            "market_industry": None,
            "oil_exposure_type": None,
            "oil_support_status": None,
            "oil_support_reasons": [],
        }

    oil_classification = classify_oil_exposure(
        sector=dataset.sector,
        market_sector=dataset.market_sector,
        market_industry=dataset.market_industry,
    )

    return {
        "sector": dataset.sector,
        "market_sector": dataset.market_sector,
        "market_industry": dataset.market_industry,
        "oil_exposure_type": oil_classification.oil_exposure_type,
        "oil_support_status": oil_classification.oil_support_status,
        "oil_support_reasons": list(oil_classification.oil_support_reasons),
    }


def _missing_fields(result: dict[str, Any]) -> list[str]:
    raw = result.get("missing_required_fields_last_3y") or result.get("missing_fields")
    if isinstance(raw, list):
        return sorted({str(item) for item in raw if item})
    data_quality = result.get("data_quality")
    if isinstance(data_quality, dict):
        raw = data_quality.get("missing_fields")
        if isinstance(raw, list):
            return sorted({str(item) for item in raw if item})
    return []


def _proxy_usage(model_name: str, result: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    input_quality = result.get("input_quality")
    if model_name == "dcf" and isinstance(input_quality, dict):
        if input_quality.get("starting_cash_flow_proxied"):
            items.append(
                {
                    "target": "free_cash_flow",
                    "proxy_fields": ["operating_cash_flow", "capex"],
                    "reason": "Direct free cash flow history was incomplete, so operating cash flow minus capex was used where needed.",
                }
            )
        if input_quality.get("capital_structure_proxied"):
            items.append(
                {
                    "target": "cash_and_short_term_investments",
                    "proxy_fields": ["cash_and_cash_equivalents", "short_term_investments"],
                    "reason": "Cash structure inputs were approximated from available cash and short-term investment balances.",
                }
            )

    if model_name == "reverse_dcf" and isinstance(input_quality, dict):
        if input_quality.get("starting_fcf_margin_proxied"):
            items.append(
                {
                    "target": "free_cash_flow_margin",
                    "proxy_fields": ["operating_cash_flow", "capex", "revenue"],
                    "reason": "Free-cash-flow margin was approximated from operating cash flow less capex when direct free cash flow was unavailable.",
                }
            )
        if input_quality.get("capital_structure_proxied"):
            items.append(
                {
                    "target": "enterprise_value",
                    "proxy_fields": ["latest_price", "shares_outstanding", "weighted_average_diluted_shares"],
                    "reason": "Reverse DCF fell back to an equity-value target because debt or cash inputs were incomplete.",
                }
            )

    data_quality = result.get("data_quality")
    if model_name == "residual_income" and isinstance(data_quality, dict) and data_quality.get("used_proxy_book_equity"):
        items.append(
            {
                "target": "book_equity",
                "proxy_fields": ["stockholders_equity"],
                "reason": "Residual income fell back to stockholders equity when asset-liability book equity was unavailable.",
            }
        )

    shareholder_yield_basis = result.get("shareholder_yield_basis")
    if model_name == "capital_allocation" and isinstance(shareholder_yield_basis, dict):
        shareholder_yield_method = str(shareholder_yield_basis.get("method") or "")
        if shareholder_yield_method.startswith("average_market_cap"):
            items.append(
                {
                    "target": "market_cap_proxy",
                    "proxy_fields": ["latest_price", "weighted_average_diluted_shares", "shares_outstanding"],
                    "reason": "Shareholder yield used an average market-cap denominator built from latest price and available share counts.",
                }
            )
        elif shareholder_yield_method == "latest_market_cap_proxy_shares":
            items.append(
                {
                    "target": "market_cap_proxy",
                    "proxy_fields": ["latest_price", "weighted_average_diluted_shares"],
                    "reason": "Shareholder yield fell back to diluted shares because point-in-time shares outstanding were unavailable.",
                }
            )
        elif shareholder_yield_basis.get("market_cap_denominator") is None:
            items.append(
                {
                    "target": "market_cap_proxy",
                    "proxy_fields": ["latest_price", "shares_outstanding"],
                    "reason": "Shareholder yield was left unavailable because a current market-cap denominator could not be observed directly.",
                }
            )

    if model_name == "roic" and result.get("capital_cost_proxy") is not None:
        items.append(
            {
                "target": "capital_cost",
                "proxy_fields": ["risk_free_rate"],
                "reason": "ROIC spread is compared against a proxy capital cost built from the risk-free rate plus a fixed spread.",
            }
        )

    return {"used": bool(items), "items": items}


def _stale_inputs(
    periods: list[dict[str, Any]],
    market_snapshot: dict[str, Any] | None,
    result: dict[str, Any],
    input_payload: dict[str, Any] | None,
    dataset: CompanyDataset | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    reference_date = _reference_date(input_payload, dataset)
    latest_period = periods[0] if periods else None
    latest_period_end = _parse_date(latest_period.get("period_end")) if isinstance(latest_period, dict) else None
    latest_filing_type = str(latest_period.get("filing_type") or "") if isinstance(latest_period, dict) else ""
    if latest_period_end is not None:
        threshold_days = 430 if latest_filing_type in ANNUAL_FORMS else 190
        age_days = (reference_date - latest_period_end).days
        if age_days > threshold_days:
            items.append(
                {
                    "input_name": "financial_statements",
                    "observed_at": latest_period_end.isoformat(),
                    "age_days": age_days,
                    "threshold_days": threshold_days,
                    "reason": "Latest financial statement is older than the freshness window expected for this filing cadence.",
                }
            )

    if isinstance(market_snapshot, dict):
        price_date = _parse_date(market_snapshot.get("price_date"))
        if price_date is not None:
            age_days = (reference_date - price_date).days
            if age_days > 10:
                items.append(
                    {
                        "input_name": "market_price",
                        "observed_at": price_date.isoformat(),
                        "age_days": age_days,
                        "threshold_days": 10,
                        "reason": "Latest cached market price is older than the short-horizon freshness window used for model overlays.",
                    }
                )

    assumption_provenance = result.get("assumption_provenance")
    if isinstance(assumption_provenance, dict):
        risk_free = assumption_provenance.get("risk_free_rate")
        if isinstance(risk_free, dict):
            observed_at = _parse_date(risk_free.get("observation_date"))
            if observed_at is not None:
                age_days = (reference_date - observed_at).days
                if age_days > 10:
                    items.append(
                        {
                            "input_name": "risk_free_rate",
                            "observed_at": observed_at.isoformat(),
                            "age_days": age_days,
                            "threshold_days": 10,
                            "reason": "The treasury curve observation backing discount-rate assumptions is older than the market freshness window.",
                        }
                    )

    return items


def _sector_suitability(model_name: str, result: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    classification = {
        "sector": context.get("sector"),
        "market_sector": context.get("market_sector"),
        "market_industry": context.get("market_industry"),
        "oil_exposure_type": context.get("oil_exposure_type"),
        "oil_support_status": context.get("oil_support_status"),
        "oil_support_reasons": context.get("oil_support_reasons") or [],
    }
    applicability = result.get("applicability") if isinstance(result.get("applicability"), dict) else None
    classification_text = " ".join(str(value or "") for value in classification.values()).lower()
    is_financial_like = any(keyword in classification_text for keyword in UNSUPPORTED_FINANCIAL_KEYWORDS)

    status = MODEL_STATUS_SUPPORTED
    reason = "Model is broadly suitable for this issuer based on the available sector classification."
    if model_name in {"dcf", "reverse_dcf"} and ((isinstance(applicability, dict) and not applicability.get("is_supported", True)) or is_financial_like):
        status = MODEL_STATUS_UNSUPPORTED
        reason = "Valuation logic is structurally unreliable for banks, insurers, REITs, and capital-markets-style financial firms."
    elif model_name == "residual_income" and is_financial_like:
        reason = "Residual income is generally more suitable than cash-flow models for balance-sheet-driven financial issuers."
    elif model_name in {"altman_z", "dupont", "piotroski", "roic", "capital_allocation"} and is_financial_like:
        status = MODEL_STATUS_PARTIAL
        reason = "This model can be directionally useful, but sector accounting conventions make issuer-level interpretation less reliable."

    return {
        "status": status,
        "is_supported": status != MODEL_STATUS_UNSUPPORTED,
        "reason": reason,
        "classification": classification,
    }


def _fields_used(
    model_name: str,
    periods: list[dict[str, Any]],
    market_snapshot: dict[str, Any] | None,
    result: dict[str, Any],
) -> list[str]:
    candidates = _MODEL_FIELDS.get(model_name, [])
    fields: list[str] = []
    data_rows = [period.get("data") for period in periods if isinstance(period.get("data"), dict)]
    input_quality = result.get("input_quality") if isinstance(result.get("input_quality"), dict) else {}

    for candidate in candidates:
        if candidate.startswith("market_snapshot."):
            key = candidate.split(".", 1)[1]
            if isinstance(market_snapshot, dict) and market_snapshot.get(key) is not None:
                fields.append(candidate)
            continue

        if candidate in {"operating_cash_flow", "capex"} and model_name == "dcf" and not input_quality.get("starting_cash_flow_proxied"):
            continue
        if candidate in {"cash_and_cash_equivalents", "short_term_investments"} and model_name == "dcf" and not input_quality.get("capital_structure_proxied"):
            continue

        if any(isinstance(row, dict) and row.get(candidate) is not None for row in data_rows):
            fields.append(candidate)

    return sorted(set(fields))


def _misleading_reasons(
    model_name: str,
    *,
    status: str,
    missing_fields: list[str],
    proxy_usage: dict[str, Any],
    stale_inputs: list[dict[str, Any]],
    sector_suitability: dict[str, Any],
) -> list[str]:
    reasons = list(_MODEL_BASELINE_WARNINGS.get(model_name, []))
    if missing_fields:
        reasons.append(f"Missing or incomplete inputs can skew the result: {', '.join(missing_fields)}.")
    if proxy_usage.get("used"):
        reasons.append("At least one core input was approximated rather than observed directly.")
    if stale_inputs:
        reasons.append("Some model inputs are stale relative to the evaluation date, which can make the output lag current conditions.")
    suitability_status = str(sector_suitability.get("status") or "")
    if suitability_status == MODEL_STATUS_PARTIAL:
        reasons.append(str(sector_suitability.get("reason") or "Sector-specific accounting can reduce comparability for this issuer."))
    if suitability_status == MODEL_STATUS_UNSUPPORTED:
        reasons.append(str(sector_suitability.get("reason") or "This issuer's sector makes the model structurally unreliable."))
    if status == MODEL_STATUS_INSUFFICIENT_DATA:
        reasons.append("The model is missing enough required evidence that the output should not be treated as decision-grade.")
    return _dedupe(reasons)


def _confidence_profile(
    *,
    status: str,
    missing_fields: list[str],
    proxy_usage: dict[str, Any],
    stale_inputs: list[dict[str, Any]],
    sector_suitability: dict[str, Any],
) -> tuple[float, list[str]]:
    base_score = {
        MODEL_STATUS_SUPPORTED: 0.9,
        MODEL_STATUS_PARTIAL: 0.65,
        MODEL_STATUS_PROXY: 0.5,
        MODEL_STATUS_INSUFFICIENT_DATA: 0.2,
        MODEL_STATUS_UNSUPPORTED: 0.0,
    }[status]
    reasons: list[str] = []

    if status == MODEL_STATUS_SUPPORTED:
        reasons.append("Core model inputs were available without a blocking sector constraint.")
    elif status == MODEL_STATUS_PARTIAL:
        reasons.append("The model is usable directionally, but some required issuer inputs are incomplete.")
    elif status == MODEL_STATUS_PROXY:
        reasons.append("The model depends on one or more approximation layers instead of direct issuer inputs.")
    elif status == MODEL_STATUS_INSUFFICIENT_DATA:
        reasons.append("Required issuer inputs were insufficient for a reliable directional output.")
    else:
        reasons.append("The issuer's sector profile makes this model structurally unsupported.")

    if missing_fields:
        base_score -= 0.05 if len(missing_fields) == 1 else 0.15
        reasons.append(f"Missing fields reduce confidence: {', '.join(missing_fields)}.")
    if proxy_usage.get("used"):
        base_score -= 0.1
        reasons.append("Proxy substitutions were required for at least one model input.")
    if stale_inputs:
        base_score -= 0.1
        reasons.append("One or more supporting inputs were stale relative to the evaluation date.")
    if str(sector_suitability.get("status") or "") == MODEL_STATUS_PARTIAL:
        base_score -= 0.1
        reasons.append("Sector-specific accounting limits comparability for this model.")

    return max(0.0, min(1.0, round(base_score, 4))), _dedupe(reasons)


def _confidence_summary(score: float, reasons: list[str]) -> str:
    if score >= 0.85:
        label = "High"
    elif score >= 0.65:
        label = "Moderate"
    elif score >= 0.35:
        label = "Low"
    else:
        label = "Very low"
    headline = reasons[0] if reasons else "No confidence rationale available."
    return f"{label} confidence ({score:.2f}): {headline}"


def _status_flags(
    status: str,
    missing_fields: list[str],
    proxy_usage: dict[str, Any],
    stale_inputs: list[dict[str, Any]],
    sector_suitability: dict[str, Any],
) -> list[str]:
    flags: list[str] = []
    if status == MODEL_STATUS_PARTIAL:
        flags.append("partial_inputs")
    if proxy_usage.get("used"):
        flags.append("proxy_usage")
    if missing_fields:
        flags.append("missing_inputs")
    if stale_inputs:
        flags.append("stale_inputs")
    if str(sector_suitability.get("status") or "") == MODEL_STATUS_UNSUPPORTED:
        flags.append("sector_unsupported")
    elif str(sector_suitability.get("status") or "") == MODEL_STATUS_PARTIAL:
        flags.append("sector_caution")
    return flags


def _reference_date(input_payload: dict[str, Any] | None, dataset: CompanyDataset | None) -> date:
    if isinstance(input_payload, dict):
        as_of_date = _parse_date(input_payload.get("as_of_date"))
        if as_of_date is not None:
            return as_of_date
    if dataset is not None and dataset.as_of_date is not None:
        return dataset.as_of_date
    if dataset is not None and dataset.market_snapshot is not None and dataset.market_snapshot.price_date is not None:
        return dataset.market_snapshot.price_date
    if dataset is not None and dataset.financials:
        latest_period_end = dataset.financials[0].period_end
        if latest_period_end is not None:
            return latest_period_end
    return datetime.now(timezone.utc).date()


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None


def _status_explanation(status: str) -> str:
    if status == MODEL_STATUS_UNSUPPORTED:
        return "This model is not structurally suitable for the issuer's sector profile."
    if status == MODEL_STATUS_PARTIAL:
        return "This model is usable directionally, but some issuer inputs are incomplete."
    if status == MODEL_STATUS_PROXY:
        return "This model depends on one or more proxy substitutions or approximation layers."
    if status == MODEL_STATUS_INSUFFICIENT_DATA:
        return "Required base inputs were not sufficient to produce a directional output."
    return "This model is supported by the available issuer inputs and sector profile."


def _dedupe(items: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)
    return ordered
