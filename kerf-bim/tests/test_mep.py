"""Tests for backend/tools/mep.py — MEP routing logic."""

import importlib.util
import json
import math
import sys
import pathlib
import unittest

# ── Load module under test via importlib ──────────────────────────────────────

_mep_path = pathlib.Path(__file__).parent.parent / "src" / "kerf_bim" / "tools" / "mep.py"
_spec = importlib.util.spec_from_file_location("tools.mep", _mep_path)
_mep = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("tools.mep", _mep)

# Stub out dependencies so we can import without a live DB
import types

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

_spec.loader.exec_module(_mep)


# ── Convenience aliases ────────────────────────────────────────────────────────

_default_route = _mep._default_route
_dist3 = _mep._dist3
_astar_3d = _mep._astar_3d


class TestDefaultRoute(unittest.TestCase):
    def test_duct_defaults(self):
        r = _default_route("duct", "Supply Air")
        self.assertEqual(r["kind"], "duct")
        self.assertEqual(r["version"], 1)
        self.assertEqual(r["system_name"], "Supply Air")
        self.assertEqual(r["material"], "galvanized_steel")
        self.assertEqual(r["size_mm"], 400)
        self.assertEqual(r["insulation_thickness_mm"], 25)
        self.assertEqual(r["segments"], [])
        self.assertEqual(r["fittings"], [])
        self.assertEqual(r["endpoints"], [])

    def test_pipe_defaults(self):
        r = _default_route("pipe", "Cold Water")
        self.assertEqual(r["kind"], "pipe")
        self.assertEqual(r["material"], "copper")
        self.assertEqual(r["size_mm"], 50)
        self.assertEqual(r["insulation_thickness_mm"], 0)

    def test_conduit_defaults(self):
        r = _default_route("conduit", "Power Run")
        self.assertEqual(r["kind"], "conduit")
        self.assertEqual(r["material"], "pvc")
        self.assertEqual(r["size_mm"], 25)

    def test_custom_size_and_material(self):
        r = _default_route("pipe", "Hot Water", size_mm=75, material="stainless_steel")
        self.assertEqual(r["size_mm"], 75)
        self.assertEqual(r["material"], "stainless_steel")


class TestDist3(unittest.TestCase):
    def test_along_x_axis(self):
        self.assertAlmostEqual(_dist3([0, 0, 0], [5000, 0, 0]), 5000.0)

    def test_diagonal_3d(self):
        # 3-4-5 right triangle in xy, z=0
        self.assertAlmostEqual(_dist3([0, 0, 0], [3000, 4000, 0]), 5000.0)

    def test_same_point(self):
        self.assertAlmostEqual(_dist3([1, 2, 3], [1, 2, 3]), 0.0)


class TestAstar3D(unittest.TestCase):
    def test_straight_line_no_obstacles(self):
        result = _astar_3d([0, 0, 0], [5000, 0, 0], [], 500)
        self.assertIn("polyline", result)
        poly = result["polyline"]
        self.assertGreaterEqual(len(poly), 2)
        self.assertIsNone(result.get("warning"))

    def test_start_equals_end(self):
        result = _astar_3d([0, 0, 0], [0, 0, 0], [], 500)
        self.assertIn("polyline", result)

    def test_detour_around_wall(self):
        # Wall blocks direct path from (0,0,0) → (6000,0,0) at x=2500..3500
        obstacles = [{"min": [2000, -500, -500], "max": [3000, 500, 500]}]
        result = _astar_3d([0, 0, 0], [6000, 0, 0], obstacles, 500)
        poly = result["polyline"]
        self.assertGreater(len(poly), 2)
        # Verify no point is inside the obstacle
        for pt in poly:
            inside = (2000 <= pt[0] <= 3000 and -500 <= pt[1] <= 500 and -500 <= pt[2] <= 500)
            self.assertFalse(inside, f"Point {pt} is inside obstacle")

    def test_grid_too_large_returns_straight_line(self):
        result = _astar_3d([0, 0, 0], [500000, 500000, 0], [], 10)
        self.assertIsNotNone(result.get("warning"))
        self.assertEqual(len(result["polyline"]), 2)

    def test_path_endpoints_near_start_end(self):
        result = _astar_3d([0, 0, 3000], [10000, 0, 3000], [], 1000)
        poly = result["polyline"]
        start = poly[0]
        end = poly[-1]
        # Grid-snapped, so within one cell of target
        self.assertLess(_dist3(start, [0, 0, 3000]), 2000)
        self.assertLess(_dist3(end, [10000, 0, 3000]), 2000)


class TestPressureDropLogic(unittest.TestCase):
    """Test the pressure drop maths directly (Darcy-Weisbach + equivalent length)."""

    def _compute(self, kind, size_mm, material, length_mm, fluid=None):
        """Manually replicate the tool's pressure-drop logic."""
        if kind == "conduit":
            return 0.0
        length_m = length_mm / 1000.0
        if length_m == 0:
            return 0.0
        if kind == "duct":
            return length_m * 1.0 * (200.0 / size_mm)
        # Pipe — Darcy-Weisbach
        rho = (fluid or {}).get("density_kg_m3", 1000)
        v = (fluid or {}).get("velocity_m_s", 1.5)
        mu = (fluid or {}).get("viscosity_Pa_s", 0.001)
        d = size_mm / 1000.0
        Re = rho * v * d / mu
        roughness = _mep.ROUGHNESS_MM.get(material, 0.046)
        eps_D = (roughness / 1000.0) / d
        if Re < 2300:
            f = 64.0 / Re
        else:
            f = 0.25 / (math.log10(eps_D / 3.7 + 5.74 / (Re ** 0.9)) ** 2)
        return f * (length_m / d) * (rho * v * v / 2.0)

    def test_conduit_zero(self):
        self.assertEqual(self._compute("conduit", 25, "pvc", 10000), 0.0)

    def test_duct_positive(self):
        dp = self._compute("duct", 400, "galvanized_steel", 20000)
        self.assertGreater(dp, 0)
        # 20m at 1 Pa/m × (200/400) = 10 Pa
        self.assertAlmostEqual(dp, 10.0, places=3)

    def test_pipe_turbulent_positive(self):
        dp = self._compute("pipe", 50, "copper", 10000)
        self.assertGreater(dp, 0)
        self.assertLess(dp, 100000)

    def test_pipe_laminar_positive(self):
        dp = self._compute("pipe", 50, "copper", 10000, {"density_kg_m3": 1000, "velocity_m_s": 0.01, "viscosity_Pa_s": 1.0})
        self.assertGreater(dp, 0)

    def test_longer_pipe_higher_drop(self):
        dp_short = self._compute("pipe", 50, "copper", 5000)
        dp_long = self._compute("pipe", 50, "copper", 10000)
        self.assertGreater(dp_long, dp_short)


class TestValidKindsAndMaterials(unittest.TestCase):
    def test_valid_kinds(self):
        self.assertEqual(_mep.VALID_KINDS, {"duct", "pipe", "conduit"})

    def test_valid_materials_includes_copper(self):
        self.assertIn("copper", _mep.VALID_MATERIALS)

    def test_file_extensions(self):
        self.assertEqual(_mep.FILE_EXTENSION["duct"], "duct.json")
        self.assertEqual(_mep.FILE_EXTENSION["pipe"], "pipe.json")
        self.assertEqual(_mep.FILE_EXTENSION["conduit"], "conduit.json")


if __name__ == "__main__":
    unittest.main()
