"""add soft delete to poem

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('poem', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('poem', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.create_index(op.f('ix_poem_is_deleted'), 'poem', ['is_deleted'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_poem_is_deleted'), table_name='poem')
    op.drop_column('poem', 'is_deleted')
    op.drop_column('poem', 'deleted_at')
