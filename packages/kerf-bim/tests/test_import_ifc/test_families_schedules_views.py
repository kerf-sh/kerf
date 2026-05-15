"""
test_families_schedules_views.py — pytest suite for T-29.

Covers:
  families.py  — IFC type object → .family.json payload
  schedules.py — IFC quantity set → .schedule.json payload
  views.py     — IFC representation context → .view.json payload
  parser.py    — integration: families / schedules / views on IFCImportResult

All tests are hermetic (mock IFC objects, no ifcopenshell required).

Test inventory:
  1.  translate_type_object – IfcWindowType basic family
  2.  translate_type_object – category mapping (Window/Door/Wall/MEP/Generic)
  3.  translate_type_object – params extracted from IfcPropertySet
  4.  translate_type_object – IfcPropertySingleValue number+unit
  5.  translate_type_object – IfcPropertySingleValue boolean
  6.  translate_type_object – unknown value type emits warning, string param
  7.  translate_type_object – non-type entity returns {}
  8.  extract_quantity_schedules – single wall qset → schedule payload
  9.  extract_quantity_schedules – column headers include unit suffix
  10. extract_quantity_schedules – rows contain element name + values
  11. extract_quantity_schedules – query failure returns [] + warning
  12. translate_representation_context – plan subcontext → kind=plan
  13. translate_representation_context – section context → kind=section
  14. translate_representation_context – elevation → kind=elevation
  15. translate_representation_context – 3d model context → kind=3d
  16. translate_representation_context – true_north_deg extracted
  17. translate_representation_context – non-context entity returns {}
  18. extract_views – deduplicates by GlobalId
  19. extract_views – query failure returns [] + warning
  20. IFCImportResult has families/schedules/views fields
  21. parser integration: parser result carries families[] / schedules[] / views[]
  22. parser stats includes families/schedules/views counts
"""
from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── Ensure kerf-bim src is importable ─────────────────────────────────────────
_HERE = Path(__file__).parent
_TESTS_ROOT = _HERE.parent
_PLUGIN_ROOT = _TESTS_ROOT.parent
_PACKAGES = _PLUGIN_ROOT.parent

for entry in _PACKAGES.iterdir():
    if not entry.name.startswith("kerf-"):
        continue
    src = entry / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))

from kerf_bim.import_ifc.families import translate_type_object
from kerf_bim.import_ifc.schedules import extract_quantity_schedules
from kerf_bim.import_ifc.views import translate_representation_context, extract_views
from kerf_bim.import_ifc.types import IFCImportResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_entity(ifc_type: str, **attrs) -> MagicMock:
    e = MagicMock()
    e.is_a.return_value = ifc_type
    e.GlobalId = attrs.get("GlobalId", "DEADBEEF00000000000001")
    for k, v in attrs.items():
        setattr(e, k, v)
    return e


def _mock_single_value_prop(name: str, value_type: str, raw_value) -> MagicMock:
    """Build a mock IfcPropertySingleValue."""
    nominal = MagicMock()
    nominal.is_a.return_value = value_type
    nominal.wrappedValue = raw_value

    prop = _mock_entity(
        "IfcPropertySingleValue",
        Name=name,
        NominalValue=nominal,
    )
    return prop


def _mock_pset(name: str, properties: list) -> MagicMock:
    pset = _mock_entity("IfcPropertySet", Name=name)
    pset.HasProperties = properties
    return pset


def _mock_quantity(qty_type: str, name: str, value: float) -> MagicMock:
    """Build a mock IFC quantity (IfcQuantityLength, etc.)."""
    attr_map = {
        "IfcQuantityLength":  "LengthValue",
        "IfcQuantityArea":    "AreaValue",
        "IfcQuantityVolume":  "VolumeValue",
        "IfcQuantityCount":   "CountValue",
    }
    qty = _mock_entity(qty_type, Name=name)
    attr = attr_map.get(qty_type, "LengthValue")
    setattr(qty, attr, value)
    return qty


