"""
Hermetic test suite for kerf_fem.em_highfreq — high-frequency EM analysis.

Covers:
  - rect_waveguide_modes():  TE10 cutoff = c/(2a) exact
  - circ_waveguide_modes():  TE11 cutoff = 1.841·c/(2πa) exact
  - microstrip_impedance():  50 Ω reference geometry within 5 %
  - transmission_line():     lossless matched S11≈0, |S21|≈1
  - quarter_wave_transformer(): |S11|≈0 at design freq, mismatch off-freq
  - abcd_to_s():             identity / through-line properties
  - abcd_cascade():          two sections = single double-length section
  - fdtd_1d():               free-space pulse arrival time ≈ L/c
  - resonant_cavity_1d():    f = c/(2L), λ = 2L
  - rectangular_cavity_resonance(): TE101 formula
  - stripline_impedance():   returns ok, Z0 > 0
  - error paths:             bad inputs return {"ok": False}

All tests are hermetic — no DB, no network, no heavy deps.
"""

from __future__ import annotations

import math

import pytest

from kerf_fem.em_highfreq import (
    transmission_line,
    microstrip_impedance,
    stripline_impedance,
    rect_waveguide_modes,
    circ_waveguide_modes,
    abcd_cascade,
    abcd_to_s,
    quarter_wave_transformer,
    fdtd_1d,
    resonant_cavity_1d,
    rectangular_cavity_resonance,
    _C0,
)

# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

C0 = 299_792_458.0     # m/s
MU0  = 4.0 * math.pi * 1e-7
EPS0 = 1.0 / (MU0 * C0 * C0)
Z_VAC = math.sqrt(MU0 / EPS0)   # ~376.73 Ω


# ===========================================================================
# 1.  Rectangular waveguide — TE10 cutoff
# ===========================================================================

class TestRectWaveguideModes:

    def test_te10_cutoff_exact(self):
        """TE10 cutoff freq must equal c/(2a) to within 1e-9 relative error."""
        a = 22.86e-3    # WR-90 a-dimension
        b = 10.16e-3
        res = rect_waveguide_modes(a, b, n_modes=6)
        assert res["ok"], res.get("reason")
        modes = res["modes"]
        # Find TE10
        te10 = next((m for m in modes if m["type"] == "TE" and m["m"] == 1 and m["n"] == 0), None)
        assert te10 is not None, "TE10 mode not found"
        fc_expected = C0 / (2.0 * a)
        assert abs(te10["fc"] - fc_expected) / fc_expected < 1e-9

    def test_te01_cutoff_exact(self):
        """TE01 cutoff = c/(2b)."""
        a = 22.86e-3
        b = 10.16e-3
        res = rect_waveguide_modes(a, b, n_modes=10)
        assert res["ok"]
        te01 = next((m for m in res["modes"] if m["type"] == "TE" and m["m"] == 0 and m["n"] == 1), None)
        assert te01 is not None, "TE01 not found"
        fc_expected = C0 / (2.0 * b)
        assert abs(te01["fc"] - fc_expected) / fc_expected < 1e-9

    def test_te10_is_dominant_for_standard_guide(self):
        """For a > b, the TE10 mode must have the lowest cutoff."""
        a, b = 22.86e-3, 10.16e-3
        res = rect_waveguide_modes(a, b, n_modes=6)
        assert res["ok"]
        fc_te10 = C0 / (2.0 * a)
        assert res["modes"][0]["fc"] == pytest.approx(fc_te10, rel=1e-9)

    def test_modes_sorted_ascending(self):
        """Returned modes must be sorted by increasing cutoff frequency."""
        res = rect_waveguide_modes(22.86e-3, 10.16e-3, n_modes=8)
        assert res["ok"]
        fcs = [m["fc"] for m in res["modes"]]
        assert fcs == sorted(fcs)

    def test_tm11_cutoff_formula(self):
        """TM11 cutoff = c/(2) * sqrt((1/a)^2 + (1/b)^2)."""
        a, b = 22.86e-3, 10.16e-3
        res = rect_waveguide_modes(a, b, n_modes=20)
        assert res["ok"]
        tm11 = next((m for m in res["modes"] if m["type"] == "TM" and m["m"] == 1 and m["n"] == 1), None)
        assert tm11 is not None
        fc_expected = C0 / 2.0 * math.sqrt((1.0 / a) ** 2 + (1.0 / b) ** 2)
        assert abs(tm11["fc"] - fc_expected) / fc_expected < 1e-9

    def test_bad_dimensions(self):
        res = rect_waveguide_modes(0.0, 10e-3)
        assert res["ok"] is False

    def test_dielectric_fill_scales_fc(self):
        """Filling with eps_r=4 halves the cutoff frequency."""
        a, b = 22.86e-3, 10.16e-3
        res_air = rect_waveguide_modes(a, b, n_modes=1)
        res_die = rect_waveguide_modes(a, b, n_modes=1, eps_r=4.0)
        assert res_air["ok"] and res_die["ok"]
        fc_ratio = res_air["modes"][0]["fc"] / res_die["modes"][0]["fc"]
        assert abs(fc_ratio - 2.0) < 1e-6


