"""add filing events cache

Revision ID: 20260319_0011
Revises: 20260318_0010
Create Date: 2026-03-19 10:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260319_0011"
down_revision = "20260318_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("filing_events_last_checked", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "filing_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=32), nullable=False),
        sa.Column("form", sa.String(length=16), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("items", sa.String(length=128), nullable=True),
        sa.Column("item_code", sa.String(length=16), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("primary_document", sa.String(length=255), nullable=True),
        sa.Column("primary_doc_description", sa.String(length=500), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("key_amounts", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "accession_number", "item_code", name="uq_filing_events_company_accession_item_code"),
    )
    op.create_index("ix_filing_events_company_id", "filing_events", ["company_id"], unique=False)
    op.create_index("ix_filing_events_company_filing_date", "filing_events", ["company_id", "filing_date"], unique=False)
    op.create_index("ix_filing_events_company_category", "filing_events", ["company_id", "category"], unique=False)
    op.create_index("ix_filing_events_company_last_checked", "filing_events", ["company_id", "last_checked"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_filing_events_company_last_checked", table_name="filing_events")
    op.drop_index("ix_filing_events_company_category", table_name="filing_events")
    op.drop_index("ix_filing_events_company_filing_date", table_name="filing_events")
    op.drop_index("ix_filing_events_company_id", table_name="filing_events")
    op.drop_table("filing_events")

    op.drop_column("companies", "filing_events_last_checked")
