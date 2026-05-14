"""Tests for backend/tools/graph.py."""

import importlib.util
import json
import sys
import types
import pathlib
import unittest

# ── Load module under test via importlib ──────────────────────────────────────

_graph_path = pathlib.Path(__file__).parent.parent / "src" / "kerf_imports" / "tools" / "graph.py"
_spec = importlib.util.spec_from_file_location("tools.graph", _graph_path)
_mod = importlib.util.module_from_spec(_spec)

for mod_name in ["tools.registry", "tools.context"]:
    if mod_name not in sys.modules:
        stub = types.ModuleType(mod_name)
        if mod_name == "tools.registry":
            stub.ToolSpec = type("ToolSpec", (), {"__init__": lambda self, **kw: None})
            stub.register = lambda *a, **kw: (lambda fn: fn)
            stub.ok_payload = lambda v: json.dumps(v)
            stub.err_payload = lambda msg, code: json.dumps({"error": msg, "code": code})
        if mod_name == "tools.context":
            stub.ProjectCtx = object
        sys.modules[mod_name] = stub

sys.modules.setdefault("tools.graph", _mod)
_spec.loader.exec_module(_mod)

# ── Aliases ───────────────────────────────────────────────────────────────────

_default_graph = _mod._default_graph
_gen_id = _mod._gen_id
_topological_order = _mod._topological_order
_evaluate_graph_data = _mod._evaluate_graph_data
_resolve_params = _mod._resolve_params
_param_refs = _mod._param_refs
BUILTIN_OPS = _mod.BUILTIN_OPS


# ── _default_graph ────────────────────────────────────────────────────────────

class TestDefaultGraph(unittest.TestCase):
    def test_version(self):
        g = _default_graph("Test")
        self.assertEqual(g["version"], 1)
        self.assertEqual(g["name"], "Test")
        self.assertEqual(g["nodes"], [])
        self.assertEqual(g["outputs"], [])

    def test_default_name(self):
        g = _default_graph()
        self.assertEqual(g["name"], "Untitled")


# ── _gen_id ───────────────────────────────────────────────────────────────────

class TestGenId(unittest.TestCase):
    def test_sequential(self):
        nodes = [{"id": "n1"}, {"id": "n2"}]
        self.assertEqual(_gen_id(nodes), "n3")

    def test_empty(self):
        self.assertEqual(_gen_id([]), "n1")

    def test_skips_existing(self):
        nodes = [{"id": "n1"}, {"id": "n3"}]
        result = _gen_id(nodes)
        # Should be n2 since we start at len+1=3, n3 exists, try n2 — actually starts at len+1
        self.assertNotIn(result, {"n1", "n3"})


# ── _param_refs ───────────────────────────────────────────────────────────────

class TestParamRefs(unittest.TestCase):
    def test_finds_ref(self):
        self.assertIn("n5", _param_refs({"v": "@n5.out"}))

    def test_no_ref(self):
        self.assertEqual(_param_refs({"v": 42}), [])

    def test_list_refs(self):
        refs = _param_refs({"arr": ["@n1.out", "@n2.out", "literal"]})
        self.assertIn("n1", refs)
        self.assertIn("n2", refs)
        self.assertNotIn("literal", refs)


# ── _resolve_params ───────────────────────────────────────────────────────────

class TestResolveParams(unittest.TestCase):
    def test_resolves_ref(self):
        resolved = _resolve_params({"x": "@n1.out"}, {"n1": 42})
        self.assertEqual(resolved["x"], 42)

    def test_unresolved_ref(self):
        resolved = _resolve_params({"x": "@n99.out"}, {})
        self.assertIn("__unresolved", resolved["x"])

    def test_literal_passthrough(self):
        resolved = _resolve_params({"x": 10}, {})
        self.assertEqual(resolved["x"], 10)

    def test_list_resolution(self):
        resolved = _resolve_params({"arr": ["@n1.out", 5]}, {"n1": 7})
        self.assertEqual(resolved["arr"], [7, 5])


# ── _topological_order ────────────────────────────────────────────────────────

class TestTopologicalOrder(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_topological_order([]), [])

    def test_single(self):
        nodes = [{"id": "n1", "params": {}, "inputs": []}]
        self.assertEqual(_topological_order(nodes), ["n1"])

    def test_source_before_dependent(self):
        nodes = [
            {"id": "n1", "params": {}, "inputs": []},
            {"id": "n2", "params": {"v": "@n1.out"}, "inputs": ["n1"]},
        ]
        order = _topological_order(nodes)
        self.assertLess(order.index("n1"), order.index("n2"))

    def test_cycle_raises(self):
        nodes = [
            {"id": "n1", "params": {"v": "@n2.out"}, "inputs": ["n2"]},
            {"id": "n2", "params": {"v": "@n1.out"}, "inputs": ["n1"]},
        ]
        with self.assertRaises(ValueError):
            _topological_order(nodes)

    def test_diamond(self):
        nodes = [
            {"id": "n1", "params": {}, "inputs": []},
            {"id": "n2", "params": {"v": "@n1.out"}, "inputs": ["n1"]},
            {"id": "n3", "params": {"v": "@n1.out"}, "inputs": ["n1"]},
            {"id": "n4", "params": {"a": "@n2.out", "b": "@n3.out"}, "inputs": ["n2", "n3"]},
        ]
        order = _topological_order(nodes)
        self.assertLess(order.index("n1"), order.index("n2"))
        self.assertLess(order.index("n1"), order.index("n3"))
        self.assertLess(order.index("n2"), order.index("n4"))
        self.assertLess(order.index("n3"), order.index("n4"))


