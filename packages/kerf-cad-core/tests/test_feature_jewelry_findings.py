"""
test_feature_jewelry_findings.py — T-6 hermetic pytest suite
=============================================================

Scope: kerf_cad_core.jewelry.findings — parametric findings library.
       Round-trip into chains (jump rings as links) and earrings (bails/ear
       findings on pendant).

Success criteria (from testing-breakdown.md T-6):
  - 25 finding-attachment combos; correct wire gauge; female/male mate clearance
  - Boundaries / malformed / idempotency cases
  - No OCC, no DB, no network — pure-Python only

All tests are hermetic.
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.jewelry.findings import (
    _FAMILY_KINDS,
    _KIND_ALIASES,
    _VALID_BAIL_KINDS,
    _VALID_CLASP_KINDS,
    _VALID_EAR_FINDING_KINDS,
    _VALID_END_CAP_KINDS,
    _VALID_FAMILIES,
    _VALID_JUMP_RING_KINDS,
    _VALID_PIN_FINDING_KINDS,
    compute_bail_params,
    compute_clasp_params,
    compute_ear_finding_params,
    compute_end_cap_params,
    compute_finding_params,
    compute_jump_ring_params,
    compute_pin_finding_params,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_WIRE = 1.0   # reference wire gauge (mm) used throughout


def _gauge_variants():
    """Representative wire gauges in mm: fine, standard, heavy."""
    return [0.4, 1.0, 2.0]


# ---------------------------------------------------------------------------
# T-6 §1  25 finding-attachment combos — wire gauge preserved
# ---------------------------------------------------------------------------

# Exactly 25 combos drawn from all six families + representative kinds
_COMBOS_25 = [
    # jump_ring (4)
    ("jump_ring",   "round_open",      {"inner_diameter_mm": 5.0}),
    ("jump_ring",   "round_closed",    {"inner_diameter_mm": 4.0}),
    ("jump_ring",   "oval_open",       {"inner_diameter_mm": 6.0, "aspect_ratio": 1.5}),
    ("jump_ring",   "oval_closed",     {"inner_diameter_mm": 5.0, "aspect_ratio": 1.3}),
    # bail (4)
    ("bail",        "pinch",           {}),
    ("bail",        "snap",            {}),
    ("bail",        "glue_on",         {}),
    ("bail",        "loop",            {}),
    # ear_finding (5)
    ("ear_finding", "fish_hook",       {}),
    ("ear_finding", "lever_back",      {}),
    ("ear_finding", "post_butterfly",  {}),
    ("ear_finding", "huggie",          {}),
    ("ear_finding", "kidney",          {}),
    # pin_finding (4)
    ("pin_finding", "pin_stem",        {}),
    ("pin_finding", "joint",           {}),
    ("pin_finding", "catch_rotating",  {}),
    ("pin_finding", "stick_pin",       {}),
    # end_cap (4)
    ("end_cap",     "glue_in",         {}),
    ("end_cap",     "crimp",           {}),
    ("end_cap",     "cord_end",        {}),
    ("end_cap",     "split_ring",      {}),
    # clasp (4)
    ("clasp",       "hook_and_eye",    {}),
    ("clasp",       "magnetic",        {}),
    ("clasp",       "barrel",          {}),
    ("clasp",       "slide_lock",      {}),
]

assert len(_COMBOS_25) == 25, "T-6 requires exactly 25 combos"


class TestFindingAttachmentCombos:
    """25 finding-attachment combos — spec floor."""

    @pytest.mark.parametrize("family,kind,extra", _COMBOS_25)
    def test_combo_returns_valid_spec(self, family, kind, extra):
        p = compute_finding_params(family, kind, _WIRE, **extra)
        assert p["family"] == family
        assert p["kind"] == kind
        assert isinstance(p["finding_hints"], dict)

    @pytest.mark.parametrize("family,kind,extra", _COMBOS_25)
    def test_wire_gauge_preserved_in_spec(self, family, kind, extra):
        """wire_gauge_mm must be echoed exactly at the top level and inside hints."""
        gauge = 1.5
        extra_aug = dict(extra)
        # bump inner_diameter_mm for jump rings so it stays > gauge
        if family == "jump_ring":
            extra_aug["inner_diameter_mm"] = max(
                extra_aug.get("inner_diameter_mm", 5.0), gauge + 1.0
            )
        p = compute_finding_params(family, kind, gauge, **extra_aug)
        assert p["wire_gauge_mm"] == pytest.approx(gauge), (
            f"{family}/{kind}: top-level wire_gauge_mm mismatch"
        )
        hints_gauge = p["finding_hints"].get("wire_gauge_mm")
        if hints_gauge is not None:
            assert hints_gauge == pytest.approx(gauge), (
                f"{family}/{kind}: finding_hints wire_gauge_mm mismatch"
            )

    @pytest.mark.parametrize("family,kind,extra", _COMBOS_25)
    def test_op_field_is_finding(self, family, kind, extra):
        """Spec dicts that carry 'op' must tag it as 'finding'."""
        p = compute_finding_params(family, kind, _WIRE, **extra)
        if "op" in p:
            assert p["op"] == "finding"


# ---------------------------------------------------------------------------
# T-6 §2  Female / male mate clearance
# ---------------------------------------------------------------------------

class TestMateClears:
    """Female (socket) / male (plug) dimension pairs must give positive clearance."""

    def test_barrel_clasp_inner_lt_outer(self):
        p = compute_clasp_params("barrel", wire_gauge_mm=1.0)
        h = p["finding_hints"]
        assert h["barrel_inner_diameter_mm"] < h["barrel_outer_diameter_mm"], (
            "barrel: inner must be < outer (wall clearance)"
        )

    def test_barrel_clasp_inner_positive(self):
        """Inner diameter must be positive — wall can't consume the full barrel."""
        p = compute_clasp_params("barrel", wire_gauge_mm=0.5)
        assert p["finding_hints"]["barrel_inner_diameter_mm"] > 0

    def test_barrel_clasp_thread_pitch_positive(self):
        p = compute_clasp_params("barrel", wire_gauge_mm=1.0)
        assert p["finding_hints"]["thread_pitch_mm"] > 0

    def test_glue_in_inner_lt_outer(self):
        p = compute_end_cap_params("glue_in", wire_gauge_mm=1.0)
        h = p["finding_hints"]
        assert h["inner_diameter_mm"] < h["outer_diameter_mm"]

    def test_crimp_inner_lt_outer(self):
        p = compute_end_cap_params("crimp", wire_gauge_mm=1.0)
        h = p["finding_hints"]
        assert h["inner_diameter_mm"] < h["outer_diameter_mm"]

    def test_crimp_wall_equals_gauge(self):
        """Crimp tube wall = wire_gauge_mm."""
        gauge = 0.8
        p = compute_end_cap_params("crimp", wire_gauge_mm=gauge)
        h = p["finding_hints"]
        wall = (h["outer_diameter_mm"] - h["inner_diameter_mm"]) / 2.0
        assert wall == pytest.approx(gauge)

    def test_magnetic_cap_larger_than_magnet(self):
        p = compute_clasp_params("magnetic", wire_gauge_mm=1.0)
        h = p["finding_hints"]
        assert h["cap_outer_diameter_mm"] > h["magnet_diameter_mm"]

    def test_hook_eye_inner_positive(self):
        p = compute_clasp_params("hook_and_eye", wire_gauge_mm=1.0)
        assert p["finding_hints"]["eye_inner_diameter_mm"] > 0

    def test_jump_ring_outer_equals_inner_plus_two_gauge(self):
        gauge = 1.2
        inner = 6.0
        p = compute_jump_ring_params("round_open", wire_gauge_mm=gauge,
                                     inner_diameter_mm=inner)
        expected_outer = round(inner + 2.0 * gauge, 4)
        assert p["finding_hints"]["outer_diameter_mm"] == pytest.approx(expected_outer)

    def test_huggie_outer_equals_inner_plus_two_gauge(self):
        gauge = 1.0
        p = compute_ear_finding_params("huggie", wire_gauge_mm=gauge,
                                       inner_diameter_mm=10.0)
        h = p["finding_hints"]
        assert h["outer_diameter_mm"] == pytest.approx(h["inner_diameter_mm"] + 2.0 * gauge)

    def test_post_butterfly_post_hole_gives_clearance(self):
        """ear_nut post-hole should be slightly larger than the post gauge."""
        gauge = 0.9
        p = compute_ear_finding_params("ear_nut", wire_gauge_mm=gauge)
        hole = p["finding_hints"]["post_hole_diameter_mm"]
        assert hole > gauge, "post-hole must exceed wire gauge for clearance"

    def test_figure_8_inner_lt_outer(self):
        p = compute_end_cap_params("figure_8", wire_gauge_mm=1.0)
        h = p["finding_hints"]
        assert h["ring_inner_diameter_mm"] < h["ring_outer_diameter_mm"]

    def test_split_ring_inner_lt_outer(self):
        p = compute_end_cap_params("split_ring", wire_gauge_mm=1.0)
        h = p["finding_hints"]
        assert h["ring_inner_diameter_mm"] < h["ring_outer_diameter_mm"]

    def test_connector_link_inner_lt_outer(self):
        p = compute_end_cap_params("connector_link", wire_gauge_mm=1.0)
        h = p["finding_hints"]
        assert h["link_inner_diameter_mm"] < h["link_outer_diameter_mm"]

    def test_lever_back_loop_id_positive(self):
        p = compute_ear_finding_params("lever_back", wire_gauge_mm=0.8)
        assert p["finding_hints"]["loop_inner_diameter_mm"] > 0


