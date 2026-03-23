"""Merge proxy and macro migration heads.

Revision ID: 20260323_0019
Revises: 20260321_0018, 20260323_0018
Create Date: 2026-03-23
"""

from __future__ import annotations

from alembic import op


# revision identifiers, used by Alembic.
revision = "20260323_0019"
down_revision = ("20260321_0018", "20260323_0018")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
