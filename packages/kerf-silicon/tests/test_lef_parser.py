"""Tests for the LEF lexer and parser (T-240).

Run with:
    PYTHONPATH=packages/kerf-core/src:packages/kerf-silicon/src \
        python3 -m pytest packages/kerf-silicon/tests/test_lef_parser.py -x
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from kerf_silicon.lef import parse_lef, parse_lef_file
from kerf_silicon.lef.ast import LefLibrary, Macro, Pin, Port
from kerf_silicon.lef.lexer import tokenize

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

FIXTURES = Path(__file__).parent / "fixtures"
INV1_LEF = FIXTURES / "inv_1.lef"
SKY130_LEF = FIXTURES / "sky130_fd_sc_hd.lef"


# ===========================================================================
# Lexer tests
# ===========================================================================


class TestLexer:
    def test_ignores_hash_comments(self):
        source = "MACRO inv_1 # this is a comment\n  CLASS CORE ;\nEND inv_1"
        tokens = tokenize(source)
        values = [t.value for t in tokens]
        # Comment text should not appear
        assert "this" not in values
        assert "comment" not in values
        # Keywords should be present
        assert "MACRO" in values
        assert "inv_1" in values
        assert "CLASS" in values

    def test_comment_only_line_produces_no_tokens(self):
        source = "# just a comment\n"
        tokens = tokenize(source)
        assert tokens == []

    def test_semicolon_is_own_token(self):
        source = "SIZE 1.380 BY 2.720 ;"
        tokens = tokenize(source)
        values = [t.value for t in tokens]
        assert ";" in values
        assert "SIZE" in values
        assert "1.380" in values

    def test_line_numbers_assigned(self):
        source = "MACRO inv_1\n  CLASS CORE ;\nEND inv_1"
        tokens = tokenize(source)
        # "MACRO" is on line 1
        macro_tok = next(t for t in tokens if t.value == "MACRO")
        assert macro_tok.line == 1
        # "CLASS" is on line 2
        class_tok = next(t for t in tokens if t.value == "CLASS")
        assert class_tok.line == 2
        # "END" is on line 3
        end_tok = next(t for t in tokens if t.value == "END")
        assert end_tok.line == 3

    def test_mixed_comments_and_code(self):
        source = (
            "# header\n"
            "VERSION 5.8 ; # inline comment\n"
            "MACRO foo # macro start\n"
            "END foo\n"
        )
        tokens = tokenize(source)
        values = [t.value for t in tokens]
        assert "VERSION" in values
        assert "5.8" in values
        assert "MACRO" in values
        assert "foo" in values
        # inline comment text should be absent
        assert "inline" not in values
        assert "header" not in values


# ===========================================================================
# Parser — inv_1.lef
# ===========================================================================


class TestInv1:
    @pytest.fixture(scope="class")
    def lib(self) -> LefLibrary:
        return parse_lef_file(str(INV1_LEF))

    def test_returns_lef_library(self, lib):
        assert isinstance(lib, LefLibrary)

    def test_exactly_one_macro(self, lib):
        assert len(lib.macros) == 1

    def test_macro_name(self, lib):
        assert lib.macros[0].name == "inv_1"

    def test_macro_class(self, lib):
        assert lib.macros[0].macro_class == "CORE"

    def test_macro_size(self, lib):
        macro = lib.macros[0]
        assert abs(macro.size_x - 1.380) < 1e-6
        assert abs(macro.size_y - 2.720) < 1e-6

    def test_four_pins(self, lib):
        """inv_1 has A, Y (signal) + VPWR, VGND (supply) = 4 pins total."""
        macro = lib.macros[0]
        assert len(macro.pins) == 4

    def test_signal_pins_present(self, lib):
        """A and Y must be present."""
        pin_names = {p.name for p in lib.macros[0].pins}
        assert "A" in pin_names
        assert "Y" in pin_names

    def test_supply_pins_present(self, lib):
        """VPWR and VGND must be present (supply pair)."""
        pin_names = {p.name for p in lib.macros[0].pins}
        assert "VPWR" in pin_names
        assert "VGND" in pin_names

    def test_pin_a_direction(self, lib):
        pin_a = next(p for p in lib.macros[0].pins if p.name == "A")
        assert pin_a.direction == "INPUT"

    def test_pin_y_direction(self, lib):
        pin_y = next(p for p in lib.macros[0].pins if p.name == "Y")
        assert pin_y.direction == "OUTPUT"

    def test_pin_vpwr_use(self, lib):
        pin = next(p for p in lib.macros[0].pins if p.name == "VPWR")
        assert pin.use == "POWER"

    def test_pin_vgnd_use(self, lib):
        pin = next(p for p in lib.macros[0].pins if p.name == "VGND")
        assert pin.use == "GROUND"

    def test_antenna_gate_area(self, lib):
        pin_a = next(p for p in lib.macros[0].pins if p.name == "A")
        assert pin_a.antenna_gate_area is not None
        assert abs(pin_a.antenna_gate_area - 0.0576) < 1e-6

    def test_pin_a_has_port_with_layer(self, lib):
        pin_a = next(p for p in lib.macros[0].pins if p.name == "A")
        assert len(pin_a.ports) >= 1
        assert pin_a.ports[0].layer == "li1"

    def test_port_has_rect_shape(self, lib):
        pin_a = next(p for p in lib.macros[0].pins if p.name == "A")
        port = pin_a.ports[0]
        assert len(port.shapes) >= 1
        shape = port.shapes[0]
        assert shape.kind == "RECT"
        assert len(shape.coords) == 4

    def test_obs_present(self, lib):
        assert len(lib.macros[0].obstructions) >= 1

    def test_version(self, lib):
        assert lib.version == "5.8"

    def test_site_parsed(self, lib):
        assert len(lib.sites) >= 1
        assert lib.sites[0].name == "unithd"

    def test_layer_parsed(self, lib):
        assert len(lib.layers) >= 1
        names = {l.name for l in lib.layers}
        assert "li1" in names


# ===========================================================================
# Parser — line numbers preserved in AST
# ===========================================================================


class TestLineNumbers:
    def test_macro_has_nonzero_line(self):
        lib = parse_lef_file(str(INV1_LEF))
        assert lib.macros[0].line > 0

    def test_pin_has_nonzero_line(self):
        lib = parse_lef_file(str(INV1_LEF))
        for pin in lib.macros[0].pins:
            assert pin.line > 0, f"pin {pin.name!r} has line=0"

    def test_port_has_nonzero_line(self):
        lib = parse_lef_file(str(INV1_LEF))
        for pin in lib.macros[0].pins:
            for port in pin.ports:
                assert port.line > 0, f"port on layer {port.layer!r} has line=0"

    def test_shape_has_nonzero_line(self):
        lib = parse_lef_file(str(INV1_LEF))
        for pin in lib.macros[0].pins:
            for port in pin.ports:
                for shape in port.shapes:
                    assert shape.line > 0

    def test_layer_has_line(self):
        lib = parse_lef_file(str(INV1_LEF))
        for layer in lib.layers:
            assert layer.line > 0

    def test_macro_line_less_than_pin_line(self):
        """Macro must start before its pins in the source."""
        lib = parse_lef_file(str(INV1_LEF))
        macro = lib.macros[0]
        for pin in macro.pins:
            assert macro.line < pin.line


# ===========================================================================
# Parser — sky130_fd_sc_hd.lef (larger sample)
# ===========================================================================


class TestSky130:
    @pytest.fixture(scope="class")
    def lib(self) -> LefLibrary:
        return parse_lef_file(str(SKY130_LEF))

    def test_at_least_five_macros(self, lib):
        assert len(lib.macros) >= 5

    def test_inv_1_present(self, lib):
        names = {m.name for m in lib.macros}
        assert "sky130_fd_sc_hd__inv_1" in names

    def test_nand2_present(self, lib):
        names = {m.name for m in lib.macros}
        assert "sky130_fd_sc_hd__nand2_1" in names

    def test_dff_present(self, lib):
        names = {m.name for m in lib.macros}
        assert "sky130_fd_sc_hd__dff_1" in names

    def test_all_macros_have_vpwr_vgnd(self, lib):
        for macro in lib.macros:
            pin_names = {p.name for p in macro.pins}
            assert "VPWR" in pin_names, f"{macro.name} missing VPWR"
            assert "VGND" in pin_names, f"{macro.name} missing VGND"

    def test_layers_parsed(self, lib):
        assert len(lib.layers) >= 3

    def test_via_parsed(self, lib):
        assert len(lib.vias) >= 1
        assert lib.vias[0].name == "M1M2_PR"

    def test_site_parsed(self, lib):
        assert len(lib.sites) >= 1
        assert lib.sites[0].name == "unithd"

    def test_dff_has_clk_pin(self, lib):
        dff = next(m for m in lib.macros if m.name == "sky130_fd_sc_hd__dff_1")
        pin_names = {p.name for p in dff.pins}
        assert "CLK" in pin_names

    def test_macro_sizes_nonzero(self, lib):
        for macro in lib.macros:
            assert macro.size_x > 0, f"{macro.name} size_x=0"
            assert macro.size_y > 0, f"{macro.name} size_y=0"


# ===========================================================================
# Parser — inline source tests
# ===========================================================================


class TestInlineParser:
    def test_minimal_macro(self):
        src = """
