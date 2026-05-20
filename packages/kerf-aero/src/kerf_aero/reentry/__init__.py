"""kerf_aero.reentry — Re-entry heat-shield / ablation analysis."""

from kerf_aero.reentry.materials import (
    MaterialProperties,
    PICA,
    LI_900,
    AVCOAT,
    CARBON_CARBON,
    SLA_561V,
    AL_2024,
    CATALOGUE,
)
from kerf_aero.reentry.tps_stack import StackLayer, TPSStack, stardust_pica_stack
from kerf_aero.reentry.ablation import (
    AblationResult,
    solve,
    analytic_semiinfinite_surface_temperature,
    analytic_semiinfinite_temperature_profile,
)
from kerf_aero.reentry.heat_flux_trajectory import (
    sutton_graves_heat_flux,
    total_heat_flux,
    stardust_src_flux_profile,
    constant_flux_profile,
)

__all__ = [
    "MaterialProperties",
    "PICA",
    "LI_900",
    "AVCOAT",
    "CARBON_CARBON",
    "SLA_561V",
    "AL_2024",
    "CATALOGUE",
    "StackLayer",
    "TPSStack",
    "stardust_pica_stack",
    "AblationResult",
    "solve",
    "analytic_semiinfinite_surface_temperature",
    "analytic_semiinfinite_temperature_profile",
    "sutton_graves_heat_flux",
    "total_heat_flux",
    "stardust_src_flux_profile",
    "constant_flux_profile",
]