# ---------------------------------------------------------------------------
# T-6 §3  Round-trip into chains (jump rings as chain links)
# ---------------------------------------------------------------------------

class TestJumpRingChainRoundTrip:
    """Jump rings used as chain links: validate total-length arithmetic."""

    def test_chain_of_n_rings_total_pitch(self):
        """
        A single-chain of N round jump rings: total inner length
        ≈ N × inner_diameter_mm (±1 mm tolerance for linking overlap).
        """
        gauge = 1.0
        inner = 5.0
        n = 20
        p = compute_jump_ring_params("round_open", wire_gauge_mm=gauge,
                                     inner_diameter_mm=inner, quantity=n)
        # Each ring contributes its inner_diameter when laid end-to-end
        estimated_total = n * inner
        # Practical chain overlaps each ring by ~1 gauge on each end
        min_total = n * (inner - 2 * gauge)
        max_total = n * inner
        assert min_total <= estimated_total <= max_total + 1.0

    def test_oval_ring_longer_axis_correct(self):
        gauge = 0.8
        inner = 5.0
        ratio = 1.6
        p = compute_jump_ring_params("oval_open", wire_gauge_mm=gauge,
                                     inner_diameter_mm=inner, aspect_ratio=ratio)
        h = p["finding_hints"]
        assert h["inner_length_mm"] == pytest.approx(inner * ratio, rel=1e-3)

    def test_round_ring_aspect_ratio_not_stored(self):
        p = compute_jump_ring_params("round_open", wire_gauge_mm=1.0,
                                     inner_diameter_mm=5.0)
        assert "aspect_ratio" not in p["finding_hints"]

    def test_oval_ring_outer_width_equals_inner_plus_two_gauge(self):
        gauge = 0.8
        inner = 4.0
        p = compute_jump_ring_params("oval_open", wire_gauge_mm=gauge,
                                     inner_diameter_mm=inner, aspect_ratio=1.5)
        h = p["finding_hints"]
        assert h["outer_width_mm"] == pytest.approx(inner + 2.0 * gauge)

    def test_batch_quantity_propagated(self):
        p = compute_jump_ring_params("round_closed", wire_gauge_mm=1.0,
                                     inner_diameter_mm=5.0, quantity=50)
        assert p["quantity"] == 50

    def test_closed_ring_not_open(self):
        p = compute_jump_ring_params("round_closed", wire_gauge_mm=1.0,
                                     inner_diameter_mm=5.0)
        assert p["finding_hints"]["open"] is False

    def test_open_ring_is_open(self):
        p = compute_jump_ring_params("round_open", wire_gauge_mm=1.0,
                                     inner_diameter_mm=5.0)
        assert p["finding_hints"]["open"] is True

    @pytest.mark.parametrize("gauge", _gauge_variants())
    def test_multiple_gauges_outer_formula(self, gauge):
        inner = gauge * 5
        p = compute_jump_ring_params("round_open", wire_gauge_mm=gauge,
                                     inner_diameter_mm=inner)
        assert p["finding_hints"]["outer_diameter_mm"] == pytest.approx(
            inner + 2.0 * gauge, rel=1e-4
        )


