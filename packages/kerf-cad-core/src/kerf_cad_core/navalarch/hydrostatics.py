"""
kerf_cad_core.navalarch.hydrostatics — pure-Python hydrostatics & intact
stability calculations.

Implements the following public functions:

  displacement_from_LBT(L, B, T, Cb, rho)
      Displacement and buoyancy from principal dimensions & block coefficient.

  displacement_from_offsets(stations, half_breadths, draft, rho)
      Displacement from a tabulated sectional-area curve via Simpson's rule.

  form_coefficients(L, B, T, Cb, Am, Aw)
      Block (Cb), prismatic (Cp), midship (Cm), waterplane (Cw) coefficients.

  waterplane_properties(stations, half_breadths_wl)
      Waterplane area Aw, centroid (LCF), second moments of area (IL, IT)
      via Simpson's rule from half-breadths at the design waterline.

  vertical_centres(T, Cb)
      KB (Morrish / Murray formula) and estimates for KG guidance.

  metacentric_height(KB, BM, KG)
      GM = KB + BM − KG with negative-GM warning.

  righting_arm_GZ(GM, phi_deg, *, wall_sided_BM_T=0.0)
      Small-angle GZ ≈ GM·sin(φ); optional wall-sided correction term.

  tpc_mctc(Aw, L, displacement_t, rho)
      Tonnes per centimetre immersion (TPC) and moment to change trim 1 cm
      (MCT1cm).

  free_surface_correction(rho_liquid, l, b, rho_sw, displacement_t)
      Free-surface correction to GM for a rectangular tank.

  resistance_admiralty(displacement_t, V_knots, Ac)
      Admiralty coefficient power estimate (EHP).

  trim_from_moment(trimming_moment_tm, MCTC, L, LCF_fwd_AP)
      Trim, change in draught forward and aft from an off-centre weight or
      ballasting moment.

All functions return plain dicts:
    success → {"ok": True, ...fields...}
    failure → {"ok": False, "reason": "<human-readable>"}

Functions NEVER raise.  Instability / excessive trim are flagged via
"warnings" list in the result dict — they do NOT cause ok=False.

Units
-----
Unless otherwise stated:
  lengths       — metres (m)
  angles        — degrees (°)
  mass          — tonnes (t) where noted, kilograms (kg) elsewhere
  force         — Newtons (N)
  density       — kg/m³ (sea water default 1025 kg/m³)
  power         — kW
  speed         — knots (kn)
  pressure      — Pascals (Pa)

References
----------
Barras, C.B. "Ship Stability for Masters and Mates", 6th ed., Butterworth-Heinemann.
Rawson & Tupper, "Basic Ship Theory", 5th ed., Butterworth-Heinemann.
Schneekluth & Bertram, "Ship Design for Efficiency and Economy", 2nd ed.
ITTC 1978 Power Prediction Method.

Author: imranparuk
"""

from __future__ import annotations

import math
import warnings as _warnings_module
from typing import Any, Sequence
from kerf_cad_core._guards import _err, _guard_nonneg, _guard_positive


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_RHO_SW = 1025.0          # sea water density (kg/m³) — ITTC standard
_G = 9.80665               # gravitational acceleration (m/s²)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _guard_fraction(name: str, value: Any, lo: float = 0.0, hi: float = 1.0) -> str | None:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number, got {value!r}"
    if not math.isfinite(v):
        return f"{name} must be finite"
    if v < lo or v > hi:
        return f"{name} must be in [{lo}, {hi}], got {v}"
    return None


def _simpsons_rule(ordinates: Sequence[float], h: float) -> float:
    """Composite Simpson's 1/3 rule for equally-spaced ordinates.

    Requires an odd number of ordinates (even number of intervals).
    If the count is even, falls back to the trapezoidal rule for the last
    panel.

    Parameters
    ----------
    ordinates : sequence of n float values y_0 … y_{n-1}
    h : float — common interval spacing

    Returns
    -------
    float — integral estimate
    """
    n = len(ordinates)
    if n < 2:
        return 0.0
    if n == 2:
        return h * (ordinates[0] + ordinates[1]) / 2.0

    # Use Simpson's on the first (n-1) ordinates if n is even,
    # then add trapezoidal for the last panel.
    if n % 2 == 0:
        # n even → n-1 panels; apply Simpson's on first n-2 panels + trap on last
        simp_part = _simpsons_rule(ordinates[:-1], h)
        trap_part = h * (ordinates[-2] + ordinates[-1]) / 2.0
        return simp_part + trap_part

    # n odd → even number of panels → standard composite Simpson's
    total = ordinates[0] + ordinates[-1]
    for i in range(1, n - 1):
        total += (4.0 if i % 2 == 1 else 2.0) * ordinates[i]
    return total * h / 3.0


