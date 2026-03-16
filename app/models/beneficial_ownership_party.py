from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.beneficial_ownership_report import BeneficialOwnershipReport


class BeneficialOwnershipParty(Base):
    __tablename__ = "beneficial_ownership_parties"
    __table_args__ = (
        Index("ix_beneficial_ownership_parties_report_id", "report_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(
        ForeignKey("beneficial_ownership_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    party_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(100), nullable=True)

    report: Mapped["BeneficialOwnershipReport"] = relationship(back_populates="parties")