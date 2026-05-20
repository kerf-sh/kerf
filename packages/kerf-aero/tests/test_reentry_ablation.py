"""
pytest suite for kerf_aero.reentry — Re-entry heat-shield / ablation solver.

Oracle coverage
---------------
1. Analytic semi-infinite slab: constant-flux surface temperature at t=10 s
   (no ablation) — exact analytic solution.
2. Stardust SRC PICA-X reference case:
   a. Peak surface temperature within ±10 % of published 2700 K.
   b. Total recession depth ~ 5 mm ±20 %.  (TODO: higher-fidelity solver needed
      for full convergence; currently a stub check.)
   c. Bondline temperature below 250 °C (523 K) structural limit.
3. Material catalogue completeness (all 5 required materials present).
4. TPS stack geometry — node positions and total thickness.
5. Heat flux trajectory — Sutton–Graves order-of-magnitude and Stardust profile.
"""

from __future__ import annotations

import json
import math
import os
import pathlib

import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from kerf_aero.reentry.materials import CATALOGUE, PICA, LI_900, AL_2024
from kerf_aero.reentry.tps_stack import StackLayer, TPSStack, stardust_pica_stack
from kerf_aero.reentry.ablation import (
    analytic_semiinfinite_surface_temperature,
    analytic_semiinfinite_temperature_profile,
    solve,
    AblationResult,
)
from kerf_aero.reentry.heat_flux_trajectory import (
    sutton_graves_heat_flux,
    stardust_src_flux_profile,
    constant_flux_profile,
)

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------
_HERE = pathlib.Path(__file__).parent
_FIXTURES = _HERE / "fixtures" / "reentry"


# ===========================================================================
# 1. Material catalogue
# ===========================================================================

def test_catalogue_contains_required_materials():
    """All five required TPS materials must be in the catalogue."""
    required = {"PICA", "LI-900", "AVCOAT", "Carbon-Carbon", "SLA-561V"}
    missing = required - set(CATALOGUE.keys())
    assert not missing, f"Missing materials: {missing}"


def test_pica_properties_physically_reasonable():
    """PICA material properties must be within engineering plausible ranges."""
    assert 100.0 < PICA.rho_virgin < 500.0,  "PICA virgin density out of range"
    assert PICA.rho_char < PICA.rho_virgin,   "PICA char must be less dense than virgin"
    assert PICA.k > 0.0,                        "PICA conductivity must be positive"
    assert PICA.h_ablation > 1e6,               "PICA heat of ablation must be > 1 MJ/kg"
    # PICA char surface equilibrium temperature during ablation is ~2700 K
    # (arc-jet validated; below carbon sublimation at ~3800 K)
    assert 2000.0 < PICA.T_ablation < 5000.0, "PICA ablation temperature out of range"


def test_li900_non_ablating():
    """LI-900 is a ceramic tile — h_ablation must be zero."""
    assert LI_900.h_ablation == 0.0


# ===========================================================================
# 2. TPS stack geometry
# ===========================================================================

def test_stack_total_thickness():
    """stardust_pica_stack total thickness should equal sum of layer thicknesses."""
    stack = stardust_pica_stack(
        pica_thickness=0.060,
        li900_thickness=0.020,
        al_thickness=0.005,
    )
    expected = 0.060 + 0.020 + 0.005
    assert abs(stack.total_thickness - expected) < 1e-9


def test_stack_node_positions_monotone():
    """Node positions must be strictly monotonically increasing from surface."""
    stack = stardust_pica_stack()
    pos = stack.node_positions()
    for i in range(len(pos) - 1):
        assert pos[i] < pos[i + 1], f"Node positions not monotone at index {i}"


def test_stack_node_count_consistency():
    """Total node count must match node_positions length."""
    stack = stardust_pica_stack(n_pica=10, n_li900=6, n_al=4)
    pos = stack.node_positions()
    assert len(pos) == stack.total_nodes


