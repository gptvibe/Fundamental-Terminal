"""Add sec_frame_snapshots and sec_frame_company_facts tables.

Revision ID: 20260505_0047
Revises: 20260505_0046
Create Date: 2026-05-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "20260505_0047"
down_revision = "20260505_0046"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sec_frame_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("concept_key", sa.String(64), nullable=False),
        sa.Column("taxonomy", sa.String(40), nullable=False, server_default="us-gaap"),
        sa.Column("tag", sa.String(128), nullable=False),
        sa.Column("unit", sa.String(40), nullable=False),
        sa.Column("period_label", sa.String(20), nullable=False),
        sa.Column("period_type", sa.String(20), nullable=False),
        sa.Column("fiscal_year", sa.Integer, nullable=False),
        sa.Column("fiscal_quarter", sa.Integer, nullable=True),
        sa.Column("pts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "concept_key", "period_label", "tag",
            name="uq_sec_frame_snapshots_concept_period_tag",
        ),
    )
    op.create_index(
        "ix_sec_frame_snapshots_concept_period",
        "sec_frame_snapshots",
        ["concept_key", "period_label"],
    )
    op.create_index(
        "ix_sec_frame_snapshots_fiscal_year",
        "sec_frame_snapshots",
        ["fiscal_year", "fiscal_quarter"],
    )

    op.create_table(
        "sec_frame_company_facts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.Integer,
            sa.ForeignKey("sec_frame_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cik", sa.String(20), nullable=False),
        sa.Column("entity_name", sa.String(255), nullable=False, server_default=""),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("value", sa.Float, nullable=True),
        sa.Column("accession_number", sa.String(30), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "snapshot_id", "cik",
            name="uq_sec_frame_company_facts_snapshot_cik",
        ),
    )
    op.create_index(
        "ix_sec_frame_company_facts_snapshot",
        "sec_frame_company_facts",
        ["snapshot_id"],
    )
    op.create_index(
        "ix_sec_frame_company_facts_cik",
        "sec_frame_company_facts",
        ["cik"],
    )
    op.create_index(
        "ix_sec_frame_company_facts_snapshot_cik",
        "sec_frame_company_facts",
        ["snapshot_id", "cik"],
    )


def downgrade() -> None:
    op.drop_table("sec_frame_company_facts")
    op.drop_table("sec_frame_snapshots")
