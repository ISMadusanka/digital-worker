"""
Unified perception service.

Produces a single :class:`Perception` snapshot of the screen for the agent:
  - a list of UI elements (with IDs) from the chosen backend,
  - a text rendering of those elements for the LLM,
  - an optional Set-of-Mark annotated screenshot (base64) for vision models.

Backend selection (``PERCEPTION_BACKEND``):
  - ``uia``        — native Windows UI Automation tree (default, no GPU)
  - ``omniparser`` — local OmniParser GPU server
  - ``hybrid``     — UIA first, OmniParser fallback if UIA returns nothing
"""

from __future__ import annotations

from dataclasses import dataclass, field

from config import settings
from services.screenshot import ScreenshotService
from services.uia import UIAutomationService
from services.preprocessor import (
    UIElement,
    build_vision_image,
    format_elements_for_llm,
    preprocess_ocr,
)
from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class Perception:
    """A single observation of the screen."""

    elements: list[UIElement] = field(default_factory=list)
    text: str = ""
    image_b64: str | None = None  # base64 JPEG of the annotated screenshot
    image_scale: float = 1.0      # downscale factor applied to the vision image

    def element_at(self, element_id: int) -> UIElement | None:
        if 0 <= element_id < len(self.elements):
            return self.elements[element_id]
        return None


class PerceptionService:
    """Captures the screen and returns a structured :class:`Perception`."""

    def __init__(self) -> None:
        self.backend = settings.PERCEPTION_BACKEND
        self.screenshot = ScreenshotService()
        self.screen_width, self.screen_height = self.screenshot.get_screen_size()

        self.uia: UIAutomationService | None = None
        self.omni = None

        if self.backend in ("uia", "hybrid"):
            self.uia = UIAutomationService()
            if not self.uia.available and self.backend == "uia":
                log.warning("UIA unavailable; will fall back to OmniParser if reachable")
                self.backend = "hybrid"

        if self.backend in ("omniparser", "hybrid"):
            # Imported lazily so a missing OmniParser server doesn't break UIA mode.
            from services.ocr import OmniParserService

            self.omni = OmniParserService()

        log.info(
            "PerceptionService ready — backend=%s, vision=%s, set-of-mark=%s, screen=%dx%d",
            self.backend,
            settings.USE_VISION,
            settings.SET_OF_MARK,
            self.screen_width,
            self.screen_height,
        )

    # ------------------------------------------------------------------
    def observe(self) -> Perception:
        """Capture the current UI state and return a :class:`Perception`.

        Primary path is the Windows UI Automation tree (text only — no screenshot
        ever reaches the LLM). A screenshot is taken ONLY when we must fall back
        to OmniParser (UIA returned nothing) or when vision is explicitly enabled.
        The overlay UI is hidden for the whole pass so it never appears in the
        tree, the OmniParser image, or any vision image.
        """
        image_b64: str | None = None
        image_scale = 1.0

        with self.screenshot.hidden():
            elements: list[UIElement] = []

            # 1) Primary: native UI Automation tree (rich, text-only).
            if self.backend in ("uia", "hybrid") and self.uia and self.uia.available:
                elements = self.uia.get_elements(self.screen_width, self.screen_height)

            # 2) Fallback: OmniParser — only if UIA found nothing. Captures a
            #    screenshot for the OmniParser SERVER (not the LLM).
            png_bytes: bytes | None = None
            if not elements and self.omni is not None:
                log.info("UIA returned no elements — falling back to OmniParser")
                png_bytes = self.screenshot.capture_full_screen(manage_visibility=False)
                elements = self._omni_elements(png_bytes)

            # 3) Optional vision image (off by default). Capture lazily if needed.
            if settings.USE_VISION:
                if png_bytes is None:
                    png_bytes = self.screenshot.capture_full_screen(manage_visibility=False)
                image_b64, image_scale = build_vision_image(
                    png_bytes,
                    elements,
                    max_width=settings.VISION_MAX_WIDTH,
                    quality=settings.VISION_JPEG_QUALITY,
                    set_of_mark=settings.SET_OF_MARK,
                )

        text = format_elements_for_llm(elements)
        return Perception(
            elements=elements, text=text, image_b64=image_b64, image_scale=image_scale
        )

    def read_active_window_text(self, max_chars: int = 6000) -> str:
        """Read the text content of the foreground window (UIA only)."""
        if self.uia and self.uia.available:
            return self.uia.get_active_window_text(max_chars=max_chars)
        log.warning("read_active_window_text requires the UIA backend")
        return ""

    # ------------------------------------------------------------------
    def _omni_elements(self, png_bytes: bytes) -> list[UIElement]:
        """Run the OmniParser fallback and return detected elements."""
        try:
            result = self.omni.process_image(png_bytes)
            return preprocess_ocr(
                omniparser_result=result,
                screen_width=self.screen_width,
                screen_height=self.screen_height,
            )
        except Exception as e:
            log.error("OmniParser detection failed: %s", e)
            return []