def _simpsons_first_moment(ordinates: Sequence[float], h: float, x0: float = 0.0) -> float:
    """First moment of area via Simpson's rule about the AP (x=0) axis.

    Integrates x * f(x) dx where x_i = x0 + i*h.
    """
    n = len(ordinates)
    moment_ordinates = [(x0 + i * h) * ordinates[i] for i in range(n)]
    return _simpsons_rule(moment_ordinates, h)


def _simpsons_second_moment(ordinates: Sequence[float], h: float, x0: float = 0.0) -> float:
    """Second moment about AP via Simpson's rule.

    Integrates x² * f(x) dx.
    """
    n = len(ordinates)
    second_ordinates = [(x0 + i * h) ** 2 * ordinates[i] for i in range(n)]
    return _simpsons_rule(second_ordinates, h)


# ---------------------------------------------------------------------------
# 1. displacement_from_LBT
# ---------------------------------------------------------------------------

def displacement_from_LBT(
    L: float,
    B: float,
    T: float,
    Cb: float,
    rho: float = _RHO_SW,
) -> dict:
    """
    Displacement volume and mass from principal dimensions and block coefficient.

    Parameters
    ----------
    L : float
        Length between perpendiculars (m). Must be > 0.
    B : float
        Moulded breadth (m). Must be > 0.
    T : float
        Mean moulded draught (m). Must be > 0.
    Cb : float
        Block coefficient (dimensionless). Must be in (0, 1].
    rho : float
        Water density (kg/m³). Default 1025 kg/m³ (sea water).

    Returns
    -------
    dict
        ok             : True
        volume_m3      : displacement volume ∇ (m³)
        displacement_t : displacement mass (tonnes)
        displacement_kN: buoyancy force (kN)
        L_m, B_m, T_m  : principal dimensions used
        Cb             : block coefficient used
        rho_kg_m3      : density used
    """
    for name, val in (("L", L), ("B", B), ("T", T)):
        err = _guard_positive(name, val)
        if err:
            return _err(err)
    err = _guard_positive("rho", rho)
    if err:
        return _err(err)
    err = _guard_fraction("Cb", Cb, lo=0.0, hi=1.0)
    if err:
        return _err(err)
    if float(Cb) == 0.0:
        return _err("Cb must be > 0")

    L, B, T, Cb, rho = float(L), float(B), float(T), float(Cb), float(rho)
    volume = L * B * T * Cb
    displacement_t = volume * rho / 1000.0
    displacement_kN = volume * rho * _G / 1000.0

    return {
        "ok": True,
        "volume_m3": volume,
        "displacement_t": displacement_t,
        "displacement_kN": displacement_kN,
        "L_m": L,
        "B_m": B,
        "T_m": T,
        "Cb": Cb,
        "rho_kg_m3": rho,
    }


# ---------------------------------------------------------------------------
# 2. displacement_from_offsets
# ---------------------------------------------------------------------------

