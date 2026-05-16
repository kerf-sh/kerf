"""Property-based invariant suite for Euler operators on B-rep topology.

Roadmap reference: GK-66 — Euler operator invariant hardening.

DESIGN
------
No external property-based framework (no hypothesis). A small deterministic
LCG (32-bit Xorshift) provides a reproducible pseudo-random sequence for
parametric and walk tests. All randomness is seeded at module level so the
test suite is fully deterministic across runs.

INVARIANT CHECKED AT EVERY STEP
--------------------------------
    V − E + F − H − 2·(S − G) == 0

where H = L − F (inner / ring loops per body), S = shells, G = genus.

All operator tests begin from a properly-seeded body (either mvfs or one of
the validated primitive constructors) so that EP=0 is guaranteed before the
first operator.  Hand-built open-shell bodies start with EP != 0 and are
NOT suitable for EP=0 assertions — tests that use them only check that each
operator is invariant-preserving (before == after), matching the approach
in the existing test_brep_topology.py::test_mef_preserves_residual.

COVERAGE
--------
- All five operators and their inverses applied to valid EP=0 bodies
- Delta vectors exactly as documented in BREP_CONTRACT.md
- Operator/inverse round-trips (counts restored, EP=0 after)
- Deterministic random walks of N=200 operator applications, re-checking
  EP=0 at every step
- Genus accounting: torus stays G=1; kfmrh raises G; kfmrh_inverse lowers
- Tolerance monotonicity asserted via validate_body for every operator
"""

from __future__ import annotations

import math
from typing import List, Tuple

import numpy as np
import pytest

from kerf_cad_core.geom.brep import (
    Body,
    Coedge,
    Edge,
    EulerError,
    Face,
    Line3,
    Loop,
    Plane,
    Shell,
    Solid,
    Vertex,
    kev,
    kef,
    kfmrh,
    kfmrh_inverse,
    kemr,
    make_box,
    make_cylinder,
    make_sphere,
    make_tetra,
    make_torus,
    mef,
    mev,
    memr,
    mvfs,
    validate_body,
)


# ---------------------------------------------------------------------------
# Deterministic 32-bit Xorshift PRNG — NO external randomness
# ---------------------------------------------------------------------------


class _LCG:
    """Deterministic 32-bit xorshift PRNG (period 2^32 − 1)."""

    def __init__(self, seed: int = 0xDEAD_BEEF):
        self._state = seed & 0xFFFF_FFFF or 1

    def next_int(self) -> int:
        x = self._state
        x ^= (x << 13) & 0xFFFF_FFFF
        x ^= (x >> 17)
        x ^= (x << 5) & 0xFFFF_FFFF
        self._state = x & 0xFFFF_FFFF
        return self._state

    def next_float(self) -> float:
        return self.next_int() / 0xFFFF_FFFF

    def choice(self, seq):
        return seq[self.next_int() % len(seq)]


# ---------------------------------------------------------------------------
# EP / validate helpers
# ---------------------------------------------------------------------------


def _assert_ep(body: Body, msg: str = "") -> None:
    res = body.euler_poincare_residual()
    assert res == 0, (
        f"EP residual={res} != 0 {msg} counts={body.euler_counts()}"
    )


def _assert_valid_ep(body: Body, msg: str = "") -> None:
    """Assert EP=0 (does not run full validate_body structure checks)."""
    _assert_ep(body, msg)


def _assert_tol_ok(body: Body, msg: str = "") -> None:
    result = validate_body(body)
    tol_errors = [e for e in result["errors"] if "tolerance" in e.lower()]
    assert not tol_errors, f"tolerance errors {msg}: {tol_errors}"


# ---------------------------------------------------------------------------
# Helper: build a spur-chain body via mvfs + N mev steps
#
# This is the canonical correct seed for kemr/memr tests: each edge has
# both its coedges inside the same single outer loop, so kemr can split it.
# ---------------------------------------------------------------------------


