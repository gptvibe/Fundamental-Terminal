"""add DESC ordering indexes for query optimization

Revision ID: 20260512_0049
Revises: 20260510_0048
Create Date: 2026-05-12 12:00:00

This migration adds indexes with explicit DESC ordering on common filtering columns
to support efficient as_of and latest queries without Python-side filtering.

"""

from __future__ import annotations

from alembic import op
from sqlalchemy.engine.reflection import Inspector


revision = "20260512_0049"
down_revision = "20260510_0048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    # price_history: support as_of filtering on trade_date DESC
    price_indexes = {index["name"] for index in inspector.get_indexes("price_history")}
    if "ix_price_history_company_trade_date_desc" not in price_indexes:
        op.create_index(
            "ix_price_history_company_trade_date_desc",
            "price_history",
            ["company_id", "trade_date"],
            unique=False,
            postgresql_using="btree",
            postgresql_ops={"trade_date": "DESC"},
        )

    # financial_statements: support as_of and latest period_end DESC queries
    financial_indexes = {index["name"] for index in inspector.get_indexes("financial_statements")}
    if "ix_financial_statements_company_period_end_desc" not in financial_indexes:
        op.create_index(
            "ix_financial_statements_company_period_end_desc",
            "financial_statements",
            ["company_id", "period_end"],
            unique=False,
            postgresql_using="btree",
            postgresql_ops={"period_end": "DESC"},
        )

    # financial_statements: support filtered latest by type and period_end DESC
    if "ix_financial_statements_company_type_period_end_desc" not in financial_indexes:
        op.create_index(
            "ix_financial_statements_company_type_period_end_desc",
            "financial_statements",
            ["company_id", "statement_type", "period_end"],
            unique=False,
            postgresql_using="btree",
            postgresql_ops={"period_end": "DESC"},
        )

    # derived_metric_points: support latest period_end DESC queries
    derived_indexes = {index["name"] for index in inspector.get_indexes("derived_metric_points")}
    if "ix_derived_metric_points_company_period_end_desc" not in derived_indexes:
        op.create_index(
            "ix_derived_metric_points_company_period_end_desc",
            "derived_metric_points",
            ["company_id", "period_end"],
            unique=False,
            postgresql_using="btree",
            postgresql_ops={"period_end": "DESC"},
        )

    # derived_metric_points: support filtered queries by metric_name and period_end DESC
    if "ix_derived_metric_points_company_metric_period_end_desc" not in derived_indexes:
        op.create_index(
            "ix_derived_metric_points_company_metric_period_end_desc",
            "derived_metric_points",
            ["company_id", "metric_key", "period_end"],
            unique=False,
            postgresql_using="btree",
            postgresql_ops={"period_end": "DESC"},
        )

    # insider_trades: support latest transaction_date DESC queries
    insider_indexes = {index["name"] for index in inspector.get_indexes("insider_trades")}
    if "ix_insider_trades_company_transaction_date_desc" not in insider_indexes:
        op.create_index(
            "ix_insider_trades_company_transaction_date_desc",
            "insider_trades",
            ["company_id", "transaction_date"],
            unique=False,
            postgresql_using="btree",
            postgresql_ops={"transaction_date": "DESC NULLS LAST"},
        )

    # institutional_holdings: support latest reporting_date DESC queries
    inst_indexes = {index["name"] for index in inspector.get_indexes("institutional_holdings")}
    if "ix_institutional_holdings_company_reporting_date_desc" not in inst_indexes:
        op.create_index(
            "ix_institutional_holdings_company_reporting_date_desc",
            "institutional_holdings",
            ["company_id", "reporting_date"],
            unique=False,
            postgresql_using="btree",
            postgresql_ops={"reporting_date": "DESC"},
        )

    # capital_markets_events: support latest filing_date DESC queries
    capital_indexes = {index["name"] for index in inspector.get_indexes("capital_markets_events")}
    if "ix_capital_markets_events_company_filing_date_desc" not in capital_indexes:
        op.create_index(
            "ix_capital_markets_events_company_filing_date_desc",
            "capital_markets_events",
            ["company_id", "filing_date"],
            unique=False,
            postgresql_using="btree",
            postgresql_ops={"filing_date": "DESC NULLS LAST"},
        )

    # beneficial_ownership_reports: support latest filing_date DESC queries
    beneficial_indexes = {index["name"] for index in inspector.get_indexes("beneficial_ownership_reports")}
    if "ix_beneficial_ownership_reports_company_filing_date_desc" not in beneficial_indexes:
        op.create_index(
            "ix_beneficial_ownership_reports_company_filing_date_desc",
            "beneficial_ownership_reports",
            ["company_id", "filing_date"],
            unique=False,
            postgresql_using="btree",
            postgresql_ops={"filing_date": "DESC NULLS LAST"},
        )

    # comment_letters: support latest filing_date DESC queries
    comment_indexes = {index["name"] for index in inspector.get_indexes("comment_letters")}
    if "ix_comment_letters_company_filing_date_desc" not in comment_indexes:
        op.create_index(
            "ix_comment_letters_company_filing_date_desc",
            "comment_letters",
            ["company_id", "filing_date"],
            unique=False,
            postgresql_using="btree",
            postgresql_ops={"filing_date": "DESC NULLS LAST"},
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    indexes_to_drop = [
        ("price_history", "ix_price_history_company_trade_date_desc"),
        ("financial_statements", "ix_financial_statements_company_period_end_desc"),
        ("financial_statements", "ix_financial_statements_company_type_period_end_desc"),
        ("derived_metric_points", "ix_derived_metric_points_company_period_end_desc"),
        ("derived_metric_points", "ix_derived_metric_points_company_metric_period_end_desc"),
        ("insider_trades", "ix_insider_trades_company_transaction_date_desc"),
        ("institutional_holdings", "ix_institutional_holdings_company_reporting_date_desc"),
        ("capital_markets_events", "ix_capital_markets_events_company_filing_date_desc"),
        ("beneficial_ownership_reports", "ix_beneficial_ownership_reports_company_filing_date_desc"),
        ("comment_letters", "ix_comment_letters_company_filing_date_desc"),
    ]

    for table_name, index_name in indexes_to_drop:
        indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name in indexes:
            op.drop_index(index_name, table_name=table_name)
