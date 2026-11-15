from dataclasses import dataclass, field

from .graph import END, Graph, RunError
from .protocol import Model, ModelReply, ToolCall
from .tools import ToolRegistry


@dataclass
class AgentState:
    messages: list[dict]
    max_model_calls: int
    model_calls: int = 0
    pending_calls: list[ToolCall] = field(default_factory=list)
    final_text: str | None = None


@dataclass(frozen=True)
class RunResult:
    text: str


def _validate_reply(reply: ModelReply) -> None:
    if not isinstance(reply, ModelReply) or not isinstance(reply.calls, list) or not isinstance(reply.provider_fields, dict):
        raise RunError("invalid_reply", "model", "Expected a ModelReply with calls and provider fields")
    if reply.text is not None and not isinstance(reply.text, str):
        raise RunError("invalid_reply", "model", "Expected text or None")
    if reply.finish_reason == "stop" and not reply.calls and reply.text and reply.text.strip():
        return
    if reply.finish_reason != "tool_calls" or not reply.calls:
        raise RunError("invalid_reply", "model", "Expected a final answer or tool requests")
    ids = set()
    for call in reply.calls:
        if not isinstance(call, ToolCall) or not isinstance(call.id, str) or not call.id.strip() or call.id in ids:
            raise RunError("invalid_reply", "model", "Each tool request needs a unique nonempty ID")
        if not isinstance(call.name, str) or not call.name.strip() or not isinstance(call.arguments, str):
            raise RunError("invalid_reply", "model", "Expected a tool name and JSON argument string")
        ids.add(call.id)


class Agent:
    def __init__(self, *, model: Model, instructions: str, tools, max_model_calls: int = 8):
        if type(max_model_calls) is not int or max_model_calls < 1:
            raise ValueError("max_model_calls must be a positive integer")
        self._model = model
        self._instructions = instructions
        self._registry = ToolRegistry(tools)
        self._max_model_calls = max_model_calls
        self._graph = Graph[AgentState]()
        self._graph.add_node("model", self._call_model)
        self._graph.add_node("tools", self._run_tools)
        self._graph.set_entry("model")
        self._graph.add_edge("model", "needs_tools", "tools")
        self._graph.add_edge("tools", "tools_done", "model")
        self._graph.add_edge("model", "answered", END)

    def _call_model(self, state: AgentState) -> str:
        state.model_calls += 1
        reply = self._model.complete(state.messages, self._registry.describe())
        _validate_reply(reply)
        state.messages.append({
            "role": "assistant", "content": reply.text, "calls": reply.calls,
            "provider_fields": reply.provider_fields,
        })
        if reply.calls:
            state.pending_calls.extend(reply.calls)
            if state.model_calls >= state.max_model_calls:
                raise RunError("model_limit", "model", "No model call left to process tool results")
            return "needs_tools"
        state.final_text = reply.text
        return "answered"

    def _run_tools(self, state: AgentState) -> str:
        while state.pending_calls:
            result = self._registry.execute(state.pending_calls[0])
            state.messages.append({"role": "tool", "tool_call_id": result.tool_call_id, "content": result.content})
            del state.pending_calls[0]
        return "tools_done"

    def run(self, task: str) -> RunResult:
        messages = [{"role": "system", "content": self._instructions}, {"role": "user", "content": task}]
        state = AgentState(messages, self._max_model_calls)
        run = self._graph.run(state, max_steps=2 * state.max_model_calls)
        if run.error is not None:
            raise run.error
        assert state.final_text is not None
        return RunResult(state.final_text)
