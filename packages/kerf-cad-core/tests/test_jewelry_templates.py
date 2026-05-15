"""
Tests for kerf_cad_core.jewelry.templates

Hermetic: no external I/O, no OCCT, no real ProjectCtx.
All async tools are driven via asyncio.run().

Coverage:
  - Registry completeness (≥30 templates, all 5 categories present)
  - Every template has required schema fields
  - All template metal keys exist in METAL_DENSITY_G_CM3
  - All template component gem-cut keys exist in GEMSTONE_CUTS
  - list_templates() returns correct counts and category filtering
  - get_template() returns deep copies (mutation isolation)
  - instantiate() base case and override merging
  - LLM tool list_jewelry_templates: success, category filter, bad category
  - LLM tool instantiate_jewelry_template: success, overrides, bad id, bad metal, bad args
  - Plugin loader discovers the module via importlib
"""

from __future__ import annotations

import asyncio
import copy
import importlib
import json
import uuid

import pytest

# Pure-Python API under test
from kerf_cad_core.jewelry.templates import (
    _TEMPLATES,
    _TEMPLATE_INDEX,
    get_template,
    list_templates,
    instantiate,
    list_jewelry_templates_spec,
    run_list_jewelry_templates,
    instantiate_jewelry_template_spec,
    run_instantiate_jewelry_template,
)
from kerf_cad_core.jewelry.metal_cost import METAL_DENSITY_G_CM3
from kerf_cad_core.jewelry.gemstones import GEMSTONE_CUTS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_ctx():
    """Return a minimal fake ProjectCtx (the tools don't use it)."""
    from unittest.mock import MagicMock
    return MagicMock()


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def ok(raw: str) -> dict:
    """Parse a successful tool response (plain JSON dict from ok_payload)."""
    d = json.loads(raw)
    # ok_payload just serializes the value — the response should NOT contain "error"
    assert "error" not in d, f"Expected success payload, got error: {raw}"
    return d


def err(raw: str, code: str | None = None) -> dict:
    """Parse an error tool response from err_payload."""
    d = json.loads(raw)
    assert "error" in d, f"Expected error payload, got: {raw}"
    if code:
        assert d.get("code") == code, f"Expected code={code!r}, got {d.get('code')!r}"
    return d


def args(**kwargs) -> bytes:
    return json.dumps(kwargs).encode()


# ---------------------------------------------------------------------------
# 1. Registry completeness
# ---------------------------------------------------------------------------

def test_at_least_30_templates():
    assert len(_TEMPLATES) >= 30, f"Expected ≥30 templates, got {len(_TEMPLATES)}"


def test_all_5_categories_present():
    cats = {t["category"] for t in _TEMPLATES}
    assert cats == {"rings", "earrings", "pendants", "bracelets", "misc"}


def test_rings_category_count():
    rings = [t for t in _TEMPLATES if t["category"] == "rings"]
    assert len(rings) >= 10, f"Expected ≥10 ring templates, got {len(rings)}"


def test_earrings_category_count():
    earrings = [t for t in _TEMPLATES if t["category"] == "earrings"]
    assert len(earrings) >= 5


def test_pendants_category_count():
    pendants = [t for t in _TEMPLATES if t["category"] == "pendants"]
    assert len(pendants) >= 5


def test_bracelets_category_count():
    bracelets = [t for t in _TEMPLATES if t["category"] == "bracelets"]
    assert len(bracelets) >= 5


def test_misc_category_count():
    misc = [t for t in _TEMPLATES if t["category"] == "misc"]
    assert len(misc) >= 5


def test_template_index_matches_list():
    assert len(_TEMPLATE_INDEX) == len(_TEMPLATES)
    for t in _TEMPLATES:
        assert t["template_id"] in _TEMPLATE_INDEX


def test_no_duplicate_template_ids():
    ids = [t["template_id"] for t in _TEMPLATES]
    assert len(ids) == len(set(ids)), "Duplicate template_id found"


# ---------------------------------------------------------------------------
# 2. Schema validation for every template
# ---------------------------------------------------------------------------

REQUIRED_TOP_LEVEL = {"template_id", "name", "category", "description",
                      "metal", "components", "tags"}

