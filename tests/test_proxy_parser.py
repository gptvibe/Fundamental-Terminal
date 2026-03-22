from __future__ import annotations

from datetime import date
from pathlib import Path

from app.services.proxy_parser import parse_proxy_filing_signals

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> str:
    return (FIXTURES_DIR / name).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Inline payload tests (deterministic, no file I/O)
# ---------------------------------------------------------------------------

def test_parse_proxy_filing_signals_extracts_core_fields():
    payload = """
    <html>
      <body>
        <h1>Annual Meeting of Shareholders will be held on May 20, 2026</h1>
        <p>Summary Compensation Table</p>
        <p>Chief Executive Officer $1,250,000</p>
        <p>Proposal 1 Election of Directors For 100,000 Against 5,000 Abstain 1,200 Broker Non-Votes 9,500</p>
        <p>Proposal 2 Advisory Vote on Executive Compensation For 88,000 Against 12,000 Abstain 500 Broker Non-Votes 15,000</p>
        <p>Proposal 3 Ratification of Auditors For 110,000 Against 2,000 Abstain 300</p>
        <p>Elect 9 directors.</p>
      </body>
    </html>
    """

    signals = parse_proxy_filing_signals(payload)

    assert signals.meeting_date == date(2026, 5, 20)
    assert signals.executive_comp_table_detected is True
    assert signals.vote_item_count == 3
    assert signals.board_nominee_count == 9
    assert signals.key_amounts
    assert signals.key_amounts[0] == 1250000.0
    assert len(signals.vote_outcomes) == 3
    assert signals.vote_outcomes[0].proposal_number == 1
    assert signals.vote_outcomes[0].for_votes == 100000
    assert signals.vote_outcomes[0].against_votes == 5000
    assert signals.vote_outcomes[0].abstain_votes == 1200
    assert signals.vote_outcomes[0].broker_non_votes == 9500


def test_parse_proxy_filing_signals_handles_sparse_content():
    signals = parse_proxy_filing_signals("<html><body>No governance markers.</body></html>")

    assert signals.meeting_date is None
    assert signals.executive_comp_table_detected is False
    assert signals.vote_item_count == 0
    assert signals.board_nominee_count is None
    assert signals.key_amounts == ()
    assert signals.vote_outcomes == ()
    assert signals.named_exec_rows == ()


# ---------------------------------------------------------------------------
# Fixture-backed DEF 14A tests
# ---------------------------------------------------------------------------

def test_def14a_standard_fixture_extracts_meeting_and_vote_outcomes():
    """def14a_standard.html — standard layout with multi-column comp table."""
    payload = load_fixture("def14a_standard.html")
    signals = parse_proxy_filing_signals(payload)

    assert signals.meeting_date == date(2025, 5, 22)
    assert signals.executive_comp_table_detected is True
    assert signals.vote_item_count == 3
    assert signals.board_nominee_count == 9

    # Three proposals should be detected with vote counts.
    assert len(signals.vote_outcomes) == 3
    prop1 = signals.vote_outcomes[0]
    assert prop1.proposal_number == 1
    assert prop1.for_votes == 210450000
    assert prop1.against_votes == 8320000
    assert prop1.abstain_votes == 2100000
    assert prop1.broker_non_votes == 18500000


def test_def14a_standard_fixture_extracts_exec_comp_rows():
    """def14a_standard.html — verifies HTML table exec comp extraction."""
    payload = load_fixture("def14a_standard.html")
    signals = parse_proxy_filing_signals(payload)

    assert signals.executive_comp_table_detected is True
    # Expect at least CEO and CFO rows extracted.
    assert len(signals.named_exec_rows) >= 2

    # The first row with non-None total_compensation should be the CEO.
    rows_with_total = [r for r in signals.named_exec_rows if r.total_compensation is not None]
    assert rows_with_total, "At least one row must have total_compensation"

    # CEO total for 2025 should be 14,985,000.
    ceo_rows = [r for r in signals.named_exec_rows if "Smith" in r.executive_name]
    assert ceo_rows, "CEO (Smith) row should be present"
    assert ceo_rows[0].salary == 1500000.0
    assert ceo_rows[0].total_compensation == 14985000.0


def test_def14a_tabular_fixture_extracts_exec_comp_with_dollar_signs():
    """def14a_tabular.html — tabular format with $-prefixed amounts."""
    payload = load_fixture("def14a_tabular.html")
    signals = parse_proxy_filing_signals(payload)

    assert signals.meeting_date == date(2024, 6, 18)
    assert signals.executive_comp_table_detected is True
    assert signals.vote_item_count == 4
    assert signals.board_nominee_count == 11

    # Exec rows should include the CEO.
    assert len(signals.named_exec_rows) >= 1
    ceo_rows = [r for r in signals.named_exec_rows if "Chen" in r.executive_name]
    assert ceo_rows, "CEO (Chen) row should be present"
    assert ceo_rows[0].total_compensation == 22885000.0


def test_def14a_sparse_fixture_returns_empty_signals():
    """def14a_sparse.html — minimal content, no parseable signals."""
    payload = load_fixture("def14a_sparse.html")
    signals = parse_proxy_filing_signals(payload)

    assert signals.meeting_date is None
    assert signals.executive_comp_table_detected is False
    assert signals.vote_item_count == 0
    assert signals.named_exec_rows == ()


def test_exec_comp_extraction_not_triggered_without_comp_table():
    """When 'summary compensation table' is absent, named_exec_rows must be empty."""
    payload = """
    <html><body>
    <p>Annual Meeting of Shareholders will be held on April 1, 2026</p>
    <table><tr><th>Name</th><th>Salary</th><th>Total</th></tr>
    <tr><td>Jane Doe</td><td>500,000</td><td>1,200,000</td></tr>
    </table>
    </body></html>
    """
    signals = parse_proxy_filing_signals(payload)
    # No "summary compensation table" keyword → extraction must not run.
    assert signals.named_exec_rows == ()
    assert signals.executive_comp_table_detected is False

