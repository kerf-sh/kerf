"""
CalculiX nonlinear-contact reference corpus.

This module encodes a set of canonical verification cases whose analytic
solutions are known in closed form.  Each case provides:

  * A mesh/BC/material description suitable for passing to
    ``CalculiXBridge.solve()``.
  * An analytic oracle function that computes the expected quantity from
    the same input parameters.
  * Metadata: tolerance, units, bibliographic reference.

The primary case is a two-cube Hertz contact problem under axial load.
Two unit cubes stacked along the z-axis are pressed together; the contact
half-width (or peak pressure) follows the Hertz formula for sphere/flat or
cylinder/flat contact.  For simplicity we use the flat-on-flat (block)
approximation and the Sneddon/Boussinesq result for a rectangular punch.

Hertz contact — circular punch on half-space
---------------------------------------------
For a cylindrical (line) contact between two elastic bodies of identical
material (Young's modulus E, Poisson ratio ν), the peak contact pressure
under a total normal force F per unit width b is (Johnson, Contact
Mechanics, 1985, eq. 4.23):

    p₀ = √( F * E* / (π * a) )

where the effective modulus E* = E / (2 * (1 - ν²)) for identical materials
and the contact half-width a = √( 4 * F * R / (π * E*) ) for a cylinder of
radius R on a flat.

For the simplified case used in this corpus — two rigid cubes with a small
effective radius R representing mesh-controlled surface roughness — we use
the finite-element result from the FEM simulation compared against the
analytic uniform-pressure estimate:

    p_analytic = F / A_contact

where A_contact is the nominal contact area (1 m × 1 m for unit cubes).
This Cauchy estimate is the simplest oracle and is exact in the limit of
infinite stiffness and flat contact.

For a more rigorous oracle we also provide the Hertz *peak* pressure for
a spherical contact (Hertz, 1881):

    a = ( 3 * F * R / (4 * E*) )^(1/3)     — contact radius
    p₀ = 3F / (2 π a²)                      — peak pressure

These formulas are used in the test suite as reference oracles; the FEM
result from ccx is compared against them with a 5% tolerance.

References
----------
Johnson, K.L. (1985). *Contact Mechanics*. Cambridge University Press.
  Chapter 4 (Hertz contact), Chapter 6 (Rolling contact).
Hertz, H. (1881). Über die Berührung fester elastischer Körper.
  J. reine angew. Math. 92, 156–171.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Hertz contact analytic oracle
# ---------------------------------------------------------------------------

def hertz_sphere_contact(
    F: float,
    R1: float,
    R2: float,
    E1: float,
    nu1: float,
    E2: float,
    nu2: float,
) -> dict:
    """
    Hertz contact mechanics for two elastic spheres under normal load F.

    Parameters
    ----------
    F   : total normal force [N]
    R1  : radius of body 1 [m]  (inf for a flat)
    R2  : radius of body 2 [m]  (inf for a flat)
    E1  : Young's modulus of body 1 [Pa]
    nu1 : Poisson ratio of body 1
    E2  : Young's modulus of body 2 [Pa]
    nu2 : Poisson ratio of body 2

    Returns
    -------
    dict with keys:
        E_star      : combined (reduced) modulus [Pa]
        R_eff       : effective radius [m]
        a           : contact radius [m]
        p0          : peak contact pressure [Pa]
        p_mean      : mean contact pressure [Pa]
        delta       : approach (indentation) [m]
    """
    # Reduced modulus  1/E* = (1-ν₁²)/E₁ + (1-ν₂²)/E₂
    E_star = 1.0 / ((1.0 - nu1 ** 2) / E1 + (1.0 - nu2 ** 2) / E2)

    # Effective radius  1/R* = 1/R₁ + 1/R₂
    R_eff = 1.0 / (1.0 / R1 + 1.0 / R2) if (R1 != math.inf and R2 != math.inf) \
        else (R1 if R2 == math.inf else R2)

    # Contact radius  a = (3FR/4E*)^(1/3)
    a = (3.0 * F * R_eff / (4.0 * E_star)) ** (1.0 / 3.0)

    # Peak pressure  p₀ = 3F/(2πa²)
    p0 = 3.0 * F / (2.0 * math.pi * a ** 2)

    # Mean pressure  p_mean = F/(πa²)
    p_mean = F / (math.pi * a ** 2)

    # Approach (indentation)  δ = a²/R*
    delta = a ** 2 / R_eff

    return {
        "E_star": E_star,
        "R_eff": R_eff,
        "a": a,
        "p0": p0,
        "p_mean": p_mean,
        "delta": delta,
    }


def hertz_flat_punch_pressure(F: float, A: float) -> float:
    """
    Cauchy (average-pressure) oracle for flat-on-flat contact.

    For two perfectly flat surfaces in contact under normal load F over
    nominal area A, the mean contact pressure is simply:

        p_mean = F / A

    This is the exact solution in the frictionless, infinite-stiffness,
    zero-gap limit and is used as the lower-bound oracle for flat FEM
    contact patches.

    Parameters
    ----------
    F : total normal force [N]
    A : contact area [m²]

    Returns
    -------
    p_mean : float — mean contact pressure [Pa]
    """
    if A <= 0:
        raise ValueError(f"Contact area must be positive, got {A}")
    return F / A


def hertz_two_spheres_equal(
    F: float,
    R: float,
    E: float,
    nu: float,
) -> dict:
    """
    Hertz contact for two identical spheres (R1 = R2 = R, E1=E2=E, ν1=ν2=ν).

    This is the standard reference case (Johnson §4.1).

    Parameters
    ----------
    F  : normal force [N]
    R  : sphere radius [m]
    E  : Young's modulus [Pa]
    nu : Poisson ratio

    Returns
    -------
    Same dict as ``hertz_sphere_contact``.
    """
    return hertz_sphere_contact(F, R, R, E, nu, E, nu)


# ---------------------------------------------------------------------------
# Two-cube contact reference case
# ---------------------------------------------------------------------------

@dataclass
class TwoCubeContactCase:
    """
    Reference problem: two unit cubes stacked on the z-axis, pressed
    together by an axial force F applied to the top face of the upper cube
    while the bottom face of the lower cube is fixed.

    Geometry
    --------
    * Lower cube:  z ∈ [0, 1], x ∈ [0, 1], y ∈ [0, 1]  — nodes 1–8
    * Upper cube:  z ∈ [1, 2], x ∈ [0, 1], y ∈ [0, 1]  — nodes 9–16
    * Contact interface: z = 1 plane

    The mesh is intentionally minimal (two C3D8 hexahedral elements, one
    per cube) so the test runs fast.  The contact normal force F is applied
    as distributed nodal loads on the top face (z = 2).

    Analytic oracle
    ---------------
    Because both cubes have the same cross-section and the contact is
    nominally flat, the mean contact pressure equals:

        p_analytic = F / A_contact   (A_contact = 1 m² for unit cubes)

    This is checked against the FEM contact pressure at the interface
    within the stated tolerance.

    Tolerance : 5%
    Reference : Cauchy flat-contact limit + Johnson §4.3
    """

    # Material
    E: float = 200e9        # Pa  (structural steel)
    nu: float = 0.3
    rho: float = 7850.0     # kg/m³

    # Load
    F: float = 1e6          # N   total axial force (compression)

    # Contact
    penalty: float = 1e11  # N/m  penalty stiffness

    # Verification tolerance (fraction)
    tolerance: float = 0.05

    def mesh(self) -> dict:
        """
        Minimal two-cube mesh: 16 nodes, 2 C3D8 hex elements.

        Node numbering (1-based):
          Lower cube corners (z=0 plane first, then z=1):
            1:(0,0,0)  2:(1,0,0)  3:(1,1,0)  4:(0,1,0)
            5:(0,0,1)  6:(1,0,1)  7:(1,1,1)  8:(0,1,1)
          Upper cube (z=1 bottom shared with lower cube top):
            Nodes 5-8 are shared (contact interface).
            9:(0,0,2)  10:(1,0,2)  11:(1,1,2)  12:(0,1,2)
        """
        nodes = [
            # Lower cube
            [0.0, 0.0, 0.0],  # 1
            [1.0, 0.0, 0.0],  # 2
            [1.0, 1.0, 0.0],  # 3
            [0.0, 1.0, 0.0],  # 4
            [0.0, 0.0, 1.0],  # 5  — contact interface (shared)
            [1.0, 0.0, 1.0],  # 6  — contact interface (shared)
            [1.0, 1.0, 1.0],  # 7  — contact interface (shared)
            [0.0, 1.0, 1.0],  # 8  — contact interface (shared)
            # Upper cube (top face)
            [0.0, 0.0, 2.0],  # 9
            [1.0, 0.0, 2.0],  # 10
            [1.0, 1.0, 2.0],  # 11
            [0.0, 1.0, 2.0],  # 12
        ]

        # C3D8 connectivity:  8 nodes ordered
        # face 1 (bottom): 1,2,3,4  face 2 (top): 5,6,7,8
        # CalculiX C3D8 node order: n1,n2,n3,n4,n5,n6,n7,n8
        # Lower cube element 1: bottom z=0, top z=1
        # Upper cube element 2: bottom z=1 (nodes 5-8), top z=2 (nodes 9-12)
        elements = [
            (1, "hex", [1, 2, 3, 4, 5, 6, 7, 8]),    # lower cube
            (2, "hex", [5, 6, 7, 8, 9, 10, 11, 12]),  # upper cube
        ]
        return {"nodes": nodes, "elements": elements}

    def materials(self) -> list[dict]:
        return [{"name": "STEEL", "E": self.E, "nu": self.nu, "rho": self.rho}]

    def boundary_conditions(self) -> list[dict]:
        """
        Fixed base (nodes 1–4, z=0) and distributed compressive load on
        top face (nodes 9–12, z=2).

        For CalculiX the BCs are expressed via named node sets with
        pre-populated ``node_ids`` keys so the bridge can emit *NSET blocks.
        """
        # Force per node on top face (4 corner nodes share the 1 m² face)
        f_per_node = self.F / 4.0

        return [
            # Fixed base
            {
                "type": "fixed",
                "node_set": "Nbase",
                "dofs": "1,3",
                "node_ids": [1, 2, 3, 4],
            },
            # Compressive load on top (-z direction)
            {
                "type": "cload",
                "node_set": "Ntop",
                "dof": 3,
                "value": -f_per_node,
                "node_ids": [9, 10, 11, 12],
            },
        ]

    def analytic_mean_contact_pressure(self) -> float:
        """
        Return the analytic mean contact pressure at the z=1 interface.

        For flat-on-flat unit cubes:  p = F / A = F / 1.0
        """
        A_contact = 1.0  # m²  (1 m × 1 m face)
        return hertz_flat_punch_pressure(self.F, A_contact)

    def analytic_hertz_sphere_peak(
        self,
        R: float = 0.1,
    ) -> dict:
        """
        Return the Hertz spherical-contact oracle for a representative
        asperity radius R (default 0.1 m).

        This is the *upper bound* — the actual FEM peak pressure will be
        lower than this for flat contact (which distributes the load more
        uniformly than a sphere).

        Parameters
        ----------
        R : effective asperity/sphere radius [m]

        Returns
        -------
        Hertz dict from ``hertz_two_spheres_equal``.
        """
        return hertz_two_spheres_equal(self.F, R, self.E, self.nu)


# ---------------------------------------------------------------------------
# Catalogue of all corpus cases
# ---------------------------------------------------------------------------

@dataclass
class CorpusCase:
    """Metadata wrapper for a single verification case."""
    name: str
    description: str
    case: object          # The actual case dataclass instance
    analysis_type: str
    reference: str
    tolerance: float


CORPUS: list[CorpusCase] = [
    CorpusCase(
        name="two_cube_contact_flat",
        description=(
            "Two unit steel cubes under 1 MN axial compression. "
            "Oracle: mean contact pressure = F/A (Cauchy flat-contact limit). "
            "Tolerance: 5%."
        ),
        case=TwoCubeContactCase(),
        analysis_type="contact",
        reference=(
            "Johnson, K.L. (1985). Contact Mechanics. "
            "Cambridge University Press. §4.3 (flat punch)."
        ),
        tolerance=0.05,
    ),
]


def get_case(name: str) -> CorpusCase:
    """Retrieve a corpus case by name."""
    for c in CORPUS:
        if c.name == name:
            return c
    raise KeyError(f"No corpus case named {name!r}. "
                   f"Available: {[c.name for c in CORPUS]}")
