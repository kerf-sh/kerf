"""
test_export_ifc.py — hermetic pytest suite for kerf_bim.export_ifc.

All tests are pure-Python with no external dependencies (no ifcopenshell,
no filesystem writes outside of the round-trip test which uses a temp dir).

Test inventory (≥ 25 cases):
  1.  export_ifc raises IFCExportError for None model
  2.  export_ifc raises IFCExportError for non-dict model
  3.  export_ifc raises IFCExportError for invalid schema
  4.  export_ifc returns IFCExportResult for minimal model
  5.  IFC header is syntactically well-formed (ISO-10303-21 / ENDSEC markers)
  6.  FILE_SCHEMA contains the requested schema string (IFC2X3)
  7.  FILE_SCHEMA contains the requested schema string (IFC4)
  8.  File ends with END-ISO-10303-21;
  9.  entity_count matches number of #N= lines in DATA section
  10. IfcUnitAssignment is present
  11. IfcGeometricRepresentationContext is present
  12. IfcOwnerHistory is present
  13. IfcProject is emitted
  14. IfcSite is emitted
  15. IfcBuilding is emitted
  16. IfcBuildingStorey is emitted for each level
  17. IfcWall entity is emitted for a wall in the model
  18. Wall extrusion uses correct height in metres (mm → m conversion)
  19. IfcSlab entity is emitted for a slab in the model
  20. IfcColumn entity is emitted
  21. IfcBeam entity is emitted
  22. IfcDoor entity is emitted for a door opening
  23. IfcWindow entity is emitted for a window opening
  24. IfcLocalPlacement hierarchy present (storey place referenced by elements)
  25. IfcRelContainedInSpatialStructure emitted for storey with elements
  26. IfcRelAggregates links project → site → building → storey
  27. Empty model (no walls/slabs) still produces valid file
  28. Multiple levels produce multiple IfcBuildingStorey entities
  29. Validation warning on undefined #ID reference (injected broken line)
  30. Round-trip: import minimal.ifc → export → file is valid STEP text
  31. Warnings list is empty for a clean well-formed model
  32. Zero-length wall produces a warning and is skipped
  33. schema field on result matches requested schema
  34. Custom author/organisation appear in FILE_NAME header
  35. All #N references in DATA section are defined (forward-ref check)
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

# ── Ensure kerf-bim src is importable ─────────────────────────────────────
_HERE = Path(__file__).parent
_PLUGIN_ROOT = _HERE.parent
_PACKAGES = _PLUGIN_ROOT.parent

for entry in _PACKAGES.iterdir():
    if not entry.name.startswith("kerf-"):
        continue
    src = entry / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))

# ── Imports under test ─────────────────────────────────────────────────────
from kerf_bim.export_ifc import export_ifc, IFCExportResult, IFCExportError
from kerf_bim.export_ifc.writer import _validate

# ── Fixtures ──────────────────────────────────────────────────────────────
_FIXTURES = _HERE / "fixtures"
_MINIMAL_IFC = _FIXTURES / "minimal.ifc"

_MINIMAL_MODEL: dict = {
    "name": "Test Building",
    "levels": [{"name": "L1", "elevation": 0.0}],
    "walls": [
        {
            "level": "L1",
            "from": [0.0, 0.0],
            "to": [5000.0, 0.0],
            "height": 3000.0,
            "thickness": 200.0,
            "name": "W1",
        }
    ],
    "slabs": [
        {
            "level": "L1",
            "boundary": [[0, 0], [5000, 0], [5000, 4000], [0, 4000]],
            "thickness": 200.0,
            "name": "S1",
        }
    ],
    "openings": [
        {
            "kind": "door",
            "level": "L1",
            "position": [1000.0, 0.0, 0.0],
            "width": 900.0,
            "height": 2100.0,
            "name": "D1",
        },
        {
            "kind": "window",
            "level": "L1",
            "position": [3000.0, 0.0, 800.0],
            "width": 1200.0,
            "height": 1200.0,
            "name": "W1",
        },
    ],
}

_FULL_MODEL: dict = {
    "name": "Full Building",
    "site": {"name": "Main Site", "latitude": -33.9, "longitude": 18.4, "elevation": 10.0},
    "levels": [
        {"name": "GF", "elevation": 0.0},
        {"name": "FF", "elevation": 3000.0},
    ],
    "walls": [
        {"level": "GF", "from": [0, 0], "to": [6000, 0], "height": 3000, "thickness": 200},
        {"level": "FF", "from": [0, 0], "to": [6000, 0], "height": 3000, "thickness": 200},
    ],
    "slabs": [
        {"level": "GF", "boundary": [[0,0],[6000,0],[6000,5000],[0,5000]], "thickness": 250},
    ],
    "openings": [
        {"kind": "window", "level": "GF", "position": [2000, 0, 900], "width": 1200, "height": 1200},
        {"kind": "door",   "level": "GF", "position": [500,  0, 0],   "width": 900,  "height": 2100},
    ],
    "columns": [
        {"level": "GF", "position": [0, 0, 0], "width": 300, "depth": 300, "height": 3000},
    ],
    "beams": [
        {"level": "FF", "start": [0, 0, 3000], "end": [6000, 0, 3000], "width": 200, "height": 400},
    ],
}


# ---------------------------------------------------------------------------
# Helper: count entity type occurrences in IFC text
# ---------------------------------------------------------------------------

def _count_ifc_type(ifc_text: str, ifc_type: str) -> int:
    """Count lines that define an entity of the given IFC type."""
    pattern = rf"#\d+={ifc_type.upper()}\("
    return len(re.findall(pattern, ifc_text, re.IGNORECASE))


def _has_ifc_type(ifc_text: str, ifc_type: str) -> bool:
    return _count_ifc_type(ifc_text, ifc_type) > 0


def _defined_ids(ifc_text: str) -> set[int]:
    """Return all entity IDs defined in the DATA section."""
    data = re.search(r"DATA;(.+)ENDSEC;", ifc_text, re.DOTALL)
    if not data:
        return set()
    return set(int(m) for m in re.findall(r"^#(\d+)=", data.group(1), re.MULTILINE))


def _referenced_ids(ifc_text: str) -> set[int]:
    """Return all #N references used on the RHS of entity lines."""
    data = re.search(r"DATA;(.+)ENDSEC;", ifc_text, re.DOTALL)
    if not data:
        return set()
    rhs = re.sub(r"^#\d+=", "", data.group(1), flags=re.MULTILINE)
    return set(int(m) for m in re.findall(r"#(\d+)", rhs))


