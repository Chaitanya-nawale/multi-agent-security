"""Telemetry and Langfuse tracing utilities for MultiAgentSecurity."""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
from typing import Any

from dotenv import load_dotenv

from src.utils.logger import get_logger

load_dotenv()
logger = get_logger("mas.telemetry")

_telemetry_available: bool | None = None
_client_instance: Any | None = None
_client_broken: bool = False


def _get_langfuse_host() -> str:
    """Return the configured Langfuse base URL from environment variables (.env).

    Checks LANGFUSE_BASE_URL, LANGFUSE_HOST, and LANGFUSE_BASEURL in order.
    Honors online cloud URLs (e.g. https://cloud.langfuse.com) as configured.
    If 'localhost' is specified for local setups, normalizes it to '127.0.0.1'
    to prevent macOS IPv6 resolution timeouts.
    """
    host = (
        os.getenv("LANGFUSE_BASE_URL")
        or os.getenv("LANGFUSE_HOST")
        or os.getenv("LANGFUSE_BASEURL")
        or "http://localhost:3000"
    ).rstrip("/")

    # Normalize localhost to IPv4 for local Docker setups on macOS; leave cloud URLs intact
    if "localhost" in host:
        host = host.replace("localhost", "127.0.0.1")

    # Synchronize environment variables so Langfuse SDK and OTel both use the exact same endpoint
    os.environ["LANGFUSE_BASE_URL"] = host
    os.environ["LANGFUSE_HOST"] = host
    return host


def is_langfuse_available(timeout: float = 4.0, force_check: bool = False) -> bool:
    """Perform a fast pre-flight probe to verify if the Langfuse server is responding.

    Args:
        timeout: Maximum seconds to wait for health check response.
        force_check: If True, bypass cached availability status.

    Returns:
        True if the server is accessible and reports healthy, False otherwise.
    """
    global _telemetry_available
    if _telemetry_available is not None and not force_check:
        return _telemetry_available

    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")
    if not public_key:
        logger.debug("Langfuse disabled: LANGFUSE_PUBLIC_KEY not set.")
        _telemetry_available = False
        return False

    base_url = _get_langfuse_host()
    probe_url = f"{base_url}/api/public/health"

    try:
        req = urllib.request.Request(
            probe_url,
            headers={"User-Agent": "MAS-Telemetry-Probe/1.0", "Connection": "close"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                logger.info("Langfuse server verified responsive at %s", probe_url)
                _telemetry_available = True
                return True
            logger.warning(
                "Langfuse server at %s returned non-200 status (%d). Disabling telemetry.",
                probe_url,
                resp.status,
            )
            _telemetry_available = False
            return False
    except Exception as exc:
        logger.warning(
            "Langfuse server at %s is unreachable or unresponsive (%s). Disabling telemetry for this run.",
            base_url,
            exc,
        )
        _telemetry_available = False
        return False


def get_langfuse_callback() -> Any | None:
    """Initialize and return a Langfuse CallbackHandler if configured and reachable.

    Returns:
        A langfuse.langchain.CallbackHandler instance if available, otherwise None.
    """
    _get_langfuse_host()

    if not is_langfuse_available():
        return None

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


def get_telemetry_client(timeout: int = 10) -> Any | None:
    """Return a shared singleton Langfuse client with circuit-breaker protection.

    Args:
        timeout: Network timeout in seconds for client requests.

    Returns:
        Shared Langfuse client instance if available, otherwise None.
    """
    global _client_instance, _client_broken
    if _client_broken:
        return None
    if _client_instance is not None:
        return _client_instance

    base_url = _get_langfuse_host()

    if not is_langfuse_available():
        return None

    try:
        from langfuse import Langfuse

        _client_instance = Langfuse(base_url=base_url, timeout=timeout)
        return _client_instance
    except Exception as exc:
        logger.warning(
            "Could not instantiate Langfuse client (%s). Tripping breaker.", exc
        )
        _client_broken = True
        return None


def log_langfuse_score(
    trace_id: str | None,
    name: str,
    value: float,
    comment: str | None = None,
) -> bool:
    """Safely record a quantitative evaluation score on a Langfuse trace.

    Args:
        trace_id: OpenTelemetry / Langfuse trace identifier.
        name: Name of the evaluation metric.
        value: Numeric score value.
        comment: Optional context description.

    Returns:
        True if score was successfully submitted, False otherwise.
    """
    global _client_broken
    if not trace_id or _client_broken:
        return False

    client = get_telemetry_client()
    if client is None:
        return False

    try:
        client.create_score(
            trace_id=trace_id,
            name=name,
            value=value,
            comment=comment,
        )
        return True
    except Exception as exc:
        logger.warning(
            "Failed to record Langfuse score '%s' (%s). Tripping telemetry circuit breaker.",
            name,
            exc,
        )
        _client_broken = True
        return False


def flush_langfuse() -> None:
    """Flush any pending background traces to the Langfuse server."""
    global _client_instance, _client_broken
    if _client_broken:
        return

    try:
        client = _client_instance
        if client is None:
            from langfuse import get_client

            client = get_client()
        client.flush()
        logger.info("Langfuse traces flushed successfully.")
    except Exception as exc:
        logger.warning("Failed to flush Langfuse client: %s", exc)


def shutdown_telemetry() -> None:
    """Cleanly flush and shut down Langfuse client, releasing all sockets and worker threads."""
    global _client_instance, _client_broken
    if _client_instance is not None:
        try:
            _client_instance.shutdown()
            logger.info("Langfuse client shut down cleanly.")
        except Exception as exc:
            logger.warning("Error during Langfuse client shutdown: %s", exc)
        finally:
            _client_instance = None
