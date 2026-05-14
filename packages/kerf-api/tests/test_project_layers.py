"""
Tests for project-level layer + display-mode helpers.

All tests operate on plain dicts (no DB / async required).
We load project_layers.py directly via importlib to avoid the package
__init__.py which eagerly imports DB config and would fail without env vars.
"""
import importlib.util
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND = os.path.dirname(_HERE)
_TOOLS = os.path.join(_BACKEND, "tools")

# Load registry + context stubs first so project_layers.py can import them.
def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod  = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

if "tools.registry" not in sys.modules:
    _load_module("tools.registry", os.path.join(_TOOLS, "registry.py"))
if "tools.context" not in sys.modules:
    _load_module("tools.context", os.path.join(_TOOLS, "context.py"))
_pl = _load_module("tools.project_layers", os.path.join(_TOOLS, "project_layers.py"))

_default_canvas  = _pl._default_canvas
_next_layer_id   = _pl._next_layer_id
_HEX_RE          = _pl._HEX_RE


# ---------------------------------------------------------------------------
# Helpers (mirror JS helpers in Python for offline testing)
# ---------------------------------------------------------------------------

def add_layer(canvas, name, color="#aaaaaa", linetype="continuous", locked=False):
    import copy
    c = copy.deepcopy(canvas)
    new_id = _next_layer_id(c["layers"])
    c["layers"].append({
        "id": new_id, "name": name, "visible": True,
        "color": color, "linetype": linetype,
        "material_id": None, "locked": locked,
    })
    return c


def remove_layer(canvas, layer_id):
    import copy
    c = copy.deepcopy(canvas)
    filtered = [l for l in c["layers"] if l["id"] != layer_id]
    if len(filtered) == len(c["layers"]):
        return c
    if not filtered:
        raise ValueError("cannot remove the last layer")
    c["layers"] = filtered
    if c["active_layer"] == layer_id:
        c["active_layer"] = filtered[0]["id"]
    return c


def set_visibility(canvas, layer_id, visible):
    import copy
    c = copy.deepcopy(canvas)
    for l in c["layers"]:
        if l["id"] == layer_id:
            l["visible"] = visible
    return c


def set_color(canvas, layer_id, color):
    import copy
    if not _HEX_RE.match(color):
        raise ValueError(f"invalid color: {color}")
    c = copy.deepcopy(canvas)
    for l in c["layers"]:
        if l["id"] == layer_id:
            l["color"] = color
    return c


def set_active_layer(canvas, layer_id):
    import copy
    if not any(l["id"] == layer_id for l in canvas["layers"]):
        raise ValueError(f"layer {layer_id} not found")
    c = copy.deepcopy(canvas)
    c["active_layer"] = layer_id
    return c


def set_active_display_mode(canvas, mode_id):
    import copy
    if not any(m["id"] == mode_id for m in canvas["display_modes"]):
        raise ValueError(f"display mode {mode_id} not found")
    c = copy.deepcopy(canvas)
    c["active_display_mode"] = mode_id
    return c


# ---------------------------------------------------------------------------
# Tests: _default_canvas
# ---------------------------------------------------------------------------

def test_default_canvas_version():
    c = _default_canvas()
    assert c["version"] == 1


def test_default_canvas_has_one_layer():
    c = _default_canvas()
    assert len(c["layers"]) == 1
    assert c["layers"][0]["id"] == "L01"
    assert c["layers"][0]["name"] == "Geometry"


def test_default_canvas_four_display_modes():
    c = _default_canvas()
    ids = {m["id"] for m in c["display_modes"]}
    assert ids == {"shaded", "wireframe", "technical", "rendered"}


def test_default_active_mode():
    c = _default_canvas()
    assert c["active_display_mode"] == "shaded"


def test_default_active_layer():
    c = _default_canvas()
    assert c["active_layer"] == "L01"


# ---------------------------------------------------------------------------
# Tests: add / remove layers
# ---------------------------------------------------------------------------

def test_add_layer_assigns_id():
    c = add_layer(_default_canvas(), "Reference")
    assert len(c["layers"]) == 2
    assert c["layers"][1]["id"] == "L02"


def test_add_layer_preserves_original():
    orig = _default_canvas()
    add_layer(orig, "Extra")
    assert len(orig["layers"]) == 1


def test_add_multiple_layers_sequential_ids():
    c = _default_canvas()
    c = add_layer(c, "A")
    c = add_layer(c, "B")
    ids = [l["id"] for l in c["layers"]]
    assert ids == ["L01", "L02", "L03"]


def test_remove_layer_by_id():
    c = add_layer(_default_canvas(), "Temp")
    c = remove_layer(c, "L02")
    assert len(c["layers"]) == 1


def test_remove_active_layer_redirects_active():
    c = add_layer(_default_canvas(), "Second")
    c = set_active_layer(c, "L02")
    c = remove_layer(c, "L02")
    assert c["active_layer"] == "L01"


def test_remove_last_layer_raises():
    c = _default_canvas()
    try:
        remove_layer(c, "L01")
        assert False, "should have raised"
    except ValueError as e:
        assert "last" in str(e).lower()


def test_remove_unknown_id_noop():
    c = _default_canvas()
    c2 = remove_layer(c, "UNKNOWN")
    assert len(c2["layers"]) == len(c["layers"])


# ---------------------------------------------------------------------------
# Tests: visibility / color / active mode
# ---------------------------------------------------------------------------

def test_set_visibility_false():
    c = set_visibility(_default_canvas(), "L01", False)
    assert c["layers"][0]["visible"] is False


def test_set_color_valid():
    c = set_color(_default_canvas(), "L01", "#ff0000")
    assert c["layers"][0]["color"] == "#ff0000"


def test_set_color_invalid_raises():
    try:
        set_color(_default_canvas(), "L01", "red")
        assert False, "should have raised"
    except ValueError:
        pass


def test_switch_display_mode():
    c = set_active_display_mode(_default_canvas(), "wireframe")
    assert c["active_display_mode"] == "wireframe"


def test_switch_display_mode_invalid_raises():
    try:
        set_active_display_mode(_default_canvas(), "xray")
        assert False, "should have raised"
    except ValueError:
        pass


# ---------------------------------------------------------------------------
# Tests: canvas JSON round-trip
# ---------------------------------------------------------------------------

def test_canvas_json_roundtrip():
    c = _default_canvas()
    c = add_layer(c, "Drawing", color="#00aaff")
    serialised = json.dumps(c)
    restored = json.loads(serialised)
    assert restored["layers"][1]["name"] == "Drawing"
    assert restored["layers"][1]["color"] == "#00aaff"


# ---------------------------------------------------------------------------
# Tests: _next_layer_id gaps
# ---------------------------------------------------------------------------

def test_next_id_avoids_collision():
    # Manually create a canvas with L01 and L02 already taken.
    c = _default_canvas()
    c["layers"].append({"id": "L02", "name": "B", "visible": True, "color": "#fff",
                        "linetype": "continuous", "material_id": None, "locked": False})
    nid = _next_layer_id(c["layers"])
    # L01 and L02 are taken; next should be L03.
    assert nid == "L03"
    assert nid not in {l["id"] for l in c["layers"]}