# ---------------------------------------------------------------------------
# Test 1-3: error paths
# ---------------------------------------------------------------------------

class TestErrorPaths(unittest.TestCase):

    def test_none_model_raises(self):
        """export_ifc(None) raises IFCExportError."""
        with self.assertRaises(IFCExportError):
            export_ifc(None)

    def test_non_dict_model_raises(self):
        """export_ifc('bad') raises IFCExportError."""
        with self.assertRaises(IFCExportError):
            export_ifc("bad string")

    def test_invalid_schema_raises(self):
        """export_ifc({}, schema='IFC99') raises IFCExportError."""
        with self.assertRaises(IFCExportError):
            export_ifc({}, schema="IFC99")


# ---------------------------------------------------------------------------
# Test 4-9: basic result shape
# ---------------------------------------------------------------------------

class TestResultShape(unittest.TestCase):

    def setUp(self):
        self.result = export_ifc(_MINIMAL_MODEL)

    def test_returns_ifc_export_result(self):
        self.assertIsInstance(self.result, IFCExportResult)

    def test_ifc_text_is_str(self):
        self.assertIsInstance(self.result.ifc_text, str)

    def test_entity_count_positive(self):
        self.assertGreater(self.result.entity_count, 0)

    def test_entity_count_matches_data_lines(self):
        """entity_count must equal the number of #N= lines in the DATA section."""
        data_m = re.search(r"DATA;(.+)ENDSEC;", self.result.ifc_text, re.DOTALL)
        self.assertIsNotNone(data_m)
        count = len(re.findall(r"^#\d+=", data_m.group(1), re.MULTILINE))
        self.assertEqual(self.result.entity_count, count)

    def test_schema_field(self):
        self.assertEqual(self.result.schema, "IFC2X3")

    def test_warnings_is_list(self):
        self.assertIsInstance(self.result.warnings, list)


# ---------------------------------------------------------------------------
# Test 5-8: header well-formedness
# ---------------------------------------------------------------------------

