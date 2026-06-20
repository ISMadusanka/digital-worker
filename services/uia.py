"""
Native Windows UI Automation (UIA) perception service.

Walks the Windows accessibility tree to discover on-screen UI elements with
exact names, control types, and bounding rectangles — straight from the OS,
with no GPU server or OCR required. This is far more reliable than detecting
elements from pixels, because the coordinates and labels are authoritative.

Used as the default perception backend; OmniParser remains available as a
fallback for apps that expose a poor accessibility tree (e.g. some games or
custom-rendered canvases).
"""

from __future__ import annotations

from typing import Optional

from config import settings
from services.preprocessor import UIElement
from utils.logger import get_logger

log = get_logger(__name__)


# Control types worth surfacing to the agent as actionable / informative.
# Mapped to the lightweight element_type vocabulary used elsewhere.
_TYPE_MAP = {
    "ButtonControl": "button",
    "SplitButtonControl": "button",
    "HyperlinkControl": "link",
    "EditControl": "input",
    "ComboBoxControl": "input",
    "DocumentControl": "input",
    "CheckBoxControl": "checkbox",
    "RadioButtonControl": "radio",
    "TabItemControl": "tab",
    "ListItemControl": "listitem",
    "MenuItemControl": "menuitem",
    "TreeItemControl": "treeitem",
    "TextControl": "label",
    "ImageControl": "icon",
}

# Types we never bother reporting (pure containers add noise without targets).
_SKIP_TYPES = {
    "PaneControl",
    "WindowControl",
    "GroupControl",
    "CustomControl",
    "ToolBarControl",
    "TitleBarControl",
    "ScrollBarControl",
    "SeparatorControl",
    "ThumbControl",
}