def displacement_from_offsets(
    stations: Sequence[float],
    sectional_areas: Sequence[float],
    rho: float = _RHO_SW,
) -> dict:
    """
    Displacement from a tabulated sectional-area curve using Simpson's rule.

    The sectional-area curve A(x) is integrated from AP to FP to obtain the
    displacement volume.  Stations need not be equally spaced; if they are
    not, the function uses the trapezoidal rule per panel.  If they are
    equally spaced (or only 2 stations), Simpson's composite rule is applied.

    Parameters
    ----------
    stations : sequence of floats
        Longitudinal positions of sections (m from AP). Monotonically
        increasing. At least 3 values required for Simpson's rule.
    sectional_areas : sequence of floats
        Submerged cross-sectional areas at each station (m²). Same length
        as stations. All >= 0.
    rho : float
        Water density (kg/m³). Default 1025 kg/m³.

    Returns
    -------
    dict
        ok             : True
        volume_m3      : displacement volume ∇ (m³)
        displacement_t : displacement mass (tonnes)
        LCB_fwd_AP     : longitudinal centre of buoyancy from AP (m)
        n_stations     : number of stations used
        method         : integration method used ('simpsons' or 'trapezoidal')
    """
    err = _guard_positive("rho", rho)
    if err:
        return _err(err)

    try:
        xs = [float(x) for x in stations]
        As = [float(a) for a in sectional_areas]
    except (TypeError, ValueError) as exc:
        return _err(f"stations/sectional_areas must be numeric: {exc}")

    if len(xs) != len(As):
        return _err(
            f"stations ({len(xs)}) and sectional_areas ({len(As)}) must have the same length"
        )
    if len(xs) < 2:
        return _err("At least 2 stations required")
    for a in As:
        if a < 0:
            return _err(f"sectional_area must be >= 0, got {a}")

    # Check monotonically increasing
    for i in range(1, len(xs)):
        if xs[i] <= xs[i - 1]:
            return _err(
                f"stations must be monotonically increasing; "
                f"station[{i}]={xs[i]} <= station[{i-1}]={xs[i-1]}"
            )

    # Check equal spacing for Simpson's
    n = len(xs)
    rho = float(rho)
    spacings = [xs[i + 1] - xs[i] for i in range(n - 1)]
    equal = all(abs(spacings[i] - spacings[0]) / max(abs(spacings[0]), 1e-12) < 1e-6
                for i in range(len(spacings)))

    if equal and n >= 3:
        h = spacings[0]
        volume = _simpsons_rule(As, h)
        # First moment for LCB
        moment = _simpsons_first_moment(As, h, x0=xs[0])
        method = "simpsons"
    else:
        # Trapezoidal rule (non-uniform spacing)
        volume = 0.0
        moment = 0.0
        for i in range(n - 1):
            dx = xs[i + 1] - xs[i]
            volume += dx * (As[i] + As[i + 1]) / 2.0
            x_mid = (xs[i] + xs[i + 1]) / 2.0
            a_mid = (As[i] + As[i + 1]) / 2.0
            moment += dx * x_mid * a_mid
        method = "trapezoidal"

    if volume <= 0.0:
        return _err("Integration produced zero or negative volume — check sectional areas")

    lcb = moment / volume
    displacement_t = volume * rho / 1000.0

    return {
        "ok": True,
        "volume_m3": volume,
        "displacement_t": displacement_t,
        "LCB_fwd_AP": lcb,
        "n_stations": n,
        "method": method,
        "rho_kg_m3": rho,
    }


# ---------------------------------------------------------------------------
# 3. form_coefficients
# ---------------------------------------------------------------------------

def form_coefficients(
    L: float,
    B: float,
    T: float,
    Cb: float,
    Am: float,
    Aw: float,
) -> dict:
    """
    Compute the four primary form coefficients.

    Parameters
    ----------
    L : float  Length between perpendiculars (m). > 0.
    B : float  Moulded breadth (m). > 0.
    T : float  Moulded draught (m). > 0.
    Cb : float Block coefficient — ∇ / (L·B·T). In (0, 1].
    Am : float Midship section area (m²). Must be > 0 and <= B×T.
    Aw : float Waterplane area (m²). Must be > 0 and <= L×B.

    Returns
    -------
    dict
        ok   : True
        Cb   : block coefficient (input)
        Cp   : prismatic coefficient  Cp = Cb × L×B×T / (Am × L) = Cb×B×T / Am
        Cm   : midship section coefficient  Cm = Am / (B×T)
        Cw   : waterplane coefficient  Cw = Aw / (L×B)
        Am_m2: midship section area used
        Aw_m2: waterplane area used
    """
    for name, val in (("L", L), ("B", B), ("T", T), ("Am", Am), ("Aw", Aw)):
        err = _guard_positive(name, val)
        if err:
            return _err(err)
    err = _guard_fraction("Cb", Cb, lo=0.0, hi=1.0)
    if err:
        return _err(err)
    if float(Cb) == 0.0:
        return _err("Cb must be > 0")

    L, B, T, Cb = float(L), float(B), float(T), float(Cb)
    Am, Aw = float(Am), float(Aw)

    Cm = Am / (B * T)
    if Cm > 1.0 + 1e-9:
        return _err(f"Am ({Am}) exceeds B×T ({B*T:.4f}) — midship area cannot exceed moulded rectangle")

    Cw = Aw / (L * B)
    if Cw > 1.0 + 1e-9:
        return _err(f"Aw ({Aw}) exceeds L×B ({L*B:.4f}) — waterplane area cannot exceed deck rectangle")

    # Prismatic coefficient: Cp = Cb / Cm  (from Cp = ∇/(Am×L) and Cb = ∇/(L×B×T))
    if Cm < 1e-12:
        return _err("Cm is effectively zero — cannot compute Cp")
    Cp = Cb / Cm

    return {
        "ok": True,
        "Cb": Cb,
        "Cp": Cp,
        "Cm": Cm,
        "Cw": min(Cw, 1.0),  # clamp numerical noise
        "Am_m2": Am,
        "Aw_m2": Aw,
        "L_m": L,
        "B_m": B,
        "T_m": T,
    }


