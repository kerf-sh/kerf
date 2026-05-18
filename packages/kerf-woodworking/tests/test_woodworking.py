"""test_woodworking.py — pytest suite for kerf-woodworking.

DoD oracles covered:
  1. Mortise+tenon volumes equal at joint engagement (shoulder_gap==0).
  2. Cut-list bin-packing is at least as efficient as first-fit-decreasing
     for a known input.
  3. Grain warning fires on a perpendicular-to-load tenon shoulder.
"""

from __future__ import annotations

import math
import unittest

from kerf_woodworking.joinery import (
    biscuit,
    dovetail,
    dowel,
    finger_joint,
    mortise_tenon,
    pocket_screw,
)
from kerf_woodworking.cut_list import (
    BoardPiece,
    optimise_cut_list,
)
from kerf_woodworking.grain import (
    GrainDirection,
    add_grain_meta,
    check_grain,
)


# ===========================================================================
# Joinery tests
# ===========================================================================


class TestMortiseTenon(unittest.TestCase):
    """Tests for the mortise-and-tenon constructor."""

    def test_returns_expected_keys(self):
        j = mortise_tenon(
            tenon_width_mm=38.0,
            tenon_height_mm=25.0,
            tenon_depth_mm=40.0,
        )
        for key in ("joint_type", "tenon_volume_mm3", "mortise_volume_mm3",
                    "engagement_mm", "volume_mm3", "warnings"):
            self.assertIn(key, j)

    def test_joint_type(self):
        j = mortise_tenon(
            tenon_width_mm=38.0,
            tenon_height_mm=25.0,
            tenon_depth_mm=40.0,
        )
        self.assertEqual(j["joint_type"], "mortise_tenon")

    # --- DoD oracle 1: volumes equal when shoulder_gap == 0 ---
    def test_volumes_equal_at_zero_gap(self):
        """Mortise volume must equal tenon volume when shoulder_gap_mm == 0."""
        j = mortise_tenon(
            tenon_width_mm=30.0,
            tenon_height_mm=20.0,
            tenon_depth_mm=35.0,
            shoulder_gap_mm=0.0,
        )
        self.assertAlmostEqual(
            j["tenon_volume_mm3"], j["mortise_volume_mm3"], places=6,
            msg="Tenon volume must equal mortise volume when shoulder_gap==0",
        )

    def test_volumes_equal_various_sizes(self):
        """Volume equality holds for multiple tenon sizes at zero gap."""
        for w, h, d in [(50, 30, 45), (10, 10, 10), (100, 80, 60)]:
            j = mortise_tenon(
                tenon_width_mm=w,
                tenon_height_mm=h,
                tenon_depth_mm=d,
                shoulder_gap_mm=0.0,
            )
            self.assertAlmostEqual(
                j["tenon_volume_mm3"], j["mortise_volume_mm3"], places=6,
                msg=f"Failed for w={w} h={h} d={d}",
            )

    def test_mortise_smaller_with_gap(self):
        """With shoulder_gap > 0, mortise must be smaller than tenon."""
        j = mortise_tenon(
            tenon_width_mm=38.0,
            tenon_height_mm=25.0,
            tenon_depth_mm=40.0,
            shoulder_gap_mm=0.2,
        )
        self.assertLess(j["mortise_volume_mm3"], j["tenon_volume_mm3"])

    def test_engagement_depth_matches_tenon_depth(self):
        j = mortise_tenon(
            tenon_width_mm=38.0,
            tenon_height_mm=25.0,
            tenon_depth_mm=55.0,
        )
        self.assertAlmostEqual(j["engagement_mm"], 55.0)

    def test_invalid_dimensions_raise(self):
        with self.assertRaises(ValueError):
            mortise_tenon(tenon_width_mm=-1, tenon_height_mm=25, tenon_depth_mm=40)
        with self.assertRaises(ValueError):
            mortise_tenon(tenon_width_mm=38, tenon_height_mm=0, tenon_depth_mm=40)

    def test_no_warnings_by_default(self):
        j = mortise_tenon(tenon_width_mm=38, tenon_height_mm=25, tenon_depth_mm=40)
        self.assertEqual(j["warnings"], [])


