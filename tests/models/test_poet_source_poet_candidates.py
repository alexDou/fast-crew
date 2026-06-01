"""Model and resume tests for persisted ``poet_candidates`` on poem_source."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from src.app.api.v1.poem_source import check_poem_source_ready
from src.app.core.db.database import Base
from src.app.models.poem_source import PoemSource
from src.app.models.user import User
from src.app.schemas.poem_source import PoemSourceStatus, PoemSourceUpdate
from tests.fixtures.poets import poet_card_fixtures


def test_poem_source_update_schema_round_trips_poet_candidates() -> None:
    cards = poet_card_fixtures()[:3]
    update = PoemSourceUpdate(
        status=PoemSourceStatus.STAGE_1.value,
        follow_up_questions=[{"id": "q1", "text": "Mood?"}],
        poet_candidates=cards,
    )

    dumped = update.model_dump()
    assert len(dumped["poet_candidates"]) == 3
    assert dumped["poet_candidates"][0]["name"] == cards[0].name


def test_poem_source_poet_candidates_survive_db_round_trip() -> None:
    candidates = [card.model_dump() for card in poet_card_fixtures()[:3]]
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[User.__table__, PoemSource.__table__])

    try:
        with Session(engine) as session:
            user = User(
                name="Test User",
                username="testuser",
                email="test@example.com",
                hashed_password="hashed",
            )
            session.add(user)
            session.flush()

            source = PoemSource(
                user_id=user.id,
                media_path="media/test.png",
                status=PoemSourceStatus.STAGE_1.value,
                follow_up_questions=[{"id": "q1", "text": "Mood?"}],
                poet_candidates=candidates,
            )
            session.add(source)
            session.commit()
            session.expire_all()

            loaded = session.scalars(select(PoemSource).where(PoemSource.id == source.id)).one()

        assert loaded.poet_candidates == candidates
    finally:
        Base.metadata.drop_all(engine, tables=[User.__table__, PoemSource.__table__])
        engine.dispose()


@pytest.mark.asyncio
async def test_ready_returns_persisted_candidates_without_re_running_picker(
    mock_db, current_user_dict
) -> None:
    persisted = [card.model_dump() for card in poet_card_fixtures()[:2]]

    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        with patch("src.app.services.crewai.prompts.generate_poet_candidate_ids") as mock_picker:
            mock_get.return_value = {
                "id": 9,
                "status": PoemSourceStatus.STAGE_1.value,
                "follow_up_questions": [{"id": "q1", "text": "Mood?"}],
                "poet_candidates": persisted,
                "error_message": None,
            }

            result = await check_poem_source_ready(Mock(), 9, mock_db, current_user_dict)

    mock_picker.assert_not_called()
    assert result["poet_candidates"] == persisted
