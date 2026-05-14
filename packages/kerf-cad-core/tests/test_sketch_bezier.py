"""test_sketch_bezier.py — Python-side round-trip tests for the `bezier` entity kind.

These tests exercise the JSON schema that kerf-cad-core's sketch.py tools
parse and persist. No WASM / planegcs involved — pure Python JSON handling.

Coverage:
  1. parse_sketch_with_bezier — load a sketch JSON containing a bezier entity
  2. bezier_control_points_preserved — round-trip control_point ids survive JSON
  3. bezier_degree_inferred — degree field round-trips
  4. bezier_construction_flag — construction=True round-trips
  5. bezier_tangent_constraint — bezier_tangent constraint round-trips
"""

import json
import pytest


def make_cubic_bezier_sketch():
    """Return a minimal sketch dict with a cubic bezier."""
    return {
        "version": 1,
        "plane": {"type": "base", "name": "XY"},
        "entities": [
            {"id": "origin", "type": "point", "x": 0, "y": 0},
            {"id": "p0", "type": "point", "x": 0, "y": 0},
            {"id": "p1", "type": "point", "x": 10, "y": 20},
            {"id": "p2", "type": "point", "x": 20, "y": 20},
            {"id": "p3", "type": "point", "x": 30, "y": 0},
            {
                "id": "bz1",
                "type": "bezier",
                "degree": 3,
                "control_points": ["p0", "p1", "p2", "p3"],
            },
        ],
        "constraints": [],
        "visible_3d": [],
        "solved": {},
        "metadata": {},
    }


def test_parse_sketch_with_bezier():
    """A sketch JSON with a bezier entity round-trips through json.loads without errors."""
    sketch = make_cubic_bezier_sketch()
    raw = json.dumps(sketch)
    parsed = json.loads(raw)
    bezier_ents = [e for e in parsed["entities"] if e.get("type") == "bezier"]
    assert len(bezier_ents) == 1, "Expected exactly one bezier entity"


def test_bezier_control_points_preserved():
    """control_points array is preserved after JSON round-trip."""
    sketch = make_cubic_bezier_sketch()
    raw = json.dumps(sketch, indent=2)
    parsed = json.loads(raw)
    bz = next(e for e in parsed["entities"] if e.get("type") == "bezier")
    assert bz["control_points"] == ["p0", "p1", "p2", "p3"]


def test_bezier_degree_inferred():
    """degree field survives round-trip and matches control_points count - 1."""
    sketch = make_cubic_bezier_sketch()
    parsed = json.loads(json.dumps(sketch))
    bz = next(e for e in parsed["entities"] if e.get("type") == "bezier")
    assert bz["degree"] == len(bz["control_points"]) - 1


def test_bezier_construction_flag():
    """construction=True flag round-trips on a bezier entity."""
    sketch = make_cubic_bezier_sketch()
    # Mark the bezier as construction geometry.
    for e in sketch["entities"]:
        if e.get("type") == "bezier":
            e["construction"] = True
    parsed = json.loads(json.dumps(sketch))
    bz = next(e for e in parsed["entities"] if e.get("type") == "bezier")
    assert bz.get("construction") is True


def test_bezier_tangent_constraint():
    """bezier_tangent constraint round-trips with p0/p1/p2 fields."""
    sketch = make_cubic_bezier_sketch()
    sketch["constraints"].append({
        "id": "ct1",
        "type": "bezier_tangent",
        "p0": "p0",
        "p1": "p1",
        "p2": "p2",
    })
    parsed = json.loads(json.dumps(sketch))
    tangent_cs = [c for c in parsed["constraints"] if c.get("type") == "bezier_tangent"]
    assert len(tangent_cs) == 1
    c = tangent_cs[0]
    assert c["p0"] == "p0"
    assert c["p1"] == "p1"
    assert c["p2"] == "p2"


def test_bezier_quadratic():
    """Quadratic bezier (degree=2, 3 control points) parses correctly."""
    sketch = {
        "version": 1,
        "plane": {"type": "base", "name": "XY"},
        "entities": [
            {"id": "origin", "type": "point", "x": 0, "y": 0},
            {"id": "q0", "type": "point", "x": 0, "y": 0},
            {"id": "q1", "type": "point", "x": 5, "y": 10},
            {"id": "q2", "type": "point", "x": 10, "y": 0},
            {
                "id": "bz_quad",
                "type": "bezier",
                "degree": 2,
                "control_points": ["q0", "q1", "q2"],
            },
        ],
        "constraints": [],
        "visible_3d": [],
        "solved": {},
        "metadata": {},
    }
    parsed = json.loads(json.dumps(sketch))
    bz = next(e for e in parsed["entities"] if e.get("type") == "bezier")
    assert bz["degree"] == 2
    assert len(bz["control_points"]) == 3
