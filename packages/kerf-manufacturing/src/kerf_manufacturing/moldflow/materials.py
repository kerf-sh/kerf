"""Cross-WLF viscosity model and common material cards.

The Cross-WLF model (Williams-Landel-Ferry shear-thinning) is the
industry-standard viscosity formulation used in Moldflow / Moldex3D:

    eta(T, gamma_dot) = eta_0(T) / (1 + (eta_0 * gamma_dot / tau_star) ^ (1 - n))

where

    eta_0(T) = D1 * exp( -A1*(T - T_star) / (A2 + (T - T_star)) )
    T_star    = D2 + D3 * P          (transition temperature)

All temperatures in Kelvin, pressures in Pa, viscosity in Pa·s,
shear rate in 1/s.

References
----------
C.L. Tucker III, "Fundamentals of Computer Modeling for Polymer Processing",
Hanser, 1989.

Follow-up (v2):
  * Pressure-dependence coefficient D3 active in T_star calculation
  * PVT (pvT) model coupling for density
  * Fibre-filled suspension viscosity (Dinh-Armstrong)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CrossWLFCard:
    """Cross-WLF viscosity parameters for a single polymer grade.

    Parameters
    ----------
    name : str
        Human-readable material name (e.g. "ABS Magnum 3325").
    n : float
        Power-law index (dimensionless, 0 < n <= 1).
        n=1 → Newtonian; typical injection-moulding grades: 0.2–0.4.
    tau_star : float
        Critical shear stress at transition from Newtonian to shear-thinning
        (Pa).  Typical range: 1e4–2e5 Pa.
    D1 : float
        Pre-exponential viscosity factor (Pa·s).
    D2 : float
        Reference temperature for WLF shift (K).  Often ~ Tg or Tm.
    D3 : float
        Pressure sensitivity coefficient (K/Pa).  Set to 0 to ignore pressure
        dependence (valid for many amorphous grades at moderate pressure).
    A1 : float
        WLF coefficient A1 (dimensionless).  Typical: 20–30.
    A2 : float
        WLF coefficient A2 (K).  Typical: 50–100 K.
    Cp : float
        Specific heat capacity (J/kg/K).  Used by thermal solver (v2).
    kappa : float
        Thermal conductivity (W/m/K).  Used by thermal solver (v2).
    rho : float
        Melt density at processing temperature (kg/m³).

    Notes
    -----
    v1 uses an *isothermal* Hele-Shaw approximation so Cp and kappa are
    stored but not consumed by the fill solver.  They will be used in the
    v2 non-isothermal extension.
    """

    name: str = "Generic ABS"
    n: float = 0.26
    tau_star: float = 3.0e4       # Pa
    D1: float = 3.08e12           # Pa·s  (ABS-like)
    D2: float = 373.15            # K  (100 °C)
    D3: float = 0.0               # K/Pa
    A1: float = 23.0
    A2: float = 67.0              # K
    Cp: float = 1800.0            # J/kg/K
    kappa: float = 0.17           # W/m/K
    rho: float = 1050.0           # kg/m³

    def eta0(self, T_K: float, P_Pa: float = 0.0) -> float:
        """Zero-shear viscosity at temperature T_K (Kelvin) and pressure P_Pa.

        Returns viscosity in Pa·s.  Clips the WLF exponent to avoid overflow.
        """
        T_star = self.D2 + self.D3 * P_Pa
        dT = T_K - T_star
        if dT <= 0.0:
            # Below glass/melt transition — viscosity effectively infinite
            return float("inf")
        exponent = -self.A1 * dT / (self.A2 + dT)
        # Clip to avoid exp overflow / underflow
        exponent = max(-500.0, min(500.0, exponent))
        return self.D1 * math.exp(exponent)

    def viscosity(self, T_K: float, gamma_dot: float, P_Pa: float = 0.0) -> float:
        """Apparent viscosity at temperature T_K, shear rate gamma_dot (1/s).

        Returns viscosity in Pa·s.
        """
        e0 = self.eta0(T_K, P_Pa)
        if e0 == float("inf"):
            return float("inf")
        if gamma_dot <= 0.0:
            return e0
        return e0 / (1.0 + (e0 * gamma_dot / self.tau_star) ** (1.0 - self.n))


# ---------------------------------------------------------------------------
# Built-in material cards (representative, not certified for production use)
# ---------------------------------------------------------------------------

#: Generic ABS (Acrylonitrile Butadiene Styrene) — amorphous, Tg ≈ 105 °C
ABS_GENERIC = CrossWLFCard(
    name="ABS Generic",
    n=0.26,
    tau_star=3.0e4,
    D1=3.08e12,
    D2=373.15,
    D3=0.0,
    A1=23.0,
    A2=67.0,
    Cp=1800.0,
    kappa=0.17,
    rho=1050.0,
)

#: Generic PP (Polypropylene, isotactic) — semi-crystalline, Tm ≈ 165 °C
PP_GENERIC = CrossWLFCard(
    name="PP Generic",
    n=0.35,
    tau_star=1.4e4,
    D1=1.60e11,
    D2=428.15,    # 155 °C
    D3=0.0,
    A1=20.4,
    A2=51.6,
    Cp=2000.0,
    kappa=0.20,
    rho=900.0,
)

#: Generic PA6 (Nylon 6) — semi-crystalline, Tm ≈ 220 °C
PA6_GENERIC = CrossWLFCard(
    name="PA6 Generic",
    n=0.28,
    tau_star=2.5e4,
    D1=4.50e12,
    D2=493.15,    # 220 °C
    D3=0.0,
    A1=24.5,
    A2=51.6,
    Cp=1670.0,
    kappa=0.23,
    rho=1130.0,
)

MATERIAL_LIBRARY: dict[str, CrossWLFCard] = {
    "ABS": ABS_GENERIC,
    "PP": PP_GENERIC,
    "PA6": PA6_GENERIC,
}
