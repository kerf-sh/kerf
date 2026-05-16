"""
Hermetic tests for kerf_cad_core.gearbox — gear-train assembly.

Coverage:
  - design_gearbox: 2-stage ratio = product of stage ratios
  - design_gearbox: output torque = input * total_ratio * total_efficiency
  - design_gearbox: speed inversely scales with ratio
  - design_gearbox: centre distance per stage = m*(z1+z2)/2  (ISO 21771 §10.1)
  - design_gearbox: single-stage baseline
  - design_gearbox: 3-stage train
  - design_gearbox: idler stage passes ratio=1 (direction reversal, no speed change)
  - design_gearbox: idler in 2-stage train (combined ratio = non-idler stage)
  - design_gearbox: undercut / interference flagged via gears.py reuse
  - design_gearbox: z < _Z_UNDERCUT with no profile shift → warning
  - design_gearbox: malformed stage → friendly error, ok=False
  - design_gearbox: missing required stage field → error
  - design_gearbox: non-positive rpm → error
  - design_gearbox: non-positive torque → error
  - design_gearbox: empty stages list → error
  - design_gearbox: stage list with non-dict element → error
  - design_gearbox: shaft table includes input shaft + one per stage
  - design_gearbox: cumulative centre distance is sum of per-stage distances
  - gearbox_ratio: 2-stage ratio = product
  - gearbox_ratio: idler stage contributes ratio=1
  - gearbox_ratio: empty list → error
  - gearbox_ratio: misformed stage → error
  - gearbox_shaft_table: returns ok + shafts list
  - gearbox_shaft_table: shaft rpms match design_gearbox
  - LLM tools: run_gearbox_design ok path
  - LLM tools: run_gearbox_ratio ok path
  - LLM tools: run_gearbox_shaft_table ok path
  - LLM tools: invalid JSON → error payload
  - LLM tools: missing stages field → error payload

Pure-Python: no OCC, no DB, no network.

Author: imranparuk
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.gearbox.train import (
    design_gearbox,
    gearbox_ratio,
    gearbox_shaft_table,
    _stage_centre_distance,
    _stage_ratio,
    _stage_interference,
)
from kerf_cad_core.gearbox.tools import (
    run_gearbox_design,
    run_gearbox_ratio,
    run_gearbox_shaft_table,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_ctx():
    try:
        from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
        return ProjectCtx(
            pool=None, storage=None,
            project_id=uuid.uuid4(), user_id=uuid.uuid4(),
            role="owner", http_client=None,
        )
    except Exception:
        return None


def _ok(raw: str) -> dict:
    d = json.loads(raw)
    assert d.get("ok") is True, f"Expected ok=True, got: {d}"
    return d


def _err_response(raw: str) -> dict:
    d = json.loads(raw)
    is_ok_false   = d.get("ok") is False
    is_err_payload = "error" in d and "code" in d
    assert is_ok_false or is_err_payload, f"Expected error response, got: {d}"
    return d


def _stage(z1: int, z2: int, m: float = 2.0, **kw) -> dict:
    """Build a minimal stage dict."""
    return {"z1": z1, "z2": z2, "module": m, **kw}


CTX = _make_ctx()


# ---------------------------------------------------------------------------
# Unit tests — train.py math helpers
# ---------------------------------------------------------------------------

class TestStageRatio:
    def test_ratio_formula(self):
        # ratio = z2 / z1
        assert _stage_ratio(20, 40) == pytest.approx(2.0)

    def test_unit_ratio(self):
        assert _stage_ratio(20, 20) == pytest.approx(1.0)

    def test_step_up(self):
        # z2 < z1 → ratio < 1 (speed increase)
        assert _stage_ratio(40, 20) == pytest.approx(0.5)


class TestStageCentreDistance:
    def test_standard_formula(self):
        # a = m*(z1+z2)/2
        assert _stage_centre_distance(2.0, 20, 40) == pytest.approx(60.0)

    def test_equal_teeth(self):
        assert _stage_centre_distance(1.5, 20, 20) == pytest.approx(30.0)

    def test_scale_with_module(self):
        a1 = _stage_centre_distance(1.0, 18, 36)
        a2 = _stage_centre_distance(2.0, 18, 36)
        assert a2 == pytest.approx(2.0 * a1)


# ---------------------------------------------------------------------------
# design_gearbox — ratio tests
# ---------------------------------------------------------------------------

class TestDesignGearboxRatio:
    def test_single_stage_ratio(self):
        stages = [_stage(20, 40)]
        r = design_gearbox(stages, 1000.0, 10.0)
        assert r["ok"] is True
        assert r["total_ratio"] == pytest.approx(2.0)

    def test_two_stage_ratio_is_product(self):
        """total_ratio = (z2_0/z1_0) * (z2_1/z1_1)"""
        stages = [_stage(20, 40), _stage(15, 45)]
        r = design_gearbox(stages, 1000.0, 10.0)
        expected = (40 / 20) * (45 / 15)   # 2.0 * 3.0 = 6.0
        assert r["ok"] is True
        assert r["total_ratio"] == pytest.approx(expected)

    def test_three_stage_ratio_is_product(self):
        stages = [_stage(20, 40), _stage(15, 45), _stage(10, 30)]
        r = design_gearbox(stages, 1000.0, 5.0)
        expected = (40 / 20) * (45 / 15) * (30 / 10)   # 2*3*3 = 18
        assert r["ok"] is True
        assert r["total_ratio"] == pytest.approx(expected)

    def test_stage_ratios_in_result(self):
        stages = [_stage(20, 40), _stage(15, 45)]
        r = design_gearbox(stages, 1000.0, 10.0)
        assert r["stages"][0]["ratio"] == pytest.approx(2.0)
        assert r["stages"][1]["ratio"] == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# design_gearbox — torque & speed relations
# ---------------------------------------------------------------------------

class TestDesignGearboxPowerTrain:
    def test_output_speed_inversely_scales_with_ratio(self):
        """n_out = n_in / total_ratio"""
        stages = [_stage(20, 40)]  # ratio = 2.0
        r = design_gearbox(stages, 1000.0, 10.0)
        assert r["output_rpm"] == pytest.approx(500.0, rel=1e-6)

    def test_output_torque_equals_input_times_ratio_times_eta(self):
        """T_out = T_in * ratio * η  (for a single stage at default η=0.98)"""
        stages = [_stage(20, 40, eta=0.98)]
        r = design_gearbox(stages, 1000.0, 10.0)
        expected = 10.0 * 2.0 * 0.98
        assert r["output_torque_nm"] == pytest.approx(expected, rel=1e-6)

    def test_two_stage_speed(self):
        stages = [_stage(20, 40), _stage(15, 45)]  # ratios 2 and 3
        r = design_gearbox(stages, 1800.0, 5.0)
        # n_out = 1800 / 6 = 300
        assert r["output_rpm"] == pytest.approx(300.0, rel=1e-6)

    def test_two_stage_torque(self):
        stages = [
            _stage(20, 40, eta=0.98),
            _stage(15, 45, eta=0.98),
        ]
        r = design_gearbox(stages, 1800.0, 5.0)
        expected = 5.0 * 2.0 * 0.98 * 3.0 * 0.98
        assert r["output_torque_nm"] == pytest.approx(expected, rel=1e-6)

    def test_total_efficiency_is_product(self):
        stages = [
            _stage(20, 40, eta=0.98),
            _stage(15, 45, eta=0.97),
        ]
        r = design_gearbox(stages, 1000.0, 10.0)
        assert r["total_efficiency"] == pytest.approx(0.98 * 0.97, rel=1e-6)

    def test_intermediate_shaft_speed(self):
        """Speed at the intermediate shaft equals n_in/ratio_stage0."""
        stages = [_stage(20, 40, shaft_in="A", shaft_out="B"),
                  _stage(15, 45, shaft_in="B", shaft_out="C")]
        r = design_gearbox(stages, 1000.0, 10.0)
        shaft_b = next(s for s in r["shafts"] if s["shaft_id"] == "B")
        assert shaft_b["rpm"] == pytest.approx(500.0, rel=1e-6)


# ---------------------------------------------------------------------------
# design_gearbox — centre distance & shaft layout
# ---------------------------------------------------------------------------

class TestDesignGearboxGeometry:
    def test_per_stage_centre_distance(self):
        """centre_distance = m*(z1+z2)/2 per ISO 21771 §10.1"""
        m, z1, z2 = 2.0, 20, 40
        stages = [_stage(z1, z2, m)]
        r = design_gearbox(stages, 1000.0, 10.0)
        expected_cd = m * (z1 + z2) / 2
        assert r["stages"][0]["centre_distance_mm"] == pytest.approx(expected_cd)

    def test_cumulative_centre_distance_is_sum(self):
        stages = [_stage(20, 40, 2.0), _stage(15, 45, 2.0)]
        r = design_gearbox(stages, 1000.0, 10.0)
        cd0 = 2.0 * (20 + 40) / 2   # 60
        cd1 = 2.0 * (15 + 45) / 2   # 60
        assert r["stages"][0]["cumulative_centre_distance_mm"] == pytest.approx(cd0)
        assert r["stages"][1]["cumulative_centre_distance_mm"] == pytest.approx(cd0 + cd1)

    def test_shaft_table_cumulative_distance(self):
        stages = [
            _stage(20, 40, 2.0, shaft_in="S0", shaft_out="S1"),
            _stage(15, 45, 2.0, shaft_in="S1", shaft_out="S2"),
        ]
        r = design_gearbox(stages, 1000.0, 10.0)
        shaft_s2 = next(s for s in r["shafts"] if s["shaft_id"] == "S2")
        expected = 2.0 * (20 + 40) / 2 + 2.0 * (15 + 45) / 2
        assert shaft_s2["cumulative_centre_distance_mm"] == pytest.approx(expected)


# ---------------------------------------------------------------------------
# design_gearbox — idler stages
# ---------------------------------------------------------------------------

class TestIdlerStage:
    def test_idler_ratio_is_one(self):
        """Idler: z2/z1 could be anything but ratio reported = 1."""
        stages = [_stage(20, 30, is_idler=True)]
        r = design_gearbox(stages, 1000.0, 10.0)
        assert r["ok"] is True
        assert r["stages"][0]["ratio"] == pytest.approx(1.0)
        assert r["total_ratio"] == pytest.approx(1.0)

    def test_idler_speed_passthrough(self):
        """Idler passes rpm unchanged."""
        stages = [_stage(20, 30, is_idler=True)]
        r = design_gearbox(stages, 1000.0, 10.0)
        assert r["output_rpm"] == pytest.approx(1000.0, rel=1e-6)

    def test_idler_in_two_stage_train(self):
        """2-stage train with idler: total ratio = non-idler stage ratio."""
        stages = [
            _stage(20, 30, is_idler=True),  # ratio=1
            _stage(20, 60),                 # ratio=3
        ]
        r = design_gearbox(stages, 1000.0, 10.0)
        assert r["total_ratio"] == pytest.approx(3.0)
        assert r["output_rpm"] == pytest.approx(1000.0 / 3.0, rel=1e-6)

    def test_idler_flagged_in_stage_result(self):
        stages = [_stage(20, 20, is_idler=True)]
        r = design_gearbox(stages, 1000.0, 5.0)
        assert r["stages"][0]["is_idler"] is True


# ---------------------------------------------------------------------------
# design_gearbox — interference / undercut via gears.py reuse
# ---------------------------------------------------------------------------

class TestInterferenceWarnings:
    def test_low_tooth_count_pinion_warns(self):
        """z1=8 < 17, no profile shift → undercut warning expected."""
        stages = [_stage(8, 40, 2.0)]
        r = design_gearbox(stages, 1000.0, 5.0)
        assert r["ok"] is True
        combined = " ".join(r["warnings"])
        assert "undercut" in combined.lower() or "8" in combined

    def test_z_above_threshold_no_undercut_warning(self):
        """Gears with large tooth counts + profile shift → no undercut warning."""
        # Use z1=25, z2=50 with x1=0.5 profile shift on the pinion so that
        # r_f > r_b; the root circle is lifted clear of the base circle.
        stages = [_stage(25, 50, 2.0, profile_shift_1=0.5)]
        r = design_gearbox(stages, 1000.0, 10.0)
        undercut_warnings = [w for w in r["warnings"] if "undercut" in w.lower()]
        assert undercut_warnings == []

    def test_warnings_prefixed_with_stage_index(self):
        """Any interference warning should be prefixed with 'stage[i]:'."""
        stages = [_stage(8, 40, 2.0)]
        r = design_gearbox(stages, 1000.0, 5.0)
        if r["warnings"]:
            assert any(w.startswith("stage[") for w in r["warnings"])

    def test_stage_interference_helper_direct(self):
        """_stage_interference returns warnings for a very small pinion."""
        warns = _stage_interference(2.0, 8, 40, 20.0, 0.0, 0.0)
        assert len(warns) > 0

    def test_stage_interference_no_warn_normal_gears(self):
        # z1=25 with x1=0.5 profile shift raises r_f above r_b → no undercut.
        warns = _stage_interference(2.0, 25, 50, 20.0, 0.5, 0.0)
        assert warns == []


# ---------------------------------------------------------------------------
# design_gearbox — validation / error handling
# ---------------------------------------------------------------------------

class TestDesignGearboxErrors:
    def test_empty_stages_list(self):
        r = design_gearbox([], 1000.0, 10.0)
        assert r["ok"] is False
        assert r["errors"]

    def test_non_positive_rpm(self):
        r = design_gearbox([_stage(20, 40)], 0.0, 10.0)
        assert r["ok"] is False

    def test_negative_rpm(self):
        r = design_gearbox([_stage(20, 40)], -100.0, 10.0)
        assert r["ok"] is False

    def test_non_positive_torque(self):
        r = design_gearbox([_stage(20, 40)], 1000.0, 0.0)
        assert r["ok"] is False

    def test_missing_z1(self):
        r = design_gearbox([{"z2": 40, "module": 2.0}], 1000.0, 10.0)
        assert r["ok"] is False
        assert any("z1" in e for e in r["errors"])

    def test_missing_module(self):
        r = design_gearbox([{"z1": 20, "z2": 40}], 1000.0, 10.0)
        assert r["ok"] is False
        assert any("module" in e for e in r["errors"])

    def test_z_too_small(self):
        r = design_gearbox([_stage(2, 40)], 1000.0, 10.0)
        assert r["ok"] is False
        assert any("z1" in e for e in r["errors"])

    def test_non_dict_stage(self):
        r = design_gearbox(["not-a-dict"], 1000.0, 10.0)
        assert r["ok"] is False

    def test_module_zero(self):
        r = design_gearbox([_stage(20, 40, 0.0)], 1000.0, 10.0)
        assert r["ok"] is False

    def test_invalid_pressure_angle(self):
        r = design_gearbox([_stage(20, 40, pressure_angle_deg=5.0)], 1000.0, 10.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# gearbox_ratio (standalone)
# ---------------------------------------------------------------------------

class TestGearboxRatio:
    def test_single_stage(self):
        r = gearbox_ratio([_stage(20, 40)])
        assert r["ok"] is True
        assert r["total_ratio"] == pytest.approx(2.0)

    def test_two_stage_product(self):
        r = gearbox_ratio([_stage(20, 40), _stage(15, 45)])
        assert r["ok"] is True
        assert r["total_ratio"] == pytest.approx(6.0)
        assert r["stage_ratios"] == pytest.approx([2.0, 3.0])

    def test_idler_contributes_one(self):
        r = gearbox_ratio([_stage(20, 40, is_idler=True), _stage(15, 45)])
        assert r["ok"] is True
        assert r["total_ratio"] == pytest.approx(3.0)
        assert r["stage_ratios"][0] == pytest.approx(1.0)

    def test_empty_stages_error(self):
        r = gearbox_ratio([])
        assert r["ok"] is False

    def test_missing_z2_error(self):
        r = gearbox_ratio([{"z1": 20, "module": 2.0}])
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# gearbox_shaft_table (standalone)
# ---------------------------------------------------------------------------

class TestGearboxShaftTable:
    def test_returns_shafts(self):
        stages = [_stage(20, 40, shaft_in="A", shaft_out="B")]
        r = gearbox_shaft_table(stages, 1000.0, 10.0)
        assert r["ok"] is True
        assert isinstance(r["shafts"], list)
        assert len(r["shafts"]) == 2  # input + output

    def test_shaft_rpms_match_design(self):
        stages = [_stage(20, 40, shaft_in="X", shaft_out="Y")]
        full = design_gearbox(stages, 1000.0, 10.0)
        table = gearbox_shaft_table(stages, 1000.0, 10.0)
        for shaft_design in full["shafts"]:
            match = next(s for s in table["shafts"]
                         if s["shaft_id"] == shaft_design["shaft_id"])
            assert match["rpm"] == pytest.approx(shaft_design["rpm"])

    def test_error_propagation(self):
        r = gearbox_shaft_table([], 1000.0, 10.0)
        assert r["ok"] is False


# ---------------------------------------------------------------------------
# LLM tool runners
# ---------------------------------------------------------------------------

class TestLLMTools:
    def test_run_gearbox_design_ok(self):
        payload = json.dumps({
            "stages": [{"z1": 20, "z2": 60, "module": 2.0}],
            "input_rpm": 1500.0,
            "input_torque": 8.0,
        }).encode()
        raw = _run(run_gearbox_design(CTX, payload))
        d = _ok(raw)
        assert d["total_ratio"] == pytest.approx(3.0)
        assert d["output_rpm"] == pytest.approx(500.0, rel=1e-5)

    def test_run_gearbox_ratio_ok(self):
        payload = json.dumps({
            "stages": [{"z1": 20, "z2": 40, "module": 2.0},
                       {"z1": 15, "z2": 60, "module": 2.0}],
        }).encode()
        raw = _run(run_gearbox_ratio(CTX, payload))
        d = _ok(raw)
        assert d["total_ratio"] == pytest.approx(8.0)

    def test_run_gearbox_shaft_table_ok(self):
        payload = json.dumps({
            "stages": [{"z1": 20, "z2": 40, "module": 2.0,
                        "shaft_in": "input", "shaft_out": "output"}],
            "input_rpm": 3000.0,
            "input_torque": 5.0,
        }).encode()
        raw = _run(run_gearbox_shaft_table(CTX, payload))
        d = _ok(raw)
        assert any(s["shaft_id"] == "output" for s in d["shafts"])

    def test_run_gearbox_design_invalid_json(self):
        raw = _run(run_gearbox_design(CTX, b"not json"))
        _err_response(raw)

    def test_run_gearbox_ratio_invalid_json(self):
        raw = _run(run_gearbox_ratio(CTX, b"{bad json}"))
        _err_response(raw)

    def test_run_gearbox_shaft_table_invalid_json(self):
        raw = _run(run_gearbox_shaft_table(CTX, b""))
        _err_response(raw)

    def test_run_gearbox_design_missing_stages(self):
        payload = json.dumps({"input_rpm": 1000.0, "input_torque": 5.0}).encode()
        raw = _run(run_gearbox_design(CTX, payload))
        _err_response(raw)

    def test_run_gearbox_ratio_missing_stages(self):
        payload = json.dumps({}).encode()
        raw = _run(run_gearbox_ratio(CTX, payload))
        _err_response(raw)


# ===========================================================================
# Externally-citable reference cases (production-confidence validation)
# Cross-checked vs Shigley 10th ed. §13-4..13-7 and ISO 21771:2007.
# ===========================================================================

from kerf_cad_core.gearbox.train import (  # noqa: E402
    design_gearbox as _ref_design_gearbox,
    gearbox_ratio as _ref_gearbox_ratio,
)


class TestGearboxExternalReferences:
    """Validated against Shigley §13-4 power-train relations & ISO 21771."""

    def test_single_stage_ratio(self):
        # ISO 21771 §3.12: i = z2/z1. z1=20, z2=60 → ratio 3.0.
        r = _ref_gearbox_ratio([{"z1": 20, "z2": 60, "module": 2.0}])
        assert r["total_ratio"] == pytest.approx(3.0, rel=1e-12)

    def test_compound_train_ratio(self):
        # Shigley §13-4: total ratio = product of stage ratios.
        # (60/20)·(50/25) = 3·2 = 6.
        r = _ref_gearbox_ratio([
            {"z1": 20, "z2": 60, "module": 2.0},
            {"z1": 25, "z2": 50, "module": 3.0},
        ])
        assert r["total_ratio"] == pytest.approx(6.0, rel=1e-12)

    def test_idler_ratio_unity(self):
        # Shigley §13-4: an idler contributes ratio 1 (direction reversal only).
        r = _ref_gearbox_ratio([
            {"z1": 20, "z2": 40, "module": 2.0},
            {"z1": 30, "z2": 30, "module": 2.0, "is_idler": True},
        ])
        assert r["total_ratio"] == pytest.approx(2.0, rel=1e-12)

    def test_output_speed_relation(self):
        # Kinematic: n_out = n_in / ratio. 1500 rpm, ratio 3 → 500 rpm.
        r = _ref_design_gearbox([{"z1": 20, "z2": 60, "module": 2.0}], 1500.0, 10.0)
        assert r["output_rpm"] == pytest.approx(500.0, rel=1e-9)

    def test_output_torque_relation(self):
        # Shigley §13-4: T_out = T_in · ratio · η.  ratio=3, η=0.98.
        r = _ref_design_gearbox([{"z1": 20, "z2": 60, "module": 2.0, "eta": 0.98}], 1500.0, 10.0)
        assert r["output_torque_nm"] == pytest.approx(10.0 * 3.0 * 0.98, rel=1e-6)

    def test_power_conservation(self):
        # Power out = power in × η.  P = T·ω.
        r = _ref_design_gearbox([{"z1": 20, "z2": 60, "module": 2.0, "eta": 0.98}], 1500.0, 10.0)
        w_in = 1500.0 * 2 * math.pi / 60.0
        w_out = r["output_rpm"] * 2 * math.pi / 60.0
        p_in = 10.0 * w_in
        p_out = r["output_torque_nm"] * w_out
        assert p_out == pytest.approx(p_in * 0.98, rel=1e-6)

    def test_centre_distance_iso21771(self):
        # ISO 21771 §10.1: a = m(z1+z2)/2. m=2, z1=20, z2=60 → a=80 mm.
        r = _ref_design_gearbox([{"z1": 20, "z2": 60, "module": 2.0}], 1000.0, 5.0)
        assert r["stages"][0]["centre_distance_mm"] == pytest.approx(80.0, rel=1e-12)

    def test_total_efficiency_product(self):
        # Two stages η=0.98 each → η_total = 0.98² = 0.9604.
        r = _ref_design_gearbox([
            {"z1": 20, "z2": 40, "module": 2.0, "eta": 0.98},
            {"z1": 20, "z2": 40, "module": 2.0, "eta": 0.98},
        ], 1000.0, 5.0)
        assert r["total_efficiency"] == pytest.approx(0.98 * 0.98, rel=1e-9)

    def test_three_stage_ratio(self):
        # Shigley §13-4: (3)(3)(3) = 27 compound reduction.
        r = _ref_gearbox_ratio([
            {"z1": 17, "z2": 51, "module": 2.0},
            {"z1": 17, "z2": 51, "module": 2.0},
            {"z1": 17, "z2": 51, "module": 2.0},
        ])
        assert r["total_ratio"] == pytest.approx(27.0, rel=1e-9)

    def test_cumulative_centre_distance(self):
        # Geometry: cumulative CD = Σ stage CD.
        # Stage1: 2·(20+40)/2=60; Stage2: 3·(25+35)/2=90 → cumulative 150.
        r = _ref_design_gearbox([
            {"z1": 20, "z2": 40, "module": 2.0},
            {"z1": 25, "z2": 35, "module": 3.0},
        ], 1000.0, 5.0)
        assert r["stages"][-1]["cumulative_centre_distance_mm"] == pytest.approx(150.0, rel=1e-9)