@pytest.mark.parametrize("t", _TEMPLATES, ids=[t["template_id"] for t in _TEMPLATES])
def test_template_has_required_fields(t):
    missing = REQUIRED_TOP_LEVEL - set(t.keys())
    assert not missing, f"{t['template_id']} missing fields: {missing}"


@pytest.mark.parametrize("t", _TEMPLATES, ids=[t["template_id"] for t in _TEMPLATES])
def test_template_components_nonempty(t):
    assert isinstance(t["components"], list) and len(t["components"]) >= 1


@pytest.mark.parametrize("t", _TEMPLATES, ids=[t["template_id"] for t in _TEMPLATES])
def test_template_component_schema(t):
    for i, comp in enumerate(t["components"]):
        assert "tool" in comp, f"{t['template_id']}[{i}] missing 'tool'"
        assert "role" in comp, f"{t['template_id']}[{i}] missing 'role'"
        assert "params" in comp, f"{t['template_id']}[{i}] missing 'params'"
        assert isinstance(comp["params"], dict)


@pytest.mark.parametrize("t", _TEMPLATES, ids=[t["template_id"] for t in _TEMPLATES])
def test_template_tags_list(t):
    assert isinstance(t["tags"], list) and len(t["tags"]) >= 1


@pytest.mark.parametrize("t", _TEMPLATES, ids=[t["template_id"] for t in _TEMPLATES])
def test_template_name_nonempty(t):
    assert isinstance(t["name"], str) and len(t["name"]) > 0


@pytest.mark.parametrize("t", _TEMPLATES, ids=[t["template_id"] for t in _TEMPLATES])
def test_template_description_nonempty(t):
    assert isinstance(t["description"], str) and len(t["description"]) > 10


# ---------------------------------------------------------------------------
# 3. Metal key validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("t", _TEMPLATES, ids=[t["template_id"] for t in _TEMPLATES])
def test_template_metal_valid(t):
    assert t["metal"] in METAL_DENSITY_G_CM3, (
        f"{t['template_id']} uses unknown metal '{t['metal']}'"
    )


# ---------------------------------------------------------------------------
# 4. Gem cut key validation
# ---------------------------------------------------------------------------

def _extract_cuts(t: dict) -> list[str]:
    cuts = []
    for comp in t["components"]:
        p = comp.get("params", {})
        for key in ("cut", "stone_cut", "border_stone_cut"):
            if key in p:
                cuts.append(p[key])
    return cuts


@pytest.mark.parametrize("t", _TEMPLATES, ids=[t["template_id"] for t in _TEMPLATES])
def test_template_cuts_valid(t):
    for cut in _extract_cuts(t):
        assert cut in GEMSTONE_CUTS, (
            f"{t['template_id']} uses unknown cut '{cut}'"
        )


# ---------------------------------------------------------------------------
# 5. Pure-Python API: list_templates
# ---------------------------------------------------------------------------

def test_list_templates_all():
    rows = list_templates()
    assert len(rows) == len(_TEMPLATES)


def test_list_templates_category_rings():
    rows = list_templates(category="rings")
    assert all(r["category"] == "rings" for r in rows)
    assert len(rows) >= 10


def test_list_templates_category_earrings():
    rows = list_templates(category="earrings")
    assert all(r["category"] == "earrings" for r in rows)
    assert len(rows) >= 5


def test_list_templates_category_misc():
    rows = list_templates(category="misc")
    assert all(r["category"] == "misc" for r in rows)
    assert len(rows) >= 5


def test_list_templates_unknown_category_returns_empty():
    rows = list_templates(category="nonexistent")
    assert rows == []


def test_list_templates_row_fields():
    rows = list_templates()
    required = {"template_id", "name", "category", "description",
                "metal", "tags", "component_count"}
    for row in rows:
        assert required.issubset(set(row.keys()))


# ---------------------------------------------------------------------------
# 6. Pure-Python API: get_template
# ---------------------------------------------------------------------------

def test_get_template_returns_copy():
    t1 = get_template("ring_solitaire_round")
    t2 = get_template("ring_solitaire_round")
    assert t1 is not t2
    t1["name"] = "MUTATED"
    t3 = get_template("ring_solitaire_round")
    assert t3["name"] != "MUTATED"


