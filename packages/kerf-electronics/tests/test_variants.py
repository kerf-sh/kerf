"""
Tests for the assembly variant system (kerf_electronics.tools.variants).

Covers:
  - _apply_variant: overlay application, DNP removal, field overrides
  - _dnp_csv: DNP CSV rendering
  - variant_bom: BOM excludes DNP parts, DNP section populated
  - variant_fab: P&P excludes DNP, zip contains DNP CSV
  - define_variant / list_variants LLM tools
  - variant_bom / variant_fab LLM tools (inline overrides + named variants)
"""

import csv
import io
import json
import unittest
import zipfile

# Import to trigger @register decorators
import kerf_electronics.tools.variants  # noqa: F401

from kerf_electronics.tools.variants import (
    _apply_variant,
    _dnp_csv,
    _VARIANT_STORE,
)

# ─── Shared fixture ───────────────────────────────────────────────────────────
# Three-component board: R1 (0402 10k), R2 (0402 10k), U1 (ATmega328P)

FIXTURE = [
    {
        "type": "pcb_board",
        "width": 100.0,
        "height": 80.0,
        "center_x": 50.0,
        "center_y": 40.0,
    },
    # source components
    {
        "type": "source_component",
        "source_component_id": "sc_r1",
        "name": "R1",
        "value": "10k",
        "footprint": "R_0402",
        "mpn": "RC0402FR-0710KL",
        "manufacturer": "Yageo",
        "description": "Resistor 10k 1% 0402",
        "distributors": [
            {"name": "DigiKey", "part_number": "311-10KLRCT-ND", "unit_price_usd": 0.10},
        ],
    },
    {
        "type": "source_component",
        "source_component_id": "sc_r2",
        "name": "R2",
        "value": "10k",
        "footprint": "R_0402",
        "mpn": "RC0402FR-0710KL",
        "manufacturer": "Yageo",
        "description": "Resistor 10k 1% 0402",
        "distributors": [
            {"name": "DigiKey", "part_number": "311-10KLRCT-ND", "unit_price_usd": 0.10},
        ],
    },
    {
        "type": "source_component",
        "source_component_id": "sc_u1",
        "name": "U1",
        "value": "ATmega328P",
        "footprint": "TQFP-32",
        "mpn": "ATMEGA328P-AU",
        "manufacturer": "Microchip",
        "description": "8-bit MCU",
        "distributors": [
            {"name": "DigiKey", "part_number": "ATMEGA328P-AU-ND", "unit_price_usd": 2.50},
        ],
    },
    # pcb components
    {
        "type": "pcb_component",
        "pcb_component_id": "pcb_r1",
        "source_component_id": "sc_r1",
        "x": 20.0, "y": 30.0, "rotation": 0.0,
        "layer": "top_copper",
    },
    {
        "type": "pcb_component",
        "pcb_component_id": "pcb_r2",
        "source_component_id": "sc_r2",
        "x": 22.0, "y": 30.0, "rotation": 0.0,
        "layer": "top_copper",
    },
    {
        "type": "pcb_component",
        "pcb_component_id": "pcb_u1",
        "source_component_id": "sc_u1",
        "x": 60.0, "y": 40.0, "rotation": 90.0,
        "layer": "top_copper",
    },
]


# ─── Unit tests: _apply_variant ───────────────────────────────────────────────