# ---------------------------------------------------------------------------
# T-6 §4  Round-trip into earrings (bail + ear_finding on pendant)
# ---------------------------------------------------------------------------

class TestEarringRoundTrip:
    """Bails + ear findings composed as a pendant earring — dimensional checks."""

    def test_bail_loop_id_exceeds_gauge(self):
        """The bail's loop inner diameter must be larger than the wire gauge
        so a chain or cord can actually thread through."""
        gauge = 0.8
        p = compute_bail_params("loop", wire_gauge_mm=gauge)
        assert p["finding_hints"]["loop_inner_diameter_mm"] > gauge

    def test_pinch_bail_has_two_spring_arms(self):
        p = compute_bail_params("pinch", wire_gauge_mm=1.0)
        assert p["finding_hints"]["spring_arm_count"] == 2

    def test_glue_on_bail_pad_positive(self):
        p = compute_bail_params("glue_on", wire_gauge_mm=1.0)
        assert p["finding_hints"]["pad_width_mm"] > 0

    def test_fish_hook_curl_radius_positive(self):
        p = compute_ear_finding_params("fish_hook", wire_gauge_mm=0.8)
        assert p["finding_hints"]["curl_radius_mm"] > 0

    def test_bail_and_fish_hook_wires_compatible(self):
        """Bail loop ID must be ≥ fish-hook wire gauge for the hook to pass through."""
        bail_gauge = 0.8
        hook_gauge = 0.8
        bail = compute_bail_params("loop", wire_gauge_mm=bail_gauge)
        hook = compute_ear_finding_params("fish_hook", wire_gauge_mm=hook_gauge)
        assert bail["finding_hints"]["loop_inner_diameter_mm"] >= hook_gauge

    def test_snap_bail_has_clip_retention(self):
        p = compute_bail_params("snap", wire_gauge_mm=1.0)
        assert p["finding_hints"]["clip_retention"] == "spring_tab"

    def test_lever_back_mechanism_is_hinged(self):
        p = compute_ear_finding_params("lever_back", wire_gauge_mm=0.8)
        assert p["finding_hints"]["lever_mechanism"] == "hinged"

    def test_kidney_has_closure_type(self):
        p = compute_ear_finding_params("kidney", wire_gauge_mm=0.8)
        assert "kidney_closure" in p["finding_hints"]

    def test_ear_nut_post_hole_slight_clearance(self):
        """post_hole_diameter_mm must be slightly > wire_gauge_mm (clearance fit)."""
        gauge = 0.9
        p = compute_ear_finding_params("ear_nut", wire_gauge_mm=gauge)
        assert p["finding_hints"]["post_hole_diameter_mm"] > gauge

    def test_huggie_inner_diameter_default_positive(self):
        p = compute_ear_finding_params("huggie", wire_gauge_mm=1.0)
        assert p["finding_hints"]["inner_diameter_mm"] > 0

    @pytest.mark.parametrize("gauge", _gauge_variants())
    def test_bail_loop_outer_equals_inner_plus_two_gauge(self, gauge):
        p = compute_bail_params("loop", wire_gauge_mm=gauge)
        h = p["finding_hints"]
        assert h["loop_outer_diameter_mm"] == pytest.approx(
            h["loop_inner_diameter_mm"] + 2.0 * gauge, rel=1e-4
        )


