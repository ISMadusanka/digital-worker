"""
Agent planner setup using LangChain and GPT-4o.
"""

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver

from config import settings
from agent.prompts import SYSTEM_PROMPT
from agent.tools import get_all_tools
from utils.logger import get_logger

log = get_logger(__name__)

class AgentPlanner:
    """Manages the LangChain agent that reasons about UI state and decides actions."""

    def __init__(self) -> None:
        log.info("Initializing AgentPlanner with %s", settings.OPENAI_MODEL)
        
        self.llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=0,
            api_key=settings.OPENAI_API_KEY,
        )
        self.tools = get_all_tools()
        self.memory = MemorySaver()
        
        self.agent = create_agent(
            model=self.llm,
            tools=self.tools,
            system_prompt=SYSTEM_PROMPT,
            checkpointer=self.memory
        )

    def plan_and_act(self, goal: str, ui_state: str, session_id: str = "default") -> dict:
        """Invoke the agent to analyze the state and execute a tool.
        
        Args:
            goal: The overarching user goal.
            ui_state: Formatted string of current UI elements.
            session_id: Session identifier for conversational memory.
            
        Returns:
            The agent's response dict (contains 'messages' key).
        """
        log.info("Invoking agent to determine next action...")
        
        user_message = f"Current Goal: {goal}\n\nCurrent UI State:\n{ui_state}\n\nWhat is your next action?"
        
        config = {"configurable": {"thread_id": session_id}}
        
        response = self.agent.invoke(
            {"messages": [("user", user_message)]},
            config=config
        )
        
        return response
