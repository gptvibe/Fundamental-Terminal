from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

import app.main as main_module
from app.db import get_db_session
from app.main import app


def _ranking_component(
    component_key: str,
    *,
    label: str,
    source_key: str,
    value: float | int | None,
    unit: str,
    weight: float,
    directionality: str,
    component_score: float | None,
) -> dict[str, object]:
    return {
        "component_key": component_key,
        "label": label,
        "source_key": source_key,
        "value": value,
        "unit": unit,
        "weight": weight,
        "directionality": directionality,
        "component_score": component_score,
        "is_proxy": False,
        "confidence_notes": [],
    }


def _ranking_payload(
    score_key: str,
    *,
    label: str,
    score: float,
    rank: int,
    percentile: float,
    score_directionality: str,
    components: list[dict[str, object]],
) -> dict[str, object]:
    return {
        "score_key": score_key,
        "label": label,
        "score": score,
        "rank": rank,
        "percentile": percentile,
        "universe_size": 2,
        "universe_basis": "candidate_universe_pre_filter",
        "score_directionality": score_directionality,
        "confidence_notes": [],
        "components": components,
    }


def _rankings_payload() -> dict[str, object]:
    return {
        "quality": _ranking_payload(
            "quality",
            label="Quality",
            score=82.0,
            rank=1,
            percentile=100.0,
            score_directionality="higher_is_better",
            components=[
                _ranking_component(
                    "revenue_growth",
                    label="Revenue growth",
                    source_key="revenue_growth",
                    value=0.18,
                    unit="ratio",
                    weight=0.3,
                    directionality="higher_increases_score",
                    component_score=85.0,
                )
            ],
        ),
        "value": _ranking_payload(
            "value",
            label="Value",
            score=74.0,
            rank=1,
            percentile=100.0,
            score_directionality="higher_is_better",
            components=[
                _ranking_component(
                    "shareholder_yield",
                    label="Shareholder yield",
                    source_key="capital_allocation.shareholder_yield",
                    value=0.06,
                    unit="ratio",
                    weight=0.4,
                    directionality="higher_increases_score",
                    component_score=80.0,
                )
            ],
        ),
        "capital_allocation": _ranking_payload(
            "capital_allocation",
            label="Capital Allocation",
            score=79.0,
            rank=1,
            percentile=100.0,
            score_directionality="higher_is_better",
            components=[
                _ranking_component(
                    "shareholder_yield",
                    label="Shareholder yield",
                    source_key="capital_allocation.shareholder_yield",
                    value=0.06,
                    unit="ratio",
                    weight=0.45,
                    directionality="higher_increases_score",
                    component_score=82.0,
                )
            ],
        ),
        "dilution_risk": _ranking_payload(
            "dilution_risk",
            label="Dilution Risk",
            score=19.0,
            rank=2,
            percentile=0.0,
            score_directionality="higher_is_worse",
            components=[
                _ranking_component(
                    "dilution",
                    label="Dilution",
                    source_key="dilution_trend",
                    value=-0.01,
                    unit="ratio",
                    weight=0.5,
                    directionality="higher_increases_score",
                    component_score=10.0,
                )
            ],
        ),
        "filing_risk": _ranking_payload(
            "filing_risk",
            label="Filing Risk",
            score=22.0,
            rank=2,
            percentile=0.0,
            score_directionality="higher_is_worse",
            components=[
                _ranking_component(
                    "filing_lag_days",
                    label="Filing lag days",
                    source_key="filing_lag_days",
                    value=33.0,
                    unit="days",
                    weight=0.4,
                    directionality="higher_increases_score",
                    component_score=25.0,
                )
            ],
        ),
    }


@contextmanager
def _client():
    app.dependency_overrides[get_db_session] = lambda: object()
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db_session, None)


def test_screener_filter_catalog_endpoint_returns_official_only_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "build_official_screener_filter_catalog",
        lambda: {
            "strict_official_only": True,
            "default_period_type": "ttm",
            "period_types": ["quarterly", "annual", "ttm"],
            "default_sort": {"field": "revenue_growth", "direction": "desc"},
            "filters": [
                {
                    "field": "shareholder_yield",
                    "label": "Shareholder yield",
                    "description": "Official proxy",
                    "comparator": "min",
                    "source_kind": "model_result",
                    "source_key": "capital_allocation.shareholder_yield",
                    "unit": "ratio",
                    "official_only": True,
                    "notes": ["Uses an official-only proxy."],
                    "suggested_values": [],
                }
            ],
            "rankings": [
                {
                    "score_key": "quality",
                    "label": "Quality",
                    "description": "Quality ranking",
                    "score_directionality": "higher_is_better",
                    "universe_basis": "candidate_universe_pre_filter",
                    "method_summary": "Weighted cross-sectional percentile blend.",
                    "components": [
                        {
                            "component_key": "revenue_growth",
                            "label": "Revenue growth",
                            "source_key": "revenue_growth",
                            "unit": "ratio",
                            "weight": 0.3,
                            "directionality": "higher_increases_score",
                            "notes": [],
                        }
                    ],
                    "confidence_notes_policy": ["missing_components_reweighted:<component_keys>"],
                    "notes": ["Transparent weighted percentile blend."],
                }
            ],
            "notes": ["No Yahoo dependency."],
            "source_hints": {
                "statement_sources": ["sec_companyfacts", "sec_edgar"],
                "uses_metrics": True,
                "uses_shareholder_yield_model": True,
            },
            "confidence_flags": ["official_source_only"],
        },
    )

    with _client() as client:
        response = client.get("/api/screener/filters")

    assert response.status_code == 200
    payload = response.json()
    assert payload["strict_official_only"] is True
    assert payload["filters"][0]["field"] == "shareholder_yield"
    assert payload["rankings"][0]["score_key"] == "quality"
    assert payload["rankings"][0]["components"][0]["directionality"] == "higher_increases_score"
    assert payload["source_mix"]["official_only"] is True
    assert payload["source_mix"]["fallback_source_ids"] == []
    assert {entry["source_id"] for entry in payload["provenance"]} == {
        "ft_screener_backend",
        "ft_derived_metrics_mart",
        "ft_model_engine",
        "sec_companyfacts",
        "sec_edgar",
    }
    assert "official_source_only" in payload["confidence_flags"]


