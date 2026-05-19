"""test_power_leakage.py — pytest suite for kerf_silicon.power.leakage.

Run with:
    PYTHONPATH=packages/kerf-core/src:packages/kerf-silicon/src \
        python3 -m pytest packages/kerf-silicon/tests/test_power_leakage.py -x

Analytic oracle
---------------
The fixture inv_1.lib contains a single cell ``sky130_fd_sc_hd__inv_1``
with ``cell_leakage_power : 0.00314``.

    leakage_power_sum(lib)        == 0.00314  (exactly 1 × 0.00314)
    leakage_power_sum(lib, {"sky130_fd_sc_hd__inv_1": 4})  == 0.01256
"""
from __future__ import annotations

import pathlib
import pytest

from kerf_silicon.liberty import parse, parse_file
from kerf_silicon.power.leakage import (
    leakage_power_sum,
    leakage_per_cell,
    CellLeakageEntry,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
INV1_LIB = FIXTURES / "inv_1.lib"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def inv1_lib():
    return parse_file(INV1_LIB)


@pytest.fixture
def multi_lib():
    """Library with three cells of known leakage values."""
    src = """
library (test_multi) {
    cell (inv_1) {
        area : 4.6;
        cell_leakage_power : 0.00314;
        pin (A) { direction : input; }
        pin (Y) { direction : output; function : "!A"; }
    }
    cell (buf_1) {
        area : 6.4;
        cell_leakage_power : 0.00520;
        pin (A) { direction : input; }
        pin (Y) { direction : output; function : "A"; }
    }
    cell (nand2_1) {
        area : 5.1;
        cell_leakage_power : 0.00780;
        pin (A) { direction : input; }
        pin (B) { direction : input; }
        pin (Y) { direction : output; function : "!(A B)"; }
    }
}
"""
    return parse(src)


@pytest.fixture
def lib_with_missing_leakage():
    """Library where some cells lack cell_leakage_power."""
    src = """
library (test_missing) {
    cell (inv_1) {
        area : 4.6;
        cell_leakage_power : 0.001;
        pin (A) { direction : input; }
        pin (Y) { direction : output; function : "!A"; }
    }
    cell (buf_1) {
        area : 6.4;
        pin (A) { direction : input; }
        pin (Y) { direction : output; function : "A"; }
    }
}
"""
    return parse(src)


# ---------------------------------------------------------------------------
# leakage_power_sum — single-cell oracle
# ---------------------------------------------------------------------------

class TestLeakagePowerSum:
    def test_inv1_single_cell_sum(self, inv1_lib):
        """Oracle: inv_1.lib has one cell with cell_leakage_power=0.00314."""
        total = leakage_power_sum(inv1_lib)
        assert total == pytest.approx(0.00314)

    def test_inv1_with_instance_count_1(self, inv1_lib):
        counts = {"sky130_fd_sc_hd__inv_1": 1}
        total = leakage_power_sum(inv1_lib, instance_counts=counts)
        assert total == pytest.approx(0.00314)

    def test_inv1_with_instance_count_4(self, inv1_lib):
        """4 instances of the same cell → 4 × 0.00314 = 0.01256."""
        counts = {"sky130_fd_sc_hd__inv_1": 4}
        total = leakage_power_sum(inv1_lib, instance_counts=counts)
        assert total == pytest.approx(4 * 0.00314)

    def test_multi_cell_sum_no_counts(self, multi_lib):
        """Three cells: 0.00314 + 0.00520 + 0.00780 = 0.01614."""
        expected = 0.00314 + 0.00520 + 0.00780
        total = leakage_power_sum(multi_lib)
        assert total == pytest.approx(expected)

    def test_multi_cell_sum_with_counts(self, multi_lib):
        """Weighted sum: inv_1×2 + buf_1×1 + nand2_1×3."""
        counts = {"inv_1": 2, "buf_1": 1, "nand2_1": 3}
        expected = 2 * 0.00314 + 1 * 0.00520 + 3 * 0.00780
        assert leakage_power_sum(multi_lib, counts) == pytest.approx(expected)

    def test_missing_leakage_treated_as_zero(self, lib_with_missing_leakage):
        """Cell without cell_leakage_power contributes 0 to the sum."""
        total = leakage_power_sum(lib_with_missing_leakage)
        # only inv_1 has leakage; buf_1 is absent → treated as 0
        assert total == pytest.approx(0.001)

    def test_empty_library_returns_zero(self):
        src = "library (empty) { }"
        lib = parse(src)
        assert leakage_power_sum(lib) == 0.0

    def test_result_is_float(self, inv1_lib):
        total = leakage_power_sum(inv1_lib)
        assert isinstance(total, float)

    def test_instance_counts_none_equals_no_arg(self, multi_lib):
        """Passing instance_counts=None is equivalent to omitting it."""
        assert leakage_power_sum(multi_lib, None) == leakage_power_sum(multi_lib)


# ---------------------------------------------------------------------------
# leakage_per_cell
# ---------------------------------------------------------------------------

class TestLeakagePerCell:
    def test_returns_list(self, inv1_lib):
        result = leakage_per_cell(inv1_lib)
        assert isinstance(result, list)

    def test_one_entry_per_cell(self, multi_lib):
        result = leakage_per_cell(multi_lib)
        assert len(result) == 3

    def test_entry_cell_name(self, inv1_lib):
        entry = leakage_per_cell(inv1_lib)[0]
        assert isinstance(entry, CellLeakageEntry)
        assert entry.cell_name == "sky130_fd_sc_hd__inv_1"

    def test_entry_leakage_value(self, inv1_lib):
        entry = leakage_per_cell(inv1_lib)[0]
        assert entry.leakage_power_W == pytest.approx(0.00314)

    def test_missing_leakage_gives_zero_entry(self, lib_with_missing_leakage):
        entries = leakage_per_cell(lib_with_missing_leakage)
        names = {e.cell_name: e for e in entries}
        assert names["buf_1"].leakage_power_W == 0.0

    def test_entry_total_W_single_instance(self, inv1_lib):
        entry = leakage_per_cell(inv1_lib)[0]
        # default instance_count = 1 → total_W == leakage_power_W
        assert entry.total_W == pytest.approx(entry.leakage_power_W)

    def test_entry_total_W_multi_instance(self, inv1_lib):
        entry = leakage_per_cell(inv1_lib)[0]
        entry.instance_count = 3
        assert entry.total_W == pytest.approx(3 * entry.leakage_power_W)

    def test_multi_lib_values_correct(self, multi_lib):
        entries = {e.cell_name: e.leakage_power_W for e in leakage_per_cell(multi_lib)}
        assert entries["inv_1"] == pytest.approx(0.00314)
        assert entries["buf_1"] == pytest.approx(0.00520)
        assert entries["nand2_1"] == pytest.approx(0.00780)
