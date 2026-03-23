"""Add macro data persistence tables

Revision ID: 20260323_0018
Revises: 20260321_0017
Create Date: 2026-03-23 00:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260323_0018"
down_revision = "20260321_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # official_data_series: metadata about each tracked macro series
    op.create_table(
        "official_data_series",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.String(length=80), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("section", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("units", sa.String(length=80), nullable=False),
        sa.Column("cadence", sa.String(length=20), nullable=True),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("last_refreshed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id", "provider", name="uq_official_data_series_id_provider"),
    )
    op.create_index("ix_official_data_series_provider", "official_data_series", ["provider"])
    op.create_index("ix_official_data_series_section", "official_data_series", ["section"])

    # official_data_observations: historical values per series
    op.create_table(
        "official_data_observations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id_fk", sa.Integer(), nullable=False),
        sa.Column("observation_date", sa.Date(), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("prior_value", sa.Float(), nullable=True),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("is_revised", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("provenance", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["series_id_fk"], ["official_data_series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id_fk", "observation_date", name="uq_official_data_obs_series_date"),
    )
    op.create_index("ix_official_data_obs_series_date", "official_data_observations", ["series_id_fk", "observation_date"])

    # market_context_snapshots: latest global macro snapshot (one per day)
    op.create_table(
        "market_context_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False, unique=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=True),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_market_context_snapshots_date", "market_context_snapshots", ["snapshot_date"])

    # company_macro_snapshots: per-company macro context snapshot (one per day per company)
    op.create_table(
        "company_macro_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("is_stale", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "snapshot_date", name="uq_company_macro_snapshots_company_date"),
    )
    op.create_index("ix_company_macro_snapshots_company", "company_macro_snapshots", ["company_id"])
    op.create_index("ix_company_macro_snapshots_company_date", "company_macro_snapshots", ["company_id", "snapshot_date"])


def downgrade() -> None:
    op.drop_index("ix_company_macro_snapshots_company_date", table_name="company_macro_snapshots")
    op.drop_index("ix_company_macro_snapshots_company", table_name="company_macro_snapshots")
    op.drop_table("company_macro_snapshots")
    op.drop_index("ix_market_context_snapshots_date", table_name="market_context_snapshots")
    op.drop_table("market_context_snapshots")
    op.drop_index("ix_official_data_obs_series_date", table_name="official_data_observations")
    op.drop_table("official_data_observations")
    op.drop_index("ix_official_data_series_section", table_name="official_data_series")
    op.drop_index("ix_official_data_series_provider", table_name="official_data_series")
    op.drop_table("official_data_series")
