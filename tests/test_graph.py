import unittest

from loom import END, Graph, RunError


class GraphTests(unittest.TestCase):
    def test_loop_routes_and_exact_budget(self):
        graph = Graph()
        def count(state):
            state.append("count")
            return "more" if len(state) < 3 else "done"

        graph.add_node("count", count)
        graph.set_entry("count")
        graph.add_edge("count", "more", "count")
        graph.add_edge("count", "done", END)
        for limit, expected in [(3, "completed"), (2, "failed")]:
            run = graph.run([], max_steps=limit)
            self.assertEqual((run.status, run.steps, len(run.state)), (expected, limit, limit))
            if limit == 2:
                self.assertEqual(run.error.code, "step_limit")

    def test_step_limit_reports_last_executed_node(self):
        graph = Graph()
        graph.add_node("one", lambda s: "next")
        graph.add_node("two", lambda s: self.fail("past step budget"))
        graph.set_entry("one")
        graph.add_edge("one", "next", "two")
        run = graph.run({}, max_steps=1)
        self.assertEqual((run.current_node, run.error.code), ("one", "step_limit"))

    def test_invalid_graph_fails_before_any_node_runs(self):
        graph = Graph()
        graph.add_node("n", lambda s: self.fail("invalid configuration"))
        graph.set_entry("n")
        graph.add_edge("n", "done", "typo")
        with self.assertRaises(ValueError):
            graph.run({}, max_steps=5)
        with self.assertRaises(ValueError):
            graph.add_edge("n", "done", END)

    def test_unhandled_signal_or_exception_stops_graph(self):
        known = RunError("inventory_error", "n", "missing inventory")
        def broken(state):
            raise state
        graph = Graph()
        graph.add_node("n", broken)
        graph.set_entry("n")
        self.assertIs(graph.run(known, max_steps=2).error, known)
        self.assertIsInstance(graph.run(ValueError("bad"), max_steps=2).error.__cause__, ValueError)
        graph.add_node("m", lambda state: "unknown")
        graph.set_entry("m")
        run = graph.run({}, max_steps=2)
        self.assertEqual((run.error.code, run.current_node, run.steps), ("graph_error", "m", 1))
