"""add point-in-time timestamps

Revision ID: 20260327_0025
Revises: 20260326_0024
Create Date: 2026-03-27 10:30:00

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector


revision = "20260327_0025"
down_revision = "20260326_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    financial_columns = {column["name"] for column in inspector.get_columns("financial_statements")}
    if "filing_acceptance_at" not in financial_columns:
        op.add_column("financial_statements", sa.Column("filing_acceptance_at", sa.DateTime(timezone=True), nullable=True))
    if "fetch_timestamp" not in financial_columns:
        op.add_column(
            "financial_statements",
            sa.Column("fetch_timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    earnings_columns = {column["name"] for column in inspector.get_columns("earnings_releases")}
    if "filing_acceptance_at" not in earnings_columns:
        op.add_column("earnings_releases", sa.Column("filing_acceptance_at", sa.DateTime(timezone=True), nullable=True))
    if "fetch_timestamp" not in earnings_columns:
        op.add_column(
            "earnings_releases",
            sa.Column("fetch_timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )

    price_columns = {column["name"] for column in inspector.get_columns("price_history")}
    if "fetch_timestamp" not in price_columns:
        op.add_column(
            "price_history",
            sa.Column("fetch_timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    price_columns = {column["name"] for column in inspector.get_columns("price_history")}
    if "fetch_timestamp" in price_columns:
        op.drop_column("price_history", "fetch_timestamp")

    earnings_columns = {column["name"] for column in inspector.get_columns("earnings_releases")}
    if "fetch_timestamp" in earnings_columns:
        op.drop_column("earnings_releases", "fetch_timestamp")
    if "filing_acceptance_at" in earnings_columns:
        op.drop_column("earnings_releases", "filing_acceptance_at")

    financial_columns = {column["name"] for column in inspector.get_columns("financial_statements")}
    if "fetch_timestamp" in financial_columns:
        op.drop_column("financial_statements", "fetch_timestamp")
    if "filing_acceptance_at" in financial_columns:
        op.drop_column("financial_statements", "filing_acceptance_at")