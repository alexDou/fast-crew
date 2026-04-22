"""Tests for the pure helpers in :mod:`app.services.crewai.prompts`."""

from types import SimpleNamespace

import pytest

from src.app.services.crewai.prompts import (
    VARIANT_ORDER,
    build_generation_context,
    extract_poems_from_result,
    extract_text_content,
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


class TestExtractPoemsFromResult:
    def test_maps_ordered_task_outputs_to_variants(self) -> None:
        result = SimpleNamespace(
            tasks_output=[
                SimpleNamespace(raw="modern"),
                SimpleNamespace(raw="classic"),
                SimpleNamespace(raw="mystic"),
            ]
        )

        poems = extract_poems_from_result(result)

        assert list(poems.keys()) == list(VARIANT_ORDER)
        assert poems == {"poet_modern": "modern", "poet_classic": "classic", "poet_mystic": "mystic"}

    def test_fills_missing_variants_with_none(self) -> None:
        result = SimpleNamespace(tasks_output=[SimpleNamespace(raw="only modern")])

        poems = extract_poems_from_result(result)

        assert poems == {"poet_modern": "only modern", "poet_classic": None, "poet_mystic": None}

    def test_handles_result_without_tasks_output_attribute(self) -> None:
        result = SimpleNamespace()

        poems = extract_poems_from_result(result)

        assert poems == {"poet_modern": None, "poet_classic": None, "poet_mystic": None}


class TestExtractTextContent:
    def test_flattens_list_payload(self) -> None:
        assert extract_text_content(["  hello ", "world  "]) == "hello world"

    def test_string_payload_is_trimmed(self) -> None:
        assert extract_text_content("  body  ") == "body"

    def test_none_becomes_empty_string(self) -> None:
        assert extract_text_content(None) == ""
