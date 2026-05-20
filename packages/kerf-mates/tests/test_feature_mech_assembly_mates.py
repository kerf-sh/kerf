"""
T-22 Mech: assembly + mates — hermetic pytest suite.

Covers:
  - 25 parametric assemblies (≥10 parts each)
  - coincident / concentric / distance / angle mates resolve
  - over-constrained and under-constrained detection
  - chain_walk BFS path building
  - Mate round-trip serialisation (to_dict / from_dict)
  - boundary / malformed / idempotency cases

All tests are purely in-process (no DB, no network, no OCCT).
Imports from:
  - kerf_cad_core.assembly.mates  (solve_assembly, Mate, MateType)
  - kerf_cad_core.assembly.model  (Assembly, Component, _identity)
  - kerf_mates.chain_walk         (build_chain_from_assembly)
"""
from __future__ import annotations

import math
import uuid
from typing import Any

import pytest

from kerf_cad_core.assembly.model import (
    Assembly,
    Component,
    _identity,
    _mat_mul,
    _transform_point,
)
from kerf_cad_core.assembly.mates import (
    Mate,
    MateType,
    solve_assembly as solve_asm_core,
)
from kerf_mates.chain_walk import build_chain_from_assembly


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _T(tx: float = 0.0, ty: float = 0.0, tz: float = 0.0) -> list[float]:
    """Pure-translation 4×4 matrix."""
    t = _identity()
    t[3] = tx
    t[7] = ty
    t[11] = tz
    return t


def _approx(a: float, b: float, tol: float = 1e-4) -> bool:
    return abs(a - b) < tol


def _vec_approx(u, v, tol: float = 1e-4) -> bool:
    return all(_approx(a, b, tol) for a, b in zip(u, v))


def _build_assembly(*part_refs: str, offsets=None) -> Assembly:
    """
    Build an Assembly from an ordered list of part_refs.
    ``offsets`` is a list of (tx, ty, tz) tuples; defaults to (i*50, 0, 0).
    """
    asm = Assembly(name="test-asm")
    for i, ref in enumerate(part_refs):
        ox, oy, oz = offsets[i] if offsets else (i * 50.0, 0.0, 0.0)
        asm.add_component(Component(part_ref=ref, transform=_T(ox, oy, oz)))
    return asm


def _iid(asm: Assembly, idx: int) -> str:
    return asm.components[idx].instance_id


def _solve(asm: Assembly, mates: list[Mate]) -> dict:
    return solve_asm_core(asm, mates)


# ---------------------------------------------------------------------------
# 1. Empty assembly
# ---------------------------------------------------------------------------

class TestEmptyAssembly:
    def test_empty_returns_ok(self):
        asm = Assembly()
        result = _solve(asm, [])
        assert result["ok"] is True
        assert result["status"] == "fully_constrained"
        assert result["components"] == []


# ---------------------------------------------------------------------------
# 2. Single-component ground — always fully constrained
# ---------------------------------------------------------------------------

class TestSingleComponent:
    def test_single_fully_constrained(self):
        asm = _build_assembly("base_plate")
        result = _solve(asm, [])
        # Ground component: 0 DOF, no mates needed
        assert result["status"] == "fully_constrained"
        assert result["dof_remaining"] == 0

    def test_single_component_transform_preserved(self):
        T = _T(10.0, 20.0, 30.0)
        asm = Assembly()
        asm.add_component(Component(part_ref="bracket", transform=T))
        result = _solve(asm, [])
        assert result["ok"] is True
        comp = result["components"][0]
        assert comp["transform"] == T


# ---------------------------------------------------------------------------
# 3. Two-part coincident mate (face-to-face)
# ---------------------------------------------------------------------------

