"""Production logger configuration for MultiAgentSecurity."""

from __future__ import annotations

import logging
import sys


def get_logger(name: str = "mas", level: int = logging.INFO) -> logging.Logger:
    """Configure and return a standard production logger.

    Args:
        name: Hierarchical logger name (e.g., 'mas.agents.orchestrator').
        level: Logging level, defaults to INFO.

    Returns:
        A configured logging.Logger instance.
    """
    logger = logging.getLogger(name)

    # Prevent duplicate handlers if called multiple times
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)

    return logger