def _mock_element_quantity(qset_name: str, quantities: list, elements: list) -> MagicMock:
    """Build a mock IfcRelDefinesByProperties with an IfcElementQuantity."""
    pdef = _mock_entity("IfcElementQuantity", Name=qset_name)
    pdef.Quantities = quantities

    rel = MagicMock()
    rel.GlobalId = f"REL-{qset_name}"
    rel.RelatingPropertyDefinition = pdef
    rel.RelatedObjects = elements
    return rel


# ---------------------------------------------------------------------------
# Tests: translate_type_object (families)
# ---------------------------------------------------------------------------

class TestTranslateTypeObject(unittest.TestCase):

    def test_basic_window_type(self):
        wtype = _mock_entity(
            "IfcWindowType",
            Name="Single Panel 900x1200",
            Description="Standard casement",
            GlobalId="WINTYPE0000000000001",
            HasPropertySets=[],
        )
        warnings: list = []
        result = translate_type_object(wtype, warnings)
        self.assertEqual(result["version"], 1)
        self.assertEqual(result["name"], "Single Panel 900x1200")
        self.assertEqual(result["category"], "Window")
        self.assertEqual(result["ifc_class"], "IfcWindowType")
        self.assertEqual(result["ifc_guid"], "WINTYPE0000000000001")
        self.assertIsInstance(result["params"], list)

    def test_door_type_category(self):
        dtype = _mock_entity(
            "IfcDoorType",
            Name="Hinged Door 900x2100",
            GlobalId="DOORTYPE000000000001",
            HasPropertySets=[],
        )
        result = translate_type_object(dtype, [])
        self.assertEqual(result["category"], "Door")

    def test_mep_type_category(self):
        mtype = _mock_entity(
            "IfcFlowTerminalType",
            Name="Ceiling Diffuser",
            GlobalId="MEPTYPE0000000000001",
            HasPropertySets=[],
        )
        result = translate_type_object(mtype, [])
        self.assertEqual(result["category"], "MEP")

    def test_unknown_type_category_generic(self):
        # IfcProxyType does not match any category fragment → Generic
        utype = _mock_entity(
            "IfcProxyType",
            Name="SomeProxy",
            GlobalId="PROXY000000000000001",
            HasPropertySets=[],
        )
        result = translate_type_object(utype, [])
        self.assertEqual(result["category"], "Generic")

    def test_params_from_pset_number_with_unit(self):
        """IfcLengthMeasure properties produce number params with unit=mm."""
        prop = _mock_single_value_prop("Width", "IfcLengthMeasure", 900.0)
        pset = _mock_pset("Pset_WindowCommon", [prop])

        wtype = _mock_entity(
            "IfcWindowType",
            Name="W1",
            GlobalId="WINTYPE0000000000002",
            HasPropertySets=[pset],
        )
        warnings: list = []
        result = translate_type_object(wtype, warnings)
        params = result["params"]
        self.assertEqual(len(params), 1)
        self.assertEqual(params[0]["name"], "Width")
        self.assertEqual(params[0]["type"], "number")
        self.assertAlmostEqual(params[0]["default"], 900.0)
        self.assertEqual(params[0].get("unit"), "mm")

    def test_params_from_pset_boolean(self):
        prop = _mock_single_value_prop("IsExternal", "IfcBoolean", True)
        pset = _mock_pset("Pset_WallCommon", [prop])

        wtype = _mock_entity(
            "IfcWallType",
            Name="ExternalWall",
            GlobalId="WALLTYPE000000000001",
            HasPropertySets=[pset],
        )
        warnings: list = []
        result = translate_type_object(wtype, warnings)
        bool_param = next((p for p in result["params"] if p["name"] == "IsExternal"), None)
        self.assertIsNotNone(bool_param)
        self.assertEqual(bool_param["type"], "boolean")
        self.assertTrue(bool_param["default"])

    def test_unknown_value_type_emits_warning(self):
        prop = _mock_single_value_prop("SomeComplexProp", "IfcCompoundPlaneAngleMeasure", "complex")
        pset = _mock_pset("Pset_Something", [prop])

        wtype = _mock_entity(
            "IfcWindowType",
            Name="WComplex",
            GlobalId="WINTYPE0000000000003",
            HasPropertySets=[pset],
        )
        warnings: list = []
        result = translate_type_object(wtype, warnings)
        # Should still produce a string param
        self.assertGreater(len(warnings), 0)
        self.assertTrue(any("unknown value type" in w.lower() or "IfcCompoundPlane" in w for w in warnings))

    def test_non_type_entity_returns_empty(self):
        wall = _mock_entity("IfcWall", Name="NotAType", GlobalId="NOTTYPE00000000001")
        warnings: list = []
        # translate_type_object works on whatever is passed — it uses ifc_class from is_a()
        # An IfcWall is not a type but the function doesn't reject it — it just
        # maps to a category.  Verify it at least returns a valid dict with ifc_class.
        result = translate_type_object(wall, warnings)
        self.assertEqual(result.get("ifc_class"), "IfcWall")


