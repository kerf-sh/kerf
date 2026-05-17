"""
Tests for kerf_bim.site — Toposolid, BuildingPad, Contour, cut_fill_volume,
slope, aspect.

All tests are hermetic (no DB / network required) and use analytic oracles
so that expected values can be derived from closed-form geometry.

Oracle sources
--------------
- Flat surface: slope = 0°, surface area = plan area, volume = plan_area * thickness.
- Linear-slope surface (dz/dx = m): slope = atan(m) in degrees.
- Contour interval k on a 0-to-H plane: ceil(H/k) + 1 contour lines or
  exactly (H/k + 1) when H is divisible by k.
- Cut/fill volume (sloping grade vs horizontal proposed): closed-form trapezoid.
- Pyramid: volume above base = (1/3) * base_area * height.
- Aspect on a surface sloping toward +X (East) → aspect = 90°.
- Aspect on a surface sloping toward +Y (North) → aspect = 0°.
"""
from __future__ import annotations

import importlib.util
import math
import os
import sys
import pathlib
import types

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Import the module under test directly (no pip install required)
# ---------------------------------------------------------------------------

_SITE_PATH = (
    pathlib.Path(__file__).parent.parent / "src" / "kerf_bim" / "site.py"
)

# Stub heavy dependencies that are not needed for pure-logic tests
for _stub_name in [
    "kerf_chat", "kerf_chat.tools", "kerf_chat.tools.registry",
    "kerf_core", "kerf_core.utils", "kerf_core.utils.context",
]:
    if _stub_name not in sys.modules:
        _stub = types.ModuleType(_stub_name)
        sys.modules[_stub_name] = _stub

_chat_reg = sys.modules["kerf_chat.tools.registry"]
_ctx_mod = sys.modules["kerf_core.utils.context"]

# Capture pre-existing state so the fixture teardown can restore it.
_SENTINEL = object()
_saved_chat_reg: dict = {
    k: getattr(_chat_reg, k, _SENTINEL)
    for k in ("ToolSpec", "register", "ok_payload", "err_payload")
}
_saved_ProjectCtx = getattr(_ctx_mod, "ProjectCtx", _SENTINEL)

# Install stubs so that site.py can be imported without the real heavy deps.
_chat_reg.ToolSpec = type("ToolSpec", (), {"__init__": lambda self, **kw: None})
_chat_reg.register = lambda *a, **kw: (lambda fn: fn)
_chat_reg.ok_payload = lambda v: v
_chat_reg.err_payload = lambda msg, code: {"error": msg, "code": code}
_ctx_mod.ProjectCtx = object

_spec = importlib.util.spec_from_file_location("kerf_bim.site", _SITE_PATH)
_site = importlib.util.module_from_spec(_spec)
sys.modules["kerf_bim.site"] = _site
_spec.loader.exec_module(_site)

# site.py is fully loaded — restore stub attributes immediately so that
# other test modules collected in the same session are not poisoned.
for _attr, _val in _saved_chat_reg.items():
    if _val is _SENTINEL:
        try:
            delattr(_chat_reg, _attr)
        except AttributeError:
            pass
    else:
        setattr(_chat_reg, _attr, _val)
if _saved_ProjectCtx is _SENTINEL:
    try:
        delattr(_ctx_mod, "ProjectCtx")
    except AttributeError:
        pass
else:
    _ctx_mod.ProjectCtx = _saved_ProjectCtx

Toposolid = _site.Toposolid
BuildingPad = _site.BuildingPad
Contour = _site.Contour
cut_fill_volume = _site.cut_fill_volume
slope = _site.slope
aspect = _site.aspect
Curve = _site.Curve


# ---------------------------------------------------------------------------
# Fixtures — shared terrain geometries
# ---------------------------------------------------------------------------

def _flat_100x100(z: float = 10.0) -> Toposolid:
    """100×100 square plot, all four corners at elevation ``z``."""
    boundary = [(0, 0), (100, 0), (100, 100), (0, 100)]
    pts = [(0, 0, z), (100, 0, z), (100, 100, z), (0, 100, z)]
    return Toposolid(boundary=boundary, points=pts, material="soil", thickness=1.0)


def _linear_slope_x(z_at_x0: float = 0.0, dz_per_m: float = 0.1,
                    size: float = 100.0) -> Toposolid:
    """100×100 plot; elevation varies linearly along X as z = z_at_x0 + dz_per_m * x."""
    boundary = [(0, 0), (size, 0), (size, size), (0, size)]
    pts = [
        (0,    0,    z_at_x0),
        (size, 0,    z_at_x0 + dz_per_m * size),
        (size, size, z_at_x0 + dz_per_m * size),
        (0,    size, z_at_x0),
    ]
    return Toposolid(boundary=boundary, points=pts, material="soil", thickness=1.0)