def test_get_template_unknown_returns_none():
    assert get_template("does_not_exist") is None


def test_get_template_all_ids_resolve():
    for t in _TEMPLATES:
        result = get_template(t["template_id"])
        assert result is not None
        assert result["template_id"] == t["template_id"]


# ---------------------------------------------------------------------------
# 7. Pure-Python API: instantiate
# ---------------------------------------------------------------------------

def test_instantiate_base_case():
    recipe = instantiate("ring_solitaire_round")
    assert recipe is not None
    assert recipe["template_id"] == "ring_solitaire_round"
    assert recipe["metal"] == "18k_white"


def test_instantiate_unknown_returns_none():
    assert instantiate("xyz_does_not_exist") is None


def test_instantiate_metal_override():
    recipe = instantiate("ring_solitaire_round", overrides={"metal": "14k_yellow"})
    assert recipe["metal"] == "14k_yellow"


def test_instantiate_component_params_override():
    recipe = instantiate(
        "ring_solitaire_round",
        overrides={"components": [{"index": 0, "params": {"ring_size": 8}}]},
    )
    assert recipe["components"][0]["params"]["ring_size"] == 8
    # Other params not patched should still be present
    assert "band_width" in recipe["components"][0]["params"]


def test_instantiate_no_mutation_of_registry():
    instantiate("ring_halo", overrides={"metal": "14k_rose"})
    original = get_template("ring_halo")
    assert original["metal"] == "18k_white"  # default unchanged


def test_instantiate_name_override():
    recipe = instantiate("pendant_solitaire", overrides={"name": "Custom Pendant"})
    assert recipe["name"] == "Custom Pendant"


def test_instantiate_none_overrides_is_safe():
    recipe = instantiate("ring_eternity", overrides=None)
    assert recipe is not None


def test_instantiate_component_index_out_of_range_is_safe():
    # index 99 should silently be ignored
    recipe = instantiate("ring_eternity", overrides={
        "components": [{"index": 99, "params": {"foo": "bar"}}]
    })
    assert recipe is not None


# ---------------------------------------------------------------------------
# 8. LLM tool: list_jewelry_templates
# ---------------------------------------------------------------------------

def test_llm_list_all():
    ctx = make_ctx()
    result = run(run_list_jewelry_templates(ctx, b"{}"))
    d = ok(result)
    assert d["total"] >= 30
    assert len(d["templates"]) >= 30


def test_llm_list_category_rings():
    ctx = make_ctx()
    result = run(run_list_jewelry_templates(ctx, args(category="rings")))
    d = ok(result)
    templates = d["templates"]
    assert len(templates) >= 10
    assert all(t["category"] == "rings" for t in templates)


def test_llm_list_category_earrings():
    ctx = make_ctx()
    result = run(run_list_jewelry_templates(ctx, args(category="earrings")))
    d = ok(result)
    assert len(d["templates"]) >= 5


def test_llm_list_category_pendants():
    ctx = make_ctx()
    result = run(run_list_jewelry_templates(ctx, args(category="pendants")))
    d = ok(result)
    assert len(d["templates"]) >= 5


def test_llm_list_category_bracelets():
    ctx = make_ctx()
    result = run(run_list_jewelry_templates(ctx, args(category="bracelets")))
    d = ok(result)
    assert len(d["templates"]) >= 5


def test_llm_list_category_misc():
    ctx = make_ctx()
    result = run(run_list_jewelry_templates(ctx, args(category="misc")))
    d = ok(result)
    assert len(d["templates"]) >= 5


def test_llm_list_bad_category():
    ctx = make_ctx()
    result = run(run_list_jewelry_templates(ctx, args(category="UNKNOWN")))
    err(result, "BAD_ARGS")


def test_llm_list_bad_json():
    ctx = make_ctx()
    result = run(run_list_jewelry_templates(ctx, b"{not json"))
    err(result, "BAD_ARGS")


def test_llm_list_categories_field_present():
    ctx = make_ctx()
    result = run(run_list_jewelry_templates(ctx, b"{}"))
    d = ok(result)
    assert "categories" in d


# ---------------------------------------------------------------------------
# 9. LLM tool: instantiate_jewelry_template
# ---------------------------------------------------------------------------

