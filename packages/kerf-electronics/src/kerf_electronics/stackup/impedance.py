"""
PCB controlled-impedance stackup designer — closed-form models.

This module is distinct from:
  • kerf_electronics.si      — signal-integrity simulation (crosstalk, termination)
  • kerf_electronics.emc     — radiated/conducted EMC pre-compliance
  • kerf_electronics.pdn     — power-delivery network (IR-drop, decap)
  • kerf_electronics.dsp     — DSP / digital filter design
  • kerf_electronics.powerconv — power converter sizing

All functions are pure Python (math module only) and follow the kerf
never-raise contract:
  - Validation errors are returned as dicts: {ok: False, reason: str}
  - Out-of-fabrication-range or unrealizable-width conditions are flagged via
    warnings.warn and reported in the result dict; they never raise.
  - Exceptions are never raised to callers.

Formulas and references
-----------------------
Microstrip Z0 (single-ended)
    Hammerstad-Jensen closed-form, as presented in:
    Wadell, "Transmission Line Design Handbook", Artech House, 1991, §3.4.
    IPC-2141A (2004) equations 1-1 / 1-2 (equivalent).

    For W/H <= 1:
        Z0 = (60 / sqrt(er_eff)) * ln(8*H/W + W/(4*H))
    For W/H > 1:
        Z0 = (120*pi / sqrt(er_eff)) / (W/H + 1.393 + 0.667*ln(W/H + 1.444))

    where er_eff = (er+1)/2 + (er-1)/2 * (1 + 12*H/W)^(-0.5) + C_T
    and C_T = -(er-1)/4.6 * T/(W*sqrt(H)) is the trace-thickness correction
    (Schneider 1969; T=0 gives the original Hammerstad formula).

Embedded microstrip Z0
    Buried trace with dielectric over the top (Wadell §3.4.4):
        er_eff_emb = er_eff * (1 - exp(-1.55 * d/H))   (approx)
        Z0 = Z0_microstrip_at_er_eff_emb

    where d = cover layer thickness above the trace, H = height above ref plane.
    For d = 0 this degenerates to the standard microstrip result.

Symmetric stripline Z0
    IPC-2141A equation 2-1 / Wadell §4.3 (buried between two equal-distance planes):
        Z0 = (60 / sqrt(er)) * ln(4*B / (0.67*pi*(0.8*W + T)))
    where B = total substrate thickness between both reference planes.
    Validity: 0.1 <= W/B <= 1.0 (IPC-2141A §2).

Asymmetric stripline Z0
    Wadell §4.5 (different distances to the two ground planes):
        Z0 = (80 / sqrt(er)) * ln(4*(b/(0.67*pi*(0.8*W + T))))
             * (b / (b + c + T))    [Wadell eqn 4.5-3]
    where b = distance from trace centre to top plane,
          c = distance from trace centre to bottom plane.
    (simplified closed form; accurate within ~5% for c/b in 0.5..2.0)

Coplanar-waveguide with ground (CPWG) Z0
    Hammerstad-Jensen via conformal mapping (Wadell §5.2 / Simons 2001):
        k  = a / b   where a = W/2, b = W/2 + gap
        k' = sqrt(1 - k^2)
        k1 = sinh(pi*a / (2*H)) / sinh(pi*b / (2*H))
        k1'= sqrt(1 - k1^2)
        er_eff = (er+1) / 2 * K(k)*K(k1') / (K(k')*K(k1))
    Approximate K(k)/K(k') via Hilberg (1966):
        if k <= 1/sqrt(2):  K(k)/K(k') ≈ pi / ln(2*(1+sqrt(k'))/(1-sqrt(k')))
                            (rounded; uses log approximation)
        else:               K(k)/K(k') ≈ ln(2*(1+sqrt(k))/(1-sqrt(k))) / pi
        Z0 = 60*pi / (sqrt(er_eff) * (K(k)/K(k') + K(k1)/K(k1')))

Differential impedance
    Wadell §3.7 (microstrip) and §4.3 (stripline):
        Zdiff = 2 * Z0 * (1 - 0.347 * exp(-2.9 * S / H))
    where S = edge-to-edge spacing, H = height above reference plane for
    microstrip, or B for stripline.

Effective dielectric constant
    Microstrip: er_eff from Hammerstad with thickness correction.
    Embedded microstrip: er_eff_emb as above.
    Stripline (symmetric/asymmetric): er_eff = er (fully enclosed in dielectric).
    CPWG: er_eff from conformal-mapping formula above.

Propagation delay
    Td [ps/mm] = sqrt(er_eff) / c_mm_ps
    where c_mm_ps = 0.299792458 mm/ps (speed of light).

Wavelength
    λ [mm] = c_mm_ps / (freq_hz * 1e-12 * sqrt(er_eff))
           = 299.792458 / (freq_hz_in_GHz * sqrt(er_eff))

Trace-width solver for target Z0
    Bisection search over W in [W_min, W_max] with relative tolerance 0.1%.
    If no root is found in the search range a warning is issued; the closest
    edge value is returned with the flag unrealizable=True.

Differential pair spacing for target Zdiff
    Bisection over S in [0, S_max] using the differential impedance formula.

Conductor (skin-effect) attenuation
    Hammerstad-Jensen (Wadell §3.5):
        alpha_c [dB/mm] = Rs / (pi * W * Z0) * 20 / ln(10)
    where Rs = sqrt(pi * f * mu0 * rho)  [surface resistance in Ohm/sq]
          rho = resistivity of copper = 1.724e-8 Ohm·m (at 20°C).
    A correction factor of 1.25 for non-ideal rough surface is applied when
    roughness_um > 0 (Huray sphere model approximation, IPC-2141A §3):
        alpha_c_rough = alpha_c * (1 + (2/pi) * arctan(1.4 * (roughness_um * 1e-6 / delta_s)^2))
    where delta_s = sqrt(rho / (pi * f * mu0)) is the skin depth.

Dielectric (loss-tangent) attenuation
    Standard transmission-line formula (Pozar "Microwave Engineering" §3.1):
        alpha_d [dB/mm] = 27.3 * er / sqrt(er_eff) * (er_eff - 1)/(er - 1) * tan_d * f_GHz / c
    Simplified form (Wadell §3.5 / IPC-2141A §3):
        alpha_d [dB/mm] = (pi * f_GHz * sqrt(er_eff) * tan_d) / (c_mm_ps * 1000) * 20/ln(10)

Copper weight → thickness conversion
    Industry standard: 1 oz/ft² ≈ 34.8 µm  (IPC-6012 §3.2).

Fab-range warnings
    Trace width:   < 0.075 mm or > 6.0 mm
    Trace spacing: < 0.075 mm
    Dielectric height: < 0.05 mm or > 3.5 mm
    These bounds are conservative (many fabs have tighter design rules).

Author: imranparuk
"""
from __future__ import annotations

import math
import warnings
from typing import List, Optional

# ── Physical constants ────────────────────────────────────────────────────────

_C_MM_PS: float = 0.299792458     # speed of light [mm/ps]
_MU0: float = 4 * math.pi * 1e-7  # free-space permeability [H/m]
_RHO_CU: float = 1.724e-8         # copper resistivity [Ohm·m] at 20 °C
_OZ_TO_MM: float = 0.0348          # 1 oz/ft² copper weight → mm thickness

# ── Fab-range bounds (conservative; warn, never raise) ────────────────────────

