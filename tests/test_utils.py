"""Deterministic unit tests for logging and telemetry utilities."""

from __future__ import annotations

import logging
import sys
from unittest.mock import MagicMock, patch

import pytest

from src.utils.logger import get_logger
from src.utils.telemetry import flush_langfuse, get_langfuse_callback


def test_get_logger_defaults() -> None:
    """Verify get_logger default parameters and handler configuration."""
    logger_name = "mas.test_default"
    log = get_logger(name=logger_name)

    assert log.name == logger_name
    assert log.level == logging.INFO
    assert len(log.handlers) == 1

    handler = log.handlers[0]
    assert isinstance(handler, logging.StreamHandler)
    assert handler.stream is sys.stdout
    assert handler.formatter is not None
    assert handler.formatter._fmt is not None
    assert "%(asctime)s" in handler.formatter._fmt
    assert "%(levelname)s" in handler.formatter._fmt


def test_get_logger_custom_level() -> None:
    """Verify get_logger respects custom log levels."""
    logger_name = "mas.test_custom_level"
    log = get_logger(name=logger_name, level=logging.DEBUG)

    assert log.name == logger_name
    assert log.level == logging.DEBUG


def test_get_logger_idempotent_handlers() -> None:
    """Verify subsequent calls to get_logger do not attach duplicate handlers."""
    logger_name = "mas.test_idempotent"
    log1 = get_logger(name=logger_name)
    initial_count = len(log1.handlers)

    log2 = get_logger(name=logger_name)
    assert len(log2.handlers) == initial_count == 1
    assert log1 is log2


def test_get_langfuse_callback_success() -> None:
    """Verify get_langfuse_callback successfully constructs CallbackHandler when available."""
    mock_handler_instance = MagicMock()
    with patch(
        "langfuse.langchain.CallbackHandler", return_value=mock_handler_instance
    ):
        handler = get_langfuse_callback()
        assert handler is mock_handler_instance


def test_get_langfuse_callback_graceful_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify get_langfuse_callback catches initialization errors, logs a warning, and returns None."""
    with (
        patch(
            "langfuse.langchain.CallbackHandler",
            side_effect=RuntimeError("Langfuse init failed"),
        ),
        caplog.at_level(logging.WARNING, logger="mas.telemetry"),
    ):
        handler = get_langfuse_callback()

    assert handler is None
    assert (
        "Could not initialize Langfuse CallbackHandler (Langfuse init failed)"
        in caplog.text
    )


def test_flush_langfuse_success() -> None:
    """Verify flush_langfuse calls client.flush() on the underlying Langfuse client."""
    mock_client = MagicMock()
    with patch("langfuse.get_client", return_value=mock_client) as mock_get_client:
        flush_langfuse()
        mock_get_client.assert_called_once()
        mock_client.flush.assert_called_once()


def test_flush_langfuse_graceful_failure(caplog: pytest.LogCaptureFixture) -> None:
    """Verify flush_langfuse catches client exceptions and logs an informative warning."""
    with (
        patch(
            "langfuse.get_client", side_effect=ConnectionError("Server unreachable")
        ) as mock_get_client,
        caplog.at_level(logging.WARNING, logger="mas.telemetry"),
    ):
        flush_langfuse()
        mock_get_client.assert_called_once()

    assert "Failed to flush Langfuse client: Server unreachable" in caplog.text
