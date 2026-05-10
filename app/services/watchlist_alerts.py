"""Watchlist alert detection service.

Detects and manages various alert conditions for watchlist companies including:
- New SEC filings (10-K, 10-Q, 8-K, proxy, Form 4)
- Amended filings
- Late filing notices
- Stale source data

Alerts are deduplicated by company, alert_type, and source_filing_accession to prevent
repeated notifications for the same event.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Company, FilingEvent, WatchlistAlert, ProxyStatement, InsiderTrade

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# Alert types
ALERT_TYPE_10K = "10-K"
ALERT_TYPE_10Q = "10-Q"
ALERT_TYPE_8K = "8-K"
ALERT_TYPE_PROXY = "proxy"
ALERT_TYPE_FORM4 = "form-4"
ALERT_TYPE_AMENDMENT = "amendment"
ALERT_TYPE_LATE_FILING = "late-filing"
ALERT_TYPE_STALE_DATA = "stale-data"

ALL_ALERT_TYPES = [
    ALERT_TYPE_10K,
    ALERT_TYPE_10Q,
    ALERT_TYPE_8K,
    ALERT_TYPE_PROXY,
    ALERT_TYPE_FORM4,
    ALERT_TYPE_AMENDMENT,
    ALERT_TYPE_LATE_FILING,
    ALERT_TYPE_STALE_DATA,
]

# Stale data thresholds (days since last update)
STALE_FILINGS_THRESHOLD_DAYS = 30
STALE_INSIDER_THRESHOLD_DAYS = 30
STALE_PROXY_THRESHOLD_DAYS = 60


def detect_and_create_alerts(session: Session, company_id: int) -> list[WatchlistAlert]:
    """Detect and create new alerts for a watchlist company.

    Args:
        session: Database session
        company_id: ID of the company to check

    Returns:
        List of newly created alerts (not including pre-existing ones)
    """
    company = session.query(Company).filter(Company.id == company_id).first()
    if not company:
        return []

    new_alerts: list[WatchlistAlert] = []

    # Get existing active alerts (not dismissed)
    existing_alerts = session.query(WatchlistAlert).filter(
        WatchlistAlert.company_id == company_id,
        WatchlistAlert.dismissed_at.is_(None),
    ).all()
    existing_keys = {(a.alert_type, a.source_filing_accession) for a in existing_alerts}

    # Detect new 10-K filings
    for accession in _get_recent_filing_accessions(session, company_id, "10-K", days=30):
        key = (ALERT_TYPE_10K, accession)
        if key not in existing_keys:
            alert = WatchlistAlert(
                company_id=company_id,
                alert_type=ALERT_TYPE_10K,
                source_filing_accession=accession,
                source_filing_form="10-K",
            )
            session.add(alert)
            new_alerts.append(alert)
            existing_keys.add(key)

    # Detect new 10-Q filings
    for accession in _get_recent_filing_accessions(session, company_id, "10-Q", days=30):
        key = (ALERT_TYPE_10Q, accession)
        if key not in existing_keys:
            alert = WatchlistAlert(
                company_id=company_id,
                alert_type=ALERT_TYPE_10Q,
                source_filing_accession=accession,
                source_filing_form="10-Q",
            )
            session.add(alert)
            new_alerts.append(alert)
            existing_keys.add(key)

    # Detect new 8-K filings
    for accession in _get_recent_filing_accessions(session, company_id, "8-K", days=30):
        key = (ALERT_TYPE_8K, accession)
        if key not in existing_keys:
            alert = WatchlistAlert(
                company_id=company_id,
                alert_type=ALERT_TYPE_8K,
                source_filing_accession=accession,
                source_filing_form="8-K",
            )
            session.add(alert)
            new_alerts.append(alert)
            existing_keys.add(key)

    # Detect new proxy filings
    for accession in _get_recent_proxy_accessions(session, company_id, days=30):
        key = (ALERT_TYPE_PROXY, accession)
        if key not in existing_keys:
            alert = WatchlistAlert(
                company_id=company_id,
                alert_type=ALERT_TYPE_PROXY,
                source_filing_accession=accession,
                source_filing_form="PROXY",
            )
            session.add(alert)
            new_alerts.append(alert)
            existing_keys.add(key)

    # Detect new Form 4 filings
    for accession in _get_recent_form4_accessions(session, company_id, days=30):
        key = (ALERT_TYPE_FORM4, accession)
        if key not in existing_keys:
            alert = WatchlistAlert(
                company_id=company_id,
                alert_type=ALERT_TYPE_FORM4,
                source_filing_accession=accession,
                source_filing_form="4",
            )
            session.add(alert)
            new_alerts.append(alert)
            existing_keys.add(key)

    # Detect amended filings
    for accession, form in _get_recent_amended_filings(session, company_id, days=30):
        key = (ALERT_TYPE_AMENDMENT, accession)
        if key not in existing_keys:
            alert = WatchlistAlert(
                company_id=company_id,
                alert_type=ALERT_TYPE_AMENDMENT,
                source_filing_accession=accession,
                source_filing_form=form,
            )
            session.add(alert)
            new_alerts.append(alert)
            existing_keys.add(key)

    # Detect late filing notices
    for accession, form in _get_recent_late_filings(session, company_id, days=30):
        key = (ALERT_TYPE_LATE_FILING, accession)
        if key not in existing_keys:
            alert = WatchlistAlert(
                company_id=company_id,
                alert_type=ALERT_TYPE_LATE_FILING,
                source_filing_accession=accession,
                source_filing_form=form,
            )
            session.add(alert)
            new_alerts.append(alert)
            existing_keys.add(key)

    # Detect stale data (one alert per stale_data type, no accession)
    if _has_stale_filings_data(session, company_id):
        key = (ALERT_TYPE_STALE_DATA, None)
        if key not in existing_keys:
            alert = WatchlistAlert(
                company_id=company_id,
                alert_type=ALERT_TYPE_STALE_DATA,
                source_filing_accession=None,
                source_filing_form=None,
            )
            session.add(alert)
            new_alerts.append(alert)

    return new_alerts


def dismiss_alert(session: Session, alert_id: int) -> bool:
    """Dismiss an alert so it won't be shown to the user."""
    alert = session.query(WatchlistAlert).filter(WatchlistAlert.id == alert_id).first()
    if not alert:
        return False

    alert.dismissed_at = datetime.now(timezone.utc)
    return True


