"""add durable refresh job queue

Revision ID: 20260406_0034
Revises: 20260405_0033
Create Date: 2026-04-06 10:30:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "20260406_0034"
down_revision = "20260405_0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if not inspector.has_table("refresh_jobs"):
        op.create_table(
            "refresh_jobs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("job_id", sa.String(length=64), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=True),
            sa.Column("ticker", sa.String(length=16), nullable=False),
            sa.Column("dataset", sa.String(length=64), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("force", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("event_sequence", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("worker_id", sa.String(length=128), nullable=True),
            sa.Column("claim_token", sa.String(length=64), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("job_id", name="uq_refresh_jobs_job_id"),
        )

    refresh_job_indexes = {index["name"] for index in inspector.get_indexes("refresh_jobs")}
    if "ix_refresh_jobs_status_requested" not in refresh_job_indexes:
        op.create_index("ix_refresh_jobs_status_requested", "refresh_jobs", ["status", "requested_at"], unique=False)
    if "ix_refresh_jobs_dataset_status_requested" not in refresh_job_indexes:
        op.create_index("ix_refresh_jobs_dataset_status_requested", "refresh_jobs", ["dataset", "status", "requested_at"], unique=False)
    if "ix_refresh_jobs_lease_expires_at" not in refresh_job_indexes:
        op.create_index("ix_refresh_jobs_lease_expires_at", "refresh_jobs", ["lease_expires_at"], unique=False)
    if "uq_refresh_jobs_active_ticker_dataset" not in refresh_job_indexes:
        op.create_index(
            "uq_refresh_jobs_active_ticker_dataset",
            "refresh_jobs",
            ["ticker", "dataset"],
            unique=True,
            postgresql_where=sa.text("status IN ('queued', 'running')"),
        )

    if not inspector.has_table("refresh_job_events"):
        op.create_table(
            "refresh_job_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("refresh_job_id", sa.Integer(), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
            sa.Column("ticker", sa.String(length=16), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("stage", sa.String(length=64), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column("level", sa.String(length=16), nullable=False),
            sa.ForeignKeyConstraint(["refresh_job_id"], ["refresh_jobs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("refresh_job_id", "sequence", name="uq_refresh_job_events_job_sequence"),
        )

    refresh_job_event_indexes = {index["name"] for index in inspector.get_indexes("refresh_job_events")}
    if "ix_refresh_job_events_job_sequence" not in refresh_job_event_indexes:
        op.create_index("ix_refresh_job_events_job_sequence", "refresh_job_events", ["refresh_job_id", "sequence"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if inspector.has_table("refresh_job_events"):
        refresh_job_event_indexes = {index["name"] for index in inspector.get_indexes("refresh_job_events")}
        if "ix_refresh_job_events_job_sequence" in refresh_job_event_indexes:
            op.drop_index("ix_refresh_job_events_job_sequence", table_name="refresh_job_events")
        op.drop_table("refresh_job_events")

    if not inspector.has_table("refresh_jobs"):
        return

    refresh_job_indexes = {index["name"] for index in inspector.get_indexes("refresh_jobs")}
    if "uq_refresh_jobs_active_ticker_dataset" in refresh_job_indexes:
        op.drop_index("uq_refresh_jobs_active_ticker_dataset", table_name="refresh_jobs")
    if "ix_refresh_jobs_lease_expires_at" in refresh_job_indexes:
        op.drop_index("ix_refresh_jobs_lease_expires_at", table_name="refresh_jobs")
    if "ix_refresh_jobs_dataset_status_requested" in refresh_job_indexes:
        op.drop_index("ix_refresh_jobs_dataset_status_requested", table_name="refresh_jobs")
    if "ix_refresh_jobs_status_requested" in refresh_job_indexes:
        op.drop_index("ix_refresh_jobs_status_requested", table_name="refresh_jobs")
    op.drop_table("refresh_jobs")