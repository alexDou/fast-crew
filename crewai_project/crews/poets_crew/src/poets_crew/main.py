#!/usr/bin/env python
import json
import os
import sys
import warnings
from datetime import datetime

from poets_crew.crew import PoetsCrew
from poets_crew.tools.image_analyzer_tool import (
    INDISTINCT_CONTENT_MESSAGE,
    ImageAnalyzerTool,
)

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")


def _resolve_openrouter_api_key() -> str:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required to run poets_crew")

    return api_key


def _format_enhance(enhance: str | None) -> str:
    if not enhance:
        return ""

    return f"\n\nAdditional context from the user: {enhance}"


def _build_poem_inputs(image_path: str, enhance: str | None = None) -> dict[str, str]:
    tool = ImageAnalyzerTool(
        api_key=_resolve_openrouter_api_key(),
        model="qwen/qwen3-vl-235b-a22b-instruct",
    )
    image_analysis = tool._run(image_path=image_path)

    if image_analysis.strip().lower() == INDISTINCT_CONTENT_MESSAGE:
        raise RuntimeError(INDISTINCT_CONTENT_MESSAGE)

    return {
        "image_path": image_path,
        "image_analysis": image_analysis,
        "enhance": _format_enhance(enhance),
    }

def run():
    """
    Run the crew.
    """
    if len(sys.argv) < 2:
        raise ValueError("Image path is required. Usage: poets_crew <image_path> [enhance]")

    image_path = sys.argv[1]
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    enhance = sys.argv[2] if len(sys.argv) > 2 else None
    inputs = _build_poem_inputs(image_path=image_path, enhance=enhance)

    try:
        result = PoetsCrew().crew().kickoff(inputs=inputs)
        print(result)
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")


def train():
    """
    Train the crew for a given number of iterations.
    """
    inputs = {
        "topic": "AI LLMs",
        'current_year': str(datetime.now().year)
    }
    try:
        PoetsCrew().crew().train(n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=inputs)

    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")

def replay():
    """
    Replay the crew execution from a specific task.
    """
    try:
        PoetsCrew().crew().replay(task_id=sys.argv[1])

    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")

def test():
    """
    Test the crew execution and returns the results.
    """
    inputs = {
        "topic": "AI LLMs",
        "current_year": str(datetime.now().year)
    }

    try:
        PoetsCrew().crew().test(n_iterations=int(sys.argv[1]), eval_llm=sys.argv[2], inputs=inputs)

    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")

def run_with_trigger():
    """
    Run the crew with trigger payload.
    """
    if len(sys.argv) < 2:
        raise Exception("No trigger payload provided. Please provide JSON payload as argument.")

    try:
        trigger_payload = json.loads(sys.argv[1])
    except json.JSONDecodeError:
        raise Exception("Invalid JSON payload provided as argument")

    image_path = trigger_payload.get("image_path")
    if not image_path:
        raise ValueError("Trigger payload must include image_path")
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    enhance = trigger_payload.get("enhance")
    inputs = _build_poem_inputs(image_path=image_path, enhance=enhance)
    inputs["crewai_trigger_payload"] = trigger_payload

    try:
        result = PoetsCrew().crew().kickoff(inputs=inputs)
        return result
    except Exception as e:
        raise Exception(f"An error occurred while running the crew with trigger: {e}")
