"""
The core action-verification loop that ties perception and reasoning together.
"""

from typing import Optional

from config import settings
from utils.logger import get_logger

log = get_logger(__name__)


class ActionVerificationLoop:
    """Manages the iteration loop: Act → Verify (Observe) → Plan."""

    def __init__(self, worker_instance) -> None:
        # We take the worker instance to call its observe/plan methods without circular imports
        self.worker = worker_instance
        self.max_retries = settings.MAX_ACTION_RETRIES

    def run_until_complete(self, goal: str) -> str:
        """Run the observe-plan-act loop until the LLM indicates completion
        or we hit max iterations.
        """
        iteration = 1
        
        while iteration <= settings.MAX_AGENT_ITERATIONS:
            log.info("=== Loop Iteration %d ===", iteration)
            
            # 1. Observe (Screenshot + OCR + Preprocess)
            ui_state = self.worker.observe()
            
            # 2. Plan and Act (Agent decides and calls tools)
            response = self.worker.reason_and_act(goal, ui_state)
            
            messages = response.get("messages", [])
            agent_output = messages[-1].content if messages else ""
            
            # The agent should state when it's done. 
            # We look for keywords, or just rely on LangChain's finish logic.
            # In a standard setup, if the agent doesn't call a tool, it returns text to the user.
            if "complete" in agent_output.lower() or "achieved" in agent_output.lower() or "finished" in agent_output.lower():
                log.info("Goal achieved according to agent!")
                return f"Success after {iteration} iterations: {agent_output}"
                
            log.info("Agent output this iteration: %s", agent_output)
            
            # The agent called a tool (or multiple) as part of `reason_and_act`.
            # LangChain's AgentExecutor handles the immediate loop of tool calling,
            # but we force a fresh UI state fetch by wrapping it here if it exits to us.
            
            iteration += 1

        return f"Failed: Reached maximum iterations ({settings.MAX_AGENT_ITERATIONS})."
