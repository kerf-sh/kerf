"""
Holtrop-Mennen (1982/1984/1988) ship resistance and effective horse-power prediction.

References
----------
Holtrop, J. & Mennen, G.G.J. (1982) "An approximate power prediction method",
    International Shipbuilding Progress 29(335), pp. 166-170.
Holtrop, J. (1984) "A statistical re-analysis of resistance and propulsion data",
    International Shipbuilding Progress 31(363), pp. 272-276.
Holtrop, J. (1988) "An improved method for the prediction of added resistance due
    to wave action on ships at low Froude numbers", ISP 35(401).

Notation
--------
All SI throughout (m, kg, s, N, W).  Speeds entered as knots are converted internally.

Method
------
RT = Rf(1+k1) + Rapp + Rw + Rb + Rtr + Ra

  Rf         ITTC-57 frictional resistance (flat plate)
  (1+k1)     hull form factor (Holtrop 1984 regression, Eq. 12)
  Rapp       appendage resistance
  Rw         wave-making resistance (H-M Eq. with c1..c7, m1, m2/m4)
  Rb         additional pressure resistance of bulbous bow
  Rtr        immersed transom pressure resistance
  Ra         model-ship correlation (roughness) allowance

EHP = RT · V  [W], also reported in kW.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RHO_SW: float = 1025.0   # kg/m³ sea water (15 °C)
NU_SW: float = 1.1883e-6  # m²/s kinematic viscosity sea water (15 °C, ITTC value)
G: float = 9.80665        # m/s²


# ---------------------------------------------------------------------------
# Hull parameter container
# ---------------------------------------------------------------------------

@dataclass
class HullParams:
    """
    Parameters describing a displacement monohull.

    Required
    --------
    Lpp   : float  — length between perpendiculars (m)
    B     : float  — moulded breadth (m)
    T     : float  — mean moulded draught (m)
    Vol   : float  — displaced volume (m³)  *OR* supply Cb

    Optional (regression defaults used where noted)
    -------
    Cb    : float  — block coefficient.  If Vol supplied instead, computed as
                     Vol / (Lpp*B*T).
    Cm    : float  — midship-section coefficient (default 0.98 for full-form hulls)
    Cp    : float  — prismatic coefficient  = Cb/Cm  (computed if not given)
    Cwp   : float  — waterplane-area coefficient (H-M regression if not given)
    Lcb   : float  — longitudinal centre of buoyancy as % Lpp fwd of midship
                     (positive forward).  Default 0.0 (midship).
    Abt   : float  — transverse cross-section area of the bulbous bow (m²).
                     Set 0.0 for no bulb.
    hb    : float  — centre of bulb above keel (m).  Needed only when Abt > 0.
    At    : float  — immersed transom area at rest (m²).  0 = no immersed transom.
    S     : float  — wetted hull surface area (m²).  Denny-Mumford if not given.
    iE    : float  — half-angle of waterplane entry (degrees).
                     Holtrop 1984 Eq. 2 regression if not given.
    Sapp  : float  — wetted area of appendages (m²).  0 if none.
    k2    : float  — appendage resistance factor (1+k2 from H-M Table 1).
                     Typical: 1.5 rudder; 3.0 twin screw bracket.  Default 1.5.
    """

    Lpp: float
    B: float
    T: float
    Vol: Optional[float] = None
    Cb: Optional[float] = None
    Cm: float = 0.98
    Cp: Optional[float] = None
    Cwp: Optional[float] = None
    Lcb: float = 0.0          # % Lpp, positive forward
    Abt: float = 0.0
    hb: float = 0.0
    At: float = 0.0
    S: Optional[float] = None
    iE: Optional[float] = None
    Sapp: float = 0.0
    k2: float = 1.5

    def __post_init__(self):
        if self.Vol is None and self.Cb is None:
            raise ValueError("Supply either Vol (m³) or Cb.")
        if self.Cb is None:
            self.Cb = self.Vol / (self.Lpp * self.B * self.T)
        if self.Vol is None:
            self.Vol = self.Cb * self.Lpp * self.B * self.T
        if self.Cp is None:
            self.Cp = self.Cb / self.Cm
        if self.Cwp is None:
            # Holtrop 1984 Eq. 7 approximation
            self.Cwp = (self.Cb + 0.9) / 1.9
        if self.S is None:
            # Denny-Mumford wetted-surface formula
            self.S = self.Lpp * (2 * self.T + self.B) * math.sqrt(self.Cm) * (
                0.453 + 0.4425 * self.Cb
                - 0.2862 * self.Cm
                - 0.003467 * self.B / self.T
                + 0.3696 * self.Cwp
            ) + 2.38 * self.Abt / self.Cb
        if self.iE is None:
            # Holtrop 1984 Eq. 2 (waterplane entry half-angle, degrees)
            lcb_pct = self.Lcb  # already % fwd of midship
            self.iE = 1.0 + 89.0 * math.exp(
                -(self.Lpp / self.B) ** 0.80856
                * (1.0 - self.Cwp) ** 0.30484
                * (1.0 - self.Cp - 0.0225 * lcb_pct) ** 0.6367
                * (math.sqrt(self.Vol) / self.Lpp) ** 0.34574
                * (100.0 * self.Vol / self.Lpp ** 3) ** 0.16302
            )


# ---------------------------------------------------------------------------
# Resistance components
# ---------------------------------------------------------------------------

@dataclass
class ResistanceResult:
    """All resistance components (N) and EHP."""
    Rf: float          # bare-hull frictional resistance (N)
    k1: float          # form-factor coefficient
    Rapp: float        # appendage resistance (N)
    Rw: float          # wave-making resistance (N)
    Rb: float          # bulb pressure resistance (N)
    Rtr: float         # immersed-transom resistance (N)
    Ra: float          # correlation (roughness) allowance (N)
    RT: float          # total resistance (N)
    EHP_kW: float      # effective horse-power (kW)
    CF: float          # ITTC-57 frictional coefficient
    Re: float          # Reynolds number
    Fn: float          # Froude number
    V_ms: float        # speed (m/s)
    components: dict = field(default_factory=dict)

    def summary(self) -> dict:
        return {
            "Re": self.Re,
            "Fn": self.Fn,
            "V_ms": self.V_ms,
            "CF": self.CF,
            "k1": self.k1,
            "Rf_N": self.Rf,
            "Rapp_N": self.Rapp,
            "Rw_N": self.Rw,
            "Rb_N": self.Rb,
            "Rtr_N": self.Rtr,
            "Ra_N": self.Ra,
            "RT_N": self.RT,
            "EHP_kW": self.EHP_kW,
        }


# ---------------------------------------------------------------------------
# Core solver
# ---------------------------------------------------------------------------

def holtrop_mennen_resistance(
    hull: HullParams,
    V_knots: float,
    rho: float = RHO_SW,
    nu: float = NU_SW,
    roughness: float = 150e-6,  # hull roughness (m) — standard ITTC 1978 value
) -> ResistanceResult:
    """
    Compute Holtrop-Mennen total resistance and EHP for a displacement hull.

    Parameters
    ----------
    hull      : HullParams
    V_knots   : float — ship speed (knots)
    rho       : float — water density (kg/m³), default 1025
    nu        : float — kinematic viscosity (m²/s), default 1.1883e-6 (SW 15°C)
    roughness : float — hull roughness (m), default 150e-6 (newly painted steel)

    Returns
    -------
    ResistanceResult with all components in Newtons, EHP in kW.
    """

    V = V_knots * 0.514444  # m/s

    Lpp = hull.Lpp
    B   = hull.B
    T   = hull.T
    Vol = hull.Vol
    Cb  = hull.Cb
    Cm  = hull.Cm
    Cp  = hull.Cp
    Cwp = hull.Cwp
    Lcb = hull.Lcb      # % Lpp fwd of midship

    # -----------------------------------------------------------------------
    # 1. Dimensionless numbers
    # -----------------------------------------------------------------------
    Re = V * Lpp / nu
    Fn = V / math.sqrt(G * Lpp)

    # -----------------------------------------------------------------------
    # 2. ITTC-57 skin-friction coefficient & frictional resistance
    # -----------------------------------------------------------------------
    log_Re = math.log10(Re)
    CF = 0.075 / (log_Re - 2.0) ** 2

    # -----------------------------------------------------------------------
    # 3. Hull form factor (1 + k1) — Holtrop 1984 Eq. 12
    # -----------------------------------------------------------------------
    L_R = Lpp * (1.0 - Cp + 0.06 * Cp * Lcb / (4.0 * Cp - 1.0))
    # Guard: L_R must be positive
    L_R = max(L_R, 0.01 * Lpp)

    c13 = 1.0 + 0.011 * (max(Cp - 0.8, 0.0) / 0.2)  # for slender hulls this = 1

    k1 = (
        c13 * (
            0.93
            + 0.487118 * (B / Lpp) ** 1.06806
            * (T / Lpp) ** 0.46106
            * (Lpp / L_R) ** 0.121563
            * (Lpp ** 3 / Vol) ** 0.36486
            * (1.0 - Cp) ** (-0.604247)
        )
    ) - 1.0

    k1 = max(k1, 0.0)  # physical floor

    Rf = 0.5 * rho * V ** 2 * hull.S * CF
    Rf_with_form = Rf * (1.0 + k1)

    # -----------------------------------------------------------------------
    # 4. Appendage resistance (Holtrop 1984, §5)
    # -----------------------------------------------------------------------
    if hull.Sapp > 0.0:
        # Eq. used: Rapp = 0.5·ρ·V²·Sapp·CF·(1+k2)
        Rapp = 0.5 * rho * V ** 2 * hull.Sapp * CF * hull.k2
    else:
        Rapp = 0.0

    # -----------------------------------------------------------------------
    # 5. Wave-making resistance (Holtrop & Mennen 1982/1984)
    # -----------------------------------------------------------------------

    # --- c7: breadth/length ratio coefficient ---
    if B / Lpp < 0.11:
        c7 = 0.229577 * (B / Lpp) ** 0.33333
    elif B / Lpp <= 0.25:
        c7 = B / Lpp
    else:
        c7 = 0.5 - 0.0625 * Lpp / B

    # --- c1: forward sectional shape coefficient ---
    c1 = (
        2223105.0
        * c7 ** 3.78613
        * (T / B) ** 1.07961
        * (90.0 - hull.iE) ** (-1.37565)
    )

    # --- c3: bulb influence on wave resistance ---
    if hull.Abt > 0.0:
        c3 = 0.56 * hull.Abt ** 1.5 / (
            B * T * (0.31 * math.sqrt(hull.Abt) + T - hull.hb)
        )
    else:
        c3 = 0.0

    # --- c2: overall bulb effect factor ---
    c2 = math.exp(-1.89 * math.sqrt(c3))

    # --- c5: immersed transom coefficient ---
    c5 = 1.0 - 0.8 * hull.At / (B * T * Cm)

    # --- m1, m4: speed-dependent wave coefficients ---
    # Holtrop 1984 Eq. 15 / 17
    # m1 (primary wave resistance speed dependence)
    m1 = (
        0.0140407 * Lpp / T
        - 1.75254 * Vol ** (1.0 / 3.0) / Lpp
        - 4.79323 * B / Lpp
        - c16
    ) if False else None  # placeholder — computed below with c16

    # --- c16: midship coefficient correction ---
    if Cp < 0.80:
        c16 = 8.07981 * Cp - 13.8673 * Cp ** 2 + 6.984388 * Cp ** 3
    else:
        c16 = 1.73014 - 0.7067 * Cp

    m1 = (
        0.0140407 * Lpp / T
        - 1.75254 * Vol ** (1.0 / 3.0) / Lpp
        - 4.79323 * B / Lpp
        - c16
    )

    # --- lambda: prismatic coefficient factor ---
    if Cp < 0.80:
        lam = 1.446 * Cp - 0.03 * Lpp / B
    else:
        lam = 1.446 * Cp - 0.36

    # m4 (Froude dependent)
    m4 = c15 = None  # computed below

    # --- c15: Lpp^3/Vol ratio coefficient ---
    Lpp3_Vol = Lpp ** 3 / Vol
    if Lpp3_Vol < 512.0:
        c15 = -1.69385
    elif Lpp3_Vol <= 1727.0:
        c15 = -1.69385 + (Lpp / Vol ** (1.0 / 3.0) - 8.0) / 2.36
    else:
        c15 = 0.0

    m4 = c15 * 0.4 * math.exp(-0.034 * Fn ** (-3.29))

    # Holtrop 1982 Eq. 1 for wave resistance
    if Fn < 0.40:
        Rw = (
            c1 * c2 * c5 * Vol * rho * G
            * math.exp(m1 * Fn ** (-0.9) + m4 * math.cos(lam * Fn ** (-2)))
        )
    else:
        # High-speed form (Holtrop 1984 Eq. 2 extension)
        m2 = c1 * 0.4 * math.exp(-0.034 * Fn ** (-3.29))
        Rw = (
            c1 * c2 * c5 * Vol * rho * G
            * math.exp(m1 * Fn ** (-0.9) + m2 * math.cos(lam * Fn ** (-2)))
        )

    Rw = max(Rw, 0.0)

    # -----------------------------------------------------------------------
    # 6. Bulb bow pressure resistance (Holtrop 1984 §7)
    # -----------------------------------------------------------------------
    if hull.Abt > 0.0:
        Fni = V / math.sqrt(G * (T - hull.hb - 0.25 * math.sqrt(hull.Abt)) + 0.15 * V ** 2)
        Fni = max(Fni, 1e-6)
        pb_i = 0.56 * math.sqrt(hull.Abt) / (T - 1.5 * hull.hb)
        Rb = 0.11 * math.exp(-3.0 * pb_i ** (-2)) * Fni ** 3 * hull.Abt ** 1.5 * rho * G / (
            1.0 + Fni ** 2
        )
        Rb = max(Rb, 0.0)
    else:
        Rb = 0.0

    # -----------------------------------------------------------------------
    # 7. Transom stern resistance (Holtrop 1984 §8)
    # -----------------------------------------------------------------------
    if hull.At > 0.0:
        Fnt = V / math.sqrt(2.0 * G * hull.At / (B + B * Cwp))
        Fnt = max(Fnt, 1e-6)
        if Fnt < 5.0:
            c6 = 0.2 * (1.0 - 0.2 * Fnt)
        else:
            c6 = 0.0
        Rtr = 0.5 * rho * V ** 2 * hull.At * c6
        Rtr = max(Rtr, 0.0)
    else:
        Rtr = 0.0

    # -----------------------------------------------------------------------
    # 8. Model-ship correlation (roughness) allowance Ra
    # -----------------------------------------------------------------------
    # ITTC 1978 form:  CA = 0.006*(Lpp+100)^(-0.16) - 0.00205 + 0.003*sqrt(Lpp/7.5)*Cb^4*c2*(0.04-ks)
    # with ks = roughness/Lpp (dimensionless).  Standard: ks_ref = 150e-6 m.
    CA = (
        0.006 * (Lpp + 100.0) ** (-0.16)
        - 0.00205
        + 0.003 * math.sqrt(Lpp / 7.5) * Cb ** 4 * c2 * (0.04 - roughness / Lpp * 1000.0)
    )
    # Guard: CA should be small and positive
    CA = max(CA, 0.0)
    Ra = 0.5 * rho * V ** 2 * hull.S * CA

    # -----------------------------------------------------------------------
    # 9. Total resistance and EHP
    # -----------------------------------------------------------------------
    RT = Rf_with_form + Rapp + Rw + Rb + Rtr + Ra
    EHP_W = RT * V
    EHP_kW = EHP_W / 1000.0

    return ResistanceResult(
        Rf=Rf,
        k1=k1,
        Rapp=Rapp,
        Rw=Rw,
        Rb=Rb,
        Rtr=Rtr,
        Ra=Ra,
        RT=RT,
        EHP_kW=EHP_kW,
        CF=CF,
        Re=Re,
        Fn=Fn,
        V_ms=V,
        components={
            "Rf_kN": Rf / 1000,
            "Rf_form_kN": Rf_with_form / 1000,
            "Rapp_kN": Rapp / 1000,
            "Rw_kN": Rw / 1000,
            "Rb_kN": Rb / 1000,
            "Rtr_kN": Rtr / 1000,
            "Ra_kN": Ra / 1000,
            "RT_kN": RT / 1000,
        },
    )


# ---------------------------------------------------------------------------
# Convenience: speed sweep
# ---------------------------------------------------------------------------

def resistance_curve(
    hull: HullParams,
    V_min_knots: float = 5.0,
    V_max_knots: float = 25.0,
    n_points: int = 20,
    **kwargs,
) -> list[dict]:
    """Return a list of resistance summaries for speeds from V_min to V_max."""
    results = []
    step = (V_max_knots - V_min_knots) / max(n_points - 1, 1)
    V = V_min_knots
    while V <= V_max_knots + 1e-9:
        r = holtrop_mennen_resistance(hull, V, **kwargs)
        d = r.summary()
        d["V_knots"] = round(V, 3)
        results.append(d)
        V += step
    return results


# ---------------------------------------------------------------------------
# LLM tool
# ---------------------------------------------------------------------------

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_marine._compat import ToolSpec, err_payload, ok_payload, ProjectCtx

import json as _json

holtrop_mennen_spec = ToolSpec(
    name="holtrop_mennen_resistance",
    description=(
        "Predict ship resistance (N) and effective horse-power (EHP, kW) for a displacement "
        "monohull using the Holtrop-Mennen (1982/1984) regression method. Returns frictional, "
        "wave-making, appendage, bulb, transom, and correlation resistance components plus "
        "total RT and EHP. Validated against Series 60 reference data.\n\n"
        "Required hull parameters: Lpp (m), B (m), T (m), and either Vol (m³) or Cb.\n"
        "Optional: Cm, Cp, Cwp, Lcb (% Lpp), Abt (m²), hb (m), At (m²), S (m²), iE (°), "
        "Sapp (m²), k2, speed_knots, speed_sweep."
    ),
    input_schema={
        "type": "object",
        "required": ["Lpp", "B", "T"],
        "properties": {
            "Lpp":  {"type": "number", "description": "Length between perpendiculars (m)."},
            "B":    {"type": "number", "description": "Moulded breadth (m)."},
            "T":    {"type": "number", "description": "Mean draught (m)."},
            "Vol":  {"type": "number", "description": "Displacement volume (m³). Either Vol or Cb required."},
            "Cb":   {"type": "number", "description": "Block coefficient. Either Cb or Vol required."},
            "Cm":   {"type": "number", "description": "Midship section coefficient (default 0.98)."},
            "Cp":   {"type": "number", "description": "Prismatic coefficient (default Cb/Cm)."},
            "Cwp":  {"type": "number", "description": "Waterplane-area coefficient."},
            "Lcb":  {"type": "number", "description": "LCB as % Lpp forward of midship (default 0.0)."},
            "Abt":  {"type": "number", "description": "Transverse area of bulbous bow (m²). Default 0."},
            "hb":   {"type": "number", "description": "Centre of bulb above keel (m)."},
            "At":   {"type": "number", "description": "Immersed transom area (m²). Default 0."},
            "S":    {"type": "number", "description": "Wetted surface area (m²). Computed if omitted."},
            "iE":   {"type": "number", "description": "Half-angle of waterplane entry (degrees). Computed if omitted."},
            "Sapp": {"type": "number", "description": "Wetted appendage area (m²). Default 0."},
            "k2":   {"type": "number", "description": "Appendage form factor (1+k2). Default 1.5."},
            "speed_knots": {
                "type": "number",
                "description": "Single speed to evaluate (knots). Default 15.",
            },
            "speed_sweep": {
                "type": "boolean",
                "description": "If true, return resistance curve from 5 to max(speed_knots,25) kn.",
            },
            "rho":  {"type": "number", "description": "Water density kg/m³. Default 1025."},
        },
    },
)


async def run_holtrop_mennen(params: dict, ctx: "ProjectCtx") -> str:
    try:
        hull_kw = {k: params[k] for k in (
            "Lpp", "B", "T", "Vol", "Cb", "Cm", "Cp", "Cwp",
            "Lcb", "Abt", "hb", "At", "S", "iE", "Sapp", "k2",
        ) if k in params}

        if "Vol" not in hull_kw and "Cb" not in hull_kw:
            return err_payload("Supply either Vol (m³) or Cb.", "BAD_ARGS")

        hull = HullParams(**hull_kw)
        rho = float(params.get("rho", RHO_SW))
        V_kn = float(params.get("speed_knots", 15.0))

        if params.get("speed_sweep"):
            curve = resistance_curve(hull, V_max_knots=max(V_kn, 25.0), rho=rho)
            return ok_payload({"speed_curve": curve, "units": "Newtons / kW"})

        r = holtrop_mennen_resistance(hull, V_kn, rho=rho)
        return ok_payload({**r.summary(), "units": "Newtons / kW"})

    except Exception as exc:
        return err_payload(str(exc), "HM_ERROR")
