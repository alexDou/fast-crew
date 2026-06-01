"""Regression tests for the stage-1 poet picker (agent c)."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.app.services.crewai.prompts import (
    POET_PICKER_MODEL,
    POET_PICKER_PROMPT,
    _request_poet_ids,
    fallback_poet_ids,
    generate_poet_candidate_ids,
    normalize_poet_ids,
)


def _chimera_completion(poet_ids: list[int]) -> SimpleNamespace:
    message = SimpleNamespace(content=json.dumps({"poet_ids": poet_ids}))
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class TestNormalizePoetIds:
    def test_deduplicates_valid_ids(self) -> None:
        allowed_ids = set(range(1, 12))

        result = normalize_poet_ids([1, 2, 3, 4, 5, 6, 7, 8, 8], allowed_ids)

        assert result == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_rejects_unknown_ids(self) -> None:
        with pytest.raises(RuntimeError, match="unknown poet id"):
            normalize_poet_ids([1, 2, 3, 4, 5, 6, 7, 999], set(range(1, 12)))

    def test_rejects_invalid_count_after_dedupe(self) -> None:
        with pytest.raises(RuntimeError, match="wrong number"):
            normalize_poet_ids([1, 2, 3, 4, 5, 6, 7], set(range(1, 12)))


class TestPoetPickerChimera:
    def test_chimera_mock_returns_deterministic_fixture_ids(self) -> None:
        # IDs 11–18 align with the shared poet fixture catalog range.
        active_poets = [{"id": poet_id, "name": f"Poet {poet_id}"} for poet_id in range(11, 23)]
        fixture_ids = list(range(11, 19))

        with patch("src.app.services.crewai.prompts.OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = _chimera_completion(
                fixture_ids
            )

            result = _request_poet_ids(
                "A quiet lake under morning light.",
                active_poets,
                "test-key",
                system_prompt=POET_PICKER_PROMPT,
            )

        assert result == fixture_ids
        call_kwargs = mock_openai.return_value.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == POET_PICKER_MODEL

    def test_generate_poet_candidate_ids_retries_then_uses_valid_ids(self) -> None:
        active_poets = [{"id": poet_id, "name": f"Poet {poet_id}"} for poet_id in range(1, 13)]

        with patch("src.app.services.crewai.prompts._request_poet_ids") as mock_request:
            mock_request.side_effect = [RuntimeError("bad output"), list(range(1, 9))]

            result = generate_poet_candidate_ids("a bright lake", active_poets, "key", 7)

        assert result == list(range(1, 9))
        assert mock_request.call_count == 2

    def test_generate_poet_candidate_ids_falls_back_after_retry_failure(self) -> None:
        active_poets = [{"id": poet_id, "name": f"Poet {poet_id}"} for poet_id in range(1, 13)]

        with patch("src.app.services.crewai.prompts._request_poet_ids", side_effect=RuntimeError("bad output")):
            result = generate_poet_candidate_ids("a bright lake", active_poets, "key", 7)

        assert result == fallback_poet_ids(active_poets, 7)

    def test_fallback_poet_ids_is_stable_per_source(self) -> None:
        active_poets = [{"id": poet_id, "name": f"Poet {poet_id}"} for poet_id in range(1, 13)]

        first = fallback_poet_ids(active_poets, poem_source_id=42)
        second = fallback_poet_ids(active_poets, poem_source_id=42)

        assert first == second
        assert len(first) == 8
