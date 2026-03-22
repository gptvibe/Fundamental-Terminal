from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.proxy_statement import ProxyStatement


class ProxyVoteResult(Base):
    __tablename__ = "proxy_vote_results"
    __table_args__ = (
        UniqueConstraint(
            "proxy_statement_id",
            "proposal_number",
            name="uq_proxy_vote_results_stmt_proposal",
        ),
        Index("ix_proxy_vote_results_company_id", "company_id"),
        Index("ix_proxy_vote_results_proxy_statement_id", "proxy_statement_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    proxy_statement_id: Mapped[int] = mapped_column(
        ForeignKey("proxy_statements.id", ondelete="CASCADE"), nullable=False
    )
    proposal_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    for_votes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    against_votes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    abstain_votes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    broker_non_votes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="proxy_vote_results")
    proxy_statement: Mapped["ProxyStatement"] = relationship(back_populates="vote_results")
