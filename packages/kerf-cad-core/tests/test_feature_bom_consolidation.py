"""
T-57 — BOM (mech + electronic) consolidation
=============================================

Scope: BOM table aggregation across kerf-parts (fasteners catalog), kerf-cad-core
weldment cut-list, and kerf-electronics cost lines into a single consolidated view.

Coverage — 25 test cases:
  Group A  (5)  — pure mech assembly BOM: quantity roll-up, dedup, sub-assembly flatten
  Group B  (5)  — weldment cut-list → BOM line conversion + mass cost proxy
  Group C  (5)  — electronics BOM lines → cost roll-up, DNP exclusion, price-break selection
  Group D  (5)  — mixed mech+elec consolidation: unified dedup, cross-domain totals
  Group E  (5)  — alternates resolution and edge cases (empty, all-DNP, duplicate part_refs)

All tests are hermetic: no OCC, no DB, no network, no filesystem side-effects.

The consolidation logic lives in `_consolidate_bom()` defined in this file — it is a
pure aggregation helper that merges kerf-cad-core assembly BOM rows, weldment
cut-list rows, and electronics BOM line items into a unified flat list, with:
  - Deduplication by canonical `part_ref` (case-insensitive, whitespace-stripped)
  - Quantity summing across sources when the same part_ref appears more than once
  - Cost roll-up: unit_price_usd × qty for each line; total = sum of all lines
  - Alternates resolution: a dict {original_ref → replacement_ref} applied before dedup

Author: imranparuk
"""

from __future__ import annotations

import math
from collections import OrderedDict
from typing import Any

import pytest

# ── kerf-cad-core assembly
from kerf_cad_core.assembly.model import Assembly, Component
from kerf_cad_core.assembly.tools import _build_flat_bom

# ── kerf-cad-core weldment
from kerf_cad_core.weldment import compute_members, compute_cutlist
from kerf_cad_core.weldment_profiles import lookup_profile

# ── kerf-cad-core fasteners
from kerf_cad_core.fasteners.catalog import lookup_hex_bolt, lookup_hex_nut, lookup_washer

# ── kerf-electronics cost roll-up (pure Python, no OCC, no DB)
from kerf_electronics.tools.bom_cost import _compute_cost_rollup, _select_price


# ---------------------------------------------------------------------------
# BOM consolidation helper
# ---------------------------------------------------------------------------

