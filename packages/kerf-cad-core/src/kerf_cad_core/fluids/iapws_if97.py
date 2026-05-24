"""
kerf_cad_core.fluids.iapws_if97 — IAPWS-IF97 industrial steam properties
==========================================================================

Implements the International Association for the Properties of Water and
Steam Industrial Formulation 1997 (IAPWS-IF97), covering:

  Region 1  — compressed liquid  (T ≤ 623.15 K, p ≥ psat(T))
  Region 2  — superheated vapour (T ≤ 1073.15 K, p ≤ psat(T))
  Region 4  — saturation curve   (273.15 K ≤ T ≤ 647.096 K)

Reference
---------
W. Wagner et al., "The IAPWS Industrial Formulation 1997 for the
Thermodynamic Properties of Water and Steam," J. Eng. Gas Turbines
Power 122(1): 150-184 (2000).

Validation table (from Table 5, 15, and 26 of the standard)
------------------------------------------------------------
Region 1 at T=300 K, p=3 MPa:
  v = 0.00100215  m³/kg
  h = 115.331     kJ/kg
  s = 0.392294    kJ/kg·K
  cp= 4.17301     kJ/kg·K

Region 2 at T=300 K, p=0.0035 MPa:
  v = 39.4913     m³/kg
  h = 2549.91     kJ/kg
  s = 8.52238     kJ/kg·K
  cp= 1.91300     kJ/kg·K

Region 4 saturation:
  Tsat(101.325 kPa) ≈ 373.124 K  (99.974 °C)
  psat(370 K)       ≈ 90.535 kPa

Pure Python — no numpy required.

Author: imranparuk
"""
from __future__ import annotations

import math
from typing import TypedDict


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_R = 461.526          # J/(kg·K) — specific gas constant for water
_T_CRIT = 647.096     # K        — critical temperature
_P_CRIT = 22.064e6    # Pa       — critical pressure
_T_MIN = 273.15       # K        — lower validity limit
_T_R1_MAX = 623.15    # K        — upper limit of Region 1
_T_R2_MAX = 1073.15   # K        — upper limit of Region 2


# ---------------------------------------------------------------------------
# Region 4 — Saturation curve (IAPWS-IF97 Section 8.1)
# ---------------------------------------------------------------------------
# Coefficients n1…n10 from Table 34 of Wagner 2000 / IAPWS-IF97 2007 release
_N4 = (
    0.11670521452767e4,    # n1
    -0.72421316703206e6,   # n2
    -0.17073846940092e2,   # n3
    0.12020824702470e5,    # n4
    -0.32325550322333e7,   # n5
    0.14915108613530e2,    # n6
    -0.48232657361591e4,   # n7
    0.40511340542057e6,    # n8
    -0.23855557567849e0,   # n9
    0.65017534844798e3,    # n10
)


def psat_T(T_K: float) -> float:
    """
    Saturation pressure at temperature T_K (K).

    Implements IAPWS-IF97 Equation (30).

    Valid range: 273.15 K ≤ T ≤ 647.096 K.

    Returns
    -------
    p_sat : float
        Saturation pressure in Pa.
    """
    if not (_T_MIN <= T_K <= _T_CRIT):
        raise ValueError(
            f"T_K={T_K} out of saturation range [{_T_MIN}, {_T_CRIT}] K"
        )
    n = _N4
    theta = T_K + n[8] / (T_K - n[9])
    A = theta ** 2 + n[0] * theta + n[1]
    B = n[2] * theta ** 2 + n[3] * theta + n[4]
    C = n[5] * theta ** 2 + n[6] * theta + n[7]
    # Eq. (30): (2C / (-B + sqrt(B²-4AC)))^4 * 1 MPa
    discriminant = B * B - 4.0 * A * C
    if discriminant < 0.0:
        raise ArithmeticError(f"Negative discriminant at T={T_K} K")
    p_star = 1.0e6  # 1 MPa in Pa
    p_sat = (2.0 * C / (-B + math.sqrt(discriminant))) ** 4 * p_star
    return p_sat


