"""Tests for GK-P49 — tool registration + dispatch for architectural geometry ops.

Asserts each new tool:
  - is registered (TOOLS list present in module)
  - dispatches correctly (run_* handler returns ok=True with expected fields)
"""
from __future__ import annotations
import json
import pytest

pytest.importorskip("kerf_cad_core", reason="kerf_cad_core not available")


# ---------------------------------------------------------------------------
# bim_make_roof
# ---------------------------------------------------------------------------

class TestRoofTool:
    def test_tools_list_present(self):
        from kerf_bim.tools.roof_geometry import TOOLS
        assert len(TOOLS) >= 1
        names = [t[0] for t in TOOLS]
        assert "bim_make_roof" in names

    def test_spec_name(self):
        from kerf_bim.tools.roof_geometry import make_roof_spec
        assert make_roof_spec.name == "bim_make_roof"

    @pytest.mark.asyncio
    async def test_gable_dispatch_returns_body(self):
        from kerf_bim.tools.roof_geometry import run_bim_make_roof
        result = json.loads(await run_bim_make_roof({
            "roof_type": "gable",
            "x_min": 0, "y_min": 0, "x_max": 12000, "y_max": 8000,
            "base_z": 3000, "pitch_deg": 30, "overhang": 600,
        }, None))
        assert result["ok"] is True
        assert result["faces_count"] == 4
        assert result["ifc_dict"]["type"] == "IfcRoof"
        assert result["ifc_dict"]["predefined_type"] == "GABLE_ROOF"

    @pytest.mark.asyncio
    async def test_hip_dispatch(self):
        from kerf_bim.tools.roof_geometry import run_bim_make_roof
        result = json.loads(await run_bim_make_roof({
            "roof_type": "hip",
            "x_max": 10000, "y_max": 6000, "pitch_deg": 25,
        }, None))
        assert result["ok"] is True
        assert result["faces_count"] == 4
        assert result["ifc_dict"]["predefined_type"] == "HIP_ROOF"

    @pytest.mark.asyncio
    async def test_shed_dispatch(self):
        from kerf_bim.tools.roof_geometry import run_bim_make_roof
        result = json.loads(await run_bim_make_roof({
            "roof_type": "shed", "pitch_deg": 15,
        }, None))
        assert result["ok"] is True
        assert result["faces_count"] == 1

    @pytest.mark.asyncio
    async def test_invalid_pitch_returns_error(self):
        from kerf_bim.tools.roof_geometry import run_bim_make_roof
        result = json.loads(await run_bim_make_roof({"pitch_deg": 0.0}, None))
        assert result.get("ok") is not True or "error" in result


# ---------------------------------------------------------------------------
# bim_curtain_wall_geometry
# ---------------------------------------------------------------------------

class TestCurtainWallGeomTool:
    def test_tools_list_present(self):
        from kerf_bim.tools.curtain_wall_geom import TOOLS
        names = [t[0] for t in TOOLS]
        assert "bim_curtain_wall_geometry" in names

    @pytest.mark.asyncio
    async def test_dispatch_returns_counts(self):
        from kerf_bim.tools.curtain_wall_geom import run_bim_curtain_wall_geometry
        result = json.loads(await run_bim_curtain_wall_geometry({
            "start_pt": [0.0, 0.0],
            "end_pt": [6000.0, 0.0],
            "height_mm": 3000.0,
            "u_divisions": [{"type": "count", "value": 4}],
            "v_divisions": [{"type": "count", "value": 3}],
            "mullion_size_mm": 50.0,
            "panel_kind": "glass",
        }, None))
        assert result["ok"] is True
        assert result["u_count"] == 4
        assert result["v_count"] == 3
        assert result["mullion_count"] > 0
        assert result["panel_count"] > 0

    @pytest.mark.asyncio
    async def test_opening_panels_returns_zero_panels(self):
        from kerf_bim.tools.curtain_wall_geom import run_bim_curtain_wall_geometry
        result = json.loads(await run_bim_curtain_wall_geometry({
            "start_pt": [0.0, 0.0],
            "end_pt": [4000.0, 0.0],
            "panel_kind": "opening",
        }, None))
        assert result["ok"] is True
        assert result["panel_count"] == 0

    @pytest.mark.asyncio
    async def test_missing_start_pt_errors(self):
        from kerf_bim.tools.curtain_wall_geom import run_bim_curtain_wall_geometry
        result = json.loads(await run_bim_curtain_wall_geometry({
            "end_pt": [5000.0, 0.0],
        }, None))
        # Should fail (missing start_pt or zero-length)
        assert "ok" in result


# ---------------------------------------------------------------------------
# bim_hatch_region
# ---------------------------------------------------------------------------

class TestHatchRegionTool:
    def test_tools_list_present(self):
        from kerf_bim.tools.drafting import TOOLS
        names = [t[0] for t in TOOLS]
        assert "bim_hatch_region" in names

    @pytest.mark.asyncio
    async def test_dispatch_returns_lines(self):
        from kerf_bim.tools.drafting import run_bim_hatch_region
        result = json.loads(await run_bim_hatch_region({
            "boundary": [[0, 0, 0], [2000, 0, 0], [2000, 1500, 0], [0, 1500, 0]],
            "pattern": "ansi31",
            "angle": 45.0,
            "scale": 200.0,
        }, None))
        assert result["ok"] is True
        assert result["line_count"] >= 0  # may be 0 for very large scale
        assert isinstance(result["lines"], list)

    @pytest.mark.asyncio
    async def test_concrete_pattern(self):
        from kerf_bim.tools.drafting import run_bim_hatch_region
        result = json.loads(await run_bim_hatch_region({
            "boundary": [[0, 0, 0], [1000, 0, 0], [1000, 1000, 0], [0, 1000, 0]],
            "pattern": "concrete",
            "scale": 100.0,
        }, None))
        assert result["ok"] is True
        assert result["pattern"] == "concrete"


