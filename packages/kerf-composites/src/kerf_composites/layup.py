"""
kerf_composites.layup — LaminateLayup data model.

A LaminateLayup is an ordered sequence of plies.  Each ply has:
  - fibre orientation in degrees (measured from the laminate reference axis)
  - material properties (orthotropic in-plane)
  - thickness in mm

This module is deliberately dependency-light (dataclasses + numpy only) so it
can be imported and tested without the full kerf-core runtime.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np


@dataclass
class PlyMaterial:
    """
    Orthotropic ply material — in-plane engineering constants.

    All moduli in GPa; strengths in MPa.

    Attributes
    ----------
    name : str
        Human-readable label (e.g. "T300/5208 CFRP").
    E1 : float
        Longitudinal (fibre-direction) Young's modulus [GPa].
    E2 : float
        Transverse Young's modulus [GPa].
    G12 : float
        In-plane shear modulus [GPa].
    nu12 : float
        Major Poisson's ratio (ν₁₂, dimensionless).
    Xt : float
        Longitudinal tensile strength [MPa].
    Xc : float
        Longitudinal compressive strength [MPa].
    Yt : float
        Transverse tensile strength [MPa].
    Yc : float
        Transverse compressive strength [MPa].
    S12 : float
        In-plane shear strength [MPa].
    """

    name: str
    E1: float   # GPa
    E2: float   # GPa
    G12: float  # GPa
    nu12: float
    Xt: float   # MPa
    Xc: float   # MPa
    Yt: float   # MPa
    Yc: float   # MPa
    S12: float  # MPa

    @property
    def nu21(self) -> float:
        """Minor Poisson's ratio (reciprocal relation)."""
        return self.nu12 * self.E2 / self.E1


# ---------------------------------------------------------------------------
# Common aerospace reference materials
# ---------------------------------------------------------------------------

#: T300/5208 carbon-epoxy — widely used aerospace reference lamina.
#: Ref: Reddy, *Mechanics of Laminated Composite Plates and Shells*, 2nd ed.
T300_5208 = PlyMaterial(
    name="T300/5208 CFRP",
    E1=181.0, E2=10.3, G12=7.17, nu12=0.28,
    Xt=1500.0, Xc=1500.0, Yt=40.0, Yc=246.0, S12=68.0,
)

#: E-glass/epoxy — common structural composite.
EGLASS_EPOXY = PlyMaterial(
    name="E-glass/epoxy",
    E1=38.6, E2=8.27, G12=4.14, nu12=0.26,
    Xt=1062.0, Xc=610.0, Yt=31.0, Yc=118.0, S12=72.0,
)


# ---------------------------------------------------------------------------
# Ply dataclass
# ---------------------------------------------------------------------------

@dataclass
class Ply:
    """
    A single composite ply.

    Parameters
    ----------
    angle : float
        Fibre orientation angle in degrees, measured anti-clockwise from the
        laminate 0° axis.
    material : PlyMaterial
        In-plane orthotropic material properties.
    thickness : float
        Ply thickness in mm.
    """

    angle: float          # degrees
    material: PlyMaterial
    thickness: float      # mm

    def __post_init__(self):
        if self.thickness <= 0.0:
            raise ValueError(f"Ply thickness must be positive, got {self.thickness!r}")


# ---------------------------------------------------------------------------
# LaminateLayup dataclass
# ---------------------------------------------------------------------------

@dataclass
class LaminateLayup:
    """
    An ordered sequence of plies forming a laminate.

    The ply sequence is stored bottom-to-top (ply[0] is the first ply laid
    down; the z-origin is at the laminate mid-plane for CLT).

    Attributes
    ----------
    plies : list[Ply]
        Ordered ply stack.
    name : str
        Optional human-readable label.
    """

    plies: list[Ply] = field(default_factory=list)
    name: str = "laminate"

    def __post_init__(self):
        if not isinstance(self.plies, list):
            self.plies = list(self.plies)

    # ------------------------------------------------------------------
    # Convenience constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_sequence(
        cls,
        angles: Sequence[float],
        material: PlyMaterial,
        ply_thickness: float = 0.125,
        name: str = "laminate",
    ) -> "LaminateLayup":
        """
        Build a laminate from a list of fibre angles with a uniform material
        and ply thickness.

        Parameters
        ----------
        angles : sequence of float
            Fibre orientations in degrees, e.g. [0, 90, 0].
        material : PlyMaterial
            Uniform material for all plies.
        ply_thickness : float
            Ply thickness in mm (default 0.125 mm, typical prepreg).
        name : str
            Optional label.

        Returns
        -------
        LaminateLayup
        """
        plies = [Ply(angle=a, material=material, thickness=ply_thickness) for a in angles]
        return cls(plies=plies, name=name)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def num_plies(self) -> int:
        return len(self.plies)

    @property
    def total_thickness(self) -> float:
        """Total laminate thickness in mm."""
        return sum(p.thickness for p in self.plies)

    @property
    def is_symmetric(self) -> bool:
        """True if the layup is symmetric about the mid-plane."""
        n = len(self.plies)
        for i in range(n // 2):
            a = self.plies[i]
            b = self.plies[n - 1 - i]
            if a.angle != b.angle or a.material is not b.material or a.thickness != b.thickness:
                return False
        return True

    @property
    def z_coords(self) -> list[float]:
        """
        Z-coordinates of ply interfaces measured from the mid-plane [mm].

        Returns a list of (num_plies + 1) values: z[0] is the bottom face,
        z[-1] is the top face.
        """
        h = self.total_thickness
        z = [-h / 2.0]
        for p in self.plies:
            z.append(z[-1] + p.thickness)
        return z

    def __repr__(self) -> str:
        angles = [p.angle for p in self.plies]
        return (
            f"LaminateLayup(name={self.name!r}, n={self.num_plies}, "
            f"h={self.total_thickness:.3f}mm, angles={angles})"
        )
