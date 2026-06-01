"""Unit tests for CrewAI service persistence and utilities."""

from unittest.mock import AsyncMock, patch

import pytest

from src.app.core.enums import PoemSourceStatus
from src.app.services.crewai.errors import INDISTINCT_CONTENT_MESSAGE
from src.app.services.crewai.service import CrewAIService
from src.app.services.crewai_service import CrewAIService as ReExportedService
from src.app.services.crewai_service import crewai_service as re_exported_singleton


def test_crewai_service_facade_re_exports_singleton() -> None:
    """The legacy import path must keep resolving to the same class+instance."""
    assert ReExportedService is CrewAIService
    assert isinstance(re_exported_singleton, CrewAIService)


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


@pytest.mark.asyncio
async def test_update_poem_source_preserves_unspecified_staged_fields(mock_db) -> None:
    """Partial updates must not clear image_analysis / follow_up_* columns."""
    service = CrewAIService()

    with patch(
        "src.app.crud.crud_poem_sources.crud_poem_sources.update", new_callable=AsyncMock
    ) as mock_update:
        await service._update_poem_source(
            mock_db,
            poem_source_id=7,
            status=PoemSourceStatus.ERROR.value,
            error_message="boom",
        )

    update_object = mock_update.await_args.kwargs["object"]

    assert update_object.model_fields_set == {"status", "error_message"}
    assert update_object.status == PoemSourceStatus.ERROR.value
    assert update_object.error_message == "boom"
    mock_db.commit.assert_awaited_once()


class TestRaiseIfIndistinct:
    def test_raises_on_exact_indistinct_sentinel(self) -> None:
        with pytest.raises(RuntimeError, match=INDISTINCT_CONTENT_MESSAGE):
            CrewAIService._raise_if_indistinct("Indistinct Content")

    def test_raises_on_error_analyzing_prefix(self) -> None:
        with pytest.raises(RuntimeError, match="Error analyzing image: bad vibes"):
            CrewAIService._raise_if_indistinct("Error analyzing image: bad vibes")

    def test_allows_normal_analysis(self) -> None:
        CrewAIService._raise_if_indistinct("A sunlit valley with a lone oak tree.")


class TestCleanupLocalImage:
    def test_skips_when_flag_is_false(self, tmp_path) -> None:
        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"data")

        CrewAIService._cleanup_local_image(str(image_path), should_cleanup=False)

        assert image_path.exists()

    def test_skips_when_path_is_empty(self) -> None:
        CrewAIService._cleanup_local_image("", should_cleanup=True)

    def test_removes_the_file_when_requested(self, tmp_path) -> None:
        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"data")

        CrewAIService._cleanup_local_image(str(image_path), should_cleanup=True)

        assert not image_path.exists()
