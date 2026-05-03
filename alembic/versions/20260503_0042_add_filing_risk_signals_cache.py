"""add filing risk signals cache

Revision ID: 20260503_0042
Revises: 20260501_0041
Create Date: 2026-05-03 09:30:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260503_0042"
down_revision = "20260501_0041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "filing_risk_signals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("cik", sa.String(length=20), nullable=False),
        sa.Column("accession_number", sa.String(length=32), nullable=False),
        sa.Column("form_type", sa.String(length=16), nullable=False),
        sa.Column("filed_date", sa.Date(), nullable=True),
        sa.Column("signal_category", sa.String(length=64), nullable=False),
        sa.Column("matched_phrase", sa.String(length=255), nullable=False),
        sa.Column("context_snippet", sa.String(length=1000), nullable=False),
        sa.Column("confidence", sa.String(length=16), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("source", sa.String(length=500), nullable=False),
        sa.Column("provenance", sa.String(length=64), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "accession_number",
            "signal_category",
            name="uq_filing_risk_signals_company_accession_category",
        ),
    )
    op.create_index("ix_filing_risk_signals_company_id", "filing_risk_signals", ["company_id"], unique=False)
    op.create_index(
        "ix_filing_risk_signals_company_filed_date",
        "filing_risk_signals",
        ["company_id", "filed_date"],
        unique=False,
    )
    op.create_index(
        "ix_filing_risk_signals_company_severity",
        "filing_risk_signals",
        ["company_id", "severity", "filed_date"],
        unique=False,
    )
    op.create_index(
        "ix_filing_risk_signals_company_last_checked",
        "filing_risk_signals",
        ["company_id", "last_checked"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_filing_risk_signals_company_last_checked", table_name="filing_risk_signals")
    op.drop_index("ix_filing_risk_signals_company_severity", table_name="filing_risk_signals")
    op.drop_index("ix_filing_risk_signals_company_filed_date", table_name="filing_risk_signals")
    op.drop_index("ix_filing_risk_signals_company_id", table_name="filing_risk_signals")
    op.drop_table("filing_risk_signals")