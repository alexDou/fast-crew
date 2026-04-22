"""Backward-compatible re-export of the CrewAI service singleton.

The implementation now lives in :mod:`app.services.crewai`; this module
only exists so existing imports such as::

    from app.services.crewai_service import crewai_service

continue to work.
"""

from .crewai import CrewAIService, crewai_service

__all__ = ["CrewAIService", "crewai_service"]
