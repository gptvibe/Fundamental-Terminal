from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class WatchlistAlert(Base):
    """Track alert state for watchlist tickers to prevent repeated alert notifications.

    Stores deduplication markers for various alert types so users don't repeatedly
    see the same alert. Tied to specific filing events or source state changes.
    """
    __tablename__ = "watchlist_alerts"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "alert_type",
            "source_filing_accession",
            name="uq_watchlist_alerts_company_type_accession",
        ),
        Index("ix_watchlist_alerts_company_id", "company_id"),
        Index("ix_watchlist_alerts_company_created", "company_id", "created_at"),
        Index("ix_watchlist_alerts_company_type", "company_id", "alert_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)

    # Alert classification: what type of event triggered this
    alert_type: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        comment="10-K, 10-Q, 8-K, proxy, form-4, amendment, late-filing, stale-data",
    )

    # Link to the filing that triggered the alert (if applicable)
    source_filing_accession: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_filing_form: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Tracking for deduplication
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    company: Mapped["Company"] = relationship(back_populates="watchlist_alerts")
