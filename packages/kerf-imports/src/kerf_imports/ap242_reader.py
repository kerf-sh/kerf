"""
ap242_reader.py — AP242 PMI / GD&T annotation reader.

Parses STEP Part 21 files (AP242 ed.1/ed.2) at the text level — no OCCT or
kernel dependency.  Extracts:

  • PMI annotations (DRAUGHTING_CALLOUT, ANNOTATION_OCCURRENCE,
    PMI_REPRESENTATION_ITEM, ANNOTATION_PLANE)
  • Datum reference frames (DATUM_FEATURE, DATUM_REFERENCE_COMPARTMENT,
    DATUM_REFERENCE_ELEMENT, DATUM)
  • GD&T tolerances (GEOMETRIC_TOLERANCE, GEOMETRIC_TOLERANCE_WITH_DATUM_REFERENCE,
    PLUS_MINUS_TOLERANCE, SYMMETRY_TOLERANCE, CYLINDRICITY_TOLERANCE,
    FLATNESS_TOLERANCE, PERPENDICULARITY_TOLERANCE, PARALLELISM_TOLERANCE,
    ANGULARITY_TOLERANCE, CIRCULARITY_TOLERANCE, STRAIGHTNESS_TOLERANCE,
    POSITION_TOLERANCE, TOTAL_RUNOUT_TOLERANCE, CIRCULAR_RUNOUT_TOLERANCE)
  • Dimensional sizes (DIMENSIONAL_SIZE, LINEAR_SIZE,
    DIMENSIONAL_CHARACTERISTIC_REPRESENTATION)

Entity tokeniser is shared with the STEP reader in kerf_cad_core.io.step_reader
(regex-level: #NNN = ENTITY_NAME(...)).

Output schema
─────────────
read_ap242_pmi(step_text) → {
  "ok": True,
  "schema": str | None,
  "product": str | None,
  "annotations": [
    {
      "kind": "pmi_annotation" | "draughting_callout" | "annotation_plane",
      "id": int,          # entity ID
      "name": str | None,
      "refs": [int],      # referenced entity IDs
    },
    ...
  ],
  "datums": [
    {
      "kind": "datum_feature" | "datum" | "datum_reference",
      "id": int,
      "label": str | None,
      "refs": [int],
    },
    ...
  ],
  "tolerances": [
    {
      "kind": str,          # e.g. "GEOMETRIC_TOLERANCE", "FLATNESS_TOLERANCE" …
      "id": int,
      "name": str | None,
      "magnitude": float | None,
      "unit": str | None,
      "refs": [int],
    },
    ...
  ],
  "dimensional_sizes": [
    {
      "id": int,
      "name": str | None,
      "nominal": float | None,
      "upper_tol": float | None,
      "lower_tol": float | None,
      "refs": [int],
    },
    ...
  ],
  "drawing_annotations": [
    # Merged flat list suitable for a .drawing annotation list.
    # Each item: {"type": str, "label": str, "id": int, "refs": [int]}
    ...
  ],
  "warnings": [str],
}
"""

from __future__ import annotations

import re
from typing import Any

__all__ = ["read_ap242_pmi", "AP242ReadError"]


class AP242ReadError(ValueError):
    """Raised only for completely unparseable input."""


# ─── Regex constants ──────────────────────────────────────────────────────────

# Entity line: #NNN = ENTITY_NAME ( ... )
_ENTITY_RE = re.compile(
    r"#(\d+)\s*=\s*([A-Z_][A-Z0-9_]*)\s*\((.*)\)\s*;",
    re.DOTALL,
)

# STEP file may split entities over many physical lines; we need to reassemble.
# We normalise into one logical line per entity before applying _ENTITY_RE.

_REF_RE = re.compile(r"#(\d+)")
_STRING_RE = re.compile(r"'([^']*)'")
_REAL_RE = re.compile(r"[+-]?(?:\d+\.?\d*|\.\d+)(?:[Ee][+-]?\d+)?")

# PMI annotation entity names
_PMI_ENTITY_NAMES: frozenset[str] = frozenset({
    "PMI_REPRESENTATION_ITEM",
    "DRAUGHTING_CALLOUT",
    "ANNOTATION_OCCURRENCE",
    "ANNOTATION_PLANE",
    "ANNOTATION_FILL_AREA",
    "DRAUGHTING_ELEMENTS",
    "DRAUGHTING_MODEL_ITEM_ASSOCIATION",
    "ANNOTATION_TEXT",
})