def Tsat_p(p_Pa: float) -> float:
    """
    Saturation temperature at pressure p_Pa (Pa).

    Implements IAPWS-IF97 Equation (31) — the backward equation.

    Valid range: 611.657 Pa ≤ p ≤ 22.064 MPa.

    Returns
    -------
    T_sat : float
        Saturation temperature in K.
    """
    _p_min = 611.657   # Pa — triple point pressure
    if not (_p_min <= p_Pa <= _P_CRIT):
        raise ValueError(
            f"p_Pa={p_Pa} out of saturation range [{_p_min}, {_P_CRIT}] Pa"
        )
    n = _N4
    beta = (p_Pa / 1.0e6) ** 0.25   # reduced pressure (MPa base)
    E = beta ** 2 + n[2] * beta + n[5]
    F = n[0] * beta ** 2 + n[3] * beta + n[6]
    G = n[1] * beta ** 2 + n[4] * beta + n[7]
    D = 2.0 * G / (-F - math.sqrt(F * F - 4.0 * E * G))
    T_sat = (n[9] + D - math.sqrt((n[9] + D) ** 2 - 4.0 * (n[8] + n[9] * D))) / 2.0
    return T_sat


# ---------------------------------------------------------------------------
# Region 1 — Compressed liquid (T ≤ 623.15 K, p ≥ psat)
# ---------------------------------------------------------------------------
# Table 2 of IAPWS-IF97 — 34 coefficients (I_i, J_i, n_i)
_R1_IJN = (
    # ( I,   J,      n                 )
    (  0,  -2,  0.14632971213167e0  ),
    (  0,  -1,  -0.84548187169114e0 ),
    (  0,   0,  -0.37563603672040e1 ),
    (  0,   1,  0.33855169168385e1  ),
    (  0,   2,  -0.95791963387872e0 ),
    (  0,   3,  0.15772038513228e0  ),
    (  0,   4,  -0.16616417199501e-1),
    (  0,   5,  0.81214629983568e-3 ),
    (  1,  -9,  0.28319080123804e-3 ),
    (  1,  -7,  -0.60706301565874e-3),
    (  1,  -1,  -0.18990068218419e-1),
    (  1,   0,  -0.32529748770505e-1),
    (  1,   1,  -0.21841717175414e-1),
    (  1,   3,  -0.52838357969930e-4),
    (  2,  -3,  -0.47184321073267e-3),
    (  2,   0,  -0.30001780793026e-3),
    (  2,   1,  0.47661393906987e-4 ),
    (  2,   3,  -0.44141845330846e-5),
    (  2,  17,  -0.72694996297594e-15),
    (  3,  -4,  -0.31679644845054e-4),
    (  3,   0,  -0.28270797985312e-5),
    (  3,   6,  -0.85205128120103e-9),
    (  4,  -5,  -0.22425281908000e-5),
    (  4,  -2,  -0.65171222895601e-6),
    (  4,  10,  -0.14341729937924e-12),
    (  5,  -8,  -0.40516996860117e-6),
    (  8, -11,  -0.12734301741641e-8),
    (  8,  -6,  -0.17424871230634e-9),
    ( 21, -29,  -0.68762131295531e-18),
    ( 23, -31,  0.14478307828521e-19),
    ( 29, -38,  0.26335781662795e-22),
    ( 30, -39,  -0.11947622640071e-22),
    ( 31, -40,  0.18228094581404e-23),
    ( 32, -41,  -0.93537087292458e-25),
)

# Reducing quantities for Region 1
_R1_T_STAR = 1386.0   # K
_R1_P_STAR = 16.53e6  # Pa


def _gamma1(pi: float, tau: float) -> tuple[float, float, float, float, float]:
    """
    Dimensionless Gibbs free energy γ and its partial derivatives for Region 1.

    Returns (γ, γ_π, γ_ππ, γ_τ, γ_ττ) where subscripts denote partial
    differentiation with respect to π and τ.
    """
    g = g_pi = g_pipi = g_tau = g_tautau = 0.0
    for I, J, n in _R1_IJN:
        # γ = Σ n_i (7.1 - π)^I (τ - 1.222)^J
        pi_term = (7.1 - pi) ** I
        tau_term = (tau - 1.222) ** J
        g += n * pi_term * tau_term
        # ∂γ/∂π = Σ n_i (-I)(7.1 - π)^(I-1)(τ - 1.222)^J
        if I != 0:
            g_pi += n * (-I) * (7.1 - pi) ** (I - 1) * tau_term
        # ∂²γ/∂π² = Σ n_i I(I-1)(7.1 - π)^(I-2)(τ - 1.222)^J
        if I >= 2:
            g_pipi += n * I * (I - 1) * (7.1 - pi) ** (I - 2) * tau_term
        # ∂γ/∂τ = Σ n_i (7.1 - π)^I J(τ - 1.222)^(J-1)
        if J != 0:
            g_tau += n * pi_term * J * (tau - 1.222) ** (J - 1)
        # ∂²γ/∂τ² = Σ n_i (7.1 - π)^I J(J-1)(τ - 1.222)^(J-2)
        # Note: J*(J-1)=0 only for J=0 or J=1; J=-1 gives (-1)(-2)=2 and must be included
        if J != 0 and J != 1:
            g_tautau += n * pi_term * J * (J - 1) * (tau - 1.222) ** (J - 2)
    return g, g_pi, g_pipi, g_tau, g_tautau


