from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: str


@dataclass(frozen=True)
class ToolResult:
    tool_call_id: str
    content: str


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict


@dataclass(frozen=True)
class ModelReply:
    finish_reason: str
    text: str | None = None
    calls: list[ToolCall] = field(default_factory=list)
    provider_fields: dict = field(default_factory=dict)


class Model(Protocol):
    def complete(self, messages: list[dict], tools: list[ToolSpec]) -> ModelReply: ...