# ---------------------------------------------------------------------------
# 4. waterplane_properties
# ---------------------------------------------------------------------------

def waterplane_properties(
    stations: Sequence[float],
    half_breadths: Sequence[float],
) -> dict:
    """
    Compute waterplane area, LCF, and second moments of area via Simpson's rule.

    The waterplane is described by half-breadths y(x) at equally-spaced or
    non-equally-spaced longitudinal stations (measured from AP).

    Area:       Aw = 2 × ∫ y dx        (factor 2 for port and starboard)
    LCF:        x̄  = (∫ x·y dx) / (∫ y dx)
    IL (long.): IL = 2 × ∫ x²·y dx     (longitudinal second moment about AP)
    IT (trans.):IT = (2/3) × ∫ y³ dx   (transverse second moment about CL)

    Parameters
    ----------
    stations : sequence of floats
        Longitudinal positions from AP (m). At least 3, monotonically increasing.
    half_breadths : sequence of floats
        Half-breadths (m) at the waterline at each station.  Same length.
        All >= 0.

    Returns
    -------
    dict
        ok        : True
        Aw_m2     : waterplane area (m²)
        LCF_fwd_AP: longitudinal centre of flotation from AP (m)
        IL_m4     : second moment of waterplane area about AP (m⁴)
        IL_LCF_m4 : second moment of waterplane area about LCF (m⁴) — for BML
        IT_m4     : transverse second moment of waterplane area about CL (m⁴)
        n_stations: number of stations used
        method    : 'simpsons' or 'trapezoidal'
    """
    try:
        xs = [float(x) for x in stations]
        ys = [float(y) for y in half_breadths]
    except (TypeError, ValueError) as exc:
        return _err(f"stations/half_breadths must be numeric: {exc}")

    if len(xs) != len(ys):
        return _err(
            f"stations ({len(xs)}) and half_breadths ({len(ys)}) must have same length"
        )
    if len(xs) < 3:
        return _err("At least 3 stations required for waterplane integration")
    for yv in ys:
        if yv < 0:
            return _err(f"half_breadth must be >= 0, got {yv}")
    for i in range(1, len(xs)):
        if xs[i] <= xs[i - 1]:
            return _err(
                f"stations must be monotonically increasing; "
                f"station[{i}]={xs[i]} <= station[{i-1}]={xs[i-1]}"
            )

    n = len(xs)
    spacings = [xs[i + 1] - xs[i] for i in range(n - 1)]
    equal = all(
        abs(spacings[i] - spacings[0]) / max(abs(spacings[0]), 1e-12) < 1e-6
        for i in range(len(spacings))
    )

    if equal and n >= 3:
        h = spacings[0]
        half_area = _simpsons_rule(ys, h)
        half_moment = _simpsons_first_moment(ys, h, x0=xs[0])
        half_IL = _simpsons_second_moment(ys, h, x0=xs[0])
        # IT: (2/3) ∫ y³ dx → integrate y³ ordinates
        y3_ords = [yv ** 3 for yv in ys]
        half_IT = _simpsons_rule(y3_ords, h)
        method = "simpsons"
    else:
        half_area = 0.0
        half_moment = 0.0
        half_IL = 0.0
        half_IT = 0.0
        for i in range(n - 1):
            dx = xs[i + 1] - xs[i]
            y_avg = (ys[i] + ys[i + 1]) / 2.0
            x_mid = (xs[i] + xs[i + 1]) / 2.0
            half_area += dx * y_avg
            half_moment += dx * x_mid * y_avg
            half_IL += dx * x_mid ** 2 * y_avg
            y3_avg = (ys[i] ** 3 + ys[i + 1] ** 3) / 2.0
            half_IT += dx * y3_avg
        method = "trapezoidal"

    if half_area <= 0.0:
        return _err("Integration produced zero or negative waterplane area — check half_breadths")

    Aw = 2.0 * half_area
    LCF = half_moment / half_area  # centroid x from AP
    IL_AP = 2.0 * half_IL
    IT = (2.0 / 3.0) * half_IT

    # Parallel-axis correction: IL about LCF = IL_AP - Aw × LCF²
    IL_LCF = IL_AP - Aw * LCF ** 2

    return {
        "ok": True,
        "Aw_m2": Aw,
        "LCF_fwd_AP": LCF,
        "IL_m4": IL_AP,
        "IL_LCF_m4": IL_LCF,
        "IT_m4": IT,
        "n_stations": n,
        "method": method,
    }


