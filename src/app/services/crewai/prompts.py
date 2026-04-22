"""Prompt-building and response-parsing helpers for the CrewAI service.

These are pure, dependency-light functions kept separate from the main
service class so they can be unit-tested without standing up the
ThreadPoolExecutor or the CrewAI runtime.
"""

from __future__ import annotations

import json
from typing import Any

from openai import OpenAI

QUESTION_MODEL = "openrouter/deepseek/deepseek-v3.2"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_FOLLOW_UP_QUESTIONS = 3

VARIANT_LABELS: dict[str, str] = {
    "poet_modern": "Modern Poet",
    "poet_classic": "Classic Poet",
    "poet_mystic": "Mystic Poet",
}
# Canonical ordering used when reading task outputs from the crew result.
VARIANT_ORDER: tuple[str, ...] = ("poet_modern", "poet_classic", "poet_mystic")

QUESTION_GENERATION_PROMPT = (
    "You are preparing a staged poetry workflow. Based on the image analysis and the user's optional note, "
    "write 1 to 3 short follow-up questions that will help poets personalize the final poems. "
    'Return JSON only in the shape {"questions": [{"text": string, "kind": string | null}]}. '
    "The questions must be specific, concrete, and easy to answer in one or two sentences."
)


def extract_text_content(content: Any) -> str:
    """Collapse OpenAI-style message ``content`` (string or parts list) to text."""
    if isinstance(content, list):
        return "".join(str(part) for part in content).strip()
    return str(content or "").strip()


def normalize_questions(raw_questions: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Return a clean, at-most-3 list of ``{id, text, [kind]}`` dicts.

    - Empty question texts are dropped.
    - IDs are re-assigned deterministically (``q1``, ``q2``, ``q3``) based
      on the *output* order so callers never see gaps such as ``q3``
      appearing on its own when upstream returned blanks for q1/q2.
    - ``kind`` is preserved only when the upstream provides a non-empty value.
    - Raises ``RuntimeError`` when no usable question survives.
    """
    normalized_questions: list[dict[str, str]] = []
    for raw_question in raw_questions[:MAX_FOLLOW_UP_QUESTIONS]:
        question_text = str(raw_question.get("text") or "").strip()
        if not question_text:
            continue

        question: dict[str, str] = {
            "id": f"q{len(normalized_questions) + 1}",
            "text": question_text,
        }
        kind = str(raw_question.get("kind") or "").strip()
        if kind:
            question["kind"] = kind
        normalized_questions.append(question)

    if not normalized_questions:
        raise RuntimeError("Question generation did not return any valid follow-up questions")

    return normalized_questions


def generate_follow_up_questions(
    image_analysis: str,
    enhance: str | None,
    openrouter_api_key: str,
) -> list[dict[str, str]]:
    """Ask the question-generation model for up to three follow-up questions.

    The caller is responsible for passing the OpenRouter API key so tests
    can inject a deterministic value instead of touching global state.
    """
    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=openrouter_api_key)
    user_context = enhance.strip() if enhance else ""
    completion = client.chat.completions.create(
        extra_headers={"HTTP-Referer": "PoetsCrew", "X-Title": "PoetsCrew"},
        model=QUESTION_MODEL,
        messages=[
            {"role": "system", "content": QUESTION_GENERATION_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Image analysis:\n{image_analysis}\n\n"
                    f"Original user note:\n{user_context or 'None provided.'}"
                ),
            },
        ],
    )

    response_content = extract_text_content(completion.choices[0].message.content)
    if response_content.startswith("```"):
        response_content = response_content.strip("`")
        if response_content.startswith("json"):
            response_content = response_content[4:].strip()

    parsed = json.loads(response_content)
    questions = parsed.get("questions")
    if not isinstance(questions, list):
        raise RuntimeError("Question generation returned an invalid payload")

    return normalize_questions(questions)


def build_generation_context(
    enhance: str | None,
    questions: list[dict[str, str]] | None,
    answers: dict[str, str] | None,
) -> str:
    """Assemble the stage-2 prompt context from enhance + Q/A pairs.

    Ordering is stable: ``enhance`` first, then follow-up answers in the
    order the user submitted them (with question text for context). An
    empty string is returned when neither source contributes anything.
    """
    parts: list[str] = []
    if enhance:
        parts.append(f"Original user context:\n{enhance}")

    if questions and answers:
        # Skip empty-text entries so ``get(id, id)`` falls back to the bare
        # id and we never render ``- : answer`` in the prompt.
        question_text_by_id = {
            question["id"]: question["text"]
            for question in questions
            if question.get("id") and question.get("text")
        }
        answer_lines: list[str] = []
        for question_id, answer in answers.items():
            question_text = question_text_by_id.get(question_id, question_id)
            answer_lines.append(f"- {question_text}: {answer}")

        if answer_lines:
            parts.append("Follow-up answers from the user:\n" + "\n".join(answer_lines))

    if not parts:
        return ""

    return "\n\n".join(parts)


def extract_poems_from_result(result: Any) -> dict[str, str | None]:
    """Map the crew result's ordered ``tasks_output`` to variant-keyed poems."""
    tasks_output = getattr(result, "tasks_output", []) or []
    poems: dict[str, str | None] = {}
    for index, variant_key in enumerate(VARIANT_ORDER):
        poems[variant_key] = tasks_output[index].raw if index < len(tasks_output) else None
    return poems
