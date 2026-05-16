"""
Hermetic tests for kerf_cad_core.dynamics — rigid-body dynamics.

Coverage (≥30 tests):
  rigidbody.rectilinear_kinematics          — s, v for constant-acceleration
  rigidbody.projectile_motion               — x, y, vx, vy, range
  rigidbody.rotational_kinematics           — θ, ω for constant angular accel
  rigidbody.relative_motion_velocity        — v_B = v_A + v_B/A
  rigidbody.newton_translation              — a = F/m
  rigidbody.euler_rotation                  — α = M/I
  rigidbody.general_plane_motion            — combined translation + rotation
  rigidbody.kinetic_energy                  — T = ½mv² + ½Iω²
  rigidbody.work_energy_theorem             — energy balance
  rigidbody.spring_potential_energy         — V_s = ½kx²
  rigidbody.power_from_torque               — P = M·ω
  rigidbody.power_from_force                — P = F·v
  rigidbody.linear_impulse                  — mv2 = mv1 + F·Δt
  rigidbody.angular_impulse                 — L2 = L1 + M·Δt
  rigidbody.direct_impact                   — post-impact velocities
  rigidbody.oblique_impact                  — 2-D oblique impact
  rigidbody.moi_solid_cylinder              — I = ½mr²
  rigidbody.moi_hollow_cylinder             — I = ½m(ro²+ri²)
  rigidbody.moi_solid_sphere                — I = 2/5 mr²
  rigidbody.moi_thin_rod                    — centroid and end axis
  rigidbody.moi_rectangular_plate           — polar MOI
  rigidbody.parallel_axis                   — Steiner's theorem
  rigidbody.flywheel_sizing                 — I from energy fluctuation
  rigidbody.flywheel_rim                    — rim cross-section
  rigidbody.static_balance                  — single-plane unbalance
  rigidbody.dynamic_balance_two_plane       — two-plane correction
  rigidbody.residual_unbalance              — U = m·e
  rigidbody.iso1940_grade                   — grade check + warning
  rigidbody.shaking_force_primary           — primary shaking force
  rigidbody.shaking_force_secondary         — secondary shaking force
  rigidbody.gyroscopic_moment               — M = I·ωs·ωp
  error paths                               — invalid inputs → ok:False

All tests are pure-Python and hermetic: no OCC, no DB, no network.
Formulas verified against Hibbeler "Engineering Mechanics: Dynamics" 14th ed.
and Beer & Johnston "Vector Mechanics: Dynamics" 12th ed. hand calculations.

Author: imranparuk
"""
from __future__ import annotations

import math

import pytest

from kerf_cad_core.dynamics.rigidbody import (
    rectilinear_kinematics,
    projectile_motion,
    rotational_kinematics,
    relative_motion_velocity,
    newton_translation,
    euler_rotation,
    general_plane_motion,
    kinetic_energy,
    work_energy_theorem,
    spring_potential_energy,
    power_from_torque,
    power_from_force,
    linear_impulse,
    angular_impulse,
    direct_impact,
    oblique_impact,
    moi_solid_cylinder,
    moi_hollow_cylinder,
    moi_solid_sphere,
    moi_thin_rod,
    moi_rectangular_plate,
    parallel_axis,
    flywheel_sizing,
    flywheel_rim,
    static_balance,
    dynamic_balance_two_plane,
    residual_unbalance,
    iso1940_grade,
    shaking_force_primary,
    shaking_force_secondary,
    gyroscopic_moment,
)


# ===========================================================================
# 1. Rectilinear kinematics
# ===========================================================================

def test_rectilinear_zero_accel():
    """Constant velocity: s = v0·t, v = v0."""
    r = rectilinear_kinematics(v0=10.0, a=0.0, t=5.0)
    assert r["ok"]
    assert r["s"] == pytest.approx(50.0)
    assert r["v"] == pytest.approx(10.0)


def test_rectilinear_freefall():
    """Free-fall from rest: s = ½·g·t², v = g·t. Hibbeler Ex. 12-1."""
    g = 9.80665
    t = 3.0
    r = rectilinear_kinematics(v0=0.0, a=g, t=t, s0=0.0)
    assert r["ok"]
    assert r["s"] == pytest.approx(0.5 * g * t ** 2, rel=1e-6)
    assert r["v"] == pytest.approx(g * t, rel=1e-6)