_FAB_W_MIN_MM = 0.075    # minimum trace width
_FAB_W_MAX_MM = 6.0      # maximum trace width
_FAB_S_MIN_MM = 0.075    # minimum trace spacing
_FAB_H_MIN_MM = 0.050    # minimum dielectric height
_FAB_H_MAX_MM = 3.5      # maximum dielectric height


# ── Validation helpers ────────────────────────────────────────────────────────

def _validate_positive(value, name: str) -> Optional[str]:
    if not isinstance(value, (int, float)) or math.isnan(value) or value <= 0:
        return f"{name} must be a positive number, got {value!r}"
    return None


def _validate_nonneg(value, name: str) -> Optional[str]:
    if not isinstance(value, (int, float)) or math.isnan(value) or value < 0:
        return f"{name} must be >= 0, got {value!r}"
    return None


def _fab_warn_width(W_mm: float, context: str = "") -> None:
    if W_mm < _FAB_W_MIN_MM:
        warnings.warn(
            f"stackup{context}: trace width {W_mm:.4f} mm is below typical fab minimum "
            f"({_FAB_W_MIN_MM} mm). Check with your PCB manufacturer.",
            stacklevel=3,
        )
    elif W_mm > _FAB_W_MAX_MM:
        warnings.warn(
            f"stackup{context}: trace width {W_mm:.4f} mm exceeds typical fab maximum "
            f"({_FAB_W_MAX_MM} mm). Check with your PCB manufacturer.",
            stacklevel=3,
        )


def _fab_warn_height(H_mm: float, context: str = "") -> None:
    if H_mm < _FAB_H_MIN_MM:
        warnings.warn(
            f"stackup{context}: dielectric height {H_mm:.4f} mm is below typical fab minimum "
            f"({_FAB_H_MIN_MM} mm). Check with your PCB manufacturer.",
            stacklevel=3,
        )
    elif H_mm > _FAB_H_MAX_MM:
        warnings.warn(
            f"stackup{context}: dielectric height {H_mm:.4f} mm exceeds typical maximum "
            f"({_FAB_H_MAX_MM} mm).",
            stacklevel=3,
        )


# ── Copper weight / thickness conversion ─────────────────────────────────────


def copper_weight_to_thickness_mm(oz: float) -> dict:
    """
    Convert copper weight in oz/ft² to foil thickness in mm.

    Industry standard: 1 oz/ft² ≈ 34.8 µm  (IPC-6012 §3.2 / IPC-4562).

    Parameters
    ----------
    oz : float — copper weight [oz/ft²], e.g. 0.5, 1.0, 2.0

    Returns
    -------
    dict with keys: ok, oz, thickness_mm, thickness_um
    """
    err = _validate_positive(oz, "oz")
    if err:
        return {"ok": False, "reason": err}
    thickness_mm = oz * _OZ_TO_MM
    return {
        "ok": True,
        "oz": oz,
        "thickness_mm": round(thickness_mm, 6),
        "thickness_um": round(thickness_mm * 1000, 3),
        "note": "1 oz/ft² = 34.8 µm (IPC-6012 §3.2)",
    }


# ── Hammerstad-Jensen microstrip effective permittivity ──────────────────────

def _microstrip_er_eff_hj(W: float, H: float, T: float, er: float) -> float:
    """
    Effective dielectric constant for microstrip — Hammerstad-Jensen with
    trace-thickness correction (Schneider 1969).

    Parameters: W [mm], H [mm], T [mm] (trace thickness), er (relative permittivity).
    All must be > 0.
    """
    # Width correction for trace thickness (IPC-2141A §1)
    # Delta_W accounts for fringing effects at trace edges
    if T > 0 and W > 0:
        dW = T / math.pi * (1.0 + math.log(2.0 * H / T))
        W_eff = W + dW
    else:
        W_eff = W

    u = W_eff / H  # normalised width

    er_eff = (er + 1.0) / 2.0 + (er - 1.0) / 2.0 * (1.0 + 12.0 / u) ** -0.5
    return er_eff


def _microstrip_z0_from_er_eff(W: float, H: float, er_eff: float) -> float:
    """
    Microstrip Z0 from effective permittivity — Hammerstad-Jensen.
    W, H in consistent units (mm).
    """
    u = W / H
    if u <= 1.0:
        z0 = (60.0 / math.sqrt(er_eff)) * math.log(8.0 / u + u / 4.0)
    else:
        z0 = (120.0 * math.pi / math.sqrt(er_eff)) / (
            u + 1.393 + 0.667 * math.log(u + 1.444)
        )
    return z0


# ── Microstrip Z0 ─────────────────────────────────────────────────────────────


def microstrip_z0(
    W_mm: float,
    H_mm: float,
    er: float,
    T_mm: float = 0.035,
) -> dict:
    """
    Single-ended microstrip characteristic impedance (Hammerstad-Jensen).

    Parameters
    ----------
    W_mm : float — trace width [mm]
    H_mm : float — dielectric height above reference plane [mm]
    er   : float — substrate relative permittivity (e.g. 4.3 for FR4)
    T_mm : float — trace thickness [mm] (default 35 µm = 1 oz copper)

    Returns
    -------
    dict with keys: ok, Z0, er_eff, W_mm, H_mm, er, T_mm, warnings
    """
    for val, name in [(W_mm, "W_mm"), (H_mm, "H_mm"), (er, "er")]:
        err = _validate_positive(val, name)
        if err:
            return {"ok": False, "reason": err}
    err = _validate_nonneg(T_mm, "T_mm")
    if err:
        return {"ok": False, "reason": err}

    result_warnings = []
    _fab_warn_width(W_mm, ".microstrip_z0")
    _fab_warn_height(H_mm, ".microstrip_z0")

    if T_mm >= H_mm:
        warnings.warn(
            f"microstrip_z0: trace thickness T={T_mm} mm >= dielectric height H={H_mm} mm; "
            "formula unreliable.",
            stacklevel=2,
        )
        result_warnings.append("T >= H; formula may be unreliable")

    er_eff = _microstrip_er_eff_hj(W_mm, H_mm, T_mm, er)
    z0 = _microstrip_z0_from_er_eff(W_mm, H_mm, er_eff)

    return {
        "ok": True,
        "Z0": round(z0, 4),
        "er_eff": round(er_eff, 6),
        "W_mm": W_mm,
        "H_mm": H_mm,
        "er": er,
        "T_mm": T_mm,
        "formula": "Hammerstad-Jensen (Wadell §3.4 / IPC-2141A eq. 1-1/1-2)",
        "warnings": result_warnings,
    }


# ── Embedded microstrip Z0 ────────────────────────────────────────────────────


