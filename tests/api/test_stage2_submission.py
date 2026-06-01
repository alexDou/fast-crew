"""API regression tests for stage-2 answer submission with optional poet_id."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from src.app.api.v1.poem_source import submit_poem_source_answers
from src.app.core.exceptions.http_exceptions import NotFoundException
from src.app.schemas.poem_source import PoemSourceAnswerSubmission, PoemSourceStatus
from tests.fixtures.poets import poet_card_fixtures
from tests.helpers.workflow import scalar_result


@pytest.mark.asyncio
async def test_submit_accepts_poet_id_from_candidates(mock_db, current_user_dict) -> None:
    poet_candidates = [poet_card_fixtures()[0].model_dump()]
    selected_poet_id = poet_candidates[0]["id"]
    mock_db.execute = AsyncMock(side_effect=[scalar_result(None), scalar_result(selected_poet_id)])
    payload = PoemSourceAnswerSubmission(answers={}, poet_id=selected_poet_id)

    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "id": 15,
            "status": PoemSourceStatus.STAGE_1.value,
            "follow_up_questions": [{"id": "q1", "text": "Q?"}],
            "poet_candidates": poet_candidates,
        }

        with patch("src.app.api.v1.poem_source.crud_poem_sources.update", new_callable=AsyncMock):
            with patch("src.app.api.v1.poem_source.crewai_service.start_stage_2_generation") as mock_start:
                await submit_poem_source_answers(Mock(), 15, payload, current_user_dict, mock_db)

    mock_start.assert_called_once_with(poem_source_id=15, poet_id=selected_poet_id)


@pytest.mark.asyncio
async def test_submit_rejects_unknown_poet_id(mock_db, current_user_dict) -> None:
    mock_db.execute = AsyncMock(side_effect=[scalar_result(None), scalar_result(None)])
    payload = PoemSourceAnswerSubmission(answers={}, poet_id=999)

    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "id": 16,
            "status": PoemSourceStatus.STAGE_1.value,
            "follow_up_questions": [{"id": "q1", "text": "Q?"}],
            "poet_candidates": [],
        }

        with pytest.raises(HTTPException) as exc_info:
            await submit_poem_source_answers(Mock(), 16, payload, current_user_dict, mock_db)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Selected poet does not exist"


@pytest.mark.asyncio
async def test_submit_rejects_poet_not_in_candidates(mock_db, current_user_dict) -> None:
    poet_candidates = [poet_card_fixtures()[0].model_dump()]
    selected_poet_id = poet_candidates[0]["id"] + 1
    mock_db.execute = AsyncMock(side_effect=[scalar_result(None), scalar_result(selected_poet_id)])
    payload = PoemSourceAnswerSubmission(answers={}, poet_id=selected_poet_id)

    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "id": 17,
            "status": PoemSourceStatus.STAGE_1.value,
            "follow_up_questions": [{"id": "q1", "text": "Q?"}],
            "poet_candidates": poet_candidates,
        }

        with pytest.raises(HTTPException) as exc_info:
            await submit_poem_source_answers(Mock(), 17, payload, current_user_dict, mock_db)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Selected poet is not available for this poem source"


@pytest.mark.asyncio
async def test_submit_rejects_regeneration_with_409(mock_db, current_user_dict) -> None:
    mock_db.execute = AsyncMock(return_value=scalar_result(123))
    payload = PoemSourceAnswerSubmission(answers={})

    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "id": 18,
            "status": PoemSourceStatus.STAGE_1.value,
            "follow_up_questions": [{"id": "q1", "text": "Q?"}],
        }

        with pytest.raises(HTTPException) as exc_info:
            await submit_poem_source_answers(Mock(), 18, payload, current_user_dict, mock_db)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Poem source already has a generated poem"


@pytest.mark.asyncio
async def test_submit_persists_answers_and_starts_stage_2(mock_db, current_user_dict) -> None:
    mock_db.execute = AsyncMock(return_value=scalar_result(None))
    payload = PoemSourceAnswerSubmission(
        answers={
            "q1": "A quiet, hopeful mood.",
            "q2": "The light on the river.",
        }
    )

    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "id": 11,
            "status": PoemSourceStatus.STAGE_1.value,
            "follow_up_questions": [
                {"id": "q1", "text": "What feeling should guide the poem?"},
                {"id": "q2", "text": "What detail matters most?"},
            ],
        }

        with patch("src.app.api.v1.poem_source.crud_poem_sources.update", new_callable=AsyncMock) as mock_update:
            with patch("src.app.api.v1.poem_source.crewai_service.start_stage_2_generation") as mock_start:
                result = await submit_poem_source_answers(Mock(), 11, payload, current_user_dict, mock_db)

    update_object = mock_update.await_args.kwargs["object"]

    assert result == {
        "message": "Answers accepted",
        "status": PoemSourceStatus.GENERATING.value,
        "poem_source_id": 11,
    }
    assert update_object.follow_up_answers == payload.answers
    mock_start.assert_called_once_with(poem_source_id=11, poet_id=None)


@pytest.mark.asyncio
async def test_submit_rejects_missing_poem_source(mock_db, current_user_dict) -> None:
    payload = PoemSourceAnswerSubmission(answers={"q1": "hello"})

    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        with pytest.raises(NotFoundException):
            await submit_poem_source_answers(Mock(), 404, payload, current_user_dict, mock_db)
