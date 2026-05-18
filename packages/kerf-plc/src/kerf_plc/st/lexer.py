"""
kerf_plc.st.lexer — IEC 61131-3 Structured Text tokeniser.

Token stream
------------
Each token is a named tuple (type, value, line, col).

Token types
-----------
  KEYWORD         reserved word (uppercase)
  IDENT           identifier
  INTEGER         decimal integer literal
  REAL            floating-point literal
  BOOL_TRUE       TRUE
  BOOL_FALSE      FALSE
  STRING          single-quoted string literal
  TIME_LIT        T#... / TIME#... literal (raw string preserved)
  OPERATOR        :=  +  -  *  /  =  <>  <=  >=  <  >  (  )  ,  ;  :  .  [  ]  ..
  EOF             end of input
"""

from __future__ import annotations

import re
from typing import NamedTuple


# ---------------------------------------------------------------------------
# Token
# ---------------------------------------------------------------------------

class Token(NamedTuple):
    type: str
    value: str
    line: int
    col: int

    def __repr__(self) -> str:
        return f"Token({self.type!r}, {self.value!r}, {self.line}:{self.col})"


# ---------------------------------------------------------------------------
# Reserved words
# ---------------------------------------------------------------------------

_KEYWORDS: frozenset[str] = frozenset({
    # POU structure
    "PROGRAM", "FUNCTION_BLOCK", "FUNCTION", "END_PROGRAM", "END_FUNCTION_BLOCK", "END_FUNCTION",
    # Variable blocks
    "VAR", "VAR_INPUT", "VAR_OUTPUT", "VAR_IN_OUT", "VAR_TEMP", "VAR_EXTERNAL",
    "CONSTANT", "RETAIN", "NON_RETAIN", "END_VAR",
    # Types
    "BOOL", "BYTE", "WORD", "DWORD", "LWORD",
    "SINT", "INT", "DINT", "LINT", "USINT", "UINT", "UDINT", "ULINT",
    "REAL", "LREAL", "TIME", "DATE", "TIME_OF_DAY", "DATE_AND_TIME",
    "STRING", "WSTRING", "ARRAY", "OF", "STRUCT", "END_STRUCT",
    # Statements
    "IF", "THEN", "ELSIF", "ELSE", "END_IF",
    "FOR", "TO", "BY", "DO", "END_FOR",
    "WHILE", "END_WHILE",
    "REPEAT", "UNTIL", "END_REPEAT",
    "CASE", "END_CASE",
    "RETURN", "EXIT", "CONTINUE",
    # Boolean operators / literals
    "TRUE", "FALSE",
    "AND", "OR", "XOR", "NOT", "MOD",
    # Miscellaneous IEC keywords
    "AT", "WITH", "READ_WRITE", "READ_ONLY",
    "RESOURCE", "ON", "TASK", "PROGRAM", "CONFIGURATION", "END_CONFIGURATION",
    "INITIAL_STEP", "STEP", "END_STEP", "TRANSITION", "FROM", "TO", "ACTION", "END_ACTION",
})

# Tokens that look like keywords but are literal values, handled separately
_BOOL_KEYWORDS = {"TRUE", "FALSE"}


# ---------------------------------------------------------------------------
# Token specification (order matters — longest match first)
# ---------------------------------------------------------------------------

_PATTERNS: list[tuple[str, str]] = [
    # Whitespace + comments (skipped)
    ("COMMENT_BLOCK", r"\(\*[\s\S]*?\*\)"),
    ("COMMENT_LINE",  r"//[^\n]*"),
    ("WS",            r"[ \t\r\n]+"),

    # TIME literal must come before IDENT
    ("TIME_LIT",  r"(?:T|TIME)#[0-9]+(?:d|h|m(?:s)?|s|ms)+(?:[_0-9]+(?:d|h|m(?:s)?|s|ms))*"),

    # Numbers — REAL before INTEGER so 1.0 matches float
    ("REAL",    r"[0-9]+\.[0-9]+(?:[eE][+-]?[0-9]+)?"),
    ("INTEGER", r"[0-9]+(?:_[0-9]+)*"),

    # String literal (single-quoted, $$ escape)
    ("STRING", r"'(?:[^'$]|\$[\s\S])*'"),

    # Operators (multi-char before single)
    ("OPERATOR", r":=|<>|<=|>=|\.\.|[+\-*/=<>(),;:\.\[\]]"),

    # Identifiers / keywords
    ("IDENT",   r"[A-Za-z_][A-Za-z0-9_]*"),
]

_MASTER_RE = re.compile(
    "|".join(f"(?P<{name}>{pattern})" for name, pattern in _PATTERNS),
    re.DOTALL,
)


# ---------------------------------------------------------------------------
# Tokenise
# ---------------------------------------------------------------------------

class LexError(Exception):
    def __init__(self, msg: str, line: int, col: int) -> None:
        super().__init__(f"Line {line}:{col} — {msg}")
        self.line = line
        self.col = col


def tokenise(source: str) -> list[Token]:
    """
    Tokenise *source* and return a flat list of ``Token`` objects.
    The list always ends with an EOF token.
    """
    tokens: list[Token] = []
    pos = 0
    line = 1
    line_start = 0
    n = len(source)

    while pos < n:
        m = _MASTER_RE.match(source, pos)
        if m is None:
            col = pos - line_start + 1
            raise LexError(f"Unexpected character {source[pos]!r}", line, col)

        kind = m.lastgroup
        text = m.group()
        col = pos - line_start + 1

        # Advance line tracking
        newlines = text.count("\n")
        if newlines:
            line += newlines
            line_start = pos + text.rfind("\n") + 1

        pos = m.end()

        # Skip whitespace and comments
        if kind in ("WS", "COMMENT_BLOCK", "COMMENT_LINE"):
            continue

        # Classify identifiers
        if kind == "IDENT":
            upper = text.upper()
            if upper in _BOOL_KEYWORDS:
                kind = "BOOL_TRUE" if upper == "TRUE" else "BOOL_FALSE"
                text = upper
            elif upper in _KEYWORDS:
                kind = "KEYWORD"
                text = upper  # normalise to uppercase
            # else stays IDENT

        tokens.append(Token(kind, text, line, col))

    tokens.append(Token("EOF", "", line, len(source) - line_start + 1))
    return tokens
