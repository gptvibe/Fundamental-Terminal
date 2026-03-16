from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.beneficial_ownership_report import BeneficialOwnershipReport
    from app.models.financial_statement import FinancialStatement
    from app.models.insider_trade import InsiderTrade
    from app.models.institutional_holding import InstitutionalHolding
    from app.models.model_run import ModelRun
    from app.models.price_history import PriceHistory


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        Index("ix_companies_ticker", "ticker", unique=True),
        Index("ix_companies_cik", "cik", unique=True),
        Index("ix_companies_ticker_cik", "ticker", "cik"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(16), nullable=False)
    cik: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    market_sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    market_industry: Mapped[str | None] = mapped_column(String(150), nullable=True)
    insider_trades_last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    institutional_holdings_last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    beneficial_ownership_last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    financial_statements: Mapped[list["FinancialStatement"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    model_runs: Mapped[list["ModelRun"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    price_history: Mapped[list["PriceHistory"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    insider_trades: Mapped[list["InsiderTrade"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    institutional_holdings: Mapped[list["InstitutionalHolding"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    beneficial_ownership_reports: Mapped[list["BeneficialOwnershipReport"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