# ===========================================================================
# 2.  Circular waveguide — TE11 cutoff
# ===========================================================================

class TestCircWaveguideModes:

    def test_te11_cutoff_exact(self):
        """TE11 cutoff = 1.8412 * c / (2π a)  (dominant mode)."""
        a = 15e-3    # 15 mm radius
        p_prime_11 = 1.8412    # zero of J1'(x)
        fc_expected = p_prime_11 * C0 / (2.0 * math.pi * a)
        res = circ_waveguide_modes(a, n_modes=6)
        assert res["ok"], res.get("reason")
        te11 = next((m for m in res["modes"] if m["type"] == "TE" and m["m"] == 1 and m["n"] == 1), None)
        assert te11 is not None, "TE11 mode not found"
        assert abs(te11["fc"] - fc_expected) / fc_expected < 1e-4

    def test_te11_is_dominant(self):
        """TE11 must have the lowest cutoff frequency in a circular guide."""
        res = circ_waveguide_modes(15e-3, n_modes=6)
        assert res["ok"]
        assert res["modes"][0]["type"] == "TE"
        assert res["modes"][0]["m"] == 1
        assert res["modes"][0]["n"] == 1

    def test_tm01_cutoff(self):
        """TM01 cutoff = 2.4048 c / (2π a)."""
        a = 15e-3
        p_01 = 2.4048
        fc_expected = p_01 * C0 / (2.0 * math.pi * a)
        res = circ_waveguide_modes(a, n_modes=10)
        assert res["ok"]
        tm01 = next((m for m in res["modes"] if m["type"] == "TM" and m["m"] == 0 and m["n"] == 1), None)
        assert tm01 is not None
        assert abs(tm01["fc"] - fc_expected) / fc_expected < 1e-4

    def test_modes_sorted_ascending(self):
        res = circ_waveguide_modes(15e-3, n_modes=8)
        assert res["ok"]
        fcs = [m["fc"] for m in res["modes"]]
        assert fcs == sorted(fcs)

    def test_bad_radius(self):
        res = circ_waveguide_modes(0.0)
        assert res["ok"] is False


# ===========================================================================
# 3.  Microstrip impedance — 50 Ω reference geometry
# ===========================================================================

class TestMicrostripImpedance:

    def test_50ohm_reference(self):
        """
        For eps_r=4.2, the Hammerstad-Jensen formula gives Z0≈50 Ω at w/h≈2.5.
        Verify to within 5 % tolerance.
        """
        h = 1.524e-3
        w = h * 2.5       # w/h = 2.5 → Z0 ≈ 50 Ω for eps_r=4.2
        res = microstrip_impedance(w, h, eps_r=4.2)
        assert res["ok"], res.get("reason")
        assert abs(res["Z0"] - 50.0) / 50.0 < 0.05, f"Z0={res['Z0']:.2f} Ω, expected ≈50 Ω"

    def test_narrow_strip_higher_impedance(self):
        """A narrower strip (smaller w/h) must give higher Z0."""
        h = 1.524e-3
        res_narrow = microstrip_impedance(0.5 * h, h, eps_r=4.2)
        res_wide   = microstrip_impedance(3.0 * h, h, eps_r=4.2)
        assert res_narrow["ok"] and res_wide["ok"]
        assert res_narrow["Z0"] > res_wide["Z0"]

    def test_dispersion_eps_eff_increases_with_freq(self):
        """ε_eff(f) must approach eps_r as frequency increases."""
        h = 1.524e-3
        w = h * 1.95
        eps_r = 4.2
        res_low  = microstrip_impedance(w, h, eps_r=eps_r, freq=1e9)
        res_high = microstrip_impedance(w, h, eps_r=eps_r, freq=100e9)
        assert res_low["ok"] and res_high["ok"]
        assert res_high["eps_eff_f"] >= res_low["eps_eff_f"]

    def test_zero_freq_no_dispersion(self):
        """At freq=0, eps_eff_f must equal eps_eff."""
        res = microstrip_impedance(2e-3, 1e-3, eps_r=3.5, freq=0.0)
        assert res["ok"]
        assert res["eps_eff_f"] == pytest.approx(res["eps_eff"], rel=1e-9)

    def test_bad_width(self):
        res = microstrip_impedance(0.0, 1e-3, eps_r=4.0)
        assert res["ok"] is False

    def test_bad_height(self):
        res = microstrip_impedance(2e-3, 0.0, eps_r=4.0)
        assert res["ok"] is False


