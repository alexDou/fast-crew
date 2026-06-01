"""Regression tests for the stage-2 prompt builder (poet vs freestyle branches)."""

from src.app.services.crewai.prompts import build_stage_2_messages


def test_builds_poet_branch_without_ids_or_style_metadata() -> None:
    system_prompt, user_prompt = build_stage_2_messages(
        "A moonlit garden.",
        [{"id": "q1", "text": "What feeling should guide it?"}],
        {"q1": "Tenderness."},
        "Emily Dickinson",
    )

    combined = system_prompt + "\n" + user_prompt
    assert "unmistakably recognizable" in system_prompt
    assert "Poet to replicate: Emily Dickinson" in user_prompt
    assert "What feeling should guide it?: Tenderness." in user_prompt
    assert "poet_id" not in combined
    assert "style_markers" not in combined


def test_builds_freestyle_branch() -> None:
    system_prompt, user_prompt = build_stage_2_messages("A quiet sea.", [], {}, None)

    assert "Do not imitate any specific named poet" in system_prompt
    assert "Poet to replicate" not in user_prompt
    assert "- None provided." in user_prompt
