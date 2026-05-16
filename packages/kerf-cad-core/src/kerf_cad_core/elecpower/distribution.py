"""
kerf_cad_core.elecpower.distribution — NEC building/industrial power distribution.

Implements pure-Python NEC calculations for building-scale electrical distribution.
All functions return plain dicts:
    success → {"ok": True, ...computed fields..., "warnings": [...]}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.

Scope is NEC building distribution — not device-level electronics (PDN/EMI),
arc-flash/creepage (elecsafety), or relay/protection coordination.

NEC References (NFPA 70, 2023 edition)
---------------------------------------
Art. 220  — Load calculations, demand factors, continuous-load 125%
Art. 240  — Overcurrent protection, standard device sizes (240.6)
Art. 250  — Grounding-electrode conductor (250.66), EGC (250.122)
Art. 310  — Conductor ampacity tables (310.16), correction/bundling factors
Art. 430  — Motor branch circuits: FLC tables, conductor sizing, OCPD
Art. 450  — Transformer sizing and feeder protection

Units
-----
Voltages    — Volts (V)
Currents    — Amperes (A)
Power       — Watts (W) or VA (volt-amperes)
Impedances  — Ohms (Ω)
Lengths     — Feet (ft) for NEC tables; internally converted
Wire sizes  — AWG / kcmil strings e.g. "12", "10", "1/0", "4/0", "250", "500"
Temperatures — Celsius (°C)

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import Any


# ---------------------------------------------------------------------------
# NEC 310.16 Ampacity table — 75°C column, copper, in conduit (most common)
# Keys are AWG/kcmil size strings; values are (ampacity_75C, area_cmil)
# area_cmil used for conduit fill per Ch.9
# ---------------------------------------------------------------------------

# fmt: off
_AMPACITY_CU_75C: dict[str, tuple[float, float]] = {
    # AWG  (amps_75C, area_cmil)
    "14":   (20.0,    4110.0),
    "12":   (25.0,    6530.0),
    "10":   (35.0,   10380.0),
    "8":    (50.0,   16510.0),
    "6":    (65.0,   26240.0),
    "4":    (85.0,   41740.0),
    "3":    (100.0,  52620.0),
    "2":    (115.0,  66360.0),
    "1":    (130.0,  83690.0),
    "1/0":  (150.0, 105600.0),
    "2/0":  (175.0, 133100.0),
    "3/0":  (200.0, 167800.0),
    "4/0":  (230.0, 211600.0),
    "250":  (255.0, 250000.0),
    "300":  (285.0, 300000.0),
    "350":  (310.0, 350000.0),
    "400":  (335.0, 400000.0),
    "500":  (380.0, 500000.0),
    "600":  (420.0, 600000.0),
    "700":  (460.0, 700000.0),
    "750":  (475.0, 750000.0),
    "1000": (545.0, 1000000.0),
}

# Aluminum 75°C ampacity (NEC 310.16, Al column)
_AMPACITY_AL_75C: dict[str, tuple[float, float]] = {
    "12":   (20.0,    6530.0),
    "10":   (30.0,   10380.0),
    "8":    (40.0,   16510.0),
    "6":    (50.0,   26240.0),
    "4":    (65.0,   41740.0),
    "3":    (75.0,   52620.0),
    "2":    (90.0,   66360.0),
    "1":    (100.0,  83690.0),
    "1/0":  (120.0, 105600.0),
    "2/0":  (135.0, 133100.0),
    "3/0":  (155.0, 167800.0),
    "4/0":  (180.0, 211600.0),
    "250":  (205.0, 250000.0),
    "300":  (230.0, 300000.0),
    "350":  (250.0, 350000.0),
    "400":  (270.0, 400000.0),
    "500":  (310.0, 500000.0),
    "600":  (340.0, 600000.0),
    "700":  (375.0, 700000.0),
    "750":  (385.0, 750000.0),
    "1000": (445.0, 1000000.0),
}
# fmt: on

# Ordered list for upsizing
_SIZE_ORDER = [
    "14", "12", "10", "8", "6", "4", "3", "2", "1",
    "1/0", "2/0", "3/0", "4/0",
    "250", "300", "350", "400", "500", "600", "700", "750", "1000",
]

# NEC 310.15(B)(2)(a) ambient temperature correction factors for 75°C rated conductors
# Key: ambient °C threshold (max); value: correction factor
_AMBIENT_CORRECTION_75C: list[tuple[float, float]] = [
    (10, 1.20),
    (15, 1.15),
    (20, 1.11),
    (25, 1.05),
    (30, 1.00),
    (35, 0.94),
    (40, 0.88),
    (45, 0.82),
    (50, 0.75),
    (55, 0.67),
    (60, 0.58),
    (70, 0.33),
    (75, 0.00),
]

# NEC 310.15(C)(1) [2023] / 310.15(B)(3)(a) [pre-2017] adjustment factors for
# more than three current-carrying conductors in a raceway or cable.
# Key: max number of current-carrying conductors; value: adjustment factor.
#   4–6   → 80%
#   7–9   → 70%
#   10–20 → 50%
#   21–30 → 45%
#   31–40 → 40%
#   41+   → 35%
_BUNDLING_FACTORS: list[tuple[int, float]] = [
    (3,  1.00),
    (6,  0.80),
    (9,  0.70),
    (20, 0.50),
    (30, 0.45),
    (40, 0.40),
    (41, 0.35),  # >40
]

# NEC 240.6(A) standard overcurrent device sizes (A)
_STANDARD_OCPD = [
    15, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100,
    110, 125, 150, 175, 200, 225, 250, 300, 350, 400, 450, 500,
    600, 700, 800, 1000, 1200, 1600, 2000, 2500, 3000, 4000, 5000, 6000,
]

# NEC 430.248 single-phase AC motor FLC table (A at 115V / 230V)
# (hp, amps_115V, amps_230V)
_MOTOR_FLC_1PH: list[tuple[float, float, float]] = [
    (1/6,  4.4,  2.2),
    (1/4,  5.8,  2.9),
    (1/3,  7.2,  3.6),
    (1/2,  9.8,  4.9),
    (3/4, 13.8,  6.9),
    (1.0, 16.0,  8.0),
    (1.5, 20.0, 10.0),
    (2.0, 24.0, 12.0),
    (3.0, 34.0, 17.0),
    (5.0, 56.0, 28.0),
    (7.5, 80.0, 40.0),
    (10.0, 100.0, 50.0),
]

# NEC 430.250 three-phase AC motor FLC table at 460V
# (hp, amps_460V)
_MOTOR_FLC_3PH_460: list[tuple[float, float]] = [
    (0.5,  1.1),
    (0.75, 1.6),
    (1.0,  2.1),
    (1.5,  3.0),
    (2.0,  3.4),
    (3.0,  4.8),
    (5.0,  7.6),
    (7.5, 11.0),
    (10.0, 14.0),
    (15.0, 21.0),
    (20.0, 27.0),
    (25.0, 34.0),
    (30.0, 40.0),
    (40.0, 52.0),
    (50.0, 65.0),
    (60.0, 77.0),
    (75.0, 96.0),
    (100.0, 124.0),
    (125.0, 156.0),
    (150.0, 180.0),
    (200.0, 240.0),
    (250.0, 302.0),
    (300.0, 361.0),
    (350.0, 414.0),
    (400.0, 477.0),
    (450.0, 515.0),
    (500.0, 590.0),
]

# NEC 250.66 Grounding-electrode conductor size (based on service-entrance conductor)
# (se_conductor_size_index_max, gec_size)  — index into _SIZE_ORDER
_GEC_TABLE: list[tuple[int, str]] = [
    (3,  "8"),    # service up to AWG 8 (index 3) → GEC 8
    (5,  "6"),    # up to AWG 4
    (7,  "4"),    # up to AWG 2
    (9,  "2"),    # up to AWG 1/0
    (10, "2"),    # up to 2/0
    (11, "0"),    # we handle this below — actually 2/0 → 1/0 GEC is complex
    # Simplified from NEC 250.66 table:
    # Service ≤ 2 AWG (cu) → GEC 8 Cu or 6 Al
    # Service ≤ 1/0 → GEC 6 Cu or 4 Al
    # Service ≤ 3/0 → GEC 4 Cu or 2 Al
    # Service ≤ 350 kcmil → GEC 2 Cu or 1/0 Al
    # Service > 350 kcmil → GEC 0 (see below)
]

# Simplified NEC 250.66 GEC sizing (Cu) based on service-entrance conductor kcmil
# (max_kcmil_or_awg_area, gec_size_cu)
def _gec_size_cu(se_size: str) -> str:
    """Return GEC copper size per NEC 250.66."""
    idx = _SIZE_ORDER.index(se_size) if se_size in _SIZE_ORDER else -1
    if idx < 0:
        return "8"
    # NEC 250.66 table simplified
    se_area = _AMPACITY_CU_75C.get(se_size, (0, 0))[1]
    if se_area <= _AMPACITY_CU_75C["2"][1]:      # ≤ AWG 2
        return "8"
    elif se_area <= _AMPACITY_CU_75C["1/0"][1]:  # ≤ 1/0
        return "6"
    elif se_area <= _AMPACITY_CU_75C["3/0"][1]:  # ≤ 3/0
        return "4"
    elif se_area <= 350000.0:                     # ≤ 350 kcmil
        return "2"
    elif se_area <= 600000.0:                     # ≤ 600 kcmil
        return "1/0"
    elif se_area <= 1100000.0:                    # ≤ 1100 kcmil
        return "2/0"
    else:
        return "3/0"


# NEC 250.122 EGC sizing (Cu) based on OCPD rating (A)
# (max_ocpd_A, egc_size_cu)
_EGC_TABLE: list[tuple[float, str]] = [
    (15,    "14"),
    (20,    "12"),
    (60,    "10"),
    (100,   "8"),
    (200,   "6"),
    (300,   "4"),
    (400,   "3"),
    (500,   "2"),
    (600,   "1"),
    (800,   "1/0"),
    (1000,  "2/0"),
    (1200,  "3/0"),
    (1600,  "4/0"),
    (2000,  "250"),
    (2500,  "350"),
    (3000,  "400"),
    (4000,  "500"),
    (5000,  "700"),
    (6000,  "800"),  # not in _SIZE_ORDER, clamp to 1000
]

# NEC Ch.9 Table 5 — conductor outer area (in²) for conduit fill (approximate)
# Using circular mil area / 1273240 to get in² approximation
def _conductor_area_in2(size: str, material: str = "cu") -> float:
    """Approximate conductor cross-section area (in²) for conduit-fill calcs.
    Uses NEC Ch.9 Table 5 approach: area proportional to circular mil area.
    """
    table = _AMPACITY_CU_75C if material == "cu" else _AMPACITY_AL_75C
    entry = table.get(size)
    if entry is None:
        return 0.0
    cmil = entry[1]
    # 1 circular mil = π/4 × (0.001 in)² = 7.854e-7 in²
    bare_area_in2 = cmil * 7.854e-7
    # Add insulation: approximate as 1.4× bare area for 600V THWN conductors
    return bare_area_in2 * 1.4


# ---------------------------------------------------------------------------
# NEC conductor resistance (Ω/1000 ft) for voltage-drop calculations
# Source: NEC Ch.9 Table 9, 75°C, copper/aluminum in conduit
# ---------------------------------------------------------------------------
_R_CU_OHMS_PER_KFT: dict[str, float] = {
    "14": 3.14, "12": 1.98, "10": 1.24, "8": 0.778,
    "6": 0.491, "4": 0.308, "3": 0.245, "2": 0.194,
    "1": 0.154, "1/0": 0.122, "2/0": 0.0967, "3/0": 0.0766,
    "4/0": 0.0608, "250": 0.0515, "300": 0.0429, "350": 0.0367,
    "400": 0.0321, "500": 0.0258, "600": 0.0214, "700": 0.0184,
    "750": 0.0171, "1000": 0.0129,
}

_R_AL_OHMS_PER_KFT: dict[str, float] = {
    "12": 3.18, "10": 2.00, "8": 1.26,
    "6": 0.808, "4": 0.508, "3": 0.403, "2": 0.319,
    "1": 0.253, "1/0": 0.201, "2/0": 0.159, "3/0": 0.126,
    "4/0": 0.100, "250": 0.0847, "300": 0.0707, "350": 0.0605,
    "400": 0.0529, "500": 0.0424, "600": 0.0353, "700": 0.0303,
    "750": 0.0282, "1000": 0.0212,
}


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def _ambient_correction(ambient_c: float) -> float:
    """NEC 310.15(B)(2)(a) ambient temperature correction for 75°C conductors."""
    for max_c, factor in _AMBIENT_CORRECTION_75C:
        if ambient_c <= max_c:
            return factor
    return 0.0  # above max rating


def _bundling_factor(num_ccc: int) -> float:
    """NEC 310.15(B)(3)(a) adjustment factor for bundled conductors."""
    for max_n, factor in _BUNDLING_FACTORS:
        if num_ccc <= max_n:
            return factor
    return 0.35


def _next_standard_ocpd(amps: float) -> int:
    """NEC 240.4(B): next standard size at or above required amperage."""
    for size in _STANDARD_OCPD:
        if size >= amps:
            return size
    return _STANDARD_OCPD[-1]


def _size_index(size: str) -> int:
    try:
        return _SIZE_ORDER.index(size)
    except ValueError:
        return -1


def _upsize(current_size: str, steps: int = 1) -> str | None:
    """Return conductor size `steps` steps up from current_size."""
    idx = _size_index(current_size)
    if idx < 0:
        return None
    new_idx = idx + steps
    if new_idx >= len(_SIZE_ORDER):
        return None
    return _SIZE_ORDER[new_idx]


def _motor_flc_1ph(hp: float, voltage: float) -> float | None:
    """Return single-phase motor FLC (A) from NEC 430.248 table."""
    # Interpolate/select nearest hp from table
    for row_hp, amps_115, amps_230 in _MOTOR_FLC_1PH:
        if abs(row_hp - hp) < 1e-6:
            if voltage <= 115:
                return amps_115
            return amps_230
    return None


def _motor_flc_3ph(hp: float, voltage: float) -> float | None:
    """Return three-phase motor FLC (A) scaled from NEC 430.250 at 460V."""
    # NEC 430.250 is at 460V; scale by 460/voltage
    for row_hp, amps_460 in _MOTOR_FLC_3PH_460:
        if abs(row_hp - hp) < 1e-6:
            if voltage <= 0:
                return None
            return amps_460 * 460.0 / voltage
    return None


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def demand_load(
    loads: list[dict],
    *,
    occupancy: str = "commercial",
    continuous_factor: float = 1.25,
) -> dict:
    """Compute feeder/service demand load per NEC Art. 220.

    Parameters
    ----------
    loads : list of dicts
        Each entry: {"name": str, "va": float, "continuous": bool (optional)}
        "va" is the connected VA.  "continuous" defaults to False.
    occupancy : str
        "dwelling" — NEC 220.42 general lighting demand factors apply.
        "commercial" — no general lighting demand factor (use 100%).
        "industrial" — same as commercial for feeder sizing.
    continuous_factor : float
        Multiplier for continuous loads (NEC 215.2, 220.14). Default 1.25 (125%).

    Returns
    -------
    dict with keys: ok, demand_va, continuous_va, noncontinuous_va, warnings
    """
    warnings: list[str] = []
    if not isinstance(loads, list):
        return {"ok": False, "reason": "loads must be a list"}
    if continuous_factor < 1.0:
        return {"ok": False, "reason": "continuous_factor must be >= 1.0"}
    if occupancy not in ("dwelling", "commercial", "industrial"):
        return {"ok": False, "reason": f"unknown occupancy '{occupancy}'"}

    continuous_va = 0.0
    noncontinuous_va = 0.0

    for i, item in enumerate(loads):
        if not isinstance(item, dict):
            return {"ok": False, "reason": f"loads[{i}] is not a dict"}
        va = item.get("va")
        if va is None:
            return {"ok": False, "reason": f"loads[{i}] missing 'va'"}
        if va < 0:
            return {"ok": False, "reason": f"loads[{i}] 'va' must be >= 0"}
        if item.get("continuous", False):
            continuous_va += va
        else:
            noncontinuous_va += va

    # NEC 220.42 dwelling lighting demand factors (simplified)
    lighting_demand_va = 0.0
    if occupancy == "dwelling":
        # Apply Table 220.42: first 3000 VA @ 100%, 3001–120000 @ 35%, remainder @ 25%
        total_lighting = noncontinuous_va  # treat all noncontinuous as general lighting
        if total_lighting <= 3000:
            lighting_demand_va = total_lighting
        elif total_lighting <= 120000:
            lighting_demand_va = 3000 + (total_lighting - 3000) * 0.35
        else:
            lighting_demand_va = 3000 + (120000 - 3000) * 0.35 + (total_lighting - 120000) * 0.25
        noncontinuous_demand = lighting_demand_va
    else:
        noncontinuous_demand = noncontinuous_va

    demand_va = continuous_va * continuous_factor + noncontinuous_demand

    if continuous_factor > 1.0 and continuous_va > 0:
        warnings.append(
            f"Continuous loads ({continuous_va:.0f} VA) multiplied by "
            f"{continuous_factor:.2f} per NEC 215.2/220.14"
        )

    return {
        "ok": True,
        "demand_va": round(demand_va, 2),
        "continuous_va": round(continuous_va, 2),
        "noncontinuous_va": round(noncontinuous_va, 2),
        "noncontinuous_demand_va": round(noncontinuous_demand, 2),
        "occupancy": occupancy,
        "warnings": warnings,
    }


def conductor_ampacity(
    size: str,
    *,
    material: str = "cu",
    ambient_c: float = 30.0,
    num_ccc: int = 3,
) -> dict:
    """Return derated conductor ampacity per NEC 310.16.

    Parameters
    ----------
    size : str
        Wire size string: "14", "12", ..., "4/0", "250", ..., "1000".
    material : str
        "cu" (copper, default) or "al" (aluminum).
    ambient_c : float
        Ambient temperature (°C). Default 30°C (NEC table base temperature).
    num_ccc : int
        Number of current-carrying conductors in raceway. Default 3.
        Triggers bundling derate when > 3 per NEC 310.15(B)(3)(a).

    Returns
    -------
    dict with keys: ok, size, material, base_ampacity_A, ambient_correction,
        bundling_factor, derated_ampacity_A, warnings
    """
    warnings: list[str] = []
    if material not in ("cu", "al"):
        return {"ok": False, "reason": "material must be 'cu' or 'al'"}
    if ambient_c <= 0:
        return {"ok": False, "reason": "ambient_c must be > 0"}
    if num_ccc < 1:
        return {"ok": False, "reason": "num_ccc must be >= 1"}

    table = _AMPACITY_CU_75C if material == "cu" else _AMPACITY_AL_75C
    entry = table.get(size)
    if entry is None:
        return {"ok": False, "reason": f"unknown conductor size '{size}' for material '{material}'"}

    base_amp = entry[0]
    amb_corr = _ambient_correction(ambient_c)
    if amb_corr <= 0.0:
        return {
            "ok": False,
            "reason": f"ambient {ambient_c}°C exceeds conductor temperature rating (75°C)",
        }
    bundle = _bundling_factor(num_ccc)

    derated = base_amp * amb_corr * bundle

    if ambient_c > 30.0:
        warnings.append(
            f"Ambient {ambient_c}°C correction factor {amb_corr:.3f} applied (NEC 310.15(B)(2))"
        )
    if num_ccc > 3:
        warnings.append(
            f"Bundling factor {bundle:.2f} applied for {num_ccc} CCC (NEC 310.15(B)(3)(a))"
        )

    return {
        "ok": True,
        "size": size,
        "material": material,
        "base_ampacity_A": base_amp,
        "ambient_correction": amb_corr,
        "bundling_factor": bundle,
        "derated_ampacity_A": round(derated, 2),
        "warnings": warnings,
    }


def conductor_size_for_load(
    load_A: float,
    *,
    material: str = "cu",
    ambient_c: float = 30.0,
    num_ccc: int = 3,
    continuous: bool = False,
) -> dict:
    """Select minimum conductor size to carry a given load per NEC 310.16.

    Applies 125% continuous-load factor if continuous=True (NEC 215.2).
    Selects smallest size whose derated ampacity meets the required current.

    Returns
    -------
    dict with keys: ok, size, material, required_A, derated_ampacity_A,
        base_ampacity_A, warnings
    """
    warnings: list[str] = []
    if load_A <= 0:
        return {"ok": False, "reason": "load_A must be > 0"}
    if material not in ("cu", "al"):
        return {"ok": False, "reason": "material must be 'cu' or 'al'"}

    required_A = load_A * 1.25 if continuous else load_A
    if continuous:
        warnings.append(
            f"Continuous load: required ampacity = {load_A:.1f} × 1.25 = {required_A:.1f} A "
            f"(NEC 215.2)"
        )

    table = _AMPACITY_CU_75C if material == "cu" else _AMPACITY_AL_75C
    selected_size: str | None = None
    selected_amp = 0.0
    selected_base = 0.0

    for size in _SIZE_ORDER:
        entry = table.get(size)
        if entry is None:
            continue
        base_amp = entry[0]
        amb_corr = _ambient_correction(ambient_c)
        if amb_corr <= 0.0:
            return {"ok": False, "reason": f"ambient {ambient_c}°C exceeds 75°C rating"}
        bundle = _bundling_factor(num_ccc)
        derated = base_amp * amb_corr * bundle
        if derated >= required_A:
            selected_size = size
            selected_amp = derated
            selected_base = base_amp
            break

    if selected_size is None:
        return {
            "ok": False,
            "reason": (
                f"No standard conductor size handles {required_A:.1f} A "
                f"with ambient {ambient_c}°C and {num_ccc} CCC; "
                f"consider parallel conductors"
            ),
        }

    if ambient_c > 30.0:
        warnings.append(
            f"Ambient {ambient_c}°C correction applied (NEC 310.15(B)(2)(a))"
        )
    if num_ccc > 3:
        warnings.append(
            f"Bundling derate applied for {num_ccc} current-carrying conductors"
        )

    return {
        "ok": True,
        "size": selected_size,
        "material": material,
        "required_A": round(required_A, 2),
        "load_A": round(load_A, 2),
        "derated_ampacity_A": round(selected_amp, 2),
        "base_ampacity_A": selected_base,
        "warnings": warnings,
    }


def voltage_drop(
    load_A: float,
    length_ft: float,
    size: str,
    voltage: float,
    *,
    phases: int = 1,
    material: str = "cu",
    pf: float = 1.0,
    vd_limit_pct: float = 3.0,
) -> dict:
    """Calculate voltage drop and check NEC recommendation (≤3% branch, ≤5% feeder).

    Formula (1φ):  VD = 2 × I × R × L / 1000
    Formula (3φ):  VD = √3 × I × R × L / 1000
    Where R is resistance in Ω/1000 ft (Ch.9 Table 9).

    Parameters
    ----------
    load_A : float  Current (A).
    length_ft : float  One-way conductor length (ft).
    size : str  Conductor size string.
    voltage : float  System voltage (V).
    phases : int  1 or 3.
    material : str  "cu" or "al".
    pf : float  Power factor (0 < pf ≤ 1.0). Affects effective impedance.
    vd_limit_pct : float  Voltage-drop limit percentage for warning flag (default 3%).

    Returns
    -------
    dict with keys: ok, vd_V, vd_pct, receiving_end_V, vd_exceeds_limit,
        recommended_size (upsized if over limit), warnings
    """
    warnings: list[str] = []
    if load_A <= 0:
        return {"ok": False, "reason": "load_A must be > 0"}
    if length_ft <= 0:
        return {"ok": False, "reason": "length_ft must be > 0"}
    if voltage <= 0:
        return {"ok": False, "reason": "voltage must be > 0"}
    if phases not in (1, 3):
        return {"ok": False, "reason": "phases must be 1 or 3"}
    if material not in ("cu", "al"):
        return {"ok": False, "reason": "material must be 'cu' or 'al'"}
    if not (0 < pf <= 1.0):
        return {"ok": False, "reason": "pf must be between 0 (exclusive) and 1.0 (inclusive)"}

    r_table = _R_CU_OHMS_PER_KFT if material == "cu" else _R_AL_OHMS_PER_KFT
    r_per_kft = r_table.get(size)
    if r_per_kft is None:
        return {"ok": False, "reason": f"unknown conductor size '{size}' for material '{material}'"}

    # Effective resistance considering power factor (approximate Zeff = R + jX; simplified to R/pf)
    r_eff = r_per_kft / pf if pf < 1.0 else r_per_kft

    if phases == 1:
        vd_v = 2.0 * load_A * r_eff * length_ft / 1000.0
    else:
        vd_v = math.sqrt(3.0) * load_A * r_eff * length_ft / 1000.0

    vd_pct = (vd_v / voltage) * 100.0
    receiving_v = voltage - vd_v
    exceeds = vd_pct > vd_limit_pct

    # Find recommended (upsized) size if over limit
    recommended_size = size
    if exceeds:
        warnings.append(
            f"Voltage drop {vd_pct:.2f}% exceeds {vd_limit_pct:.1f}% limit "
            f"(NEC 210.19(A) Informational Note)"
        )
        # Try upsizing until VD is within limit or no larger size available
        for candidate in _SIZE_ORDER[_size_index(size) + 1:]:
            r_cand = r_table.get(candidate)
            if r_cand is None:
                continue
            r_eff_c = r_cand / pf if pf < 1.0 else r_cand
            if phases == 1:
                vd_c = 2.0 * load_A * r_eff_c * length_ft / 1000.0
            else:
                vd_c = math.sqrt(3.0) * load_A * r_eff_c * length_ft / 1000.0
            if (vd_c / voltage) * 100.0 <= vd_limit_pct:
                recommended_size = candidate
                break

    return {
        "ok": True,
        "size": size,
        "material": material,
        "phases": phases,
        "vd_V": round(vd_v, 4),
        "vd_pct": round(vd_pct, 3),
        "receiving_end_V": round(receiving_v, 3),
        "vd_exceeds_limit": exceeds,
        "vd_limit_pct": vd_limit_pct,
        "recommended_size": recommended_size,
        "warnings": warnings,
    }


def conduit_fill(
    conductors: list[dict],
    conduit_trade_size_in: float,
    *,
    conduit_type: str = "EMT",
) -> dict:
    """Calculate conduit fill percentage per NEC Ch. 9.

    NEC Ch.9 Table 1: max fill 40% for 3+ conductors, 31% for 2, 53% for 1.

    Parameters
    ----------
    conductors : list of dicts
        Each: {"size": str, "material": str (optional, default "cu"), "count": int (optional, 1)}
    conduit_trade_size_in : float
        Trade size of conduit (inches): 0.5, 0.75, 1, 1.25, 1.5, 2, 2.5, 3, ...
    conduit_type : str
        "EMT", "RMC", "IMC", "PVC40", "PVC80" (affects internal area).

    Returns
    -------
    dict with keys: ok, total_conductor_area_in2, conduit_area_in2,
        fill_pct, max_fill_pct, fill_ok, warnings
    """
    warnings: list[str] = []

    # NEC Ch.9 Table 4 internal area (in²) for EMT (approximate standard values)
    _EMT_AREA: dict[float, float] = {
        0.5: 0.304, 0.75: 0.533, 1.0: 0.864, 1.25: 1.496,
        1.5: 2.036, 2.0: 3.356, 2.5: 5.858, 3.0: 8.846,
        3.5: 11.545, 4.0: 14.753,
    }
    _RMC_AREA: dict[float, float] = {
        0.5: 0.217, 0.75: 0.364, 1.0: 0.600, 1.25: 1.050,
        1.5: 1.440, 2.0: 2.400, 2.5: 3.610, 3.0: 5.370,
        3.5: 7.060, 4.0: 8.990,
    }

    area_tables = {"EMT": _EMT_AREA, "RMC": _RMC_AREA, "IMC": _RMC_AREA,
                   "PVC40": _EMT_AREA, "PVC80": _RMC_AREA}
    area_table = area_tables.get(conduit_type, _EMT_AREA)
    conduit_area = area_table.get(conduit_trade_size_in)
    if conduit_area is None:
        return {
            "ok": False,
            "reason": f"conduit trade size {conduit_trade_size_in}\" not in table for {conduit_type}",
        }

    if not isinstance(conductors, list) or len(conductors) == 0:
        return {"ok": False, "reason": "conductors must be a non-empty list"}

    total_count = 0
    total_area = 0.0
    for i, c in enumerate(conductors):
        if not isinstance(c, dict):
            return {"ok": False, "reason": f"conductors[{i}] is not a dict"}
        size = c.get("size")
        if size is None:
            return {"ok": False, "reason": f"conductors[{i}] missing 'size'"}
        mat = c.get("material", "cu")
        count = c.get("count", 1)
        if count < 1:
            return {"ok": False, "reason": f"conductors[{i}] count must be >= 1"}
        area_per = _conductor_area_in2(size, mat)
        if area_per == 0.0:
            return {"ok": False, "reason": f"unknown conductor size '{size}' material '{mat}'"}
        total_area += area_per * count
        total_count += count

    # NEC Ch.9 Table 1 max fill percentages
    if total_count == 1:
        max_fill = 53.0
    elif total_count == 2:
        max_fill = 31.0
    else:
        max_fill = 40.0

    fill_pct = (total_area / conduit_area) * 100.0
    fill_ok = fill_pct <= max_fill

    if not fill_ok:
        warnings.append(
            f"Conduit fill {fill_pct:.1f}% exceeds NEC Ch.9 Table 1 limit of {max_fill:.0f}% "
            f"for {total_count} conductors in {conduit_trade_size_in}\" {conduit_type}"
        )

    return {
        "ok": True,
        "total_conductor_area_in2": round(total_area, 5),
        "conduit_area_in2": conduit_area,
        "fill_pct": round(fill_pct, 2),
        "max_fill_pct": max_fill,
        "fill_ok": fill_ok,
        "conductor_count": total_count,
        "conduit_trade_size_in": conduit_trade_size_in,
        "conduit_type": conduit_type,
        "warnings": warnings,
    }


def overcurrent_device_size(
    conductor_size: str,
    *,
    material: str = "cu",
    load_A: float | None = None,
    continuous: bool = False,
    ambient_c: float = 30.0,
    num_ccc: int = 3,
) -> dict:
    """Size overcurrent protection device per NEC 240.4.

    Selects OCPD at or below conductor ampacity (NEC 240.4(B) next-standard-size rule:
    if calculated ampacity doesn't match a standard size, use next size UP only if
    the conductor ampacity is not more than 800A and it's not a multi-outlet branch circuit).

    Parameters
    ----------
    conductor_size : str  Conductor size string.
    material : str  "cu" or "al".
    load_A : float  Optional load current (A). If provided, checks OCPD ≥ load.
    continuous : bool  If True, required OCPD ≥ load × 1.25.
    ambient_c : float  Ambient temperature (°C).
    num_ccc : int  Number of current-carrying conductors.

    Returns
    -------
    dict with keys: ok, ocpd_A, conductor_ampacity_A, undersized_conductor, warnings
    """
    warnings: list[str] = []
    amp_result = conductor_ampacity(
        conductor_size, material=material, ambient_c=ambient_c, num_ccc=num_ccc
    )
    if not amp_result["ok"]:
        return amp_result

    derated_amp = amp_result["derated_ampacity_A"]

    # NEC 240.4(B): next standard size up allowed if conductor ampacity < calculated
    ocpd = _next_standard_ocpd(derated_amp)

    # Check against load if provided
    undersized = False
    if load_A is not None:
        if load_A <= 0:
            return {"ok": False, "reason": "load_A must be > 0"}
        required_ocpd_for_load = load_A * 1.25 if continuous else load_A
        if ocpd < required_ocpd_for_load:
            warnings.append(
                f"OCPD {ocpd}A may be undersized for load {load_A:.1f}A "
                f"({'continuous × 1.25' if continuous else 'non-continuous'})"
            )
            undersized = True
        if derated_amp < load_A:
            warnings.append(
                f"UNDERSIZED CONDUCTOR: derated ampacity {derated_amp:.1f}A < load {load_A:.1f}A"
            )
            undersized = True

    return {
        "ok": True,
        "ocpd_A": ocpd,
        "conductor_size": conductor_size,
        "material": material,
        "conductor_ampacity_A": derated_amp,
        "undersized_conductor": undersized,
        "warnings": warnings + amp_result.get("warnings", []),
    }


def motor_branch_circuit(
    hp: float,
    voltage: float,
    *,
    phases: int = 3,
    service_factor: float = 1.15,
    ocpd_type: str = "inverse_time_breaker",
) -> dict:
    """Size motor branch circuit per NEC Art. 430.

    Per NEC 430.22: conductor ≥ 125% of motor FLC.
    Per NEC 430.52: OCPD max % of FLC (Table 430.52):
        Inverse-time breaker: 250% (standard), up to 400% if needed to start.
        Dual-element fuse: 175%, up to 225%.
        Instantaneous trip breaker: 800%.

    Parameters
    ----------
    hp : float  Motor horsepower.
    voltage : float  System voltage (V).
    phases : int  1 (single-phase) or 3 (three-phase).
    service_factor : float  Motor nameplate service factor (default 1.15).
    ocpd_type : str  "inverse_time_breaker", "dual_element_fuse", or "instantaneous".

    Returns
    -------
    dict with keys: ok, flc_A, conductor_min_A, conductor_size, ocpd_max_A,
        ocpd_A, overload_A, warnings
    """
    warnings: list[str] = []

    # NEC 430.52 Table — max OCPD % of FLC
    _OCPD_PCT: dict[str, float] = {
        "inverse_time_breaker": 2.50,
        "dual_element_fuse": 1.75,
        "instantaneous": 8.00,
    }
    if ocpd_type not in _OCPD_PCT:
        return {"ok": False, "reason": f"unknown ocpd_type '{ocpd_type}'"}
    if hp <= 0:
        return {"ok": False, "reason": "hp must be > 0"}
    if voltage <= 0:
        return {"ok": False, "reason": "voltage must be > 0"}
    if phases not in (1, 3):
        return {"ok": False, "reason": "phases must be 1 or 3"}

    # Look up FLC
    if phases == 1:
        flc = _motor_flc_1ph(hp, voltage)
    else:
        flc = _motor_flc_3ph(hp, voltage)

    if flc is None:
        return {
            "ok": False,
            "reason": (
                f"Motor FLC not found in NEC table for {hp} hp, "
                f"{phases}-phase, {voltage}V. Use exact NEC table values."
            ),
        }

    # NEC 430.22: branch circuit conductor ≥ 125% FLC
    conductor_min_A = flc * 1.25

    # Select conductor size
    cond_result = conductor_size_for_load(conductor_min_A, material="cu")
    if not cond_result["ok"]:
        return {"ok": False, "reason": f"conductor sizing failed: {cond_result['reason']}"}
    conductor_size = cond_result["size"]

    # NEC 430.52: max OCPD
    ocpd_max_A = flc * _OCPD_PCT[ocpd_type]
    ocpd_A = _next_standard_ocpd(ocpd_max_A)

    # NEC 430.32: overload protection ≤ 125% FLC (SF ≥ 1.15) or 115% FLC (SF < 1.15)
    if service_factor >= 1.15:
        overload_A = flc * 1.25
    else:
        overload_A = flc * 1.15

    return {
        "ok": True,
        "hp": hp,
        "voltage": voltage,
        "phases": phases,
        "flc_A": round(flc, 2),
        "conductor_min_A": round(conductor_min_A, 2),
        "conductor_size": conductor_size,
        "ocpd_type": ocpd_type,
        "ocpd_max_A": round(ocpd_max_A, 2),
        "ocpd_A": ocpd_A,
        "overload_A": round(overload_A, 2),
        "service_factor": service_factor,
        "warnings": warnings,
    }


def transformer_feeder_size(
    kva: float,
    primary_voltage: float,
    secondary_voltage: float,
    *,
    phases: int = 3,
    impedance_pct: float = 5.75,
    primary_ocpd_pct: float = 1.25,
) -> dict:
    """Size transformer and feeder per NEC Art. 450 and 215.

    Primary FLA = kVA × 1000 / (V × √3)  for 3φ  or  / V  for 1φ.
    Secondary FLA similarly computed.
    Primary OCPD ≤ 125% FLA (NEC 450.3(B) supervised installation),
    or next standard size for unsupervised.

    Parameters
    ----------
    kva : float  Transformer kVA rating.
    primary_voltage : float  Primary voltage (V).
    secondary_voltage : float  Secondary voltage (V).
    phases : int  1 or 3.
    impedance_pct : float  Transformer %Z (default 5.75%).
    primary_ocpd_pct : float  Primary OCPD factor (default 1.25 = 125%).

    Returns
    -------
    dict with keys: ok, primary_fla_A, secondary_fla_A, primary_conductor_size,
        secondary_conductor_size, primary_ocpd_A, secondary_ocpd_A,
        impedance_pct, max_secondary_sca_A, warnings
    """
    warnings: list[str] = []
    if kva <= 0:
        return {"ok": False, "reason": "kva must be > 0"}
    if primary_voltage <= 0 or secondary_voltage <= 0:
        return {"ok": False, "reason": "voltages must be > 0"}
    if phases not in (1, 3):
        return {"ok": False, "reason": "phases must be 1 or 3"}
    if not (0 < impedance_pct < 100):
        return {"ok": False, "reason": "impedance_pct must be between 0 and 100"}

    sqrt3 = math.sqrt(3.0)
    denom = (sqrt3 * primary_voltage) if phases == 3 else primary_voltage
    primary_fla = (kva * 1000.0) / denom

    denom_sec = (sqrt3 * secondary_voltage) if phases == 3 else secondary_voltage
    secondary_fla = (kva * 1000.0) / denom_sec

    # Primary conductor ≥ FLA (NEC 215.2 / 310.16)
    pri_cond_result = conductor_size_for_load(primary_fla, material="cu")
    if not pri_cond_result["ok"]:
        return {"ok": False, "reason": f"primary conductor: {pri_cond_result['reason']}"}

    sec_cond_result = conductor_size_for_load(secondary_fla, material="cu")
    if not sec_cond_result["ok"]:
        return {"ok": False, "reason": f"secondary conductor: {sec_cond_result['reason']}"}

    # Primary OCPD ≤ 125% FLA (NEC 450.3)
    primary_ocpd_A = _next_standard_ocpd(primary_fla * primary_ocpd_pct)
    secondary_ocpd_A = _next_standard_ocpd(secondary_fla * 1.25)

    # Maximum secondary short-circuit current (infinite bus approximation)
    max_sca_A = (kva * 1000.0) / (impedance_pct / 100.0 * denom_sec)

    return {
        "ok": True,
        "kva": kva,
        "phases": phases,
        "primary_voltage": primary_voltage,
        "secondary_voltage": secondary_voltage,
        "primary_fla_A": round(primary_fla, 2),
        "secondary_fla_A": round(secondary_fla, 2),
        "primary_conductor_size": pri_cond_result["size"],
        "secondary_conductor_size": sec_cond_result["size"],
        "primary_ocpd_A": primary_ocpd_A,
        "secondary_ocpd_A": secondary_ocpd_A,
        "impedance_pct": impedance_pct,
        "max_secondary_sca_A": round(max_sca_A, 1),
        "warnings": warnings,
    }


def short_circuit_analysis(
    transformer_kva: float,
    transformer_primary_V: float,
    transformer_secondary_V: float,
    *,
    transformer_z_pct: float = 5.75,
    phases: int = 3,
    cable_length_ft: float = 0.0,
    cable_size: str = "4/0",
    cable_material: str = "cu",
    point_name: str = "distribution board",
) -> dict:
    """Point-to-point short-circuit analysis (infinite bus method).

    Calculates available fault current at a point downstream of a transformer,
    accounting for transformer %Z and cable impedance.

    Method (NEC / IEEE 141 "Red Book"):
      1. Transformer secondary bolted fault current (infinite bus):
         I_sc_xfmr = kVA × 1000 / (%Z/100 × V_sec × √3)  [3φ]
      2. Cable impedance reduces fault current downstream:
         I_fault = V_LL / (√3 × Z_total)  [3φ]
         where Z_total = Z_xfmr + Z_cable
      3. AIC rating required = I_fault × safety margin (use 1.0; flag if breaker AIC < I_fault)

    Parameters
    ----------
    transformer_kva : float  Transformer kVA.
    transformer_primary_V : float  Primary voltage (V, not used in calc but stored).
    transformer_secondary_V : float  Secondary line-to-line voltage (V).
    transformer_z_pct : float  Transformer %Z (default 5.75%).
    phases : int  1 or 3.
    cable_length_ft : float  One-way cable length from transformer to fault point (ft).
    cable_size : str  Phase conductor size.
    cable_material : str  "cu" or "al".
    point_name : str  Label for the fault point.

    Returns
    -------
    dict with keys: ok, point_name, isc_transformer_A, isc_at_point_A,
        z_transformer_ohms, z_cable_ohms, z_total_ohms, required_aic_A, warnings
    """
    warnings: list[str] = []
    if transformer_kva <= 0:
        return {"ok": False, "reason": "transformer_kva must be > 0"}
    if transformer_secondary_V <= 0:
        return {"ok": False, "reason": "transformer_secondary_V must be > 0"}
    if not (0 < transformer_z_pct < 100):
        return {"ok": False, "reason": "transformer_z_pct must be between 0 and 100"}
    if phases not in (1, 3):
        return {"ok": False, "reason": "phases must be 1 or 3"}
    if cable_length_ft < 0:
        return {"ok": False, "reason": "cable_length_ft must be >= 0"}

    sqrt3 = math.sqrt(3.0)
    v_sec = transformer_secondary_V

    # Transformer impedance (Ω, referred to secondary)
    # Z_base = V²/S;  Z_xfmr = %Z/100 × Z_base
    if phases == 3:
        s_va = transformer_kva * 1000.0
        z_base = (v_sec ** 2) / s_va
        z_xfmr = (transformer_z_pct / 100.0) * z_base
        # Transformer secondary bolted fault current
        isc_xfmr = v_sec / (sqrt3 * z_xfmr)
    else:
        s_va = transformer_kva * 1000.0
        z_base = (v_sec ** 2) / s_va
        z_xfmr = (transformer_z_pct / 100.0) * z_base
        isc_xfmr = v_sec / (2.0 * z_xfmr)  # 1φ: 2 conductors

    # Cable impedance
    z_cable = 0.0
    if cable_length_ft > 0:
        r_table = _R_CU_OHMS_PER_KFT if cable_material == "cu" else _R_AL_OHMS_PER_KFT
        r_per_kft = r_table.get(cable_size)
        if r_per_kft is None:
            return {
                "ok": False,
                "reason": f"unknown cable size '{cable_size}' for material '{cable_material}'",
            }
        # Total cable resistance (2 conductors for 1φ, 1 conductor per phase for 3φ fault path)
        if phases == 3:
            z_cable = r_per_kft * cable_length_ft / 1000.0  # one-way only for 3φ line impedance
        else:
            z_cable = 2.0 * r_per_kft * cable_length_ft / 1000.0

    z_total = z_xfmr + z_cable

    if phases == 3:
        isc_at_point = v_sec / (sqrt3 * z_total)
    else:
        isc_at_point = v_sec / (2.0 * z_total)

    # Required AIC
    required_aic = math.ceil(isc_at_point / 1000.0) * 1000.0

    if isc_at_point > 200000:
        warnings.append(
            f"Very high fault current {isc_at_point:.0f}A — verify transformer %Z and cable data"
        )

    return {
        "ok": True,
        "point_name": point_name,
        "phases": phases,
        "transformer_kva": transformer_kva,
        "transformer_secondary_V": transformer_secondary_V,
        "transformer_z_pct": transformer_z_pct,
        "cable_length_ft": cable_length_ft,
        "cable_size": cable_size,
        "isc_transformer_A": round(isc_xfmr, 1),
        "isc_at_point_A": round(isc_at_point, 1),
        "z_transformer_ohms": round(z_xfmr, 6),
        "z_cable_ohms": round(z_cable, 6),
        "z_total_ohms": round(z_total, 6),
        "required_aic_A": required_aic,
        "warnings": warnings,
    }


def power_factor_correction(
    load_kw: float,
    current_pf: float,
    target_pf: float,
    voltage: float,
    *,
    phases: int = 3,
    frequency_hz: float = 60.0,
) -> dict:
    """Calculate capacitor kVAR needed for power-factor correction.

    Q_correction = P × (tan(θ₁) − tan(θ₂))
    Capacitance: C = Q / (2πf × V²)  [1φ]  or  C = Q / (2πf × V_LL²)  [3φ per-phase: /3]

    Parameters
    ----------
    load_kw : float  Real power (kW).
    current_pf : float  Existing power factor (0 < pf ≤ 1).
    target_pf : float  Desired power factor (current_pf < target_pf ≤ 1).
    voltage : float  System voltage (V, line-to-line for 3φ).
    phases : int  1 or 3.
    frequency_hz : float  System frequency (Hz).

    Returns
    -------
    dict with keys: ok, kvar_required, kvar_bank_size, capacitance_uF_per_phase,
        current_kva, target_kva, current_kvar, target_kvar, warnings
    """
    warnings: list[str] = []
    if load_kw <= 0:
        return {"ok": False, "reason": "load_kw must be > 0"}
    if not (0 < current_pf <= 1.0):
        return {"ok": False, "reason": "current_pf must be between 0 (exclusive) and 1.0"}
    if not (0 < target_pf <= 1.0):
        return {"ok": False, "reason": "target_pf must be between 0 (exclusive) and 1.0"}
    if current_pf >= target_pf:
        return {"ok": False, "reason": "target_pf must be greater than current_pf"}
    if voltage <= 0:
        return {"ok": False, "reason": "voltage must be > 0"}
    if phases not in (1, 3):
        return {"ok": False, "reason": "phases must be 1 or 3"}
    if frequency_hz <= 0:
        return {"ok": False, "reason": "frequency_hz must be > 0"}

    theta1 = math.acos(current_pf)
    theta2 = math.acos(target_pf)

    kvar_required = load_kw * (math.tan(theta1) - math.tan(theta2))

    # Round up to nearest standard kVAR bank (use 5 kVAR increments)
    kvar_bank = math.ceil(kvar_required / 5.0) * 5.0

    # Capacitance per phase
    kvar_per_phase = (kvar_required * 1000.0) / (3 if phases == 3 else 1)
    v_per_phase = voltage / math.sqrt(3.0) if phases == 3 else voltage
    if v_per_phase <= 0:
        return {"ok": False, "reason": "computed per-phase voltage is zero"}

    cap_farads = kvar_per_phase / (2.0 * math.pi * frequency_hz * v_per_phase ** 2)
    cap_uf = cap_farads * 1e6

    current_kva = load_kw / current_pf
    target_kva = load_kw / target_pf
    current_kvar = load_kw * math.tan(theta1)
    target_kvar = load_kw * math.tan(theta2)

    return {
        "ok": True,
        "load_kw": load_kw,
        "current_pf": current_pf,
        "target_pf": target_pf,
        "phases": phases,
        "kvar_required": round(kvar_required, 3),
        "kvar_bank_size": kvar_bank,
        "capacitance_uF_per_phase": round(cap_uf, 4),
        "current_kva": round(current_kva, 3),
        "target_kva": round(target_kva, 3),
        "current_kvar": round(current_kvar, 3),
        "target_kvar": round(target_kvar, 3),
        "warnings": warnings,
    }


def grounding_conductor_size(
    service_conductor_size: str,
    *,
    ocpd_rating_A: float | None = None,
    conductor_type: str = "gec",
    material: str = "cu",
) -> dict:
    """Size grounding conductors per NEC 250.66 (GEC) and 250.122 (EGC).

    Parameters
    ----------
    service_conductor_size : str
        For GEC (conductor_type="gec"): service-entrance conductor size.
        For EGC (conductor_type="egc"): phase conductor size (not used; ocpd_rating_A required).
    ocpd_rating_A : float
        Required for EGC sizing per NEC 250.122.
    conductor_type : str
        "gec" — grounding-electrode conductor (NEC 250.66).
        "egc" — equipment-grounding conductor (NEC 250.122).
    material : str
        "cu" or "al".

    Returns
    -------
    dict with keys: ok, conductor_type, size, material, warnings
    """
    warnings: list[str] = []
    if conductor_type not in ("gec", "egc"):
        return {"ok": False, "reason": "conductor_type must be 'gec' or 'egc'"}
    if material not in ("cu", "al"):
        return {"ok": False, "reason": "material must be 'cu' or 'al'"}

    if conductor_type == "gec":
        if service_conductor_size not in _AMPACITY_CU_75C:
            return {
                "ok": False,
                "reason": f"unknown service conductor size '{service_conductor_size}'",
            }
        gec_cu = _gec_size_cu(service_conductor_size)
        # Al GEC is one size larger than Cu per NEC 250.66
        if material == "al":
            al_idx = _size_index(gec_cu)
            gec_size = _SIZE_ORDER[al_idx + 1] if al_idx + 1 < len(_SIZE_ORDER) else gec_cu
        else:
            gec_size = gec_cu

        return {
            "ok": True,
            "conductor_type": "gec",
            "size": gec_size,
            "material": material,
            "service_conductor": service_conductor_size,
            "nec_reference": "250.66",
            "warnings": warnings,
        }

    else:  # egc
        if ocpd_rating_A is None:
            return {"ok": False, "reason": "ocpd_rating_A is required for EGC sizing"}
        if ocpd_rating_A <= 0:
            return {"ok": False, "reason": "ocpd_rating_A must be > 0"}

        egc_size_cu = "14"  # default minimum
        for max_ocpd, size in _EGC_TABLE:
            if ocpd_rating_A <= max_ocpd:
                egc_size_cu = size
                break
        else:
            egc_size_cu = "1000"
            warnings.append(f"OCPD {ocpd_rating_A}A exceeds NEC 250.122 table maximum; use 1000 kcmil")

        if material == "al":
            al_idx = _size_index(egc_size_cu)
            egc_size = _SIZE_ORDER[al_idx + 1] if al_idx + 1 < len(_SIZE_ORDER) else egc_size_cu
        else:
            egc_size = egc_size_cu

        return {
            "ok": True,
            "conductor_type": "egc",
            "size": egc_size,
            "material": material,
            "ocpd_rating_A": ocpd_rating_A,
            "nec_reference": "250.122",
            "warnings": warnings,
        }


def panel_schedule_rollup(
    circuits: list[dict],
    *,
    voltage: float = 120.0,
    phases: int = 1,
    include_demand: bool = True,
    occupancy: str = "commercial",
) -> dict:
    """Compile panel schedule: sum loads, compute feeder amps, size main breaker/conductors.

    Parameters
    ----------
    circuits : list of dicts
        Each: {
            "name": str,
            "va": float,           -- connected load (VA)
            "continuous": bool,    -- defaults False
            "poles": int           -- 1 or 2 (for 240V), defaults 1
        }
    voltage : float  Panel voltage (phase-to-neutral for 1φ, line-to-line for 3φ panel).
    phases : int  1 or 3.
    include_demand : bool  Apply NEC 220 demand factors.
    occupancy : str  "dwelling", "commercial", or "industrial".

    Returns
    -------
    dict with keys: ok, total_connected_va, demand_va, total_amps,
        main_breaker_A, feeder_conductor_size, circuit_count, warnings
    """
    warnings: list[str] = []
    if not isinstance(circuits, list) or len(circuits) == 0:
        return {"ok": False, "reason": "circuits must be a non-empty list"}
    if voltage <= 0:
        return {"ok": False, "reason": "voltage must be > 0"}
    if phases not in (1, 3):
        return {"ok": False, "reason": "phases must be 1 or 3"}

    loads_for_demand = []
    total_connected = 0.0

    for i, c in enumerate(circuits):
        if not isinstance(c, dict):
            return {"ok": False, "reason": f"circuits[{i}] is not a dict"}
        va = c.get("va")
        if va is None:
            return {"ok": False, "reason": f"circuits[{i}] missing 'va'"}
        if va < 0:
            return {"ok": False, "reason": f"circuits[{i}] 'va' must be >= 0"}
        total_connected += va
        loads_for_demand.append({
            "name": c.get("name", f"circuit_{i}"),
            "va": va,
            "continuous": c.get("continuous", False),
        })

    if include_demand:
        demand_result = demand_load(loads_for_demand, occupancy=occupancy)
        if not demand_result["ok"]:
            return demand_result
        demand_va = demand_result["demand_va"]
        warnings.extend(demand_result.get("warnings", []))
    else:
        demand_va = total_connected

    # Total service amps
    sqrt3 = math.sqrt(3.0)
    if phases == 3:
        total_amps = demand_va / (voltage * sqrt3)
    else:
        total_amps = demand_va / voltage

    # Main breaker (next standard OCPD at or above total amps × 1.25 for continuous)
    main_breaker_A = _next_standard_ocpd(total_amps * 1.25)

    # Feeder conductor size
    cond_result = conductor_size_for_load(total_amps, material="cu", continuous=True)
    if not cond_result["ok"]:
        feeder_conductor_size = "parallel-required"
        warnings.append(f"Load {total_amps:.1f}A requires parallel conductors")
    else:
        feeder_conductor_size = cond_result["size"]

    return {
        "ok": True,
        "total_connected_va": round(total_connected, 2),
        "demand_va": round(demand_va, 2),
        "total_amps": round(total_amps, 2),
        "main_breaker_A": main_breaker_A,
        "feeder_conductor_size": feeder_conductor_size,
        "circuit_count": len(circuits),
        "voltage": voltage,
        "phases": phases,
        "warnings": warnings,
    }


def generator_ups_size(
    loads: list[dict],
    *,
    demand_factor: float = 0.8,
    power_factor: float = 0.8,
    starting_factor: float = 1.25,
    include_spare_pct: float = 20.0,
) -> dict:
    """Size standby generator or UPS for a given load list.

    Generator sizing method:
      1. Sum running kW load (applying demand factor).
      2. Add motor starting kVA (largest motor × starting_factor × kVA/kW / PF).
      3. Size generator to handle running kVA + starting surge.
      4. Add spare capacity %.

    Parameters
    ----------
    loads : list of dicts
        Each: {
            "name": str,
            "kw": float,          -- running power (kW)
            "pf": float,          -- load power factor (default 0.85)
            "motor_hp": float,    -- if motor load, specify HP for starting calc (optional)
            "continuous": bool    -- defaults True for generator sizing
        }
    demand_factor : float  Demand factor applied to sum of running kW (default 0.8).
    power_factor : float  Generator power factor rating (default 0.8).
    starting_factor : float  Motor starting kVA multiplier (default 1.25 × FLA × 6 LRC).
    include_spare_pct : float  Additional spare capacity percentage (default 20%).

    Returns
    -------
    dict with keys: ok, total_running_kw, demand_kw, running_kva,
        largest_motor_starting_kva, total_gen_kva, recommended_gen_kva, warnings
    """
    warnings: list[str] = []
    if not isinstance(loads, list) or len(loads) == 0:
        return {"ok": False, "reason": "loads must be a non-empty list"}
    if not (0 < demand_factor <= 1.0):
        return {"ok": False, "reason": "demand_factor must be between 0 (exclusive) and 1.0"}
    if not (0 < power_factor <= 1.0):
        return {"ok": False, "reason": "power_factor must be between 0 (exclusive) and 1.0"}
    if include_spare_pct < 0:
        return {"ok": False, "reason": "include_spare_pct must be >= 0"}

    total_kw = 0.0
    largest_motor_hp = 0.0

    for i, load in enumerate(loads):
        if not isinstance(load, dict):
            return {"ok": False, "reason": f"loads[{i}] is not a dict"}
        kw = load.get("kw")
        if kw is None:
            return {"ok": False, "reason": f"loads[{i}] missing 'kw'"}
        if kw < 0:
            return {"ok": False, "reason": f"loads[{i}] 'kw' must be >= 0"}
        total_kw += kw
        motor_hp = load.get("motor_hp", 0.0)
        if motor_hp > largest_motor_hp:
            largest_motor_hp = motor_hp

    demand_kw = total_kw * demand_factor
    running_kva = demand_kw / power_factor

    # Motor starting kVA: largest motor LRC ≈ 6 × FLA; starting kVA = 6 × FLA × V / 1000
    # Simplified: starting_kva ≈ largest_motor_hp × 0.746 / 0.85 × starting_factor × 6
    motor_starting_kva = 0.0
    if largest_motor_hp > 0:
        motor_running_kw = largest_motor_hp * 0.746
        motor_running_kva = motor_running_kw / 0.85
        motor_starting_kva = motor_running_kva * 6.0 * starting_factor
        warnings.append(
            f"Largest motor {largest_motor_hp} HP starting surge: {motor_starting_kva:.1f} kVA "
            f"(6× LRC estimate)"
        )

    total_gen_kva = running_kva + motor_starting_kva
    # Apply spare capacity
    recommended_gen_kva = total_gen_kva * (1.0 + include_spare_pct / 100.0)

    # Round up to nearest standard generator size (kVA)
    _STD_GEN_SIZES = [
        10, 15, 20, 25, 30, 40, 45, 50, 60, 75, 80, 100, 125, 150, 175,
        200, 250, 300, 350, 400, 500, 600, 750, 1000, 1250, 1500, 2000,
        2500, 3000,
    ]
    std_gen_kva = next(
        (s for s in _STD_GEN_SIZES if s >= recommended_gen_kva),
        _STD_GEN_SIZES[-1],
    )

    if recommended_gen_kva > _STD_GEN_SIZES[-1]:
        warnings.append(
            f"Required generator {recommended_gen_kva:.1f} kVA exceeds standard sizes; "
            f"use parallel units or custom generator"
        )

    return {
        "ok": True,
        "total_running_kw": round(total_kw, 3),
        "demand_kw": round(demand_kw, 3),
        "running_kva": round(running_kva, 3),
        "largest_motor_starting_kva": round(motor_starting_kva, 3),
        "total_gen_kva": round(total_gen_kva, 3),
        "recommended_gen_kva": round(recommended_gen_kva, 3),
        "standard_gen_size_kva": std_gen_kva,
        "warnings": warnings,
    }
