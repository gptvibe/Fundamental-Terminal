from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.proxy_statement import ProxyStatement


class ExecutiveCompensation(Base):
    __tablename__ = "executive_compensation"
    __table_args__ = (
        UniqueConstraint(
            "proxy_statement_id",
            "executive_name",
            "fiscal_year",
            name="uq_exec_comp_stmt_name_year",
        ),
        Index("ix_executive_compensation_company_id", "company_id"),
        Index("ix_executive_compensation_company_year_total", "company_id", "fiscal_year", "total_compensation"),
        Index("ix_executive_compensation_proxy_statement_id", "proxy_statement_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    proxy_statement_id: Mapped[int] = mapped_column(
        ForeignKey("proxy_statements.id", ondelete="CASCADE"), nullable=False
    )
    fiscal_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    executive_name: Mapped[str] = mapped_column(String(200), nullable=False)
    executive_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    salary: Mapped[float | None] = mapped_column(Float, nullable=True)
    bonus: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_awards: Mapped[float | None] = mapped_column(Float, nullable=True)
    option_awards: Mapped[float | None] = mapped_column(Float, nullable=True)
    non_equity_incentive: Mapped[float | None] = mapped_column(Float, nullable=True)
    other_compensation: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_compensation: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="exec_comp_rows")
    proxy_statement: Mapped["ProxyStatement"] = relationship(back_populates="exec_comp_rows")