def test_rectilinear_deceleration():
    """Brake from 20 m/s at -5 m/s² for 2 s."""
    r = rectilinear_kinematics(v0=20.0, a=-5.0, t=2.0)
    assert r["ok"]
    assert r["s"] == pytest.approx(30.0)   # 20*2 - ½*5*4 = 40 - 10 = 30
    assert r["v"] == pytest.approx(10.0)


def test_rectilinear_invalid_t():
    r = rectilinear_kinematics(v0=1.0, a=0.0, t=-1.0)
    assert not r["ok"]


# ===========================================================================
# 2. Projectile motion
# ===========================================================================

def test_projectile_horizontal():
    """Horizontal launch (theta=0): y = -½g t², x = v0 t."""
    r = projectile_motion(v0=20.0, theta_deg=0.0, t=2.0)
    assert r["ok"]
    assert r["x"] == pytest.approx(40.0)
    assert r["y"] == pytest.approx(-0.5 * 9.80665 * 4.0, rel=1e-6)


def test_projectile_45deg_range():
    """45° launch maximises range: R = v0²/g. Verify at peak time."""
    v0 = 30.0
    g = 9.80665
    theta = 45.0
    t_peak = v0 * math.sin(math.radians(theta)) / g
    r = projectile_motion(v0=v0, theta_deg=theta, t=t_peak)
    assert r["ok"]
    # y should be at its peak (vy == 0)
    assert abs(r["vy"]) < 1e-9
    expected_range = v0 ** 2 * math.sin(math.radians(2 * theta)) / g
    assert r["range_m"] == pytest.approx(expected_range, rel=1e-6)


def test_projectile_invalid_theta():
    r = projectile_motion(v0=10.0, theta_deg=91.0, t=1.0)
    assert not r["ok"]


# ===========================================================================
# 3. Rotational kinematics
# ===========================================================================

def test_rotational_constant_speed():
    """No angular acceleration: ω constant, θ = ω0·t."""
    r = rotational_kinematics(omega0=10.0, alpha=0.0, t=4.0)
    assert r["ok"]
    assert r["omega"] == pytest.approx(10.0)
    assert r["theta"] == pytest.approx(40.0)


def test_rotational_spin_up():
    """Motor accelerates at 5 rad/s² from rest for 3 s. Hibbeler Ex. 16-3."""
    r = rotational_kinematics(omega0=0.0, alpha=5.0, t=3.0)
    assert r["ok"]
    assert r["omega"] == pytest.approx(15.0)
    assert r["theta"] == pytest.approx(22.5)   # ½ × 5 × 9


def test_rotational_omega_sq_consistency():
    """Check ω² = ω0² + 2α(θ - θ0) is consistent."""
    r = rotational_kinematics(omega0=2.0, alpha=3.0, t=4.0)
    assert r["ok"]
    omega_computed = math.sqrt(max(r["omega_sq"], 0))
    assert omega_computed == pytest.approx(abs(r["omega"]), rel=1e-9)


# ===========================================================================
# 4. Relative motion velocity
# ===========================================================================

def test_relative_velocity_2d():
    """v_B = [3, 4] + [1, -1] = [4, 3], |v_B| = 5."""
    r = relative_motion_velocity([3.0, 4.0], [1.0, -1.0])
    assert r["ok"]
    assert r["v_B"] == pytest.approx([4.0, 3.0])
    assert r["v_mag"] == pytest.approx(5.0)


def test_relative_velocity_3d():
    r = relative_motion_velocity([1.0, 2.0, 3.0], [0.0, 0.0, -3.0])
    assert r["ok"]
    assert r["v_B"] == pytest.approx([1.0, 2.0, 0.0])
    assert r["v_mag"] == pytest.approx(math.sqrt(5.0))


def test_relative_velocity_dim_mismatch():
    r = relative_motion_velocity([1.0, 2.0], [1.0, 2.0, 3.0])
    assert not r["ok"]


# ===========================================================================
# 5. Newton translation & Euler rotation
# ===========================================================================

def test_newton_translation_basic():
    """F = 100 N, m = 5 kg → a = 20 m/s²."""
    r = newton_translation(F_net=100.0, m=5.0)
    assert r["ok"]
    assert r["a"] == pytest.approx(20.0)


def test_newton_translation_invalid_mass():
    r = newton_translation(F_net=10.0, m=0.0)
    assert not r["ok"]


