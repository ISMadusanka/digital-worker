"""
Windows-specific helper utilities.

Small, dependency-light helpers for resolving common Windows paths and the
current foreground window. Used by tools and prompts so the agent always knows
the *real* user profile paths instead of guessing ``<username>``.
"""

from __future__ import annotations

import os
from pathlib import Path

from utils.logger import get_logger

log = get_logger(__name__)


def username() -> str:
    """Return the current Windows username."""
    return os.environ.get("USERNAME") or os.environ.get("USER") or "user"


def user_profile() -> Path:
    """Return the user profile directory, e.g. C:\\Users\\<name>."""
    profile = os.environ.get("USERPROFILE")
    if profile:
        return Path(profile)
    return Path.home()


def known_folder(name: str) -> Path:
    """Resolve a well-known user folder by friendly name.

    Supported: desktop, documents, downloads, pictures, videos, music.
    Falls back to ``<user profile>/<Name>`` if the folder can't be resolved.
    """
    key = name.strip().lower()
    base = user_profile()
    mapping = {
        "desktop": base / "Desktop",
        "documents": base / "Documents",
        "downloads": base / "Downloads",
        "pictures": base / "Pictures",
        "videos": base / "Videos",
        "music": base / "Music",
    }
    return mapping.get(key, base / name.strip().title())


def resolve_path(path: str) -> Path:
    """Resolve a user-supplied path that may reference a known folder.

    Accepts inputs like ``"desktop/MyFolder"``, ``"~/Documents/x"``, environment
    variables (``%USERPROFILE%``), or absolute paths, and returns an absolute
    ``Path``.
    """
    raw = path.strip().strip('"').strip("'")
    # Expand environment variables (%USERPROFILE%) and ~ first.
    raw = os.path.expandvars(os.path.expanduser(raw))

    p = Path(raw)
    if p.is_absolute():
        return p

    # Treat a leading known-folder token (desktop, documents, ...) specially.
    parts = p.parts
    if parts:
        first = parts[0].lower()
        if first in ("desktop", "documents", "downloads", "pictures", "videos", "music"):
            return known_folder(first).joinpath(*parts[1:])

    # Otherwise resolve relative to the user profile (a sensible default).
    return user_profile() / p


def foreground_window_title() -> str:
    """Return the title of the current foreground window (best effort)."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value
    except Exception as e:  # pragma: no cover - platform/edge cases
        log.debug("Could not read foreground window title: %s", e)
        return ""
