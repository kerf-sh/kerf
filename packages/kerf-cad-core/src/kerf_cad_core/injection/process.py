"""
kerf_cad_core.injection.process — pure-Python plastic injection-moulding
process design calculations.

Distinct from ``kerf_cad_core.casting`` (metal sand/investment casting).

Implements ten public functions:

  clamp_tonnage(projected_area_m2, cavity_pressure_Pa, n_cavities)
      Required clamping force from projected area × cavity pressure.

  shot_volume_weight(part_volume_m3, runner_volume_m3, n_cavities, polymer)
      Shot volume and weight vs machine capacity check.

  gate_runner_sizing(flow_rate_m3s, wall_thickness_m, polymer)
      Gate land thickness, gate width, primary-runner diameter from
      volumetric flow-rate and part wall thickness.

  cooling_time(wall_thickness_m, melt_temp_C, mold_temp_C, ejection_temp_C,
               polymer)
      Plate-cooling equation:
          t_c = (s²/(π²·α)) · ln((8/π²) · (T_m - T_w)/(T_e - T_w))
      where s = half wall thickness, α = thermal diffusivity of polymer.

  flow_length_feasibility(flow_length_m, wall_thickness_m, polymer)
      Flow-length / wall-thickness (L/t) ratio vs polymer limit.
      Flags thin-wall-flow risk.

  shrinkage_sink_estimate(part_dim_m, wall_thickness_m, polymer)
      Linear shrinkage and sink-mark depth estimate.

  cycle_time_breakdown(cooling_time_s, fill_time_s, pack_hold_time_s,
                       mold_open_close_s, ejection_time_s)
      Total cycle time and each phase fraction.

  cavities_from_tonnage(machine_tonnage_kN, projected_area_per_cavity_m2,
                        cavity_pressure_Pa, safety_factor)
      Maximum number of cavities from available clamping force.

  draft_ejection_force(projected_area_m2, wall_thickness_m, L_draw_m,
                       polymer, surface_finish)
      Draft angle recommendation and estimated ejection force.

  polymer_properties(polymer)
      Return the built-in property record for the named polymer.

All functions return plain dicts:
    success → {"ok": True, ...fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise; exceedance conditions are recorded in the
``"warnings"`` list of the returned dict (always present on ok=True).

Units
-----
  lengths       — metres (m)
  area          — m²
  volume        — m³
  pressure      — Pascals (Pa)
  temperature   — °C
  time          — seconds (s)
  force         — kN (clamp tonnage output), N (ejection force)
  density       — kg/m³
  thermal diff. — m²/s

Polymer property table
----------------------
Supported polymers: PP, ABS, PC, PA (nylon-6/6), POM (acetal).

References
----------
Rosato, D.V. & Rosato, M.G. "Injection Moulding Handbook", 3rd ed.
Brydson, J.A. "Plastics Materials", 7th ed.
Menges, G. et al. "How to Make Injection Molds", 3rd ed.
Isayev, A.I. (ed.) "Injection and Compression Moulding Fundamentals".

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guard_positive(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v <= 0:
        return f"{name} must be > 0, got {v}"
    return None


def _guard_nonneg(name: str, value: Any) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite, got {v}"
    if v < 0:
        return f"{name} must be >= 0, got {v}"
    return None


def _err(reason: str) -> dict:
    return {"ok": False, "reason": reason}


def _ok(d: dict, warnings: list | None = None) -> dict:
    d["ok"] = True
    d["warnings"] = warnings if warnings is not None else []
    return d


# ---------------------------------------------------------------------------
# Polymer property table
# ---------------------------------------------------------------------------
# Keys:
#   melt_temp_C       — recommended melt temperature (°C)
#   mold_temp_C       — recommended mould temperature (°C)
#   ejection_temp_C   — safe demoulding temperature (°C)
#   shrinkage_pct     — linear mould shrinkage (%)  [typical midpoint]
#   alpha_m2s         — thermal diffusivity (m²/s)
#   density_kg_m3     — melt/solid density (kg/m³, solid at room temperature)
#   flow_length_limit — maximum flow-length / wall-thickness ratio (L/t)
#   mu_friction       — typical part-mould friction coefficient (for ejection)
#   cavity_pressure_typical_Pa — typical peak cavity pressure (Pa)

_POLYMER_TABLE: dict[str, dict[str, float]] = {
    "PP": {
        "melt_temp_C": 230.0,
        "mold_temp_C": 40.0,
        "ejection_temp_C": 90.0,
        "shrinkage_pct": 1.5,        # 1.0–2.0 %
        "alpha_m2s": 1.0e-7,         # typical for PP
        "density_kg_m3": 905.0,
        "flow_length_limit": 280.0,  # L/t (unitless)
        "mu_friction": 0.35,
        "cavity_pressure_typical_Pa": 35e6,
    },
    "ABS": {
        "melt_temp_C": 240.0,
        "mold_temp_C": 60.0,
        "ejection_temp_C": 80.0,
        "shrinkage_pct": 0.5,        # 0.4–0.7 %
        "alpha_m2s": 1.1e-7,
        "density_kg_m3": 1050.0,
        "flow_length_limit": 220.0,
        "mu_friction": 0.40,
        "cavity_pressure_typical_Pa": 40e6,
    },
    "PC": {
        "melt_temp_C": 295.0,
        "mold_temp_C": 85.0,
        "ejection_temp_C": 125.0,
        "shrinkage_pct": 0.6,        # 0.5–0.7 %
        "alpha_m2s": 1.2e-7,
        "density_kg_m3": 1200.0,
        "flow_length_limit": 150.0,
        "mu_friction": 0.38,
        "cavity_pressure_typical_Pa": 55e6,
    },
    "PA": {
        "melt_temp_C": 270.0,
        "mold_temp_C": 80.0,
        "ejection_temp_C": 100.0,
        "shrinkage_pct": 1.6,        # nylon-6/6, 1.2–2.0 %
        "alpha_m2s": 1.3e-7,
        "density_kg_m3": 1140.0,
        "flow_length_limit": 260.0,
        "mu_friction": 0.30,
        "cavity_pressure_typical_Pa": 45e6,
    },
    "POM": {
        "melt_temp_C": 215.0,
        "mold_temp_C": 90.0,
        "ejection_temp_C": 120.0,
        "shrinkage_pct": 2.0,        # acetal/Delrin, 1.5–2.5 %
        "alpha_m2s": 9.0e-8,
        "density_kg_m3": 1420.0,
        "flow_length_limit": 230.0,
        "mu_friction": 0.25,
        "cavity_pressure_typical_Pa": 50e6,
    },
}

# Typical machine capacity parameters (for shot-weight check)
_MACHINE_SHOT_CAPACITY_kg = 5.0   # conservative upper bound used as default

# Recommended draft angles (degrees) by surface finish
_DRAFT_ANGLES: dict[str, float] = {
    "polished": 0.5,
    "standard": 1.0,
    "textured": 3.0,
}

# Minimum recommended draft angle regardless of finish
_DRAFT_MIN_DEG = 0.5


def _get_polymer(polymer: str) -> dict | None:
    return _POLYMER_TABLE.get(str(polymer).upper().strip())


# ---------------------------------------------------------------------------
# 1. polymer_properties
# ---------------------------------------------------------------------------

def polymer_properties(polymer: str) -> dict:
    """
    Return the built-in property record for a named polymer.

    Parameters
    ----------
    polymer : str
        One of: 'PP', 'ABS', 'PC', 'PA', 'POM' (case-insensitive).

    Returns
    -------
    dict  ok=True with all property fields, or ok=False if unknown.
    """
    props = _get_polymer(polymer)
    if props is None:
        valid = list(_POLYMER_TABLE.keys())
        return _err(
            f"Unknown polymer {polymer!r}. Supported: {valid}."
        )
    return _ok({
        "polymer": str(polymer).upper().strip(),
        **props,
    })


# ---------------------------------------------------------------------------
# 2. clamp_tonnage
# ---------------------------------------------------------------------------

def clamp_tonnage(
    projected_area_m2: float,
    cavity_pressure_Pa: float,
    n_cavities: int = 1,
    *,
    safety_factor: float = 1.1,
) -> dict:
    """
    Required clamping force from projected area × cavity pressure.

    The clamping force must exceed the separating force acting on the
    parting line:

        F_clamp = n_cavities × A_proj × P_cavity × safety_factor

    Parameters
    ----------
    projected_area_m2 : float
        Projected area of one cavity in the parting-line plane (m²).
        Must be > 0.
    cavity_pressure_Pa : float
        Peak cavity pressure (Pa).  For typical injection moulding this
        is 30–80 MPa depending on polymer and part geometry.  Must be > 0.
    n_cavities : int
        Number of cavities in the mould (default 1).  Must be >= 1.
    safety_factor : float
        Clamping safety factor (default 1.1).  Values 1.0–1.25 are normal.

    Returns
    -------
    dict
        ok                  : True
        clamp_force_kN      : required clamping force (kN)
        separating_force_kN : separating force without safety factor (kN)
        n_cavities          : cavities used
        projected_area_m2   : per-cavity projected area (m²)
        cavity_pressure_Pa  : cavity pressure used (Pa)
        safety_factor       : safety factor applied
        warnings            : list of warning strings

    Flags
    -----
    'over-tonnage'  — if clamp_force_kN > 50 000 kN (very large press)
    """
    warnings: list[str] = []

    err = _guard_positive("projected_area_m2", projected_area_m2)
    if err:
        return _err(err)
    err = _guard_positive("cavity_pressure_Pa", cavity_pressure_Pa)
    if err:
        return _err(err)
    try:
        nc = int(n_cavities)
    except (TypeError, ValueError):
        return _err(f"n_cavities must be an integer, got {n_cavities!r}")
    if nc < 1:
        return _err(f"n_cavities must be >= 1, got {nc}")
    err = _guard_positive("safety_factor", safety_factor)
    if err:
        return _err(err)

    A = float(projected_area_m2)
    P = float(cavity_pressure_Pa)
    sf = float(safety_factor)

    F_sep_N = nc * A * P
    F_clamp_N = F_sep_N * sf

    F_sep_kN = F_sep_N / 1e3
    F_clamp_kN = F_clamp_N / 1e3

    if F_clamp_kN > 50_000.0:
        warnings.append(
            f"over-tonnage: required clamping force {F_clamp_kN:.0f} kN exceeds "
            "50 000 kN (very large press); verify cavity pressure and area."
        )

    return _ok({
        "clamp_force_kN": F_clamp_kN,
        "separating_force_kN": F_sep_kN,
        "n_cavities": nc,
        "projected_area_m2": A,
        "cavity_pressure_Pa": P,
        "safety_factor": sf,
    }, warnings)


# ---------------------------------------------------------------------------
# 3. shot_volume_weight
# ---------------------------------------------------------------------------

def shot_volume_weight(
    part_volume_m3: float,
    runner_volume_m3: float,
    n_cavities: int,
    polymer: str,
    *,
    machine_shot_capacity_kg: float = _MACHINE_SHOT_CAPACITY_kg,
) -> dict:
    """
    Shot volume and weight vs machine capacity check.

    Total shot volume = n_cavities × part_volume + runner_volume.
    Shot weight = total_shot_volume × polymer_density.

    Parameters
    ----------
    part_volume_m3 : float
        Volume of one moulded part (m³).  Must be > 0.
    runner_volume_m3 : float
        Combined runner and sprue volume per shot (m³).  Must be >= 0.
    n_cavities : int
        Number of cavities.  Must be >= 1.
    polymer : str
        Polymer name: PP/ABS/PC/PA/POM.
    machine_shot_capacity_kg : float
        Machine maximum shot capacity (kg).  Default 5.0 kg (medium press).
        Must be > 0.

    Returns
    -------
    dict
        ok                        : True
        shot_volume_m3            : total shot volume (m³)
        shot_weight_kg            : shot weight (kg)
        part_weight_kg            : weight of one part (kg)
        runner_weight_kg          : runner/sprue weight (kg)
        machine_shot_capacity_kg  : capacity used
        within_capacity           : True if shot_weight <= capacity
        utilisation_pct           : (shot_weight / capacity) × 100
        warnings                  : list
    """
    warnings: list[str] = []

    err = _guard_positive("part_volume_m3", part_volume_m3)
    if err:
        return _err(err)
    err = _guard_nonneg("runner_volume_m3", runner_volume_m3)
    if err:
        return _err(err)
    try:
        nc = int(n_cavities)
    except (TypeError, ValueError):
        return _err(f"n_cavities must be an integer, got {n_cavities!r}")
    if nc < 1:
        return _err(f"n_cavities must be >= 1, got {nc}")
    err = _guard_positive("machine_shot_capacity_kg", machine_shot_capacity_kg)
    if err:
        return _err(err)

    props = _get_polymer(polymer)
    if props is None:
        return _err(f"Unknown polymer {polymer!r}. Supported: {list(_POLYMER_TABLE.keys())}.")

    rho = props["density_kg_m3"]
    Vp = float(part_volume_m3)
    Vr = float(runner_volume_m3)
    cap = float(machine_shot_capacity_kg)

    shot_vol = nc * Vp + Vr
    shot_wt = shot_vol * rho
    part_wt = Vp * rho
    runner_wt = Vr * rho
    within = shot_wt <= cap
    util_pct = (shot_wt / cap) * 100.0

    if not within:
        warnings.append(
            f"short-shot risk: shot weight {shot_wt*1e3:.1f} g exceeds machine "
            f"capacity {cap*1e3:.1f} g; reduce cavities or use larger press."
        )
    if util_pct > 80.0:
        warnings.append(
            f"shot utilisation {util_pct:.1f}% > 80%; consider a larger machine "
            "to allow cushion."
        )

    return _ok({
        "shot_volume_m3": shot_vol,
        "shot_weight_kg": shot_wt,
        "part_weight_kg": part_wt,
        "runner_weight_kg": runner_wt,
        "machine_shot_capacity_kg": cap,
        "within_capacity": within,
        "utilisation_pct": util_pct,
        "polymer": str(polymer).upper().strip(),
        "density_kg_m3": rho,
    }, warnings)


# ---------------------------------------------------------------------------
# 4. gate_runner_sizing
# ---------------------------------------------------------------------------

def gate_runner_sizing(
    flow_rate_m3s: float,
    wall_thickness_m: float,
    polymer: str,
    *,
    gate_velocity_limit_ms: float = 0.5,
) -> dict:
    """
    Gate land thickness, gate width, and primary-runner diameter sizing.

    Gate land thickness is typically 50–75% of the nominal wall thickness.
    Gate width is sized so that the gate velocity does not exceed
    ``gate_velocity_limit_ms`` (default 0.5 m/s, a conservative limit to
    avoid jetting and gate blush).

    Runner diameter is sized using a simplified Hagen-Poiseuille approach:
    the runner should be at least 1.5× the gate thickness to avoid
    premature freeze-off.

    Parameters
    ----------
    flow_rate_m3s : float
        Volumetric injection flow rate (m³/s).  Must be > 0.
    wall_thickness_m : float
        Nominal part wall thickness at the gate location (m).  Must be > 0.
    polymer : str
        Polymer name: PP/ABS/PC/PA/POM.
    gate_velocity_limit_ms : float
        Maximum gate velocity (m/s, default 0.5).  Must be > 0.

    Returns
    -------
    dict
        ok                   : True
        gate_thickness_m     : recommended gate land thickness (m)
        gate_width_m         : minimum gate width for velocity limit (m)
        gate_area_m2         : gate cross-section area (m²)
        gate_velocity_ms     : gate velocity at given flow rate (m/s)
        runner_diameter_m    : recommended primary runner diameter (m)
        warnings             : list
    """
    warnings: list[str] = []

    err = _guard_positive("flow_rate_m3s", flow_rate_m3s)
    if err:
        return _err(err)
    err = _guard_positive("wall_thickness_m", wall_thickness_m)
    if err:
        return _err(err)
    err = _guard_positive("gate_velocity_limit_ms", gate_velocity_limit_ms)
    if err:
        return _err(err)

    props = _get_polymer(polymer)
    if props is None:
        return _err(f"Unknown polymer {polymer!r}. Supported: {list(_POLYMER_TABLE.keys())}.")

    Q = float(flow_rate_m3s)
    t_wall = float(wall_thickness_m)
    v_lim = float(gate_velocity_limit_ms)

    # Gate land thickness: 60% of wall thickness (midpoint of 50–75%)
    t_gate = 0.60 * t_wall

    # Gate width from velocity limit: A_gate = Q / v_lim, width = A/thickness
    A_gate = Q / v_lim
    w_gate = A_gate / t_gate

    # Actual gate velocity
    v_gate = Q / (t_gate * w_gate)  # should equal v_lim

    # Runner diameter: at least 1.5× gate thickness, rounded up to practical size
    d_runner = max(1.5 * t_gate, 4e-3)  # minimum 4 mm practical

    # Wall thickness warnings
    if t_wall < 0.8e-3:
        warnings.append(
            "thin-wall-flow risk: wall thickness < 0.8 mm; fill may be "
            "incomplete at typical injection conditions."
        )
    if t_wall > 6e-3:
        warnings.append(
            "wall thickness > 6 mm; consider coring to reduce sink marks "
            "and cycle time."
        )

    return _ok({
        "gate_thickness_m": t_gate,
        "gate_width_m": w_gate,
        "gate_area_m2": A_gate,
        "gate_velocity_ms": v_gate,
        "runner_diameter_m": d_runner,
        "wall_thickness_m": t_wall,
        "flow_rate_m3s": Q,
        "polymer": str(polymer).upper().strip(),
    }, warnings)


# ---------------------------------------------------------------------------
# 5. cooling_time
# ---------------------------------------------------------------------------

def cooling_time(
    wall_thickness_m: float,
    melt_temp_C: float,
    mold_temp_C: float,
    ejection_temp_C: float,
    polymer: str,
) -> dict:
    """
    Plate-cooling time for a flat-plate injection-moulded part.

    Uses the analytical solution for one-dimensional transient heat
    conduction in a semi-infinite slab (first-term approximation):

        t_c = (s² / (π² · α)) · ln((8/π²) · (T_m - T_w) / (T_e - T_w))

    where:
        s   = half wall thickness  (= wall_thickness_m / 2)
        α   = thermal diffusivity of polymer (m²/s)
        T_m = melt temperature (°C)
        T_w = mould wall temperature (°C)
        T_e = demoulding / ejection temperature (°C)

    Parameters
    ----------
    wall_thickness_m : float
        Part wall thickness (m).  Must be > 0.
    melt_temp_C : float
        Melt injection temperature (°C).  Must be > mold_temp_C.
    mold_temp_C : float
        Mould wall coolant temperature (°C).
    ejection_temp_C : float
        Part surface temperature at ejection (°C).  Must be:
        mold_temp_C < ejection_temp_C < melt_temp_C.
    polymer : str
        Polymer name: PP/ABS/PC/PA/POM.  Provides α.
        If not provided in args, falls back to polymer table defaults
        for temperature validation.

    Returns
    -------
    dict
        ok                : True
        cooling_time_s    : cooling time (s)
        half_thickness_m  : s = wall/2 (m)
        alpha_m2s         : thermal diffusivity used (m²/s)
        T_melt_C          : melt temperature (°C)
        T_mold_C          : mould temperature (°C)
        T_eject_C         : ejection temperature (°C)
        warnings          : list
    """
    warnings: list[str] = []

    err = _guard_positive("wall_thickness_m", wall_thickness_m)
    if err:
        return _err(err)

    props = _get_polymer(polymer)
    if props is None:
        return _err(f"Unknown polymer {polymer!r}. Supported: {list(_POLYMER_TABLE.keys())}.")

    try:
        T_m = float(melt_temp_C)
        T_w = float(mold_temp_C)
        T_e = float(ejection_temp_C)
    except (TypeError, ValueError) as exc:
        return _err(f"temperature inputs must be numbers: {exc}")

    if not (T_w < T_e < T_m):
        return _err(
            f"Temperatures must satisfy mold_temp_C ({T_w}) < ejection_temp_C "
            f"({T_e}) < melt_temp_C ({T_m})."
        )

    alpha = props["alpha_m2s"]
    s = float(wall_thickness_m) / 2.0  # half thickness

    # ln argument must be > 0
    num = T_m - T_w
    den = T_e - T_w
    if den <= 0:
        return _err("ejection_temp_C must be > mold_temp_C.")

    ln_arg = (8.0 / (math.pi ** 2)) * (num / den)
    if ln_arg <= 0:
        return _err("Logarithm argument <= 0; check temperature inputs.")

    t_c = (s ** 2 / (math.pi ** 2 * alpha)) * math.log(ln_arg)

    if t_c < 0:
        return _err(
            "Calculated cooling time is negative; ejection_temp_C may be "
            "too close to or above melt_temp_C."
        )

    if float(wall_thickness_m) < 0.8e-3:
        warnings.append(
            "thin-wall-flow risk: wall < 0.8 mm; cooling time may be "
            "underestimated due to thin-wall flow effects."
        )

    # Recommend polymer mould temperature
    rec_mold = props["mold_temp_C"]
    if abs(T_w - rec_mold) > 30.0:
        warnings.append(
            f"mould temperature {T_w:.0f} °C deviates >30 °C from "
            f"recommended {rec_mold:.0f} °C for {polymer.upper()}."
        )

    return _ok({
        "cooling_time_s": t_c,
        "half_thickness_m": s,
        "alpha_m2s": alpha,
        "T_melt_C": T_m,
        "T_mold_C": T_w,
        "T_eject_C": T_e,
        "polymer": str(polymer).upper().strip(),
    }, warnings)


# ---------------------------------------------------------------------------
# 6. flow_length_feasibility
# ---------------------------------------------------------------------------

def flow_length_feasibility(
    flow_length_m: float,
    wall_thickness_m: float,
    polymer: str,
) -> dict:
    """
    Flow-length / wall-thickness (L/t) ratio vs polymer limit.

    A flow-length ratio exceeding the polymer's empirical limit suggests
    that the part may not fill completely at standard injection conditions.

    Parameters
    ----------
    flow_length_m : float
        Longest flow-path from gate to end of fill (m).  Must be > 0.
    wall_thickness_m : float
        Nominal wall thickness along the flow path (m).  Must be > 0.
    polymer : str
        Polymer name: PP/ABS/PC/PA/POM.

    Returns
    -------
    dict
        ok                 : True
        flow_length_ratio  : L / t (dimensionless)
        limit              : polymer L/t limit
        feasible           : True if ratio <= limit
        margin_pct         : (limit - ratio) / limit × 100
        warnings           : list
    """
    warnings: list[str] = []

    err = _guard_positive("flow_length_m", flow_length_m)
    if err:
        return _err(err)
    err = _guard_positive("wall_thickness_m", wall_thickness_m)
    if err:
        return _err(err)

    props = _get_polymer(polymer)
    if props is None:
        return _err(f"Unknown polymer {polymer!r}. Supported: {list(_POLYMER_TABLE.keys())}.")

    L = float(flow_length_m)
    t = float(wall_thickness_m)
    limit = props["flow_length_limit"]

    ratio = L / t
    feasible = ratio <= limit
    margin_pct = (limit - ratio) / limit * 100.0

    if not feasible:
        warnings.append(
            f"thin-wall-flow risk: L/t ratio {ratio:.1f} exceeds "
            f"{polymer.upper()} limit of {limit:.0f}; "
            "consider increasing wall thickness, adding gates, or using a "
            "higher-flow-rate grade."
        )
    elif margin_pct < 10.0:
        warnings.append(
            f"L/t margin only {margin_pct:.1f}%; close to polymer limit; "
            "injection speed and melt temperature are critical."
        )

    if t < 0.8e-3:
        warnings.append("thin-wall-flow risk: wall thickness < 0.8 mm.")

    return _ok({
        "flow_length_ratio": ratio,
        "flow_length_m": L,
        "wall_thickness_m": t,
        "limit": limit,
        "feasible": feasible,
        "margin_pct": margin_pct,
        "polymer": str(polymer).upper().strip(),
    }, warnings)


# ---------------------------------------------------------------------------
# 7. shrinkage_sink_estimate
# ---------------------------------------------------------------------------

def shrinkage_sink_estimate(
    part_dim_m: float,
    wall_thickness_m: float,
    polymer: str,
) -> dict:
    """
    Linear shrinkage and sink-mark depth estimate.

    Linear shrinkage:
        ΔL = part_dim_m × (shrinkage_pct / 100)

    Sink-mark depth estimate (empirical rule of thumb):
        depth ≈ 0.006 × wall_thickness_m   for wall > 4 mm
        depth ≈ 0.003 × wall_thickness_m   for wall <= 4 mm
    (Rosato, "Injection Moulding Handbook", 3rd ed.)

    Mould cavity dimension (to compensate for shrinkage):
        mould_dim = part_dim_m / (1 - shrinkage_pct/100)

    Parameters
    ----------
    part_dim_m : float
        Nominal finished-part dimension to be checked (m).  Must be > 0.
    wall_thickness_m : float
        Wall thickness at or near the relevant feature (m).  Must be > 0.
    polymer : str
        Polymer name: PP/ABS/PC/PA/POM.

    Returns
    -------
    dict
        ok                  : True
        shrinkage_pct       : linear shrinkage percentage (%)
        linear_shrinkage_m  : shrinkage for the given dimension (m)
        mould_dim_m         : required mould dimension to give part_dim_m (m)
        sink_depth_m        : estimated maximum sink-mark depth (m)
        warnings            : list
    """
    warnings: list[str] = []

    err = _guard_positive("part_dim_m", part_dim_m)
    if err:
        return _err(err)
    err = _guard_positive("wall_thickness_m", wall_thickness_m)
    if err:
        return _err(err)

    props = _get_polymer(polymer)
    if props is None:
        return _err(f"Unknown polymer {polymer!r}. Supported: {list(_POLYMER_TABLE.keys())}.")

    shrink_pct = props["shrinkage_pct"]
    L = float(part_dim_m)
    t = float(wall_thickness_m)

    delta_L = L * (shrink_pct / 100.0)
    mould_dim = L / (1.0 - shrink_pct / 100.0)

    # Sink-mark depth (empirical)
    sink_factor = 0.006 if t > 4e-3 else 0.003
    sink_depth = sink_factor * t

    if t > 4e-3:
        warnings.append(
            f"wall thickness {t*1e3:.1f} mm > 4 mm; sink marks likely; "
            "consider coring or reducing wall."
        )
    if shrink_pct > 1.5:
        warnings.append(
            f"high shrinkage polymer ({shrink_pct}%); dimensional accuracy "
            "requires careful mould temperature control."
        )

    return _ok({
        "shrinkage_pct": shrink_pct,
        "linear_shrinkage_m": delta_L,
        "mould_dim_m": mould_dim,
        "part_dim_m": L,
        "wall_thickness_m": t,
        "sink_depth_m": sink_depth,
        "polymer": str(polymer).upper().strip(),
    }, warnings)


# ---------------------------------------------------------------------------
# 8. cycle_time_breakdown
# ---------------------------------------------------------------------------

def cycle_time_breakdown(
    cooling_time_s: float,
    fill_time_s: float,
    pack_hold_time_s: float,
    mold_open_close_s: float,
    ejection_time_s: float,
) -> dict:
    """
    Total injection-moulding cycle time and phase fractions.

    Cycle = fill + pack/hold + cooling + mould-open/close + ejection.
    In practice cooling dominates at 50–80% of total cycle.

    Parameters
    ----------
    cooling_time_s : float
        Cooling / solidification time (s).  Must be > 0.
    fill_time_s : float
        Injection fill time (s).  Must be > 0.
    pack_hold_time_s : float
        Pack and hold time (s).  Must be >= 0.
    mold_open_close_s : float
        Mould open + close traversal time (s).  Must be >= 0.
    ejection_time_s : float
        Ejection / part-removal time (s).  Must be >= 0.

    Returns
    -------
    dict
        ok                   : True
        total_cycle_s        : total cycle time (s)
        cooling_time_s       : cooling phase (s)
        fill_time_s          : fill phase (s)
        pack_hold_time_s     : pack/hold phase (s)
        mold_open_close_s    : mould open+close phase (s)
        ejection_time_s      : ejection phase (s)
        cooling_fraction_pct : cooling / total × 100
        fill_fraction_pct    : fill / total × 100
        shots_per_hour       : 3600 / total_cycle_s
        warnings             : list
    """
    warnings: list[str] = []

    err = _guard_positive("cooling_time_s", cooling_time_s)
    if err:
        return _err(err)
    err = _guard_positive("fill_time_s", fill_time_s)
    if err:
        return _err(err)
    for name, val in [
        ("pack_hold_time_s", pack_hold_time_s),
        ("mold_open_close_s", mold_open_close_s),
        ("ejection_time_s", ejection_time_s),
    ]:
        e = _guard_nonneg(name, val)
        if e:
            return _err(e)

    tc = float(cooling_time_s)
    tf = float(fill_time_s)
    tp = float(pack_hold_time_s)
    tm = float(mold_open_close_s)
    te = float(ejection_time_s)

    total = tc + tf + tp + tm + te
    cool_frac = tc / total * 100.0
    fill_frac = tf / total * 100.0
    sph = 3600.0 / total

    if cool_frac < 30.0:
        warnings.append(
            f"cooling fraction {cool_frac:.1f}% < 30%; verify cooling_time_s "
            "is not underestimated."
        )

    return _ok({
        "total_cycle_s": total,
        "cooling_time_s": tc,
        "fill_time_s": tf,
        "pack_hold_time_s": tp,
        "mold_open_close_s": tm,
        "ejection_time_s": te,
        "cooling_fraction_pct": cool_frac,
        "fill_fraction_pct": fill_frac,
        "shots_per_hour": sph,
    }, warnings)


# ---------------------------------------------------------------------------
# 9. cavities_from_tonnage
# ---------------------------------------------------------------------------

def cavities_from_tonnage(
    machine_tonnage_kN: float,
    projected_area_per_cavity_m2: float,
    cavity_pressure_Pa: float,
    safety_factor: float = 1.1,
) -> dict:
    """
    Maximum number of cavities from available clamping force.

    Rearranges the clamping-force equation to find:

        n_max = floor(F_machine / (A_proj × P_cavity × safety_factor))

    Parameters
    ----------
    machine_tonnage_kN : float
        Available machine clamping force (kN).  Must be > 0.
    projected_area_per_cavity_m2 : float
        Projected area of one cavity (m²).  Must be > 0.
    cavity_pressure_Pa : float
        Peak cavity pressure (Pa).  Must be > 0.
    safety_factor : float
        Clamping safety factor (default 1.1).  Must be > 0.

    Returns
    -------
    dict
        ok                           : True
        max_cavities                 : maximum integer cavities
        separating_force_per_cavity_kN : F per cavity without SF (kN)
        machine_tonnage_kN           : press size used (kN)
        warnings                     : list
    """
    warnings: list[str] = []

    err = _guard_positive("machine_tonnage_kN", machine_tonnage_kN)
    if err:
        return _err(err)
    err = _guard_positive("projected_area_per_cavity_m2", projected_area_per_cavity_m2)
    if err:
        return _err(err)
    err = _guard_positive("cavity_pressure_Pa", cavity_pressure_Pa)
    if err:
        return _err(err)
    err = _guard_positive("safety_factor", safety_factor)
    if err:
        return _err(err)

    F_machine_N = float(machine_tonnage_kN) * 1e3
    A = float(projected_area_per_cavity_m2)
    P = float(cavity_pressure_Pa)
    sf = float(safety_factor)

    F_per_cavity_N = A * P * sf
    n_max = int(F_machine_N / F_per_cavity_N)
    if n_max < 1:
        n_max = 0
        warnings.append(
            "over-tonnage: machine clamping force insufficient for even one "
            "cavity at the given cavity pressure and area; use a larger press."
        )

    F_per_cavity_kN = A * P / 1e3  # without safety factor

    return _ok({
        "max_cavities": n_max,
        "separating_force_per_cavity_kN": F_per_cavity_kN,
        "machine_tonnage_kN": float(machine_tonnage_kN),
        "projected_area_per_cavity_m2": A,
        "cavity_pressure_Pa": P,
        "safety_factor": sf,
    }, warnings)


# ---------------------------------------------------------------------------
# 10. draft_ejection_force
# ---------------------------------------------------------------------------

def draft_ejection_force(
    projected_area_m2: float,
    wall_thickness_m: float,
    L_draw_m: float,
    polymer: str,
    surface_finish: str = "standard",
) -> dict:
    """
    Recommended draft angle and estimated ejection force.

    Draft angle is looked up from a table based on surface finish.
    Ejection force is estimated using:

        F_eject = mu × P_shrink × A_side

    where:
        mu          = coefficient of friction (polymer-specific)
        P_shrink    = shrinkage pressure ≈ shrinkage_pct/100 × E_polymer
                      (simplified: use 10 MPa as a conservative representative
                       shrinkage-induced contact pressure for most polymers)
        A_side      = lateral surface area ≈ perimeter_equiv × L_draw
                      approximated as 4 × √(projected_area) × L_draw
                      (assuming a square footprint)

    Parameters
    ----------
    projected_area_m2 : float
        Projected area in the parting-line plane (m²).  Must be > 0.
    wall_thickness_m : float
        Nominal wall thickness (m).  Must be > 0.
    L_draw_m : float
        Draw depth / pull direction length (m).  Must be > 0.
    polymer : str
        Polymer name: PP/ABS/PC/PA/POM.
    surface_finish : str
        Surface finish: 'polished' / 'standard' (default) / 'textured'.

    Returns
    -------
    dict
        ok                  : True
        draft_angle_deg     : recommended draft angle (degrees)
        ejection_force_N    : estimated ejection force (N)
        mu_friction         : friction coefficient used
        A_side_m2           : estimated lateral surface area (m²)
        warnings            : list
    """
    warnings: list[str] = []

    err = _guard_positive("projected_area_m2", projected_area_m2)
    if err:
        return _err(err)
    err = _guard_positive("wall_thickness_m", wall_thickness_m)
    if err:
        return _err(err)
    err = _guard_positive("L_draw_m", L_draw_m)
    if err:
        return _err(err)

    props = _get_polymer(polymer)
    if props is None:
        return _err(f"Unknown polymer {polymer!r}. Supported: {list(_POLYMER_TABLE.keys())}.")

    fin = str(surface_finish).strip().lower()
    if fin not in _DRAFT_ANGLES:
        valid = list(_DRAFT_ANGLES.keys())
        return _err(f"Unknown surface_finish {surface_finish!r}. Supported: {valid}.")

    draft_deg = _DRAFT_ANGLES[fin]
    mu = props["mu_friction"]
    shrink_pct = props["shrinkage_pct"]

    A = float(projected_area_m2)
    t = float(wall_thickness_m)
    L = float(L_draw_m)

    # Shrinkage contact pressure — conservative 10 MPa representative value
    P_shrink_Pa = 10e6

    # Lateral area: assume square footprint → side = √A, perimeter = 4√A
    side = math.sqrt(A)
    A_side = 4.0 * side * L

    F_eject = mu * P_shrink_Pa * A_side

    if draft_deg < 1.0 and fin == "textured":
        warnings.append(
            "textured surface requires >= 1° draft per 0.025 mm texture depth; "
            "verify draft is sufficient for the specified texture."
        )
    if t < 0.8e-3:
        warnings.append("thin-wall-flow risk: wall < 0.8 mm.")
    if shrink_pct > 1.5:
        warnings.append(
            f"high shrinkage ({shrink_pct}%) increases ejection force; "
            "consider venting and generous draft."
        )

    return _ok({
        "draft_angle_deg": draft_deg,
        "ejection_force_N": F_eject,
        "mu_friction": mu,
        "A_side_m2": A_side,
        "projected_area_m2": A,
        "wall_thickness_m": t,
        "L_draw_m": L,
        "surface_finish": fin,
        "polymer": str(polymer).upper().strip(),
    }, warnings)
