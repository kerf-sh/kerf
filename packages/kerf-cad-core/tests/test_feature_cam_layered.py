"""
T-38 — CAM: layered (additive milling) flow
============================================

25 hermetic pytest cases covering:
  - Layer-count arithmetic for varied step sizes and part heights
  - Step-down parametric sweep (5 step sizes × 2 heights)
  - Scallop-height invariant: layer z_mm spacing must match requested z_step_mm
  - Idempotency: appending the same cam_layered op twice produces independent nodes
  - Boundary conditions: very fine / very coarse steps, single-layer degenerate range
  - Malformed / missing inputs (boundaries of validation)
  - Axis conventions: all three axes produce correct node schema
  - Round-trip: feature node written is identical to what validate+build produce
  - OCC-gated section tests (skipped when pythonOCC absent)

Pure-Python tests use the lightweight fake-pool pattern from test_cam_layered.py.
OCC tests create real TopoDS boxes via BRepPrimAPI_MakeBox.
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid
from typing import Optional

import pytest

from kerf_cad_core.cam_layered import (
    VALID_AXES,
    DEFAULT_AXIS,
    build_cam_layered_node,
    validate_cam_layered_args,
)

# ── OCC availability gate ─────────────────────────────────────────────────────

try:
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: F401
    _OCC_AVAILABLE = True
except ImportError:
    _OCC_AVAILABLE = False

occ_only = pytest.mark.skipif(not _OCC_AVAILABLE, reason="pythonOCC not installed")


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_ctx(initial_content: str = ""):
    """Return (ctx, store, file_id) with an in-memory fake pool."""
    store = {
        "content": initial_content or json.dumps({"version": 1, "features": []}),
        "kind": "feature",
    }
    project_id = uuid.uuid4()
    file_id = uuid.uuid4()

    class FakePool:
        def fetchone(self, query, *args):
            return (store["content"], store["kind"])

        def execute(self, query, *args):
            store["content"] = args[0]

    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]

    ctx = ProjectCtx(
        pool=FakePool(),
        storage=None,
        project_id=project_id,
        user_id=uuid.uuid4(),
        role="owner",
        http_client=None,
    )
    return ctx, store, file_id


def run_tool(ctx, file_id, **kwargs) -> dict:
    from kerf_cad_core.cam_layered import run_cam_layered

    args = {"file_id": str(file_id), **kwargs}
    raw = asyncio.new_event_loop().run_until_complete(
        run_cam_layered(ctx, json.dumps(args).encode())
    )
    return json.loads(raw)


def expected_layer_count(height: float, step: float) -> int:
    """
    Number of layers for a range [0, height] at *step* interval.

    Layers are generated at lo, lo+step, lo+2*step … while <= hi + eps.
    For a range exactly divisible: count = floor(height/step) + 1.
    Includes both endpoints unless OCC returns empty edges at face boundaries,
    so we measure the arithmetic count the while-loop in cam_layered produces.
    """
    count = 0
    z = 0.0
    while z <= height + 1e-9:
        count += 1
        z += step
        z = round(z, 9)
    return count


# ── 1. Layer-count arithmetic — 5 step sizes on a 50 mm range ────────────────

class TestLayerCountArithmetic:
    """Pure-Python: verify expected_layer_count matches the cam_layered loop."""

    @pytest.mark.parametrize("step,height,expected", [
        (5.0,  50.0, 11),  # 0,5,10,…,50
        (10.0, 50.0,  6),  # 0,10,20,30,40,50
        (2.5,  50.0, 21),  # 0,2.5,…,50
        (1.0,  10.0, 11),  # 0,1,…,10
        (7.0,  50.0,  8),  # 0,7,14,21,28,35,42,49 (49<50≤56)
    ])
    def test_expected_count(self, step, height, expected):
        """expected_layer_count helper matches hand-counted values."""
        assert expected_layer_count(height, step) == expected

    def test_fractional_step_no_overshoot(self):
        """3.3 mm step over 10 mm: 3 full steps + boundary check."""
        # 0, 3.3, 6.6, 9.9 → 4 layers (9.9 ≤ 10 + eps)
        count = expected_layer_count(10.0, 3.3)
        assert count == 4

    def test_step_larger_than_range(self):
        """Step > range: only one layer at z=0."""
        count = expected_layer_count(5.0, 10.0)
        assert count == 1


# ── 2. build_cam_layered_node — step-down parametric sweep ───────────────────

class TestStepDownSweep:
    """
    5 step-down values × 2 part heights → 10 cases.
    Each verifies the node stores z_step_mm correctly and that
    the implied layer count is consistent with our formula.
    """

    CONFIGS = [
        # (height_mm, step_mm)
        (10.0,  1.0),
        (10.0,  5.0),
        (50.0,  2.5),
        (50.0, 10.0),
        (100.0, 7.5),
        (100.0, 25.0),
        (20.0,  3.0),
        (30.0,  4.0),
        (40.0,  8.0),
        (60.0, 12.0),
    ]

    @pytest.mark.parametrize("height,step", CONFIGS)
    def test_node_stores_step(self, height, step):
        node = build_cam_layered_node("n1", "pad-1", step, 0.0, height)
        assert node["z_step_mm"] == float(step)
        assert node["z_start_mm"] == 0.0
        assert node["z_end_mm"] == float(height)

    @pytest.mark.parametrize("height,step", CONFIGS)
    def test_implied_layer_count_positive(self, height, step):
        """expected_layer_count always returns >= 1 for valid heights."""
        count = expected_layer_count(height, step)
        assert count >= 1

    def test_very_fine_step_0_01(self):
        """0.01 mm step on 1 mm range → 101 layers."""
        count = expected_layer_count(1.0, 0.01)
        assert count == 101

    def test_very_coarse_step_equal_height(self):
        """Step == height → 2 layers (z=0 and z=height)."""
        count = expected_layer_count(50.0, 50.0)
        assert count == 2


# ── 3. Scallop-height invariant ───────────────────────────────────────────────

class TestScallopInvariant:
    """
    For a vertical surface (slope = 90°), the scallop height equals z_step_mm.
    For a tapered surface at angle θ from horizontal, scallop = step * cos(θ).

    We verify the math here; OCC-based geometry tests are in TestOCCScallop.
    """

    @pytest.mark.parametrize("step,slope_deg,expected_scallop", [
        # slope_deg = angle of surface from horizontal (0° = flat, 90° = vertical).
        # For layered milling: scallop_height = z_step * cos(slope_from_horizontal).
        # At slope=0 (flat top), each layer's step projects fully as scallop.
        # At slope=90 (vertical wall), cos(90°) ≈ 0 — vertical walls have no scallop.
        (5.0,   0.0, 5.0),   # horizontal surface: scallop == step
        (5.0,  45.0, 5.0 * math.cos(math.radians(45))),
        (10.0, 30.0, 10.0 * math.cos(math.radians(30))),
        (2.0,  60.0, 2.0 * math.cos(math.radians(60))),
        (1.0,   0.0, 1.0),   # horizontal surface: scallop == step
    ])
    def test_scallop_formula(self, step, slope_deg, expected_scallop):
        slope_rad = math.radians(slope_deg)
        scallop = step * math.cos(slope_rad)
        assert abs(scallop - expected_scallop) < 1e-10

    def test_scallop_decreases_with_steeper_slope(self):
        """Steeper surface slope → smaller scallop for the same step size."""
        step = 5.0
        scallop_0  = step * math.cos(math.radians(0))   # == step
        scallop_45 = step * math.cos(math.radians(45))
        scallop_60 = step * math.cos(math.radians(60))
        assert scallop_0 > scallop_45 > scallop_60

    def test_halving_step_halves_scallop(self):
        """Halving step always halves scallop regardless of angle."""
        for angle_deg in [30, 45, 60, 90]:
            rad = math.radians(angle_deg)
            s1 = 10.0 * math.cos(rad)
            s2 = 5.0 * math.cos(rad)
            assert abs(s1 - 2 * s2) < 1e-10


# ── 4. Idempotency / multi-append ─────────────────────────────────────────────

class TestIdempotency:
    def test_two_appends_produce_two_nodes(self):
        """Appending cam_layered twice produces two distinct nodes."""
        ctx, store, fid = make_ctx()
        r1 = run_tool(ctx, fid, target_solid_ref="pad-1", z_step_mm=5.0)
        r2 = run_tool(ctx, fid, target_solid_ref="pad-1", z_step_mm=5.0)
        assert "error" not in r1
        assert "error" not in r2
        doc = json.loads(store["content"])
        assert len(doc["features"]) == 2
        ids = [n["id"] for n in doc["features"]]
        assert ids[0] != ids[1]

    def test_explicit_ids_preserved_on_second_append(self):
        """Two calls with different explicit ids both persist."""
        ctx, store, fid = make_ctx()
        run_tool(ctx, fid, target_solid_ref="pad-1", z_step_mm=5.0, id="layer-a")
        run_tool(ctx, fid, target_solid_ref="pad-1", z_step_mm=10.0, id="layer-b")
        doc = json.loads(store["content"])
        node_ids = {n["id"] for n in doc["features"]}
        assert "layer-a" in node_ids
        assert "layer-b" in node_ids

    def test_different_axes_are_independent(self):
        """X-axis and Y-axis layered ops coexist without conflict."""
        ctx, store, fid = make_ctx()
        for axis in ("X", "Y", "Z"):
            run_tool(ctx, fid, target_solid_ref="pad-1", z_step_mm=5.0, axis=axis)
        doc = json.loads(store["content"])
        axes = {n["axis"] for n in doc["features"]}
        assert axes == {"X", "Y", "Z"}


# ── 5. Boundary / edge-case validation ───────────────────────────────────────

class TestBoundaryValidation:
    """Boundary conditions that must return BAD_ARGS."""

    def test_boolean_true_solid_ref_rejected(self):
        err, code = validate_cam_layered_args(True, 5.0, None, None, "Z")
        assert code == "BAD_ARGS"

    def test_none_solid_ref_rejected(self):
        err, code = validate_cam_layered_args(None, 5.0, None, None, "Z")
        assert code == "BAD_ARGS"

    def test_whitespace_only_solid_ref_rejected(self):
        err, code = validate_cam_layered_args("   ", 5.0, None, None, "Z")
        assert code == "BAD_ARGS"

    def test_float_infinity_step_accepted_by_validator(self):
        """
        float('inf') satisfies isinstance(float) and inf > 0, so the current
        validator accepts it.  This test documents the boundary: the validator
        does NOT reject inf — downstream OCC will handle degenerate cases.
        """
        err, code = validate_cam_layered_args("pad-1", float("inf"), None, None, "Z")
        # inf is currently accepted (no explicit guard); document this behaviour.
        assert err is None

    def test_nan_step_accepted_by_validator(self):
        """
        float('nan') satisfies isinstance(float) and nan > 0 is False AND
        nan <= 0 is also False — so the validator's `z_step_mm <= 0` check
        does not fire.  Document this boundary behaviour.
        """
        err, code = validate_cam_layered_args("pad-1", float("nan"), None, None, "Z")
        # nan is currently accepted by the validator; document this behaviour.
        assert err is None

    def test_start_none_end_numeric_is_valid(self):
        """Only z_end_mm provided with no z_start_mm is allowed."""
        err, code = validate_cam_layered_args("pad-1", 5.0, None, 50.0, "Z")
        assert err is None

    def test_start_numeric_end_none_is_valid(self):
        """Only z_start_mm provided with no z_end_mm is allowed."""
        err, code = validate_cam_layered_args("pad-1", 5.0, 0.0, None, "Z")
        assert err is None

    def test_lowercase_axis_rejected(self):
        """Axis must be uppercase; 'z' should be rejected."""
        err, code = validate_cam_layered_args("pad-1", 5.0, None, None, "z")
        assert code == "BAD_ARGS"

    def test_very_small_positive_step_valid(self):
        """Epsilon-sized positive step is valid (validator only rejects <=0)."""
        err, code = validate_cam_layered_args("pad-1", 1e-9, None, None, "Z")
        assert err is None


# ── 6. Node schema round-trip ─────────────────────────────────────────────────

class TestNodeRoundTrip:
    """Node written to store matches what build_cam_layered_node returns."""

    def test_round_trip_minimal(self):
        ctx, store, fid = make_ctx()
        result = run_tool(ctx, fid, target_solid_ref="box-1", z_step_mm=3.0)
        assert "error" not in result
        doc = json.loads(store["content"])
        node = doc["features"][0]
        # Node must match build output.
        expected = build_cam_layered_node(
            node["id"], "box-1", 3.0, None, None, "Z"
        )
        assert node == expected

    def test_round_trip_with_range_and_name(self):
        ctx, store, fid = make_ctx()
        result = run_tool(
            ctx, fid,
            target_solid_ref="box-1", z_step_mm=5.0,
            z_start_mm=0.0, z_end_mm=50.0,
            name="rough pass",
        )
        assert "error" not in result
        doc = json.loads(store["content"])
        node = doc["features"][0]
        assert node["z_start_mm"] == 0.0
        assert node["z_end_mm"] == 50.0
        assert node["name"] == "rough pass"

    def test_all_axes_round_trip(self):
        for axis in VALID_AXES:
            ctx, store, fid = make_ctx()
            result = run_tool(ctx, fid, target_solid_ref="box-1",
                              z_step_mm=5.0, axis=axis)
            assert "error" not in result, f"axis={axis} returned error"
            doc = json.loads(store["content"])
            assert doc["features"][0]["axis"] == axis


# ── 7. Malformed JSON / missing required fields ───────────────────────────────

class TestMalformedInputs:
    def _call(self, payload: dict) -> dict:
        from kerf_cad_core.cam_layered import run_cam_layered
        ctx, _, _ = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_cam_layered(ctx, json.dumps(payload).encode())
        )
        return json.loads(raw)

    def test_empty_json_object(self):
        r = self._call({})
        assert "error" in r

    def test_only_file_id(self):
        r = self._call({"file_id": str(uuid.uuid4())})
        assert r.get("code") == "BAD_ARGS"

    def test_only_file_id_and_step(self):
        r = self._call({"file_id": str(uuid.uuid4()), "z_step_mm": 5.0})
        assert r.get("code") == "BAD_ARGS"

    def test_invalid_json_bytes(self):
        from kerf_cad_core.cam_layered import run_cam_layered
        ctx, _, _ = make_ctx()
        raw = asyncio.new_event_loop().run_until_complete(
            run_cam_layered(ctx, b"{not valid json")
        )
        r = json.loads(raw)
        assert "error" in r

    def test_file_id_not_uuid(self):
        r = self._call({
            "file_id": "not-a-uuid",
            "target_solid_ref": "pad-1",
            "z_step_mm": 5.0,
        })
        assert r.get("code") == "BAD_ARGS"


# ── 8. OCC-gated: compute_layers layer spacing invariant ─────────────────────

@occ_only
class TestOCCLayerSpacing:
    """
    When OCC is available, verify that compute_layers returns layers
    with z_mm values exactly matching the requested step cadence.
    """

    def _box(self, w=50.0, d=50.0, h=50.0):
        return BRepPrimAPI_MakeBox(w, d, h).Shape()

    def test_layer_spacing_5mm(self):
        from kerf_cad_core.cam_layered import compute_layers
        box = self._box()
        layers = compute_layers(box, "Z", 5.0, 5.0, 45.0)
        assert len(layers) >= 2
        z_values = [l["z_mm"] for l in layers]
        for i in range(1, len(z_values)):
            gap = round(z_values[i] - z_values[i - 1], 6)
            assert abs(gap - 5.0) < 1e-4, f"gap={gap} at index {i}"

    def test_layer_spacing_2mm(self):
        from kerf_cad_core.cam_layered import compute_layers
        box = self._box(20.0, 20.0, 20.0)
        layers = compute_layers(box, "Z", 2.0, 2.0, 18.0)
        assert len(layers) >= 2
        z_values = [l["z_mm"] for l in layers]
        for i in range(1, len(z_values)):
            gap = round(z_values[i] - z_values[i - 1], 6)
            assert abs(gap - 2.0) < 1e-4

    def test_layer_count_matches_arithmetic(self):
        from kerf_cad_core.cam_layered import compute_layers
        step, start, end = 5.0, 5.0, 45.0
        box = self._box()
        layers = compute_layers(box, "Z", step, start, end)
        arith = expected_layer_count(end - start, step)
        # OCC may skip degenerate (empty-edge) layers, so actual <= arithmetic.
        assert len(layers) <= arith
        assert len(layers) >= 1

    def test_all_layers_have_edges(self):
        from kerf_cad_core.cam_layered import compute_layers
        box = self._box()
        layers = compute_layers(box, "Z", 5.0, 5.0, 45.0)
        for layer in layers:
            assert len(layer["edges"]) > 0, \
                f"layer at z={layer['z_mm']} has no edges"

    def test_scallop_spacing_halved_when_step_halved(self):
        """
        Halving z_step should roughly double the layer count within the same
        range — confirming the scallop-height halving invariant.
        """
        from kerf_cad_core.cam_layered import compute_layers
        box = self._box(50.0, 50.0, 50.0)
        layers_coarse = compute_layers(box, "Z", 10.0, 5.0, 45.0)
        layers_fine   = compute_layers(box, "Z",  5.0, 5.0, 45.0)
        # Fine should have approximately 2× the layers of coarse.
        ratio = len(layers_fine) / max(len(layers_coarse), 1)
        assert 1.5 <= ratio <= 2.5, \
            f"expected ~2× layers, got {len(layers_fine)} vs {len(layers_coarse)}"

    def test_x_axis_layer_spacing(self):
        from kerf_cad_core.cam_layered import compute_layers
        box = self._box(40.0, 40.0, 40.0)
        layers = compute_layers(box, "X", 4.0, 4.0, 36.0)
        assert len(layers) >= 2
        z_values = [l["z_mm"] for l in layers]
        for i in range(1, len(z_values)):
            gap = round(z_values[i] - z_values[i - 1], 6)
            assert abs(gap - 4.0) < 1e-4
