"""Prompt-building and response-parsing helpers for the CrewAI service.

These are pure, dependency-light functions kept separate from the main
service class so they can be unit-tested without standing up the
ThreadPoolExecutor or the CrewAI runtime.
"""

from __future__ import annotations

import json
import random
import re
from typing import Any

from openai import OpenAI

QUESTION_MODEL = "deepseek/deepseek-v4-flash"
POET_PICKER_MODEL = "tngtech/deepseek-r1t2-chimera"
POET_WRITER_MODEL = "tngtech/deepseek-r1t2-chimera"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_FOLLOW_UP_QUESTIONS = 3
MIN_POET_CANDIDATES = 8
MAX_POET_CANDIDATES = 15
MIN_POEM_LINES = 3
MAX_POEM_LINES = 400
POET_TEMPERATURE = 0.85
FREESTYLE_TEMPERATURE = 0.9

QUESTION_GENERATION_PROMPT = (
    "You are preparing a staged poetry workflow. Based on the image analysis and the user's optional note, "
    "write 1 to 3 short follow-up questions that will help poets personalize the final poems. "
    'Return JSON only in the shape {"questions": [{"text": string}]}. '
    "The questions must be specific, concrete, and easy to answer in one or two sentences."
)

POET_PICKER_PROMPT = (
    "You are the poet picker for a poetry-generation workflow. Given an image description and a list of active "
    "poets, choose poet IDs that would make strong, varied style cards for this scene. Return JSON only in the "
    f"shape {{\"poet_ids\": [int, ...]}} with {MIN_POET_CANDIDATES} to {MAX_POET_CANDIDATES} unique IDs. "
    "Every ID must be drawn strictly from the provided list. Do not include names, commentary, or explanations."
)
POET_PICKER_RETRY_PROMPT = (
    POET_PICKER_PROMPT
    + " Your previous response was invalid. Return only valid JSON with IDs from the provided list, no duplicates."
)

POET_WRITER_SYSTEM_PROMPT = (
    "The output must be unmistakably recognizable as the work of {poet_name}. Before composing, silently recall "
    "at least five concrete stylistic signatures of that poet: form (meter, line length, stanza shape), diction "
    "register, imagery palette, recurring motifs, signature devices. Use them throughout. The poem is original — "
    "do not quote or paraphrase known lines; do not name the poet inside the poem. The poem must fit the scene "
    "described and the emotional context in the user's answers. The scene/emotion is the subject; the poet's "
    "voice is the lens. Honor the poet's typical form. Do not default to generic lyric shape. English output only. "
    "Output only the poem. No preamble, no commentary, no markdown, no title unless the poet typically titled works."
)
FREESTYLE_WRITER_SYSTEM_PROMPT = (
    "Write an original poem grounded in the scene and the user's feelings. You choose form, meter, and length; "
    "aim for what best fits the mood. Do not imitate any specific named poet. English only. Output only the poem."
)


def extract_text_content(content: Any) -> str:
    """Collapse OpenAI-style message ``content`` (string or parts list) to text."""
    if isinstance(content, list):
        return "".join(str(part) for part in content).strip()
    return str(content or "").strip()


def strip_json_markdown(response_content: str) -> str:
    """Remove common markdown fences around model JSON output."""
    response_content = response_content.strip()
    if response_content.startswith("```"):
        response_content = response_content.strip("`")
        if response_content.startswith("json"):
            response_content = response_content[4:].strip()
    return response_content


def normalize_questions(raw_questions: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Return a clean, at-most-3 list of ``{id, text}`` dicts.

    - Empty question texts are dropped.
    - IDs are re-assigned deterministically (``q1``, ``q2``, ``q3``) based
      on the *output* order so callers never see gaps such as ``q3``
      appearing on its own when upstream returned blanks for q1/q2.
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

    parsed = json.loads(strip_json_markdown(extract_text_content(completion.choices[0].message.content)))
    questions = parsed.get("questions")
    if not isinstance(questions, list):
        raise RuntimeError("Question generation returned an invalid payload")

    return normalize_questions(questions)


def normalize_poet_ids(raw_poet_ids: Any, allowed_ids: set[int]) -> list[int]:
    """Validate picker output and return de-duplicated poet IDs."""
    if not isinstance(raw_poet_ids, list):
        raise RuntimeError("Poet picker returned an invalid payload")

    normalized_ids: list[int] = []
    seen_ids: set[int] = set()
    for raw_id in raw_poet_ids:
        if not isinstance(raw_id, int):
            raise RuntimeError("Poet picker returned a non-integer poet id")
        if raw_id not in allowed_ids:
            raise RuntimeError("Poet picker returned an unknown poet id")
        if raw_id not in seen_ids:
            normalized_ids.append(raw_id)
            seen_ids.add(raw_id)

    if not (MIN_POET_CANDIDATES <= len(normalized_ids) <= MAX_POET_CANDIDATES):
        raise RuntimeError("Poet picker returned the wrong number of poet ids")

    return normalized_ids


def fallback_poet_ids(active_poets: list[dict[str, Any]], poem_source_id: int) -> list[int]:
    """Return a stable per-source random fallback from the active poet list."""
    poet_ids = [int(poet["id"]) for poet in active_poets if poet.get("id") is not None]
    if not poet_ids:
        return []

    picker = random.Random(poem_source_id)
    fallback_count = min(MIN_POET_CANDIDATES, len(poet_ids))
    return picker.sample(poet_ids, fallback_count)


def _request_poet_ids(
    image_analysis: str,
    active_poets: list[dict[str, Any]],
    openrouter_api_key: str,
    *,
    system_prompt: str,
) -> list[int]:
    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=openrouter_api_key)
    completion = client.chat.completions.create(
        extra_headers={"HTTP-Referer": "PoetsCrew", "X-Title": "PoetsCrew"},
        model=POET_PICKER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"Image description:\n{image_analysis}\n\n"
                    "Active poets as JSON array of {id, name}:\n"
                    f"{json.dumps(active_poets, ensure_ascii=False)}"
                ),
            },
        ],
    )

    parsed = json.loads(strip_json_markdown(extract_text_content(completion.choices[0].message.content)))
    return normalize_poet_ids(parsed.get("poet_ids"), {int(poet["id"]) for poet in active_poets})


