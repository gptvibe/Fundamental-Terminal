from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class InsiderTrade(Base):
    __tablename__ = "insider_trades"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "accession_number",
            "insider_name",
            "transaction_index",
            name="uq_insider_trades_company_accession_name_index",
        ),
        Index("ix_insider_trades_company_id", "company_id"),
        Index("ix_insider_trades_company_transaction_date", "company_id", "transaction_date"),
        Index("ix_insider_trades_company_last_checked", "company_id", "last_checked"),
        Index("ix_insider_trades_company_action", "company_id", "action"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False)
    filing_type: Mapped[str] = mapped_column(String(16), nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    transaction_index: Mapped[int] = mapped_column(Integer, nullable=False)
    insider_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(120), nullable=True)
    transaction_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    shares: Mapped[float | None] = mapped_column(Float, nullable=True)
    price: Mapped[float | None] = mapped_column(Float, nullable=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    ownership_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    security_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_derivative: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    ownership_nature: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exercise_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    footnote_tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    transaction_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    is_10b5_1: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("false"))
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

    company: Mapped["Company"] = relationship(back_populates="insider_trades")
