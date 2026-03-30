from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.model_engine.output_normalization import normalize_model_status
from app.models import Company, DerivedMetricPoint, FinancialRestatement, ModelRun

DEFAULT_PERIOD_TYPE = "ttm"
DEFAULT_SORT_FIELD = "revenue_growth"
DEFAULT_SORT_DIRECTION = "desc"
SUPPORTED_PERIOD_TYPES = ("quarterly", "annual", "ttm")
SUPPORTED_QUALITY_FLAG_OPTIONS = (
    "filing_date_unavailable",
    "filing_lag_proxy_from_last_updated",
    "growth_requires_previous_period",
    "historical_restatement_present",
    "metrics_cache_stale",
    "restatement_detected",
)
_RANKING_ORDER = ("quality", "value", "capital_allocation", "dilution_risk", "filing_risk")
_RANKING_UNIVERSE_BASIS = "candidate_universe_pre_filter"
_RANKING_METHOD_SUMMARY = (
    "Each component is converted into a cross-sectional percentile across the candidate universe before filters, "
    "then blended by weight into a 0-100 score. Missing components reweight the available weights, and flat distributions neutralize to 50."
)
_RANKING_CONFIDENCE_POLICY = [
    "missing_components_reweighted:<component_keys>",
    "proxy_components_present",
    "quality_flag:<flag>",
    "metrics_cache_stale",
    "single_candidate_universe",
    "flat_cross_sectional_distribution",
]
_SORTABLE_RANKING_FIELDS = {
    "quality_score": "quality",
    "value_score": "value",
    "capital_allocation_score": "capital_allocation",
    "dilution_risk_score": "dilution_risk",
    "filing_risk_score": "filing_risk",
}

_METRIC_FIELD_DEFINITIONS: dict[str, dict[str, Any]] = {
    "revenue_growth": {
        "label": "Revenue growth",
        "description": "Minimum latest persisted revenue growth from the SEC-first derived metrics mart.",
        "comparator": "min",
        "source_kind": "derived_metric",
        "source_key": "revenue_growth",
        "metric_key": "revenue_growth",
        "unit": "ratio",
        "is_proxy": True,
        "notes": ["Uses the latest persisted row for the requested cadence."],
    },
    "operating_margin": {
        "label": "Operating margin",
        "description": "Minimum operating income to revenue ratio from persisted normalized metrics.",
        "comparator": "min",
        "source_kind": "derived_metric",
        "source_key": "operating_margin",
        "metric_key": "operating_margin",
        "unit": "ratio",
        "is_proxy": False,
        "notes": [],
    },
    "fcf_margin": {
        "label": "FCF margin",
        "description": "Minimum free cash flow to revenue ratio from persisted normalized metrics.",
        "comparator": "min",
        "source_kind": "derived_metric",
        "source_key": "fcf_margin",
        "metric_key": "fcf_margin",
        "unit": "ratio",
        "is_proxy": False,
        "notes": [],
    },
    "leverage_ratio": {
        "label": "Leverage",
        "description": "Maximum debt-to-equity ratio from the persisted derived metrics mart.",
        "comparator": "max",
        "source_kind": "derived_metric",
        "source_key": "debt_to_equity",
        "metric_key": "debt_to_equity",
        "unit": "ratio",
        "is_proxy": False,
        "notes": ["v1 maps leverage to debt_to_equity for a single consistent cross-sectional proxy."],
    },
    "dilution": {
        "label": "Dilution",
        "description": "Maximum latest dilution trend from persisted share-count metrics.",
        "comparator": "max",
        "source_kind": "derived_metric",
        "source_key": "dilution_trend",
        "metric_key": "dilution_trend",
        "unit": "ratio",
        "is_proxy": True,
        "notes": ["Maps to the latest dilution_trend row from the derived metrics mart."],
    },
    "sbc_burden": {
        "label": "SBC burden",
        "description": "Maximum stock-based compensation as a share of revenue.",
        "comparator": "max",
        "source_kind": "derived_metric",
        "source_key": "sbc_to_revenue",
        "metric_key": "sbc_to_revenue",
        "unit": "ratio",
        "is_proxy": False,
        "notes": [],
    },
    "shareholder_yield": {
        "label": "Shareholder yield",
        "description": "Minimum official-only capital-allocation proxy for shareholder yield.",
        "comparator": "min",
        "source_kind": "model_result",
        "source_key": "capital_allocation.shareholder_yield",
        "metric_key": None,
        "unit": "ratio",
        "is_proxy": True,
        "notes": [
            "Uses the persisted capital_allocation model output instead of the price-backed derived_metrics shareholder_yield field.",
            "The model stays official-only by using SEC-native payout inputs and its own market-cap proxy.",
        ],
    },
    "filing_lag_days": {
        "label": "Filing lag",
        "description": "Maximum filing lag for the latest screened period.",
        "comparator": "max",
        "source_kind": "derived_metric",
        "source_key": "filing_lag_days",
        "metric_key": "filing_lag_days",
        "unit": "days",
        "is_proxy": True,
        "notes": ["Can fall back to last_updated when a direct filing_date is unavailable."],
    },
    "stale_period_flag": {
        "label": "Stale period flag",
        "description": "Internal filing-quality marker for rows whose latest screened period is stale.",
        "comparator": "boolean",
        "source_kind": "derived_metric",
        "source_key": "stale_period_flag",
        "metric_key": "stale_period_flag",
        "unit": "flag",
        "is_proxy": True,
        "notes": [],
    },
    "restatement_flag": {
        "label": "Latest-period restatement flag",
        "description": "Internal filing-quality marker for the latest screened period restatement signal.",
        "comparator": "boolean",
        "source_kind": "derived_metric",
        "source_key": "restatement_flag",
        "metric_key": "restatement_flag",
        "unit": "flag",
        "is_proxy": True,
        "notes": [],
    },
    "exclude_restatements": {
        "label": "Exclude restatements",
        "description": "Exclude companies with persisted financial_restatement history or a latest-period restatement flag.",
        "comparator": "boolean",
        "source_kind": "restatement_record",
        "source_key": "financial_restatements.count|restatement_flag",
        "metric_key": None,
        "unit": None,
        "is_proxy": False,
        "notes": [],
    },
    "exclude_stale_periods": {
        "label": "Exclude stale periods",
        "description": "Exclude rows whose latest screened period crosses the stale-period threshold in the metrics mart.",
        "comparator": "boolean",
        "source_kind": "derived_metric",
        "source_key": "stale_period_flag",
        "metric_key": None,
        "unit": "flag",
        "is_proxy": True,
        "notes": [],
    },
    "excluded_quality_flags": {
        "label": "Exclude quality flags",
        "description": "Drop results when any selected filing-quality flag is present on the latest screened row.",
        "comparator": "exclude_any",
        "source_kind": "quality_flag",
        "source_key": "filing_quality.aggregated_quality_flags",
        "metric_key": None,
        "unit": None,
        "is_proxy": False,
        "notes": ["Quality flags are aggregated from the latest screener metrics, the official shareholder-yield proxy, and persisted restatement history."],
        "suggested_values": list(SUPPORTED_QUALITY_FLAG_OPTIONS),
    },
}