def embedded_microstrip_z0(
    W_mm: float,
    H_mm: float,
    er: float,
    d_mm: float,
    T_mm: float = 0.035,
) -> dict:
    """
    Embedded microstrip (trace buried under a cover layer) characteristic impedance.

    The cover layer modifies the effective permittivity:
        er_eff_emb = er_eff * (1 - exp(-1.55 * d / H))

    For d = 0 this degenerates to standard microstrip.

    Parameters
    ----------
    W_mm : float — trace width [mm]
    H_mm : float — dielectric height above reference plane [mm]
    er   : float — substrate relative permittivity
    d_mm : float — cover layer thickness above the trace [mm]
    T_mm : float — trace thickness [mm] (default 35 µm)

    Returns
    -------
    dict with keys: ok, Z0, er_eff, er_eff_embedded, W_mm, H_mm, er, d_mm, T_mm
    """
    for val, name in [(W_mm, "W_mm"), (H_mm, "H_mm"), (er, "er")]:
        err = _validate_positive(val, name)
        if err:
            return {"ok": False, "reason": err}
    for val, name in [(d_mm, "d_mm"), (T_mm, "T_mm")]:
        err = _validate_nonneg(val, name)
        if err:
            return {"ok": False, "reason": err}

    _fab_warn_width(W_mm, ".embedded_microstrip_z0")
    _fab_warn_height(H_mm, ".embedded_microstrip_z0")

    er_eff = _microstrip_er_eff_hj(W_mm, H_mm, T_mm, er)
    # Cover-layer correction (Wadell §3.4.4):
    # A dielectric cover above the trace increases er_eff toward er.
    # er_eff_emb = er - (er - er_eff) * exp(-k * d / H)
    # At d=0: er_eff_emb = er_eff (open microstrip).
    # As d→∞: er_eff_emb → er (fully embedded).
    if d_mm > 0:
        er_eff_emb = er - (er - er_eff) * math.exp(-1.55 * d_mm / H_mm)
        # Clamp to [er_eff, er] for numerical safety
        er_eff_emb = max(er_eff, min(er_eff_emb, er))
    else:
        er_eff_emb = er_eff

    z0 = _microstrip_z0_from_er_eff(W_mm, H_mm, er_eff_emb)

    return {
        "ok": True,
        "Z0": round(z0, 4),
        "er_eff": round(er_eff, 6),
        "er_eff_embedded": round(er_eff_emb, 6),
        "W_mm": W_mm,
        "H_mm": H_mm,
        "er": er,
        "d_mm": d_mm,
        "T_mm": T_mm,
        "formula": "Wadell §3.4.4 embedded microstrip",
    }


# ── Symmetric stripline Z0 ────────────────────────────────────────────────────


def stripline_z0_symmetric(
    W_mm: float,
    B_mm: float,
    er: float,
    T_mm: float = 0.035,
) -> dict:
    """
    Symmetric stripline characteristic impedance (IPC-2141A eq. 2-1 / Wadell §4.3).

    The trace is centred between two reference planes with total dielectric
    thickness B.

    Formula:
        Z0 = (60 / sqrt(er)) * ln(4*B / (0.67*pi*(0.8*W + T)))

    Valid range: 0.1 <= W/B <= 2.0 (outside this a warning is issued).

    Parameters
    ----------
    W_mm : float — trace width [mm]
    B_mm : float — total substrate thickness between reference planes [mm]
    er   : float — substrate relative permittivity
    T_mm : float — trace thickness [mm] (default 35 µm)

    Returns
    -------
    dict with keys: ok, Z0, er_eff, W_mm, B_mm, er, T_mm
    """
    for val, name in [(W_mm, "W_mm"), (B_mm, "B_mm"), (er, "er")]:
        err = _validate_positive(val, name)
        if err:
            return {"ok": False, "reason": err}
    err = _validate_nonneg(T_mm, "T_mm")
    if err:
        return {"ok": False, "reason": err}

    _fab_warn_width(W_mm, ".stripline_z0_symmetric")

    w_b_ratio = W_mm / B_mm
    if not (0.1 <= w_b_ratio <= 2.0):
        warnings.warn(
            f"stripline_z0_symmetric: W/B = {w_b_ratio:.3f} is outside the valid range "
            f"[0.1, 2.0] for IPC-2141A eq. 2-1; accuracy may be reduced.",
            stacklevel=2,
        )

    denom = 0.67 * math.pi * (0.8 * W_mm + T_mm)
    if denom <= 0:
        return {"ok": False, "reason": "degenerate geometry: 0.8*W + T <= 0"}
    argument = 4.0 * B_mm / denom
    if argument <= 1.0:
        warnings.warn(
            "stripline_z0_symmetric: log argument <= 1; geometry may be unrealizable.",
            stacklevel=2,
        )
    z0 = (60.0 / math.sqrt(er)) * math.log(max(argument, 1.001))

    return {
        "ok": True,
        "Z0": round(z0, 4),
        "er_eff": er,  # fully enclosed: er_eff = er
        "W_mm": W_mm,
        "B_mm": B_mm,
        "er": er,
        "T_mm": T_mm,
        "formula": "IPC-2141A eq. 2-1 / Wadell §4.3",
    }


# ── Asymmetric stripline Z0 ───────────────────────────────────────────────────


def stripline_z0_asymmetric(
    W_mm: float,
    b_mm: float,
    c_mm: float,
    er: float,
    T_mm: float = 0.035,
) -> dict:
    """
    Asymmetric stripline characteristic impedance (Wadell §4.5).

    The trace is located between two reference planes at unequal distances:
      b = distance from trace centre-line to top plane
      c = distance from trace centre-line to bottom plane

    Approximate formula (Wadell eqn 4.5-3, accurate within ~5% for c/b ∈ [0.5, 2.0]):
        Z0 = (80 / sqrt(er)) * ln(4*(b + c) / (0.67*pi*(0.8*W + T))) * (b / (b + c + T))

    Parameters
    ----------
    W_mm : float — trace width [mm]
    b_mm : float — distance from trace to top reference plane [mm]
    c_mm : float — distance from trace to bottom reference plane [mm]
    er   : float — substrate relative permittivity
    T_mm : float — trace thickness [mm] (default 35 µm)

    Returns
    -------
    dict with keys: ok, Z0, er_eff, W_mm, b_mm, c_mm, er, T_mm
    """
    for val, name in [(W_mm, "W_mm"), (b_mm, "b_mm"), (c_mm, "c_mm"), (er, "er")]:
        err = _validate_positive(val, name)
        if err:
            return {"ok": False, "reason": err}
    err = _validate_nonneg(T_mm, "T_mm")
    if err:
        return {"ok": False, "reason": err}

    _fab_warn_width(W_mm, ".stripline_z0_asymmetric")

    ratio = c_mm / b_mm
    if not (0.3 <= ratio <= 3.5):
        warnings.warn(
            f"stripline_z0_asymmetric: c/b = {ratio:.3f} is outside the typical valid "
            "range [0.3, 3.5] for Wadell eqn 4.5-3; accuracy reduced.",
            stacklevel=2,
        )

    B_total = b_mm + c_mm + T_mm
    denom = 0.67 * math.pi * (0.8 * W_mm + T_mm)
    if denom <= 0:
        return {"ok": False, "reason": "degenerate geometry: 0.8*W + T <= 0"}
    argument = 4.0 * (b_mm + c_mm) / denom
    z0 = (80.0 / math.sqrt(er)) * math.log(max(argument, 1.001)) * (b_mm / B_total)

    return {
        "ok": True,
        "Z0": round(z0, 4),
        "er_eff": er,
        "W_mm": W_mm,
        "b_mm": b_mm,
        "c_mm": c_mm,
        "er": er,
        "T_mm": T_mm,
        "formula": "Wadell §4.5 asymmetric stripline",
    }


# ── Coplanar waveguide with ground (CPWG) ────────────────────────────────────

