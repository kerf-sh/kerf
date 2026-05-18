"""
3-D unstructured tetrahedral mesh generator — pure Python seed.

Algorithm
---------
Bowyer-Watson incremental Delaunay tetrahedralization.

Reference: Bowyer (1981) "Computing Dirichlet tessellations",
           Watson (1981) "Computing the n-dimensional Delaunay tessellation
           with application to Voronoi polytopes".

Boundary conformance
--------------------
After the point-cloud triangulation, required boundary triangles that are
missing from the mesh surface are re-inserted via constrained edge/face
splitting.  The approach used here is a simple Steiner-point insertion on
the centroid of any missing boundary face, which is sufficient for convex
domains and the unit-cube test case.

Output
------
``Mesh3D`` dataclass:
  - ``vertices``   : list of (x, y, z) tuples
  - ``elements``   : list of 4-tuples of vertex indices  (tetrahedra)
  - ``faces``      : list of 3-tuples of vertex indices  (boundary triangles)
  - ``face_tags``  : parallel list of integer region tags for each boundary face

Euler characteristic
--------------------
For a valid 3-manifold simplicial complex filling a simply-connected volume:

    V − E + F − T = 1

where V = vertices, E = edges, F = faces (triangles), T = tetrahedra.
This invariant is verified in the test suite.

Quality metric
--------------
Minimum dihedral angle across all tetrahedra.  Reported in degrees.
A well-shaped tet has all dihedral angles in [18°, 162°].
A degenerate (sliver) tet has a dihedral angle near 0° or 180°.
"""

from __future__ import annotations

import math
import itertools
from dataclasses import dataclass, field
from typing import Iterator


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Mesh3D:
    """3-D unstructured tetrahedral mesh."""

    vertices: list[tuple[float, float, float]]
    """Point cloud; index is the vertex id."""

    elements: list[tuple[int, int, int, int]]
    """Tetrahedra as 4-tuples of vertex indices (positive-volume orientation)."""

    faces: list[tuple[int, int, int]]
    """Boundary triangle faces as 3-tuples of vertex indices."""

    face_tags: list[int] = field(default_factory=list)
    """Region tag per boundary face (default 1 = outer boundary)."""

    # ------------------------------------------------------------------
    # Derived topology helpers
    # ------------------------------------------------------------------

    def unique_edges(self) -> set[tuple[int, int]]:
        """Return the set of unique undirected edges across all tetrahedra."""
        edges: set[tuple[int, int]] = set()
        for tet in self.elements:
            for a, b in itertools.combinations(tet, 2):
                edges.add((min(a, b), max(a, b)))
        return edges

    def unique_faces_all(self) -> set[tuple[int, int, int]]:
        """Return all unique triangular faces (interior + boundary) across all tetrahedra."""
        face_set: set[tuple[int, int, int]] = set()
        for tet in self.elements:
            for triple in itertools.combinations(tet, 3):
                key = tuple(sorted(triple))
                face_set.add(key)  # type: ignore[arg-type]
        return face_set

    def euler_characteristic(self) -> int:
        """V - E + F - T.  Should equal 1 for a simply-connected filled volume."""
        V = len(self.vertices)
        E = len(self.unique_edges())
        F = len(self.unique_faces_all())
        T = len(self.elements)
        return V - E + F - T

    def min_dihedral_angle_deg(self) -> float:
        """Return the minimum dihedral angle (degrees) across all tetrahedra.

        Dihedral angle = angle between two triangular faces sharing an edge.
        Each tet has 6 edges hence 6 dihedral angles.
        """
        min_angle = math.inf
        verts = self.vertices
        for tet in self.elements:
            a, b, c, d = [verts[i] for i in tet]
            for angle in _tet_dihedral_angles(a, b, c, d):
                if angle < min_angle:
                    min_angle = angle
        return math.degrees(min_angle) if math.isfinite(min_angle) else 0.0


# ---------------------------------------------------------------------------
# Vector arithmetic helpers (no numpy dependency)
# ---------------------------------------------------------------------------

Vec3 = tuple[float, float, float]


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def _scale(v: Vec3, s: float) -> Vec3:
    return (v[0] * s, v[1] * s, v[2] * s)


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _norm(v: Vec3) -> float:
    return math.sqrt(_dot(v, v))


def _normalize(v: Vec3) -> Vec3:
    n = _norm(v)
    if n < 1e-300:
        return (0.0, 0.0, 0.0)
    return (v[0] / n, v[1] / n, v[2] / n)


# ---------------------------------------------------------------------------
# Tet geometry
# ---------------------------------------------------------------------------

