"""
Tests for net_classes.py LLM tools.

All tools are called directly via their async functions rather than going
through the HTTP layer. The circuit_json is passed inline (no file_id) since
these tools operate on the data structure directly.
"""
import json
import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kerf_electronics.tools.net_classes import (
    define_net_class,
    assign_net_to_class,
    remove_net_class,
    list_net_classes,
    get_effective_net_rules,
)


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def board():
    return {"type": "pcb_board", "width": 50, "height": 50}


async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ── list_net_classes ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_returns_five_builtin_classes():
    r = await call(list_net_classes, circuit_json=board())
    names = [c["name"] for c in r["classes"]]
    assert set(names) >= {"Default", "Power", "Signal", "HighSpeed", "Differential"}


@pytest.mark.asyncio
async def test_list_assignments_empty_on_fresh_board():
    r = await call(list_net_classes, circuit_json=board())
    assert r["assignments"] == {}


# ── define_net_class ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_define_adds_new_class():
    r = await call(
        define_net_class,
        circuit_json=board(),
        name="HV",
        trace_width_mm=1.0,
        clearance_mm=0.8,
        via_diameter_mm=1.2,
        via_drill_mm=0.6,
    )
    assert r["defined"] == "HV"
    classes = r["circuit_json"]["net_classes"]
    assert any(c["name"] == "HV" for c in classes)


@pytest.mark.asyncio
async def test_define_updates_existing_class_no_duplicate():
    base = (await call(
        define_net_class,
        circuit_json=board(),
        name="HV",
        trace_width_mm=1.0,
        clearance_mm=0.8,
        via_diameter_mm=1.2,
        via_drill_mm=0.6,
    ))["circuit_json"]

    r2 = await call(
        define_net_class,
        circuit_json=base,
        name="HV",
        trace_width_mm=1.5,
        clearance_mm=0.8,
        via_diameter_mm=1.2,
        via_drill_mm=0.6,
    )
    hv_classes = [c for c in r2["circuit_json"]["net_classes"] if c["name"] == "HV"]
    assert len(hv_classes) == 1
    assert hv_classes[0]["trace_width_mm"] == 1.5


@pytest.mark.asyncio
async def test_define_stores_impedance():
    r = await call(
        define_net_class,
        circuit_json=board(),
        name="RF50",
        trace_width_mm=0.18,
        clearance_mm=0.15,
        via_diameter_mm=0.45,
        via_drill_mm=0.20,
        target_impedance_ohms=50,
    )
    cls = next(c for c in r["circuit_json"]["net_classes"] if c["name"] == "RF50")
    assert cls["target_impedance_ohms"] == 50


# ── assign_net_to_class ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assign_builtin_class():
    r = await call(assign_net_to_class, circuit_json=board(), net_id="GND", class_name="Power")
    assert r["circuit_json"]["net_class_assignments"]["GND"] == "Power"


@pytest.mark.asyncio
async def test_assign_nonexistent_class_returns_error():
    r = await call(assign_net_to_class, circuit_json=board(), net_id="GND", class_name="Ghost")
    assert "error" in r


@pytest.mark.asyncio
async def test_assign_is_idempotent():
    r1 = await call(assign_net_to_class, circuit_json=board(), net_id="VCC", class_name="Power")
    r2 = await call(assign_net_to_class, circuit_json=r1["circuit_json"], net_id="VCC", class_name="Power")
    assert r2["circuit_json"]["net_class_assignments"]["VCC"] == "Power"
    assert r1["circuit_json"] == r2["circuit_json"]


# ── remove_net_class ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_remove_reassigns_nets_to_default():
    base = (await call(
        define_net_class,
        circuit_json=board(),
        name="HV",
        trace_width_mm=1.0,
        clearance_mm=0.8,
        via_diameter_mm=1.2,
        via_drill_mm=0.6,
    ))["circuit_json"]

    base2 = (await call(assign_net_to_class, circuit_json=base, net_id="HVNET", class_name="HV"))["circuit_json"]

    r = await call(remove_net_class, circuit_json=base2, class_name="HV")
    assert "HVNET" in r["reassigned_to_default"]
    assert r["circuit_json"]["net_class_assignments"]["HVNET"] == "Default"
    assert not any(c["name"] == "HV" for c in r["circuit_json"]["net_classes"])


@pytest.mark.asyncio
async def test_remove_default_returns_error():
    r = await call(remove_net_class, circuit_json=board(), class_name="Default")
    assert "error" in r


# ── get_effective_net_rules ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_effective_rules_unassigned_net_uses_default():
    r = await call(get_effective_net_rules, circuit_json=board(), net_id="GND")
    assert r["net_class"] == "Default"
    assert r["trace_width_mm"] == 0.25


@pytest.mark.asyncio
async def test_effective_rules_power_net():
    base = (await call(assign_net_to_class, circuit_json=board(), net_id="VCC", class_name="Power"))["circuit_json"]
    r = await call(get_effective_net_rules, circuit_json=base, net_id="VCC")
    assert r["net_class"] == "Power"
    assert r["trace_width_mm"] == 0.50


@pytest.mark.asyncio
async def test_effective_rules_per_net_override_wins():
    base = (await call(assign_net_to_class, circuit_json=board(), net_id="GND", class_name="Power"))["circuit_json"]
    base["net_rules"] = {"GND": {"trace_width_mm": 0.9}}
    r = await call(get_effective_net_rules, circuit_json=base, net_id="GND")
    assert r["trace_width_mm"] == 0.9
    assert r["clearance_mm"] == 0.25   # still from Power class
    assert r["net_class"] == "Power"
