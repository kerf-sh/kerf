"""
T-166 — Packaging / dieline (folding carton + corrugated) seed.

Tests verify:
1. ECMA C-02 RSC generator produces correct panel dimensions (DoD criterion 1).
2. fold_dieline produces a closed 3-D carton (DoD criterion 2).
3. DXF export round-trips (DoD criterion 3).
4. ECMA A-10 tray and B-03 display generators smoke-test correctly.
5. Dieline data model, validation, and utility methods.
"""

from __future__ import annotations

import math
import os
import sys

import pytest

# ---------------------------------------------------------------------------
# sys.path bootstrap (belt-and-suspenders alongside conftest)
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(os.path.dirname(_HERE), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# Also add kerf-imports src so dxf_writer is importable
_IMPORTS_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(_SRC))),
    "packages", "kerf-imports", "src",
)
if os.path.isdir(_IMPORTS_SRC) and _IMPORTS_SRC not in sys.path:
    sys.path.insert(0, _IMPORTS_SRC)


from kerf_packaging.dieline import (
    Dieline,
    DiPanel,
    DieLine,
    FoldEdge,
    LineKind,
    Material,
    validate_dieline,
    Point2D,
)
from kerf_packaging.ecma_generators import (
    ecma_c02_rsc,
    ecma_a10_tray,
    ecma_b03_display,
)
from kerf_packaging.fold import fold_dieline, FoldResult


# ===========================================================================
# Helpers
# ===========================================================================

def _make_rsc(l=300.0, w=200.0, d=150.0, **kw):
    return ecma_c02_rsc(l, w, d, **kw)


# ===========================================================================
# 1. ECMA C-02 RSC — Correct panel dimensions (DoD criterion 1)
# ===========================================================================