def _elliptic_ratio(k: float) -> float:
    """
    Approximate K(k) / K(k') using the Hilberg (1966) log approximation.
    k must be in (0, 1).
    """
    if k <= 0.0 or k >= 1.0:
        return 1.0  # degenerate
    kp = math.sqrt(1.0 - k * k)
    if k <= 1.0 / math.sqrt(2.0):
        # K(k)/K(k') ≈ pi / ln(2*(1+sqrt(k'))/(1-sqrt(k')))
        sqkp = math.sqrt(kp)
        denom = 1.0 - sqkp
        if denom <= 1e-12:
            return 10.0  # near-degenerate: very high ratio
        return math.pi / math.log(2.0 * (1.0 + sqkp) / denom)
    else:
        # K(k)/K(k') ≈ ln(2*(1+sqrt(k))/(1-sqrt(k))) / pi
        sqk = math.sqrt(k)
        denom = 1.0 - sqk
        if denom <= 1e-12:
            return 10.0
        return math.log(2.0 * (1.0 + sqk) / denom) / math.pi


def cpwg_z0(
    W_mm: float,
    G_mm: float,
    H_mm: float,
    er: float,
    T_mm: float = 0.035,
) -> dict:
    """
    Coplanar waveguide with ground (CPWG) characteristic impedance.

    Uses conformal-mapping (Hammerstad-Jensen / Wadell §5.2):
        a = W / 2
        b = W / 2 + G
        k  = a / b
        k1 = sinh(pi*a/(2*H)) / sinh(pi*b/(2*H))
        er_eff = (er + 1) / 2 * K(k)*K(k1') / (K(k')*K(k1))
        Z0 = 60*pi / (sqrt(er_eff) * (K(k)/K(k') + K(k1)/K(k1')))

    Parameters
    ----------
    W_mm : float — trace (signal conductor) width [mm]
    G_mm : float — gap between signal conductor and ground planes [mm]
    H_mm : float — substrate height (to back-side reference plane) [mm]
    er   : float — substrate relative permittivity
    T_mm : float — trace thickness [mm] (default 35 µm, informational only)

    Returns
    -------
    dict with keys: ok, Z0, er_eff, W_mm, G_mm, H_mm, er, T_mm
    """
    for val, name in [(W_mm, "W_mm"), (G_mm, "G_mm"), (H_mm, "H_mm"), (er, "er")]:
        err = _validate_positive(val, name)
        if err:
            return {"ok": False, "reason": err}
    err = _validate_nonneg(T_mm, "T_mm")
    if err:
        return {"ok": False, "reason": err}

    _fab_warn_width(W_mm, ".cpwg_z0")
    if G_mm < _FAB_S_MIN_MM:
        warnings.warn(
            f"cpwg_z0: gap G={G_mm:.4f} mm is below typical fab minimum ({_FAB_S_MIN_MM} mm).",
            stacklevel=2,
        )

    a = W_mm / 2.0
    b = a + G_mm

    k = a / b
    if k <= 0.0 or k >= 1.0:
        return {"ok": False, "reason": "degenerate CPWG geometry: k = a/b out of (0,1)"}

    k1_num = math.sinh(math.pi * a / (2.0 * H_mm))
    k1_den = math.sinh(math.pi * b / (2.0 * H_mm))
    if k1_den <= 0:
        return {"ok": False, "reason": "degenerate CPWG geometry: sinh denominator = 0"}
    k1 = k1_num / k1_den
    if k1 <= 0.0 or k1 >= 1.0:
        k1 = max(1e-6, min(k1, 1.0 - 1e-6))

    r_k_kp = _elliptic_ratio(k)    # K(k) / K(k')
    r_k1_k1p = _elliptic_ratio(k1)  # K(k1) / K(k1')

    # er_eff via conformal mapping
    er_eff = (er + 1.0) / 2.0 * r_k_kp / r_k1_k1p

    denom_z = math.sqrt(er_eff) * (r_k_kp + r_k1_k1p)
    if denom_z <= 0:
        return {"ok": False, "reason": "degenerate CPWG geometry: zero denominator"}

    z0 = 60.0 * math.pi / denom_z

    return {
        "ok": True,
        "Z0": round(z0, 4),
        "er_eff": round(er_eff, 6),
        "W_mm": W_mm,
        "G_mm": G_mm,
        "H_mm": H_mm,
        "er": er,
        "T_mm": T_mm,
        "formula": "Wadell §5.2 conformal-mapping CPWG (Hilberg elliptic approximation)",
    }


# ── Differential impedance ────────────────────────────────────────────────────


def differential_microstrip_z0(
    W_mm: float,
    S_mm: float,
    H_mm: float,
    er: float,
    T_mm: float = 0.035,
) -> dict:
    """
    Differential microstrip impedance (Wadell §3.7).

    Uses single-ended Z0 with the coupling correction:
        Zdiff = 2 * Z0 * (1 - 0.347 * exp(-2.9 * S / H))

    Parameters
    ----------
    W_mm : float — trace width [mm]
    S_mm : float — edge-to-edge spacing between the two traces [mm]
    H_mm : float — dielectric height [mm]
    er   : float — relative permittivity
    T_mm : float — trace thickness [mm] (default 35 µm)

    Returns
    -------
    dict with keys: ok, Z0_single, Zdiff, er_eff, W_mm, S_mm, H_mm, er, T_mm
    """
    for val, name in [(W_mm, "W_mm"), (S_mm, "S_mm"), (H_mm, "H_mm"), (er, "er")]:
        err = _validate_positive(val, name)
        if err:
            return {"ok": False, "reason": err}
    err = _validate_nonneg(T_mm, "T_mm")
    if err:
        return {"ok": False, "reason": err}

    if S_mm < _FAB_S_MIN_MM:
        warnings.warn(
            f"differential_microstrip_z0: spacing S={S_mm:.4f} mm is below typical "
            f"fab minimum ({_FAB_S_MIN_MM} mm).",
            stacklevel=2,
        )

    se = microstrip_z0(W_mm=W_mm, H_mm=H_mm, er=er, T_mm=T_mm)
    if not se["ok"]:
        return se

    z0 = se["Z0"]
    er_eff = se["er_eff"]
    zdiff = 2.0 * z0 * (1.0 - 0.347 * math.exp(-2.9 * S_mm / H_mm))

    return {
        "ok": True,
        "Z0_single": round(z0, 4),
        "Zdiff": round(zdiff, 4),
        "er_eff": round(er_eff, 6),
        "W_mm": W_mm,
        "S_mm": S_mm,
        "H_mm": H_mm,
        "er": er,
        "T_mm": T_mm,
        "formula": "Wadell §3.7: Zdiff = 2*Z0*(1 - 0.347*exp(-2.9*S/H))",
    }


def differential_stripline_z0(
    W_mm: float,
    S_mm: float,
    B_mm: float,
    er: float,
    T_mm: float = 0.035,
) -> dict:
    """
    Differential symmetric stripline impedance (Wadell §4.3).

    Uses symmetric stripline Z0 with the coupling correction:
        Zdiff = 2 * Z0 * (1 - 0.347 * exp(-2.9 * S / B))

    Parameters
    ----------
    W_mm : float — trace width [mm]
    S_mm : float — edge-to-edge spacing [mm]
    B_mm : float — total dielectric thickness between reference planes [mm]
    er   : float — relative permittivity
    T_mm : float — trace thickness [mm] (default 35 µm)

    Returns
    -------
    dict with keys: ok, Z0_single, Zdiff, er_eff, W_mm, S_mm, B_mm, er, T_mm
    """
    for val, name in [(W_mm, "W_mm"), (S_mm, "S_mm"), (B_mm, "B_mm"), (er, "er")]:
        err = _validate_positive(val, name)
        if err:
            return {"ok": False, "reason": err}
    err = _validate_nonneg(T_mm, "T_mm")
    if err:
        return {"ok": False, "reason": err}

    if S_mm < _FAB_S_MIN_MM:
        warnings.warn(
            f"differential_stripline_z0: spacing S={S_mm:.4f} mm is below typical "
            f"fab minimum ({_FAB_S_MIN_MM} mm).",
            stacklevel=2,
        )

    se = stripline_z0_symmetric(W_mm=W_mm, B_mm=B_mm, er=er, T_mm=T_mm)
    if not se["ok"]:
        return se

    z0 = se["Z0"]
    er_eff = se["er_eff"]
    zdiff = 2.0 * z0 * (1.0 - 0.347 * math.exp(-2.9 * S_mm / B_mm))

    return {
        "ok": True,
        "Z0_single": round(z0, 4),
        "Zdiff": round(zdiff, 4),
        "er_eff": round(er_eff, 6),
        "W_mm": W_mm,
        "S_mm": S_mm,
        "B_mm": B_mm,
        "er": er,
        "T_mm": T_mm,
        "formula": "Wadell §4.3: Zdiff = 2*Z0*(1 - 0.347*exp(-2.9*S/B))",
    }


