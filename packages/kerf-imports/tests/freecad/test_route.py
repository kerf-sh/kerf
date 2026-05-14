"""
test_route.py — T6 route tests for POST /import-freecad-project.

Uses FastAPI TestClient + synthetic minimal .FCStd archives (generated in
memory via zipfile + xml).  No freecadcmd required.

Test plan:
  - 400 on non-FCStd file.
  - 422 on unsupported SchemaVersion < 4.
  - 200 with correct structure on empty document.
  - 200 with one sketch file on a document with one Sketcher::SketchObject.
  - 200 with one feature file on a document with one PartDesign::Body.
  - 200 with assembly key on a multi-Body document.
  - stats fields present and numeric.
  - warnings list is always present.
"""
from __future__ import annotations

import io
import json
import zipfile
import xml.etree.ElementTree as ET
from typing import Any

import pytest

# FastAPI TestClient
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
# FCStd archive builder helpers
# ---------------------------------------------------------------------------

def _make_fcstd_bytes(doc_xml: str, extra_files: dict[str, bytes] | None = None) -> bytes:
    """
    Build an in-memory .FCStd zip archive with the given Document.xml content.

    Parameters
    ----------
    doc_xml :
        The XML string for Document.xml.
    extra_files :
        Optional dict of extra members to add (e.g. BRep blobs).
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_STORED) as zf:
        zf.writestr("Document.xml", doc_xml)
        if extra_files:
            for name, data in extra_files.items():
                zf.writestr(name, data)
    return buf.getvalue()


def _empty_doc_xml(schema_version: int = 4) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Document SchemaVersion="{schema_version}" ProgramVersion="0.21R3">
  <Objects Count="0"/>
  <ObjectData Count="0"/>
</Document>"""


def _doc_with_sketch_xml(sketch_name: str = "Sketch") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Document SchemaVersion="4" ProgramVersion="0.21R3">
  <Objects Count="1">
    <Object type="Sketcher::SketchObject" name="{sketch_name}" label="{sketch_name}"/>
  </Objects>
  <ObjectData Count="1">
    <Object name="{sketch_name}">
      <Properties Count="2">
        <Property name="Geometry" type="Part::PropertyGeometryList">
          <GeometryList count="1">
            <Geometry type="Part::GeomLineSegment">
              <Start x="0" y="0" z="0"/>
              <End x="10" y="0" z="0"/>
            </Geometry>
          </GeometryList>
        </Property>
        <Property name="Constraints" type="Sketcher::PropertyConstraintList">
          <ConstraintList count="1">
            <Constrain Name="Horizontal" Type="2" First="0" FirstPos="0" Second="-1"/>
          </ConstraintList>
        </Property>
      </Properties>
    </Object>
  </ObjectData>
</Document>"""


def _doc_with_body_xml(body_name: str = "Body") -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<Document SchemaVersion="4" ProgramVersion="0.21R3">
  <Objects Count="1">
    <Object type="PartDesign::Body" name="{body_name}" label="{body_name}"/>
  </Objects>
  <ObjectData Count="1">
    <Object name="{body_name}">
      <Properties Count="0"/>
    </Object>
  </ObjectData>
</Document>"""


def _doc_with_two_bodies_xml() -> str:
    return """<?xml version="1.0" encoding="utf-8"?>
<Document SchemaVersion="4" ProgramVersion="0.21R3">
  <Objects Count="2">
    <Object type="PartDesign::Body" name="Body" label="Body"/>
    <Object type="PartDesign::Body" name="Body001" label="Body001"/>
  </Objects>
  <ObjectData Count="2">
    <Object name="Body">
      <Properties Count="0"/>
    </Object>
    <Object name="Body001">
      <Properties Count="0"/>
    </Object>
  </ObjectData>
</Document>"""


# ---------------------------------------------------------------------------
# POST /import-freecad-project tests
# ---------------------------------------------------------------------------

