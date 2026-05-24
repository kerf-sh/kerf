"""
kerf_dental.denture — Parametric full denture and removable partial denture (RPD) geometry.

Public API
----------
DentureSpec
    Design parameters for a complete denture: arch, tooth positions, flange dimensions.

RPDSpec
    Design parameters for a removable partial denture: arch type, rest positions, connector.

DentureResult
    Output of design_full_denture() — flange mesh + tooth socket positions.

RPDResult
    Output of design_rpd() — major connector mesh + rest/clasp positions.

design_full_denture(spec) -> DentureResult
    Build a parametric complete denture base as a horseshoe-arch mesh (mandibular
    or maxillary).  Returns vertex/face arrays suitable for STL milling.

design_rpd(spec) -> RPDResult
    Build a parametric RPD major connector (lingual bar for mandibular,
    palatal plate for maxillary) as a flat arch mesh.

Algorithm notes
---------------
Full denture
    1. Parametrize the dental arch as a half-ellipse: semi-axes (a, b) in mm.
       Upper (maxillary) default: a=40 mm, b=35 mm (wider palatal vault).
       Lower (mandibular) default: a=33 mm, b=25 mm (narrower ridge).
    2. Build a tube cross-section along the arch centreline:
       - Flange height h_flange (mm) in the buccal direction.
       - Flange thickness t_flange (mm).
    3. Tessellate with N_arch segments × 4 cross-section vertices per segment
       → closed manifold mesh suitable for STL milling.

RPD major connector
    1. Lingual bar (mandibular): a half-ellipse in the floor-of-mouth region,
       rectangular cross-section (width × depth).
    2. Palatal plate (maxillary): a similar half-ellipse with plate geometry.

References
----------
- Basker RM et al., "Prosthetic Treatment of the Edentulous Patient", 5th ed., 2011.
- Phoenix RD et al., "Stewart's Clinical Removable Partial Prosthodontics", 4th ed., 2008.
- ISO 22977:2006 (Dentistry — Complete dentures).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple

import numpy as np


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DentureSpec:
    """Parameters for a complete (full) denture."""

    arch: str = "mandibular"
    """'mandibular' (lower) or 'maxillary' (upper)."""

    arch_semi_a_mm: float = 0.0
    """Semi-axis in the anterior-posterior direction (mm).
    0 = use arch-specific default (40 mm maxillary, 33 mm mandibular)."""

    arch_semi_b_mm: float = 0.0
    """Semi-axis in the buccal-lingual direction (mm).
    0 = use arch-specific default (35 mm maxillary, 25 mm mandibular)."""

    flange_height_mm: float = 15.0
    """Height of the buccal/labial flange (mm).  Typical 12–18 mm."""

    flange_thickness_mm: float = 2.5
    """Flange wall thickness (mm).  Minimum clinically acceptable ~2 mm."""

    n_arch_segments: int = 32
    """Number of segments to approximate the arch curve.  ≥8 recommended."""

    n_tooth_positions: int = 14
    """Number of artificial tooth sockets to mark along the arch ridge (6–16)."""

    def __post_init__(self):
        if self.arch not in ("mandibular", "maxillary"):
            raise ValueError(f"arch must be 'mandibular' or 'maxillary', got {self.arch!r}")
        if self.flange_height_mm <= 0:
            raise ValueError("flange_height_mm must be > 0")
        if self.flange_thickness_mm <= 0:
            raise ValueError("flange_thickness_mm must be > 0")
        if self.n_arch_segments < 8:
            raise ValueError("n_arch_segments must be >= 8")
        if self.n_tooth_positions < 4:
            raise ValueError("n_tooth_positions must be >= 4")

        # Apply defaults for arch axes
        if self.arch_semi_a_mm <= 0:
            self.arch_semi_a_mm = 40.0 if self.arch == "maxillary" else 33.0
        if self.arch_semi_b_mm <= 0:
            self.arch_semi_b_mm = 35.0 if self.arch == "maxillary" else 25.0


@dataclass
class RPDSpec:
    """Parameters for a removable partial denture (RPD) major connector."""

    arch: str = "mandibular"
    """'mandibular' (lingual bar) or 'maxillary' (palatal plate/strap)."""

    arch_semi_a_mm: float = 0.0
    """Semi-axis anterior-posterior (mm). 0 = arch default."""

    arch_semi_b_mm: float = 0.0
    """Semi-axis buccal-lingual (mm). 0 = arch default."""

    connector_width_mm: float = 5.0
    """Width (buccal-lingual dimension) of the major connector bar (mm)."""

    connector_depth_mm: float = 2.0
    """Thickness (occlusal-gingival dimension) of the major connector (mm)."""

    rest_positions: list = field(default_factory=list)
    """FDI tooth numbers with rests, e.g. [24, 27] (empty = auto 4 rests)."""

    n_arch_segments: int = 32
    """Arch curve tessellation. ≥8 recommended."""

    def __post_init__(self):
        if self.arch not in ("mandibular", "maxillary"):
            raise ValueError(f"arch must be 'mandibular' or 'maxillary', got {self.arch!r}")
        if self.connector_width_mm <= 0:
            raise ValueError("connector_width_mm must be > 0")
        if self.connector_depth_mm <= 0:
            raise ValueError("connector_depth_mm must be > 0")
        if self.n_arch_segments < 8:
            raise ValueError("n_arch_segments must be >= 8")
        if self.arch_semi_a_mm <= 0:
            self.arch_semi_a_mm = 38.0 if self.arch == "maxillary" else 30.0
        if self.arch_semi_b_mm <= 0:
            self.arch_semi_b_mm = 32.0 if self.arch == "maxillary" else 22.0
        if not self.rest_positions:
            # Default: 4 rests evenly distributed
            self.rest_positions = [14, 17, 24, 27] if self.arch == "maxillary" else [34, 37, 44, 47]


@dataclass
class DentureResult:
    """Output of design_full_denture()."""

    vertices: np.ndarray
    """(V, 3) float32 — vertex coordinates in mm."""

    faces: np.ndarray
    """(F, 3) int32 — triangle face indices."""

    tooth_positions: list
    """List of (x, y, z) points in mm — one per artificial tooth slot along the ridge."""

    arch: str
    """'mandibular' or 'maxillary'."""

    arch_semi_a_mm: float
    arch_semi_b_mm: float

    @property
    def vertex_count(self) -> int:
        return len(self.vertices)

    @property
    def face_count(self) -> int:
        return len(self.faces)


@dataclass
class RPDResult:
    """Output of design_rpd()."""

    vertices: np.ndarray
    """(V, 3) float32 — connector mesh vertices (mm)."""

    faces: np.ndarray
    """(F, 3) int32 — triangle face indices."""

    rest_positions: list
    """(x, y, z) positions of occlusal rests along the arch (mm)."""

    connector_type: str
    """'lingual_bar' (mandibular) or 'palatal_plate' (maxillary)."""

    @property
    def vertex_count(self) -> int:
        return len(self.vertices)

    @property
    def face_count(self) -> int:
        return len(self.faces)


# ---------------------------------------------------------------------------
# Internal arch geometry helpers
# ---------------------------------------------------------------------------

def _arch_centreline(
    semi_a: float,
    semi_b: float,
    n_segments: int,
) -> np.ndarray:
    """
    Build the dental arch centreline as a half-ellipse in the XY plane.

    The half-ellipse spans from (−a, 0) to (+a, 0) via the anterior point (0, b).
    Returns (n_segments+1, 3) array of 3-D points (z=0).
    """
    angles = np.linspace(math.pi, 0.0, n_segments + 1)
    pts = np.column_stack([
        semi_a * np.cos(angles),
        semi_b * np.sin(angles),
        np.zeros(n_segments + 1),
    ]).astype(np.float32)
    return pts


def _arch_tube_mesh(
    centreline: np.ndarray,   # (N, 3)
    section_verts_local: np.ndarray,  # (K, 3) cross-section in local frame
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Sweep a cross-section polygon along a centreline to form a closed tube mesh.

    centreline   : (N, 3) — N points including both endpoints.
    section_verts_local : (K, 3) — cross-section vertices in the local (t, n, b) frame,
                          where t is tangent, n is in-plane normal, b = (0,0,1) is binormal.

    Returns (vertices (V, 3), faces (F, 3)) for an open tube (no end caps).
    End caps are added separately.
    """
    N = len(centreline)
    K = len(section_verts_local)

    # Build local frames at each centreline point
    # Tangent from finite difference; normal = up-vector projected; binormal = t×n
    world_verts = []
    for i in range(N):
        pt = centreline[i]
        # Tangent
        if i < N - 1:
            t = centreline[i + 1] - centreline[i]
        else:
            t = centreline[i] - centreline[i - 1]
        t_len = np.linalg.norm(t)
        if t_len < 1e-12:
            t = np.array([1.0, 0.0, 0.0], dtype=float)
        else:
            t = t / t_len

        # Binormal: use global Z as reference up
        up = np.array([0.0, 0.0, 1.0], dtype=float)
        b = np.cross(t, up)
        b_len = np.linalg.norm(b)
        if b_len < 1e-12:
            b = np.array([0.0, 1.0, 0.0], dtype=float)
        else:
            b = b / b_len
        n = np.cross(b, t)

        # Transform section verts to world
        for sv in section_verts_local:
            # sv = (s_t, s_n, s_b) — displace in n and b directions
            world_pt = pt + sv[0] * n + sv[1] * b + sv[2] * np.array([0.0, 0.0, 1.0])
            world_verts.append(world_pt)

    vertices = np.array(world_verts, dtype=np.float32)
    # Index: vertex(i, j) = i * K + j  for ring i, section vertex j

    faces = []
    for i in range(N - 1):
        for j in range(K):
            j1 = (j + 1) % K
            # Quad: (i,j) (i+1,j) (i+1,j1) (i,j1) → 2 triangles
            v00 = i * K + j
            v10 = (i + 1) * K + j
            v11 = (i + 1) * K + j1
            v01 = i * K + j1
            faces.append([v00, v10, v11])
            faces.append([v00, v11, v01])

    faces_arr = np.array(faces, dtype=np.int32)
    return vertices, faces_arr


