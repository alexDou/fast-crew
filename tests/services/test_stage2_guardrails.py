"""Regression tests for stage-2 output guardrails."""

from unittest.mock import patch

from src.app.services.crewai.prompts import (
    clean_poem_output,
    generate_stage_2_poem,
    poem_is_too_short,
)


def test_clean_poem_output_strips_preamble_and_caps_lines() -> None:
    raw = "Here is the poem:\n" + "\n".join(f"line {index}" for index in range(405))

    cleaned = clean_poem_output(raw)

    assert not cleaned.lower().startswith("here is")
    assert len(cleaned.splitlines()) == 400


def test_poem_is_too_short_counts_non_empty_lines() -> None:
    assert poem_is_too_short("one\n\n two") is True
    assert poem_is_too_short("one\ntwo\nthree") is False


def test_generate_stage_2_poem_retries_short_output() -> None:
    with patch("src.app.services.crewai.prompts._request_stage_2_poem") as mock_request:
        mock_request.side_effect = ["too short", "line one\nline two\nline three"]

        poem = generate_stage_2_poem("key", "A quiet sea.", [], {}, None)

    assert poem == "line one\nline two\nline three"
    assert mock_request.call_count == 2
