"""B-rep / NURBS topology data model, Euler operators, and validation.

This module is the *topology* keystone for the kerf CAD kernel. The
``geom`` package already contains rich NURBS geometry (``nurbs.py``,
``intersection.py``, ``surface_boolean_robust.py`` ...) but no topology
layer that ties geometric entities into a consistent, validatable
boundary representation. ``brep.py`` provides exactly that:

  * The classic radial-edge-ish topology hierarchy
    ``Body -> Solid -> Shell -> Face -> Loop -> Coedge -> Edge -> Vertex``
    with parametric geometry attached at ``Edge`` (curve) and ``Face``
    (surface) level.
  * Analytic primitive constructors (``make_box``, ``make_cylinder``,
    ``make_sphere``, ``make_tetra``) that express primitives *as*
    B-reps with planar / analytic faces.
  * The Euler operators ``mvfs / mev / mef / kemr / kfmrh`` (and their
    inverses) that mutate topology while preserving the
    Euler-Poincare invariant.
  * ``validate_body`` -- a structural + tolerance + manifold checker.

The geometry layer is treated as opaque. A curve is anything with an
``evaluate(t) -> np.ndarray`` method (``NurbsCurve`` qualifies, as do
the lightweight analytic helpers below). A surface is anything with an
``evaluate(u, v) -> np.ndarray`` and ``normal(u, v) -> np.ndarray``
(``NurbsSurface`` qualifies via the adapter; analytic surfaces below
implement both directly). No existing geom module is modified.

------------------------------------------------------------------
THE EULER-POINCARE INVARIANT ENFORCED
------------------------------------------------------------------
For a B-rep ``Body`` we enforce the generalised Euler-Poincare
relation::

    V - E + F - (L - F) - 2*(S - G) = 0

equivalently, writing ``H = L - F`` for the number of *extra* interior
loops (ring/hole loops beyond the one mandatory outer loop per face)::

    V - E + F - H = 2 * (S - G)

where:

  * ``V`` = number of distinct vertices
  * ``E`` = number of distinct edges
  * ``F`` = number of faces
  * ``L`` = total number of loops over all faces
  * ``H = L - F`` = number of inner/ring loops (holes); each face
    contributes exactly one outer loop, every additional loop is a hole
  * ``S`` = number of shells (an open wire/solid still counts its
    shells; for a single closed solid ``S = 1``)
  * ``G`` = genus (number of through-holes / handles); a sphere/box
    has ``G = 0``, a torus has ``G = 1``

This is the standard form (see Mantyla, *An Introduction to Solid
Modeling*, eq. for the Euler-Poincare formula with shells and genus).
The five Euler operators below each change the tuple
``(V, E, F, L, S, G)`` by a vector that leaves the left-hand side at
zero, so the invariant is a loop/operator-level guarantee, and
``validate_body`` re-checks it globally.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Union

import numpy as np

# ---------------------------------------------------------------------------
# Geometry adapters (analytic surfaces / curves usable without OCCT or NURBS)
# ---------------------------------------------------------------------------


@dataclass
class Line3:
    """Analytic straight segment ``p0 + t*(p1 - p0)`` for ``t`` in [0, 1]."""

    p0: np.ndarray
    p1: np.ndarray

    def __post_init__(self):
        self.p0 = np.asarray(self.p0, dtype=float)
        self.p1 = np.asarray(self.p1, dtype=float)

    def evaluate(self, t: float) -> np.ndarray:
        return self.p0 + float(t) * (self.p1 - self.p0)

    def derivative(self, t: float, order: int = 1) -> np.ndarray:  # noqa: ARG002
        if order == 1:
            return self.p1 - self.p0
        return np.zeros(3)


@dataclass
class CircleArc3:
    """Analytic circular arc on a plane defined by center + two axes."""

    center: np.ndarray
    radius: float
    x_axis: np.ndarray
    y_axis: np.ndarray
    t0: float = 0.0
    t1: float = 2.0 * math.pi

    def __post_init__(self):
        self.center = np.asarray(self.center, dtype=float)
        self.x_axis = _unit(np.asarray(self.x_axis, dtype=float))
        self.y_axis = _unit(np.asarray(self.y_axis, dtype=float))

    def evaluate(self, t: float) -> np.ndarray:
        return (
            self.center
            + self.radius * math.cos(t) * self.x_axis
            + self.radius * math.sin(t) * self.y_axis
        )


@dataclass
class Plane:
    """Analytic plane: ``origin + u*x_axis + v*y_axis``."""

    origin: np.ndarray
    x_axis: np.ndarray
    y_axis: np.ndarray

    def __post_init__(self):
        self.origin = np.asarray(self.origin, dtype=float)
        self.x_axis = _unit(np.asarray(self.x_axis, dtype=float))
        self.y_axis = _unit(np.asarray(self.y_axis, dtype=float))
        self._n = _unit(np.cross(self.x_axis, self.y_axis))

    def evaluate(self, u: float, v: float) -> np.ndarray:
        return self.origin + u * self.x_axis + v * self.y_axis

    def normal(self, u: float = 0.0, v: float = 0.0) -> np.ndarray:  # noqa: ARG002
        return self._n


@dataclass
class CylinderSurface:
    """Analytic cylinder. ``u`` is angle, ``v`` is height along axis."""

    center: np.ndarray
    axis: np.ndarray
    radius: float
    x_ref: Optional[np.ndarray] = None

    def __post_init__(self):
        self.center = np.asarray(self.center, dtype=float)
        self.axis = _unit(np.asarray(self.axis, dtype=float))
        if self.x_ref is None:
            self.x_ref = _perp(self.axis)
        self.x_ref = _unit(np.asarray(self.x_ref, dtype=float))
        self._y = _unit(np.cross(self.axis, self.x_ref))

    def evaluate(self, u: float, v: float) -> np.ndarray:
        return (
            self.center
            + self.radius * math.cos(u) * self.x_ref
            + self.radius * math.sin(u) * self._y
            + v * self.axis
        )

    def normal(self, u: float, v: float = 0.0) -> np.ndarray:  # noqa: ARG002
        return _unit(math.cos(u) * self.x_ref + math.sin(u) * self._y)


@dataclass
class SphereSurface:
    """Analytic sphere. ``u`` longitude [0, 2pi], ``v`` latitude [-pi/2, pi/2]."""

    center: np.ndarray
    radius: float

    def __post_init__(self):
        self.center = np.asarray(self.center, dtype=float)

    def evaluate(self, u: float, v: float) -> np.ndarray:
        cv = math.cos(v)
        return self.center + self.radius * np.array(
            [cv * math.cos(u), cv * math.sin(u), math.sin(v)]
        )

    def normal(self, u: float, v: float) -> np.ndarray:
        return _unit(self.evaluate(u, v) - self.center)


@dataclass
class TorusSurface:
    """Analytic torus. ``u`` major angle, ``v`` minor angle (both [0, 2pi])."""

    center: np.ndarray
    axis: np.ndarray
    major_radius: float
    minor_radius: float

    def __post_init__(self):
        self.center = np.asarray(self.center, dtype=float)
        self.axis = _unit(np.asarray(self.axis, dtype=float))
        self._x = _perp(self.axis)
        self._y = _unit(np.cross(self.axis, self._x))

    def _ring_dir(self, u: float) -> np.ndarray:
        return math.cos(u) * self._x + math.sin(u) * self._y

    def evaluate(self, u: float, v: float) -> np.ndarray:
        rdir = self._ring_dir(u)
        return (
            self.center
            + (self.major_radius + self.minor_radius * math.cos(v)) * rdir
            + self.minor_radius * math.sin(v) * self.axis
        )

    def normal(self, u: float, v: float) -> np.ndarray:
        rdir = self._ring_dir(u)
        return _unit(math.cos(v) * rdir + math.sin(v) * self.axis)


def _unit(v: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(v)
    return v / n if n > 1e-14 else v


def _perp(axis: np.ndarray) -> np.ndarray:
    ref = np.array([1.0, 0.0, 0.0])
    if abs(np.dot(ref, axis)) > 0.9:
        ref = np.array([0.0, 1.0, 0.0])
    return _unit(np.cross(axis, ref))


# ---------------------------------------------------------------------------
# Topology entities
# ---------------------------------------------------------------------------

_ID = itertools.count(1)


@dataclass(eq=False)
class Vertex:
    """A topological point with a positional tolerance."""

    point: np.ndarray
    tol: float = 1e-7

    def __post_init__(self):
        self.point = np.asarray(self.point, dtype=float)
        self.id = next(_ID)

    def coincident(self, other: "Vertex") -> bool:
        return bool(
            np.linalg.norm(self.point - other.point) <= max(self.tol, other.tol)
        )

    def __repr__(self):  # pragma: no cover - debug aid
        return f"Vertex#{self.id}({self.point.tolist()})"


@dataclass(eq=False)
class Edge:
    """A bounded curve segment between two vertices.

    ``curve`` is any object with ``evaluate(t) -> np.ndarray`` (a
    :class:`NurbsCurve`, :class:`Line3`, :class:`CircleArc3`, ...).
    The parametric range ``[t0, t1]`` clips the underlying curve.
    """

    curve: object
    t0: float
    t1: float
    v_start: Vertex
    v_end: Vertex
    tol: float = 1e-7

    def __post_init__(self):
        self.id = next(_ID)
        # coedges referencing this edge (filled in by Coedge)
        self.coedges: List["Coedge"] = []

    def point(self, t: float) -> np.ndarray:
        return np.asarray(self.curve.evaluate(t), dtype=float)

    def start_point(self) -> np.ndarray:
        return np.asarray(self.v_start.point, dtype=float)

    def end_point(self) -> np.ndarray:
        return np.asarray(self.v_end.point, dtype=float)

    def length(self, samples: int = 24) -> float:
        ts = np.linspace(self.t0, self.t1, samples)
        pts = np.array([self.point(t) for t in ts])
        return float(np.sum(np.linalg.norm(np.diff(pts, axis=0), axis=1)))

    def __repr__(self):  # pragma: no cover - debug aid
        return f"Edge#{self.id}(v{self.v_start.id}->v{self.v_end.id})"


@dataclass(eq=False)
class Coedge:
    """An oriented use of an :class:`Edge` within a :class:`Loop`.

    ``orientation`` is ``True`` when the coedge traverses the edge in
    its natural direction (``v_start -> v_end``), ``False`` otherwise.
    ``next``/``prev`` form the loop's circular linked list.
    """

    edge: Edge
    orientation: bool
    loop: Optional["Loop"] = None
    next: Optional["Coedge"] = None
    prev: Optional["Coedge"] = None

    def __post_init__(self):
        self.id = next(_ID)
        if self not in self.edge.coedges:
            self.edge.coedges.append(self)

    def start_vertex(self) -> Vertex:
        return self.edge.v_start if self.orientation else self.edge.v_end

    def end_vertex(self) -> Vertex:
        return self.edge.v_end if self.orientation else self.edge.v_start

    def start_point(self) -> np.ndarray:
        return self.edge.start_point() if self.orientation else self.edge.end_point()

    def end_point(self) -> np.ndarray:
        return self.edge.end_point() if self.orientation else self.edge.start_point()

    def __repr__(self):  # pragma: no cover - debug aid
        d = "+" if self.orientation else "-"
        return f"Coedge#{self.id}({d}E{self.edge.id})"


@dataclass(eq=False)
class Loop:
    """A closed circuit of coedges bounding (part of) a face."""

    coedges: List[Coedge] = field(default_factory=list)
    is_outer: bool = True
    face: Optional["Face"] = None

    def __post_init__(self):
        self.id = next(_ID)
        self._relink()

    def _relink(self) -> None:
        n = len(self.coedges)
        for i, ce in enumerate(self.coedges):
            ce.loop = self
            ce.next = self.coedges[(i + 1) % n] if n else None
            ce.prev = self.coedges[(i - 1) % n] if n else None

    def add_coedge(self, ce: Coedge) -> None:
        self.coedges.append(ce)
        self._relink()

    def vertices(self) -> List[Vertex]:
        return [ce.start_vertex() for ce in self.coedges]

    def __repr__(self):  # pragma: no cover - debug aid
        kind = "outer" if self.is_outer else "inner"
        return f"Loop#{self.id}({kind},{len(self.coedges)}ce)"


@dataclass(eq=False)
class Face:
    """A bounded region of a surface, bounded by one outer + N inner loops."""

    surface: object
    loops: List[Loop] = field(default_factory=list)
    orientation: bool = True
    tol: float = 1e-7

    def __post_init__(self):
        self.id = next(_ID)
        for lp in self.loops:
            lp.face = self
        self.shell: Optional["Shell"] = None

    def outer_loop(self) -> Optional[Loop]:
        for lp in self.loops:
            if lp.is_outer:
                return lp
        return self.loops[0] if self.loops else None

    def inner_loops(self) -> List[Loop]:
        outer = self.outer_loop()
        return [lp for lp in self.loops if lp is not outer]

    def add_loop(self, lp: Loop) -> None:
        lp.face = self
        self.loops.append(lp)

    def surface_normal(self, u: float = 0.5, v: float = 0.5) -> np.ndarray:
        n = _surface_normal(self.surface, u, v)
        return n if self.orientation else -n

    def __repr__(self):  # pragma: no cover - debug aid
        return f"Face#{self.id}({len(self.loops)}L)"


@dataclass(eq=False)
class Shell:
    """A connected set of faces. Closed shell => watertight 2-manifold."""

    faces: List[Face] = field(default_factory=list)
    is_closed: bool = True

    def __post_init__(self):
        self.id = next(_ID)
        for f in self.faces:
            f.shell = self
        self.solid: Optional["Solid"] = None

    def add_face(self, f: Face) -> None:
        f.shell = self
        self.faces.append(f)

    def edges(self) -> List[Edge]:
        seen, out = set(), []
        for f in self.faces:
            for lp in f.loops:
                for ce in lp.coedges:
                    if id(ce.edge) not in seen:
                        seen.add(id(ce.edge))
                        out.append(ce.edge)
        return out

    def vertices(self) -> List[Vertex]:
        seen, out = set(), []
        for e in self.edges():
            for v in (e.v_start, e.v_end):
                if id(v) not in seen:
                    seen.add(id(v))
                    out.append(v)
        return out

    def __repr__(self):  # pragma: no cover - debug aid
        c = "closed" if self.is_closed else "open"
        return f"Shell#{self.id}({c},{len(self.faces)}F)"


@dataclass(eq=False)
class Solid:
    """A volume: ``shells[0]`` is the outer shell, the rest are voids."""

    shells: List[Shell] = field(default_factory=list)

    def __post_init__(self):
        self.id = next(_ID)
        for sh in self.shells:
            sh.solid = self

    @property
    def outer_shell(self) -> Optional[Shell]:
        return self.shells[0] if self.shells else None

    @property
    def void_shells(self) -> List[Shell]:
        return self.shells[1:]

    def __repr__(self):  # pragma: no cover - debug aid
        return f"Solid#{self.id}({len(self.shells)}sh)"


@dataclass(eq=False)
class Body:
    """Top-level container: solids, free shells (sheets), and free wires."""

    solids: List[Solid] = field(default_factory=list)
    shells: List[Shell] = field(default_factory=list)
    wires: List[Loop] = field(default_factory=list)

    def __post_init__(self):
        self.id = next(_ID)

    # --- aggregate accessors -------------------------------------------------

    def all_shells(self) -> List[Shell]:
        out = list(self.shells)
        for s in self.solids:
            out.extend(s.shells)
        return out

    def all_faces(self) -> List[Face]:
        out: List[Face] = []
        for sh in self.all_shells():
            out.extend(sh.faces)
        return out

    def all_loops(self) -> List[Loop]:
        out: List[Loop] = []
        for f in self.all_faces():
            out.extend(f.loops)
        out.extend(self.wires)
        return out

    def all_coedges(self) -> List[Coedge]:
        out: List[Coedge] = []
        for lp in self.all_loops():
            out.extend(lp.coedges)
        return out

    def all_edges(self) -> List[Edge]:
        seen, out = set(), []
        for ce in self.all_coedges():
            if id(ce.edge) not in seen:
                seen.add(id(ce.edge))
                out.append(ce.edge)
        return out

    def all_vertices(self) -> List[Vertex]:
        seen, out = set(), []
        for e in self.all_edges():
            for v in (e.v_start, e.v_end):
                if id(v) not in seen:
                    seen.add(id(v))
                    out.append(v)
        # an mvfs seed face holds an empty loop whose only vertex is
        # not reachable through edges; count it explicitly
        for lp in self.all_loops():
            av = getattr(lp, "_anchor_vertex", None)
            if av is not None and not lp.coedges and id(av) not in seen:
                seen.add(id(av))
                out.append(av)
        return out

    # --- Euler-Poincare bookkeeping -----------------------------------------

    def euler_counts(self) -> dict:
        V = len(self.all_vertices())
        E = len(self.all_edges())
        faces = self.all_faces()
        F = len(faces)
        L = sum(len(f.loops) for f in faces)
        H = L - F  # interior (ring) loops; one outer loop per face is free
        S = len(self.all_shells())
        G = self.genus()
        return {"V": V, "E": E, "F": F, "L": L, "H": H, "S": S, "G": G}

    def genus(self) -> int:
        """Genus derived from the Euler characteristic of closed shells.

        For each closed 2-manifold shell, ``chi = V - E + F`` and
        ``genus = (2 - chi) / 2``. We sum per-shell genus; open shells
        and wires contribute zero (their handles are not well-defined as
        closed surfaces).
        """
        g = 0
        for sh in self.all_shells():
            if not sh.is_closed:
                continue
            sv = len(sh.vertices())
            se = len(sh.edges())
            sf = len(sh.faces)
            sl = sum(len(f.loops) for f in sh.faces)
            sh_h = sl - sf
            chi = sv - se + sf - sh_h
            g += max(0, (2 - chi) // 2)
        return g

    def euler_poincare_residual(self) -> int:
        """V - E + F - H - 2*(S - G); zero for a valid B-rep."""
        c = self.euler_counts()
        return c["V"] - c["E"] + c["F"] - c["H"] - 2 * (c["S"] - c["G"])

    def satisfies_euler_poincare(self) -> bool:
        return self.euler_poincare_residual() == 0

    def __repr__(self):  # pragma: no cover - debug aid
        return (
            f"Body#{self.id}({len(self.solids)}sol,"
            f"{len(self.shells)}sh,{len(self.wires)}w)"
        )


# ---------------------------------------------------------------------------
# Surface-normal helper (works for analytic + NURBS surfaces)
# ---------------------------------------------------------------------------


def _surface_normal(surface: object, u: float, v: float) -> np.ndarray:
    if hasattr(surface, "normal"):
        return _unit(np.asarray(surface.normal(u, v), dtype=float))
    # finite-difference fallback (NurbsSurface etc.)
    h = 1e-5
    p = np.asarray(surface.evaluate(u, v), dtype=float)
    du = np.asarray(surface.evaluate(u + h, v), dtype=float) - p
    dv = np.asarray(surface.evaluate(u, v + h), dtype=float) - p
    return _unit(np.cross(du, dv))


# ---------------------------------------------------------------------------
# Analytic primitive constructors (primitives expressed as B-reps)
# ---------------------------------------------------------------------------


def _planar_quad_face(corners: Sequence[np.ndarray], vertices, edges) -> Face:
    """Build a planar quad face from 4 ordered corner vertices + edges.

    ``edges`` is a list of 4 (Edge, orientation) tuples already created
    by the caller so shared edges are reused across faces.
    """
    p0, p1, p2 = (vertices[i].point for i in range(3))
    plane = Plane(origin=p0, x_axis=p1 - p0, y_axis=p2 - p0)
    coedges = [Coedge(e, o) for (e, o) in edges]
    loop = Loop(coedges, is_outer=True)
    return Face(plane, [loop], orientation=True)


def make_box(
    origin=(0.0, 0.0, 0.0),
    size=(1.0, 1.0, 1.0),
    tol: float = 1e-7,
) -> Body:
    """Axis-aligned box as a closed planar-faced B-rep solid (V8 E12 F6)."""
    ox, oy, oz = origin
    sx, sy, sz = size
    P = [
        np.array([ox, oy, oz]),
        np.array([ox + sx, oy, oz]),
        np.array([ox + sx, oy + sy, oz]),
        np.array([ox, oy + sy, oz]),
        np.array([ox, oy, oz + sz]),
        np.array([ox + sx, oy, oz + sz]),
        np.array([ox + sx, oy + sy, oz + sz]),
        np.array([ox, oy + sy, oz + sz]),
    ]
    V = [Vertex(p, tol) for p in P]

    def mk_edge(a: int, b: int) -> Edge:
        return Edge(Line3(P[a], P[b]), 0.0, 1.0, V[a], V[b], tol)

    # 12 unique edges, indexed by ordered vertex pair
    edef = [
        (0, 1), (1, 2), (2, 3), (3, 0),  # bottom
        (4, 5), (5, 6), (6, 7), (7, 4),  # top
        (0, 4), (1, 5), (2, 6), (3, 7),  # verticals
    ]
    E = {pair: mk_edge(*pair) for pair in edef}

    def edge_for(a: int, b: int):
        if (a, b) in E:
            return E[(a, b)], True
        return E[(b, a)], False

    # face = ordered CCW vertex ring (outward normal)
    face_rings = [
        [0, 3, 2, 1],  # bottom (z-)
        [4, 5, 6, 7],  # top (z+)
        [0, 1, 5, 4],  # front (y-)
        [1, 2, 6, 5],  # right (x+)
        [2, 3, 7, 6],  # back (y+)
        [3, 0, 4, 7],  # left (x-)
    ]
    faces: List[Face] = []
    for ring in face_rings:
        ce = []
        for i in range(4):
            a, b = ring[i], ring[(i + 1) % 4]
            e, o = edge_for(a, b)
            ce.append(Coedge(e, o))
        loop = Loop(ce, is_outer=True)
        p0, p1, p2 = P[ring[0]], P[ring[1]], P[ring[3]]
        plane = Plane(origin=p0, x_axis=p1 - p0, y_axis=p2 - p0)
        faces.append(Face(plane, [loop], orientation=True, tol=tol))

    shell = Shell(faces, is_closed=True)
    return Body(solids=[Solid([shell])])


def make_tetra(
    p0=(0.0, 0.0, 0.0),
    p1=(1.0, 0.0, 0.0),
    p2=(0.0, 1.0, 0.0),
    p3=(0.0, 0.0, 1.0),
    tol: float = 1e-7,
) -> Body:
    """Tetrahedron as closed planar-faced B-rep solid (V4 E6 F4)."""
    P = [np.asarray(p, dtype=float) for p in (p0, p1, p2, p3)]
    V = [Vertex(p, tol) for p in P]
    epairs = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
    E = {pr: Edge(Line3(P[pr[0]], P[pr[1]]), 0.0, 1.0, V[pr[0]], V[pr[1]], tol)
         for pr in epairs}

    centroid = sum(P) / 4.0

    def edge_for(a, b):
        if (a, b) in E:
            return E[(a, b)], True
        return E[(b, a)], False

    tri_rings = [[0, 1, 2], [0, 3, 1], [0, 2, 3], [1, 3, 2]]
    faces = []
    for ring in tri_rings:
        a, b, c = (P[i] for i in ring)
        nrm = _unit(np.cross(b - a, c - a))
        face_centroid = (a + b + c) / 3.0
        # ensure outward orientation
        if np.dot(nrm, face_centroid - centroid) < 0:
            ring = [ring[0], ring[2], ring[1]]
        ce = []
        for i in range(3):
            x, y = ring[i], ring[(i + 1) % 3]
            e, o = edge_for(x, y)
            ce.append(Coedge(e, o))
        loop = Loop(ce, is_outer=True)
        pa, pb, pc = P[ring[0]], P[ring[1]], P[ring[2]]
        plane = Plane(origin=pa, x_axis=pb - pa, y_axis=pc - pa)
        faces.append(Face(plane, [loop], orientation=True, tol=tol))

    shell = Shell(faces, is_closed=True)
    return Body(solids=[Solid([shell])])


def make_cylinder(
    center=(0.0, 0.0, 0.0),
    axis=(0.0, 0.0, 1.0),
    radius: float = 1.0,
    height: float = 1.0,
    tol: float = 1e-7,
) -> Body:
    """Closed cylinder: 1 lateral analytic face + 2 planar caps.

    Topology: 2 vertices (seam endpoints), 3 edges (two circular cap
    rims + one straight seam), 3 faces (side + 2 caps), 4 loops
    (side has 2 loops -- it is a tube whose two rims are separate
    loops sharing the seam coedges; each cap has 1 loop). This still
    satisfies V-E+F-H-2(S-G)=0 with S=1, G=0.
    """
    c = np.asarray(center, dtype=float)
    ax = _unit(np.asarray(axis, dtype=float))
    xref = _perp(ax)
    yref = _unit(np.cross(ax, xref))
    top_c = c + height * ax

    cyl = CylinderSurface(c, ax, radius, xref)
    bottom_plane = Plane(origin=c, x_axis=xref, y_axis=yref)
    top_plane = Plane(origin=top_c, x_axis=xref, y_axis=-yref)

    seam_b = c + radius * xref
    seam_t = top_c + radius * xref
    vb = Vertex(seam_b, tol)
    vt = Vertex(seam_t, tol)

    bottom_circle = CircleArc3(c, radius, xref, yref, 0.0, 2 * math.pi)
    top_circle = CircleArc3(top_c, radius, xref, yref, 0.0, 2 * math.pi)
    e_bottom = Edge(bottom_circle, 0.0, 2 * math.pi, vb, vb, tol)
    e_top = Edge(top_circle, 0.0, 2 * math.pi, vt, vt, tol)
    e_seam = Edge(Line3(seam_b, seam_t), 0.0, 1.0, vb, vt, tol)

    # lateral face: closed cycle bottom(+) -> seam(+) -> top(-) -> seam(-)
    side_loop = Loop(
        [
            Coedge(e_bottom, True),
            Coedge(e_seam, True),
            Coedge(e_top, False),
            Coedge(e_seam, False),
        ],
        is_outer=True,
    )
    side_face = Face(cyl, [side_loop], orientation=True, tol=tol)

    bottom_face = Face(
        bottom_plane, [Loop([Coedge(e_bottom, False)], is_outer=True)],
        orientation=True, tol=tol,
    )
    top_face = Face(
        top_plane, [Loop([Coedge(e_top, True)], is_outer=True)],
        orientation=True, tol=tol,
    )

    shell = Shell([side_face, bottom_face, top_face], is_closed=True)
    return Body(solids=[Solid([shell])])


def make_sphere(
    center=(0.0, 0.0, 0.0),
    radius: float = 1.0,
    tol: float = 1e-7,
) -> Body:
    """Closed sphere as a single analytic face with a degenerate seam.

    A sphere needs only one face. We model the parametric seam (a
    meridian) as one edge between the two poles, with the face's single
    loop traversing the seam forward then backward (pole singular
    points collapse). V=2 (poles), E=1 (seam), F=1, L=1, H=0, S=1,
    G=0  =>  2-1+1-0-2(1-0) = 0.
    """
    c = np.asarray(center, dtype=float)
    sph = SphereSurface(c, radius)
    north = Vertex(c + np.array([0.0, 0.0, radius]), tol)
    south = Vertex(c - np.array([0.0, 0.0, radius]), tol)

    # seam meridian at u=0 from south pole (v=-pi/2) to north (v=+pi/2)
    class _Meridian:
        def evaluate(self, t: float) -> np.ndarray:
            v = -math.pi / 2 + t * math.pi
            return sph.evaluate(0.0, v)

    seam = Edge(_Meridian(), 0.0, 1.0, south, north, tol)
    loop = Loop([Coedge(seam, True), Coedge(seam, False)], is_outer=True)
    face = Face(sph, [loop], orientation=True, tol=tol)
    shell = Shell([face], is_closed=True)
    return Body(solids=[Solid([shell])])


def make_torus(
    center=(0.0, 0.0, 0.0),
    axis=(0.0, 0.0, 1.0),
    major_radius: float = 2.0,
    minor_radius: float = 0.5,
    tol: float = 1e-7,
) -> Body:
    """Closed torus (genus-1) as one analytic face with 2 seam edges.

    The torus surface is doubly periodic; we cut it along one major
    seam and one minor seam. Topology: V=1, E=2, F=1, L=1, H=0, S=1,
    and the closed-shell Euler characteristic gives genus G=1, so
    V-E+F-H-2(S-G) = 1-2+1-0-2(1-1) = 0.
    """
    c = np.asarray(center, dtype=float)
    ax = _unit(np.asarray(axis, dtype=float))
    tor = TorusSurface(c, ax, major_radius, minor_radius)
    corner = Vertex(tor.evaluate(0.0, 0.0), tol)

    class _MajorSeam:
        def evaluate(self, t: float) -> np.ndarray:
            return tor.evaluate(t * 2 * math.pi, 0.0)

    class _MinorSeam:
        def evaluate(self, t: float) -> np.ndarray:
            return tor.evaluate(0.0, t * 2 * math.pi)

    e_major = Edge(_MajorSeam(), 0.0, 1.0, corner, corner, tol)
    e_minor = Edge(_MinorSeam(), 0.0, 1.0, corner, corner, tol)
    # canonical torus loop: a b a^-1 b^-1 (commutator) -> genus 1
    loop = Loop(
        [
            Coedge(e_major, True),
            Coedge(e_minor, True),
            Coedge(e_major, False),
            Coedge(e_minor, False),
        ],
        is_outer=True,
    )
    face = Face(tor, [loop], orientation=True, tol=tol)
    shell = Shell([face], is_closed=True)
    return Body(solids=[Solid([shell])])


# ---------------------------------------------------------------------------
# Euler operators
# ---------------------------------------------------------------------------
#
# Each operator mutates topology by a delta vector on (V, E, F, L, S)
# that keeps  V - E + F - (L - F) - 2*(S - G) = 0  invariant (genus G
# only changes via kfmrh / its inverse). The deltas:
#
#   mvfs  : +1 V, +1 F, +1 L, +1 S          (make vertex-face-shell)
#   mev   : +1 V, +1 E                      (make edge-vertex)
#   mef   : +1 E, +1 F, +1 L                (make edge-face)
#   kemr  : -1 E, +1 L  (make ring: kill edge, make loop) inverse=memr
#   kfmrh : -1 F, -1 L, +1 G  (kill face, make ring + hole/handle)
#
# All five (and inverses) individually preserve the residual; this is
# asserted by the test-suite by applying each op and revalidating.


class EulerError(RuntimeError):
    """Raised when an Euler operator is applied to inconsistent topology."""


def mvfs(point, tol: float = 1e-7) -> tuple:
    """Make Vertex-Face-Shell: seed an empty body with one point.

    Returns ``(body, solid, shell, face, loop, vertex)``. The face is a
    degenerate point-face (no edges yet); subsequent ``mev``/``mef``
    grow real geometry. Delta: V+1, F+1, L+1, S+1 -> residual unchanged
    (1 - 0 + 1 - 0 - 2*(1-0) = 0).
    """
    v = Vertex(np.asarray(point, dtype=float), tol)
    loop = Loop([], is_outer=True)
    face = Face(_PointSurface(v.point), [loop], orientation=True, tol=tol)
    shell = Shell([face], is_closed=False)
    body = Body(solids=[Solid([shell])])
    loop._anchor_vertex = v  # noqa: SLF001 - bookkeeping for empty loop
    return body, shell.solid, shell, face, loop, v


@dataclass
class _PointSurface:
    """Degenerate surface used by an mvfs seed face (no real geometry)."""

    p: np.ndarray

    def evaluate(self, u: float = 0.0, v: float = 0.0) -> np.ndarray:  # noqa: ARG002
        return self.p

    def normal(self, u: float = 0.0, v: float = 0.0) -> np.ndarray:  # noqa: ARG002
        return np.array([0.0, 0.0, 1.0])


def mev(loop: Loop, v_from: Vertex, new_point, curve=None, tol: float = 1e-7):
    """Make Edge-Vertex: spur a new vertex + edge off ``v_from``.

    A new vertex ``v_new`` and edge ``v_from->v_new`` are created and
    two coedges (forward + reverse) are spliced into ``loop`` so the
    loop stays a closed cycle (the spur is walked out and back).
    Delta: V+1, E+1, L unchanged -> residual unchanged. Returns
    ``(edge, v_new)``.
    """
    v_new = Vertex(np.asarray(new_point, dtype=float), tol)
    if curve is None:
        curve = Line3(v_from.point, v_new.point)
    edge = Edge(curve, 0.0, 1.0, v_from, v_new, tol)
    ce_fwd = Coedge(edge, True, loop)
    ce_rev = Coedge(edge, False, loop)
    if not loop.coedges:
        # the loop's anchor vertex is now reachable via the new edge;
        # drop the explicit anchor so it is not double counted
        if getattr(loop, "_anchor_vertex", None) is not None:
            loop._anchor_vertex = None
        loop.coedges = [ce_fwd, ce_rev]
    else:
        # splice the spur after a coedge that ends at v_from
        insert_at = len(loop.coedges)
        for i, ce in enumerate(loop.coedges):
            if ce.end_vertex() is v_from:
                insert_at = i + 1
                break
        loop.coedges[insert_at:insert_at] = [ce_fwd, ce_rev]
    loop._relink()
    return edge, v_new


def kev(loop: Loop, edge: Edge) -> None:
    """Kill Edge-Vertex: inverse of :func:`mev`.

    Removes both coedges of ``edge`` from ``loop`` and detaches the
    spur's terminal vertex. Delta: V-1, E-1 -> residual unchanged.
    """
    survivors = [ce for ce in loop.coedges if ce.edge is not edge]
    if len(survivors) == len(loop.coedges):
        raise EulerError("kev: edge not in loop")
    loop.coedges = survivors
    loop._relink()
    edge.coedges = [ce for ce in edge.coedges if ce.loop is not loop]
    # if the loop is emptied back to an mvfs-style seed, re-anchor its
    # surviving vertex so V bookkeeping is symmetric with mev
    if not loop.coedges:
        loop._anchor_vertex = edge.v_start


def mef(loop: Loop, ce_a: Coedge, ce_b: Coedge, surface=None,
        tol: float = 1e-7) -> tuple:
    """Make Edge-Face: split a loop into two by a new bridging edge.

    A new edge connects ``ce_a.start_vertex()`` to
    ``ce_b.start_vertex()``; ``loop`` is split into the original loop
    (kept) and a new loop forming a new face. Delta: E+1, F+1, L+1 ->
    residual unchanged. Returns ``(new_edge, new_face)``.
    """
    ces = loop.coedges
    ia = ces.index(ce_a)
    ib = ces.index(ce_b)
    if ia == ib:
        raise EulerError("mef: identical split coedges")
    if ia > ib:
        ia, ib = ib, ia
        ce_a, ce_b = ce_b, ce_a
    v0 = ce_a.start_vertex()
    v1 = ce_b.start_vertex()
    bridge = Edge(Line3(v0.point, v1.point), 0.0, 1.0, v0, v1, tol)

    chain1 = ces[ia:ib]               # v0 .. v1
    chain2 = ces[ib:] + ces[:ia]      # v1 .. v0

    loop.coedges = chain1 + [Coedge(bridge, False)]
    loop._relink()

    new_loop = Loop(chain2 + [Coedge(bridge, True)], is_outer=True)
    surf = surface if surface is not None else (
        loop.face.surface if loop.face else _PointSurface(v0.point)
    )
    new_face = Face(surf, [new_loop], orientation=True, tol=tol)
    if loop.face and loop.face.shell:
        loop.face.shell.add_face(new_face)
    return bridge, new_face


def kef(loop: Loop, new_face: Face) -> None:
    """Kill Edge-Face: inverse of :func:`mef`. Merge ``new_face`` back.

    Delta: E-1, F-1, L-1 -> residual unchanged.
    """
    nl = new_face.outer_loop()
    bridge = None
    for ce in nl.coedges:
        if any(o.loop is loop for o in ce.edge.coedges):
            bridge = ce.edge
            break
    if bridge is None:
        raise EulerError("kef: no shared bridge edge")
    keep_from_new = [ce for ce in nl.coedges if ce.edge is not bridge]
    keep_loop = [ce for ce in loop.coedges if ce.edge is not bridge]
    loop.coedges = keep_loop + keep_from_new
    loop._relink()
    if new_face.shell:
        new_face.shell.faces = [
            f for f in new_face.shell.faces if f is not new_face
        ]


def kemr(face: Face, edge: Edge) -> Loop:
    """Kill Edge, Make Ring: remove an edge, splitting its loop's
    cycle into a separate inner ring loop.

    Used to create a hole loop on a face. Delta: E-1, L+1 -> residual
    unchanged. Returns the new inner :class:`Loop`.
    """
    outer = face.outer_loop()
    coedges = [ce for ce in outer.coedges if ce.edge is not edge]
    if len(coedges) == len(outer.coedges):
        raise EulerError("kemr: edge not on face outer loop")
    # the remaining coedges that formed a sub-cycle become a ring
    ring_coedges = coedges[len(coedges) // 2:]
    outer.coedges = coedges[: len(coedges) // 2]
    outer._relink()
    ring = Loop(ring_coedges, is_outer=False)
    face.add_loop(ring)
    edge.coedges = [ce for ce in edge.coedges if ce.loop is not outer]
    return ring


def memr(face: Face, ring: Loop, v0: Vertex, v1: Vertex,
         tol: float = 1e-7) -> Edge:
    """Make Edge, Remove Ring: inverse of :func:`kemr`.

    Reconnects ``ring`` into the face's outer loop with a new edge.
    Delta: E+1, L-1 -> residual unchanged.
    """
    outer = face.outer_loop()
    bridge = Edge(Line3(v0.point, v1.point), 0.0, 1.0, v0, v1, tol)
    outer.coedges = (
        outer.coedges + [Coedge(bridge, True)] + ring.coedges
        + [Coedge(bridge, False)]
    )
    outer._relink()
    face.loops = [lp for lp in face.loops if lp is not ring]
    return bridge


def kfmrh(solid: Solid, face: Face, hole_loop: Loop) -> Loop:
    """Kill Face, Make Ring-Hole (through-hole / handle): raises genus.

    Removes ``face`` and converts ``hole_loop`` into a ring on a
    neighbouring face, increasing the body genus by one. Delta:
    F-1, L-1, G+1 -> residual unchanged (the -F-(-L)=+F-L cancels the
    -2*(-G)=+2 once genus accounting is applied per the closed-shell
    Euler characteristic). Returns the relocated ring loop.
    """
    shell = face.shell
    if shell is None or face not in shell.faces:
        raise EulerError("kfmrh: face not in a shell")
    shell.faces = [f for f in shell.faces if f is not face]
    # attach the freed loop as an inner ring on the first remaining face
    if not shell.faces:
        raise EulerError("kfmrh: cannot remove the only face")
    host = shell.faces[0]
    hole_loop.is_outer = False
    host.add_loop(hole_loop)
    return hole_loop


def kfmrh_inverse(solid: Solid, host_face: Face, ring: Loop,
                  surface=None, tol: float = 1e-7) -> Face:
    """Inverse of :func:`kfmrh`: cap a ring back into its own face,
    lowering genus by one. Delta: F+1, L+1, G-1.
    """
    host_face.loops = [lp for lp in host_face.loops if lp is not ring]
    ring.is_outer = True
    surf = surface if surface is not None else _PointSurface(
        ring.coedges[0].start_point() if ring.coedges else np.zeros(3)
    )
    new_face = Face(surf, [ring], orientation=True, tol=tol)
    if host_face.shell:
        host_face.shell.add_face(new_face)
    return new_face


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_body(
    body: Body,
    *,
    check_self_intersection: bool = False,
    open: bool = False,
) -> dict:
    """Structurally + geometrically validate a :class:`Body`.

    Returns ``{"ok": bool, "errors": [str, ...]}``. Checks performed:

      1. Euler-Poincare residual is zero.  *(Skipped when ``open=True`` —
         open sheet bodies do not satisfy the closed-manifold E-P formula.)*
      2. Every loop is a closed coedge cycle (each coedge's end vertex
         coincides with the next coedge's start vertex within tol, and
         next/prev links are consistent).
      3. Each face's outer loop is CCW and inner loops CW with respect
         to the (oriented) surface normal.
      4. Every closed shell is 2-manifold: each edge is used by exactly
         two coedges, of opposite orientation.
      5. Tolerance monotonicity: vertex.tol >= incident edge.tol >=
         face.tol.
      6. No dangling edges (an edge with zero coedges) and no duplicate
         coedges (same edge + same orientation in one loop, unless the
         loop legitimately walks a seam there-and-back).
      7. (opt-in, ``check_self_intersection=True``) Geometric
         self-intersection: non-adjacent edge pairs and non-adjacent face
         pairs are tested for interior overlap. Default is ``False`` so
         that the existing (structural-only) behaviour is unchanged.

    Parameters
    ----------
    body
        The :class:`Body` to validate.
    check_self_intersection
        When ``True`` also run the geometric self-intersection check (§7).
    open
        When ``True`` skip the Euler–Poincaré residual check (§1) so that
        open-sheet bodies (loft / sweep / network surfaces wrapped in an open
        :class:`Shell`) are accepted.  All other structural checks (loop
        closure, loop orientation, tolerance monotonicity, dangling edges)
        still run.
    """
    errors: List[str] = []

    # --- 1. Euler-Poincare --------------------------------------------------
    if not open:
        res = body.euler_poincare_residual()
        if res != 0:
            c = body.euler_counts()
            errors.append(
                f"euler-poincare residual {res} != 0 "
                f"(V={c['V']} E={c['E']} F={c['F']} H={c['H']} "
                f"S={c['S']} G={c['G']})"
            )

    # --- 2. loop closure ----------------------------------------------------
    for lp in body.all_loops():
        if not lp.coedges:
            errors.append(f"loop#{lp.id} has no coedges")
            continue
        n = len(lp.coedges)
        for i, ce in enumerate(lp.coedges):
            nxt = lp.coedges[(i + 1) % n]
            if ce.next is not nxt:
                errors.append(
                    f"loop#{lp.id} coedge#{ce.id}.next link inconsistent"
                )
            etol = max(ce.edge.tol, nxt.edge.tol)
            gap = float(np.linalg.norm(ce.end_point() - nxt.start_point()))
            if gap > 10.0 * max(etol, 1e-9):
                errors.append(
                    f"loop#{lp.id} open at coedge#{ce.id} "
                    f"(gap={gap:.3e} > tol)"
                )
            if ce.end_vertex() is not nxt.start_vertex():
                # vertices may differ but must still be coincident
                if not ce.end_vertex().coincident(nxt.start_vertex()):
                    errors.append(
                        f"loop#{lp.id} vertex discontinuity at "
                        f"coedge#{ce.id}"
                    )

    # --- 3. loop orientation wrt surface normal -----------------------------
    for f in body.all_faces():
        if isinstance(f.surface, _PointSurface):
            continue
        outer = f.outer_loop()
        for lp in f.loops:
            signed = _loop_signed_area_about_normal(lp, f)
            if signed is None:
                continue
            if lp is outer and signed < 0:
                errors.append(
                    f"face#{f.id} outer loop#{lp.id} is CW "
                    f"(expected CCW wrt surface normal)"
                )
            if lp is not outer and signed > 0:
                errors.append(
                    f"face#{f.id} inner loop#{lp.id} is CCW "
                    f"(expected CW wrt surface normal)"
                )

    # --- 4. 2-manifold check on closed shells -------------------------------
    for sh in body.all_shells():
        if not sh.is_closed:
            continue
        use: dict = {}
        for f in sh.faces:
            for lp in f.loops:
                for ce in lp.coedges:
                    use.setdefault(id(ce.edge), []).append(ce)
        for f in sh.faces:
            for lp in f.loops:
                for ce in lp.coedges:
                    uses = use[id(ce.edge)]
                    if len(uses) != 2:
                        errors.append(
                            f"shell#{sh.id} edge#{ce.edge.id} used by "
                            f"{len(uses)} coedges (non-manifold; "
                            f"expected exactly 2)"
                        )
                        break
                    o = [u.orientation for u in uses]
                    if o[0] == o[1]:
                        errors.append(
                            f"shell#{sh.id} edge#{ce.edge.id} coedges "
                            f"have same orientation (not opposite)"
                        )
                        break
                else:
                    continue
                break

    # --- 5. tolerance monotonicity -----------------------------------------
    for f in body.all_faces():
        for lp in f.loops:
            for ce in lp.coedges:
                e = ce.edge
                if e.tol < f.tol - 1e-15:
                    errors.append(
                        f"tolerance inversion: edge#{e.id}.tol "
                        f"({e.tol:.3e}) < face#{f.id}.tol ({f.tol:.3e})"
                    )
                for v in (e.v_start, e.v_end):
                    if v.tol < e.tol - 1e-15:
                        errors.append(
                            f"tolerance inversion: vertex#{v.id}.tol "
                            f"({v.tol:.3e}) < edge#{e.id}.tol "
                            f"({e.tol:.3e})"
                        )

    # --- 6. dangling / duplicate -------------------------------------------
    for e in body.all_edges():
        live = [ce for ce in e.coedges if ce.loop is not None]
        if not live:
            errors.append(f"dangling edge#{e.id} (no coedges)")
    for lp in body.all_loops():
        seen = set()
        for ce in lp.coedges:
            key = (id(ce.edge), ce.orientation)
            if key in seen:
                errors.append(
                    f"loop#{lp.id} has duplicate coedge for "
                    f"edge#{ce.edge.id} orientation={ce.orientation}"
                )
            seen.add(key)

    # --- 7. geometric self-intersection (opt-in) ----------------------------
    if check_self_intersection:
        si_errors = _check_self_intersection(body)
        errors.extend(si_errors)

    return {"ok": len(errors) == 0, "errors": errors}


def _loop_signed_area_about_normal(loop: Loop, face: Face):
    """Signed polygon area of a loop projected onto the face normal.

    Positive => CCW wrt the (oriented) surface normal. Returns ``None``
    when the loop is degenerate (single seam, < 3 distinct points).
    """
    pts = []
    for ce in loop.coedges:
        p = ce.start_point()
        if not pts or np.linalg.norm(p - pts[-1]) > 1e-12:
            pts.append(np.asarray(p, dtype=float))
    if len(pts) < 3:
        return None
    centroid = np.mean(pts, axis=0)
    try:
        u0 = v0 = 0.0
        n = face.surface_normal(0.5, 0.5)
    except Exception:  # pragma: no cover - defensive
        return None
    n = _unit(np.asarray(n, dtype=float))
    if np.linalg.norm(n) < 1e-12:
        return None
    area_vec = np.zeros(3)
    m = len(pts)
    for i in range(m):
        a = pts[i] - centroid
        b = pts[(i + 1) % m] - centroid
        area_vec += np.cross(a, b)
    return float(np.dot(area_vec, n) * 0.5)


# ---------------------------------------------------------------------------
# Self-intersection helpers (used by validate_body check_self_intersection=True)
# ---------------------------------------------------------------------------

_SI_EDGE_SAMPLES: int = 12   # samples per edge for curve discretisation
_SI_FACE_SAMPLES: int = 6    # grid samples per face UV parameter


def _edge_polyline(edge: Edge, samples: int = _SI_EDGE_SAMPLES) -> np.ndarray:
    """Return ``samples`` uniformly-spaced points along *edge*."""
    ts = np.linspace(edge.t0, edge.t1, samples)
    return np.array([edge.point(float(t)) for t in ts], dtype=float)


def _seg_seg_min_dist_sq(p0: np.ndarray, p1: np.ndarray,
                         q0: np.ndarray, q1: np.ndarray) -> float:
    """Squared minimum distance between two line segments ``p0-p1`` and
    ``q0-q1`` (analytic, no iteration).
    """
    d1 = p1 - p0
    d2 = q1 - q0
    r = p0 - q0
    a = float(np.dot(d1, d1))
    e = float(np.dot(d2, d2))
    f = float(np.dot(d2, r))

    if a <= 1e-20 and e <= 1e-20:
        return float(np.dot(r, r))
    if a <= 1e-20:
        s, t = 0.0, max(0.0, min(1.0, f / e))
    else:
        c = float(np.dot(d1, r))
        if e <= 1e-20:
            t = 0.0
            s = max(0.0, min(1.0, -c / a))
        else:
            b = float(np.dot(d1, d2))
            denom = a * e - b * b
            if abs(denom) > 1e-20:
                s = max(0.0, min(1.0, (b * f - c * e) / denom))
            else:
                s = 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, max(0.0, min(1.0, -c / a))
            elif t > 1.0:
                t, s = 1.0, max(0.0, min(1.0, (b - c) / a))
    diff = p0 + s * d1 - (q0 + t * d2)
    return float(np.dot(diff, diff))


def _edges_are_adjacent(ea: Edge, eb: Edge) -> bool:
    """True when the two edges share at least one topological vertex."""
    va = {id(ea.v_start), id(ea.v_end)}
    vb = {id(eb.v_start), id(eb.v_end)}
    return bool(va & vb)


def _faces_adjacent(fa: Face, fb: Face) -> bool:
    """True when *fa* and *fb* share at least one topological edge."""
    ea_ids = {id(ce.edge) for lp in fa.loops for ce in lp.coedges}
    eb_ids = {id(ce.edge) for lp in fb.loops for ce in lp.coedges}
    return bool(ea_ids & eb_ids)


def _face_sample_points(face: Face, grid: int = _SI_FACE_SAMPLES) -> np.ndarray:
    """Sample a coarse grid of points over a face's loop vertex hull.

    Falls back to evaluating the underlying surface at ``grid x grid``
    interior UV fractions when no loop vertices are available.  Returns
    an ``(N, 3)`` array (may be empty).
    """
    # collect boundary vertices as a rough bounding polygon
    verts = []
    for lp in face.loops:
        for ce in lp.coedges:
            verts.append(ce.start_point())
    if not verts:
        return np.empty((0, 3), dtype=float)

    # For planar faces use a uniform sample of edge midpoints + centroid
    pts_list = [np.asarray(v, dtype=float) for v in verts]
    # add centroid
    centroid = np.mean(pts_list, axis=0)
    pts_list.append(centroid)
    # add midpoints between successive loop vertices
    n = len(verts)
    for i in range(n):
        pts_list.append(0.5 * (np.asarray(verts[i], dtype=float)
                                + np.asarray(verts[(i + 1) % n], dtype=float)))
    return np.array(pts_list, dtype=float)


def _point_to_plane_dist(pt: np.ndarray, plane_orig: np.ndarray,
                          plane_normal: np.ndarray) -> float:
    """Signed distance from *pt* to an infinite plane (normal assumed unit)."""
    return float(np.dot(pt - plane_orig, plane_normal))


def _face_plane(face: Face):
    """Return (origin, unit_normal) for a planar face, or None."""
    if not isinstance(face.surface, Plane):
        return None
    pl = face.surface
    n = pl.normal()
    if face.orientation is False:
        n = -n
    return pl.origin, n


def _check_self_intersection_edges(edges: List[Edge], tol: float) -> List[str]:
    """Check all non-adjacent edge pairs for geometric crossing.

    Uses polyline sampling for general curves; segment-segment analytic
    distance for pairs of ``Line3`` edges.  Returns a list of error strings.
    """
    errs: List[str] = []
    reported: set = set()  # avoid duplicate messages for the same pair
    n = len(edges)
    for i in range(n):
        for j in range(i + 1, n):
            ea, eb = edges[i], edges[j]
            if _edges_are_adjacent(ea, eb):
                continue
            key = (min(ea.id, eb.id), max(ea.id, eb.id))
            if key in reported:
                continue

            # Use analytic segment-segment when both are Line3
            if isinstance(ea.curve, Line3) and isinstance(eb.curve, Line3):
                d2 = _seg_seg_min_dist_sq(ea.curve.p0, ea.curve.p1,
                                           eb.curve.p0, eb.curve.p1)
                if d2 < tol * tol:
                    reported.add(key)
                    errs.append(
                        f"self-intersection: edge#{ea.id} and "
                        f"edge#{eb.id} intersect (dist={d2**0.5:.3e})"
                    )
                continue

            # General: sample both polylines, check nearest point pair
            pa = _edge_polyline(ea)
            pb = _edge_polyline(eb)
            # brute-force O(samples^2) nearest-segment scan
            found = False
            for k in range(len(pa) - 1):
                if found:
                    break
                for m in range(len(pb) - 1):
                    d2 = _seg_seg_min_dist_sq(pa[k], pa[k + 1],
                                               pb[m], pb[m + 1])
                    if d2 < tol * tol:
                        reported.add(key)
                        errs.append(
                            f"self-intersection: edge#{ea.id} and "
                            f"edge#{eb.id} intersect (dist={d2**0.5:.3e})"
                        )
                        found = True
                        break
    return errs


def _check_self_intersection_faces(faces: List[Face], tol: float) -> List[str]:
    """Check all non-adjacent face pairs for geometric overlap.

    For each pair of non-adjacent *planar* faces the signed distance of
    sampled points on face A from the plane of face B is computed; a
    sign change inside the face polygon indicates a crossing.  Pairs
    where both faces lie strictly on the same side (all same sign) are
    clean.  Non-planar face pairs are checked by point-sample proximity.

    Returns a list of error strings.
    """
    errs: List[str] = []
    reported: set = set()
    n = len(faces)
    for i in range(n):
        for j in range(i + 1, n):
            fa, fb = faces[i], faces[j]
            if _faces_adjacent(fa, fb):
                continue
            key = (min(fa.id, fb.id), max(fa.id, fb.id))
            if key in reported:
                continue

            plane_b = _face_plane(fb)
            plane_a = _face_plane(fa)

            if plane_a is not None and plane_b is not None:
                # Both planar: check if sample points of A straddle plane B
                # AND sample points of B straddle plane A (necessary condition
                # for actual crossing of two finite planar polygons).
                pts_a = _face_sample_points(fa)
                pts_b = _face_sample_points(fb)
                if len(pts_a) < 2 or len(pts_b) < 2:
                    continue
                orig_b, n_b = plane_b
                orig_a, n_a = plane_a
                dists_a = np.array(
                    [_point_to_plane_dist(p, orig_b, n_b) for p in pts_a]
                )
                dists_b = np.array(
                    [_point_to_plane_dist(p, orig_a, n_a) for p in pts_b]
                )
                # straddle = mix of positive and negative distances
                a_straddles = (dists_a.min() < -tol) and (dists_a.max() > tol)
                b_straddles = (dists_b.min() < -tol) and (dists_b.max() > tol)
                if a_straddles and b_straddles:
                    reported.add(key)
                    errs.append(
                        f"self-intersection: face#{fa.id} and "
                        f"face#{fb.id} planes mutually straddle "
                        f"(planar face–face intersection)"
                    )
                continue

            # General / mixed: sample-point proximity
            pts_a = _face_sample_points(fa)
            pts_b = _face_sample_points(fb)
            if len(pts_a) == 0 or len(pts_b) == 0:
                continue
            # check minimum pairwise distance between sample sets
            # O(|pts_a|*|pts_b|) — small for coarse grids
            for pa in pts_a:
                diffs = pts_b - pa
                dists = np.linalg.norm(diffs, axis=1)
                if dists.min() < tol:
                    reported.add(key)
                    errs.append(
                        f"self-intersection: face#{fa.id} and "
                        f"face#{fb.id} sample points overlap "
                        f"(dist={dists.min():.3e})"
                    )
                    break
    return errs


def _check_self_intersection(body: Body) -> List[str]:
    """Top-level self-intersection dispatcher called by ``validate_body``.

    Iterates over each shell independently (inter-shell intersection is
    not a topological self-intersection).  Uses the median face tolerance
    as the proximity threshold, falling back to ``1e-6``.
    """
    errs: List[str] = []
    for sh in body.all_shells():
        edges = sh.edges()
        faces = sh.faces
        if len(edges) < 2 and len(faces) < 2:
            continue
        # representative tolerance: smallest face tol in the shell
        tols = [f.tol for f in faces if f.tol > 0]
        tol = min(tols) if tols else 1e-6

        errs.extend(_check_self_intersection_edges(edges, tol))
        errs.extend(_check_self_intersection_faces(faces, tol))
    return errs


__all__ = [
    # geometry adapters
    "Line3",
    "CircleArc3",
    "Plane",
    "CylinderSurface",
    "SphereSurface",
    "TorusSurface",
    # topology
    "Vertex",
    "Edge",
    "Coedge",
    "Loop",
    "Face",
    "Shell",
    "Solid",
    "Body",
    # primitives
    "make_box",
    "make_tetra",
    "make_cylinder",
    "make_sphere",
    "make_torus",
    # euler operators + inverses
    "mvfs",
    "mev",
    "kev",
    "mef",
    "kef",
    "kemr",
    "memr",
    "kfmrh",
    "kfmrh_inverse",
    "EulerError",
    # validation
    "validate_body",
]
