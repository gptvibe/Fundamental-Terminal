"""add company search trigram indexes

Revision ID: 20260321_0017
Revises: 20260319_0016
Create Date: 2026-03-21 00:00:00.000000
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260321_0017"
down_revision = "20260319_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_companies_name_trgm ON companies USING gin (lower(name) gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_companies_cik_trgm ON companies USING gin (cik gin_trgm_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_companies_cik_trgm")
    op.execute("DROP INDEX IF EXISTS ix_companies_name_trgm")
