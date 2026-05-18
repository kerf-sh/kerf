"""
Recursive-descent parser for synthesizable Verilog / SystemVerilog.

Entry point: parse(source, filename) -> DesignUnit

Handles:
  - module / endmodule with ANSI port list
  - parameter / localparam
  - input / output / inout  with wire / reg / logic and [msb:lsb] width
  - wire / logic / reg declarations (including unpacked array dims)
  - assign (continuous)
  - always / always_ff / always_comb / always_latch
  - begin/end blocks (named and anonymous)
  - if/else
  - case / casez / casex
  - blocking (=) and non-blocking (<=) assignments
  - for loops
  - generate / endgenerate, genvar, for-generate, if-generate
  - module instantiation
  - hex / binary / decimal / octal literals
  - `timescale and other directives (silently skipped)
  - // and /* */ comments (stripped by lexer)
"""
from __future__ import annotations

import re
from typing import List, Optional, Union

from .ast import (
    AlwaysBlock,
    BeginEnd,
    BinaryExpr,
    BlockingAssign,
    CaseItem,
    CaseStatement,
    ConcatExpr,
    ContinuousAssign,
    DesignUnit,
    ForLoop,
    GenFor,
    GenIf,
    GenerateBlock,
    Identifier,
    IfStatement,
    IndexExpr,
    ModuleDecl,
    ModuleInstance,
    NetDecl,
    NonBlockingAssign,
    Node,
    NumberLiteral,
    ParamDecl,
    PortConnection,
    PortDecl,
    ReplicateExpr,
    SensitivityEvent,
    SliceExpr,
    TernaryExpr,
    UnaryExpr,
    Width,
)
from .lexer import TT, LexError, Token, tokenize


