"""Unit tests for CrewAI service persistence behavior."""

from unittest.mock import AsyncMock, patch

import pytest

from src.app.services.crewai_service import CrewAIService


@pytest.mark.asyncio
async def test_update_poem_source_status_preserves_media_path(mock_db) -> None:
    """Status updates should not null out the stored media path."""
    service = CrewAIService()

    with patch("src.app.crud.crud_poem_sources.crud_poem_sources.update", new_callable=AsyncMock) as mock_update:
        await service._update_poem_source_status(mock_db, poem_source_id=7, status="complete")

    update_object = mock_update.await_args.kwargs["object"]

    assert update_object.status == "complete"
    assert update_object.model_fields_set == {"status"}
    mock_db.commit.assert_awaited_once()