_PUBLIC_METRIC_ORDER = (
    "revenue_growth",
    "operating_margin",
    "fcf_margin",
    "leverage_ratio",
    "dilution",
    "sbc_burden",
    "shareholder_yield",
)
_PUBLIC_FILING_QUALITY_ORDER = (
    "filing_lag_days",
    "stale_period_flag",
    "restatement_flag",
)
_METRIC_KEY_TO_PUBLIC_FIELD = {
    definition["metric_key"]: field_name
    for field_name, definition in _METRIC_FIELD_DEFINITIONS.items()
    if definition.get("metric_key")
}
_RANKING_DEFINITIONS: dict[str, dict[str, Any]] = {
    "quality": {
        "label": "Quality",
        "description": "Business quality ranking from growth, margin, cash-generation, and leverage proxies.",
        "score_directionality": "higher_is_better",
        "notes": [
            "Designed to prefer issuers with stronger growth, durable profitability, and manageable leverage from official fundamentals only.",
        ],
        "components": (
            {
                "component_key": "revenue_growth",
                "label": "Revenue growth",
                "source_section": "metrics",
                "field": "revenue_growth",
                "source_key": "revenue_growth",
                "unit": "ratio",
                "weight": 0.30,
                "directionality": "higher_increases_score",
                "notes": ["Latest requested-cadence growth proxy from the derived metrics mart."],
            },
            {
                "component_key": "operating_margin",
                "label": "Operating margin",
                "source_section": "metrics",
                "field": "operating_margin",
                "source_key": "operating_margin",
                "unit": "ratio",
                "weight": 0.30,
                "directionality": "higher_increases_score",
                "notes": ["Latest requested-cadence operating margin from persisted normalized metrics."],
            },
            {
                "component_key": "fcf_margin",
                "label": "FCF margin",
                "source_section": "metrics",
                "field": "fcf_margin",
                "source_key": "fcf_margin",
                "unit": "ratio",
                "weight": 0.25,
                "directionality": "higher_increases_score",
                "notes": ["Latest requested-cadence free-cash-flow margin from persisted normalized metrics."],
            },
            {
                "component_key": "leverage_ratio",
                "label": "Leverage",
                "source_section": "metrics",
                "field": "leverage_ratio",
                "source_key": "debt_to_equity",
                "unit": "ratio",
                "weight": 0.15,
                "directionality": "lower_increases_score",
                "notes": ["Mapped to debt_to_equity in v1 for a consistent cross-sectional leverage proxy."],
            },
        ),
    },
    "value": {
        "label": "Value",
        "description": "Official-only value ranking from payout yield, cash profitability, and leverage proxies.",
        "score_directionality": "higher_is_better",
        "notes": [
            "This is intentionally price-free in v2 of the screener backend because no official end-of-day equity price feed exists.",
            "The score emphasizes the official shareholder-yield proxy instead of market multiple signals.",
        ],
        "components": (
            {
                "component_key": "shareholder_yield",
                "label": "Shareholder yield",
                "source_section": "metrics",
                "field": "shareholder_yield",
                "source_key": "capital_allocation.shareholder_yield",
                "unit": "ratio",
                "weight": 0.40,
                "directionality": "higher_increases_score",
                "notes": ["Official-only capital-allocation proxy; no Yahoo-backed market cap input is used."],
            },
            {
                "component_key": "fcf_margin",
                "label": "FCF margin",
                "source_section": "metrics",
                "field": "fcf_margin",
                "source_key": "fcf_margin",
                "unit": "ratio",
                "weight": 0.25,
                "directionality": "higher_increases_score",
                "notes": ["Cash profitability proxy used to anchor value without market multiples."],
            },
            {
                "component_key": "operating_margin",
                "label": "Operating margin",
                "source_section": "metrics",
                "field": "operating_margin",
                "source_key": "operating_margin",
                "unit": "ratio",
                "weight": 0.15,
                "directionality": "higher_increases_score",
                "notes": ["Durable operating profitability supports the value read-through."],
            },
            {
                "component_key": "leverage_ratio",
                "label": "Leverage",
                "source_section": "metrics",
                "field": "leverage_ratio",
                "source_key": "debt_to_equity",
                "unit": "ratio",
                "weight": 0.20,
                "directionality": "lower_increases_score",
                "notes": ["Lower leverage improves the quality of the official-only value proxy."],
            },
        ),
    },
    "capital_allocation": {
        "label": "Capital Allocation",
        "description": "Capital-allocation ranking from payout yield, dilution pressure, and SBC burden.",
        "score_directionality": "higher_is_better",
        "notes": [
            "This score focuses on whether shareholder returns appear to outweigh dilution and SBC drag.",
        ],
        "components": (
            {
                "component_key": "shareholder_yield",
                "label": "Shareholder yield",
                "source_section": "metrics",
                "field": "shareholder_yield",
                "source_key": "capital_allocation.shareholder_yield",
                "unit": "ratio",
                "weight": 0.45,
                "directionality": "higher_increases_score",
                "notes": ["Official-only capital-allocation proxy from the persisted model cache."],
            },
            {
                "component_key": "dilution",
                "label": "Dilution",
                "source_section": "metrics",
                "field": "dilution",
                "source_key": "dilution_trend",
                "unit": "ratio",
                "weight": 0.30,
                "directionality": "lower_increases_score",
                "notes": ["Lower dilution improves capital-allocation quality."],
            },
            {
                "component_key": "sbc_burden",
                "label": "SBC burden",
                "source_section": "metrics",
                "field": "sbc_burden",
                "source_key": "sbc_to_revenue",
                "unit": "ratio",
                "weight": 0.25,
                "directionality": "lower_increases_score",
                "notes": ["Lower stock-based compensation burden improves the capital-allocation read."],
            },
        ),
    },
    "dilution_risk": {
        "label": "Dilution Risk",
        "description": "Risk ranking for dilution pressure from share issuance, SBC burden, and weak payout offset.",
        "score_directionality": "higher_is_worse",
        "notes": [
            "Higher scores mean higher dilution risk, not higher quality.",
        ],
        "components": (
            {
                "component_key": "dilution",
                "label": "Dilution",
                "source_section": "metrics",
                "field": "dilution",
                "source_key": "dilution_trend",
                "unit": "ratio",
                "weight": 0.50,
                "directionality": "higher_increases_score",
                "notes": ["Higher dilution increases the risk score."],
            },
            {
                "component_key": "sbc_burden",
                "label": "SBC burden",
                "source_section": "metrics",
                "field": "sbc_burden",
                "source_key": "sbc_to_revenue",
                "unit": "ratio",
                "weight": 0.35,
                "directionality": "higher_increases_score",
                "notes": ["Higher SBC burden increases dilution risk."],
            },
            {
                "component_key": "shareholder_yield",
                "label": "Shareholder yield",
                "source_section": "metrics",
                "field": "shareholder_yield",
                "source_key": "capital_allocation.shareholder_yield",
                "unit": "ratio",
                "weight": 0.15,
                "directionality": "lower_increases_score",
                "notes": ["Weak payout offset increases dilution-risk pressure."],
            },
        ),
    },
    "filing_risk": {
        "label": "Filing Risk",
        "description": "Risk ranking for filing lag, stale periods, and restatement signals.",
        "score_directionality": "higher_is_worse",
        "notes": [
            "Higher scores mean higher filing and accounting risk.",
        ],
        "components": (
            {
                "component_key": "filing_lag_days",
                "label": "Filing lag days",
                "source_section": "filing_quality_snapshot",
                "field": "filing_lag_days",
                "source_key": "filing_lag_days",
                "unit": "days",
                "weight": 0.40,
                "directionality": "higher_increases_score",
                "notes": ["Higher lag increases filing risk."],
            },
            {
                "component_key": "stale_period_flag",
                "label": "Stale period flag",
                "source_section": "filing_quality_snapshot",
                "field": "stale_period_flag",
                "source_key": "stale_period_flag",
                "unit": "flag",
                "weight": 0.20,
                "directionality": "higher_increases_score",
                "notes": ["Stale periods increase filing risk."],
            },
            {
                "component_key": "restatement_flag",
                "label": "Latest-period restatement flag",
                "source_section": "filing_quality_snapshot",
                "field": "restatement_flag",
                "source_key": "restatement_flag",
                "unit": "flag",
                "weight": 0.20,
                "directionality": "higher_increases_score",
                "notes": ["A latest-period restatement signal increases filing risk."],
            },
            {
                "component_key": "restatement_count",
                "label": "Persisted restatement count",
                "source_section": "filing_quality_scalar",
                "field": "restatement_count",
                "source_key": "financial_restatements.count",
                "unit": "count",
                "weight": 0.20,
                "directionality": "higher_increases_score",
                "notes": ["More persisted restatement history increases filing risk."],
            },
        ),
    },
}


