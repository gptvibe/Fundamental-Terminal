from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.executive_compensation import ExecutiveCompensation
    from app.models.proxy_vote_result import ProxyVoteResult


class ProxyStatement(Base):
    __tablename__ = "proxy_statements"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "accession_number",
            name="uq_proxy_statements_company_accession",
        ),
        Index("ix_proxy_statements_company_id", "company_id"),
        Index("ix_proxy_statements_company_filing_date", "company_id", "filing_date"),
        Index("ix_proxy_statements_company_filing_id", "company_id", "filing_date", "id"),
        Index("ix_proxy_statements_company_last_checked", "company_id", "last_checked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False)
    form: Mapped[str] = mapped_column(String(16), nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    meeting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    board_nominee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    vote_item_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    executive_comp_table_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    primary_document: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="proxy_statements")
    exec_comp_rows: Mapped[list["ExecutiveCompensation"]] = relationship(
        back_populates="proxy_statement",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ExecutiveCompensation.total_compensation.desc().nullslast()",
    )
    vote_results: Mapped[list["ProxyVoteResult"]] = relationship(
        back_populates="proxy_statement",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ProxyVoteResult.proposal_number.asc()",
    )
