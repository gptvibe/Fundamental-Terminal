from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class CompanyWorkspaceBootstrapSnapshot(Base):
    __tablename__ = "company_workspace_bootstrap_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "company_id",
            "as_of_key",
            "schema_version",
            "source_fingerprint",
            name="uq_cwbs_company_asof_schema_source",
        ),
        Index("ix_company_workspace_bootstrap_snapshots_company_id", "company_id"),
        Index("ix_company_workspace_bootstrap_snapshots_company_as_of", "company_id", "as_of_key"),
        Index("ix_company_workspace_bootstrap_snapshots_company_source", "company_id", "source_fingerprint"),
        Index("ix_company_workspace_bootstrap_snapshots_company_last_checked", "company_id", "last_checked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    as_of_key: Mapped[str] = mapped_column(String(64), nullable=False, server_default="latest")
    as_of_value: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    provenance: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    source_mix: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    freshness_state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="fresh")
    confidence_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    fallback_flags: Mapped[list[str]] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    strict_official_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="workspace_bootstrap_snapshots")