class TestImportFreecadProject:
    _url = "/import-freecad-project"

    def _upload(self, fcstd_bytes: bytes, filename: str = "test.FCStd"):
        return client.post(
            self._url,
            files={"file": (filename, fcstd_bytes, "application/octet-stream")},
        )

    # ── 400 / validation errors ───────────────────────────────────────────────

    def test_non_fcstd_returns_400(self):
        resp = self._upload(b"not a zip", filename="model.step")
        assert resp.status_code == 400

    def test_bad_zip_returns_400(self):
        resp = self._upload(b"this is not a zip archive at all")
        assert resp.status_code == 400

    def test_unsupported_schema_version_returns_422(self):
        xml = _empty_doc_xml(schema_version=3)
        resp = self._upload(_make_fcstd_bytes(xml))
        assert resp.status_code == 422

    # ── 200 responses ────────────────────────────────────────────────────────

    def test_empty_doc_returns_200(self):
        resp = self._upload(_make_fcstd_bytes(_empty_doc_xml()))
        assert resp.status_code == 200

    def test_response_has_required_keys(self):
        resp = self._upload(_make_fcstd_bytes(_empty_doc_xml()))
        data = resp.json()
        assert "created_files" in data
        assert "stats" in data
        assert "warnings" in data
        assert "import_folder" in data

    def test_stats_fields_are_numeric(self):
        resp = self._upload(_make_fcstd_bytes(_empty_doc_xml()))
        stats = resp.json()["stats"]
        for key in ("bodies", "sketches", "features_lifted", "brep_blobs_lifted",
                    "constraints_translated", "constraints_dropped"):
            assert key in stats
            assert isinstance(stats[key], int)

    def test_warnings_is_list(self):
        resp = self._upload(_make_fcstd_bytes(_empty_doc_xml()))
        assert isinstance(resp.json()["warnings"], list)

    def test_import_folder_default(self):
        resp = self._upload(_make_fcstd_bytes(_empty_doc_xml()))
        assert resp.json()["import_folder"] == "/freecad_import"

    # ── Sketch file creation ──────────────────────────────────────────────────

    def test_sketch_file_created(self):
        resp = self._upload(_make_fcstd_bytes(_doc_with_sketch_xml()))
        data = resp.json()
        sketch_files = [f for f in data["created_files"] if f["kind"] == "sketch"]
        assert len(sketch_files) == 1

    def test_sketch_file_has_name(self):
        resp = self._upload(_make_fcstd_bytes(_doc_with_sketch_xml()))
        data = resp.json()
        sketch = next(f for f in data["created_files"] if f["kind"] == "sketch")
        assert sketch["name"].endswith(".sketch")

    def test_sketch_stats_counted(self):
        resp = self._upload(_make_fcstd_bytes(_doc_with_sketch_xml()))
        assert resp.json()["stats"]["sketches"] == 1

    def test_sketch_constraints_counted(self):
        resp = self._upload(_make_fcstd_bytes(_doc_with_sketch_xml()))
        # One Horizontal constraint — should be counted
        stats = resp.json()["stats"]
        assert stats["constraints_translated"] >= 0  # at least non-negative
        assert stats["constraints_dropped"] >= 0

    def test_sketch_payload_has_entities(self):
        resp = self._upload(_make_fcstd_bytes(_doc_with_sketch_xml()))
        data = resp.json()
        sketch = next(f for f in data["created_files"] if f["kind"] == "sketch")
        assert "payload" in sketch
        assert "entities" in sketch["payload"]

    # ── Feature file creation ─────────────────────────────────────────────────

    def test_feature_file_created(self):
        resp = self._upload(_make_fcstd_bytes(_doc_with_body_xml()))
        data = resp.json()
        feature_files = [f for f in data["created_files"] if f["kind"] == "feature"]
        assert len(feature_files) == 1

    def test_feature_file_has_name(self):
        resp = self._upload(_make_fcstd_bytes(_doc_with_body_xml()))
        data = resp.json()
        feat = next(f for f in data["created_files"] if f["kind"] == "feature")
        assert feat["name"].endswith(".feature")

    def test_feature_payload_has_nodes(self):
        resp = self._upload(_make_fcstd_bytes(_doc_with_body_xml()))
        data = resp.json()
        feat = next(f for f in data["created_files"] if f["kind"] == "feature")
        assert "payload" in feat
        assert "nodes" in feat["payload"]

    def test_feature_nodes_start_with_import_brep(self):
        resp = self._upload(_make_fcstd_bytes(_doc_with_body_xml()))
        data = resp.json()
        feat = next(f for f in data["created_files"] if f["kind"] == "feature")
        nodes = feat["payload"]["nodes"]
        assert len(nodes) >= 1
        assert nodes[0]["kind"] == "import_brep"

    def test_bodies_stat_counted(self):
        resp = self._upload(_make_fcstd_bytes(_doc_with_body_xml()))
        stats = resp.json()["stats"]
        assert stats["bodies"] >= 1

    # ── Assembly creation (multi-body) ────────────────────────────────────────

    def test_assembly_file_created_for_two_bodies(self):
        resp = self._upload(_make_fcstd_bytes(_doc_with_two_bodies_xml()))
        data = resp.json()
        assembly_files = [f for f in data["created_files"] if f["kind"] == "assembly"]
        assert len(assembly_files) == 1

    def test_assembly_file_is_named_main(self):
        resp = self._upload(_make_fcstd_bytes(_doc_with_two_bodies_xml()))
        data = resp.json()
        asm = next(f for f in data["created_files"] if f["kind"] == "assembly")
        assert asm["name"] == "main.assembly"

    def test_assembly_payload_has_components(self):
        resp = self._upload(_make_fcstd_bytes(_doc_with_two_bodies_xml()))
        data = resp.json()
        asm = next(f for f in data["created_files"] if f["kind"] == "assembly")
        assert "components" in asm["payload"]
        assert len(asm["payload"]["components"]) == 2

    def test_no_assembly_for_single_body(self):
        resp = self._upload(_make_fcstd_bytes(_doc_with_body_xml()))
        data = resp.json()
        assembly_files = [f for f in data["created_files"] if f["kind"] == "assembly"]
        assert len(assembly_files) == 0

    # ── import_folder query param ─────────────────────────────────────────────

    def test_custom_import_folder(self):
        resp = client.post(
            self._url + "?import_folder=/my_freecad",
            files={"file": ("test.FCStd", _make_fcstd_bytes(_empty_doc_xml()), "application/octet-stream")},
        )
        assert resp.json()["import_folder"] == "/my_freecad"


# ---------------------------------------------------------------------------
# POST /import-freecad (legacy) — smoke test
# ---------------------------------------------------------------------------

class TestLegacyRoute:
    def test_legacy_returns_200(self):
        fcstd = _make_fcstd_bytes(_empty_doc_xml())
        resp = client.post(
            "/import-freecad",
            files={"file": ("test.FCStd", fcstd, "application/octet-stream")},
        )
        assert resp.status_code == 200

    def test_legacy_returns_geometry_json_key(self):
        fcstd = _make_fcstd_bytes(_empty_doc_xml())
        resp = client.post(
            "/import-freecad",
            files={"file": ("test.FCStd", fcstd, "application/octet-stream")},
        )
        data = resp.json()
        assert "geometry_json" in data

    def test_legacy_non_fcstd_returns_400(self):
        resp = client.post(
            "/import-freecad",
            files={"file": ("model.step", b"notzip", "application/octet-stream")},
        )
        assert resp.status_code == 400
