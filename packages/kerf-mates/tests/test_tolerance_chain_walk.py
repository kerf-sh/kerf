"""
Tests for the assembly mate chain-walk tolerance builder.

Covers:
  - Two-component chain (A→B) with one distance mate → 1 chain entry
  - Three-component linear chain (A→B→C) → 2 chain entries
  - Unreachable: no path → error dict
  - Tolerance accumulation: plus/minus from each link
  - Zero-contribution mates (coincident)
  - Per-mate tolerance slot {plus, minus}
  - fetch_part_dim callback injection
  - Same start == end returns empty chain
"""

import sys
import os

# Ensure packages are importable without install
_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(_HERE)
_PACKAGES_ROOT = os.path.dirname(_PLUGIN_ROOT)

if os.path.basename(_PACKAGES_ROOT) == "packages":
    for entry in os.listdir(_PACKAGES_ROOT):
        if not entry.startswith("kerf-"):
            continue
        src = os.path.join(_PACKAGES_ROOT, entry, "src")
        if os.path.isdir(src) and src not in sys.path:
            sys.path.insert(0, src)

from kerf_mates.chain_walk import build_chain_from_assembly


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_distance_mate(mate_id, comp_a, feat_a, comp_b, feat_b, value, unit="mm",
                       tol_plus=0.0, tol_minus=0.0):
    mate = {
        "id": mate_id,
        "type": "distance",
        "a": {"component_id": comp_a, "feature": "face", "feature_id": feat_a},
        "b": {"component_id": comp_b, "feature": "face", "feature_id": feat_b},
        "value": value,
        "unit": unit,
    }
    if tol_plus or tol_minus:
        mate["tolerance"] = {"plus": tol_plus, "minus": tol_minus}
    return mate


def make_coincident_mate(mate_id, comp_a, feat_a, comp_b, feat_b):
    return {
        "id": mate_id,
        "type": "coincident",
        "a": {"component_id": comp_a, "feature": "face", "feature_id": feat_a},
        "b": {"component_id": comp_b, "feature": "face", "feature_id": feat_b},
    }


def make_angle_mate(mate_id, comp_a, feat_a, comp_b, feat_b, value, unit="deg",
                    tol_plus=0.0, tol_minus=0.0):
    mate = {
        "id": mate_id,
        "type": "angle",
        "a": {"component_id": comp_a, "feature": "face", "feature_id": feat_a},
        "b": {"component_id": comp_b, "feature": "face", "feature_id": feat_b},
        "value": value,
        "unit": unit,
    }
    if tol_plus or tol_minus:
        mate["tolerance"] = {"plus": tol_plus, "minus": tol_minus}
    return mate


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_two_component_distance_chain():
    """A→B with one distance mate → chain has exactly one entry."""
    doc = {
        "mates": [
            make_distance_mate("m1", "compA", "faceA1", "compB", "faceB1", value=10.0),
        ]
    }
    start = {"component_id": "compA", "feature_id": "faceA1"}
    end = {"component_id": "compB", "feature_id": "faceB1"}

    chain = build_chain_from_assembly(doc, start, end)

    assert isinstance(chain, list), f"expected list, got {chain}"
    assert len(chain) == 1, f"expected 1 entry, got {len(chain)}"
    entry = chain[0]
    assert abs(entry["nominal"] - 10.0) < 1e-9
    assert entry["mate_type"] == "distance"
    assert entry["plus"] == 0.0
    assert entry["minus"] == 0.0


def test_three_component_linear_chain():
    """A→B→C with two distance mates → chain has two entries."""
    doc = {
        "mates": [
            make_distance_mate("m1", "compA", "faceA1", "compB", "faceB1", value=5.0),
            make_distance_mate("m2", "compB", "faceB2", "compC", "faceC1", value=3.0),
        ]
    }
    start = {"component_id": "compA", "feature_id": "faceA1"}
    end = {"component_id": "compC", "feature_id": "faceC1"}

    chain = build_chain_from_assembly(doc, start, end)

    assert isinstance(chain, list), f"expected list, got {chain}"
    assert len(chain) == 2, f"expected 2 entries, got {len(chain)}: {chain}"
    nominals = [e["nominal"] for e in chain]
    assert sorted(nominals) == sorted([5.0, 3.0]), f"nominals: {nominals}"


