"""
IEC 61131-3 PLC routes.

POST /lint-plc
  Body:   { "source": "<ST source string>" }
  Returns: {
      "diagnostics": [{"severity","message","line","column","source"}, ...],
      "warnings":    ["..."]
  }

POST /lint-ld
  Body:   { "program": { <LadderProgram JSON> } }
  Returns: {
      "diagnostics": [...],
      "warnings":    [...]
  }

POST /export-ld
  Body:   { "program": { <LadderProgram JSON> } }
  Returns: { "xml": "<IEC 61131-3 XML string>" }

Errors are never propagated as 5xx — routes always return 200 with
diagnostics so the editor can surface them cleanly.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()


@router.post("/lint-plc")
async def lint_plc_route(req: dict) -> dict:
    """Lint IEC 61131-3 Structured Text source via MATIEC."""
    source = req.get("source", "")
    if not isinstance(source, str):
        return {
            "diagnostics": [],
            "warnings": ["'source' must be a string"],
        }

    from kerf_plc.matiec_lint import Diagnostic, lint_st_source

    raw: list[Diagnostic] = lint_st_source(source)

    # Split into errors/warnings (diagnostics for Monaco) vs top-level
    # informational warnings (e.g. "MATIEC not installed").
    diagnostics = []
    warnings = []

    for d in raw:
        entry = {
            "severity": d.severity,
            "message": d.message,
            "line": d.line,
            "column": d.column,
            "source": d.source,
        }
        if d.line is None and d.severity == "warning":
            warnings.append(d.message)
        else:
            diagnostics.append(entry)

    return {"diagnostics": diagnostics, "warnings": warnings}


@router.post("/lint-ld")
async def lint_ld_route(req: dict) -> dict:
    """
    Lint an IEC 61131-3 Ladder Diagram program (structural + MATIEC via LD→ST).

    Body: { "program": { <LadderProgram JSON> } }
    Returns: { "diagnostics": [...], "warnings": [...] }
    """
    program_data = req.get("program")
    if not isinstance(program_data, dict):
        return {
            "diagnostics": [],
            "warnings": ["'program' must be a JSON object matching the .plc.ld schema"],
        }

    diagnostics = []
    warnings = []

    try:
        from kerf_plc.ld.schema import load
        from kerf_plc.ld.lint import lint_ld
        prog = load(program_data)
        raw = lint_ld(prog)
        for d in raw:
            entry = {
                "severity": d.severity,
                "message": d.message,
                "line": d.line,
                "column": d.column,
                "source": d.source,
            }
            if d.line is None and d.severity == "warning":
                warnings.append(d.message)
            else:
                diagnostics.append(entry)
    except ValueError as e:
        # Schema validation errors from load()
        for line in str(e).splitlines():
            msg = line.lstrip("•").strip()
            if msg and "LD program validation errors" not in msg:
                diagnostics.append({
                    "severity": "error",
                    "message": msg,
                    "line": None,
                    "column": None,
                    "source": "ld-schema",
                })
    except Exception as e:
        warnings.append(f"LD lint failed: {e}")

    return {"diagnostics": diagnostics, "warnings": warnings}


@router.post("/export-ld")
async def export_ld_route(req: dict) -> dict:
    """
    Export a Ladder Diagram program to IEC 61131-3 XML (PLCopen TC6).

    Body: { "program": { <LadderProgram JSON> } }
    Returns: { "xml": "<XML string>" }
    """
    program_data = req.get("program")
    if not isinstance(program_data, dict):
        return {"xml": "", "error": "'program' must be a JSON object"}

    try:
        from kerf_plc.ld.schema import load
        from kerf_plc.ld.export import export_xml
        prog = load(program_data)
        xml = export_xml(prog)
        return {"xml": xml}
    except ValueError as e:
        return {"xml": "", "error": str(e)}
    except Exception as e:
        return {"xml": "", "error": f"export failed: {e}"}
