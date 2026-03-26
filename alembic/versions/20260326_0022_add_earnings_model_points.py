"""add earnings model points

Revision ID: 20260326_0022
Revises: 20260325_0021
Create Date: 2026-03-26 09:30:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector


revision = "20260326_0022"
down_revision = "20260325_0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if not inspector.has_table("earnings_model_points"):
        op.create_table(
            "earnings_model_points",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("company_id", sa.Integer(), nullable=False),
            sa.Column("period_start", sa.Date(), nullable=False),
            sa.Column("period_end", sa.Date(), nullable=False),
            sa.Column("filing_type", sa.String(length=16), nullable=False),
            sa.Column("quality_score", sa.Float(), nullable=True),
            sa.Column("quality_score_delta", sa.Float(), nullable=True),
            sa.Column("eps_drift", sa.Float(), nullable=True),
            sa.Column("earnings_momentum_drift", sa.Float(), nullable=True),
            sa.Column("segment_contribution_delta", sa.Float(), nullable=True),
            sa.Column("release_statement_coverage_ratio", sa.Float(), nullable=True),
            sa.Column("fallback_ratio", sa.Float(), nullable=True),
            sa.Column("stale_period_warning", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("explainability", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("quality_flags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column(
                "source_statement_ids",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column(
                "source_release_ids",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'[]'::jsonb"),
            ),
            sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("last_checked", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("company_id", "period_end", name="uq_earnings_model_points_company_period"),
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes("earnings_model_points")}

    if "ix_earnings_model_points_company_id" not in existing_indexes:
        op.create_index("ix_earnings_model_points_company_id", "earnings_model_points", ["company_id"], unique=False)
    if "ix_earnings_model_points_company_period_end" not in existing_indexes:
        op.create_index(
            "ix_earnings_model_points_company_period_end",
            "earnings_model_points",
            ["company_id", "period_end"],
            unique=False,
        )
    if "ix_earnings_model_points_company_last_checked" not in existing_indexes:
        op.create_index(
            "ix_earnings_model_points_company_last_checked",
            "earnings_model_points",
            ["company_id", "last_checked"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if not inspector.has_table("earnings_model_points"):
        return

    existing_indexes = {index["name"] for index in inspector.get_indexes("earnings_model_points")}
    if "ix_earnings_model_points_company_last_checked" in existing_indexes:
        op.drop_index("ix_earnings_model_points_company_last_checked", table_name="earnings_model_points")
    if "ix_earnings_model_points_company_period_end" in existing_indexes:
        op.drop_index("ix_earnings_model_points_company_period_end", table_name="earnings_model_points")
    if "ix_earnings_model_points_company_id" in existing_indexes:
        op.drop_index("ix_earnings_model_points_company_id", table_name="earnings_model_points")

    op.drop_table("earnings_model_points")