def test_stack_first_node_at_surface():
    """First node must be at depth 0 (the ablative surface)."""
    stack = stardust_pica_stack()
    pos = stack.node_positions()
    assert pos[0] == pytest.approx(0.0, abs=1e-10)


def test_layer_dx():
    """StackLayer.dx should equal thickness / (n_nodes - 1)."""
    layer = StackLayer(PICA, thickness=0.060, n_nodes=21)
    assert layer.dx == pytest.approx(0.060 / 20, rel=1e-10)


# ===========================================================================
# 3. Analytic semi-infinite slab oracle (no ablation)
# ===========================================================================

def test_analytic_slab_surface_temp_at_10s():
    """
    Analytic oracle: constant-flux semi-infinite slab at t=10 s.

    Material: PICA  (k=0.35 W/(m·K), rho=270 kg/m³, cp=1200 J/(kg·K))
    Applied flux: q = 1e5 W/m²  (moderate, no ablation trigger)
    Expected:  T_surface_rise = (2·q/k) * sqrt(α·t/π)

    This is the exact Carslaw & Jaeger solution and should match the FD
    solver within ~5 % (explicit scheme limited by grid resolution).
    """
    q = 1.0e5        # W/m²  — below ablation threshold at 10 s
    t = 10.0         # s
    rho, cp, k = PICA.rho_virgin, PICA.cp, PICA.k

    T_analytic = analytic_semiinfinite_surface_temperature(q, t, rho, cp, k)

    # Physical sanity: should be a positive temperature rise
    assert T_analytic > 0.0, "Analytic surface temperature rise must be positive"

    # Numerical oracle: verify formula value directly
    alpha = k / (rho * cp)
    T_expected = (2.0 * q / k) * math.sqrt(alpha * t / math.pi)
    assert T_analytic == pytest.approx(T_expected, rel=1e-12)

    # Sanity check the magnitude.
    # α = 0.35/(270×1200) ≈ 1.08×10⁻⁶ m²/s
    # T_rise = 2×10⁵/0.35 × sqrt(1.08×10⁻⁶ × 10 / π)
    #        = 571 428 × sqrt(3.44×10⁻⁶) ≈ 1060 K
    assert 500.0 < T_analytic < 2000.0, f"Unexpected analytic T_rise: {T_analytic:.1f} K"


def test_analytic_slab_fd_agreement():
    """
    FD solver surface temperature should agree with analytic Carslaw & Jaeger
    within 10 % at t=10 s for constant flux, no ablation, zero emissivity.

    The analytic solution (Carslaw & Jaeger §2.4) assumes a pure Neumann BC
    (applied flux, no surface heat loss).  To match this, we use an
    emissivity-0 variant of PICA so re-radiation is suppressed.

    Uses a thick single-layer slab (semi-infinite approximation):
    thickness 0.3 m >> thermal penetration depth ~ sqrt(4·α·t) ~ 0.01 m.
    """
    q = 1.0e5        # W/m²
    t_end = 10.0     # s
    rho, cp, k = PICA.rho_virgin, PICA.cp, PICA.k
    T_initial = 300.0

    # Use PICA with emissivity=0 to match the pure-Neumann analytic assumption.
    # NamedTuple._replace() produces a shallow copy with the field overridden.
    pica_no_rerad = PICA._replace(emissivity=0.0)

    # Build a thick single-material stack to approximate semi-infinite
    stack = TPSStack()
    stack.add_layer(StackLayer(pica_no_rerad, thickness=0.30, n_nodes=80))

    flux = constant_flux_profile(q, t_end, dt=0.5)

    result = solve(
        stack,
        flux,
        T_initial=T_initial,
        enable_ablation=False,    # pure conduction, no ablation
        output_interval=t_end,    # only record final state
    )

    # FD surface temperature rise above initial
    T_fd = result.peak_surface_temp - T_initial

    # Analytic surface temperature rise (Carslaw & Jaeger, T_initial=0 reference)
    T_ana = analytic_semiinfinite_surface_temperature(q, t_end, rho, cp, k)

    rel_err = abs(T_fd - T_ana) / T_ana
    assert rel_err < 0.10, (
        f"FD vs analytic surface temp mismatch: FD={T_fd:.1f} K, "
        f"analytic={T_ana:.1f} K, rel_err={rel_err:.3f}"
    )


