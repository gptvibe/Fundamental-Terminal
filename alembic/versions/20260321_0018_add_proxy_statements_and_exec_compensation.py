"""add proxy statements and executive compensation tables

Revision ID: 20260321_0018
Revises: 20260321_0017
Create Date: 2026-03-21 18:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260321_0018"
down_revision = "20260321_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # proxy_statements — one row per DEF 14A / DEFA14A accession number
    # ------------------------------------------------------------------
    op.create_table(
        "proxy_statements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=32), nullable=False),
        sa.Column("form", sa.String(length=16), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("report_date", sa.Date(), nullable=True),
        sa.Column("meeting_date", sa.Date(), nullable=True),
        sa.Column("board_nominee_count", sa.Integer(), nullable=True),
        sa.Column("vote_item_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("executive_comp_table_detected", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("primary_document", sa.String(length=255), nullable=True),
        sa.Column("source_url", sa.String(length=500), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "accession_number",
            name="uq_proxy_statements_company_accession",
        ),
    )
    op.create_index("ix_proxy_statements_company_id", "proxy_statements", ["company_id"], unique=False)
    op.create_index(
        "ix_proxy_statements_company_filing_date",
        "proxy_statements",
        ["company_id", "filing_date"],
        unique=False,
    )
    op.create_index(
        "ix_proxy_statements_company_last_checked",
        "proxy_statements",
        ["company_id", "last_checked"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # proxy_vote_results — proposal-level ballot data per proxy statement
    # ------------------------------------------------------------------
    op.create_table(
        "proxy_vote_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("proxy_statement_id", sa.Integer(), nullable=False),
        sa.Column("proposal_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("for_votes", sa.BigInteger(), nullable=True),
        sa.Column("against_votes", sa.BigInteger(), nullable=True),
        sa.Column("abstain_votes", sa.BigInteger(), nullable=True),
        sa.Column("broker_non_votes", sa.BigInteger(), nullable=True),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["proxy_statement_id"], ["proxy_statements.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "proxy_statement_id",
            "proposal_number",
            name="uq_proxy_vote_results_stmt_proposal",
        ),
    )
    op.create_index(
        "ix_proxy_vote_results_company_id", "proxy_vote_results", ["company_id"], unique=False
    )
    op.create_index(
        "ix_proxy_vote_results_proxy_statement_id",
        "proxy_vote_results",
        ["proxy_statement_id"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # executive_compensation — named-executive pay rows per proxy statement
    # ------------------------------------------------------------------
    op.create_table(
        "executive_compensation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("proxy_statement_id", sa.Integer(), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=True),
        sa.Column("executive_name", sa.String(length=200), nullable=False),
        sa.Column("executive_title", sa.String(length=200), nullable=True),
        sa.Column("salary", sa.Float(), nullable=True),
        sa.Column("bonus", sa.Float(), nullable=True),
        sa.Column("stock_awards", sa.Float(), nullable=True),
        sa.Column("option_awards", sa.Float(), nullable=True),
        sa.Column("non_equity_incentive", sa.Float(), nullable=True),
        sa.Column("other_compensation", sa.Float(), nullable=True),
        sa.Column("total_compensation", sa.Float(), nullable=True),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["company_id"], ["companies.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["proxy_statement_id"], ["proxy_statements.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "proxy_statement_id",
            "executive_name",
            "fiscal_year",
            name="uq_exec_comp_stmt_name_year",
        ),
    )
    op.create_index(
        "ix_executive_compensation_company_id",
        "executive_compensation",
        ["company_id"],
        unique=False,
    )
    op.create_index(
        "ix_executive_compensation_proxy_statement_id",
        "executive_compensation",
        ["proxy_statement_id"],
        unique=False,
    )

    # ------------------------------------------------------------------
    # Track last proxy parse time on companies
    # ------------------------------------------------------------------
    op.add_column(
        "companies",
        sa.Column("proxy_statements_last_checked", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "proxy_statements_last_checked")

    op.drop_index("ix_executive_compensation_proxy_statement_id", table_name="executive_compensation")
    op.drop_index("ix_executive_compensation_company_id", table_name="executive_compensation")
    op.drop_table("executive_compensation")

    op.drop_index("ix_proxy_vote_results_proxy_statement_id", table_name="proxy_vote_results")
    op.drop_index("ix_proxy_vote_results_company_id", table_name="proxy_vote_results")
    op.drop_table("proxy_vote_results")

    op.drop_index("ix_proxy_statements_company_last_checked", table_name="proxy_statements")
    op.drop_index("ix_proxy_statements_company_filing_date", table_name="proxy_statements")
    op.drop_index("ix_proxy_statements_company_id", table_name="proxy_statements")
    op.drop_table("proxy_statements")
