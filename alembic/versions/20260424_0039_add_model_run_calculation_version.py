"""add model run calculation version

Revision ID: 20260424_0039
Revises: 20260423_0038
Create Date: 2026-04-24 10:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260424_0039"
down_revision = "20260423_0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("models", sa.Column("calculation_version", sa.String(length=50), nullable=True))
    op.create_index(
        "ix_models_company_name_calculation_version",
        "models",
        ["company_id", "model_name", "calculation_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_models_company_name_calculation_version", table_name="models")
    op.drop_column("models", "calculation_version")