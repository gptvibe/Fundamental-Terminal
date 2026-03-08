"""create financial schema

Revision ID: 20260307_0001
Revises:
Create Date: 2026-03-07 00:00:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260307_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "companies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=16), nullable=False),
        sa.Column("cik", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("sector", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_companies_ticker", "companies", ["ticker"], unique=True)
    op.create_index("ix_companies_cik", "companies", ["cik"], unique=True)
    op.create_index("ix_companies_ticker_cik", "companies", ["ticker", "cik"], unique=False)

    op.create_table(
        "financial_statements",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("filing_type", sa.String(length=32), nullable=False),
        sa.Column("statement_type", sa.String(length=32), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "company_id",
            "period_start",
            "period_end",
            "filing_type",
            "statement_type",
            "source",
            name="uq_financial_statements_company_period_type_source",
        ),
    )
    op.create_index("ix_financial_statements_company_id", "financial_statements", ["company_id"], unique=False)
    op.create_index(
        "ix_financial_statements_company_last_checked",
        "financial_statements",
        ["company_id", "last_checked"],
        unique=False,
    )
    op.create_index(
        "ix_financial_statements_company_period_end",
        "financial_statements",
        ["company_id", "period_end"],
        unique=False,
    )
    op.create_index(
        "ix_financial_statements_statement_type",
        "financial_statements",
        ["statement_type"],
        unique=False,
    )

    op.create_table(
        "models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("model_version", sa.String(length=50), nullable=False),
        sa.Column("input_periods", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_models_company_id", "models", ["company_id"], unique=False)
    op.create_index(
        "ix_models_company_name_version",
        "models",
        ["company_id", "model_name", "model_version"],
        unique=False,
    )
    op.create_index("ix_models_created_at", "models", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_models_created_at", table_name="models")
    op.drop_index("ix_models_company_name_version", table_name="models")
    op.drop_index("ix_models_company_id", table_name="models")
    op.drop_table("models")

    op.drop_index("ix_financial_statements_statement_type", table_name="financial_statements")
    op.drop_index("ix_financial_statements_company_last_checked", table_name="financial_statements")
    op.drop_index("ix_financial_statements_company_period_end", table_name="financial_statements")
    op.drop_index("ix_financial_statements_company_id", table_name="financial_statements")
    op.drop_table("financial_statements")

    op.drop_index("ix_companies_ticker_cik", table_name="companies")
    op.drop_index("ix_companies_cik", table_name="companies")
    op.drop_index("ix_companies_ticker", table_name="companies")
    op.drop_table("companies")