def test_euler_rotation_basic():
    """M = 50 N·m, I = 2 kg·m² → α = 25 rad/s²."""
    r = euler_rotation(M_net=50.0, I=2.0)
    assert r["ok"]
    assert r["alpha"] == pytest.approx(25.0)


def test_euler_rotation_negative_moment():
    """Negative moment gives negative α (deceleration)."""
    r = euler_rotation(M_net=-30.0, I=5.0)
    assert r["ok"]
    assert r["alpha"] == pytest.approx(-6.0)


# ===========================================================================
# 6. General plane motion
# ===========================================================================

def test_general_plane_motion_basic():
    """Cylinder rolling on flat surface: Fx=10, Fy=-20, MG=5, m=2, IG=0.5."""
    r = general_plane_motion(F_x=10.0, F_y=-20.0, M_G=5.0, m=2.0, I_G=0.5)
    assert r["ok"]
    assert r["ax"] == pytest.approx(5.0)
    assert r["ay"] == pytest.approx(-10.0)
    assert r["alpha"] == pytest.approx(10.0)


def test_general_plane_motion_invalid():
    r = general_plane_motion(F_x=0.0, F_y=0.0, M_G=0.0, m=-1.0, I_G=1.0)
    assert not r["ok"]


# ===========================================================================
# 7. Kinetic energy
# ===========================================================================

def test_kinetic_energy_translational_only():
    """T = ½ × 10 × 4² = 80 J."""
    r = kinetic_energy(m=10.0, v=4.0)
    assert r["ok"]
    assert r["T_total"] == pytest.approx(80.0)
    assert r["T_rot"] == pytest.approx(0.0)


def test_kinetic_energy_combined():
    """Rolling disk: T_trans = ½mv², T_rot = ½Iω². Hibbeler Ex. 18-2."""
    m = 5.0
    v = 3.0
    r_disk = 0.5  # radius
    I = 0.5 * m * r_disk ** 2   # = 0.625 kg·m²
    omega = v / r_disk           # = 6 rad/s (rolling without slip)
    r = kinetic_energy(m=m, v=v, I=I, omega=omega)
    assert r["ok"]
    T_trans = 0.5 * m * v ** 2   # = 22.5 J
    T_rot = 0.5 * I * omega ** 2  # = 11.25 J
    assert r["T_trans"] == pytest.approx(T_trans)
    assert r["T_rot"] == pytest.approx(T_rot)
    assert r["T_total"] == pytest.approx(T_trans + T_rot)


# ===========================================================================
# 8. Work-energy theorem
# ===========================================================================

def test_work_energy_satisfied():
    """If W_nc = T2 - T1, balance should be 0."""
    r = work_energy_theorem(KE1=100.0, KE2=180.0, W_nc=80.0)
    assert r["ok"]
    assert r["satisfied"]
    assert abs(r["balance"]) < 1e-9


def test_work_energy_unsatisfied():
    r = work_energy_theorem(KE1=100.0, KE2=200.0, W_nc=50.0)
    assert r["ok"]
    assert not r["satisfied"]
    assert r["balance"] == pytest.approx(50.0)


# ===========================================================================
# 9. Spring potential energy
# ===========================================================================

def test_spring_pe():
    """V_s = ½ × 1000 × 0.05² = 1.25 J."""
    r = spring_potential_energy(k=1000.0, x=0.05)
    assert r["ok"]
    assert r["V_s"] == pytest.approx(1.25)


def test_spring_pe_symmetric():
    """V_s is same for +x and -x."""
    r1 = spring_potential_energy(k=500.0, x=0.1)
    r2 = spring_potential_energy(k=500.0, x=-0.1)
    assert r1["ok"] and r2["ok"]
    assert r1["V_s"] == pytest.approx(r2["V_s"])


# ===========================================================================
# 10. Power
# ===========================================================================

def test_power_from_torque():
    """P = 100 N·m × 20 rad/s = 2000 W."""
    r = power_from_torque(M=100.0, omega=20.0)
    assert r["ok"]
    assert r["P_W"] == pytest.approx(2000.0)


def test_power_from_force():
    """P = 500 N × 4 m/s = 2000 W."""
    r = power_from_force(F=500.0, v=4.0)
    assert r["ok"]
    assert r["P_W"] == pytest.approx(2000.0)


