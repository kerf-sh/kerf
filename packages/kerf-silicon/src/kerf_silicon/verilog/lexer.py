"""
Verilog / SystemVerilog lexer — synthesizable subset.

Supports Verilog-2001 and SystemVerilog-2012 tokens needed to parse
synthesizable RTL: modules, ports, wire/reg/logic, always blocks,
assignments, if/case, parameters, and generate.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterator, List, Optional


# ---------------------------------------------------------------------------
# Token types
# ---------------------------------------------------------------------------

class TT(Enum):
    # Literals
    NUMBER      = auto()   # 8'hAA, 4'b1010, 42
    STRING      = auto()   # "text"
    # Identifiers / keywords (keywords are distinguished post-lex)
    IDENT       = auto()
    # Punctuation
    LPAREN      = auto()   # (
    RPAREN      = auto()   # )
    LBRACKET    = auto()   # [
    RBRACKET    = auto()   # ]
    LBRACE      = auto()   # {
    RBRACE      = auto()   # }
    SEMICOLON   = auto()   # ;
    COLON       = auto()   # :
    COMMA       = auto()   # ,
    DOT         = auto()   # .
    AT          = auto()   # @
    HASH        = auto()   # #
    # Operators
    ASSIGN      = auto()   # =
    NB_ASSIGN   = auto()   # <=
    PLUS        = auto()   # +
    MINUS       = auto()   # -
    STAR        = auto()   # *
    SLASH       = auto()   # /
    PERCENT     = auto()   # %
    AMPERSAND   = auto()   # &
    PIPE        = auto()   # |
    CARET       = auto()   # ^
    TILDE       = auto()   # ~
    BANG        = auto()   # !
    LT          = auto()   # <
    GT          = auto()   # >
    LTE         = auto()   # <=  (same as NB_ASSIGN, context-dependent)
    GTE         = auto()   # >=
    EQ          = auto()   # ==
    NEQ         = auto()   # !=
    AND         = auto()   # &&
    OR          = auto()   # ||
    LSHIFT      = auto()   # <<
    RSHIFT      = auto()   # >>
    QUESTION    = auto()   # ?
    AAND        = auto()   # &  (already have AMPERSAND)
    # Special
    DIRECTIVE   = auto()   # `timescale, `include, etc.
    EOF         = auto()


# ---------------------------------------------------------------------------
# Keyword sets
# ---------------------------------------------------------------------------

KEYWORDS: frozenset[str] = frozenset({
    # Module structure
    "module", "endmodule", "macromodule",
    # Port directions
    "input", "output", "inout",
    # Net / variable types
    "wire", "reg", "logic", "tri", "tri0", "tri1", "wand", "wor",
    "integer", "real", "realtime", "time",
    # Signed
    "signed", "unsigned",
    # Parameters
    "parameter", "localparam", "defparam", "specparam",
    # Procedural
    "always", "always_ff", "always_comb", "always_latch",
    "initial",
    "begin", "end",
    "if", "else",
    "case", "casez", "casex", "endcase",
    "for", "while", "repeat", "forever",
    "fork", "join", "join_any", "join_none",
    "disable",
    # Sensitivity
    "posedge", "negedge", "or",
    # Continuous assign
    "assign", "deassign", "force", "release",
    # Generate
    "generate", "endgenerate", "genvar",
    # Tasks / Functions
    "task", "endtask", "function", "endfunction", "automatic",
    "return",
    # System tasks / display (we emit as IDENT but list for reference)
    # "\\$display", "\\$monitor",
    # Strength
    "supply0", "supply1", "strong0", "strong1", "pull0", "pull1",
    "weak0", "weak1", "highz0", "highz1",
    # Misc
    "default", "void", "null",
    # SystemVerilog extras
    "interface", "endinterface", "modport",
    "clocking", "endclocking",
    "program", "endprogram",
    "package", "endpackage", "import", "export",
    "typedef", "struct", "union", "enum", "packed",
    "bit", "byte", "shortint", "int", "longint",
    "shortreal", "string", "chandle", "event",
    "unique", "priority",
    "unique0",
    "do", "break", "continue",
    "assert", "assume", "cover", "expect",
    "sequence", "property",
    "const",
    "ref", "var",
    "static", "protected",
    "virtual", "extends", "implements",
    "class", "endclass", "new",
    "this", "super",
    "inside", "dist",
    "with",
    "foreach",
    "randcase", "randcycle",
    "rand", "randc", "constraint",
    "solve", "before",
    "type",
    "iff",
    "wait",
    "final",
    "bind",
    "interconnect",
    "nettype",
})


# ---------------------------------------------------------------------------
# Token dataclass
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class Token:
    type: TT
    value: str
    line: int   # 1-based
    col: int    # 0-based


# ---------------------------------------------------------------------------
# Lexer
# ---------------------------------------------------------------------------

# Single-pass regex tokenizer pattern pieces
_TOKEN_SPEC = [
    # Whitespace (skip)
    ("WS",          r'[ \t\r\n]+'),
    # Line comment
    ("LCOMMENT",    r'//[^\n]*'),
    # Block comment
    ("BCOMMENT",    r'/\*.*?\*/'),
    # Compiler directive
    ("DIRECTIVE",   r'`[A-Za-z_][A-Za-z0-9_]*'),
    # System task / function ($display etc.)
    ("SYSTASK",     r'\$[A-Za-z_][A-Za-z0-9_$]*'),
    # Sized number literal:  8'h_FF  4'b1010  12'o77  16'd42
    ("SIZED_NUM",   r"[0-9]+'[sS]?[bBoOdDhH][0-9a-fA-F_xXzZ?]*"),
    # Unsized decimal
    ("UNSIZED_NUM", r'[0-9][0-9_]*'),
    # String
    ("STRING",      r'"[^"]*"'),
    # Identifier / keyword
    ("IDENT",       r'[A-Za-z_\\][A-Za-z0-9_$\\]*'),
    # Two-char operators (order matters — longer first)
    ("NB_ASSIGN",   r'<='),      # non-blocking assign  (also LTE in expr context)
    ("EQ",          r'=='),
    ("NEQ",         r'!='),
    ("GTE",         r'>='),
    ("LSHIFT",      r'<<'),
    ("RSHIFT",      r'>>'),
    ("AND",         r'&&'),
    ("OR",          r'\|\|'),
    # Single-char operators / punctuation
    ("LPAREN",      r'\('),
    ("RPAREN",      r'\)'),
    ("LBRACKET",    r'\['),
    ("RBRACKET",    r'\]'),
    ("LBRACE",      r'\{'),
    ("RBRACE",      r'\}'),
    ("SEMICOLON",   r';'),
    ("COLON",       r':'),
    ("COMMA",       r','),
    ("DOT",         r'\.'),
    ("AT",          r'@'),
    ("HASH",        r'#'),
    ("ASSIGN",      r'='),
    ("PLUS",        r'\+'),
    ("MINUS",       r'-'),
    ("STAR",        r'\*'),
    ("SLASH",       r'/'),
    ("PERCENT",     r'%'),
    ("AMPERSAND",   r'&'),
    ("PIPE",        r'\|'),
    ("CARET",       r'\^'),
    ("TILDE",       r'~'),
    ("BANG",        r'!'),
    ("LT",          r'<'),
    ("GT",          r'>'),
    ("QUESTION",    r'\?'),
]

_MASTER_RE = re.compile(
    '|'.join(f'(?P<{name}>{pat})' for name, pat in _TOKEN_SPEC),
    re.DOTALL,
)

_NAME_TO_TT: dict[str, TT] = {
    "LPAREN":    TT.LPAREN,
    "RPAREN":    TT.RPAREN,
    "LBRACKET":  TT.LBRACKET,
    "RBRACKET":  TT.RBRACKET,
    "LBRACE":    TT.LBRACE,
    "RBRACE":    TT.RBRACE,
    "SEMICOLON": TT.SEMICOLON,
    "COLON":     TT.COLON,
    "COMMA":     TT.COMMA,
    "DOT":       TT.DOT,
    "AT":        TT.AT,
    "HASH":      TT.HASH,
    "ASSIGN":    TT.ASSIGN,
    "NB_ASSIGN": TT.NB_ASSIGN,
    "PLUS":      TT.PLUS,
    "MINUS":     TT.MINUS,
    "STAR":      TT.STAR,
    "SLASH":     TT.SLASH,
    "PERCENT":   TT.PERCENT,
    "AMPERSAND": TT.AMPERSAND,
    "PIPE":      TT.PIPE,
    "CARET":     TT.CARET,
    "TILDE":     TT.TILDE,
    "BANG":      TT.BANG,
    "LT":        TT.LT,
    "GT":        TT.GT,
    "GTE":       TT.GTE,
    "EQ":        TT.EQ,
    "NEQ":       TT.NEQ,
    "AND":       TT.AND,
    "OR":        TT.OR,
    "LSHIFT":    TT.LSHIFT,
    "RSHIFT":    TT.RSHIFT,
    "QUESTION":  TT.QUESTION,
    "DIRECTIVE": TT.DIRECTIVE,
}


class LexError(Exception):
    def __init__(self, msg: str, line: int, col: int) -> None:
        super().__init__(f"{msg} at line {line}, col {col}")
        self.lex_line = line
        self.lex_col = col


def tokenize(source: str, filename: str = "<string>") -> List[Token]:
    """Lex *source* and return a list of Tokens (excluding whitespace/comments).

    Raises LexError on unexpected characters.
    """
    tokens: List[Token] = []
    line = 1
    line_start = 0

    for m in _MASTER_RE.finditer(source):
        kind = m.lastgroup
        value = m.group()
        col = m.start() - line_start

        # Track newlines for line/col accounting
        newlines_before = source[:m.start()].count('\n') if kind in ("WS", "BCOMMENT", "LCOMMENT") else None

        if kind in ("WS", "LCOMMENT", "BCOMMENT"):
            # Count newlines in the skipped region to keep line counter correct
            line += value.count('\n')
            if '\n' in value:
                line_start = m.start() + value.rfind('\n') + 1
            continue

        # Recompute after any previous skips
        line = source[:m.start()].count('\n') + 1
        line_start = source.rfind('\n', 0, m.start()) + 1
        col = m.start() - line_start

        if kind in ("SIZED_NUM", "UNSIZED_NUM"):
            tokens.append(Token(TT.NUMBER, value, line, col))

        elif kind == "STRING":
            tokens.append(Token(TT.STRING, value, line, col))

        elif kind in ("IDENT", "SYSTASK"):
            tokens.append(Token(TT.IDENT, value, line, col))

        elif kind == "DIRECTIVE":
            tokens.append(Token(TT.DIRECTIVE, value, line, col))

        elif kind in _NAME_TO_TT:
            tokens.append(Token(_NAME_TO_TT[kind], value, line, col))

        else:
            raise LexError(f"Unexpected character {value!r}", line, col)

    tokens.append(Token(TT.EOF, "", source.count('\n') + 1, 0))
    return tokens


def is_keyword(tok: Token) -> bool:
    """Return True if this IDENT token is a Verilog/SV keyword."""
    return tok.type == TT.IDENT and tok.value in KEYWORDS
