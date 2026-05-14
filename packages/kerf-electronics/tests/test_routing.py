"""
Tests for kerf_electronics/tools/routing.py — manual PCB trace routing tools.
"""
import json
import unittest

from kerf_electronics.tools.routing import (
    _get_traces,
    _set_traces,
    _trace_points,
    _set_trace_points,
    _point_to_segment_dist,
    _new_trace_id,
)
from kerf_chat.tools.registry import Registry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_circuit(*traces):
    return {"pcb_traces": list(traces)}


def _make_trace(tid, net_id, points, layer="top_copper", width=0.25):
    return {
        "type": "pcb_trace",
        "pcb_trace_id": tid,
        "net_id": net_id,
        "route": [
            {"route_type": "wire", "x": x, "y": y, "width": width, "layer": layer}
            for x, y in points
        ],
    }


async def call_tool(name, payload):
    tool = next(t for t in Registry if t.spec.name == name)
    return json.loads(await tool.run(None, json.dumps(payload).encode()))


# ---------------------------------------------------------------------------
# Unit tests — helpers
# ---------------------------------------------------------------------------

class TestHelpers(unittest.TestCase):

    def test_get_traces_from_pcb_traces_key(self):
        cj = {"pcb_traces": [{"type": "pcb_trace"}]}
        self.assertEqual(len(_get_traces(cj)), 1)

    def test_get_traces_from_traces_key(self):
        cj = {"traces": [{"type": "pcb_trace"}]}
        self.assertEqual(len(_get_traces(cj)), 1)

    def test_get_traces_empty(self):
        self.assertEqual(_get_traces({}), [])

    def test_new_trace_id_format(self):
        tid = _new_trace_id()
        self.assertTrue(tid.startswith("trace_"))
        self.assertEqual(len(tid), 14)  # "trace_" + 8 hex chars

    def test_trace_points_route_key(self):
        t = {"route": [{"x": 0, "y": 0}, {"x": 1, "y": 1}]}
        pts = _trace_points(t)
        self.assertEqual(len(pts), 2)

    def test_trace_points_points_key(self):
        t = {"points": [{"x": 0, "y": 0}]}
        self.assertEqual(len(_trace_points(t)), 1)

    def test_point_to_segment_dist_on_segment(self):
        p = {"x": 5, "y": 0}
        a = {"x": 0, "y": 0}
        b = {"x": 10, "y": 0}
        self.assertAlmostEqual(_point_to_segment_dist(p, a, b), 0.0)

    def test_point_to_segment_dist_off_segment(self):
        p = {"x": 5, "y": 3}
        a = {"x": 0, "y": 0}
        b = {"x": 10, "y": 0}
        self.assertAlmostEqual(_point_to_segment_dist(p, a, b), 3.0)


# ---------------------------------------------------------------------------
# Tool: route_trace_segments
# ---------------------------------------------------------------------------

class TestRouteTraceSegments(unittest.IsolatedAsyncioTestCase):

    async def test_add_single_segment(self):
        cj = _make_circuit()
        result = await call_tool("route_trace_segments", {
            "circuit_json": cj,
            "segments": [{"p1": {"x": 0, "y": 0}, "p2": {"x": 10, "y": 0}, "net_id": "VCC"}],
        })
        self.assertIn("circuit_json", result)
        traces = _get_traces(result["circuit_json"])
        self.assertEqual(len(traces), 1)
        self.assertEqual(len(result["added_trace_ids"]), 1)

    async def test_add_multiple_segments(self):
        cj = _make_circuit()
        result = await call_tool("route_trace_segments", {
            "circuit_json": cj,
            "segments": [
                {"p1": {"x": 0, "y": 0}, "p2": {"x": 5, "y": 0}, "net_id": "A"},
                {"p1": {"x": 5, "y": 0}, "p2": {"x": 10, "y": 0}, "net_id": "A"},
            ],
        })
        traces = _get_traces(result["circuit_json"])
        self.assertEqual(len(traces), 2)

    async def test_missing_net_id_is_error(self):
        cj = _make_circuit()
        result = await call_tool("route_trace_segments", {
            "circuit_json": cj,
            "segments": [{"p1": {"x": 0, "y": 0}, "p2": {"x": 5, "y": 0}}],
        })
        self.assertIn("error", result)

    async def test_bad_circuit_json_is_error(self):
        result = await call_tool("route_trace_segments", {
            "circuit_json": "not-a-dict",
            "segments": [{"p1": {"x": 0, "y": 0}, "p2": {"x": 5, "y": 0}, "net_id": "X"}],
        })
        self.assertIn("error", result)

    async def test_per_segment_layer_and_width(self):
        cj = _make_circuit()
        result = await call_tool("route_trace_segments", {
            "circuit_json": cj,
            "segments": [{
                "p1": {"x": 0, "y": 0}, "p2": {"x": 5, "y": 0},
                "net_id": "VCC", "layer": "bottom_copper", "width_mm": 0.5,
            }],
        })
        trace = _get_traces(result["circuit_json"])[0]
        pts = _trace_points(trace)
        self.assertEqual(pts[0]["layer"], "bottom_copper")
        self.assertAlmostEqual(pts[0]["width"], 0.5)


