from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.beneficial_ownership_report import BeneficialOwnershipReport
    from app.models.capital_markets_event import CapitalMarketsEvent
    from app.models.derived_metric_point import DerivedMetricPoint
    from app.models.dataset_refresh_state import DatasetRefreshState
    from app.models.earnings_model_point import EarningsModelPoint
    from app.models.executive_compensation import ExecutiveCompensation
    from app.models.filing_event import FilingEvent
    from app.models.financial_statement import FinancialStatement
    from app.models.form144_filing import Form144Filing
    from app.models.earnings_release import EarningsRelease
    from app.models.insider_trade import InsiderTrade
    from app.models.institutional_holding import InstitutionalHolding
    from app.models.model_run import ModelRun
    from app.models.price_history import PriceHistory
    from app.models.proxy_statement import ProxyStatement
    from app.models.proxy_vote_result import ProxyVoteResult


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
    filing_events_last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capital_markets_last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    form144_filings_last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    earnings_last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proxy_statements_last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
    filing_events: Mapped[list["FilingEvent"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    capital_markets_events: Mapped[list["CapitalMarketsEvent"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    form144_filings: Mapped[list["Form144Filing"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    earnings_releases: Mapped[list["EarningsRelease"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    proxy_statements: Mapped[list["ProxyStatement"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    exec_comp_rows: Mapped[list["ExecutiveCompensation"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    proxy_vote_results: Mapped[list["ProxyVoteResult"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    derived_metric_points: Mapped[list["DerivedMetricPoint"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    earnings_model_points: Mapped[list["EarningsModelPoint"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    dataset_refresh_states: Mapped[list["DatasetRefreshState"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
