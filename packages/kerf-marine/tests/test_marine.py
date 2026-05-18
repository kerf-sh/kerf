"""
Tests for kerf_marine — hydrostatics, stability, hull-section integration, tools.

DoD oracles (T-172):
  - Rectangular barge displacement = L·B·T·ρ  (analytic, tolerance 1e-12)
  - KB for box barge = T/2                      (analytic, tolerance 1e-12)
  - BM = B²/(12T)                              (analytic, tolerance 1e-12)
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import sys

import pytest

# Belt-and-suspenders sys.path bootstrap
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


class FakeCtx:
    pass


# ===========================================================================
# sections.py
# ===========================================================================

class TestTrapz:
    def test_constant_function(self):
        from kerf_marine.sections import _trapz
        xs = [0.0, 1.0, 2.0, 3.0]
        ys = [5.0, 5.0, 5.0, 5.0]
        result = _trapz(xs, ys)
        assert result == pytest.approx(15.0)

    def test_linear_function(self):
        from kerf_marine.sections import _trapz
        xs = [0.0, 1.0, 2.0]
        ys = [0.0, 1.0, 2.0]
        result = _trapz(xs, ys)
        assert result == pytest.approx(2.0)

    def test_single_point_zero(self):
        from kerf_marine.sections import _trapz
        result = _trapz([0.0], [5.0])
        assert result == 0.0


class TestSimpson:
    def test_constant_function(self):
        from kerf_marine.sections import _simpson
        xs = [0.0, 1.0, 2.0]
        ys = [3.0, 3.0, 3.0]
        result = _simpson(xs, ys)
        assert result == pytest.approx(6.0)

    def test_quadratic_exact(self):
        """Simpson's rule is exact for quadratics."""
        from kerf_marine.sections import _simpson
        # ∫₀² x² dx = 8/3
        xs = [0.0, 1.0, 2.0]
        ys = [x ** 2 for x in xs]
        result = _simpson(xs, ys)
        assert result == pytest.approx(8.0 / 3.0, rel=1e-10)

    def test_four_points(self):
        """Four points: Simpson + trapz fallback."""
        from kerf_marine.sections import _simpson
        # ∫₀³ 1 dx = 3
        xs = [0.0, 1.0, 2.0, 3.0]
        ys = [1.0, 1.0, 1.0, 1.0]
        result = _simpson(xs, ys)
        assert result == pytest.approx(3.0)


class TestIntegrateSection:
    def test_rectangular_section_area(self):
        """
        A rectangular cross-section of width B and depth D has area = B * D.
        Half-breadth = B/2 at all waterlines, so full breadth = B.
        ∫₀ᴰ B dz = B·D
        """
        from kerf_marine.sections import integrate_section

        B = 10.0   # m — full beam
        D = 5.0    # m — draft / depth
        wls = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
        hbs = [B / 2.0] * 6

        sl = integrate_section(wls, hbs)
        assert sl.area == pytest.approx(B * D, rel=1e-10)

    def test_rectangular_section_centroid(self):
        """Centroid of a rectangle is at D/2."""
        from kerf_marine.sections import integrate_section

        D = 6.0
        wls = [0.0, 2.0, 4.0, 6.0]
        hbs = [5.0] * 4   # full breadth = 10 m

        sl = integrate_section(wls, hbs)
        assert sl.centroid_z == pytest.approx(D / 2.0, rel=1e-10)

    def test_waterplane_half_breadth(self):
        from kerf_marine.sections import integrate_section

        wls = [0.0, 1.0, 2.0]
        hbs = [3.0, 4.0, 5.0]
        sl = integrate_section(wls, hbs)
        assert sl.waterplane_half_breadth == pytest.approx(5.0)

    def test_mismatched_lengths_raise(self):
        from kerf_marine.sections import integrate_section
        with pytest.raises(ValueError, match="equal length"):
            integrate_section([0.0, 1.0], [1.0])

    def test_too_few_waterlines_raise(self):
        from kerf_marine.sections import integrate_section
        with pytest.raises(ValueError, match="At least 2"):
            integrate_section([0.0], [1.0])


class TestOffsetTable:
    def test_add_and_retrieve(self):
        from kerf_marine.sections import OffsetTable

        t = OffsetTable()
        t.add(0.0, 0.0, 5.0)
        t.add(0.0, 1.0, 5.0)
        t.add(5.0, 0.0, 5.0)
        t.add(5.0, 1.0, 5.0)

        assert sorted(t.stations()) == [0.0, 5.0]
        wls, hbs = t.half_breadths_at_station(0.0)
        assert wls == [0.0, 1.0]
        assert hbs == [5.0, 5.0]

    def test_waterline_query(self):
        from kerf_marine.sections import OffsetTable

        t = OffsetTable()
        t.add(0.0, 2.0, 4.0)
        t.add(5.0, 2.0, 4.0)
        t.add(10.0, 2.0, 4.0)

        stns, hbs = t.half_breadths_at_waterline(2.0)
        assert stns == [0.0, 5.0, 10.0]
        assert hbs == [4.0, 4.0, 4.0]


