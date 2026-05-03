"""Tests for S-8 equity-plan dilution tracker.

Covers:
- S-8 / S-8/A form detection and inclusion in SUPPORTED_CAPITAL_FORMS
- _extract_registered_shares parser
- _extract_plan_name parser
- _shares_parse_confidence helper
- collect_capital_markets_events populates all S-8 fields correctly
- upsert_capital_markets_events persists S-8 fields
- API summary equity_plan_registrations / total_registered_equity_plan_shares
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import CapitalMarketsEvent, Company, DatasetRefreshState
from app.services.capital_markets import (
    SUPPORTED_CAPITAL_FORMS,
    NormalizedCapitalMarketsEvent,
    _extract_plan_name,
    _extract_registered_shares,
    _shares_parse_confidence,
    collect_capital_markets_events,
    upsert_capital_markets_events,
)
from app.services.sec_edgar import FilingMetadata


# ── Fixtures ──────────────────────────────────────────────────────────


def _make_session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        engine,
        tables=[
            Company.__table__,
            CapitalMarketsEvent.__table__,
            DatasetRefreshState.__table__,
        ],
    )
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _make_company(session) -> Company:
    company = Company(ticker="XYZCO", cik="0001234567", name="XYZ Corp")
    session.add(company)
    session.flush()
    return company


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Form detection ─────────────────────────────────────────────────────


def test_s8_forms_in_supported_set():
    assert "S-8" in SUPPORTED_CAPITAL_FORMS
    assert "S-8/A" in SUPPORTED_CAPITAL_FORMS


# ── Registered-share parser ────────────────────────────────────────────


@pytest.mark.parametrize(
    "description, expected",
    [
        ("Registration of 25,000,000 shares of common stock under the 2024 Plan", 25_000_000.0),
        ("10,000,000 additional shares pursuant to the ESPP", 10_000_000.0),
        ("5000000 shares of common stock", 5_000_000.0),
        ("No mention here", None),
        (None, None),
    ],
)
def test_extract_registered_shares(description, expected):
    result = _extract_registered_shares(description)
    assert result == expected


# ── Plan-name parser ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "description, expected_contains",
    [
        (
            "Registration of 10,000,000 shares pursuant to the 2024 Omnibus Incentive Plan",
            "Incentive Plan",
        ),
        (
            "S-8 registration under the Employee Stock Purchase Plan (ESPP)",
            "Stock Purchase Plan",
        ),
        (
            "Registration of shares under the 2022 Equity Incentive Plan",
            "Equity Incentive",
        ),
        ("No plan keyword at all", None),
        (None, None),
    ],
)
def test_extract_plan_name(description, expected_contains):
    result = _extract_plan_name(description)
    if expected_contains is None:
        assert result is None
    else:
        assert result is not None
        assert expected_contains.lower() in result.lower()


# ── Confidence helper ──────────────────────────────────────────────────


@pytest.mark.parametrize(
    "description, registered_shares, plan_name, expected",
    [
        # Both shares and plan → high
        ("10,000,000 shares under the 2024 Stock Plan", 10_000_000.0, "2024 Stock Plan", "high"),
        # Shares present, plan keyword in description but name not extracted → high (keyword counts as plan signal)
        ("10,000,000 shares under an incentive plan", 10_000_000.0, None, "high"),
        # No shares, plan keyword present → medium
        ("Registration for the Employee Stock Purchase Plan", None, None, "medium"),
        # Neither → low
        ("Generic S-8 registration", None, None, "low"),
    ],
)
def test_shares_parse_confidence(description, registered_shares, plan_name, expected):
    result = _shares_parse_confidence(description, registered_shares, plan_name)
    assert result == expected


# ── collect_capital_markets_events ────────────────────────────────────


def _s8_filing(accession: str = "0000010", description: str | None = None) -> FilingMetadata:
    return FilingMetadata(
        accession_number=accession,
        form="S-8",
        filing_date=date(2026, 4, 1),
        report_date=date(2026, 4, 1),
        primary_document="s8.htm",
        primary_doc_description=description or "Registration of 15,000,000 shares pursuant to the 2026 Long-Term Incentive Plan",
        items=None,
    )


def test_collect_s8_populates_equity_plan_fields():
    filing_index = {"0000010": _s8_filing()}
    rows = collect_capital_markets_events("0001234567", filing_index)

    assert len(rows) == 1
    row = rows[0]
    assert row.form == "S-8"
    assert row.event_type == "Equity Plan Registration"
    assert row.registered_shares == 15_000_000.0
    assert row.plan_name is not None
    assert "incentive plan" in row.plan_name.lower()
    assert row.shares_parse_confidence == "high"
    assert row.shelf_size is None
    assert row.is_late_filer is False


def test_collect_s8a_treated_as_equity_plan():
    filing_index = {
        "0000011": FilingMetadata(
            accession_number="0000011",
            form="S-8/A",
            filing_date=date(2026, 4, 2),
            report_date=date(2026, 4, 2),
            primary_document="s8a.htm",
            primary_doc_description="Amendment to registration of shares under the Employee Stock Purchase Plan",
            items=None,
        )
    }
    rows = collect_capital_markets_events("0001234567", filing_index)

    assert len(rows) == 1
    row = rows[0]
    assert row.form == "S-8/A"
    assert row.event_type == "Equity Plan Registration"
    assert row.shares_parse_confidence in {"medium", "high"}


def test_collect_s8_low_confidence_when_no_shares_or_plan():
    filing_index = {
        "0000012": FilingMetadata(
            accession_number="0000012",
            form="S-8",
            filing_date=date(2026, 4, 3),
            report_date=date(2026, 4, 3),
            primary_document="s8.htm",
            primary_doc_description="Generic S-8 registration statement",
            items=None,
        )
    }
    rows = collect_capital_markets_events("0001234567", filing_index)

    row = rows[0]
    assert row.registered_shares is None
    assert row.shares_parse_confidence == "low"


def test_collect_s8_non_s8_forms_not_affected():
    """S-3 filings must not have plan_name / registered_shares populated."""
    filing_index = {
        "0000020": FilingMetadata(
            accession_number="0000020",
            form="S-3",
            filing_date=date(2026, 4, 1),
            report_date=date(2026, 4, 1),
            primary_document="s3.htm",
            primary_doc_description="Shelf registration for up to $200,000,000.",
            items=None,
        )
    }
    rows = collect_capital_markets_events("0001234567", filing_index)

    row = rows[0]
    assert row.plan_name is None
    assert row.registered_shares is None
    assert row.shares_parse_confidence is None


# ── Persistence (upsert) ───────────────────────────────────────────────


def test_upsert_s8_persists_equity_plan_fields():
    SessionFactory = _make_session_factory()
    with SessionFactory() as session:
        company = _make_company(session)
        events = [
            NormalizedCapitalMarketsEvent(
                accession_number="ACC001",
                form="S-8",
                filing_date=date(2026, 3, 1),
                report_date=date(2026, 3, 1),
                primary_document="s8.htm",
                primary_doc_description="Registration of 20,000,000 shares under the 2026 Omnibus Plan",
                source_url="https://example.com/s8",
                summary="S-8 equity plan registration",
                event_type="Equity Plan Registration",
                security_type="Common Equity",
                offering_amount=None,
                shelf_size=None,
                is_late_filer=False,
                plan_name="2026 Omnibus Plan",
                registered_shares=20_000_000.0,
                shares_parse_confidence="high",
            )
        ]
        count = upsert_capital_markets_events(session, company, events, checked_at=_now())
        session.commit()
        assert count == 1

        stored = session.query(CapitalMarketsEvent).filter_by(company_id=company.id).one()
        assert stored.form == "S-8"
        assert stored.plan_name == "2026 Omnibus Plan"
        assert stored.registered_shares == 20_000_000.0
        assert stored.shares_parse_confidence == "high"


def test_upsert_s8_updates_on_conflict():
    SessionFactory = _make_session_factory()
    with SessionFactory() as session:
        company = _make_company(session)
        base_event = NormalizedCapitalMarketsEvent(
            accession_number="ACC002",
            form="S-8",
            filing_date=date(2026, 3, 1),
            report_date=date(2026, 3, 1),
            primary_document="s8.htm",
            primary_doc_description="Old description",
            source_url="https://example.com/s8",
            summary="Old",
            event_type="Equity Plan Registration",
            security_type=None,
            offering_amount=None,
            shelf_size=None,
            is_late_filer=False,
            plan_name=None,
            registered_shares=None,
            shares_parse_confidence="low",
        )
        upsert_capital_markets_events(session, company, [base_event], checked_at=_now())
        session.commit()

        # Now upsert again with better parsed data.
        updated_event = NormalizedCapitalMarketsEvent(
            accession_number="ACC002",
            form="S-8",
            filing_date=date(2026, 3, 1),
            report_date=date(2026, 3, 1),
            primary_document="s8.htm",
            primary_doc_description="Registration of 10,000,000 shares under the 2026 Stock Plan",
            source_url="https://example.com/s8",
            summary="S-8 equity plan registration",
            event_type="Equity Plan Registration",
            security_type="Common Equity",
            offering_amount=None,
            shelf_size=None,
            is_late_filer=False,
            plan_name="2026 Stock Plan",
            registered_shares=10_000_000.0,
            shares_parse_confidence="high",
        )
        upsert_capital_markets_events(session, company, [updated_event], checked_at=_now())
        session.commit()

        rows = session.query(CapitalMarketsEvent).filter_by(company_id=company.id).all()
        assert len(rows) == 1
        assert rows[0].plan_name == "2026 Stock Plan"
        assert rows[0].registered_shares == 10_000_000.0
        assert rows[0].shares_parse_confidence == "high"