def region1_props(T_K: float, p_Pa: float) -> dict:
    """
    Thermodynamic properties via Region 1 (compressed liquid) formulation.

    Parameters
    ----------
    T_K : float  — temperature in K (273.15 ≤ T ≤ 623.15)
    p_Pa : float — pressure in Pa

    Returns
    -------
    dict with keys: v, h, s, cp, u  (SI units: m³/kg, J/kg, J/(kg·K))
    """
    pi = p_Pa / _R1_P_STAR
    tau = _R1_T_STAR / T_K
    _, g_pi, g_pipi, g_tau, g_tautau = _gamma1(pi, tau)
    v   = _R * T_K / p_Pa * pi * g_pi
    h   = _R * T_K * tau * g_tau
    s   = _R * (tau * g_tau - _gamma1(pi, tau)[0])
    # Recalculate g for s
    g   = _gamma1(pi, tau)[0]
    s   = _R * (tau * g_tau - g)
    cp  = -_R * tau ** 2 * g_tautau
    return {"v": v, "h": h, "s": s, "cp": cp}


# ---------------------------------------------------------------------------
# Region 2 — Superheated steam (T ≤ 1073.15 K, p ≤ psat or low pressure)
# ---------------------------------------------------------------------------
# Table 10: ideal-gas part γ°  (9 terms)
_R2_J0N0 = (
    #  (J,      n                  )
    (  0,   -0.96927686500217e1  ),
    (  1,   0.10086655968018e2   ),
    ( -5,   -0.56087911283020e-2 ),
    ( -4,   0.71452738081455e-1  ),
    ( -3,   -0.40710498223928e0  ),
    ( -2,   0.14240819171444e1   ),
    ( -1,   -0.43839511319450e1  ),
    (  2,   -0.28408632460772e0  ),
    (  3,   0.21268463753307e-1  ),
)

# Table 11: residual part γʳ  (43 terms)
_R2_IJN_R = (
    # (I,   J,      n                  )
    (  1,   0,   -0.17731742473213e-2 ),
    (  1,   1,   -0.17834862292358e-1 ),
    (  1,   2,   -0.45996013696365e-1 ),
    (  1,   3,   -0.57581259083432e-1 ),
    (  1,   6,   -0.50325278727930e-1 ),
    (  2,   1,   -0.33032641670203e-4 ),
    (  2,   2,   -0.18948987516315e-3 ),
    (  2,   4,   -0.39392777243355e-2 ),
    (  2,   7,   -0.43797295650573e-1 ),
    (  2,  36,   -0.26674547914087e-4 ),
    (  3,   0,   0.20481737692309e-7  ),
    (  3,   1,   0.43870667284435e-6  ),
    (  3,   3,   -0.32277677238570e-4 ),
    (  3,   6,   -0.15033924542148e-2 ),
    (  3,  35,   -0.40668253562649e-1 ),
    (  4,   1,   -0.78847309559367e-9 ),
    (  4,   2,   0.12790717852285e-7  ),
    (  4,   3,   0.48225372718507e-6  ),
    (  5,   7,   0.22922076337661e-5  ),
    (  6,   3,   -0.16714766451061e-10),
    (  6,  16,   -0.21171472321355e-2 ),
    (  6,  35,   -0.23895741934104e2  ),
    (  7,   0,   -0.59059564324270e-17),
    (  7,  11,   -0.12621808899101e-5 ),
    (  7,  25,   -0.38946842435739e-1 ),
    (  8,   8,   0.11256211360459e-10 ),
    (  8,  36,   -0.82311340897998e1  ),
    (  9,  13,   0.19809330248201e-7  ),
    ( 10,   4,   0.10406965210174e-18 ),
    ( 10,  10,   -0.10234747095929e-12),
    ( 10,  14,   -0.10018179379511e-8 ),
    ( 16,  29,   -0.80882908646985e-10),
    ( 16,  50,   0.10693031879409e0   ),
    ( 18,  57,   -0.33662250574171e0  ),
    ( 20,  20,   0.89185845355421e-24 ),
    ( 20,  35,   0.30629316876232e-12 ),
    ( 20,  48,   -0.42002467698208e-5 ),
    ( 21,  21,   -0.59056029685639e-25),
    ( 22,  53,   0.37826947613457e-5  ),
    ( 23,  39,   -0.12768608934681e-14),
    ( 24,  26,   0.73087610595061e-28 ),
    ( 24,  40,   0.55414715350778e-16 ),
    ( 24,  58,   -0.94369707241210e-6 ),
)

