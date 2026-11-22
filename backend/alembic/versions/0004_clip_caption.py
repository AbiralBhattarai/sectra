"""clip caption

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-20

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("clips", sa.Column("caption", sa.Text(), nullable=False, server_default=""))


def downgrade() -> None:
    op.drop_column("clips", "caption")
