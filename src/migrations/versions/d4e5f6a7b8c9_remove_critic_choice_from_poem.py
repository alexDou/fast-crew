"""remove critic choice from poem

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-04-05 00:00:00.000000

"""
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("poem", "critic_choice")


def downgrade() -> None:
    op.add_column(
        "poem",
        sa.Column("critic_choice", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
