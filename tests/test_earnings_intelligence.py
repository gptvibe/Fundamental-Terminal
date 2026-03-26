from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.services.earnings_intelligence import (
    build_earnings_alerts,
    build_earnings_directional_backtest,
    build_earnings_model_points,
)


def _statement(
    *,
    statement_id: int,
    filing_type: str,
    period_end: date,
    revenue: float,
    net_income: float,
    operating_cash_flow: float,
    free_cash_flow: float,
    eps: float,
    segment_a_share: float,
    segment_b_share: float,
):
    segment_total = revenue
    segment_a_revenue = segment_total * segment_a_share
    segment_b_revenue = segment_total * segment_b_share
    return SimpleNamespace(
        id=statement_id,
        period_start=period_end,
        period_end=period_end,
        filing_type=filing_type,
        statement_type="canonical_xbrl",
        last_updated=period_end,
        data={
            "revenue": revenue,
            "net_income": net_income,
            "operating_cash_flow": operating_cash_flow,
            "free_cash_flow": free_cash_flow,
            "eps": eps,
            "total_assets": revenue * 1.5,
            "segment_breakdown": [
                {
                    "segment_id": "A",
                    "segment_name": "Segment A",
                    "revenue": segment_a_revenue,
                    "share_of_revenue": segment_a_share,
                },
                {
                    "segment_id": "B",
                    "segment_name": "Segment B",
                    "revenue": segment_b_revenue,
                    "share_of_revenue": segment_b_share,
                },
            ],
        },
    )


def _release(release_id: int, period_end: date, filing_date: date, accession_number: str):
    return SimpleNamespace(
        id=release_id,
        accession_number=accession_number,
        reported_period_end=period_end,
        filing_date=filing_date,
        revenue=100.0,
        diluted_eps=1.0,
    )


def _price(trade_date: date, close: float):
    return SimpleNamespace(trade_date=trade_date, close=close, source="yahoo_finance")


def test_build_earnings_model_points_includes_required_metrics_and_explainability():
    points = build_earnings_model_points(
        [
            _statement(
                statement_id=1,
                filing_type="10-Q",
                period_end=date(2025, 9, 30),
                revenue=100.0,
                net_income=12.0,
                operating_cash_flow=13.0,
                free_cash_flow=10.0,
                eps=0.8,
                segment_a_share=0.6,
                segment_b_share=0.4,
            ),
            _statement(
                statement_id=2,
                filing_type="10-Q",
                period_end=date(2025, 12, 31),
                revenue=110.0,
                net_income=15.0,
                operating_cash_flow=17.0,
                free_cash_flow=14.0,
                eps=1.1,
                segment_a_share=0.55,
                segment_b_share=0.45,
            ),
        ],
        [
            _release(1, date(2025, 9, 30), date(2025, 11, 1), "0001"),
            _release(2, date(2025, 12, 31), date(2026, 2, 1), "0002"),
        ],
        as_of_date=date(2026, 2, 10),
    )

    assert len(points) == 2
    latest = points[-1]
    assert latest["quality_score"] is not None
    assert latest["eps_drift"] == pytest.approx(0.3)
    assert latest["earnings_momentum_drift"] is None
    assert latest["segment_contribution_delta"] is not None
    assert latest["release_statement_coverage_ratio"] is not None
    assert latest["fallback_ratio"] is not None
    assert isinstance(latest["stale_period_warning"], bool)
    assert latest["explainability"]["inputs"]
    assert latest["explainability"]["proxy_usage"]


def test_directional_backtest_uses_cached_price_windows_and_returns_consistency_summary():
    model_points = [
        SimpleNamespace(period_end=date(2025, 9, 30), quality_score_delta=0.2, eps_drift=0.1),
        SimpleNamespace(period_end=date(2025, 12, 31), quality_score_delta=-0.4, eps_drift=-0.2),
    ]
    releases = [
        _release(1, date(2025, 9, 30), date(2025, 11, 1), "0001"),
        _release(2, date(2025, 12, 31), date(2026, 2, 1), "0002"),
    ]
    prices = [
        _price(date(2025, 10, 31), 100.0),
        _price(date(2025, 11, 1), 101.0),
        _price(date(2025, 11, 4), 104.0),
        _price(date(2026, 1, 31), 108.0),
        _price(date(2026, 2, 1), 106.0),
        _price(date(2026, 2, 4), 103.0),
    ]

    payload = build_earnings_directional_backtest(model_points, releases, prices, post_sessions=2)

    assert payload["window_sessions"] == 2
    assert payload["quality_total_windows"] >= 1
    assert payload["eps_total_windows"] >= 1
    assert payload["windows"]


def test_build_earnings_alerts_detects_regime_flip_sign_flip_and_segment_threshold():
    points = [
        SimpleNamespace(period_end=date(2025, 9, 30), quality_score=70.0, eps_drift=0.2, segment_contribution_delta=0.02),
        SimpleNamespace(period_end=date(2025, 12, 31), quality_score=35.0, eps_drift=-0.1, segment_contribution_delta=0.12),
    ]

    alerts = build_earnings_alerts(points)

    assert any(alert["type"] == "quality_regime_shift" for alert in alerts)
    assert any(alert["type"] == "eps_drift_sign_flip" for alert in alerts)
    assert any(alert["type"] == "segment_share_change" for alert in alerts)


def test_build_earnings_alerts_respects_tuned_profile_thresholds():
    points = [
        SimpleNamespace(period_end=date(2025, 9, 30), quality_score=56.0, eps_drift=0.04, segment_contribution_delta=0.03),
        SimpleNamespace(period_end=date(2025, 12, 31), quality_score=67.0, eps_drift=0.05, segment_contribution_delta=0.06),
    ]

    alerts = build_earnings_alerts(
        points,
        profile={
            "quality_mid_threshold": 50.0,
            "quality_high_threshold": 60.0,
            "segment_change_threshold": 0.05,
        },
    )

    assert any(alert["type"] == "quality_regime_shift" for alert in alerts)
    assert any(alert["type"] == "segment_share_change" for alert in alerts)
