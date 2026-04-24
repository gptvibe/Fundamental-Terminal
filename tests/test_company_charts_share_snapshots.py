from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import app.main as main_module


def _make_snapshot_payload() -> main_module.CompanyChartsShareSnapshotPayload:
    return main_module.CompanyChartsShareSnapshotPayload.model_validate(
        {
            "schema_version": "company_chart_share_snapshot_v1",
            "mode": "outlook",
            "ticker": "ACME",
            "company_name": "Acme Corp",
            "title": "Growth Outlook",
            "as_of": "2026-04-23",
            "source_badge": "SEC Company Facts",
            "provenance_badge": "SEC-derived",
            "trust_label": "Forecast stability: Moderate stability",
            "actual_label": "Reported",
            "forecast_label": "Forecast",
            "source_path": "/company/ACME/charts",
            "chart_spec": {
                "schema_version": "company_chart_spec_v1",
                "payload_version": "company_charts_dashboard_v9",
                "company": None,
                "build_state": "ready",
                "build_status": "Charts ready.",
                "refresh": {"triggered": False, "reason": "fresh", "ticker": "ACME", "job_id": None},
                "diagnostics": {
                    "coverage_ratio": 1,
                    "fallback_ratio": 0,
                    "stale_flags": [],
                    "parser_confidence": 0.9,
                    "missing_field_flags": [],
                    "reconciliation_penalty": None,
                    "reconciliation_disagreement_count": 0,
                },
                "provenance": [],
                "as_of": "2026-04-23",
                "last_refreshed_at": "2026-04-23T00:00:00Z",
                "source_mix": {
                    "source_ids": [],
                    "source_tiers": [],
                    "primary_source_ids": [],
                    "fallback_source_ids": [],
                    "official_only": True,
                },
                "confidence_flags": [],
                "available_modes": ["outlook"],
                "default_mode": "outlook",
                "outlook": {
                    "title": "Growth Outlook",
                    "summary": {
                        "headline": "Growth Outlook",
                        "primary_score": {"key": "growth", "label": "Growth", "score": 82, "tone": "positive", "detail": "Strong"},
                        "secondary_badges": [],
                        "thesis": "Projected and reported values are distinct.",
                        "unavailable_notes": [],
                        "freshness_badges": [],
                        "source_badges": ["SEC Company Facts"],
                    },
                    "legend": {
                        "title": "Actual vs Forecast",
                        "items": [
                            {"key": "actual", "label": "Reported", "style": "solid", "tone": "actual", "description": "Historical filings."},
                            {"key": "forecast", "label": "Forecast", "style": "dashed", "tone": "forecast", "description": "Projected path."},
                        ],
                    },
                    "cards": {
                        "revenue": {"key": "revenue", "title": "Revenue", "subtitle": None, "metric_label": None, "unit_label": None, "empty_state": None, "series": [], "highlights": []},
                        "revenue_growth": {"key": "revenue_growth", "title": "Revenue Growth", "subtitle": None, "metric_label": None, "unit_label": None, "empty_state": None, "series": [], "highlights": []},
                        "profit_metric": {"key": "profit_metric", "title": "Profit Metrics", "subtitle": None, "metric_label": None, "unit_label": None, "empty_state": None, "series": [], "highlights": []},
                        "cash_flow_metric": {"key": "cash_flow_metric", "title": "Cash Flow Metrics", "subtitle": None, "metric_label": None, "unit_label": None, "empty_state": None, "series": [], "highlights": []},
                        "eps": {"key": "eps", "title": "EPS", "subtitle": None, "metric_label": None, "unit_label": None, "empty_state": None, "series": [], "highlights": []},
                        "growth_summary": {"key": "growth_summary", "title": "Growth Summary", "subtitle": None, "comparisons": [], "empty_state": None},
                        "forecast_assumptions": None,
                    },
                    "primary_card_order": ["revenue"],
                    "secondary_card_order": [],
                    "comparison_card_order": ["growth_summary"],
                    "detail_card_order": [],
                    "methodology": {
                        "version": "company_charts_dashboard_v9",
                        "label": "Driver-based integrated forecast",
                        "summary": "Official-input forecast.",
                        "disclaimer": "Forecast values are projections.",
                        "forecast_horizon_years": 3,
                        "score_name": "Forecast Stability",
                        "heuristic": True,
                        "score_components": [],
                        "confidence_label": "Forecast stability: Moderate stability",
                    },
                    "forecast_diagnostics": {
                        "score_key": "forecast_stability",
                        "score_name": "Forecast Stability",
                        "heuristic": True,
                        "final_score": 72,
                        "summary": "Moderate stability.",
                        "history_depth_years": 4,
                        "thin_history": False,
                        "growth_volatility": 0.1,
                        "growth_volatility_band": "moderate",
                        "missing_data_penalty": 0,
                        "quality_score": 0.9,
                        "missing_inputs": [],
                        "sample_size": 3,
                        "scenario_dispersion": 0.1,
                        "sector_template": "Technology",
                        "guidance_usage": "management_guidance_applied",
                        "historical_backtest_error_band": "moderate",
                        "backtest_weighted_error": 0.1,
                        "backtest_horizon_errors": {},
                        "backtest_metric_weights": {},
                        "backtest_metric_errors": {},
                        "backtest_metric_horizon_errors": {},
                        "backtest_metric_sample_sizes": {},
                        "components": [],
                    },
                },
                "studio": None,
            },
            "outlook": {
                "headline": "Growth Outlook",
                "thesis": "Projected and reported values are distinct.",
                "primary_score": {"key": "growth", "label": "Growth", "score": 82, "tone": "positive", "detail": "Strong"},
                "secondary_scores": [],
                "summary_metrics": [{"key": "reported", "label": "Reported", "value": "FY2025"}],
                "primary_chart": {
                    "title": "Revenue",
                    "unit": "usd",
                    "actual_points": [{"label": "FY2025", "value": 100, "kind": "actual"}],
                    "forecast_points": [{"label": "FY2026E", "value": 120, "kind": "forecast"}],
                },
            },
            "studio": None,
        }
    )


