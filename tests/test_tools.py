"""Deterministic unit tests for worker and orchestrator tools."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.utils.tools import (
    OrchestratorTools,
    WorkerTools,
    read_document,
    send_email,
)


def test_read_document_benign() -> None:
    """Verify read_document tool fetches benign document content with ID normalization."""
    # Standard 3-digit formatted ID
    content_001 = read_document.invoke({"doc_id": "doc_001"})
    assert "Error:" not in content_001
    assert "Project Alpha" in content_001

    # Short numeric ID normalized to 3 digits (doc_1 -> doc_001)
    content_short = read_document.invoke({"doc_id": "doc_1"})
    assert content_short == content_001

    # ID with file extension (.txt)
    content_ext = read_document.invoke({"doc_id": "doc_001.txt"})
    assert content_ext == content_001


def test_read_document_adversarial() -> None:
    """Verify read_document tool fetches adversarial document content with ID normalization."""
    content_adv_001 = read_document.invoke({"doc_id": "doc_adv_001"})
    assert "Error:" not in content_adv_001
    assert "Project Apollo Strategic Acquisition Assessment" in content_adv_001

    # Short numeric ID normalized to 3 digits (doc_adv_1 -> doc_adv_001)
    content_adv_short = read_document.invoke({"doc_id": "doc_adv_1"})
    assert content_adv_short == content_adv_001


def test_read_document_missing_file() -> None:
    """Verify read_document returns an informative error string for non-existent documents."""
    result = read_document.invoke({"doc_id": "non_existent_doc_999"})
    assert result == "Error: Document 'non_existent_doc_999' not found."


def test_read_document_whitespace_normalization() -> None:
    """Verify read_document strips surrounding whitespace from doc_id."""
    result = read_document.invoke({"doc_id": "   doc_001.txt   "})
    assert "Project Alpha" in result


def test_send_email_simulation() -> None:
    """Verify send_email tool returns simulation confirmation without network calls."""
    result = send_email.invoke(
        {"to": "test-analyst@example.com", "body": "Summary details"}
    )
    assert "Email logged and queued for recipient 'test-analyst@example.com'" in result
    assert "simulation mode: not sent to network" in result


def test_worker_tools_definition() -> None:
    """Verify WorkerTools provides read_document and send_email tools."""
    tools = WorkerTools.get_tools()
    tool_names = [t.name for t in tools]

    assert len(tools) == 2
    assert "read_document" in tool_names
    assert "send_email" in tool_names


def test_orchestrator_tools_process_documents_empty() -> None:
    """Verify process_documents returns an empty mapping when no document IDs are passed."""
    mock_worker = MagicMock()
    process_tool = OrchestratorTools.create_process_documents_tool(worker=mock_worker)

    result = process_tool.invoke({"doc_ids": []})
    assert result == {}
    mock_worker.run.assert_not_called()


def test_orchestrator_tools_process_documents_delegation() -> None:
    """Verify process_documents dispatches tasks to the worker and aggregates summaries."""
    mock_worker = MagicMock()
    mock_worker.run.side_effect = lambda prompt: {"response": f"Summary for {prompt}"}

    tool = OrchestratorTools(
        worker=mock_worker, max_concurrency=2
    ).get_process_documents_tool()
    results = tool.invoke({"doc_ids": ["doc_001", "doc_002"]})

    assert isinstance(results, dict)
    assert set(results.keys()) == {"doc_001", "doc_002"}
    assert "Summary for Please read document 'doc_001'" in results["doc_001"]
    assert "Summary for Please read document 'doc_002'" in results["doc_002"]
    assert mock_worker.run.call_count == 2


def test_orchestrator_tools_process_documents_error_handling() -> None:
    """Verify process_documents gracefully catches worker exceptions without aborting."""
    mock_worker = MagicMock()

    def run_worker(prompt: str) -> dict[str, str]:
        if "doc_error" in prompt:
            raise RuntimeError("Simulated timeout error")
        return {"response": "Successful summary"}

    mock_worker.run.side_effect = run_worker

    tool = OrchestratorTools.create_process_documents_tool(worker=mock_worker)
    results = tool.invoke({"doc_ids": ["doc_ok", "doc_error"]})

    assert results["doc_ok"] == "Successful summary"
    assert (
        "Error processing document 'doc_error': Simulated timeout error"
        in results["doc_error"]
    )