def _add_end_cap(
    vertices: np.ndarray,
    faces: list,
    ring: np.ndarray,  # indices of the ring vertices (shape (K,))
    close_inward: bool,
) -> None:
    """
    Append a fan-triangulated end cap to the faces list.

    ring         : vertex indices for the ring
    close_inward : if True, triangles point inward (start cap); otherwise outward (end cap).
    vertices are in the vertices array; we add a centroid vertex.

    Modifies faces in place; caller must handle the new centroid vertex index.
    """
    pass  # Caller handles this separately


def _fan_cap(
    all_verts: list,
    faces: list,
    ring_verts: np.ndarray,   # (K, 3) ring vertex coordinates
    ring_base_idx: int,        # index of first ring vertex in all_verts
    K: int,
    invert: bool = False,
) -> None:
    """Add a fan cap (centroid + K triangles) to all_verts and faces."""
    centroid = ring_verts.mean(axis=0)
    cap_idx = len(all_verts)
    all_verts.append(centroid)

    for j in range(K):
        j1 = (j + 1) % K
        v0 = ring_base_idx + j
        v1 = ring_base_idx + j1
        vc = cap_idx
        if invert:
            faces.append([v0, vc, v1])
        else:
            faces.append([v0, v1, vc])


# ---------------------------------------------------------------------------
# Full denture
# ---------------------------------------------------------------------------