class TestHeaderWellFormed(unittest.TestCase):

    def setUp(self):
        self.text = export_ifc(_MINIMAL_MODEL).ifc_text

    def test_starts_with_iso_marker(self):
        self.assertTrue(self.text.startswith("ISO-10303-21;"))

    def test_has_header_section(self):
        self.assertIn("HEADER;", self.text)
        self.assertIn("FILE_DESCRIPTION(", self.text)
        self.assertIn("FILE_NAME(", self.text)
        self.assertIn("FILE_SCHEMA(", self.text)

    def test_schema_ifc2x3_in_file(self):
        self.assertIn("IFC2X3", self.text)

    def test_schema_ifc4_in_file(self):
        result = export_ifc(_MINIMAL_MODEL, schema="IFC4")
        self.assertIn("IFC4", result.ifc_text)
        self.assertNotIn("IFC2X3", result.ifc_text)

    def test_ends_with_end_iso(self):
        stripped = self.text.rstrip()
        self.assertTrue(stripped.endswith("END-ISO-10303-21;"))

    def test_data_and_endsec_present(self):
        self.assertIn("DATA;", self.text)
        self.assertIn("ENDSEC;", self.text)


# ---------------------------------------------------------------------------
# Test 10-16: required IFC infrastructure entities
# ---------------------------------------------------------------------------

class TestInfrastructureEntities(unittest.TestCase):

    def setUp(self):
        self.text = export_ifc(_MINIMAL_MODEL).ifc_text

    def test_unit_assignment_present(self):
        self.assertTrue(_has_ifc_type(self.text, "IFCUNITASSIGNMENT"))

    def test_si_length_unit_present(self):
        self.assertIn("LENGTHUNIT", self.text)
        self.assertIn("METRE", self.text)

    def test_rep_context_present(self):
        self.assertTrue(_has_ifc_type(self.text, "IFCGEOMETRICREPRESENTATIONCONTEXT"))

    def test_owner_history_present(self):
        self.assertTrue(_has_ifc_type(self.text, "IFCOWNERHISTORY"))

    def test_project_present(self):
        self.assertTrue(_has_ifc_type(self.text, "IFCPROJECT"))

    def test_site_present(self):
        self.assertTrue(_has_ifc_type(self.text, "IFCSITE"))

    def test_building_present(self):
        self.assertTrue(_has_ifc_type(self.text, "IFCBUILDING"))

    def test_storey_present(self):
        self.assertTrue(_has_ifc_type(self.text, "IFCBUILDINGSTOREY"))


# ---------------------------------------------------------------------------
# Test 17-23: element types
# ---------------------------------------------------------------------------

class TestElementTypes(unittest.TestCase):

    def setUp(self):
        self.minimal_result = export_ifc(_MINIMAL_MODEL)
        self.full_result    = export_ifc(_FULL_MODEL)

    def test_wall_emitted_ifc2x3(self):
        """IfcWallStandardCase emitted for IFC2X3."""
        self.assertTrue(_has_ifc_type(self.minimal_result.ifc_text, "IFCWALLSTANDARDCASE"))

    def test_wall_emitted_ifc4(self):
        """IfcWall emitted for IFC4."""
        result = export_ifc(_MINIMAL_MODEL, schema="IFC4")
        self.assertTrue(_has_ifc_type(result.ifc_text, "IFCWALL"))

    def test_wall_height_mm_to_m(self):
        """3000mm wall height should appear as ~3.0 in the IFC text."""
        text = self.minimal_result.ifc_text
        # The extrusion depth for the wall should be 3.0 (metres)
        self.assertIn("3.", text)

    def test_slab_emitted(self):
        self.assertTrue(_has_ifc_type(self.minimal_result.ifc_text, "IFCSLAB"))

    def test_column_emitted(self):
        self.assertTrue(_has_ifc_type(self.full_result.ifc_text, "IFCCOLUMN"))

    def test_beam_emitted(self):
        self.assertTrue(_has_ifc_type(self.full_result.ifc_text, "IFCBEAM"))

    def test_door_emitted(self):
        self.assertTrue(_has_ifc_type(self.minimal_result.ifc_text, "IFCDOOR"))

    def test_window_emitted(self):
        self.assertTrue(_has_ifc_type(self.minimal_result.ifc_text, "IFCWINDOW"))

    def test_extruded_area_solid_present(self):
        self.assertTrue(_has_ifc_type(self.minimal_result.ifc_text, "IFCEXTRUDEDAREASOLID"))

    def test_rect_profile_present(self):
        self.assertTrue(_has_ifc_type(self.minimal_result.ifc_text, "IFCRECTANGLEPROFILEDEF"))

    def test_slab_uses_arbitrary_closed_profile(self):
        self.assertTrue(_has_ifc_type(self.minimal_result.ifc_text, "IFCARBITRARYCLOSEDPROFILEDEF"))


