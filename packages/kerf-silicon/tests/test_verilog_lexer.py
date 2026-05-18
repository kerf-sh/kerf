"""
Tests for kerf_silicon.verilog.lexer — synthesizable Verilog/SV token stream.
"""
import pytest
from kerf_silicon.verilog.lexer import TT, LexError, Token, tokenize, is_keyword


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def tok_types(source: str) -> list[TT]:
    return [t.type for t in tokenize(source) if t.type != TT.EOF]


def tok_values(source: str) -> list[str]:
    return [t.value for t in tokenize(source) if t.type != TT.EOF]


# ---------------------------------------------------------------------------
# Basic tokens
# ---------------------------------------------------------------------------

class TestBasicTokens:
    def test_empty_gives_only_eof(self):
        tokens = tokenize("")
        assert len(tokens) == 1
        assert tokens[0].type == TT.EOF

    def test_whitespace_skipped(self):
        tokens = [t for t in tokenize("   \t\n  ") if t.type != TT.EOF]
        assert tokens == []

    def test_line_comment_skipped(self):
        tokens = [t for t in tokenize("// this is a comment\n") if t.type != TT.EOF]
        assert tokens == []

    def test_block_comment_skipped(self):
        tokens = [t for t in tokenize("/* block */") if t.type != TT.EOF]
        assert tokens == []

    def test_identifier(self):
        tokens = [t for t in tokenize("my_signal") if t.type != TT.EOF]
        assert len(tokens) == 1
        assert tokens[0].type == TT.IDENT
        assert tokens[0].value == "my_signal"

    def test_keyword_is_ident_token(self):
        # Keywords are emitted as IDENT — is_keyword() distinguishes them
        tokens = [t for t in tokenize("module") if t.type != TT.EOF]
        assert len(tokens) == 1
        assert tokens[0].type == TT.IDENT
        assert is_keyword(tokens[0])

    def test_non_keyword_ident_not_keyword(self):
        tokens = [t for t in tokenize("my_wire") if t.type != TT.EOF]
        assert not is_keyword(tokens[0])


# ---------------------------------------------------------------------------
# Numeric literals
# ---------------------------------------------------------------------------

class TestNumericLiterals:
    def test_unsized_decimal(self):
        toks = tokenize("42")
        assert toks[0].type == TT.NUMBER
        assert toks[0].value == "42"

    def test_hex_literal(self):
        toks = tokenize("8'hAA")
        assert toks[0].type == TT.NUMBER
        assert toks[0].value == "8'hAA"

    def test_hex_literal_lowercase(self):
        toks = tokenize("8'haa")
        assert toks[0].type == TT.NUMBER

    def test_binary_literal(self):
        toks = tokenize("4'b1010")
        assert toks[0].type == TT.NUMBER
        assert toks[0].value == "4'b1010"

    def test_decimal_sized(self):
        toks = tokenize("8'd255")
        assert toks[0].type == TT.NUMBER

    def test_octal_literal(self):
        toks = tokenize("6'o77")
        assert toks[0].type == TT.NUMBER

    def test_number_with_underscore(self):
        toks = tokenize("16'h_FF_FF")
        assert toks[0].type == TT.NUMBER

    def test_zero_literal(self):
        toks = tokenize("0")
        assert toks[0].type == TT.NUMBER
        assert toks[0].value == "0"


# ---------------------------------------------------------------------------
# Operators / punctuation
# ---------------------------------------------------------------------------

class TestOperators:
    def test_blocking_assign(self):
        assert TT.ASSIGN in tok_types("a = b")

    def test_non_blocking_assign(self):
        assert TT.NB_ASSIGN in tok_types("a <= b")

    def test_semicolon(self):
        assert TT.SEMICOLON in tok_types(";")

    def test_comma(self):
        assert TT.COMMA in tok_types(",")

    def test_lbracket_rbracket(self):
        types = tok_types("[7:0]")
        assert TT.LBRACKET in types
        assert TT.RBRACKET in types
        assert TT.COLON in types

    def test_hash(self):
        assert TT.HASH in tok_types("#")

    def test_at(self):
        assert TT.AT in tok_types("@")

    def test_dot(self):
        assert TT.DOT in tok_types(".")

    def test_eq_operator(self):
        assert TT.EQ in tok_types("a == b")

    def test_neq_operator(self):
        assert TT.NEQ in tok_types("a != b")

    def test_lshift(self):
        assert TT.LSHIFT in tok_types("a << 2")

    def test_rshift(self):
        assert TT.RSHIFT in tok_types("a >> 1")

    def test_logical_and(self):
        assert TT.AND in tok_types("a && b")

    def test_logical_or(self):
        assert TT.OR in tok_types("a || b")


