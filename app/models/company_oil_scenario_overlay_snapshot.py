from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class CompanyOilScenarioOverlaySnapshot(Base):
    __tablename__ = "company_oil_scenario_overlay_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "snapshot_date",
            name="uq_company_oil_overlay_snapshots_company_date",
        ),
        Index("ix_company_oil_overlay_snapshots_company", "company_id"),
        Index(
            "ix_company_oil_overlay_snapshots_company_date",
            "company_id",
            "snapshot_date",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    snapshot_date: Mapped[date] = mapped_column(Date(), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    is_stale: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    company: Mapped["Company"] = relationship(back_populates="oil_scenario_overlay_snapshots")