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

    # Known calculator button labels — includes common OCR variants.
    # 'x' and 'X' are how OCR often reads the multiplication sign '×'.
    _BUTTON_LABELS = {
        # Digits
        "0", "1", "2", "3", "4", "5", "6", "7", "8", "9",
        # Basic operators (Unicode and ASCII variants)
        "+", "-", "×", "÷", "=", ".", "%", "±", "√",
        "*", "/", "x", "X",
        # Parentheses and power
        "(", ")", "^",
        # Clear / delete
        "C", "CE", "AC", "⌫", "DEL",
        # Memory
        "MC", "MR", "M+", "M-", "MS",
        # Scientific extras OCR might pick up
        "1/x", "x²", "x2", "π", "e",
        "sin", "cos", "tan", "log", "ln",
        "Exp", "Mod", "n!",
    }

    if stripped in _BUTTON_LABELS:
        return "button"

    # Longer numeric string — likely the display
    if stripped.replace(",", "").replace(".", "").replace("-", "").isdigit():
        if width > 100:
            return "display"
        return "button"

    # Short text that looks like a single UI control
    if len(stripped) <= 3:
        return "button"

    # Everything else is a label
    return "label"


def _extract_elements_from_layout_items(
    items,
    full_text: str,
    screen_width: int,
    screen_height: int,
    min_confidence: float,
    min_text_length: int,
) -> list[UIElement]:
    """Shared helper: convert a list of Document AI layout items into UIElements."""
    elements: list[UIElement] = []

    for item in items:
        text = _extract_text_from_layout(item.layout, full_text)

        if len(text) < min_text_length:
            continue

        confidence = item.layout.confidence
        if confidence < min_confidence:
            continue

        vertices = (
            item.layout.bounding_poly.normalized_vertices
            or item.layout.bounding_poly.vertices
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

    return elements


def _deduplicate_elements(
    elements: list[UIElement],
    iou_threshold: float = 0.3,
) -> list[UIElement]:
    """Remove duplicate elements that refer to the same physical UI widget.

    Document AI sometimes returns multiple overlapping tokens for the same
    button (e.g. two '5' entries at nearly identical coordinates).  When the
    LLM sees both, it may click the button twice.

    Two elements are considered duplicates when they share the **same text**
    AND their bounding boxes overlap by at least *iou_threshold* (Intersection
    over Union).  In each duplicate group only the element with the highest
    confidence is kept.
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

    # Greedy de-duplication: sort by confidence (desc) so the best element
    # in each cluster is kept.
    sorted_elems = sorted(elements, key=lambda e: e.confidence, reverse=True)
    kept: list[UIElement] = []

    for elem in sorted_elems:
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
    document: documentai.Document,
    screen_width: int,
    screen_height: int,
    min_confidence: float = 0.3,
    min_text_length: int = 1,
) -> list[UIElement]:
    """Convert a Document AI response into a clean list of ``UIElement`` objects.

    Processing strategy:
      - Use **tokens** (word-level) as the primary source so that each
        individual calculator button gets its own bounding box and click
        coordinates.  Block-level extraction merges adjacent buttons
        (e.g. "× ÷ - +") into a single element whose center falls on
        dead space between buttons.
      - Fall back to **blocks** only when a page has no tokens at all.

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
        # Collect tokens from all levels.  Document AI exposes
        # page.tokens on newer processor versions.  For older ones
        # that only populate paragraphs/lines/words, walk the tree.
        tokens = getattr(page, "tokens", [])

        if tokens:
            # Finest granularity available — one element per visual token.
            elements.extend(
                _extract_elements_from_layout_items(
                    tokens, document.text,
                    screen_width, screen_height,
                    min_confidence, min_text_length,
                )
            )
        else:
            # Try symbols → words → lines → paragraphs → blocks,
            # preferring the finest granularity that has data.
            finest = None
            for attr in ("symbols", "words", "lines", "paragraphs", "blocks"):
                candidates = getattr(page, attr, None)
                if candidates:
                    finest = candidates
                    break

            if finest is not None:
                elements.extend(
                    _extract_elements_from_layout_items(
                        finest, document.text,
                        screen_width, screen_height,
                        min_confidence, min_text_length,
                    )
                )

    # De-duplicate overlapping elements (e.g. two OCR tokens for the same "5" button)
    elements = _deduplicate_elements(elements)

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