VERSION 5.8 ;
MACRO buf_1
  CLASS CORE ;
  ORIGIN 0.0 0.0 ;
  SIZE 2.0 BY 2.72 ;
  PIN A
    DIRECTION INPUT ;
    PORT
      LAYER li1 ;
        RECT 0.0 1.0 0.5 1.2 ;
    END PORT
  END A
  PIN Y
    DIRECTION OUTPUT ;
    PORT
      LAYER li1 ;
        RECT 1.5 1.0 2.0 1.2 ;
    END PORT
  END Y
END buf_1
"""
        lib = parse_lef(src)
        assert len(lib.macros) == 1
        m = lib.macros[0]
        assert m.name == "buf_1"
        assert m.macro_class == "CORE"
        assert abs(m.size_x - 2.0) < 1e-6
        assert len(m.pins) == 2

    def test_empty_source(self):
        lib = parse_lef("")
        assert isinstance(lib, LefLibrary)
        assert lib.macros == []

    def test_comments_only(self):
        lib = parse_lef("# comment line 1\n# comment line 2\n")
        assert lib.macros == []

    def test_polygon_shape(self):
        src = """
MACRO poly_cell
  CLASS CORE ;
  SIZE 2.0 BY 2.72 ;
  PIN A
    DIRECTION INPUT ;
    PORT
      LAYER li1 ;
        POLYGON 0.0 0.0 1.0 0.0 1.0 1.0 0.0 1.0 ;
    END PORT
  END A
END poly_cell
"""
        lib = parse_lef(src)
        pin_a = lib.macros[0].pins[0]
        shape = pin_a.ports[0].shapes[0]
        assert shape.kind == "POLYGON"
        assert len(shape.coords) == 8

    def test_busbitchars_parsed(self):
        lib = parse_lef('BUSBITCHARS "[]" ;')
        assert lib.bus_bit_chars == "[]"

    def test_dividerchar_parsed(self):
        lib = parse_lef('DIVIDERCHAR "/" ;')
        assert lib.divider_char == "/"

    def test_version_parsed(self):
        lib = parse_lef("VERSION 5.8 ;")
        assert lib.version == "5.8"

    def test_multiple_macros(self):
        src = """
MACRO cell_a
  CLASS CORE ;
  SIZE 1.0 BY 2.72 ;
END cell_a
MACRO cell_b
  CLASS CORE ;
  SIZE 2.0 BY 2.72 ;
END cell_b
MACRO cell_c
  CLASS CORE ;
  SIZE 3.0 BY 2.72 ;
END cell_c
"""
        lib = parse_lef(src)
        assert len(lib.macros) == 3
        names = [m.name for m in lib.macros]
        assert names == ["cell_a", "cell_b", "cell_c"]