def _pyramid(base: float = 10.0, height: float = 5.0) -> Toposolid:
    """Pyramid: four base corners at z=0, apex at centre at z=height."""
    half = base / 2
    boundary = [(-half, -half), (half, -half), (half, half), (-half, half)]
    pts = [
        (-half, -half, 0.0),
        ( half, -half, 0.0),
        ( half,  half, 0.0),
        (-half,  half, 0.0),
        (0.0,   0.0,   height),
    ]
    return Toposolid(boundary=boundary, points=pts, material="soil", thickness=0.5)


# ---------------------------------------------------------------------------
# T1 — Flat surface: slope = 0, plan_area = 10,000 m²
# ---------------------------------------------------------------------------

class TestFlatSurface:
    def test_plan_area(self):
        ts = _flat_100x100(z=10.0)
        assert abs(ts.plan_area() - 10_000.0) < 1e-3

    def test_slope_is_zero(self):
        ts = _flat_100x100(z=10.0)
        s = slope(ts)
        assert len(s) > 0
        assert np.all(s < 1e-6), f"Expected zero slope, got {s}"

    def test_flat_surface_area_equals_plan_area(self):
        ts = _flat_100x100(z=10.0)
        assert abs(ts.surface_area() - ts.plan_area()) < 1e-3

    def test_flat_volume(self):
        """Volume = plan_area * (z - base_z) where base_z = z - thickness."""
        ts = _flat_100x100(z=10.0)
        expected = 10_000.0 * 1.0  # plan_area * thickness
        assert abs(ts.volume() - expected) < 1e-2

    def test_vertices_count(self):
        ts = _flat_100x100()
        assert ts.vertices.shape == (4, 3)


# ---------------------------------------------------------------------------
# T2 — Linear slope surface
# ---------------------------------------------------------------------------

class TestLinearSlope:
    def test_slope_constant(self):
        """slope = atan(dz/dx) in degrees for linear X-gradient."""
        m = 0.1  # 10 % grade
        ts = _linear_slope_x(dz_per_m=m)
        expected_deg = math.degrees(math.atan(m))
        s = slope(ts)
        assert len(s) > 0
        for val in s:
            assert abs(val - expected_deg) < 0.1, (
                f"Expected slope ≈ {expected_deg:.3f}°, got {val:.3f}°"
            )

    def test_aspect_points_west(self):
        """Surface rising toward +X (East) → aspect ≈ 270° (West, downhill direction).

        Aspect is the downhill-facing direction.  A surface whose elevation
        increases going East drains toward the West (270°).
        """
        ts = _linear_slope_x(dz_per_m=0.1)
        a = aspect(ts)
        assert len(a) > 0
        for val in a:
            assert abs(val - 270.0) < 1.0, (
                f"Expected aspect ≈ 270° (West downhill), got {val:.1f}°"
            )

    def test_steeper_slope(self):
        m = 1.0  # 45° slope
        ts = _linear_slope_x(dz_per_m=m, size=10.0)
        expected_deg = 45.0
        s = slope(ts)
        for val in s:
            assert abs(val - expected_deg) < 0.5

    def test_elevation_at_midpoint(self):
        m = 0.1
        ts = _linear_slope_x(dz_per_m=m, size=100.0)
        z = ts.elevation_at(50.0, 50.0)
        assert z is not None
        assert abs(z - 5.0) < 1e-3

    def test_elevation_at_corner(self):
        m = 0.1
        ts = _linear_slope_x(dz_per_m=m, size=100.0)
        z = ts.elevation_at(100.0, 0.0)
        assert z is not None
        assert abs(z - 10.0) < 1e-2


# ---------------------------------------------------------------------------
# T3 — Aspect direction tests
# ---------------------------------------------------------------------------

