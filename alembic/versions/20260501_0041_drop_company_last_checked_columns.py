"""drop legacy company dataset freshness columns

Revision ID: 20260501_0041
Revises: 20260426_0040
Create Date: 2026-05-01 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


revision = "20260501_0041"
down_revision = "20260426_0040"
branch_labels = None
depends_on = None


_COLUMN_DATASET_MAP: tuple[tuple[str, str], ...] = (
    ("insider_trades_last_checked", "insiders"),
    ("institutional_holdings_last_checked", "institutional"),
    ("beneficial_ownership_last_checked", "beneficial_ownership"),
    ("filing_events_last_checked", "filings"),
    ("capital_markets_last_checked", "capital_markets"),
    ("comment_letters_last_checked", "comment_letters"),
    ("form144_filings_last_checked", "form144"),
    ("earnings_last_checked", "earnings"),
    ("proxy_statements_last_checked", "proxy"),
)


def _company_columns(inspector: Inspector) -> set[str]:
    return {column["name"] for column in inspector.get_columns("companies")}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    company_columns = _company_columns(inspector)

    if inspector.has_table("dataset_refresh_state"):
        for column_name, dataset in _COLUMN_DATASET_MAP:
            if column_name not in company_columns:
                continue
            bind.execute(
                sa.text(
                    f"""
                    INSERT INTO dataset_refresh_state (
                        company_id,
                        dataset,
                        last_checked,
                        last_success,
                        freshness_deadline,
                        active_job_id,
                        failure_count,
                        last_error,
                        payload_version_hash,
                        updated_at
                    )
                    SELECT
                        companies.id,
                        :dataset,
                        companies.{column_name},
                        companies.{column_name},
                        NULL,
                        NULL,
                        0,
                        NULL,
                        NULL,
                        COALESCE(companies.{column_name}, now())
                    FROM companies
                    WHERE companies.{column_name} IS NOT NULL
                    ON CONFLICT (company_id, dataset)
                    DO UPDATE SET
                        last_checked = GREATEST(
                            COALESCE(dataset_refresh_state.last_checked, EXCLUDED.last_checked),
                            EXCLUDED.last_checked
                        ),
                        last_success = COALESCE(dataset_refresh_state.last_success, EXCLUDED.last_success),
                        updated_at = GREATEST(dataset_refresh_state.updated_at, EXCLUDED.updated_at)
                    """
                ),
                {"dataset": dataset},
            )

    for column_name, _dataset in _COLUMN_DATASET_MAP:
        if column_name in company_columns:
            op.drop_column("companies", column_name)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    company_columns = _company_columns(inspector)

    for column_name, _dataset in _COLUMN_DATASET_MAP:
        if column_name not in company_columns:
            op.add_column("companies", sa.Column(column_name, sa.DateTime(timezone=True), nullable=True))

    if not inspector.has_table("dataset_refresh_state"):
        return

    for column_name, dataset in _COLUMN_DATASET_MAP:
                bind.execute(
                        sa.text(
                                f"""
                                UPDATE companies
                                SET {column_name} = dataset_refresh_state.last_checked
                                FROM dataset_refresh_state
                                WHERE dataset_refresh_state.company_id = companies.id
                                    AND dataset_refresh_state.dataset = :dataset
                                    AND companies.{column_name} IS NULL
                                """
                        ),
                        {"dataset": dataset},
                )
