"""Deterministic unit tests for logging and telemetry utilities."""

from __future__ import annotations

import logging
import sys
from unittest.mock import MagicMock, patch

import pytest

import src.utils.telemetry as telemetry_module
from src.utils.logger import get_logger
from src.utils.telemetry import (
    flush_langfuse,
    get_langfuse_callback,
    is_langfuse_available,
    log_langfuse_score,
    shutdown_telemetry,
)


@pytest.fixture(autouse=True)
def reset_telemetry_state() -> None:
    """Reset telemetry globals before each test."""
    telemetry_module._telemetry_available = None
    telemetry_module._client_instance = None
    telemetry_module._client_broken = False


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


def test_is_langfuse_available_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify is_langfuse_available returns False when LANGFUSE_PUBLIC_KEY is missing."""
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    assert is_langfuse_available(force_check=True) is False


def test_is_langfuse_available_cloud_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify is_langfuse_available respects LANGFUSE_BASE_URL for cloud deployments."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-cloud")
    monkeypatch.setenv("LANGFUSE_BASE_URL", "https://cloud.langfuse.com")
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        assert is_langfuse_available(force_check=True) is True
        # Verify it targeted the cloud endpoint, not localhost
        req_arg = mock_urlopen.call_args[0][0]
        assert req_arg.full_url == "https://cloud.langfuse.com/api/public/health"


def test_is_langfuse_available_probe_success(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify is_langfuse_available returns True on HTTP 200 health check response."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-mock")
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert is_langfuse_available(force_check=True) is True


def test_is_langfuse_available_probe_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify is_langfuse_available returns False on connection error."""
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-mock")
    with patch(
        "urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")
    ):
        assert is_langfuse_available(force_check=True) is False


def test_get_langfuse_callback_success() -> None:
    """Verify get_langfuse_callback successfully constructs CallbackHandler when reachable."""
    mock_handler_instance = MagicMock()
    with (
        patch("src.utils.telemetry.is_langfuse_available", return_value=True),
        patch("langfuse.langchain.CallbackHandler", return_value=mock_handler_instance),
    ):
        handler = get_langfuse_callback()
        assert handler is mock_handler_instance


def test_get_langfuse_callback_unreachable() -> None:
    """Verify get_langfuse_callback returns None when server is unreachable."""
    with patch("src.utils.telemetry.is_langfuse_available", return_value=False):
        assert get_langfuse_callback() is None


def test_get_langfuse_callback_graceful_failure(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Verify get_langfuse_callback catches initialization errors, logs a warning, and returns None."""
    with (
        patch("src.utils.telemetry.is_langfuse_available", return_value=True),
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


def test_log_langfuse_score_and_circuit_breaker() -> None:
    """Verify log_langfuse_score submits scores and trips circuit breaker on failure."""
    mock_client = MagicMock()
    with patch("src.utils.telemetry.get_telemetry_client", return_value=mock_client):
        # Successful score
        assert log_langfuse_score("trace-123", "score_name", 1.0) is True
        mock_client.create_score.assert_called_once_with(
            trace_id="trace-123", name="score_name", value=1.0, comment=None
        )

        # Trigger failure -> circuit breaker trips
        mock_client.create_score.side_effect = ConnectionError("Refused")
        assert log_langfuse_score("trace-123", "score_name", 0.0) is False

        # Subsequent call is rejected by circuit breaker without network call
        assert log_langfuse_score("trace-123", "score_name", 1.0) is False


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


def test_shutdown_telemetry() -> None:
    """Verify shutdown_telemetry calls client.shutdown() and clears singleton."""
    mock_client = MagicMock()
    telemetry_module._client_instance = mock_client
    shutdown_telemetry()
    mock_client.shutdown.assert_called_once()
    assert telemetry_module._client_instance is None
