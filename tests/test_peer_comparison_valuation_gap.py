from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

import app.services.peer_comparison as peer_comparison


def _snapshot() -> SimpleNamespace:
    company = SimpleNamespace(
        id=1,
        ticker="ACME",
        name="Acme Corp",
        sector="Technology",
        market_sector="Technology",
        market_industry="Software",
    )
    return SimpleNamespace(company=company, cache_state="fresh", last_checked=datetime.now(timezone.utc))


def _statement() -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        filing_type="10-K",
        period_end=date(2025, 12, 31),
        data={
            "revenue": 1000.0,
            "eps": 2.0,
            "free_cash_flow": 120.0,
            "total_liabilities": 300.0,
            "operating_income": 180.0,
            "shares_outstanding": 100.0,
            "net_income": 200.0,
        },
    )


def test_peer_row_fair_value_gap_uses_fair_value_per_share(monkeypatch):
    snapshot = _snapshot()
    statement = _statement()

    monkeypatch.setattr(peer_comparison, "_build_revenue_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(peer_comparison, "_valuation_band_percentile", lambda *_args, **_kwargs: None)

    row = peer_comparison._build_peer_row(
        snapshot=snapshot,
        is_focus=True,
        financials_by_company={snapshot.company.id: [statement]},
        latest_prices_by_company={snapshot.company.id: SimpleNamespace(close=100.0, trade_date=date(2026, 3, 21))},
        models_by_company={
            snapshot.company.id: {
                "dcf": SimpleNamespace(model_name="dcf", result={"model_status": "ok", "fair_value_per_share": 120.0}),
                "reverse_dcf": SimpleNamespace(model_name="reverse_dcf", result={"model_status": "ok", "implied_growth": 0.07}),
                "ratios": SimpleNamespace(model_name="ratios", result={"values": {"net_debt_to_fcf": 1.2}}),
                "dupont": SimpleNamespace(model_name="dupont", result={}),
                "piotroski": SimpleNamespace(model_name="piotroski", result={}),
                "altman_z": SimpleNamespace(model_name="altman_z", result={}),
                "roic": SimpleNamespace(model_name="roic", result={}),
                "capital_allocation": SimpleNamespace(model_name="capital_allocation", result={}),
            }
        },
    )

    assert row["fair_value_gap"] == 0.2


def test_peer_row_hides_gap_when_dcf_unsupported(monkeypatch):
    snapshot = _snapshot()
    statement = _statement()

    monkeypatch.setattr(peer_comparison, "_build_revenue_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(peer_comparison, "_valuation_band_percentile", lambda *_args, **_kwargs: None)

    row = peer_comparison._build_peer_row(
        snapshot=snapshot,
        is_focus=True,
        financials_by_company={snapshot.company.id: [statement]},
        latest_prices_by_company={snapshot.company.id: SimpleNamespace(close=100.0, trade_date=date(2026, 3, 21))},
        models_by_company={
            snapshot.company.id: {
                "dcf": SimpleNamespace(model_name="dcf", result={"model_status": "unsupported", "fair_value_per_share": 120.0}),
                "reverse_dcf": SimpleNamespace(model_name="reverse_dcf", result={"model_status": "unsupported", "implied_growth": 0.07}),
                "ratios": SimpleNamespace(model_name="ratios", result={"values": {"net_debt_to_fcf": 1.2}}),
                "dupont": SimpleNamespace(model_name="dupont", result={}),
                "piotroski": SimpleNamespace(model_name="piotroski", result={}),
                "altman_z": SimpleNamespace(model_name="altman_z", result={}),
                "roic": SimpleNamespace(model_name="roic", result={}),
                "capital_allocation": SimpleNamespace(model_name="capital_allocation", result={}),
            }
        },
    )

    assert row["fair_value_gap"] is None
    assert row["implied_growth"] is None


def test_peer_row_ev_to_ebit_uses_debt_less_cash_not_total_liabilities(monkeypatch):
    snapshot = _snapshot()
    statement = SimpleNamespace(
        id=1,
        filing_type="10-K",
        period_end=date(2025, 12, 31),
        data={
            "operating_income": 100.0,
            "shares_outstanding": 100.0,
            "current_debt": 50.0,
            "long_term_debt": 150.0,
            "cash_and_short_term_investments": 80.0,
            "total_liabilities": 1000.0,
        },
    )

    monkeypatch.setattr(peer_comparison, "_build_revenue_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(peer_comparison, "_valuation_band_percentile", lambda *_args, **_kwargs: None)

    row = peer_comparison._build_peer_row(
        snapshot=snapshot,
        is_focus=True,
        financials_by_company={snapshot.company.id: [statement]},
        latest_prices_by_company={snapshot.company.id: SimpleNamespace(close=10.0, trade_date=date(2026, 3, 21))},
        models_by_company={
            snapshot.company.id: {
                "dcf": SimpleNamespace(model_name="dcf", result={}),
                "reverse_dcf": SimpleNamespace(model_name="reverse_dcf", result={}),
                "ratios": SimpleNamespace(model_name="ratios", result={"values": {}}),
                "dupont": SimpleNamespace(model_name="dupont", result={}),
                "piotroski": SimpleNamespace(model_name="piotroski", result={}),
                "altman_z": SimpleNamespace(model_name="altman_z", result={}),
                "roic": SimpleNamespace(model_name="roic", result={}),
                "capital_allocation": SimpleNamespace(model_name="capital_allocation", result={}),
            }
        },
    )

    assert row["ev_to_ebit"] == pytest.approx((1000.0 + 200.0 - 80.0) / 100.0, rel=1e-9)
    assert row["ev_to_ebit"] != pytest.approx((1000.0 + 1000.0) / 100.0, rel=1e-9)


def test_valuation_band_percentile_ignores_non_debt_liabilities_in_ev_history():
    statements = [
        SimpleNamespace(
            id=1,
            filing_type="10-K",
            period_end=date(2025, 12, 31),
            data={
                "operating_income": 100.0,
                "shares_outstanding": 100.0,
                "current_debt": 50.0,
                "long_term_debt": 0.0,
                "cash_and_short_term_investments": 200.0,
                "total_liabilities": 1000.0,
            },
        ),
        SimpleNamespace(
            id=2,
            filing_type="10-K",
            period_end=date(2024, 12, 31),
            data={
                "operating_income": 100.0,
                "shares_outstanding": 100.0,
                "current_debt": 100.0,
                "long_term_debt": 200.0,
                "cash_and_short_term_investments": 0.0,
                "total_liabilities": 400.0,
            },
        ),
        SimpleNamespace(
            id=3,
            filing_type="10-K",
            period_end=date(2023, 12, 31),
            data={
                "operating_income": 100.0,
                "shares_outstanding": 100.0,
                "current_debt": 100.0,
                "long_term_debt": 150.0,
                "cash_and_short_term_investments": 0.0,
                "total_liabilities": 300.0,
            },
        ),
    ]

    latest_ev = peer_comparison._enterprise_value_proxy(statements[0].data, 10.0, 100.0)
    percentile = peer_comparison._valuation_band_percentile(statements, 10.0, 100.0, latest_ev)

    assert latest_ev == pytest.approx(850.0, rel=1e-9)
    assert percentile == pytest.approx(1.0 / 3.0, rel=1e-9)