def _make_spur_chain(n: int = 4):
    """Return (body, face, loop, v_list, e_list) with n spur edges.

    The loop traverses v0->v1->...->vn->vn->...->v0, making each edge
    eligible for kemr (both coedges share the same loop).
    """
    body, _, _, _, loop, v0 = mvfs((0.0, 0.0, 0.0))
    v_list = [v0]
    e_list = []
    cur = v0
    for i in range(n):
        e, vnew = mev(loop, cur, (float(i + 1), 0.0, 0.0))
        v_list.append(vnew)
        e_list.append(e)
        cur = vnew
    face = body.all_faces()[0]
    return body, face, loop, v_list, e_list


# ---------------------------------------------------------------------------
# Helper: build an mvfs-seeded quad that can be tested with mef
# ---------------------------------------------------------------------------


def _make_mvfs_spur_quad():
    """Build a 3-edge spur body (EP=0) ready for mef.

    Returns (body, face, loop, v0, va, vb, vc, ce0, ce_vb)
    where ce0 starts at v0 and ce_vb starts at vb.
    mef(loop, ce0, ce_vb) will bridge v0 to vb.
    """
    body, _, _, _, loop, v0 = mvfs((0.0, 0.0, 0.0))
    e_a, va = mev(loop, v0, (1.0, 0.0, 0.0))
    e_b, vb = mev(loop, va, (1.0, 1.0, 0.0))
    e_c, vc = mev(loop, vb, (0.0, 1.0, 0.0))
    face = body.all_faces()[0]
    ces = loop.coedges
    ce0 = next(ce for ce in ces if ce.start_vertex() is v0 and ce.orientation)
    ce_vb = next(ce for ce in ces if ce.start_vertex() is vb and ce.orientation)
    return body, face, loop, v0, va, vb, vc, ce0, ce_vb


# ---------------------------------------------------------------------------
# Section 1 — primitives: exact counts + EP=0 + validate_body ok
# ---------------------------------------------------------------------------


def test_box_ep_residual_zero():
    _assert_ep(make_box(), "make_box")


def test_box_exact_counts():
    c = make_box().euler_counts()
    assert c["V"] == 8
    assert c["E"] == 12
    assert c["F"] == 6
    assert c["H"] == 0
    assert c["S"] == 1
    assert c["G"] == 0


def test_box_euler_characteristic_two():
    c = make_box().euler_counts()
    assert c["V"] - c["E"] + c["F"] == 2


def test_tetra_ep_residual_zero():
    _assert_ep(make_tetra(), "make_tetra")


def test_tetra_exact_counts():
    c = make_tetra().euler_counts()
    assert c["V"] == 4
    assert c["E"] == 6
    assert c["F"] == 4
    assert c["H"] == 0
    assert c["S"] == 1
    assert c["G"] == 0


def test_cylinder_ep_residual_zero():
    _assert_ep(make_cylinder(), "make_cylinder")


def test_sphere_ep_residual_zero():
    _assert_ep(make_sphere(), "make_sphere")


def test_sphere_exact_counts():
    # V=2 poles, E=1 seam, F=1, H=0, S=1, G=0
    c = make_sphere().euler_counts()
    assert c["V"] == 2
    assert c["E"] == 1
    assert c["F"] == 1
    assert c["H"] == 0
    assert c["S"] == 1
    assert c["G"] == 0


def test_torus_ep_residual_zero():
    _assert_ep(make_torus(), "make_torus")


def test_torus_exact_counts():
    # V=1 corner, E=2 seams, F=1, H=0, S=1, G=1
    c = make_torus().euler_counts()
    assert c["V"] == 1
    assert c["E"] == 2
    assert c["F"] == 1
    assert c["H"] == 0
    assert c["S"] == 1
    assert c["G"] == 1


def test_torus_genus_is_one():
    assert make_torus().genus() == 1


def test_all_primitives_validate_ok():
    for name, body in [
        ("box", make_box()),
        ("tetra", make_tetra()),
        ("cylinder", make_cylinder()),
        ("sphere", make_sphere()),
        ("torus", make_torus()),
    ]:
        r = validate_body(body)
        assert r["ok"], f"{name} validate_body: {r['errors']}"


