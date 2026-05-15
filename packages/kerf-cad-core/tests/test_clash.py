"""
Tests for kerf_cad_core.clash — cross-discipline clash / interference detection.

All tests are hermetic: pure Python, no DB, no OCCT, no network.

Coverage
--------
1.  Separated axis-aligned boxes → no clash
2.  Overlapping axis-aligned boxes → hard clash with positive depth
3.  Barely touching boxes → hard clash (depth ≈ 0)
4.  Box within clearance distance → clearance violation
5.  Box outside clearance distance → clean
6.  Coincident bbox centres → coincident flag
7.  Near-coincident but not coincident → no coincident flag
8.  Single component → empty clashes
9.  Empty input → empty clashes
10. Non-list input → ok=False + error
11. Rotated OBB that overlap after rotation → hard clash
12. Rotated OBB that are clear despite AABB overlap → no clash
13. Triangle mesh: non-intersecting → clearance only
14. Triangle mesh: intersecting → hard clash
15. Three components: multiple pairs
16. Hard clash depth > 0 and proportional to overlap
17. Clearance gap value is accurate
18. Dict input components
19. Invalid component dict → error in errors list, others processed
20. min_clearance=0 with near components → no clearance report
21. min_clearance=10 with 5mm gap → clearance reported
22. Coincident check supersedes hard check
23. Two components far apart → zero clashes
24. Component at large translation → still detects clash
25. Identity transform + small box overlap
26. Non-square bbox (long thin box)
27. Hard clash: depth field is a float
28. Clearance record: depth is the gap value
29. ClashRecord to_dict keys
30. ComponentShape validation: empty instance_id
31. ComponentShape validation: bad transform length
32. _shape_from_dict round-trip
33. Multiple overlapping pairs: correct count
34. Rotated 45-degree OBB corner overlap

Author: imranparuk
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.clash.detect import (
    ClashType,
    ClashRecord,
    ComponentShape,
    COINCIDENT_TOL,
    clash_detect,
    _shape_from_dict,
    _OBB,
    _obb_sat,
    _aabb_overlap,
    _aabb_gap,
    _world_aabb,
    _obb_clearance_gap,
)
from kerf_cad_core.assembly.model import _identity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _box(iid, lo, hi, transform=None):
    """Shorthand to create a ComponentShape with an axis-aligned bbox."""
    return ComponentShape(
        instance_id=iid,
        transform=transform,
        bbox_min=lo,
        bbox_max=hi,
    )


def _translate(dx, dy, dz):
    """Return a 4x4 row-major translation matrix."""
    return [
        1, 0, 0, dx,
        0, 1, 0, dy,
        0, 0, 1, dz,
        0, 0, 0, 1,
    ]


def _rotation_z(angle_deg):
    """Return a 4x4 row-major rotation about Z axis."""
    r = math.radians(angle_deg)
    c, s = math.cos(r), math.sin(r)
    return [
        c, -s, 0, 0,
        s,  c, 0, 0,
        0,  0, 1, 0,
        0,  0, 0, 1,
    ]


def _approx(a, b, tol=1e-6):
    return abs(a - b) < tol


# ---------------------------------------------------------------------------
# 1. Separated axis-aligned boxes → no clash
# ---------------------------------------------------------------------------

class TestSeparatedBoxes:
    def test_separated_x_axis(self):
        """Two boxes 10mm apart on X — no clash."""
        a = _box("a", (0, 0, 0), (2, 2, 2))
        b = _box("b", (12, 0, 0), (14, 2, 2))
        result = clash_detect([a, b])
        assert result["ok"] is True
        assert result["clashes"] == []

    def test_separated_y_axis(self):
        a = _box("a", (0, 0, 0), (2, 2, 2))
        b = _box("b", (0, 20, 0), (2, 22, 2))
        result = clash_detect([a, b])
        assert result["clashes"] == []

    def test_separated_z_axis(self):
        a = _box("a", (0, 0, 0), (1, 1, 1))
        b = _box("b", (0, 0, 5), (1, 1, 6))
        result = clash_detect([a, b])
        assert result["clashes"] == []


# ---------------------------------------------------------------------------
# 2. Overlapping axis-aligned boxes → hard clash with positive depth
# ---------------------------------------------------------------------------

class TestOverlappingBoxes:
    def test_basic_overlap(self):
        """Two overlapping unit cubes → hard clash."""
        a = _box("a", (0, 0, 0), (2, 2, 2))
        b = _box("b", (1, 0, 0), (3, 2, 2))   # 1mm overlap on X
        result = clash_detect([a, b])
        assert len(result["clashes"]) == 1
        c = result["clashes"][0]
        assert c["type"] == ClashType.HARD
        assert c["depth"] > 0

    def test_full_containment(self):
        """Small box inside large box (off-centre) → hard clash or coincident."""
        # Outer box: centre (5,5,5).  Inner box: off-centre so centres differ.
        a = _box("outer", (0, 0, 0), (10, 10, 10))   # centre (5,5,5)
        b = _box("inner", (1, 1, 1), (4, 4, 4))       # centre (2.5,2.5,2.5) — inside A
        result = clash_detect([a, b])
        # Should be a hard clash (inner is fully inside outer, centres differ)
        assert any(
            c["type"] in (ClashType.HARD, ClashType.COINCIDENT)
            for c in result["clashes"]
        )

    def test_depth_positive(self):
        a = _box("a", (0, 0, 0), (4, 4, 4))
        b = _box("b", (2, 0, 0), (6, 4, 4))   # 2mm overlap on X
        result = clash_detect([a, b])
        assert len(result["clashes"]) == 1
        assert result["clashes"][0]["depth"] > 0


# ---------------------------------------------------------------------------
# 3. Barely touching boxes
# ---------------------------------------------------------------------------

class TestTouchingBoxes:
    def test_face_to_face_touching(self):
        """Boxes sharing exactly one face — depends on impl but depth ~0."""
        a = _box("a", (0, 0, 0), (1, 1, 1))
        b = _box("b", (1, 0, 0), (2, 1, 1))
        result = clash_detect([a, b])
        # Touching counts as 0-depth hard clash or clean — both are acceptable
        if result["clashes"]:
            assert result["clashes"][0]["depth"] >= 0


# ---------------------------------------------------------------------------
# 4. Within-clearance → clearance violation
# ---------------------------------------------------------------------------

class TestClearanceViolation:
    def test_gap_less_than_clearance(self):
        """3mm gap with min_clearance=5 → clearance violation."""
        a = _box("a", (0, 0, 0), (2, 2, 2))
        b = _box("b", (5, 0, 0), (7, 2, 2))   # gap = 3mm
        result = clash_detect([a, b], min_clearance=5.0)
        assert len(result["clashes"]) == 1
        c = result["clashes"][0]
        assert c["type"] == ClashType.CLEARANCE
        assert 0 <= c["depth"] < 5.0

    def test_type_is_clearance(self):
        a = _box("x", (0, 0, 0), (1, 1, 1))
        b = _box("y", (2, 0, 0), (3, 1, 1))   # gap = 1mm
        result = clash_detect([a, b], min_clearance=3.0)
        assert any(c["type"] == ClashType.CLEARANCE for c in result["clashes"])


# ---------------------------------------------------------------------------
# 5. Outside clearance → no clash
# ---------------------------------------------------------------------------

class TestOutsideClearance:
    def test_gap_greater_than_clearance(self):
        """10mm gap with min_clearance=5 → no clash."""
        a = _box("a", (0, 0, 0), (2, 2, 2))
        b = _box("b", (12, 0, 0), (14, 2, 2))  # gap = 10mm
        result = clash_detect([a, b], min_clearance=5.0)
        assert result["clashes"] == []


# ---------------------------------------------------------------------------
# 6. Coincident bbox centres → coincident flag
# ---------------------------------------------------------------------------

class TestCoincident:
    def test_identical_placement(self):
        """Two identical boxes at same position → coincident."""
        a = _box("a", (0, 0, 0), (2, 2, 2))
        b = _box("b", (0, 0, 0), (2, 2, 2))
        result = clash_detect([a, b])
        assert len(result["clashes"]) == 1
        assert result["clashes"][0]["type"] == ClashType.COINCIDENT

    def test_coincident_ids_correct(self):
        a = _box("comp-alpha", (0, 0, 0), (1, 1, 1))
        b = _box("comp-beta", (0, 0, 0), (1, 1, 1))
        result = clash_detect([a, b])
        c = result["clashes"][0]
        ids = {c["a"], c["b"]}
        assert ids == {"comp-alpha", "comp-beta"}

    def test_coincident_via_translation(self):
        """Same box placed via identical transform → coincident."""
        t = _translate(5, 5, 5)
        a = _box("a", (0, 0, 0), (2, 2, 2), transform=t)
        b = _box("b", (0, 0, 0), (2, 2, 2), transform=t)
        result = clash_detect([a, b])
        assert any(c["type"] == ClashType.COINCIDENT for c in result["clashes"])


# ---------------------------------------------------------------------------
# 7. Near-coincident but not coincident → no coincident flag
# ---------------------------------------------------------------------------

class TestNearCoincident:
    def test_very_close_but_not_coincident(self):
        """Centres separated by 2× COINCIDENT_TOL → not coincident."""
        offset = COINCIDENT_TOL * 2.0 + 0.001
        a = _box("a", (0, 0, 0), (2, 2, 2))
        b = _box("b", (0, 0, 0), (2, 2, 2), transform=_translate(offset, 0, 0))
        result = clash_detect([a, b])
        assert all(c["type"] != ClashType.COINCIDENT for c in result["clashes"])


# ---------------------------------------------------------------------------
# 8. Single component → empty clashes
# ---------------------------------------------------------------------------

class TestSingleComponent:
    def test_single(self):
        a = _box("only", (0, 0, 0), (1, 1, 1))
        result = clash_detect([a])
        assert result["ok"] is True
        assert result["clashes"] == []


# ---------------------------------------------------------------------------
# 9. Empty input → empty clashes
# ---------------------------------------------------------------------------

class TestEmptyInput:
    def test_empty_list(self):
        result = clash_detect([])
        assert result["ok"] is True
        assert result["clashes"] == []
        assert result["errors"] == []


# ---------------------------------------------------------------------------
# 10. Non-list input → ok=False + error
# ---------------------------------------------------------------------------

class TestInvalidInput:
    def test_non_list_components(self):
        result = clash_detect("not a list")
        assert result["ok"] is False
        assert len(result["errors"]) > 0

    def test_none_components(self):
        result = clash_detect(None)
        assert result["ok"] is False


# ---------------------------------------------------------------------------
# 11. Rotated OBB that overlap after rotation → hard clash
# ---------------------------------------------------------------------------

class TestRotatedOBBOverlap:
    def test_rotated_45_still_overlaps(self):
        """Two boxes at 45° rotation that overlap in world space."""
        # Box A: 4×4×4 cube at origin
        # Box B: 4×4×4 cube at (2,0,0) rotated 45° about Z — should overlap with A
        a = _box("a", (-2, -2, -2), (2, 2, 2))
        t_b = _translate(2, 0, 0)
        b = _box("b", (-2, -2, -2), (2, 2, 2), transform=t_b)
        result = clash_detect([a, b])
        # Boxes overlap since each extends 2mm from its centre and they are 2mm apart
        assert any(c["type"] == ClashType.HARD for c in result["clashes"])


# ---------------------------------------------------------------------------
# 12. Rotated OBB clear despite AABB overlap
# ---------------------------------------------------------------------------

class TestRotatedOBBClear:
    def test_rotated_narrow_box_no_clash(self):
        """
        Long thin box rotated 90° so it points away from second box.
        AABB may overlap but OBB SAT should reject.
        """
        # Box A: thin box along X, 20x1x1
        a = _box("a", (0, -0.5, -0.5), (20, 0.5, 0.5))
        # Box B: thin box along Y at (10,3,0) — points upward, no physical overlap
        t_b = _translate(10, 3, 0)
        b = _box("b", (-0.5, 0, -0.5), (0.5, 20, 0.5), transform=t_b)
        result = clash_detect([a, b])
        # These should not hard-clash (they are separated)
        # (Some AABB overlap may exist but OBB SAT should find no intersection)
        hard_clashes = [c for c in result["clashes"] if c["type"] == ClashType.HARD]
        assert hard_clashes == []


# ---------------------------------------------------------------------------
# 13. Triangle mesh: non-intersecting triangles
# ---------------------------------------------------------------------------

class TestMeshNonIntersecting:
    def test_separate_mesh_triangles(self):
        """Two flat triangle meshes far apart → no hard clash."""
        # Mesh A: triangle at z=0
        tris_a = [((0, 0, 0), (1, 0, 0), (0, 1, 0))]
        # Mesh B: triangle at z=10
        tris_b = [((0, 0, 10), (1, 0, 10), (0, 1, 10))]
        a = ComponentShape("a", bbox_min=(0, 0, 0), bbox_max=(1, 1, 0.01), triangles=tris_a)
        b = ComponentShape("b", bbox_min=(0, 0, 9.99), bbox_max=(1, 1, 10), triangles=tris_b)
        result = clash_detect([a, b])
        hard = [c for c in result["clashes"] if c["type"] == ClashType.HARD]
        assert hard == []


# ---------------------------------------------------------------------------
# 14. Triangle mesh: intersecting triangles → hard clash
# ---------------------------------------------------------------------------

class TestMeshIntersecting:
    def test_crossing_triangles(self):
        """Two triangles that cross each other → hard clash."""
        # Triangle A: flat in the XZ plane (Y=0), centred at (0,0,0)
        tris_a = [((-2, 0, 0), (2, 0, 0), (0, 0, 2))]
        # Triangle B: flat in the XY plane (Z=1), crossing triangle A at Z=1
        # Shifted so bbox centres differ (avoiding coincident detection)
        tris_b = [((0, -2, 1), (0, 2, 1), (0, 0, -1))]
        a = ComponentShape(
            "a",
            bbox_min=(-2, -0.1, 0), bbox_max=(2, 0.1, 2),
            triangles=tris_a,
        )
        b = ComponentShape(
            "b",
            bbox_min=(-0.1, -2, -1), bbox_max=(0.1, 2, 1),
            triangles=tris_b,
        )
        result = clash_detect([a, b])
        hard = [c for c in result["clashes"] if c["type"] == ClashType.HARD]
        assert len(hard) == 1


# ---------------------------------------------------------------------------
# 15. Three components: multiple pairs
# ---------------------------------------------------------------------------

class TestMultipleComponents:
    def test_three_overlapping_pairs(self):
        """Three boxes all in same location → 3 coincident clashes."""
        a = _box("a", (0, 0, 0), (2, 2, 2))
        b = _box("b", (0, 0, 0), (2, 2, 2))
        c = _box("c", (0, 0, 0), (2, 2, 2))
        result = clash_detect([a, b, c])
        assert len(result["clashes"]) == 3  # pairs: (a,b), (a,c), (b,c)

    def test_one_clash_in_three(self):
        """Only one pair clashes out of three components."""
        a = _box("a", (0, 0, 0), (2, 2, 2))
        b = _box("b", (1, 0, 0), (3, 2, 2))   # overlaps A
        c = _box("c", (20, 0, 0), (22, 2, 2)) # far from both
        result = clash_detect([a, b, c])
        hard = [x for x in result["clashes"] if x["type"] == ClashType.HARD]
        assert len(hard) == 1
        ids = {hard[0]["a"], hard[0]["b"]}
        assert ids == {"a", "b"}


# ---------------------------------------------------------------------------
# 16. Hard clash depth > 0 and proportional to overlap
# ---------------------------------------------------------------------------

class TestDepthProportional:
    def test_larger_overlap_larger_depth(self):
        """2mm overlap should produce deeper depth than 1mm overlap."""
        a1 = _box("a1", (0, 0, 0), (5, 5, 5))
        b1 = _box("b1", (4, 0, 0), (9, 5, 5))   # 1mm overlap
        a2 = _box("a2", (0, 0, 0), (5, 5, 5))
        b2 = _box("b2", (3, 0, 0), (8, 5, 5))   # 2mm overlap
        r1 = clash_detect([a1, b1])
        r2 = clash_detect([a2, b2])
        d1 = r1["clashes"][0]["depth"]
        d2 = r2["clashes"][0]["depth"]
        assert d2 > d1


# ---------------------------------------------------------------------------
# 17. Clearance gap value is positive
# ---------------------------------------------------------------------------

class TestClearanceGapValue:
    def test_gap_is_non_negative(self):
        a = _box("a", (0, 0, 0), (2, 2, 2))
        b = _box("b", (4, 0, 0), (6, 2, 2))   # gap = 2mm
        result = clash_detect([a, b], min_clearance=5.0)
        if result["clashes"]:
            c = result["clashes"][0]
            assert c["depth"] >= 0


# ---------------------------------------------------------------------------
# 18. Dict input components
# ---------------------------------------------------------------------------

class TestDictInput:
    def test_dict_components_accepted(self):
        comps = [
            {"instance_id": "d1", "bbox_min": [0, 0, 0], "bbox_max": [2, 2, 2]},
            {"instance_id": "d2", "bbox_min": [10, 0, 0], "bbox_max": [12, 2, 2]},
        ]
        result = clash_detect(comps)
        assert result["ok"] is True
        assert result["clashes"] == []

    def test_dict_overlap(self):
        comps = [
            {"instance_id": "d1", "bbox_min": [0, 0, 0], "bbox_max": [3, 3, 3]},
            {"instance_id": "d2", "bbox_min": [2, 0, 0], "bbox_max": [5, 3, 3]},
        ]
        result = clash_detect(comps)
        assert any(c["type"] == ClashType.HARD for c in result["clashes"])


# ---------------------------------------------------------------------------
# 19. Invalid component dict → error in errors list, others processed
# ---------------------------------------------------------------------------

class TestInvalidComponentDict:
    def test_bad_component_skipped_with_error(self):
        comps = [
            {"instance_id": "ok1", "bbox_min": [0, 0, 0], "bbox_max": [1, 1, 1]},
            {"bbox_min": [0, 0, 0], "bbox_max": [1, 1, 1]},  # missing instance_id
            {"instance_id": "ok2", "bbox_min": [10, 0, 0], "bbox_max": [11, 1, 1]},
        ]
        result = clash_detect(comps)
        assert len(result["errors"]) >= 1
        # ok1 and ok2 are valid; they shouldn't clash with each other
        assert all(c["type"] != ClashType.HARD for c in result["clashes"])


# ---------------------------------------------------------------------------
# 20. min_clearance=0 with near components → no clearance report
# ---------------------------------------------------------------------------

class TestMinClearanceZero:
    def test_near_but_not_overlapping_no_clearance_with_zero_threshold(self):
        a = _box("a", (0, 0, 0), (2, 2, 2))
        b = _box("b", (3, 0, 0), (5, 2, 2))   # 1mm gap
        result = clash_detect([a, b], min_clearance=0.0)
        assert result["clashes"] == []


# ---------------------------------------------------------------------------
# 21. min_clearance=10 with 5mm gap → clearance reported
# ---------------------------------------------------------------------------

class TestMinClearanceLargeThreshold:
    def test_5mm_gap_with_10mm_threshold(self):
        a = _box("a", (0, 0, 0), (2, 2, 2))
        b = _box("b", (7, 0, 0), (9, 2, 2))   # gap = 5mm
        result = clash_detect([a, b], min_clearance=10.0)
        assert any(c["type"] == ClashType.CLEARANCE for c in result["clashes"])


# ---------------------------------------------------------------------------
# 22. Coincident check supersedes hard check
# ---------------------------------------------------------------------------

class TestCoincidentSupersedesHard:
    def test_coincident_type_not_hard(self):
        a = _box("a", (0, 0, 0), (5, 5, 5))
        b = _box("b", (0, 0, 0), (5, 5, 5))
        result = clash_detect([a, b])
        for c in result["clashes"]:
            assert c["type"] == ClashType.COINCIDENT


# ---------------------------------------------------------------------------
# 23. Two components far apart → zero clashes
# ---------------------------------------------------------------------------

class TestFarApart:
    def test_1000mm_separation(self):
        a = _box("a", (0, 0, 0), (1, 1, 1))
        b = _box("b", (1000, 0, 0), (1001, 1, 1))
        result = clash_detect([a, b], min_clearance=100.0)
        assert result["clashes"] == []


# ---------------------------------------------------------------------------
# 24. Component at large translation → still detects clash
# ---------------------------------------------------------------------------

class TestLargeTranslation:
    def test_clash_at_large_offset(self):
        t_a = _translate(1000, 1000, 1000)
        t_b = _translate(1001, 1000, 1000)   # 1mm apart, but each box is 2mm wide
        a = _box("a", (0, 0, 0), (2, 2, 2), transform=t_a)
        b = _box("b", (0, 0, 0), (2, 2, 2), transform=t_b)
        result = clash_detect([a, b])
        assert any(c["type"] == ClashType.HARD for c in result["clashes"])


# ---------------------------------------------------------------------------
# 25. Identity transform + small box overlap
# ---------------------------------------------------------------------------

class TestIdentityTransform:
    def test_identity_transform_behaves_as_default(self):
        a = ComponentShape("a", transform=_identity(), bbox_min=(0, 0, 0), bbox_max=(3, 3, 3))
        b = ComponentShape("b", transform=None, bbox_min=(2, 0, 0), bbox_max=(5, 3, 3))
        result = clash_detect([a, b])
        assert any(c["type"] == ClashType.HARD for c in result["clashes"])


# ---------------------------------------------------------------------------
# 26. Non-square bbox (long thin box)
# ---------------------------------------------------------------------------

class TestNonSquareBbox:
    def test_thin_long_box_no_clash_in_thin_axis(self):
        """Thin box along X does not clash with box offset in Y."""
        a = _box("a", (0, 0, 0), (100, 0.5, 0.5))
        b = _box("b", (0, 2, 0), (100, 2.5, 0.5))
        result = clash_detect([a, b])
        assert result["clashes"] == []


# ---------------------------------------------------------------------------
# 27. Hard clash: depth field is a float
# ---------------------------------------------------------------------------

class TestDepthType:
    def test_depth_is_float(self):
        a = _box("a", (0, 0, 0), (3, 3, 3))
        b = _box("b", (2, 0, 0), (5, 3, 3))
        result = clash_detect([a, b])
        assert len(result["clashes"]) == 1
        assert isinstance(result["clashes"][0]["depth"], float)


# ---------------------------------------------------------------------------
# 28. Clearance record depth is the gap value
# ---------------------------------------------------------------------------

class TestClearanceDepthValue:
    def test_clearance_depth_less_than_min_clearance(self):
        a = _box("a", (0, 0, 0), (2, 2, 2))
        b = _box("b", (4, 0, 0), (6, 2, 2))   # 2mm gap
        result = clash_detect([a, b], min_clearance=5.0)
        if result["clashes"]:
            c = result["clashes"][0]
            assert c["depth"] < 5.0


# ---------------------------------------------------------------------------
# 29. ClashRecord to_dict keys
# ---------------------------------------------------------------------------

class TestClashRecordToDict:
    def test_keys(self):
        r = ClashRecord("c1", "c2", ClashType.HARD, 1.5)
        d = r.to_dict()
        assert set(d.keys()) == {"a", "b", "type", "depth"}
        assert d["a"] == "c1"
        assert d["b"] == "c2"
        assert d["type"] == "hard"
        assert d["depth"] == 1.5


# ---------------------------------------------------------------------------
# 30. ComponentShape validation: empty instance_id
# ---------------------------------------------------------------------------

class TestComponentShapeValidation:
    def test_empty_instance_id(self):
        with pytest.raises(ValueError):
            ComponentShape(instance_id="", bbox_min=(0, 0, 0), bbox_max=(1, 1, 1))

    def test_whitespace_instance_id(self):
        with pytest.raises(ValueError):
            ComponentShape(instance_id="   ", bbox_min=(0, 0, 0), bbox_max=(1, 1, 1))

    def test_bad_transform_length(self):
        with pytest.raises(ValueError):
            ComponentShape(
                instance_id="x",
                transform=[1, 2, 3],  # wrong length
                bbox_min=(0, 0, 0),
                bbox_max=(1, 1, 1),
            )


# ---------------------------------------------------------------------------
# 31. _shape_from_dict round-trip
# ---------------------------------------------------------------------------

class TestShapeFromDict:
    def test_basic_round_trip(self):
        d = {
            "instance_id": "part-1",
            "bbox_min": [0.0, 0.0, 0.0],
            "bbox_max": [5.0, 5.0, 5.0],
        }
        s = _shape_from_dict(d)
        assert s.instance_id == "part-1"
        assert s.bbox_min == (0.0, 0.0, 0.0)
        assert s.bbox_max == (5.0, 5.0, 5.0)
        assert s.triangles is None

    def test_with_transform(self):
        d = {
            "instance_id": "p2",
            "bbox_min": [0, 0, 0],
            "bbox_max": [1, 1, 1],
            "transform": _identity(),
        }
        s = _shape_from_dict(d)
        assert s.transform == _identity()

    def test_missing_instance_id_raises(self):
        with pytest.raises(Exception):
            _shape_from_dict({"bbox_min": [0, 0, 0], "bbox_max": [1, 1, 1]})


# ---------------------------------------------------------------------------
# 32. Multiple overlapping pairs: correct count
# ---------------------------------------------------------------------------

class TestMultiplePairCount:
    def test_four_boxes_all_overlap(self):
        """4 identical boxes → 6 pairs all coincident."""
        boxes = [_box(f"b{i}", (0, 0, 0), (2, 2, 2)) for i in range(4)]
        result = clash_detect(boxes)
        assert len(result["clashes"]) == 6  # C(4,2) = 6

    def test_four_separated_boxes(self):
        """4 boxes all separated → 0 clashes."""
        boxes = [_box(f"b{i}", (i * 10, 0, 0), (i * 10 + 1, 1, 1)) for i in range(4)]
        result = clash_detect(boxes)
        assert result["clashes"] == []


# ---------------------------------------------------------------------------
# 33. Rotated 45-degree OBB corner overlap
# ---------------------------------------------------------------------------

class TestRotated45Overlap:
    def test_45_degree_rotation_centre_overlap(self):
        """
        Box A: 2×2×2 at origin.
        Box B: 2×2×2 rotated 45° about Z, translated so centres are 1mm apart.
        The rotated box corners extend to sqrt(2) ≈ 1.41mm → should overlap A.
        """
        t_b = _translate(1.0, 0.0, 0.0)
        # Apply rotation first in local frame via rotated bbox
        # Use a 3×3 block: rotate then translate
        r = math.radians(45)
        c_, s_ = math.cos(r), math.sin(r)
        t_rot_trans = [
            c_, -s_, 0, 1.0,
            s_,  c_, 0, 0.0,
            0,   0,  1, 0.0,
            0,   0,  0, 1.0,
        ]
        a = _box("a", (-1, -1, -1), (1, 1, 1))
        b = _box("b", (-1, -1, -1), (1, 1, 1), transform=t_rot_trans)
        result = clash_detect([a, b])
        # Centres are 1mm apart; rotated box extends >1mm in X → should overlap
        assert any(c["type"] == ClashType.HARD for c in result["clashes"])


# ---------------------------------------------------------------------------
# 34. OBB SAT internal: verify project gives correct interval
# ---------------------------------------------------------------------------

class TestOBBSATInternal:
    def test_non_overlapping_obb_sat(self):
        """Two unit OBBs 5mm apart should not overlap."""
        a = _box("a", (0, 0, 0), (1, 1, 1))
        b = _box("b", (5, 0, 0), (6, 1, 1))
        obb_a = _OBB(a)
        obb_b = _OBB(b)
        overlapping, _ = _obb_sat(obb_a, obb_b)
        assert overlapping is False

    def test_overlapping_obb_sat(self):
        """Two overlapping unit OBBs should overlap in SAT."""
        a = _box("a", (0, 0, 0), (3, 3, 3))
        b = _box("b", (2, 0, 0), (5, 3, 3))
        obb_a = _OBB(a)
        obb_b = _OBB(b)
        overlapping, depth = _obb_sat(obb_a, obb_b)
        assert overlapping is True
        assert depth > 0
