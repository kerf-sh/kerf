"""
T-19 — Mech: GD&T datum/tolerance framework
============================================
Spec: 25 callout types (Y14.5); datum reference frames build correctly;
round-trip into drawing JSON.

Pure-Python, hermetic — no OCC, no DB, no on-disk fixtures.
Covers:
  - All 14 ASME Y14.5-2018 characteristic symbols
  - Form (4): FLATNESS, STRAIGHTNESS, CIRCULARITY, CYLINDRICITY
  - Profile (2): PROFILE_LINE, PROFILE_SURFACE
  - Orientation (3): PARALLELISM, PERPENDICULARITY, ANGULARITY
  - Location (3): POSITION, CONCENTRICITY, SYMMETRY
  - Runout (2): RUNOUT, TOTAL_RUNOUT
  - Datum reference frame construction (primary / secondary / tertiary / empty)
  - Round-trip serialisation: to_dict() → from_dict() preserves every field
  - Boundaries: zero/negative tolerance, empty feature_name, unknown symbol
  - Malformed datum inputs (invalid type, empty label)
  - Idempotency: applying the same callout twice yields the same output
  - Callout report drawing-JSON surface (summary list structure)
  - validate_scheme rules for all major constraint categories
"""
from __future__ import annotations

import copy
import json

import pytest

from kerf_cad_core.gdt.datums import Datum, DatumReferenceFrame, DatumType
from kerf_cad_core.gdt.modifiers import ToleranceModifier, requires_feature_of_size
from kerf_cad_core.gdt.report import gdt_callout_report
from kerf_cad_core.gdt.tolerances import (
    GeometricTolerance,
    ToleranceSymbol,
    tolerance_category,
)
from kerf_cad_core.gdt.tools import _validate_scheme


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _tol(
    feature_name: str,
    symbol: str,
    value: float = 0.05,
    *,
    diameter_zone: bool = False,
    datum_ref: dict | None = None,
    modifiers: list[str] | None = None,
    is_feature_of_size: bool = False,
    projected_zone_height: float | None = None,
    note: str | None = None,
) -> dict:
    """Build a minimal GeometricTolerance dict."""
    d: dict = {
        "feature_name": feature_name,
        "symbol": symbol,
        "tolerance_value": value,
        "diameter_zone": diameter_zone,
        "is_feature_of_size": is_feature_of_size,
    }
    if datum_ref is not None:
        d["datum_ref"] = datum_ref
    if modifiers is not None:
        d["modifiers"] = modifiers
    if projected_zone_height is not None:
        d["projected_zone_height"] = projected_zone_height
    if note is not None:
        d["note"] = note
    return d


def _plane_datum(label: str = "A") -> dict:
    return {"label": label, "datum_type": "PLANE"}


def _axis_datum(label: str = "A") -> dict:
    return {"label": label, "datum_type": "AXIS"}


def _centre_plane_datum(label: str = "A") -> dict:
    return {"label": label, "datum_type": "CENTRE_PLANE"}


def _roundtrip(d: dict) -> GeometricTolerance:
    """Build from dict, serialise to dict, rebuild — return final object."""
    t1 = GeometricTolerance.from_dict(d)
    t2 = GeometricTolerance.from_dict(t1.to_dict())
    return t2


# ---------------------------------------------------------------------------
# 1. All 14 Y14.5 callout types — construction + category
# ---------------------------------------------------------------------------

