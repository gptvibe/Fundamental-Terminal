from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.refresh_job import RefreshJob


class RefreshJobEvent(Base):
    __tablename__ = "refresh_job_events"
    __table_args__ = (
        UniqueConstraint("refresh_job_id", "sequence", name="uq_refresh_job_events_job_sequence"),
        Index("ix_refresh_job_events_job_sequence", "refresh_job_id", "sequence"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    refresh_job_id: Mapped[int] = mapped_column(ForeignKey("refresh_jobs.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    stage: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    level: Mapped[str] = mapped_column(String(16), nullable=False)

    job: Mapped["RefreshJob"] = relationship(back_populates="events")