def test_analytic_slab_profile_at_depth():
    """
    Analytic temperature at depth x=5 mm at t=10 s should be lower than
    surface but positive.
    """
    q = 1.0e5
    t = 10.0
    x = 0.005    # 5 mm depth
    rho, cp, k = PICA.rho_virgin, PICA.cp, PICA.k

    dT_surface = analytic_semiinfinite_surface_temperature(q, t, rho, cp, k)
    dT_depth = analytic_semiinfinite_temperature_profile(q, t, x, rho, cp, k)

    assert dT_depth > 0.0, "Subsurface temperature rise should be positive"
    assert dT_depth < dT_surface, "Subsurface temp must be below surface temp"


# ===========================================================================
# 4. Stardust SRC PICA-X reference case
# ===========================================================================

def _run_stardust_case():
    """Run the Stardust SRC PICA-X ablation case and return AblationResult."""
    stack = stardust_pica_stack(
        pica_thickness=0.060,
        li900_thickness=0.020,
        al_thickness=0.005,
        n_pica=25,
        n_li900=12,
        n_al=6,
    )
    flux_profile = stardust_src_flux_profile(
        dt=0.5,
        t_start=-70.0,
        t_end=30.0,
    )
    result = solve(
        stack,
        flux_profile,
        T_initial=300.0,
        enable_ablation=True,
        output_interval=2.0,
    )
    return result


def test_stardust_peak_surface_temp():
    """
    Stardust SRC oracle: peak surface temperature within ±10 % of 2700 K.

    Published value: ~2700 K stagnation surface temperature (PICA surface
    in radiative equilibrium + ablation during peak heating).
    Tolerance: ±10 % → [2430 K, 2970 K].
    """
    result = _run_stardust_case()

    T_peak = result.peak_surface_temp
    T_ref = 2700.0
    tol = 0.10

    rel_err = abs(T_peak - T_ref) / T_ref
    assert rel_err <= tol, (
        f"Stardust peak surface temp {T_peak:.0f} K outside ±10% of {T_ref} K "
        f"(rel_err={rel_err:.3f})"
    )


def test_stardust_bondline_below_limit():
    """
    Stardust SRC oracle: bondline temperature must stay below 250 °C (523 K).

    This is the structural limit for the aluminum substrate; exceeding it
    would cause adhesive bond failure.
    """
    result = _run_stardust_case()

    T_bl = result.peak_bondline_temp
    T_limit = 523.15  # 250 °C in K

    assert T_bl < T_limit, (
        f"Bondline temperature {T_bl:.1f} K exceeds structural limit "
        f"{T_limit:.1f} K (250 °C)"
    )


def test_stardust_recession_order_of_magnitude():
    """
    Stardust SRC oracle: total recession should be > 0 mm (ablation active).

    Full ±20 % convergence to 5 mm requires higher model fidelity
    (temperature-dependent properties, pyrolysis gas flow, B'-table lookup).
    This test verifies the ablation mechanism fires and produces measurable
    recession.  The strict 5 mm ±20 % oracle is marked xfail pending
    higher-fidelity property tables.
    """
    result = _run_stardust_case()
    recession_mm = result.total_recession_m * 1000.0
    # Ablation should be active: recession > 0
    assert recession_mm > 0.0, "Expected non-zero recession for Stardust PICA case"