def design_full_denture(spec: DentureSpec) -> DentureResult:
    """
    Build a parametric complete denture base mesh.

    The denture base is modelled as a tube swept along a half-ellipse arch:

      Cross-section (in the plane perpendicular to the arch tangent):
        4 vertices forming a U-shape:
          - Ridge crest (inner buccal wall top): (0, 0, 0)
          - Ridge inner (lingual side at base): (0, +W/2, −H)
          - Ridge outer (buccal side at base): (0, −W/2, −H)
          - Buccal flange top: (0, −W/2 − F_ext, 0)
        where W = flange_thickness_mm, H = flange_height_mm,
              F_ext = additional buccal extension = flange_thickness_mm.

    Both end rings are capped with fan triangulation.

    Parameters
    ----------
    spec : DentureSpec

    Returns
    -------
    DentureResult with vertices/faces (mm), tooth_positions along the arch ridge.
    """
    N = spec.n_arch_segments
    a = spec.arch_semi_a_mm
    b = spec.arch_semi_b_mm
    H = spec.flange_height_mm
    T = spec.flange_thickness_mm

    centreline = _arch_centreline(a, b, N)

    # Cross-section: 4 vertices in the local n-b plane
    # n = in-plane normal (toward arch centre), b = vertical (Z)
    # Place cross-section to look like a denture flange when viewed from outside:
    #   Ridge inner  : (n=+T/2, b=0)
    #   Ridge outer  : (n=-T/2, b=0)   (buccal)
    #   Flange bottom outer: (n=-T/2, b=-H)
    #   Flange bottom inner: (n=+T/2, b=-H)
    half_T = T / 2.0
    section = np.array([
        [+half_T, 0.0, 0.0],    # inner ridge crest
        [-half_T, 0.0, 0.0],    # outer ridge crest (buccal)
        [-half_T, -H, 0.0],     # outer flange base
        [+half_T, -H, 0.0],     # inner flange base
    ], dtype=float)
    K = 4

    # Build tube mesh (open tube)
    tube_verts, tube_faces = _arch_tube_mesh(centreline, section)

    # Add end caps at both arch ends (convert to list for modification)
    all_verts = list(tube_verts)
    all_faces = list(tube_faces)

    # Start ring: centreline[0] → section vertices 0..K-1
    start_ring = tube_verts[0:K]
    _fan_cap(all_verts, all_faces, start_ring, 0, K, invert=True)

    # End ring: centreline[-1] → last ring in tube: offset = (N) * K
    end_ring_base = N * K
    end_ring = tube_verts[end_ring_base: end_ring_base + K]
    _fan_cap(all_verts, all_faces, end_ring, end_ring_base, K, invert=False)

    # Tooth positions: evenly spaced along arch centreline (skip endpoints)
    M = spec.n_tooth_positions
    tooth_idxs = np.linspace(1, N - 1, M, dtype=int)
    tooth_positions = [
        (float(centreline[i][0]), float(centreline[i][1]), float(centreline[i][2]))
        for i in tooth_idxs
    ]

    vertices = np.array(all_verts, dtype=np.float32)
    faces = np.array(all_faces, dtype=np.int32)

    return DentureResult(
        vertices=vertices,
        faces=faces,
        tooth_positions=tooth_positions,
        arch=spec.arch,
        arch_semi_a_mm=a,
        arch_semi_b_mm=b,
    )


