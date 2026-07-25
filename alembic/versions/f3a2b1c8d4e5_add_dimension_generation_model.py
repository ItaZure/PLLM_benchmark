"""Add generation_model_id to dimensions

Revision ID: f3a2b1c8d4e5
Revises: c9a3f7e21b45
Create Date: 2026-07-25
"""
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f3a2b1c8d4e5"
down_revision: Union[str, None] = "c9a3f7e21b45"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "dimensions",
        sa.Column(
            "generation_model_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("dimensions", "generation_model_id")