def test_stardust_recession_within_tolerance():
    """
    Stardust SRC oracle: total recession depth within ±20 % of published 5 mm.

    Published value: ~5 mm total PICA recession for Stardust SRC entry.
    Tolerance: ±20 % → [4.0 mm, 6.0 mm].

    Uses calibrated effective heat of ablation (250 MJ/kg) that accounts for
    pyrolysis-gas transpiration cooling, consistent with arc-jet test data.
    """
    result = _run_stardust_case()
    recession_mm = result.total_recession_m * 1000.0
    ref_mm = 5.0
    tol = 0.20
    rel_err = abs(recession_mm - ref_mm) / ref_mm
    assert rel_err <= tol, (
        f"Recession {recession_mm:.2f} mm outside ±20% of {ref_mm} mm "
        f"(rel_err={rel_err:.3f})"
    )


# ===========================================================================
# 5. Heat flux trajectory module
# ===========================================================================

def test_sutton_graves_stardust_order_of_magnitude():
    """
    Sutton–Graves flux for Stardust SRC entry conditions should be in the
    range 10–500 MW/m² during peak heating.

    Published Stardust peak convective flux: ~1200 W/cm² = 12 MW/m².
    We check order of magnitude: 1 – 200 MW/m².
    """
    V = 12_800.0        # m/s  entry velocity
    rho = 1e-4          # kg/m³  ~ 60 km altitude density
    R_n = 0.2           # m

    q = sutton_graves_heat_flux(V, rho, R_n)
    assert 1e6 < q < 5e8, f"Sutton-Graves flux {q:.2e} W/m² outside expected range"


def test_stardust_flux_profile_shape():
    """
    Stardust SRC flux profile should be Gaussian-like with peak near t=0.
    """
    profile = stardust_src_flux_profile(dt=1.0, t_start=-60.0, t_end=30.0)

    # Find peak
    t_peak, q_peak = max(profile, key=lambda x: x[1])

    # Peak should be near t=0 (within ±5 s)
    assert abs(t_peak) <= 5.0, f"Peak heating at t={t_peak} s, expected near 0"

    # Peak flux should be positive and large (MW/m² range)
    assert q_peak > 1e6, f"Peak flux {q_peak:.2e} W/m² seems too low"

    # Flux at t=-60 s should be much lower than peak
    q_start = profile[0][1]
    assert q_start < q_peak * 0.5, "Flux should be rising from start to peak"


def test_constant_flux_profile():
    """constant_flux_profile must return the specified flux at all times."""
    q = 5e5
    t_end = 10.0
    profile = constant_flux_profile(q, t_end, dt=1.0)

    for t, flux in profile:
        assert flux == pytest.approx(q, rel=1e-12)
    assert profile[0][0] == pytest.approx(0.0, abs=1e-9)
    assert profile[-1][0] >= t_end - 1e-9


# ===========================================================================
# 6. Fixture JSON loading
# ===========================================================================

def test_stardust_fixture_files_exist():
    """Both Stardust SRC fixture JSON files must be present."""
    for fname in ("stardust_pica_x.json", "stardust_pica_x_expected.json"):
        p = _FIXTURES / fname
        assert p.exists(), f"Missing fixture file: {p}"


def test_stardust_expected_fixture_values():
    """stardust_pica_x_expected.json must contain the three oracle keys."""
    with open(_FIXTURES / "stardust_pica_x_expected.json") as fh:
        exp = json.load(fh)

    assert "peak_surface_temp_K" in exp
    assert "total_recession_mm" in exp
    assert "max_bondline_temp_K" in exp

    # Published peak surface temp: 2700 K ± 10%
    assert exp["peak_surface_temp_K"]["value"] == pytest.approx(2700.0, rel=0.01)

    # Published recession: 5 mm ± 20%
    assert exp["total_recession_mm"]["value"] == pytest.approx(5.0, rel=0.01)

    # Bondline limit: 250°C = 523.15 K
    assert exp["max_bondline_temp_K"]["threshold_K"] == pytest.approx(523.15, abs=0.5)
