"""
CLI Entry Point for the Digital Worker application.
"""

import sys
import traceback

from config.settings import validate_config
from ui.app import main as ui_main
from utils.logger import get_logger

log = get_logger("main")

def main() -> None:
    # Ensure environment variables are loaded
    validate_config()

    try:
        ui_main()
    except Exception as e:
        log.error("Failed to start UI: %s", e)
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