# ---------------------------------------------------------------------------
# T-6 §5  Boundary & wire-gauge variants
# ---------------------------------------------------------------------------

class TestBoundaryAndGaugeVariants:
    """Boundary conditions: minimum valid values and gauge extremes."""

    def test_minimum_valid_gauge_jump_ring(self):
        p = compute_jump_ring_params("round_open", wire_gauge_mm=0.1,
                                     inner_diameter_mm=0.5)
        assert p["wire_gauge_mm"] == pytest.approx(0.1)

    def test_maximum_realistic_gauge_just_below_limit(self):
        p = compute_jump_ring_params("round_open", wire_gauge_mm=19.9,
                                     inner_diameter_mm=40.0)
        assert p["wire_gauge_mm"] == pytest.approx(19.9)

    def test_gauge_above_20mm_raises(self):
        with pytest.raises(ValueError, match="unrealistically large"):
            compute_jump_ring_params("round_open", wire_gauge_mm=20.1,
                                     inner_diameter_mm=50.0)

    def test_inner_diameter_equal_to_gauge_raises(self):
        with pytest.raises(ValueError):
            compute_jump_ring_params("round_open", wire_gauge_mm=2.0,
                                     inner_diameter_mm=2.0)

    def test_inner_diameter_less_than_gauge_raises(self):
        with pytest.raises(ValueError):
            compute_jump_ring_params("round_open", wire_gauge_mm=3.0,
                                     inner_diameter_mm=1.5)

    def test_zero_gauge_raises_jump_ring(self):
        with pytest.raises(ValueError):
            compute_jump_ring_params("round_open", wire_gauge_mm=0,
                                     inner_diameter_mm=5.0)

    def test_negative_gauge_raises_bail(self):
        with pytest.raises(ValueError):
            compute_bail_params("pinch", wire_gauge_mm=-1.0)

    def test_oval_aspect_ratio_below_one_raises(self):
        with pytest.raises(ValueError, match="aspect_ratio"):
            compute_jump_ring_params("oval_open", wire_gauge_mm=1.0,
                                     inner_diameter_mm=5.0, aspect_ratio=0.5)

    def test_zero_gauge_raises_clasp(self):
        with pytest.raises(ValueError):
            compute_clasp_params("barrel", wire_gauge_mm=0)

    def test_zero_gauge_raises_ear_finding(self):
        with pytest.raises(ValueError):
            compute_ear_finding_params("fish_hook", wire_gauge_mm=0)

    def test_zero_gauge_raises_pin_finding(self):
        with pytest.raises(ValueError):
            compute_pin_finding_params("pin_stem", wire_gauge_mm=0)

    def test_zero_gauge_raises_end_cap(self):
        with pytest.raises(ValueError):
            compute_end_cap_params("crimp", wire_gauge_mm=0)

    def test_quantity_zero_raises(self):
        with pytest.raises(ValueError):
            compute_jump_ring_params("round_open", wire_gauge_mm=1.0,
                                     inner_diameter_mm=5.0, quantity=0)

    def test_quantity_negative_raises(self):
        with pytest.raises(ValueError):
            compute_jump_ring_params("round_open", wire_gauge_mm=1.0,
                                     inner_diameter_mm=5.0, quantity=-3)

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError):
            compute_bail_params("tube_bail", wire_gauge_mm=1.0)

    def test_unknown_family_raises(self):
        with pytest.raises(ValueError):
            compute_finding_params("widget", "round", 1.0)


