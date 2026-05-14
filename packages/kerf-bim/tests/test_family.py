"""Tests for family.py — pure logic, no DB required."""
from kerf_bim.tools.family import (
    validate_family_doc,
    resolve_params,
    _validate_param,
)


# ── validate_family_doc ────────────────────────────────────────────────────────

def test_valid_window_family():
    doc = {
        "version": 1,
        "name": "Standard Window",
        "category": "Window",
        "params": [
            {"name": "width", "type": "number", "default": 900, "min": 300, "max": 3000},
            {"name": "glazing", "type": "enum", "options": ["single", "double", "triple"], "default": "double"},
        ],
        "types": [],
    }
    errs = validate_family_doc(doc)
    assert errs == [], f"unexpected errors: {errs}"


def test_invalid_version():
    doc = {"version": 2, "name": "X", "category": "Door", "params": []}
    errs = validate_family_doc(doc)
    assert any("version" in e for e in errs)


def test_invalid_category():
    doc = {"version": 1, "name": "X", "category": "Spaceship", "params": []}
    errs = validate_family_doc(doc)
    assert any("category" in e for e in errs)


def test_duplicate_param_names():
    doc = {
        "version": 1, "name": "X", "category": "Wall",
        "params": [
            {"name": "width", "type": "number"},
            {"name": "width", "type": "number"},
        ],
    }
    errs = validate_family_doc(doc)
    assert any("duplicate" in e for e in errs)


def test_enum_no_options():
    doc = {
        "version": 1, "name": "X", "category": "Door",
        "params": [{"name": "swing", "type": "enum", "options": []}],
    }
    errs = validate_family_doc(doc)
    assert any("options" in e for e in errs)


def test_enum_default_not_in_options():
    doc = {
        "version": 1, "name": "X", "category": "Door",
        "params": [{"name": "swing", "type": "enum", "options": ["left", "right"], "default": "both"}],
    }
    errs = validate_family_doc(doc)
    assert any("not in options" in e for e in errs)


def test_number_min_gt_max():
    doc = {
        "version": 1, "name": "X", "category": "Window",
        "params": [{"name": "width", "type": "number", "min": 1000, "max": 500}],
    }
    errs = validate_family_doc(doc)
    assert any("min" in e and "max" in e for e in errs)


# ── resolve_params ─────────────────────────────────────────────────────────────

_FAMILY = {
    "version": 1, "name": "Window", "category": "Window",
    "params": [
        {"name": "width", "type": "number", "default": 900},
        {"name": "height", "type": "number", "default": 1200},
        {"name": "glazing", "type": "enum", "options": ["single", "double", "triple"], "default": "double"},
        {"name": "sill_height", "type": "number", "default": 900},
    ],
    "types": [
        {"id": "wide", "name": "Wide", "params": {"width": 1500, "glazing": "triple"}},
    ],
}


def test_resolve_defaults_only():
    r = resolve_params(_FAMILY, {})
    assert r["width"] == 900
    assert r["glazing"] == "double"


def test_resolve_instance_overrides_default():
    r = resolve_params(_FAMILY, {"params": {"width": 800}})
    assert r["width"] == 800
    assert r["height"] == 1200  # default unchanged


def test_resolve_type_overrides_default():
    r = resolve_params(_FAMILY, {"type_id": "wide"})
    assert r["width"] == 1500
    assert r["glazing"] == "triple"
    assert r["height"] == 1200  # default


def test_resolve_instance_overrides_type():
    r = resolve_params(_FAMILY, {"type_id": "wide", "params": {"width": 600, "sill_height": 850}})
    assert r["width"] == 600        # instance beats type
    assert r["glazing"] == "triple"  # type beats default
    assert r["sill_height"] == 850  # instance


def test_resolve_unknown_type_falls_back_to_defaults():
    r = resolve_params(_FAMILY, {"type_id": "nonexistent"})
    assert r["width"] == 900


# ── _validate_param ────────────────────────────────────────────────────────────

def test_validate_param_valid_number():
    errs = _validate_param({"name": "depth", "type": "number", "default": 300, "min": 100, "max": 1000}, 0)
    assert errs == []


def test_validate_param_bad_type():
    errs = _validate_param({"name": "x", "type": "blob"}, 0)
    assert any("type" in e for e in errs)


def test_validate_param_missing_name():
    errs = _validate_param({"name": "", "type": "number"}, 0)
    assert any("name" in e for e in errs)
