"""add selected facts and reconciliation to financial statements

Revision ID: 20260328_0028
Revises: 20260327_0027
Create Date: 2026-03-28 11:15:00

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.engine.reflection import Inspector


revision = "20260328_0028"
down_revision = "20260327_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if "financial_statements" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("financial_statements")}

    if "selected_facts" not in existing_columns:
        op.add_column(
            "financial_statements",
            sa.Column(
                "selected_facts",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )

    if "reconciliation" not in existing_columns:
        op.add_column(
            "financial_statements",
            sa.Column(
                "reconciliation",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)

    if "financial_statements" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("financial_statements")}

    if "reconciliation" in existing_columns:
        op.drop_column("financial_statements", "reconciliation")

    if "selected_facts" in existing_columns:
        op.drop_column("financial_statements", "selected_facts")