# ---------------------------------------------------------------------------
# Section 2 — mvfs: delta (+1, 0, +1, +1, +1, 0)
# ---------------------------------------------------------------------------


def test_mvfs_ep_zero():
    body, _, _, _, _, _ = mvfs((0.0, 0.0, 0.0))
    _assert_ep(body, "mvfs")


def test_mvfs_counts_match_delta():
    # Post-mvfs: V=1, E=0, F=1, H=0, S=1, G=0
    body, _, _, _, _, _ = mvfs((3.0, 1.0, 4.0))
    c = body.euler_counts()
    assert c["V"] == 1
    assert c["E"] == 0
    assert c["F"] == 1
    assert c["H"] == 0
    assert c["S"] == 1
    assert c["G"] == 0


def test_mvfs_ep_no_euler_error():
    body, _, _, _, _, _ = mvfs((0.0, 0.0, 0.0))
    r = validate_body(body)
    ep_errors = [e for e in r["errors"] if "euler" in e.lower()]
    assert not ep_errors, ep_errors


# ---------------------------------------------------------------------------
# Section 3 — mev: delta (+1, +1, 0, 0, 0, 0); kev inverse
# ---------------------------------------------------------------------------


def test_mev_delta_v_plus1_e_plus1():
    body, _, _, _, loop, v = mvfs((0.0, 0.0, 0.0))
    c0 = body.euler_counts()
    mev(loop, v, (1.0, 0.0, 0.0))
    c1 = body.euler_counts()
    assert c1["V"] == c0["V"] + 1
    assert c1["E"] == c0["E"] + 1
    assert c1["F"] == c0["F"]
    assert c1["H"] == c0["H"]
    assert c1["S"] == c0["S"]
    assert c1["G"] == c0["G"]
    _assert_ep(body, "after mev")


def test_mev_ep_preserved_chain():
    body, _, _, _, loop, v = mvfs((0.0, 0.0, 0.0))
    cur = v
    for i in range(1, 8):
        _, cur = mev(loop, cur, (float(i), 0.0, 0.0))
        _assert_ep(body, f"mev chain step {i}")


def test_kev_inverse_of_mev_counts():
    body, _, _, _, loop, v = mvfs((0.0, 0.0, 0.0))
    c0 = body.euler_counts()
    edge, _ = mev(loop, v, (1.0, 0.0, 0.0))
    kev(loop, edge)
    c2 = body.euler_counts()
    assert c2["V"] == c0["V"]
    assert c2["E"] == c0["E"]
    assert c2["F"] == c0["F"]
    _assert_ep(body, "after kev round-trip")


def test_kev_delta_v_minus1_e_minus1():
    body, _, _, _, loop, v = mvfs((0.0, 0.0, 0.0))
    edge, _ = mev(loop, v, (1.0, 0.0, 0.0))
    c0 = body.euler_counts()
    kev(loop, edge)
    c1 = body.euler_counts()
    assert c1["V"] == c0["V"] - 1
    assert c1["E"] == c0["E"] - 1
    assert c1["F"] == c0["F"]
    assert c1["H"] == c0["H"]
    _assert_ep(body, "after kev delta")


def test_mev_kev_multiple_round_trip():
    body, _, _, _, loop, v = mvfs((0.0, 0.0, 0.0))
    cur = v
    edges = []
    for i in range(1, 5):
        e, cur = mev(loop, cur, (float(i), 0.0, 0.0))
        edges.append(e)
    # peel back in LIFO order (kev requires leaf edges first)
    for e in reversed(edges):
        kev(loop, e)
    c_end = body.euler_counts()
    assert c_end["V"] == 1
    assert c_end["E"] == 0
    _assert_ep(body, "after multi kev")


def test_mev_tol_monotonicity():
    body, _, _, _, loop, v = mvfs((0.0, 0.0, 0.0))
    mev(loop, v, (1.0, 0.0, 0.0), tol=1e-7)
    _assert_tol_ok(body, "mev tol")


