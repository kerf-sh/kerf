"""
Dispatch tests for the 4 new composites LLM tools:
  composites_drape / composites_interlaminar / composites_thermal / composites_failure_depth

Each test calls the async handler directly and verifies the JSON payload.
"""

from __future__ import annotations

import asyncio
import json
import pytest

from kerf_composites.tools import (
    composites_drape_spec, run_composites_drape,
    composites_interlaminar_spec, run_composites_interlaminar,
    composites_thermal_spec, run_composites_thermal,
    composites_failure_depth_spec, run_composites_failure_depth,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class _Ctx:
    pass


CTX = _Ctx()

# ---------------------------------------------------------------------------
# Shared ply stack — [0/90/0] T300/5208, 3 × 0.125 mm
# ---------------------------------------------------------------------------

_PLIES_0_90_0 = [
    {"angle": 0.0, "E1": 181.0, "E2": 10.3, "G12": 7.17, "nu12": 0.28,
     "thickness": 0.125, "Xt": 1500.0, "Xc": 1500.0, "Yt": 40.0, "Yc": 246.0, "S12": 68.0},
    {"angle": 90.0, "E1": 181.0, "E2": 10.3, "G12": 7.17, "nu12": 0.28,
     "thickness": 0.125, "Xt": 1500.0, "Xc": 1500.0, "Yt": 40.0, "Yc": 246.0, "S12": 68.0},
    {"angle": 0.0, "E1": 181.0, "E2": 10.3, "G12": 7.17, "nu12": 0.28,
     "thickness": 0.125, "Xt": 1500.0, "Xc": 1500.0, "Yt": 40.0, "Yc": 246.0, "S12": 68.0},
]


# ---------------------------------------------------------------------------
# Spec sanity
# ---------------------------------------------------------------------------

class TestSpecs:
    def test_all_specs_have_names(self):
        for spec in [
            composites_drape_spec,
            composites_interlaminar_spec,
            composites_thermal_spec,
            composites_failure_depth_spec,
        ]:
            assert spec.name.startswith("composites_"), spec.name
            assert len(spec.description) > 20
            assert "type" in spec.input_schema


# ---------------------------------------------------------------------------
# composites_drape
# ---------------------------------------------------------------------------

class TestCompositesDrape:
    def test_flat_surface_zero_shear(self):
        result = json.loads(_run(run_composites_drape(
            {"surface": "flat", "u_range": [0, 100], "v_range": [0, 100], "nu": 5, "nv": 5},
            CTX,
        )))
        assert result["surface"] == "flat"
        assert result["shear_angle_deg"]["max"] == 0.0

    def test_cylinder_x_returns_coords(self):
        result = json.loads(_run(run_composites_drape(
            {"surface": "cylinder_x", "u_range": [0, 90], "v_range": [0, 50],
             "nu": 6, "nv": 6, "radius": 50.0},
            CTX,
        )))
        assert result["surf_coords_shape"] == [6, 6, 3]

    def test_bad_surface_returns_error(self):
        result = json.loads(_run(run_composites_drape(
            {"surface": "sphere"},  # not supported
            CTX,
        )))
        assert "error" in result


# ---------------------------------------------------------------------------
# composites_interlaminar
# ---------------------------------------------------------------------------

class TestCompositesInterlaminar:
    def test_returns_tau_xz(self):
        result = json.loads(_run(run_composites_interlaminar(
            {"plies": _PLIES_0_90_0, "Mx_Nmm_per_mm": 10.0, "beam_length_mm": 100.0},
            CTX,
        )))
        assert "tau_xz_MPa" in result
        assert len(result["tau_xz_MPa"]) == 4  # n_plies + 1 interfaces
        assert result["max_tau_xz_MPa"] >= 0

    def test_free_surface_near_zero(self):
        result = json.loads(_run(run_composites_interlaminar(
            {"plies": _PLIES_0_90_0},
            CTX,
        )))
        # Bottom surface should be exactly 0
        assert result["tau_xz_MPa"][0] == 0.0

    def test_bad_plies_returns_error(self):
        result = json.loads(_run(run_composites_interlaminar(
            {"plies": [{"angle": 0.0}]},  # missing required fields
            CTX,
        )))
        assert "error" in result


# ---------------------------------------------------------------------------
# composites_thermal
# ---------------------------------------------------------------------------

class TestCompositesThermal:
    def test_symmetric_laminate_low_curvature(self):
        """[0/90/0] is symmetric → thermal curvature κ should be near zero."""
        plies_with_cte = [
            dict(p, alpha1=0.02e-6, alpha2=22.5e-6) for p in _PLIES_0_90_0
        ]
        result = json.loads(_run(run_composites_thermal(
            {"plies": plies_with_cte, "delta_T": -120.0},
            CTX,
        )))
        assert "ply_thermal_stresses" in result
        assert len(result["ply_thermal_stresses"]) == 3
        # Symmetric laminate: curvatures ≈ 0
        for kap in result["curvatures_per_mm"]:
            assert abs(kap) < 1e-6, f"Expected near-zero curvature, got {kap}"

    def test_ply_stresses_have_correct_keys(self):
        result = json.loads(_run(run_composites_thermal(
            {"plies": _PLIES_0_90_0, "delta_T": -100.0},
            CTX,
        )))
        ps = result["ply_thermal_stresses"][0]
        for key in ("ply_index", "angle", "sigma1_MPa", "sigma2_MPa", "tau12_MPa"):
            assert key in ps

    def test_bad_missing_delta_T(self):
        result = json.loads(_run(run_composites_thermal(
            {"plies": _PLIES_0_90_0},  # missing delta_T
            CTX,
        )))
        assert "error" in result


# ---------------------------------------------------------------------------
# composites_failure_depth
# ---------------------------------------------------------------------------

class TestCompositesFailureDepth:
    # T300/5208 reference allowables
    MATERIAL = {
        "Xt": 1500.0, "Xc": 1500.0,
        "Yt": 40.0, "Yc": 246.0,
        "S12": 68.0,
        "E1": 181.0, "E2": 10.3, "G12": 7.17, "nu12": 0.28,
    }

    def test_safe_stress_not_failed(self):
        args = dict(self.MATERIAL, sigma1=500.0, sigma2=10.0, tau12=20.0)
        result = json.loads(_run(run_composites_failure_depth(args, CTX)))
        assert "tsai_wu" in result
        assert result["tsai_wu"]["failed"] is False
        assert result["hashin"]["failed"] is False

    def test_failure_at_limit_stress(self):
        """Apply stress exactly at Xt → tsai_wu FI ≥ 1."""
        args = dict(self.MATERIAL, sigma1=1500.0, sigma2=0.0, tau12=0.0)
        result = json.loads(_run(run_composites_failure_depth(args, CTX)))
        assert result["max_stress"]["failed"] is True

    def test_hashin_fiber_tension_mode(self):
        args = dict(self.MATERIAL, sigma1=1600.0, sigma2=0.0, tau12=0.0)
        result = json.loads(_run(run_composites_failure_depth(args, CTX)))
        assert result["hashin"]["mode"] == "fiber_tension"

    def test_all_criteria_present(self):
        args = dict(self.MATERIAL, sigma1=100.0, sigma2=5.0, tau12=10.0)
        result = json.loads(_run(run_composites_failure_depth(args, CTX)))
        for key in ("tsai_wu", "tsai_hill", "max_stress", "hashin"):
            assert key in result

    def test_missing_strength_returns_error(self):
        result = json.loads(_run(run_composites_failure_depth(
            {"sigma1": 100.0, "sigma2": 0.0, "tau12": 0.0},  # missing Xt etc.
            CTX,
        )))
        assert "error" in result
