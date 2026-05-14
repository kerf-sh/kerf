"""
test_freecad_parser.py — unit tests for the T1 pure-Python FCStd parser.

All tests build .FCStd fixtures in-memory (no real FreeCAD needed).
The fixture XML follows the schema documented in
docs/plans/freecad-tier-1-import.md.

Test plan:
  1. Round-trip — parse a 3-object document (Body + Sketch + Pad),
     assert object count, types, and Link reference from Pad to Sketch.
  2. Property typing — Float, Int, Bool, String, Vector, Placement,
     Link, FloatList all parse to correct Python types.
  3. Schema version gate — SchemaVersion=3 raises FCStdUnsupportedVersionError.
  4. BRep blob extraction — at least one .brp blob is captured as bytes.
  5. Unknown property type — doesn't crash; value starts with "_UNKNOWN_".
  6. FileIncluded property — bytes are returned for a BRep blob reference.
"""
from __future__ import annotations

import io
import zipfile
import pytest

# ---------------------------------------------------------------------------
# Helpers to build in-memory .FCStd archives
# ---------------------------------------------------------------------------

_DOCUMENT_XML_TEMPLATE = """\
<?xml version='1.0' encoding='utf-8'?>
<Document SchemaVersion="{schema_version}" ProgramVersion="{program_version}">
  <Objects Count="{obj_count}">
{object_declarations}
  </Objects>
  <ObjectData Count="{obj_count}">
{object_data}
  </ObjectData>
</Document>
"""

_BODY_DECLARATION = '    <Object type="PartDesign::Body" name="Body" label="Body"/>'
_SKETCH_DECLARATION = '    <Object type="Sketcher::SketchObject" name="Sketch" label="Rectangle sketch"/>'
_PAD_DECLARATION = '    <Object type="PartDesign::Pad" name="Pad" label="Pad"/>'

_BODY_DATA = """\
    <Object name="Body">
      <Properties Count="1">
        <Property name="Label" type="App::PropertyString">
          <String value="Body"/>
        </Property>
      </Properties>
    </Object>"""

_SKETCH_DATA = """\
    <Object name="Sketch">
      <Properties Count="5">
        <Property name="Label" type="App::PropertyString">
          <String value="Rectangle sketch"/>
        </Property>
        <Property name="MapMode" type="App::PropertyString">
          <String value="FlatFace"/>
        </Property>
        <Property name="Geometry" type="Part::PropertyGeometryList">
          <GeometryList count="4">
            <Geometry type="Part::GeomLineSegment">
              <Start x="0" y="0" z="0"/>
              <End x="10" y="0" z="0"/>
            </Geometry>
            <Geometry type="Part::GeomLineSegment">
              <Start x="10" y="0" z="0"/>
              <End x="10" y="10" z="0"/>
            </Geometry>
            <Geometry type="Part::GeomLineSegment">
              <Start x="10" y="10" z="0"/>
              <End x="0" y="10" z="0"/>
            </Geometry>
            <Geometry type="Part::GeomLineSegment">
              <Start x="0" y="10" z="0"/>
              <End x="0" y="0" z="0"/>
            </Geometry>
          </GeometryList>
        </Property>
        <Property name="Constraints" type="Sketcher::PropertyConstraintList">
          <ConstraintList count="2">
            <Constrain Name="Horizontal" Type="2" First="0" FirstPos="0"/>
            <Constrain Name="DistanceX"  Type="7" First="0" FirstPos="1"
                       SecondPos="2" Value="10"/>
          </ConstraintList>
        </Property>
        <Property name="ExternalGeometry" type="App::PropertyLinkSubList">
          <LinkSubList count="0"/>
        </Property>
      </Properties>
    </Object>"""

_PAD_DATA = """\
    <Object name="Pad">
      <Properties Count="5">
        <Property name="Profile" type="App::PropertyLink">
          <Link value="Sketch"/>
        </Property>
        <Property name="Length" type="App::PropertyFloat">
          <Float value="10.0"/>
        </Property>
        <Property name="Symmetric" type="App::PropertyBool">
          <Bool value="false"/>
        </Property>
        <Property name="Label" type="App::PropertyString">
          <String value="Pad"/>
        </Property>
        <Property name="Shape" type="App::PropertyFileIncluded">
          <FileIncluded file="PartShape1.brp"/>
        </Property>
      </Properties>
    </Object>"""