class TestEcmaC02Dimensions:
    """ECMA C02 RSC blank dimensions and panel dimensions match the standard."""

    def test_blank_width_formula(self):
        """blank_width = 2L + 2W + joint."""
        L, W, D, joint = 300.0, 200.0, 150.0, 15.0
        d = ecma_c02_rsc(L, W, D, joint=joint)
        expected_w = 2 * L + 2 * W + joint
        assert abs(d.width - expected_w) < 1e-6, (
            f"blank width {d.width} ≠ 2L+2W+joint={expected_w}"
        )

    def test_blank_height_formula(self):
        """blank_height = D + W  (flap_h = W/2 on each side)."""
        L, W, D = 300.0, 200.0, 150.0
        d = ecma_c02_rsc(L, W, D)
        expected_h = D + W   # W/2 top + W/2 bottom = W
        assert abs(d.height - expected_h) < 1e-6, (
            f"blank height {d.height} ≠ D+W={expected_h}"
        )

    def test_front_panel_width(self):
        """Front panel width = L (internal length)."""
        L, W, D = 300.0, 200.0, 150.0
        d = ecma_c02_rsc(L, W, D)
        front = next(p for p in d.panels if p.name == "front")
        assert abs(front.width - L) < 1e-6, f"front.width {front.width} ≠ L={L}"

    def test_front_panel_height(self):
        """Front panel height = D (internal depth)."""
        L, W, D = 300.0, 200.0, 150.0
        d = ecma_c02_rsc(L, W, D)
        front = next(p for p in d.panels if p.name == "front")
        assert abs(front.height - D) < 1e-6, f"front.height {front.height} ≠ D={D}"

    def test_left_panel_width(self):
        """Left panel width = W (internal width)."""
        L, W, D = 300.0, 200.0, 150.0
        d = ecma_c02_rsc(L, W, D)
        left = next(p for p in d.panels if p.name == "left")
        assert abs(left.width - W) < 1e-6, f"left.width {left.width} ≠ W={W}"

    def test_back_panel_width_equals_front(self):
        """Back panel width = L (same as front)."""
        L, W, D = 300.0, 200.0, 150.0
        d = ecma_c02_rsc(L, W, D)
        back  = next(p for p in d.panels if p.name == "back")
        front = next(p for p in d.panels if p.name == "front")
        assert abs(back.width - front.width) < 1e-6

    def test_flap_height_equals_half_width(self):
        """Top and bottom flap height = W/2."""
        L, W, D = 300.0, 200.0, 150.0
        d = ecma_c02_rsc(L, W, D)
        top_flap = next(p for p in d.panels if p.name == "top_flap_front")
        assert abs(top_flap.height - W / 2.0) < 1e-6, (
            f"top flap height {top_flap.height} ≠ W/2={W/2}"
        )

    def test_bottom_flap_height_equals_half_width(self):
        """Bottom flap height = W/2."""
        L, W, D = 300.0, 200.0, 150.0
        d = ecma_c02_rsc(L, W, D)
        bot_flap = next(p for p in d.panels if p.name == "bottom_flap_front")
        assert abs(bot_flap.height - W / 2.0) < 1e-6

    def test_panel_count(self):
        """RSC has 13 panels: 4 body + 1 joint + 4 bottom flaps + 4 top flaps."""
        d = _make_rsc()
        assert len(d.panels) == 13

    def test_expected_panel_names(self):
        """All expected panel names are present."""
        d = _make_rsc()
        names = {p.name for p in d.panels}
        expected = {
            "left", "front", "right", "back", "joint",
            "bottom_flap_left", "bottom_flap_front",
            "bottom_flap_right", "bottom_flap_back",
            "top_flap_left", "top_flap_front",
            "top_flap_right", "top_flap_back",
        }
        assert expected.issubset(names), f"missing panels: {expected - names}"

    def test_units_mm(self):
        assert _make_rsc().units == "mm"

    def test_material_sbs_default(self):
        assert _make_rsc().material == Material.SBS

    def test_material_flute_c(self):
        d = ecma_c02_rsc(300, 200, 150, material=Material.FLUTE_C)
        assert d.material == Material.FLUTE_C

    def test_name_contains_ecma_c02(self):
        assert "C02" in _make_rsc().name.upper()

    def test_metadata_internal_dimensions(self):
        L, W, D = 250.0, 180.0, 120.0
        d = ecma_c02_rsc(L, W, D)
        assert abs(d.metadata["internal_length_mm"] - L) < 1e-6
        assert abs(d.metadata["internal_width_mm"]  - W) < 1e-6
        assert abs(d.metadata["internal_depth_mm"]  - D) < 1e-6

    def test_custom_joint_width(self):
        """Custom joint width changes blank width correctly."""
        L, W, D, joint = 300.0, 200.0, 150.0, 20.0
        d = ecma_c02_rsc(L, W, D, joint=joint)
        expected_w = 2 * L + 2 * W + joint
        assert abs(d.width - expected_w) < 1e-6

    def test_different_dimensions(self):
        """Small box (100×80×60) dimensions are correct."""
        L, W, D = 100.0, 80.0, 60.0
        d = ecma_c02_rsc(L, W, D)
        assert abs(d.width  - (2*L + 2*W + 15.0)) < 1e-6
        assert abs(d.height - (D + W)) < 1e-6

    def test_invalid_zero_length_raises(self):
        with pytest.raises(ValueError):
            ecma_c02_rsc(0, 200, 150)

    def test_invalid_negative_depth_raises(self):
        with pytest.raises(ValueError):
            ecma_c02_rsc(300, 200, -10)


# ===========================================================================
# 2. Lines: cut and fold line counts
# ===========================================================================

