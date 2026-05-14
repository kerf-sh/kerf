"""test_shove_router.py — pytest suite for the shove router LLM tool."""
import importlib.util
import sys
import types

_spec = importlib.util.spec_from_file_location(
    "tools.shove_router", "/Users/pc/code/exo/kerf/.claude/worktrees/agent-a32c4befabb8b2b49/kerf-electronics/src/kerf_electronics/tools/shove_router.py"
)
_mod = importlib.util.module_from_spec(_spec)

_reg_stub = types.ModuleType("tools.registry")
_reg_stub.ToolSpec = type("ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
_reg_stub.err_payload = lambda msg, code: __import__("json").dumps({"error": msg, "code": code})
_reg_stub.ok_payload = lambda v: __import__("json").dumps(v)
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)
_prev_registry = sys.modules.get("tools.registry")
sys.modules["tools.registry"] = _reg_stub

_spec.loader.exec_module(_mod)
_route_with_shove = _mod.route_with_shove

if _prev_registry is not None:
    sys.modules["tools.registry"] = _prev_registry
else:
    del sys.modules["tools.registry"]


def _trace(id, net_id, layer, points, width_mm=0.25):
    return {"id": id, "net_id": net_id, "layer": layer, "width_mm": width_mm, "points": points}


def _circuit(traces):
    return {"pcb_board": {"pcb_trace": traces or []}}


class TestSegmentMinDistance:
    def test_intersecting_returns_zero(self):
        seg1 = {"points": [(0, 0), (10, 0)]}
        seg2 = {"points": [(5, -5), (5, 5)]}
        d = _mod._segment_min_distance(seg1, seg2)
        assert d == 0

    def test_parallel_distance(self):
        seg1 = {"points": [(0, 0), (10, 0)]}
        seg2 = {"points": [(0, 5), (10, 5)]}
        d = _mod._segment_min_distance(seg1, seg2)
        assert abs(d - 5) < 0.001

    def test_perpendicular_offset(self):
        seg1 = {"points": [(0, 0), (10, 0)]}
        seg2 = {"points": [(0, 10), (0, 20)]}
        d = _mod._segment_min_distance(seg1, seg2)
        assert abs(d - 10) < 0.001


class TestShoveSegment:
    def test_shove_by_clearance(self):
        seg = {"points": [(0, 0), (10, 0)]}
        perp = (0, 1)
        result = _mod._shove_segment(seg, perp, 0.5)
        assert abs(result["points"][0][0] - 0) < 0.001
        assert abs(result["points"][0][1] - 0.5) < 0.001
        assert abs(result["points"][1][0] - 10) < 0.001
        assert abs(result["points"][1][1] - 0.5) < 0.001


class TestRouteWithShove:
    def test_no_conflicts_no_shove(self):
        existing = _trace("t1", "net1", "top", [(0, 0), (10, 0)])
        circuit = _circuit([existing])
        result = _route_with_shove(circuit, "top", [[20, 10], [30, 10]], 0.25)
        assert len(result["shoved_traces"]) == 0
        assert result["conflicts_resolved"] == 0
        assert result["conflicts_unresolved"] == 0

    def test_perpendicular_intersection_shoves(self):
        existing = _trace("t1", "net1", "top", [(5, 0), (5, 10)])
        circuit = _circuit([existing])
        result = _route_with_shove(circuit, "top", [[0, 5], [10, 5]], 0.5)
        assert "t1" in result["shoved_traces"]

    def test_same_net_not_shoved(self):
        existing = _trace("t1", "net1", "top", [(0, 5), (10, 5)])
        circuit = _circuit([existing])
        result = _route_with_shove(circuit, "top", [[5, 0], [5, 10]], 0.25)
        assert len(result["shoved_traces"]) > 0

    def test_different_layer_not_affected(self):
        existing = _trace("t1", "net1", "top", [(0, 5), (10, 5)])
        circuit = _circuit([existing])
        result = _route_with_shove(circuit, "bottom", [[5, 0], [5, 10]], 0.25)
        assert len(result["shoved_traces"]) == 0

    def test_returns_circuit_json(self):
        circuit = _circuit([])
        result = _route_with_shove(circuit, "top", [[0, 0], [10, 0]], 0.25)
        assert result["circuit_json"] is not None

    def test_handles_null_circuit(self):
        result = _route_with_shove(None, "top", [[0, 0], [10, 0]], 0.25)
        assert result["circuit_json"] is None
        assert len(result["shoved_traces"]) == 0

    def test_multiple_traces_all_shoved(self):
        t1 = _trace("t1", "net1", "top", [(0, 5), (10, 5)])
        t2 = _trace("t2", "net2", "top", [(0, 6), (10, 6)])
        circuit = _circuit([t1, t2])
        result = _route_with_shove(circuit, "top", [[5, 0], [5, 10]], 0.25)
        assert "t1" in result["shoved_traces"] or "t2" in result["shoved_traces"]

    def test_preserves_non_conflicting_traces(self):
        t1 = _trace("t1", "net1", "top", [(0, 0), (10, 0)])
        t2 = _trace("t2", "net2", "top", [(0, 100), (10, 100)])
        circuit = _circuit([t1, t2])
        result = _route_with_shove(circuit, "top", [[5, 50], [5, 60]], 0.25)
        assert "t2" not in result["shoved_traces"]

    def test_shoved_traces_unique(self):
        existing = _trace("t1", "net1", "top", [(0, 5), (10, 5)])
        circuit = _circuit([existing])
        result = _route_with_shove(circuit, "top", [[5, 0], [5, 10]], 0.25)
        unique = list(dict.fromkeys(result["shoved_traces"]))
        assert len(result["shoved_traces"]) == len(unique)


if __name__ == "__main__":
    import unittest
    unittest.main()