def get_active_alerts(
    session: Session,
    company_id: int,
    alert_types: list[str] | None = None,
) -> list[WatchlistAlert]:
    """Get active (not dismissed) alerts for a company, optionally filtered by type."""
    query = select(WatchlistAlert).where(
        WatchlistAlert.company_id == company_id,
        WatchlistAlert.dismissed_at.is_(None),
    )

    if alert_types:
        query = query.where(WatchlistAlert.alert_type.in_(alert_types))

    query = query.order_by(WatchlistAlert.created_at.desc())
    return session.scalars(query).all()


def _get_recent_filing_accessions(
    session: Session,
    company_id: int,
    form: str,
    days: int = 30,
) -> list[str]:
    """Get accession numbers for recent filings of a specific form."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(FilingEvent.accession_number).where(
        FilingEvent.company_id == company_id,
        FilingEvent.form == form,
        FilingEvent.filing_date.isnot(None),
        FilingEvent.last_updated >= cutoff,
        FilingEvent.is_amendment.is_(False),
    ).order_by(FilingEvent.filing_date.desc())

    return session.scalars(stmt).all()


def _get_recent_proxy_accessions(
    session: Session,
    company_id: int,
    days: int = 30,
) -> list[str]:
    """Get accession numbers for recent proxy statements."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(ProxyStatement.accession_number).where(
        ProxyStatement.company_id == company_id,
        ProxyStatement.filing_date.isnot(None),
        ProxyStatement.last_updated >= cutoff,
    ).order_by(ProxyStatement.filing_date.desc())

    return session.scalars(stmt).all()


def _get_recent_form4_accessions(
    session: Session,
    company_id: int,
    days: int = 30,
) -> list[str]:
    """Get accession numbers for recent Form 4 filings."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(InsiderTrade.accession_number).where(
        InsiderTrade.company_id == company_id,
        InsiderTrade.filing_date.isnot(None),
        InsiderTrade.last_updated >= cutoff,
    ).order_by(InsiderTrade.filing_date.desc())

    return session.scalars(stmt).all()


def _get_recent_amended_filings(
    session: Session,
    company_id: int,
    days: int = 30,
) -> list[tuple[str, str]]:
    """Get (accession, form) tuples for recent amended filings."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(FilingEvent.accession_number, FilingEvent.form).where(
        FilingEvent.company_id == company_id,
        FilingEvent.is_amendment.is_(True),
        FilingEvent.filing_date.isnot(None),
        FilingEvent.last_updated >= cutoff,
    ).order_by(FilingEvent.filing_date.desc())

    return session.execute(stmt).all()


def _get_recent_late_filings(
    session: Session,
    company_id: int,
    days: int = 30,
) -> list[tuple[str, str]]:
    """Get (accession, form) tuples for recent late filing notices."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    stmt = select(FilingEvent.accession_number, FilingEvent.form).where(
        FilingEvent.company_id == company_id,
        FilingEvent.is_late_filing.is_(True),
        FilingEvent.filing_date.isnot(None),
        FilingEvent.last_updated >= cutoff,
    ).order_by(FilingEvent.filing_date.desc())

    return session.execute(stmt).all()


def _has_stale_filings_data(session: Session, company_id: int) -> bool:
    """Check if filing data is stale (no recent updates)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=STALE_FILINGS_THRESHOLD_DAYS)
    stmt = select(FilingEvent).where(
        FilingEvent.company_id == company_id,
        FilingEvent.last_checked >= cutoff,
    ).limit(1)

    result = session.scalars(stmt).first()
    return result is None
