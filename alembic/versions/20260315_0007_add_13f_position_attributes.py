"""add 13f position attributes

Revision ID: 20260315_0007
Revises: 20260315_0006
Create Date: 2026-03-15 00:15:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260315_0007"
down_revision = "20260315_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("institutional_holdings", sa.Column("put_call", sa.String(length=16), nullable=True))
    op.add_column("institutional_holdings", sa.Column("investment_discretion", sa.String(length=32), nullable=True))
    op.add_column("institutional_holdings", sa.Column("voting_authority_sole", sa.Float(), nullable=True))
    op.add_column("institutional_holdings", sa.Column("voting_authority_shared", sa.Float(), nullable=True))
    op.add_column("institutional_holdings", sa.Column("voting_authority_none", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("institutional_holdings", "voting_authority_none")
    op.drop_column("institutional_holdings", "voting_authority_shared")
    op.drop_column("institutional_holdings", "voting_authority_sole")
    op.drop_column("institutional_holdings", "investment_discretion")
    op.drop_column("institutional_holdings", "put_call")