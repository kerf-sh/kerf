"""
test_tier3_draft.py — Tier 3: Draft Workbench object translator tests.

Tests:
  - Draft::Wire       → .sketch with line entities
  - Draft::Rectangle  → .sketch with 4 line entities
  - Draft::Circle     → .sketch with circle entity
  - Draft::Circle (arc) → .sketch with arc entity
  - Draft::Polygon    → .sketch with N line entities + warning
  - Draft::Ellipse    → .sketch construction-only + warning
  - Draft::BSpline    → .sketch construction-only + warning
  - Draft::Array      → .feature with draft_array node
  - Draft::Clone      → .feature with draft_clone node
  - Draft::Mirror     → .feature with draft_mirror node
  - Unsupported Draft type → kind="skipped" + warning
  - is_draft_sketch_type / is_draft_feature_type helpers
"""
from __future__ import annotations

import math
import pytest

from kerf_imports.freecad.types import FCStdObject, LinkRef
from kerf_imports.freecad.draft_workbench import (
    translate_draft_object,
    is_draft_sketch_type,
    is_draft_feature_type,
    ALL_DRAFT_TYPES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _obj(name, type_, label=None, **props):
    return FCStdObject(
        name=name,
        type=type_,
        label=label or name,
        properties=dict(props),
    )


# ---------------------------------------------------------------------------
# Draft::Wire
# ---------------------------------------------------------------------------

class TestDraftWire:
    def _wire(self, pts, closed=False):
        return _obj(
            "Wire1", "Draft::Wire",
            Points=pts,
            Closed=closed,
        )

    def test_kind_is_sketch(self):
        pts = [{"x": 0, "y": 0, "z": 0}, {"x": 10, "y": 0, "z": 0}]
        result = translate_draft_object(self._wire(pts))
        assert result["kind"] == "sketch"

    def test_name_ends_with_sketch(self):
        pts = [{"x": 0, "y": 0, "z": 0}, {"x": 10, "y": 0, "z": 0}]
        result = translate_draft_object(self._wire(pts))
        assert result["name"].endswith(".sketch")

    def test_two_points_one_segment(self):
        pts = [{"x": 0, "y": 0, "z": 0}, {"x": 10, "y": 5, "z": 0}]
        result = translate_draft_object(self._wire(pts))
        entities = result["payload"]["entities"]
        assert len(entities) == 1
        assert entities[0]["type"] == "line"
        assert entities[0]["start"] == {"x": 0.0, "y": 0.0}
        assert entities[0]["end"] == {"x": 10.0, "y": 5.0}

    def test_three_points_two_segments(self):
        pts = [
            {"x": 0, "y": 0, "z": 0},
            {"x": 10, "y": 0, "z": 0},
            {"x": 10, "y": 10, "z": 0},
        ]
        result = translate_draft_object(self._wire(pts))
        entities = result["payload"]["entities"]
        assert len(entities) == 2

    def test_closed_wire_adds_closing_segment(self):
        pts = [
            {"x": 0, "y": 0, "z": 0},
            {"x": 10, "y": 0, "z": 0},
            {"x": 10, "y": 10, "z": 0},
        ]
        result = translate_draft_object(self._wire(pts, closed=True))
        entities = result["payload"]["entities"]
        # 3 points → 3 segments when closed (returns to start)
        assert len(entities) == 3

    def test_empty_points_warning(self):
        result = translate_draft_object(self._wire([]))
        assert result["kind"] == "sketch"
        assert any("fewer than 2" in w for w in result["warnings"])
        assert result["payload"]["entities"] == []

    def test_freecad_ref_populated(self):
        pts = [{"x": 0, "y": 0, "z": 0}, {"x": 10, "y": 0, "z": 0}]
        result = translate_draft_object(self._wire(pts))
        ref = result["payload"]["freecad_ref"]
        assert ref["type"] == "Draft::Wire"
        assert ref["name"] == "Wire1"

    def test_z_coordinate_dropped(self):
        pts = [{"x": 1, "y": 2, "z": 99}, {"x": 5, "y": 6, "z": 77}]
        result = translate_draft_object(self._wire(pts))
        start = result["payload"]["entities"][0]["start"]
        assert "z" not in start


# ---------------------------------------------------------------------------
# Draft::Rectangle
# ---------------------------------------------------------------------------

class TestDraftRectangle:
    def _rect(self, length=20.0, height=10.0):
        return _obj("Rect1", "Draft::Rectangle", Length=length, Height=height)

    def test_kind_is_sketch(self):
        result = translate_draft_object(self._rect())
        assert result["kind"] == "sketch"

    def test_four_line_segments(self):
        result = translate_draft_object(self._rect())
        entities = result["payload"]["entities"]
        assert len(entities) == 4
        for e in entities:
            assert e["type"] == "line"

    def test_corners_correct(self):
        result = translate_draft_object(self._rect(length=20.0, height=10.0))
        entities = result["payload"]["entities"]
        # Bottom edge: (0,0) → (20,0)
        bottom = next(e for e in entities if e["start"] == {"x": 0.0, "y": 0.0})
        assert bottom["end"] == {"x": 20.0, "y": 0.0}

    def test_zero_size_still_four_entities(self):
        result = translate_draft_object(self._rect(0.0, 0.0))
        entities = result["payload"]["entities"]
        assert len(entities) == 4


# ---------------------------------------------------------------------------
# Draft::Circle
# ---------------------------------------------------------------------------

class TestDraftCircle:
    def _circle(self, radius=5.0, first=None, last=None):
        props: dict = {"Radius": radius}
        if first is not None:
            props["FirstAngle"] = first
        if last is not None:
            props["LastAngle"] = last
        return _obj("Circle1", "Draft::Circle", **props)

    def test_kind_is_sketch(self):
        result = translate_draft_object(self._circle())
        assert result["kind"] == "sketch"

    def test_full_circle_entity(self):
        result = translate_draft_object(self._circle(radius=7.0))
        entities = result["payload"]["entities"]
        assert len(entities) == 1
        assert entities[0]["type"] == "circle"
        assert entities[0]["radius"] == 7.0
        assert entities[0]["center"] == {"x": 0.0, "y": 0.0}

    def test_arc_when_angles_differ(self):
        result = translate_draft_object(self._circle(radius=5.0, first=45.0, last=270.0))
        entities = result["payload"]["entities"]
        assert entities[0]["type"] == "arc"
        assert entities[0]["start_angle"] == 45.0
        assert entities[0]["end_angle"] == 270.0

    def test_full_360_is_still_circle(self):
        result = translate_draft_object(self._circle(radius=5.0, first=0.0, last=360.0))
        entities = result["payload"]["entities"]
        assert entities[0]["type"] == "circle"


# ---------------------------------------------------------------------------
# Draft::Polygon
# ---------------------------------------------------------------------------

class TestDraftPolygon:
    def _polygon(self, n=6, radius=10.0, mode="inscribed"):
        return _obj("Poly1", "Draft::Polygon",
                    FacesNumber=n,
                    Radius=radius,
                    DrawMode=mode)

    def test_kind_is_sketch(self):
        result = translate_draft_object(self._polygon())
        assert result["kind"] == "sketch"

    def test_six_sided_has_six_segments(self):
        result = translate_draft_object(self._polygon(n=6))
        entities = result["payload"]["entities"]
        assert len(entities) == 6

    def test_triangle_has_three_segments(self):
        result = translate_draft_object(self._polygon(n=3))
        entities = result["payload"]["entities"]
        assert len(entities) == 3

    def test_polygon_warning_emitted(self):
        result = translate_draft_object(self._polygon(n=5))
        assert any("polygon" in w.lower() or "Polygon" in w for w in result["warnings"])

    def test_all_entities_are_lines(self):
        result = translate_draft_object(self._polygon(n=8))
        for e in result["payload"]["entities"]:
            assert e["type"] == "line"


# ---------------------------------------------------------------------------
# Draft::Ellipse
# ---------------------------------------------------------------------------

class TestDraftEllipse:
    def test_kind_is_sketch(self):
        obj = _obj("Ellipse1", "Draft::Ellipse",
                   MajorRadius=10.0, MinorRadius=5.0)
        result = translate_draft_object(obj)
        assert result["kind"] == "sketch"

    def test_ellipse_is_construction(self):
        obj = _obj("Ellipse1", "Draft::Ellipse",
                   MajorRadius=10.0, MinorRadius=5.0)
        result = translate_draft_object(obj)
        entities = result["payload"]["entities"]
        assert len(entities) == 1
        assert entities[0]["construction"] is True
        assert entities[0]["type"] == "ellipse"

    def test_radii_captured(self):
        obj = _obj("Ellipse1", "Draft::Ellipse",
                   MajorRadius=12.0, MinorRadius=6.0)
        result = translate_draft_object(obj)
        e = result["payload"]["entities"][0]
        assert e["major_radius"] == 12.0
        assert e["minor_radius"] == 6.0

    def test_warning_emitted(self):
        obj = _obj("Ellipse1", "Draft::Ellipse",
                   MajorRadius=10.0, MinorRadius=5.0)
        result = translate_draft_object(obj)
        assert any("ellipse" in w.lower() for w in result["warnings"])


# ---------------------------------------------------------------------------
# Draft::BSpline
# ---------------------------------------------------------------------------

class TestDraftBSpline:
    def test_kind_is_sketch(self):
        obj = _obj("BSpline1", "Draft::BSpline",
                   Points=[{"x": 0, "y": 0, "z": 0}, {"x": 5, "y": 5, "z": 0}])
        result = translate_draft_object(obj)
        assert result["kind"] == "sketch"

    def test_bspline_is_construction(self):
        obj = _obj("BSpline1", "Draft::BSpline", Points=[])
        result = translate_draft_object(obj)
        entities = result["payload"]["entities"]
        assert len(entities) == 1
        assert entities[0]["construction"] is True
        assert entities[0]["type"] == "bspline"

    def test_control_points_captured(self):
        pts = [{"x": 0, "y": 0, "z": 0}, {"x": 5, "y": 5, "z": 0}, {"x": 10, "y": 0, "z": 0}]
        obj = _obj("BSpline1", "Draft::BSpline", Points=pts)
        result = translate_draft_object(obj)
        cp = result["payload"]["entities"][0]["control_points"]
        assert len(cp) == 3
        assert cp[0] == {"x": 0.0, "y": 0.0}

    def test_warning_emitted(self):
        obj = _obj("BSpline1", "Draft::BSpline", Points=[])
        result = translate_draft_object(obj)
        assert any("B-spline" in w or "Bezier" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# Draft::Array
# ---------------------------------------------------------------------------

class TestDraftArray:
    def test_kind_is_feature(self):
        obj = _obj("Arr1", "Draft::Array",
                   ArrayType="ortho",
                   Base=LinkRef("Box1"),
                   NumberX=3, NumberY=2, NumberZ=1)
        result = translate_draft_object(obj)
        assert result["kind"] == "feature"

    def test_draft_array_node_kind(self):
        obj = _obj("Arr1", "Draft::Array",
                   ArrayType="ortho",
                   Base=LinkRef("Box1"),
                   NumberX=3, NumberY=2, NumberZ=1)
        result = translate_draft_object(obj)
        node = result["payload"]["nodes"][0]
        assert node["kind"] == "draft_array"

    def test_read_only_true(self):
        obj = _obj("Arr1", "Draft::Array",
                   ArrayType="ortho",
                   Base=LinkRef("Box1"),
                   NumberX=3, NumberY=2, NumberZ=1)
        result = translate_draft_object(obj)
        node = result["payload"]["nodes"][0]
        assert node["read_only"] is True

    def test_base_object_captured(self):
        obj = _obj("Arr1", "Draft::Array",
                   ArrayType="ortho",
                   Base=LinkRef("Pad1"))
        result = translate_draft_object(obj)
        node = result["payload"]["nodes"][0]
        assert node["base_object"] == "Pad1"

    def test_ortho_counts_captured(self):
        obj = _obj("Arr1", "Draft::Array",
                   ArrayType="ortho",
                   Base=LinkRef("Box1"),
                   NumberX=4, NumberY=2, NumberZ=1)
        result = translate_draft_object(obj)
        node = result["payload"]["nodes"][0]
        assert node["numberx"] == 4
        assert node["numbery"] == 2
        assert node["numberz"] == 1

    def test_polar_array_params(self):
        obj = _obj("PArr", "Draft::Array",
                   ArrayType="polar",
                   Base=LinkRef("Box1"),
                   NumberPolar=6,
                   Angle=360.0,
                   Axis={"x": 0, "y": 0, "z": 1},
                   Center={"x": 0, "y": 0, "z": 0})
        result = translate_draft_object(obj)
        node = result["payload"]["nodes"][0]
        assert node["array_type"] == "polar"
        assert node["number_polar"] == 6
        assert node["angle"] == 360.0

    def test_freecad_ref_present(self):
        obj = _obj("Arr1", "Draft::Array", ArrayType="ortho", Base=LinkRef("Box1"))
        result = translate_draft_object(obj)
        node = result["payload"]["nodes"][0]
        assert node["freecad_ref"]["type"] == "Draft::Array"


# ---------------------------------------------------------------------------
# Draft::Clone
# ---------------------------------------------------------------------------

class TestDraftClone:
    def test_kind_is_feature(self):
        obj = _obj("Clone1", "Draft::Clone",
                   Objects=[LinkRef("Box1")],
                   Scale={"x": 1.0, "y": 1.0, "z": 1.0})
        result = translate_draft_object(obj)
        assert result["kind"] == "feature"

    def test_draft_clone_node_kind(self):
        obj = _obj("Clone1", "Draft::Clone",
                   Objects=[LinkRef("Box1")])
        result = translate_draft_object(obj)
        node = result["payload"]["nodes"][0]
        assert node["kind"] == "draft_clone"

    def test_read_only_true(self):
        obj = _obj("Clone1", "Draft::Clone", Objects=[LinkRef("Box1")])
        result = translate_draft_object(obj)
        node = result["payload"]["nodes"][0]
        assert node["read_only"] is True

    def test_source_objects_captured(self):
        obj = _obj("Clone1", "Draft::Clone",
                   Objects=[LinkRef("Pad1"), LinkRef("Pad2")])
        result = translate_draft_object(obj)
        node = result["payload"]["nodes"][0]
        assert "Pad1" in node["source_objects"]
        assert "Pad2" in node["source_objects"]

    def test_scale_captured(self):
        obj = _obj("Clone1", "Draft::Clone",
                   Objects=[LinkRef("Box1")],
                   Scale={"x": 2.0, "y": 2.0, "z": 1.5})
        result = translate_draft_object(obj)
        node = result["payload"]["nodes"][0]
        assert node["scale"] == {"x": 2.0, "y": 2.0, "z": 1.5}

    def test_no_scale_omitted(self):
        obj = _obj("Clone1", "Draft::Clone", Objects=[LinkRef("Box1")])
        result = translate_draft_object(obj)
        node = result["payload"]["nodes"][0]
        assert "scale" not in node


# ---------------------------------------------------------------------------
# Unsupported Draft type
# ---------------------------------------------------------------------------

class TestUnsupportedDraftType:
    def test_unknown_draft_type_skipped(self):
        obj = _obj("Dim1", "Draft::Dimension")
        result = translate_draft_object(obj)
        assert result["kind"] == "skipped"

    def test_skip_warning_present(self):
        obj = _obj("Dim1", "Draft::Dimension")
        result = translate_draft_object(obj)
        assert len(result["warnings"]) >= 1
        assert any("unsupported" in w.lower() or "skipped" in w.lower()
                   for w in result["warnings"])

    def test_no_payload_in_skipped(self):
        obj = _obj("Dim1", "Draft::Dimension")
        result = translate_draft_object(obj)
        assert "payload" not in result


# ---------------------------------------------------------------------------
# is_draft_sketch_type / is_draft_feature_type
# ---------------------------------------------------------------------------

class TestTypeHelpers:
    def test_wire_is_sketch_type(self):
        assert is_draft_sketch_type("Draft::Wire") is True

    def test_rectangle_is_sketch_type(self):
        assert is_draft_sketch_type("Draft::Rectangle") is True

    def test_circle_is_sketch_type(self):
        assert is_draft_sketch_type("Draft::Circle") is True

    def test_array_is_feature_type(self):
        assert is_draft_feature_type("Draft::Array") is True

    def test_clone_is_feature_type(self):
        assert is_draft_feature_type("Draft::Clone") is True

    def test_body_neither(self):
        assert is_draft_sketch_type("PartDesign::Body") is False
        assert is_draft_feature_type("PartDesign::Body") is False

    def test_all_draft_types_non_empty(self):
        assert len(ALL_DRAFT_TYPES) > 0


# ---------------------------------------------------------------------------
# Sketch payload structure invariants
# ---------------------------------------------------------------------------

class TestSketchPayloadStructure:
    """Every sketch payload must have the standard Kerf .sketch keys."""

    def _check_payload(self, result):
        assert result["kind"] == "sketch"
        payload = result["payload"]
        assert "entities" in payload
        assert "constraints" in payload
        assert "plane" in payload
        assert "warnings" in payload
        assert "freecad_ref" in payload

    def test_wire_payload_has_standard_keys(self):
        obj = _obj("W", "Draft::Wire", Points=[{"x": 0, "y": 0, "z": 0}, {"x": 5, "y": 0, "z": 0}])
        self._check_payload(translate_draft_object(obj))

    def test_rectangle_payload_has_standard_keys(self):
        obj = _obj("R", "Draft::Rectangle", Length=10.0, Height=5.0)
        self._check_payload(translate_draft_object(obj))

    def test_circle_payload_has_standard_keys(self):
        obj = _obj("C", "Draft::Circle", Radius=5.0)
        self._check_payload(translate_draft_object(obj))

    def test_ellipse_payload_has_standard_keys(self):
        obj = _obj("E", "Draft::Ellipse", MajorRadius=10.0, MinorRadius=5.0)
        self._check_payload(translate_draft_object(obj))
