from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.beneficial_ownership_report import BeneficialOwnershipReport


class BeneficialOwnershipParty(Base):
    __tablename__ = "beneficial_ownership_parties"
    __table_args__ = (
        Index("ix_beneficial_ownership_parties_report_id", "report_id"),
        Index("ix_beneficial_ownership_parties_filer_cik", "filer_cik"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("beneficial_ownership_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    party_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    filer_cik: Mapped[str | None] = mapped_column(String(10), nullable=True)
    shares_owned: Mapped[float | None] = mapped_column(Float, nullable=True)
    percent_owned: Mapped[float | None] = mapped_column(Float, nullable=True)
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purpose: Mapped[str | None] = mapped_column(String(500), nullable=True)

    report: Mapped["BeneficialOwnershipReport"] = relationship(back_populates="parties")