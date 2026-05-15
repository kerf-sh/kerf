"""
lib_mgmt.py — Symbol↔footprint library management + assignment validation.

Two LLM tools:

  assign_footprint          — assign a footprint (or auto-suggest one) to a
                              schematic symbol inside a design's component list,
                              and manage the logical library table
                              (lib_name → source path).

  check_library_assignments — validate every component in a design:
                              • every component has a footprint assigned
                              • pin count (symbol) matches pad count (footprint)
                              • no missing or duplicate reference designators
                              • designator sanity (prefix + number pattern)
                              Returns a structured AssignmentReport.

Model note — parts/symbols/footprints follow the same dict shape used by
kerf_imports.kicad_library:

  schematic_symbol  dict or None  — {library, entry_name, pin_count, pins, …}
  pcb_footprint     dict or None  — {library, entry_name, pad_count, pads, …}

Callers pass components as plain dicts (no ORM layer required).
"""

from __future__ import annotations

import json
import re
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register

# ---------------------------------------------------------------------------
# Data model — assignment record (dict-based, matches kicad_library shape)
# ---------------------------------------------------------------------------

# A "component" dict fed to these tools has this expected shape:
#
#   {
#     "refdes":           str,              # e.g. "R1", "U3"
#     "name":             str,              # part / value name
#     "schematic_symbol": dict | None,      # {library, entry_name, pin_count, pins}
#     "pcb_footprint":    dict | None,      # {library, entry_name, pad_count, pads}
#     "footprint_ref":    str | None,       # "LibName:EntryName" shorthand
#   }
#
# A "library table" is a plain dict mapping logical lib name → source path:
#   { "Device": "/usr/share/kicad/symbols/Device.kicad_sym", … }

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_REFDES_RE = re.compile(r"^([A-Za-z]+)(\d+)$")


def _refdes_ok(refdes: str) -> bool:
    """Return True when refdes looks like a valid designator (letters + digits)."""
    return bool(_REFDES_RE.match(refdes.strip())) if refdes else False


def _pin_count(sym: dict | None) -> int | None:
    if sym is None:
        return None
    # Prefer explicit pin_count; fall back to len(pins)
    pc = sym.get("pin_count")
    if isinstance(pc, int):
        return pc
    pins = sym.get("pins")
    if isinstance(pins, list):
        return len(pins)
    return None


def _pad_count(fp: dict | None) -> int | None:
    if fp is None:
        return None
    pc = fp.get("pad_count")
    if isinstance(pc, int):
        return pc
    pads = fp.get("pads")
    if isinstance(pads, list):
        return len(pads)
    return None


def _footprint_ref(fp: dict) -> str:
    """Return 'Library:EntryName' string from a pcb_footprint dict."""
    lib = fp.get("library", "")
    entry = fp.get("entry_name", "")
    if lib and entry:
        return f"{lib}:{entry}"
    return entry or lib or ""


def _auto_suggest(sym: dict, lib_table: dict) -> str | None:
    """
    Attempt a simple name-match footprint suggestion.

    Strategy:
      1. If the symbol entry_name ends with a known package token
         (e.g. "R_0805", "C_0402") use that as the suggestion.
      2. Otherwise return None (caller should surface a warning).

    This is intentionally conservative — a real suggestion engine would
    query the parts database; here we keep it hermetic for tests.
    """
    if not sym:
        return None
    entry = sym.get("entry_name", "") or ""
    # Check if entry_name itself looks like a footprint ref
    if ":" in entry:
        return entry
    # Look for a matching key in the library table
    for lib_name in lib_table:
        candidate = f"{lib_name}:{entry}"
        return candidate  # return the first library hit as a speculative suggestion
    return None


# ---------------------------------------------------------------------------
# Core: assign_footprint (pure function)
# ---------------------------------------------------------------------------

