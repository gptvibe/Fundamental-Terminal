"""add derived metrics mart

Revision ID: 20260325_0021
Revises: 20260324_0020
Create Date: 2026-03-25 10:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector


revision = "20260325_0021"
down_revision = "20260324_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if not inspector.has_table("derived_metric_points"):
        op.create_table(
            "derived_metric_points",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("period_end", sa.Date(), nullable=False),
            sa.Column("period_type", sa.String(length=16), nullable=False),
            sa.Column("filing_type", sa.String(length=32), nullable=False),
            sa.Column("metric_key", sa.String(length=64), nullable=False),
            sa.Column("metric_value", sa.Float(), nullable=True),
            sa.Column("metric_date", sa.Date(), nullable=False),
            sa.Column("is_proxy", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("provenance", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column(
                "source_statement_ids",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "quality_flags",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("last_checked", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "company_id",
                "period_end",
                "period_type",
                "metric_key",
                name="uq_derived_metric_points_company_period_type_metric",
            ),
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes("derived_metric_points")}

    if "ix_derived_metric_points_company_id" not in existing_indexes:
        op.create_index("ix_derived_metric_points_company_id", "derived_metric_points", ["company_id"], unique=False)
    if "ix_derived_metric_points_company_period_end" not in existing_indexes:
        op.create_index("ix_derived_metric_points_company_period_end", "derived_metric_points", ["company_id", "period_end"], unique=False)
    if "ix_derived_metric_points_company_metric" not in existing_indexes:
        op.create_index("ix_derived_metric_points_company_metric", "derived_metric_points", ["company_id", "metric_key"], unique=False)
    if "ix_derived_metric_points_period_type" not in existing_indexes:
        op.create_index("ix_derived_metric_points_period_type", "derived_metric_points", ["period_type"], unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if not inspector.has_table("derived_metric_points"):
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("derived_metric_points")}
    if "ix_derived_metric_points_period_type" in existing_indexes:
        op.drop_index("ix_derived_metric_points_period_type", table_name="derived_metric_points")
    if "ix_derived_metric_points_company_metric" in existing_indexes:
        op.drop_index("ix_derived_metric_points_company_metric", table_name="derived_metric_points")
    if "ix_derived_metric_points_company_period_end" in existing_indexes:
        op.drop_index("ix_derived_metric_points_company_period_end", table_name="derived_metric_points")
    if "ix_derived_metric_points_company_id" in existing_indexes:
        op.drop_index("ix_derived_metric_points_company_id", table_name="derived_metric_points")
    op.drop_table("derived_metric_points")
