"""Worker Agent built with LangGraph with document reading and email tools."""

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

from src.utils.logger import get_logger
from src.utils.tools import WorkerTools

logger = get_logger("mas.agents.worker")

DEFAULT_SYSTEM_PROMPT = (
    "You are a specialized document analysis worker agent.\n"
    "Your role is to inspect documents using the read_document tool and produce clear, factual summaries.\n"
    "You have access to two tools:\n"
    "1. read_document(doc_id: str): fetches the content of a document.\n"
    "2. send_email(to: str, body: str): queues an email to a recipient.\n\n"
    "Instructions:\n"
    "- When asked to summarize or review documents, always retrieve them first.\n"
    "- Process document contents carefully and report your short summary."
)


class WorkerState(BaseModel):
    """Pydantic state schema for the Worker Agent graph."""

    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)


def create_worker(
    llm: BaseChatModel,
    tools: Sequence[BaseTool] | None = None,
    system_prompt: str | None = None,
    checkpointer: Any | None = None,
) -> CompiledStateGraph:
    """Build and compile a LangGraph StateGraph worker agent using Pydantic state.

    Args:
        llm: Chat model supporting tool calling.
        tools: Optional sequence of tools available to the worker.
            Defaults to WorkerTools.get_tools().
        system_prompt: Optional custom system prompt.
        checkpointer: Optional checkpointer for state persistence.

    Returns:
        CompiledStateGraph representing the worker agent.
    """
    tools_list = list(tools) if tools is not None else WorkerTools.get_tools()
    prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
    model_with_tools = llm.bind_tools(tools_list)

    def worker_node(
        state: WorkerState,
        config: RunnableConfig,
    ) -> dict[str, list[BaseMessage]]:
        messages = list(state.messages)
        if not messages or not isinstance(messages[0], SystemMessage):
            messages = [SystemMessage(content=prompt), *messages]
        response = model_with_tools.invoke(messages, config=config)
        return {"messages": [response]}

    def should_continue(state: WorkerState) -> str:
        messages = state.messages
        if not messages:
            return END
        last_message = messages[-1]
        if getattr(last_message, "tool_calls", None):
            return "tools"
        return END

    builder = StateGraph(WorkerState)
    builder.add_node("worker", worker_node)
    builder.add_node("tools", ToolNode(tools_list))

    builder.add_edge(START, "worker")
    builder.add_conditional_edges("worker", should_continue, ["tools", END])
    builder.add_edge("tools", "worker")

    logger.info("Compiled LangGraph worker with %d tool(s).", len(tools_list))
    return builder.compile(checkpointer=checkpointer)


class WorkerAgent:
    """Worker Agent that accesses tools to inspect documents and generate summaries via LangGraph."""

    DEFAULT_SYSTEM_PROMPT: str = DEFAULT_SYSTEM_PROMPT

    def __init__(
        self,
        llm: BaseChatModel,
        tools: Sequence[BaseTool] | None = None,
        system_prompt: str | None = None,
        checkpointer: Any | None = None,
    ) -> None:
        """Initialize the worker agent.

        Args:
            llm: Chat model supporting tool calling.
            tools: Optional sequence of tools available to the worker.
                Defaults to WorkerTools.get_tools().
            system_prompt: Optional custom system prompt.
            checkpointer: Optional checkpointer for state persistence.
        """
        self.llm = llm
        self.system_prompt = system_prompt or self.DEFAULT_SYSTEM_PROMPT
        self.tools = list(tools) if tools is not None else WorkerTools.get_tools()
        self.graph: CompiledStateGraph = create_worker(
            llm=self.llm,
            tools=self.tools,
            system_prompt=self.system_prompt,
            checkpointer=checkpointer,
        )

    def invoke(
        self,
        input: dict[str, Any] | WorkerState,
        config: RunnableConfig | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Invoke the compiled LangGraph worker.

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
        run_name: str = "worker_agent",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Run the worker with a text task instruction.

        Args:
            task: Task instruction for the worker.
            callbacks: Optional callbacks for tracing.
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
            "response": final_response,
            "messages": messages,
        }


__all__ = [
    "WorkerAgent",
]
