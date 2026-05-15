"""
Tests for kerf_cad_core.assembly — Component/Assembly model, mates, DOF solver,
LLM tool wrappers, and BOM generation.

All tests are hermetic (pure-Python, no DB, no OCCT, no network).
"""

from __future__ import annotations

import asyncio
import json
import math
import uuid

import pytest

from kerf_cad_core.assembly.model import (
    Assembly,
    Component,
    _identity,
    _mat_mul,
    _transform_point,
    _transform_vector,
    _validate_transform,
)
from kerf_cad_core.assembly.mates import (
    Mate,
    MateType,
    solve_assembly,
)
from kerf_cad_core.assembly.tools import (
    _build_flat_bom,
    _build_tree_bom,
    run_assembly_create,
    run_assembly_add_component,
    run_assembly_add_mate,
    run_assembly_solve,
    run_assembly_bom,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _approx(a, b, tol=1e-6) -> bool:
    return abs(a - b) < tol


def _vec_approx(u, v, tol=1e-6) -> bool:
    return all(_approx(a, b, tol) for a, b in zip(u, v))


def _make_ctx():
    """Minimal fake ProjectCtx — tools only need it for type-checking."""
    class FakeCtx:
        pass
    return FakeCtx()


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _tool_call(tool_fn, args_dict: dict) -> dict:
    """
    Call a tool and return a normalised response dict with keys:
      ok      — bool (True if no 'error' key in response)
      payload — the response dict itself (on success) or {} on error
      code    — error code string (on error) or None
      raw     — the raw parsed dict
    """
    ctx = _make_ctx()
    raw = _run(tool_fn(ctx, json.dumps(args_dict).encode()))
    parsed = json.loads(raw)
    if "error" in parsed:
        return {"ok": False, "payload": {}, "code": parsed.get("code"), "raw": parsed}
    return {"ok": True, "payload": parsed, "code": None, "raw": parsed}


# ---------------------------------------------------------------------------
# 1. Model: identity transform
# ---------------------------------------------------------------------------

class TestIdentityTransform:
    def test_identity_is_16_floats(self):
        t = _identity()
        assert len(t) == 16
        assert t[0] == 1.0 and t[5] == 1.0 and t[10] == 1.0 and t[15] == 1.0

    def test_identity_diagonal(self):
        t = _identity()
        for i in range(4):
            for j in range(4):
                expected = 1.0 if i == j else 0.0
                assert _approx(t[i * 4 + j], expected), f"[{i},{j}] expected {expected}"

    def test_transform_point_identity(self):
        p = (3.0, 7.0, -2.0)
        result = _transform_point(_identity(), p)
        assert _vec_approx(result, p)

    def test_component_default_transform_is_identity(self):
        c = Component(part_ref="bolt")
        assert c.transform == _identity()

    def test_mat_mul_identity_identity(self):
        assert _mat_mul(_identity(), _identity()) == _identity()


# ---------------------------------------------------------------------------
# 2. Component round-trip
# ---------------------------------------------------------------------------

class TestComponent:
    def test_roundtrip(self):
        c = Component(part_ref="shaft", name="main-shaft")
        d = c.to_dict()
        c2 = Component.from_dict(d)
        assert c2.part_ref == "shaft"
        assert c2.name == "main-shaft"
        assert c2.instance_id == c.instance_id
        assert c2.transform == _identity()

    def test_empty_part_ref_raises(self):
        with pytest.raises(ValueError):
            Component(part_ref="")

    def test_invalid_transform_raises(self):
        with pytest.raises(ValueError):
            Component(part_ref="x", transform=[1, 2, 3])  # wrong length

    def test_explicit_instance_id(self):
        iid = str(uuid.uuid4())
        c = Component(part_ref="pin", instance_id=iid)
        assert c.instance_id == iid


# ---------------------------------------------------------------------------
# 3. Assembly model
# ---------------------------------------------------------------------------

class TestAssemblyModel:
    def test_add_and_get(self):
        asm = Assembly(name="test-asm")
        c = Component(part_ref="gear")
        asm.add_component(c)
        assert asm.get_component(c.instance_id) is c

    def test_duplicate_instance_raises(self):
        asm = Assembly()
        iid = str(uuid.uuid4())
        asm.add_component(Component(part_ref="a", instance_id=iid))
        with pytest.raises(ValueError):
            asm.add_component(Component(part_ref="b", instance_id=iid))

    def test_all_components_includes_sub(self):
        asm = Assembly()
        asm.add_component(Component(part_ref="top"))
        sub = Assembly(name="sub")
        sub.add_component(Component(part_ref="sub-part"))
        asm.add_sub_assembly(sub)
        all_comps = asm.all_components()
        assert len(all_comps) == 2
        refs = {c.part_ref for c in all_comps}
        assert refs == {"top", "sub-part"}

    def test_roundtrip(self):
        asm = Assembly(name="roundtrip")
        asm.add_component(Component(part_ref="p1", name="alpha"))
        asm.add_component(Component(part_ref="p1", name="beta"))
        d = asm.to_dict()
        asm2 = Assembly.from_dict(d)
        assert asm2.name == "roundtrip"
        assert len(asm2.components) == 2


# ---------------------------------------------------------------------------
# 4. Mate construction
# ---------------------------------------------------------------------------

class TestMate:
    def test_basic_mate(self):
        m = Mate("coincident", "a", "b")
        assert m.mate_type == MateType.COINCIDENT
        assert m.instance_id_a == "a"

    def test_invalid_mate_type(self):
        with pytest.raises(ValueError):
            Mate("bogus_type", "a", "b")

    def test_roundtrip(self):
        m = Mate(
            MateType.CONCENTRIC, "x", "y",
            point_a=(0, 0, 0), normal_a=(0, 0, 1),
            point_b=(5, 5, 0), normal_b=(0, 0, 1),
        )
        d = m.to_dict()
        m2 = Mate.from_dict(d)
        assert m2.mate_type == MateType.CONCENTRIC
        assert _vec_approx(m2.normal_a, (0, 0, 1))


# ---------------------------------------------------------------------------
# 5. Solver: identity placement (no mates)
# ---------------------------------------------------------------------------

class TestSolverIdentity:
    def test_single_component_no_mates(self):
        asm = Assembly()
        asm.add_component(Component(part_ref="base"))
        result = solve_assembly(asm, [])
        assert result["ok"] is True
        assert result["dof_remaining"] == 0
        assert result["status"] == "fully_constrained"
        assert result["components"][0]["transform"] == _identity()

    def test_two_components_no_mates(self):
        asm = Assembly()
        asm.add_component(Component(part_ref="a"))
        asm.add_component(Component(part_ref="b"))
        result = solve_assembly(asm, [])
        # b has 6 DOF unconstrained
        assert result["dof_remaining"] == 6
        assert result["status"] == "under_constrained"

    def test_empty_assembly(self):
        asm = Assembly()
        result = solve_assembly(asm, [])
        assert result["ok"] is True
        assert result["dof_remaining"] == 0
        assert result["components"] == []


# ---------------------------------------------------------------------------
# 6. Concentric mate: axis colinear
# ---------------------------------------------------------------------------

class TestConcentricMate:
    def test_concentric_reduces_dof_4(self):
        asm = Assembly()
        iid_a = "ground"
        iid_b = "free"
        asm.add_component(Component(part_ref="shaft", instance_id=iid_a))
        asm.add_component(Component(part_ref="bearing", instance_id=iid_b))

        mate = Mate(
            MateType.CONCENTRIC, iid_a, iid_b,
            point_a=(0, 0, 0), normal_a=(0, 0, 1),
            point_b=(10, 10, 0), normal_b=(0, 0, 1),
        )
        result = solve_assembly(asm, [mate])

        # 6 - 4 = 2 DOF remain
        assert result["dof_remaining"] == 2
        assert result["status"] == "under_constrained"

        # After concentric, the free component's axis reference point should
        # have zero lateral offset from the fixed axis.
        free_comp_result = next(
            c for c in result["components"] if c["instance_id"] == iid_b
        )
        T_solved = free_comp_result["transform"]
        # Transform the free point_b (10,10,0) into world space
        world_pt = _transform_point(T_solved, (10, 10, 0))
        # Lateral distance from Z-axis (fixed axis through origin along Z)
        lateral = math.sqrt(world_pt[0] ** 2 + world_pt[1] ** 2)
        assert lateral < 1e-6, f"Lateral offset {lateral} should be ~0"

    def test_concentric_already_colinear(self):
        """Concentric mate when axes are already colinear — should be no-op on rotation."""
        asm = Assembly()
        iid_a = "g"
        iid_b = "f"
        asm.add_component(Component(part_ref="a", instance_id=iid_a))
        asm.add_component(Component(part_ref="b", instance_id=iid_b))
        mate = Mate(
            MateType.CONCENTRIC, iid_a, iid_b,
            point_a=(0, 0, 0), normal_a=(0, 0, 1),
            point_b=(0, 0, 5), normal_b=(0, 0, 1),
        )
        result = solve_assembly(asm, [mate])
        assert result["ok"] is True
        assert result["dof_remaining"] == 2


# ---------------------------------------------------------------------------
# 7. Coincident mate with distance offset
# ---------------------------------------------------------------------------

class TestCoincidentMate:
    def test_coincident_reduces_dof_3(self):
        asm = Assembly()
        iid_a, iid_b = "ga", "fb"
        asm.add_component(Component(part_ref="plate", instance_id=iid_a))
        asm.add_component(Component(part_ref="lid", instance_id=iid_b))
        mate = Mate(
            MateType.COINCIDENT, iid_a, iid_b,
            point_a=(0, 0, 0), normal_a=(0, 0, 1),
            point_b=(0, 0, 0), normal_b=(0, 0, -1),
        )
        result = solve_assembly(asm, [mate])
        assert result["dof_remaining"] == 3   # 6 - 3

    def test_coincident_with_offset(self):
        """After coincident+offset the free face point should land at offset from fixed."""
        asm = Assembly()
        iid_a, iid_b = "g1", "f1"
        asm.add_component(Component(part_ref="base", instance_id=iid_a))
        asm.add_component(Component(part_ref="cover", instance_id=iid_b))
        offset = 5.0
        mate = Mate(
            MateType.COINCIDENT, iid_a, iid_b,
            point_a=(0, 0, 0), normal_a=(0, 0, 1),
            point_b=(0, 0, 0), normal_b=(0, 0, -1),
            offset=offset,
        )
        result = solve_assembly(asm, [mate])
        free_result = next(c for c in result["components"] if c["instance_id"] == iid_b)
        T = free_result["transform"]
        world_pt = _transform_point(T, (0, 0, 0))
        # Free face point should be at Z = offset
        assert _approx(world_pt[2], offset, tol=1e-5), (
            f"expected Z={offset}, got {world_pt[2]}"
        )


# ---------------------------------------------------------------------------
# 8. Parallel mate
# ---------------------------------------------------------------------------

class TestParallelMate:
    def test_parallel_reduces_dof_2(self):
        asm = Assembly()
        iid_a, iid_b = "gp", "fp"
        asm.add_component(Component(part_ref="rail", instance_id=iid_a))
        asm.add_component(Component(part_ref="slide", instance_id=iid_b))
        mate = Mate(
            MateType.PARALLEL, iid_a, iid_b,
            normal_a=(0, 0, 1),
            normal_b=(0, 1, 0),   # starts perpendicular → will be rotated to parallel
        )
        result = solve_assembly(asm, [mate])
        assert result["dof_remaining"] == 4   # 6 - 2

    def test_parallel_result_normals_are_parallel(self):
        asm = Assembly()
        iid_a, iid_b = "gpar", "fpar"
        asm.add_component(Component(part_ref="a", instance_id=iid_a))
        asm.add_component(Component(part_ref="b", instance_id=iid_b))
        mate = Mate(
            MateType.PARALLEL, iid_a, iid_b,
            normal_a=(1, 0, 0),
            normal_b=(0, 0, 1),
        )
        result = solve_assembly(asm, [mate])
        free_comp = next(c for c in result["components"] if c["instance_id"] == iid_b)
        T = free_comp["transform"]
        # The free normal (0,0,1) in local frame should now align with (1,0,0)
        world_n = _transform_vector(T, (0, 0, 1))
        # dot product with (1,0,0) should be ~1 or ~-1 (parallel)
        dot = abs(world_n[0] * 1 + world_n[1] * 0 + world_n[2] * 0)
        assert dot > 0.999, f"normals not parallel, dot={dot}"


# ---------------------------------------------------------------------------
# 9. Perpendicular mate
# ---------------------------------------------------------------------------

class TestPerpendicularMate:
    def test_perpendicular_reduces_dof_1(self):
        asm = Assembly()
        iid_a, iid_b = "gpe", "fpe"
        asm.add_component(Component(part_ref="bracket", instance_id=iid_a))
        asm.add_component(Component(part_ref="arm", instance_id=iid_b))
        mate = Mate(
            MateType.PERPENDICULAR, iid_a, iid_b,
            normal_a=(0, 0, 1),
            normal_b=(0, 0, 1),
        )
        result = solve_assembly(asm, [mate])
        assert result["dof_remaining"] == 5   # 6 - 1

    def test_perpendicular_result(self):
        asm = Assembly()
        iid_a, iid_b = "gpp", "fpp"
        asm.add_component(Component(part_ref="a", instance_id=iid_a))
        asm.add_component(Component(part_ref="b", instance_id=iid_b))
        mate = Mate(
            MateType.PERPENDICULAR, iid_a, iid_b,
            normal_a=(1, 0, 0),
            normal_b=(1, 0, 0),  # starts parallel; will be rotated to perp
        )
        result = solve_assembly(asm, [mate])
        free_comp = next(c for c in result["components"] if c["instance_id"] == iid_b)
        T = free_comp["transform"]
        world_n = _transform_vector(T, (1, 0, 0))
        # Must be perpendicular to (1,0,0): dot ~ 0
        dot = abs(world_n[0])
        assert dot < 1e-6, f"should be perpendicular, dot={dot}"


# ---------------------------------------------------------------------------
# 10. Angle mate
# ---------------------------------------------------------------------------

class TestAngleMate:
    def test_angle_mate_45_deg(self):
        asm = Assembly()
        iid_a, iid_b = "gang", "fang"
        asm.add_component(Component(part_ref="base-plate", instance_id=iid_a))
        asm.add_component(Component(part_ref="hinge-arm", instance_id=iid_b))
        mate = Mate(
            MateType.ANGLE, iid_a, iid_b,
            normal_a=(0, 0, 1),
            normal_b=(0, 0, 1),
            angle_deg=45.0,
        )
        result = solve_assembly(asm, [mate])
        assert result["dof_remaining"] == 5   # 6 - 1

        free_comp = next(c for c in result["components"] if c["instance_id"] == iid_b)
        T = free_comp["transform"]
        world_n = _transform_vector(T, (0, 0, 1))
        # angle between world_n and (0,0,1) should be ~45 deg
        dot = world_n[0] * 0 + world_n[1] * 0 + world_n[2] * 1
        dot = max(-1.0, min(1.0, dot))
        angle_result = math.degrees(math.acos(dot))
        assert abs(angle_result - 45.0) < 0.1, f"angle={angle_result}"

    def test_angle_mate_reduces_dof_1(self):
        asm = Assembly()
        asm.add_component(Component(part_ref="a"))
        asm.add_component(Component(part_ref="b"))
        c_b = asm.components[1]
        mate = Mate(
            MateType.ANGLE, asm.components[0].instance_id, c_b.instance_id,
            normal_a=(0, 0, 1), normal_b=(0, 0, 1), angle_deg=90.0,
        )
        result = solve_assembly(asm, [mate])
        assert result["dof_remaining"] == 5


# ---------------------------------------------------------------------------
# 11. Over-constrained detection
# ---------------------------------------------------------------------------

class TestOverConstrained:
    def test_over_constrained_flagged(self):
        """Applying a lock to the ground component should be over-constrained."""
        asm = Assembly()
        iid_a = "ground-oc"
        asm.add_component(Component(part_ref="fixed-part", instance_id=iid_a))
        asm.add_component(Component(part_ref="floating", instance_id="free-oc"))
        # First fully constrain
        lock = Mate(MateType.LOCK, iid_a, "free-oc")
        result = solve_assembly(asm, [lock])
        assert result["status"] == "fully_constrained"
        # Now add an additional coincident — over-constrains the free part
        coincident = Mate(
            MateType.COINCIDENT, iid_a, "free-oc",
            point_a=(0, 0, 0), normal_a=(0, 0, 1),
            point_b=(0, 0, 0), normal_b=(0, 0, -1),
        )
        result2 = solve_assembly(asm, [lock, coincident])
        assert result2["status"] == "over_constrained"
        assert len(result2["errors"]) > 0

    def test_over_constrained_errors_not_empty(self):
        asm = Assembly()
        asm.add_component(Component(part_ref="g"))
        asm.add_component(Component(part_ref="f", instance_id="foc"))
        # Lock removes all 6 DOF
        m1 = Mate(MateType.LOCK, asm.components[0].instance_id, "foc")
        # Second lock tries to remove more DOF
        m2 = Mate(MateType.LOCK, asm.components[0].instance_id, "foc")
        result = solve_assembly(asm, [m1, m2])
        assert result["status"] == "over_constrained"
        assert any("Over-constrained" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# 12. Under-constrained DOF count
# ---------------------------------------------------------------------------

class TestUnderConstrained:
    def test_three_components_unconstrained(self):
        asm = Assembly()
        for i in range(3):
            asm.add_component(Component(part_ref=f"part-{i}"))
        result = solve_assembly(asm, [])
        # 2 free components × 6 DOF = 12
        assert result["dof_remaining"] == 12
        assert result["status"] == "under_constrained"

    def test_partially_constrained_dof(self):
        asm = Assembly()
        asm.add_component(Component(part_ref="base"))
        asm.add_component(Component(part_ref="widget", instance_id="w1"))
        mate = Mate(
            MateType.COINCIDENT,
            asm.components[0].instance_id, "w1",
            normal_a=(0, 0, 1), normal_b=(0, 0, -1),
        )
        result = solve_assembly(asm, [mate])
        # 6 - 3 = 3 DOF remain
        assert result["dof_remaining"] == 3
        assert result["status"] == "under_constrained"


# ---------------------------------------------------------------------------
# 13. Invalid component ref error
# ---------------------------------------------------------------------------

class TestInvalidRef:
    def test_invalid_instance_id_in_mate(self):
        asm = Assembly()
        asm.add_component(Component(part_ref="base"))
        mate = Mate(MateType.LOCK, asm.components[0].instance_id, "nonexistent-id")
        result = solve_assembly(asm, [mate])
        assert result["ok"] is False
        assert any("nonexistent-id" in e for e in result["errors"])

    def test_invalid_instance_id_a(self):
        asm = Assembly()
        asm.add_component(Component(part_ref="base"))
        mate = Mate(MateType.COINCIDENT, "bad-id", asm.components[0].instance_id)
        result = solve_assembly(asm, [mate])
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# 14. BOM: quantity roll-up
# ---------------------------------------------------------------------------

class TestBOM:
    def test_flat_bom_qty_rollup(self):
        asm = Assembly(name="bolt-kit")
        for i in range(4):
            asm.add_component(Component(part_ref="M8-bolt", name=f"bolt-{i}"))
        asm.add_component(Component(part_ref="washer"))
        flat = _build_flat_bom(asm)
        bolt_row = next(r for r in flat if r["part_ref"] == "M8-bolt")
        washer_row = next(r for r in flat if r["part_ref"] == "washer")
        assert bolt_row["qty"] == 4
        assert len(bolt_row["instances"]) == 4
        assert washer_row["qty"] == 1

    def test_flat_bom_single_part(self):
        asm = Assembly()
        asm.add_component(Component(part_ref="frame"))
        flat = _build_flat_bom(asm)
        assert len(flat) == 1
        assert flat[0]["qty"] == 1

    def test_tree_bom_nesting(self):
        asm = Assembly(name="root")
        asm.add_component(Component(part_ref="part-A"))
        sub = Assembly(name="sub")
        sub.add_component(Component(part_ref="sub-part-X"))
        asm.add_sub_assembly(sub)
        tree = _build_tree_bom(asm, level=0)
        # Root has 1 direct component + 1 sub-assembly entry
        assert len(tree) == 2
        sub_entry = next(t for t in tree if t["name"] == "sub")
        assert len(sub_entry["sub_items"]) == 1
        assert sub_entry["sub_items"][0]["part_ref"] == "sub-part-X"

    def test_bom_empty_assembly(self):
        asm = Assembly()
        flat = _build_flat_bom(asm)
        assert flat == []


# ---------------------------------------------------------------------------
# 15. LLM tool wrappers
# ---------------------------------------------------------------------------

class TestToolCreate:
    def test_create_returns_assembly_id(self):
        resp = _tool_call(run_assembly_create, {"name": "test-asm"})
        assert resp["ok"] is True
        assert "assembly_id" in resp["payload"]
        assert resp["payload"]["assembly"]["name"] == "test-asm"

    def test_create_default_name(self):
        resp = _tool_call(run_assembly_create, {})
        assert resp["ok"] is True
        assert resp["payload"]["assembly"]["name"] == "assembly"


class TestToolAddComponent:
    def test_add_component(self):
        create = _tool_call(run_assembly_create, {"name": "asm"})
        asm = create["payload"]["assembly"]
        resp = _tool_call(run_assembly_add_component, {
            "assembly": asm,
            "part_ref": "gear-32t",
        })
        assert resp["ok"] is True
        assert resp["payload"]["part_ref"] == "gear-32t"
        iid = resp["payload"]["instance_id"]
        # The returned assembly should contain this component
        updated_asm = resp["payload"]["assembly"]
        assert any(c["instance_id"] == iid for c in updated_asm["components"])

    def test_add_component_missing_part_ref(self):
        create = _tool_call(run_assembly_create, {})
        asm = create["payload"]["assembly"]
        resp = _tool_call(run_assembly_add_component, {"assembly": asm})
        assert resp["ok"] is False
        assert resp["code"] == "BAD_ARGS"

    def test_add_component_missing_assembly(self):
        resp = _tool_call(run_assembly_add_component, {"part_ref": "x"})
        assert resp["ok"] is False

    def test_add_component_with_explicit_instance_id(self):
        create = _tool_call(run_assembly_create, {})
        asm = create["payload"]["assembly"]
        iid = str(uuid.uuid4())
        resp = _tool_call(run_assembly_add_component, {
            "assembly": asm,
            "part_ref": "pin",
            "instance_id": iid,
        })
        assert resp["ok"] is True
        assert resp["payload"]["instance_id"] == iid


class TestToolAddMate:
    def _two_component_asm(self):
        c1 = _tool_call(run_assembly_create, {"name": "asm"})
        asm = c1["payload"]["assembly"]
        c2 = _tool_call(run_assembly_add_component, {
            "assembly": asm, "part_ref": "a", "instance_id": "iid-a",
        })
        asm = c2["payload"]["assembly"]
        c3 = _tool_call(run_assembly_add_component, {
            "assembly": asm, "part_ref": "b", "instance_id": "iid-b",
        })
        return c3["payload"]["assembly"]

    def test_add_mate_concentric(self):
        asm = self._two_component_asm()
        resp = _tool_call(run_assembly_add_mate, {
            "mates": [],
            "mate_type": "concentric",
            "instance_id_a": "iid-a",
            "instance_id_b": "iid-b",
            "point_a": [0, 0, 0],
            "normal_a": [0, 0, 1],
            "point_b": [0, 0, 0],
            "normal_b": [0, 0, 1],
        })
        assert resp["ok"] is True
        assert len(resp["payload"]["mates"]) == 1

    def test_add_mate_invalid_type(self):
        resp = _tool_call(run_assembly_add_mate, {
            "mates": [],
            "mate_type": "weld",
            "instance_id_a": "a",
            "instance_id_b": "b",
        })
        assert resp["ok"] is False
        assert resp["code"] == "BAD_ARGS"

    def test_add_mate_missing_mates_field(self):
        resp = _tool_call(run_assembly_add_mate, {
            "mate_type": "lock",
            "instance_id_a": "a",
            "instance_id_b": "b",
        })
        assert resp["ok"] is False


class TestToolSolve:
    def test_solve_two_components_concentric(self):
        c1 = _tool_call(run_assembly_create, {"name": "s"})
        asm = c1["payload"]["assembly"]
        for ref, iid in [("shaft", "s1"), ("sleeve", "s2")]:
            r = _tool_call(run_assembly_add_component, {
                "assembly": asm, "part_ref": ref, "instance_id": iid,
            })
            asm = r["payload"]["assembly"]
        r = _tool_call(run_assembly_add_mate, {
            "mates": [],
            "mate_type": "concentric",
            "instance_id_a": "s1",
            "instance_id_b": "s2",
            "point_a": [0, 0, 0], "normal_a": [0, 0, 1],
            "point_b": [5, 5, 0], "normal_b": [0, 0, 1],
        })
        mates = r["payload"]["mates"]
        solve = _tool_call(run_assembly_solve, {"assembly": asm, "mates": mates})
        assert solve["ok"] is True
        result = solve["payload"]
        assert result["dof_remaining"] == 2
        assert result["status"] == "under_constrained"

    def test_solve_missing_assembly(self):
        resp = _tool_call(run_assembly_solve, {"mates": []})
        assert resp["ok"] is False

    def test_solve_invalid_mate_in_list(self):
        c1 = _tool_call(run_assembly_create, {})
        asm = c1["payload"]["assembly"]
        r = _tool_call(run_assembly_add_component, {
            "assembly": asm, "part_ref": "p",
        })
        asm = r["payload"]["assembly"]
        # Pass a malformed mate in the list
        resp = _tool_call(run_assembly_solve, {
            "assembly": asm,
            "mates": [{"not_a_mate": True}],
        })
        # Should not crash; errors are collected
        assert "errors" in resp["payload"]


class TestToolBOM:
    def test_bom_qty_rollup_via_tool(self):
        c1 = _tool_call(run_assembly_create, {"name": "bom-test"})
        asm = c1["payload"]["assembly"]
        for _ in range(3):
            r = _tool_call(run_assembly_add_component, {
                "assembly": asm, "part_ref": "bolt-M6",
            })
            asm = r["payload"]["assembly"]
        resp = _tool_call(run_assembly_bom, {"assembly": asm})
        assert resp["ok"] is True
        flat = resp["payload"]["flat"]
        assert len(flat) == 1
        assert flat[0]["qty"] == 3
        assert resp["payload"]["total_components"] == 3
        assert resp["payload"]["unique_parts"] == 1

    def test_bom_multiple_parts(self):
        c1 = _tool_call(run_assembly_create, {})
        asm = c1["payload"]["assembly"]
        for ref in ["nut", "bolt", "washer", "bolt"]:
            r = _tool_call(run_assembly_add_component, {
                "assembly": asm, "part_ref": ref,
            })
            asm = r["payload"]["assembly"]
        resp = _tool_call(run_assembly_bom, {"assembly": asm})
        flat = resp["payload"]["flat"]
        by_ref = {r["part_ref"]: r["qty"] for r in flat}
        assert by_ref["bolt"] == 2
        assert by_ref["nut"] == 1
        assert resp["payload"]["unique_parts"] == 3

    def test_bom_missing_assembly(self):
        resp = _tool_call(run_assembly_bom, {})
        assert resp["ok"] is False


# ---------------------------------------------------------------------------
# 16. Lock mate: fully constrains
# ---------------------------------------------------------------------------

class TestLockMate:
    def test_lock_fully_constrains(self):
        asm = Assembly()
        asm.add_component(Component(part_ref="base"))
        asm.add_component(Component(part_ref="fixed-to-base", instance_id="flocked"))
        mate = Mate(MateType.LOCK, asm.components[0].instance_id, "flocked")
        result = solve_assembly(asm, [mate])
        assert result["status"] == "fully_constrained"
        assert result["dof_remaining"] == 0

    def test_lock_copies_transform(self):
        """Lock should set free component's transform to match the fixed component's."""
        T = [
            2.0, 0.0, 0.0, 10.0,
            0.0, 2.0, 0.0, 20.0,
            0.0, 0.0, 2.0, 30.0,
            0.0, 0.0, 0.0, 1.0,
        ]
        asm = Assembly()
        asm.add_component(Component(part_ref="base", transform=T))
        asm.add_component(Component(part_ref="rider", instance_id="rider"))
        mate = Mate(MateType.LOCK, asm.components[0].instance_id, "rider")
        result = solve_assembly(asm, [mate])
        rider_result = next(c for c in result["components"] if c["instance_id"] == "rider")
        # Lock snaps free to fixed
        for a_val, b_val in zip(rider_result["transform"], T):
            assert _approx(a_val, b_val), f"{a_val} != {b_val}"


# ---------------------------------------------------------------------------
# 17. Tangent mate
# ---------------------------------------------------------------------------

class TestTangentMate:
    def test_tangent_reduces_dof_1(self):
        asm = Assembly()
        asm.add_component(Component(part_ref="flat-plate"))
        asm.add_component(Component(part_ref="cylinder", instance_id="cyl"))
        mate = Mate(
            MateType.TANGENT,
            asm.components[0].instance_id, "cyl",
            point_a=(0, 0, 0), normal_a=(0, 0, 1),
            point_b=(0, 0, 0),
            offset=5.0,   # cylinder radius
        )
        result = solve_assembly(asm, [mate])
        assert result["dof_remaining"] == 5   # 6 - 1


# ---------------------------------------------------------------------------
# 18. Distance mate
# ---------------------------------------------------------------------------

class TestDistanceMate:
    def test_distance_result(self):
        """After a distance mate the free point should be at offset from fixed plane."""
        asm = Assembly()
        asm.add_component(Component(part_ref="bottom"))
        asm.add_component(Component(part_ref="top", instance_id="topcomp"))
        offset = 20.0
        mate = Mate(
            MateType.DISTANCE,
            asm.components[0].instance_id, "topcomp",
            point_a=(0, 0, 0), normal_a=(0, 0, 1),
            point_b=(0, 0, 0),
            offset=offset,
        )
        result = solve_assembly(asm, [mate])
        top_result = next(c for c in result["components"] if c["instance_id"] == "topcomp")
        T = top_result["transform"]
        world_pt = _transform_point(T, (0, 0, 0))
        assert _approx(world_pt[2], offset, tol=1e-5), (
            f"expected Z={offset}, got Z={world_pt[2]}"
        )

    def test_distance_reduces_dof_1(self):
        asm = Assembly()
        asm.add_component(Component(part_ref="a"))
        asm.add_component(Component(part_ref="b"))
        mate = Mate(
            MateType.DISTANCE,
            asm.components[0].instance_id,
            asm.components[1].instance_id,
            normal_a=(0, 0, 1), offset=10.0,
        )
        result = solve_assembly(asm, [mate])
        assert result["dof_remaining"] == 5


# ---------------------------------------------------------------------------
# 19. Validate transform
# ---------------------------------------------------------------------------

class TestValidateTransform:
    def test_wrong_length_raises(self):
        with pytest.raises(ValueError):
            _validate_transform([1, 2, 3])

    def test_none_returns_identity(self):
        assert _validate_transform(None) == _identity()

    def test_valid_passthrough(self):
        t = _identity()
        assert _validate_transform(t) == t
