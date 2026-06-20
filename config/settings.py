"""
Application configuration — loads .env and exposes typed settings.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_project_root = Path(__file__).resolve().parent.parent
_env_path = _project_root / ".env"
load_dotenv(dotenv_path=_env_path)


def _as_bool(value: str) -> bool:
    return value.strip().lower() in ("true", "1", "yes", "on")


# ---------------------------------------------------------------------------
# OpenAI  (gpt-4o is multimodal — required for vision perception)
# ---------------------------------------------------------------------------
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

# ---------------------------------------------------------------------------
# Perception
# ---------------------------------------------------------------------------
# Which backend produces the list of on-screen UI elements:
#   "uia"        — native Windows UI Automation accessibility tree only (no GPU)
#   "omniparser" — local OmniParser GPU server (requires OMNIPARSER_API_URL up)
#   "hybrid"     — UIA first, fall back to OmniParser only if UIA finds nothing
#                  (default). The OmniParser screenshot goes to the OmniParser
#                  server, never to the LLM.
PERCEPTION_BACKEND: str = os.getenv("PERCEPTION_BACKEND", "hybrid").lower()

# Perception is text-only by default: the agent reasons over the structured UI
# Automation tree, NOT a screenshot. Set USE_VISION=true to also attach an
# annotated screenshot for multimodal models.
USE_VISION: bool = _as_bool(os.getenv("USE_VISION", "false"))
# Draw numbered "Set-of-Mark" boxes on the screenshot (only relevant if vision on).
SET_OF_MARK: bool = _as_bool(os.getenv("SET_OF_MARK", "true"))
# Downscale + JPEG-compress the screenshot before sending it to the model. Far
# fewer image tiles => much faster/cheaper vision calls. Click accuracy is
# unaffected because actions resolve via element IDs (full-resolution coords);
# raw fallback coordinates are scaled back up automatically. 0 = no downscale.
VISION_MAX_WIDTH: int = int(os.getenv("VISION_MAX_WIDTH", "1280"))
VISION_JPEG_QUALITY: int = int(os.getenv("VISION_JPEG_QUALITY", "70"))

# UI Automation tuning (bounds the tree walk so perception stays fast).
UIA_MAX_ELEMENTS: int = int(os.getenv("UIA_MAX_ELEMENTS", "150"))
UIA_MAX_NODES: int = int(os.getenv("UIA_MAX_NODES", "3000"))
UIA_MAX_DEPTH: int = int(os.getenv("UIA_MAX_DEPTH", "30"))

# ---------------------------------------------------------------------------
# OmniParser (optional fallback backend)
# ---------------------------------------------------------------------------
OMNIPARSER_API_URL: str = os.getenv("OMNIPARSER_API_URL", "http://localhost:8000/process")
OMNIPARSER_BOX_THRESHOLD: float = float(os.getenv("OMNIPARSER_BOX_THRESHOLD", "0.05"))
OMNIPARSER_IOU_THRESHOLD: float = float(os.getenv("OMNIPARSER_IOU_THRESHOLD", "0.1"))
OMNIPARSER_USE_PADDLEOCR: bool = _as_bool(os.getenv("OMNIPARSER_USE_PADDLEOCR", "true"))
OMNIPARSER_IMGSZ: int = int(os.getenv("OMNIPARSER_IMGSZ", "640"))

# ---------------------------------------------------------------------------
# Worker Behavior
# ---------------------------------------------------------------------------
# Complex multi-app tasks (e.g. "create a folder + summarise today's news") need
# many actions, so the iteration budget is generous by default.
MAX_ACTION_RETRIES: int = int(os.getenv("MAX_ACTION_RETRIES", "4"))
MAX_AGENT_ITERATIONS: int = int(os.getenv("MAX_AGENT_ITERATIONS", "80"))
SCREENSHOT_DELAY: float = float(os.getenv("SCREENSHOT_DELAY", "0.3"))
ACTION_PAUSE: float = float(os.getenv("ACTION_PAUSE", "0.2"))
MOUSE_MOVE_DURATION: float = float(os.getenv("MOUSE_MOVE_DURATION", "0.15"))
# Per-character typing delay. Lower = faster typing (still visibly typed).
TYPING_INTERVAL: float = float(os.getenv("TYPING_INTERVAL", "0.02"))

# Generate a step-by-step plan up front and track progress against it.
USE_PLANNER: bool = _as_bool(os.getenv("USE_PLANNER", "true"))

# Visible-GUI mode (default): the agent produces every artifact by operating the
# real apps the user can watch (File Explorer, Notepad/Word, the browser).
# Set ENABLE_POWER_TOOLS=true to ALSO expose the silent helpers that create
# folders/files/documents and run shell commands directly (faster, not visible).
ENABLE_POWER_TOOLS: bool = _as_bool(os.getenv("ENABLE_POWER_TOOLS", "false"))

# ---------------------------------------------------------------------------
# Per-Action Verification
# ---------------------------------------------------------------------------
# Off by default: blanket verify-then-Ctrl+Z after every action is destructive
# for multi-step GUI tasks (it "undoes" things like opening apps). The model
# now re-observes the fresh screen each iteration and self-corrects instead.
VERIFY_AFTER_ACTION: bool = _as_bool(os.getenv("VERIFY_AFTER_ACTION", "false"))
# Even when verification is on, only undo if this is explicitly enabled.
VERIFY_AUTO_UNDO: bool = _as_bool(os.getenv("VERIFY_AUTO_UNDO", "false"))
VERIFICATION_DELAY: float = float(os.getenv("VERIFICATION_DELAY", "1.0"))

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
SCREENSHOTS_DIR: Path = _project_root / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")


def validate_config() -> None:
    """Check that all required config values are present. Exit with a clear
    message if anything is missing."""
    errors: list[str] = []

    if not OPENAI_API_KEY:
        errors.append("OPENAI_API_KEY is not set in .env")
    if PERCEPTION_BACKEND in ("omniparser", "hybrid") and not OMNIPARSER_API_URL:
        errors.append("OMNIPARSER_API_URL is not set in .env (required for the chosen backend)")

    if errors:
        print("\n[X]  Configuration errors:")
        for e in errors:
            print(f"   - {e}")
        print("\n   Copy .env.example -> .env and fill in the values.")
        print(f"   Path: {_env_path}\n")
        sys.exit(1)
