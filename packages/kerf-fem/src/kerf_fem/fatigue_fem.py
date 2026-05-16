"""
Fatigue and durability analysis from FEM stress results.

Public entry-point
------------------
    analyse_fatigue(stress_history, material, options) -> dict

Capabilities
------------
  * Rainflow cycle counting on per-node stress histories (ASTM E1049 4-point
    algorithm)
  * Signed von-Mises and maximum-principal damage parameters
  * Critical-plane search (normal-stress amplitude on 18 planes × 2 axes)
  * Palmgren-Miner linear cumulative damage rule per node → damage map
  * Mean-stress corrections: Goodman, Gerber, Smith-Watson-Topper (SWT)
  * Stress-life (Basquin) and strain-life (Coffin-Manson) curves
  * Minimum-life location and safety factor
  * Multiaxial proportional vs non-proportional flag per node
  * FALSTAFF / block-spectrum support (list of (range, mean, count) blocks)
  * Infinite-life when all amplitudes < endurance limit

All routines are pure Python — no numpy, no scipy.
Functions never raise; errors are returned as {"ok": False, "reason": "..."}.

Input formats
-------------
stress_history : list of per-node records.
    Each record is either:
      (a) dict  { "node": int,
                  "history": [ [s11,s22,s33,s12,s13,s23], ... ] }
          — full 3-D tensor history at each time point
      (b) dict  { "node": int,
                  "unit_stress": [s11,s22,s33,s12,s13,s23],
                  "load_history": [F1, F2, ...] }
          — linear superposition: σ(t) = unit_stress * F(t)

    Alternatively a flat block spectrum:
      { "node": int,
        "spectrum": [ {"range": r, "mean": m, "cycles": n}, ... ] }

material : dict with:
    "Su"         — ultimate tensile strength [Pa]  (required)
    "Sy"         — 0.2% yield strength [Pa]        (optional, for SWT)
    "Se"         — endurance limit [Pa]             (optional; default Su/2)
    "b"          — Basquin exponent  (default -0.085)
    "c"          — Coffin-Manson exponent (default -0.60)
    "E"          — Young's modulus [Pa]             (optional, for strain-life)
    "sf_prime"   — fatigue strength coefficient [Pa] (default 1.5*Su)
    "ef_prime"   — fatigue ductility coefficient    (default 0.59)

options : dict (optional):
    "correction"        — "goodman" | "gerber" | "swt"  (default "goodman")
    "damage_param"      — "von_mises" | "max_principal"  (default "von_mises")
    "life_curve"        — "basquin" | "coffin_manson"    (default "basquin")
    "target_life"       — design life in cycles (default 1e6)
    "safety_factor_on"  — "amplitude" | "life"           (default "amplitude")

Returns
-------
{
    "ok"               : bool,
    "damage_map"       : { node_id: damage_value, ... },
    "life_map"         : { node_id: life_cycles, ... },
    "min_life_node"    : int,
    "min_life_cycles"  : float,
    "safety_factor"    : float,
    "infinite_life"    : bool,
    "multiaxial_flags" : { node_id: "proportional" | "non_proportional", ... },
    "warnings"         : [str, ...],
    "reason"           : str   (only when ok=False)
}
"""

from __future__ import annotations

import math
from typing import Any

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_fem._compat import ToolSpec, err_payload, ok_payload, register, ProjectCtx


# ===========================================================================
# Module-level constants
# ===========================================================================

_SQRT2 = math.sqrt(2.0)


# ===========================================================================
# Mathematical helpers — pure Python, no numpy
# ===========================================================================

