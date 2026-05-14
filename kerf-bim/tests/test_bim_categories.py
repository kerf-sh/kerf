"""
test_bim_categories.py — pytest suite for bim_categories.py pure logic.
No DB required; uses stub registry/context pattern.
"""
import importlib.util
import json
import sys
import types

_TOOLS = "/Users/pc/code/exo/kerf/.claude/worktrees/agent-a32c4befabb8b2b49/kerf-bim/src/kerf_bim/tools"

# ── Stub dependencies so @register calls don't blow up ────────────────────────

_reg_stub = types.ModuleType("tools.registry")
_reg_stub.ToolSpec = type("ToolSpec", (), {"__init__": lambda s, **kw: s.__dict__.update(kw)})
_reg_stub.err_payload = lambda msg, code: json.dumps({"error": msg, "code": code})
_reg_stub.ok_payload = lambda v: json.dumps(v)
_reg_stub.register = lambda spec, write=False: (lambda fn: fn)
sys.modules.setdefault("tools.registry", _reg_stub)

_ctx_stub = types.ModuleType("tools.context")
_ctx_stub.ProjectCtx = type("ProjectCtx", (), {})
sys.modules.setdefault("tools.context", _ctx_stub)

# Stub tools.bim — we only need function names, not the real implementations
_bim_stub = types.ModuleType("tools.bim")
_bim_stub.ensure_folders = None
_bim_stub.record_revision_for_file = None
_bim_stub.resolve_path = None
_bim_stub.serialize_bim = lambda d: json.dumps(d)
sys.modules.setdefault("tools.bim", _bim_stub)

# ── Load module under test ─────────────────────────────────────────────────────

