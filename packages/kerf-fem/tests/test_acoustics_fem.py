"""
Hermetic test suite for kerf_fem.acoustics_fem — Helmholtz FEM acoustics.

Covers:
  - 1-D closed tube (rigid-rigid): f_n = n·c/(2L) within mesh tolerance
  - 2-D rectangular cavity: f = (c/2)√((p/Lx)²+(q/Ly)²) for low modes
  - Rigid-wall BC gives the closed-tube series
  - Open-open vs open-closed series differ correctly
  - Duct cut-on frequency = c/(2·width)
  - Absorbing boundary reduces resonance peak vs rigid
  - Mode energy / orthogonality
  - Analytic helpers (closed_tube_modes, open_closed_tube_modes, etc.)
  - Forced response consistency (1-D and 2-D)
  - Transmission loss (mass law, normal and oblique)
  - Error / input-validation paths

All tests are hermetic — no DB, no network, no heavy deps.
"""

from __future__ import annotations

import math

import pytest

from kerf_fem.acoustics_fem import (
    cavity_modes_1d,
    cavity_modes_2d,
    forced_response_1d,
    forced_response_2d,
    transmission_loss,
    duct_cut_on,
    absorbing_boundary_1d,
    closed_tube_modes,
    open_tube_modes,
    open_closed_tube_modes,
    rectangular_cavity_modes_2d,
    mode_orthogonality,
    _assemble_1d_helmholtz,
    _rect_acoustic_mesh,
)


# ---------------------------------------------------------------------------
# Physical constants / common params
# ---------------------------------------------------------------------------

C_AIR = 343.0    # m/s  (standard air, 20 °C)
RHO   = 1.21     # kg/m³


# ---------------------------------------------------------------------------
# 1. Analytic helper: closed_tube_modes
# ---------------------------------------------------------------------------

class TestClosedTubeModesAnalytic:

    def test_first_five_modes(self):
        L = 1.0
        res = closed_tube_modes(L, C_AIR, n_max=5)
        assert res["ok"]
        freqs = res["frequencies"]
        assert len(freqs) == 5
        for n, f in enumerate(freqs, start=1):
            f_expected = n * C_AIR / (2.0 * L)
            assert abs(f - f_expected) / f_expected < 1e-12, (
                f"mode {n}: {f:.4f} Hz, expected {f_expected:.4f} Hz"
            )

    def test_scaling_with_length(self):
        res1 = closed_tube_modes(1.0, C_AIR)
        res2 = closed_tube_modes(2.0, C_AIR)
        # Doubling L halves all frequencies
        for f1, f2 in zip(res1["frequencies"], res2["frequencies"]):
            assert abs(f1 / f2 - 2.0) < 1e-10

    def test_scaling_with_c(self):
        res1 = closed_tube_modes(1.0, C_AIR)
        res2 = closed_tube_modes(1.0, 2.0 * C_AIR)
        for f1, f2 in zip(res1["frequencies"], res2["frequencies"]):
            assert abs(f2 / f1 - 2.0) < 1e-10

    def test_bad_L(self):
        res = closed_tube_modes(0.0, C_AIR)
        assert res["ok"] is False

    def test_bad_c(self):
        res = closed_tube_modes(1.0, 0.0)
        assert res["ok"] is False


# ---------------------------------------------------------------------------
# 2. Analytic helper: open_closed_tube_modes (quarter-wave series)
# ---------------------------------------------------------------------------

class TestOpenClosedModesAnalytic:

    def test_quarter_wave_series(self):
        L = 1.0
        res = open_closed_tube_modes(L, C_AIR, n_max=4)
        assert res["ok"]
        freqs = res["frequencies"]
        for n_idx, f in enumerate(freqs):
            n = 2 * (n_idx + 1) - 1
            f_expected = n * C_AIR / (4.0 * L)
            assert abs(f - f_expected) / f_expected < 1e-12

    def test_differs_from_closed_closed(self):
        L = 1.0
        r_cc = closed_tube_modes(L, C_AIR, n_max=3)
        r_oc = open_closed_tube_modes(L, C_AIR, n_max=3)
        # The two series are distinct
        for fcc, foc in zip(r_cc["frequencies"], r_oc["frequencies"]):
            assert abs(fcc - foc) > 1.0   # differ by > 1 Hz for standard params


