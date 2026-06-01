"""drop classic/modern/mystic poem variants

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-04-28 16:40:00.000000

The poet-based workflow yields exactly one poem per source. We drop the
``variant_key`` / ``author_label`` columns and replace the per-variant
partial unique index with one that enforces "at most one active poem
per poem_source".

Downgrade re-creates the old shape but leaves all rows with NULL
variant data — the original seeded values are not reconstructed.
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


OLD_VARIANT_INDEX = "uq_poem_poem_source_id_variant_key_active"
NEW_ACTIVE_POEM_INDEX = "uq_poem_poem_source_id_active"


def upgrade() -> None:
    op.drop_index(OLD_VARIANT_INDEX, table_name="poem")
    op.drop_column("poem", "author_label")
    op.drop_column("poem", "variant_key")

    # New invariant: at most one active (non-deleted) poem per source.
    op.create_index(
        NEW_ACTIVE_POEM_INDEX,
        "poem",
        ["poem_source_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index(NEW_ACTIVE_POEM_INDEX, table_name="poem")

    op.add_column("poem", sa.Column("variant_key", sa.String(length=50), nullable=True))
    op.add_column("poem", sa.Column("author_label", sa.String(length=100), nullable=True))

    op.create_index(
        OLD_VARIANT_INDEX,
        "poem",
        ["poem_source_id", "variant_key"],
        unique=True,
        postgresql_where=sa.text("variant_key IS NOT NULL AND is_deleted = false"),
    )
