from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OfficialDataObservation(Base):
    __tablename__ = "official_data_observations"
    __table_args__ = (
        UniqueConstraint("series_id_fk", "observation_date", name="uq_official_data_obs_series_date"),
        Index("ix_official_data_obs_series_date", "series_id_fk", "observation_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    series_id_fk: Mapped[int] = mapped_column(
        ForeignKey("official_data_series.id", ondelete="CASCADE"), nullable=False
    )
    observation_date: Mapped[date] = mapped_column(Date(), nullable=False)
    value: Mapped[float | None] = mapped_column(Float(), nullable=True)
    prior_value: Mapped[float | None] = mapped_column(Float(), nullable=True)
    release_date: Mapped[date | None] = mapped_column(Date(), nullable=True)
    is_revised: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    provenance: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
