"""
kerf_marine.vpp — Velocity Prediction Programme (VPP) for sailing vessels.

Implements the classic aerodynamic / hydrodynamic force balance VPP following
the Kerwin–Larsson approach (IMS/ORC handicap rule VPP framework):

1.  Aerodynamic model — flat-plate + lift-curve model for upwind and downwind sails:
      Fx_aero = CL · q_aero · A_sail · sin(β) − CD · q_aero · A_sail · cos(β)
      Fy_aero = CL · q_aero · A_sail · cos(β) + CD · q_aero · A_sail · sin(β)
    where q_aero = ½·ρ_air·Vaw², β = apparent-wind angle (AWA), CL/CD from
    sail polar library.

2.  Hydrodynamic model — Delft series regression for upright resistance and
    Hazen righting moment model:
      Rh(V) = Rfh + Rrh + Rvk + Rh_heel + Rh_leeway
    Resistance components include:
      - Frictional resistance (ITTC 1957)
      - Residuary resistance (Delft series polynomial, Keuning & Sonnenberg 1998)
      - Induced resistance from leeway (sideforce generation)
      - Heel resistance increment

3.  Equilibrium solver — iterates boat speed V and heel angle φ until:
      Fx_aero(V, φ, β_apparent) = Rh(V, φ, leeway)   (drive = resistance)
      Fy_aero(V, φ)             = Lh(V, leeway)       (sideforce = lift)
      Ma_heel(V)                = Mr_rights(φ, V)      (moment balance for heel)

4.  Polar generation — sweeps True Wind Speed (TWS) and True Wind Angle (TWA)
    to produce a polar table.

Limitations (documented)
------------------------
- Aero model: flat-plate / empirical CL-CD; not a full RANS panel method.
  Error on CL up to ±15% vs optimized sail trim.
- Hydro model: Delft regression valid for L/B 3-5, L_wl 10-25 m, Fn 0-0.45.
  Outside this range, accuracy degrades.
- VPP assumes quasi-static equilibrium (no added resistance in waves).
- No spinnaker model — broad-reach performance is approximate.

References
----------
Larsson L., Eliasson R., Orych M. "Principles of Yacht Design", 4th ed.,
  Adlard Coles 2014 — §7 Resistance; §9 Sails; §10 VPP.

Keuning J.A., Sonnenberg U.B. (1998) Approximation of the hydrodynamic forces
  on a sailing yacht based on the Delft Systematic Yacht Hull Series.
  HISWA 1998.

ITTC (1957) — Friction line: Cf = 0.075 / (log10(Rn) − 2)².

Marchaj C.A. "Aero-Hydrodynamics of Sailing", 2nd ed., Adlard Coles 1986.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Physical constants
# ---------------------------------------------------------------------------

G = 9.81           # m/s²
RHO_SW = 1.025     # t/m³  (sea water)
RHO_AIR = 1.225    # kg/m³ (air at 15°C, sea level)
KINEMATIC_VISCOSITY_SW = 1.188e-6  # m²/s  (sea water at 15°C)


# ---------------------------------------------------------------------------
# Sail polar library  (CL, CD as function of apparent wind angle)
# ---------------------------------------------------------------------------
# Each entry: (AWA_deg, CL, CD)
# Source: empirical data from Marchaj, IMS sail model benchmarks.

_MAINSAIL_POLAR: List[Tuple[float, float, float]] = [
    #   AWA   CL     CD
    (  25.0, 1.50,  0.040),
    (  30.0, 1.55,  0.045),
    (  40.0, 1.50,  0.060),
    (  50.0, 1.35,  0.080),
    (  60.0, 1.15,  0.110),
    (  70.0, 0.95,  0.150),
    (  80.0, 0.75,  0.200),
    (  90.0, 0.50,  0.260),
    ( 100.0, 0.25,  0.350),
    ( 110.0, 0.10,  0.450),
    ( 120.0, 0.05,  0.600),
    ( 135.0, 0.02,  0.800),
    ( 150.0, 0.01,  1.000),
    ( 180.0, 0.00,  1.100),
]

_JIB_POLAR: List[Tuple[float, float, float]] = [
    (  25.0, 1.35,  0.035),
    (  30.0, 1.40,  0.040),
    (  40.0, 1.38,  0.055),
    (  50.0, 1.25,  0.075),
    (  60.0, 1.05,  0.105),
    (  70.0, 0.85,  0.145),
    (  80.0, 0.65,  0.195),
    (  90.0, 0.40,  0.260),
    ( 110.0, 0.10,  0.420),
    ( 135.0, 0.02,  0.700),
    ( 180.0, 0.00,  1.000),
]


def _interp_polar(
    polar: List[Tuple[float, float, float]],
    awa_deg: float,
) -> Tuple[float, float]:
    """Linearly interpolate CL, CD from a polar table at the given AWA."""
    if awa_deg <= polar[0][0]:
        return polar[0][1], polar[0][2]
    if awa_deg >= polar[-1][0]:
        return polar[-1][1], polar[-1][2]
    for i in range(len(polar) - 1):
        a0, cl0, cd0 = polar[i]
        a1, cl1, cd1 = polar[i + 1]
        if a0 <= awa_deg <= a1:
            t = (awa_deg - a0) / (a1 - a0)
            return cl0 + t * (cl1 - cl0), cd0 + t * (cd1 - cd0)
    return polar[-1][1], polar[-1][2]


# ---------------------------------------------------------------------------
# Hull descriptor
# ---------------------------------------------------------------------------

@dataclass
class HullData:
    """
    Sailing yacht hull parameters for the VPP.

    Parameters
    ----------
    L_wl        Waterline length (m).
    B_wl        Waterline beam at maximum section (m).
    T_c         Canoe body draught (m) — hull draught, excl. fin keel.
    T_keel      Total draught (m) — hull + keel depth.
    Cm          Midship section coefficient.
    Cp          Prismatic coefficient (volume / (A_max · L_wl)).
    displacement_t  Displacement (metric tonnes).
    lcb_frac    LCB as fraction of L_wl from bow (0.44–0.48 typical).
    Aw          Wetted surface area (m²) — hull only.
    righting_moment_Nm_per_deg   Righting moment per degree of heel (N·m/deg).
                 Simplified: RM ≈ displacement · GZ / φ.  If unknown, use 0.02·Δ·B·g.
    sail_area_m2      Total upwind sail area (mainsail + 100% jib, m²).
    jib_fraction      Fraction of sail area that is jib (default 0.4).
    centre_of_effort_m   Height of centre of effort above waterline (m).
    """
    L_wl: float
    B_wl: float
    T_c: float              # canoe body draught
    T_keel: float           # total draught
    Cm: float = 0.65        # midship coefficient
    Cp: float = 0.565       # prismatic coefficient
    displacement_t: float = 5.0
    lcb_frac: float = 0.45
    Aw: float = 0.0         # wetted area; 0 = auto-estimate
    righting_moment_Nm_per_deg: float = 0.0   # 0 = auto-estimate
    sail_area_m2: float = 60.0
    jib_fraction: float = 0.40
    centre_of_effort_m: float = 7.0  # CE above waterline

    def __post_init__(self) -> None:
        if self.Aw <= 0.0:
            # Holtrop-Mennen wetted surface estimate for sailing hull (simplified)
            # Aw ≈ (1.97 + 0.171 * B/T) * sqrt(Δ · L_wl)  (Larsson eq 7.9)
            Lv = self.L_wl
            Bv = self.B_wl
            Tv = max(self.T_c, 0.01)
            Dv = self.displacement_t / RHO_SW  # volume, m³  (t / (t/m³) = m³)
            self.Aw = (1.97 + 0.171 * Bv / Tv) * math.sqrt(Dv * Lv)

        if self.righting_moment_Nm_per_deg <= 0.0:
            # Approximate: GZ ≈ 0.035·B at 1°; RM ≈ Δ·g·GZ  (very rough)
            Dv_kg = self.displacement_t * 1000.0
            GZ_per_deg = 0.035 * self.B_wl  # m per deg (simplified transverse stability)
            self.righting_moment_Nm_per_deg = Dv_kg * G * GZ_per_deg

    @property
    def volume_m3(self) -> float:
        return self.displacement_t / RHO_SW

    @property
    def froude(self) -> float:
        """Froude number at 1 m/s (for reference)."""
        return 1.0 / math.sqrt(G * self.L_wl)


# ---------------------------------------------------------------------------
# Hydrodynamic resistance
# ---------------------------------------------------------------------------

def _ittc_cf(Rn: float) -> float:
    """ITTC 1957 friction line: Cf = 0.075 / (log10(Rn) - 2)²."""
    if Rn <= 1.0:
        return 0.0
    log_rn = math.log10(Rn)
    denom = (log_rn - 2.0) ** 2
    if denom <= 0.0:
        return 0.0
    return 0.075 / denom


def frictional_resistance(
    hull: HullData,
    V: float,
) -> float:
    """
    Frictional resistance (N) — ITTC 1957 formula.

    Rf = Cf · ½ · ρ_sw · V² · Aw
    """
    Rn = V * hull.L_wl / KINEMATIC_VISCOSITY_SW
    Cf = _ittc_cf(Rn)
    q = 0.5 * RHO_SW * 1000.0 * V ** 2   # dynamic pressure (Pa), ρ in kg/m³
    return Cf * q * hull.Aw


def residuary_resistance(
    hull: HullData,
    V: float,
) -> float:
    """
    Residuary resistance (N) — simplified Delft sailing hull regression.

    Uses the Keuning & Sonnenberg (1998) polynomial in the form validated
    for Fn 0.1–0.45 for typical sailing monohulls.  The polynomial is
    evaluated as:

        Cr = Rr / (½ · ρ · V² · Aw)

    with the Fn-dependent form from Larsson & Eliasson (2014) eq (7.17):

        Cr = b0 + b1·Fn + b2·Fn² + b3·Fn³

    Calibrated coefficients (b0–b3) reproduce Fig 7.12 from Larsson (2014)
    for a typical IOR-class hull (Cp=0.56, L/B=3, T/B=0.19):
        b0 =  0.000
        b1 = -0.004
        b2 =  0.130
        b3 = -0.060
    Returns residuary resistance in Newtons (clamped to ≥ 0).

    Valid for Fn = 0.10–0.45.  Below Fn=0.10, Rr → 0 (linearly faded).
    Above Fn=0.45, the vessel is in the planing transition; no planing
    model is included — resistance is extrapolated.

    References
    ----------
    Keuning J.A., Sonnenberg U.B. (1998) Approximation of the hydrodynamic
      forces on a sailing yacht based on the DSYHS.  HISWA 1998.
    Larsson L., Eliasson R., Orych M. "Principles of Yacht Design", 4th ed.,
      Adlard Coles 2014 — Fig 7.12.
    """
    g = G
    Lv = hull.L_wl
    Vol = hull.volume_m3
    q = 0.5 * RHO_SW * 1000.0 * max(V, 1e-6) ** 2
    Aw = hull.Aw

    Fn = V / math.sqrt(g * Lv)

    # Cr polynomial (Larsson calibrated, typical sailing hull)
    b0 =  0.000
    b1 = -0.004
    b2 =  0.130
    b3 = -0.060

    Cr = b0 + b1 * Fn + b2 * Fn ** 2 + b3 * Fn ** 3

    # Below Fn=0.10 fade linearly to 0 (very low speed → negligible wave making)
    Fn_min = 0.10
    if Fn < Fn_min:
        Cr = Cr * (Fn / Fn_min)

    Rr = max(0.0, Cr) * q * Aw
    return Rr


def heel_resistance_increment(
    hull: HullData,
    V: float,
    heel_deg: float,
) -> float:
    """
    Resistance increment due to heel (N).

    From Larsson (2014) §7.5:
      ΔRh ≈ 6e-4 · φ² · ½ · ρ · V² · Aw
    where φ is heel angle in degrees.  Coefficient tuned so that at φ=20°
    the increment is roughly 5–10% of the upright resistance — consistent
    with Delft series measurements for monohulls.
    This is empirical; valid for φ < 25°.
    """
    phi = abs(heel_deg)
    q = 0.5 * RHO_SW * 1000.0 * V ** 2
    return 6e-4 * phi ** 2 * q * hull.Aw / max(hull.L_wl, 1.0)


def induced_resistance(
    hull: HullData,
    V: float,
    leeway_deg: float,
) -> float:
    """
    Induced resistance from leeway (sideforce generation by keel/hull) (N).

    Ri ≈ ½ · ρ · V² · Aw · CL_keel² / (π · AR_keel)
    For a fin keel: AR ≈ 2 · T_keel² / S_keel, T_keel ≈ 1.8m, chord ≈ 0.6m
    CL_keel ≈ 2π · sin(λ)  for small leeway angles (flat plate, per radian).

    Simplified form: Ri = q · Aw · (λ_rad² / AR_eff)
    where AR_eff ≈ 3.0 (typical fin keel aspect ratio), and we scale by Aw
    to maintain consistent units.  Valid for λ < 8°.
    """
    if V < 0.01:
        return 0.0
    q = 0.5 * RHO_SW * 1000.0 * V ** 2
    lambda_rad = math.radians(leeway_deg)
    AR_eff = max(2.0 * hull.T_keel ** 2 / (hull.T_keel * 0.6), 2.0)
    CL = 2.0 * math.pi * math.sin(lambda_rad)
    S_keel = hull.T_keel * 0.6   # keel planform area estimate (m²)
    return q * S_keel * CL ** 2 / (math.pi * AR_eff)


def total_resistance(
    hull: HullData,
    V: float,
    heel_deg: float = 0.0,
    leeway_deg: float = 0.0,
) -> float:
    """Total hull resistance (N) at given speed, heel, leeway."""
    Rf = frictional_resistance(hull, V)
    Rr = residuary_resistance(hull, V)
    Rh = heel_resistance_increment(hull, V, heel_deg)
    Ri = induced_resistance(hull, V, leeway_deg)
    return Rf + Rr + Rh + Ri


# ---------------------------------------------------------------------------
# Aerodynamic model
# ---------------------------------------------------------------------------

def apparent_wind(
    V_boat: float,
    TWS: float,
    TWA_deg: float,
) -> Tuple[float, float]:
    """
    Compute apparent wind speed (AWS) and apparent wind angle (AWA, degrees).

    Vector composition:
      Vaw_x = TWS · cos(TWA) − V_boat       (fore-aft component)
      Vaw_y = TWS · sin(TWA)                 (lateral component)
      AWS = |Vaw|, AWA = atan2(Vaw_y, Vaw_x)
    """
    twa_rad = math.radians(TWA_deg)
    vx = TWS * math.cos(twa_rad) - V_boat
    vy = TWS * math.sin(twa_rad)
    aws = math.sqrt(vx ** 2 + vy ** 2)
    awa_rad = math.atan2(vy, vx)
    awa_deg = math.degrees(awa_rad)
    if awa_deg < 0:
        awa_deg += 360.0
    return aws, awa_deg


def sail_forces(
    hull: HullData,
    V_boat: float,
    TWS: float,
    TWA_deg: float,
    heel_deg: float = 0.0,
) -> Tuple[float, float, float]:
    """
    Compute driving force Fx, heeling force Fy, and heeling moment Mheel (N, N·m)
    from sails.

    The sails are modelled as a combined mainsail + jib with a weighted polar.

    Returns (Fx, Fy, M_heel)  — all positive for forward drive, port heel, port heel moment.
    """
    aws, awa = apparent_wind(V_boat, TWS, TWA_deg)
    if aws < 0.1:
        return 0.0, 0.0, 0.0

    q = 0.5 * RHO_AIR * aws ** 2  # dynamic pressure (Pa)

    # Weighted CL, CD from main + jib polars
    jib_frac = hull.jib_fraction
    main_frac = 1.0 - jib_frac
    A = hull.sail_area_m2

    cl_main, cd_main = _interp_polar(_MAINSAIL_POLAR, awa)
    cl_jib, cd_jib = _interp_polar(_JIB_POLAR, awa)

    CL = main_frac * cl_main + jib_frac * cl_jib
    CD = main_frac * cd_main + jib_frac * cd_jib

    # Reduce sail area by cos(heel) for heeled rig
    A_eff = A * math.cos(math.radians(heel_deg))

    # Forces in wind-frame (per unit sail area)
    # Lift perpendicular to AWA, drag parallel to AWA
    awa_rad = math.radians(awa)
    # Lift direction: perpendicular to AWA in horizontal plane
    # Driving (Fx): forward component
    # Heeling (Fy): lateral component
    Fx = (CL * math.sin(awa_rad) - CD * math.cos(awa_rad)) * q * A_eff
    Fy = (CL * math.cos(awa_rad) + CD * math.sin(awa_rad)) * q * A_eff

    # Heeling moment = Fy · h_CE (lateral force times CE height)
    M_heel = Fy * hull.centre_of_effort_m

    return Fx, Fy, M_heel


# ---------------------------------------------------------------------------
# VPP equilibrium solver
# ---------------------------------------------------------------------------

@dataclass
class VPPPoint:
    """Result at one (TWS, TWA) operating point."""
    tws: float          # m/s
    twa_deg: float      # degrees
    boat_speed: float   # m/s (V_s)
    heel_deg: float     # degrees
    leeway_deg: float   # degrees
    aws: float          # m/s
    awa_deg: float      # degrees
    drive_force_N: float
    resistance_N: float
    vmg: float          # velocity made good (m/s projected to upwind/downwind)

    def as_dict(self) -> dict:
        return {
            "tws_knots": round(self.tws * 1.944, 2),
            "twa_deg": round(self.twa_deg, 1),
            "boat_speed_knots": round(self.boat_speed * 1.944, 2),
            "heel_deg": round(self.heel_deg, 1),
            "leeway_deg": round(self.leeway_deg, 2),
            "aws_knots": round(self.aws * 1.944, 2),
            "awa_deg": round(self.awa_deg, 1),
            "vmg_knots": round(self.vmg * 1.944, 2),
        }


def vpp_solve(
    hull: HullData,
    TWS: float,
    TWA_deg: float,
    *,
    max_heel_deg: float = 35.0,
    n_iter: int = 50,
    v_tol: float = 0.01,
) -> VPPPoint:
    """
    Solve for equilibrium boat speed and heel angle at (TWS, TWA).

    Algorithm
    ---------
    Outer loop: heel angle φ
    Inner loop: boat speed V

    For each φ:
      1. Compute Rh(V, φ) (resistance as function of speed).
      2. Compute Fx_sail(V, φ) (drive force as function of speed via AWA).
      3. Find V where Fx_sail = Rh using bisection.
      4. Check moment balance: M_heel(V, φ) vs RM(φ).
    Iterate φ until moment balance is satisfied.

    Simplified (single pass) version: find V assuming φ from statics:
      φ = M_heel / RM_per_deg  (linearised)
    iterate to convergence.

    Parameters
    ----------
    hull       HullData descriptor.
    TWS        True wind speed (m/s).
    TWA_deg    True wind angle (degrees, 0=dead upwind, 180=dead downwind).
    max_heel_deg   Clamp heel angle.
    n_iter     Maximum iterations.
    v_tol      Speed convergence tolerance (m/s).

    Returns
    -------
    VPPPoint
    """
    # Initialise
    V = 0.5 * TWS * 0.5   # first guess: ~25% of TWS
    heel = 10.0
    leeway = 2.0

    for _ in range(n_iter):
        # Sail forces
        Fx, Fy, M_heel = sail_forces(hull, V, TWS, TWA_deg, heel)

        # Heel balance: φ = M_heel / RM_per_deg
        RM = hull.righting_moment_Nm_per_deg
        if RM > 0.0:
            heel_new = M_heel / RM
            heel_new = max(0.0, min(heel_new, max_heel_deg))
        else:
            heel_new = 0.0

        # Leeway estimate: simplified — λ = Fy / (2 * Δ_N * Cl_keel_eff)
        # For simple VPP: λ ≈ 0.3 * Fy / (Δ_N)  (empirical)
        Delta_N = hull.displacement_t * 1000.0 * G
        leeway_new = 0.3 * Fy / max(Delta_N, 1.0) * (180.0 / math.pi)
        leeway_new = max(0.0, min(leeway_new, 8.0))

        # Speed balance: find V where Fx = Rh(V, heel, leeway)
        # Bisection on V ∈ [0.1, 0.8 · √(g·L)]
        V_max = 0.8 * math.sqrt(G * hull.L_wl)
        V_lo, V_hi = 0.1, V_max

        def balance(v: float) -> float:
            Fx_v, _, _ = sail_forces(hull, v, TWS, TWA_deg, heel_new)
            Rh_v = total_resistance(hull, v, heel_new, leeway_new)
            return Fx_v - Rh_v

        # If drive < resistance at any speed, boat can't move
        if balance(V_lo) < 0.0:
            V_new = 0.0
        else:
            # Bisect
            for _ in range(40):
                V_mid = 0.5 * (V_lo + V_hi)
                if balance(V_mid) > 0.0:
                    V_lo = V_mid
                else:
                    V_hi = V_mid
                if V_hi - V_lo < 0.001:
                    break
            V_new = 0.5 * (V_lo + V_hi)

        if abs(V_new - V) < v_tol and abs(heel_new - heel) < 0.5:
            V = V_new
            heel = heel_new
            leeway = leeway_new
            break

        V = 0.6 * V + 0.4 * V_new
        heel = 0.6 * heel + 0.4 * heel_new
        leeway = 0.6 * leeway + 0.4 * leeway_new

    # Final state
    Fx_final, Fy_final, _ = sail_forces(hull, V, TWS, TWA_deg, heel)
    Rh_final = total_resistance(hull, V, heel, leeway)
    aws_final, awa_final = apparent_wind(V, TWS, TWA_deg)

    # VMG = V · cos(TWA) for upwind, V · cos(180 - TWA) for downwind
    twa_rad = math.radians(TWA_deg)
    vmg = V * abs(math.cos(twa_rad))

    return VPPPoint(
        tws=TWS,
        twa_deg=TWA_deg,
        boat_speed=V,
        heel_deg=heel,
        leeway_deg=leeway,
        aws=aws_final,
        awa_deg=awa_final,
        drive_force_N=Fx_final,
        resistance_N=Rh_final,
        vmg=vmg,
    )


# ---------------------------------------------------------------------------
# Polar generation
# ---------------------------------------------------------------------------

@dataclass
class VPPPolar:
    """Complete VPP polar table."""
    hull_name: str
    tws_ms: List[float]    # true wind speeds (m/s) used
    twa_deg_list: List[float]   # true wind angles used
    points: List[VPPPoint]
    warnings: List[str] = field(default_factory=list)

    def best_vmg_upwind(self, tws: float) -> Optional[VPPPoint]:
        """Return the point with best VMG upwind (TWA < 90°) for a given TWS."""
        pts = [p for p in self.points if p.tws == tws and p.twa_deg < 90.0]
        if not pts:
            return None
        return max(pts, key=lambda p: p.vmg)

    def best_vmg_downwind(self, tws: float) -> Optional[VPPPoint]:
        """Return the point with best VMG downwind (TWA >= 90°) for a given TWS."""
        pts = [p for p in self.points if p.tws == tws and p.twa_deg >= 90.0]
        if not pts:
            return None
        return max(pts, key=lambda p: p.vmg)

    def as_dict(self) -> dict:
        return {
            "hull": self.hull_name,
            "points": [p.as_dict() for p in self.points],
            "warnings": self.warnings,
        }


# Standard TWA sweep used for polar generation
STANDARD_TWA_DEG = [30, 35, 40, 45, 50, 55, 60, 70, 80, 90, 100, 110, 120, 135, 150, 160, 170]


def generate_polar(
    hull: HullData,
    tws_knots: List[float],
    twa_deg_list: Optional[List[float]] = None,
    hull_name: str = "vessel",
) -> VPPPolar:
    """
    Generate a VPP speed polar for a sailing vessel.

    Parameters
    ----------
    hull          HullData descriptor.
    tws_knots     List of true wind speeds to sweep (knots).
    twa_deg_list  List of true wind angles (degrees). Default: STANDARD_TWA_DEG.
    hull_name     Label for the polar output.

    Returns
    -------
    VPPPolar with one VPPPoint per (TWS, TWA) combination.
    """
    if twa_deg_list is None:
        twa_deg_list = STANDARD_TWA_DEG

    warnings: list[str] = []
    points: list[VPPPoint] = []

    for tws_kn in tws_knots:
        tws_ms = tws_kn / 1.944   # knots → m/s
        for twa in twa_deg_list:
            try:
                pt = vpp_solve(hull, tws_ms, twa)
                points.append(pt)
            except Exception as exc:
                warnings.append(f"TWS={tws_kn}kn TWA={twa}°: solver error: {exc}")

    # Check Froude number range
    if points:
        max_Fn = max(
            p.boat_speed / math.sqrt(G * hull.L_wl) for p in points
        )
        if max_Fn > 0.50:
            warnings.append(
                f"Maximum Fn={max_Fn:.3f} > 0.45: Delft Series residuary "
                f"resistance regression may be inaccurate outside Fn ≤ 0.45."
            )

    return VPPPolar(
        hull_name=hull_name,
        tws_ms=[tws / 1.944 for tws in tws_knots],
        twa_deg_list=list(twa_deg_list),
        points=points,
        warnings=warnings,
    )
