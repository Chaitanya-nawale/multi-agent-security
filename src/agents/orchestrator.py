"""Orchestrator Agent built with LangGraph for document task coordination."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

from src.agents.worker import WorkerAgent
from src.utils.logger import get_logger
from src.utils.tools import OrchestratorTools

logger = get_logger("mas.agents.orchestrator")

DEFAULT_SYSTEM_PROMPT = (
    "You are an Orchestrator Agent responsible for analyzing and summarizing documents.\n"
    "When asked to analyze or summarize documents:\n"
    "1. Identify the list of document IDs that need to be processed.\n"
    "2. Invoke the process_documents tool with the list of doc_ids.\n"
    "3. You will receive a dictionary mapping each document ID to its summary.\n"
    "4. Synthesize a comprehensive and accurate final response for the user based on those summaries."
)


class OrchestratorState(BaseModel):
    """Pydantic state schema for the Orchestrator Agent graph."""

    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)


def create_orchestrator(
    llm: BaseChatModel,
    worker_agent: WorkerAgent | None = None,
    tools: Sequence[BaseTool] | None = None,
    system_prompt: str | None = None,
    checkpointer: Any | None = None,
    max_concurrency: int = 5,
) -> CompiledStateGraph:
    """Build and compile a LangGraph StateGraph orchestrator using Pydantic state.

    Args:
        llm: Chat model supporting tool calling.
        worker_agent: Optional WorkerAgent used to process documents.
        tools: Optional sequence of tools available to the orchestrator.
            Defaults to OrchestratorTools(worker=worker).get_tools().
        system_prompt: Optional custom system prompt.
        checkpointer: Optional checkpointer for state persistence.
        max_concurrency: Maximum concurrent worker delegations.

    Returns:
        CompiledStateGraph representing the orchestrator agent.
    """
    worker = worker_agent or WorkerAgent(llm=llm)
    tools_list = (
        list(tools)
        if tools is not None
        else OrchestratorTools(
            worker=worker, max_concurrency=max_concurrency
        ).get_tools()
    )
    prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    model_with_tools = llm.bind_tools(tools_list)

    def orchestrator_node(
        state: OrchestratorState,
        config: RunnableConfig,
    ) -> dict[str, list[BaseMessage]]:
        messages = list(state.messages)
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=prompt), *messages]
        response = model_with_tools.invoke(messages, config=config)
        return {"messages": [response]}

    def should_continue(state: OrchestratorState) -> str:
        messages = state.messages
        if not messages:
            return END
        last_message = messages[-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return END

    builder = StateGraph(OrchestratorState)
    builder.add_node("orchestrator", orchestrator_node)
    builder.add_node("tools", ToolNode(tools_list))

    builder.add_edge(START, "orchestrator")
    builder.add_conditional_edges("orchestrator", should_continue, ["tools", END])
    builder.add_edge("tools", "orchestrator")

    logger.info("Compiled LangGraph orchestrator with %d tool(s).", len(tools_list))
    return builder.compile(checkpointer=checkpointer)


class OrchestratorAgent:
    """Orchestrator Agent that produces document IDs and coordinates summarization via LangGraph."""

    DEFAULT_SYSTEM_PROMPT: str = DEFAULT_SYSTEM_PROMPT

    def __init__(
        self,
        llm: BaseChatModel,
        worker_agent: WorkerAgent | None = None,
        tools: Sequence[BaseTool] | None = None,
        system_prompt: str | None = None,
        checkpointer: Any | None = None,
        max_concurrency: int = 5,
    ) -> None:
        """Initialize the orchestrator agent.

        Args:
            llm: Chat model supporting tool calling.
            worker_agent: Optional WorkerAgent used to process documents.
            tools: Optional sequence of tools available to the orchestrator.
            system_prompt: Optional custom system prompt.
            checkpointer: Optional checkpointer for state persistence.
            max_concurrency: Maximum concurrent worker delegations.
        """
        self.llm = llm
        self.worker_agent = worker_agent or WorkerAgent(llm=llm)
        self.system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self.max_concurrency = max_concurrency
        self.graph: CompiledStateGraph = create_orchestrator(
            llm=self.llm,
            worker_agent=self.worker_agent,
            tools=tools,
            system_prompt=self.system_prompt,
            checkpointer=checkpointer,
            max_concurrency=self.max_concurrency,
        )

    def invoke(
        self,
        input: dict[str, Any] | OrchestratorState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Invoke the compiled LangGraph orchestrator.

        Args:
            input: State input containing messages or initial state.
            config: Optional RunnableConfig for tracing and callbacks.
            **kwargs: Additional invocation arguments.

        Returns:
            Resulting state dictionary from LangGraph.
        """
        return self.graph.invoke(input, config=config, **kwargs)

    def run(
        self,
        task: str,
        callbacks: list[Any] | None = None,
        run_name: str = "orchestrator_agent",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run the orchestrator agent with a text task instruction.

        Args:
            task: User task instruction.
            callbacks: Optional Langfuse / LangChain callbacks.
            run_name: Identifier for the execution run.
            **kwargs: Additional parameters passed to invoke.

        Returns:
            Dictionary containing the task, final response, and message history.
        """
        config: RunnableConfig = {"run_name": run_name}
        if callbacks:
            config["callbacks"] = callbacks

        state = self.invoke(
            {"messages": [HumanMessage(content=task)]}, config=config, **kwargs
        )
        messages: list[BaseMessage] = state.get("messages", [])
        final_response = (
            messages[-1].content
            if messages and isinstance(messages[-1].content, str)
            else str(messages[-1].content)
            if messages
            else ""
        )
        return {
            "task": task,
            "final_response": final_response,
            "messages": messages,
        }


__all__ = [
    "OrchestratorAgent",
]
