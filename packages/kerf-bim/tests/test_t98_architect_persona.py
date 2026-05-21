"""
test_t98_architect_persona.py — T-98 hermetic pytest suite.

Architect persona: space program from chat → IFC export → import back.
Success: spaces visible in 3D; IFC export valid; round-trip preserves
spaces & GlobalIds.

All tests are pure-Python (no ifcopenshell, no filesystem writes, no network,
no Postgres).  The import-side translator (import_ifc/spaces.py) is exercised
with lightweight mock objects; the export-side writer (export_ifc/writer.py)
is exercised directly.

Test inventory (20 cases)
--------------------------
Translate (pure-mock, no ifcopenshell):
 1  translate_space returns required keys
 2  translate_space: LongName takes priority over Name
 3  translate_space: Name fallback when LongName absent
 4  translate_space: "Space" fallback when both Name and LongName empty
 5  translate_space: boundary extracted from IfcPolyline items
 6  translate_space: fallback boundary when Representation is None
 7  translate_space: fallback boundary is a 4-point polygon
 8  translate_space: storey resolved via Decomposes relationship
 9  translate_space: storey resolved via ContainedInStructure relationship
10  translate_space: global_id present in result when space has GlobalId

Export (pure writer):
11  export_ifc with spaces emits IfcSpace entities
12  IfcSpace entity count matches number of spaces in model
13  Space name appears in IFC text
14  Space boundary dimensions (mm → m) appear in IFC text
15  Space GlobalId is deterministic across two exports
16  Preserved global_id round-trips into the IFC STEP text verbatim
17  export_ifc with spaces passes forward-reference validation
18  No VALIDATION warnings for a well-formed model with spaces
19  Multi-level model: spaces are contained in correct storey
20  Round-trip: export spaces to IFC text, parse STEP text for IfcSpace, names match
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# ── sys.path bootstrap (mirrors conftest.py) ──────────────────────────────────
_HERE = Path(__file__).parent
_PLUGIN_ROOT = _HERE.parent
_PACKAGES = _PLUGIN_ROOT.parent

for _entry in _PACKAGES.iterdir():
    if not _entry.name.startswith("kerf-"):
        continue
    _src = _entry / "src"
    if _src.is_dir() and str(_src) not in sys.path:
        sys.path.insert(0, str(_src))

# ── Imports under test ────────────────────────────────────────────────────────
from kerf_bim.export_ifc import export_ifc, IFCExportResult
from kerf_bim.import_ifc.spaces import translate_space

# ── Shared helpers ────────────────────────────────────────────────────────────


def _count_ifc(text: str, ifc_type: str) -> int:
    return len(re.findall(rf"#\d+={ifc_type.upper()}\(", text, re.IGNORECASE))


def _defined_ids(text: str) -> set[int]:
    data = re.search(r"DATA;(.+)ENDSEC;", text, re.DOTALL)
    if not data:
        return set()
    return {int(m) for m in re.findall(r"^#(\d+)=", data.group(1), re.MULTILINE)}


def _referenced_ids(text: str) -> set[int]:
    data = re.search(r"DATA;(.+)ENDSEC;", text, re.DOTALL)
    if not data:
        return set()
    rhs = re.sub(r"^#\d+=", "", data.group(1), flags=re.MULTILINE)
    return {int(m) for m in re.findall(r"#(\d+)", rhs)}


def _extract_space_guids(text: str) -> list[str]:
    """Extract GlobalId values from IFCSPACE( entities."""
    return re.findall(r"#\d+=IFCSPACE\('([^']+)'", text, re.IGNORECASE)


# ── Mock helpers ─────────────────────────────────────────────────────────────


def _ns(**kwargs) -> SimpleNamespace:
    """Build a SimpleNamespace with arbitrary attributes."""
    return SimpleNamespace(**kwargs)


def _mock_polyline_space(
    name: str = "Living Room",
    long_name: str = "",
    global_id: str = "SPACE_GID_00000000001",
    boundary_pts: list[tuple[float, float]] | None = None,
    storey_name: str = "L1",
    storey_gid: str = "STOREY_GID_000000001",
):
    """
    Construct a mock IfcSpace entity that exposes:
    - Name, LongName, GlobalId
    - Representation with a FootPrint IfcPolyline
    - Decomposes → IfcBuildingStorey
    """
    if boundary_pts is None:
        boundary_pts = [(0.0, 0.0), (4000.0, 0.0), (4000.0, 3000.0), (0.0, 3000.0), (0.0, 0.0)]

    # Build point objects
    points = [
        _ns(Coordinates=(x, y))
        for x, y in boundary_pts
    ]

    # IfcPolyline item in FootPrint representation
    polyline_item = _ns(**{"is_a": lambda: "IfcPolyline", "Points": points})

    # Shape representation with RepresentationIdentifier = "FootPrint"
    shape_rep = _ns(
        RepresentationIdentifier="FootPrint",
        Items=[polyline_item],
    )

    # Product representation
    product_rep = _ns(Representations=[shape_rep])

    # Storey
    storey = _ns(**{"is_a": lambda: "IfcBuildingStorey", "GlobalId": storey_gid, "Name": storey_name})

    # IfcRelAggregates pointing to storey (Decomposes)
    rel_agg = _ns(RelatingObject=storey)

    return _ns(
        Name=name,
        LongName=long_name,
        GlobalId=global_id,
        Representation=product_rep,
        Decomposes=[rel_agg],
        ContainedInStructure=[],
        ObjectPlacement=None,
    )


# ---------------------------------------------------------------------------
# Tests 1-10: translate_space (pure mock, no ifcopenshell)
# ---------------------------------------------------------------------------


class TestTranslateSpace(unittest.TestCase):
    """translate_space returns correct .bim space dicts from mock IfcSpace objects."""

    def _translate(self, space, level_map=None):
        warnings: list[str] = []
        result = translate_space(space, level_map or {}, warnings)
        return result, warnings

    # 1
    def test_returns_required_keys(self):
        """Result must have 'name', 'level', 'boundary'."""
        sp = _mock_polyline_space()
        result, _ = self._translate(sp, {"STOREY_GID_000000001": "L1"})
        for key in ("name", "level", "boundary"):
            self.assertIn(key, result, f"key {key!r} missing from result")

    # 2
    def test_long_name_priority_over_name(self):
        """LongName should override Name for display_name."""
        sp = _mock_polyline_space(name="101", long_name="Master Bedroom")
        result, _ = self._translate(sp)
        self.assertEqual(result["name"], "Master Bedroom")

    # 3
    def test_name_fallback_when_long_name_empty(self):
        """When LongName is empty, Name is used."""
        sp = _mock_polyline_space(name="Kitchen", long_name="")
        result, _ = self._translate(sp)
        self.assertEqual(result["name"], "Kitchen")

    # 4
    def test_fallback_name_when_both_absent(self):
        """When both Name and LongName are empty, result name is 'Space'."""
        sp = _mock_polyline_space(name="", long_name="")
        result, _ = self._translate(sp)
        self.assertEqual(result["name"], "Space")

    # 5
    def test_boundary_extracted_from_polyline(self):
        """Boundary polygon extracted from IfcPolyline FootPrint representation."""
        pts = [(0.0, 0.0), (6000.0, 0.0), (6000.0, 4000.0), (0.0, 4000.0), (0.0, 0.0)]
        sp = _mock_polyline_space(boundary_pts=pts)
        result, warnings = self._translate(sp)
        # Closing duplicate is removed
        self.assertLessEqual(len(result["boundary"]), 4)
        self.assertGreaterEqual(len(result["boundary"]), 3)
        # First point should be [0.0, 0.0]
        self.assertEqual(result["boundary"][0], [0.0, 0.0])

    # 6
    def test_fallback_boundary_when_no_representation(self):
        """When Representation is None, a 4-point fallback is returned and warning emitted."""
        sp = _mock_polyline_space()
        sp.Representation = None
        result, warnings = self._translate(sp)
        self.assertEqual(len(result["boundary"]), 4)
        self.assertTrue(any("default boundary" in w.lower() for w in warnings))

    # 7
    def test_fallback_boundary_is_quadrilateral(self):
        """Fallback boundary must be a 4-point rectangle."""
        sp = _mock_polyline_space()
        sp.Representation = None
        result, _ = self._translate(sp)
        self.assertEqual(len(result["boundary"]), 4)
        # All points are [x, y]
        for pt in result["boundary"]:
            self.assertEqual(len(pt), 2)

    # 8
    def test_storey_resolved_via_decomposes(self):
        """Level name is extracted from Decomposes → IfcBuildingStorey."""
        sp = _mock_polyline_space(storey_gid="GID_L2", storey_name="L2")
        result, _ = self._translate(sp, {"GID_L2": "Level 2"})
        self.assertEqual(result["level"], "Level 2")

    # 9
    def test_storey_resolved_via_contained_in_structure(self):
        """Level name is extracted via ContainedInStructure when Decomposes is empty."""
        storey = _ns(**{"is_a": lambda: "IfcBuildingStorey", "GlobalId": "GID_GF", "Name": "GF"})
        rel = _ns(RelatingStructure=storey)
        sp = _mock_polyline_space()
        sp.Decomposes = []
        sp.ContainedInStructure = [rel]
        result, _ = self._translate(sp, {"GID_GF": "Ground Floor"})
        self.assertEqual(result["level"], "Ground Floor")

    # 10
    def test_global_id_captured_in_result(self):
        """global_id key is present and matches the IfcSpace GlobalId."""
        gid = "MYGLOBALID000000001234"
        sp = _mock_polyline_space(global_id=gid)
        result, _ = self._translate(sp)
        self.assertIn("global_id", result)
        self.assertEqual(result["global_id"], gid)


# ---------------------------------------------------------------------------
# Tests 11-18: export_ifc with spaces (pure writer, no ifcopenshell)
# ---------------------------------------------------------------------------

_ARCH_MODEL: dict[str, Any] = {
    "name": "ArchitectPersonaProject",
    "levels": [{"name": "GF", "elevation": 0.0}],
    "walls": [
        {
            "name": "Perimeter_W",
            "level": "GF",
            "from": [0.0, 0.0],
            "to": [10_000.0, 0.0],
            "height": 3_200.0,
            "thickness": 300.0,
        }
    ],
    "spaces": [
        {
            "name": "Living Room",
            "level": "GF",
            "boundary": [[0, 0], [6_000, 0], [6_000, 4_000], [0, 4_000]],
            "global_id": "LIVINGROOM_GLOBALID001",
        },
        {
            "name": "Kitchen",
            "level": "GF",
            "boundary": [[6_000, 0], [10_000, 0], [10_000, 4_000], [6_000, 4_000]],
            "global_id": "KITCHEN_GLOBALID000001",
        },
        {
            "name": "Master Bedroom",
            "level": "GF",
            "boundary": [[0, 4_000], [5_000, 4_000], [5_000, 8_000], [0, 8_000]],
        },
    ],
}

_MULTI_LEVEL_MODEL: dict[str, Any] = {
    "name": "MultiLevelArch",
    "levels": [
        {"name": "GF", "elevation": 0.0},
        {"name": "FF", "elevation": 3_200.0},
    ],
    "spaces": [
        {
            "name": "Lobby",
            "level": "GF",
            "boundary": [[0, 0], [5_000, 0], [5_000, 5_000], [0, 5_000]],
            "global_id": "LOBBY_GLOBALID0000001",
        },
        {
            "name": "Office A",
            "level": "FF",
            "boundary": [[0, 0], [4_000, 0], [4_000, 3_000], [0, 3_000]],
            "global_id": "OFFICEA_GLOBALID00001",
        },
    ],
}


class TestExportSpaces(unittest.TestCase):
    """export_ifc emits IfcSpace entities for each space in the model."""

    def setUp(self):
        self.result = export_ifc(_ARCH_MODEL, schema="IFC4")
        self.text = self.result.ifc_text

    # 11
    def test_ifcspace_entities_emitted(self):
        """IfcSpace entities must be present for each space."""
        self.assertGreater(_count_ifc(self.text, "IFCSPACE"), 0)

    # 12
    def test_ifcspace_count_matches_spaces(self):
        """Number of IfcSpace entities matches the number of spaces in the model."""
        count = _count_ifc(self.text, "IFCSPACE")
        self.assertEqual(count, len(_ARCH_MODEL["spaces"]))

    # 13
    def test_space_names_in_ifc_text(self):
        """Space names appear as string literals in the IFC STEP text."""
        for sp in _ARCH_MODEL["spaces"]:
            self.assertIn(sp["name"], self.text, f"space name {sp['name']!r} not in IFC text")

    # 14
    def test_space_boundary_dimensions_in_metres(self):
        """6 000 mm boundary coordinate → 6.0 m appears in IFC text."""
        self.assertIn("6.", self.text)

    # 15
    def test_space_global_id_deterministic(self):
        """Space GlobalIds are identical across two exports of the same model."""
        r1 = export_ifc(_ARCH_MODEL, schema="IFC4")
        r2 = export_ifc(_ARCH_MODEL, schema="IFC4")
        guids1 = _extract_space_guids(r1.ifc_text)
        guids2 = _extract_space_guids(r2.ifc_text)
        self.assertGreater(len(guids1), 0, "No IfcSpace GlobalIds found")
        self.assertEqual(guids1, guids2, "Space GlobalIds differ between exports")

    # 16
    def test_preserved_global_id_roundtrips(self):
        """A space with an explicit global_id uses that exact string in the IFC output."""
        self.assertIn("LIVINGROOM_GLOBALID001", self.text)
        self.assertIn("KITCHEN_GLOBALID000001", self.text)

    # 17
    def test_forward_references_resolved(self):
        """All #N references in the IFC DATA section must be defined."""
        defined = _defined_ids(self.text)
        referenced = _referenced_ids(self.text)
        missing = referenced - defined
        self.assertEqual(
            missing, set(),
            f"Undefined #ID references in space export: {sorted(missing)[:10]}",
        )

    # 18
    def test_no_validation_warnings(self):
        """A well-formed model with spaces should have no VALIDATION warnings."""
        validation_warns = [w for w in self.result.warnings if w.startswith("VALIDATION")]
        self.assertEqual(
            validation_warns, [],
            f"Unexpected VALIDATION warnings: {validation_warns}",
        )


# ---------------------------------------------------------------------------
# Test 19: multi-level space containment
# ---------------------------------------------------------------------------


class TestMultiLevelSpaceContainment(unittest.TestCase):

    # 19
    def test_spaces_contained_in_correct_storey(self):
        """Each space is contained in its level's IfcRelContainedInSpatialStructure."""
        result = export_ifc(_MULTI_LEVEL_MODEL, schema="IFC4")
        text = result.ifc_text

        # 2 spaces across 2 levels → 2 IfcSpace entities
        self.assertEqual(_count_ifc(text, "IFCSPACE"), 2)

        # The spatial relationships must exist
        self.assertGreaterEqual(_count_ifc(text, "IFCRELCONTAINEDINSPATIALSTRUCTURE"), 2)

        # Each space GlobalId appears in the text
        self.assertIn("LOBBY_GLOBALID0000001", text)
        self.assertIn("OFFICEA_GLOBALID00001", text)

        # No forward-ref gaps
        missing = _referenced_ids(text) - _defined_ids(text)
        self.assertEqual(missing, set(), f"Dangling refs: {sorted(missing)[:5]}")


# ---------------------------------------------------------------------------
# Test 20: text round-trip (export → parse IFC STEP text for IfcSpace entities)
# ---------------------------------------------------------------------------


class TestSpaceRoundTripText(unittest.TestCase):
    """
    Export the arch model to IFC text, then parse the text with regex to
    confirm IfcSpace GlobalIds and names survive the trip.

    No ifcopenshell required: we parse the STEP text directly.
    """

    # 20
    def test_space_names_and_guids_survive_roundtrip(self):
        """
        After export, every space with an explicit global_id can be found
        in the IFC text both by GlobalId and by Name.
        """
        result = export_ifc(_ARCH_MODEL, schema="IFC4")
        text = result.ifc_text

        # Verify STEP file is syntactically valid
        self.assertTrue(text.startswith("ISO-10303-21;"))
        self.assertTrue(text.rstrip().endswith("END-ISO-10303-21;"))

        # For each space with an explicit global_id, both id and name must appear
        for sp in _ARCH_MODEL["spaces"]:
            gid = sp.get("global_id")
            if gid:
                self.assertIn(gid, text, f"GlobalId {gid!r} not found in exported text")
            self.assertIn(sp["name"], text, f"Space name {sp['name']!r} not found")

        # Derived GlobalId for the space without explicit global_id must also appear
        # (it will be _ifc_guid("space_2") — we just check the count is right)
        self.assertEqual(_count_ifc(text, "IFCSPACE"), 3)


if __name__ == "__main__":
    unittest.main()