# ── Effective dielectric constant (standalone) ────────────────────────────────


def effective_er(
    structure: str,
    W_mm: float,
    H_mm: float,
    er: float,
    T_mm: float = 0.035,
    d_mm: float = 0.0,
    G_mm: float = 0.1,
) -> dict:
    """
    Effective dielectric constant for a PCB transmission-line structure.

    Parameters
    ----------
    structure : str — one of 'microstrip', 'embedded_microstrip', 'stripline', 'cpwg'
    W_mm      : float — trace width [mm]
    H_mm      : float — dielectric height (or total B for stripline) [mm]
    er        : float — relative permittivity
    T_mm      : float — trace thickness [mm] (default 35 µm)
    d_mm      : float — cover layer thickness [mm] (embedded microstrip only)
    G_mm      : float — gap to coplanar ground [mm] (CPWG only)

    Returns
    -------
    dict with keys: ok, er_eff, structure, W_mm, H_mm, er
    """
    structure = structure.lower().strip()
    if structure == "microstrip":
        res = microstrip_z0(W_mm=W_mm, H_mm=H_mm, er=er, T_mm=T_mm)
    elif structure == "embedded_microstrip":
        res = embedded_microstrip_z0(W_mm=W_mm, H_mm=H_mm, er=er, d_mm=d_mm, T_mm=T_mm)
    elif structure in ("stripline", "symmetric_stripline"):
        res = stripline_z0_symmetric(W_mm=W_mm, B_mm=H_mm, er=er, T_mm=T_mm)
    elif structure == "cpwg":
        res = cpwg_z0(W_mm=W_mm, G_mm=G_mm, H_mm=H_mm, er=er, T_mm=T_mm)
    else:
        return {
            "ok": False,
            "reason": (
                f"Unknown structure {structure!r}. "
                "Choose from: microstrip, embedded_microstrip, stripline, cpwg."
            ),
        }
    if not res["ok"]:
        return res
    return {
        "ok": True,
        "er_eff": res["er_eff"],
        "structure": structure,
        "W_mm": W_mm,
        "H_mm": H_mm,
        "er": er,
    }


# ── Propagation delay ─────────────────────────────────────────────────────────


def propagation_delay_ps_per_mm(
    er_eff: float,
) -> dict:
    """
    Propagation delay from effective dielectric constant.

    Td [ps/mm] = sqrt(er_eff) / c
    where c = 0.299792458 mm/ps.

    Parameters
    ----------
    er_eff : float — effective relative permittivity (from any Z0 function)

    Returns
    -------
    dict with keys: ok, er_eff, Td_ps_per_mm, Td_ns_per_m
    """
    err = _validate_positive(er_eff, "er_eff")
    if err:
        return {"ok": False, "reason": err}

    td = math.sqrt(er_eff) / _C_MM_PS  # ps/mm
    return {
        "ok": True,
        "er_eff": er_eff,
        "Td_ps_per_mm": round(td, 6),
        "Td_ns_per_m": round(td * 1e-3 * 1e3, 4),  # ps/mm * 1000mm/m * 1ns/1000ps
        "formula": "Td = sqrt(er_eff) / c  [c = 0.2998 mm/ps]",
    }


# ── Wavelength ────────────────────────────────────────────────────────────────


def wavelength_mm(
    freq_hz: float,
    er_eff: float,
) -> dict:
    """
    Guided wavelength on a transmission line at frequency freq_hz.

    λ [mm] = c / (f × sqrt(er_eff))
    where c = 299792.458 mm/µs (= 0.299792458 mm/ps).

    Parameters
    ----------
    freq_hz : float — frequency [Hz]
    er_eff  : float — effective relative permittivity

    Returns
    -------
    dict with keys: ok, freq_hz, er_eff, wavelength_mm, quarter_wave_mm, tenth_wave_mm
    """
    err = _validate_positive(freq_hz, "freq_hz")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(er_eff, "er_eff")
    if err:
        return {"ok": False, "reason": err}

    # c [mm/ps], f [Hz] = f * 1e-12 [THz * ps], lambda = c/f (in mm when f in (mm/ps)^-1)
    # freq_hz [Hz] = freq_hz * 1e-12 [ps^-1 * 1e-12 * 1e12] — careful:
    # lambda [mm] = c_mm_ps [mm/ps] / (freq_hz [1/s] * 1e-12 [s/ps]) / sqrt(er_eff)
    lam = _C_MM_PS / (freq_hz * 1e-12 * math.sqrt(er_eff))

    return {
        "ok": True,
        "freq_hz": freq_hz,
        "er_eff": er_eff,
        "wavelength_mm": round(lam, 4),
        "quarter_wave_mm": round(lam / 4.0, 4),
        "tenth_wave_mm": round(lam / 10.0, 4),
    }


# ── Trace-width solver for target Z0 ─────────────────────────────────────────