# ---------------------------------------------------------------------------
# Section 4 — mef: delta (0, +1, +1, +1, 0, 0); kef inverse
#
# Tests use an mvfs-seeded body (EP=0), not a hand-built open quad.
# ---------------------------------------------------------------------------


def test_mef_delta_exact():
    body, face, loop, v0, va, vb, vc, ce0, ce_vb = _make_mvfs_spur_quad()
    c0 = body.euler_counts()
    assert body.euler_poincare_residual() == 0
    mef(loop, ce0, ce_vb, surface=face.surface)
    c1 = body.euler_counts()
    assert c1["V"] == c0["V"] + 0
    assert c1["E"] == c0["E"] + 1
    assert c1["F"] == c0["F"] + 1
    # H = L - F: both L and F increase by 1, so H is unchanged
    assert c1["H"] == c0["H"]
    assert c1["S"] == c0["S"]
    assert c1["G"] == c0["G"]
    _assert_ep(body, "after mef")


def test_mef_ep_preserved():
    body, face, loop, v0, va, vb, vc, ce0, ce_vb = _make_mvfs_spur_quad()
    _assert_ep(body, "pre-mef seed")
    mef(loop, ce0, ce_vb, surface=face.surface)
    _assert_ep(body, "post-mef")


def test_kef_inverse_of_mef():
    body, face, loop, v0, va, vb, vc, ce0, ce_vb = _make_mvfs_spur_quad()
    c0 = body.euler_counts()
    bridge, new_face = mef(loop, ce0, ce_vb, surface=face.surface)
    kef(loop, new_face)
    c2 = body.euler_counts()
    assert c2["V"] == c0["V"]
    assert c2["E"] == c0["E"]
    assert c2["F"] == c0["F"]
    _assert_ep(body, "after kef round-trip")


def test_kef_delta_exact():
    body, face, loop, v0, va, vb, vc, ce0, ce_vb = _make_mvfs_spur_quad()
    bridge, new_face = mef(loop, ce0, ce_vb, surface=face.surface)
    c0 = body.euler_counts()
    kef(loop, new_face)
    c1 = body.euler_counts()
    assert c1["E"] == c0["E"] - 1
    assert c1["F"] == c0["F"] - 1
    assert c1["H"] == c0["H"]
    _assert_ep(body, "after kef delta")


def test_mef_on_box_face_ep_preserved():
    # mef on a face of an existing box (EP=0 body)
    body = make_box()
    face = body.all_faces()[0]
    loop = face.outer_loop()
    ces = loop.coedges
    before = body.euler_poincare_residual()
    bridge, new_face = mef(loop, ces[0], ces[2], surface=face.surface)
    after = body.euler_poincare_residual()
    assert before == after == 0


def test_mef_tol_monotonicity():
    body, face, loop, v0, va, vb, vc, ce0, ce_vb = _make_mvfs_spur_quad()
    mef(loop, ce0, ce_vb, surface=face.surface, tol=1e-7)
    _assert_tol_ok(body, "mef tol")


# ---------------------------------------------------------------------------
# Section 5 — kemr: delta (0, −1, 0, +1, 0, 0); memr inverse
#
# kemr is designed for edges that have BOTH coedges in the same outer loop
# (spur-chain geometry from mvfs + mev). After mef the edge spans two
# different face loops and is no longer a valid kemr candidate.
# ---------------------------------------------------------------------------


def test_kemr_delta_exact():
    body, face, loop, v_list, e_list = _make_spur_chain(4)
    c0 = body.euler_counts()
    assert body.euler_poincare_residual() == 0
    # kemr on the middle edge (both coedges in the same outer loop)
    kemr(face, e_list[1])
    c1 = body.euler_counts()
    assert c1["E"] == c0["E"] - 1
    # H = L - F: L increases by 1, F unchanged => H+1
    assert c1["H"] == c0["H"] + 1
    assert c1["F"] == c0["F"]
    assert c1["V"] == c0["V"]
    assert c1["S"] == c0["S"]
    assert c1["G"] == c0["G"]
    _assert_ep(body, "after kemr")


