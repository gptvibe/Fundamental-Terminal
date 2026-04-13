from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class CompanyChartsDashboardSnapshot(Base):
    __tablename__ = "company_charts_dashboard_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "as_of_key",
            "schema_version",
            name="uq_company_charts_dashboard_snapshots_company_asof_schema",
        ),
        Index("ix_company_charts_dashboard_snapshots_company_id", "company_id"),
        Index("ix_company_charts_dashboard_snapshots_company_as_of", "company_id", "as_of_key"),
        Index("ix_company_charts_dashboard_snapshots_company_last_checked", "company_id", "last_checked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    as_of_key: Mapped[str] = mapped_column(String(64), nullable=False, server_default="latest")
    as_of_value: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="charts_dashboard_snapshots")