# ===========================================================================
# 4.  Transmission line — lossless matched
# ===========================================================================

class TestTransmissionLine:

    def test_matched_lossless_S11_zero(self):
        """Lossless line, ZL = Z0 = 50Ω → |S11| = 0 exactly."""
        res = transmission_line(Z0=50.0, beta=100.0, length=0.1, freq=1e9,
                                Zs=50.0, ZL=50.0)
        assert res["ok"], res.get("reason")
        assert res["|S11|"] < 1e-12, f"|S11|={res['|S11|']}"

    def test_matched_lossless_S21_unity(self):
        """Lossless matched line → |S21| = 1."""
        res = transmission_line(Z0=50.0, beta=100.0, length=0.5, freq=2e9,
                                Zs=50.0, ZL=50.0)
        assert res["ok"]
        assert abs(res["|S21|"] - 1.0) < 1e-10, f"|S21|={res['|S21|']}"

    def test_open_circuit_S11_unity(self):
        """Open-circuit load (ZL→∞ approximated as very large) → |Γ_L|≈1."""
        res = transmission_line(Z0=50.0, beta=0.0, length=0.0, freq=1e9,
                                Zs=50.0, ZL=1e12)
        assert res["ok"]
        gamma_L = res["Gamma_L"]
        assert abs(abs(gamma_L[0]) - 1.0) < 0.01, f"Γ_L={gamma_L}"

    def test_zero_length_Zin_equals_ZL(self):
        """For zero-length line, Zin must equal ZL."""
        ZL = 75.0
        res = transmission_line(Z0=50.0, beta=500.0, length=0.0, freq=1e9,
                                Zs=50.0, ZL=ZL)
        assert res["ok"]
        Zin_re, Zin_im = res["Zin"]
        assert abs(Zin_re - ZL) < 1e-6, f"Zin={Zin_re:.4f} expected {ZL}"
        assert abs(Zin_im) < 1e-6

    def test_half_wave_line_Zin_equals_ZL(self):
        """Half-wave (θ=π) lossless line: Zin = ZL."""
        ZL = 75.0
        res = transmission_line(Z0=50.0, beta=math.pi, length=1.0, freq=1e9,
                                Zs=50.0, ZL=ZL)
        assert res["ok"]
        Zin_re, Zin_im = res["Zin"]
        assert abs(Zin_re - ZL) < 0.01, f"Zin_re={Zin_re:.4f} expected {ZL}"
        assert abs(Zin_im) < 0.05, f"Zin_im={Zin_im:.4f} expected ~0"

    def test_bad_Z0(self):
        res = transmission_line(Z0=-50.0, beta=100.0, length=0.1, freq=1e9)
        assert res["ok"] is False

    def test_vswr_matched(self):
        """Matched load → VSWR = 1."""
        res = transmission_line(Z0=50.0, beta=100.0, length=0.1, freq=1e9,
                                Zs=50.0, ZL=50.0)
        assert res["ok"]
        assert abs(res["VSWR"] - 1.0) < 1e-9


# ===========================================================================
# 5.  Quarter-wave transformer
# ===========================================================================