class TestAllY145CalloutTypes:
    """One test per standard symbol; ensures symbol is known, category correct,
    and the object round-trips through to_dict / from_dict without data loss."""

    # ── Form ──────────────────────────────────────────────────────────────

    def test_flatness_form_category(self):
        t = GeometricTolerance(feature_name="top-face", symbol=ToleranceSymbol.FLATNESS,
                               tolerance_value=0.05)
        assert t.category == "form"
        assert t.symbol == ToleranceSymbol.FLATNESS

    def test_straightness_form_category(self):
        t = GeometricTolerance(feature_name="edge-1", symbol=ToleranceSymbol.STRAIGHTNESS,
                               tolerance_value=0.02)
        assert t.category == "form"

    def test_circularity_form_category(self):
        t = GeometricTolerance(feature_name="bore-od", symbol=ToleranceSymbol.CIRCULARITY,
                               tolerance_value=0.01)
        assert t.category == "form"

    def test_cylindricity_form_category(self):
        t = GeometricTolerance(feature_name="shaft", symbol=ToleranceSymbol.CYLINDRICITY,
                               tolerance_value=0.03)
        assert t.category == "form"

    # ── Profile ───────────────────────────────────────────────────────────

    def test_profile_line_profile_category(self):
        t = GeometricTolerance(feature_name="cam-edge", symbol=ToleranceSymbol.PROFILE_LINE,
                               tolerance_value=0.1)
        assert t.category == "profile"

    def test_profile_surface_profile_category(self):
        t = GeometricTolerance(feature_name="freeform-top", symbol=ToleranceSymbol.PROFILE_SURFACE,
                               tolerance_value=0.2)
        assert t.category == "profile"

    # ── Orientation ───────────────────────────────────────────────────────

    def test_parallelism_orientation_category(self):
        drf = DatumReferenceFrame(primary="A")
        t = GeometricTolerance(feature_name="base-face", symbol=ToleranceSymbol.PARALLELISM,
                               tolerance_value=0.05, datum_ref=drf)
        assert t.category == "orientation"

    def test_perpendicularity_orientation_category(self):
        drf = DatumReferenceFrame(primary="A")
        t = GeometricTolerance(feature_name="wall", symbol=ToleranceSymbol.PERPENDICULARITY,
                               tolerance_value=0.05, datum_ref=drf)
        assert t.category == "orientation"

    def test_angularity_orientation_category(self):
        drf = DatumReferenceFrame(primary="A")
        t = GeometricTolerance(feature_name="angled-face", symbol=ToleranceSymbol.ANGULARITY,
                               tolerance_value=0.1, datum_ref=drf)
        assert t.category == "orientation"

    # ── Location ──────────────────────────────────────────────────────────

    def test_position_location_category(self):
        drf = DatumReferenceFrame(primary="A", secondary="B")
        t = GeometricTolerance(feature_name="bore", symbol=ToleranceSymbol.POSITION,
                               tolerance_value=0.1, diameter_zone=True, datum_ref=drf)
        assert t.category == "location"
        assert t.diameter_zone is True

    def test_concentricity_location_category(self):
        drf = DatumReferenceFrame(primary="A")
        t = GeometricTolerance(feature_name="outer-dia", symbol=ToleranceSymbol.CONCENTRICITY,
                               tolerance_value=0.01, datum_ref=drf)
        assert t.category == "location"

    def test_symmetry_location_category(self):
        drf = DatumReferenceFrame(primary="A")
        t = GeometricTolerance(feature_name="slot", symbol=ToleranceSymbol.SYMMETRY,
                               tolerance_value=0.02, datum_ref=drf)
        assert t.category == "location"

    # ── Runout ────────────────────────────────────────────────────────────

    def test_runout_runout_category(self):
        drf = DatumReferenceFrame(primary="A")
        t = GeometricTolerance(feature_name="shaft-od", symbol=ToleranceSymbol.RUNOUT,
                               tolerance_value=0.03, datum_ref=drf)
        assert t.category == "runout"

    def test_total_runout_runout_category(self):
        drf = DatumReferenceFrame(primary="A")
        t = GeometricTolerance(feature_name="shaft-od", symbol=ToleranceSymbol.TOTAL_RUNOUT,
                               tolerance_value=0.05, datum_ref=drf)
        assert t.category == "runout"

    # 14 symbols → verify the full enum set
    def test_all_14_symbols_enumerable(self):
        expected = {
            "FLATNESS", "STRAIGHTNESS", "CIRCULARITY", "CYLINDRICITY",
            "PROFILE_LINE", "PROFILE_SURFACE",
            "PARALLELISM", "PERPENDICULARITY", "ANGULARITY",
            "POSITION", "CONCENTRICITY", "SYMMETRY",
            "RUNOUT", "TOTAL_RUNOUT",
        }
        assert {s.value for s in ToleranceSymbol} == expected


# ---------------------------------------------------------------------------
# 2. Datum Reference Frame construction
# ---------------------------------------------------------------------------