class TestApplyVariant(unittest.TestCase):

    def test_no_overrides_leaves_circuit_unchanged(self):
        patched, dnp = _apply_variant(FIXTURE, {})
        pcb_comps = [e for e in patched if e.get("type") == "pcb_component"]
        self.assertEqual(len(pcb_comps), 3)
        self.assertEqual(len(dnp), 0)

    def test_dnp_removes_pcb_component(self):
        overrides = {"R1": {"fitted": False}}
        patched, dnp = _apply_variant(FIXTURE, overrides)
        pcb_ids = {e.get("source_component_id") for e in patched if e.get("type") == "pcb_component"}
        self.assertNotIn("sc_r1", pcb_ids)

    def test_dnp_removes_correct_component_only(self):
        overrides = {"R1": {"fitted": False}}
        patched, dnp = _apply_variant(FIXTURE, overrides)
        pcb_ids = {e.get("source_component_id") for e in patched if e.get("type") == "pcb_component"}
        self.assertIn("sc_r2", pcb_ids)
        self.assertIn("sc_u1", pcb_ids)

    def test_dnp_populates_dnp_sources_list(self):
        overrides = {"R1": {"fitted": False}}
        patched, dnp = _apply_variant(FIXTURE, overrides)
        self.assertEqual(len(dnp), 1)
        self.assertEqual(dnp[0]["name"], "R1")

    def test_multiple_dnp_parts(self):
        overrides = {
            "R1": {"fitted": False},
            "R2": {"fitted": False},
        }
        patched, dnp = _apply_variant(FIXTURE, overrides)
        pcb_comps = [e for e in patched if e.get("type") == "pcb_component"]
        self.assertEqual(len(pcb_comps), 1)  # only U1 left
        self.assertEqual(len(dnp), 2)

    def test_value_override_applied_to_source_component(self):
        overrides = {"R1": {"value": "4k7"}}
        patched, dnp = _apply_variant(FIXTURE, overrides)
        src_r1 = next(
            e for e in patched
            if e.get("type") == "source_component" and e.get("source_component_id") == "sc_r1"
        )
        self.assertEqual(src_r1["value"], "4k7")

    def test_mpn_override_applied(self):
        overrides = {"U1": {"mpn": "ATMEGA328P-MU"}}
        patched, dnp = _apply_variant(FIXTURE, overrides)
        src_u1 = next(
            e for e in patched
            if e.get("type") == "source_component" and e.get("source_component_id") == "sc_u1"
        )
        self.assertEqual(src_u1["mpn"], "ATMEGA328P-MU")

    def test_footprint_override_applied(self):
        overrides = {"U1": {"footprint": "QFN-32"}}
        patched, dnp = _apply_variant(FIXTURE, overrides)
        src_u1 = next(
            e for e in patched
            if e.get("type") == "source_component" and e.get("source_component_id") == "sc_u1"
        )
        self.assertEqual(src_u1["footprint"], "QFN-32")

    def test_original_circuit_not_mutated(self):
        original_value = FIXTURE[1]["value"]  # "10k"
        overrides = {"R1": {"value": "1M"}}
        _apply_variant(FIXTURE, overrides)
        self.assertEqual(FIXTURE[1]["value"], original_value)

    def test_override_by_source_component_id(self):
        overrides = {"sc_r1": {"fitted": False}}
        patched, dnp = _apply_variant(FIXTURE, overrides)
        self.assertEqual(len(dnp), 1)

    def test_unknown_refdes_in_overrides_is_ignored(self):
        overrides = {"DOESNOTEXIST": {"fitted": False}}
        patched, dnp = _apply_variant(FIXTURE, overrides)
        pcb_comps = [e for e in patched if e.get("type") == "pcb_component"]
        self.assertEqual(len(pcb_comps), 3)
        self.assertEqual(len(dnp), 0)


# ─── Unit tests: _dnp_csv ─────────────────────────────────────────────────────

class TestDnpCsv(unittest.TestCase):

    def _dnp_sources(self):
        overrides = {"R1": {"fitted": False}}
        _, dnp = _apply_variant(FIXTURE, overrides)
        return dnp

    def test_dnp_csv_has_header(self):
        csv_text = _dnp_csv(self._dnp_sources())
        self.assertTrue(csv_text.splitlines()[0].startswith("Refdes"))

    def test_dnp_csv_lists_dnp_part(self):
        csv_text = _dnp_csv(self._dnp_sources())
        self.assertIn("R1", csv_text)

    def test_dnp_csv_has_dnp_note(self):
        csv_text = _dnp_csv(self._dnp_sources())
        self.assertIn("DNP", csv_text)

    def test_empty_dnp_sources_returns_header_only(self):
        csv_text = _dnp_csv([])
        lines = csv_text.strip().splitlines()
        self.assertEqual(len(lines), 1)  # header only


# ─── Integration: variant BOM via fab_bom ─────────────────────────────────────

