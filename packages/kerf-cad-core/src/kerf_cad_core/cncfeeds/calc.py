"""
kerf_cad_core.cncfeeds.calc — pure-Python machining feeds & speeds formulas.

Implements thirteen public functions:

  spindle_rpm(vc, diameter)
      Spindle speed from cutting speed and cutter diameter.

  feed_rate(chip_load, teeth, rpm)
      Table feed rate from chip load, number of teeth, and spindle speed.

  mrr_milling(width, depth, feed_rate)
      Material-removal rate for milling.

  mrr_drilling(diameter, feed_per_rev, rpm)
      Material-removal rate for drilling.

  mrr_turning(depth_of_cut, feed_per_rev, vc, diameter)
      Material-removal rate for turning (external/internal).

  cutting_power(mrr, kc, efficiency)
      Spindle cutting power and torque from specific cutting energy Kc.

  tangential_force(kc, chip_load, depth_of_cut, width_of_cut)
      Tangential (main) cutting force from specific cutting energy.

  chip_thinning_factor(radial_engagement, diameter)
      Chip-thinning correction factor for radial engagement < 50%.

  corrected_chip_load(nominal_chip_load, ae, diameter)
      Adjusted chip load accounting for chip thinning.

  tool_deflection(force, overhang, diameter, E)
      Cantilever tool deflection and maximum recommended stickout.

  surface_finish_ra(feed_per_rev, nose_radius)
      Theoretical surface roughness Ra from feed and nose radius.

  drill_thrust_torque(diameter, feed_per_rev, kc, drill_point_angle)
      Drilling thrust force and torque from cutting parameters.

  tapping_speed(pitch, rpm)
      Linear axial feed speed for rigid tapping.

All functions return a plain dict:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

Warning flags (non-fatal, returned in "warnings" list):
  "over_power"              — cutting_power: power exceeds machine spindle rating
  "excessive_deflection"    — tool_deflection: deflection > 0.025 mm or
                              stickout > recommended max
  "chip_load_low"           — feed_rate / corrected_chip_load: chip_load < 0.001 mm
  "chip_load_high"          — feed_rate / corrected_chip_load: chip_load > 0.5 mm
  "chip_thinning_severe"    — chip_thinning_factor: ae/D < 0.05 (very low engagement)

Units
-----
Unless otherwise noted:
  lengths          — millimetres (mm)
  speeds           — m/min  (cutting speed vc)
  rpm              — rev/min
  feed rate        — mm/min
  chip load        — mm/tooth
  MRR              — mm³/min
  power            — Watts (W)
  torque           — N·m
  forces           — Newtons (N)
  Kc               — N/mm²  (specific cutting energy / cutting pressure)
  Ra               — micrometres (µm)
  nose radius      — mm
  stickout/overhang— mm
  E                — GPa (Young's modulus)

References
----------
Machinery's Handbook, 30th ed., §§ "Speeds and Feeds", "Cutting Fluids"
SME Fundamentals of Tool Design, 6th ed.
Sandvik Coromant — General Turning, Milling, Drilling handbooks
Kennametal Machining Data Handbook

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# Kc material table  (N/mm²)
# Approximate median Kc for a reference undeformed chip thickness of 0.1 mm.
# Sources: Sandvik, Kennametal, Machinery's Handbook tables.
# ---------------------------------------------------------------------------

MATERIAL_KC: dict[str, float] = {
    # Steels
    "mild_steel":           1800.0,   # 1020 / S235, ~180 HB
    "medium_carbon_steel":  2200.0,   # 1045, ~200 HB
    "alloy_steel":          2600.0,   # 4140 HT, ~300 HB
    "tool_steel":           3200.0,   # H13, D2 ~50 HRC
    "stainless_304":        2000.0,
    "stainless_316":        2100.0,
    "duplex_stainless":     2400.0,
    # Cast iron
    "grey_cast_iron":       1100.0,
    "ductile_iron":         1500.0,
    # Non-ferrous
    "aluminum_6061":         700.0,
    "aluminum_7075":         800.0,
    "brass":                1000.0,
    "bronze":               1200.0,
    "copper":               1100.0,
    # Exotic / difficult
    "titanium_ti6al4v":     2800.0,
    "inconel_718":          4000.0,
    "hastelloy":            3800.0,
}

# Default spindle power for "over_power" warning if caller doesn't supply one
_DEFAULT_MACHINE_POWER_W = 7500.0   # 7.5 kW typical VMC

# Chip-thinning threshold: ae/D < this triggers "chip_thinning_severe" warning
_CT_SEVERE_THRESHOLD = 0.05

# Tool-deflection warning thresholds
_DEFLECTION_MAX_MM = 0.025          # 25 µm — typical precision machining limit
_STICKOUT_ASPECT_MAX = 4.0          # stickout > 4× diameter = "excessive"

# Chip-load warning thresholds (mm/tooth)
_CHIP_LOAD_LOW = 0.001
_CHIP_LOAD_HIGH = 0.500


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


# ---------------------------------------------------------------------------
# 1. spindle_rpm
# ---------------------------------------------------------------------------

def spindle_rpm(
    vc: float,
    diameter: float,
) -> dict:
    """
    Spindle speed from cutting speed and cutter/workpiece diameter.

    Parameters
    ----------
    vc : float
        Cutting speed (m/min).  Must be > 0.
    diameter : float
        Cutter or workpiece diameter (mm).  Must be > 0.

    Returns
    -------
    dict
        ok        : True
        rpm       : spindle speed (rev/min)
        vc_m_min  : cutting speed used (m/min)
        diameter_mm: diameter used (mm)
        warnings  : []

    Formula (Machinery's Handbook)
    -------
        n = 1000 × vc / (π × D)

    where vc is in m/min and D is in mm.
    """
    err = _guard_positive("vc", vc)
    if err:
        return _err(err)
    err = _guard_positive("diameter", diameter)
    if err:
        return _err(err)

    vc_val = float(vc)
    d = float(diameter)

    rpm = (1000.0 * vc_val) / (math.pi * d)

    return {
        "ok": True,
        "rpm": rpm,
        "vc_m_min": vc_val,
        "diameter_mm": d,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# 2. feed_rate
# ---------------------------------------------------------------------------

def feed_rate(
    chip_load: float,
    teeth: int,
    rpm: float,
    *,
    chip_load_min: float = _CHIP_LOAD_LOW,
    chip_load_max: float = _CHIP_LOAD_HIGH,
) -> dict:
    """
    Table feed rate from chip load (fz), number of teeth (z), and RPM.

    Parameters
    ----------
    chip_load : float
        Chip load per tooth (mm/tooth).  Must be > 0.
    teeth : int
        Number of cutter teeth / flutes.  Must be >= 1.
    rpm : float
        Spindle speed (rev/min).  Must be > 0.
    chip_load_min : float
        Lower chip-load threshold for "chip_load_low" warning (default 0.001 mm).
    chip_load_max : float
        Upper chip-load threshold for "chip_load_high" warning (default 0.5 mm).

    Returns
    -------
    dict
        ok           : True
        feed_mm_min  : table feed rate (mm/min)
        chip_load_mm : chip load used (mm/tooth)
        teeth        : number of teeth
        rpm          : spindle speed (rev/min)
        warnings     : list of warning strings

    Formula
    -------
        Vf = fz × z × n
    """
    err = _guard_positive("chip_load", chip_load)
    if err:
        return _err(err)
    err = _guard_positive("rpm", rpm)
    if err:
        return _err(err)
    try:
        z = int(teeth)
    except (TypeError, ValueError):
        return _err(f"teeth must be an integer, got {teeth!r}")
    if z < 1:
        return _err(f"teeth must be >= 1, got {z}")

    fz = float(chip_load)
    n = float(rpm)
    warnings: list[str] = []

    if fz < chip_load_min:
        warnings.append("chip_load_low")
    if fz > chip_load_max:
        warnings.append("chip_load_high")

    vf = fz * z * n

    return {
        "ok": True,
        "feed_mm_min": vf,
        "chip_load_mm": fz,
        "teeth": z,
        "rpm": n,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. mrr_milling
# ---------------------------------------------------------------------------

def mrr_milling(
    width: float,
    depth: float,
    feed_mm_min: float,
) -> dict:
    """
    Material-removal rate for milling.

    Parameters
    ----------
    width : float
        Width of cut / radial engagement ae (mm).  Must be > 0.
    depth : float
        Depth of cut / axial engagement ap (mm).  Must be > 0.
    feed_mm_min : float
        Table feed rate Vf (mm/min).  Must be > 0.

    Returns
    -------
    dict
        ok           : True
        mrr_mm3_min  : material-removal rate (mm³/min)
        width_mm     : width of cut used (mm)
        depth_mm     : depth of cut used (mm)
        feed_mm_min  : feed rate used (mm/min)
        warnings     : []

    Formula (Sandvik milling handbook)
    -------
        Q = ae × ap × Vf       [mm³/min]
    """
    for name, val in [("width", width), ("depth", depth), ("feed_mm_min", feed_mm_min)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    ae = float(width)
    ap = float(depth)
    vf = float(feed_mm_min)

    mrr = ae * ap * vf

    return {
        "ok": True,
        "mrr_mm3_min": mrr,
        "width_mm": ae,
        "depth_mm": ap,
        "feed_mm_min": vf,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# 4. mrr_drilling
# ---------------------------------------------------------------------------

def mrr_drilling(
    diameter: float,
    feed_per_rev: float,
    rpm: float,
) -> dict:
    """
    Material-removal rate for drilling.

    Parameters
    ----------
    diameter : float
        Drill diameter (mm).  Must be > 0.
    feed_per_rev : float
        Feed per revolution (mm/rev).  Must be > 0.
    rpm : float
        Spindle speed (rev/min).  Must be > 0.

    Returns
    -------
    dict
        ok           : True
        mrr_mm3_min  : material-removal rate (mm³/min)
        feed_mm_min  : resulting linear feed rate (mm/min)
        diameter_mm  : drill diameter (mm)
        feed_per_rev_mm: feed per revolution (mm/rev)
        rpm          : spindle speed (rev/min)
        warnings     : []

    Formula
    -------
        Q = (π/4) × D² × f × n       [mm³/min]
    """
    for name, val in [("diameter", diameter), ("feed_per_rev", feed_per_rev), ("rpm", rpm)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    d = float(diameter)
    f = float(feed_per_rev)
    n = float(rpm)

    feed_mm_min = f * n
    mrr = (math.pi / 4.0) * d ** 2 * feed_mm_min

    return {
        "ok": True,
        "mrr_mm3_min": mrr,
        "feed_mm_min": feed_mm_min,
        "diameter_mm": d,
        "feed_per_rev_mm": f,
        "rpm": n,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# 5. mrr_turning
# ---------------------------------------------------------------------------

def mrr_turning(
    depth_of_cut: float,
    feed_per_rev: float,
    vc: float,
) -> dict:
    """
    Material-removal rate for turning (external or internal).

    Parameters
    ----------
    depth_of_cut : float
        Radial depth of cut ap (mm).  Must be > 0.
    feed_per_rev : float
        Feed per revolution fn (mm/rev).  Must be > 0.
    vc : float
        Cutting speed (m/min).  Must be > 0.

    Returns
    -------
    dict
        ok              : True
        mrr_mm3_min     : material-removal rate (mm³/min)
        depth_of_cut_mm : depth of cut (mm)
        feed_per_rev_mm : feed per revolution (mm/rev)
        vc_m_min        : cutting speed (m/min)
        warnings        : []

    Formula (Sandvik turning handbook)
    -------
        Q = ap × fn × vc × 1000        [mm³/min]

    The ×1000 converts vc from m/min to mm/min.
    """
    for name, val in [("depth_of_cut", depth_of_cut), ("feed_per_rev", feed_per_rev), ("vc", vc)]:
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    ap = float(depth_of_cut)
    fn = float(feed_per_rev)
    vc_val = float(vc)

    mrr = ap * fn * vc_val * 1000.0

    return {
        "ok": True,
        "mrr_mm3_min": mrr,
        "depth_of_cut_mm": ap,
        "feed_per_rev_mm": fn,
        "vc_m_min": vc_val,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# 6. cutting_power
# ---------------------------------------------------------------------------

def cutting_power(
    mrr: float,
    kc: float,
    *,
    efficiency: float = 0.85,
    machine_power_W: float = _DEFAULT_MACHINE_POWER_W,
    rpm: float | None = None,
    diameter_mm: float | None = None,
) -> dict:
    """
    Spindle cutting power and torque from specific cutting energy Kc.

    Parameters
    ----------
    mrr : float
        Material-removal rate (mm³/min).  Must be > 0.
    kc : float
        Specific cutting energy (N/mm²).  Use MATERIAL_KC[...] as reference.
        Must be > 0.
    efficiency : float
        Spindle mechanical efficiency (0 < η <= 1, default 0.85).
    machine_power_W : float
        Machine spindle rated power (W, default 7500 W).  Used only to set
        the "over_power" warning flag.
    rpm : float | None
        Spindle speed (rev/min).  If provided together with diameter_mm,
        the spindle torque is also computed via the force path.
    diameter_mm : float | None
        Cutter diameter (mm).  Required for torque calculation.

    Returns
    -------
    dict
        ok              : True
        cutting_power_W : required cutting power at the tool (W)
        spindle_power_W : required spindle power (cutting_power / efficiency)
        torque_Nm       : spindle torque (N·m) — present if rpm & diameter given
        mrr_mm3_min     : MRR used (mm³/min)
        kc_N_mm2        : Kc used (N/mm²)
        efficiency      : mechanical efficiency used
        warnings        : list of warning strings

    Formula
    -------
        Pc = kc × Q / 60000      [W]   (converts mm³/min → mm³/s, kc in N/mm² = N/mm² = J/mm³)
             actually: Pc [W] = kc [N/mm²] × Q [mm³/min] / 60 000
             because  1 N/mm² × 1 mm³/s = 1 W  and  1 mm³/min = 1/60000 m³/s ... let's be precise:
             Pc [W] = kc [N/mm²] × Q [mm³/min] × (1 m³ / 1e9 mm³) × (1 min / 60 s) × 1e9
                    = kc × Q / 60
             Wait — units check:
             kc [N/mm²] = [N/mm²]; Q [mm³/min]
             Power = Force × velocity = N × m/s
             kc × Q = N/mm² × mm³/min = N·mm/min
             N·mm/min → W:  N·mm/min × (1 m / 1000 mm) × (1 min / 60 s) = N·m/(60000 s) = W/60000
             So: Pc [W] = kc [N/mm²] × Q [mm³/min] / 60000

        Ps = Pc / η

        Torque (if rpm and diameter available):
        Ft = kc × ap × ae / (tooth pitch) — but simpler via power:
        T = Ps × 60 / (2π × n)      [N·m]
    """
    err = _guard_positive("mrr", mrr)
    if err:
        return _err(err)
    err = _guard_positive("kc", kc)
    if err:
        return _err(err)
    err = _guard_positive("efficiency", efficiency)
    if err:
        return _err(err)
    if float(efficiency) > 1.0:
        return _err(f"efficiency must be <= 1.0, got {efficiency}")

    q = float(mrr)
    kc_val = float(kc)
    eta = float(efficiency)

    pc = kc_val * q / 60000.0    # cutting power at tool (W)
    ps = pc / eta                 # required spindle power (W)

    warnings: list[str] = []
    if ps > float(machine_power_W):
        warnings.append("over_power")

    result: dict = {
        "ok": True,
        "cutting_power_W": pc,
        "spindle_power_W": ps,
        "mrr_mm3_min": q,
        "kc_N_mm2": kc_val,
        "efficiency": eta,
        "warnings": warnings,
    }

    # Optional torque via power × RPM relationship
    if rpm is not None and diameter_mm is not None:
        err = _guard_positive("rpm", rpm)
        if err:
            return _err(err)
        err = _guard_positive("diameter_mm", diameter_mm)
        if err:
            return _err(err)
        n = float(rpm)
        torque = ps * 60.0 / (2.0 * math.pi * n)
        result["torque_Nm"] = torque
        result["rpm"] = n
        result["diameter_mm"] = float(diameter_mm)

    return result


# ---------------------------------------------------------------------------
# 7. tangential_force
# ---------------------------------------------------------------------------

def tangential_force(
    kc: float,
    chip_load: float,
    depth_of_cut: float,
    *,
    width_of_cut: float = 1.0,
) -> dict:
    """
    Tangential (main) cutting force from specific cutting energy.

    Parameters
    ----------
    kc : float
        Specific cutting energy (N/mm²).  Must be > 0.
    chip_load : float
        Undeformed chip thickness / chip load fz (mm).  Must be > 0.
    depth_of_cut : float
        Axial depth of cut ap (mm).  Must be > 0.
    width_of_cut : float
        Width of cut ae (mm, default 1.0 — used as unit width for turning/drilling).
        Must be > 0.

    Returns
    -------
    dict
        ok              : True
        tangential_N    : tangential cutting force Ft (N)
        kc_N_mm2        : Kc used (N/mm²)
        chip_load_mm    : chip load used (mm)
        depth_of_cut_mm : axial depth of cut (mm)
        width_of_cut_mm : width/radial engagement (mm)
        warnings        : []

    Formula
    -------
        Ft = kc × fz × ap × ae / ae = kc × fz × ap
        (for a unit chip cross-section: Ft = kc × fz × ap)
        More precisely for milling:
            Ft = kc × (fz × ae/D)^m × ap × ae
        but the simplified Ft = kc × ap × fz is the standard first-order
        approximation used in handbooks for a single tooth in cut.

        Full form (with width):
            Ft = kc × chip_load × depth_of_cut × width_of_cut   [N]
        where kc is in N/mm², dimensions in mm.
    """
    err = _guard_positive("kc", kc)
    if err:
        return _err(err)
    err = _guard_positive("chip_load", chip_load)
    if err:
        return _err(err)
    err = _guard_positive("depth_of_cut", depth_of_cut)
    if err:
        return _err(err)
    err = _guard_positive("width_of_cut", width_of_cut)
    if err:
        return _err(err)

    kc_val = float(kc)
    fz = float(chip_load)
    ap = float(depth_of_cut)
    ae = float(width_of_cut)

    ft = kc_val * fz * ap * ae

    return {
        "ok": True,
        "tangential_N": ft,
        "kc_N_mm2": kc_val,
        "chip_load_mm": fz,
        "depth_of_cut_mm": ap,
        "width_of_cut_mm": ae,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# 8. chip_thinning_factor
# ---------------------------------------------------------------------------

def chip_thinning_factor(
    radial_engagement: float,
    diameter: float,
) -> dict:
    """
    Chip-thinning correction factor for radial engagement < 50%.

    When ae < D/2 the actual chip thickness is less than the programmed chip
    load.  The chip-thinning factor (CTF) must be applied to maintain the
    desired chip thickness and avoid rubbing / tool wear.

    Parameters
    ----------
    radial_engagement : float
        Radial engagement ae (mm).  Must be > 0 and <= diameter.
    diameter : float
        Cutter diameter D (mm).  Must be > 0.

    Returns
    -------
    dict
        ok              : True
        ctf             : chip-thinning factor (dimensionless, >= 1.0)
        ae_over_D       : engagement ratio ae/D
        radial_engagement_mm : ae used (mm)
        diameter_mm     : D used (mm)
        warnings        : list of warning strings

    Formula (Sandvik / Kennametal)
    -------
        CTF = D / (2 × √(ae × (D - ae)))      when ae < D/2
        CTF = 1.0                               when ae >= D/2

    This is derived from the geometric relationship:
        actual chip thickness = fz × sin(ψ)
        where ψ is the cutter engagement half-angle = arccos(1 - 2ae/D).
        CTF = 1 / sin(ψ) for small angles.
    """
    err = _guard_positive("radial_engagement", radial_engagement)
    if err:
        return _err(err)
    err = _guard_positive("diameter", diameter)
    if err:
        return _err(err)

    ae = float(radial_engagement)
    d = float(diameter)

    if ae > d:
        return _err(
            f"radial_engagement ({ae} mm) cannot exceed diameter ({d} mm)"
        )

    ratio = ae / d
    warnings: list[str] = []

    if ratio < _CT_SEVERE_THRESHOLD:
        warnings.append("chip_thinning_severe")

    if ae >= d / 2.0:
        ctf = 1.0
    else:
        radicand = ae * (d - ae)
        if radicand <= 0:
            ctf = 1.0
        else:
            ctf = d / (2.0 * math.sqrt(radicand))

    return {
        "ok": True,
        "ctf": ctf,
        "ae_over_D": ratio,
        "radial_engagement_mm": ae,
        "diameter_mm": d,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 9. corrected_chip_load
# ---------------------------------------------------------------------------

def corrected_chip_load(
    nominal_chip_load: float,
    ae: float,
    diameter: float,
    *,
    chip_load_min: float = _CHIP_LOAD_LOW,
    chip_load_max: float = _CHIP_LOAD_HIGH,
) -> dict:
    """
    Adjusted chip load accounting for chip thinning.

    The programmed chip load must be increased by the chip-thinning factor so
    that the actual chip thickness equals the target.

    Parameters
    ----------
    nominal_chip_load : float
        Target chip load (actual undeformed chip thickness) fz_target (mm).
        Must be > 0.
    ae : float
        Radial engagement (mm).  Must be > 0 and <= diameter.
    diameter : float
        Cutter diameter (mm).  Must be > 0.

    Returns
    -------
    dict
        ok                      : True
        programmed_chip_load_mm : chip load to program (mm/tooth)
        target_chip_load_mm     : target actual chip load (mm/tooth)
        ctf                     : chip-thinning factor applied
        ae_over_D               : engagement ratio
        warnings                : list of warning strings
    """
    err = _guard_positive("nominal_chip_load", nominal_chip_load)
    if err:
        return _err(err)

    ct = chip_thinning_factor(ae, diameter)
    if not ct["ok"]:
        return ct

    fz_target = float(nominal_chip_load)
    ctf = ct["ctf"]
    programmed = fz_target * ctf

    warnings: list[str] = list(ct["warnings"])
    if fz_target < chip_load_min:
        warnings.append("chip_load_low")
    if fz_target > chip_load_max:
        warnings.append("chip_load_high")

    return {
        "ok": True,
        "programmed_chip_load_mm": programmed,
        "target_chip_load_mm": fz_target,
        "ctf": ctf,
        "ae_over_D": ct["ae_over_D"],
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 10. tool_deflection
# ---------------------------------------------------------------------------

def tool_deflection(
    force: float,
    overhang: float,
    diameter: float,
    *,
    E_GPa: float = 600.0,
    deflection_warn_mm: float = _DEFLECTION_MAX_MM,
    stickout_aspect_warn: float = _STICKOUT_ASPECT_MAX,
) -> dict:
    """
    Cantilever tool deflection and maximum recommended stickout.

    Models the tool shank as a cantilever beam with a point load at the tip.

    Parameters
    ----------
    force : float
        Transverse cutting force at tool tip (N).  Must be > 0.
    overhang : float
        Tool stickout / overhang from spindle face (mm).  Must be > 0.
    diameter : float
        Shank diameter (mm).  Must be > 0.
    E_GPa : float
        Young's modulus of tool shank (GPa, default 600 GPa for carbide).
        Steel ≈ 210 GPa, HSS ≈ 210 GPa, solid carbide ≈ 580–620 GPa.
    deflection_warn_mm : float
        Deflection threshold for "excessive_deflection" warning (default 0.025 mm).
    stickout_aspect_warn : float
        Stickout/diameter ratio threshold for stickout warning (default 4×).

    Returns
    -------
    dict
        ok                     : True
        deflection_mm          : tip deflection δ (mm)
        max_stickout_mm        : max stickout for deflection_warn_mm (mm)
        force_N                : force used (N)
        overhang_mm            : stickout used (mm)
        diameter_mm            : shank diameter (mm)
        E_GPa                  : Young's modulus used (GPa)
        warnings               : list of warning strings

    Formula (cantilever beam, point load at free end)
    -------
        I = π × D⁴ / 64    (second moment of area, mm⁴)
        EI = E × I          (E in N/mm², I in mm⁴  →  EI in N·mm²)
        δ = F × L³ / (3 × EI)   (mm)

        Max stickout for δ_limit:
        L_max = (3 × EI × δ_limit / F)^(1/3)
    """
    err = _guard_positive("force", force)
    if err:
        return _err(err)
    err = _guard_positive("overhang", overhang)
    if err:
        return _err(err)
    err = _guard_positive("diameter", diameter)
    if err:
        return _err(err)
    err = _guard_positive("E_GPa", E_GPa)
    if err:
        return _err(err)

    F = float(force)
    L = float(overhang)
    D = float(diameter)
    E_Nmm2 = float(E_GPa) * 1e3    # GPa → N/mm²

    I = math.pi * D ** 4 / 64.0    # mm⁴
    EI = E_Nmm2 * I                 # N·mm²

    deflection = F * L ** 3 / (3.0 * EI)

    # Max stickout for warn threshold
    max_stickout = (3.0 * EI * float(deflection_warn_mm) / F) ** (1.0 / 3.0)

    warnings: list[str] = []
    if deflection > float(deflection_warn_mm):
        warnings.append("excessive_deflection")
    if L / D > float(stickout_aspect_warn):
        warnings.append("excessive_deflection")
    # Deduplicate
    warnings = list(dict.fromkeys(warnings))

    return {
        "ok": True,
        "deflection_mm": deflection,
        "max_stickout_mm": max_stickout,
        "force_N": F,
        "overhang_mm": L,
        "diameter_mm": D,
        "E_GPa": E_GPa,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 11. surface_finish_ra
# ---------------------------------------------------------------------------

def surface_finish_ra(
    feed_per_rev: float,
    nose_radius: float,
) -> dict:
    """
    Theoretical surface roughness Ra from feed per revolution and nose radius.

    This is the kinematic surface finish formula for turning (also applied as
    an approximation to milling with ball-end mills and round inserts).

    Parameters
    ----------
    feed_per_rev : float
        Feed per revolution fn (mm/rev).  Must be > 0.
    nose_radius : float
        Tool nose radius r_ε (mm).  Must be > 0.

    Returns
    -------
    dict
        ok              : True
        Ra_um           : theoretical Ra (µm)
        Rz_um           : theoretical Rz ≈ 4 × Ra (µm) — peak-to-valley estimate
        feed_per_rev_mm : feed used (mm/rev)
        nose_radius_mm  : nose radius used (mm)
        warnings        : []

    Formula (Machinery's Handbook)
    -------
        Rmax = fn² / (8 × r_ε)          [mm]  (peak-to-valley theoretical height)
        Ra   ≈ Rmax / 4                  [mm]  (Ra ≈ Rmax/4 for ideal sinusoidal)
        Ra   [µm] = (fn² / (8 × r_ε)) × 1000 / 4
                  = fn² × 1000 / (32 × r_ε)
    """
    err = _guard_positive("feed_per_rev", feed_per_rev)
    if err:
        return _err(err)
    err = _guard_positive("nose_radius", nose_radius)
    if err:
        return _err(err)

    fn = float(feed_per_rev)
    re = float(nose_radius)

    rmax_mm = fn ** 2 / (8.0 * re)      # mm
    Ra_um = rmax_mm * 1000.0 / 4.0      # µm  (Ra ≈ Rmax/4)
    Rz_um = rmax_mm * 1000.0            # µm  (Rz ≈ Rmax)

    return {
        "ok": True,
        "Ra_um": Ra_um,
        "Rz_um": Rz_um,
        "feed_per_rev_mm": fn,
        "nose_radius_mm": re,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# 12. drill_thrust_torque
# ---------------------------------------------------------------------------

def drill_thrust_torque(
    diameter: float,
    feed_per_rev: float,
    kc: float,
    *,
    drill_point_angle: float = 118.0,
) -> dict:
    """
    Drilling thrust force and torque from cutting parameters.

    Uses empirical formulas from Machinery's Handbook / Sandvik Drilling
    Handbook based on specific cutting energy.

    Parameters
    ----------
    diameter : float
        Drill diameter D (mm).  Must be > 0.
    feed_per_rev : float
        Feed per revolution fn (mm/rev).  Must be > 0.
    kc : float
        Specific cutting energy of workpiece material (N/mm²).  Must be > 0.
    drill_point_angle : float
        Included drill point angle (degrees, default 118° for standard twist).
        Must be in range (0, 180) exclusive.

    Returns
    -------
    dict
        ok                  : True
        thrust_N            : axial thrust force (N)
        torque_Nm           : drilling torque (N·m)
        diameter_mm         : drill diameter (mm)
        feed_per_rev_mm     : feed used (mm/rev)
        kc_N_mm2            : Kc used (N/mm²)
        drill_point_angle_deg: point angle used (degrees)
        warnings            : []

    Formulas (Sandvik Drilling Handbook / Machinery's Handbook)
    -------
    Half point angle κ = drill_point_angle / 2  (radians)

    Chip thickness (per lip):
        hm = fn / 2 × sin(κ)

    Thrust force (both cutting lips):
        Ff = kc × fn × (D/2) × sin(κ)          [N]

    Torque:
        Mc = kc × fn × D² / 8                   [N·mm]  → /1000 for N·m
    """
    err = _guard_positive("diameter", diameter)
    if err:
        return _err(err)
    err = _guard_positive("feed_per_rev", feed_per_rev)
    if err:
        return _err(err)
    err = _guard_positive("kc", kc)
    if err:
        return _err(err)

    pa = float(drill_point_angle)
    if not (0 < pa < 180):
        return _err(f"drill_point_angle must be in (0, 180) degrees, got {pa}")

    d = float(diameter)
    fn = float(feed_per_rev)
    kc_val = float(kc)

    kappa_rad = math.radians(pa / 2.0)
    sin_kappa = math.sin(kappa_rad)

    # Thrust force
    thrust = kc_val * fn * (d / 2.0) * sin_kappa   # N

    # Torque: Mc = kc × fn × D² / 8    [N·mm]
    torque_Nmm = kc_val * fn * d ** 2 / 8.0
    torque_Nm = torque_Nmm / 1000.0

    return {
        "ok": True,
        "thrust_N": thrust,
        "torque_Nm": torque_Nm,
        "diameter_mm": d,
        "feed_per_rev_mm": fn,
        "kc_N_mm2": kc_val,
        "drill_point_angle_deg": pa,
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# 13. tapping_speed
# ---------------------------------------------------------------------------

def tapping_speed(
    pitch: float,
    rpm: float,
) -> dict:
    """
    Linear axial feed speed for rigid tapping.

    For rigid (synchronised) tapping, the axial feed must exactly equal
    pitch × RPM to avoid thread damage.

    Parameters
    ----------
    pitch : float
        Thread pitch p (mm/rev).  Must be > 0.
        Metric M: pitch in mm (e.g. M8×1.25 → pitch=1.25).
        Unified/UNC: convert to mm (e.g. 1/TPI × 25.4).
    rpm : float
        Spindle speed (rev/min).  Must be > 0.

    Returns
    -------
    dict
        ok           : True
        feed_mm_min  : required axial feed rate (mm/min)
        pitch_mm     : pitch used (mm/rev)
        rpm          : spindle speed (rev/min)
        warnings     : []

    Formula
    -------
        Vf = p × n      [mm/min]
    """
    err = _guard_positive("pitch", pitch)
    if err:
        return _err(err)
    err = _guard_positive("rpm", rpm)
    if err:
        return _err(err)

    p = float(pitch)
    n = float(rpm)

    vf = p * n

    return {
        "ok": True,
        "feed_mm_min": vf,
        "pitch_mm": p,
        "rpm": n,
        "warnings": [],
    }