# ===========================================================================
# 11. Impulse-momentum
# ===========================================================================

def test_linear_impulse_from_rest():
    """F = 200 N for 0.5 s: mv2 = 0 + 100 = 100 kg·m/s."""
    r = linear_impulse(F=200.0, dt=0.5)
    assert r["ok"]
    assert r["impulse"] == pytest.approx(100.0)
    assert r["mv2"] == pytest.approx(100.0)


def test_linear_impulse_with_initial():
    """mv1 = 50, F = 100 N for 1 s: mv2 = 150."""
    r = linear_impulse(F=100.0, dt=1.0, mv1=50.0)
    assert r["ok"]
    assert r["mv2"] == pytest.approx(150.0)


def test_angular_impulse_basic():
    """M = 20 N·m for 3 s from L1 = 10: L2 = 70."""
    r = angular_impulse(M=20.0, dt=3.0, L1=10.0)
    assert r["ok"]
    assert r["L2"] == pytest.approx(70.0)
    assert r["angular_impulse"] == pytest.approx(60.0)


# ===========================================================================
# 12. Direct central impact
# ===========================================================================

def test_direct_impact_perfectly_elastic():
    """Equal-mass elastic collision: velocities swap. e = 1.
    Hibbeler Ex. 15-6 style."""
    r = direct_impact(m1=5.0, v1=10.0, m2=5.0, v2=0.0, e=1.0)
    assert r["ok"]
    assert r["v1_prime"] == pytest.approx(0.0, abs=1e-10)
    assert r["v2_prime"] == pytest.approx(10.0)
    assert r["energy_loss"] == pytest.approx(0.0, abs=1e-9)


def test_direct_impact_perfectly_plastic():
    """Perfectly plastic: bodies stick together. e = 0.
    m1=3, v1=6, m2=1, v2=0: v_common = 18/4 = 4.5 m/s."""
    r = direct_impact(m1=3.0, v1=6.0, m2=1.0, v2=0.0, e=0.0)
    assert r["ok"]
    assert r["v1_prime"] == pytest.approx(4.5)
    assert r["v2_prime"] == pytest.approx(4.5)
    # KE loss = ½×3×36 - ½×4×4.5² = 54 - 40.5 = 13.5 J
    assert r["energy_loss"] == pytest.approx(13.5)


def test_direct_impact_clamped_e():
    """e > 1 should be clamped to 1.0 with a warning."""
    r = direct_impact(m1=2.0, v1=5.0, m2=2.0, v2=0.0, e=1.5)
    assert r["ok"]
    assert r["e"] == pytest.approx(1.0)
    assert len(r["warnings"]) >= 1


def test_direct_impact_invalid_mass():
    r = direct_impact(m1=0.0, v1=5.0, m2=1.0, v2=0.0, e=0.5)
    assert not r["ok"]


# ===========================================================================
# 13. Oblique impact
# ===========================================================================

def test_oblique_impact_tangential_unchanged():
    """y-components (tangential) must be unchanged after oblique impact."""
    r = oblique_impact(m1=2.0, v1x=5.0, v1y=3.0, m2=3.0, v2x=0.0, v2y=-1.0, e=0.8)
    assert r["ok"]
    assert r["v1y_prime"] == pytest.approx(3.0)
    assert r["v2y_prime"] == pytest.approx(-1.0)


def test_oblique_impact_momentum_conservation():
    """Total x-momentum must be conserved."""
    m1, v1x, m2, v2x = 2.0, 6.0, 3.0, -2.0
    r = oblique_impact(m1=m1, v1x=v1x, v1y=0.0, m2=m2, v2x=v2x, v2y=0.0, e=0.6)
    assert r["ok"]
    px_before = m1 * v1x + m2 * v2x
    px_after = m1 * r["v1x_prime"] + m2 * r["v2x_prime"]
    assert px_after == pytest.approx(px_before, rel=1e-9)


# ===========================================================================
# 14. Mass moments of inertia
# ===========================================================================

def test_moi_solid_cylinder():
    """I = ½ × 10 × 0.3² = 0.45 kg·m²."""
    r = moi_solid_cylinder(m=10.0, r=0.3)
    assert r["ok"]
    assert r["I"] == pytest.approx(0.45)