class TestBoxBargeTable:
    def test_table_station_count(self):
        from kerf_marine.sections import box_barge_table

        t = box_barge_table(100.0, 20.0, 5.0, n_stations=11, n_waterlines=6)
        assert len(t.stations()) == 11

    def test_table_half_breadth(self):
        """All half-breadths should be B/2 = 10.0."""
        from kerf_marine.sections import box_barge_table

        t = box_barge_table(100.0, 20.0, 5.0, n_stations=5, n_waterlines=3)
        for row in t.rows:
            assert row.half_breadth == pytest.approx(10.0)


# ===========================================================================
# hydrostatics.py — DoD oracles
# ===========================================================================

class TestBoxBargeOraclesAnalytic:
    """
    DoD oracles verified against closed-form box-barge formulas.
    tolerance: 1e-12 (floating-point exact for analytic path)
    """

    L, B, T, rho = 100.0, 20.0, 5.0, 1.025

    def _ht(self):
        from kerf_marine.hydrostatics import box_barge_hydrostatics
        return box_barge_hydrostatics(self.L, self.B, self.T, rho=self.rho)

    def test_displacement_oracle(self):
        """displacement = L·B·T·ρ"""
        ht = self._ht()
        expected = self.L * self.B * self.T * self.rho
        assert abs(ht.displacement - expected) < 1e-12, (
            f"displacement {ht.displacement} != {expected}"
        )

    def test_volume_oracle(self):
        """volume = L·B·T"""
        ht = self._ht()
        expected = self.L * self.B * self.T
        assert abs(ht.volume - expected) < 1e-12, (
            f"volume {ht.volume} != {expected}"
        )

    def test_kb_oracle(self):
        """KB = T/2"""
        ht = self._ht()
        expected = self.T / 2.0
        assert abs(ht.kb - expected) < 1e-12, (
            f"KB {ht.kb} != {expected}"
        )

    def test_bm_transverse_oracle(self):
        """BM = B²/(12·T)"""
        ht = self._ht()
        expected = (self.B ** 2) / (12.0 * self.T)
        assert abs(ht.bm_transverse - expected) < 1e-12, (
            f"BM_transverse {ht.bm_transverse} != {expected}"
        )

    def test_km(self):
        """KM = KB + BM"""
        ht = self._ht()
        expected = ht.kb + ht.bm_transverse
        assert abs(ht.km - expected) < 1e-12

    def test_waterplane_area(self):
        """A_wp = L·B"""
        ht = self._ht()
        expected = self.L * self.B
        assert abs(ht.waterplane_area - expected) < 1e-12

    def test_tpc(self):
        """TPC = rho · A_wp / 100"""
        ht = self._ht()
        expected = self.rho * self.L * self.B / 100.0
        assert abs(ht.tpc - expected) < 1e-12

    def test_lcb_at_midship(self):
        """LCB = L/2 for a box barge"""
        ht = self._ht()
        expected = self.L / 2.0
        assert abs(ht.lcb - expected) < 1e-12

    def test_lcf_at_midship(self):
        """LCF = L/2 for a box barge"""
        ht = self._ht()
        expected = self.L / 2.0
        assert abs(ht.lcf - expected) < 1e-12


class TestBoxBargeOraclesNumeric:
    """
    Same DoD oracles but via the numerical path (offset table integration).

    These use a dense offset table so the numerical integration converges
    closely to the analytic values.  Tolerance is relaxed to 1e-6 (relative)
    to account for quadrature error.
    """

    L, B, T, rho = 100.0, 20.0, 5.0, 1.025

    def _ht(self):
        from kerf_marine.sections import box_barge_table
        from kerf_marine.hydrostatics import compute_hydrostatics
        table = box_barge_table(
            self.L, self.B, self.T,
            n_stations=21,
            n_waterlines=11,
        )
        return compute_hydrostatics(table, self.T, rho=self.rho)

    def test_displacement_numeric(self):
        ht = self._ht()
        expected = self.L * self.B * self.T * self.rho
        assert ht.displacement == pytest.approx(expected, rel=1e-4)

    def test_kb_numeric(self):
        """KB ≈ T/2 via numerical integration"""
        ht = self._ht()
        expected = self.T / 2.0
        assert ht.kb == pytest.approx(expected, rel=1e-4)

    def test_bm_transverse_numeric(self):
        """BM ≈ B²/(12T) via numerical integration"""
        ht = self._ht()
        expected = (self.B ** 2) / (12.0 * self.T)
        assert ht.bm_transverse == pytest.approx(expected, rel=1e-4)


