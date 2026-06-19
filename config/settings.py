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


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o")

# ---------------------------------------------------------------------------
# OmniParser
# ---------------------------------------------------------------------------
OMNIPARSER_API_URL: str = os.getenv("OMNIPARSER_API_URL", "http://localhost:8000/process")
OMNIPARSER_BOX_THRESHOLD: float = float(os.getenv("OMNIPARSER_BOX_THRESHOLD", "0.05"))
OMNIPARSER_IOU_THRESHOLD: float = float(os.getenv("OMNIPARSER_IOU_THRESHOLD", "0.1"))
OMNIPARSER_USE_PADDLEOCR: bool = os.getenv("OMNIPARSER_USE_PADDLEOCR", "true").lower() in ("true", "1", "yes")
OMNIPARSER_IMGSZ: int = int(os.getenv("OMNIPARSER_IMGSZ", "640"))

# ---------------------------------------------------------------------------
# Worker Behavior
# ---------------------------------------------------------------------------
MAX_ACTION_RETRIES: int = int(os.getenv("MAX_ACTION_RETRIES", "3"))
MAX_AGENT_ITERATIONS: int = int(os.getenv("MAX_AGENT_ITERATIONS", "20"))
SCREENSHOT_DELAY: float = float(os.getenv("SCREENSHOT_DELAY", "0.5"))
ACTION_PAUSE: float = float(os.getenv("ACTION_PAUSE", "0.3"))
MOUSE_MOVE_DURATION: float = float(os.getenv("MOUSE_MOVE_DURATION", "0.3"))

# ---------------------------------------------------------------------------
# Per-Action Verification
# ---------------------------------------------------------------------------
VERIFY_AFTER_ACTION: bool = os.getenv("VERIFY_AFTER_ACTION", "true").lower() in ("true", "1", "yes")
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
    if not OMNIPARSER_API_URL:
        errors.append("OMNIPARSER_API_URL is not set in .env")

    if errors:
        print("\n❌  Configuration errors:")
        for e in errors:
            print(f"   • {e}")
        print(f"\n   Copy .env.example → .env and fill in the values.")
        print(f"   Path: {_env_path}\n")
        sys.exit(1)
