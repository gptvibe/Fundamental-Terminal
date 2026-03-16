"""add beneficial ownership scaffolding

Revision ID: 20260315_0009
Revises: 20260315_0008
Create Date: 2026-03-15 01:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260315_0009"
down_revision = "20260315_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("beneficial_ownership_last_checked", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "beneficial_ownership_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=32), nullable=False),
        sa.Column("form", sa.String(length=16), nullable=False),
        sa.Column("base_form", sa.String(length=8), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("is_amendment", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("primary_document", sa.String(length=255), nullable=True),
        sa.Column("primary_doc_description", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.String(length=500), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "accession_number", name="uq_beneficial_ownership_reports_company_accession"),
    )
    op.create_index("ix_beneficial_ownership_reports_company_id", "beneficial_ownership_reports", ["company_id"], unique=False)
    op.create_index(
        "ix_beneficial_ownership_reports_company_filing_date",
        "beneficial_ownership_reports",
        ["company_id", "filing_date"],
        unique=False,
    )
    op.create_index(
        "ix_beneficial_ownership_reports_company_last_checked",
        "beneficial_ownership_reports",
        ["company_id", "last_checked"],
        unique=False,
    )

    op.create_table(
        "beneficial_ownership_parties",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("party_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(["report_id"], ["beneficial_ownership_reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_beneficial_ownership_parties_report_id", "beneficial_ownership_parties", ["report_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_beneficial_ownership_parties_report_id", table_name="beneficial_ownership_parties")
    op.drop_table("beneficial_ownership_parties")

    op.drop_index("ix_beneficial_ownership_reports_company_last_checked", table_name="beneficial_ownership_reports")
    op.drop_index("ix_beneficial_ownership_reports_company_filing_date", table_name="beneficial_ownership_reports")
    op.drop_index("ix_beneficial_ownership_reports_company_id", table_name="beneficial_ownership_reports")
    op.drop_table("beneficial_ownership_reports")

    op.drop_column("companies", "beneficial_ownership_last_checked")