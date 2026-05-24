"""
kerf_cad_core.wormbevel.design — pure-Python worm-gear and bevel-gear design.

Public API
----------

WORM GEAR
  worm_geometry(m_n, N_w, N_g, *, C, phi_n_deg)
      Worm and worm-gear geometry: lead, lead angle, pitch diameters, center
      distance, gear ratio, etc.

  worm_efficiency(lambda_deg, phi_n_deg, mu)
      Efficiency and reverse-drive capability of a worm pair.  Self-locking
      criterion checked and reported in warnings.

  worm_forces(T_w, d_w, lambda_deg, phi_n_deg, mu)
      Force analysis: tangential / axial / radial / separating on worm and gear.

  worm_agma_rating(C_s, C_m, C_v, d_g, b, d_w, n_w, material_pair)
      AGMA tangential load rating and thermal-power limit for a worm-gear set.

BEVEL GEAR
  bevel_geometry(N_p, N_g, m, b_fraction)
      Straight-bevel geometry: pitch angles, cone distance, mean module, face
      width, back-cone radii, equivalent (virtual) spur-gear tooth counts.

  bevel_forces(T_p, d_m_p, Gamma_p_deg)
      Force analysis on a straight-bevel pinion: tangential, radial (= axial on
      gear), axial (= radial on gear) components.

  bevel_agma_stress(Wt, Ko, Kv, Ks, Km, b, m_m, J, I, Cp, d_m_p, metric)
      AGMA bending stress (Lewis/AGMA) and contact stress for straight bevel
      gears, including bevel geometry factors.

All functions:
  - Return {"ok": True, ...} on success, {"ok": False, "reason": ...} on error.
  - Append human-readable warnings (list[str]) for flagged conditions.
  - NEVER raise.

Units (SI unless noted)
-----------------------
  lengths  — mm (gear geometry inputs/outputs)
  angles   — degrees (inputs), radians internally
  forces   — N
  torques  — N·mm
  stress   — MPa (metric), psi (English where noted)
  power    — kW (thermal rating)

References
----------
Shigley's Mechanical Engineering Design, 10th ed., §§ 13-7 to 13-10, 13-17
AGMA 6022-C93 — Coarse-Pitch Worm Gearing
AGMA 2003-B97 — Straight Bevel, Zerol Bevel, and Spiral Bevel Gear Teeth
Norton, R.L. "Machine Design", 5th ed., Ch. 11

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive

from kerf_cad_core.gearstrength.rating import (
    agma_bending_stress as _gs_bending_stress,
    agma_contact_stress as _gs_contact_stress,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _deg2rad(deg: float) -> float:
    return deg * math.pi / 180.0


def _rad2deg(rad: float) -> float:
    return rad * 180.0 / math.pi


# ---------------------------------------------------------------------------
# WORM GEAR DESIGN
# ---------------------------------------------------------------------------

# AGMA worm material pair constants: (C_s_base, C_m_base)
# Keys: "sand_cast_bronze_cast_iron", "centrifugal_cast_bronze_steel",
#       "chilled_cast_bronze_steel"
_WORM_MATERIAL: dict[str, dict] = {
    "sand_cast_bronze_cast_iron": {
        "C_s": 1000.0,   # surface durability constant (AGMA 6022)
        "C_s_limit": "low",
        "label": "sand-cast bronze / cast-iron worm",
    },
    "centrifugal_cast_bronze_steel": {
        "C_s": 1000.0,
        "C_s_limit": "medium",
        "label": "centrifugal-cast bronze / hardened-steel worm",
    },
    "chilled_cast_bronze_steel": {
        "C_s": 1000.0,
        "C_s_limit": "high",
        "label": "chilled (die-cast) bronze / hardened-steel worm",
    },
}

# AGMA worm velocity factor table bounds  (m/s pitch-line velocity)
_VS_MAX = 30.0  # m/s — above this AGMA C_v warning issued


def worm_geometry(
    m_n: float,
    N_w: int,
    N_g: int,
    *,
    C: float | None = None,
    phi_n_deg: float = 20.0,
) -> dict:
    """
    Worm-gear pair geometry.

    Parameters
    ----------
    m_n : float
        Normal module (mm).  Must be > 0.
    N_w : int
        Number of worm starts (threads).  Typically 1–6.  Must be >= 1.
    N_g : int
        Number of worm-gear teeth.  Must be > N_w.
    C : float | None
        Centre distance (mm).  If provided, the pitch diameters are computed
        from C (AGMA practice); otherwise they are derived from the module.
    phi_n_deg : float
        Normal pressure angle (°).  Default 20°.

    Returns
    -------
    dict
        ok           : True
        m_n_mm       : normal module (mm)
        N_w          : worm starts
        N_g          : worm-gear teeth
        m_G          : gear ratio N_g / N_w
        phi_n_deg    : normal pressure angle (°)
        lead_mm      : lead = N_w × π × m_n  (mm)
        lead_angle_deg: worm lead angle λ (°)
        d_w_mm       : worm pitch diameter (mm)
        d_g_mm       : worm-gear pitch diameter (mm)
        C_mm         : centre distance (mm)
        face_width_max_mm: recommended max face width (mm)
        axial_pitch_mm: axial pitch p_x (mm)
        warnings     : list of diagnostic strings (empty on clean design)

    Notes
    -----
    Lead angle λ is computed from:
        tan λ = lead / (π × d_w)
    When C is given the AGMA preferred diameter formula is used:
        d_w = C^0.875 / 2.2   (AGMA 6022, inch-based — converted internally)
    """
    err = _guard_positive("m_n", m_n)
    if err:
        return _err(err)

    try:
        N_w_i = int(N_w)
        N_g_i = int(N_g)
    except (TypeError, ValueError):
        return _err("N_w and N_g must be integers")

    if N_w_i < 1:
        return _err(f"N_w must be >= 1, got {N_w_i}")
    if N_g_i <= N_w_i:
        return _err(f"N_g must be > N_w; got N_g={N_g_i}, N_w={N_w_i}")

    phi_n = float(phi_n_deg)
    if phi_n <= 0 or phi_n >= 90:
        return _err(f"phi_n_deg must be in (0, 90), got {phi_n}")

    warnings: list[str] = []
    m = float(m_n)

    # Axial pitch = π × m_n
    p_x = math.pi * m  # mm

    # Lead = N_w × p_x
    lead = N_w_i * p_x  # mm

    # Gear ratio
    m_G = N_g_i / N_w_i

    # Pitch diameters
    if C is not None:
        err_c = _guard_positive("C", C)
        if err_c:
            return _err(err_c)
        C_val = float(C)
        # AGMA 6022 preferred worm diameter (C in mm → convert to inches internally)
        C_in = C_val / 25.4
        d_w_in = C_in ** 0.875 / 2.2  # AGMA empirical formula
        d_w = d_w_in * 25.4  # back to mm
        d_g = 2.0 * C_val - d_w
    else:
        # Use standard module relationship: d_w chosen so that a "standard" worm
        # has a reasonable lead angle (AGMA suggests d_w ~ m_n × q where q ≈ 10)
        q = 10.0  # standard worm pitch-diameter quotient
        d_w = m * q  # mm
        d_g = m * N_g_i  # mm
        C_val = (d_w + d_g) / 2.0

    # Lead angle
    lambda_rad = math.atan(lead / (math.pi * d_w))
    lambda_deg = _rad2deg(lambda_rad)

    # Recommended max face width (Shigley §13-9): b ≤ 0.73 × d_w
    b_max = 0.73 * d_w

    # Diagnostic warnings
    if lambda_deg < 1.0:
        warnings.append(
            f"WARNING: lead angle λ={lambda_deg:.2f}° is extremely shallow — "
            "high friction losses expected."
        )
    if N_w_i == 1:
        warnings.append(
            "INFO: single-start worm provides high ratio but low efficiency — "
            "verify thermal rating."
        )
    if m_G > 100:
        warnings.append(
            f"WARNING: gear ratio {m_G:.1f} is unusually high for a single worm "
            "stage — consider compound arrangement."
        )

    return {
        "ok": True,
        "m_n_mm": m,
        "N_w": N_w_i,
        "N_g": N_g_i,
        "m_G": m_G,
        "phi_n_deg": phi_n,
        "lead_mm": lead,
        "lead_angle_deg": lambda_deg,
        "d_w_mm": d_w,
        "d_g_mm": d_g,
        "C_mm": C_val,
        "face_width_max_mm": b_max,
        "axial_pitch_mm": p_x,
        "warnings": warnings,
    }


def worm_efficiency(
    lambda_deg: float,
    phi_n_deg: float = 20.0,
    mu: float = 0.05,
) -> dict:
    """
    Worm-gear pair efficiency and self-locking analysis.

    Uses the classic kinematic efficiency formula (Shigley §13-9):

        η_forward = cos(φ_n) − μ·tan(λ)   /   cos(φ_n)·tan(λ) + μ
                  =  (cos φ_n − μ·tan λ) / (cos φ_n + μ/tan λ)

    Or equivalently:
        η_forward = tan(λ) × (cos φ_n − μ·tan λ) / (cos φ_n·tan λ + μ)

    Self-locking condition: η_forward ≤ 0  (i.e., μ ≥ cos φ_n · tan λ)

    Parameters
    ----------
    lambda_deg : float
        Lead angle (°).  Must be in (0, 90).
    phi_n_deg : float
        Normal pressure angle (°).  Default 20°.
    mu : float
        Coefficient of sliding friction.  Typical range 0.01–0.15.  Must be > 0.

    Returns
    -------
    dict
        ok                : True
        lambda_deg        : lead angle used (°)
        phi_n_deg         : normal pressure angle (°)
        mu                : friction coefficient
        eta_forward       : drive efficiency worm→gear (dimensionless, 0–1)
        eta_back          : back-drive efficiency gear→worm (dimensionless)
        self_locking      : True if gear cannot back-drive the worm
        warnings          : list of diagnostic strings
    """
    err = _guard_positive("lambda_deg", lambda_deg)
    if err:
        return _err(err)
    if lambda_deg >= 90.0:
        return _err(f"lambda_deg must be < 90, got {lambda_deg}")

    if phi_n_deg <= 0 or phi_n_deg >= 90:
        return _err(f"phi_n_deg must be in (0, 90), got {phi_n_deg}")

    err = _guard_positive("mu", mu)
    if err:
        return _err(err)

    warnings: list[str] = []

    lam = _deg2rad(float(lambda_deg))
    phi_n = _deg2rad(float(phi_n_deg))
    mu_f = float(mu)

    cos_phi = math.cos(phi_n)
    tan_lam = math.tan(lam)

    # Forward (worm drives gear) efficiency
    # η = tan(λ) × (cos φ_n − μ tan λ) / (cos φ_n tan λ + μ)
    numerator_f = cos_phi - mu_f * tan_lam
    denominator_f = cos_phi * tan_lam + mu_f
    # Avoid division by zero (degenerate geometry)
    if abs(denominator_f) < 1e-15:
        return _err("Degenerate geometry: denominator of efficiency formula is zero.")
    eta_forward = tan_lam * numerator_f / denominator_f

    # Back-drive efficiency  η_back = (cos φ_n tan λ − μ) / (cos φ_n + μ tan λ)
    numerator_b = cos_phi * tan_lam - mu_f
    denominator_b = cos_phi + mu_f * tan_lam
    eta_back = numerator_b / denominator_b if abs(denominator_b) > 1e-15 else 0.0

    # Self-locking: η_back ≤ 0  ↔  μ ≥ cos(φ_n)·tan(λ)
    self_locking = numerator_b <= 0.0

    # Clamp to physical range [0, 1]
    eta_forward_clamped = max(0.0, min(1.0, eta_forward))
    eta_back_clamped = max(0.0, min(1.0, eta_back))

    # Warnings
    if eta_forward_clamped < 0.5:
        warnings.append(
            f"WARNING: forward efficiency η={eta_forward_clamped:.3f} < 0.50 — "
            "significant thermal losses; check heat dissipation rating."
        )
    if self_locking:
        warnings.append(
            f"INFO: self-locking condition met (μ={mu_f:.4f} ≥ cos φ_n · tan λ = "
            f"{cos_phi * tan_lam:.4f}) — worm set cannot be back-driven. "
            "Useful for holding loads; verify brake function in safety-critical apps."
        )
    if mu_f > 0.12:
        warnings.append(
            f"WARNING: friction coefficient μ={mu_f:.4f} is high — ensure adequate "
            "lubrication and compatible material pairing."
        )

    return {
        "ok": True,
        "lambda_deg": float(lambda_deg),
        "phi_n_deg": float(phi_n_deg),
        "mu": mu_f,
        "eta_forward": eta_forward_clamped,
        "eta_back": eta_back_clamped,
        "self_locking": self_locking,
        "warnings": warnings,
    }


def worm_forces(
    T_w: float,
    d_w: float,
    lambda_deg: float,
    phi_n_deg: float = 20.0,
    mu: float = 0.05,
) -> dict:
    """
    Force analysis on a worm-gear pair (worm drives gear).

    The worm tangential force (= worm-gear axial force) is:
        W_t_w = 2 T_w / d_w

    Normal load in the plane of worm tooth:
        W_n = W_t_w / (cos φ_n · sin λ + μ · cos λ)

    Forces on worm (subscript w) and gear (subscript g) are related by
    action/reaction; full 3D decomposition per Shigley §13-10:

        W_t_w (worm tangential = gear axial)    = W_n · (cos φ_n · sin λ + μ cos λ)
        W_a_w (worm axial = gear tangential)     = W_n · (cos φ_n · cos λ − μ sin λ)
        W_r   (separating / radial, same on both) = W_n · sin φ_n

    Parameters
    ----------
    T_w : float
        Input torque on worm (N·mm).  Must be > 0.
    d_w : float
        Worm pitch diameter (mm).  Must be > 0.
    lambda_deg : float
        Lead angle (°).  Must be in (0, 90).
    phi_n_deg : float
        Normal pressure angle (°).  Default 20°.
    mu : float
        Coefficient of sliding friction.  Must be > 0.

    Returns
    -------
    dict
        ok            : True
        W_t_w_N       : worm tangential force (N)  [= gear axial]
        W_a_w_N       : worm axial force (N)        [= gear tangential]
        W_r_N         : separating / radial force (N) [same magnitude both members]
        W_n_N         : normal force at tooth contact (N)
        T_g_Nmm       : output torque on gear (N·mm) = W_a_w × d_g / 2  (needs d_g)
        warnings      : list of diagnostic strings

    Notes
    -----
    d_g is NOT needed as an input — W_a_w is the tangential load ON the gear,
    from which output torque can be derived externally using d_g.
    """
    err = _guard_positive("T_w", T_w)
    if err:
        return _err(err)
    err = _guard_positive("d_w", d_w)
    if err:
        return _err(err)
    err = _guard_positive("lambda_deg", lambda_deg)
    if err:
        return _err(err)
    if lambda_deg >= 90.0:
        return _err(f"lambda_deg must be < 90, got {lambda_deg}")
    if phi_n_deg <= 0 or phi_n_deg >= 90:
        return _err(f"phi_n_deg must be in (0, 90), got {phi_n_deg}")
    err = _guard_positive("mu", mu)
    if err:
        return _err(err)

    warnings: list[str] = []

    lam = _deg2rad(float(lambda_deg))
    phi_n = _deg2rad(float(phi_n_deg))
    mu_f = float(mu)
    T = float(T_w)
    dw = float(d_w)

    # Worm tangential force
    W_t_w = 2.0 * T / dw  # N (T in N·mm, d in mm → N)

    cos_phi = math.cos(phi_n)
    sin_phi = math.sin(phi_n)
    cos_lam = math.cos(lam)
    sin_lam = math.sin(lam)

    # Denominator for normal force (from W_t_w definition)
    denom = cos_phi * sin_lam + mu_f * cos_lam
    if abs(denom) < 1e-15:
        return _err("Degenerate geometry: cannot compute normal force (denominator zero).")

    W_n = W_t_w / denom

    # Worm axial force (= gear tangential)
    W_a_w = W_n * (cos_phi * cos_lam - mu_f * sin_lam)

    # Separating / radial force (same both sides)
    W_r = W_n * sin_phi

    if W_a_w < 0:
        warnings.append(
            "WARNING: W_a_w < 0 — friction dominates; worm may be self-locking in "
            "this direction or geometry is degenerate."
        )
        W_a_w = max(0.0, W_a_w)

    return {
        "ok": True,
        "W_t_w_N": W_t_w,
        "W_a_w_N": W_a_w,
        "W_r_N": W_r,
        "W_n_N": W_n,
        "warnings": warnings,
    }


def worm_agma_rating(
    C_s: float,
    C_m: float,
    C_v: float,
    d_g: float,
    b: float,
    d_w: float,
    n_w: float,
    material_pair: str = "centrifugal_cast_bronze_steel",
) -> dict:
    """
    AGMA 6022 rated tangential load and thermal power for a worm-gear set.

    AGMA tangential load rating (Shigley §13-9 / AGMA 6022):
        W_t_rated = C_s × d_g^0.8 × b × C_m × C_v

    Thermal power rating (AGMA 6022):
        H_t = 9540 × (1 − η) × W_t_rated × V_s / (1000 × C_f)
    where V_s is the sliding speed and C_f a thermal correction factor.
    A simplified form is used here:
        P_thermal_kW = C_t × A_t × (T_sump − T_amb)
    For catalogue use, the simplified form is:
        P_thermal_kW ≈ 0.1 × (d_g / 25.4)^0.8 × n_w^0.5

    Parameters
    ----------
    C_s : float
        Materials constant from AGMA 6022 (psi-based; typical range 600–1000).
    C_m : float
        Ratio correction factor.  Typical values 0.7–1.0.
    C_v : float
        Velocity factor.  Typical values 0.4–1.0 depending on sliding speed.
    d_g : float
        Worm-gear pitch diameter (mm).  Must be > 0.
    b : float
        Worm-gear face width (mm).  Must be > 0.
    d_w : float
        Worm pitch diameter (mm).  Must be > 0.
    n_w : float
        Worm rotational speed (rpm).  Must be > 0.
    material_pair : str
        One of: 'sand_cast_bronze_cast_iron', 'centrifugal_cast_bronze_steel',
        'chilled_cast_bronze_steel'.

    Returns
    -------
    dict
        ok                   : True
        W_t_rated_N          : AGMA rated tangential load on gear (N)
        P_rated_kW           : rated transmitted power (kW)
        P_thermal_kW         : approximate thermal limit (kW)
        thermal_ok           : True if P_rated_kW <= P_thermal_kW
        material_pair        : material combination used
        warnings             : list of diagnostic strings
    """
    err = _guard_positive("C_s", C_s)
    if err:
        return _err(err)
    err = _guard_positive("C_m", C_m)
    if err:
        return _err(err)
    err = _guard_positive("C_v", C_v)
    if err:
        return _err(err)
    err = _guard_positive("d_g", d_g)
    if err:
        return _err(err)
    err = _guard_positive("b", b)
    if err:
        return _err(err)
    err = _guard_positive("d_w", d_w)
    if err:
        return _err(err)
    err = _guard_positive("n_w", n_w)
    if err:
        return _err(err)

    mat = str(material_pair).strip().lower()
    if mat not in _WORM_MATERIAL:
        valid = list(_WORM_MATERIAL.keys())
        return _err(f"Unknown material_pair {material_pair!r}. Supported: {valid}.")

    warnings: list[str] = []

    # AGMA formula: W_t = C_s × d_g^0.8 × b × C_m × C_v
    # Note: AGMA 6022 uses inch units; convert mm → inches, then back to N
    d_g_in = float(d_g) / 25.4
    b_in = float(b) / 25.4
    d_w_in = float(d_w) / 25.4

    W_t_lbf = float(C_s) * (d_g_in ** 0.8) * b_in * float(C_m) * float(C_v)
    W_t_N = W_t_lbf * 4.44822  # lbf → N

    # Pitch-line velocity of gear (ft/min)
    V_g_fpm = math.pi * d_g_in * float(n_w) / (float(d_g) / float(d_w))  # approximate
    # Sliding velocity (ft/min) — approximate for worm: V_s ≈ V_g / cos(λ)
    # Use gear pitch-line velocity / gear ratio as approximation
    V_s_fpm = V_g_fpm  # simplified

    # Rated power (hp): H = W_t × V / 33000  (V in ft/min)
    V_g_fpm_actual = math.pi * d_g_in * float(n_w) * float(d_w) / float(d_g)
    H_rated_hp = W_t_lbf * max(V_g_fpm_actual, 1.0) / 33000.0
    P_rated_kW = H_rated_hp * 0.7457  # hp → kW

    # Thermal rating (simplified AGMA 6022 §5.5):
    # P_thermal ≈ 0.1 × (d_g_in)^0.8 × n_w^0.5  [kW] — rough approximation
    P_thermal_kW = 0.1 * (d_g_in ** 0.8) * (float(n_w) ** 0.5)

    thermal_ok = P_rated_kW <= P_thermal_kW

    if not thermal_ok:
        warnings.append(
            f"WARNING: OVER-TEMPERATURE — rated power {P_rated_kW:.2f} kW exceeds "
            f"estimated thermal limit {P_thermal_kW:.2f} kW. "
            "Provide forced cooling or reduce load/speed."
        )
    if C_v < 0.5:
        warnings.append(
            f"WARNING: velocity factor C_v={C_v:.3f} is low — sliding speed may be "
            "excessive for this material pair."
        )
    if float(b) > 0.73 * float(d_w):
        warnings.append(
            f"WARNING: face width b={b:.1f} mm > 0.73 × d_w = "
            f"{0.73 * float(d_w):.1f} mm (AGMA recommended limit)."
        )

    return {
        "ok": True,
        "W_t_rated_N": W_t_N,
        "P_rated_kW": P_rated_kW,
        "P_thermal_kW": P_thermal_kW,
        "thermal_ok": thermal_ok,
        "material_pair": mat,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# BEVEL GEAR DESIGN
# ---------------------------------------------------------------------------

def bevel_geometry(
    N_p: int,
    N_g: int,
    m: float,
    b_fraction: float = 0.3,
) -> dict:
    """
    Straight-bevel gear geometry.

    Parameters
    ----------
    N_p : int
        Number of pinion teeth.  Must be >= 12.
    N_g : int
        Number of gear teeth.  Must be > N_p.
    m : float
        Back-cone (outer) module (mm).  Must be > 0.
    b_fraction : float
        Face width as a fraction of cone distance A_0.  AGMA limits: 0.2–0.333.
        Default 0.3.

    Returns
    -------
    dict
        ok               : True
        N_p, N_g         : tooth counts
        m_mm             : back-cone module (mm)
        m_G              : gear ratio N_g / N_p
        Gamma_p_deg      : pinion pitch angle (°)
        Gamma_g_deg      : gear pitch angle (°)
        A_0_mm           : back-cone (outer) distance / slant height (mm)
        b_mm             : face width (mm)
        m_m_mm           : mean module (mm)
        A_m_mm           : mean cone distance (mm)
        d_p_mm           : pinion back-cone pitch diameter (mm)
        d_g_mm           : gear back-cone pitch diameter (mm)
        d_m_p_mm         : pinion mean pitch diameter (mm)
        N_e_p            : equivalent (virtual) spur-gear teeth — pinion
        N_e_g            : equivalent (virtual) spur-gear teeth — gear
        warnings         : list of diagnostic strings

    Formulas (Shigley §13-17)
    -------------------------
    Pitch angle (pinion):  tan Γ_p = N_p / N_g
    Pitch angle (gear):    Γ_g = 90° − Γ_p   (for 90° shaft angle)
    Back-cone distance:    A_0 = d_p / (2 sin Γ_p) = m × N_p / (2 sin Γ_p)
    Face width:            b = b_fraction × A_0
    Mean cone distance:    A_m = A_0 − b/2
    Mean module:           m_m = m × (A_m / A_0)
    Mean diameter (pinion): d_m_p = m_m × N_p
    Virtual spur teeth:    N_e = N / cos(Γ)
    """
    try:
        N_p_i = int(N_p)
        N_g_i = int(N_g)
    except (TypeError, ValueError):
        return _err("N_p and N_g must be integers")

    if N_p_i < 12:
        return _err(f"N_p must be >= 12 for straight bevel gears; got {N_p_i}")
    if N_g_i <= N_p_i:
        return _err(f"N_g must be > N_p; got N_g={N_g_i}, N_p={N_p_i}")

    err = _guard_positive("m", m)
    if err:
        return _err(err)

    if b_fraction <= 0 or b_fraction > 0.5:
        return _err(f"b_fraction must be in (0, 0.5], got {b_fraction}")

    warnings: list[str] = []
    m_val = float(m)

    # Gear ratio
    m_G = N_g_i / N_p_i

    # Pitch angles (90° shaft angle)
    Gamma_p_rad = math.atan(N_p_i / N_g_i)
    Gamma_g_rad = math.pi / 2.0 - Gamma_p_rad  # = atan(N_g / N_p)

    Gamma_p_deg = _rad2deg(Gamma_p_rad)
    Gamma_g_deg = _rad2deg(Gamma_g_rad)

    # Back-cone pitch diameters
    d_p = m_val * N_p_i  # mm
    d_g = m_val * N_g_i  # mm

    # Outer cone distance (slant height of pitch cone)
    A_0 = d_p / (2.0 * math.sin(Gamma_p_rad))

    # Face width
    b_val = b_fraction * A_0

    # Mean cone distance
    A_m = A_0 - b_val / 2.0

    # Mean module
    m_m = m_val * (A_m / A_0)

    # Mean pitch diameters
    d_m_p = m_m * N_p_i
    d_m_g = m_m * N_g_i

    # Equivalent (virtual) spur-gear teeth  N_e = N / cos(Γ)
    N_e_p = N_p_i / math.cos(Gamma_p_rad)
    N_e_g = N_g_i / math.cos(Gamma_g_rad)

    # AGMA face-width limits
    if b_fraction > 1.0 / 3.0:
        warnings.append(
            f"WARNING: face width b={b_val:.2f} mm ({b_fraction:.2%} of A_0) exceeds "
            "AGMA recommended maximum of A_0/3 — risk of uneven load distribution."
        )
    if b_val > 10.0 * m_val:
        warnings.append(
            f"WARNING: face width b={b_val:.2f} mm > 10m = {10 * m_val:.2f} mm "
            "(Shigley empirical upper limit)."
        )

    return {
        "ok": True,
        "N_p": N_p_i,
        "N_g": N_g_i,
        "m_mm": m_val,
        "m_G": m_G,
        "Gamma_p_deg": Gamma_p_deg,
        "Gamma_g_deg": Gamma_g_deg,
        "A_0_mm": A_0,
        "b_mm": b_val,
        "m_m_mm": m_m,
        "A_m_mm": A_m,
        "d_p_mm": d_p,
        "d_g_mm": d_g,
        "d_m_p_mm": d_m_p,
        "d_m_g_mm": d_m_g,
        "N_e_p": N_e_p,
        "N_e_g": N_e_g,
        "warnings": warnings,
    }


def bevel_forces(
    T_p: float,
    d_m_p: float,
    Gamma_p_deg: float,
    phi_n_deg: float = 20.0,
) -> dict:
    """
    Force analysis on a straight-bevel pinion.

    Using mean pitch-circle radius for force decomposition (Shigley §13-17):
        W_t = 2 T_p / d_m_p          (tangential force at mean pitch circle)
        W_r = W_t × tan(φ_n) × cos(Γ_p)  (radial on pinion = axial on gear)
        W_a = W_t × tan(φ_n) × sin(Γ_p)  (axial on pinion  = radial on gear)

    Parameters
    ----------
    T_p : float
        Pinion input torque (N·mm).  Must be > 0.
    d_m_p : float
        Pinion mean pitch diameter (mm).  Must be > 0.
    Gamma_p_deg : float
        Pinion pitch angle (°).  Must be in (0, 90).
    phi_n_deg : float
        Normal pressure angle (°).  Default 20°.

    Returns
    -------
    dict
        ok        : True
        W_t_N     : tangential force at mean pitch circle (N)
        W_r_N     : radial force on pinion (= axial force on gear) (N)
        W_a_N     : axial force on pinion  (= radial force on gear) (N)
        W_total_N : resultant tooth force (N)
        warnings  : list of diagnostic strings
    """
    err = _guard_positive("T_p", T_p)
    if err:
        return _err(err)
    err = _guard_positive("d_m_p", d_m_p)
    if err:
        return _err(err)

    if Gamma_p_deg <= 0 or Gamma_p_deg >= 90:
        return _err(f"Gamma_p_deg must be in (0, 90), got {Gamma_p_deg}")
    if phi_n_deg <= 0 or phi_n_deg >= 90:
        return _err(f"phi_n_deg must be in (0, 90), got {phi_n_deg}")

    warnings: list[str] = []

    Gamma = _deg2rad(float(Gamma_p_deg))
    phi = _deg2rad(float(phi_n_deg))
    T = float(T_p)
    dm = float(d_m_p)

    # Tangential force
    W_t = 2.0 * T / dm

    # Radial and axial components
    tan_phi = math.tan(phi)
    W_r = W_t * tan_phi * math.cos(Gamma)  # radial on pinion
    W_a = W_t * tan_phi * math.sin(Gamma)  # axial on pinion

    W_total = math.sqrt(W_t**2 + W_r**2 + W_a**2)

    return {
        "ok": True,
        "W_t_N": W_t,
        "W_r_N": W_r,
        "W_a_N": W_a,
        "W_total_N": W_total,
        "warnings": warnings,
    }


def bevel_agma_stress(
    Wt: float,
    Ko: float,
    Kv: float,
    Ks: float,
    Km: float,
    b: float,
    m_m: float,
    J: float,
    I: float,
    Cp: float,
    d_m_p: float,
    metric: bool = True,
) -> dict:
    """
    AGMA bending and contact stress for straight-bevel gears.

    Bevel-gear bending stress (AGMA 2003, metric form):
        σ_t = Wt · Ko · Kv · Ks · Km / (b · m_m · J)   [MPa]

    Bevel-gear contact stress:
        σ_c = Cp · √(Wt · Ko · Kv · Ks · Km / (d_m_p · b · I))  [√MPa]

    These are the same AGMA forms as for cylindrical gears but applied at the
    mean pitch circle with mean module and bevel geometry factors J and I.

    Parameters
    ----------
    Wt : float
        Tangential load at mean pitch circle.
        Metric: N.  English: lbf.  Must be > 0.
    Ko : float
        Overload factor (>= 1).
    Kv : float
        Dynamic factor (>= 1).
    Ks : float
        Size factor (>= 1).
    Km : float
        Load-distribution factor (>= 1).
    b : float
        Face width.  Metric: mm.  English: inches.  Must be > 0.
    m_m : float
        Mean module (metric, mm) or mean diametral pitch 1/m_m (English, teeth/in).
    J : float
        Bending geometry factor.  Typical 0.20–0.35.  Must be > 0.
    I : float
        Contact (pitting) geometry factor.  Typical 0.05–0.20.  Must be > 0.
    Cp : float
        Elastic coefficient.  Steel/steel metric: 191 √MPa.  English: 2300 √psi.
    d_m_p : float
        Pinion mean pitch diameter.  Metric: mm.  English: inches.  Must be > 0.
    metric : bool
        True (default) → SI units.  False → English (psi).

    Returns
    -------
    dict
        ok        : True
        sigma_t   : bending stress (MPa or psi)
        sigma_c   : contact stress (MPa or psi)
        unit      : 'MPa' or 'psi'
        warnings  : list of diagnostic strings

    Notes
    -----
    Spiral-bevel gears use the same formula with modified geometry factors
    (J_s, I_s from AGMA 2003 spiral-bevel tables/figures); this function
    accepts any externally computed J and I and is therefore applicable to
    both straight and spiral bevel gears.
    """
    # Input validation — same guards as before; gearstrength functions also
    # validate but we want early bevel-specific error messages.
    for name, val in (
        ("Wt", Wt), ("Ko", Ko), ("Kv", Kv), ("Ks", Ks), ("Km", Km),
        ("b", b), ("m_m", m_m), ("J", J), ("I", I), ("Cp", Cp), ("d_m_p", d_m_p),
    ):
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    warnings: list[str] = []

    # Delegate bending stress to gearstrength.rating.agma_bending_stress.
    # Bevel gears use solid blanks → KB = 1.0.  Mean module m_m maps directly
    # to m_or_Pd; mean pitch diameter is handled externally (not needed here).
    bend_res = _gs_bending_stress(
        Wt, Ko, Kv, Ks, Km, KB=1.0,
        b=b, m_or_Pd=m_m, J=J,
        metric=metric,
    )
    if not bend_res["ok"]:
        return _err(bend_res["reason"])
    sigma_t = bend_res["sigma_t"]
    unit = bend_res["unit"]

    # Delegate contact stress to gearstrength.rating.agma_contact_stress.
    # d_m_p (mean pitch diameter) is the bevel equivalent of d_p in the formula.
    cont_res = _gs_contact_stress(
        Wt, Ko, Kv, Ks, Km, Cp,
        d_p=d_m_p, b=b, I=I,
        metric=metric,
    )
    if not cont_res["ok"]:
        return _err(cont_res["reason"])
    sigma_c = cont_res["sigma_c"]
    radicand = cont_res["radicand"]

    # Bevel-specific overstress thresholds (wider contact limit than spur/helical).
    bending_limit = 700.0 if metric else 100_000.0
    contact_limit = 2000.0 if metric else 300_000.0

    if sigma_t > bending_limit:
        warnings.append(
            f"WARNING: BENDING OVERSTRESS — σ_t={sigma_t:.1f} {unit} exceeds "
            f"reference limit {bending_limit:.0f} {unit}."
        )
    if sigma_c > contact_limit:
        warnings.append(
            f"WARNING: CONTACT OVERSTRESS — σ_c={sigma_c:.1f} {unit} exceeds "
            f"reference limit {contact_limit:.0f} {unit}."
        )

    return {
        "ok": True,
        "sigma_t": sigma_t,
        "sigma_c": sigma_c,
        "unit": unit,
        "radicand_contact": radicand,
        "warnings": warnings,
    }
