from __future__ import annotations

from types import SimpleNamespace

from app.services.equity_claim_risk import _build_atm_dependency, _build_sbc_and_dilution


def test_build_atm_dependency_reads_statement_metrics_from_data_payload() -> None:
    statement = SimpleNamespace(
        data={
            "free_cash_flow": -50_000_000,
            "cash_and_short_term_investments": 60_000_000,
        }
    )

    payload = _build_atm_dependency(
        statement,
        {"summary": {"debt_due_next_twelve_months": 20_000_000}},
        [],
        [],
    )

    assert payload.negative_free_cash_flow is True
    assert payload.cash_runway_years == 1.2
    assert payload.financing_dependency_level == "high"


def test_build_sbc_and_dilution_reads_statement_metrics_from_data_payload() -> None:
    latest_statement = SimpleNamespace(
        data={
            "stock_based_compensation": 42_000_000,
            "revenue": 200_000_000,
            "weighted_average_diluted_shares": 110_000_000,
        }
    )
    previous_statement = SimpleNamespace(
        data={
            "weighted_average_shares_diluted": 100_000_000,
        }
    )

    payload = _build_sbc_and_dilution(latest_statement, previous_statement, [])

    assert payload.sbc_to_revenue == 0.21
    assert payload.weighted_average_diluted_shares_growth == 0.1