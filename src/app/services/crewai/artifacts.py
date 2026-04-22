"""Storage helpers for human-readable artifacts (markdown dumps)."""

from __future__ import annotations

import logging

from ..storage_service import StorageError, storage_service
from .prompts import VARIANT_ORDER

logger = logging.getLogger(__name__)


def persist_output_artifacts(
    poem_source_id: int,
    *,
    image_analysis: str | None = None,
    poems: dict[str, str | None] | None = None,
) -> None:
    """Best-effort: write image analysis + poem variants as markdown files.

    The DB is the source of truth; these artifacts are purely for
    debugging and manual inspection so any storage failure is logged and
    swallowed instead of failing the workflow.
    """
    artifacts: dict[str, str] = {}
    if image_analysis:
        artifacts["image_analysis.md"] = image_analysis
    if poems:
        for variant_key in VARIANT_ORDER:
            artifacts[f"{variant_key}.md"] = poems.get(variant_key) or ""

    for filename, content in artifacts.items():
        if not content.strip():
            continue

        try:
            output_path = storage_service.store_output_artifact(poem_source_id, filename, content)
            logger.info("Stored output artifact for source_id=%s: %s", poem_source_id, output_path)
        except StorageError as exc:
            logger.warning(
                "Failed to store output artifact %s for source_id=%s: %s",
                filename,
                poem_source_id,
                exc,
            )