def test_llm_instantiate_round_solitaire():
    ctx = make_ctx()
    result = run(run_instantiate_jewelry_template(
        ctx, args(template_id="ring_solitaire_round")
    ))
    d = ok(result)
    assert d["template_id"] == "ring_solitaire_round"
    assert len(d["components"]) >= 2


def test_llm_instantiate_all_templates():
    """Every template ID must instantiate successfully via the LLM tool."""
    ctx = make_ctx()
    for t in _TEMPLATES:
        result = run(run_instantiate_jewelry_template(
            ctx, args(template_id=t["template_id"])
        ))
        d = ok(result)
        assert d["template_id"] == t["template_id"]


def test_llm_instantiate_metal_override():
    ctx = make_ctx()
    result = run(run_instantiate_jewelry_template(
        ctx,
        args(template_id="ring_solitaire_round", overrides={"metal": "platinum_950"}),
    ))
    d = ok(result)
    assert d["metal"] == "platinum_950"


def test_llm_instantiate_component_param_override():
    ctx = make_ctx()
    result = run(run_instantiate_jewelry_template(
        ctx,
        args(
            template_id="ring_solitaire_round",
            overrides={"components": [{"index": 0, "params": {"ring_size": 9}}]},
        ),
    ))
    d = ok(result)
    assert d["components"][0]["params"]["ring_size"] == 9


def test_llm_instantiate_bad_template_id():
    ctx = make_ctx()
    result = run(run_instantiate_jewelry_template(
        ctx, args(template_id="does_not_exist_xyz")
    ))
    err(result, "BAD_ARGS")


def test_llm_instantiate_missing_template_id():
    ctx = make_ctx()
    result = run(run_instantiate_jewelry_template(ctx, b"{}"))
    err(result, "BAD_ARGS")


def test_llm_instantiate_bad_metal_override():
    ctx = make_ctx()
    result = run(run_instantiate_jewelry_template(
        ctx,
        args(template_id="ring_solitaire_round", overrides={"metal": "unobtainium"}),
    ))
    err(result, "BAD_ARGS")


def test_llm_instantiate_bad_json():
    ctx = make_ctx()
    result = run(run_instantiate_jewelry_template(ctx, b"not json at all"))
    err(result, "BAD_ARGS")


def test_llm_instantiate_bad_overrides_type():
    ctx = make_ctx()
    result = run(run_instantiate_jewelry_template(
        ctx,
        args(template_id="ring_solitaire_round", overrides="not-a-dict"),
    ))
    err(result, "BAD_ARGS")


def test_llm_instantiate_no_mutation_between_calls():
    """Two successive instantiations of the same template return independent dicts."""
    ctx = make_ctx()
    r1 = run(run_instantiate_jewelry_template(ctx, args(template_id="ring_halo")))
    r2 = run(run_instantiate_jewelry_template(ctx, args(template_id="ring_halo")))
    d1 = ok(r1)
    d2 = ok(r2)
    d1["name"] = "MUTATED"
    assert d2["name"] != "MUTATED"


# ---------------------------------------------------------------------------
# 10. ToolSpec registration
# ---------------------------------------------------------------------------

def test_list_spec_name():
    assert list_jewelry_templates_spec.name == "list_jewelry_templates"


def test_instantiate_spec_name():
    assert instantiate_jewelry_template_spec.name == "instantiate_jewelry_template"


def test_list_spec_has_input_schema():
    assert isinstance(list_jewelry_templates_spec.input_schema, dict)


def test_instantiate_spec_requires_template_id():
    required = instantiate_jewelry_template_spec.input_schema.get("required", [])
    assert "template_id" in required


# ---------------------------------------------------------------------------
# 11. Plugin loader
# ---------------------------------------------------------------------------

def test_importlib_loads_module():
    mod = importlib.import_module("kerf_cad_core.jewelry.templates")
    assert hasattr(mod, "run_list_jewelry_templates")
    assert hasattr(mod, "run_instantiate_jewelry_template")
    assert hasattr(mod, "_TEMPLATES")


def test_plugin_module_in_tool_modules():
    import kerf_cad_core.plugin as plugin_mod
    assert "kerf_cad_core.jewelry.templates" in plugin_mod._TOOL_MODULES
