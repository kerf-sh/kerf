"""kerf-horology — watchmaking / horology plugin for Kerf.

Thin wrapper around the ``kerf_partsgen.generators.horology`` sub-package
that exposes LLM-callable tools for:

  * Swiss lever escapement geometry (escape wheel + pallet fork)
  * Gear-train wheel and pinion geometry
  * Mainspring barrel geometry
  * ``train_calculator`` — given target frequency + power reserve, computes
    the required gear-train ratio and a factored wheel/pinion solution

Extended physics modules (new):

  * ``escapement`` — Swiss-lever geometry: draw angle, lift, drop, impulse
  * ``mainspring`` — Mainspring torque model + power-reserve calculation
  * ``balance``    — Balance-wheel period, beat rate, isochronism check

Public re-exports
-----------------
From ``kerf_partsgen.generators.horology``:

  involute_profile(module, num_teeth, pressure_angle_deg, n_points)
      → list[ProfilePoint]

  check_involute_profile(module, num_teeth, ...) → InvoluteCheckResult

From ``kerf_partsgen.generators.horology.train_calculator``:

  compute_train_ratio(freq_hz, power_reserve_hours, ...) → TrainSpec
  factorise_ratio(ratio, n_stages, ...)                   → list[TrainStage]

From ``kerf_horology.escapement``:

  swiss_lever_geometry(...) → SwissLeverGeometry

From ``kerf_horology.mainspring``:

  mainspring_torque(turns, full_turns, max_torque_Nmm, ...) → float
  power_reserve_hours(...) → float

From ``kerf_horology.balance``:

  balance_period(I_balance_gmm2, k_hairspring_Nmmrad) → float
  beats_per_hour(period_seconds) → float
  isochronism_check(...) → IsochronismResult
  hairspring_stiffness(bph, I_balance_gmm2) → float

See ``llm_docs/horology.md`` for LLM tool documentation.
"""

__version__ = "0.1.0"

from kerf_partsgen.generators.horology.involute import (  # noqa: F401
    involute_profile,
    check_involute_profile,
    InvoluteCheckResult,
    ProfilePoint,
)
from kerf_partsgen.generators.horology.train_calculator import (  # noqa: F401
    compute_train_ratio,
    factorise_ratio,
    TrainSpec,
    TrainStage,
)
from kerf_horology.escapement import (  # noqa: F401
    swiss_lever_geometry,
    SwissLeverGeometry,
)
from kerf_horology.mainspring import (  # noqa: F401
    mainspring_torque,
    power_reserve_hours,
)
from kerf_horology.balance import (  # noqa: F401
    balance_period,
    beats_per_hour,
    period_from_bph,
    isochronism_check,
    hairspring_stiffness,
    IsochronismResult,
)

__all__ = [
    "__version__",
    # involute / gear train
    "involute_profile",
    "check_involute_profile",
    "InvoluteCheckResult",
    "ProfilePoint",
    "compute_train_ratio",
    "factorise_ratio",
    "TrainSpec",
    "TrainStage",
    # escapement
    "swiss_lever_geometry",
    "SwissLeverGeometry",
    # mainspring
    "mainspring_torque",
    "power_reserve_hours",
    # balance
    "balance_period",
    "beats_per_hour",
    "period_from_bph",
    "isochronism_check",
    "hairspring_stiffness",
    "IsochronismResult",
]