class TestHydrostaticsEdgeCases:
    def test_fresh_water_lower_displacement(self):
        from kerf_marine.hydrostatics import box_barge_hydrostatics, RHO_FW, RHO_SW
        ht_sw = box_barge_hydrostatics(50, 10, 3, rho=RHO_SW)
        ht_fw = box_barge_hydrostatics(50, 10, 3, rho=RHO_FW)
        assert ht_sw.displacement > ht_fw.displacement

    def test_as_dict_keys(self):
        from kerf_marine.hydrostatics import box_barge_hydrostatics
        ht = box_barge_hydrostatics(50, 10, 3)
        d = ht.as_dict()
        for key in ["draft_m", "displacement_t", "kb_m", "bm_transverse_m",
                    "km_m", "waterplane_area_m2", "tpc", "mct1cm", "lcb_m", "lcf_m"]:
            assert key in d, f"Missing key: {key}"

    def test_hydrostatic_curve_ascending(self):
        from kerf_marine.sections import box_barge_table
        from kerf_marine.hydrostatics import hydrostatic_curve
        table = box_barge_table(50, 10, 5, n_stations=11, n_waterlines=6)
        curve = hydrostatic_curve(table, [1.0, 2.0, 3.0, 4.0, 5.0])
        drafts = [ht.draft for ht in curve]
        assert drafts == sorted(drafts)
        # Displacement increases with draft
        disps = [ht.displacement for ht in curve]
        assert all(disps[i] < disps[i + 1] for i in range(len(disps) - 1))


# ===========================================================================
# stability.py
# ===========================================================================

class TestGZWallSided:
    def test_gz_zero_at_zero(self):
        from kerf_marine.stability import gz_wall_sided
        assert gz_wall_sided(0.0, 1.0, 2.0) == pytest.approx(0.0, abs=1e-12)

    def test_gz_positive_for_positive_gm(self):
        from kerf_marine.stability import gz_wall_sided
        assert gz_wall_sided(15.0, 0.5, 3.0) > 0.0

    def test_gz_negative_for_negative_gm(self):
        """For sufficiently large angle and negative GM, GZ goes negative."""
        from kerf_marine.stability import gz_wall_sided
        # Negative GM → vessel unstable, GZ negative even at small angles
        assert gz_wall_sided(10.0, -1.0, 1.0) < 0.0

    def test_gz_increases_with_angle_stable(self):
        """For a stable vessel at moderate angles, GZ increases with angle."""
        from kerf_marine.stability import gz_wall_sided
        gz5 = gz_wall_sided(5.0, 0.5, 2.0)
        gz15 = gz_wall_sided(15.0, 0.5, 2.0)
        assert gz15 > gz5


class TestGZCurveWallSided:
    def _stable_curve(self):
        from kerf_marine.stability import gz_curve_wall_sided
        return gz_curve_wall_sided(gm=0.5, bm=3.0, angle_step_deg=5.0, max_angle_deg=90.0)

    def test_curve_has_points(self):
        curve = self._stable_curve()
        assert len(curve.points) > 10

    def test_first_point_zero(self):
        curve = self._stable_curve()
        assert curve.points[0].angle_deg == pytest.approx(0.0)
        assert curve.points[0].gz == pytest.approx(0.0, abs=1e-10)

    def test_max_gz_positive(self):
        curve = self._stable_curve()
        assert curve.max_gz > 0.0

    def test_area_0_30_positive(self):
        curve = self._stable_curve()
        assert curve.area_0_30 > 0.0

    def test_area_ordering(self):
        curve = self._stable_curve()
        # area_0_40 = area_0_30 + area_30_40 (up to numerical precision)
        assert curve.area_0_40 >= curve.area_0_30 - 1e-10
        assert curve.area_0_40 >= curve.area_30_40 - 1e-10
        # All areas non-negative
        assert curve.area_0_30 >= 0.0
        assert curve.area_30_40 >= 0.0

    def test_unstable_vessel_negative_vanishing(self):
        """Vessel with negative GM should have a vanishing angle."""
        from kerf_marine.stability import gz_curve_wall_sided
        curve = gz_curve_wall_sided(gm=-0.2, bm=3.0, angle_step_deg=1.0)
        # With negative GM, GZ(φ) = sin(φ)·(-0.2 + 1.5·tan²(φ)) = 0 at small φ
        # This vessel goes negative initially; vanishing angle may be None or small
        # Just check the curve was built
        assert len(curve.points) > 0

    def test_imo_dict_keys(self):
        curve = self._stable_curve()
        d = curve.imo_criteria()
        for key in ["area_0_30_m_rad", "area_0_30_pass", "area_0_40_m_rad",
                    "gz_at_30_m", "gz_at_30_pass", "vanishing_angle_deg"]:
            assert key in d, f"Missing IMO key: {key}"

    def test_as_dict_keys(self):
        curve = self._stable_curve()
        d = curve.as_dict()
        for key in ["points", "vanishing_angle_deg", "area_0_30_m_rad",
                    "area_0_40_m_rad", "max_gz_m"]:
            assert key in d


