"""
Reference corpus for MYSTRAN modal and aeroelastic validation.

This module provides:
1. Analytic oracles for canonical plate vibration problems.
2. Mesh generators that produce MYSTRAN-ready mesh dicts for each corpus case.
3. ``CorpusCase`` descriptors binding mesh, materials, BCs, expected values,
   and tolerance for programmatic test loops.

All analytic formulas are purely Pythonic (no numpy/scipy), citable, and
correct in the limit of classical thin-plate theory.

References
----------
Leissa, A.W., "Vibration of Plates", NASA SP-160, 1969.
    The definitive monograph for classical plate modal analysis.
    Table 4.1 (simply-supported rectangular plates, SSSS):
        λ_mn = π² (m²/a² + n²/b²)
        ω_mn = λ_mn √(D / (ρ h))    [rad/s]
        D = E h³ / (12 (1 − ν²))
Blevins, R.D., "Formulas for Natural Frequency and Mode Shape", 1979.
    Table 11-1 (simply-supported rectangular plate):
        f₁₁ = (π/2) √(D/(ρ h)) (1/a² + 1/b²)   [Hz]
        (equivalent to Leissa Table 4.1 for m=n=1)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Analytic oracles
# ---------------------------------------------------------------------------

def leissa_plate_freq_hz(
    E: float,
    nu: float,
    rho: float,
    h: float,
    a: float,
    b: float,
    m: int = 1,
    n: int = 1,
) -> float:
    """
    Natural frequency [Hz] of mode (m, n) for a thin isotropic rectangular
    plate simply-supported on all four edges (SSSS boundary condition).

    Formula
    -------
    From Leissa (1969) NASA SP-160, equation (4.1):

        D   = E h³ / [12 (1 − ν²)]          [N·m]  flexural rigidity
        ω_mn = π² (m²/a² + n²/b²) √(D / (ρ h))   [rad/s]
        f_mn = ω_mn / (2 π)                  [Hz]

    Parameters
    ----------
    E   : Young's modulus [Pa]
    nu  : Poisson's ratio
    rho : density [kg/m³]
    h   : plate thickness [m]
    a   : plate dimension in x [m]
    b   : plate dimension in y [m]
    m   : mode index in x (≥ 1)
    n   : mode index in y (≥ 1)

    Returns
    -------
    float  natural frequency in Hz
    """
    if E <= 0 or nu <= -1 or nu >= 0.5 or rho <= 0 or h <= 0 or a <= 0 or b <= 0:
        raise ValueError("Invalid material or geometry parameters")
    D = E * h ** 3 / (12.0 * (1.0 - nu ** 2))
    lam = math.pi ** 2 * (m ** 2 / a ** 2 + n ** 2 / b ** 2)
    omega = lam * math.sqrt(D / (rho * h))
    return omega / (2.0 * math.pi)


def leissa_plate_first_three_modes(
    E: float,
    nu: float,
    rho: float,
    h: float,
    a: float,
    b: float,
) -> list[float]:
    """
    First three distinct natural frequencies [Hz] of an SSSS thin plate.

    Modes returned in ascending frequency order.  For a square plate (a=b)
    modes (1,2) and (2,1) are degenerate (same frequency).  In that case all
    three entries may map to only two distinct frequency values.

    Returns
    -------
    list[float]  three natural frequencies in Hz, sorted ascending
    """
    # Enumerate the lowest few (m, n) combinations and sort by frequency.
    candidates: list[tuple[float, int, int]] = []
    for m in range(1, 5):
        for n in range(1, 5):
            f = leissa_plate_freq_hz(E, nu, rho, h, a, b, m, n)
            candidates.append((f, m, n))
    candidates.sort(key=lambda t: t[0])
    # Deduplicate by frequency (within 0.1% relative tolerance).
    unique: list[float] = []
    for f, _, _ in candidates:
        if not unique or abs(f - unique[-1]) / unique[-1] > 0.001:
            unique.append(f)
        if len(unique) == 3:
            break
    return unique


# ---------------------------------------------------------------------------
# Mesh generators for MYSTRAN corpus cases
# ---------------------------------------------------------------------------

def _uniform_plate_mesh_cquad4(
    a: float,
    b: float,
    t: float,
    nx: int,
    ny: int,
) -> dict[str, Any]:
    """
    Generate a uniform CQUAD4 mesh for a rectangular plate (z = 0 plane).

    The plate occupies [0, a] × [0, b] × {0}.  Nodes are laid out in a
    regular grid; CQUAD4 elements use counter-clockwise (CCW) connectivity.

    Parameters
    ----------
    a, b : plate dimensions in x, y [m]
    t    : plate thickness [m] (stored as ``shell_thickness`` in the mesh dict)
    nx   : number of elements in x
    ny   : number of elements in y

    Returns
    -------
    dict
        mesh dict compatible with ``MystranBridge.solve``::

            {
                "nodes": [(x, y, z), ...],            # 0-indexed; 1-indexed in BDF
                "elements": [(eid, "CQUAD4", [n1..n4]), ...],
                "shell_thickness": t,
                "boundary_node_ids": {
                    "all_edges": [...],   # all boundary nodes (for SSSS clamped)
                    "x0": [...],          # nodes at x=0
                    "x1": [...],          # nodes at x=a
                    "y0": [...],          # nodes at y=0
                    "y1": [...],          # nodes at y=b
                },
            }
    """
    dx = a / nx
    dy = b / ny
    nodes: list[tuple[float, float, float]] = []
    nid_map: dict[tuple[int, int], int] = {}  # (ix, iy) -> 1-indexed node id

    # Build nodes row by row (y-major ordering)
    for iy in range(ny + 1):
        for ix in range(nx + 1):
            nid_map[(ix, iy)] = len(nodes) + 1  # 1-indexed
            nodes.append((ix * dx, iy * dy, 0.0))

    # Build CQUAD4 elements
    elements: list[tuple[int, str, list[int]]] = []
    eid = 1
    for iy in range(ny):
        for ix in range(nx):
            n1 = nid_map[(ix,     iy)]
            n2 = nid_map[(ix + 1, iy)]
            n3 = nid_map[(ix + 1, iy + 1)]
            n4 = nid_map[(ix,     iy + 1)]
            elements.append((eid, "CQUAD4", [n1, n2, n3, n4]))
            eid += 1

    # Collect boundary node sets
    x0_nodes = [nid_map[(0,  iy)] for iy in range(ny + 1)]
    x1_nodes = [nid_map[(nx, iy)] for iy in range(ny + 1)]
    y0_nodes = [nid_map[(ix, 0)]  for ix in range(nx + 1)]
    y1_nodes = [nid_map[(ix, ny)] for ix in range(nx + 1)]

    all_edge_nodes = sorted(set(x0_nodes + x1_nodes + y0_nodes + y1_nodes))

    return {
        "nodes": nodes,
        "elements": elements,
        "shell_thickness": t,
        "boundary_node_ids": {
            "all_edges": all_edge_nodes,
            "x0": x0_nodes,
            "x1": x1_nodes,
            "y0": y0_nodes,
            "y1": y1_nodes,
        },
    }


# ---------------------------------------------------------------------------
# Corpus case descriptor
# ---------------------------------------------------------------------------

@dataclass
class CorpusCase:
    """
    A single corpus validation case binding geometry, materials, expected
    analytic frequencies, and the tolerance within which the FEM solution
    must fall.

    Attributes
    ----------
    name          : human-readable identifier
    description   : one-line description
    mesh          : mesh dict for ``MystranBridge.solve``
    materials     : material dict for ``MystranBridge.solve``
    boundary_conditions : BC list for ``MystranBridge.solve``
    analysis_type : "modal" (only type currently in corpus)
    expected_frequencies_hz : analytic oracle values [Hz]
    tolerance     : relative tolerance (e.g. 0.03 = 3%)
    reference     : citation string
    """

    name: str
    description: str
    mesh: dict[str, Any]
    materials: dict[str, Any]
    boundary_conditions: list[dict[str, Any]]
    analysis_type: str
    expected_frequencies_hz: list[float]
    tolerance: float
    reference: str
    tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Corpus builder
# ---------------------------------------------------------------------------

def build_corpus() -> list[CorpusCase]:
    """
    Return the full Mystran reference corpus.

    Currently contains:
    - ssss_plate_modal : simply-supported thin steel plate, first 3 modes vs
      Leissa (1969) analytic oracle.
    """
    return [_ssss_plate_modal_case()]


def _ssss_plate_modal_case() -> CorpusCase:
    """
    Simply-supported rectangular thin plate — first 3 modal frequencies.

    Geometry  : 0.4 m × 0.3 m, thickness 2 mm (steel)
    Material  : E = 200 GPa, ν = 0.3, ρ = 7850 kg/m³
    BC        : SSSS (all four edges simply supported — translational DOF
                constrained normal to the plate, in-plane DOF free, rotation
                DOF free).  In the BDF this is SPC1 with DOF mask "3" (T3
                only) on all edge nodes.  MYSTRAN CQUAD4 with PSHELL.
    Oracle    : Leissa (1969) NASA SP-160, Table 4.1 / eq. (4.1).
    Tolerance : 3 % (accounts for coarse mesh + CQUAD4 locking).

    Note: For a true SSSS plate the boundary condition constrains only the
    out-of-plane translation (T3).  The constraint mask "3" achieves this
    in NASTRAN/MYSTRAN DOF notation (1=T1, 2=T2, 3=T3, 4=R1, 5=R2, 6=R3).
    """
    a, b, t = 0.4, 0.3, 0.002
    E, nu, rho = 200e9, 0.3, 7850.0
    nx, ny = 8, 6  # 8×6 CQUAD4 mesh — coarse but sufficient for first 3 modes

    mesh = _uniform_plate_mesh_cquad4(a, b, t, nx, ny)

    # SSSS: constrain T3 (DOF 3) on all edge nodes
    edge_node_ids = mesh["boundary_node_ids"]["all_edges"]
    boundary_conditions = [
        {
            "type": "ssss",  # interpreted by corpus — translated to SPC1,3
            "node_ids": edge_node_ids,
            "dof_mask": "3",  # out-of-plane translation only
        }
    ]

    expected = leissa_plate_first_three_modes(E, nu, rho, t, a, b)

    return CorpusCase(
        name="ssss_plate_modal",
        description=(
            "Simply-supported thin rectangular plate (0.4×0.3 m, t=2 mm, steel), "
            "first 3 modal frequencies vs. Leissa (1969) Table 4.1 oracle."
        ),
        mesh=mesh,
        materials={"E": E, "nu": nu, "rho": rho},
        boundary_conditions=boundary_conditions,
        analysis_type="modal",
        expected_frequencies_hz=expected,
        tolerance=0.03,
        reference="Leissa, A.W., Vibration of Plates, NASA SP-160, 1969, Table 4.1",
        tags=["plate", "modal", "ssss", "leissa"],
    )


# ---------------------------------------------------------------------------
# Convenience: BDF deck for the SSSS plate corpus case (for syntax testing)
# ---------------------------------------------------------------------------

def ssss_plate_bdf() -> str:
    """
    Return the BDF deck string for the SSSS plate corpus case.

    This helper is used in syntax-only tests that do not require MYSTRAN
    to be installed.  It exercises ``_write_bdf_modal`` with the SSSS plate
    geometry so the deck syntax can be validated without running the solver.
    """
    from kerf_fem.mystran_bridge import _write_bdf_modal

    case = _ssss_plate_modal_case()
    mesh = case.mesh
    materials = case.materials

    # Translate SSSS BCs to fixed-type SPC1 with DOF mask 3.
    # ``_write_bdf_modal`` currently supports type="fixed" (DOF 123456).
    # For SSSS syntax testing we pass the edge nodes as a "fixed" BC so
    # the BDF writer exercises the SPC1 path.
    fixed_bcs = [
        {
            "type": "fixed",
            "node_ids": case.boundary_conditions[0]["node_ids"],
        }
    ]

    return _write_bdf_modal(
        nodes=mesh["nodes"],
        elements=mesh["elements"],
        materials=materials,
        boundary_conditions=fixed_bcs,
        num_modes=10,
        shell_thickness=mesh["shell_thickness"],
    )