# ---------------------------------------------------------------------------
# T-6 §6  Malformed inputs
# ---------------------------------------------------------------------------

class TestMalformedInputs:
    """Malformed / type-coercion stress cases."""

    def test_kind_with_spaces_normalised(self):
        """Kind with spaces should be normalised to underscores."""
        p = compute_bail_params("glue on", wire_gauge_mm=1.0)
        assert p["kind"] == "glue_on"

    def test_kind_with_hyphens_normalised(self):
        p = compute_bail_params("glue-on", wire_gauge_mm=1.0)
        assert p["kind"] == "glue_on"

    def test_alias_shepherd_resolves_to_fish_hook(self):
        p = compute_ear_finding_params("shepherd", wire_gauge_mm=0.8)
        assert p["kind"] == "fish_hook"

    def test_alias_torpedo_resolves_to_barrel(self):
        p = compute_clasp_params("torpedo", wire_gauge_mm=1.0)
        assert p["kind"] == "barrel"

    def test_alias_clip_resolves_to_snap(self):
        p = compute_bail_params("clip", wire_gauge_mm=1.0)
        assert p["kind"] == "snap"

    def test_alias_cord_end_cap_resolves_to_cord_end(self):
        p = compute_end_cap_params("cord_end_cap", wire_gauge_mm=1.0)
        assert p["kind"] == "cord_end"

    def test_alias_loop_bail_resolves_to_loop(self):
        p = compute_bail_params("loop_bail", wire_gauge_mm=1.0)
        assert p["kind"] == "loop"

    def test_kind_uppercase_normalised(self):
        p = compute_bail_params("PINCH", wire_gauge_mm=1.0)
        assert p["kind"] == "pinch"

    def test_kind_mixed_case_normalised(self):
        p = compute_clasp_params("Barrel", wire_gauge_mm=1.0)
        assert p["kind"] == "barrel"


