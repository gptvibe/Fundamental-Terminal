"""add comment letters cache

Revision ID: 20260404_0032
Revises: 20260404_0031
Create Date: 2026-04-04 00:30:00

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260404_0032"
down_revision = "20260404_0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("comment_letters_last_checked", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "comment_letters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("accession_number", sa.String(length=32), nullable=False),
        sa.Column("filing_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("sec_url", sa.String(length=500), nullable=False),
        sa.Column("last_updated", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("last_checked", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "accession_number", name="uq_comment_letters_company_accession"),
    )
    op.create_index("ix_comment_letters_company_id", "comment_letters", ["company_id"], unique=False)
    op.create_index("ix_comment_letters_company_filing_date", "comment_letters", ["company_id", "filing_date"], unique=False)
    op.create_index("ix_comment_letters_company_last_checked", "comment_letters", ["company_id", "last_checked"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_comment_letters_company_last_checked", table_name="comment_letters")
    op.drop_index("ix_comment_letters_company_filing_date", table_name="comment_letters")
    op.drop_index("ix_comment_letters_company_id", table_name="comment_letters")
    op.drop_table("comment_letters")

    op.drop_column("companies", "comment_letters_last_checked")