# Datum entity names
_DATUM_ENTITY_NAMES: frozenset[str] = frozenset({
    "DATUM_FEATURE",
    "DATUM",
    "DATUM_REFERENCE",
    "DATUM_REFERENCE_COMPARTMENT",
    "DATUM_REFERENCE_ELEMENT",
    "DATUM_TARGET",
    "PLACED_DATUM_TARGET_FEATURE",
    "DATUM_SYSTEM",
    "REFERENCE_ELEMENT",
})

# Tolerance entity names
_TOLERANCE_ENTITY_NAMES: frozenset[str] = frozenset({
    "GEOMETRIC_TOLERANCE",
    "GEOMETRIC_TOLERANCE_WITH_DATUM_REFERENCE",
    "GEOMETRIC_TOLERANCE_WITH_DEFINED_UNIT",
    "PLUS_MINUS_TOLERANCE",
    "SYMMETRY_TOLERANCE",
    "CYLINDRICITY_TOLERANCE",
    "FLATNESS_TOLERANCE",
    "PERPENDICULARITY_TOLERANCE",
    "PARALLELISM_TOLERANCE",
    "ANGULARITY_TOLERANCE",
    "CIRCULARITY_TOLERANCE",
    "STRAIGHTNESS_TOLERANCE",
    "POSITION_TOLERANCE",
    "TOTAL_RUNOUT_TOLERANCE",
    "CIRCULAR_RUNOUT_TOLERANCE",
    "SURFACE_PROFILE_TOLERANCE",
    "LINE_PROFILE_TOLERANCE",
    "CONCENTRICITY_TOLERANCE",
    "COAXIALITY_TOLERANCE",
    "TOLERANCE_VALUE",
})

# Dimensional size entity names
_DIM_ENTITY_NAMES: frozenset[str] = frozenset({
    "DIMENSIONAL_SIZE",
    "DIMENSIONAL_SIZE_WITH_PATH",
    "LINEAR_SIZE",
    "DIMENSIONAL_CHARACTERISTIC_REPRESENTATION",
    "DIMENSION_RELATED_TOLERANCE_ZONE_ELEMENT",
})

# Combined set for fast entity-type routing
_ALL_PMI_TYPES = (
    _PMI_ENTITY_NAMES
    | _DATUM_ENTITY_NAMES
    | _TOLERANCE_ENTITY_NAMES
    | _DIM_ENTITY_NAMES
)


# ─── Internal helpers ──────────────────────────────────────────────────────────

def _strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)


def _first_string(params: str) -> str | None:
    m = _STRING_RE.search(params)
    return m.group(1) if m else None


def _all_refs(params: str) -> list[int]:
    return [int(m.group(1)) for m in _REF_RE.finditer(params)]


def _first_real(params: str) -> float | None:
    # Skip entity references (e.g. #12) before scanning for floats
    stripped = _REF_RE.sub(" ", params)
    m = _REAL_RE.search(stripped)
    try:
        return float(m.group()) if m else None
    except (ValueError, AttributeError):
        return None


def _normalise_entities(text: str) -> list[tuple[int, str, str]]:
    """
    Reassemble multi-line entity instances into (id, name, params) triples.

    STEP Part 21 entities can span many lines terminated by ';'.
    Strategy: remove comments, then scan for '#NNN = NAME(' ...');\n' patterns
    by collecting characters until the statement is balanced.
    """
    text = _strip_comments(text)
    results: list[tuple[int, str, str]] = []

    # Find DATA section
    data_m = re.search(r"DATA\s*;", text, re.IGNORECASE)
    end_m = re.search(r"ENDSEC\s*;", text[data_m.end():] if data_m else text, re.IGNORECASE)

    if data_m:
        start = data_m.end()
        end = (start + end_m.start()) if end_m else len(text)
        data_section = text[start:end]
    else:
        data_section = text

    # Tokenise by ';' boundaries, being careful about strings
    # Simple approach: split by ';' when we're not inside a string literal
    statements: list[str] = []
    cur: list[str] = []
    in_string = False
    for ch in data_section:
        if ch == "'" and not in_string:
            in_string = True
            cur.append(ch)
        elif ch == "'" and in_string:
            in_string = False
            cur.append(ch)
        elif ch == ";" and not in_string:
            stmt = "".join(cur).strip()
            if stmt:
                statements.append(stmt)
            cur = []
        else:
            cur.append(ch)

    for stmt in statements:
        # Collapse whitespace/newlines
        stmt = re.sub(r"\s+", " ", stmt).strip()
        m = re.match(r"#(\d+)\s*=\s*([A-Z_][A-Z0-9_]*)\s*\((.*)\)\s*$", stmt, re.DOTALL)
        if not m:
            continue
        eid = int(m.group(1))
        ename = m.group(2).upper()
        params = m.group(3)
        results.append((eid, ename, params))

    return results