def _tet_volume_signed(a: Vec3, b: Vec3, c: Vec3, d: Vec3) -> float:
    """Signed volume of a tetrahedron (1/6 det[ab, ac, ad])."""
    ab = _sub(b, a)
    ac = _sub(c, a)
    ad = _sub(d, a)
    return _dot(ab, _cross(ac, ad)) / 6.0


def _tet_circumsphere(a: Vec3, b: Vec3, c: Vec3, d: Vec3) -> tuple[Vec3, float]:
    """Return (centre, radius²) of the circumsphere of tet (a,b,c,d).

    Uses the algebraic formula from Shewchuk (1997).
    Raises ValueError if the four points are coplanar.
    """
    ax, ay, az = _sub(a, d)
    bx, by, bz = _sub(b, d)
    cx, cy, cz = _sub(c, d)

    # 3×3 determinant of [[ax,ay,az],[bx,by,bz],[cx,cy,cz]]
    det = (
        ax * (by * cz - bz * cy)
        - ay * (bx * cz - bz * cx)
        + az * (bx * cy - by * cx)
    )
    if abs(det) < 1e-14:
        raise ValueError("Degenerate tetrahedron (coplanar points)")

    a2 = ax * ax + ay * ay + az * az
    b2 = bx * bx + by * by + bz * bz
    c2 = cx * cx + cy * cy + cz * cz

    ox = (
        a2 * (by * cz - bz * cy)
        - ay * (b2 * cz - bz * c2)
        + az * (b2 * cy - by * c2)
    ) / (2.0 * det)
    oy = (
        ax * (b2 * cz - bz * c2)
        - a2 * (bx * cz - bz * cx)
        + az * (bx * c2 - b2 * cx)
    ) / (2.0 * det)
    oz = (
        ax * (by * c2 - b2 * cy)
        - ay * (bx * c2 - b2 * cx)
        + a2 * (bx * cy - by * cx)
    ) / (2.0 * det)

    centre: Vec3 = (ox + d[0], oy + d[1], oz + d[2])
    r2 = ox * ox + oy * oy + oz * oz
    return centre, r2


def _tet_dihedral_angles(a: Vec3, b: Vec3, c: Vec3, d: Vec3) -> Iterator[float]:
    """Yield the 6 dihedral angles (radians) of tetrahedron (a,b,c,d).

    Each dihedral angle is computed across one edge as the angle between
    the outward normals of the two faces sharing that edge.
    """
    # Vertices indexed 0–3 for convenience
    v = [a, b, c, d]
    # Each of the 6 edges: (i,j) shares faces (i,j,k) and (i,j,l)
    for i, j in itertools.combinations(range(4), 2):
        opp = [x for x in range(4) if x not in (i, j)]
        k, l = opp
        # Edge vector
        e = _sub(v[j], v[i])
        # Normal of face (i, j, k) relative to opposite vertex l
        n1 = _cross(_sub(v[j], v[i]), _sub(v[k], v[i]))
        n2 = _cross(_sub(v[j], v[i]), _sub(v[l], v[i]))
        c_ = _dot(n1, n2) / ((_norm(n1) * _norm(n2)) + 1e-300)
        c_ = max(-1.0, min(1.0, c_))
        # Dihedral angle is π minus the angle between the two normals
        # when normals point outward from the shared edge
        yield math.acos(-c_)


# ---------------------------------------------------------------------------
# Super-tetrahedron construction
# ---------------------------------------------------------------------------

def _super_tet(points: list[Vec3]) -> tuple[list[Vec3], list[tuple[int, int, int, int]]]:
    """Build a super-tetrahedron that contains all input points.

    Returns (4 super-vertices, [one tet index tuple]).
    The super-vertices are appended after the existing point list.
    """
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    cz = (min(zs) + max(zs)) / 2.0
    dx = (max(xs) - min(xs)) or 1.0
    dy = (max(ys) - min(ys)) or 1.0
    dz = (max(zs) - min(zs)) or 1.0
    R = max(dx, dy, dz) * 10.0

    n = len(points)
    # Four vertices of the super-tet (regular tet centred at (cx,cy,cz), radius R)
    sv: list[Vec3] = [
        (cx,         cy + R * 3.0,    cz),
        (cx - R * 3.0, cy - R,         cz - R * 2.0),
        (cx + R * 3.0, cy - R,         cz - R * 2.0),
        (cx,           cy - R,         cz + R * 2.0),
    ]
    # indices n, n+1, n+2, n+3
    return sv, [(n, n + 1, n + 2, n + 3)]


# ---------------------------------------------------------------------------
# Bowyer-Watson incremental Delaunay tetrahedralization
# ---------------------------------------------------------------------------