def _principal_stresses_3d(s: list[float]) -> list[float]:
    """
    Compute eigenvalues of a 3-D symmetric stress tensor via Jacobi iteration.

    s = [s11, s22, s33, s12, s13, s23]
    Returns [sp1, sp2, sp3] sorted descending (sp1 >= sp2 >= sp3).

    Uses the classical Jacobi rotation method which is robust for all cases
    including repeated eigenvalues and degenerate tensors.
    """
    s11, s22, s33, s12, s13, s23 = s
    # Working 3×3 matrix (only need upper triangle; maintain symmetry)
    M = [
        [s11, s12, s13],
        [s12, s22, s23],
        [s13, s23, s33],
    ]
    trace = s11 + s22 + s33

    for _ in range(200):
        # Find largest off-diagonal element
        p, q = 0, 1
        max_off = abs(M[0][1])
        for i in range(3):
            for j in range(i + 1, 3):
                if abs(M[i][j]) > max_off:
                    max_off = abs(M[i][j])
                    p, q = i, j

        # Convergence check relative to trace magnitude
        if max_off < 1e-13 * (abs(trace) + 1e-30):
            break

        # Jacobi rotation angle
        denom = M[q][q] - M[p][p]
        if abs(denom) < 1e-30 * max_off:
            theta = math.pi / 4.0
        else:
            theta = 0.5 * math.atan2(2.0 * M[p][q], denom)

        c, s_val = math.cos(theta), math.sin(theta)

        # Update diagonal
        Mpp_new = (c * c * M[p][p] + 2.0 * c * s_val * M[p][q]
                   + s_val * s_val * M[q][q])
        Mqq_new = (s_val * s_val * M[p][p] - 2.0 * c * s_val * M[p][q]
                   + c * c * M[q][q])

        # Update off-diagonal rows/columns
        for k in range(3):
            if k == p or k == q:
                continue
            Mpk_new = c * M[p][k] + s_val * M[q][k]
            Mqk_new = -s_val * M[p][k] + c * M[q][k]
            M[p][k] = M[k][p] = Mpk_new
            M[q][k] = M[k][q] = Mqk_new

        M[p][p] = Mpp_new
        M[q][q] = Mqq_new
        M[p][q] = M[q][p] = 0.0

    return sorted([M[0][0], M[1][1], M[2][2]], reverse=True)


def _von_mises_stress(s: list[float]) -> float:
    """Signed von-Mises stress (sign of hydrostatic component).

    s = [s11, s22, s33, s12, s13, s23]

    von Mises formula:
        σ_vm = sqrt(0.5 * [(σ11-σ22)² + (σ22-σ33)² + (σ33-σ11)²]
                    + 3*(σ12² + σ13² + σ23²))

    Sign follows the hydrostatic component (positive under tension).
    """
    s11, s22, s33, s12, s13, s23 = s
    vm = math.sqrt(
        0.5 * ((s11 - s22) ** 2 + (s22 - s33) ** 2 + (s33 - s11) ** 2)
        + 3.0 * (s12 * s12 + s13 * s13 + s23 * s23)
    )
    sm = (s11 + s22 + s33) / 3.0
    sign = 1.0 if sm >= 0.0 else -1.0
    return sign * vm


def _normal_stress_on_plane(s: list[float], n: list[float]) -> float:
    """
    Normal stress on a plane with unit normal n = [nx, ny, nz].
    σ_n = n · [S] · n
    s = [s11, s22, s33, s12, s13, s23]
    """
    s11, s22, s33, s12, s13, s23 = s
    nx, ny, nz = n
    # Traction vector t = [S] n
    tx = s11 * nx + s12 * ny + s13 * nz
    ty = s12 * nx + s22 * ny + s23 * nz
    tz = s13 * nx + s23 * ny + s33 * nz
    return tx * nx + ty * ny + tz * nz


def _damage_parameter(s: list[float], param: str) -> float:
    """
    Scalar fatigue damage parameter from a stress tensor.

    param: "von_mises" | "max_principal"
    """
    if param == "max_principal":
        return _principal_stresses_3d(s)[0]
    # default: signed von Mises
    return _von_mises_stress(s)


# ===========================================================================
# Rainflow counting — ASTM E1049 4-point algorithm
# ===========================================================================

