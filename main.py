"""
CLI Entry Point for the Digital Worker application.
"""

import sys
import traceback
import time

from config.settings import validate_config
from core.worker import DigitalWorker
from utils.logger import get_logger


log = get_logger("main")


def print_banner() -> None:
    print(r"""
    =========================================================
      [Digital Worker] - Visual Application Automation
    =========================================================
    Available commands:
      - Type your goal (e.g. "Calculate 25 + 17")
      - Type 'q', 'quit', or 'exit' to stop.
    
    Safety first: Move your mouse to any corner of the screen
    to trigger the Fail-Safe and instantly stop the worker!
    =========================================================
    """)


def main() -> None:
    # Ensure environment variables are loaded
    validate_config()

    print_banner()

    try:
        worker = DigitalWorker()
    except Exception as e:
        log.error("Failed to initialise Digital Worker: %s", e)
        traceback.print_exc()
        sys.exit(1)

    while True:
        try:
            goal = input("\n> What would you like me to do? ")
            
            # add a 5 sec delay before executing the goal
            time.sleep(3)
            goal = goal.strip()
            
            if not goal:
                continue
                
            if goal.lower() in ("q", "quit", "exit"):
                log.info("Exiting...")
                break

            print("\n[Working...]")
            result = worker.execute_goal(goal)
            
            print(f"\n[Result]: {result}\n")
            
        except KeyboardInterrupt:
            print("\nOperation cancelled by user.")
            break
        except Exception as e:
            log.error("An error occurred during execution: %s", e)
            traceback.print_exc()

if __name__ == "__main__":
    main()
