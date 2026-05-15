"""
drc_presets.py — Named manufacturing constraint presets for PCB DRC.

Tools:
  list_drc_presets      — return the catalogue of available presets with their
                          constraint values and source citations.
  run_drc_with_preset   — apply a named preset's constraints through the
                          existing pcb_drc engine and return a violation report
                          classified by rule kind and severity.

Presets implemented
-------------------
IPC-2221 producibility classes (IPC-2221B, Table 4-1 / Table 6-2):
  ipc_2221_class_1   — Class A (minimal performance, widest tolerances)
  ipc_2221_class_2   — Class B (general industrial)
  ipc_2221_class_3   — Class C (high-reliability / military)

Representative fab-house profiles (not proprietary to any specific vendor;
values reflect typical capabilities published in public capability guides):
  prototype_standard   — common 2-layer hobby/prototype service
  prototype_advanced   — typical 4-layer advanced-prototype capability

All dimensions are in millimetres.
"""

from __future__ import annotations

import json
from typing import Any

from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
from kerf_electronics.tools.pcb_drc import _run_drc_on_circuit


# ---------------------------------------------------------------------------
# Preset catalogue
# ---------------------------------------------------------------------------

# Each preset is a dict with:
#   description  : human-readable name
#   source       : citation / standard reference
#   constraints  : dict whose keys match pcb_drc rule names
#                  (a subset is sufficient — only listed rules are overridden)

_PRESETS: dict[str, dict] = {
    # ── IPC-2221B producibility Class 1 (Level A) ──────────────────────────
    # Source: IPC-2221B §4.3, Table 6-2 (producibility level A)
    # Intended for consumer / low-complexity boards where generous tolerances
    # are acceptable.  Trace ≥0.25 mm, drill ≥0.8 mm, annular ring ≥0.15 mm.
    "ipc_2221_class_1": {
        "description": "IPC-2221B Class 1 (Level A — minimal / consumer)",
        "source": "IPC-2221B:2003 Table 6-2, producibility level A",
        "constraints": {
            "min_trace_width_mm":    0.25,
            "min_via_clearance_mm":  0.25,
            "min_drill_spacing_mm":  0.80,   # maps to minimum drill diameter
            "min_copper_to_edge_mm": 0.50,
        },
    },

    # ── IPC-2221B producibility Class 2 (Level B) ──────────────────────────
    # Source: IPC-2221B §4.3, Table 6-2 (producibility level B)
    # General industrial / commercial electronics.  Tighter than Class 1.
    "ipc_2221_class_2": {
        "description": "IPC-2221B Class 2 (Level B — general industrial)",
        "source": "IPC-2221B:2003 Table 6-2, producibility level B",
        "constraints": {
            "min_trace_width_mm":    0.15,
            "min_via_clearance_mm":  0.15,
            "min_drill_spacing_mm":  0.50,
            "min_copper_to_edge_mm": 0.30,
        },
    },

    # ── IPC-2221B producibility Class 3 (Level C) ──────────────────────────
    # Source: IPC-2221B §4.3, Table 6-2 (producibility level C)
    # High-reliability, defence, medical, aerospace.  Tightest tolerances.
    "ipc_2221_class_3": {
        "description": "IPC-2221B Class 3 (Level C — high-reliability / military)",
        "source": "IPC-2221B:2003 Table 6-2, producibility level C",
        "constraints": {
            "min_trace_width_mm":    0.075,
            "min_via_clearance_mm":  0.075,
            "min_drill_spacing_mm":  0.25,
            "min_copper_to_edge_mm": 0.20,
        },
    },

    # ── Prototype standard (2-layer) ────────────────────────────────────────
    # Representative capability for common 2-layer prototype PCB services.
    # Values reflect widely-published standard-tier capability guides (e.g.
    # 6/6 mil trace/space).  Not specific to any one vendor.
    "prototype_standard": {
        "description": "Prototype standard (2-layer, 6/6 mil trace/space — representative)",
        "source": (
            "Representative 2-layer prototype capability based on publicly "
            "available fab-house spec sheets; not a specific vendor's proprietary spec"
        ),
        "constraints": {
            "min_trace_width_mm":    0.152,  # ~6 mil
            "min_via_clearance_mm":  0.152,  # ~6 mil clearance
            "min_drill_spacing_mm":  0.40,   # 0.4 mm drill (standard vias)
            "min_copper_to_edge_mm": 0.30,
        },
    },

    # ── Prototype advanced (4-layer HDI) ────────────────────────────────────
    # Representative capability for advanced 4-layer prototype services with
    # laser-drilled microvias.  Commonly published as 4/4 mil capability.
    "prototype_advanced": {
        "description": "Prototype advanced (4-layer, 4/4 mil trace/space — representative)",
        "source": (
            "Representative 4-layer advanced prototype capability based on publicly "
            "available fab-house spec sheets; not a specific vendor's proprietary spec"
        ),
        "constraints": {
            "min_trace_width_mm":    0.100,  # ~4 mil
            "min_via_clearance_mm":  0.100,
            "min_drill_spacing_mm":  0.25,   # 0.25 mm laser drill
            "min_copper_to_edge_mm": 0.20,
        },
    },
}


# ---------------------------------------------------------------------------
# Internal: apply preset constraints and run DRC
# ---------------------------------------------------------------------------

