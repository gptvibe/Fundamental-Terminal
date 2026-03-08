from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.institutional_holding import InstitutionalHolding


class InstitutionalFund(Base):
    __tablename__ = "institutional_funds"
    __table_args__ = (
        Index("ix_institutional_funds_fund_cik", "fund_cik", unique=True),
        Index("ix_institutional_funds_fund_manager", "fund_manager"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_cik: Mapped[str] = mapped_column(String(20), nullable=False)
    fund_name: Mapped[str] = mapped_column(String(255), nullable=False)
    fund_manager: Mapped[str] = mapped_column(String(255), nullable=False)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    holdings: Mapped[list["InstitutionalHolding"]] = relationship(
        back_populates="fund",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
