from __future__ import annotations

from datetime import date, datetime, timezone

import app.services.screener as screener_service


def test_build_official_screener_filter_catalog_exposes_ranking_definitions() -> None:
    payload = screener_service.build_official_screener_filter_catalog()

    assert len(payload["rankings"]) == 5
    assert {item["score_key"] for item in payload["rankings"]} == {
        "quality",
        "value",
        "capital_allocation",
        "dilution_risk",
        "filing_risk",
    }
    value_definition = next(item for item in payload["rankings"] if item["score_key"] == "value")
    assert value_definition["score_directionality"] == "higher_is_better"
    assert value_definition["components"][0]["component_key"] == "shareholder_yield"
    assert value_definition["universe_basis"] == "candidate_universe_pre_filter"
    assert "missing_components_reweighted:<component_keys>" in value_definition["confidence_notes_policy"]


def test_internal_filing_quality_fields_have_snapshot_definitions() -> None:
    stale_snapshot = screener_service._empty_metric_snapshot("stale_period_flag")
    restatement_snapshot = screener_service._empty_metric_snapshot("restatement_flag")

    assert stale_snapshot["source_key"] == "stale_period_flag"
    assert stale_snapshot["unit"] == "flag"
    assert restatement_snapshot["source_key"] == "restatement_flag"
    assert screener_service._METRIC_KEY_TO_PUBLIC_FIELD["stale_period_flag"] == "stale_period_flag"
    assert screener_service._METRIC_KEY_TO_PUBLIC_FIELD["restatement_flag"] == "restatement_flag"


def _candidate(
    ticker: str,
    *,
    revenue_growth: float,
    operating_margin: float,
    fcf_margin: float,
    leverage_ratio: float,
    dilution: float,
    sbc_burden: float,
    shareholder_yield: float | None,
    filing_lag_days: float,
    restatement_count: int,
    cache_state: str = "fresh",
    quality_flags: list[str] | None = None,
):
    return {
        "company": {
            "ticker": ticker,
            "cik": f"0000{ticker}",
            "name": f"{ticker} Corp.",
            "sector": "Technology",
            "market_sector": "Technology",
            "market_industry": "Software",
            "cache_state": cache_state,
        },
        "period_type": "ttm",
        "period_end": date(2025, 12, 31),
        "filing_type": "TTM",
        "last_metrics_check": datetime(2026, 3, 29, tzinfo=timezone.utc),
        "last_model_check": datetime(2026, 3, 28, tzinfo=timezone.utc) if shareholder_yield is not None else None,
        "metrics": {
            "revenue_growth": {"value": revenue_growth, "unit": "ratio", "is_proxy": True, "source_key": "revenue_growth", "quality_flags": []},
            "operating_margin": {"value": operating_margin, "unit": "ratio", "is_proxy": False, "source_key": "operating_margin", "quality_flags": []},
            "fcf_margin": {"value": fcf_margin, "unit": "ratio", "is_proxy": False, "source_key": "fcf_margin", "quality_flags": []},
            "leverage_ratio": {"value": leverage_ratio, "unit": "ratio", "is_proxy": False, "source_key": "debt_to_equity", "quality_flags": []},
            "dilution": {"value": dilution, "unit": "ratio", "is_proxy": True, "source_key": "dilution_trend", "quality_flags": []},
            "sbc_burden": {"value": sbc_burden, "unit": "ratio", "is_proxy": False, "source_key": "sbc_to_revenue", "quality_flags": []},
            "shareholder_yield": {
                "value": shareholder_yield,
                "unit": "ratio",
                "is_proxy": True,
                "source_key": "capital_allocation.shareholder_yield",
                "quality_flags": ["shareholder_yield_unavailable"] if shareholder_yield is None else [],
            },
        },
        "filing_quality": {
            "filing_lag_days": {"value": filing_lag_days, "unit": "days", "is_proxy": True, "source_key": "filing_lag_days", "quality_flags": []},
            "stale_period_flag": {"value": 1.0 if cache_state == "stale" else 0.0, "unit": "flag", "is_proxy": True, "source_key": "stale_period_flag", "quality_flags": []},
            "restatement_flag": {"value": 1.0 if restatement_count else 0.0, "unit": "flag", "is_proxy": True, "source_key": "restatement_flag", "quality_flags": []},
            "restatement_count": restatement_count,
            "latest_restatement_filing_date": date(2025, 8, 1) if restatement_count else None,
            "latest_restatement_period_end": date(2025, 6, 30) if restatement_count else None,
            "aggregated_quality_flags": list(quality_flags or []),
        },
        "statement_sources": ["sec_companyfacts"],
    }


