"""add staged poem workflow fields

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-18 12:00:00.000000

"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


POEM_SOURCE_LIMIT_INDEX = "ix_poem_source_user_id_status_is_deleted"
POEM_VARIANT_UNIQUE_INDEX = "uq_poem_poem_source_id_variant_key_active"


def upgrade() -> None:
    op.add_column("poem_source", sa.Column("image_analysis", sa.Text(), nullable=True))
    op.add_column("poem_source", sa.Column("follow_up_questions", sa.JSON(), nullable=True))
    op.add_column("poem_source", sa.Column("follow_up_answers", sa.JSON(), nullable=True))
    op.add_column("poem_source", sa.Column("error_message", sa.Text(), nullable=True))

    op.add_column("poem", sa.Column("variant_key", sa.String(length=50), nullable=True))
    op.add_column("poem", sa.Column("author_label", sa.String(length=100), nullable=True))

    op.execute(sa.text("UPDATE poem_source SET status = 'complete' WHERE status = 'success'"))
    op.execute(
        sa.text(
            """
            WITH ranked_poems AS (
                SELECT
                    id,
                    ROW_NUMBER() OVER (PARTITION BY poem_source_id ORDER BY id) AS rank
                FROM poem
            )
            UPDATE poem
            SET
                variant_key = CASE ranked_poems.rank
                    WHEN 1 THEN 'poet_modern'
                    WHEN 2 THEN 'poet_classic'
                    WHEN 3 THEN 'poet_mystic'
                    ELSE NULL
                END,
                author_label = CASE ranked_poems.rank
                    WHEN 1 THEN 'Modern Poet'
                    WHEN 2 THEN 'Classic Poet'
                    WHEN 3 THEN 'Mystic Poet'
                    ELSE NULL
                END
            FROM ranked_poems
            WHERE poem.id = ranked_poems.id
            """
        )
    )

    # Composite index to accelerate the per-user request-limit lookup
    # (user_id + status + is_deleted) used by POST /api/v1/poem-source.
    op.create_index(
        POEM_SOURCE_LIMIT_INDEX,
        "poem_source",
        ["user_id", "status", "is_deleted"],
    )

    # Prevent duplicate variants for the same active poem source.
    # Partial on (variant_key IS NOT NULL AND NOT is_deleted) so legacy or
    # soft-deleted rows never interfere with stage-2 re-runs.
    op.create_index(
        POEM_VARIANT_UNIQUE_INDEX,
        "poem",
        ["poem_source_id", "variant_key"],
        unique=True,
        postgresql_where=sa.text("variant_key IS NOT NULL AND is_deleted = false"),
    )


def downgrade() -> None:
    op.drop_index(POEM_VARIANT_UNIQUE_INDEX, table_name="poem")
    op.drop_index(POEM_SOURCE_LIMIT_INDEX, table_name="poem_source")

    op.execute(sa.text("UPDATE poem_source SET status = 'success' WHERE status = 'complete'"))

    op.drop_column("poem", "author_label")
    op.drop_column("poem", "variant_key")

    op.drop_column("poem_source", "error_message")
    op.drop_column("poem_source", "follow_up_answers")
    op.drop_column("poem_source", "follow_up_questions")
    op.drop_column("poem_source", "image_analysis")
