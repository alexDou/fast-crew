"""General staged workflow API tests (status handoff and validation)."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from src.app.api.v1.poem_source import check_poem_source_ready, submit_poem_source_answers
from src.app.core.exceptions.http_exceptions import NotFoundException
from src.app.schemas.poem_source import PoemSourceAnswerSubmission, PoemSourceStatus
from tests.helpers.workflow import scalar_result


@pytest.mark.asyncio
async def test_submit_allows_partial_answers(mock_db, current_user_dict) -> None:
    mock_db.execute = AsyncMock(return_value=scalar_result(None))
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

        with patch("src.app.api.v1.poem_source.crud_poem_sources.update", new_callable=AsyncMock):
            with patch("src.app.api.v1.poem_source.crewai_service.start_stage_2_generation"):
                result = await submit_poem_source_answers(Mock(), 12, payload, current_user_dict, mock_db)

    assert result["status"] == PoemSourceStatus.GENERATING.value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("stored_status", "expected_ready", "expected_questions", "expected_message"),
    [
        (PoemSourceStatus.PROCESSING.value, False, [], None),
        (PoemSourceStatus.GENERATING.value, False, [], None),
        (PoemSourceStatus.COMPLETE.value, True, [], None),
        (PoemSourceStatus.ERROR.value, True, [], "indistinct content"),
    ],
)
async def test_check_ready_handoff_states(
    mock_db,
    current_user_dict,
    stored_status,
    expected_ready,
    expected_questions,
    expected_message,
) -> None:
    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "id": 5,
            "status": stored_status,
            "follow_up_questions": [],
            "error_message": expected_message,
        }

        result = await check_poem_source_ready(Mock(), 5, mock_db, current_user_dict)

    assert result == {
        "ready": expected_ready,
        "status": stored_status,
        "poem_source_id": 5,
        "message": expected_message,
        "questions": expected_questions,
        "poet_candidates": [],
    }


@pytest.mark.asyncio
async def test_check_ready_raises_not_found_for_other_owners(mock_db, current_user_dict) -> None:
    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        with pytest.raises(NotFoundException):
            await check_poem_source_ready(Mock(), 999, mock_db, current_user_dict)


@pytest.mark.asyncio
async def test_submit_rejects_wrong_state(mock_db, current_user_dict) -> None:
    payload = PoemSourceAnswerSubmission(answers={"q1": "hello"})

    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "id": 13,
            "status": PoemSourceStatus.GENERATING.value,
            "follow_up_questions": [{"id": "q1", "text": "Q?"}],
        }

        with pytest.raises(HTTPException) as exc_info:
            await submit_poem_source_answers(Mock(), 13, payload, current_user_dict, mock_db)

    assert exc_info.value.status_code == 409
    assert exc_info.value.detail == "Poem source is not waiting for answers"


@pytest.mark.asyncio
async def test_submit_rejects_unknown_question_id(mock_db, current_user_dict) -> None:
    mock_db.execute = AsyncMock(return_value=scalar_result(None))
    payload = PoemSourceAnswerSubmission(answers={"q1": "hello"})

    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "id": 14,
            "status": PoemSourceStatus.STAGE_1.value,
            "follow_up_questions": [],
        }

        with pytest.raises(HTTPException) as exc_info:
            await submit_poem_source_answers(Mock(), 14, payload, current_user_dict, mock_db)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == "Answers include unknown follow-up questions"