# ---------------------------------------------------------------------------
# 3. FEM 1-D cavity modes — rigid-rigid (closed tube)
# ---------------------------------------------------------------------------

class TestCavityModes1D:

    _L = 1.0
    _N_NODES = 51

    def test_rigid_rigid_closed_tube_modes(self):
        """FEM f_n must be within 1% of analytic f_n = n·c/(2L) for n=1..4."""
        res = cavity_modes_1d(
            L=self._L, c=C_AIR,
            n_nodes=self._N_NODES, n_modes=4,
            bc_left="rigid", bc_right="rigid",
        )
        assert res["ok"], res.get("reason")
        freqs_fem = res["frequencies"]
        for n, f_fem in enumerate(freqs_fem, start=1):
            f_analytic = n * C_AIR / (2.0 * self._L)
            rel_err = abs(f_fem - f_analytic) / f_analytic
            assert rel_err < 0.01, (
                f"mode {n}: FEM={f_fem:.4f}, analytic={f_analytic:.4f}, rel_err={rel_err:.4f}"
            )

    def test_modes_ascending(self):
        res = cavity_modes_1d(L=self._L, c=C_AIR, n_nodes=self._N_NODES, n_modes=5)
        assert res["ok"]
        freqs = res["frequencies"]
        for i in range(len(freqs) - 1):
            assert freqs[i] <= freqs[i + 1] + 1e-6

    def test_mode_shapes_length(self):
        res = cavity_modes_1d(L=self._L, c=C_AIR, n_nodes=self._N_NODES, n_modes=3)
        assert res["ok"]
        for shape in res["mode_shapes"]:
            assert len(shape) == self._N_NODES

    def test_x_coords(self):
        res = cavity_modes_1d(L=self._L, c=C_AIR, n_nodes=self._N_NODES)
        assert res["ok"]
        x = res["x_coords"]
        assert abs(x[0]) < 1e-12
        assert abs(x[-1] - self._L) < 1e-12

    def test_bad_L(self):
        res = cavity_modes_1d(L=0.0, c=C_AIR)
        assert res["ok"] is False

    def test_bad_c(self):
        res = cavity_modes_1d(L=1.0, c=-1.0)
        assert res["ok"] is False

    def test_bad_n_nodes(self):
        res = cavity_modes_1d(L=1.0, c=C_AIR, n_nodes=2)
        assert res["ok"] is False


# ---------------------------------------------------------------------------
# 4. FEM 1-D — open-open vs open-closed boundary series
# ---------------------------------------------------------------------------

class TestBoundaryConditionSeries:

    _L = 1.0

    def test_open_open_matches_closed_closed_series(self):
        """
        Open-open and closed-closed have the same frequency series f_n = n·c/(2L),
        but different mode shapes (cosine vs sine).
        """
        res_oo = cavity_modes_1d(
            L=self._L, c=C_AIR, n_nodes=51, n_modes=3,
            bc_left="open", bc_right="open",
        )
        assert res_oo["ok"], res_oo.get("reason")
        for n, f in enumerate(res_oo["frequencies"], start=1):
            f_expected = n * C_AIR / (2.0 * self._L)
            assert abs(f - f_expected) / f_expected < 0.01

    def test_open_closed_matches_quarter_wave_series(self):
        """
        Open-closed (one end p=0, other rigid): f_n = (2n-1)·c/(4L).
        """
        res = cavity_modes_1d(
            L=self._L, c=C_AIR, n_nodes=51, n_modes=4,
            bc_left="open", bc_right="rigid",
        )
        assert res["ok"], res.get("reason")
        for n_idx, f in enumerate(res["frequencies"]):
            n = 2 * (n_idx + 1) - 1
            f_expected = n * C_AIR / (4.0 * self._L)
            assert abs(f - f_expected) / f_expected < 0.01

    def test_open_closed_differs_from_closed_closed(self):
        """Fundamental of open-closed must be half that of closed-closed."""
        res_cc = cavity_modes_1d(L=self._L, c=C_AIR, n_nodes=51, n_modes=1,
                                 bc_left="rigid", bc_right="rigid")
        res_oc = cavity_modes_1d(L=self._L, c=C_AIR, n_nodes=51, n_modes=1,
                                 bc_left="open", bc_right="rigid")
        assert res_cc["ok"] and res_oc["ok"]
        # f_1(closed-closed) = c/2L; f_1(open-closed) = c/4L → ratio = 2
        ratio = res_cc["frequencies"][0] / res_oc["frequencies"][0]
        assert abs(ratio - 2.0) < 0.02