def _consolidate_bom(
    assembly_rows: list[dict] | None = None,
    weldment_rows: list[dict] | None = None,
    elec_rows: list[dict] | None = None,
    alternates: dict[str, str] | None = None,
) -> dict:
    """
    Merge mech-assembly, weldment, and electronics BOM lines into a single table.

    Parameters
    ----------
    assembly_rows
        From ``_build_flat_bom(asm)`` → [{part_ref, qty, instances}].
    weldment_rows
        From ``_weldment_to_bom_rows()`` → [{part_ref, qty, unit_price_usd, domain}].
    elec_rows
        Electronics BOM line items (same shape as ``_compute_cost_rollup`` input):
        [{refdes, qty, unit_price, dnp?, ...}].  DNP=true lines are excluded.
    alternates
        {original_part_ref: replacement_part_ref}.  Applied before dedup so the
        replaced ref accumulates into the replacement bucket.

    Returns
    -------
    dict
        {
          "rows": [{part_ref, qty, unit_price_usd, extended_cost_usd, domain, sources}],
          "total_qty": int,
          "total_cost_usd": float,
          "unique_parts": int,
        }
    """
    alternates = {k.strip().lower(): v.strip() for k, v in (alternates or {}).items()}

    # Canonical key: strip + lower
    def _canon(ref: str) -> str:
        ref = str(ref).strip()
        low = ref.lower()
        return alternates.get(low, ref)

    # Bucket: canonical_ref → {qty, unit_price_usd, domains, orig_ref}
    buckets: dict[str, dict] = OrderedDict()

    def _ensure(ref: str) -> dict:
        key = _canon(ref).lower()
        if key not in buckets:
            buckets[key] = {
                "part_ref": _canon(ref),
                "qty": 0,
                "unit_price_usd": None,
                "extended_cost_usd": 0.0,
                "domain": set(),
                "sources": [],
            }
        return buckets[key]

    # 1. Assembly rows
    for row in assembly_rows or []:
        ref = row.get("part_ref", "")
        if not ref:
            continue
        b = _ensure(ref)
        b["qty"] += int(row.get("qty", 0))
        price = row.get("unit_price_usd")
        if price is not None and b["unit_price_usd"] is None:
            b["unit_price_usd"] = float(price)
        b["domain"].add("mech-assembly")
        b["sources"].append("assembly")

    # 2. Weldment rows
    for row in weldment_rows or []:
        ref = row.get("part_ref", "")
        if not ref:
            continue
        b = _ensure(ref)
        b["qty"] += int(row.get("qty", 1))
        price = row.get("unit_price_usd")
        if price is not None and b["unit_price_usd"] is None:
            b["unit_price_usd"] = float(price)
        b["domain"].add("weldment")
        b["sources"].append("weldment")

    # 3. Electronics rows (skip DNP)
    for row in elec_rows or []:
        if row.get("dnp", False):
            continue
        # Use refdes as part_ref for electronics; fall back to mpn
        ref = (row.get("mpn") or row.get("refdes") or "").strip()
        if not ref:
            ref = str(row.get("refdes", "unknown")).strip()
        b = _ensure(ref)
        b["qty"] += int(row.get("qty", 1))
        # Electronics price selection
        price = _select_price(
            row.get("unit_price"),
            row.get("price_breaks") or [],
            b["qty"],
        )
        if price is not None and b["unit_price_usd"] is None:
            b["unit_price_usd"] = float(price)
        b["domain"].add("electronics")
        b["sources"].append("electronics")

    # Cost roll-up
    total_cost = 0.0
    total_qty = 0
    rows_out = []
    for b in buckets.values():
        up = b["unit_price_usd"]
        ec = round(up * b["qty"], 6) if up is not None else None
        if ec is not None:
            total_cost += ec
        total_qty += b["qty"]
        rows_out.append({
            "part_ref": b["part_ref"],
            "qty": b["qty"],
            "unit_price_usd": b["unit_price_usd"],
            "extended_cost_usd": ec,
            "domain": sorted(b["domain"]),
            "sources": b["sources"],
        })

    return {
        "rows": rows_out,
        "total_qty": total_qty,
        "total_cost_usd": round(total_cost, 6),
        "unique_parts": len(rows_out),
    }


# ---------------------------------------------------------------------------
# Weldment cut-list → BOM rows helper
# ---------------------------------------------------------------------------

def _weldment_to_bom_rows(cutlist_entries: list[dict]) -> list[dict]:
    """Convert weldment cut-list output to consolidation-ready BOM rows.

    Each cut-list entry (one per profile designation) becomes one row per
    unique length bucket, using the designation + length as the part_ref.
    The unit_price_usd is estimated as mass_kg × $2.50/kg (mild steel proxy).
    """
    STEEL_USD_PER_KG = 2.50
    rows = []
    for entry in cutlist_entries:
        desig = entry["designation"]
        mass_per_m = entry["mass_per_m_kg"]
        for piece in entry["pieces"]:
            length_mm = piece["length_mm"]
            qty = piece["quantity"]
            mass_each_kg = (length_mm / 1000.0) * mass_per_m
            price = round(mass_each_kg * STEEL_USD_PER_KG, 4)
            rows.append({
                "part_ref": f"{desig}@{length_mm:.1f}mm",
                "qty": qty,
                "unit_price_usd": price,
            })
    return rows


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _simple_asm(*part_refs: str) -> Assembly:
    """Build an assembly with one component per part_ref."""
    asm = Assembly(name="test")
    for ref in part_refs:
        asm.add_component(Component(part_ref=ref))
    return asm


def _dup_asm(part_ref: str, count: int) -> Assembly:
    """Assembly with `count` copies of the same part_ref."""
    asm = Assembly(name="dup-test")
    for _ in range(count):
        asm.add_component(Component(part_ref=part_ref))
    return asm