def trace_width_for_z0(
    Z0_target: float,
    H_mm: float,
    er: float,
    structure: str = "microstrip",
    T_mm: float = 0.035,
    B_mm: Optional[float] = None,
    tol_rel: float = 1e-4,
    max_iter: int = 60,
) -> dict:
    """
    Solve for the trace width [mm] that achieves a target Z0 using bisection.

    Parameters
    ----------
    Z0_target : float — target characteristic impedance [Ohm]
    H_mm      : float — dielectric height (microstrip) or B (stripline) [mm]
    er        : float — relative permittivity
    structure : str   — 'microstrip' or 'stripline' (default 'microstrip')
    T_mm      : float — trace thickness [mm] (default 35 µm)
    B_mm      : float — total dielectric thickness for stripline [mm] (overrides H_mm)
    tol_rel   : float — relative Z0 tolerance (default 0.01%)
    max_iter  : int   — maximum bisection iterations (default 60)

    Returns
    -------
    dict with keys: ok, W_mm, Z0_achieved, Z0_target, er_eff, iterations,
                    unrealizable (bool), warnings
    """
    err = _validate_positive(Z0_target, "Z0_target")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(H_mm, "H_mm")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(er, "er")
    if err:
        return {"ok": False, "reason": err}

    structure = structure.lower().strip()
    if structure not in ("microstrip", "stripline"):
        return {
            "ok": False,
            "reason": "structure must be 'microstrip' or 'stripline' for the width solver",
        }

    # Effective B for stripline
    B = B_mm if B_mm is not None else H_mm

    def _z0(w: float) -> float:
        if structure == "microstrip":
            r = microstrip_z0(W_mm=w, H_mm=H_mm, er=er, T_mm=T_mm)
        else:
            r = stripline_z0_symmetric(W_mm=w, B_mm=B, er=er, T_mm=T_mm)
        return r["Z0"] if r["ok"] else None

    # Z0 decreases as W increases; search range
    W_lo = 0.01   # mm — very narrow trace (high Z0)
    W_hi = 20.0   # mm — very wide trace (low Z0)

    z0_lo = _z0(W_lo)
    z0_hi = _z0(W_hi)

    if z0_lo is None or z0_hi is None:
        return {"ok": False, "reason": "could not evaluate Z0 at search boundary"}

    result_warnings = []
    unrealizable = False

    if Z0_target > z0_lo:
        warnings.warn(
            f"trace_width_for_z0: target Z0={Z0_target} Ω exceeds Z0 at W=0.01 mm "
            f"({z0_lo:.1f} Ω); geometry unrealizable — returning narrowest width.",
            stacklevel=2,
        )
        result_warnings.append(f"Z0 target {Z0_target} Ω is unrealizable (too high); returned narrowest width")
        unrealizable = True
        er_eff_val = microstrip_z0(W_mm=W_lo, H_mm=H_mm, er=er, T_mm=T_mm)["er_eff"] if structure == "microstrip" else er
        _fab_warn_width(W_lo, ".trace_width_for_z0")
        return {
            "ok": True,
            "W_mm": round(W_lo, 5),
            "Z0_achieved": round(z0_lo, 4),
            "Z0_target": Z0_target,
            "er_eff": round(er_eff_val, 6),
            "iterations": 0,
            "unrealizable": True,
            "warnings": result_warnings,
        }

    if Z0_target < z0_hi:
        warnings.warn(
            f"trace_width_for_z0: target Z0={Z0_target} Ω is below Z0 at W=20 mm "
            f"({z0_hi:.1f} Ω); geometry unrealizable — returning widest width.",
            stacklevel=2,
        )
        result_warnings.append(f"Z0 target {Z0_target} Ω is unrealizable (too low); returned widest width")
        unrealizable = True
        er_eff_val = microstrip_z0(W_mm=W_hi, H_mm=H_mm, er=er, T_mm=T_mm)["er_eff"] if structure == "microstrip" else er
        _fab_warn_width(W_hi, ".trace_width_for_z0")
        return {
            "ok": True,
            "W_mm": round(W_hi, 5),
            "Z0_achieved": round(z0_hi, 4),
            "Z0_target": Z0_target,
            "er_eff": round(er_eff_val, 6),
            "iterations": 0,
            "unrealizable": True,
            "warnings": result_warnings,
        }

    # Bisection (Z0 is monotonically decreasing in W)
    for i in range(max_iter):
        W_mid = (W_lo + W_hi) / 2.0
        z0_mid = _z0(W_mid)
        if z0_mid is None:
            return {"ok": False, "reason": "evaluation error during bisection"}
        if abs(z0_mid - Z0_target) / Z0_target < tol_rel:
            break
        if z0_mid > Z0_target:
            W_lo = W_mid  # need wider trace to reduce Z0
        else:
            W_hi = W_mid
        i_done = i

    W_result = (W_lo + W_hi) / 2.0
    z0_result = _z0(W_result)
    _fab_warn_width(W_result, ".trace_width_for_z0")

    if structure == "microstrip":
        er_eff_val = microstrip_z0(W_mm=W_result, H_mm=H_mm, er=er, T_mm=T_mm)["er_eff"]
    else:
        er_eff_val = er

    return {
        "ok": True,
        "W_mm": round(W_result, 5),
        "Z0_achieved": round(z0_result, 4),
        "Z0_target": Z0_target,
        "er_eff": round(er_eff_val, 6),
        "iterations": max_iter if i_done == max_iter - 1 else i + 1,
        "unrealizable": unrealizable,
        "warnings": result_warnings,
    }


# ── Differential pair spacing for target Zdiff ───────────────────────────────


def diff_pair_spacing_for_zdiff(
    Zdiff_target: float,
    W_mm: float,
    H_mm: float,
    er: float,
    structure: str = "microstrip",
    T_mm: float = 0.035,
    B_mm: Optional[float] = None,
    tol_rel: float = 1e-4,
    max_iter: int = 60,
) -> dict:
    """
    Solve for the trace spacing [mm] that achieves a target differential impedance.

    Uses bisection over S (edge-to-edge spacing) for the Wadell differential
    impedance formula.

    Parameters
    ----------
    Zdiff_target : float — target differential impedance [Ohm]
    W_mm         : float — trace width [mm]
    H_mm         : float — dielectric height [mm]
    er           : float — relative permittivity
    structure    : str   — 'microstrip' or 'stripline' (default 'microstrip')
    T_mm         : float — trace thickness [mm] (default 35 µm)
    B_mm         : float — total dielectric thickness for stripline [mm]
    tol_rel      : float — relative Zdiff tolerance (default 0.01%)
    max_iter     : int   — maximum bisection iterations

    Returns
    -------
    dict with keys: ok, S_mm, Zdiff_achieved, Zdiff_target, Z0_single,
                    iterations, unrealizable, warnings
    """
    err = _validate_positive(Zdiff_target, "Zdiff_target")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(W_mm, "W_mm")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(H_mm, "H_mm")
    if err:
        return {"ok": False, "reason": err}
    err = _validate_positive(er, "er")
    if err:
        return {"ok": False, "reason": err}

    structure = structure.lower().strip()
    if structure not in ("microstrip", "stripline"):
        return {
            "ok": False,
            "reason": "structure must be 'microstrip' or 'stripline'",
        }

    B = B_mm if B_mm is not None else H_mm

    def _zdiff(s: float) -> Optional[float]:
        if structure == "microstrip":
            r = differential_microstrip_z0(W_mm=W_mm, S_mm=s, H_mm=H_mm, er=er, T_mm=T_mm)
        else:
            r = differential_stripline_z0(W_mm=W_mm, S_mm=s, B_mm=B, er=er, T_mm=T_mm)
        return r["Zdiff"] if r["ok"] else None

    # Zdiff increases with S; search range
    S_lo = 0.05   # mm — very tight spacing (low Zdiff)
    S_hi = 10.0   # mm — wide spacing (Zdiff ≈ 2*Z0)

    zdiff_lo = _zdiff(S_lo)
    zdiff_hi = _zdiff(S_hi)

    if zdiff_lo is None or zdiff_hi is None:
        return {"ok": False, "reason": "could not evaluate Zdiff at search boundary"}

    result_warnings = []
    unrealizable = False

    # Get single-ended Z0 for reference
    if structure == "microstrip":
        se_res = microstrip_z0(W_mm=W_mm, H_mm=H_mm, er=er, T_mm=T_mm)
    else:
        se_res = stripline_z0_symmetric(W_mm=W_mm, B_mm=B, er=er, T_mm=T_mm)
    z0_single = se_res["Z0"] if se_res["ok"] else 0.0

    if Zdiff_target < zdiff_lo:
        warnings.warn(
            f"diff_pair_spacing_for_zdiff: target Zdiff={Zdiff_target} Ω is below "
            f"Zdiff at S=0.05 mm ({zdiff_lo:.1f} Ω); returning tightest spacing.",
            stacklevel=2,
        )
        result_warnings.append("Zdiff target is too low; returned minimum spacing")
        unrealizable = True
        return {
            "ok": True,
            "S_mm": round(S_lo, 5),
            "Zdiff_achieved": round(zdiff_lo, 4),
            "Zdiff_target": Zdiff_target,
            "Z0_single": round(z0_single, 4),
            "iterations": 0,
            "unrealizable": True,
            "warnings": result_warnings,
        }

    if Zdiff_target > zdiff_hi:
        warnings.warn(
            f"diff_pair_spacing_for_zdiff: target Zdiff={Zdiff_target} Ω exceeds "
            f"Zdiff at S=10 mm ({zdiff_hi:.1f} Ω); returning widest spacing.",
            stacklevel=2,
        )
        result_warnings.append("Zdiff target is too high; returned maximum spacing")
        unrealizable = True
        return {
            "ok": True,
            "S_mm": round(S_hi, 5),
            "Zdiff_achieved": round(zdiff_hi, 4),
            "Zdiff_target": Zdiff_target,
            "Z0_single": round(z0_single, 4),
            "iterations": 0,
            "unrealizable": True,
            "warnings": result_warnings,
        }

    for i in range(max_iter):
        S_mid = (S_lo + S_hi) / 2.0
        zdiff_mid = _zdiff(S_mid)
        if zdiff_mid is None:
            return {"ok": False, "reason": "evaluation error during bisection"}
        if abs(zdiff_mid - Zdiff_target) / Zdiff_target < tol_rel:
            break
        if zdiff_mid < Zdiff_target:
            S_lo = S_mid  # need wider spacing to increase Zdiff
        else:
            S_hi = S_mid

    S_result = (S_lo + S_hi) / 2.0
    zdiff_result = _zdiff(S_result)

    return {
        "ok": True,
        "S_mm": round(S_result, 5),
        "Zdiff_achieved": round(zdiff_result, 4),
        "Zdiff_target": Zdiff_target,
        "Z0_single": round(z0_single, 4),
        "iterations": i + 1,
        "unrealizable": unrealizable,
        "warnings": result_warnings,
    }