class TestDatumReferenceFrameConstruction:
    """Datum reference frames build correctly per ASME Y14.5 §4.4."""

    def test_empty_drf_is_empty(self):
        drf = DatumReferenceFrame()
        assert drf.is_empty is True
        assert drf.labels == []
        assert str(drf) == "(none)"

    def test_primary_only_single_label(self):
        drf = DatumReferenceFrame(primary="A")
        assert not drf.is_empty
        assert drf.labels == ["A"]
        assert str(drf) == "A"

    def test_primary_secondary_two_labels(self):
        drf = DatumReferenceFrame(primary="A", secondary="B")
        assert drf.labels == ["A", "B"]
        assert str(drf) == "A|B"

    def test_full_three_datum_drf(self):
        drf = DatumReferenceFrame(primary="A", secondary="B", tertiary="C")
        assert drf.labels == ["A", "B", "C"]
        assert str(drf) == "A|B|C"

    def test_tertiary_without_secondary_raises(self):
        with pytest.raises(ValueError, match="secondary"):
            DatumReferenceFrame(primary="A", tertiary="C")

    def test_labels_stripped_of_whitespace(self):
        drf = DatumReferenceFrame(primary="  A  ", secondary=" B ")
        assert drf.primary == "A"
        assert drf.secondary == "B"

    def test_round_trip_preserves_all_fields(self):
        drf = DatumReferenceFrame(primary="X", secondary="Y", tertiary="Z")
        drf2 = DatumReferenceFrame.from_dict(drf.to_dict())
        assert drf2.primary == "X"
        assert drf2.secondary == "Y"
        assert drf2.tertiary == "Z"

    def test_empty_drf_round_trip(self):
        drf = DatumReferenceFrame()
        drf2 = DatumReferenceFrame.from_dict(drf.to_dict())
        assert drf2.is_empty is True


# ---------------------------------------------------------------------------
# 3. Datum construction, boundary, malformed
# ---------------------------------------------------------------------------

class TestDatumConstruction:
    def test_all_five_datum_types(self):
        for dt in DatumType:
            d = Datum(label="A", datum_type=dt)
            assert d.datum_type == dt

    def test_empty_label_raises(self):
        with pytest.raises(ValueError, match="label"):
            Datum(label="")

    def test_whitespace_only_label_raises(self):
        with pytest.raises(ValueError, match="label"):
            Datum(label="   ")

    def test_label_stripped(self):
        d = Datum(label="  B  ")
        assert d.label == "B"

    def test_string_datum_type_case_insensitive(self):
        d = Datum(label="C", datum_type="axis")  # type: ignore[arg-type]
        assert d.datum_type == DatumType.AXIS

    def test_invalid_datum_type_raises(self):
        with pytest.raises((ValueError, KeyError)):
            Datum(label="D", datum_type="INVALID_TYPE")  # type: ignore[arg-type]

    def test_compound_datum_flag(self):
        d = Datum(label="A-B", is_compound=True)
        assert d.is_compound is True

    def test_feature_ref_stored(self):
        d = Datum(label="A", feature_ref="bore-face-3")
        assert d.feature_ref == "bore-face-3"

    def test_round_trip(self):
        d = Datum(label="C", datum_type=DatumType.CENTRE_PLANE,
                  feature_ref="slot-1", description="centre plane datum")
        d2 = Datum.from_dict(d.to_dict())
        assert d2.label == "C"
        assert d2.datum_type == DatumType.CENTRE_PLANE
        assert d2.feature_ref == "slot-1"
        assert d2.description == "centre plane datum"


# ---------------------------------------------------------------------------
# 4. GeometricTolerance boundary/malformed inputs
# ---------------------------------------------------------------------------

