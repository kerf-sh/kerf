"""
kerf_plc.ld.schema — IEC 61131-3 Ladder Diagram (LD) data model.

A ladder program is a list of Rungs.  Each rung is a horizontal rail with
one or more parallel branches, each branch being a sequence of Elements.

Element types (IEC 61131-3 §9):
  contact_no   — normally-open contact  -| |-
  contact_nc   — normally-closed contact -|/|-
  contact_pos  — positive-transition contact (P)
  contact_neg  — negative-transition contact (N)
  coil         — output coil            -( )-
  coil_set     — set (latching) coil    -(S)-
  coil_reset   — reset (unlatching) coil-(R)-
  coil_pos     — positive-transition coil (P)
  coil_neg     — negative-transition coil (N)
  fb_call      — function-block call    (TON, TOF, TP, CTU, CTD, CTUD, …)

JSON / YAML wire format (`.plc.ld` files):

{
  "program": "StartStopLatch",
  "variables": [                         # optional VAR declarations
    {"name": "start_pb", "type": "BOOL", "dir": "input"},
    {"name": "stop_pb",  "type": "BOOL", "dir": "input"},
    {"name": "motor_run","type": "BOOL", "dir": "output"}
  ],
  "rungs": [
    {
      "label": "Rung 0",
      "comment": "start latch",
      "branches": [
        [
          {"type": "contact_no", "var": "start_pb"},
          {"type": "contact_nc", "var": "stop_pb"}
        ]
      ],
      "output": {"type": "coil", "var": "motor_run"}
    }
  ]
}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Element types
# ---------------------------------------------------------------------------

CONTACT_TYPES = frozenset({
    "contact_no",    # -| |-
    "contact_nc",    # -|/|-
    "contact_pos",   # -|P|-
    "contact_neg",   # -|N|-
})

COIL_TYPES = frozenset({
    "coil",          # -( )-
    "coil_set",      # -(S)-
    "coil_reset",    # -(R)-
    "coil_pos",      # -(P)-
    "coil_neg",      # -(N)-
})

FB_TYPE = "fb_call"

ALL_ELEMENT_TYPES = CONTACT_TYPES | COIL_TYPES | {FB_TYPE}

# Standard IEC 61131-3 function blocks that are valid in LD
STDLIB_FB = frozenset({"TON", "TOF", "TP", "SR", "RS", "CTU", "CTD", "CTUD", "R_TRIG", "F_TRIG"})

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Element:
    """A single element on a ladder rung branch."""
    type: str           # one of ALL_ELEMENT_TYPES
    var: str = ""       # variable / coil / contact name
    # Function-block specific
    fb_type: str = ""   # e.g. "TON"
    fb_instance: str = ""  # instance name
    fb_inputs: dict[str, str] = field(default_factory=dict)  # pin→var mapping

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.type not in ALL_ELEMENT_TYPES:
            errors.append(f"unknown element type '{self.type}'")
        if self.type == FB_TYPE:
            if not self.fb_type:
                errors.append("fb_call requires 'fb_type'")
            if not self.fb_instance:
                errors.append("fb_call requires 'fb_instance'")
        else:
            if not self.var:
                errors.append(f"element '{self.type}' requires 'var'")
        return errors


@dataclass
class Rung:
    """A single horizontal rung in the ladder program."""
    label: str = ""
    comment: str = ""
    # branches: list of parallel paths; each path is a sequence of Elements
    branches: list[list[Element]] = field(default_factory=list)
    # The output element (coil / fb_call) on the right rail
    output: Element | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.branches:
            errors.append("rung has no branches (left rail is empty)")
        for i, branch in enumerate(self.branches):
            if not branch:
                errors.append(f"branch {i} is empty")
            for elem in branch:
                errs = elem.validate()
                errors.extend(f"branch {i}: {e}" for e in errs)
                if elem.type in COIL_TYPES or elem.type == FB_TYPE:
                    errors.append(
                        f"branch {i}: coil/fb_call '{elem.type}' must appear as"
                        f" the rung output, not inside a branch"
                    )
        if self.output is not None:
            out_errs = self.output.validate()
            errors.extend(f"output: {e}" for e in out_errs)
            if (self.output.type in CONTACT_TYPES):
                errors.append(
                    f"output element type '{self.output.type}' is a contact — "
                    "output must be a coil or fb_call"
                )
        return errors


@dataclass
class VariableDecl:
    name: str
    type: str = "BOOL"
    dir: Literal["local", "input", "output", "in_out", "global"] = "local"
    initial: Any = None
    comment: str = ""


@dataclass
class LadderProgram:
    """Top-level ladder program — the root of a `.plc.ld` file."""
    program: str = "Main"
    variables: list[VariableDecl] = field(default_factory=list)
    rungs: list[Rung] = field(default_factory=list)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.program or not self.program.strip():
            errors.append("program name is required")
        for i, rung in enumerate(self.rungs):
            rung_errs = rung.validate()
            errors.extend(f"rung {i} ({rung.label!r}): {e}" for e in rung_errs)
        return errors


# ---------------------------------------------------------------------------
# JSON → dataclass helpers
# ---------------------------------------------------------------------------

def _element_from_dict(d: dict) -> Element:
    return Element(
        type=d.get("type", ""),
        var=d.get("var", ""),
        fb_type=d.get("fb_type", ""),
        fb_instance=d.get("fb_instance", ""),
        fb_inputs=d.get("fb_inputs", {}),
    )


def _rung_from_dict(d: dict) -> Rung:
    branches = []
    for branch_raw in d.get("branches", []):
        branches.append([_element_from_dict(e) for e in branch_raw])
    output_raw = d.get("output")
    output = _element_from_dict(output_raw) if output_raw else None
    return Rung(
        label=d.get("label", ""),
        comment=d.get("comment", ""),
        branches=branches,
        output=output,
    )


def _var_from_dict(d: dict) -> VariableDecl:
    return VariableDecl(
        name=d.get("name", ""),
        type=d.get("type", "BOOL"),
        dir=d.get("dir", "local"),
        initial=d.get("initial"),
        comment=d.get("comment", ""),
    )


def load(data: dict) -> LadderProgram:
    """
    Deserialise a JSON/YAML-parsed dict into a LadderProgram.

    Raises ValueError listing all validation errors if the program is invalid.
    """
    prog = LadderProgram(
        program=data.get("program", "Main"),
        variables=[_var_from_dict(v) for v in data.get("variables", [])],
        rungs=[_rung_from_dict(r) for r in data.get("rungs", [])],
    )
    errors = prog.validate()
    if errors:
        raise ValueError("LD program validation errors:\n" + "\n".join(f"  • {e}" for e in errors))
    return prog


def dump(prog: LadderProgram) -> dict:
    """Serialise a LadderProgram back to a plain dict (round-trip)."""
    def _elem(e: Element) -> dict:
        d: dict = {"type": e.type}
        if e.type == FB_TYPE:
            d["fb_type"] = e.fb_type
            d["fb_instance"] = e.fb_instance
            if e.fb_inputs:
                d["fb_inputs"] = e.fb_inputs
        else:
            d["var"] = e.var
        return d

    def _rung(r: Rung) -> dict:
        rd: dict = {
            "label": r.label,
            "branches": [[_elem(e) for e in branch] for branch in r.branches],
        }
        if r.comment:
            rd["comment"] = r.comment
        if r.output is not None:
            rd["output"] = _elem(r.output)
        return rd

    def _var(v: VariableDecl) -> dict:
        vd: dict = {"name": v.name, "type": v.type}
        if v.dir != "local":
            vd["dir"] = v.dir
        if v.initial is not None:
            vd["initial"] = v.initial
        if v.comment:
            vd["comment"] = v.comment
        return vd

    return {
        "program": prog.program,
        "variables": [_var(v) for v in prog.variables],
        "rungs": [_rung(r) for r in prog.rungs],
    }