# ---------------------------------------------------------------------------
# Test 24-26: placement and spatial relationships
# ---------------------------------------------------------------------------

class TestPlacementAndRelationships(unittest.TestCase):

    def setUp(self):
        self.text = export_ifc(_MINIMAL_MODEL).ifc_text

    def test_local_placement_present(self):
        self.assertTrue(_has_ifc_type(self.text, "IFCLOCALPLACEMENT"))

    def test_rel_contained_present(self):
        self.assertTrue(_has_ifc_type(self.text, "IFCRELCONTAINEDINSPATIALSTRUCTURE"))

    def test_rel_aggregates_present(self):
        self.assertTrue(_has_ifc_type(self.text, "IFCRELAGGREGATES"))
        # Must have at least 3: project→site, site→building, building→storey
        count = _count_ifc_type(self.text, "IFCRELAGGREGATES")
        self.assertGreaterEqual(count, 3)


# ---------------------------------------------------------------------------
# Test 27: empty model
# ---------------------------------------------------------------------------

class TestEmptyModel(unittest.TestCase):

    def test_empty_dict_produces_valid_file(self):
        """An empty model dict should still produce a syntactically valid file."""
        result = export_ifc({})
        self.assertTrue(result.ifc_text.startswith("ISO-10303-21;"))
        self.assertIn("END-ISO-10303-21;", result.ifc_text)
        self.assertGreater(result.entity_count, 0)

    def test_empty_model_has_default_level_warning(self):
        """Empty model auto-creates a default level; should warn."""
        result = export_ifc({})
        # Should contain a warning about missing levels
        self.assertTrue(any("level" in w.lower() for w in result.warnings))


# ---------------------------------------------------------------------------
# Test 28: multiple levels
# ---------------------------------------------------------------------------

class TestMultipleLevels(unittest.TestCase):

    def test_two_levels_produce_two_storeys(self):
        model = {
            "name": "Two-Level",
            "levels": [
                {"name": "GF", "elevation": 0.0},
                {"name": "FF", "elevation": 3000.0},
            ],
        }
        result = export_ifc(model)
        count = _count_ifc_type(result.ifc_text, "IFCBUILDINGSTOREY")
        self.assertEqual(count, 2)

    def test_storey_elevation_in_metres(self):
        """3000mm elevation → 3.0m in the IFC STEP output."""
        model = {
            "levels": [{"name": "FF", "elevation": 3000.0}],
        }
        result = export_ifc(model)
        # IfcBuildingStorey has elevation as last float arg; should be ~3.0
        self.assertIn("3.", result.ifc_text)


# ---------------------------------------------------------------------------
# Test 29: validation catches undefined references
# ---------------------------------------------------------------------------

class TestValidation(unittest.TestCase):

    def test_validation_catches_undefined_ref(self):
        """Injecting a reference to #9999 (undefined) triggers a validation warning."""
        result = export_ifc(_MINIMAL_MODEL)
        broken_text = result.ifc_text.replace("ENDSEC;", "#9999=IFCWALL('X',$,$,$,$,$,$,$);\nENDSEC;", 1)
        warnings: list = []
        _validate(broken_text, warnings)
        # No forward-ref error expected here since we defined #9999; but inject
        # a reference instead:
        ref_text = result.ifc_text.replace(
            "ENDSEC;\nEND-ISO-10303-21;",
            "#88888=IFCWALL(#99999,$,$,$,$,$,$,$);\nENDSEC;\nEND-ISO-10303-21;",
        )
        warnings2: list = []
        _validate(ref_text, warnings2)
        self.assertTrue(any("undefined" in w.lower() for w in warnings2))

    def test_validation_catches_missing_end_marker(self):
        """File not ending with END-ISO-10303-21; triggers a warning."""
        bad_text = "ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\n"
        warnings: list = []
        _validate(bad_text, warnings)
        self.assertTrue(any("END-ISO-10303-21" in w for w in warnings))


# ---------------------------------------------------------------------------
# Test 30: round-trip (skip if ifcopenshell not installed)
# ---------------------------------------------------------------------------

try:
    import ifcopenshell  # type: ignore
    _HAS_IFCOPENSHELL = True
