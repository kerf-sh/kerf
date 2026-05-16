"""
kerf_cad_core.lubrication — tribology & fluid-film bearing design.

Public API (re-exported for convenience):

    from kerf_cad_core.lubrication import (
        sommerfeld_number,
        journal_bearing_raimondi_boyd,
        petroff_friction,
        temperature_rise,
        viscosity_walther,
        viscosity_barus,
        ehl_film_line,
        ehl_film_point,
        thrust_pad_fixed_incline,
        specific_load,
        lambda_ratio,
        lubrication_regime,
    )

Distinct from ``bearings/`` (rolling-element L10 life) and ``shaft/`` (sizing).
This module covers fluid-film (hydrodynamic / EHL) lubrication physics.

References
----------
Shigley's Mechanical Engineering Design, 10th ed., Ch. 12
Hamrock, Schmid & Jacobson, Fundamentals of Fluid Film Lubrication, 2nd ed.
Raimondi & Boyd, Trans. ASLE 1958 (journal bearing charts)
Dowson & Higginson, Elasto-Hydrodynamic Lubrication, 1977
ASTM D341 — Viscosity-Temperature Charts for Liquid Petroleum Products

Author: imranparuk
"""

from kerf_cad_core.lubrication.film import (
    sommerfeld_number,
    journal_bearing_raimondi_boyd,
    petroff_friction,
    temperature_rise,
    viscosity_walther,
    viscosity_barus,
    ehl_film_line,
    ehl_film_point,
    thrust_pad_fixed_incline,
    specific_load,
    lambda_ratio,
    lubrication_regime,
)

__all__ = [
    "sommerfeld_number",
    "journal_bearing_raimondi_boyd",
    "petroff_friction",
    "temperature_rise",
    "viscosity_walther",
    "viscosity_barus",
    "ehl_film_line",
    "ehl_film_point",
    "thrust_pad_fixed_incline",
    "specific_load",
    "lambda_ratio",
    "lubrication_regime",
]
