"""add_enhance_to_poem_source

Revision ID: 99629feea32a
Revises: 00fc5017cf3c
Create Date: 2026-01-31 18:22:45.588926

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '99629feea32a'
down_revision: Union[str, None] = '00fc5017cf3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('poem_source', sa.Column('enhance', sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column('poem_source', 'enhance')