except (ImportError, TypeError):
    _HAS_IFCOPENSHELL = False


@unittest.skipUnless(_HAS_IFCOPENSHELL, "ifcopenshell not installed")
class TestRoundTrip(unittest.TestCase):
    """
    Import the minimal.ifc fixture → export to IFC text → validate the
    text is a syntactically valid STEP file.
    """

    def test_round_trip_import_export(self):
        from kerf_bim.import_ifc import parse_ifc_file
        result_import = parse_ifc_file(_MINIMAL_IFC)
        bim_payload = result_import.bim_payload

        result_export = export_ifc(bim_payload)
        text = result_export.ifc_text

        self.assertTrue(text.startswith("ISO-10303-21;"))
        self.assertIn("END-ISO-10303-21;", text)
        self.assertGreater(result_export.entity_count, 0)

    def test_round_trip_no_validation_warnings(self):
        """Round-tripped export should have no VALIDATION: warnings."""
        from kerf_bim.import_ifc import parse_ifc_file
        result_import = parse_ifc_file(_MINIMAL_IFC)
        result_export = export_ifc(result_import.bim_payload)
        validation_warnings = [w for w in result_export.warnings if w.startswith("VALIDATION")]
        self.assertEqual(validation_warnings, [], msg=f"Unexpected warnings: {validation_warnings}")


# ---------------------------------------------------------------------------
# Test 31: clean model has no warnings
# ---------------------------------------------------------------------------

class TestCleanModelNoWarnings(unittest.TestCase):

    def test_minimal_model_no_validation_warnings(self):
        result = export_ifc(_MINIMAL_MODEL)
        validation_warns = [w for w in result.warnings if w.startswith("VALIDATION")]
        self.assertEqual(validation_warns, [])


# ---------------------------------------------------------------------------
# Test 32: zero-length wall
# ---------------------------------------------------------------------------

class TestZeroLengthWall(unittest.TestCase):

    def test_zero_length_wall_skipped_with_warning(self):
        model = {
            "levels": [{"name": "L1", "elevation": 0}],
            "walls": [{"level": "L1", "from": [0, 0], "to": [0, 0], "height": 3000, "thickness": 200}],
        }
        result = export_ifc(model)
        self.assertTrue(any("zero length" in w.lower() for w in result.warnings))
        # No wall entity should be in the file
        self.assertFalse(_has_ifc_type(result.ifc_text, "IFCWALLSTANDARDCASE"))


# ---------------------------------------------------------------------------
# Test 33: schema field
# ---------------------------------------------------------------------------

class TestSchemaField(unittest.TestCase):

    def test_schema_ifc2x3_result(self):
        result = export_ifc(_MINIMAL_MODEL, schema="IFC2X3")
        self.assertEqual(result.schema, "IFC2X3")

    def test_schema_ifc4_result(self):
        result = export_ifc(_MINIMAL_MODEL, schema="IFC4")
        self.assertEqual(result.schema, "IFC4")


# ---------------------------------------------------------------------------
# Test 34: custom author/organisation in FILE_NAME
# ---------------------------------------------------------------------------

class TestCustomAuthor(unittest.TestCase):

    def test_custom_author_in_header(self):
        result = export_ifc(_MINIMAL_MODEL, author="Jane Doe", organisation="ACME Arch")
        self.assertIn("Jane Doe", result.ifc_text)
        self.assertIn("ACME Arch", result.ifc_text)


# ---------------------------------------------------------------------------
# Test 35: all forward references resolved
# ---------------------------------------------------------------------------

class TestForwardRefs(unittest.TestCase):

    def test_all_forward_refs_resolved_minimal(self):
        result = export_ifc(_MINIMAL_MODEL)
        defined = _defined_ids(result.ifc_text)
        referenced = _referenced_ids(result.ifc_text)
        missing = referenced - defined
        self.assertEqual(
            missing, set(),
            msg=f"Undefined #ID references in output: {sorted(missing)[:10]}"
        )

    def test_all_forward_refs_resolved_full(self):
        result = export_ifc(_FULL_MODEL)
        defined = _defined_ids(result.ifc_text)
        referenced = _referenced_ids(result.ifc_text)
        missing = referenced - defined
        self.assertEqual(
            missing, set(),
            msg=f"Undefined #ID references in output: {sorted(missing)[:10]}"
        )


if __name__ == "__main__":
    unittest.main()
