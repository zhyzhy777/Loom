"""Serial execution of signal-labelled graphs over caller-owned state."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Generic, Literal, TypeVar

S = TypeVar("S")


class EndMarker(Enum):
    END = "end"


END = EndMarker.END


class RunError(Exception):
    def __init__(self, code: str, node: str, message: str, tool_call_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.node = node
        self.message = message
        self.tool_call_id = tool_call_id


@dataclass(frozen=True)
class GraphRun(Generic[S]):
    state: S
    status: Literal["completed", "failed"]
    current_node: str
    steps: int
    error: RunError | None = None


def _require_name(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Node names and signals must be nonempty strings")


class Graph(Generic[S]):
    def __init__(self) -> None:
        self._nodes: dict[str, Callable[[S], str]] = {}
        self._edges: dict[tuple[str, str], str | EndMarker] = {}
        self._entry: str | None = None

    def add_node(self, name: str, fn: Callable[[S], str]) -> None:
        _require_name(name)
        if name in self._nodes or not callable(fn):
            raise ValueError(f"Expected a new node name and a callable: {name!r}")
        self._nodes[name] = fn

    def set_entry(self, name: str) -> None:
        _require_name(name)
        self._entry = name

    def add_edge(self, source: str, signal: str, target: str | EndMarker) -> None:
        _require_name(source)
        _require_name(signal)
        if target is not END:
            _require_name(target)
        key = (source, signal)
        if key in self._edges:
            raise ValueError(f"Duplicate route: {key!r}")
        self._edges[key] = target

    def run(self, state: S, *, max_steps: int) -> GraphRun[S]:
        if type(max_steps) is not int or max_steps < 1:
            raise ValueError("max_steps must be a positive integer")
        current = self._entry
        if current is None or current not in self._nodes:
            raise ValueError(f"Unknown entry node: {current!r}")
        for (source, _), target in self._edges.items():
            if source not in self._nodes or (target is not END and target not in self._nodes):
                raise ValueError(f"Unknown node in edge {source!r} -> {target!r}")

        for step in range(1, max_steps + 1):
            try:
                signal = self._nodes[current](state)
                if not isinstance(signal, str) or (current, signal) not in self._edges:
                    raise RunError("graph_error", current, f"No route for signal {signal!r}")
                target = self._edges[current, signal]
            except RunError as error:
                return GraphRun(state, "failed", current, step, error)
            except Exception as cause:
                error = RunError("graph_error", current, f"{type(cause).__name__}: {cause}")
                error.__cause__ = cause
                return GraphRun(state, "failed", current, step, error)

            if target is END:
                return GraphRun(state, "completed", current, step)
            if step == max_steps:
                error = RunError("step_limit", current, f"Reached the limit of {max_steps} node executions")
                return GraphRun(state, "failed", current, step, error)
            current = target

        raise AssertionError("Unreachable with positive max_steps")