class TestVariantBomIntegration(unittest.TestCase):

    def test_dnp_part_absent_from_main_bom(self):
        """DNP R1 → the 10k group drops to Qty=1 (only R2 remains)."""
        from kerf_electronics.fab.fab_bom import export_fab_bom
        overrides = {"R1": {"fitted": False}}
        patched, _ = _apply_variant(FIXTURE, overrides)
        bom_files = export_fab_bom(patched, stem="test")
        bom_csv = bom_files["test-bom.csv"]
        # Parse CSV
        reader = csv.DictReader(io.StringIO(bom_csv))
        rows = list(reader)
        ten_k_rows = [r for r in rows if "10k" in r["Value"]]
        self.assertEqual(len(ten_k_rows), 1)
        self.assertEqual(ten_k_rows[0]["Qty"], "1")

    def test_dnp_both_resistors_absent_from_bom(self):
        from kerf_electronics.fab.fab_bom import export_fab_bom
        overrides = {"R1": {"fitted": False}, "R2": {"fitted": False}}
        patched, _ = _apply_variant(FIXTURE, overrides)
        bom_files = export_fab_bom(patched, stem="test")
        bom_csv = bom_files["test-bom.csv"]
        self.assertNotIn("10k", bom_csv)
        self.assertIn("ATmega328P", bom_csv)

    def test_value_override_reflected_in_bom(self):
        from kerf_electronics.fab.fab_bom import export_fab_bom
        overrides = {"R1": {"value": "4k7"}}
        patched, _ = _apply_variant(FIXTURE, overrides)
        bom_files = export_fab_bom(patched, stem="test")
        bom_csv = bom_files["test-bom.csv"]
        # R1 is now 4k7, R2 remains 10k → two groups
        self.assertIn("4k7", bom_csv)


# ─── Integration: variant P&P via pnp ─────────────────────────────────────────

class TestVariantPnPIntegration(unittest.TestCase):

    def test_dnp_part_absent_from_pnp(self):
        from kerf_electronics.fab.pnp import export_pnp
        overrides = {"U1": {"fitted": False}}
        patched, _ = _apply_variant(FIXTURE, overrides)
        pnp_files = export_pnp(patched, stem="test")
        top_csv = pnp_files["test-top-pnp.csv"]
        self.assertNotIn("U1", top_csv)

    def test_fitted_parts_remain_in_pnp(self):
        from kerf_electronics.fab.pnp import export_pnp
        overrides = {"U1": {"fitted": False}}
        patched, _ = _apply_variant(FIXTURE, overrides)
        pnp_files = export_pnp(patched, stem="test")
        top_csv = pnp_files["test-top-pnp.csv"]
        self.assertIn("R1", top_csv)
        self.assertIn("R2", top_csv)

    def test_all_dnp_yields_empty_pnp(self):
        from kerf_electronics.fab.pnp import export_pnp
        overrides = {
            "R1": {"fitted": False},
            "R2": {"fitted": False},
            "U1": {"fitted": False},
        }
        patched, _ = _apply_variant(FIXTURE, overrides)
        pnp_files = export_pnp(patched, stem="test")
        top_lines = pnp_files["test-top-pnp.csv"].strip().splitlines()
        # Only the header row
        self.assertEqual(len(top_lines), 1)


# ─── LLM tool tests ────────────────────────────────────────────────────────────

