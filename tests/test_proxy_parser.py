from __future__ import annotations

from datetime import date

from app.services.proxy_parser import parse_proxy_filing_signals


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