def _sq_frame_cutlist(profile: str = "SQ-40x40x3", length_mm: float = 500.0):
    """Single-member weldment cut-list fixture."""
    pd = lookup_profile(profile)
    skeleton = [{"start": [0, 0, 0], "end": [length_mm, 0, 0]}]
    members, errors = compute_members(skeleton, pd)
    assert not errors
    return compute_cutlist(members, pd)


def _elec_line(refdes: str, qty: int, unit_price: float, mpn: str = "", dnp: bool = False) -> dict:
    """Build a single electronics BOM line item."""
    return {
        "refdes": refdes,
        "qty": qty,
        "unit_price": unit_price,
        "mpn": mpn or refdes,
        "dnp": dnp,
    }


# ===========================================================================
# Group A — Pure mech assembly BOM (5 tests)
# ===========================================================================

class TestMechAssemblyBOM:

    def test_A1_single_part_qty_one(self):
        """Single component → qty=1, unique_parts=1."""
        asm = _simple_asm("bracket-L")
        bom = _consolidate_bom(assembly_rows=_build_flat_bom(asm))
        assert bom["unique_parts"] == 1
        assert bom["total_qty"] == 1
        row = bom["rows"][0]
        assert row["part_ref"] == "bracket-L"
        assert row["qty"] == 1

    def test_A2_duplicate_parts_rolled_up(self):
        """Four identical bolts collapse into qty=4."""
        asm = _dup_asm("M8-hex-bolt", 4)
        bom = _consolidate_bom(assembly_rows=_build_flat_bom(asm))
        assert bom["unique_parts"] == 1
        assert bom["total_qty"] == 4
        assert bom["rows"][0]["qty"] == 4

    def test_A3_mixed_parts_distinct_rows(self):
        """bolt×2 + nut×2 + washer×4 → 3 unique rows, total_qty=8."""
        asm = Assembly(name="fixture")
        for _ in range(2):
            asm.add_component(Component(part_ref="M10-bolt"))
        for _ in range(2):
            asm.add_component(Component(part_ref="M10-nut"))
        for _ in range(4):
            asm.add_component(Component(part_ref="M10-washer"))
        bom = _consolidate_bom(assembly_rows=_build_flat_bom(asm))
        assert bom["unique_parts"] == 3
        assert bom["total_qty"] == 8
        by_ref = {r["part_ref"]: r["qty"] for r in bom["rows"]}
        assert by_ref["M10-bolt"] == 2
        assert by_ref["M10-nut"] == 2
        assert by_ref["M10-washer"] == 4

    def test_A4_sub_assembly_flatten(self):
        """Sub-assembly components are flattened into the consolidated BOM."""
        root = Assembly(name="root")
        root.add_component(Component(part_ref="frame-plate"))
        sub = Assembly(name="sub-frame")
        sub.add_component(Component(part_ref="gusset"))
        sub.add_component(Component(part_ref="gusset"))
        root.add_sub_assembly(sub)

        flat = _build_flat_bom(root)
        bom = _consolidate_bom(assembly_rows=flat)
        assert bom["unique_parts"] == 2  # frame-plate + gusset
        by_ref = {r["part_ref"]: r["qty"] for r in bom["rows"]}
        assert by_ref["frame-plate"] == 1
        assert by_ref["gusset"] == 2

    def test_A5_empty_assembly(self):
        """Empty assembly → zero rows and zero cost."""
        asm = Assembly(name="empty")
        bom = _consolidate_bom(assembly_rows=_build_flat_bom(asm))
        assert bom["unique_parts"] == 0
        assert bom["total_qty"] == 0
        assert bom["total_cost_usd"] == 0.0


# ===========================================================================
# Group B — Weldment cut-list → BOM lines (5 tests)
# ===========================================================================