def test_screener_search_endpoint_returns_screened_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        main_module,
        "run_official_screener",
        lambda *_args, **_kwargs: {
            "query": {
                "period_type": "ttm",
                "ticker_universe": [],
                "filters": {
                    "revenue_growth_min": 0.1,
                    "operating_margin_min": None,
                    "fcf_margin_min": None,
                    "leverage_ratio_max": None,
                    "dilution_max": None,
                    "sbc_burden_max": None,
                    "shareholder_yield_min": None,
                    "max_filing_lag_days": None,
                    "exclude_restatements": False,
                    "exclude_stale_periods": False,
                    "excluded_quality_flags": [],
                },
                "sort": {"field": "revenue_growth", "direction": "desc"},
                "limit": 50,
                "offset": 0,
                "strict_official_only": True,
            },
            "coverage": {
                "candidate_count": 2,
                "matched_count": 1,
                "returned_count": 1,
                "fresh_count": 1,
                "stale_count": 1,
                "missing_shareholder_yield_count": 0,
                "restatement_flagged_count": 0,
                "stale_period_flagged_count": 0,
            },
            "results": [
                {
                    "company": {
                        "ticker": "AAPL",
                        "cik": "0000320193",
                        "name": "Apple Inc.",
                        "sector": "Technology",
                        "market_sector": "Technology",
                        "market_industry": "Consumer Electronics",
                        "cache_state": "fresh",
                    },
                    "period_type": "ttm",
                    "period_end": date(2025, 12, 31),
                    "filing_type": "TTM",
                    "last_metrics_check": datetime(2026, 3, 29, tzinfo=timezone.utc),
                    "last_model_check": datetime(2026, 3, 28, tzinfo=timezone.utc),
                    "metrics": {
                        "revenue_growth": {"value": 0.18, "unit": "ratio", "is_proxy": True, "source_key": "revenue_growth", "quality_flags": []},
                        "operating_margin": {"value": 0.31, "unit": "ratio", "is_proxy": False, "source_key": "operating_margin", "quality_flags": []},
                        "fcf_margin": {"value": 0.27, "unit": "ratio", "is_proxy": False, "source_key": "fcf_margin", "quality_flags": []},
                        "leverage_ratio": {"value": 0.62, "unit": "ratio", "is_proxy": False, "source_key": "debt_to_equity", "quality_flags": []},
                        "dilution": {"value": -0.01, "unit": "ratio", "is_proxy": True, "source_key": "dilution_trend", "quality_flags": []},
                        "sbc_burden": {"value": 0.04, "unit": "ratio", "is_proxy": False, "source_key": "sbc_to_revenue", "quality_flags": []},
                        "shareholder_yield": {"value": 0.06, "unit": "ratio", "is_proxy": True, "source_key": "capital_allocation.shareholder_yield", "quality_flags": []},
                    },
                    "filing_quality": {
                        "filing_lag_days": {"value": 33.0, "unit": "days", "is_proxy": True, "source_key": "filing_lag_days", "quality_flags": []},
                        "stale_period_flag": {"value": 0.0, "unit": "flag", "is_proxy": True, "source_key": "stale_period_flag", "quality_flags": []},
                        "restatement_flag": {"value": 0.0, "unit": "flag", "is_proxy": True, "source_key": "restatement_flag", "quality_flags": []},
                        "restatement_count": 0,
                        "latest_restatement_filing_date": None,
                        "latest_restatement_period_end": None,
                        "aggregated_quality_flags": [],
                    },
                    "rankings": _rankings_payload(),
                }
            ],
            "as_of": date(2025, 12, 31),
            "last_refreshed_at": datetime(2026, 3, 29, tzinfo=timezone.utc),
            "source_hints": {
                "statement_sources": ["sec_companyfacts", "sec_edgar"],
                "uses_metrics": True,
                "uses_shareholder_yield_model": True,
            },
            "confidence_flags": ["official_source_only"],
        },
    )

    with _client() as client:
        response = client.post(
            "/api/screener/search",
            json={
                "period_type": "ttm",
                "filters": {"revenue_growth_min": 0.1},
                "sort": {"field": "revenue_growth", "direction": "desc"},
                "limit": 50,
                "offset": 0,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"]["strict_official_only"] is True
    assert payload["coverage"]["matched_count"] == 1
    assert payload["results"][0]["company"]["ticker"] == "AAPL"
    assert payload["results"][0]["metrics"]["shareholder_yield"]["source_key"] == "capital_allocation.shareholder_yield"
    assert payload["results"][0]["rankings"]["quality"]["score_directionality"] == "higher_is_better"
    assert payload["results"][0]["rankings"]["filing_risk"]["score_directionality"] == "higher_is_worse"
    assert payload["results"][0]["rankings"]["quality"]["components"][0]["component_key"] == "revenue_growth"
    assert payload["source_mix"]["official_only"] is True
    assert payload["source_mix"]["fallback_source_ids"] == []
    assert {entry["source_id"] for entry in payload["provenance"]} == {
        "ft_screener_backend",
        "ft_derived_metrics_mart",
        "ft_model_engine",
        "sec_companyfacts",
        "sec_edgar",
    }