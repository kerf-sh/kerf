"""LEF parser — converts token stream into a LefLibrary AST.

Usage::

    from kerf_silicon.lef.parser import parse_lef, parse_lef_file

    lib = parse_lef_file("path/to/tech.lef")
    for macro in lib.macros:
        print(macro.name, macro.size_x, macro.size_y)

Grammar notes (informal):
    FILE       ::= STMT* END
    STMT       ::= VERSION_STMT | MACRO_BLOCK | LAYER_BLOCK
                 | VIA_BLOCK | SITE_BLOCK | BUSBITCHARS_STMT
                 | DIVIDERCHAR_STMT | ...
    MACRO_BLOCK::= MACRO name PROP* (PIN_BLOCK | OBS_BLOCK)* END name
    PIN_BLOCK  ::= PIN name PROP* PORT_BLOCK* END PIN
    PORT_BLOCK ::= PORT LAYER_STMT* END PORT
    OBS_BLOCK  ::= OBS LAYER_STMT* END OBS

Semicolons are consumed but are not required to be present (some LEF writers
omit them).  The parser is deliberately lenient: unrecognised keywords at any
level are skipped.
"""
from __future__ import annotations

from typing import List, Optional

from .ast import (
    LefLayer, LefLibrary, LefSite, LefVia,
    Macro, Obstruction, Pin, Port, Shape,
)
from .lexer import Token, tokenize, tokenize_file


class LefParseError(ValueError):
    pass


