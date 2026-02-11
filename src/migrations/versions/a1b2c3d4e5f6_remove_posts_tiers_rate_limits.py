"""remove posts tiers rate_limits

Revision ID: a1b2c3d4e5f6
Revises: f52d1f537b5e
Create Date: 2026-02-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f52d1f537b5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop post table
    op.drop_index(op.f('ix_post_is_deleted'), table_name='post')
    op.drop_index(op.f('ix_post_created_by_user_id'), table_name='post')
    op.drop_table('post')

    # Drop tier_id foreign key and index from user table
    op.drop_index(op.f('ix_user_tier_id'), table_name='user')
    op.drop_constraint('user_tier_id_fkey', 'user', type_='foreignkey')
    op.drop_column('user', 'tier_id')

    # Drop rate_limit table
    op.drop_index(op.f('ix_rate_limit_tier_id'), table_name='rate_limit')
    op.drop_table('rate_limit')

    # Drop tier table
    op.drop_table('tier')


def downgrade() -> None:
    # Recreate tier table
    op.create_table('tier',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id'),
    sa.UniqueConstraint('name')
    )

    # Recreate rate_limit table
    op.create_table('rate_limit',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('tier_id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('path', sa.String(), nullable=False),
    sa.Column('limit', sa.Integer(), nullable=False),
    sa.Column('period', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['tier_id'], ['tier.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_rate_limit_tier_id'), 'rate_limit', ['tier_id'], unique=False)

    # Recreate tier_id on user
    op.add_column('user', sa.Column('tier_id', sa.Integer(), nullable=True))
    op.create_foreign_key('user_tier_id_fkey', 'user', 'tier', ['tier_id'], ['id'])
    op.create_index(op.f('ix_user_tier_id'), 'user', ['tier_id'], unique=False)

    # Recreate post table
    op.create_table('post',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=30), nullable=False),
    sa.Column('text', sa.String(length=63206), nullable=False),
    sa.Column('uuid', sa.UUID(), nullable=False),
    sa.Column('media_url', sa.String(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id'),
    sa.UniqueConstraint('uuid')
    )
    op.create_index(op.f('ix_post_created_by_user_id'), 'post', ['created_by_user_id'], unique=False)
    op.create_index(op.f('ix_post_is_deleted'), 'post', ['is_deleted'], unique=False)
