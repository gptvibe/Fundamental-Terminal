from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import app.services.institutional_holdings as institutional_module
from app.services.institutional_holdings import _latest_n_13f_filings, _manager_candidates


def test_latest_n_13f_filings_returns_distinct_reporting_dates_in_desc_order():
    submissions = {
        "filings": {
            "recent": {
                "form": ["13F-HR", "13F-HR/A", "13F-HR", "13F-HR"],
                "accessionNumber": ["a1", "a2", "a3", "a4"],
                "filingDate": ["2026-02-15", "2026-02-20", "2025-11-15", "2025-08-14"],
                "reportDate": ["2025-12-31", "2025-12-31", "2025-09-30", "2025-06-30"],
                "primaryDocument": ["d1.xml", "d2.xml", "d3.xml", "d4.xml"],
            }
        }
    }

    rows = _latest_n_13f_filings(submissions, limit=4)

    assert [row.report_date.isoformat() for row in rows] == ["2025-12-31", "2025-09-30", "2025-06-30"]
    assert [row.accession_number for row in rows] == ["a2", "a3", "a4"]
    assert rows[0].form == "13F-HR/A"


def test_latest_n_13f_filings_respects_limit():
    submissions = {
        "filings": {
            "recent": {
                "form": ["13F-HR", "13F-HR", "13F-HR", "13F-HR"],
                "accessionNumber": ["b1", "b2", "b3", "b4"],
                "filingDate": ["2026-02-15", "2025-11-15", "2025-08-15", "2025-05-15"],
                "reportDate": ["2025-12-31", "2025-09-30", "2025-06-30", "2025-03-31"],
                "primaryDocument": ["d1.xml", "d2.xml", "d3.xml", "d4.xml"],
            }
        }
    }

    rows = _latest_n_13f_filings(submissions, limit=2)

    assert len(rows) == 2
    assert [row.accession_number for row in rows] == ["b1", "b2"]


def test_extract_company_snapshot_parses_put_call_discretion_and_voting(monkeypatch):
    xml_payload = """
    <informationTable>
        <infoTable>
            <nameOfIssuer>Apple Inc</nameOfIssuer>
            <value>150000</value>
            <sshPrnamt>900</sshPrnamt>
            <putCall>CALL</putCall>
            <investmentDiscretion>SOLE</investmentDiscretion>
            <votingAuthority>
                <Sole>800</Sole>
                <Shared>80</Shared>
                <None>20</None>
            </votingAuthority>
        </infoTable>
    </informationTable>
    """

    monkeypatch.setattr(
        institutional_module,
        "_load_information_table_xml",
        lambda *_args, **_kwargs: ("https://www.sec.gov/example.xml", xml_payload),
    )

    filing = institutional_module.FilingMetadata(
        accession_number="0000950123-26-001234",
        form="13F-HR",
        filing_date=date(2026, 2, 14),
        report_date=date(2025, 12, 31),
        primary_document="infotable.xml",
    )
    fund = SimpleNamespace(fund_name="Example Capital", fund_cik="0000123456")

    snapshot = institutional_module._extract_company_snapshot(
        client=None,  # mocked at _load_information_table_xml
        fund=fund,
        company_tokens={"apple"},
        filing=filing,
    )

    assert snapshot is not None
    assert snapshot.put_call == "CALL"
    assert snapshot.investment_discretion == "SOLE"
    assert snapshot.voting_authority_sole == 800
    assert snapshot.voting_authority_shared == 80
    assert snapshot.voting_authority_none == 20


def test_manager_candidates_curated_mode_does_not_include_extras(monkeypatch):
    monkeypatch.setattr(
        institutional_module,
        "settings",
        SimpleNamespace(sec_13f_universe_mode="curated", sec_13f_extra_managers=("Imaginary Capital",)),
    )

    candidates = _manager_candidates(limit=3)

    assert len(candidates) == 3
    assert all(manager != "Imaginary Capital" for _, manager, _ in candidates)
    assert all(source == "curated" for _, _, source in candidates)


def test_manager_candidates_expanded_mode_includes_extras_when_space_allows(monkeypatch):
    monkeypatch.setattr(
        institutional_module,
        "settings",
        SimpleNamespace(sec_13f_universe_mode="expanded", sec_13f_extra_managers=("Imaginary Capital",)),
    )

    candidates = _manager_candidates(limit=len(institutional_module.CURATED_13F_MANAGERS) + 1)

    assert any(manager == "Imaginary Capital" for _, manager, _ in candidates)
    assert any(source == "expanded" for _, manager, source in candidates if manager == "Imaginary Capital")
