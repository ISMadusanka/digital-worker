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
# Google Cloud Document AI
# ---------------------------------------------------------------------------
GOOGLE_CLOUD_PROJECT_ID: str = os.getenv("GOOGLE_CLOUD_PROJECT_ID", "")
GOOGLE_CLOUD_LOCATION: str = os.getenv("GOOGLE_CLOUD_LOCATION", "us")
GOOGLE_DOCUMENT_AI_PROCESSOR_ID: str = os.getenv("GOOGLE_DOCUMENT_AI_PROCESSOR_ID", "")
GOOGLE_APPLICATION_CREDENTIALS: str = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")

# Set the credentials path for the Google client library
if GOOGLE_APPLICATION_CREDENTIALS:
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = GOOGLE_APPLICATION_CREDENTIALS

# ---------------------------------------------------------------------------
# Worker Behavior
# ---------------------------------------------------------------------------
MAX_ACTION_RETRIES: int = int(os.getenv("MAX_ACTION_RETRIES", "3"))
MAX_AGENT_ITERATIONS: int = int(os.getenv("MAX_AGENT_ITERATIONS", "20"))
SCREENSHOT_DELAY: float = float(os.getenv("SCREENSHOT_DELAY", "0.5"))
ACTION_PAUSE: float = float(os.getenv("ACTION_PAUSE", "0.3"))
MOUSE_MOVE_DURATION: float = float(os.getenv("MOUSE_MOVE_DURATION", "0.3"))

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
    if not GOOGLE_CLOUD_PROJECT_ID:
        errors.append("GOOGLE_CLOUD_PROJECT_ID is not set in .env")
    if not GOOGLE_DOCUMENT_AI_PROCESSOR_ID:
        errors.append("GOOGLE_DOCUMENT_AI_PROCESSOR_ID is not set in .env")
    if not GOOGLE_APPLICATION_CREDENTIALS:
        errors.append("GOOGLE_APPLICATION_CREDENTIALS is not set in .env")

    if errors:
        print("\n❌  Configuration errors:")
        for e in errors:
            print(f"   • {e}")
        print(f"\n   Copy .env.example → .env and fill in the values.")
        print(f"   Path: {_env_path}\n")
        sys.exit(1)