# ── Conductor (skin-effect) attenuation ──────────────────────────────────────


def conductor_loss_db_per_mm(
    freq_hz: float,
    W_mm: float,
    Z0: float,
    roughness_um: float = 0.0,
    rho_relative: float = 1.0,
) -> dict:
    """
    Conductor (skin-effect) attenuation of a microstrip trace [dB/mm].

    Formula (Hammerstad-Jensen / Wadell §3.5):
        Rs = sqrt(pi * f * mu0 * rho)          [Ohm/sq, surface resistance]
        alpha_c = Rs / (pi * W * Z0)           [Np/m, then converted to dB/mm]

    Surface roughness correction (Huray sphere model / IPC-2141A §3):
        delta_s = sqrt(rho / (pi * f * mu0))   [skin depth, m]
        rough_factor = 1 + (2/pi) * arctan(1.4 * (roughness_um * 1e-6 / delta_s)^2)
        alpha_c_rough = alpha_c * rough_factor

    Parameters
    ----------
    freq_hz      : float — frequency [Hz]
    W_mm         : float — trace width [mm]
    Z0           : float — characteristic impedance [Ohm]
    roughness_um : float — RMS surface roughness [µm] (0 = ideal smooth; default 0)
    rho_relative : float — conductor resistivity relative to copper (default 1.0)

    Returns
    -------
    dict with keys: ok, freq_hz, W_mm, Z0, alpha_c_db_per_mm, alpha_c_rough_db_per_mm,
                    skin_depth_um, roughness_factor, Rs_ohm_sq
    """
    for val, name in [(freq_hz, "freq_hz"), (W_mm, "W_mm"), (Z0, "Z0")]:
        err = _validate_positive(val, name)
        if err:
            return {"ok": False, "reason": err}
    for val, name in [(roughness_um, "roughness_um"), (rho_relative, "rho_relative")]:
        err = _validate_nonneg(val, name) if name == "roughness_um" else _validate_positive(val, name)
        if err:
            return {"ok": False, "reason": err}

    rho = _RHO_CU * rho_relative  # Ohm·m

    # Surface resistance [Ohm/sq]
    Rs = math.sqrt(math.pi * freq_hz * _MU0 * rho)

    # Skin depth [m]
    delta_s = math.sqrt(rho / (math.pi * freq_hz * _MU0))
    delta_s_um = delta_s * 1e6  # µm

    W_m = W_mm * 1e-3  # m

    # alpha_c in Np/m
    alpha_c_npm = Rs / (math.pi * W_m * Z0)

    # Convert to dB/mm: 1 Np/m = 8.6859 dB/m = 8.6859e-3 dB/mm
    np_to_db_per_mm = 8.6859e-3
    alpha_c_db_per_mm = alpha_c_npm * np_to_db_per_mm

    # Roughness correction
    if roughness_um > 0 and delta_s_um > 0:
        rough_norm = roughness_um * 1e-6 / delta_s
        rough_factor = 1.0 + (2.0 / math.pi) * math.atan(1.4 * rough_norm ** 2)
    else:
        rough_factor = 1.0

    alpha_c_rough = alpha_c_db_per_mm * rough_factor

    return {
        "ok": True,
        "freq_hz": freq_hz,
        "W_mm": W_mm,
        "Z0": Z0,
        "roughness_um": roughness_um,
        "rho_relative": rho_relative,
        "Rs_ohm_sq": round(Rs, 6),
        "skin_depth_um": round(delta_s_um, 4),
        "alpha_c_db_per_mm": round(alpha_c_db_per_mm, 8),
        "roughness_factor": round(rough_factor, 6),
        "alpha_c_rough_db_per_mm": round(alpha_c_rough, 8),
        "formula": "Wadell §3.5 / IPC-2141A §3",
    }


# ── Dielectric (loss-tangent) attenuation ────────────────────────────────────


def dielectric_loss_db_per_mm(
    freq_hz: float,
    er: float,
    er_eff: float,
    tan_d: float,
) -> dict:
    """
    Dielectric (loss-tangent) attenuation [dB/mm].

    Formula (Wadell §3.5 / Pozar "Microwave Engineering" §3.1):
        alpha_d [Np/m] = (pi * f * sqrt(er_eff) * tan_d) / c
                       * er / er_eff * (er_eff - 1) / (er - 1)

    Simplified for microstrip (Wadell §3.5):
        alpha_d [dB/mm] = 27.3 * er * (er_eff - 1) / (er_eff * (er - 1)) * tan_d
                          * f_GHz / c_GHz
    where c_GHz = 299.792 mm/ns = speed of light in GHz-mm units.

    For stripline (er_eff = er):
        alpha_d [dB/mm] = 27.3 * tan_d * f_GHz / c_mm_ns

    Parameters
    ----------
    freq_hz : float — frequency [Hz]
    er      : float — substrate relative permittivity
    er_eff  : float — effective relative permittivity
    tan_d   : float — loss tangent of the substrate

    Returns
    -------
    dict with keys: ok, freq_hz, er, er_eff, tan_d, alpha_d_db_per_mm
    """
    for val, name in [(freq_hz, "freq_hz"), (er, "er"), (er_eff, "er_eff")]:
        err = _validate_positive(val, name)
        if err:
            return {"ok": False, "reason": err}
    err = _validate_nonneg(tan_d, "tan_d")
    if err:
        return {"ok": False, "reason": err}
    if er_eff > er + 0.01:
        return {
            "ok": False,
            "reason": f"er_eff ({er_eff}) cannot exceed er ({er}) for a standard PCB dielectric",
        }

    f_ghz = freq_hz * 1e-9  # GHz
    c_ghz_mm = 299.792458   # speed of light in mm/ns  (= mm*GHz)

    if abs(er - 1.0) < 1e-9:
        # Free space (degenerate): alpha_d = 0
        alpha_d = 0.0
    else:
        # Wadell §3.5 filling factor
        filling = er * (er_eff - 1.0) / (er_eff * (er - 1.0))
        alpha_d = 27.3 * filling * tan_d * f_ghz / c_ghz_mm

    return {
        "ok": True,
        "freq_hz": freq_hz,
        "er": er,
        "er_eff": er_eff,
        "tan_d": tan_d,
        "alpha_d_db_per_mm": round(alpha_d, 10),
        "formula": "Wadell §3.5: alpha_d = 27.3 * (er*(er_eff-1)/(er_eff*(er-1))) * tan_d * f/c",
    }