class TestQuarterWaveTransformer:

    def test_matched_at_design_freq(self):
        """At f=f0, the λ/4 transformer into ZL=100Ω from Z0=50Ω gives |S11|≈0."""
        Z0, ZL, f0 = 50.0, 100.0, 1e9
        res = quarter_wave_transformer(Z0, ZL, freq=f0, f0=f0)
        assert res["ok"], res.get("reason")
        assert res["|S11|"] < 0.01, f"|S11|={res['|S11|']:.4f} at design freq"

    def test_S21_near_unity_at_design_freq(self):
        """At f=f0, lossless transformer → |S21| ≈ 1 (power conservation)."""
        Z0, ZL, f0 = 50.0, 100.0, 1e9
        res = quarter_wave_transformer(Z0, ZL, freq=f0, f0=f0)
        assert res["ok"]
        assert res["|S21|"] > 0.98, f"|S21|={res['|S21|']:.4f}"

    def test_mismatch_off_design_freq(self):
        """At f = 2·f0 (θ = π), the transformer gives full reflection into ZL≠Z0."""
        Z0, ZL, f0 = 50.0, 100.0, 1e9
        res_off = quarter_wave_transformer(Z0, ZL, freq=2.0 * f0, f0=f0)
        assert res_off["ok"]
        # At f=2f0, electrical length θ=π → series half-wave: Zin = ZL ≠ Z0
        # so |S11| > 0 for ZL != Z0
        res_on = quarter_wave_transformer(Z0, ZL, freq=f0, f0=f0)
        assert res_off["|S11|"] > res_on["|S11|"]

    def test_Zt_formula(self):
        """Transformer impedance Zt = sqrt(Z0 * ZL)."""
        Z0, ZL = 50.0, 200.0
        res = quarter_wave_transformer(Z0, ZL, freq=1e9, f0=1e9)
        assert res["ok"]
        assert abs(res["Zt"] - math.sqrt(Z0 * ZL)) < 1e-9

    def test_bad_ZL(self):
        res = quarter_wave_transformer(50.0, 0.0, 1e9, 1e9)
        assert res["ok"] is False

    def test_bad_f0(self):
        res = quarter_wave_transformer(50.0, 100.0, 1e9, 0.0)
        assert res["ok"] is False


# ===========================================================================
# 6.  ABCD cascade & abcd_to_s
# ===========================================================================

class TestABCDAndSParams:

    def _tl_abcd(self, Z0: float, theta: float) -> list:
        """ABCD matrix of a lossless TL section with electrical length theta."""
        cos_t = math.cos(theta)
        sin_t = math.sin(theta)
        A = (cos_t, 0.0)
        B = (0.0, Z0 * sin_t)
        C = (0.0, sin_t / Z0)
        D = (cos_t, 0.0)
        return [[A, B], [C, D]]

    def test_through_line_S21_unity(self):
        """A zero-length through line (θ=0): S21 = 1, S11 = 0."""
        abcd = self._tl_abcd(50.0, 0.0)
        res = abcd_to_s(abcd, Z0=50.0)
        assert res["ok"]
        s11 = res["S11"]
        s21 = res["S21"]
        assert abs(s11[0]) < 1e-12 and abs(s11[1]) < 1e-12
        assert abs(s21[0] - 1.0) < 1e-12 and abs(s21[1]) < 1e-12

    def test_cascade_two_half_sections_equals_full(self):
        """
        Cascading two θ/2 sections must equal a single θ section.
        """
        Z0 = 50.0
        theta = 1.2   # rad
        half = self._tl_abcd(Z0, theta / 2.0)
        full = self._tl_abcd(Z0, theta)

        cascade_res = abcd_cascade([half, half])
        assert cascade_res["ok"]
        M = cascade_res["ABCD"]

        s_cascade = abcd_to_s(M, Z0)
        s_full    = abcd_to_s(full, Z0)
        assert s_cascade["ok"] and s_full["ok"]

        for key in ("S11", "S21", "S12", "S22"):
            re_c, im_c = s_cascade[key]
            re_f, im_f = s_full[key]
            assert abs(re_c - re_f) < 1e-9, f"{key} re mismatch: {re_c} vs {re_f}"
            assert abs(im_c - im_f) < 1e-9, f"{key} im mismatch"

    def test_empty_stages_error(self):
        res = abcd_cascade([])
        assert res["ok"] is False

    def test_abcd_to_s_bad_Z0(self):
        abcd = self._tl_abcd(50.0, 0.5)
        res = abcd_to_s(abcd, Z0=0.0)
        assert res["ok"] is False

    def test_S_reciprocal_for_symmetric_line(self):
        """For a lossless symmetric TL, S12 = S21."""
        abcd = self._tl_abcd(50.0, 0.7)
        res = abcd_to_s(abcd, Z0=50.0)
        assert res["ok"]
        s21 = res["S21"]
        s12 = res["S12"]
        assert abs(s21[0] - s12[0]) < 1e-9
        assert abs(s21[1] - s12[1]) < 1e-9


