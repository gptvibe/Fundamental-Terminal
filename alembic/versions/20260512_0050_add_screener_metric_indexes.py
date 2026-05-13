"""add screener metric access indexes

Revision ID: 20260512_0050
Revises: 20260512_0049
Create Date: 2026-05-12 18:00:00

"""

from __future__ import annotations

from alembic import op
from sqlalchemy.engine.reflection import Inspector


revision = "20260512_0050"
down_revision = "20260512_0049"
branch_labels = None
depends_on = None


INDEXES: tuple[tuple[str, str, list[str]], ...] = (
    (
        "derived_metric_points",
        "ix_derived_metric_points_period_type_company_period",
        ["period_type", "company_id", "period_end", "metric_key"],
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    for table_name, index_name, columns in INDEXES:
        if not inspector.has_table(table_name):
            continue
        existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name not in existing_indexes:
            op.create_index(index_name, table_name, columns, unique=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    for table_name, index_name, _columns in reversed(INDEXES):
        if not inspector.has_table(table_name):
            continue
        existing_indexes = {index["name"] for index in inspector.get_indexes(table_name)}
        if index_name in existing_indexes:
            op.drop_index(index_name, table_name=table_name)