def generate_poet_candidate_ids(
    image_analysis: str,
    active_poets: list[dict[str, Any]],
    openrouter_api_key: str,
    poem_source_id: int,
) -> list[int]:
    """Pick 8-15 poet IDs, retry once, then fall back to stable random IDs."""
    if not active_poets:
        return []

    try:
        return _request_poet_ids(
            image_analysis,
            active_poets,
            openrouter_api_key,
            system_prompt=POET_PICKER_PROMPT,
        )
    except Exception:
        try:
            return _request_poet_ids(
                image_analysis,
                active_poets,
                openrouter_api_key,
                system_prompt=POET_PICKER_RETRY_PROMPT,
            )
        except Exception:
            return fallback_poet_ids(active_poets, poem_source_id)


def build_stage_2_messages(
    image_analysis: str,
    questions: list[dict[str, str]] | None,
    answers: dict[str, str] | None,
    poet_name: str | None,
) -> tuple[str, str]:
    """Build the locked Stage 2 system/user prompt pair."""
    normalized_poet_name = poet_name.strip() if poet_name else ""
    system_prompt = (
        POET_WRITER_SYSTEM_PROMPT.format(poet_name=normalized_poet_name)
        if normalized_poet_name
        else FREESTYLE_WRITER_SYSTEM_PROMPT
    )

    prompt_lines: list[str] = []
    if normalized_poet_name:
        prompt_lines.append(f"Poet to replicate: {normalized_poet_name}")
    prompt_lines.append(f"Scene (from image analysis): {image_analysis}")
    prompt_lines.append("User's feelings and context:")

    question_text_by_id = {
        question["id"]: question["text"]
        for question in questions or []
        if question.get("id") and question.get("text")
    }
    answer_lines = [
        f"- {question_text_by_id.get(question_id, question_id)}: {answer}"
        for question_id, answer in (answers or {}).items()
        if answer.strip()
    ]
    prompt_lines.extend(answer_lines or ["- None provided."])
    prompt_lines.append("Write the poem now.")
    return system_prompt, "\n".join(prompt_lines)


def clean_poem_output(poem: str) -> str:
    """Strip common LLM wrappers while preserving poem line breaks."""
    cleaned = poem.strip()
    cleaned = strip_json_markdown(cleaned)
    cleaned = re.sub(r"^\s*(here is|here's)\b[^\n]*\n+", "", cleaned, flags=re.IGNORECASE)
    lines = cleaned.splitlines()
    if len(lines) > MAX_POEM_LINES:
        cleaned = "\n".join(lines[:MAX_POEM_LINES]).rstrip()
    return cleaned.strip()


def poem_is_too_short(poem: str) -> bool:
    """Return True when the poem has fewer than the minimum non-empty lines."""
    return len([line for line in poem.splitlines() if line.strip()]) < MIN_POEM_LINES


def _request_stage_2_poem(
    openrouter_api_key: str,
    system_prompt: str,
    user_prompt: str,
    *,
    temperature: float,
) -> str:
    client = OpenAI(base_url=OPENROUTER_BASE_URL, api_key=openrouter_api_key)
    completion = client.chat.completions.create(
        extra_headers={"HTTP-Referer": "PoetsCrew", "X-Title": "PoetsCrew"},
        model=POET_WRITER_MODEL,
        temperature=temperature,
        top_p=0.95,
        max_tokens=900,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )
    return clean_poem_output(extract_text_content(completion.choices[0].message.content))


def generate_stage_2_poem(
    openrouter_api_key: str,
    image_analysis: str,
    questions: list[dict[str, str]] | None,
    answers: dict[str, str] | None,
    poet_name: str | None,
) -> str:
    """Generate a single poem with one retry for too-short outputs."""
    system_prompt, user_prompt = build_stage_2_messages(image_analysis, questions, answers, poet_name)
    temperature = POET_TEMPERATURE if poet_name else FREESTYLE_TEMPERATURE
    poem = _request_stage_2_poem(
        openrouter_api_key,
        system_prompt,
        user_prompt,
        temperature=temperature,
    )
    if not poem_is_too_short(poem):
        return poem

    retry_prompt = user_prompt + "\nPrevious output was too short; deliver a full poem."
    return _request_stage_2_poem(
        openrouter_api_key,
        system_prompt,
        retry_prompt,
        temperature=max(0, temperature - 0.1),
    )


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


def extract_poem_from_result(result: Any) -> str | None:
    """Return the first non-empty raw output from a crew or LLM result.

    The poet-based workflow only produces one poem per source. The
    helper accepts either a CrewAI-style result (``.tasks_output[i].raw``)
    or a plain string and returns the trimmed text.
    """
    if isinstance(result, str):
        text = result.strip()
        return text or None

    tasks_output = getattr(result, "tasks_output", None) or []
    for task in tasks_output:
        raw = getattr(task, "raw", None)
        if isinstance(raw, str):
            text = raw.strip()
            if text:
                return text
    return None
