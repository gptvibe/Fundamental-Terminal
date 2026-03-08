from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class FinancialStatement(Base):
    __tablename__ = "financial_statements"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "period_start",
            "period_end",
            "filing_type",
            "statement_type",
            "source",
            name="uq_financial_statements_company_period_type_source",
        ),
        Index("ix_financial_statements_company_id", "company_id"),
        Index("ix_financial_statements_company_last_checked", "company_id", "last_checked"),
        Index("ix_financial_statements_company_period_end", "company_id", "period_end"),
        Index("ix_financial_statements_statement_type", "statement_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    filing_type: Mapped[str] = mapped_column(String(32), nullable=False)
    statement_type: Mapped[str] = mapped_column(String(32), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    last_checked: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    company: Mapped["Company"] = relationship(back_populates="financial_statements")
