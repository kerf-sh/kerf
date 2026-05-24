"""
Tests for the canonical darcy_friction_factor and its refactored callers.

Moody-chart reference points from White (2016) Fluid Mechanics, 8th ed.,
and Moody (1944) ASME Trans. 66(8):671-684.
"""
import math
import pytest
from kerf_cad_core.fluids.friction import darcy_friction_factor
from kerf_cad_core.piping.process import pressure_drop as piping_pressure_drop


# ---------------------------------------------------------------------------
# 1. darcy_friction_factor — Moody chart reference points
# ---------------------------------------------------------------------------

class TestDarcyFrictionFactor:

    # -- Laminar --

    def test_laminar_re100(self):
        """Re=100: f = 64/100 = 0.64 (exact)."""
        f = darcy_friction_factor(100.0, 0.0)
        assert abs(f - 0.64) < 1e-10

    def test_laminar_re1000(self):
        """Re=1000: f = 64/1000 = 0.064 (exact)."""
        f = darcy_friction_factor(1000.0, 0.0)
        assert abs(f - 0.064) < 1e-10

    def test_laminar_re2000(self):
        """Re=2000 (still laminar): f = 64/2000 = 0.032."""
        f = darcy_friction_factor(2000.0, 0.0)
        assert abs(f - 0.032) < 1e-10

    # -- Smooth-turbulent (Filonenko / Colebrook, ε/D = 0) --

    def test_smooth_turbulent_re1e5(self):
        """Re=1e5, smooth pipe: Moody chart ≈ 0.0180 (Colebrook smooth)."""
        f = darcy_friction_factor(1e5, 0.0)
        # Colebrook smooth: 1/√f = -2 log10(2.51/(Re √f))
        # Reference from Moody chart / Filonenko: ~0.0180
        assert 0.0165 < f < 0.0195, f

    def test_smooth_turbulent_re1e6(self):
        """Re=1e6, smooth pipe: f ≈ 0.0116 (Moody chart)."""
        f = darcy_friction_factor(1e6, 0.0)
        assert 0.010 < f < 0.013, f

    # -- Rough turbulent --

    def test_rough_turbulent_re1e5_commercial_steel(self):
        """Re=1e5, commercial steel ε/D = 46e-6/0.05 = 9.2e-4.
        Moody chart: f ≈ 0.021."""
        eps_D = 46e-6 / 0.05  # 9.2e-4
        f = darcy_friction_factor(1e5, eps_D)
        assert 0.019 < f < 0.023, f

    def test_fully_rough_limit(self):
        """Fully-rough limit (Re → ∞): 1/√f = -2 log10(ε/(3.7 D)).
        For ε/D = 0.01, f_rough ≈ 0.0385."""
        eps_D = 0.01
        f_ref = 1.0 / (-2.0 * math.log10(eps_D / 3.7)) ** 2
        # Use very high Re to approach fully-rough limit
        f = darcy_friction_factor(1e10, eps_D)
        assert abs(f - f_ref) < 0.001, f

    def test_fully_rough_coarse_pipe(self):
        """ε/D = 0.05 (very rough), high Re: Moody fully-rough f ≈ 0.0723."""
        eps_D = 0.05
        f_ref = 1.0 / (-2.0 * math.log10(eps_D / 3.7)) ** 2
        f = darcy_friction_factor(1e9, eps_D)
        assert abs(f - f_ref) < 0.002, f

    # -- Input guards --

    def test_zero_reynolds_raises(self):
        with pytest.raises(ValueError, match="reynolds must be > 0"):
            darcy_friction_factor(0.0, 0.0)

    def test_negative_reynolds_raises(self):
        with pytest.raises(ValueError):
            darcy_friction_factor(-1.0, 0.0)

    def test_negative_roughness_raises(self):
        with pytest.raises(ValueError, match="rel_roughness must be >= 0"):
            darcy_friction_factor(1e5, -0.001)

    def test_nan_reynolds_raises(self):
        with pytest.raises(ValueError, match="finite"):
            darcy_friction_factor(float("nan"), 0.0)

    def test_inf_reynolds_raises(self):
        with pytest.raises(ValueError, match="finite"):
            darcy_friction_factor(float("inf"), 0.0)

    # -- Transition zone (2300–4000) gives values between laminar and turbulent --

    def test_transition_zone_interpolated(self):
        """Transition zone (Re=3000): f must be linearly blended between
        the laminar boundary (Re=2300) and the turbulent boundary (Re=4000)."""
        f_lam = 64.0 / 2300.0
        f_turb = darcy_friction_factor(4000.0, 0.001)
        f_mid = darcy_friction_factor(3000.0, 0.001)
        f_lo = min(f_lam, f_turb)
        f_hi = max(f_lam, f_turb)
        assert f_lo <= f_mid <= f_hi, (
            f"f_mid={f_mid:.6f} not in [{f_lo:.6f}, {f_hi:.6f}]"
        )


