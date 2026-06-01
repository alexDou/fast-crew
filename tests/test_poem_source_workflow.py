"""Focused tests for the staged poem source workflow."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from src.app.api.v1.poem_source import check_poem_source_ready, submit_poem_source_answers
from src.app.core.exceptions.http_exceptions import NotFoundException
from src.app.schemas.poem_source import PoemSourceAnswerSubmission, PoemSourceStatus
from tests.fixtures.poets import poet_card_fixtures


def _scalar_result(value):
    result = Mock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.mark.asyncio
async def test_check_poem_source_ready_returns_questions_for_stage_1(mock_db, current_user_dict) -> None:
    poet_candidates = [poet_card_fixtures()[0].model_dump()]

    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "id": 7,
            "status": PoemSourceStatus.STAGE_1.value,
            "follow_up_questions": [
                {"id": "q1", "text": "What feeling should guide the poem?"},
                {"id": "q2", "text": "What detail matters most?"},
            ],
            "poet_candidates": poet_candidates,
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
        "poet_candidates": poet_candidates,
    }


@pytest.mark.asyncio
async def test_submit_poem_source_answers_persists_answers_and_starts_stage_2(mock_db, current_user_dict) -> None:
    mock_db.execute = AsyncMock(return_value=_scalar_result(None))
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
    mock_start_stage_2.assert_called_once_with(poem_source_id=11, poet_id=None)


@pytest.mark.asyncio
async def test_submit_poem_source_answers_allows_partial_answers(mock_db, current_user_dict) -> None:
    mock_db.execute = AsyncMock(return_value=_scalar_result(None))
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
async def test_check_poem_source_ready_handoff_states(
    mock_db,
    current_user_dict,
    stored_status,
    expected_ready,
    expected_questions,
    expected_message,
) -> None:
    """Readiness endpoint must map each workflow status to the right shape."""
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
async def test_check_poem_source_ready_raises_not_found_for_other_owners(
    mock_db, current_user_dict
) -> None:
    """The ownership filter on crud.get prevents foreign sources from leaking."""
    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        with pytest.raises(NotFoundException):
            await check_poem_source_ready(Mock(), 999, mock_db, current_user_dict)


@pytest.mark.asyncio
async def test_submit_poem_source_answers_rejects_wrong_state(mock_db, current_user_dict) -> None:
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
async def test_submit_poem_source_answers_rejects_missing_not_found(
    mock_db, current_user_dict
) -> None:
    payload = PoemSourceAnswerSubmission(answers={"q1": "hello"})

    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None

        with pytest.raises(NotFoundException):
            await submit_poem_source_answers(Mock(), 404, payload, current_user_dict, mock_db)


@pytest.mark.asyncio
async def test_submit_poem_source_answers_rejects_unknown_question_id(
    mock_db, current_user_dict
) -> None:
    mock_db.execute = AsyncMock(return_value=_scalar_result(None))
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


@pytest.mark.asyncio
async def test_submit_poem_source_answers_accepts_candidate_poet_id(mock_db, current_user_dict) -> None:
    poet_candidates = [poet_card_fixtures()[0].model_dump()]
    selected_poet_id = poet_candidates[0]["id"]
    mock_db.execute = AsyncMock(side_effect=[_scalar_result(None), _scalar_result(selected_poet_id)])
    payload = PoemSourceAnswerSubmission(answers={}, poet_id=selected_poet_id)

    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "id": 15,
            "status": PoemSourceStatus.STAGE_1.value,
            "follow_up_questions": [{"id": "q1", "text": "Q?"}],
            "poet_candidates": poet_candidates,
        }

        with patch("src.app.api.v1.poem_source.crud_poem_sources.update", new_callable=AsyncMock):
            with patch("src.app.api.v1.poem_source.crewai_service.start_stage_2_generation") as mock_start_stage_2:
                await submit_poem_source_answers(Mock(), 15, payload, current_user_dict, mock_db)

    mock_start_stage_2.assert_called_once_with(poem_source_id=15, poet_id=selected_poet_id)


@pytest.mark.asyncio
async def test_submit_poem_source_answers_rejects_unknown_poet_id(mock_db, current_user_dict) -> None:
    mock_db.execute = AsyncMock(side_effect=[_scalar_result(None), _scalar_result(None)])
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
async def test_submit_poem_source_answers_rejects_poet_outside_candidates(mock_db, current_user_dict) -> None:
    poet_candidates = [poet_card_fixtures()[0].model_dump()]
    selected_poet_id = poet_candidates[0]["id"] + 1
    mock_db.execute = AsyncMock(side_effect=[_scalar_result(None), _scalar_result(selected_poet_id)])
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
async def test_submit_poem_source_answers_rejects_regeneration(mock_db, current_user_dict) -> None:
    mock_db.execute = AsyncMock(return_value=_scalar_result(123))
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