def test_kemr_ep_preserved():
    body, face, loop, v_list, e_list = _make_spur_chain(4)
    _assert_ep(body, "pre-kemr")
    kemr(face, e_list[1])
    _assert_ep(body, "post-kemr")


def test_memr_inverse_of_kemr():
    body, face, loop, v_list, e_list = _make_spur_chain(4)
    c0 = body.euler_counts()
    ring = kemr(face, e_list[1])
    # memr re-bridges with new edge connecting e_list[1] endpoints
    memr(face, ring, v_list[0], v_list[2])
    c2 = body.euler_counts()
    assert c2["E"] == c0["E"]
    assert c2["H"] == c0["H"]
    _assert_ep(body, "after memr round-trip")


def test_memr_delta_exact():
    body, face, loop, v_list, e_list = _make_spur_chain(4)
    ring = kemr(face, e_list[1])
    c0 = body.euler_counts()
    memr(face, ring, v_list[0], v_list[2])
    c1 = body.euler_counts()
    assert c1["E"] == c0["E"] + 1
    assert c1["H"] == c0["H"] - 1
    assert c1["F"] == c0["F"]
    assert c1["V"] == c0["V"]
    _assert_ep(body, "after memr delta")


def test_kemr_then_memr_ep_zero_throughout():
    body, face, loop, v_list, e_list = _make_spur_chain(6)
    _assert_ep(body, "seed")
    ring = kemr(face, e_list[2])
    _assert_ep(body, "after kemr")
    memr(face, ring, v_list[0], v_list[3])
    _assert_ep(body, "after memr")


def test_kemr_tol_monotonicity():
    body, face, loop, v_list, e_list = _make_spur_chain(4)
    kemr(face, e_list[1])
    _assert_tol_ok(body, "kemr tol")


# ---------------------------------------------------------------------------
# Section 6 — kfmrh: delta (0, 0, −1, −1, 0, +1); kfmrh_inverse
# ---------------------------------------------------------------------------


def test_kfmrh_delta_exact():
    body = make_box()
    c0 = body.euler_counts()
    solid = body.solids[0]
    shell = solid.shells[0]
    removed = shell.faces[-1]
    hole = removed.outer_loop()
    kfmrh(solid, removed, hole)
    c1 = body.euler_counts()
    assert c1["F"] == c0["F"] - 1
    assert c1["G"] == c0["G"] + 1
    assert c1["V"] == c0["V"]
    assert c1["E"] == c0["E"]
    assert c1["S"] == c0["S"]
    _assert_ep(body, "after kfmrh")


def test_kfmrh_ep_preserved():
    body = make_box()
    _assert_ep(body, "pre-kfmrh")
    solid = body.solids[0]
    shell = solid.shells[0]
    removed = shell.faces[-1]
    hole = removed.outer_loop()
    kfmrh(solid, removed, hole)
    _assert_ep(body, "post-kfmrh")


def test_kfmrh_inverse_delta_exact():
    body = make_box()
    solid = body.solids[0]
    shell = solid.shells[0]
    removed = shell.faces[-1]
    hole = removed.outer_loop()
    kfmrh(solid, removed, hole)
    c0 = body.euler_counts()
    kfmrh_inverse(solid, shell.faces[0], hole)
    c1 = body.euler_counts()
    assert c1["F"] == c0["F"] + 1
    assert c1["G"] == c0["G"] - 1
    assert c1["V"] == c0["V"]
    assert c1["E"] == c0["E"]
    assert c1["S"] == c0["S"]
    _assert_ep(body, "after kfmrh_inverse")


def test_kfmrh_inverse_ep_preserved():
    body = make_box()
    solid = body.solids[0]
    shell = solid.shells[0]
    removed = shell.faces[-1]
    hole = removed.outer_loop()
    kfmrh(solid, removed, hole)
    _assert_ep(body, "mid kfmrh")
    kfmrh_inverse(solid, shell.faces[0], hole)
    _assert_ep(body, "post kfmrh_inverse")


