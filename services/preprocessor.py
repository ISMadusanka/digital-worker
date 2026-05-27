"""
Preprocessor — converts raw Document AI output into a clean list of
UI elements suitable for LLM consumption.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from google.cloud import documentai

from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class UIElement:
    """A single UI element extracted from OCR."""

    text: str
    center_x: int
    center_y: int
    x: int
    y: int
    width: int
    height: int
    confidence: float = 0.0
    element_type: str = "unknown"  # button | display | label

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "type": self.element_type,
            "center_x": self.center_x,
            "center_y": self.center_y,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


def _extract_text_from_layout(
    layout: documentai.Document.Page.Layout,
    full_text: str,
) -> str:
    """Extract the text substring that a layout element refers to."""
    text = ""
    for segment in layout.text_anchor.text_segments:
        start = int(segment.start_index)
        end = int(segment.end_index)
        text += full_text[start:end]
    return text.strip()


def _normalized_box_to_pixels(
    vertices,
    screen_width: int,
    screen_height: int,
) -> tuple[int, int, int, int]:
    """Convert normalised vertices (0.0-1.0) to pixel coordinates.

    Returns (x, y, width, height) in pixels.
    """
    xs = [v.x for v in vertices]
    ys = [v.y for v in vertices]

    x_min = int(min(xs) * screen_width)
    y_min = int(min(ys) * screen_height)
    x_max = int(max(xs) * screen_width)
    y_max = int(max(ys) * screen_height)

    return x_min, y_min, x_max - x_min, y_max - y_min


def _classify_element(text: str, width: int, height: int) -> str:
    """Simple heuristic to classify a UI element type."""
    stripped = text.strip()

    # Single character or short operator — likely a button
    if len(stripped) <= 3 and stripped in {
        "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
        "+", "-", "×", "÷", "=", ".", "%", "±", "√",
        "*", "/", "C", "CE", "⌫", "MC", "MR", "M+", "M-", "MS",
    }:
        return "button"

    # Longer numeric string — likely the display
    if stripped.replace(",", "").replace(".", "").replace("-", "").isdigit():
        if width > 100:
            return "display"
        return "button"

    # Everything else is a label
    return "label"


def preprocess_ocr(
    document: documentai.Document,
    screen_width: int,
    screen_height: int,
    min_confidence: float = 0.3,
    min_text_length: int = 1,
) -> list[UIElement]:
    """Convert a Document AI response into a clean list of ``UIElement`` objects.

    Processing steps:
      1. Iterate over every *block* on each page.
      2. Convert normalised bounding boxes → pixel coordinates.
      3. Filter out low-confidence or empty detections.
      4. Classify each element (button / display / label).

    Args:
        document: The Document AI proto returned by ``GoogleOCRService``.
        screen_width: Screen width in pixels (for coordinate conversion).
        screen_height: Screen height in pixels.
        min_confidence: Drop elements below this confidence score.
        min_text_length: Drop elements with text shorter than this.

    Returns:
        Sorted list of ``UIElement`` instances (top-to-bottom, left-to-right).
    """
    elements: list[UIElement] = []

    for page in document.pages:
        # Process blocks (highest-level grouping)
        for block in page.blocks:
            text = _extract_text_from_layout(block.layout, document.text)

            if len(text) < min_text_length:
                continue

            confidence = block.layout.confidence
            if confidence < min_confidence:
                continue

            # Prefer normalised vertices; fall back to regular vertices
            vertices = (
                block.layout.bounding_poly.normalized_vertices
                or block.layout.bounding_poly.vertices
            )
            if not vertices:
                continue

            x, y, w, h = _normalized_box_to_pixels(
                vertices, screen_width, screen_height,
            )

            # Skip tiny artefacts
            if w < 5 or h < 5:
                continue

            element_type = _classify_element(text, w, h)

            elements.append(UIElement(
                text=text,
                center_x=x + w // 2,
                center_y=y + h // 2,
                x=x,
                y=y,
                width=w,
                height=h,
                confidence=confidence,
                element_type=element_type,
            ))

    # Sort: top→bottom, then left→right
    elements.sort(key=lambda e: (e.y, e.x))

    log.info(
        "Preprocessed %d UI elements (buttons=%d, displays=%d, labels=%d)",
        len(elements),
        sum(1 for e in elements if e.element_type == "button"),
        sum(1 for e in elements if e.element_type == "display"),
        sum(1 for e in elements if e.element_type == "label"),
    )
    return elements


def format_elements_for_llm(elements: list[UIElement]) -> str:
    """Format UI elements as a human-readable string for the LLM.

    Example output::

        UI Elements currently visible:
        [button] "5" at (320, 450) — click target: (320, 450)
        [display] "42" at (300, 120) — click target: (300, 120)
    """
    if not elements:
        return "No UI elements detected on screen."

    lines = ["UI Elements currently visible on screen:"]
    for elem in elements:
        lines.append(
            f'  [{elem.element_type}] "{elem.text}" '
            f"at ({elem.center_x}, {elem.center_y}) "
            f"— size {elem.width}×{elem.height}"
        )
    return "\n".join(lines)