def build_official_screener_filter_catalog() -> dict[str, Any]:
    return {
        "strict_official_only": True,
        "default_period_type": DEFAULT_PERIOD_TYPE,
        "period_types": list(SUPPORTED_PERIOD_TYPES),
        "default_sort": {
            "field": DEFAULT_SORT_FIELD,
            "direction": DEFAULT_SORT_DIRECTION,
        },
        "filters": [
            {
                "field": field_name,
                "label": definition["label"],
                "description": definition["description"],
                "comparator": definition["comparator"],
                "source_kind": definition["source_kind"],
                "source_key": definition["source_key"],
                "unit": definition["unit"],
                "official_only": True,
                "notes": list(definition.get("notes") or []),
                "suggested_values": list(definition.get("suggested_values") or []),
            }
            for field_name, definition in _METRIC_FIELD_DEFINITIONS.items()
            if field_name not in {"stale_period_flag", "restatement_flag"}
        ],
        "rankings": _build_ranking_catalog_payload(),
        "notes": [
            "This screener is always official-source-only and never depends on Yahoo Finance, even when the workspace is not in STRICT_OFFICIAL_MODE.",
            "Cross-sectional rows use each company's latest persisted period for the requested cadence instead of a request-path live fetch.",
            "shareholder_yield is backed by the persisted capital_allocation model's official proxy rather than the price-backed derived_metrics field.",
            "exclude_restatements uses persisted financial_restatements history, while restatement_flag in each row reflects the latest screened period only.",
            "Ranking outputs are cross-sectional and pre-filter: component percentiles are blended before the threshold filters are applied.",
        ],
        "source_hints": {
            "statement_sources": [
                "sec_companyfacts",
                "sec_edgar",
                "fdic_bankfind_financials",
                "federal_reserve_fr_y9c",
            ],
            "uses_metrics": True,
            "uses_shareholder_yield_model": True,
        },
        "confidence_flags": ["official_source_only"],
    }


