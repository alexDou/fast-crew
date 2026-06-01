"""Tests for shared prompt helpers not covered by B12 regression modules."""

from types import SimpleNamespace

from src.app.services.crewai.prompts import (
    build_generation_context,
    extract_poem_from_result,
    extract_text_content,
)


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