# ---------------------------------------------------------------------------
# 5. FEM 2-D rectangular cavity modes
# ---------------------------------------------------------------------------

class TestCavityModes2D:

    _LX, _LY = 2.0, 1.0

    def test_low_modes_within_tolerance(self):
        """
        2-D rigid cavity: f_{pq} = (c/2)√((p/Lx)²+(q/Ly)²).
        Check 4 lowest non-trivial modes within 5% (coarse mesh).
        """
        res_fem = cavity_modes_2d(
            Lx=self._LX, Ly=self._LY, c=C_AIR,
            nx=4, ny=4, n_modes=6, bc="rigid",
        )
        assert res_fem["ok"], res_fem.get("reason")

        res_analytic = rectangular_cavity_modes_2d(
            self._LX, self._LY, C_AIR, p_max=3, q_max=3
        )
        assert res_analytic["ok"]

        n_check = min(4, len(res_fem["frequencies"]), len(res_analytic["frequencies"]))
        for i in range(n_check):
            f_fem = res_fem["frequencies"][i]
            f_ana = res_analytic["frequencies"][i]
            rel_err = abs(f_fem - f_ana) / f_ana
            assert rel_err < 0.05, (
                f"mode {i}: FEM={f_fem:.2f}, analytic={f_ana:.2f}, rel={rel_err:.3f}"
            )

    def test_modes_ascending(self):
        res = cavity_modes_2d(Lx=1.0, Ly=1.0, c=C_AIR, nx=4, ny=4, n_modes=5)
        assert res["ok"]
        freqs = res["frequencies"]
        for i in range(len(freqs) - 1):
            assert freqs[i] <= freqs[i + 1] + 1.0  # 1 Hz tolerance for near-degenerate

    def test_mode_shapes_correct_length(self):
        res = cavity_modes_2d(Lx=1.0, Ly=1.0, c=C_AIR, nx=4, ny=4, n_modes=3)
        assert res["ok"]
        n_nodes = len(res["nodes"])
        for shape in res["mode_shapes"]:
            assert len(shape) == n_nodes

    def test_bad_dims(self):
        res = cavity_modes_2d(Lx=0.0, Ly=1.0, c=C_AIR)
        assert res["ok"] is False

    def test_bad_c(self):
        res = cavity_modes_2d(Lx=1.0, Ly=1.0, c=0.0)
        assert res["ok"] is False


# ---------------------------------------------------------------------------
# 6. Analytic 2-D rectangular cavity modes
# ---------------------------------------------------------------------------

class TestRectangularCavityAnalytic:

    def test_square_cavity_fundamental(self):
        """For a square L×L cavity, f_{10} = f_{01} = c/(2L)."""
        L = 1.0
        res = rectangular_cavity_modes_2d(L, L, C_AIR, p_max=1, q_max=1)
        assert res["ok"]
        freqs = res["frequencies"]
        f_expected = C_AIR / (2.0 * L)
        # First two non-trivial modes (1,0) and (0,1) should equal f_expected
        assert len(freqs) >= 2
        assert abs(freqs[0] - f_expected) / f_expected < 1e-10
        assert abs(freqs[1] - f_expected) / f_expected < 1e-10

    def test_rectangular_cavity_diagonal_mode(self):
        """f_{11} = (c/2) * sqrt((1/Lx)²+(1/Ly)²)."""
        Lx, Ly = 2.0, 1.0
        res = rectangular_cavity_modes_2d(Lx, Ly, C_AIR, p_max=1, q_max=1)
        assert res["ok"]
        # Mode (1,1):
        f11_expected = (C_AIR / 2.0) * math.sqrt((1.0 / Lx) ** 2 + (1.0 / Ly) ** 2)
        found = any(abs(f - f11_expected) / f11_expected < 1e-10 for f in res["frequencies"])
        assert found

    def test_excludes_plane_wave(self):
        """Mode (0,0) (uniform pressure) must not appear."""
        res = rectangular_cavity_modes_2d(1.0, 1.0, C_AIR, p_max=2, q_max=2)
        assert res["ok"]
        # All frequencies must be > 0
        assert all(f > 0.0 for f in res["frequencies"])

    def test_bad_dims(self):
        res = rectangular_cavity_modes_2d(0.0, 1.0, C_AIR)
        assert res["ok"] is False


