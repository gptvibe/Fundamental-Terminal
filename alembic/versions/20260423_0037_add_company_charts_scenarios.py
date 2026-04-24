"""add company charts scenarios

Revision ID: 20260423_0037
Revises: 20260413_0036
Create Date: 2026-04-23 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260423_0037"
down_revision = "20260413_0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_charts_scenarios",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("owner_key", sa.String(length=160), nullable=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("visibility", sa.String(length=16), server_default="private", nullable=False),
        sa.Column("source", sa.String(length=32), server_default="sec_base_forecast", nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("override_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("forecast_year", sa.Integer(), nullable=True),
        sa.Column("as_of", sa.String(length=64), nullable=True),
        sa.Column("overrides", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("cloned_from_scenario_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_company_charts_scenarios_company_id",
        "company_charts_scenarios",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_company_charts_scenarios_company_updated_at",
        "company_charts_scenarios",
        ["company_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_company_charts_scenarios_company_owner",
        "company_charts_scenarios",
        ["company_id", "owner_key"],
        unique=False,
    )
    op.create_index(
        "ix_company_charts_scenarios_company_visibility",
        "company_charts_scenarios",
        ["company_id", "visibility"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_company_charts_scenarios_company_visibility", table_name="company_charts_scenarios")
    op.drop_index("ix_company_charts_scenarios_company_owner", table_name="company_charts_scenarios")
    op.drop_index("ix_company_charts_scenarios_company_updated_at", table_name="company_charts_scenarios")
    op.drop_index("ix_company_charts_scenarios_company_id", table_name="company_charts_scenarios")
    op.drop_table("company_charts_scenarios")