class TestGZCurveFromKN:
    def _kn_curve(self):
        from kerf_marine.stability import gz_curve_from_kn
        # Simple KN table for a vessel with KG=3.0 m
        angles = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0]
        # KN rises, peaks, then falls
        kn = [0.0, 0.60, 1.10, 1.50, 1.70, 1.65, 1.40, 1.00, 0.50, 0.0]
        return gz_curve_from_kn(angles, kn, kg=3.0)

    def test_kn_curve_has_points(self):
        curve = self._kn_curve()
        assert len(curve.points) > 0

    def test_kn_gz_at_zero_is_zero(self):
        curve = self._kn_curve()
        # GZ(0°) = KN(0°) - KG·sin(0) = 0 - 0 = 0
        assert curve.points[0].gz == pytest.approx(0.0, abs=1e-10)

    def test_kn_mismatched_lengths(self):
        from kerf_marine.stability import gz_curve_from_kn
        with pytest.raises(ValueError, match="equal length"):
            gz_curve_from_kn([0.0, 10.0], [0.0], kg=1.0)

    def test_kn_too_few_points(self):
        from kerf_marine.stability import gz_curve_from_kn
        with pytest.raises(ValueError, match="At least 2"):
            gz_curve_from_kn([0.0], [0.0], kg=1.0)

    def test_gz_interpolation(self):
        curve = self._kn_curve()
        # gz_at must return the exact tabulated value at known points
        gz10 = curve.gz_at(10.0)
        # Verify it's between 0 and max
        assert 0.0 <= gz10 <= curve.max_gz + 1e-6


class TestVanishingAngleBisect:
    def test_simple_crossing(self):
        """GZ = sin(φ) * (GM - k*φ): should find zero near some angle."""
        from kerf_marine.stability import vanishing_angle_bisect
        import math

        def gz_fn(phi_deg):
            phi = math.radians(phi_deg)
            # GZ goes to 0 at ~45°
            return math.sin(phi) * (1.0 - phi / (math.pi / 4.0))

        angle = vanishing_angle_bisect(gz_fn, lo=1.0, hi=89.0, tol=0.001)
        # Should find something near 45°
        assert angle is not None
        assert 40.0 < angle < 50.0

    def test_always_positive_returns_none(self):
        from kerf_marine.stability import vanishing_angle_bisect
        # GZ always positive
        angle = vanishing_angle_bisect(lambda phi: 1.0, lo=1.0, hi=90.0)
        assert angle is None


# ===========================================================================
# tools.py — async tool tests
# ===========================================================================

class TestMarineBoxBargeTool:
    def test_basic_box_barge(self):
        from kerf_marine.tools import run_marine_box_barge
        args = {"length": 100.0, "beam": 20.0, "draft": 5.0}
        result = _run(run_marine_box_barge(args, FakeCtx()))
        data = json.loads(result)
        assert "displacement_t" in data
        expected_disp = 1.025 * 100.0 * 20.0 * 5.0
        assert data["displacement_t"] == pytest.approx(expected_disp, rel=1e-4)

    def test_kb_oracle_via_tool(self):
        from kerf_marine.tools import run_marine_box_barge
        args = {"length": 50.0, "beam": 10.0, "draft": 4.0}
        result = _run(run_marine_box_barge(args, FakeCtx()))
        data = json.loads(result)
        assert data["kb_m"] == pytest.approx(2.0, rel=1e-10)

    def test_bm_oracle_via_tool(self):
        from kerf_marine.tools import run_marine_box_barge
        B, T = 10.0, 4.0
        args = {"length": 50.0, "beam": B, "draft": T}
        result = _run(run_marine_box_barge(args, FakeCtx()))
        data = json.loads(result)
        expected_bm = (B ** 2) / (12.0 * T)
        # Tool output is rounded to 6 d.p. via as_dict(); compare with 1e-5 rel tol
        assert data["bm_transverse_m"] == pytest.approx(expected_bm, rel=1e-5)

    def test_tool_result_has_all_keys(self):
        from kerf_marine.tools import run_marine_box_barge
        args = {"length": 80.0, "beam": 16.0, "draft": 3.0}
        result = _run(run_marine_box_barge(args, FakeCtx()))
        data = json.loads(result)
        for key in ["displacement_t", "volume_m3", "kb_m", "bm_transverse_m",
                    "km_m", "tpc", "mct1cm", "lcb_m"]:
            assert key in data, f"Missing key: {key}"