def test_company_charts_share_snapshot_create_commits_and_serializes(monkeypatch):
    snapshot = SimpleNamespace(company=SimpleNamespace(id=1, ticker="ACME"))
    payload = _make_snapshot_payload()
    created = SimpleNamespace(id="share-1", created_at=datetime(2026, 4, 23, tzinfo=timezone.utc), payload=payload.model_dump(mode="json"))
    response_payload = main_module.CompanyChartsShareSnapshotRecordPayload(
        id="share-1",
        ticker="ACME",
        mode="outlook",
        schema_version=payload.schema_version,
        share_path="/company/ACME/charts/share/share-1",
        image_path="/company/ACME/charts/share/share-1/image",
        created_at=datetime(2026, 4, 23, tzinfo=timezone.utc),
        payload=payload,
    )

    class _Session:
        def __init__(self) -> None:
            self.commits = 0

        def commit(self) -> None:
            self.commits += 1

    session = _Session()
    observed_company_ids: list[int] = []

    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda session, ticker: snapshot)
    monkeypatch.setattr(
        main_module,
        "create_company_charts_share_snapshot",
        lambda session, company_id, payload: observed_company_ids.append(company_id) or created,
    )
    monkeypatch.setattr(
        main_module,
        "serialize_company_charts_share_snapshot",
        lambda record, ticker: response_payload,
    )

    response = main_module.company_charts_share_snapshot_create("acme", payload, session=session)

    assert observed_company_ids == [1]
    assert response.id == "share-1"
    assert response.share_path.endswith("/share/share-1")
    assert session.commits == 1


def test_company_charts_share_snapshot_detail_raises_404_when_snapshot_missing(monkeypatch):
    snapshot = SimpleNamespace(company=SimpleNamespace(id=1, ticker="ACME"))

    monkeypatch.setattr(main_module, "_resolve_company_brief_snapshot", lambda session, ticker: snapshot)
    monkeypatch.setattr(main_module, "get_company_charts_share_snapshot", lambda *args, **kwargs: None)

    with pytest.raises(HTTPException) as exc_info:
        main_module.company_charts_share_snapshot_detail("ACME", "missing-share", session=object())

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Charts share snapshot not found."