# A minimal valid ASCII BRep blob (just enough bytes to verify extraction)
_FAKE_BREP_BYTES = b"CASCADE Topology V1, (c) Matra-Datavision\nLocations 0\n"


def _build_fcstd(
    schema_version: int = 4,
    program_version: str = "0.21R3",
    include_brep: bool = True,
) -> bytes:
    """Build an in-memory .FCStd zip with Body + Sketch + Pad objects."""
    declarations = "\n".join([_BODY_DECLARATION, _SKETCH_DECLARATION, _PAD_DECLARATION])
    data_blocks = "\n".join([_BODY_DATA, _SKETCH_DATA, _PAD_DATA])
    doc_xml = _DOCUMENT_XML_TEMPLATE.format(
        schema_version=schema_version,
        program_version=program_version,
        obj_count=3,
        object_declarations=declarations,
        object_data=data_blocks,
    ).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("Document.xml", doc_xml)
        if include_brep:
            zf.writestr("PartShape1.brp", _FAKE_BREP_BYTES)
    return buf.getvalue()


def _build_fcstd_with_extra_props(schema_version: int = 4) -> bytes:
    """Build a .FCStd that exercises Float, Int, Bool, Vector, Placement, FloatList."""
    doc_xml = """\
<?xml version='1.0' encoding='utf-8'?>
<Document SchemaVersion="{sv}" ProgramVersion="0.21R3">
  <Objects Count="1">
    <Object type="Part::Feature" name="Props" label="Props"/>
  </Objects>
  <ObjectData Count="1">
    <Object name="Props">
      <Properties Count="8">
        <Property name="AFloat" type="App::PropertyFloat">
          <Float value="3.14"/>
        </Property>
        <Property name="AnInt" type="App::PropertyInteger">
          <Integer value="42"/>
        </Property>
        <Property name="ABool" type="App::PropertyBool">
          <Bool value="true"/>
        </Property>
        <Property name="AString" type="App::PropertyString">
          <String value="hello"/>
        </Property>
        <Property name="AVector" type="App::PropertyVector">
          <Vector x="1.0" y="2.0" z="3.0"/>
        </Property>
        <Property name="APlacement" type="App::PropertyPlacement">
          <Placement Px="1.0" Py="2.0" Pz="3.0" Q0="0.0" Q1="0.0" Q2="0.0" Q3="1.0"/>
        </Property>
        <Property name="ALink" type="App::PropertyLink">
          <Link value="SomeOtherObject"/>
        </Property>
        <Property name="AFloatList" type="App::PropertyFloatList">
          <FloatList count="3">1.0 2.5 3.7</FloatList>
        </Property>
      </Properties>
    </Object>
  </ObjectData>
</Document>
""".format(sv=schema_version).encode("utf-8")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Document.xml", doc_xml)
    return buf.getvalue()


