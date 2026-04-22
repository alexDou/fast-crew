"""Focused tests for the staged poem source workflow."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from src.app.api.v1.poem_source import check_poem_source_ready, submit_poem_source_answers
from src.app.schemas.poem_source import PoemSourceAnswerSubmission, PoemSourceStatus


@pytest.mark.asyncio
async def test_check_poem_source_ready_returns_questions_for_stage_1(mock_db, current_user_dict) -> None:
    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "id": 7,
            "status": PoemSourceStatus.STAGE_1.value,
            "follow_up_questions": [
                {"id": "q1", "text": "What feeling should guide the poem?"},
                {"id": "q2", "text": "What detail matters most?"},
            ],
            "error_message": None,
        }

        result = await check_poem_source_ready(Mock(), 7, mock_db, current_user_dict)

    assert result == {
        "ready": True,
        "status": PoemSourceStatus.STAGE_1.value,
        "poem_source_id": 7,
        "message": None,
        "questions": [
            {"id": "q1", "text": "What feeling should guide the poem?"},
            {"id": "q2", "text": "What detail matters most?"},
        ],
    }


@pytest.mark.asyncio
async def test_submit_poem_source_answers_persists_answers_and_starts_stage_2(mock_db, current_user_dict) -> None:
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
            with patch("src.app.api.v1.poem_source.crewai_service.start_stage_2_generation") as mock_start_stage_2:
                result = await submit_poem_source_answers(Mock(), 11, payload, current_user_dict, mock_db)

    update_object = mock_update.await_args.kwargs["object"]

    assert result == {
        "message": "Answers accepted",
        "status": PoemSourceStatus.GENERATING.value,
        "poem_source_id": 11,
    }
    assert update_object.status == PoemSourceStatus.GENERATING.value
    assert update_object.follow_up_answers == payload.answers
    assert update_object.model_fields_set == {"status", "follow_up_answers", "error_message"}
    mock_db.commit.assert_awaited_once()
    mock_start_stage_2.assert_called_once_with(poem_source_id=11)


@pytest.mark.asyncio
async def test_submit_poem_source_answers_requires_every_question(mock_db, current_user_dict) -> None:
    payload = PoemSourceAnswerSubmission(answers={"q1": "Only one answer"})

    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "id": 12,
            "status": PoemSourceStatus.STAGE_1.value,
            "follow_up_questions": [
                {"id": "q1", "text": "What feeling should guide the poem?"},
                {"id": "q2", "text": "What detail matters most?"},
            ],
        }

        with pytest.raises(HTTPException) as exc_info:
            await submit_poem_source_answers(Mock(), 12, payload, current_user_dict, mock_db)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Answers must be provided for every follow-up question"
