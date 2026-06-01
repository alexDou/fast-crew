"""enable pgvector extension

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-28 16:30:00.000000

This migration only enables the ``pgvector`` extension. No schema
changes are introduced here so the upgrade is safe to apply in any
environment that has the extension available; environments without
the extension installed should install it before running this
migration (``apt install postgresql-15-pgvector`` on Debian-family
distributions, or the equivalent for the local Postgres major
version).
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: safe even when the extension is already enabled in
    # the target database (e.g. shared dev cluster).
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))


def downgrade() -> None:
    # We do not drop the extension on downgrade: other tables or
    # databases in the cluster may rely on it. Operators that want to
    # remove it can do so manually.
    pass
