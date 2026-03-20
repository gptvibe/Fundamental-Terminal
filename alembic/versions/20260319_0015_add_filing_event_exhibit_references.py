"""add filing event exhibit references

Revision ID: 20260319_0015
Revises: 20260319_0014
Create Date: 2026-03-19 19:40:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260319_0015"
down_revision = "20260319_0014"
branch_labels = None
depends_on = None


_EMPTY_JSON_ARRAY = sa.text("'[]'::jsonb")


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column.get("name") == column_name for column in columns)


def upgrade() -> None:
    if _has_column("filing_events", "exhibit_references"):
        return

    op.add_column(
        "filing_events",
        sa.Column(
            "exhibit_references",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=_EMPTY_JSON_ARRAY,
        ),
    )
    op.execute("UPDATE filing_events SET exhibit_references = '[]'::jsonb WHERE exhibit_references IS NULL")
    op.alter_column("filing_events", "exhibit_references", server_default=None)


def downgrade() -> None:
    if not _has_column("filing_events", "exhibit_references"):
        return

    op.drop_column("filing_events", "exhibit_references")