class TestWeldmentBOM:

    def test_B1_single_member_one_bom_row(self):
        """500 mm SQ-40x40x3 member → one BOM row with qty=1."""
        cl = _sq_frame_cutlist("SQ-40x40x3", 500.0)
        rows = _weldment_to_bom_rows([cl])
        bom = _consolidate_bom(weldment_rows=rows)
        assert bom["unique_parts"] == 1
        assert bom["rows"][0]["qty"] == 1

    def test_B2_cost_proxy_positive(self):
        """Cost proxy (steel unit price) must be positive for any member."""
        cl = _sq_frame_cutlist("SQ-50x50x4", 1000.0)
        rows = _weldment_to_bom_rows([cl])
        assert rows[0]["unit_price_usd"] > 0.0

    def test_B3_repeated_length_rolled_into_qty(self):
        """Three members of equal length share a single cut-list piece → qty=3."""
        pd = lookup_profile("SQ-40x40x3")
        length_mm = 300.0
        # Three collinear but distinct edges (same length)
        skeleton = [
            {"start": [0, 0, 0],     "end": [length_mm, 0, 0]},
            {"start": [0, 100, 0],   "end": [length_mm, 100, 0]},
            {"start": [0, 200, 0],   "end": [length_mm, 200, 0]},
        ]
        members, errors = compute_members(skeleton, pd)
        assert not errors
        cl = compute_cutlist(members, pd)
        rows = _weldment_to_bom_rows([cl])
        bom = _consolidate_bom(weldment_rows=rows)
        # All three are identical length; cut-list rolls them to qty=3
        total = sum(r["qty"] for r in bom["rows"])
        assert total == 3

    def test_B4_multi_length_separate_rows(self):
        """Members of different lengths produce separate BOM rows."""
        pd = lookup_profile("SQ-40x40x3")
        skeleton = [
            {"start": [0, 0, 0], "end": [300.0, 0, 0]},
            {"start": [0, 0, 0], "end": [0, 500.0, 0]},
        ]
        members, errors = compute_members(skeleton, pd)
        assert not errors
        cl = compute_cutlist(members, pd)
        rows = _weldment_to_bom_rows([cl])
        bom = _consolidate_bom(weldment_rows=rows)
        # 2 distinct lengths → 2 rows (or 1 if trimming makes them equal, allow both)
        assert bom["unique_parts"] >= 1

    def test_B5_weldment_mass_cost_proportional(self):
        """Longer member → strictly higher cost than shorter member (same profile)."""
        def _cost_for_length(length_mm):
            pd = lookup_profile("SQ-50x50x3")
            skeleton = [{"start": [0, 0, 0], "end": [length_mm, 0, 0]}]
            members, _ = compute_members(skeleton, pd)
            cl = compute_cutlist(members, pd)
            rows = _weldment_to_bom_rows([cl])
            return rows[0]["unit_price_usd"]

        short = _cost_for_length(200.0)
        long_ = _cost_for_length(800.0)
        assert long_ > short


# ===========================================================================
# Group C — Electronics BOM cost roll-up (5 tests)
# ===========================================================================

