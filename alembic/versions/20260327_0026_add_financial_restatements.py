"""add financial restatements

Revision ID: 20260327_0026
Revises: 20260327_0025
Create Date: 2026-03-27 14:30:00

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector


revision = "20260327_0026"
down_revision = "20260327_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if "financial_restatements" in inspector.get_table_names():
        return

    op.create_table(
        "financial_restatements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("statement_type", sa.String(length=32), nullable=False),
        sa.Column("filing_type", sa.String(length=32), nullable=False),
        sa.Column("form", sa.String(length=32), nullable=False),
        sa.Column("accession_number", sa.String(length=32), nullable=False),
        sa.Column("previous_accession_number", sa.String(length=32), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("previous_filing_date", sa.Date(), nullable=True),
        sa.Column("filing_acceptance_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("previous_filing_acceptance_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(length=500), nullable=False),
        sa.Column("previous_source", sa.String(length=500), nullable=True),
        sa.Column("is_amendment", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("detection_kind", sa.String(length=32), nullable=False),
        sa.Column("changed_metric_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("companyfacts_changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("normalized_data_changes", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("confidence_impact", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "statement_type",
            "accession_number",
            "detection_kind",
            name="uq_financial_restatements_company_statement_accession_kind",
        ),
    )
    op.create_index("ix_financial_restatements_company_id", "financial_restatements", ["company_id"], unique=False)
    op.create_index("ix_financial_restatements_company_period_end", "financial_restatements", ["company_id", "period_end"], unique=False)
    op.create_index("ix_financial_restatements_company_filing_date", "financial_restatements", ["company_id", "filing_date"], unique=False)
    op.create_index("ix_financial_restatements_company_last_checked", "financial_restatements", ["company_id", "last_checked"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if "financial_restatements" not in inspector.get_table_names():
        return

    op.drop_index("ix_financial_restatements_company_last_checked", table_name="financial_restatements")
    op.drop_index("ix_financial_restatements_company_filing_date", table_name="financial_restatements")
    op.drop_index("ix_financial_restatements_company_period_end", table_name="financial_restatements")
    op.drop_index("ix_financial_restatements_company_id", table_name="financial_restatements")
    op.drop_table("financial_restatements")