from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company


class CommentLetter(Base):
    __tablename__ = "comment_letters"
    __table_args__ = (
        UniqueConstraint("company_id", "accession_number", name="uq_comment_letters_company_accession"),
        Index("ix_comment_letters_company_id", "company_id"),
        Index("ix_comment_letters_company_filing_date", "company_id", "filing_date"),
        Index("ix_comment_letters_company_filing_id", "company_id", "filing_date", "id"),
        Index("ix_comment_letters_company_last_checked", "company_id", "last_checked"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), nullable=False)
    accession_number: Mapped[str] = mapped_column(String(32), nullable=False)
    filing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    sec_url: Mapped[str] = mapped_column(String(500), nullable=False)
    acceptance_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    primary_document: Mapped[str | None] = mapped_column(String(260), nullable=True)
    document_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    document_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    correspondent_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    document_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    thread_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    review_sequence: Mapped[str | None] = mapped_column(String(64), nullable=True)
    topics: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    document_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_text_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    text_extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parser_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_updated: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    last_checked: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    company: Mapped["Company"] = relationship(back_populates="comment_letters")
