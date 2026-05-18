"""
kerf_plc.st.ast — IEC 61131-3 ST Abstract Syntax Tree dataclasses.

All node classes use ``__slots__`` via @dataclass(slots=True) (Python 3.10+)
for memory efficiency, and are designed to be importable by T-220's writer.

Node hierarchy
--------------
POU
  variables: list[VarBlock]
  body: list[Statement]

VarBlock
  kind: VarKind  ('VAR' | 'VAR_INPUT' | 'VAR_OUTPUT' | 'VAR_IN_OUT')
  declarations: list[VarDecl]

VarDecl
  name: str
  type: TypeSpec
  initial_value: Expression | None

TypeSpec (sealed hierarchy)
  SimpleType(name)
  ArrayType(elem_type, lower, upper)

Statement (sealed hierarchy)
  Assignment, IfStmt, ForStmt, WhileStmt, RepeatStmt, CaseStmt, CallStmt

Expression (sealed hierarchy)
  BinaryOp, UnaryOp, FunctionCall, VarRef, FieldRef,
  IntLiteral, RealLiteral, BoolLiteral, StringLiteral, Duration
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Type system
# ---------------------------------------------------------------------------

@dataclass
class SimpleType:
    """A plain IEC type name: BOOL, INT, REAL, TIME, STRING, etc."""
    name: str

    def __repr__(self) -> str:
        return self.name


@dataclass
class ArrayType:
    """ARRAY [lower..upper] OF elem_type."""
    elem_type: "TypeSpec"
    lower: int
    upper: int

    def __repr__(self) -> str:
        return f"ARRAY[{self.lower}..{self.upper}] OF {self.elem_type!r}"


TypeSpec = SimpleType | ArrayType


# ---------------------------------------------------------------------------
# Variable declarations
# ---------------------------------------------------------------------------

class VarKind:
    VAR = "VAR"
    VAR_INPUT = "VAR_INPUT"
    VAR_OUTPUT = "VAR_OUTPUT"
    VAR_IN_OUT = "VAR_IN_OUT"


@dataclass
class VarDecl:
    name: str
    type: TypeSpec
    initial_value: Optional["Expression"] = None


@dataclass
class VarBlock:
    kind: str          # VarKind constant
    declarations: list[VarDecl] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------

@dataclass
class IntLiteral:
    value: int


@dataclass
class RealLiteral:
    value: float


@dataclass
class BoolLiteral:
    value: bool


@dataclass
class StringLiteral:
    value: str


@dataclass
class Duration:
    """TIME literal: T#100ms → Duration(ms=100)."""
    ms: int  # total milliseconds

    @classmethod
    def from_parts(
        cls,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        ms: int = 0,
    ) -> "Duration":
        total = (
            days * 86_400_000
            + hours * 3_600_000
            + minutes * 60_000
            + seconds * 1_000
            + ms
        )
        return cls(ms=total)


@dataclass
class VarRef:
    """Reference to a variable by name."""
    name: str


@dataclass
class FieldRef:
    """Structured field access: obj.field."""
    obj: "Expression"
    field: str


@dataclass
class BinaryOp:
    op: str           # '+', '-', '*', '/', 'MOD', '=', '<>', '<', '>', '<=', '>=', 'AND', 'OR', 'XOR'
    left: "Expression"
    right: "Expression"


@dataclass
class UnaryOp:
    op: str           # 'NOT', '-' (unary minus)
    operand: "Expression"


@dataclass
class FunctionCall:
    name: str
    args: list["Expression"] = field(default_factory=list)
    named_args: dict[str, "Expression"] = field(default_factory=dict)


Expression = (
    IntLiteral
    | RealLiteral
    | BoolLiteral
    | StringLiteral
    | Duration
    | VarRef
    | FieldRef
    | BinaryOp
    | UnaryOp
    | FunctionCall
)


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

@dataclass
class Assignment:
    target: "Expression"   # VarRef or FieldRef
    value: "Expression"


@dataclass
class IfStmt:
    condition: "Expression"
    then_stmts: list["Statement"] = field(default_factory=list)
    elsif_clauses: list[tuple["Expression", list["Statement"]]] = field(default_factory=list)
    else_stmts: list["Statement"] = field(default_factory=list)


@dataclass
class ForStmt:
    variable: str
    from_expr: "Expression"
    to_expr: "Expression"
    by_expr: Optional["Expression"]
    body: list["Statement"] = field(default_factory=list)


@dataclass
class WhileStmt:
    condition: "Expression"
    body: list["Statement"] = field(default_factory=list)


@dataclass
class RepeatStmt:
    body: list["Statement"] = field(default_factory=list)
    until_condition: Optional["Expression"] = None


@dataclass
class CaseClause:
    values: list["Expression"]         # one or more case selector values
    stmts: list["Statement"] = field(default_factory=list)


@dataclass
class CaseStmt:
    selector: "Expression"
    clauses: list[CaseClause] = field(default_factory=list)
    else_stmts: list["Statement"] = field(default_factory=list)


@dataclass
class CallStmt:
    """Standalone function/FB call (result discarded)."""
    call: FunctionCall


Statement = (
    Assignment
    | IfStmt
    | ForStmt
    | WhileStmt
    | RepeatStmt
    | CaseStmt
    | CallStmt
)


# ---------------------------------------------------------------------------
# Top-level POU
# ---------------------------------------------------------------------------

@dataclass
class POU:
    """
    IEC 61131-3 Program Organisation Unit.

    pou_type: 'PROGRAM' | 'FUNCTION_BLOCK' | 'FUNCTION'
    """
    name: str
    pou_type: str
    variables: list[VarBlock] = field(default_factory=list)
    body: list[Statement] = field(default_factory=list)

    # Convenience helpers -------------------------------------------------------

    def all_var_decls(self) -> list[VarDecl]:
        """Flatten all VarBlocks into a single sequence of VarDecl."""
        out: list[VarDecl] = []
        for blk in self.variables:
            out.extend(blk.declarations)
        return out

    def has_if(self) -> bool:
        """Return True when any top-level statement is an IfStmt."""
        return any(isinstance(s, IfStmt) for s in self.body)
