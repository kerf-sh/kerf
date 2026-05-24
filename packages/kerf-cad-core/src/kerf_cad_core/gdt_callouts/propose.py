"""
kerf_cad_core.gdt_callouts.propose — IT-grade tolerance maths and per-feature
callout proposal rules.

ISO 286-1 defines fundamental deviations for fits and tolerances.  The
International Tolerance (IT) grades IT01 through IT18 scale with nominal
dimension using the formula:

    IT = k * i

where `i` is the standard tolerance unit:

    i (µm) = 0.45 * D^(1/3)  +  0.001 * D        (D in mm, geometric mean of range)

and `k` is a grade-specific multiplier.

Grade multipliers k (units of `i`):
    IT01: 0.3,  IT0: 0.5,  IT1: 0.8,  IT2: 1.2,  IT3: 2,   IT4: 3,
    IT5: 7,     IT6: 10,   IT7: 16,   IT8: 25,   IT9: 40,  IT10: 64,
    IT11: 100,  IT12: 160, IT13: 250, IT14: 400, IT15: 640, IT16: 1000,
    IT17: 1600, IT18: 2500

ISO 286-1 Table 2 dimension ranges (mm):
    (0, 3], (3, 6], (6, 10], (10, 18], (18, 30], (30, 50], (50, 80],
    (80, 120], (120, 180], (180, 250], (250, 315], (315, 400], (400, 500]

For nominal sizes beyond the table the formula is extrapolated using the
same unit-of-tolerance formula.

Feature types recognised:
    "hole"          — circular bore (has diameter)
    "slot"          — rectangular/elongated recess (has width, optionally length)
    "planar_face"   — flat surface (has area / no dimension required)
    "cylindrical"   — external or internal cylindrical surface (has diameter)
    "pattern"       — repeating array of holes/features (has count + pitch)
    "freeform"      — sculptured / non-analytical surface

Tolerancing intent values (guide how tight to make calls):
    "loose"   — 2 IT grades coarser than nominal
    "nominal" — grade as-supplied (default)
    "tight"   — 1 IT grade finer than nominal
    "precise" — 2 IT grades finer than nominal
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from kerf_cad_core.gdt.datums import Datum, DatumType, DatumReferenceFrame
from kerf_cad_core.gdt.tolerances import GeometricTolerance, ToleranceSymbol
from kerf_cad_core.gdt.modifiers import ToleranceModifier
from kerf_cad_core.gdt.it_grades import (
    IT_GRADE_MULTIPLIERS as IT_GRADES,
    GRADE_ORDER as _GRADE_ORDER,
    VALID_GRADES,
    it_tolerance_mm,
    _find_dim_range,
    _tolerance_unit_i,
)


def it_grade_tolerance(nominal_mm: float, grade: str) -> float:
    """Thin wrapper preserving the legacy (nominal_mm, grade) call signature."""
    return it_tolerance_mm(grade, nominal_mm)

#: Tolerancing intent → grade offset (positive = coarser)
_INTENT_OFFSET: dict[str, int] = {
    "loose":   2,
    "nominal": 0,
    "tight":  -1,
    "precise": -2,
}

VALID_INTENTS: frozenset[str] = frozenset(_INTENT_OFFSET.keys())

#: Recognised feature types
VALID_FEATURE_TYPES: frozenset[str] = frozenset({
    "hole", "slot", "planar_face", "cylindrical", "pattern", "freeform",
})



def _grade_order_idx(grade: str) -> int:
    """Return the position of *grade* in the coarseness ordering (0 = finest)."""
    return _GRADE_ORDER.index(grade.upper())


def _adjust_grade(base_grade: str, intent: str) -> str:
    """
    Apply an intent offset to a base IT grade, clamping to valid range.

    Parameters
    ----------
    base_grade:
        The base IT grade (e.g. 'IT7').
    intent:
        Tolerancing intent: 'loose', 'nominal', 'tight', 'precise'.

    Returns
    -------
    Adjusted grade string.
    """
    offset = _INTENT_OFFSET.get(intent.lower(), 0)
    idx = _GRADE_ORDER.index(base_grade.upper())
    new_idx = max(0, min(len(_GRADE_ORDER) - 1, idx + offset))
    return _GRADE_ORDER[new_idx]


# ---------------------------------------------------------------------------
# Feature dataclass
# ---------------------------------------------------------------------------

@dataclass
class FeatureSpec:
    """
    Specification of a single model feature for callout proposal.

    Attributes
    ----------
    feature_id:
        Unique identifier of the feature (face name, feature-tree id, etc.).
    feature_type:
        One of: hole, slot, planar_face, cylindrical, pattern, freeform.
    nominal_size_mm:
        Characteristic dimension in mm:
          hole/cylindrical → diameter
          slot             → width
          planar_face      → longest edge or diagonal (used for IT lookup)
          pattern          → pitch between instances
          freeform         → characteristic span
        Set to 0 or omit for dimensionless features (tolerances use a
        size-independent fallback of 25 mm for IT lookup).
    orientation_datum:
        Datum label this feature's orientation is measured against
        (e.g. primary plane datum 'A'). Used for PERPENDICULARITY /
        PARALLELISM callouts on planar faces.
    axis_datum:
        Datum label of the rotation axis this feature is measured about.
        Used for RUNOUT callouts on cylindrical surfaces.
    primary_datum:
        Primary position reference datum label.  Used for POSITION callouts
        on holes and patterns.
    secondary_datum:
        Secondary datum label (optional).
    tertiary_datum:
        Tertiary datum label (optional).
    pattern_count:
        Number of instances in a pattern feature.  Required when
        feature_type == 'pattern'.
    is_feature_of_size:
        Whether the feature has an actual size (True for holes, cylinders,
        slots).  Inferred from feature_type when not supplied.
    extra:
        Arbitrary dict of extra metadata (not used by proposal logic).
    """
    feature_id: str
    feature_type: str
    nominal_size_mm: float = 0.0
    orientation_datum: Optional[str] = None
    axis_datum: Optional[str] = None
    primary_datum: Optional[str] = None
    secondary_datum: Optional[str] = None
    tertiary_datum: Optional[str] = None
    pattern_count: int = 0
    is_feature_of_size: Optional[bool] = None
    extra: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.feature_id = self.feature_id.strip()
        if not self.feature_id:
            raise ValueError("FeatureSpec.feature_id must not be empty")
        self.feature_type = self.feature_type.lower().strip()
        if self.feature_type not in VALID_FEATURE_TYPES:
            raise ValueError(
                f"FeatureSpec.feature_type '{self.feature_type}' is not valid. "
                f"Valid types: {sorted(VALID_FEATURE_TYPES)}"
            )
        self.nominal_size_mm = max(float(self.nominal_size_mm), 0.0)
        # Infer is_feature_of_size when not supplied
        if self.is_feature_of_size is None:
            self.is_feature_of_size = self.feature_type in {
                "hole", "cylindrical", "slot", "pattern"
            }

    @classmethod
    def from_dict(cls, d: dict) -> "FeatureSpec":
        return cls(
            feature_id=d["feature_id"],
            feature_type=d["feature_type"],
            nominal_size_mm=float(d.get("nominal_size_mm") or 0.0),
            orientation_datum=d.get("orientation_datum"),
            axis_datum=d.get("axis_datum"),
            primary_datum=d.get("primary_datum"),
            secondary_datum=d.get("secondary_datum"),
            tertiary_datum=d.get("tertiary_datum"),
            pattern_count=int(d.get("pattern_count") or 0),
            is_feature_of_size=d.get("is_feature_of_size"),
            extra=dict(d.get("extra") or {}),
        )

    def to_dict(self) -> dict:
        return {
            "feature_id": self.feature_id,
            "feature_type": self.feature_type,
            "nominal_size_mm": self.nominal_size_mm,
            "orientation_datum": self.orientation_datum,
            "axis_datum": self.axis_datum,
            "primary_datum": self.primary_datum,
            "secondary_datum": self.secondary_datum,
            "tertiary_datum": self.tertiary_datum,
            "pattern_count": self.pattern_count,
            "is_feature_of_size": self.is_feature_of_size,
            "extra": self.extra,
        }


# ---------------------------------------------------------------------------
# Callout proposal result
# ---------------------------------------------------------------------------

@dataclass
class ProposedCallout:
    """
    A single auto-proposed GD&T callout.

    Attributes
    ----------
    feature_id:
        Feature this callout is attached to.
    tolerance:
        The proposed GeometricTolerance (feature control frame).
    rationale:
        Human-readable explanation of why this callout was chosen.
    grade_used:
        The effective IT grade used (after intent adjustment).
    """
    feature_id: str
    tolerance: GeometricTolerance
    rationale: str
    grade_used: str

    def to_dict(self) -> dict:
        return {
            "feature_id": self.feature_id,
            "tolerance": self.tolerance.to_dict(),
            "rationale": self.rationale,
            "grade_used": self.grade_used,
        }


# ---------------------------------------------------------------------------
# Per-feature-type callout rules
# ---------------------------------------------------------------------------

def _effective_nominal(spec: FeatureSpec) -> float:
    """Return the nominal dimension to use for IT lookup (fallback 25 mm)."""
    return spec.nominal_size_mm if spec.nominal_size_mm > 0.0 else 25.0


def _propose_hole(
    spec: FeatureSpec, grade: str, datums: dict[str, Datum]
) -> tuple[Optional[GeometricTolerance], str]:
    """
    Propose a POSITION callout for a hole feature.

    Requires at least one position datum (primary_datum).  If no datum is
    available returns a friendly explanation instead of raising.
    """
    if not spec.primary_datum:
        return None, (
            f"hole '{spec.feature_id}': no primary_datum supplied; "
            "POSITION requires at least one datum reference"
        )

    nominal = _effective_nominal(spec)
    tol_mm = it_grade_tolerance(nominal, grade)

    drf = DatumReferenceFrame(
        primary=spec.primary_datum,
        secondary=spec.secondary_datum,
        tertiary=spec.tertiary_datum,
    )

    tol = GeometricTolerance(
        feature_name=spec.feature_id,
        symbol=ToleranceSymbol.POSITION,
        tolerance_value=tol_mm,
        diameter_zone=True,
        datum_ref=drf,
        modifiers=[ToleranceModifier.MMC] if spec.is_feature_of_size else [],
        is_feature_of_size=bool(spec.is_feature_of_size),
        note=f"auto-proposed {grade}, ⌀{nominal} mm nominal",
    )
    return tol, (
        f"hole '{spec.feature_id}': POSITION ⌀{tol_mm:.4g} mm ({grade}), "
        f"datum ref {drf}"
    )


def _propose_slot(
    spec: FeatureSpec, grade: str, datums: dict[str, Datum]
) -> tuple[Optional[GeometricTolerance], str]:
    """
    Propose a POSITION (centre-plane) callout for a slot.

    Slots use a linear (non-diametrical) tolerance zone about the
    centre-plane.  If no primary_datum is set falls back to SYMMETRY
    about a centre-plane datum when axis_datum is available, or emits a
    friendly message if neither is present.
    """
    nominal = _effective_nominal(spec)
    tol_mm = it_grade_tolerance(nominal, grade)

    if spec.primary_datum:
        drf = DatumReferenceFrame(
            primary=spec.primary_datum,
            secondary=spec.secondary_datum,
        )
        tol = GeometricTolerance(
            feature_name=spec.feature_id,
            symbol=ToleranceSymbol.POSITION,
            tolerance_value=tol_mm,
            diameter_zone=False,
            datum_ref=drf,
            modifiers=[],
            is_feature_of_size=True,
            note=f"auto-proposed {grade}, centre-plane, width {nominal} mm",
        )
        return tol, (
            f"slot '{spec.feature_id}': POSITION {tol_mm:.4g} mm ({grade}) "
            f"centre-plane, datum ref {drf}"
        )

    # No datum — return a warning
    return None, (
        f"slot '{spec.feature_id}': no primary_datum supplied; "
        "POSITION requires at least one datum reference"
    )


def _propose_planar_face(
    spec: FeatureSpec, grade: str, datums: dict[str, Datum]
) -> tuple[Optional[GeometricTolerance], str]:
    """
    Propose PERPENDICULARITY or PARALLELISM for a planar face.

    The choice depends on whether the orientation_datum is a PLANE datum
    (yields PERPENDICULARITY when the face is nominally perpendicular, or
    PARALLELISM when nominally parallel) — in the absence of geometric
    angle context we default to PERPENDICULARITY.

    If no orientation_datum is supplied the feature gets a FLATNESS callout
    (form tolerance, no datum required).
    """
    nominal = _effective_nominal(spec)
    tol_mm = it_grade_tolerance(nominal, grade)

    if not spec.orientation_datum:
        # No datum context → FLATNESS
        tol = GeometricTolerance(
            feature_name=spec.feature_id,
            symbol=ToleranceSymbol.FLATNESS,
            tolerance_value=tol_mm,
            diameter_zone=False,
            note=f"auto-proposed {grade}, no datum → FLATNESS",
        )
        return tol, (
            f"planar_face '{spec.feature_id}': no orientation_datum → "
            f"FLATNESS {tol_mm:.4g} mm ({grade})"
        )

    # Check whether the datum is an AXIS datum (→ PERPENDICULARITY by default)
    datum_obj = datums.get(spec.orientation_datum)
    use_parallel = (
        datum_obj is not None and datum_obj.datum_type == DatumType.PLANE
        and spec.extra.get("face_orientation") == "parallel"
    )
    symbol = (
        ToleranceSymbol.PARALLELISM if use_parallel
        else ToleranceSymbol.PERPENDICULARITY
    )
    drf = DatumReferenceFrame(primary=spec.orientation_datum)
    tol = GeometricTolerance(
        feature_name=spec.feature_id,
        symbol=symbol,
        tolerance_value=tol_mm,
        diameter_zone=False,
        datum_ref=drf,
        modifiers=(
            [ToleranceModifier.TANGENT]
            if spec.extra.get("tangent_modifier") else []
        ),
        note=f"auto-proposed {grade}",
    )
    return tol, (
        f"planar_face '{spec.feature_id}': {symbol.value} {tol_mm:.4g} mm "
        f"({grade}) to datum {spec.orientation_datum}"
    )


def _propose_cylindrical(
    spec: FeatureSpec, grade: str, datums: dict[str, Datum]
) -> tuple[Optional[GeometricTolerance], str]:
    """
    Propose RUNOUT about an axis datum for a cylindrical surface.

    If axis_datum is absent the feature receives a CYLINDRICITY callout
    (form, no datum required).
    """
    nominal = _effective_nominal(spec)
    tol_mm = it_grade_tolerance(nominal, grade)

    if not spec.axis_datum:
        tol = GeometricTolerance(
            feature_name=spec.feature_id,
            symbol=ToleranceSymbol.CYLINDRICITY,
            tolerance_value=tol_mm,
            diameter_zone=False,
            note=f"auto-proposed {grade}, no axis_datum → CYLINDRICITY",
        )
        return tol, (
            f"cylindrical '{spec.feature_id}': no axis_datum → "
            f"CYLINDRICITY {tol_mm:.4g} mm ({grade})"
        )

    # Validate the datum is of AXIS type if we have datum info
    datum_obj = datums.get(spec.axis_datum)
    if datum_obj is not None and datum_obj.datum_type != DatumType.AXIS:
        return None, (
            f"cylindrical '{spec.feature_id}': axis_datum '{spec.axis_datum}' "
            f"is type {datum_obj.datum_type.value}, expected AXIS; "
            "RUNOUT requires an AXIS datum"
        )

    drf = DatumReferenceFrame(primary=spec.axis_datum)
    tol = GeometricTolerance(
        feature_name=spec.feature_id,
        symbol=ToleranceSymbol.RUNOUT,
        tolerance_value=tol_mm,
        diameter_zone=False,
        datum_ref=drf,
        is_feature_of_size=True,
        note=f"auto-proposed {grade}, ⌀{nominal} mm nominal",
    )
    return tol, (
        f"cylindrical '{spec.feature_id}': RUNOUT {tol_mm:.4g} mm ({grade}) "
        f"about axis datum {spec.axis_datum}"
    )


def _propose_pattern(
    spec: FeatureSpec, grade: str, datums: dict[str, Datum]
) -> tuple[Optional[GeometricTolerance], str]:
    """
    Propose a composite POSITION callout for a hole/feature pattern.

    Per ASME Y14.5-2018 §7.5 composite positional tolerancing is used for
    patterns: the upper segment controls location of the pattern as a group
    relative to the DRF; the lower segment controls the inter-feature
    geometry.  Here we propose the primary (location) callout only — the
    lower segment tightened by one IT grade is noted in the rationale.

    Requires primary_datum for position reference.
    """
    if not spec.primary_datum:
        return None, (
            f"pattern '{spec.feature_id}': no primary_datum supplied; "
            "POSITION requires at least one datum reference"
        )

    nominal = _effective_nominal(spec)
    tol_mm = it_grade_tolerance(nominal, grade)

    # Intra-pattern segment: one IT grade finer
    fine_grade = _adjust_grade(grade, "tight")
    fine_tol_mm = it_grade_tolerance(nominal, fine_grade)

    drf = DatumReferenceFrame(
        primary=spec.primary_datum,
        secondary=spec.secondary_datum,
        tertiary=spec.tertiary_datum,
    )
    count_note = (
        f" ({spec.pattern_count} instances)" if spec.pattern_count > 1 else ""
    )
    tol = GeometricTolerance(
        feature_name=spec.feature_id,
        symbol=ToleranceSymbol.POSITION,
        tolerance_value=tol_mm,
        diameter_zone=True,
        datum_ref=drf,
        modifiers=[ToleranceModifier.MMC],
        is_feature_of_size=True,
        note=(
            f"composite POSITION, pattern{count_note}; intra-pattern "
            f"segment: ⌀{fine_tol_mm:.4g} mm ({fine_grade})"
        ),
    )
    return tol, (
        f"pattern '{spec.feature_id}'{count_note}: composite POSITION "
        f"⌀{tol_mm:.4g} mm ({grade}) + intra-segment ⌀{fine_tol_mm:.4g} mm "
        f"({fine_grade}), datum ref {drf}"
    )


def _propose_freeform(
    spec: FeatureSpec, grade: str, datums: dict[str, Datum]
) -> tuple[Optional[GeometricTolerance], str]:
    """
    Propose PROFILE_SURFACE for a free-form / sculptured surface.

    If a primary_datum is available it is included in the datum reference
    frame (bilateral profile with respect to true profile).  Without a datum
    it is an all-around unilateral profile (form only, no datum).
    """
    nominal = _effective_nominal(spec)
    # Profile tolerances are typically 2 IT grades coarser than positional
    coarse_grade = _adjust_grade(grade, "loose")
    tol_mm = it_grade_tolerance(nominal, coarse_grade)

    if not spec.primary_datum:
        tol = GeometricTolerance(
            feature_name=spec.feature_id,
            symbol=ToleranceSymbol.PROFILE_SURFACE,
            tolerance_value=tol_mm,
            diameter_zone=False,
            note=f"auto-proposed {coarse_grade}, freeform no datum",
        )
        return tol, (
            f"freeform '{spec.feature_id}': PROFILE_SURFACE {tol_mm:.4g} mm "
            f"({coarse_grade}), no datum → all-around unilateral form"
        )

    drf = DatumReferenceFrame(
        primary=spec.primary_datum,
        secondary=spec.secondary_datum,
    )
    tol = GeometricTolerance(
        feature_name=spec.feature_id,
        symbol=ToleranceSymbol.PROFILE_SURFACE,
        tolerance_value=tol_mm,
        diameter_zone=False,
        datum_ref=drf,
        note=f"auto-proposed {coarse_grade}, bilateral to true profile",
    )
    return tol, (
        f"freeform '{spec.feature_id}': PROFILE_SURFACE {tol_mm:.4g} mm "
        f"({coarse_grade}) bilateral to true profile, datum ref {drf}"
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

_PROPOSERS = {
    "hole":        _propose_hole,
    "slot":        _propose_slot,
    "planar_face": _propose_planar_face,
    "cylindrical": _propose_cylindrical,
    "pattern":     _propose_pattern,
    "freeform":    _propose_freeform,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def propose_callouts(
    features: list[dict[str, Any]],
    datums: list[dict[str, Any]],
    grade: str = "IT7",
    intent: str = "nominal",
) -> dict[str, Any]:
    """
    Auto-propose GD&T callouts for a list of classified model features.

    Parameters
    ----------
    features:
        List of feature dicts, each deserialisable as a FeatureSpec.
    datums:
        List of datum dicts (Datum.to_dict() format).  Used to validate
        datum types against callout requirements.
    grade:
        Base IT tolerance grade, e.g. 'IT7' (default).
    intent:
        Tolerancing intent: 'loose', 'nominal' (default), 'tight', 'precise'.
        Adjusts the effective grade by ±1-2 steps.

    Returns
    -------
    dict with keys:
        ``ok``          — True when all inputs were valid (even if some
                          features produced warnings rather than callouts)
        ``callouts``    — list of ProposedCallout.to_dict() entries
        ``warnings``    — list of human-readable warning strings (features
                          that could not get a callout, or datum mismatches)
        ``count``       — number of callouts proposed
        ``grade_used``  — effective IT grade after intent adjustment
        ``reason``      — present only when ok == False (top-level error)
    """
    # --- Validate grade ---
    grade_upper = grade.upper() if grade else ""
    if grade_upper not in IT_GRADES:
        return {
            "ok": False,
            "reason": (
                f"Unknown IT grade '{grade}'. "
                f"Valid grades: {sorted(IT_GRADES)}"
            ),
        }

    # --- Validate intent ---
    intent_lower = intent.lower() if intent else "nominal"
    if intent_lower not in _INTENT_OFFSET:
        return {
            "ok": False,
            "reason": (
                f"Unknown intent '{intent}'. "
                f"Valid intents: {sorted(_INTENT_OFFSET)}"
            ),
        }

    effective_grade = _adjust_grade(grade_upper, intent_lower)

    # --- Parse datums ---
    datum_map: dict[str, Datum] = {}
    datum_parse_warnings: list[str] = []
    for i, raw in enumerate(datums or []):
        try:
            d = Datum.from_dict(raw)
            datum_map[d.label] = d
        except Exception as exc:
            datum_parse_warnings.append(f"datum[{i}]: parse error: {exc}")

    # --- Validate features list ---
    if not isinstance(features, list):
        return {"ok": False, "reason": "features must be a list"}

    # --- Propose callouts ---
    callouts: list[dict] = []
    warnings: list[str] = list(datum_parse_warnings)

    for i, raw in enumerate(features):
        if not isinstance(raw, dict):
            warnings.append(f"features[{i}]: expected dict, got {type(raw).__name__}")
            continue

        try:
            spec = FeatureSpec.from_dict(raw)
        except Exception as exc:
            warnings.append(f"features[{i}]: parse error: {exc}")
            continue

        proposer = _PROPOSERS.get(spec.feature_type)
        if proposer is None:
            warnings.append(
                f"features[{i}] '{spec.feature_id}': "
                f"no proposer for type '{spec.feature_type}'"
            )
            continue

        tol, rationale = proposer(spec, effective_grade, datum_map)
        if tol is None:
            warnings.append(rationale)
        else:
            callout = ProposedCallout(
                feature_id=spec.feature_id,
                tolerance=tol,
                rationale=rationale,
                grade_used=effective_grade,
            )
            callouts.append(callout.to_dict())

    return {
        "ok": True,
        "callouts": callouts,
        "warnings": warnings,
        "count": len(callouts),
        "grade_used": effective_grade,
    }