# ── BUILTIN_OPS ───────────────────────────────────────────────────────────────

class TestBuiltinOps(unittest.TestCase):
    def test_number_slider(self):
        self.assertEqual(BUILTIN_OPS["number_slider"]({"value": 3.14}), 3.14)

    def test_integer_slider_rounds(self):
        self.assertEqual(BUILTIN_OPS["integer_slider"]({"value": 3.7}), 4)

    def test_panel_passthrough(self):
        self.assertEqual(BUILTIN_OPS["panel"]({"value": "hello"}), "hello")
        self.assertIsNone(BUILTIN_OPS["panel"]({}))

    def test_series(self):
        self.assertEqual(BUILTIN_OPS["series"]({"start": 0, "count": 3, "step": 2}), [0, 2, 4])

    def test_range_endpoints(self):
        r = BUILTIN_OPS["range"]({"from": 0, "to": 1, "count": 5})
        self.assertEqual(len(r), 5)
        self.assertAlmostEqual(r[0], 0)
        self.assertAlmostEqual(r[-1], 1)

    def test_lerp_midpoint(self):
        self.assertEqual(BUILTIN_OPS["lerp"]({"a": 0, "b": 100, "t": 0.5}), 50)

    def test_expression_math(self):
        result = BUILTIN_OPS["expression"]({"expr": "x * 2", "inputs": {"x": 5}})
        self.assertEqual(result, 10)

    def test_expression_empty(self):
        self.assertIsNone(BUILTIN_OPS["expression"]({"expr": ""}))


# ── _evaluate_graph_data ──────────────────────────────────────────────────────

class TestEvaluateGraphData(unittest.TestCase):
    def test_slider_to_panel(self):
        graph = {
            "version": 1, "name": "x",
            "nodes": [
                {"id": "n1", "op": "number_slider", "params": {"value": 42}, "inputs": []},
                {"id": "n2", "op": "panel", "params": {"value": "@n1.out"}, "inputs": ["n1"]},
            ],
            "outputs": ["n2"],
        }
        r = _evaluate_graph_data(graph)
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["outputs"]["n2"], 42)

    def test_expression_uses_slider(self):
        graph = {
            "version": 1, "name": "x",
            "nodes": [
                {"id": "n1", "op": "number_slider", "params": {"value": 10}, "inputs": []},
                {"id": "n2", "op": "expression", "params": {"expr": "x * 3", "inputs": {"x": "@n1.out"}}, "inputs": ["n1"]},
            ],
            "outputs": ["n2"],
        }
        r = _evaluate_graph_data(graph)
        self.assertEqual(r["errors"], [])
        self.assertEqual(r["outputs"]["n2"], 30)

    def test_map_each_over_series(self):
        graph = {
            "version": 1, "name": "x",
            "nodes": [
                {"id": "n1", "op": "series", "params": {"start": 0, "count": 4, "step": 1}, "inputs": []},
                {"id": "n2", "op": "map_each", "params": {"array": "@n1.out", "op": "lerp", "op_params": {"a": 0, "b": 10, "t": 0.5}}, "inputs": ["n1"]},
            ],
            "outputs": ["n2"],
        }
        r = _evaluate_graph_data(graph)
        self.assertEqual(r["errors"], [])
        self.assertEqual(len(r["outputs"]["n2"]), 4)

    def test_unknown_op_error(self):
        graph = {
            "version": 1, "name": "x",
            "nodes": [{"id": "n1", "op": "bad_op", "params": {}, "inputs": []}],
            "outputs": ["n1"],
        }
        r = _evaluate_graph_data(graph)
        self.assertTrue(len(r["errors"]) > 0)
        self.assertIn("unknown op", r["errors"][0])

    def test_cycle_error(self):
        graph = {
            "version": 1, "name": "x",
            "nodes": [
                {"id": "n1", "params": {"v": "@n2.out"}, "op": "panel", "inputs": ["n2"]},
                {"id": "n2", "params": {"v": "@n1.out"}, "op": "panel", "inputs": ["n1"]},
            ],
            "outputs": [],
        }
        r = _evaluate_graph_data(graph)
        self.assertTrue(len(r["errors"]) > 0)
        self.assertIn("Cycle", r["errors"][0])

    def test_intermediate_results_not_in_outputs(self):
        graph = {
            "version": 1, "name": "x",
            "nodes": [
                {"id": "n1", "op": "number_slider", "params": {"value": 5}, "inputs": []},
                {"id": "n2", "op": "number_slider", "params": {"value": 7}, "inputs": []},
            ],
            "outputs": ["n2"],
        }
        r = _evaluate_graph_data(graph)
        self.assertIn("n1", r["intermediate"])
        self.assertNotIn("n1", r["outputs"])
        self.assertIn("n2", r["outputs"])

    def test_range_feeds_lerp(self):
        graph = {
            "version": 1, "name": "x",
            "nodes": [
                {"id": "n1", "op": "number_slider", "params": {"value": 0}, "inputs": []},
                {"id": "n2", "op": "number_slider", "params": {"value": 100}, "inputs": []},
                {"id": "n3", "op": "lerp", "params": {"a": "@n1.out", "b": "@n2.out", "t": 0.25}, "inputs": ["n1", "n2"]},
            ],
            "outputs": ["n3"],
        }
        r = _evaluate_graph_data(graph)
        self.assertEqual(r["errors"], [])
        self.assertAlmostEqual(r["outputs"]["n3"], 25.0)


if __name__ == "__main__":
    unittest.main()