_spec = importlib.util.spec_from_file_location(
    "tools.bim_categories", f"{_TOOLS}/bim_categories.py"
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["tools.bim_categories"] = _mod
_spec.loader.exec_module(_mod)

# Pull in the pure helpers
CATEGORIES = _mod.CATEGORIES
HOST_RULES  = _mod.HOST_RULES
validate_category        = _mod.validate_category
validate_host_ref        = _mod.validate_host_ref
find_hosted_elements     = _mod.find_hosted_elements
cascade_transform        = _mod.cascade_transform
remove_with_hosted       = _mod.remove_with_hosted
validate_bim_categories_doc = _mod.validate_bim_categories_doc

# ── Fixtures ───────────────────────────────────────────────────────────────────

def make_doc(**extra):
    doc = {
        "version": 1,
        "walls": [
            {"id": "w1", "category": "Wall", "from": [0, 0], "to": [5000, 0]},
            {"id": "w2", "category": "Wall", "from": [5000, 0], "to": [5000, 4000]},
        ],
        "openings": [
            {"id": "d1", "category": "Door", "host_ref": "w1", "position": [1000, 0, 0]},
            {"id": "win1", "category": "Window", "host_ref": "w1", "position": [2000, 0, 1000]},
            {"id": "d2", "category": "Door", "host_ref": "w2", "position": [5000, 1000, 0]},
        ],
    }
    doc.update(extra)
    return doc


# ── validate_category ──────────────────────────────────────────────────────────

def test_validate_category_all_valid():
    for c in CATEGORIES:
        assert validate_category(c), f"{c} should be valid"


def test_validate_category_rejects_unknown():
    assert validate_category("Spaceship") is False


def test_validate_category_rejects_empty():
    assert validate_category("") is False


# ── validate_host_ref ──────────────────────────────────────────────────────────

def test_door_on_wall_valid():
    assert validate_host_ref("Door", "Wall") is True


def test_door_on_floor_invalid():
    assert validate_host_ref("Door", "Floor") is False


def test_window_on_wall_valid():
    assert validate_host_ref("Window", "Wall") is True


def test_casework_on_floor_or_wall():
    assert validate_host_ref("Casework", "Floor") is True
    assert validate_host_ref("Casework", "Wall") is True
    assert validate_host_ref("Casework", "Roof") is False


def test_mep_duct_cannot_be_hosted():
    assert validate_host_ref("MEP_Duct", "Wall") is False
    assert validate_host_ref("MEP_Duct", "Floor") is False


def test_mep_pipe_cannot_be_hosted():
    assert validate_host_ref("MEP_Pipe", "Wall") is False


def test_mep_conduit_cannot_be_hosted():
    assert validate_host_ref("MEP_Conduit", "Beam") is False


def test_generic_unconstrained():
    for c in CATEGORIES:
        assert validate_host_ref("Generic", c) is True, f"Generic on {c} should be allowed"


# ── find_hosted_elements ───────────────────────────────────────────────────────

def test_find_hosted_direct_children():
    doc = make_doc()
    hosted = find_hosted_elements(doc, "w1")
    assert set(hosted) == {"d1", "win1"}


def test_find_hosted_only_direct():
    doc = make_doc(fixtures=[{"id": "f1", "category": "Casework", "host_ref": "d1"}])
    assert "f1" not in find_hosted_elements(doc, "w1")
    assert "f1" in find_hosted_elements(doc, "d1")


def test_find_hosted_empty():
    doc = make_doc()
    assert find_hosted_elements(doc, "nonexistent") == []


# ── cascade_transform ──────────────────────────────────────────────────────────

def test_cascade_moves_host():
    doc = make_doc()
    result = cascade_transform(doc, "w1", [100, 200, 0])
    w1 = next(e for e in result["walls"] if e["id"] == "w1")
    assert w1["from"] == [100, 200]
    assert w1["to"] == [5100, 200]


def test_cascade_moves_hosted_children():
    doc = make_doc()
    result = cascade_transform(doc, "w1", [500, 0, 0])
    d1 = next(e for e in result["openings"] if e["id"] == "d1")
    assert d1["position"] == [1500, 0, 0]
    win1 = next(e for e in result["openings"] if e["id"] == "win1")
    assert win1["position"] == [2500, 0, 1000]


def test_cascade_does_not_move_unrelated():
    doc = make_doc()
    result = cascade_transform(doc, "w1", [500, 0, 0])
    d2 = next(e for e in result["openings"] if e["id"] == "d2")
    assert d2["position"] == [5000, 1000, 0]


def test_cascade_recursive_grandchildren():
    doc = make_doc(fixtures=[{"id": "f1", "category": "Casework", "host_ref": "d1", "position": [1050, 10, 900]}])
    result = cascade_transform(doc, "w1", [0, 300, 0])
    f1 = next(e for e in result["fixtures"] if e["id"] == "f1")
    assert f1["position"] == [1050, 310, 900]


def test_cascade_does_not_mutate_original():
    doc = make_doc()
    original = json.dumps(doc)
    cascade_transform(doc, "w1", [999, 0, 0])
    assert json.dumps(doc) == original


# ── remove_with_hosted ─────────────────────────────────────────────────────────

def test_remove_removes_element():
    doc = make_doc()
    new_doc, _ = remove_with_hosted(doc, "w2")
    ids = [e["id"] for e in new_doc["walls"]]
    assert "w2" not in ids


def test_remove_removes_hosted_children():
    doc = make_doc()
    new_doc, _ = remove_with_hosted(doc, "w1")
    ids = [e["id"] for e in new_doc["openings"]]
    assert "d1" not in ids
    assert "win1" not in ids


def test_remove_preserves_other_elements():
    doc = make_doc()
    new_doc, _ = remove_with_hosted(doc, "w1")
    ids = [e["id"] for e in new_doc["openings"]]
    assert "d2" in ids


def test_remove_grandchildren_recursive():
    doc = make_doc(fixtures=[{"id": "f1", "category": "Casework", "host_ref": "d1"}])
    new_doc, _ = remove_with_hosted(doc, "w1")
    ids = [e["id"] for e in new_doc["fixtures"]]
    assert "f1" not in ids


def test_remove_does_not_mutate_original():
    doc = make_doc()
    original = json.dumps(doc)
    remove_with_hosted(doc, "w1")
    assert json.dumps(doc) == original


# ── validate_bim_categories_doc ────────────────────────────────────────────────

def test_validate_clean_doc():
    doc = make_doc()
    result = validate_bim_categories_doc(doc)
    assert result["ok"] is True
    assert result["errors"] == []


def test_validate_bad_category():
    doc = make_doc()
    doc["walls"][0]["category"] = "Spaceship"
    result = validate_bim_categories_doc(doc)
    assert result["ok"] is False
    assert any("Spaceship" in e for e in result["errors"])


def test_validate_dangling_host_ref():
    doc = make_doc()
    doc["openings"][0]["host_ref"] = "does_not_exist"
    result = validate_bim_categories_doc(doc)
    assert result["ok"] is False
    assert any("does_not_exist" in e for e in result["errors"])


def test_validate_invalid_host_category_pair():
    doc = make_doc()
    # Put a Door hosted on a Floor (invalid per HOST_RULES)
    doc["slabs"] = [{"id": "slab1", "category": "Floor"}]
    doc["openings"][0]["host_ref"] = "slab1"
    result = validate_bim_categories_doc(doc)
    assert result["ok"] is False
    assert any("Door" in e and "Floor" in e for e in result["errors"])
