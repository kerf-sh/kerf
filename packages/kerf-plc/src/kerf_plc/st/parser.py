"""
kerf_plc.st.parser — IEC 61131-3 Structured Text recursive-descent parser.

Entry point::

    pou = parse(source_text)   # returns ast.POU

Raises ``ParseError`` on syntax errors.
"""

from __future__ import annotations

import re
from typing import Optional

from kerf_plc.st.lexer import Token, tokenise, LexError
from kerf_plc.st import ast as A


# ---------------------------------------------------------------------------
# Error
# ---------------------------------------------------------------------------

class ParseError(Exception):
    def __init__(self, msg: str, line: int = 0, col: int = 0) -> None:
        loc = f" at line {line}:{col}" if line else ""
        super().__init__(f"ParseError{loc}: {msg}")
        self.line = line
        self.col = col


# ---------------------------------------------------------------------------
# TIME literal parser
# ---------------------------------------------------------------------------

_TIME_PART_RE = re.compile(
    r"(?:(?P<d>[0-9]+(?:\.[0-9]+)?)d)?"
    r"(?:(?P<h>[0-9]+(?:\.[0-9]+)?)h)?"
    r"(?:(?P<m>[0-9]+(?:\.[0-9]+)?)m(?!s))?"
    r"(?:(?P<s>[0-9]+(?:\.[0-9]+)?)s)?"
    r"(?:(?P<ms>[0-9]+(?:\.[0-9]+)?)ms)?",
    re.IGNORECASE,
)


