"""
Preprocessor — converts raw OmniParser output into a clean list of
UI elements suitable for LLM consumption.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Optional

from utils.logger import get_logger

log = get_logger(__name__)


@dataclass
class UIElement:
    """A single UI element extracted from OmniParser."""

    text: str
    center_x: int
    center_y: int
    x: int
    y: int
    width: int
    height: int
    confidence: float = 0.0
    element_type: str = "unknown"  # button | display | label | icon

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


def _parse_icon_entry(line: str) -> Optional[dict]:
    """Parse a single 'icon N: {...}' line from OmniParser's parsed_content_list.

    Returns a dict with keys: type, bbox, interactivity, content, source.
    Returns None if parsing fails.
    """
    # Match pattern: "icon <number>: <dict>"
    match = re.match(r"icon\s+\d+:\s*(.+)", line.strip())
    if not match:
        return None

    dict_str = match.group(1)
    try:
        entry = ast.literal_eval(dict_str)
        if isinstance(entry, dict):
            return entry
    except (ValueError, SyntaxError):
        log.debug("Failed to parse icon entry: %s", line[:80])

    return None


def _classify_omniparser_element(
    content: str,
    element_type: str,
    interactivity: bool,
    width: int,
) -> str:
    """Map OmniParser element attributes to a UI element type.

    OmniParser provides 'type' ('text' or 'icon') and 'interactivity' (bool).
    We map these to our element types:
      - interactivity=True  → 'button'
      - type='text' + not interactive + looks numeric + wide → 'display'
      - type='text' + not interactive → 'label'
      - type='icon' + not interactive → 'icon'
    """
    stripped = content.strip()

    if interactivity:
        return "button"

    if element_type == "text":
        # Check if it looks like a numeric display value
        cleaned = stripped.replace(",", "").replace(".", "").replace("-", "").replace(" ", "")
        if cleaned.isdigit() and width > 100:
            return "display"
        return "label"

    # type='icon' but not interactive
    return "icon"


def _deduplicate_elements(
    elements: list[UIElement],
    iou_threshold: float = 0.3,
) -> list[UIElement]:
    """Remove duplicate elements that refer to the same physical UI widget.

    OmniParser sometimes returns multiple overlapping detections for the same
    element (e.g. from both OCR and YOLO).  When the LLM sees both, it may
    click the button twice.

    Two elements are considered duplicates when they share the **same text**
    AND their bounding boxes overlap by at least *iou_threshold* (Intersection
    over Union).  In each duplicate group only the first element encountered
    is kept (OmniParser entries are already ordered by detection confidence).
    """
    if not elements:
        return elements

    def _iou(a: UIElement, b: UIElement) -> float:
        """Compute Intersection-over-Union for two axis-aligned boxes."""
        ax1, ay1, ax2, ay2 = a.x, a.y, a.x + a.width, a.y + a.height
        bx1, by1, bx2, by2 = b.x, b.y, b.x + b.width, b.y + b.height

        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)

        inter_w = max(0, inter_x2 - inter_x1)
        inter_h = max(0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h

        area_a = a.width * a.height
        area_b = b.width * b.height
        union_area = area_a + area_b - inter_area

        if union_area == 0:
            return 0.0
        return inter_area / union_area

    kept: list[UIElement] = []

    for elem in elements:
        is_dup = False
        for existing in kept:
            if existing.text == elem.text and _iou(existing, elem) >= iou_threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(elem)

    removed = len(elements) - len(kept)
    if removed:
        log.info("Deduplication removed %d overlapping element(s)", removed)

    return kept


def preprocess_ocr(
    omniparser_result: dict,
    screen_width: int,
    screen_height: int,
    min_text_length: int = 1,
) -> list[UIElement]:
    """Convert an OmniParser response into a clean list of ``UIElement`` objects.

    Args:
        omniparser_result: The dict returned by ``OmniParserService.process_image()``.
            Must contain ``parsed_content_list`` (a newline-delimited string of
            icon entries).
        screen_width: Screen width in pixels (for coordinate conversion).
        screen_height: Screen height in pixels.
        min_text_length: Drop elements with content shorter than this.

    Returns:
        Sorted list of ``UIElement`` instances (top-to-bottom, left-to-right).
    """
    elements: list[UIElement] = []

    content_list_str = omniparser_result.get("parsed_content_list", "")
    if not content_list_str:
        log.warning("OmniParser returned empty parsed_content_list")
        return elements

    lines = content_list_str.strip().split("\n")

    for line in lines:
        entry = _parse_icon_entry(line)
        if entry is None:
            continue

        content = entry.get("content", "").strip()
        if len(content) < min_text_length:
            continue

        bbox = entry.get("bbox")
        if not bbox or len(bbox) != 4:
            continue

        # OmniParser bbox is [x_min, y_min, x_max, y_max] normalised (0.0–1.0)
        x_min_norm, y_min_norm, x_max_norm, y_max_norm = bbox

        x = int(x_min_norm * screen_width)
        y = int(y_min_norm * screen_height)
        w = int((x_max_norm - x_min_norm) * screen_width)
        h = int((y_max_norm - y_min_norm) * screen_height)

        # Skip tiny artefacts
        if w < 5 or h < 5:
            continue

        element_type = _classify_omniparser_element(
            content=content,
            element_type=entry.get("type", "text"),
            interactivity=entry.get("interactivity", False),
            width=w,
        )

        elements.append(UIElement(
            text=content,
            center_x=x + w // 2,
            center_y=y + h // 2,
            x=x,
            y=y,
            width=w,
            height=h,
            confidence=1.0,  # OmniParser doesn't expose per-element confidence
            element_type=element_type,
        ))

    # De-duplicate overlapping elements
    elements = _deduplicate_elements(elements)

    # Sort: top→bottom, then left→right
    elements.sort(key=lambda e: (e.y, e.x))

    log.info(
        "Preprocessed %d UI elements (buttons=%d, displays=%d, labels=%d, icons=%d)",
        len(elements),
        sum(1 for e in elements if e.element_type == "button"),
        sum(1 for e in elements if e.element_type == "display"),
        sum(1 for e in elements if e.element_type == "label"),
        sum(1 for e in elements if e.element_type == "icon"),
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
