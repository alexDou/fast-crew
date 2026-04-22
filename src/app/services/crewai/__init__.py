"""Staged CrewAI service package.

Import the module as ``app.services.crewai`` or rely on the thin
compatibility facade ``app.services.crewai_service`` which re-exports
the singleton for existing call-sites.
"""

from .service import CrewAIService, crewai_service

__all__ = ["CrewAIService", "crewai_service"]
