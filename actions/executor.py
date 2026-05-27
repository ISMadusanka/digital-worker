"""
Executes physical actions (mouse clicks, keyboard typing) via PyAutoGUI.
"""

import time
import pyautogui

from config import settings
from utils.logger import get_logger

log = get_logger(__name__)

# Configure PyAutoGUI safety & delays
pyautogui.FAILSAFE = True
pyautogui.PAUSE = settings.ACTION_PAUSE


class ActionExecutor:
    """Wrapper around PyAutoGUI to execute agent actions securely."""

    def click(self, x: int, y: int) -> str:
        """Move the mouse to (x,y) and click."""
        log.info("Executing click at (%d, %d)", x, y)
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
        try:
            pyautogui.moveTo(x, y, duration=settings.MOUSE_MOVE_DURATION, tween=pyautogui.easeInOutQuad)
            pyautogui.doubleClick()
            return f"Successfully double-clicked at ({x}, {y})"
        except pyautogui.FailSafeException:
            return "Failed: Mouse moved to a corner triggering fail-safe."
        except Exception as e:
            return f"Failed to double-click at ({x}, {y}): {e}"

    def type_text(self, text: str) -> str:
        """Type a string of text via the keyboard."""
        log.info('Typing text: "%s"', text)
        try:
            pyautogui.write(text, interval=0.05)
            return f'Successfully typed "{text}"'
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