class TestAspect:
    def _north_sloping(self) -> Toposolid:
        """Surface sloping toward +Y (North). dz/dy = 0.1."""
        boundary = [(0, 0), (10, 0), (10, 10), (0, 10)]
        pts = [
            (0,  0,  0.0),
            (10, 0,  0.0),
            (10, 10, 1.0),
            (0,  10, 1.0),
        ]
        return Toposolid(boundary=boundary, points=pts)

    def test_north_sloping_aspect(self):
        """Surface rising toward +Y (North) → aspect ≈ 180° (South, downhill direction).

        A surface whose elevation increases going North drains toward the South.
        """
        ts = self._north_sloping()
        a = aspect(ts)
        for val in a:
            assert abs(val - 180.0) < 1.0, (
                f"Expected aspect ≈ 180° (South downhill), got {val:.1f}°"
            )

    def test_flat_aspect_zero(self):
        ts = _flat_100x100(z=5.0)
        a = aspect(ts)
        assert np.all(a == 0.0)


# ---------------------------------------------------------------------------
# T4 — Contour generation
# ---------------------------------------------------------------------------

class TestContour:
    def test_contour_count_sloping_plane(self):
        """0→10 sloping plane with interval=1 → 11 contour levels (z=0…10)."""
        ts = _linear_slope_x(z_at_x0=0.0, dz_per_m=0.1, size=100.0)
        contours = Contour(ts, interval=1.0)
        # Levels from ceil(0/1)*1=0 to 10, inclusive: 0,1,2,...,10 → 11 levels
        assert len(contours) == 11

    def test_contour_elevations(self):
        ts = _linear_slope_x(z_at_x0=0.0, dz_per_m=0.1, size=100.0)
        contours = Contour(ts, interval=1.0)
        elevations = sorted(c.elevation for c in contours)
        for i, elev in enumerate(elevations):
            assert abs(elev - float(i)) < 1e-9

    def test_contour_interval_2(self):
        """interval=2 on 0–10 range → 6 contours (z=0,2,4,6,8,10)."""
        ts = _linear_slope_x(z_at_x0=0.0, dz_per_m=0.1, size=100.0)
        contours = Contour(ts, interval=2.0)
        assert len(contours) == 6

    def test_contour_flat_surface(self):
        """Flat surface at z=5 with interval=1 → 1 contour (z=5)."""
        ts = _flat_100x100(z=5.0)
        contours = Contour(ts, interval=1.0)
        assert len(contours) == 1
        assert abs(contours[0].elevation - 5.0) < 1e-9

    def test_contour_points_are_arrays(self):
        ts = _linear_slope_x(z_at_x0=0.0, dz_per_m=0.1, size=100.0)
        contours = Contour(ts, interval=1.0)
        for c in contours:
            assert isinstance(c.points, list)
            assert len(c.points) > 0

    def test_contour_invalid_interval(self):
        ts = _flat_100x100()
        with pytest.raises(ValueError):
            Contour(ts, interval=0.0)

    def test_contour_returns_curves(self):
        ts = _linear_slope_x(dz_per_m=0.1, size=10.0)
        contours = Contour(ts, interval=0.5)
        assert all(isinstance(c, Curve) for c in contours)


# ---------------------------------------------------------------------------
# T5 — Cut / fill volume
# ---------------------------------------------------------------------------

