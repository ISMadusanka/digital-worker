"""
The core action-verification loop that ties perception and reasoning together.
"""

from typing import Optional

from config import settings
from utils.logger import get_logger

log = get_logger(__name__)


class ActionVerificationLoop:
    """Manages the iteration loop: Observe → Plan (single action) → Verify → Repeat."""

    def __init__(self, worker_instance) -> None:
        # We take the worker instance to call its observe/plan methods without circular imports
        self.worker = worker_instance
        self.max_retries = settings.MAX_ACTION_RETRIES

    def run_until_complete(self, goal: str) -> str:
        """Run the observe-plan-act loop until the LLM indicates completion
        or we hit max iterations.

        Each iteration:
          1. Observe the current UI state (screenshot + OCR).
          2. Ask the agent to decide and execute ONE action.
          3. The action tool automatically verifies via screenshot + OCR + LLM.
          4. If verification failed, the tool returns failure info to the agent,
             which can then adapt in subsequent iterations.
        """
        iteration = 1
        consecutive_failures = 0
        
        while iteration <= settings.MAX_AGENT_ITERATIONS:
            if self.worker.stop_requested:
                log.info("Execution stopped by user.")
                return "Execution stopped by user."

            log.info("=== Loop Iteration %d ===", iteration)
            self.worker.emit_step("Observing screen...")
            
            # 1. Observe (Screenshot + OCR + Preprocess)
            ui_state = self.worker.observe()
            
            if self.worker.stop_requested:
                return "Execution stopped by user."

            self.worker.emit_step("Planning next action...")
            
            # 2. Plan and Act (Agent decides ONE action and calls a tool)
            #    The tool internally captures after-state and runs verification.
            response = self.worker.reason_and_act(goal, ui_state)
            
            messages = response.get("messages", [])
            agent_output = messages[-1].content if messages else ""
            
            # Check if verification failed in this iteration by examining
            # tool responses in the message history.
            verification_failed = self._check_for_verification_failure(messages)
            
            if verification_failed:
                consecutive_failures += 1
                log.warning(
                    "Verification failure detected (consecutive: %d/%d)",
                    consecutive_failures,
                    self.max_retries,
                )
                if consecutive_failures >= self.max_retries:
                    log.error(
                        "Too many consecutive verification failures (%d). Aborting.",
                        consecutive_failures,
                    )
                    return (
                        f"Failed: {consecutive_failures} consecutive action verification "
                        f"failures. Last agent output: {agent_output}"
                    )
            else:
                # Reset counter on any successful iteration
                consecutive_failures = 0
            
            # The agent should state when it's done. 
            # We look for keywords, or just rely on LangChain's finish logic.
            # In a standard setup, if the agent doesn't call a tool, it returns text to the user.
            if "complete" in agent_output.lower() or "achieved" in agent_output.lower() or "finished" in agent_output.lower():
                log.info("Goal achieved according to agent!")
                self.worker.emit_step("Goal achieved!")
                return f"Success after {iteration} iterations: {agent_output}"
                
            log.info("Agent output this iteration: %s", agent_output)
            self.worker.emit_step(f"Agent says: {agent_output}")
            
            # The agent called a tool (or multiple) as part of `reason_and_act`.
            # LangChain's AgentExecutor handles the immediate loop of tool calling,
            # but we force a fresh UI state fetch by wrapping it here if it exits to us.
            
            iteration += 1

        return f"Failed: Reached maximum iterations ({settings.MAX_AGENT_ITERATIONS})."

    @staticmethod
    def _check_for_verification_failure(messages: list) -> bool:
        """Scan the agent's message history for verification failure markers.

        Tool responses containing '❌' or 'VERIFICATION FAILED' indicate
        that an action did not pass verification.
        """
        for msg in messages:
            # Tool messages have content with our verification markers
            content = ""
            if hasattr(msg, "content") and isinstance(msg.content, str):
                content = msg.content
            elif isinstance(msg, dict) and "content" in msg:
                content = str(msg["content"])

            if "❌" in content or "VERIFICATION FAILED" in content:
                return True

        return False
