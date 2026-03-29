"""add model evaluation runs

Revision ID: 20260329_0030
Revises: 20260328_0029
Create Date: 2026-03-29 11:30:00

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector


revision = "20260329_0030"
down_revision = "20260328_0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if not inspector.has_table("model_evaluation_runs"):
        op.create_table(
            "model_evaluation_runs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("suite_key", sa.String(length=120), nullable=False),
            sa.Column("candidate_label", sa.String(length=120), nullable=False),
            sa.Column("baseline_label", sa.String(length=120), nullable=True),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("model_names", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("deltas", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("artifacts", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes("model_evaluation_runs")}
    if "ix_model_evaluation_runs_suite_key" not in existing_indexes:
        op.create_index("ix_model_evaluation_runs_suite_key", "model_evaluation_runs", ["suite_key", "created_at"], unique=False)
    if "ix_model_evaluation_runs_status" not in existing_indexes:
        op.create_index("ix_model_evaluation_runs_status", "model_evaluation_runs", ["status", "created_at"], unique=False)
    if "ix_model_evaluation_runs_created_at" not in existing_indexes:
        op.create_index("ix_model_evaluation_runs_created_at", "model_evaluation_runs", ["created_at"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    if not inspector.has_table("model_evaluation_runs"):
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("model_evaluation_runs")}
    if "ix_model_evaluation_runs_created_at" in existing_indexes:
        op.drop_index("ix_model_evaluation_runs_created_at", table_name="model_evaluation_runs")
    if "ix_model_evaluation_runs_status" in existing_indexes:
        op.drop_index("ix_model_evaluation_runs_status", table_name="model_evaluation_runs")
    if "ix_model_evaluation_runs_suite_key" in existing_indexes:
        op.drop_index("ix_model_evaluation_runs_suite_key", table_name="model_evaluation_runs")
    op.drop_table("model_evaluation_runs")