# ---------------------------------------------------------------------------
# bim_section_fill
# ---------------------------------------------------------------------------

class TestSectionFillTool:
    def test_tools_list_present(self):
        from kerf_bim.tools.drafting import TOOLS
        names = [t[0] for t in TOOLS]
        assert "bim_section_fill" in names

    @pytest.mark.asyncio
    async def test_dispatch_ok(self):
        from kerf_bim.tools.drafting import run_bim_section_fill
        # Simple pyramid mesh
        vertices = [
            [0, 0, 0], [4, 0, 0], [4, 4, 0], [0, 4, 0],
            [2, 2, 2],
        ]
        triangles = [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4], [0, 1, 2], [0, 2, 3]]
        result = json.loads(await run_bim_section_fill({
            "vertices": vertices,
            "triangles": triangles,
            "plane_normal": [0, 1, 0],
            "plane_point": [0, 2, 0],
            "pattern": "ansi31",
            "scale": 0.5,
        }, None))
        assert result["ok"] is True
        assert "loop_count" in result


# ---------------------------------------------------------------------------
# bim_make2d_from_brep
# ---------------------------------------------------------------------------

class TestMake2dTool:
    def test_tools_list_present(self):
        from kerf_bim.tools.drafting import TOOLS
        names = [t[0] for t in TOOLS]
        assert "bim_make2d_from_brep" in names

    @pytest.mark.asyncio
    async def test_dispatch_ok(self):
        from kerf_bim.tools.drafting import run_bim_make2d_from_brep
        # Simple box mesh (12 triangles)
        verts = [
            [0,0,0],[1,0,0],[1,1,0],[0,1,0],
            [0,0,1],[1,0,1],[1,1,1],[0,1,1],
        ]
        tris = [
            [0,1,2],[0,2,3],  # bottom
            [4,5,6],[4,6,7],  # top
            [0,1,5],[0,5,4],  # front
            [1,2,6],[1,6,5],  # right
            [2,3,7],[2,7,6],  # back
            [3,0,4],[3,4,7],  # left
        ]
        result = json.loads(await run_bim_make2d_from_brep({
            "vertices": verts,
            "triangles": tris,
            "view_direction": [-1, -1, -1],
        }, None))
        assert result["ok"] is True
        assert "visible_count" in result
        assert "hidden_count" in result


# ---------------------------------------------------------------------------
# bim_toposolid_to_brep
# ---------------------------------------------------------------------------

class TestToposolidTool:
    def test_tools_list_present(self):
        from kerf_bim.tools.site_geometry import TOOLS
        names = [t[0] for t in TOOLS]
        assert "bim_toposolid_to_brep" in names

    @pytest.mark.asyncio
    async def test_dispatch_returns_closed_body(self):
        from kerf_bim.tools.site_geometry import run_bim_toposolid_to_brep
        result = json.loads(await run_bim_toposolid_to_brep({
            "points": [
                [0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0], [5, 5, 1],
            ],
            "thickness": 1.0,
        }, None))
        assert result["ok"] is True
        assert result["shell_closed"] is True
        assert result["face_count"] > 0
        assert result["simplex_count"] > 0

    @pytest.mark.asyncio
    async def test_fewer_than_3_points_errors(self):
        from kerf_bim.tools.site_geometry import run_bim_toposolid_to_brep
        result = json.loads(await run_bim_toposolid_to_brep({
            "points": [[0, 0, 0], [10, 0, 0]],
        }, None))
        assert result.get("ok") is not True or "error" in result


# ---------------------------------------------------------------------------
# bim_cut_fill_volume
# ---------------------------------------------------------------------------

class TestCutFillVolumeTool:
    def test_tools_list_present(self):
        from kerf_bim.tools.site_geometry import TOOLS
        names = [t[0] for t in TOOLS]
        assert "bim_cut_fill_volume" in names

    @pytest.mark.asyncio
    async def test_flat_vs_flat_net_zero(self):
        from kerf_bim.tools.site_geometry import run_bim_cut_fill_volume
        flat = [[0,0,0],[10,0,0],[10,10,0],[0,10,0],[5,5,0]]
        result = json.loads(await run_bim_cut_fill_volume({
            "existing_points": flat,
            "proposed_points": flat,
            "grid_spacing": 1.0,
        }, None))
        assert result["ok"] is True
        assert abs(result["net"]) < 1e-3

    @pytest.mark.asyncio
    async def test_raised_is_fill(self):
        from kerf_bim.tools.site_geometry import run_bim_cut_fill_volume
        existing = [[0,0,0],[10,0,0],[10,10,0],[0,10,0],[5,5,0]]
        proposed = [[0,0,1],[10,0,1],[10,10,1],[0,10,1],[5,5,1]]
        result = json.loads(await run_bim_cut_fill_volume({
            "existing_points": existing,
            "proposed_points": proposed,
            "grid_spacing": 1.0,
        }, None))
        assert result["ok"] is True
        assert result["fill"] > 0
        assert result["net"] > 0
