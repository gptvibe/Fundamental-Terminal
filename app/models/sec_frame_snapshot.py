from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SecFrameSnapshot(Base):
    """One fetched SEC XBRL frame for a single concept + period.

    A frame represents the cross-company data the SEC publishes for a specific
    US-GAAP tag in a specific calendar period (e.g. CY2024Q4 for all companies
    that filed a 10-Q with quarterly revenue in Q4 2024).
    """

    __tablename__ = "sec_frame_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "concept_key", "period_label", "tag",
            name="uq_sec_frame_snapshots_concept_period_tag",
        ),
        Index("ix_sec_frame_snapshots_concept_period", "concept_key", "period_label"),
        Index("ix_sec_frame_snapshots_fiscal_year", "fiscal_year", "fiscal_quarter"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    concept_key: Mapped[str] = mapped_column(String(64), nullable=False)
    taxonomy: Mapped[str] = mapped_column(String(40), nullable=False, default="us-gaap")
    tag: Mapped[str] = mapped_column(String(128), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    period_label: Mapped[str] = mapped_column(String(20), nullable=False)
    period_type: Mapped[str] = mapped_column(String(20), nullable=False)
    fiscal_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_quarter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