def _rainflow(series: list[float]) -> list[tuple[float, float, float]]:
    """
    Rainflow cycle counting per ASTM E1049-85(2017) 4-point algorithm.

    Parameters
    ----------
    series : list of scalar peak/valley values (reversals).
              The function internally reduces the input to reversals
              (keeps only local extrema) before counting.

    Returns
    -------
    list of (range, mean, count) tuples.
      count = 1.0 for full cycles, 0.5 for half-cycles (residue).
    """
    # --- Step 1: reduce to reversals (peaks and valleys) ---
    rev = _to_reversals(series)
    if len(rev) < 2:
        return []

    stack: list[float] = []
    cycles: list[tuple[float, float, float]] = []

    for pt in rev:
        stack.append(pt)
        # Apply 4-point rule: keep collapsing while len(stack) >= 4
        while len(stack) >= 4:
            # Points A, B, C, D (last four)
            A = stack[-4]
            B = stack[-3]
            C = stack[-2]
            D = stack[-1]
            rng_X = abs(C - B)  # candidate cycle range
            rng_Y = abs(B - A)  # preceding range
            rng_Z = abs(D - C)  # following range
            if rng_X <= rng_Y and rng_X <= rng_Z:
                # Full cycle: B-C
                mean_val = (B + C) / 2.0
                cycles.append((rng_X, mean_val, 1.0))
                # Remove B and C from stack
                stack = stack[:-4] + [A, D]
            else:
                break

    # Residue: half-cycles from remaining stack
    for i in range(len(stack) - 1):
        rng_i = abs(stack[i + 1] - stack[i])
        mean_i = (stack[i] + stack[i + 1]) / 2.0
        cycles.append((rng_i, mean_i, 0.5))

    return cycles


def _to_reversals(series: list[float]) -> list[float]:
    """
    Extract peaks and valleys from a time series (remove intermediate points).
    Also ensures the series starts with a peak or valley by keeping the first
    and last point.
    """
    if len(series) <= 2:
        return list(series)

    rev = [series[0]]
    for i in range(1, len(series) - 1):
        prev, curr, nxt = series[i - 1], series[i], series[i + 1]
        # Keep if local extremum
        if (curr >= prev and curr >= nxt) or (curr <= prev and curr <= nxt):
            rev.append(curr)
    rev.append(series[-1])
    return rev


# ===========================================================================
# Stress-life (Basquin) and strain-life (Coffin-Manson)
# ===========================================================================

def _basquin_life(sigma_a: float, sf_prime: float, b: float) -> float:
    """
    Basquin equation:  σ_a = σ'_f * (2N)^b
    Solve for N (reversals / 2):
        2N = (σ_a / σ'_f)^(1/b)
        N  = 0.5 * (σ_a / σ'_f)^(1/b)
    Returns life in cycles (N).  Returns inf if σ_a ≤ 0.
    """
    if sigma_a <= 0.0 or sf_prime <= 0.0:
        return math.inf
    # b is typically negative
    exponent = 1.0 / b
    two_N = (sigma_a / sf_prime) ** exponent
    return max(0.5 * two_N, 0.0)


def _coffin_manson_life(
    sigma_a: float,
    sf_prime: float, b: float,
    ef_prime: float, c: float,
    E: float,
) -> float:
    """
    Strain-life (Coffin-Manson + Basquin):
        Δε/2 = σ'_f/E * (2N)^b + ε'_f * (2N)^c

    Solve for N by bisection on f(N) = σ'_f/E*(2N)^b + ε'_f*(2N)^c - ε_a = 0,
    where ε_a = σ_a / E (elastic approximation for the total strain amplitude).

    Returns life in cycles.  Falls back to Basquin if E is not provided.
    """
    if E is None or E <= 0.0:
        return _basquin_life(sigma_a, sf_prime, b)

    eps_a = sigma_a / E

    def _f(log_two_N: float) -> float:
        two_N = math.exp(log_two_N)
        return (sf_prime / E * two_N ** b
                + ef_prime * two_N ** c
                - eps_a)

    # Bisect in log-space: search from 2N=1 (N=0.5) to 2N=1e12 (N=5e11)
    lo, hi = 0.0, math.log(1e12)
    f_lo, f_hi = _f(lo), _f(hi)
    if f_lo * f_hi > 0.0:
        # Fallback to Basquin
        return _basquin_life(sigma_a, sf_prime, b)

    for _ in range(60):
        mid = (lo + hi) / 2.0
        f_mid = _f(mid)
        if abs(f_mid) < 1e-12 * abs(eps_a + 1e-30):
            break
        if f_lo * f_mid < 0.0:
            hi = mid
            f_hi = f_mid
        else:
            lo = mid
            f_lo = f_mid

    two_N = math.exp((lo + hi) / 2.0)
    return max(two_N / 2.0, 0.0)