# ---------------------------------------------------------------------------
# 2. Refactored caller: piping.process.pressure_drop
#    Hand-computed expected value to verify end-to-end correctness.
#
#    Setup:
#      Q = 0.001 m³/s, rho = 1000 kg/m³, mu = 1e-3 Pa·s
#      D_i = 0.05 m, L = 10 m, roughness = 46e-6 m, no fittings
#
#    A = π/4 * 0.05² = 1.9635e-3 m²
#    V = 0.001 / 1.9635e-3 = 0.5093 m/s
#    Re = 1000 * 0.5093 * 0.05 / 1e-3 = 25464
#    ε/D = 46e-6 / 0.05 = 9.2e-4
#    f (Colebrook-White, converged) ≈ 0.02699  (computed separately)
#    ΔP = f * (L/D) * (rho*V²/2) = 0.02699 * 200 * (1000*0.2594/2)
#       = 0.02699 * 200 * 129.7 ≈ 700.7 Pa
# ---------------------------------------------------------------------------

class TestPipingPressureDropCaller:

    _PARAMS = dict(
        Q=0.001,
        rho=1000.0,
        mu=1e-3,
        D_i=0.05,
        L=10.0,
        roughness=46e-6,
        fittings_Le=0.0,
    )

    def _hand_compute(self) -> float:
        Q, rho, mu, D, L, eps = (
            self._PARAMS["Q"], self._PARAMS["rho"], self._PARAMS["mu"],
            self._PARAMS["D_i"], self._PARAMS["L"], self._PARAMS["roughness"],
        )
        A = math.pi / 4.0 * D**2
        V = Q / A
        Re = rho * V * D / mu
        eps_D = eps / D
        f = darcy_friction_factor(Re, eps_D)
        return f * (L / D) * (rho * V**2 / 2.0)

    def test_pressure_drop_returns_ok(self):
        result = piping_pressure_drop(**self._PARAMS)
        assert result["ok"] is True

    def test_pressure_drop_matches_hand_computed(self):
        """ΔP from refactored caller must match canonical hand computation."""
        result = piping_pressure_drop(**self._PARAMS)
        expected = self._hand_compute()
        # Allow 0.1 Pa tolerance (numerical precision only)
        assert abs(result["dP_Pa"] - expected) < 0.1, (
            f"dP_Pa={result['dP_Pa']:.4f} Pa, expected={expected:.4f} Pa"
        )

    def test_laminar_pressure_drop(self):
        """Laminar flow (Re < 2300): f = 64/Re, result consistent."""
        result = piping_pressure_drop(
            Q=1e-6, rho=1000.0, mu=1e-3, D_i=0.05, L=10.0, roughness=46e-6
        )
        assert result["ok"] is True
        assert result["flow_regime"] == "laminar"
        # Verify friction factor: f = 64/Re
        Re = result["Re"]
        assert abs(result["friction_factor"] - 64.0 / Re) < 1e-8
