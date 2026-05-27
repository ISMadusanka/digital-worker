"""
Screenshot capture service using PyAutoGUI.
"""

import io
import time
from pathlib import Path

import pyautogui

from config import settings
from utils.logger import get_logger

log = get_logger(__name__)


class ScreenshotService:
    """Captures screenshots of the full screen or a specific region."""

    def __init__(self, save_debug: bool = True) -> None:
        self._save_debug = save_debug
        self._counter = 0

    def capture_full_screen(self) -> bytes:
        """Take a full-screen screenshot and return PNG bytes.

        A short delay is applied before capture to let any pending UI
        animations finish.
        """
        time.sleep(settings.SCREENSHOT_DELAY)

        screenshot = pyautogui.screenshot()
        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")
        png_bytes = buffer.getvalue()

        if self._save_debug:
            self._save_to_disk(png_bytes, "full")

        log.info("Captured full-screen screenshot (%d bytes)", len(png_bytes))
        return png_bytes

    def capture_region(self, x: int, y: int, width: int, height: int) -> bytes:
        """Capture a rectangular region of the screen.

        Args:
            x: Left edge (pixels).
            y: Top edge (pixels).
            width: Region width (pixels).
            height: Region height (pixels).
        """
        time.sleep(settings.SCREENSHOT_DELAY)

        screenshot = pyautogui.screenshot(region=(x, y, width, height))
        buffer = io.BytesIO()
        screenshot.save(buffer, format="PNG")
        png_bytes = buffer.getvalue()

        if self._save_debug:
            self._save_to_disk(png_bytes, f"region_{x}_{y}")

        log.info(
            "Captured region screenshot (%d×%d at %d,%d — %d bytes)",
            width, height, x, y, len(png_bytes),
        )
        return png_bytes

    @staticmethod
    def get_screen_size() -> tuple[int, int]:
        """Return (width, height) of the primary monitor."""
        size = pyautogui.size()
        return size.width, size.height

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _save_to_disk(self, png_bytes: bytes, label: str) -> None:
        """Persist a screenshot for debugging."""
        self._counter += 1
        path = settings.SCREENSHOTS_DIR / f"{self._counter:03d}_{label}.png"
        path.write_bytes(png_bytes)
        log.debug("Saved debug screenshot → %s", path)