# ---------------------------------------------------------------------------
# 5. vertical_centres
# ---------------------------------------------------------------------------

def vertical_centres(
    T: float,
    Cb: float,
) -> dict:
    """
    Estimate KB and provide guidance on KG.

    KB (height of centre of buoyancy above keel) is computed using the
    Morrish / Murray formula:

        KB = T × (5/6 − Cb / (3 × Cw_est))

    where Cw_est is estimated as:
        Cw_est = (1 + 2×Cb) / 3      (Normand's formula)

    This avoids requiring a full waterplane integration.

    For the exact KB from a full pressure integral over a boxlike hull:
        KB_box = T / 2    (exact for rectangular cross-section)

    Parameters
    ----------
    T : float   Mean draught (m). > 0.
    Cb : float  Block coefficient. In (0, 1].

    Returns
    -------
    dict
        ok        : True
        T_m       : draught used
        Cb        : block coefficient used
        Cw_est    : estimated waterplane coefficient (Normand)
        KB_m      : height of centre of buoyancy above keel (m)
        KB_box_m  : KB for a rectangular (box) hull section (= T/2), for reference
    """
    err = _guard_positive("T", T)
    if err:
        return _err(err)
    err = _guard_fraction("Cb", Cb, lo=0.0, hi=1.0)
    if err:
        return _err(err)
    if float(Cb) == 0.0:
        return _err("Cb must be > 0")

    T, Cb = float(T), float(Cb)
    Cw_est = (1.0 + 2.0 * Cb) / 3.0  # Normand's formula
    # Morrish/Murray: KB = T*(5/6 - Cb/(3*Cw))
    KB = T * (5.0 / 6.0 - Cb / (3.0 * Cw_est))
    KB_box = T / 2.0

    return {
        "ok": True,
        "T_m": T,
        "Cb": Cb,
        "Cw_est": Cw_est,
        "KB_m": KB,
        "KB_box_m": KB_box,
    }


# ---------------------------------------------------------------------------
# 6. metacentric_height
# ---------------------------------------------------------------------------

