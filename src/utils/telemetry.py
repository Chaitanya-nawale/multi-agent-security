"""Telemetry and Langfuse tracing utilities for MultiAgentSecurity."""

from __future__ import annotations

from typing import Any

from dotenv import load_dotenv

from src.utils.logger import get_logger

load_dotenv()
logger = get_logger("mas.telemetry")


def get_langfuse_callback() -> Any | None:
    """Initialize and return a Langfuse CallbackHandler if configured.

    Returns:
        A langfuse.langchain.CallbackHandler instance if available, otherwise None.
    """
    try:
        from langfuse.langchain import CallbackHandler

        handler = CallbackHandler()
        logger.info("Langfuse CallbackHandler initialized successfully.")
        return handler
    except Exception as exc:
        logger.warning(
            "Could not initialize Langfuse CallbackHandler (%s). Proceeding without Langfuse.",
            exc,
        )
        return None


def flush_langfuse() -> None:
    """Flush any pending background traces to the Langfuse server."""
    try:
        from langfuse import get_client

        client = get_client()
        client.flush()
        logger.info("Langfuse traces flushed successfully.")
    except Exception as exc:
        logger.warning("Failed to flush Langfuse client: %s", exc)
