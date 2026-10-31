"""Deterministic unit tests for WorkerAgent and OrchestratorAgent in src/agents.

Note: Non-deterministic LLM generations and multi-agent interaction evaluations
are handled separately in evaluation benchmarks (evals/).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph.state import CompiledStateGraph

from src.agents.orchestrator import (
    OrchestratorAgent,
    OrchestratorState,
    create_orchestrator,
)
from src.agents.worker import (
    WorkerAgent,
    WorkerState,
    create_worker,
)
from src.utils.tools import read_document

# ============================================================================
# Worker Agent Tests
# ============================================================================


def test_worker_state_schema() -> None:
    """Verify WorkerState initializes with default empty messages or supplied messages."""
    empty_state = WorkerState()
    assert empty_state.messages == []

    msg = HumanMessage(content="Analyze document doc_001")
    populated_state = WorkerState(messages=[msg])
    assert len(populated_state.messages) == 1
    assert populated_state.messages[0].content == "Analyze document doc_001"


def test_create_worker_factory() -> None:
    """Verify create_worker factory builds and compiles a LangGraph CompiledStateGraph."""
    mock_llm = MagicMock(spec=BaseChatModel)
    graph = create_worker(llm=mock_llm)

    assert isinstance(graph, CompiledStateGraph)
    mock_llm.bind_tools.assert_called_once()


def test_worker_agent_initialization() -> None:
    """Verify WorkerAgent builds tools, system prompt, and graph without making LLM calls."""
    mock_llm = MagicMock(spec=BaseChatModel)
    worker = WorkerAgent(llm=mock_llm)

    assert worker.llm is mock_llm
    assert worker.system_prompt == WorkerAgent.DEFAULT_SYSTEM_PROMPT
    assert [t.name for t in worker.tools] == ["read_document", "send_email"]
    assert isinstance(worker.graph, CompiledStateGraph)
    mock_llm.bind_tools.assert_called_once()


def test_worker_agent_custom_configuration() -> None:
    """Verify WorkerAgent accepts custom tools and system prompts."""
    mock_llm = MagicMock(spec=BaseChatModel)
    custom_prompt = "Custom Worker Prompt"
    custom_tools = [read_document]

    worker = WorkerAgent(llm=mock_llm, tools=custom_tools, system_prompt=custom_prompt)

    assert worker.system_prompt == custom_prompt
    assert worker.tools == custom_tools
    assert isinstance(worker.graph, CompiledStateGraph)


def test_worker_agent_run_success() -> None:
    """Verify worker.run packages prompt, configures callbacks, and extracts final response."""
    mock_llm = MagicMock(spec=BaseChatModel)
    worker = WorkerAgent(llm=mock_llm)

    expected_response = "Doc 1 Summary: All benchmarks passed."
    mock_invoke_result = {
        "messages": [
            HumanMessage(content="Please review doc_1"),
            AIMessage(content=expected_response),
        ]
    }
    mock_callback = MagicMock()

    with patch.object(
        worker.graph, "invoke", return_value=mock_invoke_result
    ) as mock_invoke:
        result = worker.run(
            task="Please review doc_1",
            callbacks=[mock_callback],
            run_name="test_worker_run",
        )

        assert result["task"] == "Please review doc_1"
        assert result["response"] == expected_response
        assert len(result["messages"]) == 2

        # Verify invoke was called with the task message and config
        mock_invoke.assert_called_once_with(
            {"messages": [HumanMessage(content="Please review doc_1")]},
            config={"run_name": "test_worker_run", "callbacks": [mock_callback]},
        )


def test_worker_agent_run_empty_messages() -> None:
    """Verify worker.run handles empty message histories gracefully."""
    mock_llm = MagicMock(spec=BaseChatModel)
    worker = WorkerAgent(llm=mock_llm)

    with patch.object(worker.graph, "invoke", return_value={"messages": []}):
        result = worker.run(task="Empty response task")
        assert result["task"] == "Empty response task"
        assert result["response"] == ""
        assert result["messages"] == []


def test_worker_agent_invoke_delegation() -> None:
    """Verify worker.invoke delegates directly to its compiled state graph."""
    mock_llm = MagicMock(spec=BaseChatModel)
    worker = WorkerAgent(llm=mock_llm)

    with patch.object(
        worker.graph, "invoke", return_value={"messages": ["mocked"]}
    ) as mock_invoke:
        output = worker.invoke({"messages": []}, config={"run_name": "custom"})
        assert output == {"messages": ["mocked"]}
        mock_invoke.assert_called_once_with(
            {"messages": []}, config={"run_name": "custom"}
        )


# ============================================================================
# Orchestrator Agent Tests
# ============================================================================


def test_orchestrator_state_schema() -> None:
    """Verify OrchestratorState initializes with default empty messages or supplied messages."""
    empty_state = OrchestratorState()
    assert empty_state.messages == []

    msg = HumanMessage(content="Summarize all documents")
    populated_state = OrchestratorState(messages=[msg])
    assert len(populated_state.messages) == 1
    assert populated_state.messages[0].content == "Summarize all documents"


def test_create_orchestrator_factory() -> None:
    """Verify create_orchestrator factory builds and compiles a LangGraph CompiledStateGraph."""
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_worker = MagicMock(spec=WorkerAgent)
    graph = create_orchestrator(
        llm=mock_llm, worker_agent=mock_worker, max_concurrency=4
    )

    assert isinstance(graph, CompiledStateGraph)
    mock_llm.bind_tools.assert_called_once()


def test_orchestrator_agent_initialization() -> None:
    """Verify OrchestratorAgent sets up delegation tools and graph with supplied worker."""
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_worker = MagicMock(spec=WorkerAgent)

    orchestrator = OrchestratorAgent(
        llm=mock_llm,
        worker_agent=mock_worker,
        max_concurrency=3,
    )

    assert orchestrator.llm is mock_llm
    assert orchestrator.worker_agent is mock_worker
    assert orchestrator.max_concurrency == 3
    assert orchestrator.system_prompt == OrchestratorAgent.DEFAULT_SYSTEM_PROMPT
    assert isinstance(orchestrator.graph, CompiledStateGraph)
    mock_llm.bind_tools.assert_called_once()


def test_orchestrator_agent_default_worker() -> None:
    """Verify OrchestratorAgent constructs a default WorkerAgent when none is supplied."""
    mock_llm = MagicMock(spec=BaseChatModel)
    orchestrator = OrchestratorAgent(llm=mock_llm)

    assert orchestrator.worker_agent is not None
    assert isinstance(orchestrator.worker_agent, WorkerAgent)
    assert orchestrator.worker_agent.llm is mock_llm


def test_orchestrator_agent_run_success() -> None:
    """Verify orchestrator.run packages prompt, configures callbacks, and extracts final response."""
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_worker = MagicMock(spec=WorkerAgent)
    orchestrator = OrchestratorAgent(llm=mock_llm, worker_agent=mock_worker)

    expected_synthesis = "Executive Summary: Both documents confirm targets met."
    mock_invoke_result = {
        "messages": [
            HumanMessage(content="Summarize doc_1 and doc_2"),
            AIMessage(content=expected_synthesis),
        ]
    }
    mock_callback = MagicMock()

    with patch.object(
        orchestrator.graph, "invoke", return_value=mock_invoke_result
    ) as mock_invoke:
        result = orchestrator.run(
            task="Summarize doc_1 and doc_2",
            callbacks=[mock_callback],
            run_name="test_orch_run",
        )

        assert result["task"] == "Summarize doc_1 and doc_2"
        assert result["final_response"] == expected_synthesis
        assert len(result["messages"]) == 2

        mock_invoke.assert_called_once_with(
            {"messages": [HumanMessage(content="Summarize doc_1 and doc_2")]},
            config={"run_name": "test_orch_run", "callbacks": [mock_callback]},
        )


def test_orchestrator_agent_run_empty_messages() -> None:
    """Verify orchestrator.run handles empty message histories gracefully."""
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_worker = MagicMock(spec=WorkerAgent)
    orchestrator = OrchestratorAgent(llm=mock_llm, worker_agent=mock_worker)

    with patch.object(orchestrator.graph, "invoke", return_value={"messages": []}):
        result = orchestrator.run(task="Empty response task")
        assert result["task"] == "Empty response task"
        assert result["final_response"] == ""
        assert result["messages"] == []


def test_orchestrator_agent_invoke_delegation() -> None:
    """Verify orchestrator.invoke delegates directly to its compiled state graph."""
    mock_llm = MagicMock(spec=BaseChatModel)
    mock_worker = MagicMock(spec=WorkerAgent)
    orchestrator = OrchestratorAgent(llm=mock_llm, worker_agent=mock_worker)

    with patch.object(
        orchestrator.graph, "invoke", return_value={"messages": ["orch_mocked"]}
    ) as mock_invoke:
        output = orchestrator.invoke({"messages": []}, config={"run_name": "custom"})
        assert output == {"messages": ["orch_mocked"]}
        mock_invoke.assert_called_once_with(
            {"messages": []}, config={"run_name": "custom"}
        )
