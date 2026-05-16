"""
Tests for kerf_cloud.job_traveler — PO / Job Traveler / Inventory module.

All tests use tmp_path for an isolated JSON store.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from kerf_cloud.job_traveler import (
    STAGE_ORDER,
    advance_stage,
    allocation_check,
    close_traveler,
    create_po,
    get_inventory_item,
    get_po,
    get_traveler,
    inventory_pick_list,
    issue_po,
    list_inventory,
    list_pos,
    list_travelers,
    receive_po,
    start_traveler,
    upsert_inventory_item,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_items(n: int = 2) -> list[dict]:
    return [
        {"part_ref": f"SKU-{i}", "qty": i + 1, "unit_price": float(i + 1) * 10.0}
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# PurchaseOrder tests
# ---------------------------------------------------------------------------

class TestCreatePO:
    def test_basic_draft(self, tmp_path):
        r = create_po("Acme Corp", _make_items(2), store_root=tmp_path)
        assert r["ok"] is True
        po = r["po"]
        assert po["status"] == "draft"
        assert po["customer"] == "Acme Corp"
        assert len(po["line_items"]) == 2
        assert po["id"].startswith("po-")

    def test_total_computed(self, tmp_path):
        items = [{"part_ref": "A", "qty": 3, "unit_price": 10.0},
                 {"part_ref": "B", "qty": 2, "unit_price": 5.0}]
        r = create_po("X", items, store_root=tmp_path)
        assert r["ok"] is True
        assert r["po"]["total"] == pytest.approx(40.0)

    def test_empty_customer_fails(self, tmp_path):
        r = create_po("", _make_items(), store_root=tmp_path)
        assert r["ok"] is False
        assert r["code"] == "BAD_ARGS"

    def test_empty_items_fails(self, tmp_path):
        r = create_po("Acme", [], store_root=tmp_path)
        assert r["ok"] is False

    def test_zero_qty_fails(self, tmp_path):
        items = [{"part_ref": "A", "qty": 0, "unit_price": 5.0}]
        r = create_po("X", items, store_root=tmp_path)
        assert r["ok"] is False
        assert r["code"] == "BAD_ARGS"

    def test_persisted_and_loadable(self, tmp_path):
        r = create_po("Persisted", _make_items(1), store_root=tmp_path)
        po_id = r["po"]["id"]
        r2 = get_po(po_id, store_root=tmp_path)
        assert r2["ok"] is True
        assert r2["po"]["customer"] == "Persisted"


class TestIssuePO:
    def test_draft_to_issued(self, tmp_path):
        po_id = create_po("B", _make_items(), store_root=tmp_path)["po"]["id"]
        r = issue_po(po_id, store_root=tmp_path)
        assert r["ok"] is True
        assert r["po"]["status"] == "issued"

    def test_cannot_issue_already_issued(self, tmp_path):
        po_id = create_po("C", _make_items(), store_root=tmp_path)["po"]["id"]
        issue_po(po_id, store_root=tmp_path)
        r = issue_po(po_id, store_root=tmp_path)
        assert r["ok"] is False
        assert r["code"] == "INVALID_STATE"

    def test_unknown_po_id_fails(self, tmp_path):
        r = issue_po("po-does-not-exist", store_root=tmp_path)
        assert r["ok"] is False
        assert r["code"] == "NOT_FOUND"


class TestReceivePO:
    def _issued_po(self, tmp_path):
        items = [{"part_ref": "WIDGET", "qty": 10, "unit_price": 2.0}]
        po_id = create_po("D", items, store_root=tmp_path)["po"]["id"]
        issue_po(po_id, store_root=tmp_path)
        return po_id

    def test_receive_updates_inventory(self, tmp_path):
        po_id = self._issued_po(tmp_path)
        r = receive_po(po_id, [{"part_ref": "WIDGET", "qty": 8}], store_root=tmp_path)
        assert r["ok"] is True
        assert r["po"]["status"] == "received"
        assert r["inventory_updates"][0]["on_hand"] == 8

    def test_receive_accumulates_existing_stock(self, tmp_path):
        upsert_inventory_item("WIDGET", on_hand=5, store_root=tmp_path)
        po_id = self._issued_po(tmp_path)
        receive_po(po_id, [{"part_ref": "WIDGET", "qty": 3}], store_root=tmp_path)
        item = get_inventory_item("WIDGET", store_root=tmp_path)["item"]
        assert item["on_hand"] == 8

    def test_receive_draft_po_fails(self, tmp_path):
        items = [{"part_ref": "X", "qty": 1, "unit_price": 1.0}]
        po_id = create_po("E", items, store_root=tmp_path)["po"]["id"]
        r = receive_po(po_id, [{"part_ref": "X", "qty": 1}], store_root=tmp_path)
        assert r["ok"] is False
        assert r["code"] == "INVALID_STATE"

    def test_full_po_flow(self, tmp_path):
        """create → issue → receive: status transitions are correct."""
        items = [{"part_ref": "GOLD", "qty": 5, "unit_price": 100.0}]
        po_id = create_po("Jeweller", items, store_root=tmp_path)["po"]["id"]
        assert get_po(po_id, store_root=tmp_path)["po"]["status"] == "draft"
        issue_po(po_id, store_root=tmp_path)
        assert get_po(po_id, store_root=tmp_path)["po"]["status"] == "issued"
        receive_po(po_id, [{"part_ref": "GOLD", "qty": 5}], store_root=tmp_path)
        assert get_po(po_id, store_root=tmp_path)["po"]["status"] == "received"


# ---------------------------------------------------------------------------
# JobTraveler tests
# ---------------------------------------------------------------------------

class TestStartTraveler:
    def test_starts_at_design_stage(self, tmp_path):
        r = start_traveler(store_root=tmp_path)
        assert r["ok"] is True
        jt = r["traveler"]
        assert jt["current_stage"] == "design"
        assert jt["stages"]["design"]["status"] == "in_progress"
        assert jt["status"] == "open"

    def test_linked_fields_stored(self, tmp_path):
        r = start_traveler(po="po-123", project="proj-456", revision="rev-789", store_root=tmp_path)
        jt = r["traveler"]
        assert jt["linked_po"] == "po-123"
        assert jt["linked_project_id"] == "proj-456"
        assert jt["linked_revision_id"] == "rev-789"

    def test_persisted(self, tmp_path):
        jt_id = start_traveler(store_root=tmp_path)["traveler"]["id"]
        r = get_traveler(jt_id, store_root=tmp_path)
        assert r["ok"] is True
        assert r["traveler"]["id"] == jt_id


class TestAdvanceStage:
    def _start(self, tmp_path):
        return start_traveler(store_root=tmp_path)["traveler"]["id"]

    def test_advance_from_design_to_cast(self, tmp_path):
        jt_id = self._start(tmp_path)
        r = advance_stage(jt_id, "design", assignee="Alice", store_root=tmp_path)
        assert r["ok"] is True
        assert r["next_stage"] == "cast"
        jt = r["traveler"]
        assert jt["stages"]["design"]["status"] == "done"
        assert jt["stages"]["cast"]["status"] == "in_progress"
        assert jt["current_stage"] == "cast"

    def test_monotonic_cannot_skip(self, tmp_path):
        jt_id = self._start(tmp_path)
        r = advance_stage(jt_id, "cast", store_root=tmp_path)
        assert r["ok"] is False
        assert r["code"] == "INVALID_STATE"

    def test_full_stage_progression(self, tmp_path):
        jt_id = self._start(tmp_path)
        for stage in STAGE_ORDER:
            r = advance_stage(jt_id, stage, store_root=tmp_path)
            assert r["ok"] is True
        # After qc done, current_stage is None
        jt = get_traveler(jt_id, store_root=tmp_path)["traveler"]
        assert jt["current_stage"] is None

    def test_history_grows_monotonically(self, tmp_path):
        jt_id = self._start(tmp_path)
        advance_stage(jt_id, "design", store_root=tmp_path)
        jt = get_traveler(jt_id, store_root=tmp_path)["traveler"]
        # started design + completed design + started cast = 3 events
        assert len(jt["stage_history"]) == 3

    def test_unknown_stage_fails(self, tmp_path):
        jt_id = self._start(tmp_path)
        r = advance_stage(jt_id, "nonexistent", store_root=tmp_path)
        assert r["ok"] is False
        assert r["code"] == "BAD_ARGS"

    def test_advance_closed_traveler_fails(self, tmp_path):
        jt_id = self._start(tmp_path)
        for stage in STAGE_ORDER:
            advance_stage(jt_id, stage, store_root=tmp_path)
        close_traveler(jt_id, qc_pass=True, store_root=tmp_path)
        r = advance_stage(jt_id, "design", store_root=tmp_path)
        assert r["ok"] is False
        assert r["code"] == "INVALID_STATE"


class TestCloseTraveler:
    def _advance_all(self, jt_id, tmp_path):
        for stage in STAGE_ORDER:
            advance_stage(jt_id, stage, store_root=tmp_path)

    def test_close_requires_qc_pass(self, tmp_path):
        jt_id = start_traveler(store_root=tmp_path)["traveler"]["id"]
        r = close_traveler(jt_id, qc_pass=False, store_root=tmp_path)
        assert r["ok"] is False
        assert r["code"] == "QC_FAILED"

    def test_close_with_qc_pass(self, tmp_path):
        jt_id = start_traveler(store_root=tmp_path)["traveler"]["id"]
        self._advance_all(jt_id, tmp_path)
        r = close_traveler(jt_id, qc_pass=True, store_root=tmp_path)
        assert r["ok"] is True
        assert r["traveler"]["status"] == "closed"

    def test_double_close_fails(self, tmp_path):
        jt_id = start_traveler(store_root=tmp_path)["traveler"]["id"]
        self._advance_all(jt_id, tmp_path)
        close_traveler(jt_id, qc_pass=True, store_root=tmp_path)
        r = close_traveler(jt_id, qc_pass=True, store_root=tmp_path)
        assert r["ok"] is False
        assert r["code"] == "INVALID_STATE"

    def test_notes_appended_on_close(self, tmp_path):
        jt_id = start_traveler(notes="initial", store_root=tmp_path)["traveler"]["id"]
        self._advance_all(jt_id, tmp_path)
        close_traveler(jt_id, qc_pass=True, notes="QC signed off", store_root=tmp_path)
        jt = get_traveler(jt_id, store_root=tmp_path)["traveler"]
        assert "QC signed off" in jt["notes"]


# ---------------------------------------------------------------------------
# Inventory / allocation_check tests
# ---------------------------------------------------------------------------

class TestAllocationCheck:
    def test_sufficient_stock_ok(self, tmp_path):
        upsert_inventory_item("PART-A", on_hand=10, allocated=2, store_root=tmp_path)
        r = allocation_check([{"part_ref": "PART-A", "qty": 5}], store_root=tmp_path)
        assert r["ok"] is True
        assert r["checks"][0]["ok"] is True
        assert r["checks"][0]["available"] == 8
        assert r["checks"][0]["shortfall"] == 0

    def test_insufficient_stock_fires(self, tmp_path):
        upsert_inventory_item("PART-B", on_hand=3, allocated=1, store_root=tmp_path)
        r = allocation_check([{"part_ref": "PART-B", "qty": 5}], store_root=tmp_path)
        # ok=False because not all items can be filled
        assert r["ok"] is False
        assert r["checks"][0]["ok"] is False
        assert r["checks"][0]["shortfall"] == 3
        assert "PART-B" in r["shortfalls"]

    def test_missing_inventory_item_is_shortfall(self, tmp_path):
        r = allocation_check([{"part_ref": "GHOST", "qty": 1}], store_root=tmp_path)
        assert r["checks"][0]["shortfall"] == 1
        assert "GHOST" in r["shortfalls"]

    def test_multiple_items_mixed(self, tmp_path):
        upsert_inventory_item("OK-PART", on_hand=20, store_root=tmp_path)
        r = allocation_check(
            [{"part_ref": "OK-PART", "qty": 5}, {"part_ref": "MISSING", "qty": 2}],
            store_root=tmp_path,
        )
        assert len(r["shortfalls"]) == 1
        assert r["shortfalls"][0] == "MISSING"


# ---------------------------------------------------------------------------
# inventory_pick_list tests
# ---------------------------------------------------------------------------

class TestInventoryPickList:
    def test_all_fillable(self, tmp_path):
        upsert_inventory_item("GOLD-WIRE", on_hand=100, store_root=tmp_path)
        bom = [{"part_ref": "GOLD-WIRE", "qty": 10, "description": "18k wire"}]
        r = inventory_pick_list(bom, store_root=tmp_path)
        assert r["ok"] is True
        assert len(r["can_fill"]) == 1
        assert len(r["needs_order"]) == 0
        assert r["summary"]["fill_lines"] == 1
        assert r["summary"]["order_lines"] == 0

    def test_none_fillable(self, tmp_path):
        bom = [{"part_ref": "RARE-GEM", "qty": 5}]
        r = inventory_pick_list(bom, store_root=tmp_path)
        assert r["ok"] is True
        assert len(r["can_fill"]) == 0
        assert len(r["needs_order"]) == 1
        assert r["needs_order"][0]["shortfall"] == 5

    def test_partial_partition(self, tmp_path):
        upsert_inventory_item("CLASP", on_hand=10, store_root=tmp_path)
        bom = [
            {"part_ref": "CLASP", "qty": 5},
            {"part_ref": "SETTING", "qty": 3},
        ]
        r = inventory_pick_list(bom, store_root=tmp_path)
        assert r["summary"]["fill_lines"] == 1
        assert r["summary"]["order_lines"] == 1

    def test_bom_preserves_extra_fields(self, tmp_path):
        upsert_inventory_item("PRONG", on_hand=50, store_root=tmp_path)
        bom = [{"part_ref": "PRONG", "qty": 4, "alloy": "18k_yellow"}]
        r = inventory_pick_list(bom, store_root=tmp_path)
        assert r["can_fill"][0].get("alloy") == "18k_yellow"


# ---------------------------------------------------------------------------
# Persistence round-trip
# ---------------------------------------------------------------------------

class TestPersistenceRoundTrip:
    def test_po_json_roundtrip(self, tmp_path):
        items = [{"part_ref": "X", "qty": 2, "unit_price": 9.99, "lead_time": "3 days"}]
        po_id = create_po("RoundTrip", items, store_root=tmp_path)["po"]["id"]
        # Read raw JSON file
        raw = json.loads((tmp_path / "purchase_orders.json").read_text())
        assert po_id in raw
        assert raw[po_id]["customer"] == "RoundTrip"
        # Reload via API
        assert get_po(po_id, store_root=tmp_path)["po"]["line_items"][0]["lead_time"] == "3 days"

    def test_traveler_json_roundtrip(self, tmp_path):
        jt_id = start_traveler(notes="hello", store_root=tmp_path)["traveler"]["id"]
        raw = json.loads((tmp_path / "job_travelers.json").read_text())
        assert jt_id in raw
        assert raw[jt_id]["notes"] == "hello"

    def test_inventory_json_roundtrip(self, tmp_path):
        upsert_inventory_item("SKU-RT", on_hand=7, supplier_ref="SUP-001", store_root=tmp_path)
        raw = json.loads((tmp_path / "inventory.json").read_text())
        assert "SKU-RT" in raw
        assert raw["SKU-RT"]["supplier_ref"] == "SUP-001"
        # Reload
        item = get_inventory_item("SKU-RT", store_root=tmp_path)["item"]
        assert item["on_hand"] == 7

    def test_list_functions(self, tmp_path):
        create_po("A", _make_items(1), store_root=tmp_path)
        create_po("B", _make_items(1), store_root=tmp_path)
        assert len(list_pos(store_root=tmp_path)["purchase_orders"]) == 2

        start_traveler(store_root=tmp_path)
        start_traveler(store_root=tmp_path)
        assert len(list_travelers(store_root=tmp_path)["travelers"]) == 2

        upsert_inventory_item("I1", on_hand=1, store_root=tmp_path)
        upsert_inventory_item("I2", on_hand=2, store_root=tmp_path)
        assert len(list_inventory(store_root=tmp_path)["items"]) == 2
