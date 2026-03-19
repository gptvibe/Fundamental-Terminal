"""add beneficial ownership party detail fields

Revision ID: 20260318_0010
Revises: 20260315_0009
Create Date: 2026-03-18 10:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260318_0010"
down_revision = "20260315_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("beneficial_ownership_parties", sa.Column("filer_cik", sa.String(length=10), nullable=True))
    op.add_column("beneficial_ownership_parties", sa.Column("shares_owned", sa.Float(), nullable=True))
    op.add_column("beneficial_ownership_parties", sa.Column("percent_owned", sa.Float(), nullable=True))
    op.add_column("beneficial_ownership_parties", sa.Column("event_date", sa.Date(), nullable=True))
    op.add_column("beneficial_ownership_parties", sa.Column("purpose", sa.String(length=500), nullable=True))
    op.create_index(
        "ix_beneficial_ownership_parties_filer_cik",
        "beneficial_ownership_parties",
        ["filer_cik"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_beneficial_ownership_parties_filer_cik", table_name="beneficial_ownership_parties")
    op.drop_column("beneficial_ownership_parties", "purpose")
    op.drop_column("beneficial_ownership_parties", "event_date")
    op.drop_column("beneficial_ownership_parties", "percent_owned")
    op.drop_column("beneficial_ownership_parties", "shares_owned")
    op.drop_column("beneficial_ownership_parties", "filer_cik")
