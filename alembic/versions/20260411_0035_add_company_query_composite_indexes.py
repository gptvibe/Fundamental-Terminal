"""add company query composite indexes

Revision ID: 20260411_0035
Revises: 20260406_0034
Create Date: 2026-04-11 11:20:00

"""

from __future__ import annotations

from alembic import op
from sqlalchemy.engine.reflection import Inspector


revision = "20260411_0035"
down_revision = "20260406_0034"
branch_labels = None
depends_on = None


INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    ("companies", "ix_companies_market_sector", ["market_sector"]),
    ("companies", "ix_companies_market_industry", ["market_industry"]),
    (
        "financial_statements",
        "ix_financial_statements_company_type_period_end_filing",
        ["company_id", "statement_type", "period_end", "filing_type"],
    ),
    (
        "dataset_refresh_state",
        "ix_dataset_refresh_state_dataset_company_checked",
        ["dataset", "company_id", "last_checked"],
    ),
    (
        "derived_metric_points",
        "ix_derived_metric_points_company_type_period_end",
        ["company_id", "period_type", "period_end", "metric_key"],
    ),
    (
        "financial_restatements",
        "ix_financial_restatements_company_acceptance_filing_period",
        ["company_id", "filing_acceptance_at", "filing_date", "period_end"],
    ),
    (
        "insider_trades",
        "ix_insider_trades_company_transaction_filing_id",
        ["company_id", "transaction_date", "filing_date", "id"],
    ),
    (
        "form144_filings",
        "ix_form144_filings_company_sale_filing_id",
        ["company_id", "planned_sale_date", "filing_date", "id"],
    ),
    (
        "earnings_releases",
        "ix_earnings_releases_company_filing_reported_id",
        ["company_id", "filing_date", "reported_period_end", "id"],
    ),
    (
        "earnings_model_points",
        "ix_earnings_model_points_company_period_end_id",
        ["company_id", "period_end", "id"],
    ),
    (
        "institutional_holdings",
        "ix_institutional_holdings_company_reporting_value",
        ["company_id", "reporting_date", "market_value"],
    ),
    (
        "beneficial_ownership_reports",
        "ix_beneficial_ownership_reports_company_filing_id",
        ["company_id", "filing_date", "id"],
    ),
    (
        "filing_events",
        "ix_filing_events_company_filing_report_accession_item",
        ["company_id", "filing_date", "report_date", "accession_number", "item_code"],
    ),
    (
        "capital_markets_events",
        "ix_capital_markets_events_company_filing_id",
        ["company_id", "filing_date", "id"],
    ),
    (
        "comment_letters",
        "ix_comment_letters_company_filing_id",
        ["company_id", "filing_date", "id"],
    ),
    (
        "capital_structure_snapshots",
        "ix_capital_structure_snapshots_company_period_updated_id",
        ["company_id", "period_end", "last_updated", "id"],
    ),
    (
        "proxy_statements",
        "ix_proxy_statements_company_filing_id",
        ["company_id", "filing_date", "id"],
    ),
    (
        "executive_compensation",
        "ix_executive_compensation_company_year_total",
        ["company_id", "fiscal_year", "total_compensation"],
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    for table_name, index_name, columns in INDEXES:
        existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name not in existing_indexes:
            op.create_index(index_name, table_name, columns, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    for table_name, index_name, _columns in reversed(INDEXES):
        existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name=table_name)
