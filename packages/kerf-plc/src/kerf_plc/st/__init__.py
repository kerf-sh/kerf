"""
kerf_plc.st — IEC 61131-3 Structured Text parser.

Public surface::

    from kerf_plc.st import parse, ParseError
    from kerf_plc.st.ast import *

``parse(source: str) -> POU`` returns the top-level POU dataclass.
``ParseError`` is raised on syntax errors with line/column info.
"""

from kerf_plc.st.parser import parse, ParseError

__all__ = ["parse", "ParseError"]