def _build_ranking_catalog_payload() -> list[dict[str, Any]]:
    return [
        {
            "score_key": score_key,
            "label": definition["label"],
            "description": definition["description"],
            "score_directionality": definition["score_directionality"],
            "universe_basis": _RANKING_UNIVERSE_BASIS,
            "method_summary": _RANKING_METHOD_SUMMARY,
            "components": [
                {
                    "component_key": component["component_key"],
                    "label": component["label"],
                    "source_key": component["source_key"],
                    "unit": component["unit"],
                    "weight": component["weight"],
                    "directionality": component["directionality"],
                    "notes": list(component.get("notes") or []),
                }
                for component in definition["components"]
            ],
            "confidence_notes_policy": list(_RANKING_CONFIDENCE_POLICY),
            "notes": list(definition.get("notes") or []),
        }
        for score_key in _RANKING_ORDER
        for definition in [_RANKING_DEFINITIONS[score_key]]
    ]


def run_official_screener(session: Session, request_payload: dict[str, Any]) -> dict[str, Any]:
    period_type = str(request_payload.get("period_type") or DEFAULT_PERIOD_TYPE)
    if period_type not in SUPPORTED_PERIOD_TYPES:
        period_type = DEFAULT_PERIOD_TYPE

    ticker_universe = [
        str(value).strip().upper()
        for value in request_payload.get("ticker_universe") or []
        if str(value).strip()
    ]
    filters = dict(request_payload.get("filters") or {})
    sort_payload = dict(request_payload.get("sort") or {})
    sort_field = str(sort_payload.get("field") or DEFAULT_SORT_FIELD)
    if sort_field not in {
        "ticker",
        "period_end",
        "revenue_growth",
        "operating_margin",
        "fcf_margin",
        "leverage_ratio",
        "dilution",
        "sbc_burden",
        "shareholder_yield",
        "filing_lag_days",
        "restatement_count",
        *tuple(_SORTABLE_RANKING_FIELDS),
    }:
        sort_field = DEFAULT_SORT_FIELD
    sort_direction = str(sort_payload.get("direction") or DEFAULT_SORT_DIRECTION).lower()
    if sort_direction not in {"asc", "desc"}:
        sort_direction = DEFAULT_SORT_DIRECTION

    limit = max(1, min(int(request_payload.get("limit") or 50), 200))
    offset = max(0, int(request_payload.get("offset") or 0))

    candidates = _load_official_screener_candidates(
        session,
        period_type=period_type,
        ticker_universe=ticker_universe,
    )
    _attach_explainable_rankings(candidates)
    matched_candidates = [candidate for candidate in candidates if _candidate_matches_filters(candidate, filters)]
    ordered_candidates = _sort_candidates(matched_candidates, field=sort_field, direction=sort_direction)
    page = ordered_candidates[offset : offset + limit]

    summary_source = matched_candidates or candidates
    statement_sources = sorted(
        {
            str(source_hint)
            for candidate in candidates
            for source_hint in candidate.get("statement_sources") or []
            if str(source_hint).strip()
        }
    )
    last_refreshed_at = _latest_datetime(
        *[
            _latest_datetime(candidate.get("last_metrics_check"), candidate.get("last_model_check"))
            for candidate in summary_source
        ]
    )
    confidence_flags = ["official_source_only"]
    if not candidates:
        confidence_flags.append("screener_universe_empty")
    if any(str((candidate.get("company") or {}).get("cache_state") or "") == "stale" for candidate in candidates):
        confidence_flags.append("stale_metrics_present")
    if any(_shareholder_yield_value(candidate) is None for candidate in candidates):
        confidence_flags.append("partial_shareholder_yield_coverage")
    if any(_candidate_is_restatement_flagged(candidate) for candidate in candidates):
        confidence_flags.append("restatement_flags_present")

    return {
        "query": {
            "period_type": period_type,
            "ticker_universe": ticker_universe,
            "filters": {
                "revenue_growth_min": filters.get("revenue_growth_min"),
                "operating_margin_min": filters.get("operating_margin_min"),
                "fcf_margin_min": filters.get("fcf_margin_min"),
                "leverage_ratio_max": filters.get("leverage_ratio_max"),
                "dilution_max": filters.get("dilution_max"),
                "sbc_burden_max": filters.get("sbc_burden_max"),
                "shareholder_yield_min": filters.get("shareholder_yield_min"),
                "max_filing_lag_days": filters.get("max_filing_lag_days"),
                "exclude_restatements": bool(filters.get("exclude_restatements")),
                "exclude_stale_periods": bool(filters.get("exclude_stale_periods")),
                "excluded_quality_flags": _normalized_flag_list(filters.get("excluded_quality_flags") or []),
            },
            "sort": {
                "field": sort_field,
                "direction": sort_direction,
            },
            "limit": limit,
            "offset": offset,
            "strict_official_only": True,
        },
        "coverage": {
            "candidate_count": len(candidates),
            "matched_count": len(matched_candidates),
            "returned_count": len(page),
            "fresh_count": sum(1 for candidate in candidates if str((candidate.get("company") or {}).get("cache_state") or "") == "fresh"),
            "stale_count": sum(1 for candidate in candidates if str((candidate.get("company") or {}).get("cache_state") or "") == "stale"),
            "missing_shareholder_yield_count": sum(1 for candidate in candidates if _shareholder_yield_value(candidate) is None),
            "restatement_flagged_count": sum(1 for candidate in candidates if _candidate_is_restatement_flagged(candidate)),
            "stale_period_flagged_count": sum(1 for candidate in candidates if _candidate_is_stale_period(candidate)),
        },
        "results": [_candidate_for_response(candidate) for candidate in page],
        "as_of": _latest_date(*[candidate.get("period_end") for candidate in summary_source]),
        "last_refreshed_at": last_refreshed_at,
        "source_hints": {
            "statement_sources": statement_sources,
            "uses_metrics": bool(candidates),
            "uses_shareholder_yield_model": any(candidate.get("last_model_check") is not None for candidate in candidates),
        },
        "confidence_flags": sorted(set(confidence_flags)),
    }