# ===========================================================================
# 7.  1-D FDTD — pulse propagation speed
# ===========================================================================

class TestFDTD1D:

    def test_pulse_arrival_approx_L_over_c(self):
        """
        Free-space Gaussian pulse launched at node 0, observed at node n//2.
        Arrival time must be within 20 % of d/c₀ where d = length/2.
        (20 % tolerance accounts for coarse Δt and pulse-width effects.)
        """
        n_cells = 200
        length  = 0.3     # 30 cm
        obs     = n_cells // 2
        n_steps = 400

        res = fdtd_1d(
            length=length,
            n_cells=n_cells,
            n_steps=n_steps,
            eps_r=1.0,
            mu_r=1.0,
            source_node=0,
            source_type="gaussian",
            obs_node=obs,
            pulse_width=20,
            amplitude=1.0,
        )
        assert res["ok"], res.get("reason")

        d = length / 2.0
        t_expected = d / C0
        t_arrived  = res["arrival_time"]

        assert t_arrived > 0.0, "pulse never arrived"
        assert abs(t_arrived - t_expected) / t_expected < 0.20, (
            f"arrival={t_arrived:.3e} s, expected≈{t_expected:.3e} s "
            f"(ratio={t_arrived/t_expected:.2f})"
        )

    def test_E_obs_nonzero_after_arrival(self):
        """After the pulse arrives, E_obs must have non-negligible values."""
        res = fdtd_1d(length=0.3, n_cells=200, n_steps=400,
                      source_node=0, obs_node=100, pulse_width=20)
        assert res["ok"]
        peak = max(abs(v) for v in res["E_obs"])
        assert peak > 0.01

    def test_dx_dt_returned(self):
        """dx and dt must be consistent with dx = length/n_cells."""
        n_cells = 100
        length = 1.0
        res = fdtd_1d(length=length, n_cells=n_cells, n_steps=100,
                      source_node=0, obs_node=50)
        assert res["ok"]
        assert abs(res["dx"] - length / n_cells) < 1e-15
        assert res["dt"] > 0.0

    def test_fdtd_bad_length(self):
        res = fdtd_1d(length=0.0, n_cells=100, n_steps=100)
        assert res["ok"] is False

    def test_fdtd_bad_n_cells(self):
        res = fdtd_1d(length=1.0, n_cells=1, n_steps=100)
        assert res["ok"] is False

    def test_fdtd_bad_source_node(self):
        res = fdtd_1d(length=1.0, n_cells=100, n_steps=100, source_node=200)
        assert res["ok"] is False

    def test_dielectric_slows_pulse(self):
        """In eps_r=4 medium, pulse takes 2× longer to arrive than in vacuum."""
        n_cells, length, n_steps = 200, 0.3, 800
        kw = dict(length=length, n_cells=n_cells, n_steps=n_steps,
                  source_node=0, obs_node=n_cells // 2, pulse_width=20)
        res_vac = fdtd_1d(**kw, eps_r=1.0)
        res_die = fdtd_1d(**kw, eps_r=4.0)
        assert res_vac["ok"] and res_die["ok"]
        # Pulse in eps_r=4 medium travels at c/2 → 2× longer
        # Arrival step should be larger in the dielectric case
        if res_vac["arrival_step"] < n_steps and res_die["arrival_step"] < n_steps:
            assert res_die["arrival_step"] > res_vac["arrival_step"]


# ===========================================================================
# 8.  Resonant cavity
# ===========================================================================

class TestResonantCavity1D:

    def test_fundamental_resonance_formula(self):
        """f_1 = c/(2L) for lossless air-filled 1-D cavity."""
        L = 0.15    # 15 cm
        res = resonant_cavity_1d(length=L)
        assert res["ok"], res.get("reason")
        f_expected = C0 / (2.0 * L)
        assert abs(res["f_resonant"] - f_expected) / f_expected < 1e-9

    def test_cavity_wavelength(self):
        """λ_1 = 2L for the fundamental mode."""
        L = 0.1
        res = resonant_cavity_1d(length=L, n_mode=1)
        assert res["ok"]
        assert abs(res["wavelength"] - 2.0 * L) < 1e-12

    def test_second_harmonic(self):
        """f_2 = 2 * f_1."""
        L = 0.2
        res1 = resonant_cavity_1d(length=L, n_mode=1)
        res2 = resonant_cavity_1d(length=L, n_mode=2)
        assert res1["ok"] and res2["ok"]
        assert abs(res2["f_resonant"] / res1["f_resonant"] - 2.0) < 1e-9

    def test_lossless_Q_is_infinite(self):
        """With R_wall=0, Q must be infinity."""
        res = resonant_cavity_1d(length=0.1, R_wall=0.0)
        assert res["ok"]
        assert math.isinf(res["Q"])

    def test_lossy_Q_finite(self):
        """Non-zero wall resistance gives finite Q."""
        res = resonant_cavity_1d(length=0.1, R_wall=1e-3)
        assert res["ok"]
        assert res["Q"] > 0.0
        assert not math.isinf(res["Q"])

    def test_dielectric_fill_scales_f(self):
        """eps_r=4 fill halves the resonant frequency."""
        L = 0.1
        res_air = resonant_cavity_1d(length=L)
        res_die = resonant_cavity_1d(length=L, eps_r=4.0)
        assert res_air["ok"] and res_die["ok"]
        assert abs(res_die["f_resonant"] / res_air["f_resonant"] - 0.5) < 1e-9

    def test_bad_length(self):
        res = resonant_cavity_1d(length=0.0)
        assert res["ok"] is False


# ===========================================================================
# 9.  Rectangular cavity resonance
# ===========================================================================

class TestRectangularCavityResonance:

    def test_te101_formula(self):
        """TE101: f = c/2 * sqrt((1/a)^2 + (1/d)^2)."""
        a, b, d = 22.86e-3, 10.16e-3, 30.0e-3
        res = rectangular_cavity_resonance(a, b, d, m=1, n=0, p=1)
        assert res["ok"], res.get("reason")
        f_expected = C0 / 2.0 * math.sqrt((1.0 / a) ** 2 + (1.0 / d) ** 2)
        assert abs(res["f_resonant"] - f_expected) / f_expected < 1e-9

    def test_all_zero_mode_error(self):
        res = rectangular_cavity_resonance(0.1, 0.05, 0.1, m=0, n=0, p=0)
        assert res["ok"] is False

    def test_dielectric_fill(self):
        """eps_r=4 should halve f."""
        a, b, d = 0.1, 0.05, 0.1
        res_air = rectangular_cavity_resonance(a, b, d, m=1, n=0, p=1)
        res_die = rectangular_cavity_resonance(a, b, d, m=1, n=0, p=1, eps_r=4.0)
        assert res_air["ok"] and res_die["ok"]
        assert abs(res_die["f_resonant"] / res_air["f_resonant"] - 0.5) < 1e-9

    def test_bad_dimensions(self):
        res = rectangular_cavity_resonance(0.0, 0.05, 0.1, m=1, n=0, p=1)
        assert res["ok"] is False


# ===========================================================================
# 10.  Stripline impedance
# ===========================================================================

class TestStriplineImpedance:

    def test_returns_ok(self):
        res = stripline_impedance(w=2e-3, b=5e-3, eps_r=2.33)
        assert res["ok"]
        assert res["Z0"] > 0.0

    def test_narrower_strip_higher_impedance(self):
        b = 5e-3
        res_n = stripline_impedance(w=1e-3, b=b, eps_r=2.33)
        res_w = stripline_impedance(w=4e-3, b=b, eps_r=2.33)
        assert res_n["ok"] and res_w["ok"]
        assert res_n["Z0"] > res_w["Z0"]

    def test_eps_eff_equals_eps_r(self):
        """Stripline: eps_eff = eps_r (no dispersion)."""
        eps_r = 3.5
        res = stripline_impedance(w=2e-3, b=5e-3, eps_r=eps_r)
        assert res["ok"]
        assert abs(res["eps_eff"] - eps_r) < 1e-9

    def test_bad_width(self):
        res = stripline_impedance(w=0.0, b=5e-3, eps_r=2.33)
        assert res["ok"] is False

    def test_bad_separation(self):
        res = stripline_impedance(w=2e-3, b=0.0, eps_r=2.33)
        assert res["ok"] is False