# ===========================================================================
# Mean-stress corrections
# ===========================================================================

def _mean_stress_correction(
    sigma_a: float,
    sigma_m: float,
    Su: float,
    Se: float,
    Sy: float,
    method: str,
) -> float:
    """
    Return equivalent fully-reversed stress amplitude after mean-stress correction.

    Goodman:   σ_a / Se + σ_m / Su = 1  →  σ_eq = σ_a / (1 - σ_m/Su)
    Gerber:    σ_a / Se + (σ_m/Su)² = 1 →  σ_eq = σ_a / (1 - (σ_m/Su)²)
    SWT:       σ_max * σ_a = σ_eq²     →  σ_eq = sqrt(σ_max * σ_a)

    Returns σ_eq (equivalent amplitude for a fully-reversed S-N curve).
    Compressive mean stress → returns σ_a unchanged (conservative).
    """
    if sigma_m <= 0.0:
        return sigma_a  # compressive mean: no correction (conservative)

    if method == "gerber":
        denom = 1.0 - (sigma_m / Su) ** 2
        if denom <= 0.0:
            return math.inf
        return sigma_a / denom

    elif method == "swt":
        sigma_max = sigma_a + sigma_m
        if sigma_max <= 0.0:
            return sigma_a
        return math.sqrt(sigma_max * sigma_a)

    else:  # goodman (default)
        denom = 1.0 - sigma_m / Su
        if denom <= 0.0:
            return math.inf
        return sigma_a / denom


# ===========================================================================
# Multiaxial proportionality check
# ===========================================================================

def _is_non_proportional(history: list[list[float]], tol: float = 0.1) -> bool:
    """
    Flag multiaxial non-proportionality.

    A stress history is proportional when all stress tensors remain in the
    same direction in deviatoric 6-D space (i.e. differ only by a scalar
    factor).  Non-proportional loading causes the deviatoric direction to
    rotate.

    Algorithm: project each tensor onto its unit deviatoric vector in 6-D,
    then compute the angle between successive unit vectors.  Non-proportional
    if the maximum such angle exceeds tol*π.

    The deviatoric vector in 6-D (Mandel notation):
        d = [s11-sm, s22-sm, s33-sm, √2·s12, √2·s13, √2·s23]
    where sm = (s11+s22+s33)/3.
    """
    if len(history) < 3:
        return False

    def _dev_unit(s: list[float]) -> list[float]:
        s11, s22, s33, s12, s13, s23 = s
        sm = (s11 + s22 + s33) / 3.0
        d = [s11 - sm, s22 - sm, s33 - sm,
             _SQRT2 * s12, _SQRT2 * s13, _SQRT2 * s23]
        mag = math.sqrt(sum(x * x for x in d))
        if mag < 1e-30:
            return [0.0] * 6
        return [x / mag for x in d]

    max_angle = 0.0
    prev_d = _dev_unit(history[0])
    for s in history[1:]:
        curr_d = _dev_unit(s)
        dot = sum(a * b for a, b in zip(prev_d, curr_d))
        # Use abs(dot) to handle sign-flips in fully reversed loading
        cos_t = max(-1.0, min(1.0, abs(dot)))
        angle = math.acos(cos_t)
        if angle > max_angle:
            max_angle = angle
        prev_d = curr_d

    return max_angle > tol * math.pi


# ===========================================================================
# Critical-plane search (normal stress amplitude maximisation)
# ===========================================================================

_PLANE_NORMALS: list[list[float]] = []


