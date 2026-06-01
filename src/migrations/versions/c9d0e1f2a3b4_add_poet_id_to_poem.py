"""add poet id to poem

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-04-28 16:45:00.000000
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("poem", sa.Column("poet_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_poem_poet_id", "poem", ["poet_id"])
    op.create_foreign_key(
        "fk_poem_poet_id_poets",
        "poem",
        "poets",
        ["poet_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_poem_poet_id_poets", "poem", type_="foreignkey")
    op.drop_index("ix_poem_poet_id", table_name="poem")
    op.drop_column("poem", "poet_id")