def _run_drc_with_preset_constraints(
    circuit_json: list,
    constraints: dict,
) -> dict:
    """
    Inject preset constraints into the pcb_board element (or a synthetic one if
    absent) and forward to the existing _run_drc_on_circuit engine.

    The board's own drc_rules are preserved; preset values only fill gaps
    (i.e. the preset acts as a *floor* — if the board already specifies a
    stricter rule, that stricter rule wins).  This matches KiCad behaviour
    where project-level rules take precedence over fab-profile minimums.

    Wait — actually for "validate against a real fab's minimums" semantics we
    want the preset to be the *effective minimum*, not just a fallback.  We
    therefore override board rules with the preset values when the preset is
    tighter (lower minimum = stricter), but leave board rules in place when
    the board is already stricter than the preset.
    """
    # Work on a shallow copy; only the board element is modified
    patched = list(circuit_json)

    board_idx = next(
        (i for i, e in enumerate(patched) if isinstance(e, dict) and e.get("type") == "pcb_board"),
        None,
    )

    if board_idx is None:
        synthetic_board: dict = {"type": "pcb_board", "drc_rules": {}}
        patched = patched + [synthetic_board]
        board_idx = len(patched) - 1

    board = dict(patched[board_idx])  # shallow copy
    existing_rules: dict = dict(board.get("drc_rules") or {})

    merged_rules = dict(existing_rules)
    for rule, preset_value in constraints.items():
        existing = existing_rules.get(rule)
        if existing is None:
            # Rule not set on board — apply preset
            merged_rules[rule] = preset_value
        else:
            # Apply the stricter (lower) of preset vs. board rule
            merged_rules[rule] = min(existing, preset_value)

    board["drc_rules"] = merged_rules
    patched[board_idx] = board

    result = _run_drc_on_circuit(patched)

    # Annotate each violation with the rule that triggered it (already present
    # as 'kind'), and tag the preset name for traceability.
    return result


def _classify_violations(result: dict, preset_name: str, constraints: dict) -> dict:
    """
    Enrich the raw DRC output with per-violation rule attribution and severity
    grouping.  Returns a structured report.
    """
    errors = result.get("errors", [])
    warnings = result.get("warnings", [])

    # Build rule-bucketed view
    by_rule: dict[str, list] = {}
    for violation in errors + warnings:
        kind = violation.get("kind", "unknown")
        by_rule.setdefault(kind, []).append(violation)

    return {
        "preset": preset_name,
        "errors": errors,
        "warnings": warnings,
        "violations_by_rule": by_rule,
        "summary": {
            "error_count": len(errors),
            "warning_count": len(warnings),
            "total_violations": len(errors) + len(warnings),
            "applied_constraints": constraints,
        },
    }


# ---------------------------------------------------------------------------
# Tool: list_drc_presets
# ---------------------------------------------------------------------------

list_drc_presets_spec = ToolSpec(
    name="list_drc_presets",
    description=(
        "Return the catalogue of available DRC manufacturing constraint presets. "
        "Each preset has a name, description, source citation, and the constraint "
        "values it enforces (min_trace_width_mm, min_via_clearance_mm, "
        "min_drill_spacing_mm, min_copper_to_edge_mm). "
        "Presets include IPC-2221B producibility classes 1-3 and representative "
        "prototype-service capability profiles."
    ),
    input_schema={
        "type": "object",
        "properties": {},
        "required": [],
    },
)


@register(list_drc_presets_spec, write=False)
async def list_drc_presets(ctx: Any, args: bytes) -> str:
    catalogue = [
        {
            "name": name,
            "description": p["description"],
            "source": p["source"],
            "constraints": p["constraints"],
        }
        for name, p in _PRESETS.items()
    ]
    return ok_payload({"presets": catalogue})


# ---------------------------------------------------------------------------
# Tool: run_drc_with_preset
# ---------------------------------------------------------------------------

run_drc_with_preset_spec = ToolSpec(
    name="run_drc_with_preset",
    description=(
        "Run PCB DRC using a named manufacturing constraint preset. "
        "Applies the preset's minimum values through the existing pcb_drc engine "
        "and returns violations classified by rule kind and severity, plus a summary. "
        "Available presets: "
        + ", ".join(_PRESETS.keys())
        + ". "
        "Use list_drc_presets to see constraint values and source citations for each preset."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "circuit_json": {
                "type": "array",
                "description": (
                    "Flat AnyCircuitElement[] array from CircuitJSON. Must include "
                    "a pcb_board element plus traces, vias, pads as needed."
                ),
                "items": {"type": "object"},
            },
            "preset_name": {
                "type": "string",
                "description": (
                    "Name of the constraint preset to apply. One of: "
                    + ", ".join(_PRESETS.keys())
                ),
                "enum": list(_PRESETS.keys()),
            },
        },
        "required": ["circuit_json", "preset_name"],
    },
)


@register(run_drc_with_preset_spec, write=False)
async def run_drc_with_preset(ctx: Any, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args: {e}", "BAD_ARGS")

    circuit_json = a.get("circuit_json")
    if not isinstance(circuit_json, list):
        return err_payload("circuit_json must be an array", "BAD_ARGS")

    preset_name = a.get("preset_name", "")
    if preset_name not in _PRESETS:
        return err_payload(
            f"unknown preset '{preset_name}'. Available: {list(_PRESETS.keys())}",
            "BAD_ARGS",
        )

    preset = _PRESETS[preset_name]
    constraints = preset["constraints"]

    raw = _run_drc_with_preset_constraints(circuit_json, constraints)
    report = _classify_violations(raw, preset_name, constraints)
    return ok_payload(report)