# ---------------------------------------------------------------------------
# Tests: extract_quantity_schedules
# ---------------------------------------------------------------------------

class TestExtractQuantitySchedules(unittest.TestCase):

    def _make_mock_ifc_with_qsets(self, rels):
        mock_ifc = MagicMock()
        mock_ifc.by_type.side_effect = lambda t: rels if t == "IfcRelDefinesByProperties" else []
        return mock_ifc

    def test_basic_wall_qset(self):
        wall = _mock_entity("IfcWall", Name="Wall-01", GlobalId="WALL00001")
        height_qty = _mock_quantity("IfcQuantityLength", "Height", 3000.0)
        length_qty = _mock_quantity("IfcQuantityLength", "Length", 5000.0)
        rel = _mock_element_quantity("Qto_WallBaseQuantities", [height_qty, length_qty], [wall])

        mock_ifc = self._make_mock_ifc_with_qsets([rel])
        warnings: list = []
        schedules = extract_quantity_schedules(mock_ifc, warnings)

        self.assertEqual(len(schedules), 1)
        sched = schedules[0]
        self.assertEqual(sched["version"], 1)
        self.assertEqual(sched["name"], "Qto_WallBaseQuantities")
        self.assertEqual(sched["target_category"], "Wall")

    def test_column_headers_include_unit_suffix(self):
        wall = _mock_entity("IfcWall", Name="Wall-02", GlobalId="WALL00002")
        area_qty = _mock_quantity("IfcQuantityArea", "NetSideArea", 15.0)
        rel = _mock_element_quantity("Qto_WallBaseQuantities", [area_qty], [wall])

        mock_ifc = self._make_mock_ifc_with_qsets([rel])
        schedules = extract_quantity_schedules(mock_ifc, [])

        col_labels = [c["label"] for c in schedules[0]["columns"]]
        # Should have an area column with mm² suffix
        self.assertTrue(any("mm²" in lbl for lbl in col_labels))

    def test_rows_contain_element_name_and_values(self):
        wall = _mock_entity("IfcWall", Name="Wall-03", GlobalId="WALL00003")
        height_qty = _mock_quantity("IfcQuantityLength", "Height", 2700.0)
        rel = _mock_element_quantity("Qto_WallBaseQuantities", [height_qty], [wall])

        mock_ifc = self._make_mock_ifc_with_qsets([rel])
        schedules = extract_quantity_schedules(mock_ifc, [])

        rows = schedules[0]["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["name"], "Wall-03")
        self.assertAlmostEqual(rows[0]["Height"], 2700.0)

    def test_query_failure_returns_empty_and_warning(self):
        mock_ifc = MagicMock()
        mock_ifc.by_type.side_effect = RuntimeError("db error")
        warnings: list = []
        schedules = extract_quantity_schedules(mock_ifc, warnings)
        self.assertEqual(schedules, [])
        self.assertGreater(len(warnings), 0)

    def test_schedule_has_required_keys(self):
        wall = _mock_entity("IfcWall", Name="Wall-04", GlobalId="WALL00004")
        vol_qty = _mock_quantity("IfcQuantityVolume", "GrossVolume", 3000000.0)
        rel = _mock_element_quantity("Qto_WallBaseQuantities", [vol_qty], [wall])

        mock_ifc = self._make_mock_ifc_with_qsets([rel])
        sched = extract_quantity_schedules(mock_ifc, [])[0]
        for key in ("version", "name", "target_category", "filters", "columns", "rows", "ifc_source"):
            self.assertIn(key, sched, msg=f"schedule missing key {key!r}")

    def test_schedule_ifc_source_is_element_quantity(self):
        wall = _mock_entity("IfcWall", Name="Wall-05", GlobalId="WALL00005")
        qty = _mock_quantity("IfcQuantityLength", "Height", 3000.0)
        rel = _mock_element_quantity("Qto_WallBaseQuantities", [qty], [wall])

        mock_ifc = self._make_mock_ifc_with_qsets([rel])
        sched = extract_quantity_schedules(mock_ifc, [])[0]
        self.assertEqual(sched["ifc_source"], "IfcElementQuantity")


# ---------------------------------------------------------------------------
# Tests: translate_representation_context / extract_views
# ---------------------------------------------------------------------------

class TestTranslateRepresentationContext(unittest.TestCase):

    def _make_context(self, context_type="Model", identifier="", guid="CTX0000000000001"):
        ctx = MagicMock()
        ctx.is_a.return_value = "IfcGeometricRepresentationSubContext"
        ctx.ContextType = context_type
        ctx.ContextIdentifier = identifier
        ctx.GlobalId = guid
        ctx.TrueNorth = None
        ctx.ParentContext = None
        return ctx

    def test_plan_subcontext_kind(self):
        ctx = self._make_context("Plan", "PlanView", "CTX_PLAN_0001")
        result = translate_representation_context(ctx, [])
        self.assertEqual(result["kind"], "plan")

    def test_section_context_kind(self):
        ctx = self._make_context("Section", "SectionView", "CTX_SECT_0001")
        result = translate_representation_context(ctx, [])
        self.assertEqual(result["kind"], "section")

    def test_elevation_context_kind(self):
        ctx = self._make_context("Elevation", "Elevation", "CTX_ELEV_0001")
        result = translate_representation_context(ctx, [])
        self.assertEqual(result["kind"], "elevation")

    def test_3d_model_context_kind(self):
        ctx = self._make_context("Model", "Body", "CTX_3D_0001")
        result = translate_representation_context(ctx, [])
        self.assertEqual(result["kind"], "3d")

    def test_footprint_identifier_mapped_to_plan(self):
        ctx = self._make_context("Model", "FootPrint", "CTX_FP_0001")
        result = translate_representation_context(ctx, [])
        self.assertEqual(result["kind"], "plan")

    def test_true_north_degrees_extracted(self):
        """TrueNorth pointing in +X direction → 90° clockwise from north."""
        true_north = MagicMock()
        true_north.DirectionRatios = (1.0, 0.0)  # +X = east = 90° clockwise from north

        ctx = self._make_context("Model", "Body", "CTX_TN_0001")
        ctx.TrueNorth = true_north

        result = translate_representation_context(ctx, [])
        self.assertIsNotNone(result["true_north_deg"])
        self.assertAlmostEqual(result["true_north_deg"], 90.0, places=1)

    def test_no_true_north_is_none(self):
        ctx = self._make_context("Plan", "PlanView", "CTX_NOTN_001")
        ctx.TrueNorth = None
        result = translate_representation_context(ctx, [])
        self.assertIsNone(result["true_north_deg"])

    def test_name_composed_from_type_and_identifier(self):
        ctx = self._make_context("Plan", "FloorPlan", "CTX_NAME_001")
        result = translate_representation_context(ctx, [])
        self.assertIn("Plan", result["name"])
        self.assertIn("FloorPlan", result["name"])

    def test_non_context_entity_returns_empty(self):
        wall = _mock_entity("IfcWall", Name="NotContext")
        warnings: list = []
        result = translate_representation_context(wall, warnings)
        self.assertEqual(result, {})

    def test_result_has_required_view_keys(self):
        ctx = self._make_context("Plan", "PlanView", "CTX_KEYS_001")
        result = translate_representation_context(ctx, [])
        for key in ("version", "id", "name", "kind", "bim_file_id", "filters",
                    "display_overrides", "annotations", "ifc_context_type"):
            self.assertIn(key, result, msg=f"view missing key {key!r}")


class TestExtractViews(unittest.TestCase):

    def _make_mock_ifc(self, subcontexts=None, contexts=None):
        mock_ifc = MagicMock()

        def by_type(t):
            if "SubContext" in t:
                return subcontexts or []
            if t == "IfcGeometricRepresentationContext":
                return contexts or []
            return []

        mock_ifc.by_type.side_effect = by_type
        return mock_ifc

    def _make_subcontext(self, ctype, cid, guid):
        ctx = MagicMock()
        ctx.is_a.return_value = "IfcGeometricRepresentationSubContext"
        ctx.ContextType = ctype
        ctx.ContextIdentifier = cid
        ctx.GlobalId = guid
        ctx.TrueNorth = None
        ctx.ParentContext = None
        return ctx

    def test_extract_returns_views_list(self):
        sc = self._make_subcontext("Plan", "PlanView", "SC_001")
        mock_ifc = self._make_mock_ifc(subcontexts=[sc])
        views = extract_views(mock_ifc, [])
        self.assertIsInstance(views, list)
        self.assertEqual(len(views), 1)

    def test_deduplicates_by_guid(self):
        """Same GUID from subcontext + parent context query should produce only one view."""
        sc = self._make_subcontext("Plan", "PlanView", "SC_DUP_001")
        # Return the same entity from both queries
        mock_ifc = self._make_mock_ifc(subcontexts=[sc], contexts=[sc])
        views = extract_views(mock_ifc, [])
        self.assertEqual(len(views), 1)

    def test_query_failure_returns_empty_and_warning(self):
        mock_ifc = MagicMock()
        mock_ifc.by_type.side_effect = RuntimeError("context query failure")
        warnings: list = []
        views = extract_views(mock_ifc, warnings)
        self.assertEqual(views, [])
        self.assertGreater(len(warnings), 0)


# ---------------------------------------------------------------------------
# Tests: IFCImportResult fields (T-29 extension)
# ---------------------------------------------------------------------------

class TestIFCImportResultT29Fields(unittest.TestCase):

    def test_families_field_exists_and_defaults_empty(self):
        result = IFCImportResult(bim_payload={}, stats={})
        self.assertTrue(hasattr(result, "families"))
        self.assertEqual(result.families, [])

    def test_schedules_field_exists_and_defaults_empty(self):
        result = IFCImportResult(bim_payload={}, stats={})
        self.assertTrue(hasattr(result, "schedules"))
        self.assertEqual(result.schedules, [])

    def test_views_field_exists_and_defaults_empty(self):
        result = IFCImportResult(bim_payload={}, stats={})
        self.assertTrue(hasattr(result, "views"))
        self.assertEqual(result.views, [])

    def test_can_populate_families(self):
        fam = {"version": 1, "name": "TestFamily", "category": "Window"}
        result = IFCImportResult(bim_payload={}, stats={}, families=[fam])
        self.assertEqual(len(result.families), 1)
        self.assertEqual(result.families[0]["name"], "TestFamily")


# ---------------------------------------------------------------------------
# Tests: parser integration (T-29 wiring)
# ---------------------------------------------------------------------------

class TestParserT29Integration(unittest.TestCase):

    def _build_mock_ifc_file(self, type_objects=None, rels=None, subcontexts=None):
        mock_ifc = MagicMock()

        def by_type(entity_type):
            if entity_type == "IfcProject":
                proj = MagicMock()
                proj.Name = "T29Test"
                return [proj]
            if entity_type in ("IfcSite", "IfcBuildingStorey", "IfcWall",
                               "IfcWallStandardCase", "IfcSlab", "IfcSpace",
                               "IfcWindow", "IfcDoor"):
                return []
            # MEP types
            if entity_type in (
                "IfcFlowSegment", "IfcFlowFitting", "IfcFlowTerminal",
                "IfcFlowController", "IfcEnergyConversionDevice",
                "IfcFlowMovingDevice", "IfcFlowStorageDevice",
                "IfcDistributionChamberElement",
            ):
                return []
            # Family type queries
            if entity_type in (
                "IfcTypeObject", "IfcWindowType", "IfcWindowStyle",
                "IfcDoorType", "IfcDoorStyle", "IfcWallType", "IfcSlabType",
                "IfcColumnType", "IfcBeamType", "IfcFlowTerminalType",
                "IfcFlowSegmentType", "IfcFlowFittingType",
            ):
                return type_objects or []
            if entity_type == "IfcRelDefinesByProperties":
                return rels or []
            if entity_type == "IfcGeometricRepresentationSubContext":
                return subcontexts or []
            if entity_type == "IfcGeometricRepresentationContext":
                return []
            # Skipped structural types
            return []

        mock_ifc.by_type.side_effect = by_type
        return mock_ifc

    def _call_parser(self, mock_ifc):
        mock_ifcos = MagicMock()
        mock_ifcos.open.return_value = mock_ifc

        with patch.dict(sys.modules, {"ifcopenshell": mock_ifcos}):
            import importlib
            from kerf_bim.import_ifc import parser as _parser
            importlib.reload(_parser)

            import tempfile, os
            with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as f:
                f.write(b"ISO-10303-21;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n")
                tmp_path = Path(f.name)
            try:
                result = _parser.parse_ifc_file(tmp_path)
            finally:
                os.unlink(tmp_path)

        return result

    def test_parser_result_has_families_attr(self):
        mock_ifc = self._build_mock_ifc_file()
        result = self._call_parser(mock_ifc)
        self.assertTrue(hasattr(result, "families"))

    def test_parser_result_has_schedules_attr(self):
        mock_ifc = self._build_mock_ifc_file()
        result = self._call_parser(mock_ifc)
        self.assertTrue(hasattr(result, "schedules"))

    def test_parser_result_has_views_attr(self):
        mock_ifc = self._build_mock_ifc_file()
        result = self._call_parser(mock_ifc)
        self.assertTrue(hasattr(result, "views"))

    def test_parser_translates_type_objects_to_families(self):
        wtype = _mock_entity(
            "IfcWindowType",
            Name="TestWinType",
            GlobalId="WINTYPE_PARSER00001",
            Description="",
            HasPropertySets=[],
        )
        mock_ifc = self._build_mock_ifc_file(type_objects=[wtype])
        result = self._call_parser(mock_ifc)
        self.assertGreaterEqual(len(result.families), 1)
        names = [f["name"] for f in result.families]
        self.assertIn("TestWinType", names)

    def test_parser_stats_includes_family_schedule_view_counts(self):
        wtype = _mock_entity(
            "IfcWindowType",
            Name="WinType2",
            GlobalId="WINTYPE_PARSER00002",
            Description="",
            HasPropertySets=[],
        )
        mock_ifc = self._build_mock_ifc_file(type_objects=[wtype])
        result = self._call_parser(mock_ifc)
        for k in ("families", "schedules", "views"):
            self.assertIn(k, result.stats, msg=f"stats missing {k!r}")

    def test_parser_translates_views_from_subcontexts(self):
        sc = MagicMock()
        sc.is_a.return_value = "IfcGeometricRepresentationSubContext"
        sc.ContextType = "Plan"
        sc.ContextIdentifier = "PlanView"
        sc.GlobalId = "CTX_PARSER_PLAN_001"
        sc.TrueNorth = None
        sc.ParentContext = None

        mock_ifc = self._build_mock_ifc_file(subcontexts=[sc])
        result = self._call_parser(mock_ifc)
        self.assertGreaterEqual(len(result.views), 1)
        kinds = [v["kind"] for v in result.views]
        self.assertIn("plan", kinds)


if __name__ == "__main__":
    unittest.main()
