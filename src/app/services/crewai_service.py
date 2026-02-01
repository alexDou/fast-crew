"""Service for running CrewAI poetry generation in the background."""
import sys
import os
import logging
import traceback
from pathlib import Path
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
                
                poem_data = PoemCreateInternal(
                    user_id=user_id,
                    poem_source_id=poem_source_id,
                    poem=poem_text,
                    critic_choice=is_critic_choice
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
            from ...crewai.crews.poets_crew.src.poets_crew.crew import PoetsCrew

            inputs = {"image_path": image_path}
            if enhance:
                inputs["enhance"] = enhance
            
            logger.info(f"Kicking off PoetsCrew with inputs: {inputs}")
            result = PoetsCrew().crew().kickoff(inputs=inputs)
            logger.info(f"PoetsCrew completed successfully")

            image_analysis = result.tasks_output[0].raw if len(result.tasks_output) > 0 else None
            poem_1 = result.tasks_output[1].raw if len(result.tasks_output) > 1 else None
            poem_2 = result.tasks_output[2].raw if len(result.tasks_output) > 2 else None
            poem_free = result.tasks_output[3].raw if len(result.tasks_output) > 3 else None
            critic = result.tasks_output[4].raw if len(result.tasks_output) > 4 else None
            
            poems = {
                "poem_1": poem_1,
                "poem_2": poem_2,
                "poem_free": poem_free
            }
            
            async def save_results():
                async with db_session_maker() as db:
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
                        raise e
            
            asyncio.run(save_results())
            
            return {
                "image_analysis": image_analysis,
                "poems": poems,
                "critic": critic
            }
            
        except Exception as e:
            logger.error(f"CRITICAL ERROR in CrewAI service for source_id={poem_source_id}: {e}")
            logger.error(f"Full traceback:\n{traceback.format_exc()}")
            
            async def update_error():
                async with db_session_maker() as db:
                    await self._update_poem_source_status(
                        db=db,
                        poem_source_id=poem_source_id,
                        status="error"
                    )
            
            asyncio.run(update_error())
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