class TestGeometricToleranceBoundaries:
    def test_zero_tolerance_raises(self):
        with pytest.raises(ValueError):
            GeometricTolerance(feature_name="f", symbol=ToleranceSymbol.FLATNESS,
                               tolerance_value=0.0)

    def test_negative_tolerance_raises(self):
        with pytest.raises(ValueError):
            GeometricTolerance(feature_name="f", symbol=ToleranceSymbol.FLATNESS,
                               tolerance_value=-0.001)

    def test_string_tolerance_coerced(self):
        t = GeometricTolerance(feature_name="f", symbol=ToleranceSymbol.FLATNESS,
                               tolerance_value="0.05")  # type: ignore[arg-type]
        assert t.tolerance_value == pytest.approx(0.05)

    def test_non_numeric_tolerance_raises(self):
        with pytest.raises(ValueError):
            GeometricTolerance(feature_name="f", symbol=ToleranceSymbol.FLATNESS,
                               tolerance_value="not-a-number")

    def test_empty_feature_name_raises(self):
        with pytest.raises(ValueError):
            GeometricTolerance(feature_name="", symbol=ToleranceSymbol.FLATNESS,
                               tolerance_value=0.05)

    def test_whitespace_feature_name_raises(self):
        with pytest.raises(ValueError):
            GeometricTolerance(feature_name="   ", symbol=ToleranceSymbol.FLATNESS,
                               tolerance_value=0.05)

    def test_unknown_symbol_raises(self):
        with pytest.raises((ValueError, KeyError)):
            GeometricTolerance(feature_name="f", symbol="SQUARENESS",  # type: ignore[arg-type]
                               tolerance_value=0.05)

    def test_lowercase_symbol_normalised(self):
        t = GeometricTolerance(feature_name="face", symbol="flatness",  # type: ignore[arg-type]
                               tolerance_value=0.05)
        assert t.symbol == ToleranceSymbol.FLATNESS

    def test_very_small_tolerance_accepted(self):
        t = GeometricTolerance(feature_name="f", symbol=ToleranceSymbol.FLATNESS,
                               tolerance_value=1e-6)
        assert t.tolerance_value == pytest.approx(1e-6)

    def test_very_large_tolerance_accepted(self):
        t = GeometricTolerance(feature_name="f", symbol=ToleranceSymbol.STRAIGHTNESS,
                               tolerance_value=999.9)
        assert t.tolerance_value == pytest.approx(999.9)

    def test_mmc_modifier_normalised_from_string(self):
        t = GeometricTolerance(
            feature_name="bore", symbol=ToleranceSymbol.POSITION,
            tolerance_value=0.05,
            modifiers=["mmc"],  # type: ignore[list-item]
            is_feature_of_size=True,
        )
        assert ToleranceModifier.MMC in t.modifiers


# ---------------------------------------------------------------------------
# 5. Round-trip into drawing JSON (to_dict / from_dict)
# ---------------------------------------------------------------------------

