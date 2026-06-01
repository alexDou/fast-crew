"""Unit tests for CrewAI service persistence behavior."""

import time
from contextlib import ExitStack
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.app.core.enums import PoemSourceStatus
from src.app.services.crewai.errors import INDISTINCT_CONTENT_MESSAGE
from src.app.services.crewai.service import CrewAIService
from src.app.services.crewai_service import CrewAIService as ReExportedService
from src.app.services.crewai_service import crewai_service as re_exported_singleton

ACTIVE_POETS = [{"id": 11, "name": "Walt Whitman"}]
WITH_THREAD_DB_PATH = "src.app.services.crewai.service.persistence.with_thread_db"
RUN_ASYNC_PATH = "src.app.services.crewai.service.persistence.run_async"
PICKER_PATH = "src.app.services.crewai.service.generate_poet_candidate_ids"


class _FakeImageAnalyzerTool:
    def __init__(self, api_key: str, model: str) -> None:
        self.api_key = api_key
        self.model = model

    def _run(self, image_path: str) -> str:
        return "A quiet lake under morning light."


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

    # Only the fields we explicitly set should be serialized back to FastCRUD
    # so existing media_path / image_analysis / follow_up_questions /
    # follow_up_answers values remain untouched on the row.
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
        # No exception -> a regular analysis string passes through.
        CrewAIService._raise_if_indistinct("A sunlit valley with a lone oak tree.")


class TestStage1Orchestration:
    def test_persists_questions_and_poet_candidates(self) -> None:
        service = CrewAIService()
        poet_cards = [
            {
                "id": 11,
                "name": "Walt Whitman",
                "era": "19th century",
                "known_for": "Free verse",
                "style_markers": ["long line"],
            }
        ]

        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.load_poets_crew_modules",
                    return_value=(None, _FakeImageAnalyzerTool, "key"),
                )
            )
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.storage_service.prepare_local_media_file",
                    return_value=("/tmp/image.png", False),
                )
            )
            stack.enter_context(patch.object(service, "_load_active_poets", return_value=ACTIVE_POETS))
            stack.enter_context(patch.object(service, "_load_poet_cards", return_value=poet_cards))
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.generate_follow_up_questions",
                    return_value=[{"id": "q1", "text": "What feeling?"}],
                )
            )
            stack.enter_context(patch(PICKER_PATH, return_value=[11]))
            stack.enter_context(patch("src.app.services.crewai.service.persist_output_artifacts"))
            stack.enter_context(patch(WITH_THREAD_DB_PATH, new=Mock(return_value=object())))
            stack.enter_context(patch(RUN_ASYNC_PATH))

            result = service._run_stage_1_sync(7, "media/a.png", 1, None)

        assert result == {
            "image_analysis": "A quiet lake under morning light.",
            "questions": [{"id": "q1", "text": "What feeling?"}],
            "poet_candidates": poet_cards,
        }

    def test_questions_and_poet_picker_run_in_parallel(self) -> None:
        service = CrewAIService()

        def _slow_questions(*_args) -> list[dict[str, str]]:
            time.sleep(0.1)
            return [{"id": "q1", "text": "What feeling?"}]

        def _slow_picker(*_args) -> list[int]:
            time.sleep(0.1)
            return [11]

        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.load_poets_crew_modules",
                    return_value=(None, _FakeImageAnalyzerTool, "key"),
                )
            )
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.storage_service.prepare_local_media_file",
                    return_value=("/tmp/image.png", False),
                )
            )
            stack.enter_context(patch.object(service, "_load_active_poets", return_value=ACTIVE_POETS))
            stack.enter_context(patch.object(service, "_load_poet_cards", return_value=[]))
            stack.enter_context(
                patch("src.app.services.crewai.service.generate_follow_up_questions", side_effect=_slow_questions)
            )
            stack.enter_context(patch(PICKER_PATH, side_effect=_slow_picker))
            stack.enter_context(patch("src.app.services.crewai.service.persist_output_artifacts"))
            stack.enter_context(patch(WITH_THREAD_DB_PATH, new=Mock(return_value=object())))
            stack.enter_context(patch(RUN_ASYNC_PATH))

            started_at = time.perf_counter()
            service._run_stage_1_sync(7, "media/a.png", 1, None)
            elapsed = time.perf_counter() - started_at

        assert elapsed < 0.18

    def test_poet_picker_failure_keeps_stage_1_successful_with_empty_candidates(self) -> None:
        service = CrewAIService()

        with ExitStack() as stack:
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.load_poets_crew_modules",
                    return_value=(None, _FakeImageAnalyzerTool, "key"),
                )
            )
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.storage_service.prepare_local_media_file",
                    return_value=("/tmp/image.png", False),
                )
            )
            stack.enter_context(patch.object(service, "_load_active_poets", return_value=ACTIVE_POETS))
            mock_load_cards = stack.enter_context(patch.object(service, "_load_poet_cards", return_value=[]))
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.generate_follow_up_questions",
                    return_value=[{"id": "q1", "text": "What feeling?"}],
                )
            )
            stack.enter_context(
                patch(
                    "src.app.services.crewai.service.generate_poet_candidate_ids",
                    side_effect=RuntimeError("picker down"),
                )
            )
            stack.enter_context(patch("src.app.services.crewai.service.persist_output_artifacts"))
            stack.enter_context(patch(WITH_THREAD_DB_PATH, new=Mock(return_value=object())))
            stack.enter_context(patch(RUN_ASYNC_PATH))

            result = service._run_stage_1_sync(7, "media/a.png", 1, None)

        assert result["questions"] == [{"id": "q1", "text": "What feeling?"}]
        assert result["poet_candidates"] == []
        mock_load_cards.assert_called_once_with([])


class TestCleanupLocalImage:
    def test_skips_when_flag_is_false(self, tmp_path) -> None:
        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"data")

        CrewAIService._cleanup_local_image(str(image_path), should_cleanup=False)

        assert image_path.exists()

    def test_skips_when_path_is_empty(self) -> None:
        # Should be a no-op rather than raising on missing path.
        CrewAIService._cleanup_local_image("", should_cleanup=True)

    def test_removes_the_file_when_requested(self, tmp_path) -> None:
        image_path = tmp_path / "photo.jpg"
        image_path.write_bytes(b"data")

        CrewAIService._cleanup_local_image(str(image_path), should_cleanup=True)

        assert not image_path.exists()