class TestDovetail(unittest.TestCase):
    def test_joint_type(self):
        j = dovetail(board_thickness_mm=19.0)
        self.assertEqual(j["joint_type"], "dovetail")

    def test_through_dovetail_full_engagement(self):
        j = dovetail(board_thickness_mm=20.0, half_blind=False)
        self.assertAlmostEqual(j["engagement_mm"], 20.0)

    def test_half_blind_engagement_reduced(self):
        j = dovetail(board_thickness_mm=20.0, half_blind=True, lap_mm=5.0)
        self.assertAlmostEqual(j["engagement_mm"], 15.0)

    def test_default_lap_is_quarter_thickness(self):
        j = dovetail(board_thickness_mm=20.0, half_blind=True)
        self.assertAlmostEqual(j["lap_mm"], 5.0)

    def test_tail_angle_affects_half_width(self):
        j8  = dovetail(board_thickness_mm=19.0, tail_angle_deg=8.0)
        j14 = dovetail(board_thickness_mm=19.0, tail_angle_deg=14.0)
        self.assertLess(j8["tail_half_width_mm"], j14["tail_half_width_mm"])

    def test_invalid_angle(self):
        with self.assertRaises(ValueError):
            dovetail(board_thickness_mm=19.0, tail_angle_deg=0.0)

    def test_tail_count_in_result(self):
        j = dovetail(board_thickness_mm=19.0, tail_count=6)
        self.assertEqual(j["tail_count"], 6)


class TestFingerJoint(unittest.TestCase):
    def test_joint_type(self):
        j = finger_joint(board_thickness_mm=18.0)
        self.assertEqual(j["joint_type"], "finger_joint")

    def test_finger_count_positive(self):
        j = finger_joint(board_thickness_mm=75.0, finger_width_mm=10.0, kerf_mm=3.0)
        self.assertGreaterEqual(j["finger_count"], 1)

    def test_narrow_board_at_least_one_finger(self):
        j = finger_joint(board_thickness_mm=5.0, finger_width_mm=10.0)
        self.assertEqual(j["finger_count"], 1)

    def test_invalid_dimensions(self):
        with self.assertRaises(ValueError):
            finger_joint(board_thickness_mm=0.0)


class TestDowel(unittest.TestCase):
    def test_joint_type(self):
        j = dowel()
        self.assertEqual(j["joint_type"], "dowel")

    def test_engagement_is_half_length(self):
        j = dowel(length_mm=60.0)
        self.assertAlmostEqual(j["engagement_mm"], 30.0)

    def test_bore_volume_formula(self):
        j = dowel(diameter_mm=10.0, length_mm=40.0, count=1)
        expected = math.pi * 5.0 ** 2 * 20.0
        self.assertAlmostEqual(j["bore_volume_mm3"], expected, places=3)

    def test_count_multiplied_in_total_volume(self):
        j2 = dowel(diameter_mm=8.0, length_mm=40.0, count=2)
        j4 = dowel(diameter_mm=8.0, length_mm=40.0, count=4)
        self.assertAlmostEqual(j4["volume_mm3"] / j2["volume_mm3"], 2.0, places=6)


class TestBiscuit(unittest.TestCase):
    def test_joint_type(self):
        j = biscuit()
        self.assertEqual(j["joint_type"], "biscuit")

    def test_size_20_dimensions(self):
        j = biscuit(size="#20")
        self.assertAlmostEqual(j["biscuit_length_mm"], 56.0)
        self.assertAlmostEqual(j["biscuit_width_mm"],  23.0)
        self.assertAlmostEqual(j["biscuit_thickness_mm"], 4.0)

    def test_engagement_is_half_length(self):
        j = biscuit(size="#20")
        self.assertAlmostEqual(j["engagement_mm"], 28.0)

    def test_invalid_size(self):
        with self.assertRaises(ValueError):
            biscuit(size="#99")

    def test_count_in_result(self):
        j = biscuit(count=5)
        self.assertEqual(j["count"], 5)


class TestPocketScrew(unittest.TestCase):
    def test_joint_type(self):
        j = pocket_screw()
        self.assertEqual(j["joint_type"], "pocket_screw")

    def test_engagement_positive(self):
        j = pocket_screw(board_thickness_mm=19.0, screw_length_mm=38.0)
        self.assertGreater(j["engagement_mm"], 0.0)

    def test_count_in_result(self):
        j = pocket_screw(count=4)
        self.assertEqual(j["count"], 4)

    def test_pocket_angle_is_15(self):
        j = pocket_screw()
        self.assertAlmostEqual(j["pocket_angle_deg"], 15.0)


# ===========================================================================
# Cut-list tests
# ===========================================================================


class TestCutListEmpty(unittest.TestCase):
    def test_empty_pieces(self):
        result = optimise_cut_list([], stock_length_mm=2400.0)
        self.assertEqual(result.stock_used, 0)
        self.assertEqual(result.total_waste_mm, 0.0)
        self.assertEqual(result.assignments, [])


