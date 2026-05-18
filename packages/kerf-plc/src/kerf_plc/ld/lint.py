"""
kerf_plc.ld.lint — IEC 61131-3 Ladder Diagram lint.

Two-phase approach:
  1. Schema validation — check the LD data model for structural errors
     (missing variables, unknown element types, coils inside branches, …).
     This is always available; no external tool required.

  2. MATIEC lint — compile the LD via LD→ST transpilation then pass the
     generated ST to the existing `matiec_lint.lint_st_source` pipeline.
     Gracefully skipped when MATIEC is absent (same pattern as ST lint).

Public API:
  lint_ld(prog: LadderProgram) -> list[Diagnostic]

A Diagnostic here is the same NamedTuple as in `kerf_plc.matiec_lint`.
"""
from __future__ import annotations

from kerf_plc.matiec_lint import Diagnostic, lint_st_source
from kerf_plc.ld.schema import (
    COIL_TYPES,
    CONTACT_TYPES,
    FB_TYPE,
    Element,
    LadderProgram,
    Rung,
)


# ---------------------------------------------------------------------------
# Phase 1 — schema-level structural checks
# ---------------------------------------------------------------------------

def _structural_lint(prog: LadderProgram) -> list[Diagnostic]:
    """
    Validate a LadderProgram structurally without running external tools.

    Returns a list of Diagnostic objects (severity='error' or 'warning').
    """
    diags: list[Diagnostic] = []
    declared_vars = {v.name for v in prog.variables}

    def _check_var_declared(name: str, location: str) -> None:
        if declared_vars and name and name not in declared_vars:
            diags.append(Diagnostic(
                severity="warning",
                message=f"{location}: variable '{name}' not declared in program header",
                source="ld-lint",
            ))

    for ri, rung in enumerate(prog.rungs):
        loc = f"rung {ri}" + (f" ({rung.label!r})" if rung.label else "")

        if not rung.branches:
            diags.append(Diagnostic(
                severity="error",
                message=f"{loc}: rung has no contact branches",
                source="ld-lint",
            ))
            continue

        for bi, branch in enumerate(rung.branches):
            if not branch:
                diags.append(Diagnostic(
                    severity="error",
                    message=f"{loc} branch {bi}: empty branch",
                    source="ld-lint",
                ))
                continue
            for elem in branch:
                if elem.type not in CONTACT_TYPES:
                    diags.append(Diagnostic(
                        severity="error",
                        message=(
                            f"{loc} branch {bi}: element type '{elem.type}' is not a contact — "
                            "only contacts may appear inside a branch; coils/FBs must be the rung output"
                        ),
                        source="ld-lint",
                    ))
                if elem.var:
                    _check_var_declared(elem.var, f"{loc} branch {bi}")

        if rung.output is None:
            diags.append(Diagnostic(
                severity="warning",
                message=f"{loc}: rung has no output element (coil/FB)",
                source="ld-lint",
            ))
        else:
            out = rung.output
            if out.type not in COIL_TYPES and out.type != FB_TYPE:
                diags.append(Diagnostic(
                    severity="error",
                    message=(
                        f"{loc}: output element type '{out.type}' is not a coil or FB — "
                        "rung output must be a coil or function block call"
                    ),
                    source="ld-lint",
                ))
            if out.type in COIL_TYPES and out.var:
                _check_var_declared(out.var, f"{loc} output")
            if out.type == FB_TYPE:
                if not out.fb_type:
                    diags.append(Diagnostic(
                        severity="error",
                        message=f"{loc}: fb_call output missing 'fb_type'",
                        source="ld-lint",
                    ))
                if not out.fb_instance:
                    diags.append(Diagnostic(
                        severity="error",
                        message=f"{loc}: fb_call output missing 'fb_instance'",
                        source="ld-lint",
                    ))

    return diags


# ---------------------------------------------------------------------------
# Phase 2 — LD → ST transpilation
# ---------------------------------------------------------------------------

_DIR_MAP = {
    "input": "VAR_INPUT",
    "output": "VAR_OUTPUT",
    "in_out": "VAR_IN_OUT",
    "global": "VAR_GLOBAL",
    "local": "VAR",
}

_CONTACT_EXPR = {
    "contact_no":  "{var}",
    "contact_nc":  "NOT {var}",
    "contact_pos": "R_TRIG_{var}",   # simplified; real LD uses R_TRIG FB
    "contact_neg": "F_TRIG_{var}",
}


