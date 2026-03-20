"""add beneficial ownership amendment chain fields

Revision ID: 20260319_0014
Revises: 20260319_0013
Create Date: 2026-03-19 15:50:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0014"
down_revision = "20260319_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("beneficial_ownership_reports", sa.Column("amendment_chain_key", sa.String(length=180), nullable=True))
    op.add_column("beneficial_ownership_reports", sa.Column("previous_accession_number", sa.String(length=32), nullable=True))
    op.add_column("beneficial_ownership_reports", sa.Column("amendment_sequence", sa.Integer(), nullable=True))
    op.add_column("beneficial_ownership_reports", sa.Column("amendment_chain_size", sa.Integer(), nullable=True))

    op.create_index(
        "ix_beneficial_ownership_reports_company_chain_key",
        "beneficial_ownership_reports",
        ["company_id", "amendment_chain_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_beneficial_ownership_reports_company_chain_key", table_name="beneficial_ownership_reports")

    op.drop_column("beneficial_ownership_reports", "amendment_chain_size")
    op.drop_column("beneficial_ownership_reports", "amendment_sequence")
    op.drop_column("beneficial_ownership_reports", "previous_accession_number")
    op.drop_column("beneficial_ownership_reports", "amendment_chain_key")