class TestCutFillVolume:
    def _existing_sloping(self) -> Toposolid:
        """Sloping existing terrain: z linearly from 0 to 10 across 100 m."""
        return _linear_slope_x(z_at_x0=0.0, dz_per_m=0.1, size=100.0)

    def _proposed_flat(self, z: float = 5.0) -> Toposolid:
        """Proposed flat grade at constant elevation z."""
        boundary = [(0, 0), (100, 0), (100, 100), (0, 100)]
        pts = [(0, 0, z), (100, 0, z), (100, 100, z), (0, 100, z)]
        return Toposolid(boundary=boundary, points=pts)

    def test_symmetric_cut_fill(self):
        """Flat proposed at z=5 vs 0-to-10 existing → cut ≈ fill (symmetric)."""
        existing = self._existing_sloping()
        proposed = self._proposed_flat(z=5.0)
        result = cut_fill_volume(existing, proposed, grid_spacing=2.0)
        # At z=5 grade through a 0-to-10 slope: half the area is cut, half fill
        # Total = 100*100 * 5/2 = 25_000 m³ each (approx)
        # Symmetric → cut ≈ fill → net ≈ 0
        assert abs(result["net"]) < result["cut"] * 0.05, (
            f"Expected net ≈ 0, got cut={result['cut']:.1f} fill={result['fill']:.1f}"
        )

    def test_cut_volume_sign(self):
        """Flat proposed lower than existing → cut only, no fill."""
        # Proposed at z=0, existing from 0→10 → cut where existing > 0
        existing = self._existing_sloping()
        proposed = self._proposed_flat(z=-1.0)  # below all terrain
        result = cut_fill_volume(existing, proposed, grid_spacing=2.0)
        assert result["cut"] > 0
        assert result["fill"] < 1.0  # negligible fill

    def test_fill_volume_sign(self):
        """Flat proposed higher than existing → fill only, no cut."""
        existing = self._existing_sloping()
        proposed = self._proposed_flat(z=11.0)  # above all terrain
        result = cut_fill_volume(existing, proposed, grid_spacing=2.0)
        assert result["fill"] > 0
        assert result["cut"] < 1.0

    def test_net_is_fill_minus_cut(self):
        existing = self._existing_sloping()
        proposed = self._proposed_flat(z=5.0)
        result = cut_fill_volume(existing, proposed, grid_spacing=2.0)
        assert abs(result["net"] - (result["fill"] - result["cut"])) < 1e-6

    def test_zero_volume_identical_surfaces(self):
        """Same terrain as both inputs → zero cut/fill."""
        ts = _flat_100x100(z=5.0)
        result = cut_fill_volume(ts, ts, grid_spacing=5.0)
        assert result["cut"] < 1e-6
        assert result["fill"] < 1e-6

    def test_cut_fill_approximate_magnitude(self):
        """Verify approximate closed-form magnitude.

        Existing grade: z = 0.1*x over 100×100.
        Proposed: flat at z = 5.

        Closed form (strip integration over x in [0,100]):
          Fill region: x in [0, 50] where z_proposed > z_existing
            Fill volume = integral_0^50 (5 - 0.1*x) * 100 dx
                        = 100 * [5x - 0.05*x²]_0^50
                        = 100 * (250 - 125) = 12,500 m³
          Cut region: x in [50, 100]
            Cut volume = integral_50^100 (0.1*x - 5) * 100 dx
                       = 100 * [0.05*x² - 5x]_50^100
                       = 100 * ((500-500) - (125-250)) = 12,500 m³
        """
        existing = self._existing_sloping()
        proposed = self._proposed_flat(z=5.0)
        result = cut_fill_volume(existing, proposed, grid_spacing=1.0)
        expected = 12_500.0
        tol = expected * 0.05  # 5 % tolerance for grid discretisation
        assert abs(result["cut"] - expected) < tol, (
            f"cut: expected ≈ {expected:.0f}, got {result['cut']:.1f}"
        )
        assert abs(result["fill"] - expected) < tol, (
            f"fill: expected ≈ {expected:.0f}, got {result['fill']:.1f}"
        )

    def test_invalid_grid_spacing(self):
        ts = _flat_100x100()
        with pytest.raises(ValueError):
            cut_fill_volume(ts, ts, grid_spacing=0.0)


# ---------------------------------------------------------------------------
# T6 — Pyramid volume
# ---------------------------------------------------------------------------

class TestPyramidVolume:
    def test_pyramid_volume(self):
        """Pyramid volume above its base = (1/3) * base_area * height."""
        base = 10.0
        height = 5.0
        ts = _pyramid(base=base, height=height)

        # The toposolid volume includes the TIN surface + downward extrusion
        # to base_z = min_z - thickness.
        # min_z = 0, thickness = 0.5  →  base_z = -0.5
        # Toposolid volume = pyramid_volume_above_base_z
        # = pyramid_above_z=0 + rectangular slab (-0.5 to 0)
        # pyramid_above_z=0 = (1/3) * base² * height = (1/3)*100*5 = 166.67
        # slab = base² * 0.5 = 50
        expected_pyramid = (1.0 / 3.0) * base ** 2 * height  # 166.667
        expected_slab = base ** 2 * 0.5                        # 50.0
        expected_total = expected_pyramid + expected_slab       # 216.667

        v = ts.volume()
        assert abs(v - expected_total) < expected_total * 0.02, (
            f"Pyramid volume: expected ≈ {expected_total:.2f}, got {v:.2f}"
        )

    def test_pyramid_plan_area(self):
        base = 10.0
        ts = _pyramid(base=base)
        assert abs(ts.plan_area() - base ** 2) < 1e-3


# ---------------------------------------------------------------------------
# T7 — BuildingPad
# ---------------------------------------------------------------------------

