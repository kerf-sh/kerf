"""
LLM tool: create_ladder_rung

Create or append a new rung to a `.plc.ld` Ladder Diagram program.

The tool accepts a text description of the desired rung logic and a JSON
`rung` object, merges it into the existing (or new) ladder program JSON,
and returns the updated program JSON + an SVG preview string.

Schema:
  {
    "program": "<JSON string or object — the full .plc.ld program>",
    "rung": {
      "label":   "<optional rung label>",
      "comment": "<optional comment>",
      "branches": [
        [
          {"type": "contact_no",  "var": "start_pb"},
          {"type": "contact_nc",  "var": "stop_pb"}
        ]
      ],
      "output": {"type": "coil", "var": "motor_run"}
    }
  }

Returns:
  ok_payload({
    "program": { <updated LadderProgram as dict> },
    "svg":     "<SVG string preview>",
    "errors":  [<structural lint errors>],
    "warnings":[<lint warnings>]
  })
"""
from __future__ import annotations

import json

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register
    from kerf_core.utils.context import ProjectCtx
except ImportError:
    from kerf_plc._compat import ToolSpec, err_payload, ok_payload, register, ProjectCtx  # type: ignore


create_ladder_rung_spec = ToolSpec(
    name="create_ladder_rung",
    description=(
        "Create a new rung in an IEC 61131-3 Ladder Diagram (.plc.ld) program. "
        "Provide the current program JSON (or an empty dict for a new program) "
        "and a rung object describing the contacts, branches, and output coil or "
        "function block. The tool validates the rung structurally, appends it to "
        "the program, and returns the updated program JSON plus an SVG preview. "
        "See llm_docs/ladder.md for the schema, element types, and examples."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "program": {
                "description": (
                    "The current .plc.ld program as a JSON object or JSON string. "
                    "Pass an empty object {} to start a new program. "
                    "Must have at minimum a 'program' key with the POU name."
                ),
                "oneOf": [
                    {"type": "object"},
                    {"type": "string"},
                ],
            },
            "rung": {
                "type": "object",
                "description": (
                    "The rung to append. Must have at least one branch (list of "
                    "contact elements) and an output (coil or fb_call). "
                    "See ladder.md for element type names."
                ),
                "properties": {
                    "label":   {"type": "string"},
                    "comment": {"type": "string"},
                    "branches": {
                        "type": "array",
                        "items": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "type": {"type": "string"},
                                    "var":  {"type": "string"},
                                },
                                "required": ["type", "var"],
                            },
                        },
                    },
                    "output": {
                        "type": "object",
                        "properties": {
                            "type":        {"type": "string"},
                            "var":         {"type": "string"},
                            "fb_type":     {"type": "string"},
                            "fb_instance": {"type": "string"},
                            "fb_inputs":   {"type": "object"},
                        },
                        "required": ["type"],
                    },
                },
                "required": ["branches", "output"],
            },
        },
        "required": ["program", "rung"],
    },
)


@register(create_ladder_rung_spec)
async def create_ladder_rung(ctx: ProjectCtx, args: bytes) -> str:
    try:
        a = json.loads(args)
    except Exception as e:
        return err_payload(f"invalid args JSON: {e}", "BAD_ARGS")

    # Parse program argument (string or object)
    raw_prog = a.get("program", {})
    if isinstance(raw_prog, str):
        try:
            prog_dict = json.loads(raw_prog)
        except Exception as e:
            return err_payload(f"'program' is not valid JSON: {e}", "BAD_ARGS")
    elif isinstance(raw_prog, dict):
        prog_dict = raw_prog
    else:
        return err_payload("'program' must be an object or JSON string", "BAD_ARGS")

    raw_rung = a.get("rung")
    if not isinstance(raw_rung, dict):
        return err_payload("'rung' must be an object", "BAD_ARGS")

    # Ensure the program dict has the minimum keys
    if "program" not in prog_dict:
        prog_dict["program"] = "Main"
    if "variables" not in prog_dict:
        prog_dict["variables"] = []
    if "rungs" not in prog_dict:
        prog_dict["rungs"] = []

    # Append the new rung
    prog_dict["rungs"].append(raw_rung)

    # Validate via schema
    from kerf_plc.ld.schema import load, dump
    from kerf_plc.ld.lint import lint_ld
    from kerf_plc.ld.renderer import render_svg

    errors: list[str] = []
    warnings: list[str] = []
    svg = ""

    try:
        prog = load(prog_dict)
    except ValueError as e:
        # Validation errors — return them but still give back the dict
        errors = str(e).splitlines()
        # Strip the header line
        errors = [l.lstrip("•").strip() for l in errors if l.strip() and l.strip() != "LD program validation errors:"]
        return ok_payload({
            "program": prog_dict,
            "svg": "",
            "errors": errors,
            "warnings": [],
        })

    # Lint
    from kerf_plc.matiec_lint import Diagnostic
    diags = lint_ld(prog)
    for d in diags:
        if d.severity == "error":
            errors.append(d.message)
        else:
            warnings.append(d.message)

    # Render SVG preview
    try:
        svg = render_svg(prog)
    except Exception as exc:
        warnings.append(f"SVG render failed: {exc}")

    return ok_payload({
        "program": dump(prog),
        "svg": svg,
        "errors": errors,
        "warnings": warnings,
    })
