from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

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

    monkeypatch.setattr(peer_comparison, "get_company_financials", lambda *_args, **_kwargs: [statement])
    monkeypatch.setattr(
        peer_comparison,
        "get_company_models",
        lambda *_args, **_kwargs: [
            SimpleNamespace(model_name="dcf", result={"model_status": "ok", "fair_value_per_share": 120.0}),
            SimpleNamespace(model_name="reverse_dcf", result={"model_status": "ok", "implied_growth": 0.07}),
            SimpleNamespace(model_name="ratios", result={"values": {"net_debt_to_fcf": 1.2}}),
            SimpleNamespace(model_name="dupont", result={}),
            SimpleNamespace(model_name="piotroski", result={}),
            SimpleNamespace(model_name="altman_z", result={}),
            SimpleNamespace(model_name="roic", result={}),
            SimpleNamespace(model_name="capital_allocation", result={}),
        ],
    )
    monkeypatch.setattr(peer_comparison, "_latest_price_point", lambda *_args, **_kwargs: SimpleNamespace(close=100.0, trade_date=date(2026, 3, 21)))
    monkeypatch.setattr(peer_comparison, "_build_revenue_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(peer_comparison, "_valuation_band_percentile", lambda *_args, **_kwargs: None)

    row = peer_comparison._build_peer_row(session=SimpleNamespace(), snapshot=snapshot, is_focus=True)

    assert row["fair_value_gap"] == 0.2


def test_peer_row_hides_gap_when_dcf_unsupported(monkeypatch):
    snapshot = _snapshot()
    statement = _statement()

    monkeypatch.setattr(peer_comparison, "get_company_financials", lambda *_args, **_kwargs: [statement])
    monkeypatch.setattr(
        peer_comparison,
        "get_company_models",
        lambda *_args, **_kwargs: [
            SimpleNamespace(model_name="dcf", result={"model_status": "unsupported", "fair_value_per_share": 120.0}),
            SimpleNamespace(model_name="reverse_dcf", result={"model_status": "unsupported", "implied_growth": 0.07}),
            SimpleNamespace(model_name="ratios", result={"values": {"net_debt_to_fcf": 1.2}}),
            SimpleNamespace(model_name="dupont", result={}),
            SimpleNamespace(model_name="piotroski", result={}),
            SimpleNamespace(model_name="altman_z", result={}),
            SimpleNamespace(model_name="roic", result={}),
            SimpleNamespace(model_name="capital_allocation", result={}),
        ],
    )
    monkeypatch.setattr(peer_comparison, "_latest_price_point", lambda *_args, **_kwargs: SimpleNamespace(close=100.0, trade_date=date(2026, 3, 21)))
    monkeypatch.setattr(peer_comparison, "_build_revenue_history", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(peer_comparison, "_valuation_band_percentile", lambda *_args, **_kwargs: None)

    row = peer_comparison._build_peer_row(session=SimpleNamespace(), snapshot=snapshot, is_focus=True)

    assert row["fair_value_gap"] is None
    assert row["implied_growth"] is None