def test_moi_hollow_cylinder():
    """I = ½ × 5 × (0.4² + 0.2²) = ½ × 5 × 0.2 = 0.5 kg·m²."""
    r = moi_hollow_cylinder(m=5.0, r_o=0.4, r_i=0.2)
    assert r["ok"]
    assert r["I"] == pytest.approx(0.5)


def test_moi_hollow_cylinder_invalid():
    """r_i >= r_o should fail."""
    r = moi_hollow_cylinder(m=5.0, r_o=0.2, r_i=0.3)
    assert not r["ok"]


def test_moi_solid_sphere():
    """I = 2/5 × 2 × 0.5² = 0.2 kg·m²."""
    r = moi_solid_sphere(m=2.0, r=0.5)
    assert r["ok"]
    assert r["I"] == pytest.approx(0.2)


def test_moi_thin_rod_centroid():
    """I = 1/12 × 6 × 2² = 2.0 kg·m²."""
    r = moi_thin_rod(m=6.0, L=2.0, axis="centroid")
    assert r["ok"]
    assert r["I"] == pytest.approx(2.0)


def test_moi_thin_rod_end():
    """I = 1/3 × 6 × 2² = 8.0 kg·m²."""
    r = moi_thin_rod(m=6.0, L=2.0, axis="end")
    assert r["ok"]
    assert r["I"] == pytest.approx(8.0)


def test_moi_thin_rod_parallel_axis_check():
    """I_end should equal I_centroid + m × (L/2)². Steiner consistency."""
    m, L = 6.0, 2.0
    r_c = moi_thin_rod(m=m, L=L, axis="centroid")
    r_e = moi_thin_rod(m=m, L=L, axis="end")
    assert r_c["ok"] and r_e["ok"]
    # I_end = I_centroid + m*(L/2)^2
    assert r_e["I"] == pytest.approx(r_c["I"] + m * (L / 2) ** 2)


def test_moi_rectangular_plate():
    """I_z = 1/12 × 3 × (0.4² + 0.3²) = 1/4 × 0.25 = 0.0625 kg·m²."""
    r = moi_rectangular_plate(m=3.0, a=0.4, b=0.3)
    assert r["ok"]
    expected = (3.0 / 12.0) * (0.16 + 0.09)
    assert r["I_z"] == pytest.approx(expected)
    assert r["I_z"] == pytest.approx(r["I_x"] + r["I_y"])


def test_parallel_axis():
    """I = 0.5 + 2 × 0.3² = 0.5 + 0.18 = 0.68 kg·m²."""
    r = parallel_axis(I_cm=0.5, m=2.0, d=0.3)
    assert r["ok"]
    assert r["I"] == pytest.approx(0.68)


# ===========================================================================
# 15. Flywheel sizing
# ===========================================================================

def test_flywheel_sizing_basic():
    """I = ΔE / (ω² Cs) = 2000 / (200² × 0.02) = 2000/800 = 2.5 kg·m²."""
    r = flywheel_sizing(E_fluctuation=2000.0, omega_mean=200.0, Cs=0.02)
    assert r["ok"]
    assert r["I_required"] == pytest.approx(2.5, rel=1e-6)


def test_flywheel_sizing_large_Cs_warning():
    """Cs > 0.2 should trigger a warning."""
    r = flywheel_sizing(E_fluctuation=500.0, omega_mean=100.0, Cs=0.5)
    assert r["ok"]
    assert len(r["warnings"]) >= 1


def test_flywheel_rim_round_trip():
    """Rim A_cs round-trip: given I, compute A_cs, then recompute I."""
    rho = 7200.0   # kg/m³ cast iron
    r_mean = 0.5   # m
    b = 0.1        # m
    I_req = 10.0   # kg·m²
    r = flywheel_rim(I_required=I_req, rho=rho, r_mean=r_mean, b=b)
    assert r["ok"]
    # Cross-check: I = m_rim × r_mean² (thin-rim approximation)
    I_check = r["m_rim"] * r_mean ** 2
    assert I_check == pytest.approx(I_req, rel=1e-4)


# ===========================================================================
# 16. Rotating-mass balancing
# ===========================================================================

def test_static_balance_two_equal_opposite():
    """Two equal masses 180° apart → resultant = 0."""
    r = static_balance(
        masses=[2.0, 2.0],
        radii=[0.5, 0.5],
        angles_deg=[0.0, 180.0],
    )
    assert r["ok"]
    assert r["resultant_mr"] == pytest.approx(0.0, abs=1e-9)


