# kerf-electronics EMC/EMI pre-compliance sub-package.
# Public API is re-exported from estimate.py.
from kerf_electronics.emc.estimate import (
    radiated_emission_differential,
    radiated_emission_common_mode,
    fcc_limit_dbuvm,
    cispr_limit_dbuvm,
    emission_margin_db,
    near_field_crosstalk,
    shielding_effectiveness,
)

__all__ = [
    "radiated_emission_differential",
    "radiated_emission_common_mode",
    "fcc_limit_dbuvm",
    "cispr_limit_dbuvm",
    "emission_margin_db",
    "near_field_crosstalk",
    "shielding_effectiveness",
]
