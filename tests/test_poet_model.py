"""Model-level tests for the curated poets catalog."""

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.app.core.db.database import Base
from src.app.models.poet import Poet


def test_poet_model_round_trips_with_json_default() -> None:
    """Poet rows preserve JSON style markers and default to an empty list."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Poet.__table__])

    try:
        with Session(engine) as session:
            poet = Poet(
                name="Emily Dickinson",
                era="19th century",
                known_for="Slant rhyme and compact lyric",
            )
            poet.id = 12

            session.add(poet)
            session.commit()
            session.expire_all()

            loaded = session.scalars(select(Poet).where(Poet.id == 12)).one()

        assert loaded.name == "Emily Dickinson"
        assert loaded.style_markers == []
        assert loaded.is_active is True
    finally:
        Base.metadata.drop_all(engine, tables=[Poet.__table__])
        engine.dispose()


def test_poet_model_round_trips_style_markers() -> None:
    """Explicit style markers survive a DB write/read cycle."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[Poet.__table__])

    try:
        with Session(engine) as session:
            poet = Poet(
                name="Walt Whitman",
                era="19th century",
                known_for="American free verse",
                style_markers=["long line", "catalog imagery"],
            )
            poet.id = 11

            session.add(poet)
            session.commit()
            session.expire_all()

            loaded = session.scalars(select(Poet).where(Poet.id == 11)).one()

        assert loaded.style_markers == ["long line", "catalog imagery"]
    finally:
        Base.metadata.drop_all(engine, tables=[Poet.__table__])
        engine.dispose()
