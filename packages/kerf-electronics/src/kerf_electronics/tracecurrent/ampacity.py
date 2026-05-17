"""
PCB trace current-capacity and copper-thermal design — closed-form models.

This module is distinct from:
  • kerf_electronics.protection  — fuse selection, Onderdonk fusing (thermal runaway)
  • kerf_electronics.pdn         — power-delivery network impedance / IR-drop
  • kerf_electronics.stackup     — controlled-impedance / transmission-line design
  • kerf_electronics.thermal     — component junction-to-board thermal paths

Formulas and references
-----------------------
IPC trace current-carrying capacity
    The closed-form base model is the widely-cited IPC-2221(B) Eq. 6-4
    charts equation (also reproduced in IPC-2152 Annex / Saturn PCB
    Toolkit).  IPC-2152 (2009) refined the underlying test data, but the
    IPC-2221 power-law remains the standard analytical form and is used
    here with the IPC-2152 correction factors layered on top.

    Steady-state current for a trace (IPC-2221B Eq.):
        I [A] = k_0 × ΔT^b × A_mil²^c
    where A_mil² = cross-sectional area in mil² (width_mil × thickness_mil),
    ΔT = allowable temperature rise above ambient [°C].

    IPC-2221B coefficients (air-cooled, no ground plane adjacent):
        External copper:  k_0 = 0.048, b = 0.44,  c = 0.725
        Internal copper:  k_0 = 0.024, b = 0.44,  c = 0.725
        (internal = exactly half of external — IPC-2221B derating).
    Reference (Saturn PCB Toolkit / IPC-2221B): a 100 mil-wide, 1 oz
    external trace at ΔT = 10 °C carries ≈ 4.7 A; 1 A at ΔT = 10 °C
    needs ≈ 12–13 mil (≈ 0.30 mm) of 1 oz external copper.

    Correction factors (IPC-2152 §6.2):
        Copper-weight (oz/ft²) correction: from regression of IPC-2152 Fig. 6-1
            cf_cw  = (oz / 1.0)^0.045          (normalised to 1 oz baseline)
        Board-thickness / base-material thermal-conductivity correction:
            cf_th  = (k_pcb / 0.25)^0.10 × (t_pcb_mm / 1.6)^0.05
            (k_pcb in W/m·K, FR4 baseline ≈ 0.25 W/m·K; t_pcb baseline 1.6 mm)
        Copper-plane proximity correction (adjacent solid plane ≤ H_plane_mm away):
            cf_pl  = 1.0 + 0.15 × exp(−H_plane_mm / 0.3)
            (adjacent plane increases heat spreading; coefficient empirical)

    Corrected capacity:
        I_corrected = I_ipc × cf_cw × cf_th × cf_pl

Trace DC resistance and I²R
    ρ_Cu at 20°C = 1.724e-8 Ω·m  (IEC 60228)
    Temperature coefficient α = 3.93e-3 /°C  (NIST)
    R [Ω] = ρ_Cu × (1 + α×(T-20)) × L / A
    P_loss [W] = I² × R
    V_drop [V] = I × R

Via current capacity (IPC-2152 §7)
    The current-carrying barrel is the plated annulus:
        A_barrel_mil² = π × (drill_mil/2 + plating_mil)² − π × (drill_mil/2)²
                      ≈ π × drill_mil × plating_mil   (thin-wall approximation)
    Capacity uses the same IPC-2152 model as a trace with T_trace = plating_mm×2.

Required number of vias:
    n_vias = ceil(I_total / I_per_via)

Thermal-via array (IPC-7093)
    Each via: Rθ_via = t_pcb_mm × 1e-3 / (A_barrel_m² × k_Cu)
    Parallel vias:  Rθ_array = Rθ_via / n
    Spreading resistance (square heat source of side L):
        Rθ_spread ≈ 1 / (4 × k_pcb × L)
    Total: Rθ_total = Rθ_array + Rθ_spread
    ΔT = P_diss × Rθ_total

Copper-plane sheet resistance
    Rs = ρ_Cu × (1 + α×(T-20)) / t_Cu_m   [Ω/square]
    Current density J = I / (w × t)   [A/m²]
    Onderdonk fusing temperature check (cross-check only):
        t_fuse [s] = (A_mil² / I²) × (log10(T_fuse/T_ambient+1) / 0.0297)
        (Onderdonk 1923; reference only — not a replacement for protection.protect)

Polygon-pour heatsink area
    For a target junction-to-board thermal resistance Rθ_target [°C/W]
    and copper-plane of thickness t_Cu [m]:
        Rθ_plane ≈ t_pcb / (A_pour × k_pcb)
        A_pour = t_pcb / (Rθ_target × k_pcb)   [m²]

Busbar copper sizing
    I = J_max × W × T   →  W_mm = (I / (J_max × T_mm × 1e-3)) × 1e3
    where J_max is the allowable current density [A/mm²].

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import Any, Dict

# ── Physical constants ────────────────────────────────────────────────────────
_RHO_CU_20C: float = 1.724e-8     # Ω·m  (IEC 60228, annealed copper at 20 °C)
_ALPHA_CU: float = 3.93e-3        # /°C  (NIST resistivity temperature coefficient)
_K_CU: float = 385.0              # W/(m·K)  copper thermal conductivity
_K_FR4_DEFAULT: float = 0.25      # W/(m·K)  FR-4 baseline (IPC-2152 §6.2)
_T_PCB_DEFAULT_MM: float = 1.6    # mm     FR-4 standard thickness baseline
_OZ_TO_MM: float = 0.0348         # mm per oz/ft²  (1 oz = 34.8 µm)
_MM2_TO_MIL2: float = 1550.0031   # 1 mm² = 1550 mil²
_MM_TO_MIL: float = 39.3701       # 1 mm  = 39.3701 mil

# IPC-2152 Table 6-1 curve-fit coefficients (no correction factors applied)
_IPC_K0_EXT: float = 0.048
_IPC_K0_INT: float = 0.024
_IPC_B: float = 0.44
_IPC_C: float = 0.725

# Copper fusing temperature (Onderdonk): melting point of Cu ≈ 1083 °C
_T_FUSE_CU: float = 1083.0


# ── helpers ───────────────────────────────────────────────────────────────────

def _validate_positive(name: str, val: Any) -> str | None:
    """Return an error string if val is not a positive real number."""
    if val is None:
        return f"'{name}' is required"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return f"'{name}' must be numeric, got {val!r}"
    if not math.isfinite(v) or v <= 0:
        return f"'{name}' must be > 0, got {v}"
    return None


def _validate_nonneg(name: str, val: Any) -> str | None:
    if val is None:
        return f"'{name}' is required"
    try:
        v = float(val)
    except (TypeError, ValueError):
        return f"'{name}' must be numeric, got {val!r}"
    if not math.isfinite(v) or v < 0:
        return f"'{name}' must be ≥ 0, got {v}"
    return None


def _oz_to_mm(oz: float) -> float:
    return oz * _OZ_TO_MM


def _rho_cu(temp_c: float) -> float:
    """Copper resistivity at temperature temp_c [°C]."""
    return _RHO_CU_20C * (1.0 + _ALPHA_CU * (temp_c - 20.0))


# ═══════════════════════════════════════════════════════════════════════════════
# 1. ipc2152_trace_current  — IPC-2152 steady-state current capacity
# ═══════════════════════════════════════════════════════════════════════════════

def ipc2152_trace_current(
    *,
    width_mm: float,
    copper_oz: float = 1.0,
    delta_t_c: float = 10.0,
    layer: str = "external",
    k_pcb: float = _K_FR4_DEFAULT,
    t_pcb_mm: float = _T_PCB_DEFAULT_MM,
    h_plane_mm: float | None = None,
) -> Dict[str, Any]:
    """
    IPC-2152 steady-state current capacity for a PCB trace.

    Parameters
    ----------
    width_mm    : trace width [mm]
    copper_oz   : copper weight [oz/ft²] (default 1.0)
    delta_t_c   : allowable temperature rise above ambient [°C] (default 10)
    layer       : 'external' or 'internal'
    k_pcb       : board base-material thermal conductivity [W/(m·K)] (FR-4 default 0.25)
    t_pcb_mm    : board thickness [mm] (default 1.6)
    h_plane_mm  : distance to adjacent copper plane [mm] (None = no nearby plane)

    Returns
    -------
    dict with ok, current_a, cross_section_mil2, width_mm, copper_oz, delta_t_c,
    layer, cf_copper_weight, cf_board, cf_plane, warnings
    """
    errs = []
    for name, val in [("width_mm", width_mm), ("copper_oz", copper_oz),
                      ("delta_t_c", delta_t_c), ("k_pcb", k_pcb),
                      ("t_pcb_mm", t_pcb_mm)]:
        e = _validate_positive(name, val)
        if e:
            errs.append(e)
    if layer not in ("external", "internal"):
        errs.append(f"'layer' must be 'external' or 'internal', got {layer!r}")
    if errs:
        return {"ok": False, "reason": "; ".join(errs)}

    t_cu_mm = _oz_to_mm(float(copper_oz))
    w_mil = float(width_mm) * _MM_TO_MIL
    t_mil = t_cu_mm * _MM_TO_MIL
    area_mil2 = w_mil * t_mil

    k0 = _IPC_K0_EXT if layer == "external" else _IPC_K0_INT
    dt = float(delta_t_c)
    i_base = k0 * (dt ** _IPC_B) * (area_mil2 ** _IPC_C)

    # Correction factors
    cf_cw = (float(copper_oz) / 1.0) ** 0.045
    cf_th = ((float(k_pcb) / _K_FR4_DEFAULT) ** 0.10
             * (float(t_pcb_mm) / _T_PCB_DEFAULT_MM) ** 0.05)

    cf_pl = 1.0
    if h_plane_mm is not None:
        e = _validate_positive("h_plane_mm", h_plane_mm)
        if e:
            return {"ok": False, "reason": e}
        cf_pl = 1.0 + 0.15 * math.exp(-float(h_plane_mm) / 0.3)

    i_corrected = i_base * cf_cw * cf_th * cf_pl

    warn_msgs: list[str] = []
    if i_corrected < 0.01:
        warnings.warn(
            f"tracecurrent: computed capacity {i_corrected:.4f} A is extremely low "
            "(check inputs)", stacklevel=2
        )
        warn_msgs.append("capacity_very_low")

    return {
        "ok": True,
        "current_a": round(i_corrected, 4),
        "current_base_a": round(i_base, 4),
        "cross_section_mil2": round(area_mil2, 2),
        "width_mm": float(width_mm),
        "thickness_mm": round(t_cu_mm, 5),
        "copper_oz": float(copper_oz),
        "delta_t_c": float(delta_t_c),
        "layer": layer,
        "cf_copper_weight": round(cf_cw, 5),
        "cf_board": round(cf_th, 5),
        "cf_plane": round(cf_pl, 5),
        "warnings": warn_msgs,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 2. required_trace_width  — solver: width for a target current / ΔT
# ═══════════════════════════════════════════════════════════════════════════════

def required_trace_width(
    *,
    current_a: float,
    copper_oz: float = 1.0,
    delta_t_c: float = 10.0,
    layer: str = "external",
    k_pcb: float = _K_FR4_DEFAULT,
    t_pcb_mm: float = _T_PCB_DEFAULT_MM,
    h_plane_mm: float | None = None,
) -> Dict[str, Any]:
    """
    Bisection solver: trace width [mm] required to carry current_a with ΔT ≤ delta_t_c.

    Returns
    -------
    dict with ok, width_mm, current_a, delta_t_c, cross_section_mil2, warnings
    """
    errs = []
    for name, val in [("current_a", current_a), ("copper_oz", copper_oz),
                      ("delta_t_c", delta_t_c), ("k_pcb", k_pcb),
                      ("t_pcb_mm", t_pcb_mm)]:
        e = _validate_positive(name, val)
        if e:
            errs.append(e)
    if layer not in ("external", "internal"):
        errs.append(f"'layer' must be 'external' or 'internal', got {layer!r}")
    if errs:
        return {"ok": False, "reason": "; ".join(errs)}

    # Bisect over width_mm [0.01, 100]
    lo, hi = 0.001, 100.0
    for _ in range(80):
        mid = (lo + hi) / 2.0
        res = ipc2152_trace_current(
            width_mm=mid,
            copper_oz=copper_oz,
            delta_t_c=delta_t_c,
            layer=layer,
            k_pcb=k_pcb,
            t_pcb_mm=t_pcb_mm,
            h_plane_mm=h_plane_mm,
        )
        if not res["ok"]:
            return res
        if res["current_a"] < float(current_a):
            lo = mid
        else:
            hi = mid

    w_mm = (lo + hi) / 2.0
    final = ipc2152_trace_current(
        width_mm=w_mm,
        copper_oz=copper_oz,
        delta_t_c=delta_t_c,
        layer=layer,
        k_pcb=k_pcb,
        t_pcb_mm=t_pcb_mm,
        h_plane_mm=h_plane_mm,
    )

    warn_msgs: list[str] = []
    if w_mm > 20.0:
        warnings.warn(
            f"tracecurrent: required trace width {w_mm:.2f} mm is unusually wide",
            stacklevel=2,
        )
        warn_msgs.append("width_very_wide")

    return {
        "ok": True,
        "width_mm": round(w_mm, 4),
        "current_a": float(current_a),
        "delta_t_c": float(delta_t_c),
        "cross_section_mil2": final["cross_section_mil2"],
        "copper_oz": float(copper_oz),
        "layer": layer,
        "warnings": warn_msgs,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 3. trace_resistance  — DC resistance, I²R power, voltage drop
# ═══════════════════════════════════════════════════════════════════════════════

def trace_resistance(
    *,
    width_mm: float,
    length_mm: float,
    copper_oz: float = 1.0,
    current_a: float = 1.0,
    temp_c: float = 25.0,
) -> Dict[str, Any]:
    """
    Trace DC resistance [Ω], I²R power loss [W], and voltage drop [V].

    Parameters
    ----------
    width_mm  : trace width [mm]
    length_mm : trace length [mm]
    copper_oz : copper weight [oz/ft²] (default 1.0)
    current_a : trace current [A] (default 1.0)
    temp_c    : operating temperature [°C] (default 25.0)

    Returns
    -------
    dict with ok, resistance_ohm, power_w, voltage_drop_v, sheet_resistance_ohm_sq,
    width_mm, length_mm, copper_oz, temp_c, warnings
    """
    errs = []
    for name, val in [("width_mm", width_mm), ("length_mm", length_mm),
                      ("copper_oz", copper_oz)]:
        e = _validate_positive(name, val)
        if e:
            errs.append(e)
    e = _validate_nonneg("current_a", current_a)
    if e:
        errs.append(e)
    if errs:
        return {"ok": False, "reason": "; ".join(errs)}

    t_cu_m = _oz_to_mm(float(copper_oz)) * 1e-3
    w_m = float(width_mm) * 1e-3
    l_m = float(length_mm) * 1e-3
    rho = _rho_cu(float(temp_c))

    area_m2 = w_m * t_cu_m
    r_ohm = rho * l_m / area_m2
    rs_ohm_sq = rho / t_cu_m          # sheet resistance [Ω/□]
    i = float(current_a)
    p_w = i * i * r_ohm
    v_drop = i * r_ohm

    warn_msgs: list[str] = []
    if v_drop > 0.1 * 3.3:
        warnings.warn(
            f"tracecurrent: voltage drop {v_drop:.3f} V exceeds 10% of 3.3 V rail",
            stacklevel=2,
        )
        warn_msgs.append("high_voltage_drop")

    return {
        "ok": True,
        "resistance_ohm": round(r_ohm, 8),
        "power_w": round(p_w, 6),
        "voltage_drop_v": round(v_drop, 6),
        "sheet_resistance_ohm_sq": round(rs_ohm_sq, 8),
        "width_mm": float(width_mm),
        "length_mm": float(length_mm),
        "copper_oz": float(copper_oz),
        "current_a": float(current_a),
        "temp_c": float(temp_c),
        "warnings": warn_msgs,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 4. via_current_capacity  — via barrel current capacity
# ═══════════════════════════════════════════════════════════════════════════════

def via_current_capacity(
    *,
    drill_mm: float,
    plating_mm: float = 0.025,
    delta_t_c: float = 10.0,
    layer: str = "internal",
) -> Dict[str, Any]:
    """
    IPC-2152–based via barrel current capacity.

    The plated barrel is modelled as a circular trace whose effective width is
    the inner circumference (π × drill_mm) and whose thickness is plating_mm.

    Parameters
    ----------
    drill_mm   : finished (after-plating) drill diameter [mm]; the model uses
                 this as the inner bore diameter.
    plating_mm : copper plating thickness [mm] (default 0.025 mm = 25 µm, IPC min)
    delta_t_c  : allowable temperature rise [°C] (default 10)
    layer      : 'external' or 'internal' (default 'internal')

    Returns
    -------
    dict with ok, current_a, barrel_area_mil2, drill_mm, plating_mm, delta_t_c, warnings
    """
    errs = []
    for name, val in [("drill_mm", drill_mm), ("plating_mm", plating_mm),
                      ("delta_t_c", delta_t_c)]:
        e = _validate_positive(name, val)
        if e:
            errs.append(e)
    if layer not in ("external", "internal"):
        errs.append(f"'layer' must be 'external' or 'internal', got {layer!r}")
    if errs:
        return {"ok": False, "reason": "; ".join(errs)}

    # Effective width = inner circumference
    eff_width_mm = math.pi * float(drill_mm)
    plating_oz = float(plating_mm) / _OZ_TO_MM

    res = ipc2152_trace_current(
        width_mm=eff_width_mm,
        copper_oz=plating_oz,
        delta_t_c=float(delta_t_c),
        layer=layer,
    )
    if not res["ok"]:
        return res

    warn_msgs: list[str] = []
    if plating_oz < 0.5:
        warnings.warn(
            f"tracecurrent: via plating {float(plating_mm)*1000:.1f} µm is below "
            "IPC-6012 Class 2 minimum (18 µm), capacity may be underestimated",
            stacklevel=2,
        )
        warn_msgs.append("thin_plating")

    return {
        "ok": True,
        "current_a": res["current_a"],
        "barrel_area_mil2": res["cross_section_mil2"],
        "drill_mm": float(drill_mm),
        "plating_mm": float(plating_mm),
        "delta_t_c": float(delta_t_c),
        "layer": layer,
        "warnings": warn_msgs,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 5. required_via_count  — number of vias for a current
# ═══════════════════════════════════════════════════════════════════════════════

def required_via_count(
    *,
    total_current_a: float,
    drill_mm: float,
    plating_mm: float = 0.025,
    delta_t_c: float = 10.0,
    layer: str = "internal",
) -> Dict[str, Any]:
    """
    Minimum number of vias required to carry total_current_a.

    Returns
    -------
    dict with ok, n_vias, current_per_via_a, total_current_a, warnings
    """
    errs = []
    for name, val in [("total_current_a", total_current_a)]:
        e = _validate_positive(name, val)
        if e:
            errs.append(e)
    if errs:
        return {"ok": False, "reason": "; ".join(errs)}

    res = via_current_capacity(
        drill_mm=drill_mm,
        plating_mm=plating_mm,
        delta_t_c=delta_t_c,
        layer=layer,
    )
    if not res["ok"]:
        return res

    i_per_via = res["current_a"]
    if i_per_via <= 0:
        return {"ok": False, "reason": "via current capacity is zero"}

    n = math.ceil(float(total_current_a) / i_per_via)

    warn_msgs: list[str] = []
    if n > 20:
        warnings.warn(
            f"tracecurrent: {n} vias required — consider a larger drill diameter "
            "or heavier plating",
            stacklevel=2,
        )
        warn_msgs.append("many_vias")

    return {
        "ok": True,
        "n_vias": n,
        "current_per_via_a": round(i_per_via, 4),
        "total_current_a": float(total_current_a),
        "drill_mm": float(drill_mm),
        "plating_mm": float(plating_mm),
        "warnings": warn_msgs,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 6. thermal_via_array  — thermal resistance of a via array (IPC-7093)
# ═══════════════════════════════════════════════════════════════════════════════

def thermal_via_array(
    *,
    n_vias: int,
    drill_mm: float,
    plating_mm: float = 0.025,
    t_pcb_mm: float = _T_PCB_DEFAULT_MM,
    k_pcb: float = _K_FR4_DEFAULT,
    array_side_mm: float = 3.0,
    power_w: float = 1.0,
) -> Dict[str, Any]:
    """
    Thermal resistance and ΔT of a thermal-via array (IPC-7093 model).

    Each via barrel conducts heat through the board in copper; the remaining
    PCB area conducts through FR-4.  Spreading resistance is approximated for
    a square heat source.

    Parameters
    ----------
    n_vias         : number of thermal vias in the array
    drill_mm       : via drill diameter [mm] (inner bore)
    plating_mm     : copper plating thickness [mm] (default 0.025 mm)
    t_pcb_mm       : board thickness [mm] (default 1.6 mm)
    k_pcb          : base-material thermal conductivity [W/(m·K)] (default 0.25)
    array_side_mm  : side length of the square via-array footprint [mm] (default 3.0)
    power_w        : dissipated power [W] (default 1.0)

    Returns
    -------
    dict with ok, rth_via_each_k_per_w, rth_array_k_per_w, rth_spread_k_per_w,
    rth_total_k_per_w, delta_t_k, n_vias, warnings
    """
    errs = []
    for name, val in [("drill_mm", drill_mm), ("plating_mm", plating_mm),
                      ("t_pcb_mm", t_pcb_mm), ("k_pcb", k_pcb),
                      ("array_side_mm", array_side_mm), ("power_w", power_w)]:
        e = _validate_positive(name, val)
        if e:
            errs.append(e)
    if n_vias is None or int(n_vias) < 1:
        errs.append("'n_vias' must be ≥ 1")
    if errs:
        return {"ok": False, "reason": "; ".join(errs)}

    n = int(n_vias)
    d_m = float(drill_mm) * 1e-3
    pl_m = float(plating_mm) * 1e-3
    t_m = float(t_pcb_mm) * 1e-3
    s_m = float(array_side_mm) * 1e-3

    # Barrel cross-sectional area (annular ring)
    r_outer = d_m / 2.0 + pl_m
    r_inner = d_m / 2.0
    a_barrel = math.pi * (r_outer ** 2 - r_inner ** 2)

    # Thermal resistance of one via
    rth_each = t_m / (a_barrel * _K_CU)

    # Parallel combination of n vias
    rth_array = rth_each / n

    # Spreading resistance for a square source (side = array_side_mm)
    rth_spread = 1.0 / (4.0 * float(k_pcb) * s_m)

    rth_total = rth_array + rth_spread
    dt = float(power_w) * rth_total

    warn_msgs: list[str] = []
    if dt > 15.0:
        warnings.warn(
            f"tracecurrent: thermal-via array ΔT = {dt:.1f} K — "
            "consider more vias or a larger array",
            stacklevel=2,
        )
        warn_msgs.append("high_delta_t")

    return {
        "ok": True,
        "rth_via_each_k_per_w": round(rth_each, 4),
        "rth_array_k_per_w": round(rth_array, 4),
        "rth_spread_k_per_w": round(rth_spread, 4),
        "rth_total_k_per_w": round(rth_total, 4),
        "delta_t_k": round(dt, 4),
        "n_vias": n,
        "drill_mm": float(drill_mm),
        "plating_mm": float(plating_mm),
        "power_w": float(power_w),
        "warnings": warn_msgs,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 7. plane_sheet_resistance  — copper-plane Rs, current density, fusing margin
# ═══════════════════════════════════════════════════════════════════════════════

def plane_sheet_resistance(
    *,
    copper_oz: float = 1.0,
    temp_c: float = 25.0,
    current_a: float | None = None,
    plane_width_mm: float | None = None,
    ambient_c: float = 25.0,
) -> Dict[str, Any]:
    """
    Copper-plane sheet resistance [Ω/□] and optional current-density check.

    If current_a and plane_width_mm are provided, also returns:
      • current density J [A/mm²]
      • Onderdonk fusing time t_fuse [s] at current_a per unit-width cross-section
        (cross-check only; for accurate fuse sizing use protection.protect)

    Parameters
    ----------
    copper_oz      : copper weight [oz/ft²] (default 1.0)
    temp_c         : operating temperature [°C] (default 25.0)
    current_a      : current [A] (optional; enables density + Onderdonk check)
    plane_width_mm : plane width [mm] (optional, required if current_a given)
    ambient_c      : ambient temperature [°C] for Onderdonk (default 25.0)

    Returns
    -------
    dict with ok, sheet_resistance_ohm_sq, thickness_mm, copper_oz, temp_c,
    [current_density_a_mm2, onderdonk_fuse_time_s, fusing_margin_ok], warnings
    """
    errs = []
    for name, val in [("copper_oz", copper_oz)]:
        e = _validate_positive(name, val)
        if e:
            errs.append(e)
    if errs:
        return {"ok": False, "reason": "; ".join(errs)}

    t_cu_m = _oz_to_mm(float(copper_oz)) * 1e-3
    rho = _rho_cu(float(temp_c))
    rs = rho / t_cu_m

    result: Dict[str, Any] = {
        "ok": True,
        "sheet_resistance_ohm_sq": round(rs, 11),
        "thickness_mm": round(t_cu_m * 1e3, 5),
        "copper_oz": float(copper_oz),
        "temp_c": float(temp_c),
        "warnings": [],
    }

    if current_a is not None:
        ec = _validate_positive("current_a", current_a)
        if ec:
            return {"ok": False, "reason": ec}
        if plane_width_mm is None:
            return {"ok": False, "reason": "'plane_width_mm' required when current_a is given"}
        ep = _validate_positive("plane_width_mm", plane_width_mm)
        if ep:
            return {"ok": False, "reason": ep}

        w_mm = float(plane_width_mm)
        i = float(current_a)
        t_mm = t_cu_m * 1e3
        j = i / (w_mm * t_mm)   # A/mm²
        result["current_density_a_mm2"] = round(j, 4)

        # Onderdonk fusing time (cross-check reference only)
        # t_fuse = (A_mil² / I²) * log10((T_fuse - T_amb)/234 + 1) / 0.0297
        # simplified: A_mil² = width_mil * thickness_mil
        w_mil = w_mm * _MM_TO_MIL
        t_mil = t_mm * _MM_TO_MIL
        a_mil2 = w_mil * t_mil
        amb = float(ambient_c)
        if _T_FUSE_CU <= amb:
            result["onderdonk_fuse_time_s"] = None
            result["fusing_margin_ok"] = False
        else:
            log_term = math.log10((_T_FUSE_CU - amb) / 234.0 + 1.0)
            t_fuse = (a_mil2 / (i * i)) * (log_term / 0.0297)
            result["onderdonk_fuse_time_s"] = round(t_fuse, 4)
            result["fusing_margin_ok"] = t_fuse > 1.0  # flag if fuses in < 1 s

            if t_fuse < 0.1:
                warnings.warn(
                    f"tracecurrent: Onderdonk fusing time {t_fuse:.4f} s < 0.1 s — "
                    "plane may fuse; verify with protection.protect for accurate fuse sizing",
                    stacklevel=2,
                )
                result["warnings"].append("onderdonk_near_fusing")

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# 8. polygon_pour_heatsink_area  — copper-pour area for target Rθ
# ═══════════════════════════════════════════════════════════════════════════════

def polygon_pour_heatsink_area(
    *,
    rth_target_k_per_w: float,
    t_pcb_mm: float = _T_PCB_DEFAULT_MM,
    k_pcb: float = _K_FR4_DEFAULT,
) -> Dict[str, Any]:
    """
    Required copper-pour (polygon heatsink) area for a target thermal resistance.

    Model: one-dimensional conduction through the PCB substrate under the pour:
        Rθ_plane ≈ t_pcb / (A_pour × k_pcb)
        →  A_pour = t_pcb / (Rθ_target × k_pcb)

    This is a conservative (lower-bound) estimate; the actual Rθ will be lower
    because copper spreading in the plane is not modelled.

    Parameters
    ----------
    rth_target_k_per_w : target thermal resistance [K/W] or [°C/W]
    t_pcb_mm           : board thickness [mm] (default 1.6 mm)
    k_pcb              : base-material k [W/(m·K)] (default 0.25 for FR-4)

    Returns
    -------
    dict with ok, area_mm2, area_cm2, side_mm (square equivalent),
    rth_target_k_per_w, t_pcb_mm, k_pcb, warnings
    """
    errs = []
    for name, val in [("rth_target_k_per_w", rth_target_k_per_w),
                      ("t_pcb_mm", t_pcb_mm), ("k_pcb", k_pcb)]:
        e = _validate_positive(name, val)
        if e:
            errs.append(e)
    if errs:
        return {"ok": False, "reason": "; ".join(errs)}

    t_m = float(t_pcb_mm) * 1e-3
    a_m2 = t_m / (float(rth_target_k_per_w) * float(k_pcb))
    a_mm2 = a_m2 * 1e6
    a_cm2 = a_m2 * 1e4
    side_mm = math.sqrt(a_mm2)

    warn_msgs: list[str] = []
    if a_cm2 > 100.0:
        warnings.warn(
            f"tracecurrent: required pour area {a_cm2:.1f} cm² is very large; "
            "consider a metal-core PCB or external heatsink",
            stacklevel=2,
        )
        warn_msgs.append("large_pour_area")

    return {
        "ok": True,
        "area_mm2": round(a_mm2, 2),
        "area_cm2": round(a_cm2, 4),
        "side_mm": round(side_mm, 2),
        "rth_target_k_per_w": float(rth_target_k_per_w),
        "t_pcb_mm": float(t_pcb_mm),
        "k_pcb": float(k_pcb),
        "warnings": warn_msgs,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# 9. busbar_sizing  — copper busbar cross-section for a current
# ═══════════════════════════════════════════════════════════════════════════════

def busbar_sizing(
    *,
    current_a: float,
    thickness_mm: float = 2.0,
    j_max_a_mm2: float = 3.0,
    length_mm: float = 100.0,
    temp_c: float = 25.0,
) -> Dict[str, Any]:
    """
    Copper busbar width and resistance for a given current.

    Parameters
    ----------
    current_a    : busbar current [A]
    thickness_mm : busbar thickness [mm] (default 2.0 mm)
    j_max_a_mm2  : maximum allowable current density [A/mm²] (default 3.0)
    length_mm    : busbar length [mm] (default 100 mm)
    temp_c       : operating temperature [°C] (default 25.0)

    Returns
    -------
    dict with ok, width_mm, cross_section_mm2, resistance_ohm, power_w,
    voltage_drop_v, current_density_a_mm2, warnings
    """
    errs = []
    for name, val in [("current_a", current_a), ("thickness_mm", thickness_mm),
                      ("j_max_a_mm2", j_max_a_mm2), ("length_mm", length_mm)]:
        e = _validate_positive(name, val)
        if e:
            errs.append(e)
    if errs:
        return {"ok": False, "reason": "; ".join(errs)}

    i = float(current_a)
    t_mm = float(thickness_mm)
    j_max = float(j_max_a_mm2)
    l_mm = float(length_mm)

    # Minimum width from current density
    w_mm = i / (j_max * t_mm)
    a_mm2 = w_mm * t_mm

    # Resistance and losses
    rho = _rho_cu(float(temp_c))
    a_m2 = a_mm2 * 1e-6
    l_m = l_mm * 1e-3
    r_ohm = rho * l_m / a_m2
    p_w = i * i * r_ohm
    v_drop = i * r_ohm
    j_actual = i / a_mm2

    warn_msgs: list[str] = []
    if j_actual > j_max * 1.01:
        warnings.warn(
            f"tracecurrent: busbar current density {j_actual:.2f} A/mm² exceeds "
            f"limit {j_max:.2f} A/mm²",
            stacklevel=2,
        )
        warn_msgs.append("overcurrent_density")

    return {
        "ok": True,
        "width_mm": round(w_mm, 3),
        "cross_section_mm2": round(a_mm2, 4),
        "resistance_ohm": round(r_ohm, 8),
        "power_w": round(p_w, 5),
        "voltage_drop_v": round(v_drop, 5),
        "current_density_a_mm2": round(j_actual, 4),
        "current_a": i,
        "thickness_mm": t_mm,
        "length_mm": l_mm,
        "temp_c": float(temp_c),
        "warnings": warn_msgs,
    }
