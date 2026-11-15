"""DeepSeek Chat Completions adapter."""

import http.client
import json
import math

from .graph import RunError
from .protocol import ModelReply, ToolCall, ToolSpec


def _encode_message(message: dict) -> dict:
    if message["role"] != "assistant":
        return dict(message)
    encoded = {**message["provider_fields"], "role": "assistant", "content": message["content"]}
    if message["calls"]:
        encoded["tool_calls"] = [
            {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
            for call in message["calls"]
        ]
    return encoded


def _decode_reply(body: bytes) -> ModelReply:
    try:
        choice = json.loads(body)["choices"][0]
        message = choice["message"]
        if message["role"] != "assistant":
            raise ValueError("Expected an assistant message")
        calls = []
        raw_calls = message.get("tool_calls")
        if raw_calls is not None:
            if not isinstance(raw_calls, list):
                raise ValueError("Expected a list of tool calls")
            for item in raw_calls:
                if item["type"] != "function":
                    raise ValueError("Unsupported tool call type")
                function = item["function"]
                calls.append(ToolCall(item["id"], function["name"], function["arguments"]))
        fields = {k: v for k, v in message.items() if k not in ("role", "content", "tool_calls")}
        return ModelReply(choice["finish_reason"], message.get("content"), calls, fields)
    except (ValueError, TypeError, KeyError, IndexError, RecursionError):
        raise RunError("invalid_reply", "model", "Malformed DeepSeek response") from None


class DeepSeekModel:
    def __init__(self, *, api_key: str, model: str, timeout_seconds: float = 30):
        if not isinstance(api_key, str) or not api_key.strip():
            raise ValueError("api_key must be a nonempty string")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a nonempty string")
        if type(timeout_seconds) not in (int, float) or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be a positive finite number")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout_seconds

    def complete(self, messages: list[dict], tools: list[ToolSpec]) -> ModelReply:
        payload = {"model": self._model, "messages": [_encode_message(message) for message in messages]}
        if tools:
            payload["tools"] = [
                {"type": "function", "function": {
                    "name": spec.name, "description": spec.description, "parameters": spec.parameters,
                }}
                for spec in tools
            ]
        connection = http.client.HTTPSConnection("api.deepseek.com", timeout=self._timeout)
        try:
            connection.request("POST", "/chat/completions", body=json.dumps(payload).encode("utf-8"),
                               headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"})
            response = connection.getresponse()
            if not 200 <= response.status < 300:
                raise RunError("model_error", "model", f"DeepSeek returned HTTP {response.status}")
            body = response.read()
        except TimeoutError:
            raise RunError("model_timeout", "model", "DeepSeek request timed out") from None
        except (OSError, http.client.HTTPException, ValueError):
            raise RunError("model_error", "model", "DeepSeek request failed") from None
        finally:
            connection.close()
        return _decode_reply(body)