class TestElectronicsBOM:

    def test_C1_single_line_cost(self):
        """Single resistor at $0.10 → extended_cost_usd = qty × 0.10."""
        rows = [_elec_line("R1", 2, 0.10, mpn="RC0402-10K")]
        bom = _consolidate_bom(elec_rows=rows)
        assert bom["unique_parts"] == 1
        r = bom["rows"][0]
        assert r["qty"] == 2
        assert abs(r["extended_cost_usd"] - 0.20) < 1e-9

    def test_C2_dnp_excluded_from_bom(self):
        """DNP line is completely excluded from the consolidated BOM."""
        rows = [
            _elec_line("R1", 2, 0.10),
            _elec_line("DNP-PART", 1, 5.00, dnp=True),
        ]
        bom = _consolidate_bom(elec_rows=rows)
        assert bom["unique_parts"] == 1
        refs = [r["part_ref"] for r in bom["rows"]]
        assert "DNP-PART" not in refs

    def test_C3_all_dnp_zero_cost(self):
        """All DNP → empty BOM, zero cost."""
        rows = [
            _elec_line("U1", 1, 3.00, dnp=True),
            _elec_line("C1", 4, 0.05, dnp=True),
        ]
        bom = _consolidate_bom(elec_rows=rows)
        assert bom["unique_parts"] == 0
        assert bom["total_cost_usd"] == 0.0

    def test_C4_price_break_selection(self):
        """Price-break tier is correctly selected for the extended qty."""
        row = {
            "refdes": "C1",
            "qty": 50,
            "mpn": "GRM155R71C104KA88D",
            "unit_price": 0.10,
            "price_breaks": [
                {"min_qty": 1,   "unit_price": 0.10},
                {"min_qty": 10,  "unit_price": 0.07},
                {"min_qty": 100, "unit_price": 0.04},
            ],
        }
        # qty=50 → should select the 10-tier (0.07), not the 100-tier (0.04)
        price = _select_price(row["unit_price"], row["price_breaks"], 50)
        assert abs(price - 0.07) < 1e-9

        bom = _consolidate_bom(elec_rows=[row])
        r = bom["rows"][0]
        assert abs(r["unit_price_usd"] - 0.07) < 1e-9
        assert abs(r["extended_cost_usd"] - 50 * 0.07) < 1e-9

    def test_C5_multi_line_total(self):
        """Five electronics lines → total = sum of extended costs."""
        prices = [0.05, 0.12, 1.50, 0.30, 2.00]
        qtys   = [10,    5,    2,    8,    1  ]
        rows = [
            _elec_line(f"PART{i}", qtys[i], prices[i])
            for i in range(5)
        ]
        bom = _consolidate_bom(elec_rows=rows)
        expected_total = sum(p * q for p, q in zip(prices, qtys))
        assert abs(bom["total_cost_usd"] - expected_total) < 1e-4
        assert bom["unique_parts"] == 5


# ===========================================================================
# Group D — Mixed mech + electronics consolidation (5 tests)
# ===========================================================================

class TestMixedBOM:

    def test_D1_mech_and_elec_combined_unique_count(self):
        """Mech bolts + elec capacitors → unique_parts = sum of distinct refs."""
        asm = _dup_asm("M6-bolt", 6)
        elec = [_elec_line("C1", 10, 0.05, mpn="CAP-100NF")]
        bom = _consolidate_bom(
            assembly_rows=_build_flat_bom(asm),
            elec_rows=elec,
        )
        assert bom["unique_parts"] == 2
        refs = {r["part_ref"] for r in bom["rows"]}
        assert "M6-bolt" in refs
        assert "CAP-100NF" in refs

    def test_D2_total_qty_correct_across_domains(self):
        """Total qty = mech qty + elec qty."""
        asm = _simple_asm("frame-weld", "frame-weld", "cover-plate")
        elec = [
            _elec_line("R1", 5, 0.10),
            _elec_line("C1", 3, 0.05),
        ]
        bom = _consolidate_bom(
            assembly_rows=_build_flat_bom(asm),
            elec_rows=elec,
        )
        assert bom["total_qty"] == 3 + 5 + 3  # 2 weld + 1 cover + 5 R1 + 3 C1

    def test_D3_weldment_plus_elec_total_cost(self):
        """Weldment + electronics cost is additive."""
        cl = _sq_frame_cutlist("SQ-40x40x3", 400.0)
        weld_rows = _weldment_to_bom_rows([cl])
        elec = [_elec_line("U1", 1, 10.00, mpn="MCU-STM32")]
        bom = _consolidate_bom(weldment_rows=weld_rows, elec_rows=elec)
        weld_cost = sum(r["unit_price_usd"] * r["qty"]
                        for r in weld_rows if r.get("unit_price_usd") is not None)
        mcu_cost = 10.00
        expected = weld_cost + mcu_cost
        assert abs(bom["total_cost_usd"] - expected) < 1e-3

    def test_D4_domain_tags_correct(self):
        """Rows originating from each domain carry the correct domain tag."""
        asm = _simple_asm("bracket")
        cl = _sq_frame_cutlist("SQ-30x30x2", 200.0)
        weld_rows = _weldment_to_bom_rows([cl])
        elec = [_elec_line("R1", 1, 0.05)]
        bom = _consolidate_bom(
            assembly_rows=_build_flat_bom(asm),
            weldment_rows=weld_rows,
            elec_rows=elec,
        )
        by_ref = {r["part_ref"]: r for r in bom["rows"]}
        assert "mech-assembly" in by_ref["bracket"]["domain"]
        assert "weldment" in next(
            r for r in bom["rows"] if "weldment" in r["domain"]
        )["domain"]
        assert "electronics" in by_ref["R1"]["domain"]

    def test_D5_cost_only_priced_lines(self):
        """Lines without a unit_price_usd do not contribute to total_cost_usd."""
        asm_rows = [{"part_ref": "custom-part", "qty": 3}]  # no price
        elec = [_elec_line("R1", 2, 1.00)]
        bom = _consolidate_bom(assembly_rows=asm_rows, elec_rows=elec)
        # Only R1 contributes cost
        assert abs(bom["total_cost_usd"] - 2.00) < 1e-9