def _elem_expr(elem: Element) -> str:
    """Convert a contact element to an ST boolean expression fragment."""
    tmpl = _CONTACT_EXPR.get(elem.type, "{var}")
    return tmpl.format(var=elem.var)


def _branch_expr(branch: list[Element]) -> str:
    """AND-combine all contacts in a branch."""
    if not branch:
        return "FALSE"
    parts = [_elem_expr(e) for e in branch]
    return " AND ".join(f"({p})" for p in parts)


def _rung_to_st(rung: Rung, rung_idx: int) -> list[str]:
    """
    Transpile one rung to IEC 61131-3 Structured Text lines.

    Parallel branches are OR-combined; the result drives the coil/FB.
    """
    lines: list[str] = []

    if not rung.branches or rung.output is None:
        return lines

    # OR-combine parallel branches
    branch_exprs = [f"({_branch_expr(b)})" for b in rung.branches if b]
    cond = " OR ".join(branch_exprs) if branch_exprs else "FALSE"

    out = rung.output
    if out.type == "coil":
        lines.append(f"  {out.var} := {cond};")
    elif out.type == "coil_set":
        lines.append(f"  IF {cond} THEN {out.var} := TRUE; END_IF")
    elif out.type == "coil_reset":
        lines.append(f"  IF {cond} THEN {out.var} := FALSE; END_IF")
    elif out.type in ("coil_pos", "coil_neg"):
        # P/N coils in ST need edge-detect temp var; simplified here
        lines.append(f"  (* {out.type.upper()} coil *)")
        lines.append(f"  IF {cond} THEN {out.var} := TRUE; END_IF")
    elif out.type == FB_TYPE:
        # FB call with EN input driven by the rung condition
        lines.append(f"  {out.fb_instance}(EN := {cond});")

    return lines


def _prog_to_st(prog: LadderProgram) -> str:
    """Transpile a full LadderProgram to an IEC 61131-3 ST PROGRAM block."""
    lines: list[str] = []
    lines.append(f"PROGRAM {prog.program}")

    # Group variables by dir
    from collections import defaultdict
    groups: dict[str, list] = defaultdict(list)
    for v in prog.variables:
        groups[v.dir].append(v)

    # FB instance declarations (TON, TOF, etc.)
    fb_instances: dict[str, str] = {}
    for rung in prog.rungs:
        if rung.output and rung.output.type == FB_TYPE:
            fb_instances[rung.output.fb_instance] = rung.output.fb_type

    for dir_key, section in _DIR_MAP.items():
        var_list = groups.get(dir_key, [])
        if not var_list:
            continue
        lines.append(section)
        for v in var_list:
            init_str = f" := {v.initial}" if v.initial is not None else ""
            lines.append(f"  {v.name} : {v.type}{init_str};")
        lines.append("END_VAR")

    if fb_instances:
        lines.append("VAR")
        for inst, fb_type in fb_instances.items():
            lines.append(f"  {inst} : {fb_type};")
        lines.append("END_VAR")

    for ri, rung in enumerate(prog.rungs):
        rung_lines = _rung_to_st(rung, ri)
        if rung.comment:
            lines.append(f"  (* {rung.comment} *)")
        lines.extend(rung_lines)

    lines.append("END_PROGRAM")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def lint_ld(prog: LadderProgram) -> list[Diagnostic]:
    """
    Lint an IEC 61131-3 Ladder Diagram program.

    Phase 1: structural schema validation (always runs).
    Phase 2: transpile LD→ST and run MATIEC (gracefully degrades when absent).

    Returns a combined list of Diagnostic objects.
    """
    diags: list[Diagnostic] = []

    # Phase 1 — schema
    diags.extend(_structural_lint(prog))

    # Phase 2 — MATIEC via ST transpilation
    try:
        st_source = _prog_to_st(prog)
        matiec_diags = lint_st_source(st_source)
        # Tag matiec diagnostics as coming from the LD→ST path
        for d in matiec_diags:
            diags.append(Diagnostic(
                severity=d.severity,
                message=f"[LD→ST] {d.message}",
                line=d.line,
                column=d.column,
                source="matiec-ld",
            ))
    except Exception as exc:
        diags.append(Diagnostic(
            severity="warning",
            message=f"LD→ST transpilation failed: {exc}",
            source="ld-lint",
        ))

    return diags
