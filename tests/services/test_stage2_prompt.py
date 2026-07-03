"""Regression tests for the stage-2 prompt builder (poet vs freestyle branches)."""

from src.app.services.crewai.prompts import POET_WRITER_MODEL, build_stage_2_messages


def test_uses_deepseek_v4_pro_for_poem_generation() -> None:
    assert POET_WRITER_MODEL == "tngtech/deepseek-r1t2-chimera"


def test_builds_poet_branch_with_style_metadata() -> None:
    system_prompt, user_prompt = build_stage_2_messages(
        "A moonlit garden.",
        [{"id": "q1", "text": "What feeling should guide it?"}],
        {"q1": "Tenderness."},
        "Emily Dickinson",
        {
            "era": "American Romanticism",
            "known_for": "slant rhyme, compressed hymnal stanzas, dashes",
            "style_markers": ["short hymn-like stanzas", "slant rhyme", "em dashes"],
        },
    )

    combined = system_prompt + "\n" + user_prompt
    assert "unmistakably recognizable" in system_prompt
    assert "exact syntax, vocabulary, pacing" in system_prompt
    assert "Absolutely avoid predictable elementary AABB/ABAB rhyme schemes" in system_prompt
    assert "Poet to replicate: Emily Dickinson" in user_prompt
    assert "American Romanticism" in user_prompt
    assert "short hymn-like stanzas; slant rhyme; em dashes" in user_prompt
    assert "What feeling should guide it?: Tenderness." in user_prompt
    assert "poet_id" not in combined


def test_builds_freestyle_branch() -> None:
    system_prompt, user_prompt = build_stage_2_messages("A quiet sea.", [], {}, None)

    assert "Do not imitate any specific named poet" in system_prompt
    assert "Poet to replicate" not in user_prompt
    assert "- None provided." in user_prompt