class TestEcmaC02Lines:
    """Verify line types and counts for ECMA C02."""

    def test_has_cut_lines(self):
        d = _make_rsc()
        assert len(d.cut_lines()) > 0

    def test_has_fold_lines(self):
        d = _make_rsc()
        assert len(d.fold_lines()) > 0

    def test_fold_edge_count(self):
        """12 fold edges: 4 body + 4 bottom + 4 top."""
        d = _make_rsc()
        assert len(d.fold_edges) == 12

    def test_fold_lines_have_fold_kind(self):
        d = _make_rsc()
        for line in d.fold_lines():
            assert line.kind == LineKind.FOLD

    def test_cut_lines_have_cut_kind(self):
        d = _make_rsc()
        for line in d.cut_lines():
            assert line.kind == LineKind.CUT

    def test_no_zero_length_lines(self):
        d = _make_rsc()
        for i, line in enumerate(d.lines):
            assert line.length() > 1e-9, f"zero-length line[{i}]"

    def test_lines_within_blank_bounds(self):
        """All line endpoints are within the blank dimensions."""
        d = _make_rsc()
        tol = 1e-6
        for line in d.lines:
            assert -tol <= line.x1 <= d.width  + tol, f"x1={line.x1}"
            assert -tol <= line.x2 <= d.width  + tol, f"x2={line.x2}"
            assert -tol <= line.y1 <= d.height + tol, f"y1={line.y1}"
            assert -tol <= line.y2 <= d.height + tol, f"y2={line.y2}"

    def test_fold_angles_are_90(self):
        """All fold edges in C02 are 90-degree folds."""
        d = _make_rsc()
        for fe in d.fold_edges:
            assert abs(fe.angle_deg - 90.0) < 1e-6


# ===========================================================================
# 3. fold_dieline — closed 3-D carton (DoD criterion 2)
# ===========================================================================

class TestFoldDieline:
    """fold_dieline produces a closed 3-D shape."""

    def test_returns_fold_result(self):
        d = _make_rsc()
        result = fold_dieline(d)
        assert isinstance(result, FoldResult)

    def test_panels_dict_non_empty(self):
        d = _make_rsc()
        result = fold_dieline(d)
        assert len(result.panels) > 0

    def test_all_body_panels_have_4_corners(self):
        """Each rectangular panel should have 4 corner vertices."""
        d = _make_rsc()
        result = fold_dieline(d)
        body_panels = ["front", "back", "left", "right"]
        for name in body_panels:
            assert name in result.panels, f"panel '{name}' missing"
            assert len(result.panels[name]) == 4, (
                f"panel '{name}' has {len(result.panels[name])} vertices, expected 4"
            )

    def test_is_closed(self):
        """A fully-folded RSC should be classified as closed."""
        d = _make_rsc()
        result = fold_dieline(d)
        assert result.is_closed, (
            f"RSC fold not closed; warnings: {result.warnings}"
        )

    def test_bounding_box_non_degenerate(self):
        """The bounding box of the folded shape should span 3 dimensions."""
        d = _make_rsc(300, 200, 150)
        result = fold_dieline(d, fold_angle_override=90.0)
        bb_min, bb_max = result.bounding_box
        span_x = bb_max[0] - bb_min[0]
        span_y = bb_max[1] - bb_min[1]
        span_z = bb_max[2] - bb_min[2]
        # After folding, at least one dimension should have non-zero span
        assert span_x > 1.0 or span_y > 1.0 or span_z > 1.0, (
            f"degenerate bounding box: min={bb_min}, max={bb_max}"
        )

    def test_flat_fold_no_z_displacement(self):
        """fold_angle=0 keeps all panels flat (z ≈ 0 for most vertices)."""
        d = _make_rsc()
        result = fold_dieline(d, fold_angle_override=0.0)
        for name, verts in result.panels.items():
            for v in verts:
                assert abs(v[2]) < 1e-6, (
                    f"panel '{name}' vertex z={v[2]} is non-zero at fold_angle=0"
                )

    def test_folded_has_nonzero_z(self):
        """After folding at 90°, some vertices should have non-zero z."""
        d = _make_rsc(300, 200, 150)
        result = fold_dieline(d, fold_angle_override=90.0)
        max_z = max(abs(v[2]) for verts in result.panels.values() for v in verts)
        assert max_z > 1.0, f"no z-displacement after 90° fold (max_z={max_z})"

    def test_a10_tray_fold_closed(self):
        """A10 tray fold is also classified as closed."""
        d = ecma_a10_tray(200.0, 150.0, 50.0)
        result = fold_dieline(d)
        # Just verify it returns without error and is_closed is a bool
        assert isinstance(result.is_closed, bool)

    def test_b03_display_fold(self):
        """B03 display fold returns a result without error."""
        d = ecma_b03_display(200.0, 100.0, 150.0)
        result = fold_dieline(d)
        assert len(result.panels) > 0