class ParseError(Exception):
    def __init__(self, msg: str, tok: Token) -> None:
        super().__init__(f"{msg} at line {tok.line}, col {tok.col} (got {tok.type.name} {tok.value!r})")
        self.parse_line = tok.line
        self.parse_col = tok.col
        self.token = tok


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class Parser:
    def __init__(self, tokens: List[Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    # ------------------------------------------------------------------
    # Primitives
    # ------------------------------------------------------------------

    def _peek(self, offset: int = 0) -> Token:
        idx = self._pos + offset
        if idx >= len(self._tokens):
            return self._tokens[-1]  # EOF
        return self._tokens[idx]

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        if self._pos < len(self._tokens) - 1:
            self._pos += 1
        return tok

    def _expect(self, tt: TT, value: Optional[str] = None) -> Token:
        tok = self._peek()
        if tok.type != tt:
            raise ParseError(f"Expected {tt.name}{' ' + repr(value) if value else ''}", tok)
        if value is not None and tok.value != value:
            raise ParseError(f"Expected {tt.name} {value!r}", tok)
        return self._advance()

    def _expect_kw(self, kw: str) -> Token:
        tok = self._peek()
        if tok.type != TT.IDENT or tok.value != kw:
            raise ParseError(f"Expected keyword {kw!r}", tok)
        return self._advance()

    def _eat_if(self, tt: TT, value: Optional[str] = None) -> Optional[Token]:
        tok = self._peek()
        if tok.type == tt and (value is None or tok.value == value):
            return self._advance()
        return None

    def _eat_kw(self, kw: str) -> Optional[Token]:
        tok = self._peek()
        if tok.type == TT.IDENT and tok.value == kw:
            return self._advance()
        return None

    def _is_kw(self, *kws: str) -> bool:
        tok = self._peek()
        return tok.type == TT.IDENT and tok.value in kws

    def _pos_of(self, tok: Token) -> tuple[int, int]:
        return tok.line, tok.col

    # ------------------------------------------------------------------
    # Skip compiler directives
    # ------------------------------------------------------------------

    def _skip_directives(self) -> None:
        while self._peek().type == TT.DIRECTIVE:
            # Skip directive and any trailing tokens up to ';' or newline-equiv
            tok = self._advance()
            # `timescale 1ns/1ps — skip tokens until ';' or next directive or keyword
            if tok.value in ("`timescale", "`include", "`define", "`ifdef",
                             "`ifndef", "`else", "`elsif", "`endif", "`undef"):
                # skip rest of "line" heuristically — until ';', 'module', or directive
                while True:
                    p = self._peek()
                    if p.type in (TT.EOF, TT.SEMICOLON, TT.DIRECTIVE):
                        break
                    if p.type == TT.IDENT and p.value in ("module", "endmodule"):
                        break
                    self._advance()
                self._eat_if(TT.SEMICOLON)

    # ------------------------------------------------------------------
    # Top-level
    # ------------------------------------------------------------------

    def parse(self, filename: str = "") -> DesignUnit:
        self._skip_directives()
        modules: List[ModuleDecl] = []
        while self._peek().type != TT.EOF:
            self._skip_directives()
            if self._peek().type == TT.EOF:
                break
            if self._is_kw("module", "macromodule"):
                modules.append(self._parse_module())
            else:
                # Skip unknown top-level tokens
                self._advance()
        du = DesignUnit(modules=modules, filename=filename)
        du.line, du.col = 1, 0
        return du

    # ------------------------------------------------------------------
    # Module
    # ------------------------------------------------------------------

    def _parse_module(self) -> ModuleDecl:
        kw_tok = self._advance()  # 'module' or 'macromodule'
        name_tok = self._expect(TT.IDENT)
        mod = ModuleDecl(name=name_tok.value)
        mod.line, mod.col = kw_tok.line, kw_tok.col

        # Optional parameter list:  #(parameter ...)
        if self._eat_if(TT.HASH):
            self._expect(TT.LPAREN)
            mod.params = self._parse_param_port_list()
            self._expect(TT.RPAREN)

        # Port list
        if self._eat_if(TT.LPAREN):
            if not self._eat_if(TT.RPAREN):
                mod.ports = self._parse_ansi_port_list()
                self._expect(TT.RPAREN)

        self._expect(TT.SEMICOLON)

        # Module body
        while not (self._is_kw("endmodule") or self._peek().type == TT.EOF):
            self._skip_directives()
            if self._is_kw("endmodule"):
                break
            item = self._parse_module_item()
            if item is not None:
                mod.items.append(item)

        self._expect_kw("endmodule")
        # optional label after endmodule: endmodule : name
        if self._eat_if(TT.COLON):
            self._eat_if(TT.IDENT)

        return mod

    def _parse_param_port_list(self) -> List[ParamDecl]:
        params: List[ParamDecl] = []
        while self._peek().type != TT.RPAREN and self._peek().type != TT.EOF:
            if self._is_kw("parameter", "localparam"):
                params.append(self._parse_param_decl())
            else:
                self._advance()  # skip
            if not self._eat_if(TT.COMMA):
                break
        return params

    def _parse_ansi_port_list(self) -> List[PortDecl]:
        ports: List[PortDecl] = []
        while self._peek().type != TT.RPAREN and self._peek().type != TT.EOF:
            # Each port: direction [type] [signed] [width] name
            if self._is_kw("input", "output", "inout"):
                ports.append(self._parse_port_decl())
            elif self._peek().type == TT.COMMA:
                self._advance()
                continue
            elif self._peek().type == TT.IDENT:
                # Plain port name without direction — skip for now
                self._advance()
            else:
                self._advance()
            if not self._eat_if(TT.COMMA):
                break
        return ports

    def _parse_port_decl(self) -> PortDecl:
        dir_tok = self._advance()  # input / output / inout
        port = PortDecl(direction=dir_tok.value)
        port.line, port.col = dir_tok.line, dir_tok.col

        # Optional net type
        if self._is_kw("wire", "reg", "logic", "tri", "tri0", "tri1",
                        "wand", "wor", "integer", "bit", "byte",
                        "shortint", "int", "longint"):
            port.net_type = self._advance().value

        # Optional signed
        if self._eat_kw("signed"):
            port.signed = True
        elif self._eat_kw("unsigned"):
            pass

        # Optional width [msb:lsb]
        if self._peek().type == TT.LBRACKET:
            port.width = self._parse_width()

        # Port name
        name_tok = self._expect(TT.IDENT)
        port.name = name_tok.value

        # Optional unpacked dimensions
        while self._peek().type == TT.LBRACKET:
            port.dims.append(self._parse_width())

        return port

    def _parse_width(self) -> Width:
        tok = self._expect(TT.LBRACKET)
        w = Width()
        w.line, w.col = tok.line, tok.col
        msb_expr = self._parse_expr()
        self._expect(TT.COLON)
        lsb_expr = self._parse_expr()
        self._expect(TT.RBRACKET)
        # Evaluate simple constant expressions
        w.msb = self._eval_const(msb_expr)
        w.lsb = self._eval_const(lsb_expr)
        return w

    def _eval_const(self, node: Node) -> int:
        """Best-effort constant folding for width declarations."""
        if isinstance(node, NumberLiteral):
            return node.value
        if isinstance(node, Identifier):
            return 0   # Can't resolve parameters statically here
        if isinstance(node, BinaryExpr):
            l = self._eval_const(node.left)
            r = self._eval_const(node.right)
            ops = {'+': l + r, '-': l - r, '*': l * r,
                   '-': l - r, '/': l // r if r else 0}
            return ops.get(node.op, 0)
        return 0

    # ------------------------------------------------------------------
    # Module body items
    # ------------------------------------------------------------------

    def _parse_module_item(self) -> Optional[Node]:
        tok = self._peek()

        # Declarations
        if self._is_kw("wire", "reg", "logic", "tri", "tri0", "tri1",
                        "integer", "bit", "byte", "shortint", "int", "longint"):
            return self._parse_net_decl()

        if self._is_kw("input", "output", "inout"):
            port = self._parse_port_decl()
            self._eat_if(TT.SEMICOLON)
            return port

        if self._is_kw("parameter", "localparam"):
            p = self._parse_param_decl()
            self._eat_if(TT.SEMICOLON)
            return p

        # Continuous assign
        if self._is_kw("assign"):
            return self._parse_continuous_assign()

        # Always blocks
        if self._is_kw("always", "always_ff", "always_comb", "always_latch"):
            return self._parse_always()

        # Initial (skip body)
        if self._is_kw("initial"):
            return self._parse_initial()

        # Generate
        if self._is_kw("generate"):
            return self._parse_generate()

        # Genvar
        if self._is_kw("genvar"):
            return self._parse_genvar_decl()

        # Function / task (skip for now)
        if self._is_kw("function", "task"):
            return self._skip_function_task()

        # Directives
        if tok.type == TT.DIRECTIVE:
            self._advance()
            return None

        # Semicolon (empty statement)
        if tok.type == TT.SEMICOLON:
            self._advance()
            return None

        # Module instantiation or unknown IDENT
        if tok.type == TT.IDENT and tok.value not in (
            "endmodule", "end", "endcase", "endgenerate",
            "endfunction", "endtask"
        ):
            # Could be module instantiation: ModName #(...) inst_name (...)
            # or defparam, etc.
            return self._parse_module_instantiation_or_stmt()

        # Unknown — skip
        self._advance()
        return None

    # ------------------------------------------------------------------
    # Net declarations
    # ------------------------------------------------------------------

    def _parse_net_decl(self) -> NetDecl:
        type_tok = self._advance()
        decl = NetDecl(net_type=type_tok.value)
        decl.line, decl.col = type_tok.line, type_tok.col

        if self._eat_kw("signed"):
            decl.signed = True
        elif self._eat_kw("unsigned"):
            pass

        if self._peek().type == TT.LBRACKET:
            decl.width = self._parse_width()

        name_tok = self._expect(TT.IDENT)
        decl.name = name_tok.value

        # Unpacked array dimensions
        while self._peek().type == TT.LBRACKET:
            decl.dims.append(self._parse_width())

        # Optional initializer
        if self._eat_if(TT.ASSIGN):
            decl.init = self._parse_expr()

        self._expect(TT.SEMICOLON)
        return decl

    # ------------------------------------------------------------------
    # Parameter declarations
    # ------------------------------------------------------------------

    def _parse_param_decl(self) -> ParamDecl:
        kw_tok = self._advance()  # parameter / localparam
        p = ParamDecl(kind=kw_tok.value)
        p.line, p.col = kw_tok.line, kw_tok.col

        # Optional type keyword
        if self._is_kw("integer", "real", "realtime", "time",
                        "bit", "byte", "logic", "reg"):
            self._advance()

        # Optional width
        if self._peek().type == TT.LBRACKET:
            p.width = self._parse_width()

        name_tok = self._expect(TT.IDENT)
        p.name = name_tok.value

        if self._eat_if(TT.ASSIGN):
            p.value = self._parse_expr()

        return p

    # ------------------------------------------------------------------
    # Continuous assign
    # ------------------------------------------------------------------

    def _parse_continuous_assign(self) -> ContinuousAssign:
        kw_tok = self._expect_kw("assign")
        ca = ContinuousAssign()
        ca.line, ca.col = kw_tok.line, kw_tok.col

        # Optional drive strength — skip
        ca.lhs = self._parse_lvalue()
        self._expect(TT.ASSIGN)
        ca.rhs = self._parse_expr()
        self._expect(TT.SEMICOLON)
        return ca

    # ------------------------------------------------------------------
    # Always blocks
    # ------------------------------------------------------------------

    def _parse_always(self) -> AlwaysBlock:
        kw_tok = self._advance()  # always / always_ff / ...
        ab = AlwaysBlock(kind=kw_tok.value)
        ab.line, ab.col = kw_tok.line, kw_tok.col

        # Sensitivity list
        if self._eat_if(TT.AT):
            if kw_tok.value in ("always_comb", "always_latch"):
                # @* or @(*) may appear
                if self._eat_if(TT.STAR):
                    ab.sensitivity = ["*"]
                elif self._peek().type == TT.LPAREN:
                    self._advance()
                    self._eat_if(TT.STAR)
                    self._eat_if(TT.RPAREN)
                    ab.sensitivity = ["*"]
            elif self._peek().type == TT.LPAREN:
                self._advance()
                ab.sensitivity = self._parse_sensitivity_list()
                self._expect(TT.RPAREN)
            else:
                # @signal
                ident = self._expect(TT.IDENT)
                ev = SensitivityEvent(edge="", signal=Identifier(name=ident.value))
                ev.line, ev.col = ident.line, ident.col
                ab.sensitivity = [ev]
        elif kw_tok.value in ("always_comb", "always_latch"):
            ab.sensitivity = ["*"]

        # Body
        ab.body = self._parse_stmt_or_block()
        return ab

    def _parse_sensitivity_list(self) -> list:
        events = []
        while self._peek().type != TT.RPAREN and self._peek().type != TT.EOF:
            if self._peek().type == TT.STAR:
                self._advance()
                events = ["*"]
                break
            ev = SensitivityEvent()
            tok = self._peek()
            ev.line, ev.col = tok.line, tok.col
            if self._is_kw("posedge"):
                self._advance()
                ev.edge = "posedge"
            elif self._is_kw("negedge"):
                self._advance()
                ev.edge = "negedge"
            sig_tok = self._expect(TT.IDENT)
            ev.signal = Identifier(name=sig_tok.value, line=sig_tok.line, col=sig_tok.col)
            events.append(ev)
            # 'or' or ',' between events
            if self._eat_kw("or"):
                continue
            if self._eat_if(TT.COMMA):
                continue
            break
        return events

    # ------------------------------------------------------------------
    # Initial block (skip body)
    # ------------------------------------------------------------------

    def _parse_initial(self) -> Optional[Node]:
        self._expect_kw("initial")
        self._parse_stmt_or_block()
        return None

    # ------------------------------------------------------------------
    # Statements
    # ------------------------------------------------------------------

    def _parse_stmt_or_block(self) -> List[Node]:
        """Returns a list containing the statement(s)."""
        tok = self._peek()
        if self._is_kw("begin"):
            block = self._parse_begin_end()
            return [block]
        else:
            stmt = self._parse_stmt()
            if stmt is None:
                return []
            return [stmt]

    def _parse_begin_end(self) -> BeginEnd:
        kw_tok = self._expect_kw("begin")
        block = BeginEnd()
        block.line, block.col = kw_tok.line, kw_tok.col

        # Optional label: begin : label
        if self._eat_if(TT.COLON):
            label_tok = self._eat_if(TT.IDENT)
            if label_tok:
                block.label = label_tok.value

        while not (self._is_kw("end") or self._peek().type == TT.EOF):
            stmt = self._parse_stmt()
            if stmt is not None:
                block.stmts.append(stmt)

        self._expect_kw("end")
        # Optional label: end : label
        if self._eat_if(TT.COLON):
            self._eat_if(TT.IDENT)

        return block

    def _parse_stmt(self) -> Optional[Node]:
        tok = self._peek()

        # Empty statement
        if tok.type == TT.SEMICOLON:
            self._advance()
            return None

        # begin/end block
        if self._is_kw("begin"):
            return self._parse_begin_end()

        # if/else
        if self._is_kw("if"):
            return self._parse_if()

        # case/casez/casex
        if self._is_kw("case", "casez", "casex"):
            return self._parse_case()

        # for loop
        if self._is_kw("for"):
            return self._parse_for()

        # Local declarations inside procedural blocks (SV)
        if self._is_kw("wire", "reg", "logic", "integer", "bit",
                        "byte", "shortint", "int", "longint"):
            return self._parse_net_decl()

        # Directives
        if tok.type == TT.DIRECTIVE:
            self._advance()
            return None

        # Assignment or function call — parse an lvalue/expr then check for = or <=
        if tok.type == TT.IDENT or tok.type == TT.LBRACE:
            return self._parse_assignment_or_call()

        # Skip unknown
        self._advance()
        return None

    def _parse_if(self) -> IfStatement:
        kw_tok = self._expect_kw("if")
        stmt = IfStatement()
        stmt.line, stmt.col = kw_tok.line, kw_tok.col

        self._expect(TT.LPAREN)
        stmt.cond = self._parse_expr()
        self._expect(TT.RPAREN)

        stmt.then_body = self._parse_stmt_or_block()

        if self._eat_kw("else"):
            stmt.else_body = self._parse_stmt_or_block()

        return stmt

    def _parse_case(self) -> CaseStatement:
        kw_tok = self._advance()  # case / casez / casex
        cs = CaseStatement(style=kw_tok.value)
        cs.line, cs.col = kw_tok.line, kw_tok.col

        self._expect(TT.LPAREN)
        cs.expr = self._parse_expr()
        self._expect(TT.RPAREN)

        while not (self._is_kw("endcase") or self._peek().type == TT.EOF):
            item = self._parse_case_item()
            if item is not None:
                cs.items.append(item)

        self._expect_kw("endcase")
        return cs

    def _parse_case_item(self) -> Optional[CaseItem]:
        tok = self._peek()
        if tok.type == TT.EOF or self._is_kw("endcase"):
            return None

        item = CaseItem()
        item.line, item.col = tok.line, tok.col

        if self._is_kw("default"):
            self._advance()
            self._eat_if(TT.COLON)
        else:
            while True:
                item.exprs.append(self._parse_expr())
                if not self._eat_if(TT.COMMA):
                    break
            self._expect(TT.COLON)

        item.body = self._parse_stmt_or_block()
        return item

    def _parse_for(self) -> ForLoop:
        kw_tok = self._expect_kw("for")
        fl = ForLoop()
        fl.line, fl.col = kw_tok.line, kw_tok.col

        self._expect(TT.LPAREN)
        # init
        if self._peek().type != TT.SEMICOLON:
            fl.init = self._parse_assignment_or_decl_raw()
        self._eat_if(TT.SEMICOLON)
        # cond
        if self._peek().type != TT.SEMICOLON:
            fl.cond = self._parse_expr()
        self._eat_if(TT.SEMICOLON)
        # step
        if self._peek().type != TT.RPAREN:
            fl.step = self._parse_assignment_raw()
        self._expect(TT.RPAREN)

        fl.body = self._parse_stmt_or_block()
        return fl

    def _parse_assignment_raw(self) -> Optional[Node]:
        """Parse an assignment without trailing semicolon."""
        lhs = self._parse_lvalue()
        if self._eat_if(TT.ASSIGN):
            rhs = self._parse_expr()
            ba = BlockingAssign(lhs=lhs, rhs=rhs)
            ba.line, ba.col = lhs.line, lhs.col
            return ba
        if self._eat_if(TT.NB_ASSIGN):
            rhs = self._parse_expr()
            nba = NonBlockingAssign(lhs=lhs, rhs=rhs)
            nba.line, nba.col = lhs.line, lhs.col
            return nba
        return lhs

    def _parse_assignment_or_decl_raw(self) -> Optional[Node]:
        """Parse for-init: integer i = 0 or i = 0."""
        if self._is_kw("integer", "reg", "logic", "bit", "int",
                        "shortint", "longint", "byte"):
            type_tok = self._advance()
            name_tok = self._expect(TT.IDENT)
            decl = NetDecl(net_type=type_tok.value, name=name_tok.value)
            decl.line, decl.col = type_tok.line, type_tok.col
            if self._eat_if(TT.ASSIGN):
                decl.init = self._parse_expr()
            return decl
        return self._parse_assignment_raw()

    def _parse_assignment_or_call(self) -> Optional[Node]:
        """Parse a procedural statement that starts with an lvalue."""
        lhs = self._parse_lvalue()

        if self._eat_if(TT.ASSIGN):
            rhs = self._parse_expr()
            self._expect(TT.SEMICOLON)
            ba = BlockingAssign(lhs=lhs, rhs=rhs)
            ba.line, ba.col = lhs.line, lhs.col
            return ba

        if self._eat_if(TT.NB_ASSIGN):
            rhs = self._parse_expr()
            self._expect(TT.SEMICOLON)
            nba = NonBlockingAssign(lhs=lhs, rhs=rhs)
            nba.line, nba.col = lhs.line, lhs.col
            return nba

        # Might be a function call — skip to semicolon
        self._eat_if(TT.LPAREN)
        depth = 1 if self._peek(-1 if self._pos > 0 else 0).type == TT.LPAREN else 0
        if depth:
            while depth > 0 and self._peek().type != TT.EOF:
                t = self._advance()
                if t.type == TT.LPAREN:
                    depth += 1
                elif t.type == TT.RPAREN:
                    depth -= 1
        self._eat_if(TT.SEMICOLON)
        return None

    # ------------------------------------------------------------------
    # LValue
    # ------------------------------------------------------------------

    def _parse_lvalue(self) -> Node:
        tok = self._peek()

        if tok.type == TT.LBRACE:
            # Concatenation lvalue
            self._advance()
            parts: List[Node] = []
            while self._peek().type != TT.RBRACE and self._peek().type != TT.EOF:
                parts.append(self._parse_lvalue())
                self._eat_if(TT.COMMA)
            self._expect(TT.RBRACE)
            cc = ConcatExpr(parts=parts)
            cc.line, cc.col = tok.line, tok.col
            return cc

        name_tok = self._expect(TT.IDENT)
        node: Node = Identifier(name=name_tok.value, line=name_tok.line, col=name_tok.col)

        # Post-fix: indexing and slicing
        while self._peek().type == TT.LBRACKET:
            self._advance()
            idx = self._parse_expr()
            if self._eat_if(TT.COLON):
                lsb = self._parse_expr()
                self._expect(TT.RBRACKET)
                sl = SliceExpr(base=node, msb=idx, lsb=lsb)
                sl.line, sl.col = name_tok.line, name_tok.col
                node = sl
            else:
                self._expect(TT.RBRACKET)
                ie = IndexExpr(base=node, index=idx)
                ie.line, ie.col = name_tok.line, name_tok.col
                node = ie

        return node

    # ------------------------------------------------------------------
    # Expressions
    # ------------------------------------------------------------------

    def _parse_expr(self) -> Node:
        return self._parse_ternary()

    def _parse_ternary(self) -> Node:
        expr = self._parse_or_expr()
        if self._eat_if(TT.QUESTION):
            then_e = self._parse_ternary()
            self._expect(TT.COLON)
            else_e = self._parse_ternary()
            te = TernaryExpr(cond=expr, then_expr=then_e, else_expr=else_e)
            te.line, te.col = expr.line, expr.col
            return te
        return expr

    def _parse_or_expr(self) -> Node:
        left = self._parse_and_expr()
        while self._peek().type in (TT.OR, TT.PIPE):
            op_tok = self._advance()
            right = self._parse_and_expr()
            be = BinaryExpr(op=op_tok.value, left=left, right=right)
            be.line, be.col = left.line, left.col
            left = be
        return left

    def _parse_and_expr(self) -> Node:
        left = self._parse_eq_expr()
        while self._peek().type in (TT.AND, TT.AMPERSAND):
            op_tok = self._advance()
            right = self._parse_eq_expr()
            be = BinaryExpr(op=op_tok.value, left=left, right=right)
            be.line, be.col = left.line, left.col
            left = be
        return left

    def _parse_eq_expr(self) -> Node:
        left = self._parse_rel_expr()
        while self._peek().type in (TT.EQ, TT.NEQ):
            op_tok = self._advance()
            right = self._parse_rel_expr()
            be = BinaryExpr(op=op_tok.value, left=left, right=right)
            be.line, be.col = left.line, left.col
            left = be
        return left

    def _parse_rel_expr(self) -> Node:
        left = self._parse_shift_expr()
        while self._peek().type in (TT.LT, TT.GT, TT.GTE):
            # NB_ASSIGN (<= ) handled specially: it's NB in stmt context but LTE in expr
            op_tok = self._advance()
            right = self._parse_shift_expr()
            be = BinaryExpr(op=op_tok.value, left=left, right=right)
            be.line, be.col = left.line, left.col
            left = be
        # Handle <= as LTE in expression context
        while self._peek().type == TT.NB_ASSIGN:
            op_tok = self._advance()
            right = self._parse_shift_expr()
            be = BinaryExpr(op="<=", left=left, right=right)
            be.line, be.col = left.line, left.col
            left = be
        return left

    def _parse_shift_expr(self) -> Node:
        left = self._parse_add_expr()
        while self._peek().type in (TT.LSHIFT, TT.RSHIFT):
            op_tok = self._advance()
            right = self._parse_add_expr()
            be = BinaryExpr(op=op_tok.value, left=left, right=right)
            be.line, be.col = left.line, left.col
            left = be
        return left

    def _parse_add_expr(self) -> Node:
        left = self._parse_mul_expr()
        while self._peek().type in (TT.PLUS, TT.MINUS, TT.CARET, TT.PIPE):
            op_tok = self._advance()
            right = self._parse_mul_expr()
            be = BinaryExpr(op=op_tok.value, left=left, right=right)
            be.line, be.col = left.line, left.col
            left = be
        return left

    def _parse_mul_expr(self) -> Node:
        left = self._parse_unary()
        while self._peek().type in (TT.STAR, TT.SLASH, TT.PERCENT):
            op_tok = self._advance()
            right = self._parse_unary()
            be = BinaryExpr(op=op_tok.value, left=left, right=right)
            be.line, be.col = left.line, left.col
            left = be
        return left

    def _parse_unary(self) -> Node:
        tok = self._peek()
        if tok.type in (TT.BANG, TT.TILDE, TT.MINUS, TT.PLUS, TT.AMPERSAND, TT.PIPE, TT.CARET):
            self._advance()
            operand = self._parse_postfix()
            ue = UnaryExpr(op=tok.value, operand=operand)
            ue.line, ue.col = tok.line, tok.col
            return ue
        return self._parse_postfix()

    def _parse_postfix(self) -> Node:
        node = self._parse_primary()
        while True:
            if self._peek().type == TT.LBRACKET:
                self._advance()
                idx = self._parse_expr()
                if self._eat_if(TT.COLON):
                    lsb = self._parse_expr()
                    self._expect(TT.RBRACKET)
                    sl = SliceExpr(base=node, msb=idx, lsb=lsb)
                    sl.line, sl.col = node.line, node.col
                    node = sl
                else:
                    self._expect(TT.RBRACKET)
                    ie = IndexExpr(base=node, index=idx)
                    ie.line, ie.col = node.line, node.col
                    node = ie
            elif self._peek().type == TT.DOT:
                self._advance()
                field_tok = self._expect(TT.IDENT)
                # Treat as identifier (member access simplified)
                combined = f"{node.name if hasattr(node, 'name') else '?'}.{field_tok.value}"
                node = Identifier(name=combined, line=field_tok.line, col=field_tok.col)
            else:
                break
        return node

    def _parse_primary(self) -> Node:
        tok = self._peek()

        # Parenthesized expression
        if tok.type == TT.LPAREN:
            self._advance()
            expr = self._parse_expr()
            self._expect(TT.RPAREN)
            return expr

        # Concatenation or replication: {expr} or {N{expr}}
        if tok.type == TT.LBRACE:
            return self._parse_concat_or_replicate()

        # Number literal
        if tok.type == TT.NUMBER:
            return self._parse_number()

        # String
        if tok.type == TT.STRING:
            self._advance()
            n = NumberLiteral(raw=tok.value, bits=None, base='d', value=0)
            n.line, n.col = tok.line, tok.col
            return n

        # Identifier or system task
        if tok.type == TT.IDENT:
            self._advance()
            node: Node = Identifier(name=tok.value, line=tok.line, col=tok.col)
            # Function call
            if self._peek().type == TT.LPAREN:
                self._advance()
                args: List[Node] = []
                while self._peek().type != TT.RPAREN and self._peek().type != TT.EOF:
                    args.append(self._parse_expr())
                    self._eat_if(TT.COMMA)
                self._expect(TT.RPAREN)
                # Return first arg or identifier (simplified — we don't model function calls)
                if args:
                    return args[0]
            return node

        # Fallback
        self._advance()
        n = Identifier(name=tok.value, line=tok.line, col=tok.col)
        return n

    def _parse_concat_or_replicate(self) -> Node:
        tok = self._advance()  # {
        first = self._parse_expr()
        if self._peek().type == TT.LBRACE:
            # Replication: N{expr}
            self._advance()
            val = self._parse_expr()
            # Allow comma-separated inside replication
            inner_parts = [val]
            while self._eat_if(TT.COMMA):
                inner_parts.append(self._parse_expr())
            self._expect(TT.RBRACE)
            self._expect(TT.RBRACE)
            if len(inner_parts) == 1:
                rr = ReplicateExpr(count=first, value=val)
            else:
                cc = ConcatExpr(parts=inner_parts)
                cc.line, cc.col = tok.line, tok.col
                rr = ReplicateExpr(count=first, value=cc)
            rr.line, rr.col = tok.line, tok.col
            return rr
        else:
            parts = [first]
            while self._eat_if(TT.COMMA):
                parts.append(self._parse_expr())
            self._expect(TT.RBRACE)
            cc = ConcatExpr(parts=parts)
            cc.line, cc.col = tok.line, tok.col
            return cc

    def _parse_number(self) -> NumberLiteral:
        tok = self._advance()
        n = NumberLiteral(raw=tok.value)
        n.line, n.col = tok.line, tok.col

        raw = tok.value.replace("_", "")

        # Sized: 8'hFF or 8'shFF
        apos = raw.find("'")
        if apos >= 0:
            n.bits = int(raw[:apos]) if raw[:apos] else None
            rest = raw[apos + 1:]
            if rest and rest[0].lower() == 's':
                rest = rest[1:]
            if rest:
                base_char = rest[0].lower()
                digits = rest[1:] if len(rest) > 1 else "0"
                # Strip x/z/? to 0
                digits = re.sub(r'[xXzZ?]', '0', digits) or '0'
                n.base = base_char
                bases = {'b': 2, 'o': 8, 'd': 10, 'h': 16}
                base_num = bases.get(base_char, 10)
                try:
                    n.value = int(digits, base_num)
                except ValueError:
                    n.value = 0
        else:
            # Unsized decimal
            n.base = 'd'
            n.bits = None
            try:
                n.value = int(raw, 10)
            except ValueError:
                n.value = 0
        return n

    # ------------------------------------------------------------------
    # Module instantiation
    # ------------------------------------------------------------------

    def _parse_module_instantiation_or_stmt(self) -> Optional[Node]:
        """
        Heuristic: if we see IDENT (IDENT | #(...) IDENT) ( ... ) ; it's an instantiation.
        Otherwise try to parse as a statement.
        """
        save_pos = self._pos
        try:
            return self._parse_module_instance()
        except (ParseError, Exception):
            self._pos = save_pos
            # Try as a statement
            try:
                return self._parse_assignment_or_call()
            except Exception:
                self._pos = save_pos
                self._advance()  # skip
                return None

    def _parse_module_instance(self) -> ModuleInstance:
        mod_tok = self._expect(TT.IDENT)
        inst = ModuleInstance(module_name=mod_tok.value)
        inst.line, inst.col = mod_tok.line, mod_tok.col

        # Optional parameter overrides: #(.P1(v1), ...)
        if self._eat_if(TT.HASH):
            self._expect(TT.LPAREN)
            inst.param_overrides = self._parse_port_connections()
            self._expect(TT.RPAREN)

        # Instance name
        inst_name_tok = self._expect(TT.IDENT)
        inst.instance_name = inst_name_tok.value

        # Optional array of instances: inst_name [N:0]
        if self._peek().type == TT.LBRACKET:
            self._advance()
            self._parse_expr()
            self._eat_if(TT.COLON)
            self._parse_expr()
            self._expect(TT.RBRACKET)

        # Connections
        self._expect(TT.LPAREN)
        inst.connections = self._parse_port_connections()
        self._expect(TT.RPAREN)

        self._expect(TT.SEMICOLON)
        return inst

    def _parse_port_connections(self) -> List[PortConnection]:
        conns: List[PortConnection] = []
        while self._peek().type != TT.RPAREN and self._peek().type != TT.EOF:
            tok = self._peek()
            pc = PortConnection()
            pc.line, pc.col = tok.line, tok.col
            if tok.type == TT.DOT:
                self._advance()
                name_tok = self._expect(TT.IDENT)
                pc.port_name = name_tok.value
                if self._eat_if(TT.LPAREN):
                    if self._peek().type != TT.RPAREN:
                        pc.expr = self._parse_expr()
                    self._expect(TT.RPAREN)
            else:
                pc.expr = self._parse_expr()
            conns.append(pc)
            if not self._eat_if(TT.COMMA):
                break
        return conns

    # ------------------------------------------------------------------
    # Generate
    # ------------------------------------------------------------------

    def _parse_generate(self) -> GenerateBlock:
        kw_tok = self._expect_kw("generate")
        gb = GenerateBlock()
        gb.line, gb.col = kw_tok.line, kw_tok.col

        while not (self._is_kw("endgenerate") or self._peek().type == TT.EOF):
            self._skip_directives()
            if self._is_kw("endgenerate"):
                break
            item = self._parse_gen_item()
            if item is not None:
                gb.items.append(item)

        self._expect_kw("endgenerate")
        return gb

    def _parse_gen_item(self) -> Optional[Node]:
        if self._is_kw("for"):
            return self._parse_gen_for()
        if self._is_kw("if"):
            return self._parse_gen_if()
        if self._is_kw("begin"):
            return self._parse_begin_end()
        # Fall through to module_item
        return self._parse_module_item()

    def _parse_gen_for(self) -> GenFor:
        kw_tok = self._expect_kw("for")
        gf = GenFor()
        gf.line, gf.col = kw_tok.line, kw_tok.col

        self._expect(TT.LPAREN)

        # genvar decl inside for
        if self._is_kw("genvar"):
            self._advance()
        gv_tok = self._expect(TT.IDENT)
        gf.genvar = gv_tok.value
        self._expect(TT.ASSIGN)
        gf.init = self._parse_expr()
        self._expect(TT.SEMICOLON)
        gf.cond = self._parse_expr()
        self._expect(TT.SEMICOLON)
        gf.step = self._parse_assignment_raw()
        self._expect(TT.RPAREN)

        if self._is_kw("begin"):
            block = self._parse_begin_end()
            gf.items = block.stmts
        else:
            item = self._parse_gen_item()
            if item is not None:
                gf.items = [item]

        return gf

    def _parse_gen_if(self) -> GenIf:
        kw_tok = self._expect_kw("if")
        gi = GenIf()
        gi.line, gi.col = kw_tok.line, kw_tok.col

        self._expect(TT.LPAREN)
        gi.cond = self._parse_expr()
        self._expect(TT.RPAREN)

        if self._is_kw("begin"):
            block = self._parse_begin_end()
            gi.then_items = block.stmts
        else:
            item = self._parse_gen_item()
            if item is not None:
                gi.then_items = [item]

        if self._eat_kw("else"):
            if self._is_kw("begin"):
                block = self._parse_begin_end()
                gi.else_items = block.stmts
            else:
                item = self._parse_gen_item()
                if item is not None:
                    gi.else_items = [item]

        return gi

    def _parse_genvar_decl(self) -> Optional[Node]:
        self._expect_kw("genvar")
        while True:
            self._expect(TT.IDENT)
            if not self._eat_if(TT.COMMA):
                break
        self._expect(TT.SEMICOLON)
        return None

    # ------------------------------------------------------------------
    # Function / Task (skip)
    # ------------------------------------------------------------------

    def _skip_function_task(self) -> Optional[Node]:
        kw = self._advance().value  # function or task
        end_kw = "end" + kw
        depth = 1
        while depth > 0 and self._peek().type != TT.EOF:
            t = self._advance()
            if t.type == TT.IDENT and t.value == kw:
                depth += 1
            elif t.type == TT.IDENT and t.value == end_kw:
                depth -= 1
        # optional label
        if self._eat_if(TT.COLON):
            self._eat_if(TT.IDENT)
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(source: str, filename: str = "<string>") -> DesignUnit:
    """Lex and parse Verilog/SystemVerilog source; return a DesignUnit."""
    tokens = tokenize(source, filename)
    parser = Parser(tokens)
    return parser.parse(filename)


def parse_file(path: str) -> DesignUnit:
    """Read *path* and parse it."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()
    return parse(source, filename=path)