class TestCoincidentMate:
    def _two_part(self):
        asm = _build_assembly("base", "lid", offsets=[(0, 0, 0), (0, 0, 50)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        return asm, a, b

    def test_coincident_resolves(self):
        asm, a, b = self._two_part()
        mate = Mate(
            MateType.COINCIDENT, a, b,
            point_a=(0, 0, 0), normal_a=(0, 0, 1),
            point_b=(0, 0, 0), normal_b=(0, 0, -1),
        )
        result = _solve(asm, [mate])
        assert result["ok"] is True
        assert result["status"] == "under_constrained"   # 3 of 6 DOF removed

    def test_coincident_dof_count(self):
        asm, a, b = self._two_part()
        mate = Mate(MateType.COINCIDENT, a, b)
        result = _solve(asm, [mate])
        # Ground=0, second part=6-3=3
        assert result["dof_remaining"] == 3

    def test_coincident_with_offset(self):
        asm, a, b = self._two_part()
        mate = Mate(
            MateType.COINCIDENT, a, b,
            point_a=(0, 0, 0), normal_a=(0, 0, 1),
            point_b=(0, 0, 0), normal_b=(0, 0, -1),
            offset=10.0,
        )
        result = _solve(asm, [mate])
        assert result["ok"] is True
        # Free component translated along normal by offset
        T_b = result["components"][1]["transform"]
        z_trans = T_b[11]
        assert _approx(z_trans, 10.0, tol=1e-3)

    def test_coincident_face_points_coplanar(self):
        asm, a, b = self._two_part()
        mate = Mate(
            MateType.COINCIDENT, a, b,
            point_a=(0, 0, 5), normal_a=(0, 0, 1),
            point_b=(0, 0, 0), normal_b=(0, 0, -1),
        )
        result = _solve(asm, [mate])
        assert result["ok"] is True
        # After solve, free-component face point at world z=5
        T_b = result["components"][1]["transform"]
        free_pt = _transform_point(T_b, (0, 0, 0))
        assert _approx(free_pt[2], 5.0, tol=1e-3)


# ---------------------------------------------------------------------------
# 4. Two-part concentric mate (axis-to-axis)
# ---------------------------------------------------------------------------

class TestConcentricMate:
    def test_concentric_resolves(self):
        asm = _build_assembly("shaft", "bushing", offsets=[(0, 0, 0), (5, 5, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(
            MateType.CONCENTRIC, a, b,
            point_a=(0, 0, 0), normal_a=(0, 0, 1),
            point_b=(0, 0, 0), normal_b=(0, 0, 1),
        )
        result = _solve(asm, [mate])
        assert result["ok"] is True

    def test_concentric_dof_count(self):
        asm = _build_assembly("bolt", "nut", offsets=[(0, 0, 0), (3, 3, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(MateType.CONCENTRIC, a, b)
        result = _solve(asm, [mate])
        # 6 - 4 = 2 DOF remaining on free component
        assert result["dof_remaining"] == 2

    def test_concentric_axes_colinear_after_solve(self):
        asm = _build_assembly("pin", "collar", offsets=[(0, 0, 0), (10, 10, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(
            MateType.CONCENTRIC, a, b,
            point_a=(0, 0, 0), normal_a=(0, 0, 1),
            point_b=(0, 0, 0), normal_b=(0, 0, 1),
        )
        result = _solve(asm, [mate])
        assert result["ok"] is True
        T_b = result["components"][1]["transform"]
        # After concentric, axis point of b is on a's axis
        world_pt_b = _transform_point(T_b, (0, 0, 0))
        # Lateral offset (x,y) should be near 0
        assert _approx(world_pt_b[0], 0.0, tol=1e-3)
        assert _approx(world_pt_b[1], 0.0, tol=1e-3)


# ---------------------------------------------------------------------------
# 5. Distance mate
# ---------------------------------------------------------------------------

class TestDistanceMate:
    def test_distance_resolves(self):
        asm = _build_assembly("wall_a", "wall_b", offsets=[(0, 0, 0), (100, 0, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(
            MateType.DISTANCE, a, b,
            point_a=(0, 0, 0), normal_a=(1, 0, 0),
            point_b=(0, 0, 0),
            offset=25.0,
        )
        result = _solve(asm, [mate])
        assert result["ok"] is True

    def test_distance_correct_offset(self):
        asm = _build_assembly("block_a", "block_b", offsets=[(0, 0, 0), (200, 0, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(
            MateType.DISTANCE, a, b,
            point_a=(0, 0, 0), normal_a=(1, 0, 0),
            point_b=(0, 0, 0),
            offset=50.0,
        )
        result = _solve(asm, [mate])
        assert result["ok"] is True
        T_b = result["components"][1]["transform"]
        world_b = _transform_point(T_b, (0, 0, 0))
        assert _approx(world_b[0], 50.0, tol=1e-3)

    def test_distance_zero_offset(self):
        asm = _build_assembly("face_a", "face_b", offsets=[(0, 0, 0), (80, 0, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(
            MateType.DISTANCE, a, b,
            point_a=(0, 0, 0), normal_a=(1, 0, 0),
            point_b=(0, 0, 0),
            offset=0.0,
        )
        result = _solve(asm, [mate])
        assert result["ok"] is True
        T_b = result["components"][1]["transform"]
        world_b = _transform_point(T_b, (0, 0, 0))
        assert _approx(world_b[0], 0.0, tol=1e-3)

    def test_distance_dof_one(self):
        asm = _build_assembly("plate_a", "plate_b", offsets=[(0, 0, 0), (50, 0, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(MateType.DISTANCE, a, b, offset=20.0)
        result = _solve(asm, [mate])
        # 6 - 1 = 5 DOF remaining
        assert result["dof_remaining"] == 5


# ---------------------------------------------------------------------------
# 6. Angle mate
# ---------------------------------------------------------------------------

class TestAngleMate:
    def test_angle_45_resolves(self):
        asm = _build_assembly("hinge_base", "hinge_arm", offsets=[(0, 0, 0), (0, 0, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(
            MateType.ANGLE, a, b,
            normal_a=(0, 0, 1),
            normal_b=(0, 0, 1),
            angle_deg=45.0,
        )
        result = _solve(asm, [mate])
        assert result["ok"] is True

    def test_angle_90_resolves(self):
        asm = _build_assembly("arm_base", "arm_link", offsets=[(0, 0, 0), (0, 0, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(
            MateType.ANGLE, a, b,
            normal_a=(0, 0, 1),
            normal_b=(0, 0, 1),
            angle_deg=90.0,
        )
        result = _solve(asm, [mate])
        assert result["ok"] is True

    def test_angle_zero_resolves(self):
        asm = _build_assembly("face_p", "face_q", offsets=[(0, 0, 0), (0, 0, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(
            MateType.ANGLE, a, b,
            normal_a=(0, 0, 1),
            normal_b=(0, 0, 1),
            angle_deg=0.0,
        )
        result = _solve(asm, [mate])
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# 7. Parallel & perpendicular
# ---------------------------------------------------------------------------

class TestParallelPerpendicularMates:
    def test_parallel_resolves(self):
        asm = _build_assembly("rail_a", "rail_b", offsets=[(0, 0, 0), (0, 10, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(
            MateType.PARALLEL, a, b,
            normal_a=(0, 0, 1),
            normal_b=(0, 0, 1),
        )
        result = _solve(asm, [mate])
        assert result["ok"] is True
        assert result["dof_remaining"] == 4  # 6-2

    def test_perpendicular_resolves(self):
        asm = _build_assembly("rib_a", "rib_b", offsets=[(0, 0, 0), (0, 10, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(
            MateType.PERPENDICULAR, a, b,
            normal_a=(0, 0, 1),
            normal_b=(1, 0, 0),
        )
        result = _solve(asm, [mate])
        assert result["ok"] is True
        assert result["dof_remaining"] == 5  # 6-1


# ---------------------------------------------------------------------------
# 8. Lock mate
# ---------------------------------------------------------------------------

class TestLockMate:
    def test_lock_fully_constrains(self):
        asm = _build_assembly("chassis", "motor", offsets=[(0, 0, 0), (20, 0, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(MateType.LOCK, a, b)
        result = _solve(asm, [mate])
        assert result["ok"] is True
        assert result["status"] == "fully_constrained"
        assert result["dof_remaining"] == 0

    def test_lock_sets_transform_to_ground(self):
        T_ground = _T(5.0, 10.0, 15.0)
        asm = Assembly()
        asm.add_component(Component(part_ref="ground", transform=T_ground))
        asm.add_component(Component(part_ref="follower", transform=_T(99, 99, 99)))
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(MateType.LOCK, a, b)
        result = _solve(asm, [mate])
        assert result["ok"] is True
        assert result["components"][1]["transform"] == T_ground


# ---------------------------------------------------------------------------
# 9. Tangent mate
# ---------------------------------------------------------------------------

class TestTangentMate:
    def test_tangent_resolves(self):
        asm = _build_assembly("cylinder", "flat_plane", offsets=[(0, 0, 0), (0, 0, 30)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(
            MateType.TANGENT, a, b,
            point_a=(0, 0, 0), normal_a=(0, 0, 1),
            point_b=(0, 0, 0),
            offset=10.0,  # cylinder radius
        )
        result = _solve(asm, [mate])
        assert result["ok"] is True


# ---------------------------------------------------------------------------
# 10. Over-constrained detection
# ---------------------------------------------------------------------------

class TestOverConstrained:
    def test_double_lock_over_constrained(self):
        asm = _build_assembly("base", "part", offsets=[(0, 0, 0), (10, 0, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mates = [
            Mate(MateType.LOCK, a, b),
            Mate(MateType.LOCK, a, b),
        ]
        result = _solve(asm, mates)
        assert result["status"] == "over_constrained"
        assert len(result["errors"]) >= 1

    def test_over_constrained_dof_already_zero(self):
        asm = _build_assembly("prt_a", "prt_b", offsets=[(0, 0, 0), (0, 0, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        # Concentric removes 4 DOF, then another concentric tries to remove 4 more
        mates = [
            Mate(MateType.CONCENTRIC, a, b),
            Mate(MateType.CONCENTRIC, a, b),
        ]
        result = _solve(asm, mates)
        # Second concentric should flag over-constrained (only 2 left)
        assert result["status"] == "over_constrained"

    def test_errors_list_populated_on_over_constrain(self):
        asm = _build_assembly("g", "f", offsets=[(0, 0, 0), (0, 0, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mates = [
            Mate(MateType.LOCK, a, b),
            Mate(MateType.COINCIDENT, a, b),
        ]
        result = _solve(asm, mates)
        assert result["status"] == "over_constrained"
        assert any("Over-constrained" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# 11. Under-constrained detection
# ---------------------------------------------------------------------------

class TestUnderConstrained:
    def test_two_free_parts_no_mates(self):
        asm = _build_assembly("p1", "p2")
        result = _solve(asm, [])
        assert result["status"] == "under_constrained"
        assert result["dof_remaining"] == 6

    def test_partial_constraint_under_constrained(self):
        asm = _build_assembly("a", "b")
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(MateType.COINCIDENT, a, b)  # removes 3 of 6
        result = _solve(asm, [mate])
        assert result["status"] == "under_constrained"
        assert result["dof_remaining"] == 3


# ---------------------------------------------------------------------------
# 12. Invalid instance ids
# ---------------------------------------------------------------------------

class TestInvalidMateRefs:
    def test_unknown_instance_id_a(self):
        asm = _build_assembly("real_part")
        mate = Mate(MateType.COINCIDENT, "nonexistent-id", _iid(asm, 0))
        result = _solve(asm, [mate])
        assert result["ok"] is False
        assert any("nonexistent-id" in e for e in result["errors"])

    def test_unknown_instance_id_b(self):
        asm = _build_assembly("real_part")
        mate = Mate(MateType.COINCIDENT, _iid(asm, 0), "ghost-id")
        result = _solve(asm, [mate])
        assert result["ok"] is False
        assert any("ghost-id" in e for e in result["errors"])

    def test_both_unknown_ids(self):
        asm = _build_assembly("real_part")
        mate = Mate(MateType.COINCIDENT, "bad_a", "bad_b")
        result = _solve(asm, [mate])
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# 13. Mate round-trip serialisation
# ---------------------------------------------------------------------------

class TestMateSerialisation:
    def test_to_dict_from_dict_roundtrip(self):
        m = Mate(
            MateType.DISTANCE, "inst-a", "inst-b",
            point_a=(1.0, 2.0, 3.0), normal_a=(0, 0, 1),
            point_b=(4.0, 5.0, 6.0), normal_b=(0, 1, 0),
            offset=15.0, angle_deg=30.0, mate_id="m-001",
        )
        d = m.to_dict()
        m2 = Mate.from_dict(d)
        assert m2.mate_id == "m-001"
        assert m2.mate_type == MateType.DISTANCE
        assert m2.instance_id_a == "inst-a"
        assert m2.instance_id_b == "inst-b"
        assert m2.offset == 15.0
        assert m2.angle_deg == 30.0
        assert _vec_approx(m2.point_a, (1.0, 2.0, 3.0))
        assert _vec_approx(m2.normal_b, (0, 1, 0))

    def test_mate_type_string_coercion(self):
        m = Mate("concentric", "a", "b")
        assert m.mate_type == MateType.CONCENTRIC

    def test_invalid_mate_type_string_raises(self):
        with pytest.raises(ValueError):
            Mate("flying", "a", "b")

    def test_mate_auto_id_is_unique(self):
        m1 = Mate(MateType.LOCK, "a", "b")
        m2 = Mate(MateType.LOCK, "a", "b")
        assert m1.mate_id != m2.mate_id

    def test_all_mate_types_round_trip(self):
        for mt in MateType:
            m = Mate(mt, "x", "y", mate_id=f"rt-{mt.value}")
            d = m.to_dict()
            m2 = Mate.from_dict(d)
            assert m2.mate_type == mt


# ---------------------------------------------------------------------------
# 14. Idempotency: solving twice gives same result
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_same_result_on_repeated_solve(self):
        asm = _build_assembly("base", "arm", offsets=[(0, 0, 0), (30, 0, 0)])
        a, b = _iid(asm, 0), _iid(asm, 1)
        mate = Mate(
            MateType.COINCIDENT, a, b,
            point_a=(0, 0, 0), normal_a=(1, 0, 0),
            point_b=(0, 0, 0), normal_b=(-1, 0, 0),
        )
        r1 = _solve(asm, [mate])
        r2 = _solve(asm, [mate])
        assert r1["status"] == r2["status"]
        assert r1["dof_remaining"] == r2["dof_remaining"]
        for c1, c2 in zip(r1["components"], r2["components"]):
            for v1, v2 in zip(c1["transform"], c2["transform"]):
                assert _approx(v1, v2)


# ---------------------------------------------------------------------------
# 15. Large assemblies — 25 parametric scenarios (≥10 parts each)
# ---------------------------------------------------------------------------

class TestLargeAssemblies:
    """
    Each test builds an assembly with ≥10 parts and applies a mix of mate
    types.  Checks that solve completes without crash and produces a valid
    status.
    """

    # ── helper ──────────────────────────────────────────────────────────────
    @staticmethod
    def _n_part_asm(n: int, spread: float = 50.0) -> Assembly:
        asm = Assembly(name=f"{n}-part-asm")
        for i in range(n):
            asm.add_component(Component(
                part_ref=f"part_{i}",
                transform=_T(i * spread, 0.0, 0.0),
            ))
        return asm

    @staticmethod
    def _ids(asm: Assembly) -> list[str]:
        return [c.instance_id for c in asm.components]

    # ── assembly 1: 10-part linear chain via distance mates ─────────────────
    def test_asm_01_linear_distance_chain(self):
        n = 10
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates = [
            Mate(MateType.DISTANCE, ids[i], ids[i + 1],
                 point_a=(0, 0, 0), normal_a=(1, 0, 0),
                 point_b=(0, 0, 0), offset=float(i + 1) * 10)
            for i in range(n - 1)
        ]
        result = _solve(asm, mates)
        assert "status" in result

    # ── assembly 2: 10-part star via lock to ground ──────────────────────────
    def test_asm_02_star_lock_to_ground(self):
        n = 10
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates = [Mate(MateType.LOCK, ids[0], ids[i]) for i in range(1, n)]
        result = _solve(asm, mates)
        assert result["status"] == "fully_constrained"

    # ── assembly 3: 12-part coincident chain ────────────────────────────────
    def test_asm_03_coincident_chain(self):
        n = 12
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates = [
            Mate(MateType.COINCIDENT, ids[i], ids[i + 1])
            for i in range(n - 1)
        ]
        result = _solve(asm, mates)
        assert "status" in result

    # ── assembly 4: 10-part concentric stack ────────────────────────────────
    def test_asm_04_concentric_stack(self):
        n = 10
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates = [
            Mate(MateType.CONCENTRIC, ids[i], ids[i + 1],
                 point_a=(0, 0, 0), normal_a=(0, 0, 1),
                 point_b=(0, 0, 0), normal_b=(0, 0, 1))
            for i in range(n - 1)
        ]
        result = _solve(asm, mates)
        assert "status" in result

    # ── assembly 5: 10-part angle chain (hinge array) ───────────────────────
    def test_asm_05_angle_chain(self):
        n = 10
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates = [
            Mate(MateType.ANGLE, ids[i], ids[i + 1],
                 normal_a=(0, 0, 1), normal_b=(0, 0, 1),
                 angle_deg=float(i * 15))
            for i in range(n - 1)
        ]
        result = _solve(asm, mates)
        assert "status" in result

    # ── assembly 6: 11-part mixed (coincident + concentric + distance) ───────
    def test_asm_06_mixed_mates(self):
        n = 11
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates: list[Mate] = []
        mates.append(Mate(MateType.COINCIDENT, ids[0], ids[1]))
        mates.append(Mate(MateType.CONCENTRIC, ids[1], ids[2],
                          point_a=(0, 0, 0), normal_a=(0, 0, 1),
                          point_b=(0, 0, 0), normal_b=(0, 0, 1)))
        for i in range(2, n - 1):
            mates.append(Mate(MateType.DISTANCE, ids[i], ids[i + 1],
                              point_a=(0, 0, 0), normal_a=(1, 0, 0),
                              point_b=(0, 0, 0), offset=float(i) * 5))
        result = _solve(asm, mates)
        assert "status" in result

    # ── assembly 7: 10-part parallel array ──────────────────────────────────
    def test_asm_07_parallel_array(self):
        n = 10
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates = [
            Mate(MateType.PARALLEL, ids[i], ids[i + 1],
                 normal_a=(0, 0, 1), normal_b=(0, 0, 1))
            for i in range(n - 1)
        ]
        result = _solve(asm, mates)
        assert "status" in result

    # ── assembly 8: 10-part perpendicular array ──────────────────────────────
    def test_asm_08_perpendicular_array(self):
        n = 10
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates = [
            Mate(MateType.PERPENDICULAR, ids[i], ids[i + 1],
                 normal_a=(0, 0, 1), normal_b=(1, 0, 0))
            for i in range(n - 1)
        ]
        result = _solve(asm, mates)
        assert "status" in result

    # ── assembly 9: 10-part tangent (cylinder-on-plane) array ────────────────
    def test_asm_09_tangent_array(self):
        n = 10
        asm = self._n_part_asm(n, spread=20.0)
        ids = self._ids(asm)
        mates = [
            Mate(MateType.TANGENT, ids[i], ids[i + 1],
                 point_a=(0, 0, 0), normal_a=(0, 0, 1),
                 point_b=(0, 0, 0), offset=5.0)
            for i in range(n - 1)
        ]
        result = _solve(asm, mates)
        assert "status" in result

    # ── assembly 10: 15-part fully constrained via alternating lock pairs ─────
    def test_asm_10_alternating_lock(self):
        n = 15
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates = [Mate(MateType.LOCK, ids[0], ids[i]) for i in range(1, n)]
        result = _solve(asm, mates)
        assert result["status"] == "fully_constrained"
        assert result["dof_remaining"] == 0

    # ── assembly 11: 10-part BOM presence check ──────────────────────────────
    def test_asm_11_bom_all_parts_present(self):
        n = 10
        refs = [f"component_{chr(65 + i)}" for i in range(n)]
        asm = Assembly(name="bom-check")
        for i, ref in enumerate(refs):
            asm.add_component(Component(part_ref=ref, transform=_T(i * 30)))
        ids = self._ids(asm)
        mates = [Mate(MateType.LOCK, ids[0], ids[i]) for i in range(1, n)]
        result = _solve(asm, mates)
        present = {c["part_ref"] for c in result["components"]}
        assert present == set(refs)

    # ── assembly 12: 10-part; ground transform propagated correctly ──────────
    def test_asm_12_ground_transform_identity(self):
        n = 10
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates = [Mate(MateType.LOCK, ids[0], ids[i]) for i in range(1, n)]
        result = _solve(asm, mates)
        # Ground (first component) transform is unchanged
        ground_T = result["components"][0]["transform"]
        # First component was placed at _T(0, 0, 0) which is identity
        assert ground_T == _identity()

    # ── assembly 13: 10-part; distance mates to known positions ─────────────
    def test_asm_13_distance_absolute_positions(self):
        n = 10
        asm = Assembly(name="dist-pos")
        for i in range(n):
            asm.add_component(Component(part_ref=f"p{i}", transform=_identity()))
        ids = self._ids(asm)
        mates = [
            Mate(MateType.DISTANCE, ids[0], ids[i],
                 point_a=(0, 0, 0), normal_a=(1, 0, 0),
                 point_b=(0, 0, 0), offset=float(i) * 10.0)
            for i in range(1, n)
        ]
        result = _solve(asm, mates)
        assert "status" in result
        # No errors expected
        assert result["ok"] is True

    # ── assembly 14: 10-part angle fan ──────────────────────────────────────
    def test_asm_14_angle_fan_from_ground(self):
        n = 10
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        step = 360.0 / n
        mates = [
            Mate(MateType.ANGLE, ids[0], ids[i],
                 normal_a=(0, 0, 1), normal_b=(0, 0, 1),
                 angle_deg=i * step)
            for i in range(1, n)
        ]
        result = _solve(asm, mates)
        assert result["ok"] is True

    # ── assembly 15: 10-part concentric + coincident (shaft-in-bore) ─────────
    def test_asm_15_shaft_in_bore(self):
        n = 10
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates: list[Mate] = []
        for i in range(1, n):
            # Concentric removes 4 DOF; coincident removes 3 → attempt but
            # only 2 DOF remain after concentric → will over-constrain pair 2
            mates.append(Mate(MateType.CONCENTRIC, ids[0], ids[i],
                              point_a=(0, 0, 0), normal_a=(0, 0, 1),
                              point_b=(0, 0, 0), normal_b=(0, 0, 1)))
        result = _solve(asm, mates)
        # Each part constrained individually to ground via concentric
        assert "status" in result

    # ── assembly 16: 12-part; Mate.from_dict round-trips in a live solve ─────
    def test_asm_16_dict_roundtrip_mates(self):
        n = 12
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates_orig = [
            Mate(MateType.DISTANCE, ids[i], ids[i + 1],
                 point_a=(0, 0, 0), normal_a=(1, 0, 0),
                 point_b=(0, 0, 0), offset=float(i + 1) * 8.0)
            for i in range(n - 1)
        ]
        mates_rt = [Mate.from_dict(m.to_dict()) for m in mates_orig]
        r_orig = _solve(asm, mates_orig)
        r_rt = _solve(asm, mates_rt)
        assert r_orig["status"] == r_rt["status"]
        assert r_orig["dof_remaining"] == r_rt["dof_remaining"]

    # ── assembly 17: 10-part; sub-assembly nesting ──────────────────────────
    def test_asm_17_sub_assembly_nesting(self):
        sub = Assembly(name="sub")
        for i in range(5):
            sub.add_component(Component(part_ref=f"sub_part_{i}", transform=_T(i * 20)))
        top = Assembly(name="top")
        for i in range(5):
            top.add_component(Component(part_ref=f"top_part_{i}", transform=_T(i * 20, 100)))
        top.add_sub_assembly(sub)
        all_comps = top.all_components()
        assert len(all_comps) == 10
        ids = [c.instance_id for c in all_comps]
        mates = [Mate(MateType.LOCK, ids[0], ids[i]) for i in range(1, len(ids))]
        result = _solve(top, mates)
        assert result["status"] == "fully_constrained"

    # ── assembly 18: 10-part with repeated same mate type list ───────────────
    def test_asm_18_repeated_coincident_chain(self):
        n = 10
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates = [
            Mate(MateType.COINCIDENT, ids[i], ids[i + 1],
                 point_a=(0, 0, 0), normal_a=(0, 0, 1),
                 point_b=(0, 0, 0), normal_b=(0, 0, -1))
            for i in range(n - 1)
        ]
        result = _solve(asm, mates)
        assert "status" in result

    # ── assembly 19: 10-part; zero-mate assembly, all under-constrained ──────
    def test_asm_19_all_under_constrained_no_mates(self):
        n = 10
        asm = self._n_part_asm(n)
        result = _solve(asm, [])
        assert result["status"] == "under_constrained"
        # 9 free parts × 6 DOF each
        assert result["dof_remaining"] == 9 * 6

    # ── assembly 20: 10-part; distance mate offset values vary ───────────────
    def test_asm_20_variable_offsets(self):
        n = 10
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        offsets = [5.0, 12.5, 0.0, 100.0, 1.0, 50.0, 25.0, 75.0, 10.0]
        mates = [
            Mate(MateType.DISTANCE, ids[i], ids[i + 1],
                 point_a=(0, 0, 0), normal_a=(1, 0, 0),
                 point_b=(0, 0, 0), offset=offsets[i])
            for i in range(n - 1)
        ]
        result = _solve(asm, mates)
        assert result["ok"] is True

    # ── assembly 21: 10-part; coincident normals antiparallel edge ───────────
    def test_asm_21_antiparallel_normals(self):
        n = 10
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates = [
            Mate(MateType.COINCIDENT, ids[i], ids[i + 1],
                 point_a=(0, 0, 0), normal_a=(0, 0, 1),
                 point_b=(0, 0, 0), normal_b=(0, 0, -1))
            for i in range(n - 1)
        ]
        result = _solve(asm, mates)
        assert result["ok"] is True

    # ── assembly 22: 10-part; mixed over-constrained detection ───────────────
    def test_asm_22_partial_overconstrain(self):
        n = 10
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates: list[Mate] = []
        # Lock all parts to ground first (valid)
        for i in range(1, n):
            mates.append(Mate(MateType.LOCK, ids[0], ids[i]))
        # Now try to coincident an already-locked part → over-constrained
        mates.append(Mate(MateType.COINCIDENT, ids[0], ids[1]))
        result = _solve(asm, mates)
        assert result["status"] == "over_constrained"

    # ── assembly 23: 10-part; concentric from non-z axis ─────────────────────
    def test_asm_23_concentric_x_axis(self):
        n = 10
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mates = [
            Mate(MateType.CONCENTRIC, ids[i], ids[i + 1],
                 point_a=(0, 0, 0), normal_a=(1, 0, 0),
                 point_b=(0, 0, 0), normal_b=(1, 0, 0))
            for i in range(n - 1)
        ]
        result = _solve(asm, mates)
        assert "status" in result

    # ── assembly 24: 10-part; large offset values (stress boundary) ──────────
    def test_asm_24_large_offset_values(self):
        n = 10
        asm = self._n_part_asm(n, spread=0.0)  # all at origin
        ids = self._ids(asm)
        mates = [
            Mate(MateType.DISTANCE, ids[i], ids[i + 1],
                 point_a=(0, 0, 0), normal_a=(0, 0, 1),
                 point_b=(0, 0, 0), offset=1_000_000.0)  # 1 km
            for i in range(n - 1)
        ]
        result = _solve(asm, mates)
        assert result["ok"] is True

    # ── assembly 25: 10-part; Mate explicit ids are preserved ────────────────
    def test_asm_25_explicit_mate_ids_preserved(self):
        n = 10
        asm = self._n_part_asm(n)
        ids = self._ids(asm)
        mate_ids = [f"explicit-{i}" for i in range(n - 1)]
        mates = [
            Mate(MateType.DISTANCE, ids[i], ids[i + 1],
                 point_a=(0, 0, 0), normal_a=(1, 0, 0),
                 point_b=(0, 0, 0), offset=10.0,
                 mate_id=mate_ids[i])
            for i in range(n - 1)
        ]
        for m, eid in zip(mates, mate_ids):
            assert m.mate_id == eid
        result = _solve(asm, mates)
        assert "status" in result


# ---------------------------------------------------------------------------
# 16. chain_walk: build_chain_from_assembly
# ---------------------------------------------------------------------------

class TestChainWalk:
    @staticmethod
    def _doc(mates: list[dict]) -> dict:
        return {"mates": mates}

    def test_simple_two_mate_path(self):
        doc = self._doc([
            {
                "id": "m1", "type": "distance", "value": 10.0, "unit": "mm",
                "a": {"component_id": "c1", "feature_id": "f1"},
                "b": {"component_id": "c2", "feature_id": "f2"},
            },
            {
                "id": "m2", "type": "distance", "value": 20.0, "unit": "mm",
                "a": {"component_id": "c2", "feature_id": "f3"},
                "b": {"component_id": "c3", "feature_id": "f4"},
            },
        ])
        chain = build_chain_from_assembly(
            doc,
            {"component_id": "c1", "feature_id": "f1"},
            {"component_id": "c3", "feature_id": "f4"},
        )
        assert isinstance(chain, list)
        # Two distance mates should give 2 entries
        assert len(chain) == 2
        assert chain[0]["nominal"] == 10.0
        assert chain[1]["nominal"] == 20.0

    def test_same_start_end_returns_empty(self):
        doc = self._doc([])
        chain = build_chain_from_assembly(
            doc,
            {"component_id": "c1", "feature_id": "f1"},
            {"component_id": "c1", "feature_id": "f1"},
        )
        assert chain == []

    def test_missing_feature_returns_error(self):
        doc = self._doc([
            {
                "id": "m1", "type": "distance", "value": 5.0, "unit": "mm",
                "a": {"component_id": "c1", "feature_id": "f1"},
                "b": {"component_id": "c2", "feature_id": "f2"},
            },
        ])
        result = build_chain_from_assembly(
            doc,
            {"component_id": "c_ghost", "feature_id": "fX"},
            {"component_id": "c2", "feature_id": "f2"},
        )
        assert isinstance(result, dict)
        assert "error" in result
        assert result["code"] == "NO_PATH"

    def test_bad_ref_missing_keys(self):
        doc = self._doc([])
        result = build_chain_from_assembly(
            doc,
            {},   # missing component_id / feature_id
            {"component_id": "c1", "feature_id": "f1"},
        )
        assert isinstance(result, dict)
        assert result["code"] == "BAD_REF"

    def test_bad_ref_not_a_dict(self):
        doc = self._doc([])
        result = build_chain_from_assembly(doc, "not-a-dict", {"component_id": "c1", "feature_id": "f1"})
        assert isinstance(result, dict)
        assert result["code"] == "BAD_REF"

    def test_zero_contribution_coincident_mate(self):
        doc = self._doc([
            {
                "id": "m1", "type": "coincident",
                "a": {"component_id": "c1", "feature_id": "f1"},
                "b": {"component_id": "c2", "feature_id": "f2"},
            },
        ])
        chain = build_chain_from_assembly(
            doc,
            {"component_id": "c1", "feature_id": "f1"},
            {"component_id": "c2", "feature_id": "f2"},
        )
        assert isinstance(chain, list)
        assert len(chain) == 1
        assert chain[0]["nominal"] == 0.0

    def test_fetch_part_dim_callback(self):
        doc = self._doc([
            {
                "id": "m1", "type": "distance", "value": 8.0, "unit": "mm",
                "a": {"component_id": "c1", "feature_id": "f1"},
                "b": {"component_id": "c2", "feature_id": "f2"},
            },
        ])

        def _fetch(comp_id: str, feat_id: str):
            return {"name": f"dim:{comp_id}:{feat_id}", "nominal": 1.0,
                    "plus": 0.05, "minus": 0.05, "unit": "mm"}

        chain = build_chain_from_assembly(
            doc,
            {"component_id": "c1", "feature_id": "f1"},
            {"component_id": "c2", "feature_id": "f2"},
            fetch_part_dim=_fetch,
        )
        assert isinstance(chain, list)
        # start part dim + mate + end part dim
        assert len(chain) == 3

    def test_tolerance_slot_in_chain(self):
        doc = self._doc([
            {
                "id": "m1", "type": "distance", "value": 15.0, "unit": "mm",
                "tolerance": {"plus": 0.1, "minus": 0.05},
                "a": {"component_id": "c1", "feature_id": "f1"},
                "b": {"component_id": "c2", "feature_id": "f2"},
            },
        ])
        chain = build_chain_from_assembly(
            doc,
            {"component_id": "c1", "feature_id": "f1"},
            {"component_id": "c2", "feature_id": "f2"},
        )
        assert isinstance(chain, list)
        entry = chain[0]
        assert entry["plus"] == 0.1
        assert entry["minus"] == 0.05

    def test_no_mate_path_returns_error(self):
        # Two disconnected islands
        doc = self._doc([
            {
                "id": "m1", "type": "distance", "value": 5.0, "unit": "mm",
                "a": {"component_id": "cA", "feature_id": "fA1"},
                "b": {"component_id": "cA", "feature_id": "fA2"},
            },
            {
                "id": "m2", "type": "distance", "value": 5.0, "unit": "mm",
                "a": {"component_id": "cB", "feature_id": "fB1"},
                "b": {"component_id": "cB", "feature_id": "fB2"},
            },
        ])
        result = build_chain_from_assembly(
            doc,
            {"component_id": "cA", "feature_id": "fA1"},
            {"component_id": "cB", "feature_id": "fB1"},
        )
        assert isinstance(result, dict)
        assert result["code"] == "NO_PATH"

    def test_empty_mates_list(self):
        doc = self._doc([])
        result = build_chain_from_assembly(
            doc,
            {"component_id": "c1", "feature_id": "f1"},
            {"component_id": "c2", "feature_id": "f2"},
        )
        assert isinstance(result, dict)
        assert "error" in result

    def test_angle_mate_nominal_value(self):
        doc = self._doc([
            {
                "id": "m1", "type": "angle", "value": 45.0, "unit": "deg",
                "a": {"component_id": "c1", "feature_id": "f1"},
                "b": {"component_id": "c2", "feature_id": "f2"},
            },
        ])
        chain = build_chain_from_assembly(
            doc,
            {"component_id": "c1", "feature_id": "f1"},
            {"component_id": "c2", "feature_id": "f2"},
        )
        assert isinstance(chain, list)
        assert chain[0]["nominal"] == 45.0
        assert chain[0]["mate_type"] == "angle"


# ---------------------------------------------------------------------------
# 17. Malformed inputs / boundary
# ---------------------------------------------------------------------------

class TestMalformedInputs:
    def test_coerce_vec_bad_value_raises(self):
        from kerf_cad_core.assembly.mates import _coerce_vec
        with pytest.raises(ValueError):
            _coerce_vec([1, 2])  # only 2 elements

    def test_coerce_vec_none_returns_none(self):
        from kerf_cad_core.assembly.mates import _coerce_vec
        assert _coerce_vec(None) is None

    def test_coerce_vec_accepts_tuple(self):
        from kerf_cad_core.assembly.mates import _coerce_vec
        v = _coerce_vec((1.0, 2.0, 3.0))
        assert v == (1.0, 2.0, 3.0)

    def test_component_whitespace_part_ref_stripped(self):
        c = Component(part_ref="  shaft  ")
        assert c.part_ref == "shaft"

    def test_assembly_duplicate_instance_id_raises(self):
        asm = Assembly()
        c = Component(part_ref="part", instance_id="fixed-id")
        asm.add_component(c)
        c2 = Component(part_ref="part2", instance_id="fixed-id")  # same id
        with pytest.raises(ValueError):
            asm.add_component(c2)

    def test_assembly_round_trip(self):
        asm = Assembly(name="rt-asm")
        for i in range(5):
            asm.add_component(Component(part_ref=f"p{i}", transform=_T(i * 10)))
        d = asm.to_dict()
        asm2 = Assembly.from_dict(d)
        assert asm2.name == "rt-asm"
        assert len(asm2.components) == 5
        for c, c2 in zip(asm.components, asm2.components):
            assert c.part_ref == c2.part_ref
            assert c.instance_id == c2.instance_id

    def test_solve_with_empty_mates_list(self):
        asm = _build_assembly("ground", "free_part")
        result = _solve(asm, [])
        assert result["status"] == "under_constrained"

    def test_validate_transform_wrong_length(self):
        from kerf_cad_core.assembly.model import _validate_transform
        with pytest.raises(ValueError):
            _validate_transform([1.0] * 9)

    def test_validate_transform_none_returns_identity(self):
        from kerf_cad_core.assembly.model import _validate_transform
        assert _validate_transform(None) == _identity()

    def test_validate_transform_bad_type_raises(self):
        from kerf_cad_core.assembly.model import _validate_transform
        with pytest.raises(ValueError):
            _validate_transform("not-a-matrix")
