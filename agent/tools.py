"""
LangChain tools that the agent can use to interact with the system.

Each tool automatically captures before/after UI states and verifies
the action via the ActionVerificationService when verification is enabled.

Enhanced with Windows 11-specific tools: right-click, scroll, drag,
shell command execution, and an open_application convenience tool.
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


# ═══════════════════════════════════════════════════════════════════════════
# MOUSE ACTION TOOLS
# ═══════════════════════════════════════════════════════════════════════════

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
def double_click_element(element_name: str, x: int, y: int) -> str:
    """Double-click on a UI element at the specified screen coordinates.

    Use this to open applications from desktop shortcuts, open files, or
    any action that requires a double-click.

    Args:
        element_name: A short description of what is being double-clicked.
        x: The X coordinate on the screen.
        y: The Y coordinate on the screen.

    Returns:
        A status message indicating success or failure, including verification result.
    """
    ui_state_before = _current_ui_state
    action_desc = f"Double-clicked '{element_name}' at ({x}, {y})"

    click_result = _executor.double_click(x, y)
    if click_result.startswith("Failed"):
        return click_result

    return _verify_action(action_desc, ui_state_before)


@tool
def right_click_element(element_name: str, x: int, y: int) -> str:
    """Right-click on a UI element to open its context menu.

    On Windows 11, right-clicking opens a compact context menu. If you need
    the full classic context menu, look for "Show more options" at the bottom
    of the compact menu and click it.

    Common uses: desktop right-click for display settings/personalize,
    file/folder right-click for copy/cut/paste/rename/delete/properties,
    taskbar right-click for taskbar settings.

    Args:
        element_name: A short description of what is being right-clicked.
        x: The X coordinate on the screen.
        y: The Y coordinate on the screen.

    Returns:
        A status message indicating success or failure, including verification result.
    """
    ui_state_before = _current_ui_state
    action_desc = f"Right-clicked '{element_name}' at ({x}, {y})"

    click_result = _executor.right_click(x, y)
    if click_result.startswith("Failed"):
        return click_result

    return _verify_action(action_desc, ui_state_before)


@tool
def scroll(direction: str, amount: int = 3, x: int = -1, y: int = -1) -> str:
    """Scroll the mouse wheel up or down to navigate content.

    Use this to scroll through long lists, web pages, settings panels,
    File Explorer, or any scrollable content on Windows 11.

    Args:
        direction: Either "up" or "down".
        amount: Number of scroll clicks (default 3). Use larger values for faster scrolling.
        x: Optional X coordinate to scroll at (-1 to use current mouse position).
        y: Optional Y coordinate to scroll at (-1 to use current mouse position).

    Returns:
        A status message indicating success or failure, including verification result.
    """
    ui_state_before = _current_ui_state
    clicks = amount if direction.lower() == "up" else -amount
    pos_x = x if x >= 0 else None
    pos_y = y if y >= 0 else None

    action_desc = f"Scrolled {direction} {amount} clicks"
    if pos_x is not None:
        action_desc += f" at ({pos_x}, {pos_y})"

    scroll_result = _executor.scroll(clicks, pos_x, pos_y)
    if scroll_result.startswith("Failed"):
        return scroll_result

    return _verify_action(action_desc, ui_state_before)


@tool
def drag_element(element_name: str, start_x: int, start_y: int, end_x: int, end_y: int) -> str:
    """Drag a UI element from one position to another.

    Use this for drag-and-drop operations such as moving files in File Explorer,
    rearranging items, resizing windows by dragging edges, moving sliders, etc.

    Args:
        element_name: A short description of what is being dragged.
        start_x: The starting X coordinate (where to pick up).
        start_y: The starting Y coordinate (where to pick up).
        end_x: The ending X coordinate (where to drop).
        end_y: The ending Y coordinate (where to drop).

    Returns:
        A status message indicating success or failure, including verification result.
    """
    ui_state_before = _current_ui_state
    action_desc = f"Dragged '{element_name}' from ({start_x}, {start_y}) to ({end_x}, {end_y})"

    drag_result = _executor.drag(start_x, start_y, end_x, end_y)
    if drag_result.startswith("Failed"):
        return drag_result

    return _verify_action(action_desc, ui_state_before)


# ═══════════════════════════════════════════════════════════════════════════
# KEYBOARD ACTION TOOLS
# ═══════════════════════════════════════════════════════════════════════════

@tool
def type_text(text: str, press_enter: bool = False) -> str:
    """Type a string of text using the keyboard.

    Args:
        text: The text to type.
        press_enter: If True, automatically press the Enter key immediately after typing the text. 
                     Set this to True when typing into search bars, address bars, or any text field 
                     where you want to submit the input immediately (e.g., Chrome address bar).

    Returns:
        A status message indicating success or failure, including verification result.
    """
    ui_state_before = _current_ui_state
    action_desc = f'Typed text: "{text}"'
    if press_enter:
        action_desc += ' and pressed Enter'

    type_result = _executor.type_text(text, press_enter=press_enter)
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


@tool
def press_hotkey(keys: str) -> str:
    """Press a keyboard shortcut / key combination.

    Use this for multi-key combos. On Windows 11, important shortcuts include:
    - win+s: Open Windows Search
    - win+i: Open Settings
    - win+e: Open File Explorer
    - ctrl+shift+esc: Open Task Manager
    - win+d: Show/hide desktop
    - alt+tab: Switch windows
    - alt+F4: Close active window
    - win+l: Lock computer
    - ctrl+c / ctrl+v: Copy / Paste
    - win+shift+s: Snipping Tool screenshot
    - win+x: Quick Link / Power User menu

    Args:
        keys: The keys to press simultaneously, separated by '+'.
              Examples: 'win+s', 'ctrl+c', 'alt+F4', 'ctrl+shift+esc'.

    Returns:
        A status message indicating success or failure, including verification result.
    """
    ui_state_before = _current_ui_state
    key_list = [k.strip() for k in keys.split('+')]
    action_desc = f"Pressed hotkey: '{keys}'"

    hotkey_result = _executor.hotkey(*key_list)
    if hotkey_result.startswith("Failed"):
        return hotkey_result

    return _verify_action(action_desc, ui_state_before)


# ═══════════════════════════════════════════════════════════════════════════
# WINDOWS 11 SPECIFIC TOOLS
# ═══════════════════════════════════════════════════════════════════════════

@tool
def open_application(app_name: str) -> str:
    """Open a Windows 11 application using the Start Menu search.

    This is a convenience tool that automates the pattern:
    Win+S → type app name → press Enter.

    Use this when you need to launch an application by name. The function
    opens Windows Search, types the application name, and presses Enter
    to launch the top result.

    Args:
        app_name: The name of the application to open (e.g., "Calculator",
                  "Notepad", "File Explorer", "Paint", "Edge", "Chrome",
                  "Word", "Excel", "PowerPoint", "VS Code", "Terminal").

    Returns:
        A status message indicating the application launch was initiated.
    """
    ui_state_before = _current_ui_state
    action_desc = f"Opening application: '{app_name}'"

    # Step 1: Open Windows Search
    hotkey_result = _executor.hotkey("win", "s")
    if hotkey_result.startswith("Failed"):
        return f"Failed to open Windows Search: {hotkey_result}"

    time.sleep(0.8)  # Wait for search to appear

    # Step 2: Type the application name
    type_result = _executor.type_text(app_name)
    if type_result.startswith("Failed"):
        return f"Failed to type app name: {type_result}"

    time.sleep(1.0)  # Wait for search results to populate

    # Step 3: Press Enter to launch the top result
    press_result = _executor.press_key("enter")
    if press_result.startswith("Failed"):
        return f"Failed to press Enter: {press_result}"

    time.sleep(1.5)  # Wait for the app to open

    return _verify_action(action_desc, ui_state_before)


@tool
def run_shell_command(command: str, timeout: int = 30) -> str:
    """Execute a PowerShell command on Windows 11 and return its output.

    Use this for tasks that are more efficient via command line than GUI
    interaction. The command runs non-interactively via PowerShell.

    GOOD USE CASES:
    - Get system information: "systeminfo", "Get-ComputerInfo"
    - List files: "Get-ChildItem C:\\Users"
    - Check network: "ipconfig", "ping google.com", "Test-NetConnection"
    - Manage processes: "Get-Process", "Stop-Process -Name notepad"
    - Check disk space: "Get-PSDrive C"
    - Get Windows version: "(Get-WmiObject Win32_OperatingSystem).Caption"
    - Get IP address: "Get-NetIPAddress"
    - Check installed software: "Get-WmiObject Win32_Product | Select Name"
    - Environment variables: "Get-ChildItem Env:"
    - Create files/folders: "New-Item -Path 'C:\\temp\\test' -ItemType Directory"
    - Read file content: "Get-Content 'C:\\path\\to\\file.txt'"
    - Check Windows services: "Get-Service | Where-Object {$_.Status -eq 'Running'}"

    DO NOT USE FOR:
    - Tasks that require GUI interaction (use mouse/keyboard tools instead).
    - Commands that require user input or are interactive.
    - Commands that could damage the system (format, delete system files, etc.).

    Args:
        command: The PowerShell command to execute.
        timeout: Maximum seconds to wait for completion (default 30, max 120).

    Returns:
        The command output (stdout and stderr) and exit status.
    """
    # Cap timeout to prevent runaway commands
    safe_timeout = min(max(timeout, 5), 120)

    result = _executor.run_shell_command(command, timeout=safe_timeout)
    return f"Shell command: {command}\n{result}"


def get_all_tools() -> list[Any]:
    """Return the list of tools available to the agent."""
    return [
        # Mouse actions
        click_element,
        double_click_element,
        right_click_element,
        scroll,
        drag_element,
        # Keyboard actions
        type_text,
        press_key,
        press_hotkey,
        # Windows 11 specific
        open_application,
        run_shell_command,
    ]
