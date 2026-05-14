"""
Tests for length_tuning.py LLM tools.

Uses importlib.util.spec_from_file_location + a tools.registry stub to avoid
triggering the full tools package init (which requires a live DB/env).
"""
import importlib.util
import json
import math
import sys
import types
import pytest


# ── Stub tools.registry ───────────────────────────────────────────────────────

_reg_stub = types.ModuleType("tools.registry")
_reg_stub.ToolSpec    = type("ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
_reg_stub.err_payload = lambda msg, code: json.dumps({"error": msg, "code": code})
_reg_stub.ok_payload  = lambda v: json.dumps(v)
_reg_stub.register    = lambda spec, write=False: (lambda fn: fn)

_prev_registry = sys.modules.get("tools.registry")
sys.modules["tools.registry"] = _reg_stub

_spec = importlib.util.spec_from_file_location(
    "tools.length_tuning",
    "/Users/pc/code/exo/kerf/.claude/worktrees/agent-a32c4befabb8b2b49/kerf-electronics/src/kerf_electronics/tools/length_tuning.py",
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

# Restore registry
if _prev_registry is not None:
    sys.modules["tools.registry"] = _prev_registry
else:
    sys.modules.pop("tools.registry", None)

# Internal helpers
_trace_length      = _mod._trace_length
_generate_meander  = _mod._generate_meander
_apply_meander     = _mod._apply_meander
_differential_skew = _mod._differential_skew

# LLM tool functions
set_trace_target_length = _mod.set_trace_target_length
tune_trace_to_target    = _mod.tune_trace_to_target
report_diff_pair_skew   = _mod.report_diff_pair_skew
match_diff_pair         = _mod.match_diff_pair


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def board_with_pairs(pairs):
    return {"type": "pcb_board", "width": 100, "height": 100, "differential_pairs": pairs}


def make_trace(points, net_id="SIG", trace_id="t1", target_length_mm=None):
    t = {"type": "pcb_trace", "id": trace_id, "net_id": net_id, "points": points}
    if target_length_mm is not None:
        t["target_length_mm"] = target_length_mm
    return t


def path_length(points):
    total = 0.0
    for i in range(len(points) - 1):
        dx = points[i + 1]["x"] - points[i]["x"]
        dy = points[i + 1]["y"] - points[i]["y"]
        total += math.sqrt(dx * dx + dy * dy)
    return total


async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ── _trace_length unit tests ──────────────────────────────────────────────────

def test_trace_length_single_segment():
    t = make_trace([{"x": 0, "y": 0}, {"x": 10, "y": 0}])
    assert abs(_trace_length(t) - 10.0) < 1e-9


def test_trace_length_two_segments():
    # (0,0)→(3,0)→(3,4) = 3+4 = 7
    t = make_trace([{"x": 0, "y": 0}, {"x": 3, "y": 0}, {"x": 3, "y": 4}])
    assert abs(_trace_length(t) - 7.0) < 1e-9


def test_trace_length_diagonal_345():
    t = make_trace([{"x": 0, "y": 0}, {"x": 3, "y": 4}])
    assert abs(_trace_length(t) - 5.0) < 1e-9


def test_trace_length_empty_returns_zero():
    assert _trace_length(make_trace([])) == 0.0
    assert _trace_length(make_trace([{"x": 0, "y": 0}])) == 0.0


# ── _generate_meander unit tests ──────────────────────────────────────────────

def test_generate_meander_serpentine_length():
    start = {"x": 0, "y": 0}
    end = {"x": 20, "y": 0}
    target = 30.0
    pts = _generate_meander(start, end, target, "serpentine", 1.0, 2.0)
    actual = path_length(pts)
    assert actual >= target * 0.99


def test_generate_meander_accordion_length():
    start = {"x": 0, "y": 0}
    end = {"x": 20, "y": 0}
    target = 30.0
    pts = _generate_meander(start, end, target, "accordion", 1.0, 2.0)
    actual = path_length(pts)
    assert actual >= target * 0.85


def test_generate_meander_trombone_length():
    start = {"x": 0, "y": 0}
    end = {"x": 20, "y": 0}
    target = 30.0
    pts = _generate_meander(start, end, target, "trombone", 2.0)
    actual = path_length(pts)
    assert actual >= target * 0.75


def test_generate_meander_endpoints_preserved():
    start = {"x": 0, "y": 0}
    end = {"x": 20, "y": 0}
    for style in ("serpentine", "accordion", "trombone"):
        pts = _generate_meander(start, end, 35.0, style, 1.0, 2.0)
        assert abs(pts[0]["x"] - start["x"]) < 1e-9
        assert abs(pts[0]["y"] - start["y"]) < 1e-9
        assert abs(pts[-1]["x"] - end["x"]) < 1e-9
        assert abs(pts[-1]["y"] - end["y"]) < 1e-9


def test_generate_meander_refuses_when_target_too_short():
    start = {"x": 0, "y": 0}
    end = {"x": 20, "y": 0}
    try:
        _generate_meander(start, end, 10.0, "serpentine", 1.0, 2.0)
        assert False, "Expected ValueError"
    except ValueError:
        pass


def test_generate_meander_straight_when_target_equals_distance():
    start = {"x": 0, "y": 0}
    end = {"x": 20, "y": 0}
    pts = _generate_meander(start, end, 20.0, "serpentine", 1.0, 2.0)
    assert len(pts) == 2


# ── _differential_skew unit tests ─────────────────────────────────────────────

def test_differential_skew_equal_pair():
    elements = [
        board_with_pairs([{"name": "USB", "net_p_id": "USB_P", "net_n_id": "USB_N"}]),
        make_trace([{"x": 0, "y": 0}, {"x": 10, "y": 0}], net_id="USB_P"),
        make_trace([{"x": 0, "y": 1}, {"x": 10, "y": 1}], net_id="USB_N"),
    ]
    r = _differential_skew(elements, "USB")
    assert abs(r["delta_mm"]) < 1e-9


def test_differential_skew_unequal_pair():
    elements = [
        board_with_pairs([{"name": "DDR", "net_p_id": "DQ_P", "net_n_id": "DQ_N"}]),
        make_trace([{"x": 0, "y": 0}, {"x": 15, "y": 0}], net_id="DQ_P"),
        make_trace([{"x": 0, "y": 1}, {"x": 10, "y": 1}], net_id="DQ_N"),
    ]
    r = _differential_skew(elements, "DDR")
    assert abs(r["delta_mm"] - 5.0) < 1e-9


def test_differential_skew_missing_pair():
    elements = [board_with_pairs([])]
    r = _differential_skew(elements, "GHOST")
    assert "error" in r


def test_differential_skew_missing_board_key():
    elements = [{"type": "pcb_board", "width": 50, "height": 50}]
    r = _differential_skew(elements, "X")
    assert "error" in r


# ── LLM tool tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_set_trace_target_length_ok():
    t = make_trace([{"x": 0, "y": 0}, {"x": 10, "y": 0}], trace_id="tr1")
    r = await call(set_trace_target_length, circuit_json=[t], trace_id="tr1", target_length_mm=20.0)
    elems = r["circuit_json"]
    trace = next(e for e in elems if e.get("id") == "tr1")
    assert trace["target_length_mm"] == 20.0


@pytest.mark.asyncio
async def test_set_trace_target_length_not_found():
    t = make_trace([{"x": 0, "y": 0}, {"x": 10, "y": 0}], trace_id="tr1")
    r = await call(set_trace_target_length, circuit_json=[t], trace_id="NOPE", target_length_mm=20.0)
    assert "error" in r


@pytest.mark.asyncio
async def test_tune_trace_to_target_increases_length():
    t = make_trace(
        [{"x": 0, "y": 0}, {"x": 20, "y": 0}],
        trace_id="tr1",
        target_length_mm=30.0,
    )
    r = await call(tune_trace_to_target, circuit_json=[t], trace_id="tr1",
                   style="serpentine", amplitude_mm=1.0)
    assert r["new_length_mm"] > 29.0
    assert "circuit_json" in r


@pytest.mark.asyncio
async def test_report_diff_pair_skew_ok():
    circuit = [
        board_with_pairs([{"name": "USB", "net_p_id": "USB_P", "net_n_id": "USB_N"}]),
        make_trace([{"x": 0, "y": 0}, {"x": 12, "y": 0}], net_id="USB_P"),
        make_trace([{"x": 0, "y": 1}, {"x": 10, "y": 1}], net_id="USB_N"),
    ]
    r = await call(report_diff_pair_skew, circuit_json=circuit, pair_name="USB")
    assert abs(r["delta_mm"] - 2.0) < 1e-9
    assert r["pair_name"] == "USB"


@pytest.mark.asyncio
async def test_report_diff_pair_skew_missing():
    circuit = [board_with_pairs([])]
    r = await call(report_diff_pair_skew, circuit_json=circuit, pair_name="X")
    assert "error" in r


@pytest.mark.asyncio
async def test_match_diff_pair_reduces_skew():
    circuit = [
        board_with_pairs([{
            "name": "USB", "net_p_id": "USB_P", "net_n_id": "USB_N", "skew_max_mm": 0.1
        }]),
        make_trace([{"x": 0, "y": 0}, {"x": 20, "y": 0}], net_id="USB_P", trace_id="tp"),
        make_trace([{"x": 0, "y": 1}, {"x": 15, "y": 1}], net_id="USB_N", trace_id="tn"),
    ]
    r = await call(match_diff_pair, circuit_json=circuit, pair_name="USB",
                   style="serpentine", amplitude_mm=0.5, skew_max_mm=0.1)
    assert r["delta_mm"] <= 0.15
    assert r["tuned_net"] == "USB_N"


@pytest.mark.asyncio
async def test_match_diff_pair_no_op_when_within_tolerance():
    circuit = [
        board_with_pairs([{
            "name": "USB", "net_p_id": "USB_P", "net_n_id": "USB_N", "skew_max_mm": 1.0
        }]),
        make_trace([{"x": 0, "y": 0}, {"x": 10, "y": 0}], net_id="USB_P", trace_id="tp"),
        make_trace([{"x": 0, "y": 1}, {"x": 10.05, "y": 1}], net_id="USB_N", trace_id="tn"),
    ]
    r = await call(match_diff_pair, circuit_json=circuit, pair_name="USB",
                   style="serpentine", amplitude_mm=0.5, skew_max_mm=1.0)
    assert r["tuned_net"] is None