def test_static_balance_single_mass():
    """Single mass: correction must equal its m·r."""
    r = static_balance(masses=[3.0], radii=[0.2], angles_deg=[45.0])
    assert r["ok"]
    assert r["correction_mr"] == pytest.approx(3.0 * 0.2, rel=1e-9)
    # Correction must be opposite
    expected_correction_angle = (45.0 + 180.0) % 360.0
    assert r["correction_angle_deg"] == pytest.approx(expected_correction_angle, abs=0.01)


def test_dynamic_balance_two_plane_single_mass():
    """Single unbalance mass at z = 0.3 m; planes at z=0 and z=1.
    Hand calc: take moments about plane B (z=1):
    cA × (0-1) + m·r·cos(θ)·(0.3-1) = 0 → cA_x = m·r·cos(θ)·0.7
    Similarly for y.
    """
    m, r_mass, theta = 4.0, 0.1, 30.0
    zA, zB = 0.0, 1.0
    z_mass = 0.3

    r = dynamic_balance_two_plane(
        masses=[m],
        radii=[r_mass],
        angles_deg=[theta],
        axial_positions=[z_mass],
        plane_a_pos=zA,
        plane_b_pos=zB,
    )
    assert r["ok"]

    # Check force balance: cA + cB + unbalance = 0 (vector)
    theta_rad = math.radians(theta)
    ub_x = m * r_mass * math.cos(theta_rad)
    ub_y = m * r_mass * math.sin(theta_rad)

    cA_x = r["correction_A_mr"] * math.cos(math.radians(r["correction_A_angle"]))
    cA_y = r["correction_A_mr"] * math.sin(math.radians(r["correction_A_angle"]))
    cB_x = r["correction_B_mr"] * math.cos(math.radians(r["correction_B_angle"]))
    cB_y = r["correction_B_mr"] * math.sin(math.radians(r["correction_B_angle"]))

    assert cA_x + cB_x + ub_x == pytest.approx(0.0, abs=1e-9)
    assert cA_y + cB_y + ub_y == pytest.approx(0.0, abs=1e-9)


def test_dynamic_balance_plane_identity_error():
    """plane_a_pos == plane_b_pos should fail."""
    r = dynamic_balance_two_plane(
        masses=[1.0], radii=[0.1], angles_deg=[0.0],
        axial_positions=[0.2], plane_a_pos=0.0, plane_b_pos=0.0,
    )
    assert not r["ok"]


def test_residual_unbalance_basic():
    """U = 10 g × 5 mm = 50 g·mm."""
    r = residual_unbalance(m_correction=10.0, e=5.0)
    assert r["ok"]
    assert r["U_g_mm"] == pytest.approx(50.0)


def test_iso1940_grade_within():
    """Rotor 20 kg at 1500 rpm (157 rad/s), G6.3 grade.
    eper_perm = 6.3 / 157 = 0.04013 mm.
    U_perm = 0.04013 × 20000 g = 802.5 g·mm.
    Use U = 500 g·mm → within grade."""
    omega = 2 * math.pi * 1500 / 60   # ≈ 157.08 rad/s
    r = iso1940_grade(U_g_mm=500.0, m_rotor_kg=20.0, omega_rad_s=omega, grade="G6.3")
    assert r["ok"]
    assert r["within_grade"]
    assert len(r["warnings"]) == 0


def test_iso1940_grade_exceeds():
    """U far exceeds G2.5 → warning and within_grade = False."""
    omega = 2 * math.pi * 3000 / 60  # 314 rad/s
    r = iso1940_grade(U_g_mm=5000.0, m_rotor_kg=5.0, omega_rad_s=omega, grade="G2.5")
    assert r["ok"]
    assert not r["within_grade"]
    assert len(r["warnings"]) >= 1


def test_iso1940_invalid_grade():
    r = iso1940_grade(U_g_mm=100.0, m_rotor_kg=10.0, omega_rad_s=100.0, grade="G99")
    assert not r["ok"]


# ===========================================================================
# 17. Reciprocating shaking forces
# ===========================================================================

