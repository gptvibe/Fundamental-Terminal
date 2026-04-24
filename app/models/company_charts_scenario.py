from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class CompanyChartsScenario(Base):
    __tablename__ = "company_charts_scenarios"
    __table_args__ = (
        Index("ix_company_charts_scenarios_company_id", "company_id"),
        Index("ix_company_charts_scenarios_company_updated_at", "company_id", "updated_at"),
        Index("ix_company_charts_scenarios_company_owner", "company_id", "owner_key"),
        Index("ix_company_charts_scenarios_company_visibility", "company_id", "visibility"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    owner_key: Mapped[str | None] = mapped_column(String(160), nullable=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="private")
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="sec_base_forecast")
    schema_version: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    override_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    forecast_year: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    as_of: Mapped[str | None] = mapped_column(String(64), nullable=True)
    overrides: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    metrics: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    cloned_from_scenario_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    company: Mapped["Company"] = relationship(back_populates="charts_scenarios")
