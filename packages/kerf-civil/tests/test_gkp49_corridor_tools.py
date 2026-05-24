"""Tests for GK-P49 — corridor tool registration + dispatch.

Asserts:
  - civil_corridor_brep / volume / ifc_alignment tools are registered
  - handlers dispatch correctly
"""
from __future__ import annotations
import json
import pytest

pytest.importorskip("kerf_cad_core", reason="kerf_cad_core not available")


class TestCorridorToolRegistration:
    def test_tools_list_present(self):
        from kerf_civil.tools_corridor import TOOLS
        names = [t[0] for t in TOOLS]
        assert "civil_corridor_brep" in names
        assert "civil_corridor_volume" in names
        assert "civil_corridor_ifc_alignment" in names

    def test_specs_have_correct_names(self):
        from kerf_civil.tools_corridor import (
            civil_corridor_brep_spec,
            civil_corridor_volume_spec,
            civil_corridor_ifc_alignment_spec,
        )
        assert civil_corridor_brep_spec.name == "civil_corridor_brep"
        assert civil_corridor_volume_spec.name == "civil_corridor_volume"
        assert civil_corridor_ifc_alignment_spec.name == "civil_corridor_ifc_alignment"


class TestCorridorBrepTool:
    @pytest.mark.asyncio
    async def test_dispatch_returns_body(self):
        from kerf_civil.tools_corridor import run_civil_corridor_brep
        result = json.loads(await run_civil_corridor_brep({
            "alignment_length_m": 200.0,
            "interval_m": 50.0,
            "lane_width_m": 3.65,
            "shoulder_width_m": 2.4,
            "lanes_each_side": 1,
        }, None))
        assert result["ok"] is True
        assert result["face_count"] > 0
        assert result["shell_count"] >= 1

    @pytest.mark.asyncio
    async def test_finer_interval_more_faces(self):
        from kerf_civil.tools_corridor import run_civil_corridor_brep
        coarse = json.loads(await run_civil_corridor_brep({
            "alignment_length_m": 200.0,
            "interval_m": 100.0,
        }, None))
        fine = json.loads(await run_civil_corridor_brep({
            "alignment_length_m": 200.0,
            "interval_m": 20.0,
        }, None))
        assert coarse["ok"] and fine["ok"]
        assert fine["face_count"] > coarse["face_count"]


class TestCorridorVolumeTool:
    @pytest.mark.asyncio
    async def test_dispatch_positive_volume(self):
        from kerf_civil.tools_corridor import run_civil_corridor_volume
        result = json.loads(await run_civil_corridor_volume({
            "alignment_length_m": 300.0,
        }, None))
        assert result["ok"] is True
        assert result["volume_m3"] > 0.0

    @pytest.mark.asyncio
    async def test_longer_corridor_larger_volume(self):
        from kerf_civil.tools_corridor import run_civil_corridor_volume
        r1 = json.loads(await run_civil_corridor_volume({"alignment_length_m": 100.0}, None))
        r2 = json.loads(await run_civil_corridor_volume({"alignment_length_m": 200.0}, None))
        assert r1["ok"] and r2["ok"]
        assert r2["volume_m3"] > r1["volume_m3"]


class TestCorridorIfcAlignmentTool:
    @pytest.mark.asyncio
    async def test_dispatch_returns_ifc_dict(self):
        from kerf_civil.tools_corridor import run_civil_corridor_ifc_alignment
        result = json.loads(await run_civil_corridor_ifc_alignment({
            "alignment_length_m": 300.0,
            "lane_width_m": 3.65,
            "shoulder_width_m": 2.4,
        }, None))
        assert result["ok"] is True
        ifc = result["ifc_dict"]
        assert ifc["type"] == "IfcAlignmentProduct"
        assert abs(ifc["total_length_m"] - 300.0) < 1e-3
        assert abs(ifc["lane_width_m"] - 3.65) < 1e-6

    @pytest.mark.asyncio
    async def test_all_expected_ifc_keys(self):
        from kerf_civil.tools_corridor import run_civil_corridor_ifc_alignment
        result = json.loads(await run_civil_corridor_ifc_alignment({
            "alignment_length_m": 200.0,
        }, None))
        assert result["ok"] is True
        for key in (
            "type", "total_length_m", "lane_width_m",
            "shoulder_width_m", "lanes_each_side",
            "cut_slope_h_v", "fill_slope_h_v", "crown_slope_pct",
        ):
            assert key in result["ifc_dict"], f"Missing key: {key}"