# Reducing quantities for Region 2
_R2_T_STAR = 540.0    # K
_R2_P_STAR = 1.0e6    # Pa


def _gamma2_ideal(pi: float, tau: float) -> tuple[float, float, float, float, float]:
    """Ideal-gas part γ° and derivatives for Region 2."""
    g0 = math.log(pi)   # ln(π) term
    g0_pi = 1.0 / pi
    g0_pipi = -1.0 / pi ** 2
    g0_tau = g0_tautau = 0.0
    for J, n in _R2_J0N0:
        tau_term = tau ** J
        g0 += n * tau_term
        if J != 0:
            g0_tau += n * J * tau ** (J - 1)
        # J*(J-1)=0 only for J=0 or J=1; J=-1 gives 2, must be included
        if J != 0 and J != 1:
            g0_tautau += n * J * (J - 1) * tau ** (J - 2)
    return g0, g0_pi, g0_pipi, g0_tau, g0_tautau


def _gamma2_residual(pi: float, tau: float) -> tuple[float, float, float, float, float]:
    """Residual part γʳ and derivatives for Region 2."""
    gr = gr_pi = gr_pipi = gr_tau = gr_tautau = 0.0
    for I, J, n in _R2_IJN_R:
        pi_term = pi ** I
        tau_term = (tau - 0.5) ** J
        gr += n * pi_term * tau_term
        if I != 0:
            gr_pi += n * I * pi ** (I - 1) * tau_term
        if I >= 2:
            gr_pipi += n * I * (I - 1) * pi ** (I - 2) * tau_term
        if J != 0:
            gr_tau += n * pi_term * J * (tau - 0.5) ** (J - 1)
        # J*(J-1)=0 only for J=0 or J=1; must include J=-1 etc.
        if J != 0 and J != 1:
            gr_tautau += n * pi_term * J * (J - 1) * (tau - 0.5) ** (J - 2)
    return gr, gr_pi, gr_pipi, gr_tau, gr_tautau


def region2_props(T_K: float, p_Pa: float) -> dict:
    """
    Thermodynamic properties via Region 2 (superheated steam) formulation.

    Parameters
    ----------
    T_K : float  — temperature in K (273.15 ≤ T ≤ 1073.15)
    p_Pa : float — pressure in Pa

    Returns
    -------
    dict with keys: v, h, s, cp  (SI units: m³/kg, J/kg, J/(kg·K))
    """
    pi = p_Pa / _R2_P_STAR
    tau = _R2_T_STAR / T_K
    g0, g0_pi, g0_pipi, g0_tau, g0_tautau = _gamma2_ideal(pi, tau)
    gr, gr_pi, gr_pipi, gr_tau, gr_tautau = _gamma2_residual(pi, tau)
    # Eq. (15)–(19) from IAPWS-IF97
    v   = _R * T_K / p_Pa * pi * (g0_pi + gr_pi)
    h   = _R * T_K * tau * (g0_tau + gr_tau)
    s   = _R * (tau * (g0_tau + gr_tau) - (g0 + gr))
    cp  = -_R * tau ** 2 * (g0_tautau + gr_tautau)
    return {"v": v, "h": h, "s": s, "cp": cp}


# ---------------------------------------------------------------------------
# Phase identification + dispatcher
# ---------------------------------------------------------------------------

class SteamProperties(TypedDict):
    T_K: float
    p_Pa: float
    v_m3_per_kg: float
    h_J_per_kg: float
    s_J_per_kg_K: float
    cp_J_per_kg_K: float
    phase: str