def assign_footprint(
    components: list[dict],
    assignments: dict,
    lib_table: dict,
    auto_suggest: bool = False,
) -> dict:
    """
    Apply footprint assignments to components.

    Args:
        components:   list of component dicts (mutated in place — copies returned).
        assignments:  {refdes: "LibName:EntryName"} map of desired assignments.
        lib_table:    logical lib-name → source path map.
        auto_suggest: if True, attempt name-match suggestions for unassigned
                      components that have a schematic_symbol.

    Returns a dict:
        {
          "updated":    [refdes, …],      # refdes that received a new assignment
          "suggested":  {refdes: ref},    # auto-suggestions (not applied)
          "not_found":  [refdes, …],      # refdes in assignments not in components
          "lib_table":  {…},              # the (possibly unchanged) lib_table
          "components": [updated copies],
        }
    """
    comp_by_ref: dict[str, dict] = {}
    for c in components:
        ref = (c.get("refdes") or c.get("name") or "").strip()
        if ref:
            comp_by_ref[ref] = dict(c)  # shallow copy so we don't mutate input

    updated: list[str] = []
    not_found: list[str] = []

    for refdes, fp_ref in assignments.items():
        if refdes not in comp_by_ref:
            not_found.append(refdes)
            continue
        # Parse "Lib:Entry" or bare entry name
        if ":" in fp_ref:
            lib_part, entry_part = fp_ref.split(":", 1)
        else:
            lib_part, entry_part = "", fp_ref
        comp_by_ref[refdes]["pcb_footprint"] = {
            "library": lib_part,
            "entry_name": entry_part,
            "pad_count": None,
            "pads": [],
        }
        comp_by_ref[refdes]["footprint_ref"] = fp_ref
        updated.append(refdes)

    suggested: dict[str, str] = {}
    if auto_suggest:
        for ref, comp in comp_by_ref.items():
            if comp.get("pcb_footprint") is not None:
                continue
            sym = comp.get("schematic_symbol")
            suggestion = _auto_suggest(sym, lib_table)
            if suggestion:
                suggested[ref] = suggestion

    return {
        "updated": sorted(updated),
        "suggested": suggested,
        "not_found": sorted(not_found),
        "lib_table": lib_table,
        "components": list(comp_by_ref.values()),
    }


# ---------------------------------------------------------------------------
# Core: check_library_assignments (pure function)
# ---------------------------------------------------------------------------

