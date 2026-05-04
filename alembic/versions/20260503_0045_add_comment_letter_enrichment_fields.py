"""add comment letter enrichment fields

Revision ID: 20260503_0045
Revises: 20260503_0044
Create Date: 2026-05-03 18:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260503_0045"
down_revision = "20260503_0044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("comment_letters", sa.Column("acceptance_datetime", sa.DateTime(timezone=True), nullable=True))
    op.add_column("comment_letters", sa.Column("primary_document", sa.String(length=260), nullable=True))
    op.add_column("comment_letters", sa.Column("document_url", sa.String(length=500), nullable=True))
    op.add_column("comment_letters", sa.Column("document_format", sa.String(length=32), nullable=True))
    op.add_column("comment_letters", sa.Column("correspondent_role", sa.String(length=32), nullable=True))
    op.add_column("comment_letters", sa.Column("document_kind", sa.String(length=32), nullable=True))
    op.add_column("comment_letters", sa.Column("thread_key", sa.String(length=120), nullable=True))
    op.add_column("comment_letters", sa.Column("review_sequence", sa.String(length=64), nullable=True))
    op.add_column("comment_letters", sa.Column("topics", sa.JSON(), nullable=True))
    op.add_column("comment_letters", sa.Column("document_text", sa.Text(), nullable=True))
    op.add_column("comment_letters", sa.Column("document_text_sha256", sa.String(length=64), nullable=True))
    op.add_column("comment_letters", sa.Column("text_extracted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("comment_letters", sa.Column("parser_version", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("comment_letters", "parser_version")
    op.drop_column("comment_letters", "text_extracted_at")
    op.drop_column("comment_letters", "document_text_sha256")
    op.drop_column("comment_letters", "document_text")
    op.drop_column("comment_letters", "topics")
    op.drop_column("comment_letters", "review_sequence")
    op.drop_column("comment_letters", "thread_key")
    op.drop_column("comment_letters", "document_kind")
    op.drop_column("comment_letters", "correspondent_role")
    op.drop_column("comment_letters", "document_format")
    op.drop_column("comment_letters", "document_url")
    op.drop_column("comment_letters", "primary_document")
    op.drop_column("comment_letters", "acceptance_datetime")