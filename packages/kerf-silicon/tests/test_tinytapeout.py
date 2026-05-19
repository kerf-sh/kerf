"""test_tinytapeout.py — pytest suite for the Tiny Tapeout submission packager.

Tests
-----
- valid_design_packages          : full happy-path end-to-end
- wrong_module_name              : ValidationError on bad tt_um_ name
- wrong_io_width                 : ValidationError when port width ≠ [7:0]
- missing_io_port                : ValidationError when a required port is absent
- info_yaml_round_trip           : dump_yaml → load_yaml preserves values
- tile_area_check                : correct µm² for every supported tile
- invalid_tile_raises            : ValidationError on unknown tile label
- missing_rtl_sources            : ValidationError when no .v files exist
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from kerf_silicon.tinytapeout import ValidationError, package_for_tt
from kerf_silicon.tinytapeout.info_yaml import (
    build_info_dict,
    dump_yaml,
    load_yaml,
    validate_info_dict,
)
from kerf_silicon.tinytapeout.tile_constraints import all_tiles, validate_tile

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_VALID_RTL = textwrap.dedent(
    """\
    module tt_um_adder (
        input  wire [7:0] ui_in,
        output wire [7:0] uo_out,
        input  wire [7:0] uio_in,
        output wire [7:0] uio_out,
        output wire [7:0] uio_oe,
        input  wire       ena,
        input  wire       clk,
        input  wire       rst_n
    );
        assign uo_out  = ui_in + 1;
        assign uio_out = 8'b0;
        assign uio_oe  = 8'b0;
    endmodule
    """
)


def _valid_info(top_module: str = "tt_um_adder", tiles: str = "1x1") -> dict:
    return build_info_dict(
        title="My Adder",
        author="Alice",
        description="A simple adder",
        top_module=top_module,
        language="Verilog",
        tiles=tiles,
        what_it_does="Adds one to input.",
        how_it_works="Combinational adder.",
        how_to_test="Apply ui_in, read uo_out.",
    )


def _make_design(tmp_path: Path, rtl_text: str = _VALID_RTL) -> Path:
    design_dir = tmp_path / "my_design"
    design_dir.mkdir(parents=True, exist_ok=True)
    (design_dir / "top.v").write_text(rtl_text)
    return design_dir


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestValidDesignPackages:
    def test_returns_path(self, tmp_path: Path):
        design_dir = _make_design(tmp_path)
        result = package_for_tt(design_dir, _valid_info())
        assert isinstance(result, Path)

    def test_output_inside_design_dir(self, tmp_path: Path):
        design_dir = _make_design(tmp_path)
        result = package_for_tt(design_dir, _valid_info())
        assert result.parent == design_dir

    def test_info_yaml_written(self, tmp_path: Path):
        design_dir = _make_design(tmp_path)
        out_dir = package_for_tt(design_dir, _valid_info())
        assert (out_dir / "info.yaml").exists()

    def test_wrapper_written(self, tmp_path: Path):
        design_dir = _make_design(tmp_path)
        out_dir = package_for_tt(design_dir, _valid_info())
        wrapper = out_dir / "wrapper.v"
        assert wrapper.exists()
        content = wrapper.read_text()
        assert "tt_um_adder" in content

    def test_rtl_source_copied(self, tmp_path: Path):
        design_dir = _make_design(tmp_path)
        out_dir = package_for_tt(design_dir, _valid_info())
        src_dir = out_dir / "src"
        assert src_dir.is_dir()
        verilog_files = list(src_dir.rglob("*.v"))
        assert len(verilog_files) >= 1

    def test_summary_written(self, tmp_path: Path):
        design_dir = _make_design(tmp_path)
        out_dir = package_for_tt(design_dir, _valid_info())
        assert (out_dir / "PACKAGE_SUMMARY.txt").exists()

    def test_idempotent_second_call(self, tmp_path: Path):
        design_dir = _make_design(tmp_path)
        out1 = package_for_tt(design_dir, _valid_info())
        out2 = package_for_tt(design_dir, _valid_info())
        assert out1 == out2

    def test_different_tile_sizes(self, tmp_path: Path):
        for tile in ("1x1", "2x2", "4x2", "8x2"):
            design_dir = _make_design(tmp_path / tile)
            out_dir = package_for_tt(design_dir, _valid_info(tiles=tile))
            summary = (out_dir / "PACKAGE_SUMMARY.txt").read_text()
            assert tile in summary


# ---------------------------------------------------------------------------
# Module name validation
# ---------------------------------------------------------------------------


class TestModuleNameValidation:
    def test_valid_name_accepted(self):
        # Should not raise
        info = _valid_info("tt_um_my_design_v2")
        validate_info_dict(info)

    def test_missing_tt_um_prefix_raises(self, tmp_path: Path):
        rtl = _VALID_RTL.replace("tt_um_adder", "my_adder")
        design_dir = _make_design(tmp_path, rtl)
        info = _valid_info("my_adder")
        with pytest.raises(ValidationError, match="tt_um_"):
            package_for_tt(design_dir, info)

    def test_bare_tt_um_raises(self, tmp_path: Path):
        rtl = _VALID_RTL.replace("tt_um_adder", "tt_um_")
        design_dir = _make_design(tmp_path, rtl)
        info = _valid_info("tt_um_")
        with pytest.raises(ValidationError):
            package_for_tt(design_dir, info)

    def test_spaces_in_name_raises(self, tmp_path: Path):
        design_dir = _make_design(tmp_path)
        info = _valid_info("tt_um_bad name")
        with pytest.raises(ValidationError):
            package_for_tt(design_dir, info)

    def test_numeric_suffix_ok(self, tmp_path: Path):
        rtl = _VALID_RTL.replace("tt_um_adder", "tt_um_design42")
        design_dir = _make_design(tmp_path, rtl)
        info = _valid_info("tt_um_design42")
        out = package_for_tt(design_dir, info)
        assert (out / "info.yaml").exists()


# ---------------------------------------------------------------------------
# I/O signature validation
# ---------------------------------------------------------------------------


class TestIOSignatureValidation:
    def test_wrong_io_width_raises(self, tmp_path: Path):
        # Replace [7:0] with [3:0] for ui_in
        bad_rtl = _VALID_RTL.replace(
            "input  wire [7:0] ui_in",
            "input  wire [3:0] ui_in",
        )
        design_dir = _make_design(tmp_path, bad_rtl)
        with pytest.raises(ValidationError, match="ui_in"):
            package_for_tt(design_dir, _valid_info())

    def test_missing_uo_out_raises(self, tmp_path: Path):
        bad_rtl = _VALID_RTL.replace(
            "output wire [7:0] uo_out,\n", ""
        ).replace("    assign uo_out  = ui_in + 1;\n", "")
        design_dir = _make_design(tmp_path, bad_rtl)
        with pytest.raises(ValidationError, match="uo_out"):
            package_for_tt(design_dir, _valid_info())

    def test_missing_uio_in_raises(self, tmp_path: Path):
        bad_rtl = _VALID_RTL.replace(
            "input  wire [7:0] uio_in,\n", ""
        )
        design_dir = _make_design(tmp_path, bad_rtl)
        with pytest.raises(ValidationError, match="uio_in"):
            package_for_tt(design_dir, _valid_info())

    def test_missing_uio_out_raises(self, tmp_path: Path):
        bad_rtl = _VALID_RTL.replace(
            "output wire [7:0] uio_out,\n", ""
        ).replace("    assign uio_out = 8'b0;\n", "")
        design_dir = _make_design(tmp_path, bad_rtl)
        with pytest.raises(ValidationError, match="uio_out"):
            package_for_tt(design_dir, _valid_info())

    def test_missing_uio_oe_raises(self, tmp_path: Path):
        bad_rtl = _VALID_RTL.replace(
            "output wire [7:0] uio_oe,\n", ""
        ).replace("    assign uio_oe  = 8'b0;\n", "")
        design_dir = _make_design(tmp_path, bad_rtl)
        with pytest.raises(ValidationError, match="uio_oe"):
            package_for_tt(design_dir, _valid_info())

    def test_all_ports_present_no_error(self, tmp_path: Path):
        design_dir = _make_design(tmp_path)
        out = package_for_tt(design_dir, _valid_info())
        assert out.is_dir()


# ---------------------------------------------------------------------------
# info.yaml round-trip
# ---------------------------------------------------------------------------


class TestInfoYamlRoundTrip:
    def test_scalar_values_preserved(self):
        info = _valid_info()
        text = dump_yaml(info)
        parsed = load_yaml(text)
        assert parsed["project"]["title"] == "My Adder"
        assert parsed["project"]["author"] == "Alice"
        assert parsed["project"]["top_module"] == "tt_um_adder"
        assert parsed["project"]["tiles"] == "1x1"
        assert parsed["project"]["language"] == "Verilog"

    def test_documentation_section_preserved(self):
        info = _valid_info()
        text = dump_yaml(info)
        parsed = load_yaml(text)
        assert "documentation" in parsed
        assert "what_it_does" in parsed["documentation"]

    def test_yaml_starts_with_document_marker(self):
        info = _valid_info()
        text = dump_yaml(info)
        assert text.startswith("---")

    def test_file_written_matches_dump(self, tmp_path: Path):
        design_dir = _make_design(tmp_path)
        info = _valid_info()
        out_dir = package_for_tt(design_dir, info)
        file_content = (out_dir / "info.yaml").read_text()
        assert "tt_um_adder" in file_content
        assert "My Adder" in file_content

    def test_build_info_dict_produces_valid_structure(self):
        info = build_info_dict(
            title="Test",
            author="Bob",
            description="Desc",
            top_module="tt_um_test",
            language="Verilog",
            tiles="2x2",
        )
        validate_info_dict(info)  # should not raise

    def test_missing_required_field_raises(self):
        info = _valid_info()
        del info["project"]["author"]
        with pytest.raises(ValueError, match="author"):
            validate_info_dict(info)

    def test_invalid_language_raises(self):
        info = _valid_info()
        info["project"]["language"] = "Brainfuck"
        with pytest.raises(ValueError, match="language"):
            validate_info_dict(info)


# ---------------------------------------------------------------------------
# Tile constraint / area checks
# ---------------------------------------------------------------------------


class TestTileAreaCheck:
    def test_1x1_area(self):
        t = validate_tile("1x1")
        assert t.width_um == pytest.approx(160.0)
        assert t.height_um == pytest.approx(100.0)
        assert t.area_um2 == pytest.approx(16_000.0)

    def test_2x2_area(self):
        t = validate_tile("2x2")
        assert t.width_um == pytest.approx(320.0)
        assert t.height_um == pytest.approx(200.0)
        assert t.area_um2 == pytest.approx(64_000.0)

    def test_4x2_area(self):
        t = validate_tile("4x2")
        assert t.width_um == pytest.approx(640.0)
        assert t.height_um == pytest.approx(200.0)
        assert t.area_um2 == pytest.approx(128_000.0)

    def test_8x2_area(self):
        t = validate_tile("8x2")
        assert t.width_um == pytest.approx(1280.0)
        assert t.height_um == pytest.approx(200.0)
        assert t.area_um2 == pytest.approx(256_000.0)

    def test_all_tiles_returns_four(self):
        tiles = all_tiles()
        assert len(tiles) == 4

    def test_all_tiles_ordered_by_area(self):
        tiles = all_tiles()
        areas = [t.area_um2 for t in tiles]
        assert areas == sorted(areas)

    def test_invalid_tile_raises_validation_error(self, tmp_path: Path):
        design_dir = _make_design(tmp_path)
        info = _valid_info(tiles="3x3")
        with pytest.raises(ValidationError, match="tile"):
            package_for_tt(design_dir, info)

    def test_unknown_tile_label_raises_value_error(self):
        with pytest.raises(ValueError):
            validate_tile("99x99")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_no_rtl_sources_raises(self, tmp_path: Path):
        design_dir = tmp_path / "empty"
        design_dir.mkdir()
        with pytest.raises(ValidationError, match="No RTL source files"):
            package_for_tt(design_dir, _valid_info())

    def test_design_dir_not_found_raises(self, tmp_path: Path):
        missing = tmp_path / "does_not_exist"
        with pytest.raises(FileNotFoundError):
            package_for_tt(missing, _valid_info())

    def test_multiple_source_files(self, tmp_path: Path):
        design_dir = tmp_path / "multi"
        design_dir.mkdir()
        (design_dir / "top.v").write_text(_VALID_RTL)
        # A second file that has no ports — should be fine, ports already found
        (design_dir / "helper.v").write_text("module helper(); endmodule\n")
        out = package_for_tt(design_dir, _valid_info())
        copied = list((out / "src").rglob("*.v"))
        assert len(copied) == 2

    def test_sv_extension_accepted(self, tmp_path: Path):
        design_dir = tmp_path / "sv_design"
        design_dir.mkdir()
        sv_rtl = _VALID_RTL.replace("module tt_um_adder", "module tt_um_adder")
        (design_dir / "top.sv").write_text(sv_rtl)
        out = package_for_tt(design_dir, _valid_info())
        assert (out / "src" / "top.sv").exists()
