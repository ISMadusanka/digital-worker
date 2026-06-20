"""
The core observe → plan → act loop that drives the worker.

Flow per iteration:
  1. Observe the current screen (screenshot + element detection + annotation).
  2. Ask the agent to decide and execute the next action toward the plan.
  3. Re-observe on the next iteration; the agent self-corrects from the fresh state.

Completion is signalled explicitly by the agent calling the ``finish`` tool.
"""

from config import settings
from agent import tools
from utils.logger import get_logger

log = get_logger(__name__)


class ActionVerificationLoop:
    """Manages the iteration loop: Observe → Act → Re-observe → Repeat."""

    def __init__(self, worker_instance) -> None:
        self.worker = worker_instance

    def run_until_complete(self, goal: str) -> str:
        """Run the observe-act loop until the agent calls finish() or we hit
        the iteration ceiling."""
        # Build a high-level plan up front; the agent follows it step by step.
        plan = self.worker.make_plan(goal)
        if plan:
            self.worker.emit_step("Plan ready.")

        iteration = 1
        last_action_summary = ""
        history: list[str] = []
        last_sig = ""
        repeat_count = 0

        while iteration <= settings.MAX_AGENT_ITERATIONS:
            if self.worker.stop_requested:
                log.info("Execution stopped by user.")
                return "Execution stopped by user."

            log.info("=== Loop Iteration %d ===", iteration)
            self.worker.emit_step(f"[{iteration}] Observing screen...")

            # 1. Observe
            perception = self.worker.observe()
            if self.worker.stop_requested:
                return "Execution stopped by user."

            self.worker.emit_step(f"[{iteration}] Deciding next action...")

            # 2. Decide and act (agent calls a tool)
            history_text = "\n".join(history[-12:])  # recent actions, bounded
            try:
                response = self.worker.reason_and_act(
                    goal, perception, plan, history_text, iteration
                )
            except Exception as e:
                log.error("Agent step failed: %s", e)
                self.worker.emit_step(f"Step error: {e}")
                iteration += 1
                continue

            results = response.get("results", [])
            agent_text = response.get("text", "") or ""
            last_action_summary = (results[0] if results else agent_text).strip()

            if last_action_summary:
                self.worker.emit_step(last_action_summary[:120])
                history.append(f"{iteration}. {last_action_summary[:200]}")
            else:
                # No tool call and no text — nudge it forward next turn.
                history.append(f"{iteration}. (no action taken)")
            log.info("Iteration %d action: %s", iteration, last_action_summary or "(none)")

            # 2b. Stuck-loop detection — never let it repeat one dead action forever.
            sig = response.get("action_sig", "")
            if sig and sig == last_sig:
                repeat_count += 1
            else:
                repeat_count = 0
                last_sig = sig

            if repeat_count >= 2:  # 3rd identical action in a row
                warn = (
                    "STUCK: the exact same action just ran "
                    f"{repeat_count + 1} times with no effect. STOP repeating it — press 'escape' "
                    "to close any stuck menu and use a DIFFERENT method (e.g. a keyboard shortcut)."
                )
                log.warning(warn)
                history.append(f"{iteration}. {warn}")
            if repeat_count >= 5:  # 6th identical action — give up gracefully
                msg = (
                    f"Aborted: repeated the same action {repeat_count + 1} times without progress "
                    f"({sig}). It likely hit an unreliable UI path."
                )
                log.error(msg)
                self.worker.emit_step("Stuck — aborting.")
                return msg

            # 3. Completion check — the agent calls finish() when done.
            if tools.is_finished():
                summary = tools.get_finish_summary() or agent_text
                log.info("Goal complete: %s", summary)
                self.worker.emit_step("Goal achieved!")
                return f"Success after {iteration} iteration(s): {summary}"

            iteration += 1

        return (
            f"Reached the maximum of {settings.MAX_AGENT_ITERATIONS} iterations. "
            f"Last action: {last_action_summary}"
        )
