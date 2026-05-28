"""
LangChain tools that the agent can use to interact with the system.

Each tool automatically captures before/after UI states and verifies
the action via the ActionVerificationService when verification is enabled.
"""

from __future__ import annotations

import time
from typing import Any, Optional, Callable

from langchain.tools import tool

from actions.executor import ActionExecutor
from config import settings
from utils.logger import get_logger

log = get_logger(__name__)

# Global executor instance for tools to use
_executor = ActionExecutor()

# These are set at runtime by the DigitalWorker when it initializes.
# They allow tools to call back into the worker for observation and verification.
_observe_fn: Optional[Callable[[], str]] = None
_verify_fn: Optional[Callable[..., Any]] = None
_current_goal: str = ""
_current_ui_state: str = ""


def configure_tools(
    observe_fn: Callable[[], str],
    verify_fn: Callable[..., Any],
) -> None:
    """Set the observation and verification callbacks.

    Called once by ``DigitalWorker.__init__`` so that tools can capture
    fresh UI state and trigger verification without circular imports.
    """
    global _observe_fn, _verify_fn
    _observe_fn = observe_fn
    _verify_fn = verify_fn
    log.info("Tools configured with observe/verify callbacks")


def set_current_context(goal: str, ui_state: str) -> None:
    """Update the current goal and UI state so tools can access them.

    Called by ``DigitalWorker.reason_and_act`` before each agent invocation.
    """
    global _current_goal, _current_ui_state
    _current_goal = goal
    _current_ui_state = ui_state


def _verify_action(action_description: str, ui_state_before: str) -> str:
    """Shared verification logic for all action tools.

    1. Wait for UI to settle.
    2. Capture a fresh screenshot + OCR (the 'after' state).
    3. Ask the verification LLM to compare before/after.
    4. If verification fails, attempt Ctrl+Z undo.
    5. Return a detailed status message for the agent.
    """
    if not settings.VERIFY_AFTER_ACTION or _verify_fn is None or _observe_fn is None:
        return f"{action_description} — (verification disabled)"

    # Wait for the UI to settle after the action
    time.sleep(settings.VERIFICATION_DELAY)

    # Capture the after-state
    try:
        ui_state_after = _observe_fn()
    except Exception as e:
        log.error("Failed to capture post-action UI state: %s", e)
        return f"{action_description} — verification skipped (observation error: {e})"

    # Run verification
    result = _verify_fn(
        action_description=action_description,
        ui_state_before=ui_state_before,
        ui_state_after=ui_state_after,
        overall_goal=_current_goal,
    )

    if result.verified:
        return (
            f"✅ {action_description} — VERIFIED: {result.explanation}"
        )
    else:
        # Attempt undo
        log.warning(
            "Action verification FAILED: %s. Attempting undo...",
            result.explanation,
        )
        undo_result = _executor.undo()
        log.info("Undo result: %s", undo_result)

        correction_hint = ""
        if result.suggested_correction:
            correction_hint = (
                f" Suggested correction: {result.suggested_correction}"
            )

        return (
            f"❌ {action_description} — VERIFICATION FAILED: {result.explanation}. "
            f"Undo attempted ({undo_result}).{correction_hint} "
            f"Please re-examine the UI state and try a different approach."
        )


@tool
def click_element(element_name: str, x: int, y: int) -> str:
    """Click on a UI element at the specified screen coordinates.

    Args:
        element_name: A short description of what is being clicked (for logging purposes).
        x: The X coordinate on the screen.
        y: The Y coordinate on the screen.

    Returns:
        A status message indicating success or failure, including verification result.
    """
    ui_state_before = _current_ui_state
    action_desc = f"Clicked '{element_name}' at ({x}, {y})"

    click_result = _executor.click(x, y)
    if click_result.startswith("Failed"):
        return click_result

    return _verify_action(action_desc, ui_state_before)


@tool
def type_text(text: str) -> str:
    """Type a string of text using the keyboard.

    Args:
        text: The text to type.

    Returns:
        A status message indicating success or failure, including verification result.
    """
    ui_state_before = _current_ui_state
    action_desc = f'Typed text: "{text}"'

    type_result = _executor.type_text(text)
    if type_result.startswith("Failed"):
        return type_result

    return _verify_action(action_desc, ui_state_before)


@tool
def press_key(key: str) -> str:
    """Press a specific keyboard key (e.g., 'enter', 'tab', 'escape').

    Args:
        key: The name of the key to press.

    Returns:
        A status message indicating success or failure, including verification result.
    """
    ui_state_before = _current_ui_state
    action_desc = f"Pressed key: '{key}'"

    press_result = _executor.press_key(key)
    if press_result.startswith("Failed"):
        return press_result

    return _verify_action(action_desc, ui_state_before)


def get_all_tools() -> list[Any]:
    """Return the list of tools available to the agent."""
    return [click_element, type_text, press_key]
