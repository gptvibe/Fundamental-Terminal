"""add capital markets events cache

Revision ID: 20260319_0012
Revises: 20260319_0011
Create Date: 2026-03-19 10:30:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0012"
down_revision = "20260319_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("capital_markets_last_checked", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "capital_markets_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=32), nullable=False),
        sa.Column("form", sa.String(length=16), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("primary_document", sa.String(length=255), nullable=True),
        sa.Column("primary_doc_description", sa.String(length=500), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=True),
        sa.Column("security_type", sa.String(length=64), nullable=True),
        sa.Column("offering_amount", sa.Float(), nullable=True),
        sa.Column("shelf_size", sa.Float(), nullable=True),
        sa.Column("is_late_filer", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "accession_number", name="uq_capital_markets_events_company_accession"),
    )
    op.create_index("ix_capital_markets_events_company_id", "capital_markets_events", ["company_id"], unique=False)
    op.create_index("ix_capital_markets_events_company_filing_date", "capital_markets_events", ["company_id", "filing_date"], unique=False)
    op.create_index("ix_capital_markets_events_company_form", "capital_markets_events", ["company_id", "form"], unique=False)
    op.create_index("ix_capital_markets_events_company_last_checked", "capital_markets_events", ["company_id", "last_checked"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_capital_markets_events_company_last_checked", table_name="capital_markets_events")
    op.drop_index("ix_capital_markets_events_company_form", table_name="capital_markets_events")
    op.drop_index("ix_capital_markets_events_company_filing_date", table_name="capital_markets_events")
    op.drop_index("ix_capital_markets_events_company_id", table_name="capital_markets_events")
    op.drop_table("capital_markets_events")

    op.drop_column("companies", "capital_markets_last_checked")
