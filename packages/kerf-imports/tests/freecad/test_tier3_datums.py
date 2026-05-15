"""
test_tier3_datums.py — Tier 3: PartDesign datum object translator tests.

Tests:
  - PartDesign::Plane → datum_plane dict with placement + map_mode
  - PartDesign::Line  → datum_line dict
  - PartDesign::Point → datum_point dict
  - build_datum_map: collects all datums from a doc
  - sketch_attachment_from_datum: resolves sketch → datum link
  - Non-datum type returns None
  - Missing properties handled gracefully
"""
from __future__ import annotations

import pytest

from kerf_imports.freecad.types import FCStdDocument, FCStdObject, LinkRef
from kerf_imports.freecad.datums import (
    translate_datum,
    build_datum_map,
    sketch_attachment_from_datum,
    ALL_DATUM_TYPES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_doc(*objects):
    return FCStdDocument(
        schema_version=4,
        program_version="0.21R3",
        objects=list(objects),
        properties={},
        brep_blobs={},
        raw_xml={},
    )


def _datum_plane(name="DatumPlane", label=None, map_mode="FlatFace", placement=None):
    props: dict = {"MapMode": map_mode}
    if placement is not None:
        props["Placement"] = placement
    return FCStdObject(
        name=name,
        type="PartDesign::Plane",
        label=label or name,
        properties=props,
    )


def _datum_line(name="DatumLine", label=None):
    return FCStdObject(
        name=name,
        type="PartDesign::Line",
        label=label or name,
        properties={"MapMode": "ObjectXY"},
    )


def _datum_point(name="DatumPoint", label=None):
    return FCStdObject(
        name=name,
        type="PartDesign::Point",
        label=label or name,
        properties={"MapMode": "ThreePoints"},
    )


def _sketch(name="Sketch", support=None):
    props: dict = {"Geometry": [], "Constraints": []}
    if support is not None:
        props["Support"] = support
    return FCStdObject(
        name=name,
        type="Sketcher::SketchObject",
        label=name,
        properties=props,
    )


# ---------------------------------------------------------------------------
# PartDesign::Plane
# ---------------------------------------------------------------------------

class TestDatumPlane:
    def test_kind_is_datum_plane(self):
        obj = _datum_plane()
        result = translate_datum(obj)
        assert result is not None
        assert result["kind"] == "datum_plane"

    def test_name_and_label_preserved(self):
        obj = _datum_plane(name="MyPlane", label="My Datum Plane")
        result = translate_datum(obj)
        assert result["name"] == "MyPlane"
        assert result["label"] == "My Datum Plane"

    def test_map_mode_translated(self):
        obj = _datum_plane(map_mode="FlatFace")
        result = translate_datum(obj)
        assert result["map_mode"] == "face"

    def test_map_mode_world_xy(self):
        obj = _datum_plane(map_mode="ObjectXY")
        result = translate_datum(obj)
        assert result["map_mode"] == "world_xy"

    def test_unknown_map_mode_preserved_raw(self):
        obj = _datum_plane(map_mode="SomeFutureMode")
        result = translate_datum(obj)
        assert result["map_mode"] == "SomeFutureMode"

    def test_placement_captured(self):
        placement = {"Px": 10.0, "Py": 0.0, "Pz": 5.0, "Q0": 1.0, "Q1": 0.0, "Q2": 0.0, "Q3": 0.0}
        obj = _datum_plane(placement=placement)
        result = translate_datum(obj)
        assert result.get("placement") == placement

    def test_no_placement_omitted(self):
        obj = _datum_plane()
        result = translate_datum(obj)
        assert "placement" not in result

    def test_map_reversed_default_false(self):
        obj = _datum_plane()
        result = translate_datum(obj)
        assert result["map_reversed"] is False

    def test_map_reversed_true(self):
        obj = FCStdObject(
            name="P", type="PartDesign::Plane", label="P",
            properties={"MapMode": "FlatFace", "MapReversed": True},
        )
        result = translate_datum(obj)
        assert result["map_reversed"] is True

    def test_freecad_ref_populated(self):
        obj = _datum_plane(name="DP1")
        result = translate_datum(obj)
        ref = result["freecad_ref"]
        assert ref["type"] == "PartDesign::Plane"
        assert ref["name"] == "DP1"

    def test_support_refs_extracted(self):
        obj = FCStdObject(
            name="P", type="PartDesign::Plane", label="P",
            properties={
                "MapMode": "FlatFace",
                "Support": LinkRef("Pad", ["Face3"]),
            },
        )
        result = translate_datum(obj)
        assert "support_refs" in result
        assert result["support_refs"][0]["object"] == "Pad"
        assert "Face3" in result["support_refs"][0]["sub_elements"]


# ---------------------------------------------------------------------------
# PartDesign::Line
# ---------------------------------------------------------------------------

class TestDatumLine:
    def test_kind_is_datum_line(self):
        obj = _datum_line()
        result = translate_datum(obj)
        assert result is not None
        assert result["kind"] == "datum_line"

    def test_name_preserved(self):
        obj = _datum_line(name="MyAxis")
        result = translate_datum(obj)
        assert result["name"] == "MyAxis"

    def test_freecad_ref_type(self):
        obj = _datum_line()
        result = translate_datum(obj)
        assert result["freecad_ref"]["type"] == "PartDesign::Line"


# ---------------------------------------------------------------------------
# PartDesign::Point
# ---------------------------------------------------------------------------

class TestDatumPoint:
    def test_kind_is_datum_point(self):
        obj = _datum_point()
        result = translate_datum(obj)
        assert result is not None
        assert result["kind"] == "datum_point"

    def test_freecad_ref_type(self):
        obj = _datum_point()
        result = translate_datum(obj)
        assert result["freecad_ref"]["type"] == "PartDesign::Point"


# ---------------------------------------------------------------------------
# Non-datum type → None
# ---------------------------------------------------------------------------

class TestNonDatumReturnsNone:
    def test_body_returns_none(self):
        obj = FCStdObject(name="Body", type="PartDesign::Body", label="Body", properties={})
        assert translate_datum(obj) is None

    def test_sketch_returns_none(self):
        obj = FCStdObject(name="Sk", type="Sketcher::SketchObject", label="Sk", properties={})
        assert translate_datum(obj) is None

    def test_pad_returns_none(self):
        obj = FCStdObject(name="Pad", type="PartDesign::Pad", label="Pad", properties={})
        assert translate_datum(obj) is None


# ---------------------------------------------------------------------------
# build_datum_map
# ---------------------------------------------------------------------------

class TestBuildDatumMap:
    def test_collects_plane_line_point(self):
        plane = _datum_plane("DP1")
        line = _datum_line("DL1")
        point = _datum_point("DPt1")
        non_datum = FCStdObject(name="Body", type="PartDesign::Body", label="Body", properties={})
        doc = _make_doc(plane, line, point, non_datum)

        dm = build_datum_map(doc)
        assert "DP1" in dm
        assert "DL1" in dm
        assert "DPt1" in dm
        assert "Body" not in dm

    def test_empty_doc(self):
        doc = _make_doc()
        dm = build_datum_map(doc)
        assert dm == {}

    def test_map_values_are_dicts(self):
        plane = _datum_plane("DP1")
        doc = _make_doc(plane)
        dm = build_datum_map(doc)
        assert isinstance(dm["DP1"], dict)
        assert dm["DP1"]["kind"] == "datum_plane"

    def test_mixed_objects_only_datums_collected(self):
        plane = _datum_plane("DP")
        sketch = _sketch("Sk")
        doc = _make_doc(plane, sketch)
        dm = build_datum_map(doc)
        assert len(dm) == 1
        assert "DP" in dm


# ---------------------------------------------------------------------------
# sketch_attachment_from_datum
# ---------------------------------------------------------------------------

class TestSketchAttachmentFromDatum:
    def _build_datum_map(self):
        plane = _datum_plane("DP1", map_mode="FlatFace")
        doc = _make_doc(plane)
        return build_datum_map(doc)

    def test_sketch_with_datum_support_resolved(self):
        dm = self._build_datum_map()
        sk = _sketch("Sk", support=LinkRef("DP1", ["Face1"]))
        result = sketch_attachment_from_datum(sk, dm)
        assert result is not None
        assert result["datum_name"] == "DP1"
        assert result["datum_kind"] == "datum_plane"
        assert result["map_mode"] == "face"

    def test_sketch_without_support_returns_none(self):
        dm = self._build_datum_map()
        sk = _sketch("Sk")  # no Support
        result = sketch_attachment_from_datum(sk, dm)
        assert result is None

    def test_sketch_with_unknown_support_returns_none(self):
        dm = self._build_datum_map()
        sk = _sketch("Sk", support=LinkRef("UnknownObj"))
        result = sketch_attachment_from_datum(sk, dm)
        assert result is None

    def test_label_included_in_result(self):
        plane = FCStdObject(
            name="DP1", type="PartDesign::Plane", label="Top Face Datum",
            properties={"MapMode": "FlatFace"},
        )
        doc = _make_doc(plane)
        dm = build_datum_map(doc)
        sk = _sketch("Sk", support=LinkRef("DP1"))
        result = sketch_attachment_from_datum(sk, dm)
        assert result["datum_label"] == "Top Face Datum"


# ---------------------------------------------------------------------------
# ALL_DATUM_TYPES coverage
# ---------------------------------------------------------------------------

class TestAllDatumTypesCoverage:
    def test_plane_in_all_datum_types(self):
        assert "PartDesign::Plane" in ALL_DATUM_TYPES

    def test_line_in_all_datum_types(self):
        assert "PartDesign::Line" in ALL_DATUM_TYPES

    def test_point_in_all_datum_types(self):
        assert "PartDesign::Point" in ALL_DATUM_TYPES

    def test_body_not_in_all_datum_types(self):
        assert "PartDesign::Body" not in ALL_DATUM_TYPES