# ---------------------------------------------------------------------------
# 7. Duct cut-on frequency
# ---------------------------------------------------------------------------

class TestDuctCutOn:

    def test_first_transverse_mode(self):
        """f_cut = c / (2 * width) for mode (1,0)."""
        width = 0.1
        res = duct_cut_on(width=width, c=C_AIR)
        assert res["ok"]
        f_expected = C_AIR / (2.0 * width)
        assert abs(res["f_cut"] - f_expected) / f_expected < 1e-10

    def test_mode_2_twice_mode_1(self):
        """f_cut(2,0) = 2 * f_cut(1,0)."""
        width = 0.05
        res1 = duct_cut_on(width=width, c=C_AIR, mode_m=1)
        res2 = duct_cut_on(width=width, c=C_AIR, mode_m=2)
        assert res1["ok"] and res2["ok"]
        assert abs(res2["f_cut"] / res1["f_cut"] - 2.0) < 1e-10

    def test_wavelength_is_consistent(self):
        """Wavelength = c / f_cut."""
        width = 0.2
        res = duct_cut_on(width=width, c=C_AIR)
        assert res["ok"]
        assert abs(res["wavelength"] - C_AIR / res["f_cut"]) < 1e-8

    def test_2d_duct_formula(self):
        """2-D duct: f_cut = c / (2 * width) for mode (1, 0)."""
        width = 0.3
        res = duct_cut_on(width=width, c=C_AIR, height=None, mode_m=1, mode_n=0)
        assert res["ok"]
        f_expected = C_AIR / (2.0 * width)
        assert abs(res["f_cut"] - f_expected) / f_expected < 1e-10

    def test_bad_width(self):
        res = duct_cut_on(width=0.0, c=C_AIR)
        assert res["ok"] is False

    def test_zero_zero_mode_error(self):
        res = duct_cut_on(width=0.1, c=C_AIR, mode_m=0, mode_n=0)
        assert res["ok"] is False


# ---------------------------------------------------------------------------
# 8. Transmission loss (mass law)
# ---------------------------------------------------------------------------

class TestTransmissionLoss:

    def test_mass_doubling_adds_6dB(self):
        """Mass law: doubling surface density adds ~6 dB at high frequencies."""
        freq = 1000.0
        res1 = transmission_loss(freq=freq, surface_density=5.0)
        res2 = transmission_loss(freq=freq, surface_density=10.0)
        assert res1["ok"] and res2["ok"]
        dTL = res2["TL"] - res1["TL"]
        # At high mass load, TL ≈ 20 log10(ωm/2ρc); doubling m → +6 dB
        # For large z, dTL ≈ 20 log10(2) = 6.02 dB.  Allow 15% tolerance.
        assert abs(dTL - 20.0 * math.log10(2.0)) < 1.5

    def test_tau_between_0_and_1(self):
        res = transmission_loss(freq=500.0, surface_density=12.0)
        assert res["ok"]
        assert 0.0 < res["tau"] <= 1.0

    def test_TL_positive(self):
        res = transmission_loss(freq=500.0, surface_density=5.0)
        assert res["ok"]
        assert res["TL"] > 0.0

    def test_normal_vs_oblique(self):
        """TL at oblique incidence < TL at normal incidence (less damping)."""
        res0 = transmission_loss(freq=1000.0, surface_density=10.0, angle_deg=0.0)
        res45 = transmission_loss(freq=1000.0, surface_density=10.0, angle_deg=45.0)
        assert res0["ok"] and res45["ok"]
        assert res0["TL"] > res45["TL"]

    def test_bad_freq(self):
        res = transmission_loss(freq=0.0, surface_density=5.0)
        assert res["ok"] is False

    def test_bad_surface_density(self):
        res = transmission_loss(freq=1000.0, surface_density=0.0)
        assert res["ok"] is False