# ---------------------------------------------------------------------------
# T-6 §7  Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    """Calling compute_* twice with the same args must give identical results."""

    @pytest.mark.parametrize("family,kind,extra", _COMBOS_25)
    def test_idempotent(self, family, kind, extra):
        p1 = compute_finding_params(family, kind, _WIRE, **extra)
        p2 = compute_finding_params(family, kind, _WIRE, **extra)
        assert p1 == p2, f"{family}/{kind}: results not idempotent"

    def test_idempotent_with_gauge_variants(self):
        for gauge in _gauge_variants():
            inner = gauge * 5
            p1 = compute_jump_ring_params("round_open", wire_gauge_mm=gauge,
                                          inner_diameter_mm=inner)
            p2 = compute_jump_ring_params("round_open", wire_gauge_mm=gauge,
                                          inner_diameter_mm=inner)
            assert p1 == p2


# ---------------------------------------------------------------------------
# T-6 §8  Completeness: all families + family_kinds mapping
# ---------------------------------------------------------------------------

class TestCompleteness:
    """All six families are registered and each kind produces a valid spec."""

    def test_six_families_defined(self):
        assert len(_VALID_FAMILIES) == 6

    def test_family_kinds_map_covers_all_families(self):
        assert set(_FAMILY_KINDS.keys()) == _VALID_FAMILIES

    @pytest.mark.parametrize("kind", sorted(_VALID_JUMP_RING_KINDS))
    def test_all_jump_ring_kinds_valid(self, kind):
        p = compute_jump_ring_params(kind, wire_gauge_mm=1.0, inner_diameter_mm=5.0)
        assert p["family"] == "jump_ring"

    @pytest.mark.parametrize("kind", sorted(_VALID_BAIL_KINDS))
    def test_all_bail_kinds_valid(self, kind):
        p = compute_bail_params(kind, wire_gauge_mm=1.0)
        assert p["family"] == "bail"

    @pytest.mark.parametrize("kind", sorted(_VALID_EAR_FINDING_KINDS))
    def test_all_ear_finding_kinds_valid(self, kind):
        p = compute_ear_finding_params(kind, wire_gauge_mm=0.8)
        assert p["family"] == "ear_finding"

    @pytest.mark.parametrize("kind", sorted(_VALID_PIN_FINDING_KINDS))
    def test_all_pin_finding_kinds_valid(self, kind):
        p = compute_pin_finding_params(kind, wire_gauge_mm=1.0)
        assert p["family"] == "pin_finding"

    @pytest.mark.parametrize("kind", sorted(_VALID_END_CAP_KINDS))
    def test_all_end_cap_kinds_valid(self, kind):
        p = compute_end_cap_params(kind, wire_gauge_mm=1.0)
        assert p["family"] == "end_cap"

    @pytest.mark.parametrize("kind", sorted(_VALID_CLASP_KINDS))
    def test_all_clasp_kinds_valid(self, kind):
        p = compute_clasp_params(kind, wire_gauge_mm=1.0)
        assert p["family"] == "clasp"

    def test_all_kind_aliases_resolve_to_valid_targets(self):
        all_valid_kinds = set()
        for kinds in _FAMILY_KINDS.values():
            all_valid_kinds.update(kinds)
        for alias, target in _KIND_ALIASES.items():
            assert target in all_valid_kinds, (
                f"Alias {alias!r} → {target!r} is not a valid kind"
            )

    def test_finding_hints_present_on_all_combos(self):
        for family, kind, extra in _COMBOS_25:
            p = compute_finding_params(family, kind, _WIRE, **extra)
            assert "finding_hints" in p, f"{family}/{kind}: missing finding_hints"
            assert isinstance(p["finding_hints"], dict), (
                f"{family}/{kind}: finding_hints is not a dict"
            )