def _load_official_screener_candidates(
    session: Session,
    *,
    period_type: str,
    ticker_universe: list[str],
) -> list[dict[str, Any]]:
    latest_periods = select(
        DerivedMetricPoint.company_id.label("company_id"),
        func.max(DerivedMetricPoint.period_end).label("period_end"),
    ).where(DerivedMetricPoint.period_type == period_type)
    if ticker_universe:
        latest_periods = latest_periods.join(Company, Company.id == DerivedMetricPoint.company_id).where(Company.ticker.in_(ticker_universe))
    latest_periods = latest_periods.group_by(DerivedMetricPoint.company_id).subquery()

    metric_statement = (
        select(Company, DerivedMetricPoint)
        .join(latest_periods, latest_periods.c.company_id == Company.id)
        .join(
            DerivedMetricPoint,
            (DerivedMetricPoint.company_id == Company.id)
            & (DerivedMetricPoint.period_end == latest_periods.c.period_end)
            & (DerivedMetricPoint.period_type == period_type),
        )
        .where(DerivedMetricPoint.metric_key.in_(tuple(_METRIC_KEY_TO_PUBLIC_FIELD)))
        .order_by(Company.ticker.asc(), DerivedMetricPoint.metric_key.asc())
    )
    metric_rows = session.execute(metric_statement).all()
    if not metric_rows:
        return []

    candidates: dict[int, dict[str, Any]] = {}
    for company, metric in metric_rows:
        public_field = _METRIC_KEY_TO_PUBLIC_FIELD.get(metric.metric_key)
        if public_field is None:
            continue
        candidate = candidates.setdefault(
            company.id,
            {
                "company": {
                    "ticker": company.ticker,
                    "cik": company.cik,
                    "name": company.name,
                    "sector": company.sector,
                    "market_sector": company.market_sector,
                    "market_industry": company.market_industry,
                    "cache_state": "missing",
                },
                "period_type": period_type,
                "period_end": metric.period_end,
                "filing_type": metric.filing_type,
                "last_metrics_check": None,
                "last_model_check": None,
                "metrics": {
                    field_name: _empty_metric_snapshot(field_name)
                    for field_name in _PUBLIC_METRIC_ORDER
                },
                "filing_quality": {
                    field_name: _empty_metric_snapshot(field_name)
                    for field_name in _PUBLIC_FILING_QUALITY_ORDER
                },
                "statement_sources": [],
            },
        )

        snapshot = _metric_snapshot_from_row(metric, public_field)
        if public_field in candidate["metrics"]:
            candidate["metrics"][public_field] = snapshot
        else:
            candidate["filing_quality"][public_field] = snapshot
        candidate["last_metrics_check"] = _latest_datetime(candidate.get("last_metrics_check"), getattr(metric, "last_checked", None))
        candidate["company"]["cache_state"] = _cache_state_from_last_checked(candidate.get("last_metrics_check"))
        provenance = getattr(metric, "provenance", None)
        statement_source = str((provenance or {}).get("statement_source") or "").strip() if isinstance(provenance, dict) else ""
        if statement_source and statement_source not in candidate["statement_sources"]:
            candidate["statement_sources"].append(statement_source)

    company_ids = sorted(candidates)
    latest_models = _load_latest_capital_allocation_models(session, company_ids)
    restatement_summaries = _load_restatement_summaries(session, company_ids)

    for company_id, candidate in candidates.items():
        model_run = latest_models.get(company_id)
        if model_run is not None:
            candidate["metrics"]["shareholder_yield"] = _shareholder_yield_snapshot_from_model(model_run)
            candidate["last_model_check"] = getattr(model_run, "created_at", None)
        summary = restatement_summaries.get(company_id)
        filing_quality = candidate["filing_quality"]
        filing_quality["restatement_count"] = int(summary.get("restatement_count") or 0) if summary is not None else 0
        filing_quality["latest_restatement_filing_date"] = summary.get("latest_restatement_filing_date") if summary is not None else None
        filing_quality["latest_restatement_period_end"] = summary.get("latest_restatement_period_end") if summary is not None else None
        aggregated_quality_flags = {
            flag
            for snapshot in (*candidate["metrics"].values(), *[filing_quality[key] for key in _PUBLIC_FILING_QUALITY_ORDER])
            for flag in snapshot.get("quality_flags") or []
            if flag
        }
        if filing_quality["restatement_count"] > 0:
            aggregated_quality_flags.add("historical_restatement_present")
        if str(candidate["company"].get("cache_state") or "") == "stale":
            aggregated_quality_flags.add("metrics_cache_stale")
        filing_quality["aggregated_quality_flags"] = sorted(aggregated_quality_flags)

    return [candidates[company_id] for company_id in sorted(candidates, key=lambda item: candidates[item]["company"]["ticker"])]


