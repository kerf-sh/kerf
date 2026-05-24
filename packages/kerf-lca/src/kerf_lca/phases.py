"""
ISO 14040/44 lifecycle phase calculators — Phases 2, 3, 4 and full summary.

Phase 1 (cradle-to-gate embodied carbon) is handled by report.lca_report.

References:
  - Transport emission factors: EcoTransIT World / GLEC Framework v2.
  - Grid emission factors: IEA Electricity Information 2023 + EPA eGrid (US).
  - ISO 14067:2018 (product carbon footprint).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Per-region grid emission factors  (kg CO₂-eq / kWh)   [ISO 14067-aligned]
# ---------------------------------------------------------------------------

GRID_FACTORS: dict[str, float] = {
    "US": 0.386,   # EPA eGrid 2022 national average
    "EU": 0.233,   # IEA Europe 2022 average
    "CN": 0.581,   # IEA China 2022
    "ZA": 0.900,   # Eskom grid intensity 2023 (coal-heavy)
    "IN": 0.708,   # IEA India 2022
    "AU": 0.510,   # IEA Australia 2022
    "GB": 0.193,   # DESNZ 2023
    "DE": 0.365,   # UBA Germany 2022
    "FR": 0.052,   # IEA France 2022 (nuclear-heavy)
    "WORLD": 0.475,  # IEA global average 2022
}

# ---------------------------------------------------------------------------
# Transport emission factors  (kg CO₂-eq / tonne·km)
# Source: EcoTransIT World / GLEC Framework v2
# ---------------------------------------------------------------------------

TRANSPORT_FACTORS: dict[str, float] = {
    "truck": 0.10,   # average road freight
    "rail": 0.030,   # average rail freight
    "sea": 0.015,    # average container shipping
    "air": 0.85,     # air freight (belly + freighter average)
}


# ---------------------------------------------------------------------------
# End-of-life scenarios
# ---------------------------------------------------------------------------

# Incineration energy recovery credit: avoided grid electricity (kg CO₂-eq/kg)
# Typical municipal waste incineration: ~0.10 kWh/kg generated → grid credit
_INCINERATION_ENERGY_CREDIT_KWH_PER_KG = 0.5   # conservative net electrical output
_INCINERATION_PROCESS_KG_CO2_PER_KG = 0.05     # transport + sorting to WtE plant

# Landfill: negligible direct CO₂ from non-organics; small transport factor
_LANDFILL_PROCESS_KG_CO2_PER_KG = 0.025

# Recyclability credit: avoided virgin-material production (50:50 allocation default)
# These are fraction of cradle-to-gate GWP credited back (cut-off or 50:50)
_RECYCLE_ALLOCATION_FACTOR = 0.50   # 50:50 default; 0 = cut-off method


@dataclass
class PhaseResult:
    """Impact from a single lifecycle phase, per impact category."""
    phase: str
    gwp_kg_co2_eq: float
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "phase": self.phase,
            "gwp_kg_co2_eq": round(self.gwp_kg_co2_eq, 6),
            **{k: v for k, v in self.metadata.items()},
        }


@dataclass
class LifecycleSummary:
    """Full lifecycle impact across all four phases."""
    product: str
    functional_unit: str
    phases: list[PhaseResult] = field(default_factory=list)
    total_gwp_kg_co2_eq: float = 0.0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "product": self.product,
            "functional_unit": self.functional_unit,
            "total_gwp_kg_co2_eq": round(self.total_gwp_kg_co2_eq, 6),
            "phases": [p.to_dict() for p in self.phases],
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Phase 2: Use-phase energy
# ---------------------------------------------------------------------------

def use_phase_impact(
    product: str,
    lifetime_years: float,
    annual_energy_kWh: float,
    *,
    grid_emission_factor_kgCO2_per_kWh: float | None = None,
    region: str = "WORLD",
) -> PhaseResult:
    """
    Compute use-phase GWP (Phase B6 / Module B6 per EN 15978).

    Args:
        product: descriptive product name.
        lifetime_years: reference service life in years.
        annual_energy_kWh: operational energy per year (kWh/yr).
        grid_emission_factor_kgCO2_per_kWh: override grid factor (kg CO₂-eq/kWh).
            If None, looked up from GRID_FACTORS by *region*.
        region: ISO 3166-1 alpha-2 or custom key from GRID_FACTORS
            (US / EU / CN / ZA / IN / AU / GB / DE / FR / WORLD).

    Returns:
        PhaseResult with gwp_kg_co2_eq = lifetime energy × grid factor.
    """
    if grid_emission_factor_kgCO2_per_kWh is None:
        ef = GRID_FACTORS.get(region.upper())
        if ef is None:
            ef = GRID_FACTORS["WORLD"]
        effective_region = region.upper()
    else:
        ef = grid_emission_factor_kgCO2_per_kWh
        effective_region = "custom"

    total_energy_kWh = annual_energy_kWh * lifetime_years
    gwp = total_energy_kWh * ef

    return PhaseResult(
        phase="use",
        gwp_kg_co2_eq=gwp,
        metadata={
            "product": product,
            "lifetime_years": lifetime_years,
            "annual_energy_kWh": annual_energy_kWh,
            "total_energy_kWh": total_energy_kWh,
            "grid_emission_factor_kgCO2_per_kWh": ef,
            "region": effective_region,
        },
    )


# ---------------------------------------------------------------------------
# Phase 3: Transport
# ---------------------------------------------------------------------------

def transport_impact(
    mass_kg: float,
    distance_km: float,
    mode: str = "truck",
) -> PhaseResult:
    """
    Compute transport-phase GWP (Module A4/C2 per EN 15978).

    Args:
        mass_kg: mass of goods transported (kg).
        distance_km: one-way transport distance (km).
        mode: 'truck' | 'rail' | 'sea' | 'air'.

    Returns:
        PhaseResult with gwp_kg_co2_eq = (mass_kg/1000) × distance_km × factor.

    Emission factors (kg CO₂-eq / tonne·km):
        truck: 0.10   (GLEC road freight)
        rail:  0.030  (GLEC rail freight)
        sea:   0.015  (GLEC container shipping)
        air:   0.85   (GLEC air freight)
    """
    mode_key = mode.strip().lower()
    factor = TRANSPORT_FACTORS.get(mode_key)
    if factor is None:
        raise ValueError(
            f"Unknown transport mode '{mode}'. "
            f"Valid modes: {list(TRANSPORT_FACTORS)}"
        )

    mass_tonnes = mass_kg / 1000.0
    gwp = mass_tonnes * distance_km * factor

    return PhaseResult(
        phase="transport",
        gwp_kg_co2_eq=gwp,
        metadata={
            "mass_kg": mass_kg,
            "distance_km": distance_km,
            "mode": mode_key,
            "emission_factor_kgCO2_per_tonne_km": factor,
        },
    )


# ---------------------------------------------------------------------------
# Phase 4: End-of-life
# ---------------------------------------------------------------------------

def eol_impact(
    product: str,
    mass_kg: float,
    scenario: str,
    *,
    material_gwp_factor: float = 0.0,
    recycle_allocation: float = _RECYCLE_ALLOCATION_FACTOR,
    grid_region: str = "WORLD",
) -> PhaseResult:
    """
    Compute end-of-life GWP (Module C3/C4/D per EN 15978).

    Scenarios:
        landfill     — small transport + burial; no credits.
        incinerate   — waste-to-energy; grid credit for recovered electricity.
        recycle      — avoided virgin production; credit by allocation method.

    Args:
        product: descriptive product name.
        mass_kg: mass to be disposed (kg).
        scenario: 'landfill' | 'incinerate' | 'recycle'.
        material_gwp_factor: cradle-to-gate GWP of the material (kg CO₂-eq/kg).
            Required for 'recycle' scenario to compute avoided-burden credit.
        recycle_allocation: fraction of avoided burden credited (0–1).
            0 = cut-off method (no credit), 0.5 = 50:50 allocation (default).
        grid_region: region key for electricity credit in incineration.

    Returns:
        PhaseResult. gwp_kg_co2_eq is negative when credits exceed impacts.
    """
    s = scenario.strip().lower()

    if s == "landfill":
        gwp = mass_kg * _LANDFILL_PROCESS_KG_CO2_PER_KG
        meta = {"scenario": "landfill", "process_factor_kgCO2_per_kg": _LANDFILL_PROCESS_KG_CO2_PER_KG}

    elif s == "incinerate":
        process_co2 = mass_kg * _INCINERATION_PROCESS_KG_CO2_PER_KG
        grid_ef = GRID_FACTORS.get(grid_region.upper(), GRID_FACTORS["WORLD"])
        energy_kWh = mass_kg * _INCINERATION_ENERGY_CREDIT_KWH_PER_KG
        credit = energy_kWh * grid_ef  # avoided grid electricity (negative impact)
        gwp = process_co2 - credit
        meta = {
            "scenario": "incinerate",
            "process_co2_kg": process_co2,
            "recovered_energy_kWh": energy_kWh,
            "grid_credit_kgCO2": credit,
            "net_gwp_kgCO2": gwp,
        }

    elif s == "recycle":
        process_co2 = mass_kg * 0.02  # collection + sorting transport
        avoided_burden = material_gwp_factor * mass_kg * recycle_allocation
        gwp = process_co2 - avoided_burden
        meta = {
            "scenario": "recycle",
            "allocation_method": f"{recycle_allocation*100:.0f}:50",
            "process_co2_kg": process_co2,
            "avoided_virgin_credit_kgCO2": avoided_burden,
            "net_gwp_kgCO2": gwp,
        }

    else:
        raise ValueError(
            f"Unknown EoL scenario '{scenario}'. "
            "Valid: 'landfill', 'incinerate', 'recycle'."
        )

    return PhaseResult(
        phase="end_of_life",
        gwp_kg_co2_eq=gwp,
        metadata={"product": product, "mass_kg": mass_kg, **meta},
    )


# ---------------------------------------------------------------------------
# Full lifecycle summary
# ---------------------------------------------------------------------------

def lifecycle_summary(
    product: str,
    *,
    cradle_to_gate_gwp: float = 0.0,
    use_args: dict | None = None,
    transport_args: dict | None = None,
    eol_args: dict | None = None,
    functional_unit: str = "1 unit",
) -> LifecycleSummary:
    """
    Sum all lifecycle phases and return a LifecycleSummary.

    Args:
        product: product name.
        cradle_to_gate_gwp: Phase 1 GWP from lca_report (kg CO₂-eq).
        use_args: kwargs for use_phase_impact (excluding 'product').
            Required keys: lifetime_years, annual_energy_kWh.
        transport_args: kwargs for transport_impact.
            Required keys: mass_kg, distance_km, mode.
        eol_args: kwargs for eol_impact (excluding 'product').
            Required keys: mass_kg, scenario.
        functional_unit: human-readable FU declaration.

    Returns:
        LifecycleSummary with all phases and total GWP.
    """
    phases: list[PhaseResult] = []
    warnings: list[str] = []
    total = 0.0

    # Phase 1
    if cradle_to_gate_gwp != 0.0:
        p1 = PhaseResult(
            phase="cradle_to_gate",
            gwp_kg_co2_eq=cradle_to_gate_gwp,
            metadata={"note": "embodied carbon from ICE v3 / lca_report"},
        )
        phases.append(p1)
        total += p1.gwp_kg_co2_eq

    # Phase 2 (use)
    if use_args is not None:
        try:
            p2 = use_phase_impact(product, **use_args)
            phases.append(p2)
            total += p2.gwp_kg_co2_eq
        except Exception as e:
            warnings.append(f"use_phase_impact failed: {e}")

    # Phase 3 (transport)
    if transport_args is not None:
        try:
            p3 = transport_impact(**transport_args)
            phases.append(p3)
            total += p3.gwp_kg_co2_eq
        except Exception as e:
            warnings.append(f"transport_impact failed: {e}")

    # Phase 4 (EoL)
    if eol_args is not None:
        try:
            p4 = eol_impact(product, **eol_args)
            phases.append(p4)
            total += p4.gwp_kg_co2_eq
        except Exception as e:
            warnings.append(f"eol_impact failed: {e}")

    return LifecycleSummary(
        product=product,
        functional_unit=functional_unit,
        phases=phases,
        total_gwp_kg_co2_eq=total,
        warnings=warnings,
    )