class TestCutListBasic(unittest.TestCase):
    def test_single_piece_one_board(self):
        pieces = [BoardPiece(label="leg", length_mm=700.0)]
        result = optimise_cut_list(pieces, stock_length_mm=2400.0)
        self.assertEqual(result.stock_used, 1)
        self.assertEqual(len(result.assignments), 1)
        self.assertEqual(result.assignments[0].piece_label, "leg")

    def test_multiple_pieces_fit_one_board(self):
        pieces = [
            BoardPiece(label="rail_top",    length_mm=400.0),
            BoardPiece(label="rail_bottom", length_mm=400.0),
            BoardPiece(label="stile",       length_mm=600.0),
        ]
        result = optimise_cut_list(pieces, stock_length_mm=2400.0, kerf_mm=3.0)
        self.assertEqual(result.stock_used, 1)

    def test_utilisation_100_when_perfect_fit(self):
        # Exactly one piece of exactly the stock length with zero kerf.
        pieces = [BoardPiece(label="shelf", length_mm=2400.0)]
        result = optimise_cut_list(pieces, stock_length_mm=2400.0, kerf_mm=0.0)
        self.assertAlmostEqual(result.utilisation_pct, 100.0, places=1)


class TestCutListQuantity(unittest.TestCase):
    def test_quantity_expansion(self):
        pieces = [BoardPiece(label="leg", length_mm=700.0, quantity=4)]
        result = optimise_cut_list(pieces, stock_length_mm=2400.0)
        leg_assignments = [a for a in result.assignments if a.piece_label == "leg"]
        self.assertEqual(len(leg_assignments), 4)


class TestCutListFFD(unittest.TestCase):
    """DoD oracle 2: packing is at least as efficient as FFD.

    Reference FFD: sort pieces descending, then first-fit onto bins of
    stock_length.  Our algorithm must use <= FFD stock boards.
    """

    def _ffd_stock_count(self, lengths, stock_length, kerf):
        """Plain first-fit decreasing — reference implementation."""
        bins: list[float] = []
        for length in sorted(lengths, reverse=True):
            placed = False
            for i, rem in enumerate(bins):
                cost = length + (kerf if i >= 0 and bins else 0.0)
                if length + (kerf if bins[i] < stock_length else 0.0) <= rem + 1e-9:
                    bins[i] -= (length + kerf)
                    placed = True
                    break
            if not placed:
                bins.append(stock_length - length)
        return len(bins)

    def _reference_ffd(self, lengths, stock_length, kerf):
        """Plain FFD without look-ahead (bin remaining tracks available space)."""
        remaining: list[float] = []
        for length in sorted(lengths, reverse=True):
            placed = False
            for i, rem in enumerate(remaining):
                needed = length + (kerf if remaining[i] < stock_length else 0.0)
                if needed <= rem + 1e-9:
                    remaining[i] -= needed
                    placed = True
                    break
            if not placed:
                remaining.append(stock_length - length)
        return len(remaining)

    def test_at_least_as_efficient_as_ffd(self):
        """Our packer must use <= FFD bins for a known furniture cut list."""
        stock_len = 2400.0
        kerf = 3.175
        # Typical dining table cut list: 4 legs + 2 long rails + 4 short rails
        raw = [700, 700, 700, 700, 1500, 1500, 500, 500, 500, 500]
        pieces = [BoardPiece(label=f"p{i}", length_mm=float(l)) for i, l in enumerate(raw)]
        result = optimise_cut_list(pieces, stock_length_mm=stock_len, kerf_mm=kerf)
        ffd_count = self._reference_ffd(raw, stock_len, kerf)
        self.assertLessEqual(
            result.stock_used, ffd_count,
            msg=f"Our packer used {result.stock_used} boards; FFD used {ffd_count}",
        )

    def test_known_input_stock_count(self):
        """Verify a manually-verifiable cut list uses the expected board count."""
        # 3 pieces of 1000 mm on 2400 mm stock with 3.175 mm kerf:
        # Two pieces fit in one board (1000+3.175+1000 = 2003.175 <= 2400),
        # one piece needs a second board.  Expect 2 boards.
        pieces = [BoardPiece(label=f"shelf{i}", length_mm=1000.0) for i in range(3)]
        result = optimise_cut_list(pieces, stock_length_mm=2400.0, kerf_mm=3.175)
        self.assertLessEqual(result.stock_used, 2)

    def test_waste_is_non_negative(self):
        pieces = [BoardPiece(label="a", length_mm=800.0, quantity=3)]
        result = optimise_cut_list(pieces, stock_length_mm=2400.0)
        self.assertGreaterEqual(result.total_waste_mm, 0.0)

    def test_utilisation_between_0_and_100(self):
        pieces = [BoardPiece(label="b", length_mm=600.0, quantity=5)]
        result = optimise_cut_list(pieces, stock_length_mm=2400.0)
        self.assertGreaterEqual(result.utilisation_pct, 0.0)
        self.assertLessEqual(result.utilisation_pct, 100.0)

    def test_off_cut_count_matches_stock_with_leftovers(self):
        pieces = [BoardPiece(label="c", length_mm=1000.0)]
        result = optimise_cut_list(pieces, stock_length_mm=2400.0)
        # One board used, one off-cut
        self.assertEqual(len(result.off_cuts), 1)
        self.assertAlmostEqual(
            result.off_cuts[0]["length_mm"], 2400.0 - 1000.0, places=1
        )