def _load_latest_capital_allocation_models(session: Session, company_ids: list[int]) -> dict[int, ModelRun]:
    if not company_ids:
        return {}

    ranked = (
        select(
            ModelRun.id.label("id"),
            ModelRun.company_id.label("company_id"),
            func.row_number().over(
                partition_by=ModelRun.company_id,
                order_by=(ModelRun.created_at.desc(), ModelRun.id.desc()),
            ).label("rn"),
        )
        .where(
            ModelRun.company_id.in_(company_ids),
            func.lower(ModelRun.model_name) == "capital_allocation",
        )
        .subquery()
    )
    statement = select(ModelRun).join(ranked, ranked.c.id == ModelRun.id).where(ranked.c.rn == 1)
    return {model_run.company_id: model_run for model_run in session.execute(statement).scalars()}


def _load_restatement_summaries(session: Session, company_ids: list[int]) -> dict[int, dict[str, Any]]:
    if not company_ids:
        return {}

    statement = (
        select(
            FinancialRestatement.company_id.label("company_id"),
            func.count(FinancialRestatement.id).label("restatement_count"),
            func.max(FinancialRestatement.filing_date).label("latest_restatement_filing_date"),
            func.max(FinancialRestatement.period_end).label("latest_restatement_period_end"),
        )
        .where(FinancialRestatement.company_id.in_(company_ids))
        .group_by(FinancialRestatement.company_id)
    )
    return {
        int(company_id): {
            "restatement_count": int(restatement_count or 0),
            "latest_restatement_filing_date": latest_restatement_filing_date,
            "latest_restatement_period_end": latest_restatement_period_end,
        }
        for company_id, restatement_count, latest_restatement_filing_date, latest_restatement_period_end in session.execute(statement).all()
    }


def _metric_snapshot_from_row(metric: DerivedMetricPoint, public_field: str) -> dict[str, Any]:
    definition = _METRIC_FIELD_DEFINITIONS[public_field]
    provenance = getattr(metric, "provenance", None)
    unit = definition["unit"]
    if isinstance(provenance, dict) and provenance.get("unit"):
        unit = str(provenance.get("unit"))
    return {
        "value": getattr(metric, "metric_value", None),
        "unit": unit,
        "is_proxy": bool(getattr(metric, "is_proxy", False) or definition["is_proxy"]),
        "source_key": definition["source_key"],
        "quality_flags": list(getattr(metric, "quality_flags", None) or []),
    }


def _shareholder_yield_snapshot_from_model(model_run: ModelRun) -> dict[str, Any]:
    result = dict(getattr(model_run, "result", None) or {})
    status_value = normalize_model_status(str(result.get("model_status") or result.get("status") or ""))
    quality_flags: list[str] = []
    if status_value and status_value != "supported":
        quality_flags.append(f"capital_allocation_{status_value}")
    for missing_field in result.get("missing_required_fields_last_3y") or []:
        field_name = str(missing_field).strip()
        if field_name:
            quality_flags.append(f"capital_allocation_missing_{field_name}")

    value = _coerce_number(result.get("shareholder_yield"))
    if value is None:
        quality_flags.append("shareholder_yield_unavailable")
    return {
        "value": value,
        "unit": "ratio",
        "is_proxy": True,
        "source_key": "capital_allocation.shareholder_yield",
        "quality_flags": sorted(set(quality_flags)),
    }


def _empty_metric_snapshot(public_field: str) -> dict[str, Any]:
    definition = _METRIC_FIELD_DEFINITIONS[public_field]
    return {
        "value": None,
        "unit": definition["unit"] or "flag",
        "is_proxy": bool(definition["is_proxy"]),
        "source_key": definition["source_key"],
        "quality_flags": [],
    }


def _candidate_matches_filters(candidate: dict[str, Any], filters: dict[str, Any]) -> bool:
    if not _meets_minimum(candidate, "revenue_growth", filters.get("revenue_growth_min")):
        return False
    if not _meets_minimum(candidate, "operating_margin", filters.get("operating_margin_min")):
        return False
    if not _meets_minimum(candidate, "fcf_margin", filters.get("fcf_margin_min")):
        return False
    if not _meets_maximum(candidate, "leverage_ratio", filters.get("leverage_ratio_max")):
        return False
    if not _meets_maximum(candidate, "dilution", filters.get("dilution_max")):
        return False
    if not _meets_maximum(candidate, "sbc_burden", filters.get("sbc_burden_max")):
        return False
    if not _meets_minimum(candidate, "shareholder_yield", filters.get("shareholder_yield_min")):
        return False
    if not _meets_maximum(candidate, "filing_lag_days", filters.get("max_filing_lag_days")):
        return False
    if bool(filters.get("exclude_restatements")) and _candidate_is_restatement_flagged(candidate):
        return False
    if bool(filters.get("exclude_stale_periods")) and _candidate_is_stale_period(candidate):
        return False
    excluded_quality_flags = set(_normalized_flag_list(filters.get("excluded_quality_flags") or []))
    if excluded_quality_flags and excluded_quality_flags.intersection(candidate.get("filing_quality", {}).get("aggregated_quality_flags") or []):
        return False
    return True


