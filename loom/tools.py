import inspect
import json
import math
from copy import deepcopy
from typing import Callable, get_type_hints

from .graph import RunError
from .protocol import ToolCall, ToolResult, ToolSpec


_SCHEMA_TYPES = {str: "string", int: "integer", float: "number", bool: "boolean"}


def tool(fn: Callable) -> Callable:
    fn.__loom_tool__ = True
    return fn


def _describe(fn: Callable) -> ToolSpec:
    if not inspect.isfunction(fn) or not getattr(fn, "__loom_tool__", False):
        raise ValueError("Expected a function decorated with @tool")
    if inspect.iscoroutinefunction(fn) or inspect.isgeneratorfunction(fn) or inspect.isasyncgenfunction(fn):
        raise ValueError(f"{fn.__name__} must be synchronous and return a string")
    description = inspect.getdoc(fn)
    try:
        hints = get_type_hints(fn)
    except (TypeError, NameError) as cause:
        raise ValueError(f"Invalid annotations on {fn.__name__}") from cause
    if not description or hints.get("return") is not str:
        raise ValueError(f"{fn.__name__} requires a docstring and a str return annotation")
    properties = {}
    for param in inspect.signature(fn).parameters.values():
        if param.kind not in (param.POSITIONAL_OR_KEYWORD, param.KEYWORD_ONLY) or param.default is not param.empty:
            raise ValueError(f"Expected a required keyword-addressable parameter: {param.name}")
        annotation = hints.get(param.name)
        if annotation not in _SCHEMA_TYPES:
            raise ValueError(f"Unsupported annotation for {param.name}")
        properties[param.name] = {"type": _SCHEMA_TYPES[annotation]}
    return ToolSpec(fn.__name__, description, {
        "type": "object", "properties": properties, "required": list(properties), "additionalProperties": False,
    })


class ToolRegistry:
    def __init__(self, tools):
        self._functions = {}
        self._specs = {}
        for fn in tools:
            spec = _describe(fn)
            if spec.name in self._functions:
                raise ValueError(f"Duplicate tool: {spec.name}")
            self._functions[spec.name] = fn
            self._specs[spec.name] = spec

    def describe(self) -> list[ToolSpec]:
        return deepcopy(list(self._specs.values()))

    def execute(self, call: ToolCall) -> ToolResult:
        if call.name not in self._functions:
            raise RunError("unknown_tool", "tools", f"Unknown tool: {call.name}", call.id)
        properties = self._specs[call.name].parameters["properties"]
        try:
            arguments = json.loads(call.arguments)
            if not isinstance(arguments, dict) or arguments.keys() != properties.keys():
                raise ValueError(f"Expected an object with keys {list(properties)}")
            for name, spec in properties.items():
                value = arguments[name]
                if spec["type"] == "number":
                    if type(value) not in (int, float) or not math.isfinite(value):
                        raise ValueError(f"Expected a finite number for {name}")
                    arguments[name] = float(value)
                elif _SCHEMA_TYPES.get(type(value)) != spec["type"]:
                    raise ValueError(f"Invalid {spec['type']} argument: {name}")
        except (ValueError, TypeError, OverflowError, RecursionError) as cause:
            raise RunError("invalid_arguments", "tools", str(cause), call.id) from cause
        try:
            content = self._functions[call.name](**arguments)
        except Exception as cause:
            raise RunError("tool_error", "tools", str(cause), call.id) from cause
        if not isinstance(content, str):
            raise RunError("invalid_tool_result", "tools", "Tool must return a string", call.id)
        return ToolResult(call.id, content)
