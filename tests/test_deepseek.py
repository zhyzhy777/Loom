import json
import unittest
from unittest.mock import Mock, patch

from examples.shipping_agent import calculate_shipping
from loom import Agent, DeepSeekModel, RunError


class DeepSeekTests(unittest.TestCase):
    def setUp(self):
        connection = patch("loom.deepseek.http.client.HTTPSConnection")
        self.connect = connection.start()
        self.addCleanup(connection.stop)
        self.http = self.connect.return_value
        self.model = DeepSeekModel(api_key="unit-test", model="test-model", timeout_seconds=5)

    def response(self, reason, **message):
        body = {"choices": [{"finish_reason": reason, "message": {"role": "assistant", **message}}]}
        response = Mock(status=200)
        response.read.return_value = json.dumps(body).encode()
        return response

    def test_tool_roundtrip(self):
        call = {"type": "function", "id": "call_1", "function": {
            "name": "calculate_shipping", "arguments": '{"weight_kg":2.5}',
        }}
        self.http.getresponse.side_effect = [
            self.response("tool_calls", content=None, tool_calls=[call], reasoning_content="trace"),
            self.response("stop", content="运费为20.00 元。"),
        ]
        agent = Agent(model=self.model, tools=[calculate_shipping], instructions="运费助手", max_model_calls=2)
        self.assertEqual(agent.run("2.5 千克").text, "运费为20.00 元。")
        first, second = self.http.request.call_args_list
        self.assertEqual(first.args, ("POST", "/chat/completions"))
        self.connect.assert_called_with("api.deepseek.com", timeout=5)
        self.assertEqual(first.kwargs["headers"]["Authorization"], "Bearer unit-test")
        payload = json.loads(first.kwargs["body"])
        self.assertEqual(payload["model"], "test-model")
        self.assertEqual(payload["tools"][0]["function"]["parameters"]["required"], ["weight_kg"])
        history = json.loads(second.kwargs["body"])["messages"]
        self.assertEqual(history[-2], {"role": "assistant", "content": None,
                                       "reasoning_content": "trace", "tool_calls": [call]})
        self.assertEqual(history[-1], {"role": "tool", "tool_call_id": "call_1", "content": "20.00 元"})

    def test_transport_and_decoding_errors(self):
        malformed = Mock(status=200)
        malformed.read.return_value = b'{"choices":[]}'
        for response, error in [(TimeoutError(), "model_timeout"), (OSError(), "model_error"),
                                (Mock(status=401), "model_error"), (malformed, "invalid_reply")]:
            with self.subTest(error=error):
                self.http.getresponse.side_effect = [response]
                with self.assertRaises(RunError) as caught:
                    self.model.complete([], [])
                self.assertEqual((caught.exception.code, caught.exception.node), (error, "model"))
                self.assertNotIn("tools", json.loads(self.http.request.call_args.kwargs["body"]))
                self.http.close.assert_called()