class TestDrawingJsonRoundTrip:
    """All 14 symbols; full field preservation; summary list structure."""

    @pytest.mark.parametrize("symbol,use_datum", [
        (ToleranceSymbol.FLATNESS,            False),
        (ToleranceSymbol.STRAIGHTNESS,        False),
        (ToleranceSymbol.CIRCULARITY,         False),
        (ToleranceSymbol.CYLINDRICITY,        False),
        (ToleranceSymbol.PROFILE_LINE,        False),
        (ToleranceSymbol.PROFILE_SURFACE,     False),
        (ToleranceSymbol.PARALLELISM,         True),
        (ToleranceSymbol.PERPENDICULARITY,    True),
        (ToleranceSymbol.ANGULARITY,          True),
        (ToleranceSymbol.POSITION,            True),
        (ToleranceSymbol.CONCENTRICITY,       True),
        (ToleranceSymbol.SYMMETRY,            True),
        (ToleranceSymbol.RUNOUT,              True),
        (ToleranceSymbol.TOTAL_RUNOUT,        True),
    ])
    def test_round_trip_all_14_symbols(self, symbol, use_datum):
        drf = DatumReferenceFrame(primary="A") if use_datum else DatumReferenceFrame()
        t1 = GeometricTolerance(
            feature_name="feat-1",
            symbol=symbol,
            tolerance_value=0.05,
            datum_ref=drf,
        )
        d = t1.to_dict()
        t2 = GeometricTolerance.from_dict(d)
        assert t2.symbol == symbol
        assert t2.tolerance_value == pytest.approx(0.05)
        assert t2.feature_name == "feat-1"
        assert t2.datum_ref.labels == drf.labels

    def test_round_trip_preserves_diameter_zone(self):
        t = _roundtrip(_tol("bore", "POSITION", 0.1, diameter_zone=True,
                            datum_ref={"primary": "A"}))
        assert t.diameter_zone is True

    def test_round_trip_preserves_note(self):
        t = _roundtrip(_tol("slot", "SYMMETRY", 0.02, note="centre plane ref",
                            datum_ref={"primary": "A"}))
        assert t.note == "centre plane ref"

    def test_round_trip_preserves_modifiers(self):
        d = _tol("pin", "POSITION", 0.05,
                 datum_ref={"primary": "A"},
                 modifiers=["MMC"],
                 is_feature_of_size=True)
        t = _roundtrip(d)
        assert ToleranceModifier.MMC in t.modifiers
        assert t.is_feature_of_size is True

    def test_round_trip_preserves_projected_zone_height(self):
        d = _tol("threaded-hole", "POSITION", 0.1,
                 datum_ref={"primary": "A"},
                 modifiers=["PROJECTED"],
                 is_feature_of_size=True,
                 projected_zone_height=12.5)
        t = _roundtrip(d)
        assert t.projected_zone_height == pytest.approx(12.5)

    def test_to_dict_contains_category_key(self):
        t = GeometricTolerance(feature_name="f", symbol=ToleranceSymbol.FLATNESS,
                               tolerance_value=0.05)
        assert t.to_dict()["category"] == "form"

    def test_drawing_json_summary_list(self):
        """gdt_callout_report 'summary' is the drawing-JSON surface."""
        features = [
            _tol("face-top", "FLATNESS", 0.05),
            _tol("bore", "POSITION", 0.1, diameter_zone=True, datum_ref={"primary": "A"}),
            _tol("shaft-od", "RUNOUT", 0.03, datum_ref={"primary": "B"}),
        ]
        report = gdt_callout_report(features)
        assert report["count"] == 3
        summary = report["summary"]
        assert len(summary) == 3
        # Each summary entry is a full to_dict() payload
        symbols = {s["symbol"] for s in summary}
        assert symbols == {"FLATNESS", "POSITION", "RUNOUT"}

    def test_drawing_json_summary_each_has_category(self):
        features = [
            _tol("f1", "FLATNESS", 0.01),
            _tol("f2", "POSITION", 0.05, datum_ref={"primary": "A"}),
            _tol("f3", "PARALLELISM", 0.03, datum_ref={"primary": "A"}),
            _tol("f4", "RUNOUT", 0.02, datum_ref={"primary": "A"}),
            _tol("f5", "PROFILE_SURFACE", 0.1),
        ]
        report = gdt_callout_report(features)
        cats = {e["symbol"]: e["category"] for e in report["summary"]}
        assert cats["FLATNESS"] == "form"
        assert cats["POSITION"] == "location"
        assert cats["PARALLELISM"] == "orientation"
        assert cats["RUNOUT"] == "runout"
        assert cats["PROFILE_SURFACE"] == "profile"

    def test_drawing_json_datum_ref_embedded(self):
        features = [
            _tol("bore", "POSITION", 0.1,
                 datum_ref={"primary": "A", "secondary": "B", "tertiary": "C"}),
        ]
        report = gdt_callout_report(features)
        dr = report["summary"][0]["datum_ref"]
        assert dr["primary"] == "A"
        assert dr["secondary"] == "B"
        assert dr["tertiary"] == "C"


# ---------------------------------------------------------------------------
# 6. Idempotency
# ---------------------------------------------------------------------------

class TestIdempotency:
    """Applying the same callout twice should produce identical output."""

    def test_idempotent_flatness_roundtrip(self):
        d = _tol("top", "FLATNESS", 0.05)
        t1 = GeometricTolerance.from_dict(d)
        t2 = GeometricTolerance.from_dict(t1.to_dict())
        assert t1.to_dict() == t2.to_dict()

    def test_idempotent_position_with_full_drf(self):
        d = _tol("bore", "POSITION", 0.1, diameter_zone=True,
                 datum_ref={"primary": "A", "secondary": "B", "tertiary": "C"},
                 modifiers=["MMC"], is_feature_of_size=True)
        t1 = GeometricTolerance.from_dict(d)
        t2 = GeometricTolerance.from_dict(t1.to_dict())
        assert t1.to_dict() == t2.to_dict()

    def test_idempotent_report_generation(self):
        features = [
            _tol("f1", "FLATNESS", 0.05),
            _tol("f2", "POSITION", 0.1, datum_ref={"primary": "A"}),
        ]
        r1 = gdt_callout_report(copy.deepcopy(features))
        r2 = gdt_callout_report(copy.deepcopy(features))
        assert r1["count"] == r2["count"]
        assert r1["callouts"] == r2["callouts"]
        assert r1["by_category"] == r2["by_category"]

    def test_idempotent_datum_round_trip(self):
        d1 = Datum(label="A", datum_type=DatumType.AXIS, feature_ref="shaft-end",
                   description="primary axis", is_compound=False)
        d2 = Datum.from_dict(d1.to_dict())
        assert d1.to_dict() == d2.to_dict()