def _sort_candidates(candidates: list[dict[str, Any]], *, field: str, direction: str) -> list[dict[str, Any]]:
    def _sort_value(candidate: dict[str, Any]) -> Any:
        if field == "ticker":
            return str((candidate.get("company") or {}).get("ticker") or "")
        if field == "period_end":
            return candidate.get("period_end")
        if field in _SORTABLE_RANKING_FIELDS:
            score_key = _SORTABLE_RANKING_FIELDS[field]
            return _coerce_number((candidate.get("rankings") or {}).get(score_key, {}).get("score"))
        if field == "restatement_count":
            return float((candidate.get("filing_quality") or {}).get("restatement_count") or 0)
        if field == "filing_lag_days":
            return (candidate.get("filing_quality") or {}).get("filing_lag_days", {}).get("value")
        return (candidate.get("metrics") or {}).get(field, {}).get("value")

    present = [candidate for candidate in candidates if _sort_value(candidate) is not None]
    missing = [candidate for candidate in candidates if _sort_value(candidate) is None]
    present.sort(key=_sort_value, reverse=(direction == "desc"))
    return present + missing


def _candidate_for_response(candidate: dict[str, Any]) -> dict[str, Any]:
    response = dict(candidate)
    response.pop("statement_sources", None)
    response["company"] = dict(candidate.get("company") or {})
    response["metrics"] = {key: dict(value) for key, value in (candidate.get("metrics") or {}).items()}
    response["filing_quality"] = {
        key: dict(value) if isinstance(value, dict) else value
        for key, value in (candidate.get("filing_quality") or {}).items()
    }
    response["rankings"] = {
        score_key: {
            **dict(ranking),
            "components": [dict(component) for component in ranking.get("components") or []],
        }
        for score_key, ranking in (candidate.get("rankings") or {}).items()
    }
    return response


def _attach_explainable_rankings(candidates: list[dict[str, Any]]) -> None:
    if not candidates:
        return

    for candidate in candidates:
        candidate["rankings"] = {}

    for score_key in _RANKING_ORDER:
        definition = _RANKING_DEFINITIONS[score_key]
        component_runtime: dict[str, dict[str, Any]] = {}
        for component in definition["components"]:
            runtime_rows: list[dict[str, Any]] = []
            raw_values: list[float] = []
            for candidate in candidates:
                runtime_row = _lookup_ranking_component_value(candidate, component)
                runtime_rows.append(runtime_row)
                value = _coerce_number(runtime_row.get("value"))
                if value is not None:
                    raw_values.append(value)
            component_runtime[component["component_key"]] = {
                "rows": runtime_rows,
                "values": raw_values,
            }

        ranking_payloads: list[dict[str, Any]] = []
        for index, candidate in enumerate(candidates):
            components: list[dict[str, Any]] = []
            for component in definition["components"]:
                component_key = component["component_key"]
                base_row = dict(component_runtime[component_key]["rows"][index])
                raw_values = component_runtime[component_key]["values"]
                value = _coerce_number(base_row.get("value"))
                base_row["component_score"] = _component_distribution_score(
                    value,
                    raw_values,
                    directionality=component["directionality"],
                )
                if value is not None:
                    unique_values = {item for item in raw_values}
                    if len(raw_values) <= 1 and "single_candidate_universe" not in base_row["confidence_notes"]:
                        base_row["confidence_notes"].append("single_candidate_universe")
                    elif len(unique_values) == 1 and "flat_cross_sectional_distribution" not in base_row["confidence_notes"]:
                        base_row["confidence_notes"].append("flat_cross_sectional_distribution")
                components.append(base_row)

            ranking_payload = _build_ranking_payload(candidate, score_key, definition, components, universe_size=len(candidates))
            candidate["rankings"][score_key] = ranking_payload
            ranking_payloads.append(ranking_payload)

        _apply_ranking_order(ranking_payloads)


def _build_ranking_payload(
    candidate: dict[str, Any],
    score_key: str,
    definition: dict[str, Any],
    components: list[dict[str, Any]],
    *,
    universe_size: int,
) -> dict[str, Any]:
    available_components = [component for component in components if component.get("component_score") is not None]
    confidence_notes: set[str] = set()
    missing_components = [component["component_key"] for component in components if component.get("component_score") is None]
    if missing_components:
        confidence_notes.add("missing_components_reweighted:" + ",".join(missing_components))
    if any(bool(component.get("is_proxy")) for component in available_components):
        confidence_notes.add("proxy_components_present")
    if str((candidate.get("company") or {}).get("cache_state") or "") == "stale":
        confidence_notes.add("metrics_cache_stale")
    for component in components:
        for note in component.get("confidence_notes") or []:
            if note:
                confidence_notes.add(str(note))

    if not available_components:
        confidence_notes.add("ranking_unavailable")
        score = None
    else:
        total_weight = sum(float(component["weight"]) for component in available_components)
        score = round(
            sum(float(component["component_score"]) * float(component["weight"]) for component in available_components) / total_weight,
            2,
        ) if total_weight > 0 else None

    return {
        "score_key": score_key,
        "label": definition["label"],
        "score": score,
        "rank": None,
        "percentile": None,
        "universe_size": universe_size,
        "universe_basis": _RANKING_UNIVERSE_BASIS,
        "score_directionality": definition["score_directionality"],
        "confidence_notes": sorted(confidence_notes),
        "components": components,
    }


