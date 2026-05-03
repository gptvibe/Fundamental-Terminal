"""add s8 equity plan fields to capital markets events

Revision ID: 20260503_0044
Revises: 20260503_0043
Create Date: 2026-05-03 12:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260503_0044"
down_revision = "20260503_0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("capital_markets_events", sa.Column("plan_name", sa.String(length=255), nullable=True))
    op.add_column("capital_markets_events", sa.Column("registered_shares", sa.Float(), nullable=True))
    op.add_column("capital_markets_events", sa.Column("shares_parse_confidence", sa.String(length=16), nullable=True))


def downgrade() -> None:
    op.drop_column("capital_markets_events", "shares_parse_confidence")
    op.drop_column("capital_markets_events", "registered_shares")
    op.drop_column("capital_markets_events", "plan_name")
