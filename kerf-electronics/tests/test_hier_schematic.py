"""
Tests for hier_schematic.py LLM tools.

Tools are called directly via their async functions without going through HTTP.
Uses importlib save/restore pattern for isolation.
"""

import json
import sys
import os
import importlib.util
import importlib.machinery
import pytest

# ── Module loading (save/restore pattern) ────────────────────────────────────

_MODULE_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "kerf_electronics", "tools", "hier_schematic.py")


def _load_module():
    # Ensure the plugin package is importable
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
    spec = importlib.util.spec_from_file_location("tools.hier_schematic", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_mod = _load_module()

add_sub_sheet = _mod.add_sub_sheet
remove_sub_sheet = _mod.remove_sub_sheet
add_global_label = _mod.add_global_label
add_hierarchical_label = _mod.add_hierarchical_label
flatten_hierarchy = _mod.flatten_hierarchy
validate_hierarchy = _mod.validate_hierarchy

# Internal helpers (for building fixtures)
_add_sub_sheet = _mod._add_sub_sheet
_add_global_label = _mod._add_global_label
_add_hierarchical_label = _mod._add_hierarchical_label
_validate_hierarchy = _mod._validate_hierarchy
_flatten_hierarchy = _mod._flatten_hierarchy


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def board():
    return {"type": "pcb_board", "width": 100, "height": 100}


def child_board(sheet_id, labels=None):
    """Build a minimal child board with hierarchical labels already bound."""
    b = board()
    b["hierarchical_labels"] = [
        {"name": lbl["name"], "net_id": lbl["net_id"], "sheet_id": sheet_id}
        for lbl in (labels or [])
    ]
    return b


async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ── add_sub_sheet ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_sub_sheet_basic():
    r = await call(add_sub_sheet, circuit_json=board(), name="Power", file_id="fid-1")
    assert r["circuit_json"]["sub_sheets"][0]["name"] == "Power"
    assert r["circuit_json"]["sub_sheets"][0]["file_id"] == "fid-1"
    assert len(r["circuit_json"]["sub_sheets"][0]["id"]) == 36  # UUID


@pytest.mark.asyncio
async def test_add_sub_sheet_with_pins():
    pins = [{"name": "VIN", "type": "input", "net_id": "net-vin"}]
    r = await call(add_sub_sheet, circuit_json=board(), name="PSU", file_id="fid-2", pins=pins)
    assert r["circuit_json"]["sub_sheets"][0]["pins"] == pins


@pytest.mark.asyncio
async def test_add_sub_sheet_missing_name():
    r = await call(add_sub_sheet, circuit_json=board(), file_id="fid-1")
    assert "error" in r


@pytest.mark.asyncio
async def test_add_sub_sheet_missing_file_id():
    r = await call(add_sub_sheet, circuit_json=board(), name="PSU")
    assert "error" in r


@pytest.mark.asyncio
async def test_add_sub_sheet_accumulates():
    r1 = await call(add_sub_sheet, circuit_json=board(), name="A", file_id="fa")
    r2 = await call(add_sub_sheet, circuit_json=r1["circuit_json"], name="B", file_id="fb")
    assert len(r2["circuit_json"]["sub_sheets"]) == 2


# ── remove_sub_sheet ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_remove_sub_sheet():
    r1 = await call(add_sub_sheet, circuit_json=board(), name="A", file_id="fa")
    sid = r1["circuit_json"]["sub_sheets"][0]["id"]
    r2 = await call(remove_sub_sheet, circuit_json=r1["circuit_json"], sub_sheet_id=sid)
    assert r2["circuit_json"]["sub_sheets"] == []


@pytest.mark.asyncio
async def test_remove_sub_sheet_cleans_hier_labels():
    r1 = await call(add_sub_sheet, circuit_json=board(), name="A", file_id="fa")
    sid = r1["circuit_json"]["sub_sheets"][0]["id"]
    # Manually add a hier label for this sheet
    cj = r1["circuit_json"]
    cj["hierarchical_labels"] = [{"name": "VOUT", "net_id": "net-1", "sheet_id": sid}]
    r2 = await call(remove_sub_sheet, circuit_json=cj, sub_sheet_id=sid)
    assert r2["circuit_json"]["hierarchical_labels"] == []


# ── add_global_label ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_global_label_basic():
    r = await call(add_global_label, circuit_json=board(), name="GND", net_id="net-gnd")
    assert r["circuit_json"]["global_labels"] == [{"name": "GND", "net_id": "net-gnd"}]
    assert r["name"] == "GND"


@pytest.mark.asyncio
async def test_add_global_label_updates_existing():
    r1 = await call(add_global_label, circuit_json=board(), name="VCC", net_id="old")
    r2 = await call(add_global_label, circuit_json=r1["circuit_json"], name="VCC", net_id="new")
    assert len(r2["circuit_json"]["global_labels"]) == 1
    assert r2["circuit_json"]["global_labels"][0]["net_id"] == "new"


@pytest.mark.asyncio
async def test_add_global_label_missing_name():
    r = await call(add_global_label, circuit_json=board(), net_id="net-x")
    assert "error" in r


# ── add_hierarchical_label ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_hierarchical_label_basic():
    r = await call(add_hierarchical_label, circuit_json=board(), name="VOUT", net_id="net-vout", sheet_id="sh1")
    hl = r["circuit_json"]["hierarchical_labels"][0]
    assert hl == {"name": "VOUT", "net_id": "net-vout", "sheet_id": "sh1"}


@pytest.mark.asyncio
async def test_add_hierarchical_label_updates_existing():
    r1 = await call(add_hierarchical_label, circuit_json=board(), name="SIG", net_id="old", sheet_id="sh1")
    r2 = await call(add_hierarchical_label, circuit_json=r1["circuit_json"], name="SIG", net_id="new", sheet_id="sh1")
    assert len(r2["circuit_json"]["hierarchical_labels"]) == 1
    assert r2["circuit_json"]["hierarchical_labels"][0]["net_id"] == "new"


@pytest.mark.asyncio
async def test_add_hierarchical_label_does_not_cross_sheets():
    """Same label name on two different sheet_ids must produce two entries."""
    r1 = await call(add_hierarchical_label, circuit_json=board(), name="SIG", net_id="net-a", sheet_id="sh-a")
    r2 = await call(add_hierarchical_label, circuit_json=r1["circuit_json"], name="SIG", net_id="net-b", sheet_id="sh-b")
    assert len(r2["circuit_json"]["hierarchical_labels"]) == 2


# ── flatten_hierarchy ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_flatten_merges_pin_with_hier_label():
    top = _add_sub_sheet(board(), "PSU", "f-psu", [0, 0],
                          [{"name": "VOUT", "type": "output", "net_id": "net-parent-vout"}])
    sid = top["sub_sheets"][0]["id"]
    child = child_board(sid, [{"name": "VOUT", "net_id": "net-child-vout"}])

    r = await call(flatten_hierarchy, top_circuit_json=top, children={"f-psu": child})
    groups = r["net_groups"]
    merged = next(
        (g for g in groups if any("net-parent-vout" in k for k in g) and any("net-child-vout" in k for k in g)),
        None,
    )
    assert merged is not None


@pytest.mark.asyncio
async def test_flatten_global_labels_merge():
    top = _add_global_label(board(), "GND", "gnd-top")
    top = _add_sub_sheet(top, "Sub", "fsub", [0, 0], [])
    child = _add_global_label(board(), "GND", "gnd-child")

    r = await call(flatten_hierarchy, top_circuit_json=top, children={"fsub": child})
    groups = r["net_groups"]
    merged = next(
        (g for g in groups if any("gnd-top" in k for k in g) and any("gnd-child" in k for k in g)),
        None,
    )
    assert merged is not None


@pytest.mark.asyncio
async def test_flatten_missing_child_is_skipped():
    top = _add_sub_sheet(board(), "Ghost", "f-ghost", [0, 0], [])
    # Should not raise
    r = await call(flatten_hierarchy, top_circuit_json=top, children={})
    assert "net_groups" in r


@pytest.mark.asyncio
async def test_flatten_three_tier_gnd():
    """GND propagates through top → mid → leaf via global labels."""
    top = _add_global_label(board(), "GND", "gnd-top")
    top = _add_sub_sheet(top, "Mid", "f-mid", [0, 0], [])
    mid = _add_global_label(board(), "GND", "gnd-mid")
    mid = _add_sub_sheet(mid, "Leaf", "f-leaf", [0, 0], [])
    leaf = _add_global_label(board(), "GND", "gnd-leaf")

    r = await call(flatten_hierarchy, top_circuit_json=top, children={"f-mid": mid, "f-leaf": leaf})
    groups = r["net_groups"]
    big = next(
        (g for g in groups
         if any("gnd-top" in k for k in g)
         and any("gnd-mid" in k for k in g)
         and any("gnd-leaf" in k for k in g)),
        None,
    )
    assert big is not None


# ── validate_hierarchy ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_ok_for_valid_hierarchy():
    top = _add_sub_sheet(board(), "PSU", "f-psu", [0, 0],
                          [{"name": "VOUT", "type": "output", "net_id": "net-v"}])
    sid = top["sub_sheets"][0]["id"]
    child = child_board(sid, [{"name": "VOUT", "net_id": "net-child-v"}])

    r = await call(validate_hierarchy, top_circuit_json=top, children={"f-psu": child})
    assert r["ok"] is True
    assert r["errors"] == []


@pytest.mark.asyncio
async def test_validate_reports_missing_child():
    top = _add_sub_sheet(board(), "Ghost", "f-ghost", [0, 0], [])
    r = await call(validate_hierarchy, top_circuit_json=top, children={})
    assert r["ok"] is False
    assert any("f-ghost" in e for e in r["errors"])


@pytest.mark.asyncio
async def test_validate_reports_orphaned_hier_label():
    top = _add_sub_sheet(board(), "PSU", "f-psu", [0, 0], [])
    sid = top["sub_sheets"][0]["id"]
    child = child_board(sid, [{"name": "ORPHAN", "net_id": "net-o"}])

    r = await call(validate_hierarchy, top_circuit_json=top, children={"f-psu": child})
    assert r["ok"] is False
    assert any("ORPHAN" in e for e in r["errors"])


@pytest.mark.asyncio
async def test_validate_reports_unmatched_pin():
    top = _add_sub_sheet(board(), "PSU", "f-psu", [0, 0],
                          [{"name": "ENABLE", "type": "input", "net_id": "net-en"}])
    # Child has NO hier labels
    child = board()

    r = await call(validate_hierarchy, top_circuit_json=top, children={"f-psu": child})
    assert r["ok"] is False
    assert any("ENABLE" in e for e in r["errors"])


@pytest.mark.asyncio
async def test_validate_reports_global_label_collision():
    b = _add_global_label(board(), "GND", "net-gnd-a")
    # Manually insert second conflicting GND
    b["global_labels"].append({"name": "GND", "net_id": "net-gnd-b"})

    r = await call(validate_hierarchy, top_circuit_json=b, children={})
    assert r["ok"] is False
    assert any("GND" in e and "conflict" in e for e in r["errors"])