# ---------------------------------------------------------------------------
# Tool: delete_trace
# ---------------------------------------------------------------------------

class TestDeleteTrace(unittest.IsolatedAsyncioTestCase):

    async def test_delete_by_trace_id(self):
        t1 = _make_trace("t1", "A", [(0, 0), (5, 0)])
        t2 = _make_trace("t2", "B", [(0, 1), (5, 1)])
        cj = _make_circuit(t1, t2)
        result = await call_tool("delete_trace", {"circuit_json": cj, "trace_id": "t1"})
        traces = _get_traces(result["circuit_json"])
        self.assertEqual(len(traces), 1)
        self.assertEqual(traces[0]["pcb_trace_id"], "t2")

    async def test_delete_nonexistent_trace_is_error(self):
        cj = _make_circuit(_make_trace("t1", "A", [(0, 0), (5, 0)]))
        result = await call_tool("delete_trace", {"circuit_json": cj, "trace_id": "noexist"})
        self.assertIn("error", result)

    async def test_delete_requires_identifier(self):
        cj = _make_circuit()
        result = await call_tool("delete_trace", {"circuit_json": cj})
        self.assertIn("error", result)

    async def test_delete_by_net_and_index(self):
        t1 = _make_trace("t1", "NET1", [(0, 0), (5, 0)])
        t2 = _make_trace("t2", "NET1", [(0, 1), (5, 1)])
        cj = _make_circuit(t1, t2)
        result = await call_tool("delete_trace", {
            "circuit_json": cj, "net_id": "NET1", "index": 0,
        })
        traces = _get_traces(result["circuit_json"])
        self.assertEqual(len(traces), 1)


# ---------------------------------------------------------------------------
# Tool: split_trace
# ---------------------------------------------------------------------------

class TestSplitTrace(unittest.IsolatedAsyncioTestCase):

    async def test_split_at_midpoint(self):
        t = _make_trace("t1", "A", [(0, 0), (10, 0)])
        cj = _make_circuit(t)
        result = await call_tool("split_trace", {
            "circuit_json": cj,
            "trace_id": "t1",
            "point": {"x": 5, "y": 0},
        })
        traces = _get_traces(result["circuit_json"])
        self.assertEqual(len(traces), 2)
        self.assertIn("trace_id_a", result)
        self.assertIn("trace_id_b", result)

    async def test_split_preserves_net(self):
        t = _make_trace("t1", "MYNET", [(0, 0), (10, 0)])
        cj = _make_circuit(t)
        result = await call_tool("split_trace", {
            "circuit_json": cj, "trace_id": "t1", "point": {"x": 5, "y": 0},
        })
        for tr in _get_traces(result["circuit_json"]):
            self.assertEqual(tr.get("net_id"), "MYNET")

    async def test_split_far_from_trace_is_error(self):
        t = _make_trace("t1", "A", [(0, 0), (10, 0)])
        cj = _make_circuit(t)
        result = await call_tool("split_trace", {
            "circuit_json": cj, "trace_id": "t1", "point": {"x": 5, "y": 50},
        })
        self.assertIn("error", result)

    async def test_split_nonexistent_trace_is_error(self):
        cj = _make_circuit()
        result = await call_tool("split_trace", {
            "circuit_json": cj, "trace_id": "no", "point": {"x": 0, "y": 0},
        })
        self.assertIn("error", result)


