from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SecFrameCompanyFact(Base):
    """One company value from a fetched SEC XBRL frame snapshot.

    Each row holds the value a single company reported for the concept covered
    by its parent SecFrameSnapshot.  CIK is the company identifier (no FK to
    companies because some CIKs may not be in our tracked universe).
    """

    __tablename__ = "sec_frame_company_facts"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id", "cik",
            name="uq_sec_frame_company_facts_snapshot_cik",
        ),
        Index("ix_sec_frame_company_facts_snapshot", "snapshot_id"),
        Index("ix_sec_frame_company_facts_cik", "cik"),
        Index("ix_sec_frame_company_facts_snapshot_cik", "snapshot_id", "cik"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("sec_frame_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    cik: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_name: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    accession_number: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
