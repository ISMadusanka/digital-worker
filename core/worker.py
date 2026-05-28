"""
Main orchestrator unifying services, agents, and execution.
"""

import uuid

from services.screenshot import ScreenshotService
from services.ocr import GoogleOCRService
from services.preprocessor import preprocess_ocr, format_elements_for_llm
from services.verifier import ActionVerificationService
from agent.planner import AgentPlanner
from agent.tools import configure_tools, set_current_context
from core.loop import ActionVerificationLoop
from config import settings
from utils.logger import get_logger

log = get_logger(__name__)


class DigitalWorker:
    """Orchestrates perception, reasoning, and action."""

    def __init__(self) -> None:
        log.info("Starting up Digital Worker components...")
        self.screenshot = ScreenshotService()
        self.ocr = GoogleOCRService()
        self.verifier = ActionVerificationService()
        self.agent = AgentPlanner()
        self.loop = ActionVerificationLoop(self)
        
        # Screen dimensions needed for OCR normalisation
        self.screen_width, self.screen_height = self.screenshot.get_screen_size()
        
        self.session_id = str(uuid.uuid4())
        
        # Wire up the tools with observation and verification callbacks
        # so they can capture post-action UI state and run verification
        # without circular imports.
        configure_tools(
            observe_fn=self.observe,
            verify_fn=self.verifier.verify,
        )
        
        log.info("Digital Worker ready. Session: %s", self.session_id)

    def observe(self) -> str:
        """Capture screen, run OCR, and format UI elements as text."""
        log.info("Observing screen state...")
        
        # 1. Capture
        png_bytes = self.screenshot.capture_full_screen()
        
        # 2. Extract Document data
        document = self.ocr.process_image(png_bytes)
        
        # 3. Preprocess to UI elements
        elements = preprocess_ocr(
            document=document,
            screen_width=self.screen_width,
            screen_height=self.screen_height,
        )
        
        # 4. Format for LLM
        ui_state_text = format_elements_for_llm(elements)
        return ui_state_text

    def reason_and_act(self, goal: str, ui_state: str) -> dict:
        """Pass the goal and current state to the LangChain agent.
        The agent will automatically call tools if needed.
        """
        # Update the tools module with current context so that
        # verification callbacks know the current goal and UI state.
        set_current_context(goal=goal, ui_state=ui_state)
        
        return self.agent.plan_and_act(
            goal=goal,
            ui_state=ui_state,
            session_id=self.session_id
        )

    def execute_goal(self, user_goal: str) -> str:
        """Main entry point to fulfill a user request."""
        log.info('--- Starting execution for goal: "%s" ---', user_goal)
        
        # Generate a new session ID for every new goal to keep memory clean
        self.session_id = str(uuid.uuid4())

        result = self.loop.run_until_complete(user_goal)
        
        log.info('--- Finished execution. Result: %s ---', result)
        return result