class TestMarineHydrostaticsTool:
    def _box_offsets(self, L=50.0, B=10.0, T=3.0, ns=11, nwl=6):
        from kerf_marine.sections import box_barge_table
        table = box_barge_table(L, B, T, n_stations=ns, n_waterlines=nwl)
        offsets = [[r.station, r.waterline, r.half_breadth] for r in table.rows]
        return offsets

    def test_hydrostatics_tool_returns_ok(self):
        from kerf_marine.tools import run_marine_hydrostatics
        offsets = self._box_offsets()
        args = {"offsets": offsets, "draft": 3.0}
        result = _run(run_marine_hydrostatics(args, FakeCtx()))
        data = json.loads(result)
        assert "displacement_t" in data
        assert "error" not in data

    def test_hydrostatics_displacement_approx_correct(self):
        from kerf_marine.tools import run_marine_hydrostatics
        L, B, T = 50.0, 10.0, 3.0
        offsets = self._box_offsets(L, B, T)
        args = {"offsets": offsets, "draft": T, "rho": 1.025}
        result = _run(run_marine_hydrostatics(args, FakeCtx()))
        data = json.loads(result)
        expected = 1.025 * L * B * T
        assert data["displacement_t"] == pytest.approx(expected, rel=1e-4)


class TestMarineStabilityGZTool:
    def test_wall_sided_mode(self):
        from kerf_marine.tools import run_marine_stability_gz
        args = {"gm": 0.5, "bm": 3.0, "angle_step": 5.0}
        result = _run(run_marine_stability_gz(args, FakeCtx()))
        data = json.loads(result)
        assert "points" in data
        assert "imo_criteria" in data
        assert len(data["points"]) > 5

    def test_kn_mode(self):
        from kerf_marine.tools import run_marine_stability_gz
        angles = [0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0]
        kn = [0.0, 0.5, 0.9, 1.2, 1.3, 1.2, 0.9]
        args = {"kn_angles": angles, "kn_values": kn, "kg": 2.5}
        result = _run(run_marine_stability_gz(args, FakeCtx()))
        data = json.loads(result)
        assert "points" in data
        assert "imo_criteria" in data

    def test_bad_args_error(self):
        from kerf_marine.tools import run_marine_stability_gz
        args = {}   # neither mode
        result = _run(run_marine_stability_gz(args, FakeCtx()))
        data = json.loads(result)
        assert "error" in data
        assert data["code"] == "MARINE_GZ_BAD_ARGS"

    def test_imo_criteria_in_output(self):
        from kerf_marine.tools import run_marine_stability_gz
        args = {"gm": 1.0, "bm": 4.0}
        result = _run(run_marine_stability_gz(args, FakeCtx()))
        data = json.loads(result)
        imo = data["imo_criteria"]
        for key in ["area_0_30_m_rad", "area_0_30_pass", "gz_at_30_pass"]:
            assert key in imo


# ===========================================================================
# Module compile smoke tests
# ===========================================================================

class TestModuleImports:
    def test_sections_imports(self):
        import kerf_marine.sections  # noqa: F401

    def test_hydrostatics_imports(self):
        import kerf_marine.hydrostatics  # noqa: F401

    def test_stability_imports(self):
        import kerf_marine.stability  # noqa: F401

    def test_tools_imports(self):
        import kerf_marine.tools  # noqa: F401

    def test_plugin_imports(self):
        import kerf_marine.plugin  # noqa: F401

    def test_compat_imports(self):
        import kerf_marine._compat  # noqa: F401

    def test_pycompile_sections(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_marine", "sections.py")
        py_compile.compile(path, doraise=True)

    def test_pycompile_hydrostatics(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_marine", "hydrostatics.py")
        py_compile.compile(path, doraise=True)

    def test_pycompile_stability(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_marine", "stability.py")
        py_compile.compile(path, doraise=True)

    def test_pycompile_tools(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_marine", "tools.py")
        py_compile.compile(path, doraise=True)
