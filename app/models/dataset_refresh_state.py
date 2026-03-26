from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class DatasetRefreshState(Base):
    __tablename__ = "dataset_refresh_state"
    __table_args__ = (
        UniqueConstraint("company_id", "dataset", name="uq_dataset_refresh_state_company_dataset"),
        Index("ix_dataset_refresh_state_company_dataset", "company_id", "dataset"),
        Index("ix_dataset_refresh_state_deadline", "dataset", "freshness_deadline"),
        Index("ix_dataset_refresh_state_active_job", "active_job_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    dataset: Mapped[str] = mapped_column(String(64), nullable=False)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    freshness_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_version_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    company: Mapped["Company"] = relationship(back_populates="dataset_refresh_states")
