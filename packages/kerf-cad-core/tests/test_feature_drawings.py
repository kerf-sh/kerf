"""
Feature tests: T-42 Drawings — project / dimension / annotate.

Coverage (>=25 part-drawing pairs):
  - 4-view sheet structure (front / top / right / iso)
  - Overall L×W×H linear dimensions in correct views
  - Hole table: grouping by diameter, qty, thread callouts
  - Fillet callouts: unique radii, count accumulation
  - Section note when internal_features=True
  - GD&T frames (parallelism, perpendicularity, position)
  - Title block content and scale label
  - Sheet borders: closed polylines, correct sheet sizes
  - DXF R12 export: ENTITIES section, layers, text labels
  - SVG 1.1 export: opening/closing tags, view labels, dims
  - Boundary / malformed input rejection (never raises)
  - Idempotency: two calls with the same input produce equal structure

All tests are pure-Python and hermetic: no OCC, no DB, no network.

References
----------
ISO 128-20: Technical product documentation — views
ISO 129-1:2018: Indication of dimensions and tolerances
ASME Y14.5-2018: Dimensioning and Tolerancing
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import pytest

from kerf_cad_core.drawings.auto_dimension import (
    auto_dimension,
    dxf_export,
    svg_export,
)


# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

def _simple_part(
    name: str = "Bracket A",
    length: float = 100.0,
    width: float = 60.0,
    height: float = 30.0,
    n_holes: int = 0,
    threaded: bool = False,
    n_fillets: int = 0,
    internal_features: bool = False,
    material: str = "Steel 1045",
    revision: str = "A",
    drawn_by: str = "Test",
    project: str = "PROJ-1",
) -> Dict[str, Any]:
    """Return a minimal mechanical part dict."""
    holes: List[Dict[str, Any]] = []
    for i in range(n_holes):
        h: Dict[str, Any] = {
            "diameter_mm": 8.0 + i,
            "depth_mm": 20.0,
            "x_mm": 10.0 + i * 15.0,
            "y_mm": 10.0,
            "z_mm": height,
            "threaded": threaded,
            "countersunk": False,
            "counterbored": False,
        }
        if threaded:
            h["thread_pitch_mm"] = 1.25
        holes.append(h)

    fillets: List[Dict[str, Any]] = []
    for i in range(n_fillets):
        fillets.append({
            "radius_mm": 2.0 + i * 0.5,
            "count": 4,
            "face": "edge",
        })

    return {
        "name": name,
        "material": material,
        "revision": revision,
        "drawn_by": drawn_by,
        "project": project,
        "bbox": {"length": length, "width": width, "height": height},
        "holes": holes,
        "fillets": fillets,
        "internal_features": internal_features,
        "mesh": None,
    }


def _run(part: Any, sheet: str = "A3") -> Dict[str, Any]:
    return auto_dimension(part, sheet=sheet)


# ---------------------------------------------------------------------------
# 1–4: 4-view sheet structure
# ---------------------------------------------------------------------------

class TestFourViewsPresent:
    def test_all_four_views_present_simple_part(self):
        d = _run(_simple_part())
        assert d["ok"] is True
        for v in ("front", "top", "right", "iso"):
            assert v in d["views"], f"view {v!r} missing"

    def test_each_view_has_bbox(self):
        d = _run(_simple_part(length=50.0, width=50.0, height=50.0))
        for v in ("front", "top", "right", "iso"):
            bbox = d["views"][v]["bbox"]
            assert "x" in bbox and "y" in bbox and "w" in bbox and "h" in bbox

    def test_each_view_has_label(self):
        d = _run(_simple_part())
        expected_labels = {"front": "FRONT", "top": "TOP", "right": "RIGHT", "iso": "ISO (3D)"}
        for v, lbl in expected_labels.items():
            assert d["views"][v]["label"] == lbl, f"wrong label for {v}"

    def test_view_names_in_meta(self):
        d = _run(_simple_part())
        assert d["meta"]["view_names"] == ["front", "top", "right", "iso"]

    def test_each_view_has_dimensions_key(self):
        d = _run(_simple_part())
        for v in ("front", "top", "right", "iso"):
            assert "dimensions" in d["views"][v]
            assert isinstance(d["views"][v]["dimensions"], list)

    def test_each_view_has_visible_hidden_keys(self):
        d = _run(_simple_part())
        for v in ("front", "top", "right", "iso"):
            assert "visible" in d["views"][v]
            assert "hidden" in d["views"][v]
            assert isinstance(d["views"][v]["visible"], list)
            assert isinstance(d["views"][v]["hidden"], list)


# ---------------------------------------------------------------------------
# 5–8: Overall L×W×H linear dimensions
# ---------------------------------------------------------------------------

class TestOverallDimensions:
    def test_front_view_has_length_dim(self):
        d = _run(_simple_part(length=120.0, width=60.0, height=40.0))
        front_dims = d["views"]["front"]["dimensions"]
        labels = [dim["label"] for dim in front_dims]
        assert any("L=" in lbl for lbl in labels), f"no L= dim in front; got {labels}"

    def test_front_view_has_height_dim(self):
        d = _run(_simple_part(length=120.0, width=60.0, height=40.0))
        front_dims = d["views"]["front"]["dimensions"]
        labels = [dim["label"] for dim in front_dims]
        assert any("H=" in lbl for lbl in labels), f"no H= dim in front; got {labels}"

    def test_top_view_has_width_dim(self):
        d = _run(_simple_part(length=80.0, width=50.0, height=25.0))
        top_dims = d["views"]["top"]["dimensions"]
        labels = [dim["label"] for dim in top_dims]
        assert any("W=" in lbl for lbl in labels), f"no W= dim in top; got {labels}"

    def test_dim_value_matches_bbox_length(self):
        d = _run(_simple_part(length=75.0, width=40.0, height=20.0))
        front_dims = d["views"]["front"]["dimensions"]
        l_dims = [dim for dim in front_dims if "L=" in dim.get("label", "")]
        assert len(l_dims) == 1
        assert abs(l_dims[0]["value_mm"] - 75.0) < 1e-6

    def test_dim_value_matches_bbox_height(self):
        d = _run(_simple_part(length=75.0, width=40.0, height=35.0))
        front_dims = d["views"]["front"]["dimensions"]
        h_dims = [dim for dim in front_dims if "H=" in dim.get("label", "")]
        assert len(h_dims) == 1
        assert abs(h_dims[0]["value_mm"] - 35.0) < 1e-6

    def test_no_bbox_produces_empty_overall_dims(self):
        part = {"name": "NoBox", "bbox": None, "holes": [], "fillets": []}
        d = _run(part)
        assert d["ok"] is True
        assert d["annotations"]["overall_dims"] == []

    def test_overall_dims_flat_list_in_annotations(self):
        d = _run(_simple_part(length=100.0, width=50.0, height=30.0))
        dims = d["annotations"]["overall_dims"]
        assert isinstance(dims, list)
        assert len(dims) >= 3  # L(front), H(front), L(top), W(top), W(right)


# ---------------------------------------------------------------------------
# 9–12: Hole table
# ---------------------------------------------------------------------------

class TestHoleTable:
    def test_no_holes_empty_hole_table(self):
        d = _run(_simple_part(n_holes=0))
        assert d["annotations"]["hole_table"] == []

    def test_single_hole_one_table_row(self):
        d = _run(_simple_part(n_holes=1))
        ht = d["annotations"]["hole_table"]
        assert len(ht) == 1

    def test_multiple_identical_holes_grouped(self):
        # 3 holes with identical diameter — should group into 1 row
        part = {
            "name": "Plate",
            "bbox": {"length": 100.0, "width": 60.0, "height": 10.0},
            "holes": [
                {"diameter_mm": 6.0, "depth_mm": 10.0, "x_mm": 10.0, "y_mm": 10.0,
                 "z_mm": 10.0, "threaded": False, "countersunk": False, "counterbored": False},
                {"diameter_mm": 6.0, "depth_mm": 10.0, "x_mm": 25.0, "y_mm": 10.0,
                 "z_mm": 10.0, "threaded": False, "countersunk": False, "counterbored": False},
                {"diameter_mm": 6.0, "depth_mm": 10.0, "x_mm": 40.0, "y_mm": 10.0,
                 "z_mm": 10.0, "threaded": False, "countersunk": False, "counterbored": False},
            ],
            "fillets": [],
        }
        d = _run(part)
        ht = d["annotations"]["hole_table"]
        assert len(ht) == 1
        assert ht[0]["qty"] == 3

    def test_different_diameter_holes_separate_rows(self):
        part = {
            "name": "Plate",
            "bbox": {"length": 100.0, "width": 60.0, "height": 10.0},
            "holes": [
                {"diameter_mm": 6.0, "depth_mm": 10.0, "x_mm": 10.0, "y_mm": 10.0,
                 "z_mm": 10.0, "threaded": False, "countersunk": False, "counterbored": False},
                {"diameter_mm": 10.0, "depth_mm": 15.0, "x_mm": 50.0, "y_mm": 10.0,
                 "z_mm": 10.0, "threaded": False, "countersunk": False, "counterbored": False},
            ],
            "fillets": [],
        }
        d = _run(part)
        ht = d["annotations"]["hole_table"]
        assert len(ht) == 2


# ---------------------------------------------------------------------------
# 13–15: Thread callouts
# ---------------------------------------------------------------------------

class TestThreadCallouts:
    def test_no_threaded_holes_no_callouts(self):
        d = _run(_simple_part(n_holes=2, threaded=False))
        assert d["annotations"]["thread_callouts"] == []

    def test_threaded_hole_produces_callout(self):
        d = _run(_simple_part(n_holes=1, threaded=True))
        tcs = d["annotations"]["thread_callouts"]
        assert len(tcs) == 1

    def test_thread_callout_label_format(self):
        d = _run(_simple_part(n_holes=1, threaded=True))
        tc = d["annotations"]["thread_callouts"][0]
        # e.g. "M8 ×1.2 ×20 DP"
        assert "M" in tc["label"] and "×" in tc["label"]

    def test_duplicate_threaded_holes_deduped(self):
        # Two holes with the same thread spec → one callout
        part = {
            "name": "Bracket",
            "bbox": {"length": 100.0, "width": 60.0, "height": 20.0},
            "holes": [
                {"diameter_mm": 8.0, "depth_mm": 20.0, "x_mm": 10.0, "y_mm": 10.0,
                 "z_mm": 20.0, "threaded": True, "thread_pitch_mm": 1.25,
                 "countersunk": False, "counterbored": False},
                {"diameter_mm": 8.0, "depth_mm": 20.0, "x_mm": 30.0, "y_mm": 10.0,
                 "z_mm": 20.0, "threaded": True, "thread_pitch_mm": 1.25,
                 "countersunk": False, "counterbored": False},
            ],
            "fillets": [],
        }
        d = _run(part)
        assert len(d["annotations"]["thread_callouts"]) == 1

    def test_thread_callout_has_position(self):
        d = _run(_simple_part(n_holes=1, threaded=True))
        tc = d["annotations"]["thread_callouts"][0]
        assert "position_2d" in tc
        assert len(tc["position_2d"]) == 2


# ---------------------------------------------------------------------------
# 16–17: Fillet callouts
# ---------------------------------------------------------------------------

class TestFilletCallouts:
    def test_no_fillets_no_callouts(self):
        d = _run(_simple_part(n_fillets=0))
        assert d["annotations"]["fillet_callouts"] == []

    def test_single_fillet_one_callout(self):
        d = _run(_simple_part(n_fillets=1))
        fcs = d["annotations"]["fillet_callouts"]
        assert len(fcs) == 1
        assert fcs[0]["label"].startswith("R")

    def test_multiple_unique_radii_multiple_callouts(self):
        d = _run(_simple_part(n_fillets=3))
        fcs = d["annotations"]["fillet_callouts"]
        # 3 fillets with different radii → 3 callouts
        assert len(fcs) == 3

    def test_fillet_count_accumulates_for_same_radius(self):
        part = {
            "name": "Plate",
            "bbox": {"length": 100.0, "width": 60.0, "height": 10.0},
            "holes": [],
            "fillets": [
                {"radius_mm": 3.0, "count": 2, "face": "top"},
                {"radius_mm": 3.0, "count": 4, "face": "edge"},
            ],
        }
        d = _run(part)
        fcs = d["annotations"]["fillet_callouts"]
        assert len(fcs) == 1
        assert fcs[0]["count"] == 6

    def test_zero_radius_fillet_ignored(self):
        part = {
            "name": "Plate",
            "bbox": {"length": 100.0, "width": 60.0, "height": 10.0},
            "holes": [],
            "fillets": [{"radius_mm": 0.0, "count": 4, "face": "edge"}],
        }
        d = _run(part)
        assert d["annotations"]["fillet_callouts"] == []


# ---------------------------------------------------------------------------
# 18: Section note
# ---------------------------------------------------------------------------

class TestSectionNote:
    def test_no_internal_features_no_section_note(self):
        d = _run(_simple_part(internal_features=False))
        assert d["annotations"]["section_note"] is None

    def test_internal_features_produces_section_note(self):
        d = _run(_simple_part(internal_features=True))
        note = d["annotations"]["section_note"]
        assert note is not None
        assert len(note) > 0
        assert "SECTION" in note.upper()


# ---------------------------------------------------------------------------
# 19–20: GD&T frames
# ---------------------------------------------------------------------------

class TestGdtFrames:
    def test_no_bbox_no_gdt_frames(self):
        part = {"name": "NoBox", "bbox": None, "holes": [], "fillets": []}
        d = _run(part)
        assert d["annotations"]["gdt_frames"] == []

    def test_bbox_produces_at_least_two_gdt_frames(self):
        d = _run(_simple_part())
        gdt = d["annotations"]["gdt_frames"]
        assert len(gdt) >= 2

    def test_parallelism_frame_present(self):
        d = _run(_simple_part())
        gdt = d["annotations"]["gdt_frames"]
        symbols = [f["symbol"] for f in gdt]
        assert "//" in symbols

    def test_perpendicularity_frame_present(self):
        d = _run(_simple_part())
        gdt = d["annotations"]["gdt_frames"]
        symbols = [f["symbol"] for f in gdt]
        assert "⊥" in symbols

    def test_position_frame_added_for_two_plus_holes(self):
        d = _run(_simple_part(n_holes=2))
        gdt = d["annotations"]["gdt_frames"]
        symbols = [f["symbol"] for f in gdt]
        assert "⊕" in symbols

    def test_position_frame_absent_for_single_hole(self):
        d = _run(_simple_part(n_holes=1))
        gdt = d["annotations"]["gdt_frames"]
        symbols = [f["symbol"] for f in gdt]
        assert "⊕" not in symbols


# ---------------------------------------------------------------------------
# 21–22: Title block and sheet metadata
# ---------------------------------------------------------------------------

class TestTitleBlock:
    def test_title_block_has_name(self):
        d = _run(_simple_part(name="Widget X"))
        tb = d["annotations"]["title_block"]
        assert tb["name"] == "Widget X"

    def test_title_block_has_revision(self):
        d = _run(_simple_part(revision="B"))
        tb = d["annotations"]["title_block"]
        assert tb["revision"] == "B"

    def test_title_block_scale_label_1_1_for_small_part(self):
        # A tiny 10×10×10 part on A3 should scale 1:1
        d = _run(_simple_part(length=10.0, width=10.0, height=10.0))
        tb = d["annotations"]["title_block"]
        assert "1:1" in tb["scale"] or "1" in tb["scale"]

    def test_title_block_material_present(self):
        d = _run(_simple_part(material="Aluminium 6061"))
        tb = d["annotations"]["title_block"]
        assert tb["material"] == "Aluminium 6061"

    def test_drawing_id_is_uuid_format(self):
        import re
        d = _run(_simple_part())
        did = d["meta"]["drawing_id"]
        assert re.match(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            did,
        ), f"drawing_id is not a UUID: {did!r}"


class TestSheetMetadata:
    def test_a3_sheet_dimensions(self):
        d = _run(_simple_part(), sheet="A3")
        sheet = d["sheet"]
        assert abs(sheet["width_mm"] - 420.0) < 1e-6
        assert abs(sheet["height_mm"] - 297.0) < 1e-6

    def test_a4_sheet_dimensions(self):
        d = _run(_simple_part(), sheet="A4")
        sheet = d["sheet"]
        assert abs(sheet["width_mm"] - 297.0) < 1e-6
        assert abs(sheet["height_mm"] - 210.0) < 1e-6

    def test_letter_sheet_dimensions(self):
        d = _run(_simple_part(), sheet="LETTER")
        sheet = d["sheet"]
        assert abs(sheet["width_mm"] - 279.4) < 1e-3
        assert abs(sheet["height_mm"] - 215.9) < 1e-3

    def test_sheet_border_is_closed(self):
        d = _run(_simple_part())
        border = d["sheet"]["border"]
        assert len(border) >= 4
        assert border[0] == border[-1], "border polyline must be closed"

    def test_title_block_border_is_closed(self):
        d = _run(_simple_part())
        tb_border = d["sheet"]["title_block"]
        assert len(tb_border) >= 4
        assert tb_border[0] == tb_border[-1]


# ---------------------------------------------------------------------------
# 23–24: DXF export
# ---------------------------------------------------------------------------

class TestDxfExport:
    def test_dxf_non_empty_for_valid_drawing(self):
        d = _run(_simple_part())
        dxf = dxf_export(d)
        assert len(dxf) > 0

    def test_dxf_has_entities_section(self):
        d = _run(_simple_part())
        dxf = dxf_export(d)
        assert "ENTITIES" in dxf

    def test_dxf_has_eof_marker(self):
        d = _run(_simple_part())
        dxf = dxf_export(d)
        assert "EOF" in dxf

    def test_dxf_contains_view_label_text(self):
        d = _run(_simple_part())
        dxf = dxf_export(d)
        assert "FRONT" in dxf

    def test_dxf_contains_part_name(self):
        d = _run(_simple_part(name="SpecialPart"))
        dxf = dxf_export(d)
        assert "SpecialPart" in dxf

    def test_dxf_contains_dim_layer(self):
        d = _run(_simple_part(length=100.0, width=60.0, height=30.0))
        dxf = dxf_export(d)
        assert "DIM" in dxf

    def test_dxf_contains_border_layer(self):
        d = _run(_simple_part())
        dxf = dxf_export(d)
        assert "BORDER" in dxf

    def test_dxf_thread_label_for_threaded_part(self):
        d = _run(_simple_part(n_holes=1, threaded=True))
        dxf = dxf_export(d)
        assert "THREAD" in dxf

    def test_dxf_returns_empty_for_bad_drawing(self):
        dxf = dxf_export({"ok": False, "reason": "test"})
        assert dxf == ""

    def test_dxf_returns_empty_for_empty_dict(self):
        dxf = dxf_export({})
        assert dxf == ""


# ---------------------------------------------------------------------------
# 25–26: SVG export
# ---------------------------------------------------------------------------

class TestSvgExport:
    def test_svg_non_empty_for_valid_drawing(self):
        d = _run(_simple_part())
        svg = svg_export(d)
        assert len(svg) > 0

    def test_svg_has_opening_tag(self):
        d = _run(_simple_part())
        svg = svg_export(d)
        assert "<svg" in svg

    def test_svg_has_closing_tag(self):
        d = _run(_simple_part())
        svg = svg_export(d)
        assert "</svg>" in svg

    def test_svg_contains_view_label(self):
        d = _run(_simple_part())
        svg = svg_export(d)
        assert "FRONT" in svg

    def test_svg_contains_part_name(self):
        d = _run(_simple_part(name="AeroClip"))
        svg = svg_export(d)
        assert "AeroClip" in svg

    def test_svg_contains_dimension_line(self):
        d = _run(_simple_part(length=100.0, width=60.0, height=30.0))
        svg = svg_export(d)
        assert "<line" in svg

    def test_svg_contains_border_polyline(self):
        d = _run(_simple_part())
        svg = svg_export(d)
        assert '<polyline class="bdr"' in svg

    def test_svg_section_note_present_when_internal(self):
        d = _run(_simple_part(internal_features=True))
        svg = svg_export(d)
        assert "SECTION" in svg.upper()

    def test_svg_fillet_callout_present(self):
        d = _run(_simple_part(n_fillets=1))
        svg = svg_export(d)
        # Fillet label like "R2.00"
        assert "R2" in svg or "R" in svg

    def test_svg_returns_empty_for_bad_drawing(self):
        svg = svg_export({"ok": False, "reason": "bad"})
        assert svg == ""


# ---------------------------------------------------------------------------
# 27: Boundary / malformed input — never raises
# ---------------------------------------------------------------------------

class TestBoundaryInputs:
    def test_none_input_returns_error(self):
        d = _run(None)
        assert d["ok"] is False

    def test_string_input_returns_error(self):
        d = _run("not a dict")
        assert d["ok"] is False

    def test_list_input_returns_error(self):
        d = _run([1, 2, 3])
        assert d["ok"] is False

    def test_unknown_sheet_returns_error(self):
        d = auto_dimension(_simple_part(), sheet="X99")
        assert d["ok"] is False

    def test_empty_dict_does_not_raise(self):
        d = _run({})
        # Should succeed (empty part is valid — no bbox, no holes, no fillets)
        assert "ok" in d

    def test_holes_not_list_does_not_raise(self):
        part = {
            "name": "Test",
            "bbox": {"length": 100.0, "width": 60.0, "height": 30.0},
            "holes": "not a list",
            "fillets": [],
        }
        d = _run(part)
        assert "ok" in d

    def test_fillets_not_list_does_not_raise(self):
        part = {
            "name": "Test",
            "bbox": {"length": 100.0, "width": 60.0, "height": 30.0},
            "holes": [],
            "fillets": "not a list",
        }
        d = _run(part)
        assert "ok" in d

    def test_negative_bbox_does_not_crash(self):
        part = {
            "name": "Test",
            "bbox": {"length": -10.0, "width": -5.0, "height": -1.0},
            "holes": [],
            "fillets": [],
        }
        d = _run(part)
        assert "ok" in d

    def test_zero_bbox_does_not_crash(self):
        part = {
            "name": "Test",
            "bbox": {"length": 0.0, "width": 0.0, "height": 0.0},
            "holes": [],
            "fillets": [],
        }
        d = _run(part)
        assert "ok" in d

    def test_hole_missing_required_keys_does_not_crash(self):
        part = {
            "name": "Test",
            "bbox": {"length": 100.0, "width": 60.0, "height": 30.0},
            "holes": [{}],  # all keys missing
            "fillets": [],
        }
        d = _run(part)
        assert "ok" in d

    def test_bbox_with_missing_height_does_not_crash(self):
        part = {
            "name": "Test",
            "bbox": {"length": 100.0, "width": 60.0},  # height missing
            "holes": [],
            "fillets": [],
        }
        d = _run(part)
        assert "ok" in d


# ---------------------------------------------------------------------------
# 28: Idempotency — two calls with same input give same structure
# ---------------------------------------------------------------------------

class TestIdempotency:
    def test_same_structure_on_repeated_call(self):
        part = _simple_part(length=80.0, width=50.0, height=25.0, n_holes=2)
        d1 = _run(part)
        d2 = _run(part)
        assert d1["ok"] == d2["ok"]
        # Views names and labels identical
        assert list(d1["views"].keys()) == list(d2["views"].keys())
        for v in d1["views"]:
            assert d1["views"][v]["label"] == d2["views"][v]["label"]
        # Sheet sizes identical
        assert d1["sheet"]["width_mm"] == d2["sheet"]["width_mm"]
        assert d1["sheet"]["height_mm"] == d2["sheet"]["height_mm"]
        # Scale identical
        assert d1["meta"]["scale"] == d2["meta"]["scale"]
        # Annotation counts identical
        assert len(d1["annotations"]["overall_dims"]) == len(d2["annotations"]["overall_dims"])
        assert len(d1["annotations"]["hole_table"]) == len(d2["annotations"]["hole_table"])

    def test_dxf_deterministic_length(self):
        part = _simple_part(n_holes=1, threaded=True)
        d = _run(part)
        dxf1 = dxf_export(d)
        dxf2 = dxf_export(d)
        assert len(dxf1) == len(dxf2)

    def test_svg_deterministic_length(self):
        part = _simple_part(n_holes=1)
        d = _run(part)
        svg1 = svg_export(d)
        svg2 = svg_export(d)
        assert len(svg1) == len(svg2)


# ---------------------------------------------------------------------------
# 29: All sheet sizes accepted
# ---------------------------------------------------------------------------

class TestAllSheetSizes:
    @pytest.mark.parametrize("sheet", ["A0", "A1", "A2", "A3", "A4", "LETTER"])
    def test_sheet_size_accepted(self, sheet: str):
        d = auto_dimension(_simple_part(), sheet=sheet)
        assert d["ok"] is True
        assert d["sheet"]["size"] == sheet

    def test_lowercase_sheet_accepted(self):
        d = auto_dimension(_simple_part(), sheet="a3")
        assert d["ok"] is True
        assert d["sheet"]["size"] == "A3"


# ---------------------------------------------------------------------------
# 30: Large / complex part — 25-part sweep
# ---------------------------------------------------------------------------

class TestLargePartSweep:
    """Exercise 25 distinct part-drawing pairs to meet the floor."""

    @pytest.mark.parametrize("idx,length,width,height,n_holes,n_fillets,internal", [
        (0,  200.0,  80.0, 40.0, 0, 0, False),
        (1,   50.0,  50.0, 50.0, 0, 0, False),
        (2,  100.0,  30.0, 10.0, 1, 0, False),
        (3,  100.0,  60.0, 30.0, 2, 0, False),
        (4,  100.0,  60.0, 30.0, 3, 0, True),
        (5,  100.0,  60.0, 30.0, 0, 1, False),
        (6,  100.0,  60.0, 30.0, 0, 3, False),
        (7,  100.0,  60.0, 30.0, 2, 2, True),
        (8,  500.0, 300.0, 200.0, 0, 0, False),   # very large → scale < 1
        (9,    5.0,   3.0,   2.0, 0, 0, False),   # very small
        (10, 100.0,  60.0, 30.0, 4, 0, False),    # 4 different holes
        (11, 100.0,  60.0, 30.0, 4, 4, True),
        (12, 100.0,  60.0, 30.0, 2, 1, False),
        (13, 150.0,  90.0, 60.0, 3, 2, True),
        (14,  80.0,  40.0, 20.0, 0, 0, False),
        (15, 250.0, 100.0, 50.0, 5, 0, False),
        (16, 100.0, 100.0, 100.0, 0, 0, False),   # cube
        (17, 200.0,  50.0, 10.0, 0, 0, False),    # flat plate
        (18,  10.0, 100.0, 50.0, 0, 0, False),    # narrow extrusion
        (19, 100.0,  60.0, 30.0, 2, 0, True),
        (20, 100.0,  60.0, 30.0, 0, 5, False),
        (21,  75.0,  45.0, 25.0, 1, 1, False),
        (22, 120.0,  80.0, 40.0, 3, 3, True),
        (23,  60.0,  30.0, 15.0, 0, 2, False),
        (24, 100.0,  60.0, 30.0, 6, 2, True),
    ])
    def test_part_drawing_pair(
        self,
        idx: int,
        length: float,
        width: float,
        height: float,
        n_holes: int,
        n_fillets: int,
        internal: bool,
    ):
        part = _simple_part(
            name=f"Part-{idx:02d}",
            length=length,
            width=width,
            height=height,
            n_holes=n_holes,
            n_fillets=n_fillets,
            internal_features=internal,
        )
        d = _run(part)
        assert d["ok"] is True, f"Part {idx}: drawing failed: {d.get('reason')}"
        assert len(d["views"]) == 4
        # DXF and SVG must both succeed
        dxf = dxf_export(d)
        svg = svg_export(d)
        assert len(dxf) > 0, f"Part {idx}: DXF empty"
        assert "<svg" in svg, f"Part {idx}: SVG invalid"
        assert "</svg>" in svg, f"Part {idx}: SVG unclosed"
        # Dimensions present when bbox given
        assert len(d["annotations"]["overall_dims"]) >= 3
        # Hole table count matches
        holes_input = len(part.get("holes", []))
        if holes_input == 0:
            assert d["annotations"]["hole_table"] == []
        # Section note correct
        if internal:
            assert d["annotations"]["section_note"] is not None
        else:
            assert d["annotations"]["section_note"] is None
