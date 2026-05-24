"""add company workspace bootstrap snapshots

Revision ID: 20260524_0051
Revises: 20260512_0050
Create Date: 2026-05-24 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260524_0051"
down_revision = "20260512_0050"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_workspace_bootstrap_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("as_of_key", sa.String(length=64), server_default="latest", nullable=False),
        sa.Column("as_of_value", sa.DateTime(timezone=True), nullable=True),
        sa.Column("schema_version", sa.String(length=32), nullable=False),
        sa.Column("source_fingerprint", sa.String(length=128), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("source_mix", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("freshness_state", sa.String(length=16), server_default="fresh", nullable=False),
        sa.Column("confidence_flags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("fallback_flags", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("strict_official_eligible", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "as_of_key",
            "schema_version",
            "source_fingerprint",
            name="uq_cwbs_company_asof_schema_source",
        ),
    )
    op.create_index("ix_company_workspace_bootstrap_snapshots_company_id", "company_workspace_bootstrap_snapshots", ["company_id"], unique=False)
    op.create_index(
        "ix_company_workspace_bootstrap_snapshots_company_as_of",
        "company_workspace_bootstrap_snapshots",
        ["company_id", "as_of_key"],
        unique=False,
    )
    op.create_index(
        "ix_company_workspace_bootstrap_snapshots_company_source",
        "company_workspace_bootstrap_snapshots",
        ["company_id", "source_fingerprint"],
        unique=False,
    )
    op.create_index(
        "ix_company_workspace_bootstrap_snapshots_company_last_checked",
        "company_workspace_bootstrap_snapshots",
        ["company_id", "last_checked"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_company_workspace_bootstrap_snapshots_company_last_checked", table_name="company_workspace_bootstrap_snapshots")
    op.drop_index("ix_company_workspace_bootstrap_snapshots_company_source", table_name="company_workspace_bootstrap_snapshots")
    op.drop_index("ix_company_workspace_bootstrap_snapshots_company_as_of", table_name="company_workspace_bootstrap_snapshots")
    op.drop_index("ix_company_workspace_bootstrap_snapshots_company_id", table_name="company_workspace_bootstrap_snapshots")
    op.drop_table("company_workspace_bootstrap_snapshots")