class TestDefineVariantTool(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        _VARIANT_STORE.clear()

    async def _call(self, payload: dict) -> dict:
        from kerf_electronics.tools.variants import run_define_variant
        return json.loads(await run_define_variant(None, json.dumps(payload).encode()))

    async def test_define_variant_returns_success(self):
        result = await self._call({
            "variant_name": "production",
            "overrides": {"R1": {"fitted": False}},
        })
        self.assertNotIn("error", result)
        self.assertEqual(result["variant_name"], "production")

    async def test_define_variant_counts_dnp(self):
        result = await self._call({
            "variant_name": "v1",
            "overrides": {
                "R1": {"fitted": False},
                "R2": {"fitted": False},
                "U1": {"mpn": "XALT"},
            },
        })
        self.assertEqual(result["dnp_parts"], 2)
        self.assertEqual(result["alternate_parts"], 1)

    async def test_define_variant_stores_in_store(self):
        await self._call({
            "variant_name": "debug",
            "overrides": {"U1": {"fitted": False}},
        })
        self.assertIn("debug", _VARIANT_STORE)

    async def test_missing_variant_name_returns_error(self):
        result = await self._call({
            "variant_name": "",
            "overrides": {},
        })
        self.assertIn("error", result)

    async def test_bad_overrides_type_returns_error(self):
        result = await self._call({
            "variant_name": "v",
            "overrides": "not-an-object",
        })
        self.assertIn("error", result)


class TestListVariantsTool(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        _VARIANT_STORE.clear()

    async def _call(self) -> dict:
        from kerf_electronics.tools.variants import run_list_variants
        return json.loads(await run_list_variants(None, json.dumps({}).encode()))

    async def test_empty_store(self):
        result = await self._call()
        self.assertNotIn("error", result)
        self.assertEqual(result["count"], 0)
        self.assertEqual(result["variants"], [])

    async def test_lists_defined_variants(self):
        _VARIANT_STORE["alpha"] = {"_meta": {}, "R1": {"fitted": False}}
        _VARIANT_STORE["beta"] = {"_meta": {"description": "test"}, "U1": {"mpn": "X"}}
        result = await self._call()
        self.assertEqual(result["count"], 2)
        names = {v["name"] for v in result["variants"]}
        self.assertEqual(names, {"alpha", "beta"})

    async def test_dnp_count_in_listing(self):
        _VARIANT_STORE["v1"] = {"_meta": {}, "R1": {"fitted": False}, "R2": {"fitted": False}}
        result = await self._call()
        v1 = next(v for v in result["variants"] if v["name"] == "v1")
        self.assertEqual(v1["dnp_parts"], 2)


class TestVariantBomTool(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        _VARIANT_STORE.clear()

    async def _call(self, payload: dict) -> dict:
        from kerf_electronics.tools.variants import run_variant_bom
        return json.loads(await run_variant_bom(None, json.dumps(payload).encode()))

    async def test_inline_overrides_dnp_excluded_from_bom(self):
        result = await self._call({
            "circuit_json": FIXTURE,
            "overrides": {"R1": {"fitted": False}},
            "stem": "board",
        })
        self.assertNotIn("error", result)
        self.assertIn("bom_csv", result)
        # DNP count == 1
        self.assertEqual(result["dnp_count"], 1)

    async def test_dnp_csv_present_when_dnp_exists(self):
        result = await self._call({
            "circuit_json": FIXTURE,
            "overrides": {"R1": {"fitted": False}},
        })
        self.assertIn("dnp_csv", result)
        self.assertIn("R1", result["dnp_csv"])

    async def test_dnp_part_absent_from_main_bom_csv(self):
        """With R1 DNP and R2 fitted, main BOM should show Qty=1 for 10k group."""
        result = await self._call({
            "circuit_json": FIXTURE,
            "overrides": {"R1": {"fitted": False}},
        })
        bom_csv = result["bom_csv"]
        reader = csv.DictReader(io.StringIO(bom_csv))
        rows = list(reader)
        ten_k_rows = [r for r in rows if "10k" in r.get("Value", "")]
        # R2 still fitted → one row with Qty=1
        self.assertEqual(len(ten_k_rows), 1)
        self.assertEqual(ten_k_rows[0]["Qty"], "1")

    async def test_named_variant_lookup(self):
        _VARIANT_STORE["prod"] = {"_meta": {}, "U1": {"fitted": False}}
        result = await self._call({
            "circuit_json": FIXTURE,
            "variant_name": "prod",
        })
        self.assertNotIn("error", result)
        self.assertEqual(result["dnp_count"], 1)

    async def test_unknown_variant_returns_error(self):
        result = await self._call({
            "circuit_json": FIXTURE,
            "variant_name": "does_not_exist",
        })
        self.assertIn("error", result)

    async def test_bad_circuit_json_type(self):
        result = await self._call({
            "circuit_json": "not-an-array",
        })
        self.assertIn("error", result)

    async def test_no_dnp_csv_empty_when_no_dnp(self):
        result = await self._call({
            "circuit_json": FIXTURE,
            "overrides": {},
        })
        self.assertEqual(result["dnp_count"], 0)


class TestVariantFabTool(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        _VARIANT_STORE.clear()

    async def _call(self, payload: dict) -> dict:
        from kerf_electronics.tools.variants import run_variant_fab
        return json.loads(await run_variant_fab(None, json.dumps(payload).encode()))

    async def test_returns_zip_b64(self):
        result = await self._call({
            "circuit_json": FIXTURE,
            "overrides": {"R1": {"fitted": False}},
            "variant_name": "prod",
            "stem": "board",
        })
        self.assertNotIn("error", result)
        self.assertIn("zip_b64", result)

    async def test_zip_is_valid(self):
        result = await self._call({
            "circuit_json": FIXTURE,
            "overrides": {"R1": {"fitted": False}},
            "variant_name": "prod",
        })
        zip_bytes = __import__("base64").b64decode(result["zip_b64"])
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(zip_bytes)))

    async def test_zip_contains_dnp_csv(self):
        result = await self._call({
            "circuit_json": FIXTURE,
            "overrides": {"R1": {"fitted": False}},
            "variant_name": "prod",
            "stem": "board",
        })
        import base64
        zip_bytes = base64.b64decode(result["zip_b64"])
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            dnp_files = [n for n in zf.namelist() if "dnp" in n]
        self.assertGreater(len(dnp_files), 0)

    async def test_dnp_part_absent_from_pnp_in_zip(self):
        """U1 is DNP → U1 should NOT appear in the top P&P CSV inside the zip."""
        result = await self._call({
            "circuit_json": FIXTURE,
            "overrides": {"U1": {"fitted": False}},
            "variant_name": "noproc",
            "stem": "board",
        })
        import base64
        zip_bytes = base64.b64decode(result["zip_b64"])
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            pnp_names = [n for n in zf.namelist() if "pnp" in n and n.endswith(".csv")]
            self.assertTrue(pnp_names)
            pnp_contents = "".join(
                zf.read(n).decode("utf-8") for n in pnp_names
            )
        self.assertNotIn("U1", pnp_contents)

    async def test_zip_contains_gerbers(self):
        result = await self._call({
            "circuit_json": FIXTURE,
            "overrides": {},
            "variant_name": "base",
        })
        import base64
        zip_bytes = base64.b64decode(result["zip_b64"])
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            gerbers = [n for n in zf.namelist() if n.endswith(".GTL")]
        self.assertGreater(len(gerbers), 0)

    async def test_zip_contains_bom(self):
        result = await self._call({
            "circuit_json": FIXTURE,
            "overrides": {},
            "variant_name": "base",
        })
        import base64
        zip_bytes = base64.b64decode(result["zip_b64"])
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            bom_files = [n for n in zf.namelist() if "bom" in n and n.endswith(".csv")]
        self.assertGreater(len(bom_files), 0)

    async def test_named_variant_lookup(self):
        _VARIANT_STORE["v2"] = {"_meta": {}, "R2": {"fitted": False}}
        result = await self._call({
            "circuit_json": FIXTURE,
            "variant_name": "v2",
        })
        self.assertNotIn("error", result)
        self.assertEqual(result["dnp_count"], 1)
        self.assertIn("R2", result["dnp_parts"])

    async def test_unknown_variant_returns_error(self):
        result = await self._call({
            "circuit_json": FIXTURE,
            "variant_name": "ghost",
        })
        self.assertIn("error", result)

    async def test_dnp_parts_listed_in_result(self):
        result = await self._call({
            "circuit_json": FIXTURE,
            "overrides": {"R1": {"fitted": False}, "R2": {"fitted": False}},
            "variant_name": "low-cost",
        })
        self.assertEqual(result["dnp_count"], 2)
        self.assertIn("R1", result["dnp_parts"])
        self.assertIn("R2", result["dnp_parts"])


# ─── Tool spec / handler export check ────────────────────────────────────────

class TestVariantToolSpecs(unittest.TestCase):
    """Verify the module exports all four tool specs and async handlers."""

    def test_all_specs_present(self):
        from kerf_electronics.tools.variants import (
            define_variant_spec,
            list_variants_spec,
            variant_bom_spec,
            variant_fab_spec,
        )
        for spec in (define_variant_spec, list_variants_spec, variant_bom_spec, variant_fab_spec):
            self.assertTrue(hasattr(spec, "name"), f"Spec missing name: {spec}")

    def test_all_handlers_callable(self):
        from kerf_electronics.tools.variants import (
            run_define_variant,
            run_list_variants,
            run_variant_bom,
            run_variant_fab,
        )
        import asyncio
        for fn in (run_define_variant, run_list_variants, run_variant_bom, run_variant_fab):
            self.assertTrue(asyncio.iscoroutinefunction(fn), f"{fn.__name__} is not async")

    def test_spec_names_correct(self):
        from kerf_electronics.tools.variants import (
            define_variant_spec,
            list_variants_spec,
            variant_bom_spec,
            variant_fab_spec,
        )
        self.assertEqual(define_variant_spec.name, "define_variant")
        self.assertEqual(list_variants_spec.name, "list_variants")
        self.assertEqual(variant_bom_spec.name, "variant_bom")
        self.assertEqual(variant_fab_spec.name, "variant_fab")


if __name__ == "__main__":
    unittest.main()
