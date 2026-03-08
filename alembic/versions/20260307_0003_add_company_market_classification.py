"""add company market classification

Revision ID: 20260307_0003
Revises: 20260307_0002
Create Date: 2026-03-07 02:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260307_0003"
down_revision = "20260307_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("market_sector", sa.String(length=100), nullable=True))
    op.add_column("companies", sa.Column("market_industry", sa.String(length=150), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "market_industry")
    op.drop_column("companies", "market_sector")
