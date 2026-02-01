from multiprocessing import context
from typing import List
from dotenv import load_dotenv
import os
from crewai import Agent, Crew, Process, Task, LLM
from crewai.project import CrewBase, agent, crew, task
from crewai.agents.agent_builder.base_agent import BaseAgent
from crewai.knowledge.source.text_file_knowledge_source import TextFileKnowledgeSource
from crewai_tools import VisionTool

load_dotenv()
openrouter_api_key = os.getenv("OPENROUTER_API_KEY")

# Get absolute path to the image
current_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
image_path = os.path.join(current_dir, "media", "nature-picknic.jpeg")
vision_tool = VisionTool(image_path_url=image_path)

@CrewBase
class PoetsCrew():
    """PoetsCrew crew"""

    agents: List[BaseAgent]
    tasks: List[Task]

    agents_config = 'config/agents.yaml'
    tasks_config = 'config/tasks.yaml'

    text_knowledge_source = TextFileKnowledgeSource(
        file_paths=["preferences.txt"],
    )

    @agent
    def image_analyzer(self) -> Agent:
        return Agent(
            config=self.agents_config['image_analyzer'],
            verbose=True,
            tools=[vision_tool],
        )    
        
    @agent
    def poet_1(self) -> Agent:
        llm = LLM(
            model="openrouter/anthropic/claude-haiku-4.5",
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
    #         model="openrouter/tngtech/deepseek-r1t-chimera:free",
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
            model="openrouter/tngtech/deepseek-r1t2-chimera:free",
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
    def analyze_image_task(self) -> Task:
        return Task(
            config=self.tasks_config['analyze_image_task'],
        )

    @task
    def poem_task_1(self) -> Task:
        return Task(
            config=self.tasks_config['poem_task_1'],
            context=[self.analyze_image_task()],
        )

    @task
    def poem_task_2(self) -> Task:
        return Task(
            config=self.tasks_config['poem_task_2'],
            context=[self.analyze_image_task()],
        )

    @task
    def poem_task_free(self) -> Task:
        return Task(
            config=self.tasks_config['poem_task_free'],
            context=[self.analyze_image_task()],
        )

    @task
    def critic_task(self) -> Task:
        return Task(
            config=self.tasks_config['critic_task'],
            context=[self.poem_task_1(), self.poem_task_2(), self.poem_task_free()],
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
