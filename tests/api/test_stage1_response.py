"""API regression tests for the stage-1 readiness response contract."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.app.api.v1.poem_source import check_poem_source_ready
from src.app.schemas.poem_source import PoemSourceStatus, PoemSourceStatusResponse
from tests.fixtures.poets import poet_card_fixtures

STALE_KIND_FIELD_NAMES = frozenset(
    {
        "kind",
        "poem_kind",
        "variants",
        "classic",
        "modern",
        "mystic",
        "author_label",
        "variant_key",
    }
)


def test_stage1_response_schema_has_no_stale_kind_fields() -> None:
    field_names = set(PoemSourceStatusResponse.model_fields)

    assert not field_names & STALE_KIND_FIELD_NAMES


@pytest.mark.asyncio
async def test_ready_response_includes_questions_and_poet_candidates(
    mock_db, current_user_dict
) -> None:
    poet_candidates = [card.model_dump() for card in poet_card_fixtures()[:3]]

    with patch("src.app.api.v1.poem_source.crud_poem_sources.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "id": 7,
            "status": PoemSourceStatus.STAGE_1.value,
            "follow_up_questions": [
                {"id": "q1", "text": "What feeling should guide the poem?"},
            ],
            "poet_candidates": poet_candidates,
            "error_message": None,
        }

        result = await check_poem_source_ready(Mock(), 7, mock_db, current_user_dict)

    assert result["questions"] == [{"id": "q1", "text": "What feeling should guide the poem?"}]
    assert result["poet_candidates"] == poet_candidates
    assert "kind" not in result
    assert "poem_kind" not in result
    assert "variants" not in result

    validated = PoemSourceStatusResponse.model_validate(result)
    assert len(validated.poet_candidates) == 3
    assert validated.poet_candidates[0].name == poet_candidates[0]["name"]