def test_shaking_force_primary_tdc():
    """At TDC (theta=0), cos(0)=1 → F_primary = m·r·ω². Beer Ex."""
    m_r, r, omega = 1.5, 0.08, 200.0
    expected = m_r * r * omega ** 2
    res = shaking_force_primary(m_recip=m_r, r=r, omega=omega, theta_deg=0.0)
    assert res["ok"]
    assert res["F_primary"] == pytest.approx(expected)


def test_shaking_force_primary_bdc():
    """At BDC (theta=180°), cos(180°)=-1 → F_primary = -m·r·ω²."""
    m_r, r, omega = 1.5, 0.08, 200.0
    res = shaking_force_primary(m_recip=m_r, r=r, omega=omega, theta_deg=180.0)
    assert res["ok"]
    assert res["F_primary"] == pytest.approx(-m_r * r * omega ** 2, rel=1e-9)


def test_shaking_force_secondary_tdc():
    """At TDC, cos(0)=1 → F_secondary = m·r·ω²/n."""
    m_r, r, omega, n = 1.5, 0.08, 200.0, 4.0
    expected = m_r * r * omega ** 2 / n
    res = shaking_force_secondary(m_recip=m_r, r=r, omega=omega, n=n, theta_deg=0.0)
    assert res["ok"]
    assert res["F_secondary"] == pytest.approx(expected)


def test_shaking_force_secondary_90deg():
    """At 90°, cos(180°) = -1 → F_secondary = -m·r·ω²/n."""
    m_r, r, omega, n = 2.0, 0.1, 150.0, 3.5
    expected = -m_r * r * omega ** 2 / n
    res = shaking_force_secondary(m_recip=m_r, r=r, omega=omega, n=n, theta_deg=90.0)
    assert res["ok"]
    assert res["F_secondary"] == pytest.approx(expected, rel=1e-9)


def test_shaking_force_secondary_invalid_n():
    """n <= 1 should fail."""
    res = shaking_force_secondary(m_recip=1.0, r=0.05, omega=100.0, n=0.8, theta_deg=0.0)
    assert not res["ok"]


# ===========================================================================
# 18. Gyroscopic moment
# ===========================================================================

def test_gyroscopic_moment_basic():
    """M = 0.5 × 100 × 2.0 = 100 N·m. Hibbeler Ex. 21-5."""
    r = gyroscopic_moment(I_spin=0.5, omega_spin=100.0, omega_precession=2.0)
    assert r["ok"]
    assert r["M_gyro"] == pytest.approx(100.0)


def test_gyroscopic_moment_invalid():
    r = gyroscopic_moment(I_spin=-1.0, omega_spin=10.0, omega_precession=1.0)
    assert not r["ok"]


# ===========================================================================
# Externally-citable reference cases (production-confidence validation)
# Cross-checked vs Hibbeler "Engineering Mechanics: Dynamics" 14th ed.,
# Beer & Johnston "Vector Mechanics" 12th ed., ISO 1940-1:2003.
# ===========================================================================

from kerf_cad_core.dynamics.rigidbody import (  # noqa: E402
    rectilinear_kinematics as _ref_rect,
    projectile_motion as _ref_proj,
    direct_impact as _ref_impact,
    moi_solid_cylinder as _ref_moi_cyl,
    moi_solid_sphere as _ref_moi_sph,
    moi_thin_rod as _ref_moi_rod,
    parallel_axis as _ref_pax,
    flywheel_sizing as _ref_fly,
    iso1940_grade as _ref_iso1940,
    shaking_force_primary as _ref_shake1,
    gyroscopic_moment as _ref_gyro,
)


