"""
test_gk119_mold_split.py
=========================
GK-119: Hermetic pytest oracle for mold_split().

Oracle: core ∪ cavity ∪ part volumes = block volume ± tol.
        Both halves are watertight (validate_body passes).

All tests are hermetic (pure-Python, no DB, no OCC required).
"""

from __future__ import annotations

import pytest

from kerf_cad_core.geom.mold import mold_split
from kerf_cad_core.geom.brep_build import box_to_body
from kerf_cad_core.geom.mass_props import body_mass_props
from kerf_cad_core.geom.brep import validate_body


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _volume(body) -> float:
    return abs(body_mass_props(body)["volume"])


def _validate(body, label: str) -> None:
    """Assert body passes validate_body (closed solid)."""
    result = validate_body(body)
    assert result["ok"], (
        f"{label} failed validate_body: {result['errors']}"
    )


# ---------------------------------------------------------------------------
# GK-119 oracle tests
# ---------------------------------------------------------------------------

class TestMoldSplitVolumeOracle:
    """Volume conservation: vol(core) + vol(cavity) + vol(part) ≈ vol(block)."""

    def _run_volume_oracle(
        self,
        part,
        block,
        pull_direction,
        tol: float = 1e-5,
    ) -> None:
        result = mold_split(part, block, pull_direction)
        core = result["core"]
        cavity = result["cavity"]

        v_block = _volume(block)
        v_part = _volume(part)
        v_core = _volume(core)
        v_cavity = _volume(cavity)

        total = v_core + v_cavity + v_part
        assert abs(total - v_block) < tol * v_block + tol, (
            f"Volume oracle failed: "
            f"core={v_core:.6f} + cavity={v_cavity:.6f} + part={v_part:.6f} "
            f"= {total:.6f} != block={v_block:.6f} "
            f"(diff={abs(total-v_block):.2e})"
        )

    def test_unit_cube_part_in_unit_block_pull_z(self):
        """Small part centred in block, pull along +Z."""
        # Block: 4×4×4 centred at origin → corner (-2,-2,-2)
        block = box_to_body([-2.0, -2.0, -2.0], 4.0, 4.0, 4.0)
        # Part: 1×1×1 centred at origin → corner (-0.5,-0.5,-0.5)
        part = box_to_body([-0.5, -0.5, -0.5], 1.0, 1.0, 1.0)
        self._run_volume_oracle(part, block, [0.0, 0.0, 1.0])

    def test_part_fully_in_lower_half(self):
        """Part is below parting plane; cavity half is untouched."""
        block = box_to_body([0.0, 0.0, 0.0], 10.0, 10.0, 10.0)
        # Part in lower Z region
        part = box_to_body([1.0, 1.0, 1.0], 2.0, 2.0, 1.5)
        self._run_volume_oracle(part, block, [0.0, 0.0, 1.0])

    def test_part_fully_in_upper_half(self):
        """Part is above parting plane; core half is untouched."""
        block = box_to_body([0.0, 0.0, 0.0], 10.0, 10.0, 10.0)
        # Part in upper Z region (z 7..9)
        part = box_to_body([1.0, 1.0, 7.0], 2.0, 2.0, 2.0)
        self._run_volume_oracle(part, block, [0.0, 0.0, 1.0])

    def test_pull_along_x(self):
        """Pull direction along +X instead of +Z."""
        block = box_to_body([0.0, 0.0, 0.0], 10.0, 10.0, 10.0)
        part = box_to_body([4.0, 4.0, 4.0], 2.0, 2.0, 2.0)
        self._run_volume_oracle(part, block, [1.0, 0.0, 0.0])

    def test_pull_along_y(self):
        """Pull direction along +Y."""
        block = box_to_body([0.0, 0.0, 0.0], 10.0, 10.0, 10.0)
        part = box_to_body([4.0, 4.0, 4.0], 2.0, 2.0, 2.0)
        self._run_volume_oracle(part, block, [0.0, 1.0, 0.0])

    def test_non_unit_pull_direction_normalised(self):
        """Pull direction need not be unit length."""
        block = box_to_body([-5.0, -5.0, -5.0], 10.0, 10.0, 10.0)
        part = box_to_body([-1.0, -1.0, -1.0], 2.0, 2.0, 2.0)
        self._run_volume_oracle(part, block, [0.0, 0.0, 5.0])


class TestMoldSplitWatertight:
    """Both halves must pass validate_body (watertight closed solids)."""

    def test_core_watertight(self):
        block = box_to_body([0.0, 0.0, 0.0], 10.0, 10.0, 10.0)
        part = box_to_body([2.0, 2.0, 2.0], 3.0, 3.0, 2.0)
        result = mold_split(part, block, [0.0, 0.0, 1.0])
        _validate(result["core"], "core")

    def test_cavity_watertight(self):
        block = box_to_body([0.0, 0.0, 0.0], 10.0, 10.0, 10.0)
        part = box_to_body([2.0, 2.0, 2.0], 3.0, 3.0, 2.0)
        result = mold_split(part, block, [0.0, 0.0, 1.0])
        _validate(result["cavity"], "cavity")


class TestMoldSplitReturnShape:
    """Return value has correct keys and types."""

    def test_returns_dict_with_core_cavity(self):
        block = box_to_body([0.0, 0.0, 0.0], 4.0, 4.0, 4.0)
        part = box_to_body([1.0, 1.0, 1.0], 1.0, 1.0, 1.0)
        result = mold_split(part, block, [0.0, 0.0, 1.0])
        assert isinstance(result, dict), "mold_split must return a dict"
        assert "core" in result, "result must have 'core' key"
        assert "cavity" in result, "result must have 'cavity' key"

    def test_zero_pull_raises(self):
        block = box_to_body([0.0, 0.0, 0.0], 4.0, 4.0, 4.0)
        part = box_to_body([1.0, 1.0, 1.0], 1.0, 1.0, 1.0)
        with pytest.raises(ValueError, match="non-zero"):
            mold_split(part, block, [0.0, 0.0, 0.0])

    def test_exported_from_geom_init(self):
        """mold_split must be importable from the public geom façade."""
        from kerf_cad_core.geom import mold_split as ms  # noqa: F401
        assert callable(ms)
