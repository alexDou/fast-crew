"""Service for running CrewAI poetry generation in the background."""
import os
import logging
import traceback
from typing import Dict, Any
import asyncio
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CrewAIService:
    """Service to run CrewAI poetry generation tasks."""
    
    def __init__(self):
        # Thread pool for running synchronous CrewAI code
        self.executor = ThreadPoolExecutor(max_workers=3)
    
    @staticmethod
    def _get_first_line_normalized(text: str) -> str:
        import re
        
        if not text:
            return ""
        
        first_line = text.strip().split('\n')[0]
        normalized = re.sub(r'\s+', '', first_line).lower()
        
        return normalized
    
    async def _update_poem_source_status(
        self, 
        db: AsyncSession, 
        poem_source_id: int, 
        status: str
    ):
        from ..crud.crud_poem_sources import crud_poem_sources
        from ..schemas.poem_source import PoemSourceUpdate
        
        await crud_poem_sources.update(
            db=db,
            object=PoemSourceUpdate(status=status),
            id=poem_source_id
        )
        await db.commit()
    
    async def _save_poems(
        self,
        db: AsyncSession,
        user_id: int,
        poem_source_id: int,
        poems: Dict[str, str],
        critic_choice: str | None
    ):
        from datetime import datetime, UTC
        from ..crud.crud_poems import crud_poems
        from ..schemas.poem import PoemCreateInternal
        
        critic_first_line = self._get_first_line_normalized(critic_choice) if critic_choice else ""
        
        poem_first_lines = {}
        for key, text in poems.items():
            if text and text.strip():
                poem_first_lines[key] = self._get_first_line_normalized(text)
        
        for key, poem_text in poems.items():
            if poem_text and poem_text.strip():  # Only save non-empty poems
                poem_first_line = poem_first_lines.get(key, "")

                is_critic_choice = (
                    critic_first_line and 
                    poem_first_line and 
                    poem_first_line == critic_first_line
                )
                
                # Generate datetime directly to avoid serialization issues
                now = datetime.now(UTC).replace(tzinfo=None)
                
                poem_data = PoemCreateInternal(
                    user_id=user_id,
                    poem_source_id=poem_source_id,
                    poem=poem_text,
                    critic_choice=is_critic_choice,
                    created_at=now,
                    updated_at=None
                )
                
                await crud_poems.create(db=db, object=poem_data)
        
        await db.commit()
    
    def _run_crew_sync(
        self, 
        poem_source_id: int, 
        image_path: str,
        user_id: int,
        enhance: str | None,
        db_session_maker
    ) -> Dict[str, Any]:
        try:
            logger.info(f"Starting CrewAI poem generation for source_id={poem_source_id}, image={image_path}")
            
            # Direct import - crewai_project is in parent directory
            import importlib.util
            from pathlib import Path
            
            # CrewAI expects working directory to be the crew root for knowledge sources
            # Detect if running in Docker or locally
            if os.path.exists("/code/crewai_project"):
                base_path = Path("/code")
            else:
                # Find project root by looking for pyproject.toml
                current = Path(__file__).resolve()
                while current.parent != current:
                    if (current / "pyproject.toml").exists():
                        base_path = current
                        break
                    current = current.parent
                else:
                    # Fallback to 3 levels up from this file
                    base_path = Path(__file__).resolve().parent.parent.parent
            
            crew_root = base_path / "crewai_project" / "crews" / "poets_crew"
            logger.info(f"Base path: {base_path}, Crew root: {crew_root}, Exists: {crew_root.exists()}")
            original_cwd = os.getcwd()
            # Change to crew root for knowledge files
            os.chdir(str(crew_root))
            logger.info(f"Changed directory to {crew_root}")
            
            crew_path = str(crew_root / "src" / "poets_crew" / "crew.py")
            logger.info(f"Loading PoetsCrew from: {crew_path}")
            spec = importlib.util.spec_from_file_location("poets_crew.crew", crew_path)
            crew_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(crew_module)
            PoetsCrew = crew_module.PoetsCrew
            
            # Restore original working directory
            os.chdir(original_cwd)

            inputs = {"image_path": image_path}
            if enhance:
                inputs["enhance"] = f"\n\nAdditional context from the user: {enhance}"
            else:
                inputs["enhance"] = ""
            
            logger.info(f"Kicking off PoetsCrew with inputs: {inputs}")
            
            # Create crew instance and set image path for VisionTool
            poets_crew = PoetsCrew()
            poets_crew.set_image_path(image_path)
            
            result = poets_crew.crew().kickoff(inputs=inputs)
            logger.info(f"PoetsCrew completed successfully")

            # Tasks: 0=analyze_image, 1=poem_1, 2=poem_free, 3=critic
            image_analysis = result.tasks_output[0].raw if len(result.tasks_output) > 0 else None
            poem_1 = result.tasks_output[1].raw if len(result.tasks_output) > 1 else None
            poem_free = result.tasks_output[2].raw if len(result.tasks_output) > 2 else None
            critic = result.tasks_output[3].raw if len(result.tasks_output) > 3 else None
            
            poems = {
                "poem_1": poem_1,
                "poem_free": poem_free
            }
            
            # Save poems using new async engine in this thread's event loop
            from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
            from ..core.config import settings
            
            async def save_results():
                # Create a new engine and session factory for this thread
                database_url = f"{settings.POSTGRES_ASYNC_PREFIX}{settings.POSTGRES_URI}"
                engine = create_async_engine(
                    database_url,
                    echo=False,
                    future=True,
                )
                async_session = async_sessionmaker(
                    engine, class_=AsyncSession, expire_on_commit=False
                )
                
                async with async_session() as db:
                    try:
                        await self._save_poems(
                            db=db,
                            user_id=user_id,
                            poem_source_id=poem_source_id,
                            poems=poems,
                            critic_choice=critic
                        )

                        await self._update_poem_source_status(
                            db=db,
                            poem_source_id=poem_source_id,
                            status="success"
                        )
                    except Exception as e:
                        logger.error(f"Error saving poems for source_id={poem_source_id}: {e}")
                        logger.error(traceback.format_exc())
                        await self._update_poem_source_status(
                            db=db,
                            poem_source_id=poem_source_id,
                            status="error"
                        )
                    finally:
                        await engine.dispose()
            
            # Use new event loop in thread pool
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(save_results())
            finally:
                loop.close()
            
            return {
                "image_analysis": image_analysis,
                "poems": poems,
                "critic": critic
            }
            
        except Exception as e:
            logger.error(f"CRITICAL ERROR in CrewAI service for source_id={poem_source_id}: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            
            # Update error status using new async engine in this thread's event loop
            from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
            from ..core.config import settings
            
            async def update_error():
                # Create a new engine and session factory for this thread
                database_url = f"{settings.POSTGRES_ASYNC_PREFIX}{settings.POSTGRES_URI}"
                engine = create_async_engine(
                    database_url,
                    echo=False,
                    future=True,
                )
                async_session = async_sessionmaker(
                    engine, class_=AsyncSession, expire_on_commit=False
                )
                
                async with async_session() as db:
                    try:
                        await self._update_poem_source_status(
                            db=db,
                            poem_source_id=poem_source_id,
                            status="error"
                        )
                    finally:
                        await engine.dispose()
            
            # Use new event loop in thread pool
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(update_error())
            finally:
                loop.close()
            # Don't re-raise - log and mark as error instead
            logger.error(f"Poem generation failed for source_id={poem_source_id}")
    
    def start_poem_generation(
        self, 
        poem_source_id: int, 
        image_path: str,
        user_id: int,
        enhance: str | None,
        db_session_maker
    ) -> None:
        self.executor.submit(
            self._run_crew_sync,
            poem_source_id,
            image_path,
            user_id,
            enhance,
            db_session_maker
        )

crewai_service = CrewAIService()
