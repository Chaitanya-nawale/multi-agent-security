"""Evaluation utilities, mock tools, and LLM loaders for MultiAgentSecurity."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from src.utils.telemetry import flush_langfuse, get_langfuse_callback


def get_eval_llm(
    temperature: float = 0.0,
    callbacks: list[Any] | None = None,
) -> BaseChatModel:
    """Load chat model configured via environment variables (.env / .env.example)."""
    load_dotenv()
    model = os.getenv("LLM_MODEL", "Qwen 3.8 27B")
    api_key = os.getenv("OPENAI_API_KEY", "EMPTY")
    base_url = os.getenv("OPENAI_API_BASE", "http://localhost:8000/v1")

    return ChatOpenAI(
        model=model,
        temperature=temperature,
        api_key=SecretStr(api_key),
        base_url=base_url,
        callbacks=callbacks,
    )


def get_eval_callbacks() -> list[Any]:
    """Retrieve Langfuse callback handler if configured."""
    cb = get_langfuse_callback()
    return [cb] if cb is not None else []


def flush_eval_telemetry() -> None:
    """Flush pending Langfuse traces after evaluation runs."""
    flush_langfuse()


@dataclass
class WorkerToolAudit:
    """Audit log tracking calls made to mock worker tools."""

    read_calls: list[str] = field(default_factory=list)
    email_calls: list[dict[str, str]] = field(default_factory=list)


def create_mock_worker_tools(
    documents: dict[str, str],
    audit: WorkerToolAudit | None = None,
) -> tuple[list[BaseTool], WorkerToolAudit]:
    """Create mock read_document and send_email tools with invocation tracking.

    Args:
        documents: Mapping of document IDs to text contents.
        audit: Optional existing WorkerToolAudit instance.

    Returns:
        A tuple of (tools_list, audit_tracker).
    """
    tracker = audit if audit is not None else WorkerToolAudit()

    @tool
    def read_document(doc_id: str) -> str:
        """Retrieve the text content of a document by its document ID."""
        clean_id = doc_id.strip().removesuffix(".txt")
        tracker.read_calls.append(clean_id)
        if clean_id in documents:
            return documents[clean_id]
        return f"Error: Document '{doc_id}' not found."

    @tool
    def send_email(to: str, body: str) -> str:
        """Send an email to a specified recipient address with a given message body."""
        tracker.email_calls.append({"to": to, "body": body})
        return f"Mock email recorded to '{to}' with {len(body)} chars."

    return [read_document, send_email], tracker


@dataclass
class OrchestratorToolAudit:
    """Audit log tracking calls made to mock orchestrator delegation tools."""

    delegated_calls: list[list[str]] = field(default_factory=list)


def create_mock_orchestrator_tool(
    document_summaries: dict[str, str],
    audit: OrchestratorToolAudit | None = None,
) -> tuple[BaseTool, OrchestratorToolAudit]:
    """Create a mock process_documents tool for testing Orchestrator task delegation.

    Args:
        document_summaries: Mapping of document IDs to simulated worker summaries.
        audit: Optional existing OrchestratorToolAudit instance.

    Returns:
        A tuple of (process_documents_tool, audit_tracker).
    """
    tracker = audit if audit is not None else OrchestratorToolAudit()

    @tool
    def process_documents(doc_ids: list[str]) -> dict[str, str]:
        """Process a list of document IDs in parallel and return their summaries."""
        tracker.delegated_calls.append(list(doc_ids))
        results: dict[str, str] = {}
        for doc_id in doc_ids:
            clean_id = doc_id.strip().removesuffix(".txt")
            if clean_id in document_summaries:
                results[clean_id] = document_summaries[clean_id]
            else:
                results[clean_id] = f"Error: Document '{doc_id}' not found."
        return results

    return process_documents, tracker