# ---------------------------------------------------------------------------
# 9. Absorbing boundary reduces resonance peak
# ---------------------------------------------------------------------------

class TestAbsorbingBoundary1D:

    def _sweep(self, z_s: float, n_pts: int = 20):
        L = 1.0
        # Sweep around the first resonance of a rigid tube
        f1 = C_AIR / (2.0 * L)
        freq_range = [f1 * (0.5 + i / n_pts) for i in range(n_pts + 1)]
        return absorbing_boundary_1d(
            L=L, c=C_AIR, rho=RHO,
            freq_range=freq_range,
            specific_impedance=z_s,
            n_nodes=31,
            n_modes=4,
            source_node=0,
        )

    def test_absorbing_returns_ok(self):
        res = self._sweep(z_s=1.0)
        assert res["ok"], res.get("reason")
        assert len(res["pressure_rms"]) > 0

    def test_absorbing_reduces_peak_vs_rigid(self):
        """Peak pressure with absorbing end (Z_s=1) < near-rigid (Z_s=1000)."""
        res_abs = self._sweep(z_s=1.0)
        res_rigid = self._sweep(z_s=1000.0)
        assert res_abs["ok"] and res_rigid["ok"]
        peak_abs = max(res_abs["pressure_rms"])
        peak_rigid = max(res_rigid["pressure_rms"])
        assert peak_abs < peak_rigid, (
            f"Absorbing peak {peak_abs:.4f} not less than rigid peak {peak_rigid:.4f}"
        )

    def test_modal_freqs_returned(self):
        res = self._sweep(z_s=1.0)
        assert res["ok"]
        assert isinstance(res["modal_freqs"], list)
        assert len(res["modal_freqs"]) > 0

    def test_bad_impedance(self):
        res = absorbing_boundary_1d(
            L=1.0, c=C_AIR, rho=RHO, freq_range=[100.0],
            specific_impedance=0.0,
        )
        assert res["ok"] is False


# ---------------------------------------------------------------------------
# 10. Mode orthogonality / energy
# ---------------------------------------------------------------------------

class TestModeOrthogonality:

    def test_same_mode_not_orthogonal_to_itself(self):
        L = 1.0
        res = cavity_modes_1d(L=L, c=C_AIR, n_nodes=51, n_modes=2)
        assert res["ok"]
        phi0 = res["mode_shapes"][0]
        orth = mode_orthogonality(phi0, phi0, n_nodes=51, L=L)
        assert orth["ok"]
        # <φ, φ>_M = 1 (mass-normalised modes)
        assert abs(orth["dot_product"]) > 1e-6
        assert not orth["is_orthogonal"]

    def test_distinct_modes_orthogonal(self):
        L = 1.0
        n = 51
        res = cavity_modes_1d(L=L, c=C_AIR, n_nodes=n, n_modes=3)
        assert res["ok"]
        phi0 = res["mode_shapes"][0]
        phi1 = res["mode_shapes"][1]
        orth = mode_orthogonality(phi0, phi1, n_nodes=n, L=L)
        assert orth["ok"]
        assert orth["is_orthogonal"], (
            f"Modes 0 and 1 not orthogonal: dot={orth['dot_product']:.4e}"
        )

    def test_three_distinct_modes_pairwise_orthogonal(self):
        L = 1.0
        n = 51
        res = cavity_modes_1d(L=L, c=C_AIR, n_nodes=n, n_modes=4)
        assert res["ok"]
        shapes = res["mode_shapes"]
        for i in range(len(shapes)):
            for j in range(i + 1, len(shapes)):
                orth = mode_orthogonality(shapes[i], shapes[j], n_nodes=n, L=L)
                assert orth["ok"]
                assert orth["is_orthogonal"], (
                    f"Modes {i},{j} not orthogonal: dot={orth['dot_product']:.4e}"
                )

    def test_mismatched_lengths(self):
        orth = mode_orthogonality([1.0, 2.0], [1.0, 2.0, 3.0])
        assert orth["ok"] is False


# ---------------------------------------------------------------------------
# 11. Forced response 1-D sanity checks
# ---------------------------------------------------------------------------

