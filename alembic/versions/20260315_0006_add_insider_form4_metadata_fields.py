"""add insider form4 metadata fields

Revision ID: 20260315_0006
Revises: 20260307_0005
Create Date: 2026-03-15 00:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260315_0006"
down_revision = "20260307_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("insider_trades", sa.Column("security_title", sa.String(length=255), nullable=True))
    op.add_column("insider_trades", sa.Column("is_derivative", sa.Boolean(), nullable=True))
    op.add_column("insider_trades", sa.Column("ownership_nature", sa.String(length=32), nullable=True))
    op.add_column("insider_trades", sa.Column("exercise_price", sa.Float(), nullable=True))
    op.add_column("insider_trades", sa.Column("expiration_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("insider_trades", "expiration_date")
    op.drop_column("insider_trades", "exercise_price")
    op.drop_column("insider_trades", "ownership_nature")
    op.drop_column("insider_trades", "is_derivative")
    op.drop_column("insider_trades", "security_title")