def _build_fcstd_with_unknown_prop() -> bytes:
    """Build a .FCStd with an unknown property type to test graceful degradation."""
    doc_xml = b"""\
<?xml version='1.0' encoding='utf-8'?>
<Document SchemaVersion="4" ProgramVersion="0.21R3">
  <Objects Count="1">
    <Object type="Part::Feature" name="Obj1" label="Obj1"/>
  </Objects>
  <ObjectData Count="1">
    <Object name="Obj1">
      <Properties Count="1">
        <Property name="Mysterious" type="App::PropertyMysteryType42">
          <MysteryValue data="secret"/>
        </Property>
      </Properties>
    </Object>
  </ObjectData>
</Document>
"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("Document.xml", doc_xml)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from kerf_imports.freecad.parser import parse_fcstd  # noqa: E402
from kerf_imports.freecad.types import (  # noqa: E402
    FCStdDocument,
    FCStdObject,
    FCStdUnsupportedVersionError,
    LinkRef,
)


# ---------------------------------------------------------------------------
# Test 1: Round-trip — 3-object document
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def setup_method(self):
        self.doc = parse_fcstd(_build_fcstd())

    def test_returns_fcstd_document(self):
        assert isinstance(self.doc, FCStdDocument)

    def test_schema_version(self):
        assert self.doc.schema_version == 4

    def test_program_version(self):
        assert self.doc.program_version == "0.21R3"

    def test_object_count(self):
        assert len(self.doc.objects) == 3

    def test_object_types(self):
        types = [o.type for o in self.doc.objects]
        assert "PartDesign::Body" in types
        assert "Sketcher::SketchObject" in types
        assert "PartDesign::Pad" in types

    def test_object_names(self):
        names = [o.name for o in self.doc.objects]
        assert "Body" in names
        assert "Sketch" in names
        assert "Pad" in names

    def test_object_labels(self):
        sketch = self.doc.object_by_name("Sketch")
        assert sketch is not None
        assert sketch.label == "Rectangle sketch"

    def test_pad_links_to_sketch(self):
        pad = self.doc.object_by_name("Pad")
        assert pad is not None
        profile = pad.properties.get("Profile")
        assert isinstance(profile, LinkRef)
        assert profile.target_name == "Sketch"

    def test_objects_by_type_helper(self):
        pd_objects = self.doc.objects_by_type("PartDesign::")
        names = [o.name for o in pd_objects]
        assert "Body" in names
        assert "Pad" in names
        assert "Sketch" not in names


# ---------------------------------------------------------------------------
# Test 2: Property typing
# ---------------------------------------------------------------------------

class TestPropertyTyping:
    def setup_method(self):
        self.doc = parse_fcstd(_build_fcstd_with_extra_props())
        self.obj = self.doc.object_by_name("Props")
        assert self.obj is not None

    def test_float(self):
        v = self.obj.properties["AFloat"]
        assert isinstance(v, float)
        assert abs(v - 3.14) < 1e-6

    def test_int(self):
        v = self.obj.properties["AnInt"]
        assert isinstance(v, int)
        assert v == 42

    def test_bool_true(self):
        v = self.obj.properties["ABool"]
        assert v is True

    def test_string(self):
        v = self.obj.properties["AString"]
        assert v == "hello"

    def test_vector(self):
        v = self.obj.properties["AVector"]
        assert isinstance(v, dict)
        assert v["x"] == pytest.approx(1.0)
        assert v["y"] == pytest.approx(2.0)
        assert v["z"] == pytest.approx(3.0)

    def test_placement(self):
        v = self.obj.properties["APlacement"]
        assert isinstance(v, dict)
        assert v["Px"] == pytest.approx(1.0)
        assert v["Py"] == pytest.approx(2.0)
        assert v["Pz"] == pytest.approx(3.0)
        assert v["Q3"] == pytest.approx(1.0)

    def test_link(self):
        v = self.obj.properties["ALink"]
        assert isinstance(v, LinkRef)
        assert v.target_name == "SomeOtherObject"

    def test_float_list(self):
        v = self.obj.properties["AFloatList"]
        assert isinstance(v, list)
        assert len(v) == 3
        assert v[0] == pytest.approx(1.0)
        assert v[1] == pytest.approx(2.5)
        assert v[2] == pytest.approx(3.7)


# ---------------------------------------------------------------------------
# Test 3: Schema version gate
# ---------------------------------------------------------------------------

class TestSchemaVersionGate:
    def test_version_3_raises(self):
        with pytest.raises(FCStdUnsupportedVersionError) as exc_info:
            parse_fcstd(_build_fcstd(schema_version=3))
        assert exc_info.value.version == 3

    def test_version_4_accepted(self):
        doc = parse_fcstd(_build_fcstd(schema_version=4))
        assert doc.schema_version == 4

    def test_version_5_accepted(self):
        doc = parse_fcstd(_build_fcstd(schema_version=5))
        assert doc.schema_version == 5

    def test_error_message_mentions_version(self):
        with pytest.raises(FCStdUnsupportedVersionError) as exc_info:
            parse_fcstd(_build_fcstd(schema_version=2))
        assert "2" in str(exc_info.value)
        assert "0.19" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test 4: BRep blob extraction
# ---------------------------------------------------------------------------

class TestBRepBlobExtraction:
    def test_brep_blobs_captured(self):
        doc = parse_fcstd(_build_fcstd(include_brep=True))
        assert len(doc.brep_blobs) >= 1

    def test_brep_blob_key_matches_filename(self):
        doc = parse_fcstd(_build_fcstd(include_brep=True))
        assert "PartShape1.brp" in doc.brep_blobs

    def test_brep_blob_is_bytes(self):
        doc = parse_fcstd(_build_fcstd(include_brep=True))
        blob = doc.brep_blobs["PartShape1.brp"]
        assert isinstance(blob, bytes)
        assert len(blob) > 0

    def test_brep_blob_content_matches(self):
        doc = parse_fcstd(_build_fcstd(include_brep=True))
        assert doc.brep_blobs["PartShape1.brp"] == _FAKE_BREP_BYTES

    def test_file_included_property_returns_bytes(self):
        """
        The Shape property on Pad uses FileIncluded — it should return the
        raw BRep bytes from the zip when parsed inline.
        """
        doc = parse_fcstd(_build_fcstd(include_brep=True))
        pad = doc.object_by_name("Pad")
        assert pad is not None
        shape_val = pad.properties.get("Shape")
        # FileIncluded returns raw bytes when the zip member exists
        assert isinstance(shape_val, bytes)
        assert len(shape_val) > 0

    def test_no_brep_when_none_in_archive(self):
        doc = parse_fcstd(_build_fcstd(include_brep=False))
        assert len(doc.brep_blobs) == 0


# ---------------------------------------------------------------------------
# Test 5: Unknown property type
# ---------------------------------------------------------------------------

class TestUnknownPropertyType:
    def test_does_not_crash(self):
        doc = parse_fcstd(_build_fcstd_with_unknown_prop())
        assert len(doc.objects) == 1

    def test_marks_as_unknown(self):
        doc = parse_fcstd(_build_fcstd_with_unknown_prop())
        obj = doc.objects[0]
        v = obj.properties.get("Mysterious")
        assert isinstance(v, str)
        assert v.startswith("_UNKNOWN_")

    def test_unknown_value_contains_type_name(self):
        doc = parse_fcstd(_build_fcstd_with_unknown_prop())
        obj = doc.objects[0]
        v = obj.properties.get("Mysterious")
        assert "MysteryType42" in v


# ---------------------------------------------------------------------------
# Test 6: Sketch properties (GeometryList + ConstraintList)
# ---------------------------------------------------------------------------

class TestSketchProperties:
    def setup_method(self):
        self.doc = parse_fcstd(_build_fcstd())
        self.sketch = self.doc.object_by_name("Sketch")

    def test_geometry_list_parsed(self):
        geom = self.sketch.properties.get("Geometry")
        assert isinstance(geom, list)
        assert len(geom) == 4

    def test_geometry_types(self):
        geom = self.sketch.properties.get("Geometry")
        for g in geom:
            assert g["type"] == "Part::GeomLineSegment"

    def test_constraint_list_parsed(self):
        constraints = self.sketch.properties.get("Constraints")
        assert isinstance(constraints, list)
        assert len(constraints) == 2

    def test_constraint_type_coerced_to_int(self):
        constraints = self.sketch.properties.get("Constraints")
        types = [c["Type"] for c in constraints]
        assert 2 in types   # Horizontal
        assert 7 in types   # DistanceX

    def test_constraint_value_coerced_to_float(self):
        constraints = self.sketch.properties.get("Constraints")
        dist_x = next(c for c in constraints if c["Type"] == 7)
        assert dist_x["Value"] == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Test 7: Accepting bytes input (upload path)
# ---------------------------------------------------------------------------

class TestBytesInput:
    def test_accepts_bytes(self):
        raw = _build_fcstd()
        assert isinstance(raw, bytes)
        doc = parse_fcstd(raw)
        assert doc.schema_version == 4
        assert len(doc.objects) == 3

    def test_accepts_bytearray(self):
        raw = bytearray(_build_fcstd())
        doc = parse_fcstd(raw)
        assert doc.schema_version == 4


# ---------------------------------------------------------------------------
# Test 8: raw_xml preservation
# ---------------------------------------------------------------------------

class TestRawXML:
    def test_document_xml_preserved(self):
        doc = parse_fcstd(_build_fcstd())
        assert "Document.xml" in doc.raw_xml
        assert isinstance(doc.raw_xml["Document.xml"], bytes)

    def test_raw_xml_contains_valid_content(self):
        doc = parse_fcstd(_build_fcstd())
        xml_bytes = doc.raw_xml["Document.xml"]
        assert b"SchemaVersion" in xml_bytes


# ---------------------------------------------------------------------------
# Test 9: LinkRef repr
# ---------------------------------------------------------------------------

class TestLinkRef:
    def test_repr_no_subs(self):
        ref = LinkRef("Body")
        assert "Body" in repr(ref)

    def test_repr_with_subs(self):
        ref = LinkRef("Body", ["Edge1", "Face2"])
        r = repr(ref)
        assert "Body" in r
        assert "Edge1" in r
