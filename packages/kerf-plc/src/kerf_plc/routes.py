"""
IEC 61131-3 Structured Text lint route.

POST /lint-plc
Body:   { "source": "<ST source string>" }
Returns: {
    "diagnostics": [{"severity","message","line","column","source"}, ...],
    "warnings":    ["..."]          # high-level warnings (e.g. MATIEC absent)
}

Errors are never propagated as 5xx — the route always returns 200 with
diagnostics so the Monaco editor can surface them cleanly.
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
            # Top-level advisory (e.g. tool not installed) → warnings bucket
            warnings.append(d.message)
        else:
            diagnostics.append(entry)

    return {"diagnostics": diagnostics, "warnings": warnings}
