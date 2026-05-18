"""LEF lexer — whitespace-separated tokens, # comments, semicolons.

Token fields:
    value: str   — the raw token text
    line:  int   — 1-based source line number

Behaviour:
    - Strips # ... end-of-line comments before tokenising.
    - Treats semicolons as standalone tokens (i.e. ';' is itself a token).
    - Quoted strings (double-quoted) are returned as a single token including
      the surrounding quotes so the parser can strip them if needed.
    - All-caps keywords (MACRO, PIN, ...) pass through unchanged.
    - Numbers (int / float) pass through as string tokens; the parser converts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator, List


@dataclass(frozen=True)
class Token:
    value: str
    line: int

    def __repr__(self) -> str:
        return f"Token({self.value!r}, line={self.line})"


# A quoted string, a semicolon, or a run of non-whitespace/non-semicolon chars.
_TOKEN_RE = re.compile(
    r'"[^"]*"'      # double-quoted string
    r"|"
    r";"            # semicolon as its own token
    r"|"
    r"[^\s;]+"      # everything else
)

_COMMENT_RE = re.compile(r"#[^\n]*")


def tokenize(source: str) -> List[Token]:
    """Tokenize *source* (full file text) and return a list of Token objects."""
    tokens: List[Token] = []
    for lineno, raw_line in enumerate(source.splitlines(), start=1):
        # Strip comments first
        line = _COMMENT_RE.sub("", raw_line)
        for m in _TOKEN_RE.finditer(line):
            tokens.append(Token(value=m.group(), line=lineno))
    return tokens


def tokenize_file(path: str) -> List[Token]:
    """Read *path* from disk and tokenise it."""
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return tokenize(fh.read())
