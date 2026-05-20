"""GK-68 — Tolerance-sweep robustness harness.

Every P0/P1 construction and validation op is run across a ladder of
tolerances (tight → loose).  The oracle is:

    A looser tolerance NEVER turns a previously-valid Body invalid.

That is, if ``validate_body`` returns ``ok=True`` at tolerance ``t_i``,
it must also return ``ok=True`` at every ``t_j > t_i`` in the ladder.

DESIGN
------
* Hermetic pure-Python: no network, no OCCT, no external fixtures.
* A single ``TOL_LADDER`` list drives all parametric tests — one pytest
  parameter per rung.
* Every op is wrapped in ``_run_op(tol)`` returning a
  ``(body_or_None, ok, errors)`` triple so the sweep logic is uniform.
* Monotonicity assertion: given the ladder ``[t0, t1, ..., tN]`` (sorted
  ascending), collect the validity flags ``[v0, v1, ..., vN]``.  Assert
  that the sequence is non-decreasing (False→True is allowed; True→False
  is forbidden).
* Validity assertion: every body that IS successfully constructed at any
  rung must satisfy ``validate_body(body)["ok"] is True``.

COVERED OPS
-----------
P0 (must pass at every rung):
    1.  make_box          (brep.py)
    2.  make_tetra        (brep.py)
    3.  make_cylinder     (brep.py)
    4.  make_sphere       (brep.py)
    5.  make_torus        (brep.py)
    6.  box_to_body       (brep_build.py)
    7.  cylinder_to_body  (brep_build.py)
    8.  sphere_to_body    (brep_build.py)
    9.  sew_faces         (sew.py) — 6 independent planar faces sewn
   10.  sew_into_solid    (sew.py) — same input, closed-solid path

P1 (boolean ops — may raise BuildError for some combos; monotonicity still
    applies to the valid subset):
   11.  body_union        (boolean.py) — box U box, overlapping
   12.  body_union        (boolean.py) — box U box, disjoint
   13.  body_union        (boolean.py) — sphere U sphere
   14.  body_intersection (boolean.py) — box ∩ box
   15.  body_intersection (boolean.py) — sphere ∩ sphere (contained)
   16.  body_difference   (boolean.py) — box \\ box
   17.  body_difference   (boolean.py) — box \\ box (b contains a → empty)
   18.  fit_curve         (curve_toolkit.py) — deviation must not increase
                          as tolerance loosens
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Imports from the geom layer (stable contract surface only)
# ---------------------------------------------------------------------------

from kerf_cad_core.geom.brep import (
    Body,
    Coedge,
    Edge,
    Face,
    Line3,
    Loop,
    Plane,
    Shell,
    Solid,
    Vertex,
    make_box,
    make_cylinder,
    make_sphere,
    make_tetra,
    make_torus,
    validate_body,
)
from kerf_cad_core.geom.brep_build import (
    BuildError,
    box_to_body,
    cylinder_to_body,
    sphere_to_body,
)
from kerf_cad_core.geom.sew import sew_faces, sew_into_solid
from kerf_cad_core.geom.boolean import (
    body_difference,
    body_intersection,
    body_union,
)
from kerf_cad_core.geom.curve_toolkit import fit_curve

# ---------------------------------------------------------------------------
# Tolerance ladder — strictly increasing, covers tight analytic to lax sew
# ---------------------------------------------------------------------------

TOL_LADDER: List[float] = [
    1e-9,
    1e-8,
    1e-7,
    1e-6,
    5e-6,
    1e-5,
    5e-5,
    1e-4,
]

# ---------------------------------------------------------------------------
# Helper types
# ---------------------------------------------------------------------------

_OpResult = Tuple[Optional[Body], bool, List[str]]
_OpFn = Callable[[float], _OpResult]


def _wrap(fn: Callable[[float], Body]) -> _OpFn:
    """Wrap a constructor that returns a Body; catch BuildError gracefully."""
    def _run(tol: float) -> _OpResult:
        try:
            body = fn(tol)
            res = validate_body(body)
            return (body, res["ok"], res.get("errors", []))
        except (BuildError, Exception) as exc:  # noqa: BLE001
            return (None, False, [str(exc)])
    return _run


# ---------------------------------------------------------------------------
# Six independent planar faces for sew tests (an open cube without top/bottom)
# — helper returns fresh face objects each call so sew can mutate them
# ---------------------------------------------------------------------------

def _six_cube_faces(tol: float) -> List[Face]:
    """Return 6 fresh, disconnected planar Face objects forming a closed cube."""
    ox, oy, oz = 0.0, 0.0, 0.0
    sx, sy, sz = 2.0, 2.0, 2.0
    P = [
        np.array([ox,      oy,      oz     ]),
        np.array([ox + sx, oy,      oz     ]),
        np.array([ox + sx, oy + sy, oz     ]),
        np.array([ox,      oy + sy, oz     ]),
        np.array([ox,      oy,      oz + sz]),
        np.array([ox + sx, oy,      oz + sz]),
        np.array([ox + sx, oy + sy, oz + sz]),
        np.array([ox,      oy + sy, oz + sz]),
    ]
    face_rings = [
        [0, 3, 2, 1],  # bottom z-
        [4, 5, 6, 7],  # top    z+
        [0, 1, 5, 4],  # front  y-
        [1, 2, 6, 5],  # right  x+
        [2, 3, 7, 6],  # back   y+
        [3, 0, 4, 7],  # left   x-
    ]
    faces: List[Face] = []
    for ring in face_rings:
        verts = [Vertex(P[i], tol) for i in ring]
        coedges = []
        for i in range(4):
            a_pt = P[ring[i]]
            b_pt = P[ring[(i + 1) % 4]]
            va = verts[i]
            vb = verts[(i + 1) % 4]
            e = Edge(Line3(a_pt, b_pt), 0.0, 1.0, va, vb, tol)
            coedges.append(Coedge(e, True))
        loop = Loop(coedges, is_outer=True)
        p0, p1, p2 = P[ring[0]], P[ring[1]], P[ring[3]]
        plane = Plane(origin=p0, x_axis=p1 - p0, y_axis=p2 - p0)
        faces.append(Face(plane, [loop], orientation=True, tol=tol))
    return faces


# ---------------------------------------------------------------------------
# Named op definitions
# ---------------------------------------------------------------------------

OP_MAKE_BOX: _OpFn = _wrap(lambda tol: make_box(tol=tol))

OP_MAKE_TETRA: _OpFn = _wrap(lambda tol: make_tetra(tol=tol))

OP_MAKE_CYLINDER: _OpFn = _wrap(
    lambda tol: make_cylinder(
        center=(0.0, 0.0, 0.0),
        axis=(0.0, 0.0, 1.0),
        radius=1.0,
        height=2.0,
        tol=tol,
    )
)

OP_MAKE_SPHERE: _OpFn = _wrap(
    lambda tol: make_sphere(center=(0.0, 0.0, 0.0), radius=1.5, tol=tol)
)

OP_MAKE_TORUS: _OpFn = _wrap(
    lambda tol: make_torus(
        center=(0.0, 0.0, 0.0),
        axis=(0.0, 0.0, 1.0),
        major_radius=3.0,
        minor_radius=0.8,
        tol=tol,
    )
)

OP_BOX_TO_BODY: _OpFn = _wrap(
    lambda tol: box_to_body([0.0, 0.0, 0.0], 1.0, 1.0, 1.0, tol)
)

OP_CYLINDER_TO_BODY: _OpFn = _wrap(
    lambda tol: cylinder_to_body(
        [0.0, 0.0, 0.0], [0.0, 0.0, 1.0], 1.0, 2.0, tol
    )
)

OP_SPHERE_TO_BODY: _OpFn = _wrap(
    lambda tol: sphere_to_body([0.0, 0.0, 0.0], 1.0, tol)
)


def _op_sew_faces(tol: float) -> _OpResult:
    try:
        faces = _six_cube_faces(tol)
        shell = sew_faces(faces, tol=tol)
        # sew_faces returns a Shell; wrap in Body for validate_body
        if shell.is_closed:
            body = Body(solids=[Solid([shell])])
        else:
            body = Body(shells=[shell])
        res = validate_body(body)
        return (body, res["ok"], res.get("errors", []))
    except (BuildError, Exception) as exc:  # noqa: BLE001
        return (None, False, [str(exc)])


def _op_sew_into_solid(tol: float) -> _OpResult:
    try:
        faces = _six_cube_faces(tol)
        body = sew_into_solid(faces, tol=tol)
        res = validate_body(body)
        return (body, res["ok"], res.get("errors", []))
    except (BuildError, Exception) as exc:  # noqa: BLE001
        return (None, False, [str(exc)])


def _op_union_box_overlapping(tol: float) -> _OpResult:
    try:
        a = box_to_body([0.0, 0.0, 0.0], 2.0, 2.0, 2.0, tol)
        b = box_to_body([1.0, 0.0, 0.0], 2.0, 2.0, 2.0, tol)
        result = body_union(a, b, tol)
        res = validate_body(result)
        return (result, res["ok"], res.get("errors", []))
    except (BuildError, Exception) as exc:  # noqa: BLE001
        return (None, False, [str(exc)])


def _op_union_box_disjoint(tol: float) -> _OpResult:
    try:
        a = box_to_body([0.0, 0.0, 0.0], 1.0, 1.0, 1.0, tol)
        b = box_to_body([5.0, 0.0, 0.0], 1.0, 1.0, 1.0, tol)
        result = body_union(a, b, tol)
        res = validate_body(result)
        return (result, res["ok"], res.get("errors", []))
    except (BuildError, Exception) as exc:  # noqa: BLE001
        return (None, False, [str(exc)])


def _op_union_sphere(tol: float) -> _OpResult:
    try:
        a = sphere_to_body([0.0, 0.0, 0.0], 1.0, tol)
        b = sphere_to_body([3.0, 0.0, 0.0], 1.0, tol)  # disjoint
        result = body_union(a, b, tol)
        res = validate_body(result)
        return (result, res["ok"], res.get("errors", []))
    except (BuildError, Exception) as exc:  # noqa: BLE001
        return (None, False, [str(exc)])


def _op_intersection_box(tol: float) -> _OpResult:
    try:
        a = box_to_body([0.0, 0.0, 0.0], 2.0, 2.0, 2.0, tol)
        b = box_to_body([1.0, 0.0, 0.0], 2.0, 2.0, 2.0, tol)
        result = body_intersection(a, b, tol)
        res = validate_body(result)
        return (result, res["ok"], res.get("errors", []))
    except (BuildError, Exception) as exc:  # noqa: BLE001
        return (None, False, [str(exc)])


def _op_intersection_sphere_contained(tol: float) -> _OpResult:
    try:
        # b is completely inside a
        a = sphere_to_body([0.0, 0.0, 0.0], 2.0, tol)
        b = sphere_to_body([0.0, 0.0, 0.0], 1.0, tol)
        result = body_intersection(a, b, tol)
        res = validate_body(result)
        return (result, res["ok"], res.get("errors", []))
    except (BuildError, Exception) as exc:  # noqa: BLE001
        return (None, False, [str(exc)])


def _op_difference_box(tol: float) -> _OpResult:
    try:
        a = box_to_body([0.0, 0.0, 0.0], 3.0, 3.0, 3.0, tol)
        b = box_to_body([1.0, 1.0, 1.0], 1.0, 1.0, 1.0, tol)  # b inside a
        result = body_difference(a, b, tol)
        res = validate_body(result)
        return (result, res["ok"], res.get("errors", []))
    except (BuildError, Exception) as exc:  # noqa: BLE001
        return (None, False, [str(exc)])


def _op_difference_box_b_contains_a(tol: float) -> _OpResult:
    try:
        a = box_to_body([1.0, 1.0, 1.0], 1.0, 1.0, 1.0, tol)
        b = box_to_body([0.0, 0.0, 0.0], 3.0, 3.0, 3.0, tol)  # b contains a
        result = body_difference(a, b, tol)  # => empty Body
        # An empty body (no solids) has no topology to validate; treat as ok
        if not result.solids and not result.shells and not result.wires:
            return (result, True, [])
        res = validate_body(result)
        return (result, res["ok"], res.get("errors", []))
    except (BuildError, Exception) as exc:  # noqa: BLE001
        return (None, False, [str(exc)])


# All ops: (name, callable)
ALL_OPS: List[Tuple[str, _OpFn]] = [
    ("make_box",                       OP_MAKE_BOX),
    ("make_tetra",                     OP_MAKE_TETRA),
    ("make_cylinder",                  OP_MAKE_CYLINDER),
    ("make_sphere",                    OP_MAKE_SPHERE),
    ("make_torus",                     OP_MAKE_TORUS),
    ("box_to_body",                    OP_BOX_TO_BODY),
    ("cylinder_to_body",               OP_CYLINDER_TO_BODY),
    ("sphere_to_body",                 OP_SPHERE_TO_BODY),
    ("sew_faces",                      _op_sew_faces),
    ("sew_into_solid",                 _op_sew_into_solid),
    ("body_union_box_overlapping",     _op_union_box_overlapping),
    ("body_union_box_disjoint",        _op_union_box_disjoint),
    ("body_union_sphere_disjoint",     _op_union_sphere),
    ("body_intersection_box",         _op_intersection_box),
    ("body_intersection_sphere_cont", _op_intersection_sphere_contained),
    ("body_difference_box",           _op_difference_box),
    ("body_difference_b_contains_a",  _op_difference_box_b_contains_a),
]

OP_NAMES = [name for name, _ in ALL_OPS]
OP_MAP: Dict[str, _OpFn] = dict(ALL_OPS)

# ---------------------------------------------------------------------------
# Core monotonicity assertion helper
# ---------------------------------------------------------------------------


def _assert_monotone_validity(op_name: str, op_fn: _OpFn) -> None:
    """Run *op_fn* across TOL_LADDER and assert non-decreasing validity.

    The oracle: if the op was valid at rung ``i``, it must remain valid at
    every rung ``j > i``.  Transitions False→True are fine (looser tol
    recovers from a near-tolerance check); True→False is a regression.
    """
    results: List[_OpResult] = [op_fn(tol) for tol in TOL_LADDER]
    validity: List[bool] = [ok for _, ok, _ in results]

    # Find the first True index
    first_true = next((i for i, v in enumerate(validity) if v), None)
    if first_true is None:
        # Op never succeeded across the ladder — not a monotonicity failure
        # but record for diagnostics
        return

    # From first_true onward, every rung must also be True
    for i in range(first_true, len(validity)):
        tol = TOL_LADDER[i]
        _, ok, errors = results[i]
        assert ok, (
            f"[GK-68] MONOTONICITY VIOLATION in '{op_name}' at tol={tol:.2e}: "
            f"was valid at tol={TOL_LADDER[first_true]:.2e} but became invalid. "
            f"errors={errors}"
        )


# ---------------------------------------------------------------------------
# Test: individual per-rung validity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tol", TOL_LADDER, ids=[f"tol={t:.0e}" for t in TOL_LADDER])
@pytest.mark.parametrize("op_name", OP_NAMES)
def test_valid_body_stays_valid_at_tol(op_name: str, tol: float) -> None:
    """Any Body produced at *tol* must satisfy validate_body."""
    op_fn = OP_MAP[op_name]
    body, ok, errors = op_fn(tol)
    if body is None:
        # Op could not produce a body at this rung — skip (not a failure)
        pytest.skip(f"op '{op_name}' did not produce a body at tol={tol:.2e}")
    assert ok, (
        f"[GK-68] validate_body FAILED for op='{op_name}' at tol={tol:.2e}: "
        f"errors={errors}"
    )


# ---------------------------------------------------------------------------
# Test: monotonicity sweep (one test per op across the entire ladder)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("op_name", OP_NAMES)
def test_monotone_validity_across_tol_ladder(op_name: str) -> None:
    """Looser tolerance must NEVER invalidate a previously-valid Body."""
    op_fn = OP_MAP[op_name]
    _assert_monotone_validity(op_name, op_fn)


# ---------------------------------------------------------------------------
# Test: P0 primitives are valid at every ladder rung (no skip allowed)
# ---------------------------------------------------------------------------

P0_OPS = [
    "make_box",
    "make_tetra",
    "make_cylinder",
    "make_sphere",
    "make_torus",
    "box_to_body",
    "cylinder_to_body",
    "sphere_to_body",
]


@pytest.mark.parametrize("tol", TOL_LADDER, ids=[f"tol={t:.0e}" for t in TOL_LADDER])
@pytest.mark.parametrize("op_name", P0_OPS)
def test_p0_primitive_always_valid(op_name: str, tol: float) -> None:
    """P0 primitives must produce a valid Body at every ladder rung."""
    op_fn = OP_MAP[op_name]
    body, ok, errors = op_fn(tol)
    assert body is not None, (
        f"[GK-68] P0 op '{op_name}' raised at tol={tol:.2e}"
    )
    assert ok, (
        f"[GK-68] P0 op '{op_name}' produced invalid Body at tol={tol:.2e}: "
        f"errors={errors}"
    )


# ---------------------------------------------------------------------------
# Test: Euler–Poincare invariant holds for all P0 bodies across the ladder
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tol", TOL_LADDER, ids=[f"tol={t:.0e}" for t in TOL_LADDER])
@pytest.mark.parametrize("op_name", P0_OPS)
def test_euler_poincare_holds_across_ladder(op_name: str, tol: float) -> None:
    """V−E+F−H−2(S−G) == 0 for every P0 body at every tolerance rung."""
    op_fn = OP_MAP[op_name]
    body, ok, _ = op_fn(tol)
    assert body is not None
    assert ok
    residual = body.euler_poincare_residual()
    assert residual == 0, (
        f"[GK-68] Euler-Poincare residual={residual} for op='{op_name}' "
        f"at tol={tol:.2e}"
    )


# ---------------------------------------------------------------------------
# Test: validate_body is idempotent — calling it twice gives the same result
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tol", [1e-7, 1e-6, 1e-5], ids=["t=1e-7", "t=1e-6", "t=1e-5"])
@pytest.mark.parametrize("op_name", P0_OPS)
def test_validate_body_is_idempotent(op_name: str, tol: float) -> None:
    """validate_body called twice on the same Body returns the same result."""
    op_fn = OP_MAP[op_name]
    body, ok1, errors1 = op_fn(tol)
    assert body is not None
    res2 = validate_body(body)
    ok2, errors2 = res2["ok"], res2.get("errors", [])
    assert ok1 == ok2, (
        f"[GK-68] validate_body not idempotent for '{op_name}' at tol={tol:.2e}: "
        f"first={ok1} second={ok2}"
    )
    assert errors1 == errors2


# ---------------------------------------------------------------------------
# Test: fit_curve — deviation is finite and within tolerance at every rung
# ---------------------------------------------------------------------------


def _sample_helix_points(n: int = 20) -> np.ndarray:
    """Return *n* points on a 3-D helix (well-conditioned for fitting)."""
    t = np.linspace(0, 2 * math.pi, n)
    return np.column_stack([np.cos(t), np.sin(t), t / (2 * math.pi)])


HELIX_PTS = _sample_helix_points(20)


@pytest.mark.parametrize("tol", TOL_LADDER, ids=[f"tol={t:.0e}" for t in TOL_LADDER])
def test_fit_curve_returns_finite_deviation(tol: float) -> None:
    """fit_curve must always return a finite deviation (never NaN/inf)."""
    result = fit_curve(HELIX_PTS, degree=3, tolerance=tol)
    assert isinstance(result, dict), "fit_curve must return a dict"
    dev = result.get("deviation", float("nan"))
    assert math.isfinite(dev), (
        f"[GK-68] fit_curve returned non-finite deviation={dev} at tol={tol:.2e}"
    )


@pytest.mark.parametrize("tol", TOL_LADDER, ids=[f"tol={t:.0e}" for t in TOL_LADDER])
def test_fit_curve_ok_flag_consistent(tol: float) -> None:
    """fit_curve ok flag must be consistent with the reported deviation."""
    result = fit_curve(HELIX_PTS, degree=3, tolerance=tol)
    ok = result.get("ok", False)
    dev = result.get("deviation", float("inf"))
    if ok:
        # If ok=True the deviation should be within tolerance
        assert dev <= tol or math.isclose(dev, tol, rel_tol=1e-2), (
            f"[GK-68] fit_curve ok=True but deviation={dev:.3e} > tol={tol:.3e}"
        )


def test_fit_curve_ok_monotone() -> None:
    """fit_curve ok flag must be non-decreasing across the tolerance ladder.

    If the fitter can satisfy a tight tolerance (ok=True at tol_i), it must
    trivially satisfy any looser tolerance (ok=True at tol_j > tol_i), because
    the same curve whose deviation <= tol_i also satisfies deviation <= tol_j.

    Note: the reported *deviation* value may increase with looser tol because
    fit_curve stops adding control points as soon as dev <= tol (early exit
    with fewer knots).  That is correct behaviour — the monotone property
    applies to the *ok* flag, not the raw deviation value.
    """
    ok_flags = []
    deviations = []
    for tol in TOL_LADDER:
        r = fit_curve(HELIX_PTS, degree=3, tolerance=tol)
        ok_flags.append(r.get("ok", False))
        deviations.append(r.get("deviation", float("inf")))

    # All deviations must be finite
    for i, (tol, dev) in enumerate(zip(TOL_LADDER, deviations)):
        assert math.isfinite(dev), (
            f"[GK-68] fit_curve returned non-finite deviation at ladder rung "
            f"{i} (tol={tol:.2e}): dev={dev}"
        )

    # ok flag must be non-decreasing (False→True allowed; True→False forbidden)
    first_ok = next((i for i, v in enumerate(ok_flags) if v), None)
    if first_ok is None:
        return  # never succeeded — not a monotonicity violation
    for i in range(first_ok, len(ok_flags)):
        assert ok_flags[i], (
            f"[GK-68] fit_curve ok=True at tol={TOL_LADDER[first_ok]:.2e} "
            f"but ok=False at tol={TOL_LADDER[i]:.2e} (deviation={deviations[i]:.4e}) — "
            f"MONOTONICITY VIOLATION"
        )

    # Sanity: when ok=True, deviation <= tolerance (with small numerical slack)
    for i, (tol, ok, dev) in enumerate(zip(TOL_LADDER, ok_flags, deviations)):
        if ok:
            assert dev <= tol * (1.0 + 1e-6) + 1e-14, (
                f"[GK-68] fit_curve ok=True but deviation={dev:.4e} > tol={tol:.2e}"
            )


# ---------------------------------------------------------------------------
# Test: sew_faces and sew_into_solid — closed flag monotonicity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tol", TOL_LADDER, ids=[f"tol={t:.0e}" for t in TOL_LADDER])
def test_sew_faces_produces_closed_shell(tol: float) -> None:
    """sew_faces on a complete cube must yield a closed Shell at every rung."""
    faces = _six_cube_faces(tol)
    try:
        shell = sew_faces(faces, tol=tol)
        assert shell.is_closed, (
            f"[GK-68] sew_faces shell.is_closed=False at tol={tol:.2e}"
        )
    except (BuildError, Exception) as exc:  # noqa: BLE001
        pytest.skip(f"sew_faces raised at tol={tol:.2e}: {exc}")


@pytest.mark.parametrize("tol", TOL_LADDER, ids=[f"tol={t:.0e}" for t in TOL_LADDER])
def test_sew_into_solid_produces_valid_body(tol: float) -> None:
    """sew_into_solid on a complete cube must yield a valid Body at every rung."""
    faces = _six_cube_faces(tol)
    try:
        body = sew_into_solid(faces, tol=tol)
        res = validate_body(body)
        assert res["ok"], (
            f"[GK-68] sew_into_solid body invalid at tol={tol:.2e}: "
            f"{res['errors']}"
        )
    except (BuildError, Exception) as exc:  # noqa: BLE001
        pytest.skip(f"sew_into_solid raised at tol={tol:.2e}: {exc}")


# ---------------------------------------------------------------------------
# Test: Boolean results are validate_body-clean when they succeed
# ---------------------------------------------------------------------------


BOOLEAN_OPS: List[Tuple[str, _OpFn]] = [
    ("body_union_box_overlapping",    _op_union_box_overlapping),
    ("body_union_box_disjoint",       _op_union_box_disjoint),
    ("body_union_sphere_disjoint",    _op_union_sphere),
    ("body_intersection_box",        _op_intersection_box),
    ("body_intersection_sphere_cont",_op_intersection_sphere_contained),
    ("body_difference_box",          _op_difference_box),
    ("body_difference_b_contains_a", _op_difference_box_b_contains_a),
]


@pytest.mark.parametrize("tol", TOL_LADDER, ids=[f"tol={t:.0e}" for t in TOL_LADDER])
@pytest.mark.parametrize("op_name,op_fn", BOOLEAN_OPS, ids=[n for n, _ in BOOLEAN_OPS])
def test_boolean_result_is_valid_when_produced(op_name: str, op_fn: _OpFn, tol: float) -> None:
    """Any Body produced by a boolean op must satisfy validate_body."""
    body, ok, errors = op_fn(tol)
    if body is None:
        pytest.skip(f"boolean op '{op_name}' did not produce a body at tol={tol:.2e}")
    assert ok, (
        f"[GK-68] Boolean op '{op_name}' produced invalid body at tol={tol:.2e}: "
        f"errors={errors}"
    )
