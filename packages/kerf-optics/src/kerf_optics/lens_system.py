"""
Lens system data model and ABCD matrix builder.

A LensSystem is an ordered list of optical elements.  Each element
is a dataclass that knows how to generate the sequence of ABCD matrices
that represent it in the paraxial model.

Supported element types:

    ThinLens(f)            — thin lens of focal length f
    FreeSpace(d, n)        — free-space propagation of distance d in medium n
    CurvedInterface(R, n1, n2) — refraction at a spherical interface
    Mirror(R)              — concave/convex spherical mirror
    Aperture(diameter)     — thin aperture stop (identity in ABCD model)
    Detector()             — marks the image plane (identity, ends the system)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Union

import numpy as np

from kerf_optics.ray_transfer import (
    M_free,
    M_thin_lens,
    M_refraction,
    M_mirror,
    M_identity,
    system_matrix,
    focal_length,
    image_distance,
    back_focal_distance,
    front_focal_distance,
    trace_ray,
    trace_bundle,
    spot_radius_at_plane,
)


# ---------------------------------------------------------------------------
# Element dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ThinLens:
    """Thin lens of focal length *f* (metres). f > 0 → converging."""
    f: float

    def matrices(self) -> list[np.ndarray]:
        return [M_thin_lens(self.f)]

    def describe(self) -> str:
        return f"ThinLens(f={self.f})"


@dataclass
class FreeSpace:
    """Free-space propagation of distance *d* in medium of index *n*."""
    d: float
    n: float = 1.0

    def matrices(self) -> list[np.ndarray]:
        return [M_free(self.d, self.n)]

    def describe(self) -> str:
        return f"FreeSpace(d={self.d}, n={self.n})"


@dataclass
class CurvedInterface:
    """Refraction at a spherical interface.

    R > 0 → centre of curvature to the right (convex surface for light
    travelling left→right).
    """
    R: float
    n1: float
    n2: float

    def matrices(self) -> list[np.ndarray]:
        return [M_refraction(self.R, self.n1, self.n2)]

    def describe(self) -> str:
        return f"CurvedInterface(R={self.R}, n1={self.n1}, n2={self.n2})"


@dataclass
class Mirror:
    """Spherical mirror. R > 0 → concave (converging)."""
    R: float

    def matrices(self) -> list[np.ndarray]:
        return [M_mirror(self.R)]

    def describe(self) -> str:
        return f"Mirror(R={self.R})"


@dataclass
class Aperture:
    """Thin aperture stop. Only records the diameter; identity in ABCD model."""
    diameter: float

    def matrices(self) -> list[np.ndarray]:
        return [M_identity()]

    def describe(self) -> str:
        return f"Aperture(diameter={self.diameter})"


@dataclass
class Detector:
    """Image-plane / detector.  Identity matrix — ends the system."""

    def matrices(self) -> list[np.ndarray]:
        return [M_identity()]

    def describe(self) -> str:
        return "Detector()"


Element = Union[ThinLens, FreeSpace, CurvedInterface, Mirror, Aperture, Detector]


# ---------------------------------------------------------------------------
# LensSystem
# ---------------------------------------------------------------------------

@dataclass
class LensSystem:
    """Ordered list of optical elements from object to image.

    Parameters
    ----------
    elements : list of Element objects (ThinLens, FreeSpace, etc.)
    """
    elements: list[Element] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Construction helpers
    # ------------------------------------------------------------------

    def append(self, element: Element) -> "LensSystem":
        """Add an element to the end of the system (mutates in place, returns self)."""
        self.elements.append(element)
        return self

    # ------------------------------------------------------------------
    # System matrix
    # ------------------------------------------------------------------

    def system_matrix(self) -> np.ndarray:
        """Build and return the compound ABCD matrix for the whole system."""
        all_matrices: list[np.ndarray] = []
        for el in self.elements:
            all_matrices.extend(el.matrices())
        return system_matrix(all_matrices)

    def _flat_matrices(self) -> list[np.ndarray]:
        """Flatten all per-element matrices into a single list."""
        result = []
        for el in self.elements:
            result.extend(el.matrices())
        return result

    # ------------------------------------------------------------------
    # First-order properties
    # ------------------------------------------------------------------

    def efl(self) -> float:
        """Effective focal length of the system (metres)."""
        return focal_length(self.system_matrix())

    def back_focal_distance(self) -> float:
        """Back focal distance (distance from rear principal plane to rear focal point)."""
        return back_focal_distance(self.system_matrix())

    def front_focal_distance(self) -> float:
        """Front focal distance."""
        return front_focal_distance(self.system_matrix())

    def image_distance(self, object_distance: float) -> float:
        """Paraxial image distance for an object at *object_distance*."""
        return image_distance(self.system_matrix(), object_distance)

    # ------------------------------------------------------------------
    # Ray tracing
    # ------------------------------------------------------------------

    def trace(self, y0: float, u0: float) -> list[tuple[float, float]]:
        """Trace a single ray (y0, nu0) through the system.

        Returns list of (y, nu) states at each surface.
        """
        return trace_ray(y0, u0, self._flat_matrices())

    def trace_bundle(
        self,
        rays: list[tuple[float, float]],
    ) -> list[list[tuple[float, float]]]:
        """Trace a ray bundle through the system."""
        return trace_bundle(rays, self._flat_matrices())

    def spot_radius(self, rays: list[tuple[float, float]]) -> float:
        """RMS spot radius at the exit plane for the given ray bundle."""
        return spot_radius_at_plane(rays, self._flat_matrices())

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def thin_lens(cls, f: float, object_distance: float, image_distance: float) -> "LensSystem":
        """Build a simple single-thin-lens system:
        FreeSpace(do) → ThinLens(f) → FreeSpace(di)
        """
        return cls([
            FreeSpace(object_distance),
            ThinLens(f),
            FreeSpace(image_distance),
        ])

    @classmethod
    def telephoto(
        cls,
        f1: float,
        f2: float,
        separation: float,
        object_distance: float,
    ) -> "LensSystem":
        """Two-lens telephoto: lens1 → gap → lens2.

        The caller provides the object_distance; the image plane is not
        pre-placed (use image_distance() to find di, then append FreeSpace).
        """
        return cls([
            FreeSpace(object_distance),
            ThinLens(f1),
            FreeSpace(separation),
            ThinLens(f2),
        ])

    # ------------------------------------------------------------------
    # Spot diagram helper
    # ------------------------------------------------------------------

    def spot_diagram(
        self,
        n_rays: int = 7,
        y_range: float = 0.01,
        u_range: float = 0.01,
    ) -> dict:
        """Generate a paraxial spot diagram at the exit plane.

        Creates a bundle of rays with heights uniformly sampled in
        [-y_range, y_range] and angles uniformly sampled in
        [-u_range, u_range].  Returns a dict with:
            - 'heights'  : list of final ray heights
            - 'rms_spot' : RMS spot radius
            - 'n_rays'   : number of rays traced

        Note: In the paraxial model, the spot diagram is a linear
        map from input to output — the 'spot' size reflects the
        aberration-free Gaussian beam waist, not diffraction.
        """
        import numpy as np_inner  # avoid shadowing module-level np

        ys = np_inner.linspace(-y_range, y_range, n_rays)
        us = np_inner.linspace(-u_range, u_range, n_rays)

        # On-axis bundle: varying angle, fixed height
        rays_angular = [(0.0, float(u)) for u in us]
        # Off-axis bundle: varying height, fixed angle
        rays_height = [(float(y), 0.0) for y in ys]

        all_rays = rays_angular + rays_height

        histories = self.trace_bundle(all_rays)
        final_heights = [h[-1][0] for h in histories]

        rms = float(np.sqrt(np.mean(np.array(final_heights) ** 2)))

        return {
            "heights": final_heights,
            "rms_spot": rms,
            "n_rays": len(all_rays),
        }

    def summary(self) -> dict:
        """Return a first-order summary of the lens system."""
        M = self.system_matrix()
        C = M[1, 0]
        result: dict = {
            "n_elements": len(self.elements),
            "elements": [el.describe() for el in self.elements],
            "system_matrix": M.tolist(),
        }
        if abs(C) > 1e-14:
            result["efl"] = self.efl()
            result["back_focal_distance"] = self.back_focal_distance()
            result["front_focal_distance"] = self.front_focal_distance()
        else:
            result["efl"] = None  # afocal / collimating system
        return result