class TestDynamicsExternalReferences:
    """Validated against Hibbeler/Beer dynamics & ISO 1940-1 relations."""

    def test_rectilinear_hibbeler_12_2(self):
        # Hibbeler §12-2: s=s0+v0t+½at²; v=v0+at; v²=v0²+2a(s−s0).
        r = _ref_rect(5.0, 2.0, 3.0, 10.0)
        assert r["s"] == pytest.approx(10 + 5 * 3 + 0.5 * 2 * 9, rel=1e-12)
        assert r["v"] == pytest.approx(5 + 2 * 3, rel=1e-12)
        assert r["v_sq"] == pytest.approx(25 + 2 * 2 * (r["s"] - 10), rel=1e-12)

    def test_projectile_range_hibbeler_12_6(self):
        # Hibbeler §12-6: 45° gives max range = v0²/g.
        r = _ref_proj(20.0, 45.0, 0.0, g=9.81)
        assert r["range_m"] == pytest.approx(20.0 ** 2 / 9.81, rel=1e-9)

    def test_direct_impact_beer_13_13(self):
        # Beer §13.13: momentum + COR. m1=2,v1=10,m2=3,v2=0,e=0.8.
        r = _ref_impact(2.0, 10.0, 3.0, 0.0, 0.8)
        M = 5.0
        v1p = (2 * 10 + 0 - 3 * 0.8 * 10) / M
        v2p = (2 * 10 + 0 + 2 * 0.8 * 10) / M
        assert r["v1_prime"] == pytest.approx(v1p, rel=1e-12)
        assert r["v2_prime"] == pytest.approx(v2p, rel=1e-12)

    def test_impact_perfectly_elastic_conserves_ke(self):
        # Beer §13.13: e=1 → kinetic energy conserved (energy_loss≈0).
        r = _ref_impact(2.0, 5.0, 3.0, -2.0, 1.0)
        assert r["energy_loss"] == pytest.approx(0.0, abs=1e-9)

    def test_moi_solid_cylinder_hibbeler_appB(self):
        # Hibbeler App. B: I = ½ m r². m=10, r=0.2 → 0.2.
        r = _ref_moi_cyl(10.0, 0.2)
        assert r["I"] == pytest.approx(0.5 * 10.0 * 0.2 ** 2, rel=1e-12)

    def test_moi_solid_sphere_hibbeler_appB(self):
        # Hibbeler App. B: I = 2/5 m r².
        r = _ref_moi_sph(5.0, 0.1)
        assert r["I"] == pytest.approx(0.4 * 5.0 * 0.1 ** 2, rel=1e-12)

    def test_moi_thin_rod_hibbeler_appB(self):
        # Hibbeler App. B: centroid 1/12 mL²; end 1/3 mL².
        rc = _ref_moi_rod(3.0, 2.0, axis="centroid")
        re = _ref_moi_rod(3.0, 2.0, axis="end")
        assert rc["I"] == pytest.approx(3.0 * 4.0 / 12.0, rel=1e-12)
        assert re["I"] == pytest.approx(3.0 * 4.0 / 3.0, rel=1e-12)

    def test_parallel_axis_steiner(self):
        # Beer §9.11: I = I_cm + m d². Rod centroid + (L/2)² → end value.
        Icm = 3.0 * 4.0 / 12.0
        r = _ref_pax(Icm, 3.0, 1.0)
        assert r["I"] == pytest.approx(Icm + 3.0 * 1.0 ** 2, rel=1e-12)
        assert r["I"] == pytest.approx(3.0 * 4.0 / 3.0, rel=1e-12)  # = rod-about-end

    def test_flywheel_sizing_shigley_16_6(self):
        # Shigley Eq (16-61): I = ΔE/(ω²·Cs). ΔE=2000, ω=200, Cs=0.04.
        r = _ref_fly(2000.0, 200.0, 0.04)
        assert r["I_required"] == pytest.approx(2000.0 / (200.0 ** 2 * 0.04), rel=1e-12)

    def test_iso1940_permissible_unbalance(self):
        # ISO 1940-1 §4: e_per = G/ω; U_per = e_per·m_rotor.
        # G6.3, ω=314.16 rad/s, m=10 kg → e_per = 6.3/314.16 mm.
        r = _ref_iso1940(50.0, 10.0, 314.159265, grade="G6.3")
        assert r["eper_permissible_mm"] == pytest.approx(6.3 / 314.159265, rel=1e-9)
        assert r["U_permissible_g_mm"] == pytest.approx((6.3 / 314.159265) * 10000.0, rel=1e-9)

    def test_primary_shaking_force(self):
        # Norton §13.6: F_p = mₑ·r·ω²·cos θ. At θ=0 → max = mₑrω².
        r = _ref_shake1(1.0, 0.05, 100.0, 0.0)
        assert r["F_primary"] == pytest.approx(1.0 * 0.05 * 100.0 ** 2, rel=1e-12)

    def test_gyroscopic_moment_hibbeler_21_5(self):
        # Hibbeler §21-5: M = I·ωs·ωp (perpendicular axes).
        r = _ref_gyro(0.5, 200.0, 2.0)
        assert r["M_gyro"] == pytest.approx(0.5 * 200.0 * 2.0, rel=1e-12)
