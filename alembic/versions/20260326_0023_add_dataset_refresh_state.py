"""add dataset refresh state

Revision ID: 20260326_0023
Revises: 20260326_0022
Create Date: 2026-03-26 13:15:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "20260326_0023"
down_revision = "20260326_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if not inspector.has_table("dataset_refresh_state"):
        op.create_table(
            "dataset_refresh_state",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("dataset", sa.String(length=64), nullable=False),
            sa.Column("last_checked", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_success", sa.DateTime(timezone=True), nullable=True),
            sa.Column("freshness_deadline", sa.DateTime(timezone=True), nullable=True),
            sa.Column("active_job_id", sa.String(length=64), nullable=True),
            sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("payload_version_hash", sa.String(length=128), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("company_id", "dataset", name="uq_dataset_refresh_state_company_dataset"),
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes("dataset_refresh_state")}
    if "ix_dataset_refresh_state_company_dataset" not in existing_indexes:
        op.create_index(
            "ix_dataset_refresh_state_company_dataset",
            "dataset_refresh_state",
            ["company_id", "dataset"],
            unique=False,
        )
    if "ix_dataset_refresh_state_deadline" not in existing_indexes:
        op.create_index(
            "ix_dataset_refresh_state_deadline",
            "dataset_refresh_state",
            ["dataset", "freshness_deadline"],
            unique=False,
        )
    if "ix_dataset_refresh_state_active_job" not in existing_indexes:
        op.create_index(
            "ix_dataset_refresh_state_active_job",
            "dataset_refresh_state",
            ["active_job_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if not inspector.has_table("dataset_refresh_state"):
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("dataset_refresh_state")}
    if "ix_dataset_refresh_state_active_job" in existing_indexes:
        op.drop_index("ix_dataset_refresh_state_active_job", table_name="dataset_refresh_state")
    if "ix_dataset_refresh_state_deadline" in existing_indexes:
        op.drop_index("ix_dataset_refresh_state_deadline", table_name="dataset_refresh_state")
    if "ix_dataset_refresh_state_company_dataset" in existing_indexes:
        op.drop_index("ix_dataset_refresh_state_company_dataset", table_name="dataset_refresh_state")

    op.drop_table("dataset_refresh_state")