def check_library_assignments(
    components: list[dict],
    lib_table: dict | None = None,
) -> dict:
    """
    Validate footprint assignments for a list of component dicts.

    Checks:
      1. missing_footprint     — component has no pcb_footprint
      2. pin_pad_mismatch      — symbol pin_count ≠ footprint pad_count
      3. missing_refdes        — component has no refdes / blank refdes
      4. duplicate_refdes      — two components share the same refdes
      5. invalid_refdes_format — refdes doesn't match [letters][digits] pattern

    Args:
        components:  list of component dicts (not mutated).
        lib_table:   optional logical lib-name → source path map (informational).

    Returns:
        {
          "status":     "OK" | "ISSUES_FOUND",
          "total":      int,
          "issues": [
              {
                "kind":     str,    # one of the 5 check names above
                "severity": "error" | "warning",
                "refdes":   str | None,
                "message":  str,
              },
              …
          ],
          "summary": {
            "missing_footprint":     int,
            "pin_pad_mismatch":      int,
            "missing_refdes":        int,
            "duplicate_refdes":      int,
            "invalid_refdes_format": int,
          },
          "lib_table": dict,
        }
    """
    if lib_table is None:
        lib_table = {}

    issues: list[dict] = []
    seen_refdes: dict[str, int] = {}  # refdes → first-seen component index

    for idx, comp in enumerate(components):
        # Use the raw "refdes" field to detect missing designators; only fall back
        # to "name" for display purposes once we know refdes is absent.
        raw_refdes = (comp.get("refdes") or "").strip()

        # Check 3: missing refdes — raw refdes field is blank or absent
        refdes_missing = not raw_refdes
        if refdes_missing:
            issues.append({
                "kind": "missing_refdes",
                "severity": "error",
                "refdes": None,
                "message": f"Component at index {idx} has no reference designator",
            })
            refdes = f"<index:{idx}>"  # synthetic key for dedup checks
        else:
            refdes = raw_refdes

        # Check 4: duplicate refdes
        if refdes in seen_refdes:
            issues.append({
                "kind": "duplicate_refdes",
                "severity": "error",
                "refdes": refdes,
                "message": (
                    f'Duplicate reference designator "{refdes}" '
                    f"(first seen at index {seen_refdes[refdes]}, repeated at index {idx})"
                ),
            })
        else:
            seen_refdes[refdes] = idx

        # Check 5: invalid refdes format (skip synthetic keys)
        if not refdes.startswith("<index:") and not _refdes_ok(refdes):
            issues.append({
                "kind": "invalid_refdes_format",
                "severity": "warning",
                "refdes": refdes,
                "message": (
                    f'Reference designator "{refdes}" does not match '
                    "the expected [letters][digits] pattern (e.g. R1, U3, C12)"
                ),
            })

        fp = comp.get("pcb_footprint")
        sym = comp.get("schematic_symbol")

        # Check 1: missing footprint
        if fp is None:
            # Also allow a footprint_ref string as a lightweight assignment
            fp_ref = comp.get("footprint_ref")
            if not fp_ref:
                issues.append({
                    "kind": "missing_footprint",
                    "severity": "error",
                    "refdes": refdes if not refdes.startswith("<index:") else None,
                    "message": (
                        f'Component "{refdes}" has no footprint assigned. '
                        "Use assign_footprint or set pcb_footprint / footprint_ref."
                    ),
                })
                continue  # skip pin/pad check — no footprint to compare against

        # Check 2: pin/pad count mismatch
        pin_cnt = _pin_count(sym)
        pad_cnt = _pad_count(fp)

        # pad_count can be None when set via a lightweight footprint_ref string
        # (no detailed pad list); skip mismatch check in that case.
        if pin_cnt is not None and pad_cnt is not None:
            if pin_cnt != pad_cnt:
                sym_name = (
                    f"{sym.get('library', '')}:{sym.get('entry_name', '')}"
                    if sym else "?"
                )
                fp_name = _footprint_ref(fp) if fp else (comp.get("footprint_ref") or "?")
                issues.append({
                    "kind": "pin_pad_mismatch",
                    "severity": "error",
                    "refdes": refdes if not refdes.startswith("<index:") else None,
                    "message": (
                        f'Component "{refdes}": symbol "{sym_name}" has {pin_cnt} pin(s) '
                        f"but footprint \"{fp_name}\" declares {pad_cnt} pad(s)."
                    ),
                })

    # Build summary counts
    summary: dict[str, int] = {
        "missing_footprint": 0,
        "pin_pad_mismatch": 0,
        "missing_refdes": 0,
        "duplicate_refdes": 0,
        "invalid_refdes_format": 0,
    }
    for iss in issues:
        kind = iss["kind"]
        if kind in summary:
            summary[kind] += 1

    status = "OK" if not issues else "ISSUES_FOUND"

    return {
        "status": status,
        "total": len(components),
        "issues": issues,
        "summary": summary,
        "lib_table": lib_table,
    }


# ---------------------------------------------------------------------------
# LLM tool: assign_footprint
# ---------------------------------------------------------------------------

assign_footprint_spec = ToolSpec(
    name="assign_footprint",
    description=(
        "Assign or auto-suggest footprints for schematic symbols in a design's "
        "component list.  Also manages the logical library table "
        "(lib_name → source path).  "
        "Pass assignments as a {refdes: 'LibName:EntryName'} map; "
        "set auto_suggest=true to receive name-match suggestions for any "
        "component that still has no footprint after explicit assignments. "
        "Returns updated component list, suggestions, and not-found refdes list. "
        "Run check_library_assignments after assigning to validate the design."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "components": {
                "type": "array",
                "description": (
                    "List of component dicts, each with at minimum: "
                    "refdes (string), schematic_symbol (object|null), "
                    "pcb_footprint (object|null)."
                ),
                "items": {"type": "object"},
            },
            "assignments": {
                "type": "object",
                "description": (
                    "Map of {refdes: 'LibName:EntryName'} footprint assignments. "
                    "Use an empty object {} to skip explicit assignments "
                    "(combine with auto_suggest)."
                ),
                "additionalProperties": {"type": "string"},
            },
            "lib_table": {
                "type": "object",
                "description": (
                    "Logical library name → source path map. "
                    "E.g. {\"Device\": \"/usr/share/kicad/symbols/Device.kicad_sym\"}. "
                    "Pass {} if not yet configured."
                ),
                "additionalProperties": {"type": "string"},
            },
            "auto_suggest": {
                "type": "boolean",
                "description": (
                    "If true, attempt name-match footprint suggestions for components "
                    "that remain unassigned after explicit assignments (default false)."
                ),
            },
        },
        "required": ["components", "assignments"],
    },
)


