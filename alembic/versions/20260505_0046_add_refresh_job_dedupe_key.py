"""add refresh job dedupe key dimensions

Revision ID: 20260505_0046
Revises: 20260503_0045
Create Date: 2026-05-05 09:10:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "20260505_0046"
down_revision = "20260503_0045"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if not inspector.has_table("refresh_jobs"):
        return

    columns = {column["name"] for column in inspector.get_columns("refresh_jobs")}

    if "as_of_key" not in columns:
        op.add_column(
            "refresh_jobs",
            sa.Column("as_of_key", sa.String(length=32), nullable=False, server_default=sa.text("'latest'")),
        )
    if "reason" not in columns:
        op.add_column(
            "refresh_jobs",
            sa.Column("reason", sa.String(length=32), nullable=False, server_default=sa.text("'manual'")),
        )

    index_names = {index["name"] for index in inspector.get_indexes("refresh_jobs")}
    if "uq_refresh_jobs_active_ticker_dataset" in index_names:
        op.drop_index("uq_refresh_jobs_active_ticker_dataset", table_name="refresh_jobs")

    op.create_index(
        "uq_refresh_jobs_active_ticker_dataset",
        "refresh_jobs",
        ["ticker", "dataset", "as_of_key", "reason"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if not inspector.has_table("refresh_jobs"):
        return

    index_names = {index["name"] for index in inspector.get_indexes("refresh_jobs")}
    if "uq_refresh_jobs_active_ticker_dataset" in index_names:
        op.drop_index("uq_refresh_jobs_active_ticker_dataset", table_name="refresh_jobs")

    op.create_index(
        "uq_refresh_jobs_active_ticker_dataset",
        "refresh_jobs",
        ["ticker", "dataset"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    columns = {column["name"] for column in inspector.get_columns("refresh_jobs")}
    if "reason" in columns:
        op.drop_column("refresh_jobs", "reason")
    if "as_of_key" in columns:
        op.drop_column("refresh_jobs", "as_of_key")
