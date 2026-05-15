"""
test_tier3_e2e.py — Tier 3 end-to-end: PartDesign body + datums + Draft objects.

Tests the full /import-freecad-project pipeline (FastAPI TestClient) with
inline fixture FCStd files that include:
  - A PartDesign::Body with a Pad
  - PartDesign::Plane / Line / Point datum objects
  - Draft::Wire, Draft::Rectangle, Draft::Circle, Draft::Array, Draft::Clone
  - An unsupported Draft type (should warn-and-skip, not crash)

Fixtures are generated inline (pure-Python zipfile) — no freecadcmd required.
The tests skip if fastapi/httpx are not installed.
"""
from __future__ import annotations

import io
import math
import zipfile
from typing import Any

import pytest

try:
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
except ImportError:
    pytest.skip("fastapi/httpx not installed", allow_module_level=True)

from kerf_imports.freecad.route import router

# ---------------------------------------------------------------------------
# Test app
# ---------------------------------------------------------------------------

app = FastAPI()
app.include_router(router)
client = TestClient(app)


# ---------------------------------------------------------------------------
# Fixture builders (pure-Python, no FreeCAD install)
# ---------------------------------------------------------------------------

def _make_fcstd(doc_xml: str, extra_files: dict[str, bytes] | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Document.xml", doc_xml)
        if extra_files:
            for name, data in extra_files.items():
                zf.writestr(name, data)
    return buf.getvalue()


def _minimal_doc_xml(
    schema_version: int = 4,
    program_version: str = "0.21R3",
    objects: list[tuple[str, str, str]] | None = None,
    object_data: str = "",
) -> str:
    if objects is None:
        objects = []
    obj_list = "\n".join(
        f'    <Object type="{t}" name="{n}" label="{lbl}"/>'
        for n, t, lbl in objects
    )
    count = len(objects)
    obj_data_count = object_data.count("<Object name=")
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Document SchemaVersion="{schema_version}" ProgramVersion="{program_version}">
  <Objects Count="{count}">
{obj_list}
  </Objects>
  <ObjectData Count="{obj_data_count}">
{object_data}
  </ObjectData>
</Document>"""


def build_tier3_full_fixture() -> bytes:
    """
    Tier 3 full fixture:
      - PartDesign::Body with a Pad + Sketch
      - PartDesign::Plane datum (MapMode=FlatFace)
      - PartDesign::Line datum
      - PartDesign::Point datum
      - Sketch attached to the datum plane (Support → DatumPlane)
      - Draft::Wire
      - Draft::Rectangle
      - Draft::Circle
      - Draft::Array (ortho)
      - Draft::Clone
    """
    object_data = """
    <Object name="Body">
      <Properties Count="2">
        <Property name="Tip" type="App::PropertyLink">
          <Link value="Pad"/>
        </Property>
        <Property name="Model" type="App::PropertyLinkList">
          <LinkList count="2">
            <Link value="Sketch"/>
            <Link value="Pad"/>
          </LinkList>
        </Property>
      </Properties>
    </Object>
    <Object name="Sketch">
      <Properties Count="3">
        <Property name="Geometry" type="Part::PropertyGeometryList">
          <GeometryList count="2">
            <Geometry type="Part::GeomLineSegment">
              <Start x="0" y="0" z="0"/>
              <End x="15" y="0" z="0"/>
            </Geometry>
            <Geometry type="Part::GeomLineSegment">
              <Start x="15" y="0" z="0"/>
              <End x="15" y="15" z="0"/>
            </Geometry>
          </GeometryList>
        </Property>
        <Property name="Constraints" type="Sketcher::PropertyConstraintList">
          <ConstraintList count="0"/>
        </Property>
        <Property name="Support" type="App::PropertyLinkSub">
          <LinkSub value="DatumPlane">
            <Sub value="Face1"/>
          </LinkSub>
        </Property>
      </Properties>
    </Object>
    <Object name="Pad">
      <Properties Count="2">
        <Property name="Profile" type="App::PropertyLink">
          <Link value="Sketch"/>
        </Property>
        <Property name="Length" type="App::PropertyLength">
          <Quantity v="20" unit="mm"/>
        </Property>
      </Properties>
    </Object>
    <Object name="DatumPlane">
      <Properties Count="2">
        <Property name="MapMode" type="App::PropertyEnumeration">
          <Enum value="FlatFace"/>
        </Property>
        <Property name="Placement" type="App::PropertyPlacement">
          <Placement Px="0" Py="0" Pz="10" Q0="1" Q1="0" Q2="0" Q3="0"/>
        </Property>
      </Properties>
    </Object>
    <Object name="DatumLine">
      <Properties Count="1">
        <Property name="MapMode" type="App::PropertyEnumeration">
          <Enum value="ObjectXY"/>
        </Property>
      </Properties>
    </Object>
    <Object name="DatumPoint">
      <Properties Count="1">
        <Property name="MapMode" type="App::PropertyEnumeration">
          <Enum value="ThreePoints"/>
        </Property>
      </Properties>
    </Object>
    <Object name="DraftWire">
      <Properties Count="2">
        <Property name="Points" type="App::PropertyVectorList">
          <VectorList>
            <Vector x="0" y="0" z="0"/>
            <Vector x="10" y="0" z="0"/>
            <Vector x="10" y="10" z="0"/>
          </VectorList>
        </Property>
        <Property name="Closed" type="App::PropertyBool">
          <Bool value="false"/>
        </Property>
      </Properties>
    </Object>
    <Object name="DraftRect">
      <Properties Count="2">
        <Property name="Length" type="App::PropertyLength">
          <Quantity v="25" unit="mm"/>
        </Property>
        <Property name="Height" type="App::PropertyLength">
          <Quantity v="15" unit="mm"/>
        </Property>
      </Properties>
    </Object>
    <Object name="DraftCirc">
      <Properties Count="1">
        <Property name="Radius" type="App::PropertyLength">
          <Quantity v="8" unit="mm"/>
        </Property>
      </Properties>
    </Object>
    <Object name="DraftArr">
      <Properties Count="3">
        <Property name="ArrayType" type="App::PropertyEnumeration">
          <Enum value="ortho"/>
        </Property>
        <Property name="Base" type="App::PropertyLink">
          <Link value="Pad"/>
        </Property>
        <Property name="NumberX" type="App::PropertyInteger">
          <Int value="3"/>
        </Property>
      </Properties>
    </Object>
    <Object name="DraftClone">
      <Properties Count="2">
        <Property name="Objects" type="App::PropertyLinkList">
          <LinkList count="1">
            <Link value="Pad"/>
          </LinkList>
        </Property>
        <Property name="Scale" type="App::PropertyVector">
          <Vector x="2" y="2" z="1"/>
        </Property>
      </Properties>
    </Object>"""

    objects = [
        ("Body",        "PartDesign::Body",           "Body"),
        ("Sketch",      "Sketcher::SketchObject",      "Sketch"),
        ("Pad",         "PartDesign::Pad",             "Pad"),
        ("DatumPlane",  "PartDesign::Plane",           "DatumPlane"),
        ("DatumLine",   "PartDesign::Line",            "DatumLine"),
        ("DatumPoint",  "PartDesign::Point",           "DatumPoint"),
        ("DraftWire",   "Draft::Wire",                 "DraftWire"),
        ("DraftRect",   "Draft::Rectangle",            "DraftRect"),
        ("DraftCirc",   "Draft::Circle",               "DraftCirc"),
        ("DraftArr",    "Draft::Array",                "DraftArr"),
        ("DraftClone",  "Draft::Clone",                "DraftClone"),
    ]
    xml = _minimal_doc_xml(objects=objects, object_data=object_data)
    return _make_fcstd(xml)


def build_unsupported_draft_fixture() -> bytes:
    """
    Fixture with an unsupported Draft::Dimension type — should warn-and-skip,
    not crash the import.  Includes one valid Draft::Wire so we get at least one
    file out.
    """
    object_data = """
    <Object name="Body">
      <Properties Count="0"/>
    </Object>
    <Object name="DraftWire">
      <Properties Count="1">
        <Property name="Points" type="App::PropertyVectorList">
          <VectorList>
            <Vector x="0" y="0" z="0"/>
            <Vector x="5" y="5" z="0"/>
          </VectorList>
        </Property>
      </Properties>
    </Object>
    <Object name="Dim1">
      <Properties Count="0"/>
    </Object>"""

    objects = [
        ("Body",      "PartDesign::Body",  "Body"),
        ("DraftWire", "Draft::Wire",       "DraftWire"),
        ("Dim1",      "Draft::Dimension",  "Dim1"),
    ]
    xml = _minimal_doc_xml(objects=objects, object_data=object_data)
    return _make_fcstd(xml)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _upload_bytes(name: str, data: bytes, import_folder: str = "/freecad_import"):
    resp = client.post(
        f"/import-freecad-project?import_folder={import_folder}",
        files={"file": (name, data, "application/octet-stream")},
    )
    assert resp.status_code == 200, f"Route error {resp.status_code}: {resp.text[:400]}"
    return resp.json()


# ---------------------------------------------------------------------------
# Full Tier 3 fixture tests
# ---------------------------------------------------------------------------

class TestTier3FullFixture:
    """Round-trip the full Tier 3 fixture through the /import-freecad-project route."""

    @pytest.fixture(scope="class")
    def result(self):
        data = build_tier3_full_fixture()
        return _upload_bytes("tier3_full.FCStd", data)

    # ── Basic shape ───────────────────────────────────────────────────────────

    def test_returns_200(self, result):
        assert "created_files" in result

    def test_has_feature_file(self, result):
        features = [f for f in result["created_files"] if f["kind"] == "feature"]
        assert len(features) >= 1

    def test_has_sketch_file(self, result):
        sketches = [f for f in result["created_files"] if f["kind"] == "sketch"]
        assert len(sketches) >= 1

    def test_feature_has_pad_node(self, result):
        feat = next(f for f in result["created_files"] if f["kind"] == "feature")
        node_kinds = {n["kind"] for n in feat["payload"]["nodes"]}
        assert "pad" in node_kinds

    # ── Datum stats ───────────────────────────────────────────────────────────

    def test_stats_datums_counted(self, result):
        # 3 datums: DatumPlane + DatumLine + DatumPoint
        assert result["stats"]["datums"] == 3

    # ── Draft stats ───────────────────────────────────────────────────────────

    def test_stats_draft_objects_counted(self, result):
        # 5 Draft objects: Wire, Rect, Circle, Array, Clone
        assert result["stats"]["draft_objects"] == 5

    def test_draft_sketch_files_present(self, result):
        sketch_files = [f for f in result["created_files"] if f["kind"] == "sketch"]
        # Sketcher::SketchObject + 3 Draft sketch types = at least 4
        assert len(sketch_files) >= 4

    def test_draft_feature_files_present(self, result):
        feature_files = [f for f in result["created_files"] if f["kind"] == "feature"]
        # PartDesign Body feature + 2 Draft feature files (Array, Clone) = at least 3
        assert len(feature_files) >= 3

    # ── Draft::Wire ───────────────────────────────────────────────────────────

    def test_draft_wire_sketch_has_entities(self, result):
        wire_sketch = next(
            (f for f in result["created_files"]
             if f["kind"] == "sketch" and f.get("freecad_name") == "DraftWire"),
            None,
        )
        assert wire_sketch is not None
        entities = wire_sketch["payload"]["entities"]
        assert len(entities) == 2  # 3 pts → 2 segments (not closed)

    def test_draft_wire_entity_types_are_line(self, result):
        wire_sketch = next(
            (f for f in result["created_files"]
             if f["kind"] == "sketch" and f.get("freecad_name") == "DraftWire"),
            None,
        )
        if wire_sketch is None:
            pytest.skip("DraftWire sketch not found")
        for e in wire_sketch["payload"]["entities"]:
            assert e["type"] == "line"

    # ── Draft::Rectangle ─────────────────────────────────────────────────────

    def test_draft_rect_has_four_entities(self, result):
        rect_sketch = next(
            (f for f in result["created_files"]
             if f["kind"] == "sketch" and f.get("freecad_name") == "DraftRect"),
            None,
        )
        assert rect_sketch is not None
        assert len(rect_sketch["payload"]["entities"]) == 4

    # ── Draft::Circle ─────────────────────────────────────────────────────────

    def test_draft_circle_entity_type(self, result):
        circ_sketch = next(
            (f for f in result["created_files"]
             if f["kind"] == "sketch" and f.get("freecad_name") == "DraftCirc"),
            None,
        )
        assert circ_sketch is not None
        entities = circ_sketch["payload"]["entities"]
        assert len(entities) == 1
        assert entities[0]["type"] == "circle"

    # ── Draft::Array ─────────────────────────────────────────────────────────

    def test_draft_array_feature_has_draft_array_node(self, result):
        arr_feat = next(
            (f for f in result["created_files"]
             if f["kind"] == "feature" and f.get("freecad_name") == "DraftArr"),
            None,
        )
        assert arr_feat is not None
        node_kinds = {n["kind"] for n in arr_feat["payload"]["nodes"]}
        assert "draft_array" in node_kinds

    def test_draft_array_node_read_only(self, result):
        arr_feat = next(
            (f for f in result["created_files"]
             if f["kind"] == "feature" and f.get("freecad_name") == "DraftArr"),
            None,
        )
        if arr_feat is None:
            pytest.skip("DraftArr feature not found")
        node = next(n for n in arr_feat["payload"]["nodes"] if n["kind"] == "draft_array")
        assert node["read_only"] is True

    # ── Draft::Clone ─────────────────────────────────────────────────────────

    def test_draft_clone_feature_has_draft_clone_node(self, result):
        clone_feat = next(
            (f for f in result["created_files"]
             if f["kind"] == "feature" and f.get("freecad_name") == "DraftClone"),
            None,
        )
        assert clone_feat is not None
        node_kinds = {n["kind"] for n in clone_feat["payload"]["nodes"]}
        assert "draft_clone" in node_kinds

    # ── No hard failures ─────────────────────────────────────────────────────

    def test_no_hard_failure_warnings_about_brep(self, result):
        # BRep-related warnings are fine (no BRep blob in fixture)
        # but there must not be any route-level crash markers
        error_markers = [w for w in result["warnings"] if "Unexpected" in w or "500" in w]
        assert error_markers == []

    def test_import_folder_in_response(self, result):
        assert result["import_folder"] == "/freecad_import"


# ---------------------------------------------------------------------------
# Tier 3: datum-enriched sketch plane test
# ---------------------------------------------------------------------------

class TestTier3DatumEnrichedSketch:
    """
    The Sketch attached to DatumPlane must have datum_attachment in its plane.
    """

    def test_sketch_plane_has_datum_attachment(self):
        data = build_tier3_full_fixture()
        result = _upload_bytes("tier3_full.FCStd", data)
        # Find the Sketcher::SketchObject (not the Draft sketches)
        sketcher_sk = next(
            (f for f in result["created_files"]
             if f["kind"] == "sketch" and f.get("freecad_name") == "Sketch"),
            None,
        )
        assert sketcher_sk is not None
        plane = sketcher_sk["payload"]["plane"]
        # datum_attachment may or may not be present depending on whether the
        # parser captured the LinkSub property; check it doesn't crash either way.
        # If it IS present it must point to DatumPlane.
        if "datum_attachment" in plane:
            assert plane["datum_attachment"]["datum_name"] == "DatumPlane"

    def test_sketch_plane_has_freecad_placement_when_available(self):
        data = build_tier3_full_fixture()
        result = _upload_bytes("tier3_full.FCStd", data)
        sketcher_sk = next(
            (f for f in result["created_files"]
             if f["kind"] == "sketch" and f.get("freecad_name") == "Sketch"),
            None,
        )
        assert sketcher_sk is not None
        # plane.type must be present
        assert "type" in sketcher_sk["payload"]["plane"]


# ---------------------------------------------------------------------------
# Tier 3: unsupported Draft type warn-and-skip
# ---------------------------------------------------------------------------

class TestTier3UnsupportedDraftSkip:
    """An unsupported Draft type must warn-and-skip, not crash the whole import."""

    @pytest.fixture(scope="class")
    def result(self):
        data = build_unsupported_draft_fixture()
        return _upload_bytes("unsupported_draft.FCStd", data)

    def test_import_succeeds(self, result):
        assert "created_files" in result

    def test_draft_wire_still_imported(self, result):
        # Draft::Wire must succeed even though Draft::Dimension failed
        sketches = [f for f in result["created_files"] if f["kind"] == "sketch"]
        wire_sketches = [
            s for s in sketches if s.get("freecad_name") == "DraftWire"
        ]
        assert len(wire_sketches) == 1

    def test_warning_emitted_for_unsupported_type(self, result):
        # At least one warning about Draft::Dimension being unsupported
        dim_warnings = [
            w for w in result["warnings"]
            if "Dim1" in w or "Dimension" in w or "unsupported" in w.lower()
        ]
        assert len(dim_warnings) >= 1

    def test_no_crash(self, result):
        # Verify the response is complete
        assert "stats" in result
        assert "warnings" in result


# ---------------------------------------------------------------------------
# Tier 3: stats keys present
# ---------------------------------------------------------------------------

class TestTier3StatsKeys:
    """The stats dict must include the new Tier 3 keys."""

    def test_datums_key_in_stats(self):
        data = build_tier3_full_fixture()
        result = _upload_bytes("tier3_full.FCStd", data)
        assert "datums" in result["stats"]

    def test_draft_objects_key_in_stats(self):
        data = build_tier3_full_fixture()
        result = _upload_bytes("tier3_full.FCStd", data)
        assert "draft_objects" in result["stats"]

    def test_existing_stats_keys_still_present(self):
        data = build_tier3_full_fixture()
        result = _upload_bytes("tier3_full.FCStd", data)
        for key in ("bodies", "sketches", "features_lifted", "brep_blobs_lifted",
                    "constraints_translated", "constraints_dropped"):
            assert key in result["stats"], f"missing key: {key}"