def test_unreachable_no_path():
    """No path exists → return error dict with code NO_PATH."""
    doc = {
        "mates": [
            make_distance_mate("m1", "compA", "faceA1", "compB", "faceB1", value=5.0),
            # compC is only connected to compD, not to A or B
            make_distance_mate("m2", "compC", "faceC1", "compD", "faceD1", value=2.0),
        ]
    }
    start = {"component_id": "compA", "feature_id": "faceA1"}
    end = {"component_id": "compC", "feature_id": "faceC1"}

    result = build_chain_from_assembly(doc, start, end)

    assert isinstance(result, dict), f"expected error dict, got {result}"
    assert "error" in result
    assert result.get("code") == "NO_PATH"


def test_tolerance_accumulation():
    """
    A→B (distance 5mm ±0.1/0.05) → B→C (distance 3mm ±0.08/0.08)
    Total worst-case plus = 0.1 + 0.08 = 0.18, minus = 0.05 + 0.08 = 0.13
    """
    doc = {
        "mates": [
            make_distance_mate("m1", "compA", "faceA1", "compB", "faceB1",
                               value=5.0, tol_plus=0.1, tol_minus=0.05),
            make_distance_mate("m2", "compB", "faceB2", "compC", "faceC1",
                               value=3.0, tol_plus=0.08, tol_minus=0.08),
        ]
    }
    start = {"component_id": "compA", "feature_id": "faceA1"}
    end = {"component_id": "compC", "feature_id": "faceC1"}

    chain = build_chain_from_assembly(doc, start, end)

    assert isinstance(chain, list), f"expected list, got {chain}"
    assert len(chain) == 2

    total_plus = sum(e["plus"] for e in chain)
    total_minus = sum(e["minus"] for e in chain)
    assert abs(total_plus - 0.18) < 1e-9, f"total plus {total_plus}"
    assert abs(total_minus - 0.13) < 1e-9, f"total minus {total_minus}"


def test_zero_contribution_coincident_mate():
    """Coincident mate → nominal=0, plus=0, minus=0."""
    doc = {
        "mates": [
            make_coincident_mate("m1", "compA", "faceA1", "compB", "faceB1"),
        ]
    }
    start = {"component_id": "compA", "feature_id": "faceA1"}
    end = {"component_id": "compB", "feature_id": "faceB1"}

    chain = build_chain_from_assembly(doc, start, end)

    assert isinstance(chain, list)
    assert len(chain) == 1
    entry = chain[0]
    assert entry["nominal"] == 0.0
    assert entry["plus"] == 0.0
    assert entry["minus"] == 0.0
    assert entry["mate_type"] == "coincident"


def test_angle_mate_contribution():
    """Angle mate with value=90 deg ±0.5 appears in chain."""
    doc = {
        "mates": [
            make_angle_mate("m1", "compA", "faceA1", "compB", "faceB1",
                            value=90.0, unit="deg", tol_plus=0.5, tol_minus=0.5),
        ]
    }
    start = {"component_id": "compA", "feature_id": "faceA1"}
    end = {"component_id": "compB", "feature_id": "faceB1"}

    chain = build_chain_from_assembly(doc, start, end)

    assert isinstance(chain, list)
    assert len(chain) == 1
    entry = chain[0]
    assert abs(entry["nominal"] - 90.0) < 1e-9
    assert abs(entry["plus"] - 0.5) < 1e-9
    assert abs(entry["minus"] - 0.5) < 1e-9
    assert entry["unit"] == "deg"


def test_start_equals_end():
    """start_ref == end_ref → empty chain (trivial)."""
    doc = {
        "mates": [
            make_distance_mate("m1", "compA", "faceA1", "compB", "faceB1", value=5.0),
        ]
    }
    ref = {"component_id": "compA", "feature_id": "faceA1"}
    chain = build_chain_from_assembly(doc, ref, ref)
    assert chain == []


def test_fetch_part_dim_callback():
    """
    fetch_part_dim is called for start node and nodes along the path.
    Contributions from the callback are inserted into the chain.
    """
    doc = {
        "mates": [
            make_distance_mate("m1", "compA", "faceA1", "compB", "faceB1", value=4.0),
        ]
    }
    start = {"component_id": "compA", "feature_id": "faceA1"}
    end = {"component_id": "compB", "feature_id": "faceB1"}

    calls = []

    def fake_fetch(comp_id, feat_id):
        calls.append((comp_id, feat_id))
        # Return a small part dimension for compA only
        if comp_id == "compA":
            return {"name": f"part:{comp_id}", "nominal": 1.5, "plus": 0.05, "minus": 0.05, "unit": "mm"}
        return None

    chain = build_chain_from_assembly(doc, start, end, fetch_part_dim=fake_fetch)

    assert isinstance(chain, list)
    # Should contain: part dim for compA (start), then mate m1, then nothing for compB
    assert len(chain) == 2, f"chain: {chain}"
    part_entries = [e for e in chain if e.get("source") != "mate"]
    assert len(part_entries) == 1
    assert abs(part_entries[0]["nominal"] - 1.5) < 1e-9
    # callback was invoked for start + end nodes
    assert len(calls) == 2


