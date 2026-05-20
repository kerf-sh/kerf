"""
kerf_aero.reentry.materials — Thermal-protection-system material catalogue.

All properties are representative engineering values at moderate temperatures
(300 K reference).  Temperature-dependent tables are provided as piecewise-
linear functions of temperature in Kelvin.

References
----------
- PICA: Milos & Chen, "Two-Dimensional Ablation, Thermal Response, and
  Sizing Program for Pyrolyzing Ablators", JSR 2009.
- LI-900: NASA TM-58237 (Space Shuttle tile properties).
- AVCOAT: Apollo heat-shield documentation; Kendall et al. JSR 1967.
- Carbon–Carbon: CINDAS handbook values.
- SLA-561V: MSL entry aerothermodynamics, Chen 2014.
"""

from __future__ import annotations

import math
from typing import NamedTuple


class MaterialProperties(NamedTuple):
    """Isotropic ablator / TPS material properties.

    Parameters
    ----------
    name : str
        Human-readable identifier.
    rho_virgin : float
        Virgin-material density [kg/m³].
    rho_char : float
        Fully-charred density [kg/m³].  Set equal to rho_virgin for
        non-ablating structural materials.
    cp : float
        Specific heat [J/(kg·K)] — representative value.
    k : float
        Thermal conductivity [W/(m·K)] — representative value.
    h_ablation : float
        Effective heat of ablation [J/kg].  Energy absorbed per unit mass
        of material removed from the surface (pyrolysis + phase change).
        Set to 0 for non-ablating materials.
    T_ablation : float
        Surface ablation temperature [K] — surface is held at this value
        while ablation is occurring.
    emissivity : float
        Total hemispherical emissivity (0–1).
    """

    name: str
    rho_virgin: float   # kg/m³
    rho_char: float     # kg/m³
    cp: float           # J/(kg·K)
    k: float            # W/(m·K)
    h_ablation: float   # J/kg
    T_ablation: float   # K
    emissivity: float   # dimensionless


# ---------------------------------------------------------------------------
# Material catalogue
# ---------------------------------------------------------------------------

#: Phenolic-Impregnated Carbon Ablator (PICA / PICA-X).
#: Used on Stardust SRC, Dragon capsule.
PICA = MaterialProperties(
    name="PICA",
    rho_virgin=270.0,       # kg/m³  (PICA nominal ~240–280 kg/m³)
    rho_char=130.0,         # kg/m³
    cp=1200.0,              # J/(kg·K)  (increases with T; 1200 is ~700–1200 K mean)
    k=0.35,                 # W/(m·K)  (through-thickness; ~0.25 char, ~0.45 virgin)
    h_ablation=250.0e6,     # J/kg   (effective heat of ablation incl. pyrolysis + transpiration
                            #         cooling; arc-jet validated range 200–400 MJ/kg for PICA)
    T_ablation=2700.0,      # K      (char-surface equilibrium temperature during ablation,
                            #         from Stardust SRC / PICA-X arc-jet measurements)
    emissivity=0.85,
)

#: LI-900 silica foam tile — Space Shuttle Orbiter belly tile.
#: Non-ablating (ceramic tile; h_ablation=0).
LI_900 = MaterialProperties(
    name="LI-900",
    rho_virgin=144.0,       # kg/m³
    rho_char=144.0,         # non-ablating
    cp=628.0,               # J/(kg·K)
    k=0.058,                # W/(m·K)  (low-k insulator)
    h_ablation=0.0,
    T_ablation=1922.0,      # K  (max use temperature)
    emissivity=0.85,
)

#: AVCOAT — Apollo and Orion heat-shield ablator.
AVCOAT = MaterialProperties(
    name="AVCOAT",
    rho_virgin=510.0,       # kg/m³
    rho_char=230.0,         # kg/m³
    cp=1300.0,              # J/(kg·K)
    k=0.26,                 # W/(m·K)
    h_ablation=15.0e6,      # J/kg
    T_ablation=3000.0,      # K
    emissivity=0.90,
)

#: Carbon–Carbon (2-D woven composite) — nose cap / leading edges.
#: Sublimation ablation at very high temperatures.
CARBON_CARBON = MaterialProperties(
    name="Carbon-Carbon",
    rho_virgin=1650.0,      # kg/m³
    rho_char=1500.0,        # kg/m³  (minimal charring, mainly oxidation / sublimation)
    cp=750.0,               # J/(kg·K)
    k=25.0,                 # W/(m·K)  (in-plane; through-thickness ~5 W/(m·K))
    h_ablation=59.0e6,      # J/kg   (carbon sublimation enthalpy)
    T_ablation=3800.0,      # K
    emissivity=0.85,
)

#: SLA-561V — Mars entry ablator (Viking, Pathfinder, MER, MSL, InSight).
SLA_561V = MaterialProperties(
    name="SLA-561V",
    rho_virgin=256.0,       # kg/m³
    rho_char=140.0,         # kg/m³
    cp=1100.0,              # J/(kg·K)
    k=0.24,                 # W/(m·K)
    h_ablation=8.0e6,       # J/kg  (lower flux Mars entry)
    T_ablation=2600.0,      # K
    emissivity=0.88,
)

#: Aluminum alloy 2024-T3 — structural substrate (non-ablating).
AL_2024 = MaterialProperties(
    name="Al-2024",
    rho_virgin=2780.0,
    rho_char=2780.0,
    cp=875.0,
    k=121.0,
    h_ablation=0.0,
    T_ablation=923.0,       # K  (melt onset)
    emissivity=0.10,
)

#: Public catalogue dict keyed by name.
CATALOGUE: dict[str, MaterialProperties] = {
    m.name: m
    for m in (PICA, LI_900, AVCOAT, CARBON_CARBON, SLA_561V, AL_2024)
}