# ---------------------------------------------------------------------------
# 7. validate_scheme rules — all major constraint categories
# ---------------------------------------------------------------------------

class TestValidateSchemeRules:
    """Cross-category scheme validation."""

    def test_form_tolerance_needs_no_datum(self):
        for sym in ["FLATNESS", "STRAIGHTNESS", "CIRCULARITY", "CYLINDRICITY"]:
            r = _validate_scheme(datums=[], tolerances=[_tol("f", sym, 0.05)])
            assert r["ok"] is True, f"{sym} should not require datum: {r['errors']}"

    def test_orientation_without_datum_is_permitted_by_validator(self):
        # The current validator enforces datum-requirement only for POSITION,
        # CONCENTRICITY, SYMMETRY, and RUNOUT/TOTAL_RUNOUT.  Orientation
        # tolerances (PARALLELISM, PERPENDICULARITY, ANGULARITY) are allowed
        # through without a datum — they carry a category but no hard constraint.
        for sym in ["PARALLELISM", "PERPENDICULARITY", "ANGULARITY"]:
            r = _validate_scheme(datums=[], tolerances=[_tol("f", sym, 0.05)])
            assert r["ok"] is True, f"{sym} validator unexpectedly rejected datum-free case"

    def test_location_position_requires_datum(self):
        r = _validate_scheme(datums=[],
                              tolerances=[_tol("bore", "POSITION", 0.1)])
        assert r["ok"] is False

    def test_runout_requires_exactly_one_axis_datum(self):
        # Two axis datums in ref — invalid
        r = _validate_scheme(
            datums=[_axis_datum("A"), _axis_datum("B")],
            tolerances=[_tol("od", "RUNOUT", 0.02,
                             datum_ref={"primary": "A", "secondary": "B"})],
        )
        assert r["ok"] is False
        assert any("exactly one" in e for e in r["errors"])

    def test_runout_plane_datum_invalid(self):
        r = _validate_scheme(
            datums=[_plane_datum("A")],
            tolerances=[_tol("od", "RUNOUT", 0.02, datum_ref={"primary": "A"})],
        )
        assert r["ok"] is False
        assert any("AXIS" in e for e in r["errors"])

    def test_concentricity_requires_axis_or_centre_plane(self):
        # PLANE datum → invalid
        r = _validate_scheme(
            datums=[_plane_datum("A")],
            tolerances=[_tol("dia", "CONCENTRICITY", 0.01, datum_ref={"primary": "A"})],
        )
        assert r["ok"] is False

    def test_symmetry_requires_centre_plane_or_axis(self):
        r = _validate_scheme(
            datums=[_plane_datum("A")],
            tolerances=[_tol("slot", "SYMMETRY", 0.02, datum_ref={"primary": "A"})],
        )
        assert r["ok"] is False

    def test_mmc_without_fos_fails(self):
        r = _validate_scheme(
            datums=[_axis_datum("A")],
            tolerances=[_tol("bore", "POSITION", 0.05,
                             datum_ref={"primary": "A"},
                             modifiers=["MMC"],
                             is_feature_of_size=False)],
        )
        assert r["ok"] is False
        assert any("MMC" in e for e in r["errors"])

    def test_projected_without_height_fails(self):
        r = _validate_scheme(
            datums=[_axis_datum("A")],
            tolerances=[_tol("hole", "POSITION", 0.1,
                             datum_ref={"primary": "A"},
                             modifiers=["PROJECTED"],
                             is_feature_of_size=True)],
        )
        assert r["ok"] is False
        assert any("projected_zone_height" in e for e in r["errors"])

    def test_multiple_violations_all_reported(self):
        r = _validate_scheme(
            datums=[_plane_datum("A")],
            tolerances=[
                _tol("bore", "POSITION", 0.05),          # missing datum
                _tol("od", "RUNOUT", 0.02, datum_ref={"primary": "A"}),  # plane not axis
            ],
        )
        assert r["ok"] is False
        assert len(r["errors"]) >= 2

    def test_empty_scheme_always_valid(self):
        r = _validate_scheme(datums=[], tolerances=[])
        assert r["ok"] is True

    def test_full_valid_three_datum_scheme(self):
        datums = [_plane_datum("A"), _plane_datum("B"), _axis_datum("C")]
        tolerances = [
            _tol("base", "FLATNESS", 0.02),
            _tol("wall", "PERPENDICULARITY", 0.05, datum_ref={"primary": "A"}),
            _tol("bore", "POSITION", 0.1, diameter_zone=True,
                 datum_ref={"primary": "A", "secondary": "B"},
                 modifiers=["MMC"], is_feature_of_size=True),
            _tol("shaft-od", "RUNOUT", 0.03, datum_ref={"primary": "C"}),
        ]
        r = _validate_scheme(datums=datums, tolerances=tolerances)
        assert r["ok"] is True, f"Valid scheme failed: {r['errors']}"