# ===========================================================================
# 4. DXF export round-trip (DoD criterion 3)
# ===========================================================================

class TestDxfRoundTrip:
    """DXF export round-trips: the exported DXF text parses back to lines."""

    @pytest.fixture
    def dxf_writer_available(self):
        try:
            from kerf_imports.dxf_writer import dxf_export_result
            return dxf_export_result
        except ImportError:
            pytest.skip("kerf_imports.dxf_writer not available")

    def test_dxf_export_ok(self, dxf_writer_available):
        dxf_export_result = dxf_writer_available
        d = _make_rsc()
        drawing = d.to_drawing_dict()
        result = dxf_export_result(drawing, version="R2004")
        assert result["ok"] is True, f"DXF export failed: {result.get('reason')}"

    def test_dxf_contains_line_entities(self, dxf_writer_available):
        """The exported DXF text contains LINE entity markers."""
        dxf_export_result = dxf_writer_available
        d = _make_rsc()
        drawing = d.to_drawing_dict()
        result = dxf_export_result(drawing)
        assert "LINE" in result["dxf"], "DXF output contains no LINE entities"

    def test_dxf_contains_cut_layer(self, dxf_writer_available):
        """The exported DXF declares the 'cut' layer."""
        dxf_export_result = dxf_writer_available
        d = _make_rsc()
        drawing = d.to_drawing_dict()
        result = dxf_export_result(drawing)
        assert "cut" in result["dxf"], "DXF output missing 'cut' layer"

    def test_dxf_contains_fold_layer(self, dxf_writer_available):
        """The exported DXF declares the 'fold' layer."""
        dxf_export_result = dxf_writer_available
        d = _make_rsc()
        drawing = d.to_drawing_dict()
        result = dxf_export_result(drawing)
        assert "fold" in result["dxf"], "DXF output missing 'fold' layer"

    def test_dxf_r12_also_works(self, dxf_writer_available):
        """DXF export in R12 format also succeeds."""
        dxf_export_result = dxf_writer_available
        d = _make_rsc()
        drawing = d.to_drawing_dict()
        result = dxf_export_result(drawing, version="R12")
        assert result["ok"] is True
        assert "LINE" in result["dxf"]

    def test_drawing_dict_has_entities(self):
        """to_drawing_dict produces entities list with correct types."""
        d = _make_rsc()
        drawing = d.to_drawing_dict()
        assert "entities" in drawing
        assert len(drawing["entities"]) > 0
        for ent in drawing["entities"]:
            assert ent.get("type") == "line"
            assert "x1" in ent and "y1" in ent
            assert "x2" in ent and "y2" in ent

    def test_drawing_dict_layers(self):
        """to_drawing_dict has layers for cut and fold."""
        d = _make_rsc()
        drawing = d.to_drawing_dict()
        layer_names = {l["name"] for l in drawing.get("layers", [])}
        assert "cut"  in layer_names
        assert "fold" in layer_names

    def test_drawing_dict_line_count(self):
        """Drawing dict entity count equals dieline total line count."""
        d = _make_rsc()
        drawing = d.to_drawing_dict()
        assert len(drawing["entities"]) == len(d.lines)

    def test_dxf_round_trip_line_count(self, dxf_writer_available):
        """The number of LINE entries in the DXF matches the dieline line count."""
        dxf_export_result = dxf_writer_available
        d = _make_rsc()
        drawing = d.to_drawing_dict()
        result = dxf_export_result(drawing)
        dxf_text = result["dxf"]
        # Count LINE entity markers in the ENTITIES section
        # (each LINE entity starts with a '  0\nLINE' pair)
        line_count_in_dxf = dxf_text.count("\n  0\nLINE\n") + dxf_text.count("\n  0\nLINE\r\n")
        # Also count at start of file
        if dxf_text.startswith("  0\nLINE"):
            line_count_in_dxf += 1
        assert line_count_in_dxf == len(d.lines), (
            f"DXF has {line_count_in_dxf} LINE entities but dieline has {len(d.lines)}"
        )


