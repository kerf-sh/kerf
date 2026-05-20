"""
T-8: Jewelry engraving / monogram / signet — hermetic pytest suite.

Spec mandates:
  - 25 text/glyph permutations; engraved depth & font fidelity
  - UTF-8 + ligature stress cases

The core compute-function and tool-runner tests live in test_engraving.py
(126 tests, all green).  This file adds the spec-required permutation sweep,
UTF-8/ligature stress, idempotency, and boundary coverage that are not
duplicated there.
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.jewelry.engraving import (
    _DEFAULT_STROKE_WIDTH_FRAC,
    _VALID_BORDER_SHAPES,
    _VALID_ENGRAVING_MODES,
    _VALID_MONOGRAM_STYLES,
    compute_monogram_compose,
    compute_signet_seal,
    compute_text_on_band_inner,
    compute_text_on_curve,
    get_glyph,
    render_text_outlines,
    text_width_em,
    total_stroke_length,
)

# ---------------------------------------------------------------------------
# 25 text/glyph permutations — depth & font fidelity
# ---------------------------------------------------------------------------

# 25 distinct (text, cap_height_mm, depth_mm, feature_fn, feature_name) combos
_TEXT_PERMS = [
    # (text, cap_height_mm, depth_mm)
    ("A",          2.0, 0.10),
    ("Z",          2.0, 0.15),
    ("M",          3.0, 0.20),
    ("I",          3.0, 0.10),
    ("0",          4.0, 0.25),
    ("9",          4.0, 0.30),
    ("AZ",         3.0, 0.20),
    ("AB",         4.0, 0.15),
    ("MR",         5.0, 0.30),
    ("XY",         3.5, 0.20),
    ("ABC",        3.0, 0.20),
    ("JRS",        6.0, 0.35),
    ("LOVE",       2.5, 0.15),
    ("1985",       3.0, 0.20),
    ("SMITH",      4.0, 0.25),
    ("HELLO",      4.0, 0.20),
    ("WORLD",      3.5, 0.30),
    ("ABCDE",      3.0, 0.20),
    ("JOHN",       3.0, 0.15),
    ("JANE",       3.0, 0.15),
    ("KERF",       5.0, 0.25),
    ("RING",       4.5, 0.20),
    ("GOLD",       4.0, 0.30),
    ("HEART",      3.0, 0.20),
    ("HANDMADE",   2.5, 0.15),
]

assert len(_TEXT_PERMS) == 25, "must have exactly 25 permutations"


@pytest.mark.parametrize("text,cap,depth", _TEXT_PERMS)
def test_text_on_curve_depth_fidelity(text, cap, depth):
    """Each permutation: depth stored correctly; outline_paths non-empty."""
    s = compute_text_on_curve("ref-curve", text, cap_height_mm=cap, depth_mm=depth)
    assert s["engraving_hints"]["depth_mm"] == pytest.approx(depth, rel=1e-5)
    assert len(s["outline_paths"]) > 0


@pytest.mark.parametrize("text,cap,depth", _TEXT_PERMS)
def test_text_on_curve_stroke_width_fidelity(text, cap, depth):
    """min_stroke_width_mm = DEFAULT_FRAC * cap_height for each permutation."""
    s = compute_text_on_curve("ref-curve", text, cap_height_mm=cap, depth_mm=depth)
    expected_sw = _DEFAULT_STROKE_WIDTH_FRAC * cap
    assert s["diagnostics"]["min_stroke_width_mm"] == pytest.approx(expected_sw, rel=1e-4)


@pytest.mark.parametrize("text,cap,depth", _TEXT_PERMS)
def test_signet_seal_permutation_depth_fidelity(text, cap, depth):
    """signet_seal: depth stored for each permutation."""
    s = compute_signet_seal("face-ref", text, cap_height_mm=cap, depth_mm=depth)
    assert s["engraving_hints"]["depth_mm"] == pytest.approx(depth, rel=1e-5)
    assert s["engraving_hints"]["total_text_width_mm"] > 0


@pytest.mark.parametrize("text,cap,depth", _TEXT_PERMS)
def test_text_on_band_inner_permutation(text, cap, depth):
    """text_on_band_inner: inner_circumference and text_arc_deg correct."""
    d_mm = 18.0  # fixed inner diameter for parametric sweep
    s = compute_text_on_band_inner(
        "band-ref", text, band_inner_diameter_mm=d_mm, cap_height_mm=cap, depth_mm=depth
    )
    expected_circ = math.pi * d_mm
    assert s["engraving_hints"]["inner_circumference_mm"] == pytest.approx(expected_circ, rel=1e-5)
    w = s["engraving_hints"]["total_text_width_mm"]
    expected_arc = (w / expected_circ) * 360.0
    assert s["engraving_hints"]["text_arc_deg"] == pytest.approx(expected_arc, rel=1e-4)


# ---------------------------------------------------------------------------
# UTF-8 + ligature / symbol stress cases
# ---------------------------------------------------------------------------

_UTF8_CASES = [
    # (text, description)
    ("©",         "copyright symbol"),
    ("®",         "registered symbol"),
    ("°",         "degree symbol"),
    ("@",         "at-sign"),
    ("&",         "ampersand"),
    (".-",        "dot-hyphen sequence"),
    ("A.B",       "letters with dot separator"),
    ("18K©",      "hallmark with copyright"),
    ("®GOLD",     "registered + word"),
    ("A&B",       "ampersand flanked"),
    ("2024°",     "year with degree"),
    ("© KERF",    "copyright + space + word"),
    ("AB&CD",     "multi-char with ampersand"),
    # Unmapped / surrogate chars fall back gracefully
    ("é",    "accented e — fallback"),
    ("ö",    "umlaut o — fallback"),
    ("…",    "ellipsis — fallback"),
    ("éö", "two accented chars"),
    ("éA",   "accented e + ASCII letter"),
]


@pytest.mark.parametrize("text,desc", _UTF8_CASES, ids=[d for _, d in _UTF8_CASES])
def test_utf8_stress_render_text_outlines_no_crash(text, desc):
    """render_text_outlines must not raise for any UTF-8 input."""
    pls, w, sw = render_text_outlines(text, 4.0)
    assert isinstance(pls, list)
    assert isinstance(w, float)
    assert sw > 0


@pytest.mark.parametrize("text,desc", _UTF8_CASES, ids=[d for _, d in _UTF8_CASES])
def test_utf8_stress_compute_text_on_curve_no_crash(text, desc):
    """compute_text_on_curve must handle all UTF-8 inputs without crash."""
    s = compute_text_on_curve("utf8-curve", text, cap_height_mm=4.0)
    assert s["feature"] == "text_on_curve"


@pytest.mark.parametrize("text,desc", _UTF8_CASES, ids=[d for _, d in _UTF8_CASES])
def test_utf8_stress_signet_seal_no_crash(text, desc):
    """compute_signet_seal must handle all UTF-8 inputs without crash."""
    s = compute_signet_seal("utf8-face", text, cap_height_mm=5.0)
    assert s["feature"] == "signet_seal"


def test_ligature_ampersand_glyph_has_strokes():
    """Ampersand glyph must have at least one stroke (not treated as space)."""
    g = get_glyph("&")
    assert len(g["strokes"]) > 0


def test_copyright_glyph_has_strokes():
    g = get_glyph("©")
    assert len(g["strokes"]) > 0


def test_registered_glyph_has_strokes():
    g = get_glyph("®")
    assert len(g["strokes"]) > 0


def test_degree_glyph_has_strokes():
    g = get_glyph("°")
    assert len(g["strokes"]) > 0


def test_unknown_glyph_fallback_advance_positive():
    """Any unmapped codepoint must still return a positive advance (fallback glyph)."""
    for ch in ["é", "€", "ß", "☃"]:
        g = get_glyph(ch)
        assert g["advance"] > 0, f"zero advance for unmapped char {ch!r}"


def test_mixed_ascii_utf8_width_increases():
    """A longer mixed string must have greater width than the ASCII-only prefix."""
    w_ascii = text_width_em("AB")
    w_mixed = text_width_em("AB©")
    assert w_mixed > w_ascii


# ---------------------------------------------------------------------------
# Idempotency: calling compute_* twice with same args gives identical output
# ---------------------------------------------------------------------------

def test_text_on_curve_idempotent():
    kwargs = dict(target_ref="idm-curve", text="HELLO", cap_height_mm=4.0, depth_mm=0.2)
    s1 = compute_text_on_curve(**kwargs)
    s2 = compute_text_on_curve(**kwargs)
    assert s1["engraving_hints"] == s2["engraving_hints"]
    assert s1["diagnostics"] == s2["diagnostics"]
    assert s1["outline_paths"] == s2["outline_paths"]


def test_signet_seal_idempotent():
    kwargs = dict(target_ref="idm-face", text="JRS", cap_height_mm=6.0, depth_mm=0.3,
                  border_shape="oval")
    s1 = compute_signet_seal(**kwargs)
    s2 = compute_signet_seal(**kwargs)
    assert s1["engraving_hints"] == s2["engraving_hints"]
    assert s1["diagnostics"] == s2["diagnostics"]


def test_monogram_compose_idempotent():
    kwargs = dict(initials="JRS", style="encircled", cap_height_mm=8.0)
    s1 = compute_monogram_compose(**kwargs)
    s2 = compute_monogram_compose(**kwargs)
    assert s1["bounding_box"] == s2["bounding_box"]
    assert s1["outline_paths"] == s2["outline_paths"]


def test_text_on_band_inner_idempotent():
    kwargs = dict(target_ref="idm-band", text="LOVE", band_inner_diameter_mm=17.0,
                  cap_height_mm=2.0, depth_mm=0.15)
    s1 = compute_text_on_band_inner(**kwargs)
    s2 = compute_text_on_band_inner(**kwargs)
    assert s1["engraving_hints"] == s2["engraving_hints"]


# ---------------------------------------------------------------------------
# Boundary: minimum/maximum valid values
# ---------------------------------------------------------------------------

def test_text_on_curve_min_cap_height_boundary():
    """cap_height_mm = epsilon above zero must succeed."""
    s = compute_text_on_curve("b-curve", "A", cap_height_mm=0.001)
    assert s["engraving_hints"]["cap_height_mm"] == pytest.approx(0.001, rel=1e-4)


def test_text_on_curve_large_cap_height():
    """Very large cap_height_mm should succeed."""
    s = compute_text_on_curve("b-curve", "A", cap_height_mm=200.0)
    assert s["engraving_hints"]["cap_height_mm"] == pytest.approx(200.0)


def test_signet_seal_zero_border_width_allowed():
    """border_width_mm = 0.0 is valid (>= 0 constraint)."""
    s = compute_signet_seal("b-face", "A", cap_height_mm=5.0, border_width_mm=0.0)
    assert s["engraving_hints"]["border_width_mm"] == pytest.approx(0.0)


def test_text_on_band_inner_start_t_boundary_zero():
    """start_t = 0.0 is valid for text_on_curve."""
    s = compute_text_on_curve("b-curve", "A", cap_height_mm=3.0, start_t=0.0)
    assert s["engraving_hints"]["start_t"] == pytest.approx(0.0)


def test_text_on_curve_start_t_boundary_one():
    """start_t = 1.0 is valid (inclusive)."""
    s = compute_text_on_curve("b-curve", "A", cap_height_mm=3.0, start_t=1.0)
    assert s["engraving_hints"]["start_t"] == pytest.approx(1.0)


def test_monogram_compose_side_scale_minimum_exclusive():
    """side_scale = 0.0 is rejected (must be > 0)."""
    with pytest.raises(ValueError, match="side_scale"):
        compute_monogram_compose("AB", side_scale=0.0, cap_height_mm=6.0)


def test_monogram_compose_side_scale_maximum():
    """side_scale = 1.5 is valid (boundary inclusive)."""
    s = compute_monogram_compose("AB", side_scale=1.5, cap_height_mm=6.0)
    assert s["monogram_hints"]["side_scale"] == pytest.approx(1.5)


def test_monogram_compose_side_scale_above_max():
    """side_scale = 1.51 is rejected."""
    with pytest.raises(ValueError, match="side_scale"):
        compute_monogram_compose("AB", side_scale=1.51, cap_height_mm=6.0)


# ---------------------------------------------------------------------------
# Malformed / bad inputs not covered by test_engraving.py
# ---------------------------------------------------------------------------

def test_compute_text_on_curve_whitespace_only_text_raises():
    """Text that is only whitespace after strip must raise."""
    with pytest.raises(ValueError, match="text is required"):
        compute_text_on_curve("c-ref", "   ", cap_height_mm=3.0)


def test_signet_seal_whitespace_only_text_raises():
    with pytest.raises(ValueError, match="text is required"):
        compute_signet_seal("f-ref", "\t\n", cap_height_mm=4.0)


def test_text_on_band_inner_negative_cap_height_raises():
    with pytest.raises(ValueError, match="cap_height_mm must be > 0"):
        compute_text_on_band_inner("b-ref", "A", band_inner_diameter_mm=17.0, cap_height_mm=-2.0)


def test_text_on_curve_start_t_slightly_above_one_raises():
    with pytest.raises(ValueError, match="start_t must be in"):
        compute_text_on_curve("c-ref", "A", cap_height_mm=3.0, start_t=1.001)


def test_text_on_curve_negative_start_t_raises():
    with pytest.raises(ValueError, match="start_t must be in"):
        compute_text_on_curve("c-ref", "A", cap_height_mm=3.0, start_t=-0.001)


def test_monogram_compose_non_alpha_in_initials_raises():
    """Initials containing chars not in built-in font should raise."""
    # '!' is not in the font and not a fallback path that auto-succeeds;
    # the implementation raises ValueError for unmapped chars when validating initials
    with pytest.raises(ValueError):
        compute_monogram_compose("A!", cap_height_mm=6.0)


def test_signet_seal_depth_zero_raises():
    with pytest.raises(ValueError, match="depth_mm must be > 0"):
        compute_signet_seal("f-ref", "A", cap_height_mm=5.0, depth_mm=0.0)


def test_text_on_band_inner_depth_zero_raises():
    with pytest.raises(ValueError, match="depth_mm must be > 0"):
        compute_text_on_band_inner("b-ref", "A", band_inner_diameter_mm=17.0,
                                   cap_height_mm=2.0, depth_mm=0.0)


# ---------------------------------------------------------------------------
# Engraved-volume sanity checks across permutations
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,cap,depth", _TEXT_PERMS)
def test_recessed_volume_proportional_to_depth(text, cap, depth):
    """Doubling depth_mm should roughly double recessed_volume (linear model)."""
    s1 = compute_text_on_curve("v-curve", text, cap_height_mm=cap, depth_mm=depth)
    s2 = compute_text_on_curve("v-curve", text, cap_height_mm=cap, depth_mm=depth * 2)
    vol1 = s1["diagnostics"]["recessed_volume_mm3"]
    vol2 = s2["diagnostics"]["recessed_volume_mm3"]
    if vol1 > 0:
        assert vol2 == pytest.approx(vol1 * 2, rel=1e-3)
