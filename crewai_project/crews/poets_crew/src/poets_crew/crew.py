from typing import List
from dotenv import load_dotenv
import os
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.knowledge.source.text_file_knowledge_source import TextFileKnowledgeSource

load_dotenv()
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")


@CrewBase
class PoetsCrew():
    """PoetsCrew crew"""

    POET_FREE_DEFAULT_MODEL = "openrouter/tngtech/deepseek-r1t2-chimera"
    POET_FREE_FALLBACK_MODEL = "openrouter/deepseek/deepseek-v3.2"

    agents: List[BaseAgent]
    tasks: List[Task]

    # Use absolute paths for config files
    _config_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config')
    agents_config = os.path.join(_config_dir, 'agents.yaml')
    tasks_config = os.path.join(_config_dir, 'tasks.yaml')

    def __init__(self, poet_free_model: str | None = None):
        self._poet_free_model = poet_free_model or self.POET_FREE_DEFAULT_MODEL

    # CrewAI TextFileKnowledgeSource automatically looks in the knowledge/ directory
    text_knowledge_source = TextFileKnowledgeSource(
        file_paths=["preferences.txt"],
    )

    @agent
    def poet_1(self) -> Agent:
        llm = LLM(
            model="openrouter/meta-llama/llama-3.2-3b-instruct",
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_api_key
        )
        return Agent(
            llm=llm,
            config=self.agents_config['poet_1'],
            verbose=True,
        )

    # @agent
    # def poet_2(self) -> Agent:
    #     llm = LLM(
    #         model="openrouter/meta-llama/llama-3.2-3b-instruct",
    #         base_url="https://openrouter.ai/api/v1",
    #         api_key=openrouter_api_key
    #     )
    #     return Agent(
    #         llm=llm,
    #         config=self.agents_config['poet_2'],
    #         verbose=True,
    #     )

    @agent
    def poet_free(self) -> Agent:
        llm = LLM(
            model=self._poet_free_model,
            base_url="https://openrouter.ai/api/v1",
            api_key=openrouter_api_key
        )
        return Agent(
            llm=llm,
            config=self.agents_config['poet_free'],
            verbose=True,
        )

    @agent
    def critic(self) -> Agent:
        return Agent(
            config=self.agents_config['critic'],
            verbose=True,
        )

    @task
    def poem_task_1(self) -> Task:
        return Task(
            config=self.tasks_config['poem_task_1'],
        )

    # @task
    # def poem_task_2(self) -> Task:
    #     return Task(
    #         config=self.tasks_config['poem_task_2'],
    #     )

    @task
    def poem_task_free(self) -> Task:
        return Task(
            config=self.tasks_config['poem_task_free'],
        )

    @task
    def critic_task(self) -> Task:
        return Task(
            config=self.tasks_config['critic_task'],
            context=[self.poem_task_1(), self.poem_task_free()],
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
