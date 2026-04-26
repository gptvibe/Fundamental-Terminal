from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ResearchWorkspace(Base):
    __tablename__ = "research_workspaces"
    __table_args__ = (
        UniqueConstraint("workspace_key", name="uq_research_workspaces_workspace_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    saved_companies: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    notes: Mapped[dict[str, dict[str, Any]]] = mapped_column(JSON, nullable=False)
    pinned_metrics: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    pinned_charts: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    compare_baskets: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    memo_draft: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