def steam_properties_if97(T_K: float, p_Pa: float) -> SteamProperties:
    """
    Compute water/steam thermodynamic properties using IAPWS-IF97.

    Dispatches to Region 1 (liquid), Region 2 (vapour), or returns a
    two-phase marker (Region 4) depending on the given T and p.

    Parameters
    ----------
    T_K : float
        Temperature in Kelvin.  Valid: 273.15 – 1073.15 K.
    p_Pa : float
        Pressure in Pascals.  Valid: above triple-point pressure.

    Returns
    -------
    SteamProperties — dict with fields:
        T_K, p_Pa, v_m3_per_kg, h_J_per_kg, s_J_per_kg_K,
        cp_J_per_kg_K, phase.
    """
    if T_K < _T_MIN or T_K > _T_R2_MAX:
        raise ValueError(
            f"T_K={T_K} outside valid range [{_T_MIN}, {_T_R2_MAX}] K"
        )
    if p_Pa <= 0.0:
        raise ValueError("p_Pa must be positive")

    # Determine psat if T is within saturation curve range
    if T_K <= _T_CRIT:
        p_sat = psat_T(T_K)
    else:
        p_sat = _P_CRIT + 1.0  # above critical T, always supercritical

    if T_K <= _T_R1_MAX and p_Pa >= p_sat:
        # Region 1 — compressed liquid (includes sub-cooled for T ≤ 623.15 K)
        props = region1_props(T_K, p_Pa)
        phase = "liquid"
    elif T_K <= _T_R2_MAX and p_Pa < p_sat:
        # Region 2 — superheated/superheated-above-saturation
        props = region2_props(T_K, p_Pa)
        phase = "vapour"
    else:
        raise ValueError(
            f"State (T={T_K} K, p={p_Pa} Pa) outside Regions 1/2 "
            "(T > 623.15 K in liquid region is Region 3, not implemented here)"
        )

    return SteamProperties(
        T_K=T_K,
        p_Pa=p_Pa,
        v_m3_per_kg=props["v"],
        h_J_per_kg=props["h"],
        s_J_per_kg_K=props["s"],
        cp_J_per_kg_K=props["cp"],
        phase=phase,
    )


# ---------------------------------------------------------------------------
# LLM tool registration
# ---------------------------------------------------------------------------
try:
    import json as _json
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx  # noqa: F401

    _steam_if97_spec = ToolSpec(
        name="fluids_steam_if97",
        description=(
            "Compute water/steam thermodynamic properties using the international "
            "IAPWS-IF97 standard (sub-mK accuracy on saturation, 5+ sig-fig "
            "accuracy on enthalpy/entropy).\n"
            "\n"
            "Covers:\n"
            "  • Region 1 — compressed liquid (T ≤ 623.15 K, p ≥ psat)\n"
            "  • Region 2 — superheated steam (T ≤ 1073.15 K, p < psat)\n"
            "  • Saturation properties via Region 4 boundary equations\n"
            "\n"
            "Returns:\n"
            "  T_K, p_Pa — input state point\n"
            "  v_m3_per_kg — specific volume (m³/kg)\n"
            "  h_J_per_kg  — specific enthalpy (J/kg)\n"
            "  s_J_per_kg_K — specific entropy (J/kg·K)\n"
            "  cp_J_per_kg_K — isobaric heat capacity (J/kg·K)\n"
            "  phase — 'liquid' or 'vapour'\n"
            "\n"
            "Errors: {ok:false, reason} for out-of-range inputs. Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "T_K": {
                    "type": "number",
                    "description": (
                        "Temperature in Kelvin. Valid range: 273.15 – 1073.15 K."
                    ),
                },
                "p_Pa": {
                    "type": "number",
                    "description": (
                        "Pressure in Pascals. Must be positive and within the "
                        "validity domain of the chosen region."
                    ),
                },
            },
            "required": ["T_K", "p_Pa"],
        },
    )

    @register(_steam_if97_spec, write=False)
    async def run_fluids_steam_if97(ctx: ProjectCtx, args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid JSON: {exc}", "BAD_ARGS")

        for field in ("T_K", "p_Pa"):
            if a.get(field) is None:
                return _json.dumps({"ok": False, "reason": f"{field} is required"})

        try:
            result = steam_properties_if97(float(a["T_K"]), float(a["p_Pa"]))
        except (ValueError, ArithmeticError) as exc:
            return err_payload(str(exc), "OUT_OF_RANGE")
        except Exception as exc:
            return err_payload(f"unexpected error: {exc}", "INTERNAL")

        return ok_payload(dict(result))

except ImportError:
    # kerf_chat not available in pure-Python / test context — skip registration
    pass
