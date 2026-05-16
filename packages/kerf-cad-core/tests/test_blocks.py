"""
Tests for kerf_cad_core.geom.blocks — Block definitions + instance references.

All tests are hermetic: no OCC, no database, no network.  Pure-Python only.

Coverage (≥30 tests across 9 groups):
  1.  BlockDefinition — construction, validity, defaults, metadata.
  2.  BlockInstance — construction, defaults, transform_matrix property.
  3.  BlockLibrary CRUD — add/get/remove/definition_names/unique_block_count.
  4.  Cycle detection — has_cycle, cycle_members, self-reference, chain, DAG.
  5.  world_transform_of — identity, translation, scale, compose.
  6.  instantiate — flat block, nested block, instance count, transform composition.
  7.  Cycle in nested blocks — cycle detected & skipped, not infinite-looped.
  8.  bom_from_instances — rollup, unknown blocks counted, empty list.
  9.  Override attributes — propagation through instantiate, child wins.
 10.  Matrix helpers — _mat4_mul identity, _mat4_translation, _mat4_scale.
"""

from __future__ import annotations

import math

import pytest

from kerf_cad_core.geom.blocks import (
    BlockDefinition,
    BlockInstance,
    BlockLibrary,
    _mat4_identity,
    _mat4_mul,
    _mat4_scale,
    _mat4_translation,
    _mat4_from_transform,
    bom_from_instances,
    instantiate,
    instance_count,
    unique_block_count,
    world_transform_of,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _approx_equal(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) < tol


def _mat_approx(m1, m2, tol: float = 1e-9) -> bool:
    for i in range(4):
        for j in range(4):
            if not _approx_equal(m1[i][j], m2[i][j], tol):
                return False
    return True


def _make_lib_with_bolt() -> BlockLibrary:
    lib = BlockLibrary()
    lib.add(BlockDefinition(name="bolt", parts=["shank", "head"]))
    return lib


def _make_nested_lib() -> BlockLibrary:
    """wheel -> [spoke, hub]; hub -> [axle]; axle is a leaf."""
    lib = BlockLibrary()
    lib.add(BlockDefinition(name="axle", parts=["axle_geom"]))
    lib.add(BlockDefinition(name="hub", parts=["hub_geom", "axle"]))
    lib.add(BlockDefinition(name="wheel", parts=["spoke", "hub"]))
    return lib


# ===========================================================================
# 1. BlockDefinition
# ===========================================================================

def test_block_definition_basic():
    d = BlockDefinition(name="widget", parts=["body", "cap"])
    assert d.name == "widget"
    assert d.parts == ["body", "cap"]
    assert d.base_point == (0.0, 0.0, 0.0)
    assert d.metadata == {}


def test_block_definition_valid():
    assert BlockDefinition(name="x", parts=[]).is_valid()


def test_block_definition_empty_name_invalid():
    assert not BlockDefinition(name="", parts=[]).is_valid()
    assert not BlockDefinition(name="   ", parts=[]).is_valid()


def test_block_definition_metadata():
    d = BlockDefinition(name="gear", parts=[], metadata={"layer": "MECH", "colour": "red"})
    assert d.metadata["layer"] == "MECH"
    assert d.metadata["colour"] == "red"


def test_block_definition_custom_base_point():
    d = BlockDefinition(name="flange", parts=[], base_point=(1.0, 2.0, 3.0))
    assert d.base_point == (1.0, 2.0, 3.0)


# ===========================================================================
# 2. BlockInstance
# ===========================================================================

def test_block_instance_defaults():
    inst = BlockInstance(block_name="bolt")
    assert inst.translate == (0.0, 0.0, 0.0)
    assert inst.rotate == (0.0, 0.0, 0.0)
    assert inst.scale == (1.0, 1.0, 1.0)
    assert inst.attributes == {}


def test_block_instance_transform_matrix_identity():
    inst = BlockInstance(block_name="x")
    m = inst.transform_matrix
    assert _mat_approx(m, _mat4_identity())


def test_block_instance_transform_matrix_translation():
    inst = BlockInstance(block_name="x", translate=(5.0, 3.0, -1.0))
    m = inst.transform_matrix
    assert _approx_equal(m[0][3], 5.0)
    assert _approx_equal(m[1][3], 3.0)
    assert _approx_equal(m[2][3], -1.0)


def test_block_instance_scale_in_matrix():
    inst = BlockInstance(block_name="x", scale=(2.0, 3.0, 4.0))
    m = inst.transform_matrix
    assert _approx_equal(m[0][0], 2.0)
    assert _approx_equal(m[1][1], 3.0)
    assert _approx_equal(m[2][2], 4.0)


# ===========================================================================
# 3. BlockLibrary CRUD
# ===========================================================================

def test_library_add_get():
    lib = _make_lib_with_bolt()
    d = lib.get("bolt")
    assert d is not None
    assert d.name == "bolt"
    assert "shank" in d.parts


def test_library_get_missing_returns_none():
    lib = BlockLibrary()
    assert lib.get("nonexistent") is None


def test_library_remove_existing():
    lib = _make_lib_with_bolt()
    removed = lib.remove("bolt")
    assert removed is True
    assert lib.get("bolt") is None


def test_library_remove_missing_returns_false():
    lib = BlockLibrary()
    assert lib.remove("ghost") is False


def test_library_definition_names_sorted():
    lib = BlockLibrary()
    lib.add(BlockDefinition(name="zebra", parts=[]))
    lib.add(BlockDefinition(name="alpha", parts=[]))
    lib.add(BlockDefinition(name="mango", parts=[]))
    names = lib.definition_names()
    assert names == ["alpha", "mango", "zebra"]


def test_unique_block_count_empty():
    assert unique_block_count(BlockLibrary()) == 0


def test_unique_block_count():
    lib = _make_nested_lib()
    assert unique_block_count(lib) == 3


def test_library_add_non_definition_is_ignored():
    lib = BlockLibrary()
    lib.add("not a definition")  # type: ignore[arg-type]
    assert unique_block_count(lib) == 0


# ===========================================================================
# 4. Cycle detection
# ===========================================================================

def test_no_cycle_in_dag():
    lib = _make_nested_lib()
    assert not lib.has_cycle()
    assert lib.cycle_members() == []


def test_self_reference_cycle():
    lib = BlockLibrary()
    lib.add(BlockDefinition(name="self_ref", parts=["self_ref"]))
    assert lib.has_cycle()
    assert "self_ref" in lib.cycle_members()


def test_two_node_cycle():
    lib = BlockLibrary()
    lib.add(BlockDefinition(name="a", parts=["b"]))
    lib.add(BlockDefinition(name="b", parts=["a"]))
    assert lib.has_cycle()
    members = lib.cycle_members()
    assert "a" in members
    assert "b" in members


def test_three_node_cycle():
    lib = BlockLibrary()
    lib.add(BlockDefinition(name="x", parts=["y"]))
    lib.add(BlockDefinition(name="y", parts=["z"]))
    lib.add(BlockDefinition(name="z", parts=["x"]))
    assert lib.has_cycle()
    members = lib.cycle_members()
    assert set(members) == {"x", "y", "z"}


def test_mixed_dag_and_cycle():
    """Only the cyclic sub-graph is reported."""
    lib = BlockLibrary()
    lib.add(BlockDefinition(name="root", parts=["a", "safe"]))
    lib.add(BlockDefinition(name="a", parts=["b"]))
    lib.add(BlockDefinition(name="b", parts=["a"]))
    lib.add(BlockDefinition(name="safe", parts=["leaf"]))
    members = lib.cycle_members()
    assert "a" in members
    assert "b" in members
    assert "safe" not in members


# ===========================================================================
# 5. world_transform_of
# ===========================================================================

def test_world_transform_identity():
    inst = BlockInstance(block_name="x")
    assert _mat_approx(world_transform_of(inst), _mat4_identity())


def test_world_transform_translation_only():
    inst = BlockInstance(block_name="x", translate=(10.0, 0.0, 0.0))
    m = world_transform_of(inst)
    assert _approx_equal(m[0][3], 10.0)


def test_world_transform_rotation_z_90():
    angle = math.pi / 2
    inst = BlockInstance(block_name="x", rotate=(0.0, 0.0, angle))
    m = world_transform_of(inst)
    # cos(90°) ≈ 0, sin(90°) ≈ 1
    assert _approx_equal(m[0][0], 0.0, tol=1e-9)
    assert _approx_equal(m[0][1], -1.0, tol=1e-9)
    assert _approx_equal(m[1][0], 1.0, tol=1e-9)


# ===========================================================================
# 6. instantiate — expansion + transform composition
# ===========================================================================

def test_instantiate_flat_block_leaf_count():
    """bolt (shank + head) → 2 leaves."""
    lib = _make_lib_with_bolt()
    inst = BlockInstance(block_name="bolt")
    leaves = instantiate(lib, inst)
    assert len(leaves) == 2


def test_instantiate_nested_block_count():
    """wheel → spoke + hub(hub_geom + axle(axle_geom)) = 3 leaf nodes."""
    lib = _make_nested_lib()
    inst = BlockInstance(block_name="wheel")
    leaves = instantiate(lib, inst)
    leaf_names = [l.block_name for l in leaves]
    # spoke, hub_geom, axle_geom
    assert len(leaves) == 3
    assert "spoke" in leaf_names
    assert "hub_geom" in leaf_names
    assert "axle_geom" in leaf_names


def test_instantiate_identity_transform_passthrough():
    """Identity instance → leaves have identity matrix."""
    lib = _make_lib_with_bolt()
    inst = BlockInstance(block_name="bolt")
    leaves = instantiate(lib, inst)
    for leaf in leaves:
        m = leaf.attributes["_matrix"]
        assert _mat_approx(m, _mat4_identity())


def test_instantiate_composed_translation():
    """Parent translate (5,0,0) → leaf matrices have tx=5."""
    lib = _make_lib_with_bolt()
    inst = BlockInstance(block_name="bolt", translate=(5.0, 0.0, 0.0))
    leaves = instantiate(lib, inst)
    for leaf in leaves:
        m = leaf.attributes["_matrix"]
        assert _approx_equal(m[0][3], 5.0)


def test_instantiate_composed_scale():
    """Parent scale (2,2,2) → leaf matrices diagonal = 2."""
    lib = _make_lib_with_bolt()
    inst = BlockInstance(block_name="bolt", scale=(2.0, 2.0, 2.0))
    leaves = instantiate(lib, inst)
    for leaf in leaves:
        m = leaf.attributes["_matrix"]
        assert _approx_equal(m[0][0], 2.0)
        assert _approx_equal(m[1][1], 2.0)
        assert _approx_equal(m[2][2], 2.0)


def test_instantiate_composed_transform_equals_mat_product():
    """T(3,0,0) @ T(0,4,0) should give tx=3, ty=4 in leaf matrix."""
    lib = BlockLibrary()
    lib.add(BlockDefinition(name="inner", parts=["geom"]))
    lib.add(BlockDefinition(name="outer", parts=["inner"]))
    # Place inner at (0,4,0) by adding as a sub-instance via instantiate directly
    inner_inst = BlockInstance(block_name="inner", translate=(0.0, 4.0, 0.0))
    outer_inst = BlockInstance(block_name="outer", translate=(3.0, 0.0, 0.0))

    # Manually compute expected composed matrix
    parent_mat = _mat4_translation(3.0, 0.0, 0.0)
    child_mat = _mat4_translation(0.0, 4.0, 0.0)
    expected = _mat4_mul(parent_mat, child_mat)

    # The outer block contains "inner" as a sub-block name, but without a
    # custom transform for the nested level.  Verify by calling instantiate
    # on inner_inst under parent matrix directly.
    leaves = instantiate(lib, inner_inst, _parent_matrix=parent_mat)
    assert len(leaves) == 1
    m = leaves[0].attributes["_matrix"]
    assert _approx_equal(m[0][3], 3.0)
    assert _approx_equal(m[1][3], 4.0)


def test_instantiate_unknown_block_returns_leaf():
    """Instantiating a block not in the library returns it as a single leaf."""
    lib = BlockLibrary()
    inst = BlockInstance(block_name="mystery")
    leaves = instantiate(lib, inst)
    assert len(leaves) == 1
    assert leaves[0].block_name == "mystery"


def test_instance_count_flat():
    lib = _make_lib_with_bolt()
    assert instance_count(lib, "bolt") == 2


def test_instance_count_nested():
    lib = _make_nested_lib()
    # wheel: spoke(1) + hub(hub_geom(1) + axle(axle_geom(1))) = 3
    assert instance_count(lib, "wheel") == 3


def test_instance_count_unknown_block():
    assert instance_count(BlockLibrary(), "ghost") == 0


# ===========================================================================
# 7. Cycle in nested blocks — not infinite-looped
# ===========================================================================

def test_instantiate_cycle_no_infinite_loop():
    """Cyclic blocks are skipped cleanly; the function terminates."""
    lib = BlockLibrary()
    lib.add(BlockDefinition(name="a", parts=["b", "leaf_a"]))
    lib.add(BlockDefinition(name="b", parts=["a", "leaf_b"]))
    inst = BlockInstance(block_name="a")
    # Must return without hanging; cycle back-edge produces no extra leaves.
    leaves = instantiate(lib, inst)
    # leaf_a and leaf_b are emitted on first expansion; cycle stopped.
    assert all(l.block_name in ("leaf_a", "leaf_b") for l in leaves)
    assert len(leaves) >= 1  # at minimum leaf_a emitted on first pass


def test_instance_count_cycle_no_infinite_loop():
    lib = BlockLibrary()
    lib.add(BlockDefinition(name="a", parts=["b"]))
    lib.add(BlockDefinition(name="b", parts=["a"]))
    # Should terminate and return a finite number
    count = instance_count(lib, "a")
    assert isinstance(count, int)


def test_self_reference_no_infinite_loop():
    lib = BlockLibrary()
    lib.add(BlockDefinition(name="self_ref", parts=["self_ref", "leaf"]))
    leaves = instantiate(lib, BlockInstance(block_name="self_ref"))
    # "leaf" is a non-block part and should be emitted; self_ref back-edge skipped
    leaf_names = [l.block_name for l in leaves]
    assert "leaf" in leaf_names


# ===========================================================================
# 8. bom_from_instances
# ===========================================================================

def test_bom_empty():
    lib = BlockLibrary()
    assert bom_from_instances(lib, []) == {}


def test_bom_single():
    lib = _make_lib_with_bolt()
    instances = [BlockInstance(block_name="bolt")]
    bom = bom_from_instances(lib, instances)
    assert bom == {"bolt": 1}


def test_bom_multiple_same_block():
    lib = _make_lib_with_bolt()
    instances = [
        BlockInstance(block_name="bolt"),
        BlockInstance(block_name="bolt"),
        BlockInstance(block_name="bolt"),
    ]
    bom = bom_from_instances(lib, instances)
    assert bom["bolt"] == 3


def test_bom_mixed_blocks():
    lib = _make_nested_lib()
    instances = [
        BlockInstance(block_name="wheel"),
        BlockInstance(block_name="wheel"),
        BlockInstance(block_name="axle"),
    ]
    bom = bom_from_instances(lib, instances)
    assert bom["wheel"] == 2
    assert bom["axle"] == 1


def test_bom_unknown_block_still_counted():
    lib = BlockLibrary()
    instances = [BlockInstance(block_name="exotic_part")]
    bom = bom_from_instances(lib, instances)
    assert bom["exotic_part"] == 1


# ===========================================================================
# 9. Override attributes — propagation
# ===========================================================================

def test_override_attributes_propagate_to_leaves():
    lib = _make_lib_with_bolt()
    inst = BlockInstance(block_name="bolt", attributes={"colour": "gold"})
    leaves = instantiate(lib, inst)
    for leaf in leaves:
        assert leaf.attributes.get("colour") == "gold"


def test_override_attributes_child_wins():
    """Definition metadata is overridden by instance attributes."""
    lib = BlockLibrary()
    lib.add(BlockDefinition(name="bolt", parts=["shank"], metadata={"colour": "silver"}))
    inst = BlockInstance(block_name="bolt", attributes={"colour": "gold"})
    leaves = instantiate(lib, inst)
    for leaf in leaves:
        # Instance attribute wins over definition metadata
        assert leaf.attributes.get("colour") == "gold"


def test_override_attributes_no_override_uses_def_metadata():
    lib = BlockLibrary()
    lib.add(BlockDefinition(name="bolt", parts=["shank"], metadata={"layer": "MECH"}))
    inst = BlockInstance(block_name="bolt")
    leaves = instantiate(lib, inst)
    for leaf in leaves:
        assert leaf.attributes.get("layer") == "MECH"


# ===========================================================================
# 10. Matrix helpers
# ===========================================================================

def test_mat4_identity():
    m = _mat4_identity()
    for i in range(4):
        for j in range(4):
            expected = 1.0 if i == j else 0.0
            assert _approx_equal(m[i][j], expected)


def test_mat4_mul_identity():
    m = _mat4_translation(3.0, 4.0, 5.0)
    result = _mat4_mul(m, _mat4_identity())
    assert _mat_approx(result, m)


def test_mat4_translation_values():
    m = _mat4_translation(1.0, 2.0, 3.0)
    assert _approx_equal(m[0][3], 1.0)
    assert _approx_equal(m[1][3], 2.0)
    assert _approx_equal(m[2][3], 3.0)
    assert _approx_equal(m[3][3], 1.0)


def test_mat4_scale_values():
    m = _mat4_scale(2.0, 3.0, 4.0)
    assert _approx_equal(m[0][0], 2.0)
    assert _approx_equal(m[1][1], 3.0)
    assert _approx_equal(m[2][2], 4.0)
    assert _approx_equal(m[3][3], 1.0)


def test_mat4_mul_translation_composition():
    """T(1,0,0) @ T(0,2,0) should translate by (1,2,0)."""
    t1 = _mat4_translation(1.0, 0.0, 0.0)
    t2 = _mat4_translation(0.0, 2.0, 0.0)
    result = _mat4_mul(t1, t2)
    assert _approx_equal(result[0][3], 1.0)
    assert _approx_equal(result[1][3], 2.0)
    assert _approx_equal(result[2][3], 0.0)


def test_mat4_from_transform_identity():
    m = _mat4_from_transform()
    assert _mat_approx(m, _mat4_identity())
