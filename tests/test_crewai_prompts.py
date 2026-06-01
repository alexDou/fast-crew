"""Tests for the pure helpers in :mod:`app.services.crewai.prompts`."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.app.services.crewai.prompts import (
    build_generation_context,
    extract_poem_from_result,
    extract_text_content,
    fallback_poet_ids,
    generate_poet_candidate_ids,
    normalize_poet_ids,
    normalize_questions,
)


class TestNormalizeQuestions:
    def test_assigns_deterministic_ids_and_caps_at_three(self) -> None:
        raw = [
            {"text": "  What mood?  "},
            {"text": "Any smells?", "kind": "sensory"},
            {"text": "Name the place"},
            {"text": "dropped because we cap at three"},
        ]

        result = normalize_questions(raw)

        assert result == [
            {"id": "q1", "text": "What mood?"},
            {"id": "q2", "text": "Any smells?", "kind": "sensory"},
            {"id": "q3", "text": "Name the place"},
        ]

    def test_drops_blank_questions_and_ignores_blank_kind(self) -> None:
        raw = [
            {"text": ""},
            {"text": "   "},
            {"text": "What about the hands?", "kind": "   "},
        ]

        result = normalize_questions(raw)

        assert result == [{"id": "q1", "text": "What about the hands?"}]

    def test_raises_when_no_usable_question(self) -> None:
        with pytest.raises(RuntimeError, match="did not return any valid follow-up questions"):
            normalize_questions([{"text": ""}, {"text": "   "}])


class TestBuildGenerationContext:
    def test_returns_empty_when_nothing_is_provided(self) -> None:
        assert build_generation_context(None, None, None) == ""
        assert build_generation_context(None, [], {}) == ""

    def test_combines_enhance_with_answered_questions(self) -> None:
        context = build_generation_context(
            "The photo was taken in 2026.",
            [
                {"id": "q1", "text": "What feeling should guide the poem?"},
                {"id": "q2", "text": "What detail matters most?"},
            ],
            {
                "q1": "A quiet, hopeful mood.",
                "q2": "The light on the river.",
            },
        )

        assert context == (
            "Original user context:\n"
            "The photo was taken in 2026.\n\n"
            "Follow-up answers from the user:\n"
            "- What feeling should guide the poem?: A quiet, hopeful mood.\n"
            "- What detail matters most?: The light on the river."
        )

    def test_falls_back_to_question_id_when_text_is_missing(self) -> None:
        context = build_generation_context(
            None,
            [{"id": "q1", "text": ""}],
            {"q1": "Warm and soft."},
        )

        assert "- q1: Warm and soft." in context

    def test_omits_answers_block_when_no_questions_match(self) -> None:
        context = build_generation_context("Some context", [], {"q1": "unused"})

        assert context == "Original user context:\nSome context"


class TestPoetPickerHelpers:
    def test_normalize_poet_ids_deduplicates_valid_ids(self) -> None:
        result = normalize_poet_ids([1, 2, 3, 4, 5, 6, 7, 8, 8], set(range(1, 12)))

        assert result == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_normalize_poet_ids_rejects_unknown_ids(self) -> None:
        with pytest.raises(RuntimeError, match="unknown poet id"):
            normalize_poet_ids([1, 2, 3, 4, 5, 6, 7, 999], set(range(1, 12)))

    def test_normalize_poet_ids_rejects_invalid_count_after_dedupe(self) -> None:
        with pytest.raises(RuntimeError, match="wrong number"):
            normalize_poet_ids([1, 2, 3, 4, 5, 6, 7], set(range(1, 12)))

    def test_fallback_poet_ids_is_stable_per_source(self) -> None:
        active_poets = [{"id": poet_id, "name": f"Poet {poet_id}"} for poet_id in range(1, 13)]

        first = fallback_poet_ids(active_poets, poem_source_id=42)
        second = fallback_poet_ids(active_poets, poem_source_id=42)

        assert first == second
        assert len(first) == 8
        assert set(first).issubset(set(range(1, 13)))

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


class TestExtractPoemFromResult:
    def test_returns_first_non_empty_task_output(self) -> None:
        result = SimpleNamespace(
            tasks_output=[
                SimpleNamespace(raw=""),
                SimpleNamespace(raw="  One finished poem  "),
                SimpleNamespace(raw="ignored"),
            ]
        )

        poem = extract_poem_from_result(result)

        assert poem == "One finished poem"

    def test_accepts_plain_string_result(self) -> None:
        assert extract_poem_from_result("  A plain poem  ") == "A plain poem"

    def test_returns_none_when_no_output_exists(self) -> None:
        result = SimpleNamespace(tasks_output=[SimpleNamespace(raw="   ")])

        assert extract_poem_from_result(result) is None

    def test_handles_result_without_tasks_output_attribute(self) -> None:
        result = SimpleNamespace()

        assert extract_poem_from_result(result) is None


class TestExtractTextContent:
    def test_flattens_list_payload(self) -> None:
        assert extract_text_content(["  hello ", "world  "]) == "hello world"

    def test_string_payload_is_trimmed(self) -> None:
        assert extract_text_content("  body  ") == "body"

    def test_none_becomes_empty_string(self) -> None:
        assert extract_text_content(None) == ""
