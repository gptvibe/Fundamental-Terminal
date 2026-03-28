"""add capital structure snapshots

Revision ID: 20260327_0027
Revises: 20260327_0026
Create Date: 2026-03-27 22:45:00

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector


revision = "20260327_0027"
down_revision = "20260327_0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if "capital_structure_snapshots" in inspector.get_table_names():
        return

    op.create_table(
        "capital_structure_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=32), nullable=True),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("filing_type", sa.String(length=32), nullable=False),
        sa.Column("statement_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=500), nullable=False),
        sa.Column("filing_acceptance_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_statement_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("quality_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_checked", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "period_end", "filing_type", name="uq_capital_structure_snapshots_company_period_filing"),
    )
    op.create_index("ix_capital_structure_snapshots_company_id", "capital_structure_snapshots", ["company_id"], unique=False)
    op.create_index("ix_capital_structure_snapshots_company_period_end", "capital_structure_snapshots", ["company_id", "period_end"], unique=False)
    op.create_index("ix_capital_structure_snapshots_company_last_checked", "capital_structure_snapshots", ["company_id", "last_checked"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if "capital_structure_snapshots" not in inspector.get_table_names():
        return

    op.drop_index("ix_capital_structure_snapshots_company_last_checked", table_name="capital_structure_snapshots")
    op.drop_index("ix_capital_structure_snapshots_company_period_end", table_name="capital_structure_snapshots")
    op.drop_index("ix_capital_structure_snapshots_company_id", table_name="capital_structure_snapshots")
    op.drop_table("capital_structure_snapshots")