# ---------------------------------------------------------------------------
# Removable partial denture (RPD) major connector
# ---------------------------------------------------------------------------

def design_rpd(spec: RPDSpec) -> RPDResult:
    """
    Build a parametric RPD major connector mesh.

    Mandibular: lingual bar — a half-ellipse bar in the floor-of-mouth region.
    Maxillary: palatal plate — a half-ellipse plate across the palate.

    Cross-section (rectangular, in the local n-b plane):
      n = normal to arch tangent (in-plane)
      b = vertical (Z)

    4 vertices of the rectangular cross-section:
      (±W/2, 0),  (±W/2, −D)
    where W = connector_width_mm, D = connector_depth_mm.

    Parameters
    ----------
    spec : RPDSpec

    Returns
    -------
    RPDResult
    """
    N = spec.n_arch_segments
    a = spec.arch_semi_a_mm
    b = spec.arch_semi_b_mm
    W = spec.connector_width_mm
    D = spec.connector_depth_mm

    # Lingual bar is offset inward (toward tongue): shift arch inward by W
    # For simplicity, use the same arch curve and interpret the cross-section
    # as straddling the lingual bar position.
    centreline = _arch_centreline(a, b, N)

    half_W = W / 2.0
    section = np.array([
        [-half_W, 0.0, 0.0],
        [+half_W, 0.0, 0.0],
        [+half_W, -D, 0.0],
        [-half_W, -D, 0.0],
    ], dtype=float)
    K = 4

    tube_verts, tube_faces = _arch_tube_mesh(centreline, section)
    all_verts = list(tube_verts)
    all_faces = list(tube_faces)

    # End caps
    start_ring = tube_verts[0:K]
    _fan_cap(all_verts, all_faces, start_ring, 0, K, invert=True)
    end_ring_base = N * K
    end_ring = tube_verts[end_ring_base: end_ring_base + K]
    _fan_cap(all_verts, all_faces, end_ring, end_ring_base, K, invert=False)

    # Rest positions: distribute evenly along arch
    n_rests = max(len(spec.rest_positions), 4)
    rest_idxs = np.linspace(0, N, n_rests, endpoint=False, dtype=int)
    rest_positions = [
        (float(centreline[i][0]), float(centreline[i][1]), float(centreline[i][2]))
        for i in rest_idxs
    ]

    connector_type = "palatal_plate" if spec.arch == "maxillary" else "lingual_bar"

    vertices = np.array(all_verts, dtype=np.float32)
    faces = np.array(all_faces, dtype=np.int32)

    return RPDResult(
        vertices=vertices,
        faces=faces,
        rest_positions=rest_positions,
        connector_type=connector_type,
    )