def _build_plane_normals() -> list[list[float]]:
    """
    18 candidate plane normals distributed on the upper hemisphere.
    6 axis-aligned + 12 face-diagonal directions.
    """
    s = math.sqrt(0.5)
    normals = [
        [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
        [s, s, 0.0], [s, -s, 0.0], [s, 0.0, s],
        [s, 0.0, -s], [0.0, s, s], [0.0, s, -s],
    ]
    t = math.sqrt(1.0 / 3.0)
    normals += [
        [t, t, t], [t, t, -t], [t, -t, t], [t, -t, -t],
        [-t, t, t], [-t, t, -t], [-t, -t, t], [-t, -t, -t],
        [s, s * 0.5, s * 0.5],
    ]
    return normals


_PLANE_NORMALS = _build_plane_normals()


def _critical_plane_amplitude(history: list[list[float]]) -> tuple[float, float]:
    """
    Find the critical plane: the plane that maximises the normal-stress amplitude.

    Returns (sigma_a_max, sigma_m_critical).
    """
    best_amp = 0.0
    best_mean = 0.0

    for n in _PLANE_NORMALS:
        normals_series = [_normal_stress_on_plane(s, n) for s in history]
        sigma_max_p = max(normals_series)
        sigma_min_p = min(normals_series)
        amp = (sigma_max_p - sigma_min_p) / 2.0
        mean = (sigma_max_p + sigma_min_p) / 2.0
        if amp > best_amp:
            best_amp = amp
            best_mean = mean

    return best_amp, best_mean


# ===========================================================================
# Per-node damage accumulation
# ===========================================================================

def _compute_node_damage(
    node_record: dict,
    material: dict,
    options: dict,
) -> dict:
    """
    Compute Palmgren-Miner cumulative damage for a single node.

    Returns dict with keys: damage, life, proportional_flag, warnings.
    """
    Su = material["Su"]
    Se = material.get("Se", Su / 2.0)
    Sy = material.get("Sy", 0.9 * Su)
    b = material.get("b", -0.085)
    c = material.get("c", -0.60)
    E = material.get("E", None)
    sf_prime = material.get("sf_prime", 1.5 * Su)
    ef_prime = material.get("ef_prime", 0.59)

    correction = options.get("correction", "goodman")
    damage_param = options.get("damage_param", "von_mises")
    life_curve = options.get("life_curve", "basquin")

    warnings_node: list[str] = []
    prop_flag = "proportional"

    # --- Extract cycles ---
    # Three input modes: "spectrum", "unit_stress"+"load_history", "history"
    if "spectrum" in node_record:
        # Block spectrum: list of {"range", "mean", "cycles"}
        cycles: list[tuple[float, float, float]] = []
        for blk in node_record["spectrum"]:
            rng = float(blk["range"])
            mean_val = float(blk.get("mean", 0.0))
            n_cyc = float(blk["cycles"])
            cycles.append((rng, mean_val, n_cyc))

    elif "unit_stress" in node_record and "load_history" in node_record:
        # Linear superposition: σ(t) = unit_stress * F(t)
        us = node_record["unit_stress"]
        lh = node_record["load_history"]
        history = [[c * f for c in us] for f in lh]
        prop_flag = "non_proportional" if _is_non_proportional(history) else "proportional"
        scalar_series = [_damage_parameter(s, damage_param) for s in history]
        cycles = _rainflow(scalar_series)

    elif "history" in node_record:
        history = node_record["history"]
        prop_flag = "non_proportional" if _is_non_proportional(history) else "proportional"
        scalar_series = [_damage_parameter(s, damage_param) for s in history]
        cycles = _rainflow(scalar_series)

    else:
        return {"damage": 0.0, "life": math.inf, "flag": prop_flag,
                "warnings": ["node has no usable stress data"]}

    if not cycles:
        return {"damage": 0.0, "life": math.inf, "flag": prop_flag, "warnings": []}

    # --- Accumulate damage ---
    damage = 0.0
    for (rng, mean_val, n_applied) in cycles:
        sigma_a = rng / 2.0

        if sigma_a <= 0.0:
            continue

        # Mean-stress correction → equivalent fully-reversed amplitude
        sigma_eq = _mean_stress_correction(sigma_a, mean_val, Su, Se, Sy, correction)

        # Infinite life check
        if sigma_eq < Se:
            continue  # below endurance limit → no damage for this cycle

        # Cycles to failure at this amplitude
        if life_curve == "coffin_manson":
            N_f = _coffin_manson_life(sigma_eq, sf_prime, b, ef_prime, c, E)
        else:
            N_f = _basquin_life(sigma_eq, sf_prime, b)

        if N_f <= 0.0 or math.isinf(N_f):
            if math.isinf(N_f):
                continue
            warnings_node.append(f"Basquin/C-M returned non-positive life at σ_a={sigma_eq:.3e}")
            N_f = 1.0  # avoid division by zero; damage = n

        damage += n_applied / N_f

    # Life estimate from Miner's rule
    if damage > 0.0:
        life = 1.0 / damage
    else:
        life = math.inf

    return {"damage": damage, "life": life, "flag": prop_flag, "warnings": warnings_node}


# ===========================================================================
# Public API
# ===========================================================================

def analyse_fatigue(
    stress_history: list[dict],
    material: dict,
    options: dict | None = None,
) -> dict[str, Any]:
    """
    Fatigue and durability analysis.

    Parameters
    ----------
    stress_history : list of per-node dicts (see module docstring for formats).
    material       : material S-N properties dict.
    options        : analysis options dict (optional).

    Returns
    -------
    Result dict (see module docstring).
    """
    try:
        return _analyse_fatigue_inner(stress_history, material, options or {})
    except Exception as exc:
        return {"ok": False, "reason": f"unexpected error: {exc}",
                "damage_map": {}, "life_map": {}, "min_life_node": None,
                "min_life_cycles": math.inf, "safety_factor": 0.0,
                "infinite_life": False, "multiaxial_flags": {}, "warnings": []}


def _analyse_fatigue_inner(
    stress_history: list[dict],
    material: dict,
    options: dict,
) -> dict[str, Any]:
    # --- Validate material ---
    if not isinstance(material, dict):
        return {"ok": False, "reason": "material must be a dict",
                "damage_map": {}, "life_map": {}, "min_life_node": None,
                "min_life_cycles": math.inf, "safety_factor": 0.0,
                "infinite_life": False, "multiaxial_flags": {}, "warnings": []}

    Su = material.get("Su")
    if Su is None or Su <= 0.0:
        return {"ok": False, "reason": "material.Su (ultimate tensile strength) must be > 0",
                "damage_map": {}, "life_map": {}, "min_life_node": None,
                "min_life_cycles": math.inf, "safety_factor": 0.0,
                "infinite_life": False, "multiaxial_flags": {}, "warnings": []}

    if not stress_history:
        return {"ok": False, "reason": "stress_history is empty",
                "damage_map": {}, "life_map": {}, "min_life_node": None,
                "min_life_cycles": math.inf, "safety_factor": 0.0,
                "infinite_life": False, "multiaxial_flags": {}, "warnings": []}

    Se = material.get("Se", Su / 2.0)
    target_life = float(options.get("target_life", 1e6))
    safety_on = options.get("safety_factor_on", "amplitude")

    all_warnings: list[str] = []
    damage_map: dict[int, float] = {}
    life_map: dict[int, float] = {}
    multiaxial_flags: dict[int, str] = {}

    for record in stress_history:
        node_id = int(record.get("node", 0))
        result = _compute_node_damage(record, material, options)

        all_warnings.extend(
            f"node {node_id}: {w}" for w in result.get("warnings", [])
        )

        damage_map[node_id] = result["damage"]
        life_map[node_id] = result["life"]
        multiaxial_flags[node_id] = result["flag"]

    # --- Minimum life / damage location ---
    if not life_map:
        min_life_node = None
        min_life_cycles = math.inf
    else:
        min_life_node = min(life_map, key=lambda k: life_map[k])
        min_life_cycles = life_map[min_life_node]

    # --- Infinite life check ---
    infinite_life = all(math.isinf(v) for v in life_map.values())

    # --- Safety factor ---
    safety_factor = 0.0
    if infinite_life:
        safety_factor = math.inf
    elif min_life_cycles > 0.0 and not math.isinf(min_life_cycles):
        if safety_on == "life":
            safety_factor = min_life_cycles / target_life
        else:
            # On amplitude: SF = (Se / σ_a_equivalent at critical node)
            # Approximate: SF proportional to life^(-1/b)
            b = material.get("b", -0.085)
            sf_prime = material.get("sf_prime", 1.5 * Su)
            # σ_a from Basquin at target_life:
            sigma_at_target = sf_prime * (2.0 * target_life) ** b
            sigma_at_min = sf_prime * (2.0 * max(min_life_cycles, 0.5)) ** b
            if sigma_at_min > 0.0:
                safety_factor = sigma_at_target / sigma_at_min
            else:
                safety_factor = math.inf

    return {
        "ok": True,
        "damage_map": damage_map,
        "life_map": life_map,
        "min_life_node": min_life_node,
        "min_life_cycles": min_life_cycles,
        "safety_factor": safety_factor,
        "infinite_life": infinite_life,
        "multiaxial_flags": multiaxial_flags,
        "warnings": all_warnings,
    }


# ===========================================================================
# LLM tool registration
# ===========================================================================

_fem_fatigue_spec = ToolSpec(
    name="fem_fatigue",
    description=(
        "Fatigue and durability analysis from FEM stress results. "
        "Given per-node stress histories (or load spectrum + unit-load result), "
        "performs rainflow cycle counting (ASTM E1049), Palmgren-Miner cumulative "
        "damage, mean-stress corrections (Goodman/Gerber/SWT), Basquin or "
        "Coffin-Manson life curves, critical-plane analysis, and multiaxial "
        "proportionality flagging.  Returns a damage map, life map, minimum-life "
        "node, and safety factor."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "stress_history": {
                "type": "array",
                "description": (
                    "Per-node stress records.  Each entry is one of: "
                    "(a) {node, history: [[s11,s22,s33,s12,s13,s23],...]} — "
                    "full tensor time history; "
                    "(b) {node, unit_stress:[...], load_history:[F,...]} — "
                    "superposition; "
                    "(c) {node, spectrum:[{range,mean,cycles},...]} — block spectrum."
                ),
                "items": {"type": "object"},
            },
            "material": {
                "type": "object",
                "description": "S-N material properties.",
                "properties": {
                    "Su":       {"type": "number", "description": "Ultimate tensile strength [Pa]"},
                    "Sy":       {"type": "number", "description": "Yield strength [Pa]"},
                    "Se":       {"type": "number", "description": "Endurance limit [Pa]"},
                    "b":        {"type": "number", "description": "Basquin exponent (default -0.085)"},
                    "c":        {"type": "number", "description": "Coffin-Manson exponent (default -0.60)"},
                    "E":        {"type": "number", "description": "Young's modulus [Pa]"},
                    "sf_prime": {"type": "number", "description": "Fatigue strength coeff σ'_f [Pa]"},
                    "ef_prime": {"type": "number", "description": "Fatigue ductility coeff ε'_f"},
                },
                "required": ["Su"],
            },
            "options": {
                "type": "object",
                "description": "Analysis options.",
                "properties": {
                    "correction":       {"type": "string",
                                         "enum": ["goodman", "gerber", "swt"],
                                         "description": "Mean-stress correction method"},
                    "damage_param":     {"type": "string",
                                         "enum": ["von_mises", "max_principal"],
                                         "description": "Scalar damage parameter"},
                    "life_curve":       {"type": "string",
                                         "enum": ["basquin", "coffin_manson"],
                                         "description": "S-N or ε-N curve"},
                    "target_life":      {"type": "number",
                                         "description": "Design life [cycles]", "default": 1e6},
                    "safety_factor_on": {"type": "string",
                                         "enum": ["amplitude", "life"],
                                         "description": "Basis for safety factor"},
                },
            },
        },
        "required": ["stress_history", "material"],
    },
)


@register(_fem_fatigue_spec)
async def run_fem_fatigue(ctx: ProjectCtx, args: bytes) -> str:
    import json
    try:
        a = json.loads(args)
    except Exception as exc:
        return err_payload(f"invalid args: {exc}", "BAD_ARGS")

    stress_history = a.get("stress_history")
    material = a.get("material")
    options = a.get("options", {})

    if not stress_history:
        return err_payload("stress_history is required", "BAD_ARGS")
    if not material:
        return err_payload("material is required", "BAD_ARGS")

    result = analyse_fatigue(
        stress_history=stress_history,
        material=material,
        options=options,
    )
    return json.dumps(result)
