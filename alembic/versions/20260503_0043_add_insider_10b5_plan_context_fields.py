"""add insider 10b5 plan context fields

Revision ID: 20260503_0043
Revises: 20260503_0042
Create Date: 2026-05-03 11:45:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260503_0043"
down_revision = "20260503_0042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("insider_trades", sa.Column("sale_context", sa.String(length=24), nullable=True))
    op.add_column("insider_trades", sa.Column("plan_adoption_date", sa.Date(), nullable=True))
    op.add_column("insider_trades", sa.Column("plan_modification", sa.String(length=32), nullable=True))
    op.add_column("insider_trades", sa.Column("plan_modification_date", sa.Date(), nullable=True))
    op.add_column("insider_trades", sa.Column("plan_signal_confidence", sa.String(length=16), nullable=True))
    op.add_column("insider_trades", sa.Column("plan_signal_provenance", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("insider_trades", "plan_signal_provenance")
    op.drop_column("insider_trades", "plan_signal_confidence")
    op.drop_column("insider_trades", "plan_modification_date")
    op.drop_column("insider_trades", "plan_modification")
    op.drop_column("insider_trades", "plan_adoption_date")
    op.drop_column("insider_trades", "sale_context")