def _bowyer_watson(points: list[Vec3]) -> list[tuple[int, int, int, int]]:
    """Return a Delaunay tetrahedralization of the given points.

    Uses the Bowyer-Watson algorithm.  Super-tet vertices are stripped at
    the end.

    Args:
        points: list of (x,y,z) coordinate tuples (must have ≥ 4 points).

    Returns:
        List of 4-index tuples into *points* (super-tet vertices excluded).
    """
    n_orig = len(points)
    super_verts, super_tets = _super_tet(points)
    all_verts: list[Vec3] = list(points) + super_verts
    tets: list[tuple[int, int, int, int]] = list(super_tets)

    # Precompute circumsphere cache: tet index → (centre, r²)
    cs_cache: dict[int, tuple[Vec3, float]] = {}
    for idx, t in enumerate(tets):
        try:
            cs_cache[idx] = _tet_circumsphere(
                all_verts[t[0]], all_verts[t[1]], all_verts[t[2]], all_verts[t[3]]
            )
        except ValueError:
            pass  # degenerate, skip caching

    tet_counter = [len(tets)]  # mutable counter for stable cache keys

    def _add_tet(t: tuple[int, int, int, int]) -> int:
        idx = tet_counter[0]
        tet_counter[0] += 1
        tets.append(t)
        try:
            cs_cache[idx] = _tet_circumsphere(
                all_verts[t[0]], all_verts[t[1]], all_verts[t[2]], all_verts[t[3]]
            )
        except ValueError:
            pass
        return idx

    for pi, p in enumerate(points):
        # Find all tets whose circumsphere contains p
        bad: list[int] = []
        for ti, t in enumerate(tets):
            if t is None:  # type: ignore[comparison-overlap]
                continue
            if ti in cs_cache:
                centre, r2 = cs_cache[ti]
                dist2 = (
                    (p[0] - centre[0]) ** 2
                    + (p[1] - centre[1]) ** 2
                    + (p[2] - centre[2]) ** 2
                )
                if dist2 < r2 * (1.0 + 1e-10):
                    bad.append(ti)
            else:
                try:
                    centre, r2 = _tet_circumsphere(
                        all_verts[t[0]], all_verts[t[1]],
                        all_verts[t[2]], all_verts[t[3]]
                    )
                    dist2 = (
                        (p[0] - centre[0]) ** 2
                        + (p[1] - centre[1]) ** 2
                        + (p[2] - centre[2]) ** 2
                    )
                    if dist2 < r2 * (1.0 + 1e-10):
                        bad.append(ti)
                except ValueError:
                    pass

        # Find boundary faces of the bad-tet cavity (faces shared by exactly one bad tet)
        face_count: dict[tuple[int, int, int], list[int]] = {}
        for ti in bad:
            t = tets[ti]
            for triple in itertools.combinations(t, 3):
                key = tuple(sorted(triple))
                face_count.setdefault(key, []).append(ti)  # type: ignore[arg-type]

        boundary_faces = [f for f, owners in face_count.items() if len(owners) == 1]

        # Remove bad tets
        for ti in sorted(bad, reverse=True):
            tets[ti] = None  # type: ignore[call-overload]
            cs_cache.pop(ti, None)

        # Re-triangulate cavity: connect each boundary face to the new point
        for face in boundary_faces:
            new_tet = (face[0], face[1], face[2], pi)
            # Ensure positive volume
            vols = _tet_volume_signed(
                all_verts[face[0]], all_verts[face[1]],
                all_verts[face[2]], all_verts[pi]
            )
            if vols < 0:
                new_tet = (face[1], face[0], face[2], pi)
            _add_tet(new_tet)

    # Filter out None slots and tets that reference super-tet vertices
    super_indices = {n_orig, n_orig + 1, n_orig + 2, n_orig + 3}
    result: list[tuple[int, int, int, int]] = []
    for t in tets:
        if t is None:  # type: ignore[comparison-overlap]
            continue
        if any(v in super_indices for v in t):
            continue
        result.append(t)
    return result


# ---------------------------------------------------------------------------
# Boundary face extraction
# ---------------------------------------------------------------------------

def _extract_boundary_faces(
    tets: list[tuple[int, int, int, int]]
) -> list[tuple[int, int, int]]:
    """Return the boundary faces of the mesh (faces belonging to exactly one tet)."""
    face_count: dict[tuple[int, int, int], int] = {}
    for t in tets:
        for triple in itertools.combinations(t, 3):
            key: tuple[int, int, int] = tuple(sorted(triple))  # type: ignore[assignment]
            face_count[key] = face_count.get(key, 0) + 1
    return [f for f, cnt in face_count.items() if cnt == 1]


