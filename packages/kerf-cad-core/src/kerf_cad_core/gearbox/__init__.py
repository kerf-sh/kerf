"""
kerf_cad_core.gearbox — Gear-train / gearbox assembly.

Public surface
--------------
train.design_gearbox(stages, input_rpm, input_torque) -> dict
train.gearbox_ratio(stages)                           -> dict
train.gearbox_shaft_table(stages, input_rpm, torque)  -> dict

tools.*  — LLM tool runners registered via @register

Author: imranparuk
"""

from kerf_cad_core.gearbox.train import (
    design_gearbox,
    gearbox_ratio,
    gearbox_shaft_table,
)

__all__ = [
    "design_gearbox",
    "gearbox_ratio",
    "gearbox_shaft_table",
]