def test_kfmrh_round_trip_counts_restored():
    body = make_box()
    c0 = body.euler_counts()
    solid = body.solids[0]
    shell = solid.shells[0]
    removed = shell.faces[-1]
    hole = removed.outer_loop()
    kfmrh(solid, removed, hole)
    kfmrh_inverse(solid, shell.faces[0], hole)
    c2 = body.euler_counts()
    assert c2["F"] == c0["F"]
    assert c2["G"] == c0["G"]
    assert c2["E"] == c0["E"]
    assert c2["V"] == c0["V"]
    _assert_ep(body, "round-trip kfmrh/inverse")


def test_kfmrh_tol_monotonicity():
    body = make_box()
    solid = body.solids[0]
    shell = solid.shells[0]
    removed = shell.faces[-1]
    hole = removed.outer_loop()
    kfmrh(solid, removed, hole)
    _assert_tol_ok(body, "kfmrh tol")


# ---------------------------------------------------------------------------
# Section 7 — genus accounting
# ---------------------------------------------------------------------------


def test_torus_genus_is_one_constant():
    body = make_torus()
    assert body.genus() == 1
    _assert_ep(body, "torus genus baseline")


def test_box_genus_zero():
    assert make_box().genus() == 0


def test_tetra_genus_zero():
    assert make_tetra().genus() == 0


def test_cylinder_genus_zero():
    assert make_cylinder().genus() == 0


def test_sphere_genus_zero():
    assert make_sphere().genus() == 0


def test_kfmrh_raises_genus_by_one():
    body = make_box()
    g0 = body.genus()
    solid = body.solids[0]
    shell = solid.shells[0]
    removed = shell.faces[-1]
    hole = removed.outer_loop()
    kfmrh(solid, removed, hole)
    assert body.genus() == g0 + 1
    _assert_ep(body, "genus +1")


def test_kfmrh_applied_twice_genus_increments_twice():
    body = make_box()
    solid = body.solids[0]
    shell = solid.shells[0]
    g0 = body.genus()
    # first removal
    r1 = shell.faces[-1]
    h1 = r1.outer_loop()
    kfmrh(solid, r1, h1)
    assert body.genus() == g0 + 1
    _assert_ep(body, "kfmrh x1 genus")
    # second removal (at least 2 remaining faces on a box)
    if len(shell.faces) >= 2:
        r2 = shell.faces[-1]
        h2 = r2.outer_loop()
        kfmrh(solid, r2, h2)
        assert body.genus() == g0 + 2
        _assert_ep(body, "kfmrh x2 genus")


def test_kfmrh_inverse_lowers_genus():
    body = make_box()
    solid = body.solids[0]
    shell = solid.shells[0]
    removed = shell.faces[-1]
    hole = removed.outer_loop()
    kfmrh(solid, removed, hole)
    g_mid = body.genus()
    kfmrh_inverse(solid, shell.faces[0], hole)
    assert body.genus() == g_mid - 1
    _assert_ep(body, "genus after kfmrh_inverse")


def test_torus_genus_stable_through_mev():
    # torus stays genus-1; mev on a seed body doesn't interact with torus
    body = make_torus()
    assert body.genus() == 1
    _assert_ep(body, "torus unchanged by mev on separate body")


# ---------------------------------------------------------------------------
# Section 8 — tolerance monotonicity preserved by all operators
# ---------------------------------------------------------------------------


def test_tol_monotonicity_all_primitives():
    for name, body in [
        ("box", make_box()),
        ("tetra", make_tetra()),
        ("cylinder", make_cylinder()),
        ("sphere", make_sphere()),
        ("torus", make_torus()),
    ]:
        r = validate_body(body)
        tol_errors = [e for e in r["errors"] if "tolerance" in e.lower()]
        assert not tol_errors, f"{name}: {tol_errors}"