# ---------------------------------------------------------------------------
# 8. Callout report drawing-JSON surface — format checks
# ---------------------------------------------------------------------------

class TestCalloutReportFormat:
    """Callout report is the drawing annotation surface per the spec."""

    def test_callout_text_contains_symbol_char_for_all_14(self):
        """The text report renders the unicode character for every symbol."""
        sym_char_pairs = [
            ("FLATNESS",         "⏥"),
            ("STRAIGHTNESS",     "⏤"),
            ("CIRCULARITY",      "○"),
            ("CYLINDRICITY",     "⌭"),
            ("PROFILE_LINE",     "⌒"),
            ("PROFILE_SURFACE",  "⌓"),
            ("PARALLELISM",      "∥"),
            ("PERPENDICULARITY", "⊥"),
            ("ANGULARITY",       "∠"),
            ("POSITION",         "⊕"),
            ("CONCENTRICITY",    "◎"),
            ("SYMMETRY",         "≡"),
            ("RUNOUT",           "↗"),
            ("TOTAL_RUNOUT",     "⟿"),
        ]
        for sym, char in sym_char_pairs:
            datum = {"primary": "A"} if sym not in {
                "FLATNESS", "STRAIGHTNESS", "CIRCULARITY", "CYLINDRICITY",
                "PROFILE_LINE", "PROFILE_SURFACE",
            } else None
            features = [_tol(f"feat-{sym}", sym, 0.05, datum_ref=datum)]
            r = gdt_callout_report(features)
            assert char in r["callouts"][0], f"Symbol char {char!r} missing for {sym}"

    def test_by_category_all_five_cats(self):
        features = [
            _tol("f1", "FLATNESS", 0.01),
            _tol("f2", "PROFILE_SURFACE", 0.05),
            _tol("f3", "PERPENDICULARITY", 0.03, datum_ref={"primary": "A"}),
            _tol("f4", "POSITION", 0.1, datum_ref={"primary": "A"}),
            _tol("f5", "RUNOUT", 0.02, datum_ref={"primary": "A"}),
        ]
        r = gdt_callout_report(features)
        cats = set(r["by_category"].keys())
        assert cats == {"form", "profile", "orientation", "location", "runout"}

    def test_parse_error_skips_bad_entry(self):
        features = [
            {"feature_name": "", "symbol": "FLATNESS", "tolerance_value": 0.05},  # bad
            _tol("good", "FLATNESS", 0.05),
        ]
        r = gdt_callout_report(features)
        assert r["count"] == 1
        assert len(r["parse_errors"]) == 1

    def test_diameter_prefix_in_callout(self):
        features = [_tol("bore", "POSITION", 0.05,
                         diameter_zone=True, datum_ref={"primary": "A"})]
        r = gdt_callout_report(features)
        assert "⌀" in r["callouts"][0]

    def test_datum_labels_in_callout_text(self):
        features = [_tol("pin", "POSITION", 0.1,
                         datum_ref={"primary": "A", "secondary": "B", "tertiary": "C"})]
        r = gdt_callout_report(features)
        text = r["callouts"][0]
        for label in ["A", "B", "C"]:
            assert label in text

    def test_modifier_chars_in_callout(self):
        for mod, expected_char in [("MMC", "(M)"), ("LMC", "(L)"), ("RFS", "(S)")]:
            features = [_tol("bore", "POSITION", 0.05,
                             datum_ref={"primary": "A"},
                             modifiers=[mod],
                             is_feature_of_size=True)]
            r = gdt_callout_report(features)
            assert expected_char in r["callouts"][0], \
                f"Expected {expected_char!r} for modifier {mod}"