def _parse_time_literal(raw: str) -> A.Duration:
    """Convert T#5s300ms → Duration(ms=5300)."""
    # Strip prefix T# or TIME#
    body = re.sub(r"^(?:T|TIME)#", "", raw, flags=re.IGNORECASE)
    total_ms = 0.0
    # Scan for each unit
    for m in re.finditer(r"([0-9]+(?:\.[0-9]+)?)(d|h|ms|m|s)", body, re.IGNORECASE):
        val = float(m.group(1))
        unit = m.group(2).lower()
        if unit == "d":
            total_ms += val * 86_400_000
        elif unit == "h":
            total_ms += val * 3_600_000
        elif unit == "m":
            total_ms += val * 60_000
        elif unit == "s":
            total_ms += val * 1_000
        elif unit == "ms":
            total_ms += val
    return A.Duration(ms=int(total_ms))


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    # ── low-level helpers ──────────────────────────────────────────────────

    def _peek(self) -> Token:
        return self._tokens[self._pos]

    def _peek2(self) -> Token:
        p = self._pos + 1
        if p < len(self._tokens):
            return self._tokens[p]
        return self._tokens[-1]  # EOF

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        if self._pos + 1 < len(self._tokens):
            self._pos += 1
        return tok

    def _check_kw(self, *kws: str) -> bool:
        t = self._peek()
        return t.type == "KEYWORD" and t.value in kws

    def _check_op(self, op: str) -> bool:
        t = self._peek()
        return t.type == "OPERATOR" and t.value == op

    def _expect_kw(self, *kws: str) -> Token:
        t = self._peek()
        if t.type != "KEYWORD" or t.value not in kws:
            raise ParseError(
                f"Expected keyword {' or '.join(kws)!r}, got {t.value!r}",
                t.line, t.col,
            )
        return self._advance()

    def _expect_op(self, op: str) -> Token:
        t = self._peek()
        if t.type != "OPERATOR" or t.value != op:
            raise ParseError(
                f"Expected {op!r}, got {t.value!r}", t.line, t.col
            )
        return self._advance()

    def _expect_ident(self) -> str:
        t = self._peek()
        if t.type != "IDENT":
            raise ParseError(
                f"Expected identifier, got {t.value!r}", t.line, t.col
            )
        self._advance()
        return t.value

    # ── POU ───────────────────────────────────────────────────────────────

    def parse_pou(self) -> A.POU:
        """Parse PROGRAM / FUNCTION_BLOCK / FUNCTION ... END_xxx."""
        t = self._peek()
        if t.type != "KEYWORD" or t.value not in ("PROGRAM", "FUNCTION_BLOCK", "FUNCTION"):
            raise ParseError(
                "Expected PROGRAM, FUNCTION_BLOCK, or FUNCTION", t.line, t.col
            )
        pou_type = self._advance().value
        name = self._expect_ident()

        # For FUNCTION, optional return type: FUNCTION Foo : BOOL
        if pou_type == "FUNCTION" and self._check_op(":"):
            self._advance()  # consume ':'
            self._parse_type()   # return type — discard for now

        var_blocks: list[A.VarBlock] = []
        while self._check_kw("VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT",
                              "VAR_TEMP", "VAR_EXTERNAL"):
            var_blocks.append(self._parse_var_block())

        body: list[A.Statement] = []
        end_kw = {"PROGRAM": "END_PROGRAM",
                  "FUNCTION_BLOCK": "END_FUNCTION_BLOCK",
                  "FUNCTION": "END_FUNCTION"}[pou_type]

        while not self._check_kw(end_kw):
            if self._peek().type == "EOF":
                raise ParseError(f"Unexpected EOF, expected {end_kw}")
            stmt = self._parse_statement()
            if stmt is not None:
                body.append(stmt)

        self._expect_kw(end_kw)
        return A.POU(name=name, pou_type=pou_type, variables=var_blocks, body=body)

    # ── VAR block ─────────────────────────────────────────────────────────

    def _parse_var_block(self) -> A.VarBlock:
        kind_kw = self._advance()  # VAR / VAR_INPUT / …
        kind = kind_kw.value       # already uppercased by lexer

        # Optional RETAIN / CONSTANT / NON_RETAIN qualifier — ignore
        while self._check_kw("RETAIN", "CONSTANT", "NON_RETAIN"):
            self._advance()

        decls: list[A.VarDecl] = []
        while not self._check_kw("END_VAR"):
            if self._peek().type == "EOF":
                raise ParseError("Unexpected EOF in VAR block")
            decls.extend(self._parse_var_decl_line())

        self._expect_kw("END_VAR")
        return A.VarBlock(kind=kind, declarations=decls)

    def _parse_var_decl_line(self) -> list[A.VarDecl]:
        """name {, name} : type [:= init_expr] ;"""
        names: list[str] = []
        names.append(self._expect_ident())
        while self._check_op(","):
            self._advance()
            names.append(self._expect_ident())
        self._expect_op(":")
        type_spec = self._parse_type()

        init: Optional[A.Expression] = None
        if self._check_op(":="):
            self._advance()
            init = self._parse_expression()

        # Semicolon is optional inside AT declarations and sometimes omitted
        if self._check_op(";"):
            self._advance()

        return [A.VarDecl(name=n, type=type_spec, initial_value=init) for n in names]

    def _parse_type(self) -> A.TypeSpec:
        """Parse a type specifier."""
        if self._check_kw("ARRAY"):
            return self._parse_array_type()

        t = self._peek()
        # Accept any keyword that looks like a type name or an identifier
        if t.type in ("KEYWORD", "IDENT"):
            self._advance()
            return A.SimpleType(name=t.value)

        raise ParseError(f"Expected type, got {t.value!r}", t.line, t.col)

    def _parse_array_type(self) -> A.ArrayType:
        """ARRAY [ lower .. upper ] OF elem_type"""
        self._expect_kw("ARRAY")
        self._expect_op("[")
        lower_tok = self._peek()
        lower = int(self._advance().value)
        self._expect_op("..")
        upper = int(self._advance().value)
        self._expect_op("]")
        self._expect_kw("OF")
        elem = self._parse_type()
        return A.ArrayType(elem_type=elem, lower=lower, upper=upper)

    # ── Statements ────────────────────────────────────────────────────────

    def _parse_statement(self) -> Optional[A.Statement]:
        t = self._peek()

        if t.type == "KEYWORD":
            kw = t.value
            if kw == "IF":
                return self._parse_if()
            if kw == "FOR":
                return self._parse_for()
            if kw == "WHILE":
                return self._parse_while()
            if kw == "REPEAT":
                return self._parse_repeat()
            if kw == "CASE":
                return self._parse_case()
            if kw in ("RETURN", "EXIT", "CONTINUE"):
                self._advance()
                if self._check_op(";"):
                    self._advance()
                return None  # drop control-flow keywords for now
            # Fall through — might be a function call acting as statement
            return self._parse_assign_or_call()

        if t.type == "IDENT":
            return self._parse_assign_or_call()

        # Skip stray semicolons
        if t.type == "OPERATOR" and t.value == ";":
            self._advance()
            return None

        raise ParseError(f"Unexpected token {t.value!r}", t.line, t.col)

    def _parse_assign_or_call(self) -> A.Statement:
        """Parse either  target := expr;  or  FuncCall(...);"""
        lhs = self._parse_postfix()

        if self._check_op(":="):
            self._advance()
            rhs = self._parse_expression()
            if self._check_op(";"):
                self._advance()
            return A.Assignment(target=lhs, value=rhs)

        # It must be a standalone function/FB call
        if isinstance(lhs, A.FunctionCall):
            if self._check_op(";"):
                self._advance()
            return A.CallStmt(call=lhs)

        # Otherwise treat as call (e.g. bare FB call without parens like t(...) already parsed)
        if self._check_op(";"):
            self._advance()
        if isinstance(lhs, A.FunctionCall):
            return A.CallStmt(call=lhs)
        # Wrap var ref as a degenerate call
        if isinstance(lhs, A.VarRef):
            return A.CallStmt(call=A.FunctionCall(name=lhs.name))
        raise ParseError(f"Cannot form statement from {lhs!r}")

    def _parse_if(self) -> A.IfStmt:
        self._expect_kw("IF")
        cond = self._parse_expression()
        self._expect_kw("THEN")
        then_body = self._parse_stmt_list("ELSIF", "ELSE", "END_IF")
        elsif_clauses: list[tuple[A.Expression, list[A.Statement]]] = []
        while self._check_kw("ELSIF"):
            self._advance()
            ec = self._parse_expression()
            self._expect_kw("THEN")
            eb = self._parse_stmt_list("ELSIF", "ELSE", "END_IF")
            elsif_clauses.append((ec, eb))
        else_body: list[A.Statement] = []
        if self._check_kw("ELSE"):
            self._advance()
            else_body = self._parse_stmt_list("END_IF")
        self._expect_kw("END_IF")
        if self._check_op(";"):
            self._advance()
        return A.IfStmt(
            condition=cond,
            then_stmts=then_body,
            elsif_clauses=elsif_clauses,
            else_stmts=else_body,
        )

    def _parse_for(self) -> A.ForStmt:
        self._expect_kw("FOR")
        var = self._expect_ident()
        self._expect_op(":=")
        from_e = self._parse_expression()
        self._expect_kw("TO")
        to_e = self._parse_expression()
        by_e: Optional[A.Expression] = None
        if self._check_kw("BY"):
            self._advance()
            by_e = self._parse_expression()
        self._expect_kw("DO")
        body = self._parse_stmt_list("END_FOR")
        self._expect_kw("END_FOR")
        if self._check_op(";"):
            self._advance()
        return A.ForStmt(variable=var, from_expr=from_e, to_expr=to_e, by_expr=by_e, body=body)

    def _parse_while(self) -> A.WhileStmt:
        self._expect_kw("WHILE")
        cond = self._parse_expression()
        self._expect_kw("DO")
        body = self._parse_stmt_list("END_WHILE")
        self._expect_kw("END_WHILE")
        if self._check_op(";"):
            self._advance()
        return A.WhileStmt(condition=cond, body=body)

    def _parse_repeat(self) -> A.RepeatStmt:
        self._expect_kw("REPEAT")
        body = self._parse_stmt_list("UNTIL")
        self._expect_kw("UNTIL")
        cond = self._parse_expression()
        if self._check_op(";"):
            self._advance()
        self._expect_kw("END_REPEAT")
        if self._check_op(";"):
            self._advance()
        return A.RepeatStmt(body=body, until_condition=cond)

    def _is_case_label_start(self) -> bool:
        """
        Return True if the current position looks like the start of a new CASE
        clause label: an integer, identifier, or TRUE/FALSE immediately followed
        (after possible commas) by a colon that is NOT ':='.
        """
        t = self._peek()
        if t.type in ("INTEGER", "IDENT", "BOOL_TRUE", "BOOL_FALSE"):
            # Scan ahead: skip integers/idents/commas until we find a ':' that
            # is not ':=' or until we hit something unexpected.
            saved = self._pos
            try:
                while True:
                    tok = self._peek()
                    if tok.type in ("INTEGER", "IDENT", "BOOL_TRUE", "BOOL_FALSE"):
                        self._advance()
                    elif tok.type == "OPERATOR" and tok.value == ",":
                        self._advance()
                    elif tok.type == "OPERATOR" and tok.value == ":":
                        return True
                    else:
                        return False
            finally:
                self._pos = saved
        return False

    def _parse_case(self) -> A.CaseStmt:
        self._expect_kw("CASE")
        selector = self._parse_expression()
        self._expect_kw("OF")
        clauses: list[A.CaseClause] = []
        else_stmts: list[A.Statement] = []

        while not self._check_kw("END_CASE"):
            if self._peek().type == "EOF":
                raise ParseError("Unexpected EOF in CASE")
            if self._check_kw("ELSE"):
                self._advance()
                else_stmts = self._parse_case_body()
                break
            # Parse case label(s): value {, value} :
            vals: list[A.Expression] = [self._parse_expression()]
            while self._check_op(","):
                self._advance()
                vals.append(self._parse_expression())
            self._expect_op(":")
            stmts = self._parse_case_body()
            clauses.append(A.CaseClause(values=vals, stmts=stmts))

        self._expect_kw("END_CASE")
        if self._check_op(";"):
            self._advance()
        return A.CaseStmt(selector=selector, clauses=clauses, else_stmts=else_stmts)

    def _parse_case_body(self) -> list[A.Statement]:
        """
        Parse statements within a CASE clause body.
        Stop before: ELSE keyword, END_CASE keyword, or a new case label
        (integer/ident/TRUE/FALSE immediately followed by ':').
        """
        stmts: list[A.Statement] = []
        while True:
            t = self._peek()
            if t.type == "EOF":
                break
            if t.type == "KEYWORD" and t.value in ("ELSE", "END_CASE"):
                break
            if self._is_case_label_start():
                break
            stmt = self._parse_statement()
            if stmt is not None:
                stmts.append(stmt)
        return stmts

    def _parse_stmt_list(self, *stop_kws: str) -> list[A.Statement]:
        """Parse statements until one of the stop keywords is seen."""
        stmts: list[A.Statement] = []
        while True:
            t = self._peek()
            if t.type == "EOF":
                break
            if t.type == "KEYWORD" and t.value in stop_kws:
                break
            stmt = self._parse_statement()
            if stmt is not None:
                stmts.append(stmt)
        return stmts

    # ── Expressions ───────────────────────────────────────────────────────
    # Precedence (low → high):
    #   OR XOR  →  AND  →  NOT  →  comparison  →  add/sub  →  mul/div/mod  →  unary -  →  postfix/primary

    def _parse_expression(self) -> A.Expression:
        return self._parse_or()

    def _parse_or(self) -> A.Expression:
        left = self._parse_and()
        while self._check_kw("OR", "XOR"):
            op = self._advance().value
            right = self._parse_and()
            left = A.BinaryOp(op=op, left=left, right=right)
        return left

    def _parse_and(self) -> A.Expression:
        left = self._parse_not()
        while self._check_kw("AND") or (self._peek().type == "OPERATOR" and self._peek().value == "&"):
            op = self._advance().value
            if op == "&":
                op = "AND"
            right = self._parse_not()
            left = A.BinaryOp(op=op, left=left, right=right)
        return left

    def _parse_not(self) -> A.Expression:
        if self._check_kw("NOT"):
            self._advance()
            operand = self._parse_comparison()
            return A.UnaryOp(op="NOT", operand=operand)
        return self._parse_comparison()

    def _parse_comparison(self) -> A.Expression:
        left = self._parse_additive()
        _cmp_ops = {"=", "<>", "<", ">", "<=", ">="}
        while self._peek().type == "OPERATOR" and self._peek().value in _cmp_ops:
            op = self._advance().value
            right = self._parse_additive()
            left = A.BinaryOp(op=op, left=left, right=right)
        return left

    def _parse_additive(self) -> A.Expression:
        left = self._parse_multiplicative()
        while self._peek().type == "OPERATOR" and self._peek().value in ("+", "-"):
            op = self._advance().value
            right = self._parse_multiplicative()
            left = A.BinaryOp(op=op, left=left, right=right)
        return left

    def _parse_multiplicative(self) -> A.Expression:
        left = self._parse_unary()
        while (
            (self._peek().type == "OPERATOR" and self._peek().value in ("*", "/"))
            or self._check_kw("MOD")
        ):
            op = self._advance().value
            right = self._parse_unary()
            left = A.BinaryOp(op=op, left=left, right=right)
        return left

    def _parse_unary(self) -> A.Expression:
        if self._peek().type == "OPERATOR" and self._peek().value == "-":
            self._advance()
            operand = self._parse_postfix()
            return A.UnaryOp(op="-", operand=operand)
        return self._parse_postfix()

    def _parse_postfix(self) -> A.Expression:
        """Handle function calls and field access: foo(...), obj.field"""
        node = self._parse_primary()

        while True:
            if self._check_op("(") and isinstance(node, A.VarRef):
                # Function/FB call
                node = self._parse_call_args(node.name)
            elif self._check_op("."):
                self._advance()
                fname = self._expect_ident()
                if self._check_op("(") and isinstance(node, A.VarRef):
                    # Method call: obj.method(...)
                    inner = self._parse_call_args(f"{node.name}.{fname}")
                    node = inner
                else:
                    node = A.FieldRef(obj=node, field=fname)
            else:
                break
        return node

    def _parse_call_args(self, name: str) -> A.FunctionCall:
        """Parse ( [arg {, arg}] ) possibly with named params a := expr."""
        self._expect_op("(")
        args: list[A.Expression] = []
        named: dict[str, A.Expression] = {}

        while not self._check_op(")"):
            if self._peek().type == "EOF":
                raise ParseError("Unexpected EOF in function call")
            # Peek ahead for  name :=  pattern (named arg)
            if self._peek().type == "IDENT" and self._peek2().type == "OPERATOR" and self._peek2().value == ":=":
                param_name = self._expect_ident()
                self._expect_op(":=")
                val = self._parse_expression()
                named[param_name] = val
            else:
                args.append(self._parse_expression())
            if not self._check_op(")"):
                self._expect_op(",")

        self._expect_op(")")
        return A.FunctionCall(name=name, args=args, named_args=named)

    def _parse_primary(self) -> A.Expression:
        t = self._peek()

        # Parenthesised expression
        if t.type == "OPERATOR" and t.value == "(":
            self._advance()
            expr = self._parse_expression()
            self._expect_op(")")
            return expr

        # Boolean literals
        if t.type == "BOOL_TRUE":
            self._advance()
            return A.BoolLiteral(value=True)
        if t.type == "BOOL_FALSE":
            self._advance()
            return A.BoolLiteral(value=False)

        # TIME literal
        if t.type == "TIME_LIT":
            self._advance()
            return _parse_time_literal(t.value)

        # String literal
        if t.type == "STRING":
            self._advance()
            # Strip surrounding quotes
            return A.StringLiteral(value=t.value[1:-1])

        # Real literal
        if t.type == "REAL":
            self._advance()
            return A.RealLiteral(value=float(t.value.replace("_", "")))

        # Integer literal
        if t.type == "INTEGER":
            self._advance()
            return A.IntLiteral(value=int(t.value.replace("_", "")))

        # Identifier (variable reference — may become function call in postfix)
        if t.type == "IDENT":
            self._advance()
            return A.VarRef(name=t.value)

        raise ParseError(f"Unexpected token {t.value!r}", t.line, t.col)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse(source: str) -> A.POU:
    """
    Parse *source* (a complete IEC 61131-3 ST POU) and return an ``ast.POU``.

    Raises ``ParseError`` on syntax errors.
    """
    try:
        tokens = tokenise(source)
    except LexError as exc:
        raise ParseError(str(exc), exc.line, exc.col) from exc

    p = _Parser(tokens)
    return p.parse_pou()