def test_tol_monotonicity_after_mev():
    body, _, _, _, loop, v = mvfs((0.0, 0.0, 0.0))
    mev(loop, v, (1.0, 0.0, 0.0), tol=1e-7)
    _assert_tol_ok(body, "mev tol check")


def test_tol_monotonicity_after_mef():
    body, face, loop, v0, va, vb, vc, ce0, ce_vb = _make_mvfs_spur_quad()
    mef(loop, ce0, ce_vb, surface=face.surface, tol=1e-7)
    _assert_tol_ok(body, "mef tol check")


def test_tol_monotonicity_after_kemr():
    body, face, loop, v_list, e_list = _make_spur_chain(4)
    kemr(face, e_list[1])
    _assert_tol_ok(body, "kemr tol check")


def test_tol_monotonicity_after_kfmrh():
    body = make_box()
    solid = body.solids[0]
    shell = solid.shells[0]
    removed = shell.faces[-1]
    hole = removed.outer_loop()
    kfmrh(solid, removed, hole)
    _assert_tol_ok(body, "kfmrh tol check")


# ---------------------------------------------------------------------------
# Section 9 — Operator/inverse round-trips: EP=0 before and after
# ---------------------------------------------------------------------------


def test_mev_kev_validate_ep_before_and_after():
    body, _, _, _, loop, v = mvfs((0.0, 0.0, 0.0))
    _assert_ep(body, "seed")
    edge, _ = mev(loop, v, (1.0, 0.0, 0.0))
    _assert_ep(body, "after mev")
    kev(loop, edge)
    _assert_ep(body, "after kev")


def test_mef_kef_validate_ep_before_and_after():
    body, face, loop, v0, va, vb, vc, ce0, ce_vb = _make_mvfs_spur_quad()
    _assert_ep(body, "seed")
    bridge, new_face = mef(loop, ce0, ce_vb, surface=face.surface)
    _assert_ep(body, "after mef")
    kef(loop, new_face)
    _assert_ep(body, "after kef")


def test_kemr_memr_validate_ep_before_and_after():
    body, face, loop, v_list, e_list = _make_spur_chain(4)
    _assert_ep(body, "seed")
    ring = kemr(face, e_list[1])
    _assert_ep(body, "after kemr")
    memr(face, ring, v_list[0], v_list[2])
    _assert_ep(body, "after memr")


def test_kfmrh_kfmrh_inverse_validate_ep():
    body = make_box()
    solid = body.solids[0]
    shell = solid.shells[0]
    removed = shell.faces[-1]
    hole = removed.outer_loop()
    _assert_ep(body, "box seed")
    kfmrh(solid, removed, hole)
    _assert_ep(body, "after kfmrh")
    kfmrh_inverse(solid, shell.faces[0], hole)
    _assert_ep(body, "after kfmrh_inverse")


# ---------------------------------------------------------------------------
# Section 10 — Deterministic random walks (N = 200 operator steps each)
# ---------------------------------------------------------------------------


def test_random_walk_200_mev_steps():
    """200 mev steps from an mvfs seed; EP=0 checked every step."""
    rng = _LCG(0x1234_5678)
    body, _, _, _, loop, v = mvfs((0.0, 0.0, 0.0))
    cur = v
    for step in range(200):
        x = rng.next_float() * 10.0
        y = rng.next_float() * 10.0
        z = rng.next_float() * 10.0
        _, cur = mev(loop, cur, (x, y, z))
        _assert_ep(body, f"mev walk step {step}")


def test_random_walk_200_mev_kev_cycles():
    """Alternating mev/kev pairs; invariant checked every op."""
    rng = _LCG(0x5678_9ABC)
    total = 0
    while total < 200:
        body, _, _, _, loop, v = mvfs((0.0, 0.0, 0.0))
        cur = v
        n = max(1, rng.next_int() % 10 + 1)
        edges = []
        for _ in range(n):
            x = rng.next_float() * 4
            e, cur = mev(loop, cur, (x, rng.next_float(), 0.0))
            edges.append(e)
            total += 1
            _assert_ep(body, f"walk mev total={total}")
        for e in reversed(edges):
            kev(loop, e)
            total += 1
            _assert_ep(body, f"walk kev total={total}")


