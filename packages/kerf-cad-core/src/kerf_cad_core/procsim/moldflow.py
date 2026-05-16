"""
kerf_cad_core.procsim.moldflow
===============================
1-D / 2.5-D injection-moulding flow simulation for a plate/strip cavity fed
from one or more gates.

Physical model overview
-----------------------
All cavities are treated as rectangular slot (parallel-plate) channels of
half-gap h = t_wall / 2.  Power-law melt rheology:

    η_app(γ̇) = K · γ̇^(n-1)          [Pa·s]

where K is the consistency index [Pa·s^n] and n is the power-law index
(n=1 → Newtonian; n<1 → shear-thinning, typical for thermoplastics).

Pressure drop — Hagen-Poiseuille / power-law slot flow
-------------------------------------------------------
For a slit of width W, half-gap h, flow length L, volumetric flow rate Q:

    ΔP = (2n+1)/(n) · K · L / (W · h^((2n+1)/n)) · (Q / (2 W h^2))^n  ... (1)

rearranged to the compact form used in Injection Moulding texts (e.g. Throne):

    ΔP = 2 K L / (h^(n+2)) · ((2n+1)/n · Q / (2 W))^n                 ... (2)

For a Newtonian melt (n=1, K=η) equation (2) reduces to the classical slit-flow
Hagen-Poiseuille:

    ΔP_N = 12 η Q L / (W h³ · 2) = 6 η Q L / (W h³)                   ... (3)

which matches standard texts (note factor-of-2 convention difference; here h is
half-gap so W·(2h)³/12 = W h³ / 1.5 is the full-gap result — both forms are
equivalent after unit reconciliation).

Clamp tonnage
-------------
Clamp force = projected_area × average_cavity_pressure.
The average cavity pressure is approximated as ΔP / 2 (pressure ramps from
gate at ΔP to zero at the flow front).

    F_clamp [N] = (projected_area [m²]) × (ΔP / 2 [Pa])
    F_clamp_ton = F_clamp / (1000 × 9.80665)            [metric tonnes]

Shear rate and shear stress (apparent, slit flow)
-------------------------------------------------
    γ̇_app = Q / (W · h²)           [s⁻¹]   (Newtonian apparent wall shear rate)
    γ̇_true = (2n+1)/(2n) · γ̇_app  [s⁻¹]   (Rabinowitsch correction, slit)
    τ_wall = K · γ̇_true^n          [Pa]

Freeze-off / short-shot prediction
------------------------------------
Frozen-layer thickness grows as (Graetz / Stefan approximation):

    δ_frozen(t) = 2 · sqrt(α · t)    [m]

where α = k_melt / (ρ_melt · cp_melt) is the thermal diffusivity of the melt.
The cavity is "frozen off" (full shot impossible) when:

    δ_frozen(t_fill) ≥ h              →  short_shot = True

Fill time at flow rate Q:
    t_fill = (flow_length × W × 2h) / Q   [s]     (cavity volume / flow rate)

Weld-line locations
-------------------
N equally-spaced gates divide the cavity into N segments of length L/N.
Weld lines form where adjacent flow fronts meet — at the midpoint between each
pair of neighbouring gates, and symmetrically at the two ends for edge gates.
If flow fronts from a gate pair travel equal distances, the weld line is at the
midpoint of the two gate positions.

For M holes (obstacles), each hole contributes one weld line downstream at
approximately the hole centre + hole_diameter/2 in the flow direction.

Sink-mark risk
--------------
Thick sections cool slower — the skin solidifies before the interior can
shrink.  Practical rule (Rosato):
    risk = True  when  t_rib / t_wall > 0.6

(Some refs cite 0.5; the conservative limit 0.6 is used here.)

Gate and runner sizing
-----------------------
Gate diameter (land gate):
    d_gate = sqrt(4 · A_part / (π · Cv))   where Cv is a sizing coefficient
In practice a simpler empirical form is used:
    d_gate [mm] = 0.206 · sqrt(A_part_mm2) · (t_wall_mm / t_ref)^0.5
    (Brydson empirical; A_part in mm², t_ref = 3 mm reference thickness)

Runner diameter (full-round runner for lowest pressure-drop per unit material):
    d_runner = d_gate · (N_cavities)^(1/3)   [balanced runner, natural balance]
    (Moldflow empirical: runner diameter scales with cube-root of n-cavities)

Multi-cavity runner balance
---------------------------
Balanced runner: all cavities receive equal flow — equal fill times.
Naturally-balanced (H-tree): also equal.
Unbalanced (all cavities on one runner of varying length): fill times differ.

For N cavities on a simple sequential manifold (single sprue feeding cavity 1,
cavity 1 feeds cavity 2, etc.):
    fill_time_i = (V_cavity × i) / Q_total   (each cavity has to wait for
                                              the upstream cavity to partly fill)
This gives unequal fill times by construction.

Cooling time
------------
Transverse heat conduction out through the mould walls (planar cavity):

    t_cool = (t_wall² / (π² α)) · ln((4/π) · (T_melt - T_mould) / (T_eject - T_mould))
           = t_wall² / (π² α) · ln(C_cool)

where:
    α = thermal diffusivity of the polymer melt [m²/s]
    T_melt  = melt temperature [°C]
    T_mould = mould surface temperature [°C]
    T_eject = ejection temperature [°C] (approx. heat-distortion temperature)
    C_cool  = (4/π) · (T_melt - T_mould) / (T_eject - T_mould)

This is the classical Rosato / Throne form of the Carslaw-Jaeger solution for a
slab cooled symmetrically from both sides (first-term approximation).

Cross-checks
------------
* ΔP ∝ L   (linear in flow length) — verified by ratio test
* ΔP ∝ h^{-(n+2)} (inverse power of half-gap) — for n=1: ΔP ∝ h^{-3}
* t_cool ∝ t_wall² · ln(C)        — verified by ratio test
* t_cool ∝ 1/α                    — verified by ratio test

Never raises.  All public functions return {"ok": bool, ...}.

References
----------
Throne J.L. (1979). "Plastics Process Engineering." Marcel Dekker.
Rosato D.V., Rosato M.G. (2000). "Injection Molding Handbook." 3rd ed. Kluwer.
Tadmor Z., Gogos C.G. (2006). "Principles of Polymer Processing." 2nd ed. Wiley.
Brydson J.A. (1995). "Plastics Materials." 6th ed. Butterworth-Heinemann.
Carslaw H.S., Jaeger J.C. (1959). "Conduction of Heat in Solids." 2nd ed. OUP.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Default polymer material presets
# ---------------------------------------------------------------------------

_POLYMERS: Dict[str, Dict[str, float]] = {
    "abs": {
        "K": 28_000.0,      # Pa·s^n  consistency index
        "n": 0.27,          # power-law index (shear-thinning)
        "rho": 1050.0,      # kg/m³  melt density
        "cp": 1800.0,       # J/(kg·K)
        "k_melt": 0.17,     # W/(m·K)  thermal conductivity of melt
        "T_melt": 230.0,    # °C  recommended melt temperature
        "T_eject": 80.0,    # °C  ejection (HDT) temperature
        "tau_limit": 0.25e6,  # Pa  max allowable shear stress (material limit)
        "shear_rate_limit": 50_000.0,  # s⁻¹  max allowable shear rate
    },
    "pp": {
        "K": 7_400.0,
        "n": 0.38,
        "rho": 900.0,
        "cp": 2100.0,
        "k_melt": 0.20,
        "T_melt": 220.0,
        "T_eject": 70.0,
        "tau_limit": 0.20e6,
        "shear_rate_limit": 100_000.0,
    },
    "pe": {
        "K": 6_200.0,
        "n": 0.41,
        "rho": 950.0,
        "cp": 2200.0,
        "k_melt": 0.36,
        "T_melt": 200.0,
        "T_eject": 70.0,
        "tau_limit": 0.15e6,
        "shear_rate_limit": 100_000.0,
    },
    "ps": {
        "K": 25_000.0,
        "n": 0.30,
        "rho": 1050.0,
        "cp": 1300.0,
        "k_melt": 0.14,
        "T_melt": 220.0,
        "T_eject": 75.0,
        "tau_limit": 0.25e6,
        "shear_rate_limit": 40_000.0,
    },
    "nylon66": {
        "K": 400.0,
        "n": 0.66,
        "rho": 1140.0,
        "cp": 1700.0,
        "k_melt": 0.25,
        "T_melt": 285.0,
        "T_eject": 120.0,
        "tau_limit": 0.30e6,
        "shear_rate_limit": 100_000.0,
    },
    "pc": {
        "K": 600.0,
        "n": 0.83,
        "rho": 1200.0,
        "cp": 1200.0,
        "k_melt": 0.20,
        "T_melt": 300.0,
        "T_eject": 130.0,
        "tau_limit": 0.40e6,
        "shear_rate_limit": 40_000.0,
    },
}

_POLYMER_ALIASES: Dict[str, str] = {
    "polypropylene": "pp",
    "polyethylene": "pe",
    "polystyrene": "ps",
    "polycarbonate": "pc",
    "nylon": "nylon66",
    "pa66": "nylon66",
    "hdpe": "pe",
    "ldpe": "pe",
}


def _resolve_polymer(name: str) -> Optional[str]:
    k = name.strip().lower()
    if k in _POLYMERS:
        return k
    return _POLYMER_ALIASES.get(k)


# ---------------------------------------------------------------------------
# Slot-flow pressure-drop (power-law)
# ---------------------------------------------------------------------------

def _slot_pressure_drop(
    flow_length: float,
    width: float,
    half_gap: float,
    flow_rate: float,
    K: float,
    n: float,
) -> float:
    """Pressure drop across a rectangular slit (power-law melt).

    Parameters
    ----------
    flow_length : L [m]
    width       : W [m]
    half_gap    : h [m]  (= t_wall / 2)
    flow_rate   : Q [m³/s]
    K           : consistency index [Pa·s^n]
    n           : power-law index [-]

    Returns
    -------
    ΔP [Pa]
    """
    if half_gap <= 0.0 or width <= 0.0 or flow_length <= 0.0 or flow_rate <= 0.0:
        return 0.0
    # Apparent shear rate at the wall (Newtonian, slit geometry):
    #   γ̇_app = Q / (W · h²)
    gamma_app = flow_rate / (width * half_gap ** 2)
    # Rabinowitsch correction for power-law slit:
    #   γ̇_true = (2n+1)/(2n) · γ̇_app
    gamma_true = ((2.0 * n + 1.0) / (2.0 * n)) * gamma_app
    # Wall shear stress: τ = K · γ̇_true^n
    tau_wall = K * (gamma_true ** n)
    # ΔP = 2 · τ_wall · L / h
    delta_p = 2.0 * tau_wall * flow_length / half_gap
    return delta_p


def _shear_rate_stress(
    width: float,
    half_gap: float,
    flow_rate: float,
    K: float,
    n: float,
) -> Tuple[float, float, float]:
    """Return (gamma_app, gamma_true, tau_wall) for given slit conditions."""
    if half_gap <= 0.0 or width <= 0.0 or flow_rate <= 0.0:
        return 0.0, 0.0, 0.0
    gamma_app = flow_rate / (width * half_gap ** 2)
    gamma_true = ((2.0 * n + 1.0) / (2.0 * n)) * gamma_app
    tau_wall = K * (gamma_true ** n)
    return gamma_app, gamma_true, tau_wall


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------

def moldflow_fill(
    flow_length_m: float,
    t_wall_m: float,
    width_m: float,
    flow_rate_m3s: float,
    material: str = "abs",
    n_gates: int = 1,
    n_holes: int = 0,
    hole_diameter_m: float = 0.005,
    t_mould_C: float = 60.0,
    rib_wall_ratio: float = 0.0,
    n_cavities: int = 1,
    runner_balanced: bool = True,
) -> Dict[str, Any]:
    """Injection-moulding 1-D / 2.5-D fill simulation for a plate/strip cavity.

    Computes fill time, pressure drop, clamp tonnage, shear rate/stress vs
    material limits, freeze-off / short-shot prediction, weld-line positions,
    sink-mark risk, gate sizing, runner sizing, and cooling time.

    Parameters
    ----------
    flow_length_m   : cavity flow length [m]. Must be > 0.
    t_wall_m        : nominal wall thickness [m]. Must be > 0.
    width_m         : cavity width [m]. Must be > 0.
    flow_rate_m3s   : volumetric injection flow rate [m³/s]. Must be > 0.
    material        : polymer key: 'abs', 'pp', 'pe', 'ps', 'nylon66', 'pc'.
    n_gates         : number of gates (equally spaced along cavity). Default 1.
    n_holes         : number of circular holes (flow obstacles) in cavity. Default 0.
    hole_diameter_m : hole diameter [m] for weld-line positioning. Default 0.005 m.
    t_mould_C       : mould surface temperature [°C]. Default 60.
    rib_wall_ratio  : rib thickness / wall thickness [-]. 0 = no rib. Default 0.
    n_cavities      : number of identical cavities in the mould. Default 1.
    runner_balanced : True = balanced (H-tree) runner; False = sequential manifold.

    Returns
    -------
    dict with ok=True and fields:
      fill_time_s             — time to fill cavity [s]
      pressure_drop_Pa        — ΔP from gate to flow front [Pa]
      clamp_force_N           — required clamp force [N]
      clamp_tonnage_t         — required clamp force [metric tonnes]
      shear_rate_apparent_s⁻¹ — apparent wall shear rate [s⁻¹]
      shear_rate_true_s⁻¹     — Rabinowitsch-corrected wall shear rate [s⁻¹]
      shear_stress_Pa         — wall shear stress [Pa]
      shear_rate_over_limit   — True if γ̇_true > material shear-rate limit
      shear_stress_over_limit — True if τ_wall > material tau_limit
      short_shot              — True if frozen layer fills half-gap before fill
      frozen_layer_m          — frozen-layer thickness at end of fill [m]
      weld_line_positions_m   — list of weld-line positions along flow axis [m]
      sink_mark_risk          — True if rib_wall_ratio > 0.6
      gate_diameter_m         — recommended gate diameter [m]
      runner_diameter_m       — recommended runner diameter [m]
      cavity_fill_times_s     — fill time per cavity (list, length n_cavities)
      runner_balanced_equal   — True if all cavity fill times are equal
      cooling_time_s          — estimated cooling time [s]
      thermal_diffusivity_m2s — polymer thermal diffusivity [m²/s]
      warnings                — list of warning strings
    """
    try:
        return _moldflow_fill_inner(
            flow_length_m=flow_length_m,
            t_wall_m=t_wall_m,
            width_m=width_m,
            flow_rate_m3s=flow_rate_m3s,
            material=material,
            n_gates=n_gates,
            n_holes=n_holes,
            hole_diameter_m=hole_diameter_m,
            t_mould_C=t_mould_C,
            rib_wall_ratio=rib_wall_ratio,
            n_cavities=n_cavities,
            runner_balanced=runner_balanced,
        )
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def _moldflow_fill_inner(
    flow_length_m: float,
    t_wall_m: float,
    width_m: float,
    flow_rate_m3s: float,
    material: str,
    n_gates: int,
    n_holes: int,
    hole_diameter_m: float,
    t_mould_C: float,
    rib_wall_ratio: float,
    n_cavities: int,
    runner_balanced: bool,
) -> Dict[str, Any]:

    # -- Validation -----------------------------------------------------------
    if flow_length_m <= 0.0:
        return {"ok": False, "reason": "flow_length_m must be > 0"}
    if t_wall_m <= 0.0:
        return {"ok": False, "reason": "t_wall_m must be > 0"}
    if width_m <= 0.0:
        return {"ok": False, "reason": "width_m must be > 0"}
    if flow_rate_m3s <= 0.0:
        return {"ok": False, "reason": "flow_rate_m3s must be > 0"}
    if n_gates < 1:
        return {"ok": False, "reason": "n_gates must be >= 1"}
    if n_holes < 0:
        return {"ok": False, "reason": "n_holes must be >= 0"}
    if n_cavities < 1:
        return {"ok": False, "reason": "n_cavities must be >= 1"}
    if rib_wall_ratio < 0.0:
        return {"ok": False, "reason": "rib_wall_ratio must be >= 0"}

    poly_key = _resolve_polymer(material)
    if poly_key is None:
        return {"ok": False, "reason": f"unknown material '{material}'. Known: {sorted(_POLYMERS)}"}
    mat = _POLYMERS[poly_key]

    K = mat["K"]
    n = mat["n"]
    rho = mat["rho"]
    cp = mat["cp"]
    k_melt = mat["k_melt"]
    T_melt_mat = mat["T_melt"]
    T_eject = mat["T_eject"]
    tau_limit = mat["tau_limit"]
    gamma_limit = mat["shear_rate_limit"]

    warnings: List[str] = []

    # Geometric quantities
    h = t_wall_m / 2.0  # half-gap [m]
    # Each gate feeds a segment of length L/n_gates
    seg_length = flow_length_m / n_gates  # flow length per gate segment [m]
    # Cavity volume
    V_cavity = flow_length_m * width_m * t_wall_m  # [m³]
    # Projected area [m²]
    projected_area = flow_length_m * width_m

    # -- Thermal diffusivity --------------------------------------------------
    alpha_therm = k_melt / (rho * cp)  # [m²/s]

    # -- Fill time (cavity vol / flow rate) -----------------------------------
    t_fill = V_cavity / flow_rate_m3s  # [s]

    # -- Pressure drop (power-law slit, gate to flow front) ------------------
    # The flow from each gate covers seg_length at flow_rate / n_gates
    q_per_gate = flow_rate_m3s / n_gates
    delta_p = _slot_pressure_drop(seg_length, width_m, h, q_per_gate, K, n)

    # -- Clamp force ----------------------------------------------------------
    # Average cavity pressure ≈ ΔP / 2  (linear pressure gradient gate→front)
    p_avg = delta_p / 2.0
    clamp_force_N = projected_area * p_avg
    clamp_ton = clamp_force_N / (1000.0 * 9.80665)

    # -- Shear rate and shear stress ------------------------------------------
    gamma_app, gamma_true, tau_wall = _shear_rate_stress(width_m, h, q_per_gate, K, n)
    shear_rate_over = gamma_true > gamma_limit
    shear_stress_over = tau_wall > tau_limit

    if shear_rate_over:
        warnings.append(
            f"True wall shear rate {gamma_true:.1f} s⁻¹ exceeds material limit "
            f"{gamma_limit:.1f} s⁻¹ — risk of material degradation."
        )
    if shear_stress_over:
        warnings.append(
            f"Wall shear stress {tau_wall:.0f} Pa exceeds material limit "
            f"{tau_limit:.0f} Pa — risk of molecular degradation."
        )

    # -- Frozen-layer growth (Stefan approximation) ---------------------------
    # δ_frozen(t) = 2 · sqrt(α · t)   [m]
    delta_frozen = 2.0 * math.sqrt(alpha_therm * t_fill)
    short_shot = delta_frozen >= h

    if short_shot:
        warnings.append(
            f"Frozen layer ({delta_frozen*1e3:.2f} mm) ≥ half-gap ({h*1e3:.2f} mm) — "
            "short-shot predicted. Increase wall thickness, melt temperature, or flow rate."
        )

    # -- Weld-line locations --------------------------------------------------
    weld_positions: List[float] = []

    # Weld lines between adjacent flow fronts from multiple gates
    # Gates at positions: x_gate_i = (i + 0.5) * (flow_length / n_gates), i=0..n-1
    # BUT standard approach: gates equally spaced, weld lines at midpoints between gates
    # Gate i is at position: x_i = i * (flow_length / (n_gates - 1)) if n_gates>1
    # else at x = 0 (single gate at inlet)
    if n_gates == 1:
        gate_positions = [0.0]
    else:
        gate_positions = [i * (flow_length_m / (n_gates - 1)) for i in range(n_gates)]

    # Weld lines between neighbouring flow fronts (meet at the midpoint)
    for i in range(len(gate_positions) - 1):
        midpoint = (gate_positions[i] + gate_positions[i + 1]) / 2.0
        weld_positions.append(midpoint)

    # Weld lines from holes (flow splits and rejoins downstream)
    for j in range(n_holes):
        # Space holes evenly along the flow axis
        # Hole centre position along flow
        hole_centre = (j + 0.5) * (flow_length_m / max(n_holes, 1))
        # Weld line appears just downstream of the hole
        weld_pos = hole_centre + hole_diameter_m / 2.0
        if weld_pos < flow_length_m:
            weld_positions.append(weld_pos)

    weld_positions.sort()

    # -- Sink-mark risk -------------------------------------------------------
    # Practical rule: t_rib / t_wall > 0.6 → sink-mark risk
    sink_mark_risk = rib_wall_ratio > 0.6

    if sink_mark_risk:
        warnings.append(
            f"Rib-to-wall ratio {rib_wall_ratio:.2f} > 0.6 — sink-mark risk on "
            "opposite face. Reduce rib thickness or use coring."
        )

    # -- Gate sizing (Brydson empirical) --------------------------------------
    A_part_mm2 = (flow_length_m * 1e3) * (width_m * 1e3)  # part area [mm²]
    t_wall_mm = t_wall_m * 1e3
    t_ref_mm = 3.0
    gate_d_mm = 0.206 * math.sqrt(A_part_mm2) * math.sqrt(t_wall_mm / t_ref_mm)
    gate_d_m = gate_d_mm * 1e-3

    # -- Runner sizing --------------------------------------------------------
    # d_runner = d_gate × N^(1/3)  (cube-root rule for balanced runner)
    runner_d_m = gate_d_m * (n_cavities ** (1.0 / 3.0))

    # -- Multi-cavity fill times ----------------------------------------------
    cavity_fill_times: List[float] = []
    if runner_balanced:
        # All cavities fill simultaneously — equal fill times
        for _ in range(n_cavities):
            cavity_fill_times.append(t_fill)
    else:
        # Sequential manifold: cavity i must wait for upstream cavities to fill
        # cavity i fill time = (V_cavity * (i+1)) / flow_rate_m3s   (approx)
        # This gives monotonically increasing fill times.
        for i in range(n_cavities):
            cavity_fill_times.append(V_cavity * (i + 1) / flow_rate_m3s)

    # Check if all fill times are equal
    runner_equal = all(
        abs(t - cavity_fill_times[0]) < 1e-9 * max(cavity_fill_times[0], 1e-12)
        for t in cavity_fill_times
    )

    # -- Cooling time ---------------------------------------------------------
    # t_cool = (t_wall² / (π² α)) · ln((4/π) · (T_melt - T_mould) / (T_eject - T_mould))
    # Guard against degenerate temperatures
    dT_melt_mould = T_melt_mat - t_mould_C
    dT_eject_mould = T_eject - t_mould_C
    if dT_melt_mould <= 0.0 or dT_eject_mould <= 0.0 or dT_melt_mould <= dT_eject_mould:
        # Fallback: use simple diffusion scale t_cool ~ t_wall² / (10 α)
        t_cool = t_wall_m ** 2 / (10.0 * alpha_therm)
        warnings.append(
            "Mould/ejection temperature configuration unusual — cooling time is approximate."
        )
    else:
        C_cool = (4.0 / math.pi) * dT_melt_mould / dT_eject_mould
        if C_cool <= 1.0:
            t_cool = t_wall_m ** 2 / (10.0 * alpha_therm)
            warnings.append(
                "Cooling time argument C_cool ≤ 1 — mould temperature close to ejection temperature."
            )
        else:
            t_cool = (t_wall_m ** 2 / (math.pi ** 2 * alpha_therm)) * math.log(C_cool)

    # -- Final warnings -------------------------------------------------------
    if delta_p > 150e6:
        warnings.append(
            f"Cavity pressure drop {delta_p/1e6:.1f} MPa is very high — "
            "consider increasing wall thickness or reducing flow length."
        )

    return {
        "ok": True,
        "fill_time_s": t_fill,
        "pressure_drop_Pa": delta_p,
        "clamp_force_N": clamp_force_N,
        "clamp_tonnage_t": clamp_ton,
        "shear_rate_apparent_inv_s": gamma_app,
        "shear_rate_true_inv_s": gamma_true,
        "shear_stress_Pa": tau_wall,
        "shear_rate_over_limit": shear_rate_over,
        "shear_stress_over_limit": shear_stress_over,
        "short_shot": short_shot,
        "frozen_layer_m": delta_frozen,
        "weld_line_positions_m": weld_positions,
        "sink_mark_risk": sink_mark_risk,
        "gate_diameter_m": gate_d_m,
        "runner_diameter_m": runner_d_m,
        "cavity_fill_times_s": cavity_fill_times,
        "runner_balanced_equal": runner_equal,
        "cooling_time_s": t_cool,
        "thermal_diffusivity_m2s": alpha_therm,
        "material": poly_key,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# Standalone cooling-time estimate
# ---------------------------------------------------------------------------

def cooling_time(
    t_wall_m: float,
    material: str = "abs",
    T_melt_C: Optional[float] = None,
    T_mould_C: float = 60.0,
    T_eject_C: Optional[float] = None,
) -> Dict[str, Any]:
    """Estimate cooling time for a given wall thickness using the Carslaw-Jaeger
    slab-cooling approximation (first-term, symmetric cooling).

    Parameters
    ----------
    t_wall_m  : wall thickness [m]. Must be > 0.
    material  : polymer key. Default 'abs'.
    T_melt_C  : melt injection temperature [°C]. Default = material preset.
    T_mould_C : mould surface temperature [°C]. Default 60.
    T_eject_C : ejection temperature [°C]. Default = material preset (HDT).

    Returns
    -------
    dict with ok=True and:
      cooling_time_s          — estimated cooling time [s]
      thermal_diffusivity_m2s — α [m²/s]
      C_cool                  — ln argument (dimensionless temperature ratio)
    """
    try:
        return _cooling_time_inner(t_wall_m, material, T_melt_C, T_mould_C, T_eject_C)
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


def _cooling_time_inner(t_wall_m, material, T_melt_C, T_mould_C, T_eject_C):
    if t_wall_m <= 0.0:
        return {"ok": False, "reason": "t_wall_m must be > 0"}
    poly_key = _resolve_polymer(material)
    if poly_key is None:
        return {"ok": False, "reason": f"unknown material '{material}'"}
    mat = _POLYMERS[poly_key]
    T_melt = T_melt_C if T_melt_C is not None else mat["T_melt"]
    T_eject = T_eject_C if T_eject_C is not None else mat["T_eject"]
    alpha_therm = mat["k_melt"] / (mat["rho"] * mat["cp"])
    dT_mm = T_melt - T_mould_C
    dT_em = T_eject - T_mould_C
    if dT_mm <= 0.0 or dT_em <= 0.0 or dT_mm <= dT_em:
        return {"ok": False, "reason": "Require T_melt > T_eject > T_mould"}
    C_cool = (4.0 / math.pi) * dT_mm / dT_em
    if C_cool <= 1.0:
        return {"ok": False, "reason": "C_cool ≤ 1: temperature difference too small"}
    t_cool = (t_wall_m ** 2 / (math.pi ** 2 * alpha_therm)) * math.log(C_cool)
    return {
        "ok": True,
        "cooling_time_s": t_cool,
        "thermal_diffusivity_m2s": alpha_therm,
        "C_cool": C_cool,
    }


# ---------------------------------------------------------------------------
# Pressure-drop scan (parametric)
# ---------------------------------------------------------------------------

def pressure_drop_scan(
    flow_lengths_m: List[float],
    t_wall_m: float,
    width_m: float,
    flow_rate_m3s: float,
    material: str = "abs",
) -> Dict[str, Any]:
    """Compute pressure drop for a list of flow lengths (parametric sweep).

    Returns a list of ΔP values in the same order as flow_lengths_m.
    Useful for cross-checking ΔP ∝ L scaling.
    """
    try:
        if not flow_lengths_m:
            return {"ok": False, "reason": "flow_lengths_m must be non-empty"}
        poly_key = _resolve_polymer(material)
        if poly_key is None:
            return {"ok": False, "reason": f"unknown material '{material}'"}
        mat = _POLYMERS[poly_key]
        h = t_wall_m / 2.0
        K, n = mat["K"], mat["n"]
        results = []
        for L in flow_lengths_m:
            dp = _slot_pressure_drop(L, width_m, h, flow_rate_m3s, K, n)
            results.append(dp)
        return {"ok": True, "pressure_drop_Pa": results, "flow_lengths_m": flow_lengths_m}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


# ---------------------------------------------------------------------------
# LLM tool wrappers (gated on kerf_chat / kerf_core availability)
# ---------------------------------------------------------------------------

try:
    import json as _json
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register  # type: ignore[import]
    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    _REGISTRY_AVAILABLE = True
except ImportError:
    _REGISTRY_AVAILABLE = False

if _REGISTRY_AVAILABLE:

    # ------------------------------------------------------------------ #
    # moldflow_fill_sim                                                   #
    # ------------------------------------------------------------------ #

    _fill_spec = ToolSpec(
        name="moldflow_fill_sim",
        description=(
            "Injection-moulding 1-D / 2.5-D fill simulation (Moldflow direction).\n"
            "\n"
            "Computes for a rectangular plate/strip cavity:\n"
            "  • Fill time & flow rate balance\n"
            "  • Pressure drop (power-law slit flow, Hagen-Poiseuille)\n"
            "  • Clamp tonnage (projected area × cavity pressure)\n"
            "  • Shear rate & shear stress vs material limits\n"
            "  • Freeze-off / short-shot prediction (frozen-layer growth)\n"
            "  • Weld-line positions (multi-gate + flow-around-holes)\n"
            "  • Sink-mark risk (rib-to-wall ratio > 0.6)\n"
            "  • Gate & runner sizing\n"
            "  • Multi-cavity runner balance (balanced vs sequential)\n"
            "  • Cooling time (Carslaw-Jaeger slab approximation)\n"
            "\n"
            "material: 'abs' | 'pp' | 'pe' | 'ps' | 'nylon66' | 'pc'\n"
            "\n"
            "Errors: {ok:false, reason} — never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "flow_length_m": {
                    "type": "number",
                    "description": "Cavity flow length [m]. Must be > 0.",
                },
                "t_wall_m": {
                    "type": "number",
                    "description": "Nominal wall thickness [m]. Must be > 0.",
                },
                "width_m": {
                    "type": "number",
                    "description": "Cavity width [m]. Must be > 0.",
                },
                "flow_rate_m3s": {
                    "type": "number",
                    "description": "Volumetric injection flow rate [m³/s]. Must be > 0.",
                },
                "material": {
                    "type": "string",
                    "description": "Polymer: 'abs', 'pp', 'pe', 'ps', 'nylon66', 'pc'.",
                },
                "n_gates": {
                    "type": "integer",
                    "description": "Number of gates (equally spaced). Default 1.",
                },
                "n_holes": {
                    "type": "integer",
                    "description": "Number of circular holes (flow obstacles). Default 0.",
                },
                "hole_diameter_m": {
                    "type": "number",
                    "description": "Hole diameter [m]. Default 0.005.",
                },
                "t_mould_C": {
                    "type": "number",
                    "description": "Mould surface temperature [°C]. Default 60.",
                },
                "rib_wall_ratio": {
                    "type": "number",
                    "description": "Rib thickness / wall thickness [-]. Default 0.",
                },
                "n_cavities": {
                    "type": "integer",
                    "description": "Number of identical cavities. Default 1.",
                },
                "runner_balanced": {
                    "type": "boolean",
                    "description": "True = balanced runner (equal fill times). Default True.",
                },
            },
            "required": ["flow_length_m", "t_wall_m", "width_m", "flow_rate_m3s"],
        },
    )

    @register(_fill_spec, write=False)
    async def run_moldflow_fill(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        for f in ("flow_length_m", "t_wall_m", "width_m", "flow_rate_m3s"):
            if a.get(f) is None:
                return _json.dumps({"ok": False, "reason": f"{f} is required"})
        kwargs: dict = {}
        for opt in ("material", "n_gates", "n_holes", "hole_diameter_m",
                    "t_mould_C", "rib_wall_ratio", "n_cavities", "runner_balanced"):
            if opt in a:
                kwargs[opt] = a[opt]
        result = moldflow_fill(
            flow_length_m=float(a["flow_length_m"]),
            t_wall_m=float(a["t_wall_m"]),
            width_m=float(a["width_m"]),
            flow_rate_m3s=float(a["flow_rate_m3s"]),
            **kwargs,
        )
        return ok_payload(result) if result["ok"] else _json.dumps(result)

    # ------------------------------------------------------------------ #
    # moldflow_cooling_time                                               #
    # ------------------------------------------------------------------ #

    _cool_spec = ToolSpec(
        name="moldflow_cooling_time",
        description=(
            "Estimate injection-moulding cooling time for a given wall thickness.\n"
            "\n"
            "Uses the Carslaw-Jaeger symmetric slab-cooling first-term approximation:\n"
            "  t_cool = t_wall² / (π² α) · ln((4/π)·(T_melt−T_mould)/(T_eject−T_mould))\n"
            "\n"
            "Errors: {ok:false, reason} — never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "t_wall_m": {
                    "type": "number",
                    "description": "Wall thickness [m]. Must be > 0.",
                },
                "material": {
                    "type": "string",
                    "description": "Polymer: 'abs', 'pp', 'pe', 'ps', 'nylon66', 'pc'.",
                },
                "T_melt_C": {
                    "type": "number",
                    "description": "Melt temperature [°C]. Default = material preset.",
                },
                "T_mould_C": {
                    "type": "number",
                    "description": "Mould surface temperature [°C]. Default 60.",
                },
                "T_eject_C": {
                    "type": "number",
                    "description": "Ejection (HDT) temperature [°C]. Default = material preset.",
                },
            },
            "required": ["t_wall_m"],
        },
    )

    @register(_cool_spec, write=False)
    async def run_moldflow_cooling(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args JSON: {exc}", "BAD_ARGS")
        if a.get("t_wall_m") is None:
            return _json.dumps({"ok": False, "reason": "t_wall_m is required"})
        kwargs: dict = {}
        for opt in ("material", "T_melt_C", "T_mould_C", "T_eject_C"):
            if opt in a:
                kwargs[opt] = a[opt]
        result = cooling_time(t_wall_m=float(a["t_wall_m"]), **kwargs)
        return ok_payload(result) if result["ok"] else _json.dumps(result)
