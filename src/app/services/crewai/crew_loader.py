"""Dynamic loader for the poets_crew project.

``CrewAIService`` boots the CrewAI code from a read-only mount at
``/code/crewai_project`` in Docker or from the repository itself during
local development. This module encapsulates that path resolution,
OpenRouter API key wiring, and module re-import so the rest of the
service can stay focused on orchestration.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

CrewAIModules = tuple[type[Any], type[Any], str]


def resolve_openrouter_api_key() -> str:
    """Read the OpenRouter API key from settings and export it to the crew process.

    The crew modules read ``OPENROUTER_API_KEY`` from the environment, so
    we mirror the secret into ``os.environ`` alongside returning it to the
    caller. Raises ``RuntimeError`` when the key is not configured.
    """
    from ...core.config import settings

    if not settings.OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not configured")

    api_key = settings.OPENROUTER_API_KEY.get_secret_value()
    os.environ["OPENROUTER_API_KEY"] = api_key
    return api_key


def resolve_crewai_root() -> tuple[str, str]:
    """Return ``(base_path, crew_root)`` for the poets_crew project.

    In Docker we mount the project at ``/code/crewai_project``; locally
    we walk up from this file to find the repo root. Either way the
    resolver returns the location of the poets crew package.
    """
    if os.path.exists("/code/crewai_project"):
        base_path = Path("/code")
    else:
        current = Path(__file__).resolve()
        while current.parent != current:
            if (current / "pyproject.toml").exists():
                base_path = current
                break
            current = current.parent
        else:
            base_path = Path(__file__).resolve().parent.parent.parent

    crew_root = base_path / "crewai_project" / "crews" / "poets_crew"
    return str(base_path), str(crew_root)


def load_poets_crew_modules() -> CrewAIModules:
    """Import ``PoetsCrew`` and ``ImageAnalyzerTool`` fresh for this job.

    The crew package reads YAML config with relative paths, so we temporarily
    ``chdir`` into the crew root. Stale module state is cleared first to
    make sure per-job model overrides (e.g. the fallback model) are honored.

    Returns the loaded classes plus the resolved OpenRouter API key so the
    caller can share it with the question-generation prompt.
    """
    _, crew_root = resolve_crewai_root()
    original_cwd = os.getcwd()
    try:
        os.chdir(crew_root)
        pkg_src = os.path.join(crew_root, "src")
        if pkg_src not in sys.path:
            sys.path.insert(0, pkg_src)

        openrouter_api_key = resolve_openrouter_api_key()

        for mod_name in list(sys.modules):
            if mod_name.startswith("poets_crew"):
                del sys.modules[mod_name]

        from poets_crew.crew import PoetsCrew
        from poets_crew.tools.image_analyzer_tool import ImageAnalyzerTool

        return PoetsCrew, ImageAnalyzerTool, openrouter_api_key
    finally:
        os.chdir(original_cwd)