def test_no_mates_returns_error():
    """Assembly with no mates → both nodes absent → NO_PATH."""
    doc = {"mates": []}
    start = {"component_id": "compA", "feature_id": "faceA1"}
    end = {"component_id": "compB", "feature_id": "faceB1"}

    result = build_chain_from_assembly(doc, start, end)

    assert isinstance(result, dict)
    assert result.get("code") == "NO_PATH"


def test_missing_mates_key():
    """Assembly doc with no 'mates' key is treated as empty mates list."""
    doc = {"components": []}
    start = {"component_id": "compA", "feature_id": "faceA1"}
    end = {"component_id": "compB", "feature_id": "faceB1"}

    result = build_chain_from_assembly(doc, start, end)

    assert isinstance(result, dict)
    assert "error" in result


def test_tolerance_legacy_flat_fields():
    """tolerance_plus / tolerance_minus flat fields (solver.py convention) work."""
    doc = {
        "mates": [
            {
                "id": "m1",
                "type": "distance",
                "a": {"component_id": "compA", "feature": "face", "feature_id": "faceA1"},
                "b": {"component_id": "compB", "feature": "face", "feature_id": "faceB1"},
                "value": 7.0,
                "unit": "mm",
                "tolerance_plus": 0.2,
                "tolerance_minus": 0.1,
            }
        ]
    }
    start = {"component_id": "compA", "feature_id": "faceA1"}
    end = {"component_id": "compB", "feature_id": "faceB1"}

    chain = build_chain_from_assembly(doc, start, end)

    assert isinstance(chain, list)
    assert len(chain) == 1
    entry = chain[0]
    assert abs(entry["nominal"] - 7.0) < 1e-9
    assert abs(entry["plus"] - 0.2) < 1e-9
    assert abs(entry["minus"] - 0.1) < 1e-9


def test_four_component_chain_shortest_path():
    """
    Graph: A-B-C-D (linear).
    Also a longer path A-B-X-D exists.
    BFS finds A-B-C-D as shorter (3 edges) vs A-B-X-D (3 edges — same length,
    but this just verifies the path is found and correct length).
    Actual test: A→D via the linear chain = 3 distance mates.
    """
    doc = {
        "mates": [
            make_distance_mate("m1", "compA", "faceA1", "compB", "faceB1", value=1.0),
            make_distance_mate("m2", "compB", "faceB2", "compC", "faceC1", value=2.0),
            make_distance_mate("m3", "compC", "faceC2", "compD", "faceD1", value=3.0),
        ]
    }
    start = {"component_id": "compA", "feature_id": "faceA1"}
    end = {"component_id": "compD", "feature_id": "faceD1"}

    chain = build_chain_from_assembly(doc, start, end)

    assert isinstance(chain, list)
    assert len(chain) == 3
    total_nominal = sum(e["nominal"] for e in chain)
    assert abs(total_nominal - 6.0) < 1e-9


def main():
    test_two_component_distance_chain()
    print("test_two_component_distance_chain PASSED")
    test_three_component_linear_chain()
    print("test_three_component_linear_chain PASSED")
    test_unreachable_no_path()
    print("test_unreachable_no_path PASSED")
    test_tolerance_accumulation()
    print("test_tolerance_accumulation PASSED")
    test_zero_contribution_coincident_mate()
    print("test_zero_contribution_coincident_mate PASSED")
    test_angle_mate_contribution()
    print("test_angle_mate_contribution PASSED")
    test_start_equals_end()
    print("test_start_equals_end PASSED")
    test_fetch_part_dim_callback()
    print("test_fetch_part_dim_callback PASSED")
    test_no_mates_returns_error()
    print("test_no_mates_returns_error PASSED")
    test_missing_mates_key()
    print("test_missing_mates_key PASSED")
    test_tolerance_legacy_flat_fields()
    print("test_tolerance_legacy_flat_fields PASSED")
    test_four_component_chain_shortest_path()
    print("test_four_component_chain_shortest_path PASSED")
    print("\nAll chain-walk tests passed!")


if __name__ == "__main__":
    main()
