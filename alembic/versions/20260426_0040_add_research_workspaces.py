"""add research workspaces

Revision ID: 20260426_0040
Revises: 20260424_0039
Create Date: 2026-04-26 09:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260426_0040"
down_revision = "20260424_0039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "research_workspaces",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_key", sa.String(length=120), nullable=False),
        sa.Column("saved_companies", sa.JSON(), nullable=False),
        sa.Column("notes", sa.JSON(), nullable=False),
        sa.Column("pinned_metrics", sa.JSON(), nullable=False),
        sa.Column("pinned_charts", sa.JSON(), nullable=False),
        sa.Column("compare_baskets", sa.JSON(), nullable=False),
        sa.Column("memo_draft", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_key", name="uq_research_workspaces_workspace_key"),
    )
    op.create_index("ix_research_workspaces_workspace_key", "research_workspaces", ["workspace_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_research_workspaces_workspace_key", table_name="research_workspaces")
    op.drop_table("research_workspaces")
