"""
tests/test_st_parser.py — pytest oracles for the IEC 61131-3 ST parser.

Oracle checklist
----------------
1.  blinker.st parses to a non-empty AST (non-empty body + variables).
2.  conveyor.st has an IF/THEN/ELSE branch at top level.
3.  Variable declaration order is preserved.
4.  Round-trip: dump minimal source → re-parse → same structure (stable).
5.  TIME literal parses to Duration(ms=…) correctly.
6.  All VAR/VAR_INPUT/VAR_OUTPUT blocks are parsed.
7.  Nested IF (ELSIF) is parsed.
8.  FOR loop is parsed.
9.  WHILE loop is parsed.
10. REPEAT/UNTIL loop is parsed.
11. CASE statement is parsed.
12. ParseError is raised on bad syntax.
13. Function call with named args (FB call) is parsed.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from kerf_plc.st import parse, ParseError
from kerf_plc.st.ast import (
    POU,
    VarBlock,
    VarDecl,
    VarKind,
    SimpleType,
    ArrayType,
    Assignment,
    IfStmt,
    ForStmt,
    WhileStmt,
    RepeatStmt,
    CaseStmt,
    CallStmt,
    FunctionCall,
    BoolLiteral,
    IntLiteral,
    RealLiteral,
    StringLiteral,
    Duration,
    VarRef,
    FieldRef,
    BinaryOp,
    UnaryOp,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def parse_fixture(name: str) -> POU:
    return parse((FIXTURES / name).read_text())


# ---------------------------------------------------------------------------
# 1. blinker.st — non-empty AST
# ---------------------------------------------------------------------------

class TestBlinker:
    def test_parses_without_error(self):
        pou = parse_fixture("blinker.st")
        assert isinstance(pou, POU)

    def test_pou_name(self):
        pou = parse_fixture("blinker.st")
        assert pou.name == "Blinker"

    def test_body_non_empty(self):
        pou = parse_fixture("blinker.st")
        assert len(pou.body) > 0

    def test_var_block_present(self):
        pou = parse_fixture("blinker.st")
        assert len(pou.variables) > 0

    def test_has_three_variables(self):
        pou = parse_fixture("blinker.st")
        all_decls = pou.all_var_decls()
        names = [d.name for d in all_decls]
        assert "clock_in" in names
        assert "pulse_out" in names
        assert "t" in names


# ---------------------------------------------------------------------------
# 2. conveyor.st — IF/THEN/ELSE branch
# ---------------------------------------------------------------------------

class TestConveyor:
    def test_parses_without_error(self):
        pou = parse_fixture("conveyor.st")
        assert isinstance(pou, POU)

    def test_has_if_stmt(self):
        pou = parse_fixture("conveyor.st")
        assert pou.has_if(), "Expected at least one IfStmt in conveyor body"

    def test_if_has_else(self):
        pou = parse_fixture("conveyor.st")
        if_stmts = [s for s in pou.body if isinstance(s, IfStmt)]
        assert if_stmts
        # The conveyor IF should have an ELSE branch
        assert if_stmts[0].else_stmts is not None

    def test_var_input_block(self):
        pou = parse_fixture("conveyor.st")
        input_blocks = [b for b in pou.variables if b.kind == VarKind.VAR_INPUT]
        assert input_blocks, "Expected VAR_INPUT block"
        names = [d.name for d in input_blocks[0].declarations]
        assert "start_btn" in names
        assert "estop" in names

    def test_var_output_block(self):
        pou = parse_fixture("conveyor.st")
        output_blocks = [b for b in pou.variables if b.kind == VarKind.VAR_OUTPUT]
        assert output_blocks, "Expected VAR_OUTPUT block"
        names = [d.name for d in output_blocks[0].declarations]
        assert "motor_run" in names

    def test_elsif_clauses(self):
        pou = parse_fixture("conveyor.st")
        if_stmts = [s for s in pou.body if isinstance(s, IfStmt)]
        assert if_stmts[0].elsif_clauses, "Expected ELSIF clause(s)"


# ---------------------------------------------------------------------------
# 3. Variable declaration order preserved
# ---------------------------------------------------------------------------

class TestVarOrder:
    def test_blinker_var_order(self):
        pou = parse_fixture("blinker.st")
        names = [d.name for d in pou.all_var_decls()]
        ci = names.index("clock_in")
        po = names.index("pulse_out")
        t  = names.index("t")
        assert ci < po < t, f"Unexpected order: {names}"

    def test_conveyor_input_order(self):
        pou = parse_fixture("conveyor.st")
        input_blocks = [b for b in pou.variables if b.kind == VarKind.VAR_INPUT]
        names = [d.name for d in input_blocks[0].declarations]
        assert names.index("start_btn") < names.index("stop_btn") < names.index("estop")


# ---------------------------------------------------------------------------
# 4. Round-trip stability
# ---------------------------------------------------------------------------

def _minimal_source(pou: POU) -> str:
    """
    Produce a minimal but valid ST re-serialisation of *pou*.
    Only covers the constructs used by the fixtures.
    """
    lines: list[str] = []
    lines.append(f"{pou.pou_type} {pou.name}")

    for blk in pou.variables:
        lines.append(blk.kind)
        for d in blk.declarations:
            type_str = d.type.name if isinstance(d.type, SimpleType) else repr(d.type)
            lines.append(f"    {d.name} : {type_str};")
        lines.append("END_VAR")

    def emit_stmt(s, indent=""):
        if isinstance(s, Assignment):
            lhs = _expr_str(s.target)
            rhs = _expr_str(s.value)
            lines.append(f"{indent}{lhs} := {rhs};")
        elif isinstance(s, IfStmt):
            lines.append(f"{indent}IF {_expr_str(s.condition)} THEN")
            for sub in s.then_stmts:
                emit_stmt(sub, indent + "    ")
            for ec, eb in s.elsif_clauses:
                lines.append(f"{indent}ELSIF {_expr_str(ec)} THEN")
                for sub in eb:
                    emit_stmt(sub, indent + "    ")
            if s.else_stmts:
                lines.append(f"{indent}ELSE")
                for sub in s.else_stmts:
                    emit_stmt(sub, indent + "    ")
            lines.append(f"{indent}END_IF")
        elif isinstance(s, CallStmt):
            c = s.call
            named = ", ".join(f"{k} := {_expr_str(v)}" for k, v in c.named_args.items())
            positional = ", ".join(_expr_str(a) for a in c.args)
            args_str = ", ".join(filter(None, [positional, named]))
            lines.append(f"{indent}{c.name}({args_str});")
        else:
            lines.append(f"{indent}(* stmt *)")

    for stmt in pou.body:
        emit_stmt(stmt)

    end_kw = {"PROGRAM": "END_PROGRAM", "FUNCTION_BLOCK": "END_FUNCTION_BLOCK",
               "FUNCTION": "END_FUNCTION"}.get(pou.pou_type, "END_PROGRAM")
    lines.append(end_kw)
    return "\n".join(lines) + "\n"


def _expr_str(e) -> str:
    if isinstance(e, VarRef):
        return e.name
    if isinstance(e, FieldRef):
        return f"{_expr_str(e.obj)}.{e.field}"
    if isinstance(e, BoolLiteral):
        return "TRUE" if e.value else "FALSE"
    if isinstance(e, IntLiteral):
        return str(e.value)
    if isinstance(e, RealLiteral):
        return str(e.value)
    if isinstance(e, StringLiteral):
        return f"'{e.value}'"
    if isinstance(e, Duration):
        return f"T#{e.ms}ms"
    if isinstance(e, BinaryOp):
        return f"({_expr_str(e.left)} {e.op} {_expr_str(e.right)})"
    if isinstance(e, UnaryOp):
        return f"({e.op} {_expr_str(e.operand)})"
    if isinstance(e, FunctionCall):
        named = ", ".join(f"{k} := {_expr_str(v)}" for k, v in e.named_args.items())
        positional = ", ".join(_expr_str(a) for a in e.args)
        args_str = ", ".join(filter(None, [positional, named]))
        return f"{e.name}({args_str})"
    return repr(e)


class TestRoundTrip:
    def _do_round_trip(self, name: str) -> tuple[POU, POU]:
        pou1 = parse_fixture(name)
        src2 = _minimal_source(pou1)
        pou2 = parse(src2)
        return pou1, pou2

    def test_blinker_var_count_stable(self):
        p1, p2 = self._do_round_trip("blinker.st")
        assert len(p1.all_var_decls()) == len(p2.all_var_decls())

    def test_blinker_stmt_count_stable(self):
        p1, p2 = self._do_round_trip("blinker.st")
        assert len(p1.body) == len(p2.body)

    def test_blinker_var_names_stable(self):
        p1, p2 = self._do_round_trip("blinker.st")
        names1 = [d.name for d in p1.all_var_decls()]
        names2 = [d.name for d in p2.all_var_decls()]
        assert names1 == names2

    def test_conveyor_stmt_count_stable(self):
        p1, p2 = self._do_round_trip("conveyor.st")
        assert len(p1.body) == len(p2.body)


# ---------------------------------------------------------------------------
# 5. TIME literal → Duration
# ---------------------------------------------------------------------------

class TestTimeLiteral:
    def _parse_time_expr(self, src: str) -> Duration:
        prog = textwrap.dedent(f"""\
            PROGRAM P
            VAR x : TIME; END_VAR
            x := {src};
            END_PROGRAM
        """)
        pou = parse(prog)
        assign = pou.body[0]
        assert isinstance(assign, Assignment)
        assert isinstance(assign.value, Duration)
        return assign.value

    def test_milliseconds(self):
        d = self._parse_time_expr("T#100ms")
        assert d.ms == 100

    def test_seconds(self):
        d = self._parse_time_expr("T#5s")
        assert d.ms == 5000

    def test_minutes(self):
        d = self._parse_time_expr("T#1m")
        assert d.ms == 60_000

    def test_combined(self):
        d = self._parse_time_expr("T#1s500ms")
        assert d.ms == 1500

    def test_hours(self):
        d = self._parse_time_expr("T#2h")
        assert d.ms == 7_200_000

    def test_from_parts_helper(self):
        d = Duration.from_parts(seconds=1)
        assert d.ms == 1000

    def test_from_parts_combined(self):
        d = Duration.from_parts(minutes=1, seconds=30)
        assert d.ms == 90_000


# ---------------------------------------------------------------------------
# 6. VAR_INPUT / VAR_OUTPUT blocks
# ---------------------------------------------------------------------------

class TestVarBlocks:
    def test_var_input_kind(self):
        src = textwrap.dedent("""\
            FUNCTION_BLOCK FB
            VAR_INPUT
                x : INT;
            END_VAR
            END_FUNCTION_BLOCK
        """)
        pou = parse(src)
        assert pou.variables[0].kind == VarKind.VAR_INPUT

    def test_var_output_kind(self):
        src = textwrap.dedent("""\
            FUNCTION_BLOCK FB
            VAR_OUTPUT
                y : BOOL;
            END_VAR
            END_FUNCTION_BLOCK
        """)
        pou = parse(src)
        assert pou.variables[0].kind == VarKind.VAR_OUTPUT

    def test_array_type_parsed(self):
        src = textwrap.dedent("""\
            PROGRAM P
            VAR
                buf : ARRAY [1..10] OF INT;
            END_VAR
            END_PROGRAM
        """)
        pou = parse(src)
        decl = pou.variables[0].declarations[0]
        assert isinstance(decl.type, ArrayType)
        assert decl.type.lower == 1
        assert decl.type.upper == 10
        assert decl.type.elem_type.name == "INT"


# ---------------------------------------------------------------------------
# 7. ELSIF is parsed
# ---------------------------------------------------------------------------

class TestElsif:
    def test_elsif_count(self):
        src = textwrap.dedent("""\
            PROGRAM P
            VAR x : INT; END_VAR
            IF x = 1 THEN
                x := 10;
            ELSIF x = 2 THEN
                x := 20;
            ELSIF x = 3 THEN
                x := 30;
            ELSE
                x := 0;
            END_IF
            END_PROGRAM
        """)
        pou = parse(src)
        if_s = pou.body[0]
        assert isinstance(if_s, IfStmt)
        assert len(if_s.elsif_clauses) == 2


# ---------------------------------------------------------------------------
# 8. FOR loop
# ---------------------------------------------------------------------------

class TestFor:
    def test_for_loop_parsed(self):
        src = textwrap.dedent("""\
            PROGRAM P
            VAR i : INT; END_VAR
            FOR i := 1 TO 10 DO
                i := i + 1;
            END_FOR
            END_PROGRAM
        """)
        pou = parse(src)
        for_s = pou.body[0]
        assert isinstance(for_s, ForStmt)
        assert for_s.variable == "i"
        assert isinstance(for_s.from_expr, IntLiteral)
        assert for_s.from_expr.value == 1
        assert isinstance(for_s.to_expr, IntLiteral)
        assert for_s.to_expr.value == 10

    def test_for_by_clause(self):
        src = textwrap.dedent("""\
            PROGRAM P
            VAR i : INT; END_VAR
            FOR i := 0 TO 100 BY 5 DO
            END_FOR
            END_PROGRAM
        """)
        pou = parse(src)
        for_s = pou.body[0]
        assert isinstance(for_s, ForStmt)
        assert isinstance(for_s.by_expr, IntLiteral)
        assert for_s.by_expr.value == 5


# ---------------------------------------------------------------------------
# 9. WHILE loop
# ---------------------------------------------------------------------------

class TestWhile:
    def test_while_parsed(self):
        src = textwrap.dedent("""\
            PROGRAM P
            VAR running : BOOL; END_VAR
            WHILE running DO
                running := FALSE;
            END_WHILE
            END_PROGRAM
        """)
        pou = parse(src)
        while_s = pou.body[0]
        assert isinstance(while_s, WhileStmt)
        assert len(while_s.body) == 1


# ---------------------------------------------------------------------------
# 10. REPEAT/UNTIL loop
# ---------------------------------------------------------------------------

class TestRepeat:
    def test_repeat_parsed(self):
        src = textwrap.dedent("""\
            PROGRAM P
            VAR x : INT; END_VAR
            REPEAT
                x := x + 1;
            UNTIL x >= 10
            END_REPEAT
            END_PROGRAM
        """)
        pou = parse(src)
        rep_s = pou.body[0]
        assert isinstance(rep_s, RepeatStmt)
        assert len(rep_s.body) == 1
        assert isinstance(rep_s.until_condition, BinaryOp)
        assert rep_s.until_condition.op == ">="


# ---------------------------------------------------------------------------
# 11. CASE statement
# ---------------------------------------------------------------------------

class TestCase:
    def test_case_parsed(self):
        src = textwrap.dedent("""\
            PROGRAM P
            VAR state : INT; y : INT; END_VAR
            CASE state OF
                1: y := 10;
                2: y := 20;
                ELSE y := 0;
            END_CASE
            END_PROGRAM
        """)
        pou = parse(src)
        case_s = pou.body[0]
        assert isinstance(case_s, CaseStmt)
        assert len(case_s.clauses) == 2
        assert len(case_s.else_stmts) == 1


# ---------------------------------------------------------------------------
# 12. ParseError on bad syntax
# ---------------------------------------------------------------------------

class TestErrors:
    def test_missing_end_program(self):
        with pytest.raises(ParseError):
            parse("PROGRAM P VAR x : INT; END_VAR x := 1;")

    def test_missing_end_var(self):
        with pytest.raises(ParseError):
            parse("PROGRAM P\nVAR x : INT;\nEND_PROGRAM")

    def test_empty_source(self):
        with pytest.raises(ParseError):
            parse("")

    def test_unknown_token(self):
        with pytest.raises((ParseError, Exception)):
            parse("PROGRAM P\nVAR END_VAR\n@ := 1;\nEND_PROGRAM")


# ---------------------------------------------------------------------------
# 13. Named FB call (t(IN := ..., PT := ...))
# ---------------------------------------------------------------------------

class TestFBCall:
    def test_named_args_parsed(self):
        src = textwrap.dedent("""\
            FUNCTION_BLOCK Blinker
            VAR
                clock_in : BOOL;
                t : TON;
            END_VAR
            t(IN := clock_in, PT := T#1s);
            END_FUNCTION_BLOCK
        """)
        pou = parse(src)
        stmt = pou.body[0]
        assert isinstance(stmt, CallStmt)
        fc = stmt.call
        assert fc.name == "t"
        assert "IN" in fc.named_args
        assert "PT" in fc.named_args
        assert isinstance(fc.named_args["PT"], Duration)
        assert fc.named_args["PT"].ms == 1000

    def test_field_ref_on_fb(self):
        """pulse_out := t.Q  should parse to FieldRef."""
        src = textwrap.dedent("""\
            FUNCTION_BLOCK Blinker
            VAR
                pulse_out : BOOL;
                t : TON;
            END_VAR
            pulse_out := t.Q;
            END_FUNCTION_BLOCK
        """)
        pou = parse(src)
        stmt = pou.body[0]
        assert isinstance(stmt, Assignment)
        assert isinstance(stmt.value, FieldRef)
        assert stmt.value.field == "Q"
