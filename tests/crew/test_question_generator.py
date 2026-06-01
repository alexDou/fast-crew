"""Regression tests for the stage-1 question generator (agent b)."""

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.app.services.crewai.prompts import (
    QUESTION_GENERATION_PROMPT,
    QUESTION_MODEL,
    generate_follow_up_questions,
    normalize_questions,
)


class TestNormalizeQuestions:
    def test_assigns_deterministic_ids_and_caps_at_three(self) -> None:
        raw = [
            {"text": "  What mood?  "},
            {"text": "Any smells?", "category": "ignored"},
            {"text": "Name the place"},
            {"text": "dropped because we cap at three"},
        ]

        result = normalize_questions(raw)

        assert result == [
            {"id": "q1", "text": "What mood?"},
            {"id": "q2", "text": "Any smells?"},
            {"id": "q3", "text": "Name the place"},
        ]

    def test_drops_blank_questions_and_ignores_extra_metadata(self) -> None:
        raw = [
            {"text": ""},
            {"text": "   "},
            {"text": "What about the hands?", "category": "sensory"},
        ]

        result = normalize_questions(raw)

        assert result == [{"id": "q1", "text": "What about the hands?"}]

    def test_raises_when_no_usable_question(self) -> None:
        with pytest.raises(RuntimeError, match="did not return any valid follow-up questions"):
            normalize_questions([{"text": ""}, {"text": "   "}])


class TestGenerateFollowUpQuestions:
    def test_parses_chimera_json_and_assigns_ids(self) -> None:
        completion = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content=json.dumps(
                            {
                                "questions": [
                                    {"text": "What mood should guide the poem?"},
                                    {"text": "Which detail matters most?"},
                                ]
                            }
                        )
                    )
                )
            ]
        )

        with patch("src.app.services.crewai.prompts.OpenAI") as mock_openai:
            mock_openai.return_value.chat.completions.create.return_value = completion

            result = generate_follow_up_questions(
                "A quiet lake under morning light.",
                "Taken at dawn.",
                "test-key",
            )

        assert result == [
            {"id": "q1", "text": "What mood should guide the poem?"},
            {"id": "q2", "text": "Which detail matters most?"},
        ]
        call_kwargs = mock_openai.return_value.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == QUESTION_MODEL
        assert call_kwargs["messages"][0]["content"] == QUESTION_GENERATION_PROMPT
