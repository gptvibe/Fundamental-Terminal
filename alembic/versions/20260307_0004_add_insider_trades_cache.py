"""add insider trades cache

Revision ID: 20260307_0004
Revises: 20260307_0003
Create Date: 2026-03-07 19:45:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260307_0004"
down_revision = "20260307_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("insider_trades_last_checked", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "insider_trades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=32), nullable=False),
        sa.Column("filing_type", sa.String(length=16), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("transaction_index", sa.Integer(), nullable=False),
        sa.Column("insider_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=120), nullable=True),
        sa.Column("transaction_date", sa.Date(), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("shares", sa.Float(), nullable=True),
        sa.Column("price", sa.Float(), nullable=True),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("ownership_after", sa.Float(), nullable=True),
        sa.Column("transaction_code", sa.String(length=8), nullable=True),
        sa.Column("is_10b5_1", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "accession_number",
            "insider_name",
            "transaction_index",
            name="uq_insider_trades_company_accession_name_index",
        ),
    )
    op.create_index("ix_insider_trades_company_id", "insider_trades", ["company_id"], unique=False)
    op.create_index(
        "ix_insider_trades_company_transaction_date",
        "insider_trades",
        ["company_id", "transaction_date"],
        unique=False,
    )
    op.create_index(
        "ix_insider_trades_company_last_checked",
        "insider_trades",
        ["company_id", "last_checked"],
        unique=False,
    )
    op.create_index("ix_insider_trades_company_action", "insider_trades", ["company_id", "action"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_insider_trades_company_action", table_name="insider_trades")
    op.drop_index("ix_insider_trades_company_last_checked", table_name="insider_trades")
    op.drop_index("ix_insider_trades_company_transaction_date", table_name="insider_trades")
    op.drop_index("ix_insider_trades_company_id", table_name="insider_trades")
    op.drop_table("insider_trades")
    op.drop_column("companies", "insider_trades_last_checked")
