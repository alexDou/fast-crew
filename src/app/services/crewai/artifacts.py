"""Storage helpers for human-readable artifacts (markdown dumps)."""

from __future__ import annotations

import logging

from ..storage_service import StorageError, storage_service

logger = logging.getLogger(__name__)


def persist_output_artifacts(
    poem_source_id: int,
    *,
    image_analysis: str | None = None,
    poem: str | None = None,
) -> None:
    """Best-effort: write image analysis + the generated poem as markdown files.

    The DB is the source of truth; these artifacts are purely for
    debugging and manual inspection so any storage failure is logged and
    swallowed instead of failing the workflow.
    """
    artifacts: dict[str, str] = {}
    if image_analysis:
        artifacts["image_analysis.md"] = image_analysis
    if poem:
        artifacts["poem.md"] = poem

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
