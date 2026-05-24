"""
kerf_mold.cooling — Injection-mold cooling channel thermal analysis.

Implements the Binder-Cahn mold cooling model (Menges et al. 2001) for:
  - Series and parallel cooling circuit layouts
  - Reynolds number and turbulence classification
  - Heat-transfer coefficient from Dittus-Boelter / Sieder-Tate
  - Cooling time estimate (Janeschitz-Kriegl squeezing model)
  - Coolant temperature rise and heat load

Key functions
-------------
CoolingChannel   — single straight channel descriptor.
CoolingCircuit   — collection of channels in series or parallel.
channel_flow     — Re, Nu, h, pressure drop for one channel.
circuit_analysis — Full thermal analysis of a cooling circuit.
cooling_time     — Estimated mould-open cooling time (part ejection).

References
----------
Menges G., Michaeli W., Mohren P. "How to Make Injection Molds", 3rd ed.,
  Hanser 2001 — §9 Cooling systems; §9.2 Heat transfer; §9.4 Cooling time.

Dittus F.W., Boelter L.M.K. (1930) Heat transfer in automobile radiators.
  Univ. Calif. Pub. Eng. 2(13):443–461.
  Nu = 0.023 · Re^0.8 · Pr^0.4  (turbulent, heating; exponent 0.3 for cooling)

Janeschitz-Kriegl H. (1979) Injection moulding of plastics.
  Cooling time model: t_cool = s² / (π² · a) · ln(4/π · (ΔT_melt / ΔT_eject))
  where a = thermal diffusivity of polymer (m²/s).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence


# ---------------------------------------------------------------------------
# Physical constants and material libraries
# ---------------------------------------------------------------------------

# Water coolant properties at ~25 °C (reference for calculations)
# Users can override via CoolantProperties
_WATER_DENSITY = 997.0        # kg/m³
_WATER_VISCOSITY = 8.90e-4    # Pa·s  (dynamic, 25°C)
_WATER_THERMAL_COND = 0.610   # W/(m·K)
_WATER_SPECIFIC_HEAT = 4182.0 # J/(kg·K)  (Cp)
_WATER_PRANDTL = (
    _WATER_VISCOSITY * _WATER_SPECIFIC_HEAT / _WATER_THERMAL_COND
)   # ≈ 6.09

# Common polymer thermal diffusivity (m²/s) — for cooling time estimate
POLYMER_THERMAL_DIFFUSIVITY: dict[str, float] = {
    "PP":  8.6e-8,    # polypropylene
    "PE":  9.0e-8,    # polyethylene (HDPE)
    "ABS": 1.0e-7,    # acrylonitrile-butadiene-styrene
    "PA6": 1.0e-7,    # nylon 6
    "PC":  1.2e-7,    # polycarbonate
    "POM": 9.0e-8,    # acetal (Delrin)
    "PS":  9.0e-8,    # polystyrene
    "PVC": 1.1e-7,    # rigid PVC
}

# Default mould steel thermal conductivity (W/(m·K)) — P20, H13, etc.
MOULD_STEEL_K = 29.0   # W/(m·K)  (P20 tool steel)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CoolantProperties:
    """Thermophysical properties of the cooling fluid."""
    name: str = "water"
    density_kg_m3: float = _WATER_DENSITY
    dynamic_viscosity_Pa_s: float = _WATER_VISCOSITY
    thermal_conductivity_W_mK: float = _WATER_THERMAL_COND
    specific_heat_J_kgK: float = _WATER_SPECIFIC_HEAT

    @property
    def prandtl(self) -> float:
        """Dimensionless Prandtl number."""
        return (
            self.dynamic_viscosity_Pa_s * self.specific_heat_J_kgK
            / self.thermal_conductivity_W_mK
        )

    @property
    def kinematic_viscosity_m2_s(self) -> float:
        return self.dynamic_viscosity_Pa_s / self.density_kg_m3


@dataclass
class CoolingChannel:
    """
    A single straight cylindrical cooling channel.

    Parameters
    ----------
    diameter_mm      Channel bore diameter (mm).
    length_mm        Channel straight-run length (mm).
    distance_mm      Centre-to-wall distance: depth from cavity surface (mm).
    pitch_mm         Centre-to-centre distance between parallel channels (mm).
                     Used for heat flux uniformity estimate.
    label            Optional label (e.g. 'C1-inlet', 'C2-return').
    """
    diameter_mm: float = 10.0
    length_mm: float = 200.0
    distance_mm: float = 15.0   # depth from parting surface
    pitch_mm: float = 25.0
    label: str = ""

    @property
    def diameter_m(self) -> float:
        return self.diameter_mm * 1e-3

    @property
    def length_m(self) -> float:
        return self.length_mm * 1e-3

    @property
    def cross_section_area_m2(self) -> float:
        return math.pi * (self.diameter_m / 2.0) ** 2

    @property
    def hydraulic_diameter_m(self) -> float:
        """For a circular pipe: D_h = D."""
        return self.diameter_m


@dataclass
class CoolingCircuit:
    """
    A complete cooling circuit (series or parallel channels).

    Parameters
    ----------
    channels      Ordered list of CoolingChannel objects.
    layout        'series' or 'parallel'.
    flow_rate_lpm Volumetric flow rate (litres per minute, total circuit).
    coolant_inlet_temp_c  Coolant inlet temperature (°C).
    """
    channels: List[CoolingChannel] = field(default_factory=list)
    layout: str = "series"       # 'series' | 'parallel'
    flow_rate_lpm: float = 5.0   # L/min
    coolant_inlet_temp_c: float = 20.0

    def __post_init__(self) -> None:
        if self.layout not in ("series", "parallel"):
            raise ValueError(f"layout must be 'series' or 'parallel', got {self.layout!r}")
        if not self.channels:
            raise ValueError("CoolingCircuit must have at least one channel")
        if self.flow_rate_lpm <= 0.0:
            raise ValueError("flow_rate_lpm must be > 0")


# ---------------------------------------------------------------------------
# Single-channel flow analysis
# ---------------------------------------------------------------------------

@dataclass
class ChannelFlowResult:
    """Results of a single-channel flow and heat-transfer calculation."""
    channel_label: str
    reynolds: float
    nusselt: float
    htc_W_m2K: float        # heat-transfer coefficient (W/(m²·K))
    pressure_drop_pa: float # Darcy-Weisbach pressure drop (Pa)
    velocity_m_s: float
    flow_regime: str        # 'laminar', 'transitional', 'turbulent'

    def as_dict(self) -> dict:
        return {
            "channel": self.channel_label,
            "reynolds": round(self.reynolds, 1),
            "nusselt": round(self.nusselt, 2),
            "htc_W_m2K": round(self.htc_W_m2K, 1),
            "pressure_drop_kPa": round(self.pressure_drop_pa / 1000.0, 3),
            "velocity_m_s": round(self.velocity_m_s, 3),
            "flow_regime": self.flow_regime,
        }


def channel_flow(
    ch: CoolingChannel,
    flow_rate_m3_s: float,
    coolant: CoolantProperties = None,
) -> ChannelFlowResult:
    """
    Compute Re, Nu, h, and pressure drop for a single cooling channel.

    Friction factor uses Churchill (1977) correlation (covers all Re regimes):
        f = 8 * [(8/Re)^12 + (A+B)^(-1.5)]^(1/12)
    where A = [-2.457 ln((7/Re)^0.9 + 0.27*ε/D)]^16
          B = (37530/Re)^16
    For smooth pipes (ε → 0), B = 0, A → [−2.457 ln((7/Re)^0.9)]^16.

    Heat transfer uses Dittus-Boelter (turbulent, Re > 10 000):
        Nu = 0.023 · Re^0.8 · Pr^0.4

    For laminar flow (Re < 2300):
        Nu = 3.66  (uniform wall temperature, fully developed)
        or  Nu = 4.36  (uniform heat flux)  — we use 3.66 (conservative).

    For transitional (2300 ≤ Re < 10 000):
        Linear interpolation between laminar and turbulent Nu.

    Reference: Incropera F.P. et al. "Fundamentals of Heat and Mass Transfer",
               7th ed., Wiley 2011, §8.4.

    Parameters
    ----------
    ch            CoolingChannel descriptor.
    flow_rate_m3_s  Volumetric flow rate through THIS channel (m³/s).
    coolant       CoolantProperties (default: water at 25°C).

    Returns
    -------
    ChannelFlowResult
    """
    if coolant is None:
        coolant = CoolantProperties()

    D = ch.hydraulic_diameter_m
    L = ch.length_m
    A = ch.cross_section_area_m2

    if A <= 0.0 or D <= 0.0:
        raise ValueError(f"Channel '{ch.label}': degenerate geometry (D={D}, A={A})")
    if flow_rate_m3_s <= 0.0:
        raise ValueError(f"Channel '{ch.label}': flow_rate_m3_s must be > 0")

    rho = coolant.density_kg_m3
    mu = coolant.dynamic_viscosity_Pa_s
    k = coolant.thermal_conductivity_W_mK
    Pr = coolant.prandtl

    velocity = flow_rate_m3_s / A
    Re = rho * velocity * D / mu

    # Flow regime classification
    if Re < 2300.0:
        regime = "laminar"
    elif Re < 10000.0:
        regime = "transitional"
    else:
        regime = "turbulent"

    # Nusselt number
    if Re < 2300.0:
        Nu = 3.66  # fully developed laminar, constant wall temperature
    elif Re >= 10000.0:
        # Dittus-Boelter (heating coolant, exponent 0.4)
        Nu = 0.023 * (Re ** 0.8) * (Pr ** 0.4)
    else:
        # Transitional: linear interpolation
        Nu_lam = 3.66
        Nu_turb = 0.023 * (10000.0 ** 0.8) * (Pr ** 0.4)
        t = (Re - 2300.0) / (10000.0 - 2300.0)
        Nu = Nu_lam + t * (Nu_turb - Nu_lam)

    htc = Nu * k / D   # W/(m²·K)

    # Friction factor — Churchill (1977) smooth-pipe approximation
    # For smooth pipe: ε/D → 0 → B term ~ 0
    if Re < 1e-9:
        f = 0.0
        dp = 0.0
    else:
        # Churchill smooth pipe
        if Re <= 2300.0:
            f = 64.0 / Re  # Hagen-Poiseuille
        else:
            # Colebrook-White (smooth pipe, iterative not needed: use Filonenko approx)
            # f = 1 / (1.821 · log10(Re) − 1.64)²  (Filonenko, Re > 10^4)
            # Blended with laminar below 10000
            if Re >= 10000.0:
                f = 1.0 / (1.821 * math.log10(Re) - 1.64) ** 2
            else:
                f_lam = 64.0 / 2300.0
                f_turb = 1.0 / (1.821 * math.log10(10000.0) - 1.64) ** 2
                t = (Re - 2300.0) / (10000.0 - 2300.0)
                f = f_lam + t * (f_turb - f_lam)

        # Darcy-Weisbach pressure drop: ΔP = f · (L/D) · ρv²/2
        dp = f * (L / D) * 0.5 * rho * velocity ** 2

    return ChannelFlowResult(
        channel_label=ch.label,
        reynolds=Re,
        nusselt=Nu,
        htc_W_m2K=htc,
        pressure_drop_pa=dp,
        velocity_m_s=velocity,
        flow_regime=regime,
    )


# ---------------------------------------------------------------------------
# Circuit analysis
# ---------------------------------------------------------------------------

@dataclass
class CircuitAnalysisResult:
    """Full thermal analysis of a cooling circuit."""
    layout: str
    total_flow_rate_lpm: float
    channels: List[ChannelFlowResult]
    total_htc_W_m2K: float          # effective overall HTC (area-weighted)
    total_heat_area_m2: float       # total wetted heat-transfer area
    coolant_temp_rise_c: float      # ΔT of coolant through circuit
    total_pressure_drop_kPa: float
    heat_extraction_W: float        # heat extracted per degree of driving ΔT
    warnings: List[str]

    def as_dict(self) -> dict:
        return {
            "layout": self.layout,
            "total_flow_lpm": round(self.total_flow_rate_lpm, 3),
            "channels": [c.as_dict() for c in self.channels],
            "effective_htc_W_m2K": round(self.total_htc_W_m2K, 1),
            "total_area_m2": round(self.total_heat_area_m2, 4),
            "coolant_temp_rise_c": round(self.coolant_temp_rise_c, 3),
            "total_pressure_drop_kPa": round(self.total_pressure_drop_kPa, 3),
            "heat_extraction_per_dT_W": round(self.heat_extraction_W, 1),
            "warnings": self.warnings,
        }


def circuit_analysis(
    circuit: CoolingCircuit,
    mould_surface_temp_c: float = 60.0,
    heat_load_W: float = 0.0,
    coolant: CoolantProperties = None,
) -> CircuitAnalysisResult:
    """
    Perform full thermal analysis of a CoolingCircuit.

    For a SERIES circuit:
      - Each channel receives the full circuit flow rate.
      - Pressure drop is summed across channels.
      - Coolant temperature rises monotonically through the circuit.

    For a PARALLEL circuit:
      - Flow is divided equally between channels (simplified; assumes equal
        resistance — a conservative baseline).
      - Pressure drop equals the single-channel value for one branch.
      - Each channel cools independently.

    The coolant temperature rise (for series) uses Newton's law of cooling
    integrated along the channel:

        Q_per_channel = h · A_ch · (T_mould - T_coolant_mean)

    where T_coolant_mean is approximated as the mean of inlet and outlet
    temperature for that channel.

    Parameters
    ----------
    circuit               CoolingCircuit instance.
    mould_surface_temp_c  Target mould cavity surface temperature (°C).
    heat_load_W           Total heat load from polymer (W).  If 0, only
                          geometry/flow analysis is performed.
    coolant               CoolantProperties (default: water at 25°C).

    Returns
    -------
    CircuitAnalysisResult
    """
    if coolant is None:
        coolant = CoolantProperties()

    warnings: list[str] = []

    # Flow rate per channel
    Q_total_m3_s = circuit.flow_rate_lpm / 60.0 / 1000.0  # L/min → m³/s
    n = len(circuit.channels)

    if circuit.layout == "series":
        Q_per_channel = Q_total_m3_s
    else:  # parallel
        Q_per_channel = Q_total_m3_s / n

    # Analyse each channel
    channel_results: list[ChannelFlowResult] = []
    total_dp_pa = 0.0
    total_area = 0.0
    total_htc_area = 0.0
    T_coolant_in = circuit.coolant_inlet_temp_c
    cumulative_temp = T_coolant_in

    for ch in circuit.channels:
        try:
            res = channel_flow(ch, Q_per_channel, coolant)
        except ValueError as exc:
            warnings.append(f"Channel '{ch.label}': {exc}")
            # Create a dummy result
            res = ChannelFlowResult(
                channel_label=ch.label,
                reynolds=0.0, nusselt=0.0, htc_W_m2K=0.0,
                pressure_drop_pa=0.0, velocity_m_s=0.0,
                flow_regime="unknown",
            )
        channel_results.append(res)

        # Wetted area (cylindrical channel, inside surface)
        A_ch = math.pi * ch.diameter_m * ch.length_m
        total_area += A_ch
        total_htc_area += res.htc_W_m2K * A_ch

        if circuit.layout == "series":
            total_dp_pa += res.pressure_drop_pa
        else:
            total_dp_pa = max(total_dp_pa, res.pressure_drop_pa)  # parallel: max branch

        # Estimate coolant temperature rise (series only, simplified)
        if circuit.layout == "series" and res.htc_W_m2K > 0.0 and Q_per_channel > 0.0:
            # Q = h·A·ΔT_lm ≈ h·A·(T_wall - T_coolant)
            # Energy balance: Q = rho·Q_vol·Cp·ΔT_coolant
            # Iterate: use midpoint temperature
            T_mid = cumulative_temp
            Q_extracted = res.htc_W_m2K * A_ch * max(0.0, mould_surface_temp_c - T_mid)
            m_dot = coolant.density_kg_m3 * Q_per_channel  # kg/s
            dT = Q_extracted / (m_dot * coolant.specific_heat_J_kgK) if m_dot > 0 else 0.0
            cumulative_temp += dT

        if res.flow_regime == "laminar":
            warnings.append(
                f"Channel '{ch.label}': Re={res.reynolds:.0f} — laminar flow. "
                f"Turbulent flow (Re > 10 000) is recommended for efficient mould cooling. "
                f"Increase flow rate or reduce channel diameter."
            )

    # Effective (area-weighted mean) HTC
    eff_htc = total_htc_area / total_area if total_area > 0.0 else 0.0

    # Coolant temperature rise
    if circuit.layout == "series":
        coolant_temp_rise = cumulative_temp - circuit.coolant_inlet_temp_c
    else:
        # Parallel: temp rise is for a single branch
        if len(channel_results) > 0 and total_area > 0.0:
            A_branch = math.pi * circuit.channels[0].diameter_m * circuit.channels[0].length_m
            T_mid = circuit.coolant_inlet_temp_c
            Q_branch = channel_results[0].htc_W_m2K * A_branch * max(0.0, mould_surface_temp_c - T_mid)
            m_dot_branch = coolant.density_kg_m3 * Q_per_channel
            coolant_temp_rise = Q_branch / (m_dot_branch * coolant.specific_heat_J_kgK) if m_dot_branch > 0 else 0.0
        else:
            coolant_temp_rise = 0.0

    # Heat extraction capacity per degree of driving ΔT
    # Q_total = h_eff · A_total · ΔT → Q per degree = h_eff · A_total
    heat_per_dT = eff_htc * total_area

    return CircuitAnalysisResult(
        layout=circuit.layout,
        total_flow_rate_lpm=circuit.flow_rate_lpm,
        channels=channel_results,
        total_htc_W_m2K=eff_htc,
        total_heat_area_m2=total_area,
        coolant_temp_rise_c=coolant_temp_rise,
        total_pressure_drop_kPa=total_dp_pa / 1000.0,
        heat_extraction_W=heat_per_dT,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Cooling time estimate — Janeschitz-Kriegl model
# ---------------------------------------------------------------------------

@dataclass
class CoolingTimeResult:
    """Result of mould cooling time calculation."""
    cooling_time_s: float
    wall_thickness_mm: float
    polymer: str
    melt_temp_c: float
    mould_temp_c: float
    ejection_temp_c: float
    thermal_diffusivity_m2_s: float
    warnings: List[str]

    def as_dict(self) -> dict:
        return {
            "cooling_time_s": round(self.cooling_time_s, 2),
            "wall_thickness_mm": self.wall_thickness_mm,
            "polymer": self.polymer,
            "melt_temp_c": self.melt_temp_c,
            "mould_temp_c": self.mould_temp_c,
            "ejection_temp_c": self.ejection_temp_c,
            "thermal_diffusivity_m2_s": self.thermal_diffusivity_m2_s,
            "warnings": self.warnings,
        }


def cooling_time(
    wall_thickness_mm: float,
    melt_temp_c: float,
    mould_temp_c: float,
    ejection_temp_c: float,
    polymer: str = "PP",
    thermal_diffusivity_m2_s: Optional[float] = None,
) -> CoolingTimeResult:
    """
    Estimate mould cooling time using the Janeschitz-Kriegl squeezing model.

    The classic approximation for a flat part cooled symmetrically:

        t_cool = (s² / (π² · a)) · ln(4/π · (T_melt - T_mould) / (T_eject - T_mould))

    where
      s    = nominal wall thickness (m)  — half-thickness of the part
      a    = thermal diffusivity of polymer (m²/s)
      T_melt   = melt injection temperature (°C)
      T_mould  = average mould wall temperature (°C)
      T_eject  = target centreline temperature at ejection (°C)

    This formula is valid for:
      - One-sided cooling: replace s with full wall thickness
      - Two-sided cooling: s is the half-thickness
    We use HALF the wall thickness (two-sided cooling) as the default.

    Reference: Menges G., Michaeli W., Mohren P. "How to Make Injection Molds",
      3rd ed., Hanser 2001, §9.4.2 equation (9.13).

    Parameters
    ----------
    wall_thickness_mm       Nominal part wall thickness (mm).
    melt_temp_c             Melt injection temperature (°C).
    mould_temp_c            Mould wall temperature (°C).
    ejection_temp_c         Target part centreline temperature at ejection (°C).
    polymer                 Polymer name (key in POLYMER_THERMAL_DIFFUSIVITY).
    thermal_diffusivity_m2_s  Override thermal diffusivity (m²/s). If None,
                            uses the POLYMER_THERMAL_DIFFUSIVITY table.

    Returns
    -------
    CoolingTimeResult
    """
    warnings: list[str] = []

    if thermal_diffusivity_m2_s is None:
        poly_key = polymer.upper()
        if poly_key not in POLYMER_THERMAL_DIFFUSIVITY:
            available = sorted(POLYMER_THERMAL_DIFFUSIVITY.keys())
            warnings.append(
                f"Polymer '{polymer}' not in library; defaulting to PP. "
                f"Available: {available}"
            )
            poly_key = "PP"
        a = POLYMER_THERMAL_DIFFUSIVITY[poly_key]
    else:
        a = float(thermal_diffusivity_m2_s)

    # Half wall thickness (two-sided cooling) in metres
    s = (wall_thickness_mm * 1e-3) / 2.0

    delta_T_melt = melt_temp_c - mould_temp_c
    delta_T_eject = ejection_temp_c - mould_temp_c

    if delta_T_melt <= 0.0:
        return CoolingTimeResult(
            cooling_time_s=0.0,
            wall_thickness_mm=wall_thickness_mm,
            polymer=polymer,
            melt_temp_c=melt_temp_c,
            mould_temp_c=mould_temp_c,
            ejection_temp_c=ejection_temp_c,
            thermal_diffusivity_m2_s=a,
            warnings=["melt_temp_c must be > mould_temp_c; returning 0"],
        )

    if delta_T_eject <= 0.0:
        warnings.append(
            "ejection_temp_c <= mould_temp_c; part would never cool to ejection temp — "
            "returning a large cooling time estimate"
        )
        delta_T_eject = 1.0  # avoid log(0)

    if delta_T_eject >= delta_T_melt:
        warnings.append(
            "ejection_temp_c >= melt_temp_c — ejection temperature should be below "
            "melt temperature. Check inputs."
        )

    # Janeschitz-Kriegl formula
    ratio = (4.0 / math.pi) * (delta_T_melt / delta_T_eject)
    if ratio <= 0.0:
        t_cool = 0.0
    else:
        t_cool = (s ** 2 / (math.pi ** 2 * a)) * math.log(ratio)

    if t_cool < 0.0:
        t_cool = 0.0
        warnings.append("Negative cooling time computed; check temperature inputs.")

    return CoolingTimeResult(
        cooling_time_s=t_cool,
        wall_thickness_mm=wall_thickness_mm,
        polymer=polymer,
        melt_temp_c=melt_temp_c,
        mould_temp_c=mould_temp_c,
        ejection_temp_c=ejection_temp_c,
        thermal_diffusivity_m2_s=a,
        warnings=warnings,
    )