# ---------------------------------------------------------------------------
# Directives
# ---------------------------------------------------------------------------

class TestDirectives:
    def test_timescale_directive(self):
        types = tok_types("`timescale 1ns/1ps")
        assert TT.DIRECTIVE in types

    def test_include_directive(self):
        types = tok_types('`include "defs.v"')
        assert TT.DIRECTIVE in types


# ---------------------------------------------------------------------------
# Source position tracking
# ---------------------------------------------------------------------------

class TestSourcePosition:
    def test_line_number_starts_at_1(self):
        toks = tokenize("module")
        assert toks[0].line == 1

    def test_col_starts_at_0(self):
        toks = tokenize("module")
        assert toks[0].col == 0

    def test_second_line(self):
        source = "wire a;\nreg b;"
        toks = [t for t in tokenize(source) if t.type != TT.EOF]
        # 'reg' should be on line 2
        reg_tok = next(t for t in toks if t.value == "reg")
        assert reg_tok.line == 2

    def test_col_offset(self):
        source = "  wire"
        toks = [t for t in tokenize(source) if t.type != TT.EOF]
        assert toks[0].col == 2

    def test_all_tokens_have_position(self):
        source = "module foo(input wire a, output reg b); endmodule"
        for tok in tokenize(source):
            assert tok.line >= 1
            assert tok.col >= 0


# ---------------------------------------------------------------------------
# Real snippet round-trips
# ---------------------------------------------------------------------------

class TestRealSnippets:
    def test_simple_module_header(self):
        source = "module and2(input a, input b, output y);"
        types = tok_types(source)
        assert TT.IDENT in types
        assert TT.LPAREN in types
        assert TT.RPAREN in types
        assert TT.SEMICOLON in types

    def test_always_ff_sensitivity(self):
        source = "always_ff @(posedge clk)"
        toks = [t for t in tokenize(source) if t.type != TT.EOF]
        values = [t.value for t in toks]
        assert "always_ff" in values
        assert "posedge" in values
        assert "clk" in values

    def test_non_blocking_assign_statement(self):
        source = "count <= count + 8'h01;"
        types = tok_types(source)
        assert TT.NB_ASSIGN in types
        assert TT.NUMBER in types

    def test_wire_decl(self):
        source = "wire [7:0] data_bus;"
        toks = [t for t in tokenize(source) if t.type != TT.EOF]
        values = [t.value for t in toks]
        assert "wire" in values
        assert "7" in values
        assert "0" in values
        assert "data_bus" in values

    def test_logic_array(self):
        source = "logic [7:0] mem [0:7];"
        toks = [t for t in tokenize(source) if t.type != TT.EOF]
        values = [t.value for t in toks]
        assert "logic" in values
        assert "mem" in values

    def test_parameter_decl(self):
        source = "parameter DATA_WIDTH = 8;"
        toks = [t for t in tokenize(source) if t.type != TT.EOF]
        values = [t.value for t in toks]
        assert "parameter" in values
        assert "DATA_WIDTH" in values
        assert "8" in values

    def test_case_statement_tokens(self):
        source = "case (state) 2'b00: next = IDLE; default: next = state; endcase"
        types = tok_types(source)
        assert TT.IDENT in types  # case / state / default
        assert TT.NUMBER in types

    def test_generate_tokens(self):
        source = "generate for (genvar i = 0; i < 4; i = i + 1) begin end endgenerate"
        toks = [t for t in tokenize(source) if t.type != TT.EOF]
        values = [t.value for t in toks]
        assert "generate" in values
        assert "genvar" in values
        assert "endgenerate" in values
