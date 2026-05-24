"""
kerf_cad_core.springs.design — pure-Python mechanical spring design formulas.

Implements four public functions:

  helical_compression(d, D, N, G, *, E, Sut, Se, Fa, Fm, end_type, set_removed)
      Helical compression spring design:
        - Spring rate:           k = G d^4 / (8 D^3 N)
        - Solid height:          Ls = N_total * d  (depends on end_type)
        - Slenderness / buckling: λ = L_free / D  (flag if > critical)
        - Wahl correction factor: Kw = (4C-1)/(4C-4) + 0.615/C
        - Shear stress:          τ = Kw * 8 F D / (π d^3)
        - Goodman fatigue check: σa/Se + σm/Sut <= 1

  helical_extension(d, D, N, G, *, E, Sut, Se, Fa, Fm, initial_tension_N)
      Helical extension spring:
        - Rate (same as compression): k = G d^4 / (8 D^3 N)
        - Initial tension            (required to open coils)
        - Hook bending stress at the hook (stress concentration KB)

  torsion_spring(d, D, N, E, *, torque_Nm, angular_deflection_deg)
      Helical torsion spring:
        - Angular rate:  k_theta = E d^4 / (64 D N)    [N·m/rev]
        - Angular rate:  k_rad   = E d^4 / (10.8 D N)  [N·m/rad]
        - Bending stress at coil body (Wahl curvature correction for bending)

  belleville_washer(De, Di, t, h0, E, nu, *, P_target)
      Belleville (disc) spring per Almen-László:
        - Load at target deflection
        - Deflection at target load
        - Stress at inner edge (largest stress)
        - Flat position load (deflection = h0)

All functions return plain dicts:
    success  → {"ok": True, ...computed fields..., "warnings": [...]}
    failure  → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

Units
-----
  lengths  — metres (m)
  forces   — Newtons (N)
  moments  — Newton-metres (N·m)
  stress   — Pascals (Pa)
  angles   — degrees (deg) or radians (rad) as noted
  moduli   — Pascals (Pa)

References
----------
Shigley's Mechanical Engineering Design, 10th ed., Ch. 10
Wahl, A.M. "Mechanical Springs", 2nd ed. (1963)
Almen, J.O. & László, A. Trans. ASME Vol. 58 (1936) p. 305-314
EN 16983:2017 (Disc springs)

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_END_TYPES = {
    "plain":               (0.0, "plain ends"),
    "plain_ground":        (1.0, "plain-ground ends"),
    "squared":             (2.0, "squared (closed) ends"),
    "squared_ground":      (2.0, "squared-and-ground ends (closed-ground)"),
}

# Buckling criterion: Shigley §10-5
# λ_cr ≈ 2.62 for fixed-free ends (one end fixed), 1.04 for both-ends-fixed
# Conservative: use λ = L_free / D >= 4.0 as a caution flag (Shigley p. 511)
_SLENDERNESS_WARN = 4.0   # flag if L_free / D exceeds this (unstable buckling risk)


def helical_compression(
    d: float,
    D: float,
    N: float,
    G: float,
    *,
    E: float = 0.0,
    Sut: float = 0.0,
    Se: float = 0.0,
    Fa: float = 0.0,
    Fm: float = 0.0,
    end_type: str = "squared_ground",
    set_removed: bool = False,
) -> dict:
    """
    Helical compression spring design.

    Parameters
    ----------
    d : float
        Wire diameter (m). Must be > 0.
    D : float
        Mean coil diameter (m). Must be > 0.
    N : float
        Number of active coils. Must be > 0.
    G : float
        Shear modulus (Pa). Must be > 0.
        Steel ≈ 79.3e9 Pa.
    E : float
        Young's modulus (Pa). Used only for Goodman fatigue if Sut is provided.
        Pass 0 to skip.  Steel ≈ 200e9 Pa.
    Sut : float
        Tensile strength (Pa). Required for Goodman fatigue check. Pass 0 to skip.
    Se : float
        Shear endurance limit of the wire (Pa). Used for Goodman. Pass 0 to skip.
    Fa : float
        Alternating force amplitude (N). Used for stress / Goodman. Pass 0 to skip.
    Fm : float
        Mean force (N). Used for stress / Goodman. Pass 0 to skip.
    end_type : str
        End condition for coil count / solid height:
          "plain"         — N_total = N,     Ls = N * d
          "plain_ground"  — N_total = N+1,   Ls = (N+1) * d
          "squared"       — N_total = N+2,   Ls = (N+2) * d
          "squared_ground"— N_total = N+2,   Ls = (N+2) * d  [default]
    set_removed : bool
        If True, the spring has been preset (set removed), increasing the
        yield strength effectively.  Currently noted as a flag in warnings.

    Returns
    -------
    dict
        ok                  : True
        rate_N_per_m        : spring rate k (N/m)
        C                   : spring index D/d
        Kw                  : Wahl correction factor
        solid_height_m      : solid height Ls (m)
        N_total             : total coils (active + inactive)
        slenderness         : L_free / D  (if free_length_m provided; else None)
        shear_stress_Pa     : peak shear stress τ (Pa) — only if Fa or Fm > 0
        goodman_ratio       : σa/Se + σm/Sut — only if fatigue inputs supplied
        goodman_ok          : True if goodman_ratio <= 1.0
        warnings            : list of warning strings
        end_type            : end type string used

    Notes
    -----
    Spring index C = D/d.  Wahl factor Kw = (4C-1)/(4C-4) + 0.615/C.
    Rate k = G d^4 / (8 D^3 N).
    Stress τ = Kw × 8 F D / (π d³).
    Goodman: τa/Sse + τm/Ssu ≤ 1,  where Sse ≈ Se, Ssu ≈ 0.67 Sut.

    References
    ----------
    Shigley 10th ed., §§ 10-4, 10-5, 10-6
    """
    err = _guard_positive("d", d)
    if err:
        return _err(err)
    err = _guard_positive("D", D)
    if err:
        return _err(err)
    err = _guard_positive("N", N)
    if err:
        return _err(err)
    err = _guard_positive("G", G)
    if err:
        return _err(err)
    err = _guard_nonneg("Fa", Fa)
    if err:
        return _err(err)
    err = _guard_nonneg("Fm", Fm)
    if err:
        return _err(err)

    d = float(d)
    D = float(D)
    N = float(N)
    G = float(G)
    Fa = float(Fa)
    Fm = float(Fm)
    Sut = float(Sut)
    Se = float(Se)
    E = float(E)

    et = str(end_type).strip().lower().replace("-", "_").replace(" ", "_")
    if et not in _END_TYPES:
        valid = list(_END_TYPES.keys())
        return _err(f"Unknown end_type {end_type!r}. Supported: {valid}.")

    inactive_coils, _end_label = _END_TYPES[et]
    N_total = N + inactive_coils

    warnings: list[str] = []

    # Spring index
    C = D / d
    if C < 3.0:
        warnings.append(f"Spring index C={C:.2f} < 3; difficult to manufacture.")
    if C > 12.0:
        warnings.append(f"Spring index C={C:.2f} > 12; prone to buckling and tangling.")

    # Wahl correction factor (shear stress curvature + direct shear)
    # Kw = (4C-1)/(4C-4) + 0.615/C   [Shigley eq. 10-7]
    Kw = (4.0 * C - 1.0) / (4.0 * C - 4.0) + 0.615 / C

    # Spring rate  k = G d^4 / (8 D^3 N)
    k = G * d**4 / (8.0 * D**3 * N)

    # Solid height  Ls = N_total * d
    Ls = N_total * d

    # Shear stress at peak force = Fa + Fm  (max force)
    F_max = Fa + Fm
    tau_max = None
    tau_a = None
    tau_m = None
    if F_max > 0:
        tau_max = Kw * 8.0 * F_max * D / (math.pi * d**3)

    if Fa > 0 or Fm > 0:
        tau_a = Kw * 8.0 * Fa * D / (math.pi * d**3)
        tau_m = Kw * 8.0 * Fm * D / (math.pi * d**3)

    # Goodman fatigue check  τa/Sse + τm/Ssu ≤ 1
    # Ssu ≈ 0.67 Sut  (Shigley eq. 10-30)
    goodman_ratio = None
    goodman_ok = None
    if Se > 0 and Sut > 0 and tau_a is not None and tau_m is not None:
        Sse = Se          # shear endurance limit (already shear if user supplies Se_shear)
        Ssu = 0.67 * Sut  # approximate ultimate shear strength
        goodman_ratio = tau_a / Sse + tau_m / Ssu
        goodman_ok = goodman_ratio <= 1.0
        if not goodman_ok:
            warnings.append(
                f"Goodman fatigue check FAILED: τa/Sse + τm/Ssu = {goodman_ratio:.4f} > 1.0"
            )

    # Slenderness — cannot compute without free length; return None
    # Callers who know the free length can check: slenderness = L_free / D
    slenderness = None

    if set_removed:
        warnings.append(
            "set_removed=True: preset increases usable stress range; "
            "verify Ls against operating length."
        )

    result: dict = {
        "ok": True,
        "rate_N_per_m": k,
        "C": C,
        "Kw": Kw,
        "solid_height_m": Ls,
        "N_total": N_total,
        "slenderness": slenderness,
        "end_type": et,
        "warnings": warnings,
    }
    if tau_max is not None:
        result["shear_stress_max_Pa"] = tau_max
    if tau_a is not None:
        result["shear_stress_alt_Pa"] = tau_a
        result["shear_stress_mean_Pa"] = tau_m
    if goodman_ratio is not None:
        result["goodman_ratio"] = goodman_ratio
        result["goodman_ok"] = goodman_ok

    return result


def helical_compression_with_free_length(
    d: float,
    D: float,
    N: float,
    G: float,
    free_length_m: float,
    *,
    end_type: str = "squared_ground",
    **kwargs,
) -> dict:
    """
    Wrapper around helical_compression that also computes slenderness and
    buckling risk from a known free length.

    Slenderness λ = L_free / D.
    Buckling risk is flagged when λ > 4.0 (conservative; Shigley §10-5).
    """
    err = _guard_positive("free_length_m", free_length_m)
    if err:
        return _err(err)

    res = helical_compression(d, D, N, G, end_type=end_type, **kwargs)
    if not res.get("ok"):
        return res

    D = float(D)
    lam = float(free_length_m) / D
    res["slenderness"] = lam
    res["free_length_m"] = float(free_length_m)
    if lam > _SLENDERNESS_WARN:
        res["warnings"].append(
            f"Buckling risk: slenderness L/D = {lam:.2f} > {_SLENDERNESS_WARN}. "
            "Consider guided spring or reduce free length."
        )
    return res


# ---------------------------------------------------------------------------
# 2. helical_extension
# ---------------------------------------------------------------------------

# Hook stress concentration factor KB (Wahl, eq. for round-hook):
# KB = (4C^2 - C - 1) / (4C(C-1))   [Shigley eq. 10-13]

def _hook_stress_factor(C: float) -> float:
    """Wahl hook bending stress concentration KB."""
    return (4.0 * C**2 - C - 1.0) / (4.0 * C * (C - 1.0))


def helical_extension(
    d: float,
    D: float,
    N: float,
    G: float,
    *,
    Sut: float = 0.0,
    Se: float = 0.0,
    Fa: float = 0.0,
    Fm: float = 0.0,
    initial_tension_N: float = 0.0,
) -> dict:
    """
    Helical extension spring design.

    The extension spring has an initial tension (pre-load) built in during
    coiling: the spring only begins to extend once the applied force exceeds
    this initial tension.

    Parameters
    ----------
    d : float
        Wire diameter (m). Must be > 0.
    D : float
        Mean coil diameter (m). Must be > 0.
    N : float
        Number of active coils. Must be > 0.
    G : float
        Shear modulus (Pa). Must be > 0.
    Sut : float
        Tensile strength (Pa). For Goodman check; 0 to skip.
    Se : float
        Shear endurance limit (Pa). For Goodman check; 0 to skip.
    Fa : float
        Alternating force amplitude (N). Must be >= 0.
    Fm : float
        Mean force (N). Must be >= 0.  Net force on coils = Fm + Fa - Fi.
    initial_tension_N : float
        Initial tension Fi (N) built into coils at manufacture. Must be >= 0.
        Typical range: τi = G/... see Shigley eq. 10-18.

    Returns
    -------
    dict
        ok                    : True
        rate_N_per_m          : spring rate k (N/m)
        C                     : spring index D/d
        Kw                    : Wahl shear stress correction
        KB                    : hook bending stress concentration factor
        hook_bending_stress_Pa: bending stress at hook (at F_max) (Pa) if forces supplied
        shear_stress_max_Pa   : shear stress in coil body at F_max (Pa) if forces supplied
        initial_tension_N     : initial tension Fi used (N)
        goodman_ratio         : τa/Sse + τm/Ssu if fatigue inputs supplied
        goodman_ok            : True if goodman_ratio <= 1.0
        warnings              : list of warning strings
    """
    err = _guard_positive("d", d)
    if err:
        return _err(err)
    err = _guard_positive("D", D)
    if err:
        return _err(err)
    err = _guard_positive("N", N)
    if err:
        return _err(err)
    err = _guard_positive("G", G)
    if err:
        return _err(err)
    err = _guard_nonneg("Fa", Fa)
    if err:
        return _err(err)
    err = _guard_nonneg("Fm", Fm)
    if err:
        return _err(err)
    err = _guard_nonneg("initial_tension_N", initial_tension_N)
    if err:
        return _err(err)

    d = float(d)
    D = float(D)
    N = float(N)
    G = float(G)
    Fa = float(Fa)
    Fm = float(Fm)
    Fi = float(initial_tension_N)
    Sut = float(Sut)
    Se = float(Se)

    warnings: list[str] = []

    C = D / d
    if C < 3.0:
        warnings.append(f"Spring index C={C:.2f} < 3; difficult to manufacture.")
    if C > 12.0:
        warnings.append(f"Spring index C={C:.2f} > 12; prone to tangling.")

    # Wahl shear stress factor (same as compression)
    Kw = (4.0 * C - 1.0) / (4.0 * C - 4.0) + 0.615 / C

    # Hook bending stress concentration KB
    KB = _hook_stress_factor(C)

    # Spring rate
    k = G * d**4 / (8.0 * D**3 * N)

    result: dict = {
        "ok": True,
        "rate_N_per_m": k,
        "C": C,
        "Kw": Kw,
        "KB": KB,
        "initial_tension_N": Fi,
        "warnings": warnings,
    }

    F_max = Fa + Fm
    if F_max > 0:
        # Shear stress in coil body
        tau_max = Kw * 8.0 * F_max * D / (math.pi * d**3)
        result["shear_stress_max_Pa"] = tau_max

        # Hook bending stress: σ_b = KB × 32 M / (π d³)
        # At the hook the bending moment M ≈ F × (D/2) for a round hook
        # Shigley eq. 10-13: σ = KB × 32 F D / (π d³) ... but factor is 16 for max:
        # More precisely: σ_b = 16 F D / (π d³) × KB   [bending at hook bend]
        # Shigley eq. 10-13 gives KB for the bending at inner fiber of the hook
        sigma_hook = KB * 16.0 * F_max * D / (math.pi * d**3)
        result["hook_bending_stress_Pa"] = sigma_hook

    if Fa > 0 or Fm > 0:
        tau_a = Kw * 8.0 * Fa * D / (math.pi * d**3)
        tau_m = Kw * 8.0 * Fm * D / (math.pi * d**3)
        result["shear_stress_alt_Pa"] = tau_a
        result["shear_stress_mean_Pa"] = tau_m

        if Se > 0 and Sut > 0:
            Sse = Se
            Ssu = 0.67 * Sut
            goodman_ratio = tau_a / Sse + tau_m / Ssu
            goodman_ok = goodman_ratio <= 1.0
            result["goodman_ratio"] = goodman_ratio
            result["goodman_ok"] = goodman_ok
            if not goodman_ok:
                warnings.append(
                    f"Goodman fatigue check FAILED: ratio={goodman_ratio:.4f} > 1.0"
                )

    if Fi > 0 and Fm > 0 and Fi > Fm:
        warnings.append(
            f"Initial tension Fi={Fi:.2f} N exceeds mean force Fm={Fm:.2f} N; "
            "spring may not open under operating load."
        )

    return result


# ---------------------------------------------------------------------------
# 3. torsion_spring
# ---------------------------------------------------------------------------

def torsion_spring(
    d: float,
    D: float,
    N: float,
    E: float,
    *,
    torque_Nm: float = 0.0,
    angular_deflection_deg: float = 0.0,
) -> dict:
    """
    Helical torsion spring design.

    A torsion spring resists *rotation*.  Its primary stress is **bending**,
    not torsion (unlike compression/extension springs).

    Parameters
    ----------
    d : float
        Wire diameter (m). Must be > 0.
    D : float
        Mean coil diameter (m). Must be > 0.
    N : float
        Number of active coils. Must be > 0.
    E : float
        Young's modulus (Pa). Steel ≈ 200e9 Pa. Must be > 0.
    torque_Nm : float
        Applied torque (N·m). Must be >= 0.
        Used to compute bending stress.
    angular_deflection_deg : float
        Angular deflection (degrees). Must be >= 0.
        Used to verify consistency with torque via angular rate.

    Returns
    -------
    dict
        ok                        : True
        rate_Nm_per_rev           : angular rate (N·m per revolution)
        rate_Nm_per_rad           : angular rate (N·m/rad)
        bending_stress_Pa         : bending stress at coil body (Pa) if torque supplied
        curvature_correction_Ki   : inner-fiber curvature correction Ki
        C                         : spring index D/d
        torque_from_deflection_Nm : torque computed from angular_deflection (N·m)
        warnings                  : list of warning strings

    Formulas
    --------
    Angular spring rate (Shigley eq. 10-43):

        k_theta = E d^4 / (64 D N)        [N·m / rev]
        k_rad   = E d^4 / (64 D N × 2π)  [N·m / rad]

    Alternatively:
        k_rad = E d^4 / (10.8 D N)   (Shigley 10th ed. eq. 10-44, slight rounding)
        Note: 64×2π = 402.1; books sometimes approximate as 10.8·D·N×32/d^4 → consistent.

    Bending stress with curvature correction (Shigley eq. 10-46):
        Ki = (4C^2 - C - 1) / (4C(C-1))   [inner-fiber correction]
        σ = Ki × 32 T / (π d^3)

    References
    ----------
    Shigley's Mechanical Engineering Design, 10th ed., §10-12
    """
    err = _guard_positive("d", d)
    if err:
        return _err(err)
    err = _guard_positive("D", D)
    if err:
        return _err(err)
    err = _guard_positive("N", N)
    if err:
        return _err(err)
    err = _guard_positive("E", E)
    if err:
        return _err(err)
    err = _guard_nonneg("torque_Nm", torque_Nm)
    if err:
        return _err(err)
    err = _guard_nonneg("angular_deflection_deg", angular_deflection_deg)
    if err:
        return _err(err)

    d = float(d)
    D = float(D)
    N = float(N)
    E = float(E)
    T = float(torque_Nm)
    theta_deg = float(angular_deflection_deg)

    warnings: list[str] = []

    C = D / d
    if C < 3.0:
        warnings.append(f"Spring index C={C:.2f} < 3; difficult to manufacture.")

    # Curvature correction for inner fiber (same form as KB for extension hook)
    Ki = (4.0 * C**2 - C - 1.0) / (4.0 * C * (C - 1.0))

    # Angular rate: k_theta = E d^4 / (64 D N)  [N·m / rev]
    rate_per_rev = E * d**4 / (64.0 * D * N)
    # [N·m / rad] = rate_per_rev / (2π)
    rate_per_rad = rate_per_rev / (2.0 * math.pi)

    result: dict = {
        "ok": True,
        "rate_Nm_per_rev": rate_per_rev,
        "rate_Nm_per_rad": rate_per_rad,
        "C": C,
        "curvature_correction_Ki": Ki,
        "warnings": warnings,
    }

    # Bending stress: σ = Ki × 32 T / (π d^3)
    if T > 0:
        sigma = Ki * 32.0 * T / (math.pi * d**3)
        result["bending_stress_Pa"] = sigma

    # Torque from angular deflection
    if theta_deg > 0:
        theta_rev = theta_deg / 360.0
        T_from_deflection = rate_per_rev * theta_rev
        result["torque_from_deflection_Nm"] = T_from_deflection

        # Cross-check consistency if both torque and deflection supplied
        if T > 0:
            rel_diff = abs(T - T_from_deflection) / max(T, T_from_deflection)
            if rel_diff > 0.05:
                warnings.append(
                    f"Supplied torque ({T:.4f} N·m) and torque from deflection "
                    f"({T_from_deflection:.4f} N·m) differ by {rel_diff*100:.1f}%."
                )

    return result


# ---------------------------------------------------------------------------
# 4. belleville_washer (disc spring)
# ---------------------------------------------------------------------------

def belleville_washer(
    De: float,
    Di: float,
    t: float,
    h0: float,
    E: float,
    nu: float,
    *,
    P_target: float = 0.0,
    delta_target: float = 0.0,
) -> dict:
    """
    Belleville (disc) spring load-deflection per Almen-László theory.

    The Almen-László closed-form is the standard for disc springs
    (referenced by EN 16983 and Shigley §10-14).

    Parameters
    ----------
    De : float
        Outer diameter (m). Must be > 0.
    Di : float
        Inner diameter (m). Must be > 0 and < De.
    t : float
        Disc thickness (m). Must be > 0.
    h0 : float
        Free cone height (m): the axial height before contact with the flat.
        Must be > 0.  Typically h0 ≈ 0.4 t to 0.75 t for optimal fatigue life.
    E : float
        Young's modulus (Pa). Must be > 0.  Steel ≈ 200e9 Pa.
    nu : float
        Poisson's ratio. Must be in (0, 0.5].  Steel ≈ 0.3.
    P_target : float
        Optional: compute deflection δ at this load (N). 0 to skip.
    delta_target : float
        Optional: compute load P at this deflection (m). 0 to skip.
        Must be in [0, h0] if provided.

    Returns
    -------
    dict
        ok                      : True
        P_flat_N                : load to flatten disc completely (δ = h0) (N)
        delta_max_stress_m      : deflection at maximum stress point (m)
        stress_inner_top_Pa     : compressive stress at inner edge upper face (Pa)
        alpha_factor            : geometric constant α (Almen-László)
        beta_factor             : geometric constant β (Almen-László)
        P_at_delta_target_N     : load at delta_target (N) — if delta_target supplied
        delta_at_P_target_m     : deflection at P_target (N) — if P_target supplied
        De_m                    : outer diameter used (m)
        Di_m                    : inner diameter used (m)
        t_m                     : thickness used (m)
        h0_m                    : free height used (m)
        warnings                : list of warning strings

    Formulas (Almen-László)
    -----------------------
    Let R = De/Di (diameter ratio).

    α = 6(R-1)² / (π ln R × R²)   — shape factor (note: some texts define slightly differently)

    Actually the standard Almen-László formulation uses:

        C1 = (6/π) × (ln R / (R-1)) × [(R/ln R) - 1]^(-1)  ... varies by reference

    We use the formulation from Shigley 10th ed. §10-14, Eq. (10-56) to (10-59):

    Let:
        R  = De / Di
        t  = disc thickness
        h0 = free cone height

    Almen-László constants (Shigley eq. 10-56):

        α = (6 (R-1)²) / (π ln R  R²)
        β = (6 (R-1))  / (π ln R  R²) × [R/ln R - 1/(R-1)]

    Load-deflection (Shigley eq. 10-57):

        P(δ) = (4 E t δ) / (α (1-ν²) De²) × [(h0 - δ/2)(h0 - δ) t² + t³]

    Simplified equivalent:

        P(δ) = C_coeff × [h0 δ - δ²/2) (h0 - δ) + t² δ]

    where C_coeff = 4 E / (α (1-ν²) De²)

    The standard formulation (EN 16983 §6.2) is:

        P = 4E t³ δ / ((1-ν²) De² C1) × [(h0/t)(1 - δ/(2h0)) + 1]
          × [(h0/t - δ/(2t)) + 1]

    We implement the widely cited Shigley form directly.

    Stress at inner edge (OM face, largest compressive stress):

        σ_I = -C_σ × 4E t δ / (α (1-ν²) De²)
              × [C2 h0 + C3 t]

    For practical use we compute σ at δ = h0/2 as representative operating point.

    References
    ----------
    Shigley's Mechanical Engineering Design, 10th ed., §10-14, eqs. 10-56 to 10-59
    Almen & László, Trans. ASME 58 (1936) p. 305
    EN 16983:2017, §6.2
    """
    err = _guard_positive("De", De)
    if err:
        return _err(err)
    err = _guard_positive("Di", Di)
    if err:
        return _err(err)
    err = _guard_positive("t", t)
    if err:
        return _err(err)
    err = _guard_positive("h0", h0)
    if err:
        return _err(err)
    err = _guard_positive("E", E)
    if err:
        return _err(err)

    try:
        nu_f = float(nu)
    except (TypeError, ValueError):
        return _err(f"nu must be a number, got {nu!r}")
    if not (0.0 < nu_f <= 0.5):
        return _err(f"nu must be in (0, 0.5], got {nu_f}")

    if float(Di) >= float(De):
        return _err(f"Di ({Di}) must be < De ({De}).")

    De = float(De)
    Di = float(Di)
    t = float(t)
    h0 = float(h0)
    E = float(E)

    warnings: list[str] = []

    # h0/t ratio — optimal fatigue life for 0.4 ≤ h0/t ≤ 0.75
    h0_t = h0 / t
    if h0_t > 1.5:
        warnings.append(
            f"h0/t = {h0_t:.2f} > 1.5: highly non-linear load-deflection; "
            "load may dip (snap-through) near flat position."
        )
    elif h0_t > 0.75:
        warnings.append(
            f"h0/t = {h0_t:.2f}: outside optimal fatigue range (0.4–0.75)."
        )

    R = De / Di
    lnR = math.log(R)

    # Almen-László constant α (Shigley eq. 10-56a):
    #   α = (6/π) × (R-1)² / (ln R × R²)
    # Note: some texts write α without the 6/π; we follow Shigley 10th ed.
    alpha = (6.0 / math.pi) * (R - 1.0)**2 / (lnR * R**2)

    # Constant β (Shigley eq. 10-56b):
    #   β = (6/π) × (R-1) / (ln R × R²) × [R/ln R - 1/(R-1)]
    # This corresponds to the stress coefficient for inner edge.
    beta_inner = (6.0 / math.pi) * (R - 1.0) / (lnR * R**2) * (R / lnR - 1.0 / (R - 1.0))

    # Common load coefficient:
    #   C_load = 4 E / (alpha (1-nu^2) De^2)
    C_load = 4.0 * E / (alpha * (1.0 - nu_f**2) * De**2)

    def _load_at_delta(delta: float) -> float:
        """Almen-László load at deflection delta (Shigley eq. 10-57)."""
        # P = C_load × t × delta × [(h0 - delta/2)(h0 - delta) + t^2]
        term1 = (h0 - delta / 2.0) * (h0 - delta)
        return C_load * t * delta * (term1 + t**2)

    def _stress_inner_at_delta(delta: float) -> float:
        """
        Compressive stress at inner edge, upper face (OM).
        Shigley eq. 10-59: σ_OM = -C_load × E t δ / (alpha(1-nu²) De²)
                                  × (C2 h0 - C3 t)
        where C2, C3 are functions of beta_inner and alpha.

        Simplified (Shigley 10th eq. 10-59):
            σ_I = -4E t δ / ((1-ν²) α De²) × [beta_inner (h0 - δ/2) + t]
        """
        if delta <= 0:
            return 0.0
        # Using C_load = 4E / (alpha(1-nu^2) De^2):
        # σ_I = -C_load × t × δ × [beta_inner (h0 - δ/2) + t]
        # The sign is compressive at inner edge; return magnitude
        sigma = C_load * t * delta * (beta_inner * (h0 - delta / 2.0) + t)
        return abs(sigma)

    # Load to flatten (δ = h0)
    P_flat = _load_at_delta(h0)

    # Deflection at maximum stress ≈ h0/2 (commonly cited; exact requires dσ/dδ=0)
    delta_max_stress = h0 / 2.0
    sigma_inner_op = _stress_inner_at_delta(delta_max_stress)

    if P_flat <= 0:
        warnings.append("Computed P_flat <= 0; check geometry.")

    result: dict = {
        "ok": True,
        "P_flat_N": P_flat,
        "delta_max_stress_m": delta_max_stress,
        "stress_inner_top_Pa": sigma_inner_op,
        "alpha_factor": alpha,
        "beta_factor": beta_inner,
        "De_m": De,
        "Di_m": Di,
        "t_m": t,
        "h0_m": h0,
        "warnings": warnings,
    }

    # Optional: load at specified deflection
    if delta_target > 0:
        err = _guard_positive("delta_target", delta_target)
        if err:
            return _err(err)
        delta_t = float(delta_target)
        if delta_t > h0:
            warnings.append(
                f"delta_target={delta_t:.6f} m > h0={h0:.6f} m; "
                "spring already past flat position."
            )
        result["P_at_delta_target_N"] = _load_at_delta(min(delta_t, h0))

    # Optional: deflection at specified load (binary search, monotonic P(δ) for h0/t <= 1)
    if P_target > 0:
        if P_target > P_flat * 1.1:
            warnings.append(
                f"P_target={P_target:.1f} N exceeds P_flat={P_flat:.1f} N; "
                "spring cannot reach this load."
            )
            result["delta_at_P_target_m"] = h0  # clamp at flat
        else:
            # Bisection on [0, h0]
            lo, hi = 0.0, h0
            for _ in range(60):
                mid = (lo + hi) / 2.0
                if _load_at_delta(mid) < P_target:
                    lo = mid
                else:
                    hi = mid
            result["delta_at_P_target_m"] = (lo + hi) / 2.0

    return result
