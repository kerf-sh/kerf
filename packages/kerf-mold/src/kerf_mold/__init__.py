"""kerf-mold: injection-mold tooling design plugin for Kerf."""

from kerf_mold.mold import (
    Face,
    EjectorPin,
    GateLocation,
    PartingLine,
    MoldDesign,
    check_moldability,
    generate_parting_surface,
    draft_angle_per_face,
)

__all__ = [
    "Face",
    "EjectorPin",
    "GateLocation",
    "PartingLine",
    "MoldDesign",
    "check_moldability",
    "generate_parting_surface",
    "draft_angle_per_face",
]
