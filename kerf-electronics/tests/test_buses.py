"""
Tests for buses.py LLM tools.

All tools are called directly via their async functions rather than going
through the HTTP layer.  The circuit_json is passed inline (no file_id) since
these tools operate on the data structure directly.
"""
import json
import pytest

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from kerf_electronics.tools.buses import (
    expand_bus,
    add_bus,
    add_differential_pair,
    list_differential_pairs,
)


# ── Fixtures / helpers ────────────────────────────────────────────────────────

def board():
    return {"type": "pcb_board", "width": 50, "height": 50}


async def call(fn, **kwargs):
    result = await fn(None, json.dumps(kwargs).encode())
    return json.loads(result)


# ── expand_bus ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_expand_descending_slice():
    r = await call(expand_bus, spec="DATA[7..0]")
    assert r["nets"] == ["DATA7", "DATA6", "DATA5", "DATA4", "DATA3", "DATA2", "DATA1", "DATA0"]


@pytest.mark.asyncio
async def test_expand_ascending_slice():
    r = await call(expand_bus, spec="ADDR[0..3]")
    assert r["nets"] == ["ADDR0", "ADDR1", "ADDR2", "ADDR3"]


@pytest.mark.asyncio
async def test_expand_single_bit():
    r = await call(expand_bus, spec="BIT[5..5]")
    assert r["nets"] == ["BIT5"]


@pytest.mark.asyncio
async def test_expand_plain_name():
    r = await call(expand_bus, spec="CLK")
    assert r["nets"] == ["CLK"]


@pytest.mark.asyncio
async def test_expand_invalid_returns_empty():
    r = await call(expand_bus, spec="BAD[]]")
    assert r["nets"] == []


# ── add_bus ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_bus_simple():
    r = await call(add_bus, circuit_json=board(), name="DATA_BUS", member_nets=["D0", "D1"])
    assert r["name"] == "DATA_BUS"
    assert r["circuit_json"]["bus_definitions"][0]["member_nets"] == ["D0", "D1"]


@pytest.mark.asyncio
async def test_add_bus_with_slice_notation():
    r = await call(add_bus, circuit_json=board(), name="DATA_BUS", member_nets=["DATA[7..0]"])
    assert r["circuit_json"]["bus_definitions"][0]["member_nets"] == ["DATA[7..0]"]


@pytest.mark.asyncio
async def test_add_bus_updates_existing():
    base = (await call(add_bus, circuit_json=board(), name="BUS", member_nets=["N0"]))["circuit_json"]
    r2 = await call(add_bus, circuit_json=base, name="BUS", member_nets=["N0", "N1", "N2"])
    assert len(r2["circuit_json"]["bus_definitions"]) == 1
    assert r2["circuit_json"]["bus_definitions"][0]["member_nets"] == ["N0", "N1", "N2"]


@pytest.mark.asyncio
async def test_add_bus_invalid_empty_member_nets():
    r = await call(add_bus, circuit_json=board(), name="BUS", member_nets=[])
    assert "error" in r


@pytest.mark.asyncio
async def test_add_bus_invalid_slice():
    r = await call(add_bus, circuit_json=board(), name="BUS", member_nets=["BAD[]]"])
    assert "error" in r
    assert "invalid slice syntax" in r["error"]


# ── add_differential_pair ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_differential_pair_basic():
    r = await call(add_differential_pair, circuit_json=board(), name="USB", net_p="USB_P", net_n="USB_N")
    assert r["name"] == "USB"
    dp = r["circuit_json"]["differential_pairs"][0]
    assert dp["net_p_id"] == "USB_P"
    assert dp["net_n_id"] == "USB_N"


@pytest.mark.asyncio
async def test_add_differential_pair_with_options():
    r = await call(
        add_differential_pair,
        circuit_json=board(),
        name="HDMI",
        net_p="HDMI_P",
        net_n="HDMI_N",
        target_impedance_ohms=100,
        skew_max_mm=0.05,
    )
    dp = r["circuit_json"]["differential_pairs"][0]
    assert dp["target_impedance_ohms"] == 100
    assert dp["skew_max_mm"] == 0.05


@pytest.mark.asyncio
async def test_add_differential_pair_same_p_n_returns_error():
    r = await call(add_differential_pair, circuit_json=board(), name="BAD", net_p="X", net_n="X")
    assert "error" in r


@pytest.mark.asyncio
async def test_add_differential_pair_updates_existing():
    base = (await call(add_differential_pair, circuit_json=board(), name="DP", net_p="P1", net_n="N1"))["circuit_json"]
    r2 = await call(add_differential_pair, circuit_json=base, name="DP", net_p="P2", net_n="N2")
    assert len(r2["circuit_json"]["differential_pairs"]) == 1
    assert r2["circuit_json"]["differential_pairs"][0]["net_p_id"] == "P2"


# ── list_differential_pairs ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_empty_when_no_pairs():
    r = await call(list_differential_pairs, circuit_json=board())
    assert r["pairs"] == []


@pytest.mark.asyncio
async def test_list_returns_all_pairs():
    base = (await call(add_differential_pair, circuit_json=board(), name="A", net_p="AP", net_n="AN"))["circuit_json"]
    base2 = (await call(add_differential_pair, circuit_json=base, name="B", net_p="BP", net_n="BN"))["circuit_json"]
    r = await call(list_differential_pairs, circuit_json=base2)
    assert len(r["pairs"]) == 2
    assert {p["name"] for p in r["pairs"]} == {"A", "B"}