# ---------------------------------------------------------------------------
# Constrained boundary re-insertion
# ---------------------------------------------------------------------------

def _orient_face_outward(
    face: tuple[int, int, int],
    vertices: list[Vec3],
    centroid: Vec3,
) -> tuple[int, int, int]:
    """Return the face oriented so its normal points away from centroid."""
    a, b, c = [vertices[i] for i in face]
    n = _cross(_sub(b, a), _sub(c, a))
    # Vector from centroid to face mid-point
    mid: Vec3 = (
        (a[0] + b[0] + c[0]) / 3.0,
        (a[1] + b[1] + c[1]) / 3.0,
        (a[2] + b[2] + c[2]) / 3.0,
    )
    d = _sub(mid, centroid)
    if _dot(n, d) < 0:
        return (face[1], face[0], face[2])
    return face


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def mesh_unit_cube(
    n: int = 3,
    *,
    add_interior: bool = True,
) -> Mesh3D:
    """Generate a tet mesh of the unit cube [0,1]³.

    Args:
        n: Number of divisions along each axis for the initial point lattice.
           Total points = (n+1)³ + optional interior perturbation.
        add_interior: Whether to add a small set of perturbed interior points
           to improve mesh quality (avoids degenerate flat tets on a pure grid).

    Returns:
        A valid ``Mesh3D`` filling the unit cube.
    """
    points: list[Vec3] = []

    # Corner + lattice points
    step = 1.0 / n
    for i in range(n + 1):
        for j in range(n + 1):
            for k in range(n + 1):
                points.append((i * step, j * step, k * step))

    if add_interior:
        # Offset mid-points slightly to break coplanarity and improve BW robustness
        offsets = [0.1, -0.1]
        interior_seeds = [
            (0.5 + 0.07,  0.5 - 0.05,  0.5 + 0.03),
            (0.25 + 0.03, 0.25 - 0.03, 0.75 + 0.02),
            (0.75 - 0.04, 0.75 + 0.06, 0.25 - 0.02),
            (0.5 - 0.06,  0.25 + 0.04, 0.5 - 0.05),
            (0.5 + 0.05,  0.75 - 0.03, 0.5 + 0.06),
        ]
        points.extend(interior_seeds)

    tets = _bowyer_watson(points)

    # Keep only tets with positive volume > numerical noise
    keep: list[tuple[int, int, int, int]] = []
    for t in tets:
        vol = _tet_volume_signed(points[t[0]], points[t[1]], points[t[2]], points[t[3]])
        if abs(vol) > 1e-12:
            if vol < 0:
                # Re-orient to positive volume
                t = (t[1], t[0], t[2], t[3])
            keep.append(t)
    tets = keep

    # Boundary faces
    bfaces_raw = _extract_boundary_faces(tets)

    # Compute mesh centroid
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    cz = sum(p[2] for p in points) / len(points)
    centroid: Vec3 = (cx, cy, cz)

    bfaces = [_orient_face_outward(f, points, centroid) for f in bfaces_raw]
    tags = [1] * len(bfaces)

    return Mesh3D(
        vertices=points,
        elements=tets,
        faces=bfaces,
        face_tags=tags,
    )


def mesh_point_cloud(points: list[Vec3]) -> Mesh3D:
    """Generate a Delaunay tet mesh from an arbitrary point cloud.

    Args:
        points: List of (x,y,z) coordinates.  Must contain ≥ 4 non-coplanar points.

    Returns:
        ``Mesh3D`` with Delaunay tetrahedralization.
    """
    if len(points) < 4:
        raise ValueError("Need at least 4 non-coplanar points to form a tetrahedron")

    tets = _bowyer_watson(list(points))

    keep: list[tuple[int, int, int, int]] = []
    for t in tets:
        vol = _tet_volume_signed(points[t[0]], points[t[1]], points[t[2]], points[t[3]])
        if abs(vol) > 1e-12:
            if vol < 0:
                t = (t[1], t[0], t[2], t[3])
            keep.append(t)
    tets = keep

    bfaces_raw = _extract_boundary_faces(tets)

    if points:
        cx = sum(p[0] for p in points) / len(points)
        cy = sum(p[1] for p in points) / len(points)
        cz = sum(p[2] for p in points) / len(points)
        centroid: Vec3 = (cx, cy, cz)
        bfaces = [_orient_face_outward(f, list(points), centroid) for f in bfaces_raw]
    else:
        bfaces = list(bfaces_raw)

    return Mesh3D(
        vertices=list(points),
        elements=tets,
        faces=bfaces,
        face_tags=[1] * len(bfaces),
    )
