"""add dimension sort_order

Revision ID: c9a3f7e21b45
Revises: b8f2c1a4d9e0
Create Date: 2026-07-23

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9a3f7e21b45"
down_revision: Union[str, None] = "b8f2c1a4d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "dimensions",
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
    )
    # Backfill so existing rows keep their current display order
    # (list was created_at DESC → newest first gets the smallest sort_order).
    op.execute(
        """
        UPDATE dimensions AS d
        SET sort_order = t.rn
        FROM (
            SELECT id, ROW_NUMBER() OVER (ORDER BY created_at DESC) - 1 AS rn
            FROM dimensions
        ) AS t
        WHERE d.id = t.id
        """
    )


def downgrade() -> None:
    op.drop_column("dimensions", "sort_order")
