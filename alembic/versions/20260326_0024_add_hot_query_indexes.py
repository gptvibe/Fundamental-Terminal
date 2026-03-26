"""add hot query indexes

Revision ID: 20260326_0024
Revises: 20260326_0023
Create Date: 2026-03-26 13:45:00

"""

from __future__ import annotations

from alembic import op
from sqlalchemy.engine.reflection import Inspector


revision = "20260326_0024"
down_revision = "20260326_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    financial_indexes = {index["name"] for index in inspector.get_indexes("financial_statements")}
    if "ix_financial_statements_company_type_period_end" not in financial_indexes:
        op.create_index(
            "ix_financial_statements_company_type_period_end",
            "financial_statements",
            ["company_id", "statement_type", "period_end"],
            unique=False,
        )

    model_indexes = {index["name"] for index in inspector.get_indexes("models")}
    if "ix_models_company_name_created_id" not in model_indexes:
        op.create_index(
            "ix_models_company_name_created_id",
            "models",
            ["company_id", "model_name", "created_at", "id"],
            unique=False,
        )

    price_indexes = {index["name"] for index in inspector.get_indexes("price_history")}
    if "ix_price_history_company_trade_date_id" not in price_indexes:
        op.create_index(
            "ix_price_history_company_trade_date_id",
            "price_history",
            ["company_id", "trade_date", "id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    financial_indexes = {index["name"] for index in inspector.get_indexes("financial_statements")}
    if "ix_financial_statements_company_type_period_end" in financial_indexes:
        op.drop_index("ix_financial_statements_company_type_period_end", table_name="financial_statements")

    model_indexes = {index["name"] for index in inspector.get_indexes("models")}
    if "ix_models_company_name_created_id" in model_indexes:
        op.drop_index("ix_models_company_name_created_id", table_name="models")

    price_indexes = {index["name"] for index in inspector.get_indexes("price_history")}
    if "ix_price_history_company_trade_date_id" in price_indexes:
        op.drop_index("ix_price_history_company_trade_date_id", table_name="price_history")
