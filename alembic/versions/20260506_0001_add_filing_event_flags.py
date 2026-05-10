"""Add is_amendment and is_late_filing columns to filing_events table

Revision ID: 20260506_0001
Revises: 20260505_0047
Create Date: 2026-05-06 00:01:00.000000

"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260506_0001"
down_revision = "20260505_0047"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "filing_events",
        sa.Column("is_amendment", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "filing_events",
        sa.Column("is_late_filing", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("filing_events", "is_late_filing")
    op.drop_column("filing_events", "is_amendment")