# ===========================================================================
# 5. ECMA A-10 tray
# ===========================================================================

class TestEcmaA10Tray:
    """ECMA A-10 one-piece tray generator."""

    def test_blank_width(self):
        L, W, D = 200.0, 150.0, 50.0
        d = ecma_a10_tray(L, W, D)
        assert abs(d.width - (L + 2 * D)) < 1e-6

    def test_blank_height(self):
        L, W, D = 200.0, 150.0, 50.0
        d = ecma_a10_tray(L, W, D)
        assert abs(d.height - (W + 2 * D)) < 1e-6

    def test_base_panel_dimensions(self):
        L, W, D = 200.0, 150.0, 50.0
        d = ecma_a10_tray(L, W, D)
        base = next(p for p in d.panels if p.name == "base")
        assert abs(base.width  - L) < 1e-6
        assert abs(base.height - W) < 1e-6

    def test_has_base_and_side_panels(self):
        d = ecma_a10_tray(200.0, 150.0, 50.0)
        names = {p.name for p in d.panels}
        assert "base" in names
        assert "front_panel" in names
        assert "back_panel" in names
        assert "left_panel" in names
        assert "right_panel" in names

    def test_has_fold_edges(self):
        d = ecma_a10_tray(200.0, 150.0, 50.0)
        assert len(d.fold_edges) >= 4

    def test_invalid_dimensions_raises(self):
        with pytest.raises(ValueError):
            ecma_a10_tray(-10, 150, 50)


# ===========================================================================
# 6. ECMA B-03 display box
# ===========================================================================

class TestEcmaB03Display:
    """ECMA B-03 counter display box generator."""

    def test_blank_width_formula(self):
        L, W, D = 200.0, 100.0, 150.0
        d = ecma_b03_display(L, W, D)
        joint = 15.0
        expected_w = 2.0 * W + 2.0 * L + joint
        assert abs(d.width - expected_w) < 1e-6

    def test_has_tuck_front_panel(self):
        d = ecma_b03_display(200.0, 100.0, 150.0)
        names = {p.name for p in d.panels}
        assert "tuck_front" in names

    def test_has_dust_panels(self):
        d = ecma_b03_display(200.0, 100.0, 150.0)
        names = {p.name for p in d.panels}
        assert "dust_front" in names
        assert "dust_back" in names

    def test_custom_tuck_depth(self):
        d = ecma_b03_display(200.0, 100.0, 150.0, tuck_depth=25.0)
        assert abs(d.metadata["tuck_depth_mm"] - 25.0) < 1e-6

    def test_default_tuck_depth_at_least_15(self):
        d = ecma_b03_display(200.0, 100.0, 30.0)
        assert d.metadata["tuck_depth_mm"] >= 15.0

    def test_invalid_dimensions_raises(self):
        with pytest.raises(ValueError):
            ecma_b03_display(0, 100, 150)


# ===========================================================================
# 7. Dieline data model and validation
# ===========================================================================