# ─── Public reader ────────────────────────────────────────────────────────────

def read_ap242_pmi(step_text: str) -> dict[str, Any]:
    """
    Parse AP242 PMI / GD&T annotations from a STEP Part 21 text string.

    Returns a structured dict with keys: ok, schema, product, annotations,
    datums, tolerances, dimensional_sizes, drawing_annotations, warnings.
    """
    warnings: list[str] = []

    # ── Header fields ──────────────────────────────────────────────────────
    schema: str | None = None
    product: str | None = None

    m_schema = re.search(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", step_text, re.IGNORECASE)
    if m_schema:
        schema = m_schema.group(1)
        if "AP242" not in schema.upper():
            warnings.append(f"FILE_SCHEMA is '{schema}' — not AP242; continuing anyway")

    m_prod = re.search(r"\bPRODUCT\s*\(\s*'([^']*)'", step_text, re.IGNORECASE)
    if m_prod:
        product = m_prod.group(1)

    # ── Parse entity instances ─────────────────────────────────────────────
    try:
        entities = _normalise_entities(step_text)
    except Exception as exc:
        return {"ok": False, "reason": f"entity parse error: {exc}"}

    annotations: list[dict] = []
    datums: list[dict] = []
    tolerances: list[dict] = []
    dimensional_sizes: list[dict] = []

    for eid, ename, params in entities:
        if ename in _PMI_ENTITY_NAMES:
            annotations.append({
                "kind": ename.lower(),
                "id": eid,
                "name": _first_string(params),
                "refs": _all_refs(params),
            })

        elif ename in _DATUM_ENTITY_NAMES:
            datums.append({
                "kind": ename.lower(),
                "id": eid,
                "label": _first_string(params),
                "refs": _all_refs(params),
            })

        elif ename in _TOLERANCE_ENTITY_NAMES:
            mag = _first_real(params)
            # Try to get magnitude from MEASURE_WITH_UNIT sub-entity if inline
            unit: str | None = None
            # Some files inline: GEOMETRIC_TOLERANCE('name', ..., (value, #unit), ...)
            # We just capture the first float as magnitude.
            tolerances.append({
                "kind": ename,
                "id": eid,
                "name": _first_string(params),
                "magnitude": mag,
                "unit": unit,
                "refs": _all_refs(params),
            })

        elif ename in _DIM_ENTITY_NAMES:
            nominal = _first_real(params)
            dimensional_sizes.append({
                "id": eid,
                "name": _first_string(params),
                "nominal": nominal,
                "upper_tol": None,
                "lower_tol": None,
                "refs": _all_refs(params),
            })

    # ── Build flat drawing_annotations list ───────────────────────────────
    drawing_annotations: list[dict] = []

    for ann in annotations:
        label = ann.get("name") or ann["kind"].replace("_", " ").title()
        drawing_annotations.append({
            "type": ann["kind"],
            "label": label,
            "id": ann["id"],
            "refs": ann["refs"],
        })

    for datum in datums:
        label = datum.get("label") or datum["kind"].replace("_", " ").title()
        drawing_annotations.append({
            "type": datum["kind"],
            "label": label,
            "id": datum["id"],
            "refs": datum["refs"],
        })

    for tol in tolerances:
        mag_str = f" ±{tol['magnitude']}" if tol["magnitude"] is not None else ""
        label = (tol.get("name") or tol["kind"].replace("_", " ").title()) + mag_str
        drawing_annotations.append({
            "type": tol["kind"].lower(),
            "label": label,
            "id": tol["id"],
            "refs": tol["refs"],
        })

    for dim in dimensional_sizes:
        nom_str = f" {dim['nominal']}" if dim["nominal"] is not None else ""
        label = (dim.get("name") or "Dimensional Size") + nom_str
        drawing_annotations.append({
            "type": "dimensional_size",
            "label": label,
            "id": dim["id"],
            "refs": dim["refs"],
        })

    return {
        "ok": True,
        "schema": schema,
        "product": product,
        "annotations": annotations,
        "datums": datums,
        "tolerances": tolerances,
        "dimensional_sizes": dimensional_sizes,
        "drawing_annotations": drawing_annotations,
        "warnings": warnings,
    }