class UIAutomationService:
    """Reads on-screen elements via the Windows UI Automation tree."""

    def __init__(self) -> None:
        self._auto = None
        try:
            import uiautomation as auto  # noqa: WPS433 (lazy import; Windows only)

            self._auto = auto
            # Keep the library quiet and snappy.
            auto.SetGlobalSearchTimeout(2)
            log.info("UI Automation service ready (native Windows accessibility tree)")
        except Exception as e:  # pragma: no cover - import/platform failure
            log.error("uiautomation unavailable — UIA perception disabled: %s", e)

    @property
    def available(self) -> bool:
        return self._auto is not None

    # ------------------------------------------------------------------
    # Element discovery
    # ------------------------------------------------------------------
    def get_elements(self, screen_width: int, screen_height: int) -> list[UIElement]:
        """Walk the accessibility tree and return visible, useful UI elements.

        The walk is bounded by ``UIA_MAX_NODES`` / ``UIA_MAX_DEPTH`` /
        ``UIA_MAX_ELEMENTS`` so perception stays fast even on heavy apps like
        browsers. Results are sorted top→bottom, left→right.
        """
        if not self.available:
            return []

        auto = self._auto
        elements: list[UIElement] = []
        seen: set[tuple[str, int, int]] = set()
        nodes_visited = 0

        try:
            root = auto.GetRootControl()
        except Exception as e:
            log.error("Failed to get UIA root control: %s", e)
            return []

        # DFS over the tree. We start from the desktop root so that the taskbar,
        # Start menu, open dialogs/menus, and the foreground app are all covered.
        # Each stack entry carries the label of its top-level window (depth-1
        # ancestor) so every element can be grouped under the right window.
        stack: list[tuple[object, int, str]] = [(root, 0, "")]

        while stack and len(elements) < settings.UIA_MAX_ELEMENTS and nodes_visited < settings.UIA_MAX_NODES:
            ctrl, depth, win_name = stack.pop()
            nodes_visited += 1

            # Fetch the bounding rect once and reuse it (each property is a COM
            # round-trip, so we minimise them).
            try:
                rect = ctrl.BoundingRectangle
                rx, ry = int(rect.left), int(rect.top)
                rw, rh = int(rect.right - rect.left), int(rect.bottom - rect.top)
            except Exception:
                rx = ry = rw = rh = 0

            on_screen = (
                rw > 0 and rh > 0
                and rx < screen_width and ry < screen_height
                and rx + rw > 0 and ry + rh > 0
            )

            # Prune: an off-screen / zero-size subtree has no visible descendants,
            # so don't walk into it. This skips minimised/hidden windows entirely
            # and is the main speedup. (depth 0 = desktop root, always descend.)
            if depth > 0 and not on_screen:
                continue

            # At depth 1 the node IS a top-level window — its name labels the
            # whole subtree below it.
            this_window = win_name
            if depth == 1:
                try:
                    this_window = (ctrl.Name or "").strip() or ctrl.ControlTypeName
                except Exception:
                    this_window = win_name

            if depth < settings.UIA_MAX_DEPTH:
                try:
                    for child in ctrl.GetChildren():
                        stack.append((child, depth + 1, this_window))
                except Exception:
                    pass

            if depth == 0:
                continue  # skip the desktop root itself

            element = self._to_element(ctrl, screen_width, screen_height, (rx, ry, rw, rh))
            if element is None:
                continue

            element.window = this_window or ""

            # De-duplicate identical text at the same location.
            key = (element.text, element.center_x // 5, element.center_y // 5)
            if key in seen:
                continue
            seen.add(key)
            elements.append(element)

        # Mark the element that currently has keyboard focus (one COM call) so
        # the agent knows where typing will go.
        try:
            focused = auto.GetFocusedControl()
            fr = focused.BoundingRectangle
            fcx, fcy = (fr.left + fr.right) // 2, (fr.top + fr.bottom) // 2
            for el in elements:
                if abs(el.center_x - fcx) <= 3 and abs(el.center_y - fcy) <= 3:
                    el.state = f"{el.state},focused" if el.state else "focused"
                    break
        except Exception:
            pass

        elements.sort(key=lambda e: (e.y, e.x))
        log.info(
            "UIA perception: %d elements (visited %d nodes)",
            len(elements),
            nodes_visited,
        )
        return elements

    def _to_element(
        self,
        ctrl,
        screen_width: int,
        screen_height: int,
        rect: tuple[int, int, int, int],
    ) -> Optional[UIElement]:
        """Convert a UIA control into a ``UIElement`` (or None if not useful).

        ``rect`` is the already-fetched (x, y, w, h) bounding box, so we avoid
        re-querying it over COM.
        """
        x, y, w, h = rect

        # Reject empty / tiny boxes.
        if w < 5 or h < 5:
            return None

        # Reject near-full-screen boxes — these are background containers
        # (desktop, root panes), not actionable targets, and their giant
        # annotation boxes just add noise.
        if (w * h) >= 0.85 * (screen_width * screen_height):
            return None

        try:
            type_name = ctrl.ControlTypeName
        except Exception:
            return None

        if type_name in _SKIP_TYPES:
            return None

        try:
            name = (ctrl.Name or "").strip()
        except Exception:
            name = ""

        element_type = _TYPE_MAP.get(type_name, "element")

        # Inputs/buttons are worth reporting even without a name (e.g. an empty
        # address bar); plain labels/icons without text are just noise.
        if not name and element_type in ("label", "icon", "element"):
            return None

        # Clamp the box to the screen so annotations don't overflow.
        x = max(0, x)
        y = max(0, y)
        w = min(w, screen_width - x)
        h = min(h, screen_height - y)

        value, state = self._read_value_and_state(ctrl, element_type)

        return UIElement(
            text=name or f"<{element_type}>",
            center_x=x + w // 2,
            center_y=y + h // 2,
            x=x,
            y=y,
            width=w,
            height=h,
            confidence=1.0,
            element_type=element_type,
            value=value,
            state=state,
        )

    @staticmethod
    def _read_value_and_state(ctrl, element_type: str) -> tuple[str, str]:
        """Extract the control's value and interaction state via UIA patterns.

        Pattern queries are COM round-trips, so we only run the ones relevant to
        each control type to keep the tree walk fast.
        """
        value = ""
        states: list[str] = []
        interactive = element_type in (
            "button", "input", "checkbox", "radio", "menuitem", "link", "tab",
            "listitem", "treeitem",
        )

        if interactive:
            try:
                if ctrl.IsEnabled is False:
                    states.append("disabled")
            except Exception:
                pass

        if element_type == "input":
            try:
                vp = ctrl.GetValuePattern()
                v = (vp.Value or "").strip() if vp else ""
                if v:
                    value = v if len(v) <= 80 else v[:77] + "..."
            except Exception:
                pass

        elif element_type in ("checkbox", "radio"):
            try:
                tp = ctrl.GetTogglePattern()
                ts = tp.ToggleState if tp else None
                if ts == 1:
                    states.append("checked")
                elif ts == 2:
                    states.append("indeterminate")
                else:
                    states.append("unchecked")
            except Exception:
                pass

        elif element_type in ("listitem", "tab", "treeitem"):
            try:
                sp = ctrl.GetSelectionItemPattern()
                if sp and sp.IsSelected:
                    states.append("selected")
            except Exception:
                pass

        return value, ",".join(states)

    # ------------------------------------------------------------------
    # Content extraction (for "grab the text on this page" style tasks)
    # ------------------------------------------------------------------
    def get_active_window_text(self, max_chars: int = 6000) -> str:
        """Extract readable text from the current foreground window.

        Collects Text / Document / Hyperlink / ListItem names from the active
        window's subtree. This lets the agent *read* content (e.g. news
        headlines in a browser) instead of trying to OCR it.
        """
        if not self.available:
            return ""

        auto = self._auto
        try:
            window = auto.GetForegroundControl()
        except Exception as e:
            log.error("Failed to get foreground control: %s", e)
            return ""

        wanted = {"TextControl", "DocumentControl", "HyperlinkControl", "ListItemControl"}
        chunks: list[str] = []
        seen: set[str] = set()
        nodes_visited = 0
        stack: list[object] = [window]

        while stack and nodes_visited < settings.UIA_MAX_NODES * 2:
            ctrl = stack.pop()
            nodes_visited += 1
            try:
                stack.extend(ctrl.GetChildren())
            except Exception:
                pass

            try:
                if ctrl.ControlTypeName not in wanted:
                    continue
                text = (ctrl.Name or "").strip()
            except Exception:
                continue

            if not text or len(text) < 2 or text in seen:
                continue
            seen.add(text)
            chunks.append(text)

            if sum(len(c) for c in chunks) >= max_chars:
                break

        result = "\n".join(chunks)
        log.info("UIA extracted %d chars of window text", len(result))
        return result[:max_chars]