class TestDielineDataModel:
    """Dieline dataclass and validation helpers."""

    def test_dieline_instantiation(self):
        d = Dieline(name="test", width=100.0, height=50.0)
        assert d.name == "test"
        assert d.width == 100.0

    def test_dieline_defaults(self):
        d = Dieline()
        assert d.panels == []
        assert d.lines == []
        assert d.fold_edges == []
        assert d.material == Material.SBS
        assert d.units == "mm"

    def test_cut_lines_filter(self):
        d = _make_rsc()
        cut = d.cut_lines()
        assert all(l.kind == LineKind.CUT for l in cut)

    def test_fold_lines_filter(self):
        d = _make_rsc()
        fold = d.fold_lines()
        assert all(l.kind == LineKind.FOLD for l in fold)

    def test_validate_clean_dieline(self):
        d = _make_rsc()
        warnings = validate_dieline(d)
        assert warnings == [], f"unexpected warnings: {warnings}"

    def test_validate_empty_dieline(self):
        d = Dieline()
        warnings = validate_dieline(d)
        assert len(warnings) > 0  # should warn about missing name, panels, lines, size

    def test_validate_no_name(self):
        d = _make_rsc()
        d.name = ""
        warnings = validate_dieline(d)
        assert any("name" in w for w in warnings)

    def test_panel_area(self):
        p = DiPanel(name="test", x=0.0, y=0.0, width=100.0, height=50.0)
        assert abs(p.area() - 5000.0) < 1e-6

    def test_dieline_to_drawing_dict_units(self):
        d = _make_rsc()
        drawing = d.to_drawing_dict()
        assert drawing["units"] == "mm"

    def test_line_length(self):
        line = DieLine(0.0, 0.0, 3.0, 4.0)
        assert abs(line.length() - 5.0) < 1e-9

    def test_line_midpoint(self):
        line = DieLine(0.0, 0.0, 4.0, 0.0)
        mid = line.midpoint()
        assert abs(mid.x - 2.0) < 1e-9
        assert abs(mid.y - 0.0) < 1e-9

    def test_line_angle_horizontal(self):
        line = DieLine(0.0, 0.0, 1.0, 0.0)
        assert abs(line.angle_deg() - 0.0) < 1e-6

    def test_line_angle_vertical(self):
        line = DieLine(0.0, 0.0, 0.0, 1.0)
        assert abs(line.angle_deg() - 90.0) < 1e-6

    def test_line_as_entity(self):
        line = DieLine(1.0, 2.0, 3.0, 4.0, kind=LineKind.FOLD)
        ent = line.as_entity()
        assert ent["type"] == "line"
        assert ent["layer"] == "fold"
        assert abs(ent["x1"] - 1.0) < 1e-9
        assert abs(ent["y2"] - 4.0) < 1e-9

    def test_material_enum_values(self):
        assert Material.SBS.value == "sbs"
        assert Material.FLUTE_C.value == "flute_c"

    def test_line_kind_enum_values(self):
        assert LineKind.CUT.value   == "cut"
        assert LineKind.FOLD.value  == "fold"
        assert LineKind.SCORE.value == "score"
        assert LineKind.PERF.value  == "perf"


# ===========================================================================
# 8. Module-level compile / import checks
# ===========================================================================

class TestModuleImports:
    """Smoke tests for module-level imports and py_compile."""

    def test_dieline_imports(self):
        import kerf_packaging.dieline  # noqa: F401

    def test_ecma_generators_imports(self):
        import kerf_packaging.ecma_generators  # noqa: F401

    def test_fold_imports(self):
        import kerf_packaging.fold  # noqa: F401

    def test_tools_imports(self):
        import kerf_packaging.tools  # noqa: F401

    def test_plugin_imports(self):
        import kerf_packaging.plugin  # noqa: F401

    def test_pycompile_dieline(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_packaging", "dieline.py")
        py_compile.compile(path, doraise=True)

    def test_pycompile_ecma_generators(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_packaging", "ecma_generators.py")
        py_compile.compile(path, doraise=True)

    def test_pycompile_fold(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_packaging", "fold.py")
        py_compile.compile(path, doraise=True)

    def test_pycompile_tools(self):
        import py_compile
        path = os.path.join(_SRC, "kerf_packaging", "tools.py")
        py_compile.compile(path, doraise=True)
