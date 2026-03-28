from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from app.services.capital_structure_intelligence import build_capital_structure_snapshots, snapshot_effective_at


def _statement(
    statement_id: int,
    period_start: date,
    period_end: date,
    filing_type: str,
    data: dict[str, float | int | None],
):
    return SimpleNamespace(
        id=statement_id,
        period_start=period_start,
        period_end=period_end,
        filing_type=filing_type,
        statement_type="canonical_xbrl",
        source="https://data.sec.gov/api/xbrl/companyfacts/CIK0000123456.json",
        filing_acceptance_at=datetime.combine(period_end, datetime.min.time(), tzinfo=timezone.utc),
        last_updated=datetime(2026, 3, 25, tzinfo=timezone.utc),
        last_checked=datetime(2026, 3, 25, tzinfo=timezone.utc),
        data=data,
    )


def test_build_capital_structure_snapshots_outputs_rollforward_payout_and_dilution_sections() -> None:
    statements = [
        _statement(
            1,
            date(2024, 1, 1),
            date(2024, 12, 31),
            "10-K",
            {
                "current_debt": 20,
                "long_term_debt": 80,
                "interest_expense": 3,
                "revenue": 180,
                "operating_cash_flow": 50,
                "operating_income": 60,
                "dividends": -4,
                "share_buybacks": -10,
                "stock_based_compensation": 5,
                "shares_outstanding": 100,
                "weighted_average_diluted_shares": 103,
                "shares_issued": 4,
                "shares_repurchased": 1,
            },
        ),
        _statement(
            2,
            date(2025, 1, 1),
            date(2025, 12, 31),
            "10-K",
            {
                "current_debt": 30,
                "long_term_debt": 90,
                "interest_expense": 4,
                "revenue": 200,
                "operating_cash_flow": 60,
                "operating_income": 80,
                "dividends": -5,
                "share_buybacks": -12,
                "stock_based_compensation": 6,
                "debt_issuance": 20,
                "debt_repayment": 8,
                "debt_changes": 12,
                "shares_outstanding": 102,
                "weighted_average_diluted_shares": 105,
                "shares_issued": 5,
                "shares_repurchased": 3,
                "debt_maturity_due_next_twelve_months": 10,
                "debt_maturity_due_year_two": 11,
                "debt_maturity_due_year_three": 12,
                "debt_maturity_due_year_four": 13,
                "debt_maturity_due_year_five": 14,
                "debt_maturity_due_thereafter": 15,
                "lease_liabilities": 18,
                "lease_due_next_twelve_months": 3,
                "lease_due_year_two": 3,
                "lease_due_year_three": 4,
                "lease_due_year_four": 4,
                "lease_due_year_five": 5,
                "lease_due_thereafter": 6,
            },
        ),
    ]

    snapshots = build_capital_structure_snapshots(statements)

    assert len(snapshots) == 2
    latest = snapshots[-1]
    assert latest["data"]["summary"]["total_debt"] == 120
    assert latest["data"]["debt_rollforward"]["opening_total_debt"] == 100
    assert latest["data"]["debt_rollforward"]["debt_issued"] == 20
    assert latest["data"]["debt_rollforward"]["debt_repaid"] == 8
    assert latest["data"]["capital_returns"]["gross_shareholder_payout"] == 17
    assert latest["data"]["capital_returns"]["net_shareholder_payout"] == 11
    assert latest["data"]["capital_returns"]["payout_mix"]["repurchases_share"] == 12 / 17
    assert latest["data"]["net_dilution_bridge"]["opening_shares"] == 100
    assert latest["data"]["net_dilution_bridge"]["shares_issued"] == 5
    assert latest["data"]["net_dilution_bridge"]["shares_repurchased"] == 3
    assert latest["data"]["net_dilution_bridge"]["ending_shares"] == 102
    assert latest["data"]["debt_maturity_ladder"]["meta"]["confidence_score"] == 1
    assert latest["data"]["lease_obligations"]["meta"]["confidence_score"] == 1


def test_snapshot_effective_at_prefers_filing_acceptance_datetime() -> None:
    snapshot = SimpleNamespace(
        filing_acceptance_at=datetime(2026, 2, 1, 13, 30, tzinfo=timezone.utc),
        period_end=date(2025, 12, 31),
    )

    assert snapshot_effective_at(snapshot) == datetime(2026, 2, 1, 13, 30, tzinfo=timezone.utc)
