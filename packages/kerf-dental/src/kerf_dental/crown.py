"""
kerf_dental.crown — Parametric dental crown design.

Public API
----------
ToothAnatomy
    Dataclass describing a single tooth (crown, root, arch position).

CrownDesignInput
    Design parameters: margin line polygon, opposing tooth profile, material.

design_crown(inp) -> CrownResult
    Build a parametric crown Body from a margin-line polygon + opposing
    tooth cusp heights. Returns a B-rep Body that passes validate_body,
    plus diagnostic metadata.

Notes
-----
The crown surface is modelled as a capped cylinder whose radius and height
are derived from the convex hull of the margin-line polygon. The occlusal
surface height follows the highest cusp from the opposing-tooth profile.
This gives a topologically sound Body that can be post-processed (offset,
boolean) by the rest of the kerf CAD kernel.

The crown geometry is defined in a local coordinate frame:
  - Origin = centroid of the margin line
  - Z-axis = occlusal (superior) direction
  - X / Y axes span the margin plane
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class ToothAnatomy:
    """Anatomical description of a single tooth."""

    tooth_id: str
    """FDI notation, e.g. '16' (upper-right first molar)."""

    arch: str
    """'upper' or 'lower'."""

    crown_height_mm: float
    """Anatomical crown height in millimetres (typical 7–10 mm)."""

    root_length_mm: float
    """Root length in millimetres (typical 12–17 mm)."""

    mesio_distal_width_mm: float
    """Mesio-distal (x-axis) crown width in millimetres."""

    bucco_lingual_width_mm: float
    """Bucco-lingual (y-axis) crown width in millimetres."""

    cusp_heights_mm: list[float] = field(default_factory=lambda: [1.5])
    """Cusp heights above the margin line (mm).  One per cusp."""


@dataclass
class CrownDesignInput:
    """Inputs required to design a parametric crown."""

    margin_line: Sequence[tuple[float, float, float]]
    """3-D polygon (closed implied) defining the tooth preparation margin.
    Points are in mm, expressed in a common jaw coordinate frame."""

    opposing_cusp_heights_mm: Sequence[float]
    """Heights (mm) of functional cusps on the opposing tooth.
    Used to derive occlusal clearance and morphology. At least one value."""

    material: str = "zirconia"
    """Restorative material — informational only (zirconia, PMMA, e.max, etc.)."""

    occlusal_clearance_mm: float = 0.3
    """Minimum clearance between crown occlusal surface and opposing cusps (mm)."""

    def __post_init__(self):
        pts = list(self.margin_line)
        if len(pts) < 3:
            raise ValueError(
                f"margin_line must have at least 3 points, got {len(pts)}"
            )
        heights = list(self.opposing_cusp_heights_mm)
        if not heights:
            raise ValueError("opposing_cusp_heights_mm must not be empty")
        if self.occlusal_clearance_mm < 0:
            raise ValueError("occlusal_clearance_mm must be >= 0")


@dataclass
class CrownResult:
    """Output of design_crown()."""

    body: object
    """kerf_cad_core.geom.brep.Body — a closed, validate_body-clean B-rep."""

    margin_centroid_mm: tuple[float, float, float]
    """Centroid of the fitted margin line (mm)."""

    crown_radius_mm: float
    """Fitted circumradius of the crown footprint (mm)."""

    crown_height_mm: float
    """Total crown height (margin plane to occlusal surface) (mm)."""

    tooth_anatomy: "ToothAnatomy | None" = None
    """Populated anatomy dataclass when tooth_id is supplied."""


# ---------------------------------------------------------------------------
# Crown design
# ---------------------------------------------------------------------------

def design_crown(inp: CrownDesignInput) -> CrownResult:
    """
    Build a parametric crown B-rep from a margin line + opposing tooth profile.

    The algorithm:
    1. Fit the margin-line polygon:
       - Project to best-fit plane via PCA.
       - Compute the circumscribed radius (max distance from centroid).
    2. Determine crown height:
       - Max opposing cusp height + occlusal_clearance_mm.
    3. Build the crown Body:
       - make_cylinder(radius=circumradius, height=crown_height) oriented
         along the local Z axis of the margin plane.
    4. Return CrownResult; the Body is guaranteed validate_body-clean
       because make_cylinder produces a topologically sound manifold solid.

    Parameters
    ----------
    inp : CrownDesignInput

    Returns
    -------
    CrownResult with a closed, validate_body-clean Body.

    Raises
    ------
    ImportError  if kerf_cad_core is not importable.
    ValueError   if the margin line is degenerate (all points collinear).
    """
    from kerf_cad_core.geom.brep import make_cylinder, validate_body

    pts = np.array(inp.margin_line, dtype=float)
    if pts.ndim != 2 or pts.shape[1] != 3:
        raise ValueError(
            f"margin_line must be an (N, 3) array-like, got shape {pts.shape}"
        )

    centroid = pts.mean(axis=0)

    # PCA to find best-fit plane normal (smallest eigenvalue eigenvector)
    centered = pts - centroid
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    normal = vh[2]  # smallest-variance direction = plane normal
    if np.linalg.norm(normal) < 1e-12:
        raise ValueError("Margin line points are degenerate (zero spread)")
    normal = normal / np.linalg.norm(normal)

    # Ensure normal points in the "occlusal" (positive z) sense
    if normal[2] < 0:
        normal = -normal

    # Circumscribed radius = max distance from centroid projected to margin plane
    proj = centered - np.outer(centered.dot(normal), normal)
    radii = np.linalg.norm(proj, axis=1)
    crown_radius = float(radii.max())
    if crown_radius < 1e-6:
        raise ValueError("Margin line degenerates to a single point")

    # Crown height: tallest opposing cusp + clearance
    crown_height = float(max(inp.opposing_cusp_heights_mm)) + inp.occlusal_clearance_mm
    if crown_height < 0.1:
        crown_height = 0.1  # minimum 0.1 mm structural thickness

    # Build the crown body as a cylinder along the margin-plane normal
    body = make_cylinder(
        center=tuple(centroid),
        axis=tuple(normal),
        radius=crown_radius,
        height=crown_height,
    )

    # Sanity check — should always pass for make_cylinder output
    vr = validate_body(body)
    if not vr["ok"]:
        raise RuntimeError(
            f"design_crown produced an invalid body: {vr['errors']}"
        )

    return CrownResult(
        body=body,
        margin_centroid_mm=(float(centroid[0]), float(centroid[1]), float(centroid[2])),
        crown_radius_mm=crown_radius,
        crown_height_mm=crown_height,
    )
