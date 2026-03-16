from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.institutional_fund import InstitutionalFund


class InstitutionalHolding(Base):
    __tablename__ = "institutional_holdings"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "fund_id",
            "reporting_date",
            name="uq_institutional_holdings_company_fund_reporting_date",
        ),
        Index("ix_institutional_holdings_company_id", "company_id"),
        Index("ix_institutional_holdings_fund_id", "fund_id"),
        Index("ix_institutional_holdings_company_reporting_date", "company_id", "reporting_date"),
        Index("ix_institutional_holdings_company_last_checked", "company_id", "last_checked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    fund_id: Mapped[int] = mapped_column(
        ForeignKey("institutional_funds.id", ondelete="CASCADE"),
        nullable=False,
    )
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False)
    reporting_date: Mapped[date] = mapped_column(Date, nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    shares_held: Mapped[float | None] = mapped_column(Float, nullable=True)
    market_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_in_shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    percent_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    portfolio_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    put_call: Mapped[str | None] = mapped_column(String(16), nullable=True)
    investment_discretion: Mapped[str | None] = mapped_column(String(32), nullable=True)
    voting_authority_sole: Mapped[float | None] = mapped_column(Float, nullable=True)
    voting_authority_shared: Mapped[float | None] = mapped_column(Float, nullable=True)
    voting_authority_none: Mapped[float | None] = mapped_column(Float, nullable=True)
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

    company: Mapped["Company"] = relationship(back_populates="institutional_holdings")
    fund: Mapped["InstitutionalFund"] = relationship(back_populates="holdings")
