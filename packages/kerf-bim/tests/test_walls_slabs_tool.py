"""
Dispatch tests for bim_make_wall and bim_make_slab LLM tools.

Oracles
-------
bim_make_wall preset  — 'Ext - Single Brick 230' has total thickness 245 mm (230 brick + 15 plaster)
bim_make_wall custom  — 200 concrete + 13 plaster → 213 mm total
bim_make_slab preset  — 'RC Flat Slab 200' has 200 mm total thickness
bim_make_slab custom  — single 200 mm concrete layer with floor function
"""
from __future__ import annotations

import asyncio
import json
import pytest

from kerf_bim.tools.walls_slabs import (
    _make_wall_spec,
    run_bim_make_wall,
    _make_slab_spec,
    run_bim_make_slab,
    TOOLS,
)


def _run(coro):
    return asyncio.run(coro)


def _call_wall(payload: dict) -> dict:
    return json.loads(_run(run_bim_make_wall(payload, None)))


def _call_slab(payload: dict) -> dict:
    return json.loads(_run(run_bim_make_slab(payload, None)))


# ---------------------------------------------------------------------------
# Spec smoke tests
# ---------------------------------------------------------------------------

class TestSpec:
    def test_wall_spec_name(self):
        assert _make_wall_spec.name == "bim_make_wall"

    def test_slab_spec_name(self):
        assert _make_slab_spec.name == "bim_make_slab"

    def test_wall_spec_required(self):
        assert "start_m" in _make_wall_spec.input_schema["required"]
        assert "end_m" in _make_wall_spec.input_schema["required"]

    def test_slab_spec_required(self):
        assert "boundary_m" in _make_slab_spec.input_schema["required"]

    def test_tools_list_length(self):
        assert len(TOOLS) == 2

    def test_tools_names(self):
        names = [t[0] for t in TOOLS]
        assert "bim_make_wall" in names
        assert "bim_make_slab" in names


# ---------------------------------------------------------------------------
# bim_make_wall — preset mode
# ---------------------------------------------------------------------------

class TestMakeWallPreset:
    def _brick_wall(self, **kw) -> dict:
        return _call_wall({
            "start_m": [0.0, 0.0],
            "end_m": [5.0, 0.0],
            "preset_name": "Ext - Single Brick 230",
            **kw,
        })

    def test_ok(self):
        assert self._brick_wall().get("ok") is True

    def test_type_name(self):
        assert self._brick_wall()["type_name"] == "Ext - Single Brick 230"

    def test_total_thickness_230_brick_plus_plaster(self):
        # 230 mm brick + 15 mm lime plaster = 245 mm
        r = self._brick_wall()
        assert r["total_thickness_mm"] == pytest.approx(245.0)

    def test_length_m(self):
        r = self._brick_wall()
        assert r["length_m"] == pytest.approx(5.0)

    def test_height_default(self):
        r = self._brick_wall()
        assert r["height_m"] == pytest.approx(3.0)

    def test_height_custom(self):
        r = self._brick_wall(height_m=2.8)
        assert r["height_m"] == pytest.approx(2.8)

    def test_n_layers(self):
        r = self._brick_wall()
        assert r["n_layers"] >= 1

    def test_layer_material_present(self):
        r = self._brick_wall()
        materials = [l["material"] for l in r["layers"]]
        assert "brick_clay" in materials

    def test_ifc_dict_present(self):
        r = self._brick_wall()
        assert "ifc_dict" in r

    def test_bad_preset_name(self):
        r = _call_wall({"start_m": [0, 0], "end_m": [5, 0], "preset_name": "no_such_wall"})
        assert "error" in r


# ---------------------------------------------------------------------------
# bim_make_wall — custom layers
# ---------------------------------------------------------------------------

class TestMakeWallCustom:
    def _custom_wall(self, **kw) -> dict:
        return _call_wall({
            "start_m": [0.0, 0.0],
            "end_m": [4.0, 0.0],
            "height_m": 2.8,
            "layers": [
                ["concrete", 200.0, "structure"],
                ["plaster", 13.0, "finish1"],
            ],
            **kw,
        })

    def test_ok(self):
        assert self._custom_wall().get("ok") is True

    def test_n_layers(self):
        assert self._custom_wall()["n_layers"] == 2

    def test_total_thickness(self):
        assert self._custom_wall()["total_thickness_mm"] == pytest.approx(213.0)

    def test_missing_end_returns_error(self):
        r = _call_wall({"start_m": [0, 0]})
        assert "error" in r

    def test_no_layers_no_preset_returns_error(self):
        r = _call_wall({"start_m": [0, 0], "end_m": [5, 0]})
        assert "error" in r

    def test_diagonal_length(self):
        r = _call_wall({
            "start_m": [0.0, 0.0],
            "end_m": [3.0, 4.0],
            "height_m": 3.0,
            "layers": [["concrete", 200.0, "structure"]],
        })
        assert r.get("ok") is True
        assert r["length_m"] == pytest.approx(5.0)  # 3-4-5 triangle


# ---------------------------------------------------------------------------
# bim_make_slab — preset mode
# ---------------------------------------------------------------------------

class TestMakeSlabPreset:
    def _rc_slab(self, **kw) -> dict:
        return _call_slab({
            "boundary_m": [[0, 0], [5, 0], [5, 5], [0, 5]],
            "preset_name": "RC Flat Slab 200",
            **kw,
        })

    def test_ok(self):
        assert self._rc_slab().get("ok") is True

    def test_type_name(self):
        assert self._rc_slab()["type_name"] == "RC Flat Slab 200"

    def test_total_thickness(self):
        assert self._rc_slab()["total_thickness_mm"] == pytest.approx(200.0)

    def test_n_boundary_pts(self):
        assert self._rc_slab()["n_boundary_pts"] == 4

    def test_ifc_dict_present(self):
        r = self._rc_slab()
        assert "ifc_dict" in r

    def test_bad_preset_name(self):
        r = _call_slab({"boundary_m": [[0,0],[1,0],[1,1],[0,1]], "preset_name": "no_such"})
        assert "error" in r


# ---------------------------------------------------------------------------
# bim_make_slab — custom layers
# ---------------------------------------------------------------------------

class TestMakeSlabCustom:
    def _custom_slab(self, **kw) -> dict:
        return _call_slab({
            "boundary_m": [[0, 0], [6, 0], [6, 4], [0, 4]],
            "layers": [["concrete", 200.0, "structure"]],
            "slab_function": "floor",
            **kw,
        })

    def test_ok(self):
        assert self._custom_slab().get("ok") is True

    def test_function(self):
        assert self._custom_slab()["function"] == "floor"

    def test_n_layers(self):
        assert self._custom_slab()["n_layers"] == 1

    def test_total_thickness(self):
        assert self._custom_slab()["total_thickness_mm"] == pytest.approx(200.0)

    def test_missing_boundary_returns_error(self):
        r = _call_slab({})
        assert "error" in r

    def test_too_few_vertices(self):
        r = _call_slab({"boundary_m": [[0, 0], [1, 0]]})
        assert "error" in r

    def test_no_layers_no_preset_returns_error(self):
        r = _call_slab({"boundary_m": [[0,0],[5,0],[5,5],[0,5]]})
        assert "error" in r

    def test_roof_function(self):
        r = _call_slab({
            "boundary_m": [[0, 0], [8, 0], [8, 6], [0, 6]],
            "layers": [["concrete", 200.0, "structure"], ["insulation", 80.0, "thermal"]],
            "slab_function": "roof",
        })
        assert r.get("ok") is True
        assert r["function"] == "roof"
        assert r["n_layers"] == 2
