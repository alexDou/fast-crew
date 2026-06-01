"""ORM model for the curated poets catalog.

The ``embedding`` column is created in migration ``a7b8c9d0e1f2`` as a
``vector(512)`` placeholder reserved for the future pre-filter
described in ``staged-workflow-handoff.md`` §8. We do not declare it
on the SQLAlchemy model because no MVP code reads or writes it, and
because referencing the pgvector type would force every test
environment to install the package even when pgvector is unused.
Once the pre-filter ships, add the column declaration alongside the
``pgvector.sqlalchemy.Vector`` type.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..core.db.database import Base


class Poet(Base):
    __tablename__ = "poets"

    id: Mapped[int] = mapped_column(
        "id",
        BigInteger,
        autoincrement=True,
        nullable=False,
        primary_key=True,
        init=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    era: Mapped[str] = mapped_column(Text, nullable=False)
    known_for: Mapped[str] = mapped_column(Text, nullable=False)
    style_markers: Mapped[list[str]] = mapped_column(JSON, nullable=False, default_factory=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default_factory=lambda: datetime.now(UTC),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=None,
        onupdate=lambda: datetime.now(UTC),
    )