class TestForcedResponse1D:

    def test_returns_ok_and_length(self):
        n = 31
        res = forced_response_1d(L=1.0, c=C_AIR, freq=50.0,
                                  source_node=0, n_nodes=n)
        assert res["ok"], res.get("reason")
        assert len(res["pressure"]) == n

    def test_wave_number_consistent(self):
        freq = 200.0
        res = forced_response_1d(L=1.0, c=C_AIR, freq=freq, source_node=0)
        assert res["ok"]
        k_expected = 2.0 * math.pi * freq / C_AIR
        assert abs(res["k"] - k_expected) / k_expected < 1e-10

    def test_pressure_nonzero_away_from_source(self):
        """Pressure must propagate — nodes away from source should have nonzero value."""
        res = forced_response_1d(L=2.0, c=C_AIR, freq=50.0,
                                  source_node=0, n_nodes=41,
                                  bc_left="rigid", bc_right="rigid")
        assert res["ok"]
        p = res["pressure"]
        # Sum of squares away from source must be nonzero
        far_energy = sum(v * v for v in p[5:])
        assert far_energy > 0.0

    def test_bad_freq(self):
        res = forced_response_1d(L=1.0, c=C_AIR, freq=-1.0, source_node=0)
        assert res["ok"] is False

    def test_bad_source_node(self):
        res = forced_response_1d(L=1.0, c=C_AIR, freq=100.0, source_node=999)
        assert res["ok"] is False


# ---------------------------------------------------------------------------
# 12. Forced response 2-D sanity checks
# ---------------------------------------------------------------------------

class TestForcedResponse2D:

    def test_returns_ok(self):
        res = forced_response_2d(Lx=1.0, Ly=1.0, c=C_AIR, freq=50.0,
                                  source_node=0, nx=4, ny=4)
        assert res["ok"], res.get("reason")

    def test_pressure_length_matches_nodes(self):
        nx, ny = 4, 4
        res = forced_response_2d(Lx=1.0, Ly=1.0, c=C_AIR, freq=50.0,
                                  source_node=0, nx=nx, ny=ny)
        assert res["ok"]
        assert len(res["pressure"]) == len(res["nodes"])

    def test_bad_dims(self):
        res = forced_response_2d(Lx=0.0, Ly=1.0, c=C_AIR, freq=50.0, source_node=0)
        assert res["ok"] is False


# ---------------------------------------------------------------------------
# 13. Mesh builder sanity
# ---------------------------------------------------------------------------

class TestMeshBuilder:

    def test_rect_mesh_node_count(self):
        nx, ny = 4, 3
        mesh = _rect_acoustic_mesh(1.0, 1.0, nx, ny)
        assert len(mesh["nodes"]) == (nx + 1) * (ny + 1)
        assert len(mesh["elements"]) == 2 * nx * ny

    def test_rect_mesh_connectivity_valid(self):
        nx, ny = 3, 3
        mesh = _rect_acoustic_mesh(1.0, 1.0, nx, ny)
        n_nodes = len(mesh["nodes"])
        for tri in mesh["elements"]:
            for idx in tri:
                assert 0 <= idx < n_nodes


# ---------------------------------------------------------------------------
# 14. FEM 1-D assembly sanity (stiffness / mass)
# ---------------------------------------------------------------------------

class TestAssemble1D:

    def test_mass_matrix_row_sum(self):
        """Consistent mass: each row should sum to L/n_elem (approximately)."""
        n = 5
        L = 1.0
        _, M = _assemble_1d_helmholtz(n, L, 0.0)
        row_sums = [sum(M[i]) for i in range(n)]
        # Each interior row: h/6 + 2h/3 + h/6 = h = L/(n-1) ... actually
        # Row i (interior): M[i][i-1] + M[i][i] + M[i][i+1] = h/6 + 2h/3 + h/6 = h
        h = L / (n - 1)
        # Interior rows
        for i in range(1, n - 1):
            assert abs(row_sums[i] - h) < 1e-12

    def test_stiffness_singular_before_bc(self):
        """K (free-free) should be singular: rigid body mode → K has zero eigenvalue."""
        n = 5
        L = 1.0
        K, _ = _assemble_1d_helmholtz(n, L, 0.0)
        # Row sums of K should be zero (partition of unity)
        for i in range(n):
            row_sum = sum(K[i])
            assert abs(row_sum) < 1e-12, f"row {i} sum={row_sum:.2e}"