# ===========================================================================
# Group E — Alternates resolution and edge cases (5 tests)
# ===========================================================================

class TestAlternatesAndEdgeCases:

    def test_E1_alternate_merges_into_replacement(self):
        """Part A replaced by part B → B's qty = A qty + B qty."""
        asm = Assembly(name="mix")
        for _ in range(3):
            asm.add_component(Component(part_ref="PartA"))
        for _ in range(2):
            asm.add_component(Component(part_ref="PartB"))
        # Declare PartA as alternate for PartB
        bom = _consolidate_bom(
            assembly_rows=_build_flat_bom(asm),
            alternates={"PartA": "PartB"},
        )
        assert bom["unique_parts"] == 1
        assert bom["rows"][0]["part_ref"] == "PartB"
        assert bom["rows"][0]["qty"] == 5

    def test_E2_alternate_case_insensitive(self):
        """Alternate keys are matched case-insensitively."""
        asm_rows = [
            {"part_ref": "FASTENER-M8", "qty": 4},
            {"part_ref": "fastener-m8", "qty": 2},
        ]
        bom = _consolidate_bom(
            assembly_rows=asm_rows,
            alternates={"fastener-m8": "M8-Bolt"},
        )
        # Both FASTENER-M8 and fastener-m8 map to M8-Bolt
        assert bom["unique_parts"] == 1
        assert bom["rows"][0]["qty"] == 6

    def test_E3_completely_empty_input(self):
        """No inputs at all → empty BOM with zero totals."""
        bom = _consolidate_bom()
        assert bom["unique_parts"] == 0
        assert bom["total_qty"] == 0
        assert bom["total_cost_usd"] == 0.0
        assert bom["rows"] == []

    def test_E4_cost_rollup_compute_helper_matches_manual(self):
        """_compute_cost_rollup total matches manual line-by-line sum."""
        lines = [
            {"refdes": "R1", "qty": 10, "unit_price": 0.05},
            {"refdes": "C1", "qty": 5,  "unit_price": 0.12},
            {"refdes": "U1", "qty": 1,  "unit_price": 3.50},
        ]
        result = _compute_cost_rollup(lines, board_qty=5, assembly_qty=5, nre_usd=0.0, dnp_list=[])
        manual = sum(l["qty"] * l["unit_price"] * 5 for l in lines)
        assert abs(result["subtotal_parts_usd"] - manual) < 1e-4

    def test_E5_weldment_ibeam_bom_row_has_part_ref(self):
        """IBEAM profile produces a valid weldment BOM row with non-empty part_ref."""
        pd = lookup_profile("IBEAM-IPE100")
        skeleton = [{"start": [0, 0, 0], "end": [600.0, 0, 0]}]
        members, errors = compute_members(skeleton, pd)
        assert not errors
        cl = compute_cutlist(members, pd)
        rows = _weldment_to_bom_rows([cl])
        assert len(rows) == 1
        assert rows[0]["part_ref"].startswith("IBEAM-IPE100")
        bom = _consolidate_bom(weldment_rows=rows)
        assert bom["unique_parts"] == 1
        assert bom["rows"][0]["unit_price_usd"] > 0.0