class TestBuildingPad:
    def _make_pad(self) -> BuildingPad:
        ts = _linear_slope_x(z_at_x0=0.0, dz_per_m=0.1, size=100.0)
        footprint = [(10, 10), (30, 10), (30, 30), (10, 30)]
        return BuildingPad(toposolid=ts, footprint_curve=footprint,
                           level=5.0, side_slope=2.0)

    def test_pad_area(self):
        """20×20 footprint → area = 400 m²."""
        pad = self._make_pad()
        assert abs(pad.pad_area() - 400.0) < 1e-6

    def test_slope_offset_above_level(self):
        """Terrain at z=7, pad at z=5 → offset = (7-5)*2 = 4 m."""
        pad = self._make_pad()
        assert abs(pad.slope_offset(7.0) - 4.0) < 1e-9

    def test_slope_offset_at_level(self):
        """Terrain at pad level → zero offset."""
        pad = self._make_pad()
        assert abs(pad.slope_offset(5.0)) < 1e-9

    def test_slope_offset_below_level(self):
        """Terrain below pad level → no cut (offset = 0)."""
        pad = self._make_pad()
        assert abs(pad.slope_offset(3.0)) < 1e-9

    def test_invalid_side_slope(self):
        ts = _flat_100x100()
        with pytest.raises(ValueError):
            BuildingPad(toposolid=ts,
                        footprint_curve=[(0, 0), (10, 0), (10, 10), (0, 10)],
                        level=5.0, side_slope=-1.0)

    def test_invalid_footprint(self):
        ts = _flat_100x100()
        with pytest.raises(ValueError):
            BuildingPad(toposolid=ts, footprint_curve=[(0, 0), (10, 0)],
                        level=5.0, side_slope=2.0)


# ---------------------------------------------------------------------------
# T8 — Toposolid construction edge cases
# ---------------------------------------------------------------------------

class TestToposolidConstruction:
    def test_too_few_points(self):
        with pytest.raises((ValueError, Exception)):
            Toposolid(boundary=[(0, 0), (1, 0)],
                      points=[(0, 0, 0), (1, 0, 1)])

    def test_material_stored(self):
        ts = _flat_100x100()
        assert ts.material == "soil"

    def test_thickness_stored(self):
        ts = _flat_100x100()
        assert ts.thickness == 1.0

    def test_simplices_shape(self):
        ts = _flat_100x100()
        assert ts.simplices.ndim == 2
        assert ts.simplices.shape[1] == 3


# ---------------------------------------------------------------------------
# T9 — to_brep smoke test (returns a Body if kerf_cad_core is available)
# ---------------------------------------------------------------------------

class TestToBrep:
    def test_toposolid_to_brep_runs(self):
        ts = _flat_100x100()
        try:
            body = ts.to_brep()
            assert body is not None
        except ImportError:
            pytest.skip("kerf_cad_core not available in this environment")

    def test_building_pad_to_brep_runs(self):
        ts = _flat_100x100()
        pad = BuildingPad(
            toposolid=ts,
            footprint_curve=[(0, 0), (10, 0), (10, 10), (0, 10)],
            level=5.0,
        )
        try:
            body = pad.to_brep()
            assert body is not None
        except ImportError:
            pytest.skip("kerf_cad_core not available in this environment")


# ---------------------------------------------------------------------------
# T10 — Curve helper
# ---------------------------------------------------------------------------

class TestCurve:
    def test_length_line(self):
        c = Curve(points=[np.array([0.0, 0.0, 0.0]), np.array([3.0, 4.0, 0.0])])
        assert abs(c.length() - 5.0) < 1e-9

    def test_as_array_shape(self):
        c = Curve(points=[np.array([0.0, 0.0, 0.0]), np.array([1.0, 0.0, 0.0])])
        arr = c.as_array()
        assert arr.shape == (2, 3)

    def test_elevation_stored(self):
        c = Curve(points=[np.array([0.0, 0.0, 5.0])], elevation=5.0)
        assert c.elevation == 5.0


# ---------------------------------------------------------------------------
# T11 — surface_area > plan_area for sloped surface; elevation outside mesh
# ---------------------------------------------------------------------------

class TestSlopedSurfaceArea:
    def test_sloped_surface_area_exceeds_plan_area(self):
        """On a non-flat surface the 3-D TIN area must exceed the plan area."""
        ts = _linear_slope_x(dz_per_m=0.1, size=100.0)
        sa = ts.surface_area()
        pa = ts.plan_area()
        assert sa > pa, f"3-D area {sa:.2f} should exceed plan area {pa:.2f}"

    def test_elevation_outside_mesh_returns_none(self):
        """elevation_at() returns None for points outside the TIN."""
        ts = _flat_100x100(z=10.0)
        z = ts.elevation_at(200.0, 200.0)
        assert z is None, f"Expected None for point outside mesh, got {z}"
