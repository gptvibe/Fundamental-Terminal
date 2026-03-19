"""add 13f manager universe and amendment flags

Revision ID: 20260319_0013
Revises: 20260319_0012
Create Date: 2026-03-19 12:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0013"
down_revision = "20260319_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("institutional_funds", sa.Column("manager_query", sa.String(length=255), nullable=True))
    op.add_column("institutional_funds", sa.Column("universe_source", sa.String(length=32), nullable=True))

    op.add_column("institutional_holdings", sa.Column("filing_form", sa.String(length=16), nullable=True))
    op.add_column("institutional_holdings", sa.Column("base_form", sa.String(length=16), nullable=True))
    op.add_column(
        "institutional_holdings",
        sa.Column("is_amendment", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("institutional_holdings", "is_amendment")
    op.drop_column("institutional_holdings", "base_form")
    op.drop_column("institutional_holdings", "filing_form")

    op.drop_column("institutional_funds", "universe_source")
    op.drop_column("institutional_funds", "manager_query")