# ---------------------------------------------------------------------------
# Tool: merge_traces
# ---------------------------------------------------------------------------

class TestMergeTraces(unittest.IsolatedAsyncioTestCase):

    async def test_merge_connected_traces(self):
        t1 = _make_trace("t1", "A", [(0, 0), (5, 0)])
        t2 = _make_trace("t2", "A", [(5, 0), (10, 0)])
        cj = _make_circuit(t1, t2)
        result = await call_tool("merge_traces", {
            "circuit_json": cj, "trace_ids": ["t1", "t2"],
        })
        traces = _get_traces(result["circuit_json"])
        self.assertEqual(len(traces), 1)
        self.assertIn("merged_trace_id", result)

    async def test_merge_different_nets_is_error(self):
        t1 = _make_trace("t1", "A", [(0, 0), (5, 0)])
        t2 = _make_trace("t2", "B", [(5, 0), (10, 0)])
        cj = _make_circuit(t1, t2)
        result = await call_tool("merge_traces", {
            "circuit_json": cj, "trace_ids": ["t1", "t2"],
        })
        self.assertIn("error", result)

    async def test_merge_disconnected_traces_is_error(self):
        t1 = _make_trace("t1", "A", [(0, 0), (5, 0)])
        t2 = _make_trace("t2", "A", [(20, 0), (25, 0)])
        cj = _make_circuit(t1, t2)
        result = await call_tool("merge_traces", {
            "circuit_json": cj, "trace_ids": ["t1", "t2"],
        })
        self.assertIn("error", result)

    async def test_merge_same_id_is_error(self):
        t1 = _make_trace("t1", "A", [(0, 0), (5, 0)])
        cj = _make_circuit(t1)
        result = await call_tool("merge_traces", {
            "circuit_json": cj, "trace_ids": ["t1", "t1"],
        })
        self.assertIn("error", result)


# ---------------------------------------------------------------------------
# Tool: move_trace_vertex
# ---------------------------------------------------------------------------

class TestMoveTraceVertex(unittest.IsolatedAsyncioTestCase):

    async def test_move_vertex_0(self):
        t = _make_trace("t1", "A", [(0, 0), (10, 0)])
        cj = _make_circuit(t)
        result = await call_tool("move_trace_vertex", {
            "circuit_json": cj,
            "trace_id": "t1",
            "vertex_index": 0,
            "new_point": {"x": -5, "y": 0},
        })
        pts = _trace_points(_get_traces(result["circuit_json"])[0])
        self.assertAlmostEqual(pts[0]["x"], -5.0)

    async def test_move_out_of_bounds_is_error(self):
        t = _make_trace("t1", "A", [(0, 0), (10, 0)])
        cj = _make_circuit(t)
        result = await call_tool("move_trace_vertex", {
            "circuit_json": cj,
            "trace_id": "t1",
            "vertex_index": 99,
            "new_point": {"x": 0, "y": 0},
        })
        self.assertIn("error", result)

    async def test_move_nonexistent_trace_is_error(self):
        cj = _make_circuit()
        result = await call_tool("move_trace_vertex", {
            "circuit_json": cj,
            "trace_id": "no",
            "vertex_index": 0,
            "new_point": {"x": 0, "y": 0},
        })
        self.assertIn("error", result)


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

class TestRoutingToolsRegistered(unittest.IsolatedAsyncioTestCase):

    async def test_all_tools_registered(self):
        names = {t.spec.name for t in Registry}
        for tool_name in (
            "route_trace_segments",
            "delete_trace",
            "split_trace",
            "merge_traces",
            "move_trace_vertex",
        ):
            self.assertIn(tool_name, names)


if __name__ == "__main__":
    unittest.main()
