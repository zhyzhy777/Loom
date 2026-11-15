import unittest

from examples.shipping_agent import calculate_shipping
from loom import Agent, ModelReply, RunError, ToolCall, ToolRegistry, tool


class ScriptedModel:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.histories = []

    def complete(self, messages, tools):
        self.histories.append(list(messages))
        return next(self.replies)


def request(call_id, args='{"weight_kg": 2.5}'):
    return ToolCall(call_id, "calculate_shipping", args)


class AgentTests(unittest.TestCase):
    def make_agent(self, replies, budget=3):
        self.model = ScriptedModel(replies)
        return Agent(model=self.model, tools=[calculate_shipping], instructions="test", max_model_calls=budget)

    def test_batch_ids_provider_fields_and_multiple_rounds(self):
        replies = [
            ModelReply("tool_calls", calls=[request("a"), request("b", '{"weight_kg":1}')],
                       provider_fields={"trace": "preserve"}),
            ModelReply("tool_calls", calls=[request("c")]),
            ModelReply("stop", "done"),
        ]
        self.assertEqual(self.make_agent(replies).run("ship").text, "done")
        history = self.model.histories[2]
        self.assertEqual(history[2]["provider_fields"], {"trace": "preserve"})
        self.assertEqual([(m["tool_call_id"], m["content"]) for m in history if m["role"] == "tool"],
                         [("a", "20.00 元"), ("b", "8.00 元"), ("c", "20.00 元")])

    def test_direct_answer_and_task_isolation(self):
        agent = self.make_agent([ModelReply("stop", "done")] * 2, budget=1)
        for task in ("first", "second"):
            self.assertEqual(agent.run(task).text, "done")
            self.assertEqual([m["content"] for m in self.model.histories[-1]], ["test", task])

    def test_limit_and_failure_stop_side_effects(self):
        seen = []

        @tool
        def record(n: int) -> str:
            """Record a number."""
            seen.append(n)
            if n == 2:
                raise ValueError("failed")
            return str(n)

        calls = [ToolCall(str(n), "record", '{"n": %d}' % n) for n in (1, 2, 3)]
        for budget, code, call_id, expected in [(1, "model_limit", None, []), (2, "tool_error", "2", [1, 2])]:
            model = ScriptedModel([ModelReply("tool_calls", calls=calls)])
            agent = Agent(model=model, tools=[record], instructions="", max_model_calls=budget)
            with self.assertRaises(RunError) as caught:
                agent.run("task")
            self.assertEqual((caught.exception.code, caught.exception.tool_call_id, seen), (code, call_id, expected))

    def test_invalid_replies(self):
        for reply in (ModelReply("stop", " "), ModelReply("length", "partial"),
                      ModelReply("tool_calls"), ModelReply("stop", "answer", [request("a")]),
                      ModelReply("tool_calls", calls=[request("a"), request("a")])):
            with self.subTest(reply=reply), self.assertRaises(RunError) as caught:
                self.make_agent([reply]).run("task")
            self.assertEqual(caught.exception.code, "invalid_reply")

    def test_tool_schema_and_invalid_arguments(self):
        registry = ToolRegistry([calculate_shipping])
        spec, = registry.describe()
        self.assertEqual(spec.parameters, {"type": "object", "properties": {"weight_kg": {"type": "number"}},
                                          "required": ["weight_kg"], "additionalProperties": False})
        for args in ("[]", "{}", "{bad", '{"weight_kg":true}', '{"weight_kg":1,"x":2}'):
            with self.subTest(args=args), self.assertRaises(RunError) as caught:
                registry.execute(request("a", args))
            self.assertEqual((caught.exception.code, caught.exception.tool_call_id), ("invalid_arguments", "a"))
        with self.assertRaises(ValueError):
            ToolRegistry([calculate_shipping, calculate_shipping])