# ── Stackup total thickness ───────────────────────────────────────────────────


def stackup_thickness_mm(layers: List[dict]) -> dict:
    """
    Compute total PCB stackup thickness from a list of layer descriptions.

    Each layer dict must have:
        type        : str — 'dielectric' | 'copper'
        thickness_mm: float — layer thickness [mm]
        name        : str (optional) — layer name

    Parameters
    ----------
    layers : list of dicts — ordered stackup layer definitions (top to bottom)

    Returns
    -------
    dict with keys: ok, total_thickness_mm, copper_thickness_mm,
                    dielectric_thickness_mm, layer_count, layers_summary
    """
    if not isinstance(layers, list) or len(layers) == 0:
        return {"ok": False, "reason": "layers must be a non-empty list of dicts"}

    total = 0.0
    copper_total = 0.0
    dielectric_total = 0.0
    summary = []

    for i, layer in enumerate(layers):
        if not isinstance(layer, dict):
            return {"ok": False, "reason": f"layer[{i}] must be a dict"}
        ltype = str(layer.get("type", "")).lower().strip()
        t = layer.get("thickness_mm")
        err = _validate_positive(t, f"layer[{i}].thickness_mm")
        if err:
            return {"ok": False, "reason": err}
        if ltype not in ("dielectric", "copper"):
            return {
                "ok": False,
                "reason": f"layer[{i}].type must be 'dielectric' or 'copper', got {ltype!r}",
            }
        total += t
        if ltype == "copper":
            copper_total += t
        else:
            dielectric_total += t
        summary.append({
            "index": i,
            "name": layer.get("name", f"layer_{i}"),
            "type": ltype,
            "thickness_mm": t,
        })

    return {
        "ok": True,
        "total_thickness_mm": round(total, 6),
        "copper_thickness_mm": round(copper_total, 6),
        "dielectric_thickness_mm": round(dielectric_total, 6),
        "layer_count": len(layers),
        "layers_summary": summary,
    }


# ── Stackup impedance budget ──────────────────────────────────────────────────


def stackup_impedance_budget(
    nets: List[dict],
    tolerance_pct: float = 10.0,
) -> dict:
    """
    Compute Z0 for each controlled-impedance net in a multilayer stackup
    and flag any that fall outside the impedance tolerance window.

    Each net dict must have:
        name      : str
        structure : str — 'microstrip' | 'stripline' | 'differential_microstrip' |
                          'differential_stripline'
        W_mm      : float — trace width [mm]
        H_mm      : float — dielectric height (or B for stripline) [mm]
        er        : float — substrate relative permittivity
        T_mm      : float (optional, default 0.035) — trace thickness [mm]
        S_mm      : float (optional) — spacing for differential pairs
        target_z0 : float (optional) — target impedance for budget check [Ohm]

    Parameters
    ----------
    nets          : list of net dicts
    tolerance_pct : float — allowed deviation from target_z0 [%] (default 10%)

    Returns
    -------
    dict with keys: ok, nets_results, all_in_budget, out_of_budget_names, tolerance_pct
    """
    if not isinstance(nets, list) or len(nets) == 0:
        return {"ok": False, "reason": "nets must be a non-empty list of dicts"}

    err = _validate_positive(tolerance_pct, "tolerance_pct")
    if err:
        return {"ok": False, "reason": err}

    results = []
    out_of_budget = []

    for i, net in enumerate(nets):
        if not isinstance(net, dict):
            results.append({"index": i, "ok": False, "reason": "not a dict"})
            continue

        name = net.get("name", f"net_{i}")
        structure = str(net.get("structure", "microstrip")).lower().strip()
        W_mm = net.get("W_mm")
        H_mm = net.get("H_mm")
        er = net.get("er")
        T_mm = net.get("T_mm", 0.035)
        S_mm = net.get("S_mm")
        target_z0 = net.get("target_z0")

        # Dispatch to the right function
        if structure == "microstrip":
            res = microstrip_z0(W_mm=W_mm, H_mm=H_mm, er=er, T_mm=T_mm)
            z_key = "Z0"
        elif structure == "stripline":
            res = stripline_z0_symmetric(W_mm=W_mm, B_mm=H_mm, er=er, T_mm=T_mm)
            z_key = "Z0"
        elif structure == "differential_microstrip":
            if S_mm is None:
                res = {"ok": False, "reason": "S_mm required for differential_microstrip"}
            else:
                res = differential_microstrip_z0(W_mm=W_mm, S_mm=S_mm, H_mm=H_mm, er=er, T_mm=T_mm)
            z_key = "Zdiff"
        elif structure == "differential_stripline":
            if S_mm is None:
                res = {"ok": False, "reason": "S_mm required for differential_stripline"}
            else:
                res = differential_stripline_z0(W_mm=W_mm, S_mm=S_mm, B_mm=H_mm, er=er, T_mm=T_mm)
            z_key = "Zdiff"
        else:
            res = {"ok": False, "reason": f"unknown structure {structure!r}"}
            z_key = "Z0"

        if not res.get("ok"):
            entry = {
                "index": i,
                "name": name,
                "ok": False,
                "reason": res.get("reason", "unknown"),
            }
            results.append(entry)
            continue

        z_achieved = res.get(z_key)
        in_budget = True
        budget_margin_pct = None

        if target_z0 is not None:
            deviation_pct = abs(z_achieved - target_z0) / target_z0 * 100.0
            budget_margin_pct = round(tolerance_pct - deviation_pct, 3)
            in_budget = deviation_pct <= tolerance_pct
            if not in_budget:
                out_of_budget.append(name)
                warnings.warn(
                    f"stackup_impedance_budget: net '{name}' achieved Z={z_achieved:.2f} Ω "
                    f"vs target {target_z0:.2f} Ω (deviation {deviation_pct:.1f}% > "
                    f"tolerance {tolerance_pct:.1f}%).",
                    stacklevel=2,
                )

        entry = {
            "index": i,
            "name": name,
            "ok": True,
            "structure": structure,
            "W_mm": W_mm,
            "H_mm": H_mm,
            "er": er,
            "T_mm": T_mm,
            z_key: z_achieved,
            "er_eff": res.get("er_eff"),
            "target_z0": target_z0,
            "in_budget": in_budget,
            "budget_margin_pct": budget_margin_pct,
        }
        results.append(entry)

    all_in_budget = len(out_of_budget) == 0

    return {
        "ok": True,
        "nets_results": results,
        "all_in_budget": all_in_budget,
        "out_of_budget_names": out_of_budget,
        "tolerance_pct": tolerance_pct,
    }
