"""
Main orchestrator unifying perception, planning, and execution.
"""

import uuid

from services.perception import PerceptionService, Perception
from services.verifier import ActionVerificationService
from agent.planner import AgentPlanner
from agent.tools import configure_tools, set_current_context, reset_finished
from core.loop import ActionVerificationLoop
from utils.logger import get_logger

log = get_logger(__name__)


class DigitalWorker:
    """Orchestrates perception, reasoning, and action on Windows 11."""

    def __init__(self, on_step_callback=None) -> None:
        self.on_step_callback = on_step_callback
        self.stop_requested = False
        log.info("Starting up Digital Worker components...")

        self.perception = PerceptionService()
        self.verifier = ActionVerificationService()
        self.agent = AgentPlanner()
        self.loop = ActionVerificationLoop(self)

        self.session_id = str(uuid.uuid4())

        # Wire tools to the worker's perception/verification callbacks.
        configure_tools(
            observe_fn=self.observe,
            verify_fn=self.verifier.verify,
            read_text_fn=self.perception.read_active_window_text,
        )

        log.info("Digital Worker ready. Session: %s", self.session_id)

    def observe(self) -> Perception:
        """Capture the screen as a structured perception snapshot."""
        return self.perception.observe()

    def make_plan(self, goal: str) -> str:
        """Decompose the goal into an ordered checklist (best effort)."""
        self.emit_step("Planning approach...")
        return self.agent.make_plan(goal)

    def reason_and_act(
        self, goal: str, perception: Perception, plan: str, history: str, iteration: int
    ) -> dict:
        """Pass the goal + current screen to the agent so it can act."""
        # Expose the current goal/elements to the tools (for id->coord resolution).
        set_current_context(goal=goal, ui_state=perception.text, elements=perception.elements)

        return self.agent.plan_and_act(
            goal=goal,
            ui_state=perception.text,
            image_b64=perception.image_b64,
            plan=plan,
            history=history,
            iteration=iteration,
            session_id=self.session_id,
        )

    def emit_step(self, message: str) -> None:
        if self.on_step_callback:
            self.on_step_callback(message)

    def execute_goal(self, user_goal: str) -> str:
        """Main entry point to fulfill a user request."""
        self.stop_requested = False
        reset_finished()
        self.emit_step(f"Starting goal: {user_goal}")
        log.info('--- Starting execution for goal: "%s" ---', user_goal)

        # Fresh session id per goal keeps conversational memory clean.
        self.session_id = str(uuid.uuid4())

        result = self.loop.run_until_complete(user_goal)

        self.emit_step(f"Finished: {result}")
        log.info('--- Finished execution. Result: %s ---', result)
        return result
