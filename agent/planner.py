"""
Agent planner setup using LangChain and a multimodal GPT-4o model.

Provides two capabilities:
  - :meth:`make_plan` — decompose a complex goal into an ordered checklist.
  - :meth:`plan_and_act` — given the current screen (text + annotated image),
    decide and execute the next action(s).
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from config import settings
from agent.prompts import SYSTEM_PROMPT, PLANNER_PROMPT
from agent.tools import get_all_tools
from utils import win
from utils.logger import get_logger

log = get_logger(__name__)


class AgentPlanner:
    """Reasons about screen state and decides actions; can also plan ahead.

    Each :meth:`plan_and_act` call makes exactly ONE model decision and executes
    exactly ONE tool, then returns so the worker re-observes a fresh screen. This
    deliberately avoids an autonomous multi-tool agent loop, which would act on
    stale coordinates (e.g. clicking a context-menu item that only appears after
    a right-click it never re-observed).
    """

    def __init__(self) -> None:
        log.info("Initializing AgentPlanner with %s", settings.OPENAI_MODEL)

        self.llm = ChatOpenAI(
            model=settings.OPENAI_MODEL,
            temperature=0,
            api_key=settings.OPENAI_API_KEY,
        )
        self.tools = get_all_tools()
        self._tool_map = {t.name: t for t in self.tools}
        self.llm_with_tools = self.llm.bind_tools(self.tools)

    # ------------------------------------------------------------------
    def make_plan(self, goal: str) -> str:
        """Decompose a goal into an ordered, numbered checklist of steps."""
        if not settings.USE_PLANNER:
            return ""
        try:
            response = self.llm.invoke([
                SystemMessage(content=PLANNER_PROMPT),
                HumanMessage(content=f"User goal: {goal}\n\nProduce the step-by-step plan."),
            ])
            plan = response.content.strip()
            log.info("Generated plan:\n%s", plan)
            return plan
        except Exception as e:
            log.error("Planning failed (continuing without a plan): %s", e)
            return ""

    # ------------------------------------------------------------------
    def plan_and_act(
        self,
        goal: str,
        ui_state: str,
        image_b64: str | None = None,
        plan: str = "",
        history: str = "",
        iteration: int = 1,
        session_id: str = "default",
        should_run=None,
    ) -> dict:
        """Invoke the agent to analyze the current screen and act.

        Each call is self-contained: it carries the goal, the plan, a compact
        text history of actions already taken, and the CURRENT screen (element
        list + one annotated screenshot). This keeps token usage bounded over
        long tasks instead of accumulating one image per iteration in memory.

        Args:
            goal: The overall user goal.
            ui_state: Text rendering of the current on-screen elements.
            image_b64: Base64 PNG of the annotated screenshot (vision), or None.
            plan: The step checklist to follow.
            history: Compact text log of actions taken so far.
            iteration: Current loop iteration (for the agent's awareness).
            session_id: Base id used to derive a per-iteration thread id.
        """
        log.info("Invoking agent for next action (iteration %d)...", iteration)

        env_line = (
            f"ENVIRONMENT: Desktop = {win.known_folder('desktop')} ; "
            f"Documents = {win.known_folder('documents')}. "
            "Use these absolute paths in Save dialogs.\n\n"
        )

        text = (
            f"OVERALL GOAL: {goal}\n\n"
            f"{env_line}"
            f"{('PLAN:' + chr(10) + plan + chr(10) + chr(10)) if plan else ''}"
            f"{('ACTIONS TAKEN SO FAR:' + chr(10) + history + chr(10) + chr(10)) if history else ''}"
            f"CURRENT UI STRUCTURE (iteration {iteration}) — act on an element by its [ID]:\n{ui_state}\n\n"
            "Decide the single next action that best advances the plan, then call ONE tool. "
            "If the screen looks unchanged from your last action, do NOT repeat it — try a different "
            "method. When the entire goal is complete, call finish()."
        )

        content: list | str
        if image_b64:
            content = [
                {"type": "text", "text": text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"},
                },
            ]
        else:
            content = text

        messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=content)]
        ai = self.llm_with_tools.invoke(messages)

        # Stop requested while the model was thinking? Don't fire the action.
        if should_run is not None and not should_run():
            return {"results": [], "text": "", "tool_called": False, "action_sig": ""}

        results: list[str] = []
        tool_called = False
        action_sig = ""
        # Execute only the FIRST tool call — one action per observe cycle.
        for call in (ai.tool_calls or []):
            name = call.get("name", "")
            tool = self._tool_map.get(name)
            if tool is None:
                results.append(f"Unknown tool: {name}")
                continue
            tool_called = True
            args = call.get("args", {})
            action_sig = f"{name}:{args}"
            try:
                result = tool.invoke(args)
            except Exception as e:
                log.error("Tool '%s' raised: %s", name, e)
                result = f"Failed: tool '{name}' error: {e}"
            results.append(f"{name}: {result}")
            break

        ai_text = ai.content if isinstance(ai.content, str) else ""
        return {
            "results": results,
            "text": ai_text,
            "tool_called": tool_called,
            "action_sig": action_sig,
        }
