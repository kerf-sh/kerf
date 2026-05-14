import json
import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kerf_electronics.tools.pad_overrides import (
    set_pad_mask_override,
    set_pad_paste_override,
    clear_pad_overrides,
)


def board():
    return {"type": "pcb_board", "width": 50, "height": 50}


def make_circuit_json():
    return {
        "type": "pcb_board",
        "width": 50,
        "height": 50,
        "pcb_smtpad": [
            {"pcb_smtpad_id": "PAD1", "x": 10, "y": 20, "width": 2, "height": 3},
            {"pcb_smtpad_id": "PAD2", "x": 30, "y": 40, "width": 1, "height": 1},
        ],
    }


async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


@pytest.mark.asyncio
async def test_set_mask_override_expands_pad():
    r = await call(set_pad_mask_override, circuit_json=make_circuit_json(), pad_id="PAD1", expansion_mm=0.2)
    assert "error" not in r
    assert r["expansion_mm"] == 0.2
    assert r["circuit_json"]["pcb_smtpad"][0]["mask_override"]["expansion_mm"] == 0.2


@pytest.mark.asyncio
async def test_set_mask_override_not_found():
    r = await call(set_pad_mask_override, circuit_json=make_circuit_json(), pad_id="BAD", expansion_mm=0.1)
    assert "error" in r
    assert "not found" in r["error"].lower()


@pytest.mark.asyncio
async def test_set_mask_override_negative_fails():
    r = await call(set_pad_mask_override, circuit_json=make_circuit_json(), pad_id="PAD1", expansion_mm=-0.1)
    assert "error" in r
    assert "non-negative" in r["error"].lower()


@pytest.mark.asyncio
async def test_set_paste_override_scale():
    r = await call(set_pad_paste_override, circuit_json=make_circuit_json(), pad_id="PAD1", scale=0.8)
    assert "error" not in r
    assert r["paste_override"]["scale"] == 0.8


@pytest.mark.asyncio
async def test_set_paste_override_offset():
    r = await call(set_pad_paste_override, circuit_json=make_circuit_json(), pad_id="PAD1", offset_mm=0.05)
    assert "error" not in r
    assert r["paste_override"]["offset_mm"] == 0.05


@pytest.mark.asyncio
async def test_set_paste_override_polygon():
    poly = [[0, 0], [2, 0], [2, 2], [0, 2]]
    r = await call(set_pad_paste_override, circuit_json=make_circuit_json(), pad_id="PAD1", polygon=poly)
    assert "error" not in r
    assert r["paste_override"]["polygon"] == poly


@pytest.mark.asyncio
async def test_set_paste_override_invalid_polygon():
    r = await call(set_pad_paste_override, circuit_json=make_circuit_json(), pad_id="PAD1", polygon=[[0, 0]])
    assert "error" in r
    assert "at least 3" in r["error"].lower()


@pytest.mark.asyncio
async def test_clear_overrides_removes_both():
    await call(set_pad_mask_override, circuit_json=make_circuit_json(), pad_id="PAD1", expansion_mm=0.2)
    await call(set_pad_paste_override, circuit_json=make_circuit_json(), pad_id="PAD1", scale=0.8)
    r = await call(clear_pad_overrides, circuit_json=make_circuit_json(), pad_id="PAD1")
    assert "error" not in r
    pad = r["circuit_json"]["pcb_smtpad"][0]
    assert "mask_override" not in pad
    assert "paste_override" not in pad


@pytest.mark.asyncio
async def test_clear_overrides_not_found():
    r = await call(clear_pad_overrides, circuit_json=make_circuit_json(), pad_id="BAD")
    assert "error" in r