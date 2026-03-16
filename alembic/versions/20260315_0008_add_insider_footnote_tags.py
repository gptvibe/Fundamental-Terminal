"""add insider footnote tags

Revision ID: 20260315_0008
Revises: 20260315_0007
Create Date: 2026-03-15 00:30:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260315_0008"
down_revision = "20260315_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("insider_trades", sa.Column("footnote_tags", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("insider_trades", "footnote_tags")