"""create poets table

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-04-28 16:35:00.000000

The ``poets`` table stores the curated catalog of poets the picker
agent draws from at the end of stage_1. The ``embedding`` column is a
``vector(512)`` placeholder for the future pre-filter (see
``staged-workflow-handoff.md`` §8); MVP code never reads or writes
it, but reserving the column now keeps the future migration small.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "poets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("era", sa.Text(), nullable=False),
        sa.Column("known_for", sa.Text(), nullable=False),
        sa.Column(
            "style_markers",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.UniqueConstraint("name", name="uq_poets_name"),
    )

    # ``embedding`` is added as raw DDL because it requires the pgvector
    # extension which is enabled in the previous migration.
    op.execute(sa.text("ALTER TABLE poets ADD COLUMN embedding vector(512) NULL"))


def downgrade() -> None:
    op.execute(sa.text("ALTER TABLE poets DROP COLUMN IF EXISTS embedding"))
    op.drop_table("poets")
