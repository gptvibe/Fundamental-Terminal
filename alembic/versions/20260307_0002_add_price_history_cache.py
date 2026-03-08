"""add price history cache

Revision ID: 20260307_0002
Revises: 20260307_0001
Create Date: 2026-03-07 00:30:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260307_0002"
down_revision = "20260307_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "price_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("close", sa.Float(), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "trade_date", "source", name="uq_price_history_company_date_source"),
    )
    op.create_index("ix_price_history_company_id", "price_history", ["company_id"], unique=False)
    op.create_index("ix_price_history_company_trade_date", "price_history", ["company_id", "trade_date"], unique=False)
    op.create_index("ix_price_history_company_last_checked", "price_history", ["company_id", "last_checked"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_price_history_company_last_checked", table_name="price_history")
    op.drop_index("ix_price_history_company_trade_date", table_name="price_history")
    op.drop_index("ix_price_history_company_id", table_name="price_history")
    op.drop_table("price_history")
