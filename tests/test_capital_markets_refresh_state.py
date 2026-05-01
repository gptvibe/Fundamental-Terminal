from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import CapitalMarketsEvent, Company, DatasetRefreshState
from app.services.cache_queries import get_company_capital_markets_cache_status
from app.services.capital_markets import (
    NormalizedCapitalMarketsEvent,
    upsert_capital_markets_events,
)
from app.services.refresh_state import (
    _normalize_datetime,
    get_dataset_state,
    mark_dataset_checked,
)
from app.services.sec_edgar import _latest_capital_markets_last_checked


def _make_session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    # Only create tables under test — Base.metadata includes JSONB models
    # that SQLite cannot compile.
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
    company = Company(ticker="AAPL", cik="0000320193", name="Apple Inc.")
    session.add(company)
    session.flush()
    return company


def _make_event(session, company: Company, checked_at: datetime) -> CapitalMarketsEvent:
    event = CapitalMarketsEvent(
        company_id=company.id,
        accession_number="0000001",
        form="S-3",
        filing_date=checked_at.date(),
        report_date=checked_at.date(),
        primary_document="s3.htm",
        primary_doc_description="Registration statement.",
        source_url="https://example.com/doc",
        summary="S-3 Registration; Common Equity; $500,000,000.",
        last_checked=checked_at,
    )
    session.add(event)
    session.flush()
    return event


def _recent() -> datetime:
    """A just-now timestamp guaranteed to be considered fresh."""
    return datetime.now(timezone.utc)


def _assert_datetimes_equal(a: datetime | None, b: datetime | None) -> None:
    """Compare datetimes, normalizing away tzinfo differences from SQLite."""
    assert _normalize_datetime(a) == _normalize_datetime(b)


# ── Write path ────────────────────────────────────────────────────────


def test_upsert_writes_dataset_refresh_state():
    factory = _make_session_factory()
    session = factory()
    checked_at = _recent()
    company = _make_company(session)

    event = NormalizedCapitalMarketsEvent(
        accession_number="0000001",
        form="S-3",
        filing_date=checked_at.date(),
        report_date=checked_at.date(),
        primary_document="s3.htm",
        primary_doc_description="Shelf registration.",
        source_url="https://example.com/doc",
        summary="S-3 Registration.",
    )

    upsert_capital_markets_events(
        session,
        company,
        [event],
        checked_at=checked_at,
    )
    session.commit()

    # DatasetRefreshState must be set
    state = get_dataset_state(session, company.id, "capital_markets")
    assert state is not None
    _assert_datetimes_equal(state.last_checked, checked_at)
    _assert_datetimes_equal(state.last_success, checked_at)
    assert state.failure_count == 0


# ── Read path: cache_queries ──────────────────────────────────────────


def test_cache_status_returns_fresh_from_dataset_state():
    factory = _make_session_factory()
    session = factory()
    checked_at = _recent()
    company = _make_company(session)

    mark_dataset_checked(
        session,
        company.id,
        "capital_markets",
        checked_at=checked_at,
        success=True,
    )
    session.commit()

    last_checked, cache_state = get_company_capital_markets_cache_status(session, company)
    assert cache_state == "fresh"
    _assert_datetimes_equal(last_checked, checked_at)


def test_cache_status_backfills_from_child_table():
    factory = _make_session_factory()
    session = factory()
    checked_at = _recent()
    company = _make_company(session)
    _make_event(session, company, checked_at)
    session.commit()

    last_checked, cache_state = get_company_capital_markets_cache_status(session, company)
    _assert_datetimes_equal(last_checked, checked_at)
    # After backfill, DatasetRefreshState should exist
    state = get_dataset_state(session, company.id, "capital_markets")
    assert state is not None
    _assert_datetimes_equal(state.last_checked, checked_at)


def test_cache_status_missing_when_no_data():
    factory = _make_session_factory()
    session = factory()
    company = _make_company(session)
    session.commit()

    last_checked, cache_state = get_company_capital_markets_cache_status(session, company)
    assert last_checked is None
    assert cache_state == "missing"


# ── Read path: sec_edgar ──────────────────────────────────────────────


def test_latest_last_checked_returns_from_dataset_state():
    factory = _make_session_factory()
    session = factory()
    checked_at = _recent()
    company = _make_company(session)

    mark_dataset_checked(
        session,
        company.id,
        "capital_markets",
        checked_at=checked_at,
        success=True,
    )
    session.commit()

    result = _latest_capital_markets_last_checked(session, company)
    _assert_datetimes_equal(result, checked_at)


def test_latest_last_checked_backfills_from_child_table():
    factory = _make_session_factory()
    session = factory()
    checked_at = _recent()
    company = _make_company(session)
    _make_event(session, company, checked_at)
    session.commit()

    result = _latest_capital_markets_last_checked(session, company)
    _assert_datetimes_equal(result, checked_at)

    # Backfill should have populated DatasetRefreshState
    state = get_dataset_state(session, company.id, "capital_markets")
    assert state is not None
    _assert_datetimes_equal(state.last_checked, checked_at)


def test_latest_last_checked_none_when_no_data():
    factory = _make_session_factory()
    session = factory()
    company = _make_company(session)
    session.commit()

    result = _latest_capital_markets_last_checked(session, company)
    assert result is None


# ── Stale detection ───────────────────────────────────────────────────


def test_cache_state_is_stale_when_past_freshness_window():
    factory = _make_session_factory()
    session = factory()
    old_checked_at = datetime(2020, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    company = _make_company(session)

    mark_dataset_checked(
        session,
        company.id,
        "capital_markets",
        checked_at=old_checked_at,
        success=True,
    )
    session.commit()

    last_checked, cache_state = get_company_capital_markets_cache_status(session, company)
    assert cache_state == "stale"
    _assert_datetimes_equal(last_checked, old_checked_at)