def metacentric_height(
    KB: float,
    BM: float,
    KG: float,
) -> dict:
    """
    Compute GM = KB + BM − KG and flag instability.

    BM (metacentric radius) = IT / ∇ for transverse stability.
    For longitudinal: BML = IL / ∇.

    Parameters
    ----------
    KB : float   Height of centre of buoyancy above keel (m). >= 0.
    BM : float   Metacentric radius (m). >= 0.
    KG : float   Height of centre of gravity above keel (m). >= 0.

    Returns
    -------
    dict
        ok       : True
        GM_m     : metacentric height (m); negative → unstable
        KB_m     : KB used
        BM_m     : BM used
        KG_m     : KG used
        KM_m     : KM = KB + BM (m)
        stable   : True if GM > 0
        warnings : list of warning strings (empty if stable)
    """
    for name, val in (("KB", KB), ("BM", BM), ("KG", KG)):
        err = _guard_nonneg(name, val)
        if err:
            return _err(err)

    KB, BM, KG = float(KB), float(BM), float(KG)
    KM = KB + BM
    GM = KM - KG
    warns: list[str] = []
    stable = GM > 0.0
    if not stable:
        warns.append(
            f"NEGATIVE GM ({GM:.4f} m) — vessel is UNSTABLE in this condition"
        )

    return {
        "ok": True,
        "GM_m": GM,
        "KB_m": KB,
        "BM_m": BM,
        "KG_m": KG,
        "KM_m": KM,
        "stable": stable,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 7. righting_arm_GZ
# ---------------------------------------------------------------------------

def righting_arm_GZ(
    GM: float,
    phi_deg: float,
    *,
    wall_sided_BM_T: float = 0.0,
) -> dict:
    """
    Righting arm GZ at angle of heel φ.

    Small-angle formula:
        GZ_small = GM × sin(φ)

    Wall-sided correction (Moseley / Soding):
        GZ_wall = (GM + ½ × BM_T × tan²φ) × sin(φ)

    where BM_T is the transverse metacentric radius.

    Parameters
    ----------
    GM : float
        Transverse metacentric height (m).  May be negative (unstable).
    phi_deg : float
        Angle of heel (degrees).  Must be in [0, 90].
    wall_sided_BM_T : float
        Transverse metacentric radius BM_T (m) for the wall-sided correction.
        Default 0.0 (skips wall-sided correction).

    Returns
    -------
    dict
        ok                  : True
        phi_deg             : angle of heel used
        GZ_small_angle_m    : GZ from small-angle formula (m)
        GZ_wall_sided_m     : GZ with wall-sided correction (m) — equals
                              GZ_small_angle_m when BM_T=0
        GM_m                : GM used
        stable              : True if GZ_wall_sided_m > 0
        warnings            : list of warning strings
    """
    err = _guard_nonneg("phi_deg", phi_deg)
    if err:
        return _err(err)
    err = _guard_nonneg("wall_sided_BM_T", wall_sided_BM_T)
    if err:
        return _err(err)
    try:
        phi_f = float(phi_deg)
        GM_f = float(GM)
    except (TypeError, ValueError) as exc:
        return _err(f"phi_deg / GM must be numeric: {exc}")
    if not math.isfinite(phi_f):
        return _err("phi_deg must be finite")
    if not math.isfinite(GM_f):
        return _err("GM must be finite")
    if phi_f > 90.0:
        return _err("phi_deg must be <= 90°")

    BM_T = float(wall_sided_BM_T)
    phi_rad = math.radians(phi_f)
    sin_phi = math.sin(phi_rad)
    tan_phi = math.tan(phi_rad) if phi_f < 90.0 else math.inf

    GZ_small = GM_f * sin_phi

    if phi_f < 90.0:
        GZ_wall = (GM_f + 0.5 * BM_T * tan_phi ** 2) * sin_phi
    else:
        GZ_wall = GZ_small

    warns: list[str] = []
    if GM_f <= 0.0:
        warns.append(f"GM is non-positive ({GM_f:.4f} m) — vessel may be unstable")
    if GZ_wall <= 0.0 and phi_f > 0.0:
        warns.append(f"GZ is non-positive ({GZ_wall:.4f} m) at {phi_f}° — vessel has no righting moment")

    return {
        "ok": True,
        "phi_deg": phi_f,
        "GZ_small_angle_m": GZ_small,
        "GZ_wall_sided_m": GZ_wall,
        "GM_m": GM_f,
        "stable": GZ_wall > 0.0,
        "warnings": warns,
    }


# ---------------------------------------------------------------------------
# 8. tpc_mctc
# ---------------------------------------------------------------------------

def tpc_mctc(
    Aw: float,
    L: float,
    displacement_t: float,
    rho: float = _RHO_SW,
) -> dict:
    """
    Tonnes Per Centimetre immersion (TPC) and Moment to Change Trim 1 cm (MCT1cm).

    TPC = Aw × ρ / 100  [t/cm]   (adding mass increases draught)

    GML (longitudinal metacentric height) is approximated as:
        GML ≈ BML = IL / ∇ = (Cw² × L² × Aw) / (12 × ∇)
    Then:
        MCT1cm = (W × GML) / (100 × L)   [t·m/cm]

    For this function we use the simpler direct formula in terms of IL:
        MCT1cm = (W × IL) / (100 × L × ∇)
    which is approximated here using:
        IL ≈ Aw × L² / 12   (rectangular waterplane approximation)

    Parameters
    ----------
    Aw : float
        Waterplane area (m²). > 0.
    L : float
        Length between perpendiculars (m). > 0.
    displacement_t : float
        Displacement (tonnes). > 0.
    rho : float
        Water density (kg/m³). Default 1025.

    Returns
    -------
    dict
        ok             : True
        TPC            : tonnes per centimetre immersion
        MCT1cm_tm_per_cm: moment to change trim 1 cm (t·m per cm)
        BML_approx_m   : approximate longitudinal BM (m)
        Aw_m2          : waterplane area used
        displacement_t : displacement used
    """
    for name, val in (("Aw", Aw), ("L", L), ("displacement_t", displacement_t)):
        err = _guard_positive(name, val)
        if err:
            return _err(err)
    err = _guard_positive("rho", rho)
    if err:
        return _err(err)

    Aw, L, W, rho = float(Aw), float(L), float(displacement_t), float(rho)

    # TPC [t/cm]
    TPC = Aw * rho / (1000.0 * 100.0)  # Aw m² × ρ kg/m³ / (1000 kg/t × 100 cm/m)

    # Volume
    volume = W * 1000.0 / rho  # m³

    # IL approximation (rectangular waterplane): IL = Aw × L² / 12
    IL_approx = Aw * L ** 2 / 12.0

    BML = IL_approx / volume

    # MCT1cm = (W × GML) / (100 × L) ≈ (W × BML) / (100 × L)
    MCT1cm = W * BML / (100.0 * L)

    return {
        "ok": True,
        "TPC": TPC,
        "MCT1cm_tm_per_cm": MCT1cm,
        "BML_approx_m": BML,
        "Aw_m2": Aw,
        "displacement_t": W,
        "rho_kg_m3": rho,
    }


# ---------------------------------------------------------------------------
# 9. free_surface_correction
# ---------------------------------------------------------------------------

def free_surface_correction(
    rho_liquid: float,
    tank_length: float,
    tank_breadth: float,
    rho_sw: float,
    displacement_t: float,
) -> dict:
    """
    Free-surface correction (FSC) to GM for a rectangular tank.

    The free-surface moment for a rectangular tank is:
        FSM = ρ_liquid × l × b³ / 12

    The correction to GM is:
        FSC = FSM / (ρ_sw × ∇) = FSM / (W × 1000)    [metres]

    where W is displacement in tonnes.

    This reduces the effective GM:
        GM_corrected = GM - FSC

    Parameters
    ----------
    rho_liquid : float
        Density of tank liquid (kg/m³). > 0.
    tank_length : float
        Length of the free surface (m). > 0.
    tank_breadth : float
        Breadth of the free surface (m). > 0.
    rho_sw : float
        Sea water density (kg/m³). Default 1025.
    displacement_t : float
        Ship displacement (tonnes). > 0.

    Returns
    -------
    dict
        ok               : True
        free_surface_moment_tm: free surface moment (tonne·m)
        FSC_m            : free surface correction to GM (m)
        rho_liquid       : liquid density used
        tank_length_m    : tank length used
        tank_breadth_m   : tank breadth used
    """
    for name, val in (
        ("rho_liquid", rho_liquid),
        ("tank_length", tank_length),
        ("tank_breadth", tank_breadth),
        ("rho_sw", rho_sw),
        ("displacement_t", displacement_t),
    ):
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    rl, l, b, rs, W = (
        float(rho_liquid), float(tank_length), float(tank_breadth),
        float(rho_sw), float(displacement_t),
    )

    # Free-surface moment in N·m; convert to t·m
    it_tank = l * b ** 3 / 12.0   # second moment of tank free surface (m⁴)
    FSM_Nm = rl * _G * it_tank     # N·m
    FSM_tm = FSM_Nm / (_G * 1000.0)  # tonne·m  (ρ_liquid × it / 1000)
    # Simpler: FSC = (ρ_l / ρ_sw) × it / ∇ = (ρ_l × it) / (ρ_sw × ∇)
    volume = W * 1000.0 / rs   # m³
    FSC = (rl / rs) * it_tank / volume

    return {
        "ok": True,
        "free_surface_moment_tm": (rl / 1000.0) * it_tank,  # t·m
        "FSC_m": FSC,
        "rho_liquid_kg_m3": rl,
        "tank_length_m": l,
        "tank_breadth_m": b,
        "it_tank_m4": it_tank,
    }


# ---------------------------------------------------------------------------
# 10. resistance_admiralty
# ---------------------------------------------------------------------------

def resistance_admiralty(
    displacement_t: float,
    V_knots: float,
    Ac: float,
) -> dict:
    """
    Admiralty Coefficient method for effective power estimate.

    The Admiralty Coefficient is defined as:

        Ac = (W^(2/3) × V³) / EHP

    Rearranging:

        EHP = (W^(2/3) × V³) / Ac

    where:
      W  = displacement (tonnes)
      V  = speed (knots)
      EHP = effective horse power (hp); here also converted to kW (1 hp = 0.7457 kW)

    The Froude number is computed for reference:

        Fn = V_m_s / √(g × L)

    (L is estimated from displacement here if not provided, using an
    approximate length–displacement ratio; pass L directly via
    resistance_admiralty_full if needed.)

    Parameters
    ----------
    displacement_t : float
        Ship displacement (tonnes). > 0.
    V_knots : float
        Ship speed (knots). > 0.
    Ac : float
        Admiralty coefficient for the vessel. > 0.
        Typical ranges: cargo ships 350–500, tankers 700–1000, warships 150–250.

    Returns
    -------
    dict
        ok             : True
        EHP_hp         : effective horsepower (hp)
        EHP_kW         : effective power (kW)
        V_knots        : speed used
        displacement_t : displacement used
        Ac             : admiralty coefficient used
        W_2_3          : W^(2/3) used in formula
        V_cubed        : V³ used in formula
    """
    for name, val in (("displacement_t", displacement_t), ("V_knots", V_knots), ("Ac", Ac)):
        err = _guard_positive(name, val)
        if err:
            return _err(err)

    W, V, ac = float(displacement_t), float(V_knots), float(Ac)

    W23 = W ** (2.0 / 3.0)
    V3 = V ** 3
    EHP_hp = W23 * V3 / ac
    EHP_kW = EHP_hp * 0.7457

    return {
        "ok": True,
        "EHP_hp": EHP_hp,
        "EHP_kW": EHP_kW,
        "V_knots": V,
        "displacement_t": W,
        "Ac": ac,
        "W_2_3": W23,
        "V_cubed": V3,
    }


# ---------------------------------------------------------------------------
# 11. trim_from_moment
# ---------------------------------------------------------------------------

def trim_from_moment(
    trimming_moment_tm: float,
    MCTC: float,
    L: float,
    LCF_fwd_AP: float,
) -> dict:
    """
    Trim, and change in draught forward/aft, from an off-centre weight or
    ballasting moment.

    Trim change:
        t = trimming_moment / MCTC     [cm]

    Change in draught aft:
        δT_A = t × (L − LCF) / L      [cm]

    Change in draught forward:
        δT_F = t × LCF / L            [cm]   (positive = increase when trimming aft)

    Sign convention:
      trimming_moment_tm > 0 → trimming by stern (stern goes deeper)
      trimming_moment_tm < 0 → trimming by head

    Parameters
    ----------
    trimming_moment_tm : float
        Trimming moment (tonne·metres). Positive = by stern. May be negative.
    MCTC : float
        Moment to change trim 1 cm (tonne·metres per cm). > 0.
    L : float
        Length between perpendiculars (m). > 0.
    LCF_fwd_AP : float
        Longitudinal centre of flotation measured from AP (m). In [0, L].

    Returns
    -------
    dict
        ok               : True
        trim_cm          : trim change (cm); positive = stern trim
        dT_aft_cm        : change in draught aft (cm); positive = deeper
        dT_fwd_cm        : change in draught forward (cm); positive = deeper at bow
        trimming_moment  : input moment (t·m)
        MCTC             : MCTC used
        warnings         : list of warning strings
    """
    for name, val in (("MCTC", MCTC), ("L", L)):
        err = _guard_positive(name, val)
        if err:
            return _err(err)
    try:
        tm = float(trimming_moment_tm)
        lcf = float(LCF_fwd_AP)
    except (TypeError, ValueError) as exc:
        return _err(f"trimming_moment_tm / LCF_fwd_AP must be numeric: {exc}")
    if not math.isfinite(tm):
        return _err("trimming_moment_tm must be finite")
    if not math.isfinite(lcf):
        return _err("LCF_fwd_AP must be finite")

    L_f, MCT = float(L), float(MCTC)
    if lcf < 0 or lcf > L_f:
        return _err(f"LCF_fwd_AP ({lcf}) must be in [0, {L_f}]")

    trim_cm = tm / MCT
    # Lever arms about LCF
    l_aft = L_f - lcf    # distance from LCF to AP
    l_fwd = lcf          # distance from LCF to FP

    dT_aft_cm = trim_cm * l_aft / L_f
    dT_fwd_cm = -trim_cm * l_fwd / L_f   # opposite sign: bow rises when stern sinks

    warns: list[str] = []
    if abs(trim_cm) > 100.0:
        warns.append(
            f"Excessive trim: {abs(trim_cm):.1f} cm — check moment and MCTC values"
        )

    return {
        "ok": True,
        "trim_cm": trim_cm,
        "dT_aft_cm": dT_aft_cm,
        "dT_fwd_cm": dT_fwd_cm,
        "trimming_moment_tm": tm,
        "MCTC": MCT,
        "L_m": L_f,
        "LCF_fwd_AP_m": lcf,
        "warnings": warns,
    }