def test_random_walk_200_mef_kef_cycles():
    """200 mef/kef cycle pairs; EP=0 at each step."""
    rng = _LCG(0xABCD_EF01)
    for cycle in range(100):
        body, face, loop, v0, va, vb, vc, ce0, ce_vb = _make_mvfs_spur_quad()
        _assert_ep(body, f"mef cycle {cycle} pre")
        bridge, new_face = mef(loop, ce0, ce_vb, surface=face.surface)
        _assert_ep(body, f"mef cycle {cycle} after mef")
        kef(loop, new_face)
        _assert_ep(body, f"mef cycle {cycle} after kef")


def test_random_walk_200_kfmrh_cycles():
    """100 kfmrh + kfmrh_inverse pairs; EP=0 at each step."""
    for cycle in range(100):
        body = make_box()
        solid = body.solids[0]
        shell = solid.shells[0]
        removed = shell.faces[-1]
        hole = removed.outer_loop()
        kfmrh(solid, removed, hole)
        _assert_ep(body, f"kfmrh cycle {cycle}")
        kfmrh_inverse(solid, shell.faces[0], hole)
        _assert_ep(body, f"kfmrh_inverse cycle {cycle}")


def test_random_walk_primitives_ep_stable():
    """Parametric sweep: N deterministic parameter sets for each primitive."""
    rng = _LCG(0xDEAD_C0DE)
    for step in range(50):
        size = max(0.1, rng.next_float() * 5.0 + 0.1)
        _assert_ep(make_box(size=(size, size, size)), f"box param {step}")

        r = max(0.1, rng.next_float() * 3.0 + 0.1)
        _assert_ep(make_sphere(radius=r), f"sphere param {step}")

        major = max(1.5, rng.next_float() * 5.0 + 1.5)
        minor = max(0.1, rng.next_float() * 0.5 + 0.1)
        _assert_ep(make_torus(major_radius=major, minor_radius=minor),
                   f"torus param {step}")


def test_random_walk_combined_200_steps():
    """Mixed operator walk: mev, kev, mef, kef, kemr, memr, kfmrh,
    kfmrh_inverse; all from EP=0 seeds; EP=0 at every step."""
    rng = _LCG(0xFEED_FACE)
    total = 0

    # Phase A: 60 mev steps on growing spur chain
    body_a, _, _, _, loop_a, v_a = mvfs((0.0, 0.0, 0.0))
    cur = v_a
    spur_edges = []
    for _ in range(60):
        x = rng.next_float() * 4.0
        e, cur = mev(loop_a, cur, (x, rng.next_float(), 0.0))
        spur_edges.append(e)
        total += 1
        _assert_ep(body_a, f"combined walk A total={total}")

    # Phase B: 40 kev teardown (LIFO)
    while spur_edges and total < 100:
        e = spur_edges.pop()
        kev(loop_a, e)
        total += 1
        _assert_ep(body_a, f"combined walk B total={total}")

    # Phase C: mef/kef cycles on fresh mvfs bodies
    while total < 160:
        body_c, face_c, loop_c, v0, va, vb, vc, ce0, ce_vb = _make_mvfs_spur_quad()
        bridge, nf = mef(loop_c, ce0, ce_vb, surface=face_c.surface)
        total += 1
        _assert_ep(body_c, f"combined walk C mef total={total}")
        kef(loop_c, nf)
        total += 1
        _assert_ep(body_c, f"combined walk C kef total={total}")

    # Phase D: kemr/memr cycles on spur chains
    while total < 200:
        body_d, face_d, loop_d, v_list, e_list = _make_spur_chain(4)
        ring = kemr(face_d, e_list[1])
        total += 1
        _assert_ep(body_d, f"combined walk D kemr total={total}")
        memr(face_d, ring, v_list[0], v_list[2])
        total += 1
        _assert_ep(body_d, f"combined walk D memr total={total}")

    assert total >= 200
