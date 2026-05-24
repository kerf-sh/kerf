"""
kerf_cad_core.struct.eurocode8 — Eurocode 8 (EN 1998-1) seismic design.

Pure-Python module; no OCC dependency.  Parallel to kerf_cad_core.seismic
(ASCE 7); this module covers the European standard.

Public functions
----------------
ec8_design_spectrum(T, ag, ground_type, spectrum_type, q, gamma_I)
    EC8 design response spectrum Sd(T) per EN 1998-1 §3.2.2.5
    Eq. (3.13)–(3.16) and Table 3.2/3.3.
    Returns Sd in m/s² and auxiliary spectral values.

ec8_lateral_force(ag, ground_type, H, m_stories, z_stories, *, ...)
    Lateral force method per EN 1998-1 §4.3.3.2.
    T1 = Ct·H^(3/4), Fb = Sd(T1)·m·λ, Fi distributed by zi·mi.

ec8_rsa(ag, ground_type, omega_n, phi_n, m_stories, *, ...)
    Modal response spectrum analysis per EN 1998-1 §4.3.3.3.
    Per-mode response from Sd(Tn); SRSS or CQC combination.
    Checks Σm_eff ≥ 0.9·M_total.

All functions return a plain dict:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

LLM tool wrappers: ec8_spectrum, ec8_lateral_force, ec8_rsa
(registered with the Kerf tool registry when imported).

Units
-----
  ag          — m/s²  (peak ground acceleration; e.g. 0.25g = 0.25 × 9.80665)
  Sd, Se      — m/s²
  T           — seconds
  H           — metres (building height)
  m, mi       — kg    (floor/storey mass)
  Fi, Fb      — N     (force)
  z, zi       — metres (height above base)
  omega_n     — rad/s (undamped natural circular frequency)
  phi_n       — list[list[float]] mode shapes (n_modes × n_dof)
  q           — dimensionless behaviour factor
  gamma_I     — dimensionless importance factor

Validation reference (EN 1998-1 Table 3.2, Type 1, ground type B)
------------------------------------------------------------------
  S=1.2, TB=0.15 s, TC=0.5 s, TD=2.0 s
  At T=0: Sd(0) = ag·gamma_I·S·(2/3 + 0/(TB)·(2.5/q - 2/3))
                = ag·gamma_I·S·(2/3) = 0.25·9.80665·1.2·(2/3) ≈ 1.961 m/s²
  At T→TB (plateau entry): Sd = ag·gamma_I·S·2.5/q
  At T=TC (end of plateau): Sd = ag·gamma_I·S·2.5/q
  At T=TD: Sd = ag·gamma_I·S·2.5/q·(TC/TD), lower bound 0.2·ag·gamma_I

References
----------
EN 1998-1:2004 "Design of structures for earthquake resistance —
Part 1: General rules, seismic actions and rules for buildings".

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any

__all__ = [
    "ec8_design_spectrum",
    "ec8_lateral_force",
    "ec8_rsa",
]

# ---------------------------------------------------------------------------
# Gravity constant
# ---------------------------------------------------------------------------
_G = 9.80665  # m/s²

# ---------------------------------------------------------------------------
# EC8 site class (ground type) parameters
# Table 3.2 (Type 1 spectrum) and Table 3.3 (Type 2 spectrum)
# Columns: S, TB (s), TC (s), TD (s)
# ---------------------------------------------------------------------------

_GROUND_PARAMS: dict[str, dict[str, tuple[float, float, float, float]]] = {
    # Type 1 (M_s > 5.5)
    "1": {
        "A": (1.0, 0.15, 0.4, 2.0),
        "B": (1.2, 0.15, 0.5, 2.0),
        "C": (1.15, 0.20, 0.6, 2.0),
        "D": (1.35, 0.20, 0.8, 2.0),
        "E": (1.4, 0.15, 0.5, 2.0),
    },
    # Type 2 (M_s ≤ 5.5)
    "2": {
        "A": (1.0, 0.05, 0.25, 1.2),
        "B": (1.35, 0.05, 0.25, 1.2),
        "C": (1.5, 0.10, 0.25, 1.2),
        "D": (1.8, 0.10, 0.30, 1.2),
        "E": (1.6, 0.05, 0.25, 1.2),
    },
}

_VALID_GROUND_TYPES = ("A", "B", "C", "D", "E")
_VALID_SPECTRUM_TYPES = ("1", "2")

# ---------------------------------------------------------------------------
# Importance factors (EN 1998-1 Table 4.3)
# Importance classes I, II, III, IV → gamma_I recommended values
# (national annexes may differ; these are the informative values)
# ---------------------------------------------------------------------------
_IMPORTANCE_FACTORS: dict[int, float] = {
    1: 0.8,   # Importance class I   (low importance)
    2: 1.0,   # Importance class II  (ordinary)
    3: 1.2,   # Importance class III (important)
    4: 1.4,   # Importance class IV  (critical)
}

# ---------------------------------------------------------------------------
# Approximate period coefficients §4.3.3.2.2 Eq. (4.6)
# structural_type: Ct (for T1 = Ct·H^(3/4))
# ---------------------------------------------------------------------------
_CT: dict[str, float] = {
    "moment_resisting_frame_concrete": 0.075,
    "moment_resisting_frame_steel":    0.085,
    "eccentrically_braced_steel":      0.075,
    "other":                           0.050,
}

# ---------------------------------------------------------------------------
# Lower bound factor for Sd: β = 0.2 (EN 1998-1 §3.2.2.5 note)
# ---------------------------------------------------------------------------
_BETA = 0.2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _se_elastic(T: float, ag_eff: float, S: float, TB: float, TC: float,
                TD: float, eta: float) -> float:
    """Elastic response spectrum Se(T) per Eq. (3.9)–(3.12).

    eta = damping correction factor = sqrt(10/(5+xi)) >= 0.55 (xi % damping).
    All inputs validated by caller.
    Returns Se in m/s².
    """
    if T < TB:
        # Eq. (3.9): 0 ≤ T < TB  (rising)
        return ag_eff * S * (1.0 + (T / TB) * (eta * 2.5 - 1.0))
    elif T <= TC:
        # Eq. (3.10): TB ≤ T ≤ TC  (constant acceleration plateau)
        return ag_eff * S * eta * 2.5
    elif T <= TD:
        # Eq. (3.11): TC < T ≤ TD  (constant velocity)
        return ag_eff * S * eta * 2.5 * (TC / T)
    else:
        # Eq. (3.12): TD < T ≤ 4 s  (constant displacement)
        return ag_eff * S * eta * 2.5 * (TC * TD / (T * T))


def _sd_design(T: float, ag_eff: float, S: float, TB: float, TC: float,
               TD: float, q: float) -> float:
    """Design spectrum Sd(T) per Eq. (3.13)–(3.16).

    Lower bound β·ag_eff applied in regions (3.15) and (3.16).
    Returns Sd in m/s².
    """
    beta_ag = _BETA * ag_eff
    if T < TB:
        # Eq. (3.13): 0 ≤ T < TB
        return ag_eff * S * (2.0 / 3.0 + (T / TB) * (2.5 / q - 2.0 / 3.0))
    elif T <= TC:
        # Eq. (3.14): TB ≤ T ≤ TC
        return ag_eff * S * 2.5 / q
    elif T <= TD:
        # Eq. (3.15): TC < T ≤ TD
        val = ag_eff * S * 2.5 / q * (TC / T)
        return max(val, beta_ag)
    else:
        # Eq. (3.16): TD < T ≤ 4 s
        val = ag_eff * S * 2.5 / q * (TC * TD / (T * T))
        return max(val, beta_ag)


# ---------------------------------------------------------------------------
# ec8_design_spectrum
# ---------------------------------------------------------------------------

def ec8_design_spectrum(
    T: float,
    ag: float,
    ground_type: str,
    spectrum_type: str = "1",
    q: float = 1.5,
    gamma_I: float = 1.0,
    *,
    xi: float = 5.0,
) -> dict[str, Any]:
    """EC8 design response spectrum Sd(T).

    Parameters
    ----------
    T : float
        Structural period (s). Must be >= 0 and <= 4.0 s.
    ag : float
        Reference peak ground acceleration (m/s²). > 0.
        (e.g. for ag = 0.25g pass 0.25 * 9.80665 = 2.452 m/s²)
    ground_type : str
        EC8 ground type: 'A', 'B', 'C', 'D', or 'E'.
    spectrum_type : str
        '1' (Type 1, M_s > 5.5) or '2' (Type 2, M_s ≤ 5.5). Default '1'.
    q : float
        Behaviour factor (energy dissipation). >= 1.0. Default 1.5.
    gamma_I : float
        Importance factor. > 0. Default 1.0 (Importance Class II).
    xi : float
        Viscous damping ratio (%). Default 5.0. Affects elastic spectrum eta.

    Returns
    -------
    dict with keys: ok, T, Sd_m_s2, Se_m_s2, ag_eff, S, TB, TC, TD,
                    spectrum_type, ground_type, q, gamma_I, eta, region,
                    warnings.
    """
    warnings: list[str] = []

    # --- Validate ---
    gt = ground_type.upper().strip()
    st = str(spectrum_type).strip()
    if gt not in _VALID_GROUND_TYPES:
        return {"ok": False, "reason": f"ground_type must be one of {_VALID_GROUND_TYPES}"}
    if st not in _VALID_SPECTRUM_TYPES:
        return {"ok": False, "reason": f"spectrum_type must be '1' or '2'"}
    if T < 0:
        return {"ok": False, "reason": "T must be >= 0"}
    if T > 4.0:
        return {"ok": False, "reason": "T must be <= 4.0 s (EC8 spectrum defined to 4 s)"}
    if ag <= 0:
        return {"ok": False, "reason": "ag must be > 0 (m/s²)"}
    if q < 1.0:
        return {"ok": False, "reason": "q (behaviour factor) must be >= 1.0"}
    if gamma_I <= 0:
        return {"ok": False, "reason": "gamma_I must be > 0"}
    if xi <= 0:
        return {"ok": False, "reason": "xi (damping %) must be > 0"}

    S, TB, TC, TD = _GROUND_PARAMS[st][gt]
    ag_eff = ag * gamma_I  # design PGA

    # Damping correction factor eta (Eq. 3.4), floor 0.55
    eta = max(math.sqrt(10.0 / (5.0 + xi)), 0.55)

    Se = _se_elastic(T, ag_eff, S, TB, TC, TD, eta)
    Sd = _sd_design(T, ag_eff, S, TB, TC, TD, q)

    # Determine region
    if T < TB:
        region = "rising"
    elif T <= TC:
        region = "plateau"
    elif T <= TD:
        region = "velocity"
    else:
        region = "displacement"

    if T > 2.5:
        warnings.append(
            f"T={T:.3f}s > 2.5 s: long-period range; verify modal RSA is more "
            "appropriate per EN 1998-1 §4.3.3.1."
        )
    if q > 6.5:
        warnings.append(
            f"q={q:.2f} > 6.5: unusually high behaviour factor; confirm with "
            "EN 1998-1 §5–6 and national annex."
        )

    return {
        "ok": True,
        "T": round(T, 4),
        "Sd_m_s2": round(Sd, 6),
        "Se_m_s2": round(Se, 6),
        "ag_eff": round(ag_eff, 6),
        "S": S,
        "TB": TB,
        "TC": TC,
        "TD": TD,
        "spectrum_type": st,
        "ground_type": gt,
        "q": q,
        "gamma_I": gamma_I,
        "eta": round(eta, 6),
        "region": region,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# ec8_lateral_force
# ---------------------------------------------------------------------------

def ec8_lateral_force(
    ag: float,
    ground_type: str,
    H: float,
    m_stories: list[float],
    z_stories: list[float],
    *,
    spectrum_type: str = "1",
    q: float = 1.5,
    gamma_I: float = 1.0,
    lambda_corr: float | None = None,
    structural_type: str = "other",
    xi: float = 5.0,
) -> dict[str, Any]:
    """EC8 lateral force method (§4.3.3.2).

    Parameters
    ----------
    ag : float
        Reference peak ground acceleration (m/s²). > 0.
    ground_type : str
        EC8 ground type: 'A', 'B', 'C', 'D', or 'E'.
    H : float
        Total building height above base (m). > 0.
    m_stories : list[float]
        Seismic mass at each storey (kg). Bottom to top. All > 0.
    z_stories : list[float]
        Height of each storey above base (m). Bottom to top.
        Strictly increasing. All > 0.
    spectrum_type : str
        '1' or '2'. Default '1'.
    q : float
        Behaviour factor. >= 1.0. Default 1.5.
    gamma_I : float
        Importance factor. > 0. Default 1.0.
    lambda_corr : float or None
        Correction factor λ per §4.3.3.2.2 (0.85 when T1 ≤ 2·TC and
        building has > 2 storeys, else 1.0). If None, auto-computed.
    structural_type : str
        Structural system type for Ct: 'moment_resisting_frame_concrete',
        'moment_resisting_frame_steel', 'eccentrically_braced_steel',
        'other' (default).
    xi : float
        Damping ratio (%). Default 5.0.

    Returns
    -------
    dict with keys: ok, T1_s, Sd_T1, Fb_N, Fi_N (list), Cvx (list),
                    Ct, H_m, m_total_kg, lambda_corr, warnings.
    """
    warnings: list[str] = []

    # --- Validate ---
    gt = ground_type.upper().strip()
    st = str(spectrum_type).strip()
    stype = structural_type.lower().strip()

    if gt not in _VALID_GROUND_TYPES:
        return {"ok": False, "reason": f"ground_type must be one of {_VALID_GROUND_TYPES}"}
    if st not in _VALID_SPECTRUM_TYPES:
        return {"ok": False, "reason": "spectrum_type must be '1' or '2'"}
    if stype not in _CT:
        return {"ok": False, "reason": f"structural_type must be one of {list(_CT.keys())}"}
    if ag <= 0:
        return {"ok": False, "reason": "ag must be > 0 (m/s²)"}
    if H <= 0:
        return {"ok": False, "reason": "H must be > 0 (m)"}
    if len(m_stories) == 0:
        return {"ok": False, "reason": "m_stories must not be empty"}
    if len(m_stories) != len(z_stories):
        return {"ok": False, "reason": "m_stories and z_stories must be the same length"}
    if any(m <= 0 for m in m_stories):
        return {"ok": False, "reason": "All m_stories values must be > 0 (kg)"}
    if any(z <= 0 for z in z_stories):
        return {"ok": False, "reason": "All z_stories values must be > 0 (m)"}
    for i in range(1, len(z_stories)):
        if z_stories[i] <= z_stories[i - 1]:
            return {
                "ok": False,
                "reason": "z_stories must be strictly increasing (bottom to top)",
            }
    if q < 1.0:
        return {"ok": False, "reason": "q must be >= 1.0"}
    if gamma_I <= 0:
        return {"ok": False, "reason": "gamma_I must be > 0"}

    # --- Approximate fundamental period T1 = Ct · H^(3/4) ---
    Ct = _CT[stype]
    T1 = Ct * (H ** 0.75)

    # Clamp to spectrum range
    if T1 > 4.0:
        warnings.append(
            f"T1={T1:.3f}s > 4.0 s: clamped to 4.0 s for spectrum evaluation; "
            "modal RSA strongly recommended per EN 1998-1 §4.3.3.1."
        )
        T1_spec = 4.0
    else:
        T1_spec = T1

    # --- Design spectral acceleration at T1 ---
    sd_res = ec8_design_spectrum(
        T1_spec, ag, gt,
        spectrum_type=st, q=q, gamma_I=gamma_I, xi=xi,
    )
    if not sd_res["ok"]:
        return sd_res
    Sd_T1 = sd_res["Sd_m_s2"]  # m/s²

    TC = sd_res["TC"]

    # --- Correction factor λ ---
    n = len(m_stories)
    if lambda_corr is None:
        if T1 <= 2.0 * TC and n > 2:
            lambda_corr = 0.85
        else:
            lambda_corr = 1.0

    # --- Total mass and base shear ---
    m_total = sum(m_stories)
    Fb = Sd_T1 * m_total * lambda_corr  # Newtons

    # --- Storey force distribution: Fi = Fb · (zi·mi) / Σ(zj·mj) ---
    zm = [z_stories[i] * m_stories[i] for i in range(n)]
    sum_zm = sum(zm)
    if sum_zm == 0.0:
        return {"ok": False, "reason": "Σ(zi·mi) is zero; check z_stories and m_stories"}

    Cvx = [v / sum_zm for v in zm]
    Fi = [Fb * c for c in Cvx]

    if abs(sum(Cvx) - 1.0) > 1e-9:
        warnings.append("Cvx values do not sum to 1.0 — numerical precision issue.")

    if T1 > 2.0 * TC:
        warnings.append(
            f"T1={T1:.3f}s > 2·TC={2.0 * TC:.3f}s: lateral force method applicability "
            "limit. Check regularity criteria per EN 1998-1 §4.3.3.1."
        )

    return {
        "ok": True,
        "T1_s": round(T1, 4),
        "T1_spec_s": round(T1_spec, 4),
        "Sd_T1_m_s2": round(Sd_T1, 6),
        "Fb_N": round(Fb, 3),
        "Fi_N": [round(f, 3) for f in Fi],
        "Cvx": [round(c, 6) for c in Cvx],
        "Ct": Ct,
        "H_m": round(H, 3),
        "m_total_kg": round(m_total, 3),
        "lambda_corr": lambda_corr,
        "spectrum_type": st,
        "ground_type": gt,
        "q": q,
        "gamma_I": gamma_I,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# ec8_rsa — Modal response spectrum analysis
# ---------------------------------------------------------------------------

def ec8_rsa(
    ag: float,
    ground_type: str,
    omega_n: list[float],
    phi_n: list[list[float]],
    m_stories: list[float],
    *,
    spectrum_type: str = "1",
    q: float = 1.5,
    gamma_I: float = 1.0,
    combination: str = "srss",
    xi: float = 5.0,
) -> dict[str, Any]:
    """EC8 modal response spectrum analysis (§4.3.3.3).

    Parameters
    ----------
    ag : float
        Reference peak ground acceleration (m/s²). > 0.
    ground_type : str
        EC8 ground type: 'A', 'B', 'C', 'D', or 'E'.
    omega_n : list[float]
        Undamped natural circular frequencies (rad/s), one per mode. All > 0.
    phi_n : list[list[float]]
        Mode shapes — list of n_modes lists, each of length n_dof (= len(m_stories)).
        phi_n[k][i] = mode-shape amplitude at DOF i for mode k.
    m_stories : list[float]
        Floor masses (kg). Length = n_dof. All > 0.
    spectrum_type : str
        '1' or '2'. Default '1'.
    q : float
        Behaviour factor. >= 1.0. Default 1.5.
    gamma_I : float
        Importance factor. > 0. Default 1.0.
    combination : str
        Modal combination rule: 'srss' (square-root sum of squares) or
        'cqc' (complete quadratic combination, Wilson-Penzien). Default 'srss'.
    xi : float
        Damping ratio (%) — uniform for all modes. Default 5.0.

    Returns
    -------
    dict with keys:
        ok, n_modes, n_dof,
        T_n (list: period per mode, s),
        Sd_n (list: Sd per mode, m/s²),
        Gamma_n (list: modal participation factor),
        m_eff_n (list: effective modal mass, kg),
        m_eff_total_kg, m_total_kg, m_eff_ratio,
        m_eff_check_ok (bool: ratio >= 0.9),
        V_n (list: modal base shear per mode, N),
        V_combined_N (float: combined base shear, N),
        u_n (list[list]: modal peak displacement per storey, m),
        u_combined (list: combined peak displacement per storey, m),
        drift_n (list[list]: inter-storey drift per mode, m),
        drift_combined (list: combined inter-storey drift, m),
        combination, warnings.
    """
    warnings: list[str] = []

    # --- Validate ---
    gt = ground_type.upper().strip()
    st = str(spectrum_type).strip()
    comb = combination.lower().strip()

    if gt not in _VALID_GROUND_TYPES:
        return {"ok": False, "reason": f"ground_type must be one of {_VALID_GROUND_TYPES}"}
    if st not in _VALID_SPECTRUM_TYPES:
        return {"ok": False, "reason": "spectrum_type must be '1' or '2'"}
    if comb not in ("srss", "cqc"):
        return {"ok": False, "reason": "combination must be 'srss' or 'cqc'"}
    if ag <= 0:
        return {"ok": False, "reason": "ag must be > 0 (m/s²)"}
    if q < 1.0:
        return {"ok": False, "reason": "q must be >= 1.0"}
    if gamma_I <= 0:
        return {"ok": False, "reason": "gamma_I must be > 0"}

    n_modes = len(omega_n)
    if n_modes == 0:
        return {"ok": False, "reason": "omega_n must not be empty"}
    if any(w <= 0 for w in omega_n):
        return {"ok": False, "reason": "All omega_n values must be > 0 (rad/s)"}

    n_dof = len(m_stories)
    if n_dof == 0:
        return {"ok": False, "reason": "m_stories must not be empty"}
    if any(m <= 0 for m in m_stories):
        return {"ok": False, "reason": "All m_stories values must be > 0 (kg)"}
    if len(phi_n) != n_modes:
        return {"ok": False, "reason": f"phi_n must have {n_modes} rows (one per mode)"}
    for k, phi_k in enumerate(phi_n):
        if len(phi_k) != n_dof:
            return {
                "ok": False,
                "reason": (
                    f"phi_n[{k}] has {len(phi_k)} entries; "
                    f"expected {n_dof} (= len(m_stories))"
                ),
            }

    m_total = sum(m_stories)

    # --- Per-mode calculations ---
    T_n: list[float] = []
    Sd_n: list[float] = []
    Gamma_n: list[float] = []
    m_eff_n: list[float] = []
    V_n: list[float] = []
    u_n: list[list[float]] = []

    xi_frac = xi / 100.0  # dimensionless for CQC

    for k in range(n_modes):
        omega_k = omega_n[k]
        phi_k = phi_n[k]

        T_k = 2.0 * math.pi / omega_k

        # Evaluate Sd at T_k (clamp to [0, 4] for spectrum)
        T_spec = min(T_k, 4.0)
        if T_k > 4.0:
            warnings.append(
                f"Mode {k + 1}: T={T_k:.3f}s > 4.0 s; clamped to 4.0 s for "
                "spectrum evaluation."
            )
        sd_res = ec8_design_spectrum(
            T_spec, ag, gt,
            spectrum_type=st, q=q, gamma_I=gamma_I, xi=xi,
        )
        if not sd_res["ok"]:
            return sd_res
        Sd_k = sd_res["Sd_m_s2"]

        # Modal participation factor Γ_k = (φ_k^T · M · 1) / (φ_k^T · M · φ_k)
        # (unit participation vector; seismic excitation along all DOF equally)
        phi_T_M_1 = sum(phi_k[i] * m_stories[i] for i in range(n_dof))
        phi_T_M_phi = sum(phi_k[i] * phi_k[i] * m_stories[i] for i in range(n_dof))

        if abs(phi_T_M_phi) < 1e-30:
            return {
                "ok": False,
                "reason": f"Mode {k + 1}: modal mass φ^T·M·φ ≈ 0; degenerate mode shape.",
            }

        Gamma_k = phi_T_M_1 / phi_T_M_phi
        m_eff_k = (phi_T_M_1 ** 2) / phi_T_M_phi  # effective modal mass

        # Modal peak displacements at each storey (m)
        # u_k(i) = Γ_k · φ_k(i) · Sd(T_k) / omega_k²
        # (Sd is acceleration; convert to displacement: Sd·T²/(4π²) = Sd/ω²)
        u_k = [Gamma_k * phi_k[i] * Sd_k / (omega_k ** 2) for i in range(n_dof)]

        # Modal base shear: Vb_k = m_eff_k · Sd(T_k)
        Vb_k = m_eff_k * Sd_k

        T_n.append(T_k)
        Sd_n.append(Sd_k)
        Gamma_n.append(Gamma_k)
        m_eff_n.append(m_eff_k)
        V_n.append(Vb_k)
        u_n.append(u_k)

    # --- Effective mass check ---
    m_eff_total = sum(m_eff_n)
    m_eff_ratio = m_eff_total / m_total if m_total > 0 else 0.0
    m_eff_check_ok = m_eff_ratio >= 0.90

    if not m_eff_check_ok:
        warnings.append(
            f"Effective modal mass ratio = {m_eff_ratio:.3f} < 0.90 "
            "(EN 1998-1 §4.3.3.3.1(3)). Include more modes."
        )

    # --- Modal combination ---
    def _srss_combine_scalar(vals: list[float]) -> float:
        return math.sqrt(sum(v * v for v in vals))

    def _cqc_combine_scalar(vals: list[float]) -> float:
        """CQC combination per Wilson-Penzien.
        Cross-correlation ρ_kl = 8·ξ²·(1+r)·r^(3/2) / ((1-r²)²+4·ξ²·r·(1+r)²)
        where r = omega_k/omega_l.
        """
        n = len(vals)
        result = 0.0
        for k_idx in range(n):
            for l_idx in range(n):
                r = omega_n[k_idx] / omega_n[l_idx]
                xi2 = xi_frac * xi_frac
                num = 8.0 * xi2 * (1.0 + r) * (r ** 1.5)
                denom = (1.0 - r * r) ** 2 + 4.0 * xi2 * r * (1.0 + r) ** 2
                rho = num / denom if abs(denom) > 1e-30 else 1.0
                result += rho * vals[k_idx] * vals[l_idx]
        return math.sqrt(max(result, 0.0))

    if comb == "srss":
        V_combined = _srss_combine_scalar(V_n)
        u_combined = [
            _srss_combine_scalar([u_n[k][i] for k in range(n_modes)])
            for i in range(n_dof)
        ]
    else:  # cqc
        V_combined = _cqc_combine_scalar(V_n)
        u_combined = [
            _cqc_combine_scalar([u_n[k][i] for k in range(n_modes)])
            for i in range(n_dof)
        ]

    # --- Inter-storey drift per mode and combined ---
    # drift[i] = |u[i+1] - u[i]| (top - below); drift[0] = u[0] (above base=0)
    drift_n: list[list[float]] = []
    for k_idx in range(n_modes):
        dk = [abs(u_n[k_idx][0])]
        for i in range(1, n_dof):
            dk.append(abs(u_n[k_idx][i] - u_n[k_idx][i - 1]))
        drift_n.append(dk)

    drift_combined = [abs(u_combined[0])]
    for i in range(1, n_dof):
        drift_combined.append(abs(u_combined[i] - u_combined[i - 1]))

    return {
        "ok": True,
        "n_modes": n_modes,
        "n_dof": n_dof,
        "T_n": [round(t, 6) for t in T_n],
        "Sd_n": [round(s, 6) for s in Sd_n],
        "Gamma_n": [round(g, 6) for g in Gamma_n],
        "m_eff_n": [round(m, 3) for m in m_eff_n],
        "m_eff_total_kg": round(m_eff_total, 3),
        "m_total_kg": round(m_total, 3),
        "m_eff_ratio": round(m_eff_ratio, 6),
        "m_eff_check_ok": m_eff_check_ok,
        "V_n": [round(v, 3) for v in V_n],
        "V_combined_N": round(V_combined, 3),
        "u_n": [[round(u, 9) for u in uk] for uk in u_n],
        "u_combined": [round(u, 9) for u in u_combined],
        "drift_n": [[round(d, 9) for d in dk] for dk in drift_n],
        "drift_combined": [round(d, 9) for d in drift_combined],
        "combination": comb,
        "spectrum_type": st,
        "ground_type": gt,
        "q": q,
        "gamma_I": gamma_I,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# LLM tool wrappers (registered lazily via try/except for hermetic tests)
# ---------------------------------------------------------------------------

try:
    import json as _json

    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx  # noqa: F401

    _ec8_spectrum_spec = ToolSpec(
        name="ec8_spectrum",
        description=(
            "Evaluate the Eurocode 8 (EN 1998-1) design response spectrum "
            "Sd(T) at a given structural period.\n"
            "\n"
            "Per §3.2.2.5 Eq. (3.13)–(3.16):\n"
            "  0 ≤ T < TB:  Sd = ag·γI·S·(2/3 + T/TB·(2.5/q − 2/3))\n"
            "  TB ≤ T ≤ TC: Sd = ag·γI·S·2.5/q\n"
            "  TC < T ≤ TD: Sd = ag·γI·S·2.5/q·(TC/T)  ≥ β·ag·γI\n"
            "  TD < T ≤ 4s: Sd = ag·γI·S·2.5/q·(TC·TD/T²) ≥ β·ag·γI\n"
            "\n"
            "Ground type parameters (Type 1) — S, TB, TC, TD:\n"
            "  A: 1.0, 0.15, 0.4, 2.0\n"
            "  B: 1.2, 0.15, 0.5, 2.0\n"
            "  C: 1.15, 0.20, 0.6, 2.0\n"
            "  D: 1.35, 0.20, 0.8, 2.0\n"
            "  E: 1.4, 0.15, 0.5, 2.0\n"
            "\n"
            "Returns Sd_m_s2, Se_m_s2, ag_eff, S, TB, TC, TD, region, eta, warnings.\n"
            "Errors: {ok:false, reason} — never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "T": {"type": "number", "description": "Structural period (s). 0 ≤ T ≤ 4.0."},
                "ag": {
                    "type": "number",
                    "description": (
                        "Reference peak ground acceleration (m/s²). > 0. "
                        "Example: 0.25g = 0.25 × 9.80665 = 2.452 m/s²."
                    ),
                },
                "ground_type": {
                    "type": "string",
                    "enum": ["A", "B", "C", "D", "E"],
                    "description": "EC8 ground type (soil class). A=rock, E=soft.",
                },
                "spectrum_type": {
                    "type": "string",
                    "enum": ["1", "2"],
                    "description": (
                        "Type 1 (M_s > 5.5, far-field) or Type 2 (M_s ≤ 5.5). "
                        "Default '1'."
                    ),
                },
                "q": {
                    "type": "number",
                    "description": "Behaviour factor (energy dissipation). >= 1.0. Default 1.5.",
                },
                "gamma_I": {
                    "type": "number",
                    "description": "Importance factor. Default 1.0 (Importance Class II).",
                },
                "xi": {
                    "type": "number",
                    "description": "Viscous damping ratio (%). Default 5.0.",
                },
            },
            "required": ["T", "ag", "ground_type"],
        },
    )

    @register(_ec8_spectrum_spec, write=False)
    async def run_ec8_spectrum(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

        for field in ("T", "ag", "ground_type"):
            if a.get(field) is None:
                return _json.dumps({"ok": False, "reason": f"{field} is required"})

        kwargs: dict = {}
        for opt in ("spectrum_type", "q", "gamma_I", "xi"):
            if opt in a:
                kwargs[opt] = a[opt]

        result = ec8_design_spectrum(a["T"], a["ag"], a["ground_type"], **kwargs)
        return ok_payload(result)

    # --- ec8_lateral_force tool ---

    _ec8_lf_spec = ToolSpec(
        name="ec8_lateral_force",
        description=(
            "EC8 lateral force method per EN 1998-1 §4.3.3.2.\n"
            "\n"
            "  T1 = Ct · H^(3/4)   (Ct depends on structural type)\n"
            "  Fb = Sd(T1) · m · λ  (base shear, N)\n"
            "  Fi = Fb · (zi·mi) / Σ(zj·mj)\n"
            "\n"
            "λ correction: 0.85 when T1 ≤ 2·TC and storeys > 2; else 1.0.\n"
            "\n"
            "Returns T1_s, Sd_T1_m_s2, Fb_N, Fi_N, Cvx, m_total_kg, warnings.\n"
            "Errors: {ok:false, reason} — never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "ag": {"type": "number", "description": "Peak ground acceleration (m/s²). > 0."},
                "ground_type": {
                    "type": "string",
                    "enum": ["A", "B", "C", "D", "E"],
                    "description": "EC8 ground type.",
                },
                "H": {"type": "number", "description": "Total building height above base (m). > 0."},
                "m_stories": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Floor masses (kg). Bottom to top. All > 0.",
                },
                "z_stories": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Floor heights above base (m). Strictly increasing.",
                },
                "spectrum_type": {"type": "string", "enum": ["1", "2"], "description": "Default '1'."},
                "q": {"type": "number", "description": "Behaviour factor >= 1.0. Default 1.5."},
                "gamma_I": {"type": "number", "description": "Importance factor. Default 1.0."},
                "structural_type": {
                    "type": "string",
                    "enum": [
                        "moment_resisting_frame_concrete",
                        "moment_resisting_frame_steel",
                        "eccentrically_braced_steel",
                        "other",
                    ],
                    "description": "Structural type for Ct. Default 'other' (Ct=0.05).",
                },
                "lambda_corr": {
                    "type": "number",
                    "description": "Correction factor λ (override auto). Typically 0.85 or 1.0.",
                },
                "xi": {"type": "number", "description": "Damping ratio (%). Default 5.0."},
            },
            "required": ["ag", "ground_type", "H", "m_stories", "z_stories"],
        },
    )

    @register(_ec8_lf_spec, write=False)
    async def run_ec8_lateral_force(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

        for field in ("ag", "ground_type", "H", "m_stories", "z_stories"):
            if a.get(field) is None:
                return _json.dumps({"ok": False, "reason": f"{field} is required"})

        kwargs: dict = {}
        for opt in ("spectrum_type", "q", "gamma_I", "lambda_corr",
                    "structural_type", "xi"):
            if opt in a:
                kwargs[opt] = a[opt]

        result = ec8_lateral_force(
            a["ag"], a["ground_type"], a["H"],
            a["m_stories"], a["z_stories"],
            **kwargs,
        )
        return ok_payload(result)

    # --- ec8_rsa tool ---

    _ec8_rsa_spec = ToolSpec(
        name="ec8_rsa",
        description=(
            "EC8 modal response spectrum analysis per EN 1998-1 §4.3.3.3.\n"
            "\n"
            "Per-mode response:\n"
            "  T_k = 2π / ω_k\n"
            "  Γ_k = (φ_k^T·M·1) / (φ_k^T·M·φ_k)   (participation factor)\n"
            "  m_eff_k = (φ_k^T·M·1)² / (φ_k^T·M·φ_k) (effective modal mass)\n"
            "  V_k = m_eff_k · Sd(T_k)               (modal base shear, N)\n"
            "\n"
            "Checks Σm_eff ≥ 0.90·M_total (§4.3.3.3.1(3)).\n"
            "Combines modes via SRSS or CQC (Wilson-Penzien).\n"
            "\n"
            "Returns T_n, Sd_n, Gamma_n, m_eff_n, m_eff_ratio, m_eff_check_ok, "
            "V_n, V_combined_N, u_combined, drift_combined, warnings.\n"
            "Errors: {ok:false, reason} — never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "ag": {"type": "number", "description": "Peak ground acceleration (m/s²). > 0."},
                "ground_type": {
                    "type": "string",
                    "enum": ["A", "B", "C", "D", "E"],
                    "description": "EC8 ground type.",
                },
                "omega_n": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Natural circular frequencies (rad/s). One per mode. All > 0.",
                },
                "phi_n": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                    "description": "Mode shapes. phi_n[k][i] = mode k, DOF i.",
                },
                "m_stories": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Floor masses (kg). All > 0.",
                },
                "spectrum_type": {"type": "string", "enum": ["1", "2"], "description": "Default '1'."},
                "q": {"type": "number", "description": "Behaviour factor >= 1.0. Default 1.5."},
                "gamma_I": {"type": "number", "description": "Importance factor. Default 1.0."},
                "combination": {
                    "type": "string",
                    "enum": ["srss", "cqc"],
                    "description": "Modal combination: 'srss' or 'cqc'. Default 'srss'.",
                },
                "xi": {"type": "number", "description": "Damping ratio (%). Default 5.0."},
            },
            "required": ["ag", "ground_type", "omega_n", "phi_n", "m_stories"],
        },
    )

    @register(_ec8_rsa_spec, write=False)
    async def run_ec8_rsa(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")

        for field in ("ag", "ground_type", "omega_n", "phi_n", "m_stories"):
            if a.get(field) is None:
                return _json.dumps({"ok": False, "reason": f"{field} is required"})

        kwargs: dict = {}
        for opt in ("spectrum_type", "q", "gamma_I", "combination", "xi"):
            if opt in a:
                kwargs[opt] = a[opt]

        result = ec8_rsa(
            a["ag"], a["ground_type"],
            a["omega_n"], a["phi_n"], a["m_stories"],
            **kwargs,
        )
        return ok_payload(result)

except ImportError:
    # Running in hermetic / pure-Python test environment
    pass
