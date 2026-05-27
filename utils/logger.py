"""
Structured logging configuration for the Digital Worker.
"""

import logging
import sys
from config.settings import LOG_LEVEL


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger instance.

    Args:
        name: Logger name — typically ``__name__`` from the calling module.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-7s | %(name)-28s | %(message)s",
            datefmt="%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))
    return logger
