"""
AST node definitions for synthesizable Verilog/SystemVerilog.

Every node carries (line, col) source position (1-based line, 0-based col).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

@dataclass
class Node:
    """Base AST node; all nodes carry source position."""
    line: int = 0
    col: int = 0


# ---------------------------------------------------------------------------
# Types / Identifiers
# ---------------------------------------------------------------------------

@dataclass
class Width(Node):
    """Bit width range, e.g. [7:0]."""
    msb: int = 0
    lsb: int = 0


@dataclass
class Identifier(Node):
    name: str = ""


# ---------------------------------------------------------------------------
# Literals
# ---------------------------------------------------------------------------

@dataclass
class NumberLiteral(Node):
    """
    Verilog numeric literal.

    Examples:
      8'hAA  -> bits=8, base='h', value=0xAA
      4'b1010 -> bits=4, base='b', value=0b1010
      42     -> bits=None, base='d', value=42
    """
    bits: Optional[int] = None
    base: str = "d"      # 'd' | 'h' | 'b' | 'o'
    value: int = 0
    raw: str = ""


# ---------------------------------------------------------------------------
# Expressions
# ---------------------------------------------------------------------------

@dataclass
class BinaryExpr(Node):
    op: str = ""
    left: Optional[Node] = None
    right: Optional[Node] = None


@dataclass
class UnaryExpr(Node):
    op: str = ""
    operand: Optional[Node] = None


@dataclass
class IndexExpr(Node):
    """e.g. mem[addr]"""
    base: Optional[Node] = None
    index: Optional[Node] = None


@dataclass
class SliceExpr(Node):
    """e.g. data[7:0]"""
    base: Optional[Node] = None
    msb: Optional[Node] = None
    lsb: Optional[Node] = None


@dataclass
class ConcatExpr(Node):
    """e.g. {a, b, c}"""
    parts: List[Node] = field(default_factory=list)


@dataclass
class ReplicateExpr(Node):
    """e.g. {4{1'b0}}"""
    count: Optional[Node] = None
    value: Optional[Node] = None


@dataclass
class TernaryExpr(Node):
    cond: Optional[Node] = None
    then_expr: Optional[Node] = None
    else_expr: Optional[Node] = None


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

@dataclass
class BlockingAssign(Node):
    """lhs = rhs"""
    lhs: Optional[Node] = None
    rhs: Optional[Node] = None


@dataclass
class NonBlockingAssign(Node):
    """lhs <= rhs"""
    lhs: Optional[Node] = None
    rhs: Optional[Node] = None


@dataclass
class IfStatement(Node):
    cond: Optional[Node] = None
    then_body: List[Node] = field(default_factory=list)
    else_body: List[Node] = field(default_factory=list)


@dataclass
class CaseItem(Node):
    exprs: List[Node] = field(default_factory=list)   # empty = default
    body: List[Node] = field(default_factory=list)


@dataclass
class CaseStatement(Node):
    expr: Optional[Node] = None
    items: List[CaseItem] = field(default_factory=list)
    style: str = "case"   # 'case' | 'casez' | 'casex'


@dataclass
class BeginEnd(Node):
    """Named or anonymous begin/end block."""
    label: Optional[str] = None
    stmts: List[Node] = field(default_factory=list)


@dataclass
class ForLoop(Node):
    init: Optional[Node] = None
    cond: Optional[Node] = None
    step: Optional[Node] = None
    body: List[Node] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Always blocks
# ---------------------------------------------------------------------------

@dataclass
class SensitivityEvent(Node):
    """posedge/negedge/plain signal in sensitivity list."""
    edge: str = ""      # 'posedge' | 'negedge' | ''
    signal: Optional[Node] = None


@dataclass
class AlwaysBlock(Node):
    """
    always / always_ff / always_comb / always_latch.
    sensitivity: list of SensitivityEvent, or ['*'] for always_comb/@(*)
    """
    kind: str = "always"   # 'always' | 'always_ff' | 'always_comb' | 'always_latch'
    sensitivity: List[Union[SensitivityEvent, str]] = field(default_factory=list)
    body: List[Node] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Continuous assign
# ---------------------------------------------------------------------------

@dataclass
class ContinuousAssign(Node):
    lhs: Optional[Node] = None
    rhs: Optional[Node] = None


# ---------------------------------------------------------------------------
# Declarations
# ---------------------------------------------------------------------------

@dataclass
class PortDecl(Node):
    """input / output / inout port declaration."""
    direction: str = ""   # 'input' | 'output' | 'inout'
    net_type: str = ""    # 'wire' | 'reg' | 'logic' | ''
    signed: bool = False
    width: Optional[Width] = None
    dims: List[Width] = field(default_factory=list)  # unpacked dimensions
    name: str = ""


@dataclass
class NetDecl(Node):
    """wire / logic / reg declaration inside module body."""
    net_type: str = ""    # 'wire' | 'logic' | 'reg'
    signed: bool = False
    width: Optional[Width] = None
    dims: List[Width] = field(default_factory=list)  # unpacked array dimensions
    name: str = ""
    init: Optional[Node] = None


@dataclass
class ParamDecl(Node):
    """parameter / localparam."""
    kind: str = "parameter"   # 'parameter' | 'localparam'
    width: Optional[Width] = None
    name: str = ""
    value: Optional[Node] = None


# ---------------------------------------------------------------------------
# Module instances
# ---------------------------------------------------------------------------

@dataclass
class PortConnection(Node):
    """Named: .clk(sys_clk) or positional."""
    port_name: Optional[str] = None   # None = positional
    expr: Optional[Node] = None


@dataclass
class ModuleInstance(Node):
    module_name: str = ""
    instance_name: str = ""
    param_overrides: List[PortConnection] = field(default_factory=list)
    connections: List[PortConnection] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------

@dataclass
class GenerateBlock(Node):
    items: List[Node] = field(default_factory=list)


@dataclass
class GenIf(Node):
    cond: Optional[Node] = None
    then_items: List[Node] = field(default_factory=list)
    else_items: List[Node] = field(default_factory=list)


@dataclass
class GenFor(Node):
    genvar: str = ""
    init: Optional[Node] = None
    cond: Optional[Node] = None
    step: Optional[Node] = None
    items: List[Node] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Top-level
# ---------------------------------------------------------------------------

@dataclass
class ModuleDecl(Node):
    """Top-level module declaration."""
    name: str = ""
    params: List[ParamDecl] = field(default_factory=list)
    ports: List[PortDecl] = field(default_factory=list)
    items: List[Node] = field(default_factory=list)


@dataclass
class DesignUnit(Node):
    """Root of a parsed file — list of module declarations."""
    modules: List[ModuleDecl] = field(default_factory=list)
    filename: str = ""