class TestCutListGrainWarning(unittest.TestCase):
    def test_across_grain_piece_warns(self):
        pieces = [
            BoardPiece(label="cross_rail", length_mm=400.0, grain_direction="across")
        ]
        result = optimise_cut_list(pieces, stock_length_mm=2400.0)
        self.assertTrue(
            any("cross_rail" in w for w in result.warnings),
            msg="Expected grain warning for across-grain piece",
        )

    def test_along_grain_no_warning(self):
        pieces = [BoardPiece(label="leg", length_mm=700.0, grain_direction="along")]
        result = optimise_cut_list(pieces, stock_length_mm=2400.0)
        self.assertFalse(
            any("grain" in w.lower() for w in result.warnings),
        )


# ===========================================================================
# Grain tests
# ===========================================================================


class TestGrainCheck(unittest.TestCase):
    # --- DoD oracle 3: grain warning fires on perpendicular-to-load tenon shoulder ---
    def test_across_shoulder_grain_warns(self):
        """A mortise-tenon with shoulder_grain='across' must produce a grain warning."""
        j = mortise_tenon(
            tenon_width_mm=38.0,
            tenon_height_mm=25.0,
            tenon_depth_mm=40.0,
        )
        add_grain_meta(j, shoulder_grain=GrainDirection.ACROSS)
        grain_warnings = [w for w in j["warnings"] if w.get("kind") == "grain_warning"]
        self.assertTrue(
            len(grain_warnings) > 0,
            msg="Expected at least one grain_warning for across-grain tenon shoulder",
        )
        self.assertTrue(
            any(w["direction"] == "across" for w in grain_warnings),
        )

    def test_along_shoulder_grain_no_warn(self):
        """Along-grain shoulder must not produce a grain warning."""
        j = mortise_tenon(
            tenon_width_mm=38.0,
            tenon_height_mm=25.0,
            tenon_depth_mm=40.0,
        )
        add_grain_meta(j, shoulder_grain=GrainDirection.ALONG)
        grain_warnings = [w for w in j["warnings"] if w.get("kind") == "grain_warning"]
        self.assertEqual(grain_warnings, [])

    def test_across_grain_direction_warns(self):
        j = {"joint_type": "generic", "grain_direction": "across"}
        w = check_grain(j)
        self.assertTrue(len(w) > 0)
        self.assertTrue(any(w_["direction"] == "across" for w_ in w))

    def test_pocket_screw_end_grain_warns(self):
        j = pocket_screw()
        add_grain_meta(j, target_grain="end")
        grain_warnings = [w for w in j["warnings"] if w.get("kind") == "grain_warning"]
        self.assertTrue(len(grain_warnings) > 0)
        self.assertTrue(any("end" in w["direction"] for w in grain_warnings))

    def test_dovetail_across_board_grain_errors(self):
        j = dovetail(board_thickness_mm=19.0)
        add_grain_meta(j, board_grain=GrainDirection.ACROSS)
        grain_warnings = [w for w in j["warnings"] if w.get("kind") == "grain_warning"]
        self.assertTrue(any(w["severity"] == "error" for w in grain_warnings))

    def test_check_grain_returns_list(self):
        j = {"joint_type": "dowel"}
        result = check_grain(j)
        self.assertIsInstance(result, list)

    def test_add_grain_meta_mutates_and_returns_same_dict(self):
        j = mortise_tenon(tenon_width_mm=30, tenon_height_mm=20, tenon_depth_mm=35)
        returned = add_grain_meta(j, grain_direction="along")
        self.assertIs(returned, j)
        self.assertEqual(j["grain_direction"], "along")


# ===========================================================================
# Tool surface smoke tests (sync import, no async runner needed)
# ===========================================================================


class TestToolsImport(unittest.TestCase):
    def test_tools_module_importable(self):
        import kerf_woodworking.tools as t
        self.assertTrue(hasattr(t, "woodworking_mortise_tenon"))

    def test_registry_populated(self):
        # Ensure tools module is imported so @register decorators run.
        import kerf_woodworking.tools  # noqa: F401
        from kerf_woodworking._compat import Registry
        names = [tool.spec.name for tool in Registry]
        self.assertIn("woodworking_mortise_tenon", names)
        self.assertIn("woodworking_cut_list", names)
        self.assertIn("woodworking_grain_check", names)

    def test_plugin_importable(self):
        import kerf_woodworking.plugin as p
        self.assertTrue(callable(p.register))


if __name__ == "__main__":
    unittest.main()