def test_run_official_screener_filters_and_sorts(monkeypatch) -> None:
    monkeypatch.setattr(
        screener_service,
        "_load_official_screener_candidates",
        lambda *_args, **_kwargs: [
            _candidate(
                "AAA",
                revenue_growth=0.28,
                operating_margin=0.22,
                fcf_margin=0.18,
                leverage_ratio=0.4,
                dilution=0.01,
                sbc_burden=0.03,
                shareholder_yield=0.05,
                filing_lag_days=31.0,
                restatement_count=0,
            ),
            _candidate(
                "BBB",
                revenue_growth=0.19,
                operating_margin=0.18,
                fcf_margin=0.11,
                leverage_ratio=1.4,
                dilution=0.02,
                sbc_burden=0.04,
                shareholder_yield=0.02,
                filing_lag_days=29.0,
                restatement_count=0,
            ),
            _candidate(
                "CCC",
                revenue_growth=0.33,
                operating_margin=0.25,
                fcf_margin=0.2,
                leverage_ratio=0.35,
                dilution=0.0,
                sbc_burden=0.02,
                shareholder_yield=None,
                filing_lag_days=62.0,
                restatement_count=1,
                quality_flags=["historical_restatement_present"],
            ),
        ],
    )

    payload = screener_service.run_official_screener(
        object(),
        {
            "period_type": "ttm",
            "filters": {
                "revenue_growth_min": 0.2,
                "leverage_ratio_max": 1.0,
                "shareholder_yield_min": 0.03,
                "exclude_restatements": True,
                "max_filing_lag_days": 40,
            },
            "sort": {"field": "revenue_growth", "direction": "desc"},
            "limit": 10,
            "offset": 0,
        },
    )

    assert payload["coverage"]["candidate_count"] == 3
    assert payload["coverage"]["matched_count"] == 1
    assert [row["company"]["ticker"] for row in payload["results"]] == ["AAA"]
    assert payload["results"][0]["metrics"]["shareholder_yield"]["value"] == 0.05
    assert payload["results"][0]["rankings"]["quality"]["score_directionality"] == "higher_is_better"
    assert payload["results"][0]["rankings"]["quality"]["components"][0]["component_key"] == "revenue_growth"
    assert payload["results"][0]["rankings"]["quality"]["universe_size"] == 3
    leverage_component = next(
        component
        for component in payload["results"][0]["rankings"]["quality"]["components"]
        if component["component_key"] == "leverage_ratio"
    )
    assert leverage_component["directionality"] == "lower_increases_score"
    assert payload["results"][0]["rankings"]["dilution_risk"]["score_directionality"] == "higher_is_worse"
    assert payload["source_hints"]["statement_sources"] == ["sec_companyfacts"]
    assert "partial_shareholder_yield_coverage" in payload["confidence_flags"]


def test_run_official_screener_excludes_requested_quality_flags(monkeypatch) -> None:
    monkeypatch.setattr(
        screener_service,
        "_load_official_screener_candidates",
        lambda *_args, **_kwargs: [
            _candidate(
                "AAA",
                revenue_growth=0.28,
                operating_margin=0.22,
                fcf_margin=0.18,
                leverage_ratio=0.4,
                dilution=0.01,
                sbc_burden=0.03,
                shareholder_yield=0.05,
                filing_lag_days=31.0,
                restatement_count=0,
                quality_flags=["filing_lag_proxy_from_last_updated"],
            ),
            _candidate(
                "BBB",
                revenue_growth=0.21,
                operating_margin=0.21,
                fcf_margin=0.17,
                leverage_ratio=0.45,
                dilution=0.02,
                sbc_burden=0.02,
                shareholder_yield=0.04,
                filing_lag_days=30.0,
                restatement_count=0,
                quality_flags=[],
            ),
        ],
    )

    payload = screener_service.run_official_screener(
        object(),
        {
            "filters": {
                "excluded_quality_flags": ["filing_lag_proxy_from_last_updated"],
            },
            "sort": {"field": "ticker", "direction": "asc"},
            "limit": 10,
            "offset": 0,
        },
    )

    assert payload["coverage"]["matched_count"] == 1
    assert [row["company"]["ticker"] for row in payload["results"]] == ["BBB"]


def test_run_official_screener_sorts_by_ranking_score(monkeypatch) -> None:
    monkeypatch.setattr(
        screener_service,
        "_load_official_screener_candidates",
        lambda *_args, **_kwargs: [
            _candidate(
                "AAA",
                revenue_growth=0.24,
                operating_margin=0.22,
                fcf_margin=0.16,
                leverage_ratio=0.4,
                dilution=0.01,
                sbc_burden=0.03,
                shareholder_yield=0.05,
                filing_lag_days=22.0,
                restatement_count=0,
            ),
            _candidate(
                "BBB",
                revenue_growth=0.11,
                operating_margin=0.09,
                fcf_margin=0.05,
                leverage_ratio=1.3,
                dilution=0.08,
                sbc_burden=0.09,
                shareholder_yield=0.01,
                filing_lag_days=88.0,
                restatement_count=2,
            ),
        ],
    )

    payload = screener_service.run_official_screener(
        object(),
        {
            "sort": {"field": "filing_risk_score", "direction": "desc"},
            "limit": 10,
            "offset": 0,
        },
    )

    assert [row["company"]["ticker"] for row in payload["results"]] == ["BBB", "AAA"]
    assert payload["results"][0]["rankings"]["filing_risk"]["rank"] == 1
    assert payload["results"][0]["rankings"]["filing_risk"]["score_directionality"] == "higher_is_worse"