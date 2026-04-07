import os

from crewai import LLM, Agent, Crew, Process, Task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.knowledge.source.text_file_knowledge_source import TextFileKnowledgeSource
from crewai.project import CrewBase, agent, crew, task


def _get_openrouter_api_key() -> str:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY is required to initialize PoetsCrew")
    return api_key


@CrewBase
class PoetsCrew:
    """PoetsCrew crew"""

    POET_DEFAULT_MODEL = "openrouter/tngtech/deepseek-r1t2-chimera"
    POET_MYSTIC_MODEL = "openrouter/deepseek/deepseek-v3.2"
    POET_FALLBACK_MODEL = "openrouter/deepseek/deepseek-v3.2"

    agents: list[BaseAgent]
    tasks: list[Task]

    # Use absolute paths for config files
    _config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
    agents_config = os.path.join(_config_dir, 'agents.yaml')
    tasks_config = os.path.join(_config_dir, 'tasks.yaml')

    def __init__(self, poet_model: str | None = None, poet_mystic_model: str | None = None):
        self._poet_model = poet_model or self.POET_DEFAULT_MODEL
        self._poet_mystic_model = poet_mystic_model or self.POET_MYSTIC_MODEL

    # CrewAI TextFileKnowledgeSource automatically looks in the knowledge/ directory
    text_knowledge_source = TextFileKnowledgeSource(
        file_paths=["preferences.txt"],
    )

    @agent
    def poet_modern(self) -> Agent:
        llm = LLM(
            model=self._poet_model,
            base_url="https://openrouter.ai/api/v1",
            api_key=_get_openrouter_api_key()
        )
        return Agent(
            llm=llm,
            config=self.agents_config['poet_modern'],
            verbose=True,
        )

    @agent
    def poet_classic(self) -> Agent:
        llm = LLM(
            model=self._poet_model,
            base_url="https://openrouter.ai/api/v1",
            api_key=_get_openrouter_api_key()
        )
        return Agent(
            llm=llm,
            config=self.agents_config['poet_classic'],
            verbose=True,
        )

    @agent
    def poet_mystic(self) -> Agent:
        llm = LLM(
            model=self._poet_mystic_model,
            base_url="https://openrouter.ai/api/v1",
            api_key=_get_openrouter_api_key()
        )
        return Agent(
            llm=llm,
            config=self.agents_config['poet_mystic'],
            verbose=True,
        )

    @task
    def poem_task_modern(self) -> Task:
        return Task(
            config=self.tasks_config['poem_task_modern'],
        )

    @task
    def poem_task_classic(self) -> Task:
        return Task(
            config=self.tasks_config['poem_task_classic'],
        )

    @task
    def poem_task_mystic(self) -> Task:
        return Task(
            config=self.tasks_config['poem_task_mystic'],
            context=[self.poem_task_modern(), self.poem_task_classic()],
        )

    @crew
    def crew(self) -> Crew:
        """Creates the crew of Poets"""

        return Crew(
            agents=self.agents, # Automatically created by the @agent decorator
            tasks=self.tasks, # Automatically created by the @task decorator
            process=Process.sequential,
            verbose=True,
            knowledge_sources=[self.text_knowledge_source],
            # process=Process.hierarchical, # In case you wanna use that instead https://docs.crewai.com/how-to/Hierarchical/
        )