def _apply_ranking_order(ranking_payloads: list[dict[str, Any]]) -> None:
    scores = [score for payload in ranking_payloads if (score := _coerce_number(payload.get("score"))) is not None]
    for payload in ranking_payloads:
        score = _coerce_number(payload.get("score"))
        if score is None:
            payload["rank"] = None
            payload["percentile"] = None
            continue
        payload["rank"] = 1 + sum(other_score > score for other_score in scores)
        percentile = _distribution_percentile(score, scores)
        payload["percentile"] = round(percentile * 100.0, 2) if percentile is not None else None


def _lookup_ranking_component_value(candidate: dict[str, Any], component: dict[str, Any]) -> dict[str, Any]:
    source_section = component["source_section"]
    field = component["field"]
    confidence_notes: list[str] = []
    is_proxy = False
    quality_flags: list[str] = []

    if source_section == "metrics":
        snapshot = dict((candidate.get("metrics") or {}).get(field) or {})
        value = _coerce_number(snapshot.get("value"))
        unit = str(snapshot.get("unit") or component["unit"])
        source_key = str(snapshot.get("source_key") or component["source_key"])
        is_proxy = bool(snapshot.get("is_proxy"))
        quality_flags = [str(flag) for flag in snapshot.get("quality_flags") or [] if str(flag).strip()]
    elif source_section == "filing_quality_snapshot":
        snapshot = dict((candidate.get("filing_quality") or {}).get(field) or {})
        value = _coerce_number(snapshot.get("value"))
        unit = str(snapshot.get("unit") or component["unit"])
        source_key = str(snapshot.get("source_key") or component["source_key"])
        is_proxy = bool(snapshot.get("is_proxy"))
        quality_flags = [str(flag) for flag in snapshot.get("quality_flags") or [] if str(flag).strip()]
    else:
        value = _coerce_number((candidate.get("filing_quality") or {}).get(field))
        unit = str(component["unit"])
        source_key = str(component["source_key"])

    if value is None:
        confidence_notes.append("component_unavailable")
    if is_proxy:
        confidence_notes.append("proxy_component")
    confidence_notes.extend(f"quality_flag:{flag}" for flag in quality_flags)

    return {
        "component_key": component["component_key"],
        "label": component["label"],
        "source_key": source_key,
        "value": value,
        "unit": unit,
        "weight": float(component["weight"]),
        "directionality": component["directionality"],
        "component_score": None,
        "is_proxy": is_proxy,
        "confidence_notes": _normalized_flag_list(confidence_notes),
    }


def _component_distribution_score(
    value: float | None,
    raw_values: list[float],
    *,
    directionality: str,
) -> float | None:
    percentile = _distribution_percentile(value, raw_values)
    if percentile is None:
        return None
    if directionality == "lower_increases_score":
        percentile = 1.0 - percentile
    return round(percentile * 100.0, 2)


def _distribution_percentile(value: float | None, raw_values: list[float]) -> float | None:
    if value is None or not raw_values:
        return None
    unique_values = {item for item in raw_values}
    if len(raw_values) <= 1 or len(unique_values) == 1:
        return 0.5
    lower_count = sum(1 for item in raw_values if item < value)
    equal_count = sum(1 for item in raw_values if item == value)
    return (lower_count + (0.5 * max(equal_count - 1, 0))) / max(len(raw_values) - 1, 1)


def _shareholder_yield_value(candidate: dict[str, Any]) -> float | None:
    return _coerce_number((candidate.get("metrics") or {}).get("shareholder_yield", {}).get("value"))


def _candidate_is_restatement_flagged(candidate: dict[str, Any]) -> bool:
    restatement_count = int((candidate.get("filing_quality") or {}).get("restatement_count") or 0)
    latest_period_flag = _coerce_number((candidate.get("filing_quality") or {}).get("restatement_flag", {}).get("value")) or 0.0
    return restatement_count > 0 or latest_period_flag > 0


def _candidate_is_stale_period(candidate: dict[str, Any]) -> bool:
    stale_period_flag = _coerce_number((candidate.get("filing_quality") or {}).get("stale_period_flag", {}).get("value")) or 0.0
    return stale_period_flag > 0


def _meets_minimum(candidate: dict[str, Any], field: str, threshold: Any) -> bool:
    minimum = _coerce_number(threshold)
    if minimum is None:
        return True
    value = _lookup_field_value(candidate, field)
    return value is not None and value >= minimum


def _meets_maximum(candidate: dict[str, Any], field: str, threshold: Any) -> bool:
    maximum = _coerce_number(threshold)
    if maximum is None:
        return True
    value = _lookup_field_value(candidate, field)
    return value is not None and value <= maximum


def _lookup_field_value(candidate: dict[str, Any], field: str) -> float | None:
    if field == "filing_lag_days":
        return _coerce_number((candidate.get("filing_quality") or {}).get("filing_lag_days", {}).get("value"))
    return _coerce_number((candidate.get("metrics") or {}).get(field, {}).get("value"))


def _cache_state_from_last_checked(last_checked: datetime | None) -> str:
    normalized_last_checked = _normalize_datetime(last_checked)
    if normalized_last_checked is None:
        return "missing"
    freshness_cutoff = datetime.now(timezone.utc) - timedelta(hours=settings.freshness_window_hours)
    return "stale" if normalized_last_checked < freshness_cutoff else "fresh"


def _normalized_flag_list(values: Iterable[Any]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _latest_datetime(*values: datetime | None) -> datetime | None:
    normalized = [_normalize_datetime(value) for value in values if value is not None]
    return max(normalized) if normalized else None


def _latest_date(*values: date | None) -> date | None:
    normalized = [value for value in values if isinstance(value, date)]
    return max(normalized) if normalized else None


def _coerce_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None