class _Parser:
    """Recursive-descent parser over a flat token list."""

    def __init__(self, tokens: List[Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    # ------------------------------------------------------------------
    # Low-level helpers
    # ------------------------------------------------------------------

    def _peek(self) -> Optional[Token]:
        if self._pos < len(self._tokens):
            return self._tokens[self._pos]
        return None

    def _peek_value(self) -> Optional[str]:
        t = self._peek()
        return t.value if t else None

    def _advance(self) -> Token:
        if self._pos >= len(self._tokens):
            raise LefParseError("Unexpected end of token stream")
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _consume_if(self, value: str) -> bool:
        """Consume the next token if it matches *value* (case-insensitive)."""
        t = self._peek()
        if t and t.value.upper() == value.upper():
            self._advance()
            return True
        return False

    def _expect(self, value: str) -> Token:
        t = self._advance()
        if t.value.upper() != value.upper():
            raise LefParseError(
                f"line {t.line}: expected {value!r}, got {t.value!r}"
            )
        return t

    def _current_line(self) -> int:
        t = self._peek()
        if t:
            return t.line
        if self._tokens:
            return self._tokens[-1].line
        return 0

    def _skip_until_end_of_stmt(self) -> None:
        """Skip tokens until we hit a semicolon or a block-ending keyword."""
        _BLOCK_ENDS = {"END", "MACRO", "PIN", "PORT", "OBS", "LAYER", "VIA", "SITE"}
        while True:
            t = self._peek()
            if t is None:
                break
            if t.value == ";":
                self._advance()
                break
            if t.value.upper() in _BLOCK_ENDS:
                break
            self._advance()

    def _consume_semicolons(self) -> None:
        while self._peek_value() == ";":
            self._advance()

    # ------------------------------------------------------------------
    # Top-level
    # ------------------------------------------------------------------

    def parse(self) -> LefLibrary:
        lib = LefLibrary()

        while self._peek() is not None:
            t = self._peek()
            if t is None:
                break
            kw = t.value.upper()

            if kw == "VERSION":
                self._advance()
                vt = self._advance()
                lib.version = vt.value
                self._consume_semicolons()

            elif kw == "BUSBITCHARS":
                self._advance()
                lib.bus_bit_chars = self._advance().value.strip('"')
                self._consume_semicolons()

            elif kw == "DIVIDERCHAR":
                self._advance()
                lib.divider_char = self._advance().value.strip('"')
                self._consume_semicolons()

            elif kw == "UNITS":
                self._skip_block("UNITS")

            elif kw == "LAYER":
                lib.layers.append(self._parse_layer())

            elif kw == "VIA":
                via = self._parse_via()
                if via is not None:
                    lib.vias.append(via)

            elif kw == "VIARULE":
                self._skip_block("VIARULE")

            elif kw == "SITE":
                lib.sites.append(self._parse_site())

            elif kw == "MACRO":
                lib.macros.append(self._parse_macro())

            elif kw in {"END", "EOF"}:
                # END LIBRARY or stray END
                self._advance()
                # Consume optional name token after END
                nxt = self._peek()
                if nxt and nxt.value.upper() not in {
                    "MACRO", "PIN", "PORT", "OBS", "LAYER",
                    "VIA", "SITE", "LIBRARY",
                }:
                    self._advance()

            else:
                # Unknown top-level keyword — skip until semicolon
                self._advance()
                self._skip_until_end_of_stmt()

        return lib

    # ------------------------------------------------------------------
    # Block skippers
    # ------------------------------------------------------------------

    def _skip_block(self, block_kw: str) -> None:
        """Skip everything until END <block_kw>."""
        self._advance()  # consume block_kw
        depth = 1
        while self._peek() is not None and depth > 0:
            t = self._advance()
            if t.value.upper() == block_kw.upper():
                depth += 1
            elif t.value.upper() == "END":
                nxt = self._peek()
                if nxt and nxt.value.upper() == block_kw.upper():
                    self._advance()
                    depth -= 1
                # If END has no matching name we just continue

    # ------------------------------------------------------------------
    # LAYER
    # ------------------------------------------------------------------

    def _parse_layer(self) -> LefLayer:
        line = self._current_line()
        self._expect("LAYER")
        name_tok = self._advance()
        layer = LefLayer(name=name_tok.value, line=line)

        while self._peek() is not None:
            kw = self._peek_value()
            if kw is None:
                break
            kw_up = kw.upper()
            if kw_up == "END":
                self._advance()
                # consume layer name after END
                nxt = self._peek()
                if nxt and nxt.value == layer.name:
                    self._advance()
                break
            elif kw_up == "TYPE":
                self._advance()
                layer.layer_type = self._advance().value
                self._consume_semicolons()
            elif kw_up == "PITCH":
                self._advance()
                layer.pitch = float(self._advance().value)
                self._consume_semicolons()
            elif kw_up == "WIDTH":
                self._advance()
                layer.width = float(self._advance().value)
                self._consume_semicolons()
            elif kw_up == "SPACING":
                self._advance()
                layer.spacing = float(self._advance().value)
                self._consume_semicolons()
            elif kw_up == "DIRECTION":
                self._advance()
                layer.direction = self._advance().value
                self._consume_semicolons()
            else:
                self._advance()
                self._skip_until_end_of_stmt()

        return layer

    # ------------------------------------------------------------------
    # VIA
    # ------------------------------------------------------------------

    def _parse_via(self) -> Optional[LefVia]:
        line = self._current_line()
        self._expect("VIA")
        name_tok = self._advance()

        # Optional DEFAULT keyword
        if self._peek_value() and self._peek_value().upper() == "DEFAULT":
            self._advance()

        via = LefVia(name=name_tok.value, line=line)
        current_layer: Optional[str] = None
        current_shapes: List[Shape] = []

        while self._peek() is not None:
            kw = self._peek_value()
            if kw is None:
                break
            kw_up = kw.upper()

            if kw_up == "END":
                self._advance()
                nxt = self._peek()
                if nxt and nxt.value == via.name:
                    self._advance()
                if current_layer is not None:
                    via.layer_shapes.append((current_layer, current_shapes))
                break
            elif kw_up == "LAYER":
                if current_layer is not None:
                    via.layer_shapes.append((current_layer, current_shapes))
                self._advance()
                current_layer = self._advance().value
                current_shapes = []
                self._consume_semicolons()
            elif kw_up in {"RECT", "POLYGON"}:
                shape = self._parse_shape()
                current_shapes.append(shape)
            elif kw_up == ";":
                self._advance()
            else:
                self._advance()
                self._skip_until_end_of_stmt()

        return via

    # ------------------------------------------------------------------
    # SITE
    # ------------------------------------------------------------------

    def _parse_site(self) -> LefSite:
        line = self._current_line()
        self._expect("SITE")
        name_tok = self._advance()
        site = LefSite(name=name_tok.value, line=line)

        while self._peek() is not None:
            kw = self._peek_value()
            if kw is None:
                break
            kw_up = kw.upper()
            if kw_up == "END":
                self._advance()
                nxt = self._peek()
                if nxt and nxt.value == site.name:
                    self._advance()
                break
            elif kw_up == "CLASS":
                self._advance()
                site.site_class = self._advance().value
                self._consume_semicolons()
            elif kw_up == "SYMMETRY":
                self._advance()
                # symmetry can be multiple tokens: X Y R90 etc., read until ;
                parts = []
                while self._peek_value() and self._peek_value() != ";":
                    parts.append(self._advance().value)
                site.symmetry = " ".join(parts)
                self._consume_semicolons()
            elif kw_up == "SIZE":
                self._advance()
                site.size_x = float(self._advance().value)
                self._consume_if("BY")
                site.size_y = float(self._advance().value)
                self._consume_semicolons()
            else:
                self._advance()
                self._skip_until_end_of_stmt()

        return site

    # ------------------------------------------------------------------
    # MACRO
    # ------------------------------------------------------------------

    def _parse_macro(self) -> Macro:
        line = self._current_line()
        self._expect("MACRO")
        name_tok = self._advance()
        macro = Macro(name=name_tok.value, line=line)

        while self._peek() is not None:
            kw = self._peek_value()
            if kw is None:
                break
            kw_up = kw.upper()

            if kw_up == "END":
                self._advance()
                # consume macro name after END
                nxt = self._peek()
                if nxt and nxt.value == macro.name:
                    self._advance()
                break

            elif kw_up == "CLASS":
                self._advance()
                macro.macro_class = self._advance().value
                self._consume_semicolons()

            elif kw_up == "ORIGIN":
                self._advance()
                macro.origin_x = float(self._advance().value)
                macro.origin_y = float(self._advance().value)
                self._consume_semicolons()

            elif kw_up == "SIZE":
                self._advance()
                macro.size_x = float(self._advance().value)
                self._consume_if("BY")
                macro.size_y = float(self._advance().value)
                self._consume_semicolons()

            elif kw_up == "SYMMETRY":
                self._advance()
                parts = []
                while self._peek_value() and self._peek_value() != ";":
                    parts.append(self._advance().value)
                macro.symmetry = " ".join(parts)
                self._consume_semicolons()

            elif kw_up == "SITE":
                self._advance()
                macro.site = self._advance().value
                self._consume_semicolons()

            elif kw_up == "PIN":
                macro.pins.append(self._parse_pin())

            elif kw_up == "OBS":
                macro.obstructions.extend(self._parse_obs())

            else:
                self._advance()
                self._skip_until_end_of_stmt()

        return macro

    # ------------------------------------------------------------------
    # PIN
    # ------------------------------------------------------------------

    def _parse_pin(self) -> Pin:
        line = self._current_line()
        self._expect("PIN")
        name_tok = self._advance()
        pin = Pin(name=name_tok.value, line=line)

        while self._peek() is not None:
            kw = self._peek_value()
            if kw is None:
                break
            kw_up = kw.upper()

            if kw_up == "END":
                self._advance()
                nxt = self._peek()
                if nxt and nxt.value == pin.name:
                    self._advance()
                break

            elif kw_up == "DIRECTION":
                self._advance()
                pin.direction = self._advance().value
                self._consume_semicolons()

            elif kw_up == "USE":
                self._advance()
                pin.use = self._advance().value
                self._consume_semicolons()

            elif kw_up == "ANTENNAGATEAREA":
                self._advance()
                pin.antenna_gate_area = float(self._advance().value)
                self._consume_semicolons()

            elif kw_up == "PORT":
                pin.ports.extend(self._parse_port())

            else:
                self._advance()
                self._skip_until_end_of_stmt()

        return pin

    # ------------------------------------------------------------------
    # PORT
    # ------------------------------------------------------------------

    def _parse_port(self) -> List[Port]:
        """Parse a PORT block and return a list of Port objects (one per LAYER)."""
        self._expect("PORT")
        ports: List[Port] = []
        current_port: Optional[Port] = None

        while self._peek() is not None:
            kw = self._peek_value()
            if kw is None:
                break
            kw_up = kw.upper()

            if kw_up == "END":
                self._advance()
                # consume "PORT" after END
                nxt = self._peek()
                if nxt and nxt.value.upper() == "PORT":
                    self._advance()
                if current_port is not None:
                    ports.append(current_port)
                break

            elif kw_up == "LAYER":
                if current_port is not None:
                    ports.append(current_port)
                self._advance()
                layer_name = self._advance().value
                self._consume_semicolons()
                current_port = Port(layer=layer_name, line=self._current_line())

            elif kw_up in {"RECT", "POLYGON"}:
                shape = self._parse_shape()
                if current_port is not None:
                    current_port.shapes.append(shape)

            elif kw_up == ";":
                self._advance()

            else:
                self._advance()
                self._skip_until_end_of_stmt()

        return ports

    # ------------------------------------------------------------------
    # OBS
    # ------------------------------------------------------------------

    def _parse_obs(self) -> List[Obstruction]:
        """Parse an OBS block and return a list of Obstruction objects."""
        self._expect("OBS")
        obstructions: List[Obstruction] = []
        current_obs: Optional[Obstruction] = None

        while self._peek() is not None:
            kw = self._peek_value()
            if kw is None:
                break
            kw_up = kw.upper()

            if kw_up == "END":
                self._advance()
                nxt = self._peek()
                if nxt and nxt.value.upper() == "OBS":
                    self._advance()
                if current_obs is not None:
                    obstructions.append(current_obs)
                break

            elif kw_up == "LAYER":
                if current_obs is not None:
                    obstructions.append(current_obs)
                self._advance()
                layer_name = self._advance().value
                self._consume_semicolons()
                current_obs = Obstruction(layer=layer_name, line=self._current_line())

            elif kw_up in {"RECT", "POLYGON"}:
                shape = self._parse_shape()
                if current_obs is not None:
                    current_obs.shapes.append(shape)

            elif kw_up == ";":
                self._advance()

            else:
                self._advance()
                self._skip_until_end_of_stmt()

        return obstructions

    # ------------------------------------------------------------------
    # Shapes
    # ------------------------------------------------------------------

    def _parse_shape(self) -> Shape:
        """Parse a RECT x1 y1 x2 y2 ; or POLYGON x y ... ;"""
        line = self._current_line()
        kind_tok = self._advance()
        kind = kind_tok.value.upper()
        coords: List[float] = []

        while self._peek_value() not in {";", None}:
            nxt = self._peek()
            if nxt is None:
                break
            # Check if the next token looks like a number
            try:
                coords.append(float(nxt.value))
                self._advance()
            except ValueError:
                # Not a number — stop collecting coords
                break

        self._consume_semicolons()
        return Shape(kind=kind, coords=coords, line=line)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_lef(source: str) -> LefLibrary:
    """Parse *source* (LEF text) and return a :class:`LefLibrary`."""
    tokens = tokenize(source)
    return _Parser(tokens).parse()


def parse_lef_file(path: str) -> LefLibrary:
    """Read *path* from disk, parse it, and return a :class:`LefLibrary`."""
    tokens = tokenize_file(path)
    return _Parser(tokens).parse()
