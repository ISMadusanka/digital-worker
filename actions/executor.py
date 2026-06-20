"""
Executes physical actions (mouse clicks, keyboard typing) via PyAutoGUI.

Includes undo capabilities for correcting failed actions.
Enhanced with Windows 11-specific actions (right-click, scroll, shell commands).
"""

import time
import subprocess
import pyautogui

from config import settings
from utils.logger import get_logger

log = get_logger(__name__)

# Configure PyAutoGUI safety & delays
pyautogui.FAILSAFE = True
pyautogui.PAUSE = settings.ACTION_PAUSE


import contextlib

class ActionExecutor:
    """Wrapper around PyAutoGUI to execute agent actions securely on Windows 11."""

    on_before_action = None
    on_after_action = None

    @contextlib.contextmanager
    def _action_context(self):
        if ActionExecutor.on_before_action:
            ActionExecutor.on_before_action()
            time.sleep(0.1)
        try:
            yield
        finally:
            if ActionExecutor.on_after_action:
                ActionExecutor.on_after_action()

    def click(self, x: int, y: int) -> str:
        """Move the mouse to (x,y) and click."""
        log.info("Executing click at (%d, %d)", x, y)
        with self._action_context():
            try:
                pyautogui.moveTo(x, y, duration=settings.MOUSE_MOVE_DURATION, tween=pyautogui.easeInOutQuad)
                pyautogui.click()
                return f"Successfully clicked at ({x}, {y})"
            except pyautogui.FailSafeException:
                log.warning("Fail-safe triggered during click!")
                return "Failed: Mouse moved to a corner triggering fail-safe."
            except Exception as e:
                log.error("Click failed: %s", e)
                return f"Failed to click at ({x}, {y}): {e}"

    def double_click(self, x: int, y: int) -> str:
        """Move the mouse to (x,y) and double click."""
        log.info("Executing double-click at (%d, %d)", x, y)
        with self._action_context():
            try:
                pyautogui.moveTo(x, y, duration=settings.MOUSE_MOVE_DURATION, tween=pyautogui.easeInOutQuad)
                pyautogui.doubleClick()
                return f"Successfully double-clicked at ({x}, {y})"
            except pyautogui.FailSafeException:
                return "Failed: Mouse moved to a corner triggering fail-safe."
            except Exception as e:
                return f"Failed to double-click at ({x}, {y}): {e}"

    def right_click(self, x: int, y: int) -> str:
        """Move the mouse to (x,y) and right-click to open context menu."""
        log.info("Executing right-click at (%d, %d)", x, y)
        with self._action_context():
            try:
                pyautogui.moveTo(x, y, duration=settings.MOUSE_MOVE_DURATION, tween=pyautogui.easeInOutQuad)
                pyautogui.rightClick()
                return f"Successfully right-clicked at ({x}, {y})"
            except pyautogui.FailSafeException:
                return "Failed: Mouse moved to a corner triggering fail-safe."
            except Exception as e:
                log.error("Right-click failed: %s", e)
                return f"Failed to right-click at ({x}, {y}): {e}"

    def type_text(self, text: str, press_enter: bool = False) -> str:
        """Type a string of text via the keyboard."""
        log.info('Typing text: "%s" (press_enter=%s)', text, press_enter)
        try:
            pyautogui.write(text, interval=settings.TYPING_INTERVAL)
            if press_enter:
                pyautogui.press('enter')
            msg = f'Successfully typed "{text}"'
            if press_enter:
                msg += ' and pressed Enter'
            return msg
        except pyautogui.FailSafeException:
            return "Failed: Mouse moved to a corner triggering fail-safe."
        except Exception as e:
            return f"Failed to type text: {e}"

    def press_key(self, key: str) -> str:
        """Press a specific key (e.g., 'enter', 'escape', 'ctrl')."""
        log.info("Pressing key: %s", key)
        try:
            pyautogui.press(key)
            return f"Successfully pressed '{key}'"
        except pyautogui.FailSafeException:
            return "Failed: Mouse moved to a corner triggering fail-safe."
        except Exception as e:
            return f"Failed to press key '{key}': {e}"

    def hotkey(self, *keys: str) -> str:
        """Press a key combination (e.g., 'win', 's' for Win+S)."""
        log.info("Executing hotkey: %s", " + ".join(keys))
        try:
            pyautogui.hotkey(*keys)
            return f"Successfully pressed hotkey: {' + '.join(keys)}"
        except pyautogui.FailSafeException:
            return "Failed: Mouse moved to a corner triggering fail-safe."
        except Exception as e:
            log.error("Hotkey failed: %s", e)
            return f"Failed to press hotkey '{' + '.join(keys)}': {e}"

    def scroll(self, clicks: int, x: int | None = None, y: int | None = None) -> str:
        """Scroll the mouse wheel at the current or specified position.

        Args:
            clicks: Number of 'clicks' to scroll. Positive = up, negative = down.
            x: Optional X coordinate to scroll at.
            y: Optional Y coordinate to scroll at.
        """
        direction = "up" if clicks > 0 else "down"
        log.info("Scrolling %s (%d clicks) at (%s, %s)", direction, abs(clicks), x, y)
        with self._action_context():
            try:
                if x is not None and y is not None:
                    pyautogui.moveTo(x, y, duration=settings.MOUSE_MOVE_DURATION)
                pyautogui.scroll(clicks)
                pos_info = f" at ({x}, {y})" if x is not None else ""
                return f"Successfully scrolled {direction} {abs(clicks)} clicks{pos_info}"
            except pyautogui.FailSafeException:
                return "Failed: Mouse moved to a corner triggering fail-safe."
            except Exception as e:
                log.error("Scroll failed: %s", e)
                return f"Failed to scroll: {e}"

    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int) -> str:
        """Drag from one position to another (click and hold, then release)."""
        log.info("Dragging from (%d, %d) to (%d, %d)", start_x, start_y, end_x, end_y)
        with self._action_context():
            try:
                pyautogui.moveTo(start_x, start_y, duration=settings.MOUSE_MOVE_DURATION)
                pyautogui.mouseDown()
                pyautogui.moveTo(end_x, end_y, duration=settings.MOUSE_MOVE_DURATION * 2)
                pyautogui.mouseUp()
                return f"Successfully dragged from ({start_x}, {start_y}) to ({end_x}, {end_y})"
            except pyautogui.FailSafeException:
                return "Failed: Mouse moved to a corner triggering fail-safe."
            except Exception as e:
                log.error("Drag failed: %s", e)
                return f"Failed to drag: {e}"

    def run_shell_command(self, command: str, timeout: int = 30) -> str:
        """Execute a PowerShell command on Windows 11 and return its output.

        This runs commands non-interactively via PowerShell. Use for tasks
        that are more efficient via CLI than GUI (e.g., checking system info,
        listing files, managing processes, network diagnostics).

        Args:
            command: The PowerShell command to execute.
            timeout: Maximum seconds to wait for the command to complete.
        """
        log.info("Executing shell command: %s", command)
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            output = ""
            if result.stdout.strip():
                output += f"STDOUT:\n{result.stdout.strip()}"
            if result.stderr.strip():
                if output:
                    output += "\n"
                output += f"STDERR:\n{result.stderr.strip()}"
            if not output:
                output = "(no output)"

            status = "succeeded" if result.returncode == 0 else f"failed (exit code {result.returncode})"
            return f"Command {status}.\n{output}"

        except subprocess.TimeoutExpired:
            log.warning("Shell command timed out after %d seconds: %s", timeout, command)
            return f"Failed: Command timed out after {timeout} seconds."
        except Exception as e:
            log.error("Shell command execution failed: %s", e)
            return f"Failed to execute command: {e}"

    def undo(self) -> str:
        """Send Ctrl+Z to undo the last action in the active application."""
        log.info("Executing undo (Ctrl+Z)")
        try:
            pyautogui.hotkey("ctrl", "z")
            time.sleep(0.3)  # Brief pause to let the undo take effect
            return "Successfully sent Ctrl+Z (undo)"
        except pyautogui.FailSafeException:
            return "Failed: Mouse moved to a corner triggering fail-safe."
        except Exception as e:
            log.error("Undo failed: %s", e)
            return f"Failed to undo: {e}"