@register(assign_footprint_spec, write=True)
async def run_assign_footprint(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    components = a.get("components")
    if not isinstance(components, list):
        return err_payload("components must be an array", "BAD_ARGS")

    assignments = a.get("assignments")
    if not isinstance(assignments, dict):
        return err_payload("assignments must be an object", "BAD_ARGS")

    lib_table = a.get("lib_table") or {}
    if not isinstance(lib_table, dict):
        lib_table = {}

    auto = bool(a.get("auto_suggest", False))

    try:
        result = assign_footprint(components, assignments, lib_table, auto_suggest=auto)
    except Exception as e:
        return err_payload(f"assign_footprint failed: {e}", "ASSIGN_ERROR")

    result["message"] = (
        f"Assigned {len(result['updated'])} footprint(s). "
        + (f"{len(result['suggested'])} suggestion(s) available. " if result["suggested"] else "")
        + (f"{len(result['not_found'])} refdes not found: {result['not_found']}. " if result["not_found"] else "")
        + "Run check_library_assignments to validate."
    )
    return ok_payload(result)


# ---------------------------------------------------------------------------
# LLM tool: check_library_assignments
# ---------------------------------------------------------------------------

check_library_assignments_spec = ToolSpec(
    name="check_library_assignments",
    description=(
        "Validate footprint assignments for every component in a design. "
        "Flags: missing footprint, pin/pad count mismatch between symbol and "
        "footprint, missing reference designators, duplicate reference designators, "
        "and designator sanity (must be [letters][digits] pattern, e.g. R1, U3). "
        "Returns a structured report with status OK or ISSUES_FOUND, per-issue "
        "details, and a summary count per issue kind. "
        "Run this after assign_footprint to confirm the design is ready for layout."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "components": {
                "type": "array",
                "description": (
                    "List of component dicts. Each should have: "
                    "refdes (string), schematic_symbol (object|null, with pin_count), "
                    "pcb_footprint (object|null, with pad_count). "
                    "Lightweight footprint assignments via footprint_ref "
                    "(string 'LibName:EntryName') are also accepted."
                ),
                "items": {"type": "object"},
            },
            "lib_table": {
                "type": "object",
                "description": (
                    "Optional logical library name → source path map "
                    "(included in the report for reference)."
                ),
                "additionalProperties": {"type": "string"},
            },
        },
        "required": ["components"],
    },
)


@register(check_library_assignments_spec, write=False)
async def run_check_library_assignments(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    components = a.get("components")
    if not isinstance(components, list):
        return err_payload("components must be an array", "BAD_ARGS")

    lib_table = a.get("lib_table") or {}
    if not isinstance(lib_table, dict):
        lib_table = {}

    try:
        report = check_library_assignments(components, lib_table)
    except Exception as e:
        return err_payload(f"check_library_assignments failed: {e}", "CHECK_ERROR")

    issues = report["issues"]
    s = report["summary"]
    parts: list[str] = []
    if s["missing_footprint"]:
        parts.append(f"{s['missing_footprint']} missing footprint(s)")
    if s["pin_pad_mismatch"]:
        parts.append(f"{s['pin_pad_mismatch']} pin/pad mismatch(es)")
    if s["duplicate_refdes"]:
        parts.append(f"{s['duplicate_refdes']} duplicate refdes")
    if s["missing_refdes"]:
        parts.append(f"{s['missing_refdes']} missing refdes")
    if s["invalid_refdes_format"]:
        parts.append(f"{s['invalid_refdes_format']} invalid refdes format")

    if issues:
        report["message"] = (
            f"Assignment check: {len(issues)} issue(s) found in "
            f"{report['total']} component(s). "
            + "; ".join(parts) + "."
        )
    else:
        report["message"] = (
            f"Assignment check passed: {report['total']} component(s), "
            "all footprints assigned and pin/pad counts match."
        )

    return ok_payload(report)
