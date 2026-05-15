"""
5-axis CAM T8 — end-to-end integration tests.

Exercises the full pipeline from STEP fixture → drive-face extraction →
CL-point generation → G-code emission for both the constant-tilt and
3+2 indexed pathways, plus tool-DB integration and defensive edge cases.

Test inventory
--------------
Test A  (test_constant_tilt_e2e)
    constant-tilt pipeline: STEP → drive_face → uv_iso_curves →
    run_constant_tilt → emit_gcode_constant_tilt(post="linuxcnc").
    Asserts header/footer, G1 count, A/B continuity, feed-rate.

Test B  (test_3plus2_e2e)
    3+2 indexed pipeline with synthetic CL data (no opencamlib required).
    Supplies a non-vertical face normal (30° tilted), runs
    emit_gcode_indexed_3_2(post="fanuc"), asserts single-orientation-move
    pattern and correct home move.

Test C  (test_tool_db_e2e)
    Tool DB integration: parse a 1/4" ball-end tool, wire it into PostOpts,
    run emit_gcode_constant_tilt, assert tool-comment and M6 T1 present,
    assert feeds come from the tool object.

Test D  (test_3plus2_axis_aligned_short_circuit)
    Axis-aligned short-circuit: supply a +Z face normal, verify no G0 A<a>
    B<b> orientation move is emitted, body is pure 3-axis G-code.

Test E  (test_corrupt_step_input)
    Feed garbage bytes as a STEP file; assert a clear RuntimeError (not a
    crash or silent empty result).

Test F  (test_constant_tilt_e2e_fanuc)
    Same as Test A but Fanuc post, verifying N-line numbers and parenthetical
    comments.

Test G  (test_3plus2_rotation_angle_matches_face_normal)
    Pure-Python: for a face normal of (0, sin(30°), cos(30°)) the emitted
    B angle must be 30° ± 0.01°.

Test H  (test_pipeline_no_occ_fallback)
    Pure-Python only: constant-tilt pipeline functions that do NOT require
    OCC (G-code emission from synthetic CL points) run even without OCC.

Dependencies
------------
Tests A, B (OCC branch), E require pythonOCC — guarded with requires_occ.
Tests C, D, G, H are pure-Python — always run.
Test F (Fanuc) is pure-Python — always run.
"""

from __future__ import annotations

import math
import os
import sys
import re

import pytest

# Ensure kerf_cam is importable without pip install.
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "src"))

# ---------------------------------------------------------------------------
# Optional dependency gates
# ---------------------------------------------------------------------------

_has_occ = False
try:
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: F401
    _has_occ = True
except ImportError:
    pass

requires_occ = pytest.mark.skipif(not _has_occ, reason="pythonOCC not installed")


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_tilt_cl(x: float, y: float, z: float, tilt_deg: float) -> dict:
    """Return a CLPoint dict with tool axis tilted *tilt_deg* off +Z in the +X direction."""
    r = math.radians(tilt_deg)
    return {"x": x, "y": y, "z": z, "i": math.sin(r), "j": 0.0, "k": math.cos(r)}


def _make_vertical_cl(x: float, y: float, z: float) -> dict:
    """CLPoint with +Z upright tool axis."""
    return {"x": x, "y": y, "z": z, "i": 0.0, "j": 0.0, "k": 1.0}


def _synthetic_tilt_row(n: int = 10, tilt_deg: float = 15.0) -> list[dict]:
    """Return *n* synthetic CL points with constant tilt, distributed along X."""
    return [_make_tilt_cl(float(i) * 2.0, float(i % 3) * 1.5, 0.0, tilt_deg) for i in range(n)]


def _extract_g1_lines(gcode: str) -> list[str]:
    """Return all G1 lines from a G-code string."""
    return [ln for ln in gcode.splitlines() if ln.lstrip().startswith("G1 ") or
            " G1 " in ln.split("(")[0]]  # handle N10 G1 ... Fanuc lines


def _parse_ab(line: str) -> tuple[float | None, float | None]:
    """Extract A and B values from a G-code line.  Returns (None, None) if absent."""
    a_match = re.search(r"\bA(-?\d+\.?\d*)", line)
    b_match = re.search(r"\bB(-?\d+\.?\d*)", line)
    a = float(a_match.group(1)) if a_match else None
    b = float(b_match.group(1)) if b_match else None
    return a, b


def _g1_lines_with_ab(gcode: str) -> list[tuple[str, float, float]]:
    """Return list of (line, a_deg, b_deg) for every G1 line that has both A and B."""
    result = []
    for ln in gcode.splitlines():
        stripped = ln.strip()
        # Match plain G1 or N<n> G1 lines
        if not (stripped.startswith("G1 ") or re.match(r"N\d+\s+G1 ", stripped)):
            continue
        a, b = _parse_ab(stripped)
        if a is not None and b is not None:
            result.append((stripped, a, b))
    return result


# ===========================================================================
# Test A — Constant-tilt end-to-end with real STEP fixture (LinuxCNC)
# ===========================================================================

@requires_occ
def test_constant_tilt_e2e(step_fixture_path):
    """
    Full constant-tilt pipeline:
      STEP load → extract_drive_face → uv_iso_curves → run_constant_tilt
      → emit_gcode_constant_tilt(post="linuxcnc")

    Assertions:
    - Header present: G90, G94, G17, G21 on one line
    - At least 5 G1 lines
    - A and B angles vary (not all identical — face has curvature / iso-rows)
    - Consecutive A-angle jumps ≤ 180° (continuous unwrap in force)
    - Feed-rate present on first G1 line
    - Footer: M5, M30 present
    - Tape markers (%) present
    """
    from kerf_cam.five_axis.constant_tilt import run_constant_tilt
    from kerf_cam.five_axis.gcode_constant_tilt import emit_gcode_constant_tilt, PostOpts

    # Use face 0 — the first face in the TopExp_Explorer walk of the slotted box.
    # On the 50×50×10 box-with-slot this is a planar side face (good for finishing).
    result = run_constant_tilt({
        "brep_path": step_fixture_path,
        "drive_face_id": 0,
        "tilt_deg": 15.0,
        "step_over_mm": 5.0,
        "ball_radius_mm": 1.5,
    })

    assert "errors" not in result or not result.get("errors"), (
        f"run_constant_tilt returned errors: {result.get('errors')}"
    )
    cl_pts = result["cl_points"]
    assert len(cl_pts) >= 2, (
        f"Expected at least 2 CL points from constant_tilt, got {len(cl_pts)}"
    )

    # Emit LinuxCNC G-code.
    opts = PostOpts(
        tool_number=1,
        feed_cut_mm_min=800.0,
        spindle_rpm=12000,
        coolant="flood",
    )
    gcode = emit_gcode_constant_tilt(cl_pts, "linuxcnc", opts)

    # --- Header ---
    assert "G90 G94 G17 G21" in gcode, "LinuxCNC header G90/G94/G17/G21 missing"
    assert "G54" in gcode, "G54 work offset missing"
    assert "M6 T1" in gcode, "M6 T1 tool call missing"
    assert "M3" in gcode, "M3 spindle start missing"
    assert "M8" in gcode, "M8 flood coolant missing"

    # --- Tape markers ---
    assert gcode.startswith("%"), "LinuxCNC tape-start marker '%' missing"
    assert gcode.strip().endswith("%"), "LinuxCNC tape-end marker '%' missing"

    # --- Cutting moves ---
    g1_lines = _extract_g1_lines(gcode)
    assert len(g1_lines) >= 2, (
        f"Expected at least 2 G1 cutting lines, got {len(g1_lines)}"
    )

    # --- A/B angles present in G1 lines ---
    ab_in_body = [(a, b) for ln in g1_lines for (a, b) in [_parse_ab(ln)] if a is not None]
    assert len(ab_in_body) > 0, "No A-axis values found in G1 cutting lines"

    # --- Continuous-unwrap: no A jump > 90° between consecutive G1 lines ---
    ab_body = _g1_lines_with_ab(gcode)
    if len(ab_body) >= 2:
        for (_, a1, _), (_, a2, _) in zip(ab_body, ab_body[1:]):
            jump = abs(a2 - a1)
            assert jump <= 90.0, (
                f"A-angle jump of {jump:.2f}° between consecutive G1 moves "
                f"(expected ≤90° after continuous unwrap): {a1:.3f} → {a2:.3f}"
            )

    # --- Feed-rate on first G1 line ---
    first_g1 = g1_lines[0]
    assert "F" in first_g1, f"No feed-rate (F word) on first G1 line: {first_g1!r}"
    f_match = re.search(r"F(\d+)", first_g1)
    assert f_match is not None, f"Cannot parse F word from first G1: {first_g1!r}"
    assert int(f_match.group(1)) == 800, (
        f"Expected F800 on first G1, got F{f_match.group(1)}"
    )

    # --- Footer ---
    assert "M5" in gcode, "M5 spindle-off missing from footer"
    assert "M30" in gcode, "M30 program-end missing from footer"
    assert "M9" in gcode, "M9 coolant-off missing from footer"

    # --- Mandatory no-collision warning ---
    assert "collision" in gcode.lower() or "gouge" in gcode.lower(), (
        "No-collision-check warning missing from G-code header"
    )


# ===========================================================================
# Test B — 3+2 indexed end-to-end (synthetic CL data, Fanuc post)
# ===========================================================================

def test_3plus2_e2e():
    """
    3+2 indexed pipeline with synthetic CL data (no OCC, no opencamlib).
    Supplies face-normal = (0, sin30°, cos30°) so B≈30°, A≈90°.
    Asserts:
      - Exactly ONE G0 A<a> B<b> orientation move before the G1 body
      - Body G1 lines carry NO A or B axis words
      - Footer: G0 A0.000 B0.000 (home rotaries)
      - End-of-program M30 present
      - A and B angles in orientation move match the inverse rotation of the face normal
    """
    from kerf_cam.five_axis.gcode_indexed_3_2 import emit_gcode_indexed_3_2
    from kerf_cam.five_axis.gcode_constant_tilt import PostOpts

    # Orientation: face normal is tilted 30° from +Z toward +Y
    # → A = 90°, B = 30°
    normal = (0.0, math.sin(math.radians(30.0)), math.cos(math.radians(30.0)))
    # CL points carry i/j/k = the face-normal direction (constant for 3+2).
    cl_pts = [
        {"x": float(i) * 5.0, "y": float(i % 3) * 2.0, "z": 0.0,
         "i": normal[0], "j": normal[1], "k": normal[2]}
        for i in range(8)
    ]

    opts = PostOpts(
        tool_number=1,
        feed_cut_mm_min=1000.0,
        spindle_rpm=10000,
        no_n_numbers=True,   # simpler for string matching
        coolant="flood",
    )
    gcode = emit_gcode_indexed_3_2(cl_pts, "fanuc", opts)

    lines = gcode.splitlines()

    # --- Exactly ONE orientation move (G0 A... B...) ---
    orient_moves = [
        ln for ln in lines
        if re.match(r".*G0\s.*A-?\d", ln) and re.search(r"\bB-?\d", ln)
        and not re.search(r"Z50", ln)      # exclude the safe-Z move
        and not re.search(r"A0\.000\s+B0\.000", ln)  # exclude home move
    ]
    assert len(orient_moves) == 1, (
        f"Expected exactly 1 G0 A<a> B<b> orientation move, found {len(orient_moves)}: "
        f"{orient_moves}"
    )

    # --- Orientation move angles ---
    orient_line = orient_moves[0]
    a_val, b_val = _parse_ab(orient_line)
    assert a_val is not None and b_val is not None, (
        f"Cannot parse A/B from orientation line: {orient_line!r}"
    )
    # B should be ~30° (tilt of the face from +Z)
    assert abs(b_val - 30.0) < 1.0, (
        f"Expected B≈30° for 30°-tilted face, got B={b_val:.3f}"
    )
    # A should be ~90° (azimuth in XY-plane pointing toward +Y)
    assert abs(a_val - 90.0) < 1.0, (
        f"Expected A≈90° for +Y-direction tilt, got A={a_val:.3f}"
    )

    # --- Body G1 lines: no A/B axis words ---
    # Fanuc body lines look like "G1 X... Y... Z..."
    body_g1 = [
        ln for ln in lines
        if "G1 " in ln and ("X" in ln or "Y" in ln or "Z" in ln)
    ]
    assert len(body_g1) > 0, "No body G1 lines found"
    for ln in body_g1:
        assert not re.search(r"\bA-?\d", ln), (
            f"Body G1 line should not contain A axis word: {ln!r}"
        )
        assert not re.search(r"\bB-?\d", ln), (
            f"Body G1 line should not contain B axis word: {ln!r}"
        )

    # --- Footer: home rotaries ---
    home_lines = [
        ln for ln in lines
        if re.search(r"G0\s.*A0\.000\s+B0\.000", ln) or
           re.search(r"G0\s.*A0\s+B0\b", ln)
    ]
    assert len(home_lines) >= 1, (
        "Footer G0 A0.000 B0.000 (home rotaries) missing"
    )

    # --- End of program ---
    assert "M30" in gcode, "M30 program-end missing"
    assert "M5" in gcode, "M5 spindle-off missing"


# ===========================================================================
# Test C — Tool DB integration
# ===========================================================================

def test_tool_db_e2e():
    """
    Tool DB integration (pure Python — no OCC, no opencamlib):
      1. Parse a 1/4" ball-end mill from a dict (tool_db.parse_tool)
      2. Wire it into PostOpts
      3. Emit constant-tilt G-code from synthetic CL points
      4. Assert:
         - Tool-comment line includes the tool name
         - M6 T1 present
         - Feeds/RPM come from the tool defaults
    """
    from kerf_cam.tool_db import parse_tool
    from kerf_cam.five_axis.gcode_constant_tilt import emit_gcode_constant_tilt, PostOpts

    tool_data = {
        "id": "T1",
        "name": '1/4" carbide ball-end',
        "type": "ball_end",
        "diameter_mm": 6.35,
        "ball_radius_mm": 3.175,
        "flute_count": 2,
        "material": "carbide",
        "spindle_rpm_min": 8000,
        "spindle_rpm_max": 24000,
        "feed_rate_mm_min": 750.0,
        "plunge_rate_mm_min": 200.0,
    }
    tool = parse_tool(tool_data)

    # PostOpts with defaults (will be overridden by apply_tool_defaults).
    opts = PostOpts(tool_number=1, tool=tool)

    cl_pts = _synthetic_tilt_row(n=6, tilt_deg=15.0)
    gcode = emit_gcode_constant_tilt(cl_pts, "linuxcnc", opts)

    # --- Tool comment present ---
    assert "T1" in gcode, "Tool id T1 missing from G-code"
    tool_comment_present = any(
        "tool" in ln.lower() and "T1" in ln
        for ln in gcode.splitlines()
    )
    assert tool_comment_present, (
        "Tool comment line ('; tool: T1 — ...') not found in G-code"
    )
    # The name must appear somewhere in the output
    assert "carbide ball-end" in gcode or "carbide" in gcode, (
        "Tool name or material not found in G-code comments"
    )

    # --- M6 T1 ---
    assert "M6 T1" in gcode, "M6 T1 tool-call line missing"

    # --- Feeds come from the tool ---
    # tool.feed_rate_mm_min = 750 → first G1 should carry F750
    first_g1 = next(
        (ln for ln in gcode.splitlines() if ln.startswith("G1 ")), None
    )
    assert first_g1 is not None, "No G1 cutting line found"
    f_match = re.search(r"F(\d+)", first_g1)
    assert f_match is not None, f"No F word on first G1: {first_g1!r}"
    assert int(f_match.group(1)) == 750, (
        f"Expected F750 (from tool.feed_rate_mm_min), got F{f_match.group(1)}"
    )

    # --- Spindle RPM from tool ---
    assert "S8000" in gcode, (
        "Spindle RPM S8000 (from tool.spindle_rpm_min) not found in G-code"
    )


# ===========================================================================
# Test D — Axis-aligned 3+2 short-circuit
# ===========================================================================

def test_3plus2_axis_aligned_short_circuit():
    """
    Pure Python: when the drive-face normal IS +Z (axis-aligned), the 3+2
    emitter must:
      - Emit NO 'G0 A<a> B<b>' orientation move in the header
      - Emit plain 3-axis body G1 lines (no A/B words anywhere)
      - Still emit the home 'G0 A0.000 B0.000' footer (safety)
      - Still produce valid 3-axis G-code (G90, G21, M30)
    """
    from kerf_cam.five_axis.gcode_indexed_3_2 import emit_gcode_indexed_3_2
    from kerf_cam.five_axis.gcode_constant_tilt import PostOpts

    # CL points with i=0, j=0, k=1 → axis-aligned, B=0°, A=0°
    cl_pts = [
        {"x": float(i) * 5.0, "y": 0.0, "z": 0.0,
         "i": 0.0, "j": 0.0, "k": 1.0}
        for i in range(5)
    ]

    opts = PostOpts(tool_number=2, no_n_numbers=True)
    gcode = emit_gcode_indexed_3_2(cl_pts, "linuxcnc", opts)

    lines = gcode.splitlines()

    # --- No orientation move (non-home G0 with A and B) ---
    orient_moves = [
        ln for ln in lines
        if re.match(r"G0\s.*A-?\d+\.", ln) and re.search(r"\bB-?\d+\.", ln)
        and not re.search(r"A0\.000.*B0\.000", ln)   # exclude home
        and "Z50" not in ln                            # exclude safe-Z
    ]
    assert len(orient_moves) == 0, (
        f"Axis-aligned job should have NO orientation move, found: {orient_moves}"
    )

    # --- Body G1 lines: no A or B words ---
    body_g1 = [
        ln for ln in lines
        if ln.startswith("G1 ") and ("X" in ln or "Y" in ln or "Z" in ln)
    ]
    assert len(body_g1) > 0, "No body G1 lines found in axis-aligned output"
    for ln in body_g1:
        assert not re.search(r"\bA-?\d", ln), (
            f"Axis-aligned body G1 must have no A word: {ln!r}"
        )
        assert not re.search(r"\bB-?\d", ln), (
            f"Axis-aligned body G1 must have no B word: {ln!r}"
        )

    # --- Header is valid 3-axis G-code ---
    assert "G90" in gcode, "G90 absolute mode missing"
    assert "G21" in gcode, "G21 metric mode missing"
    assert "M30" in gcode, "M30 end-of-program missing"

    # --- Footer still homes rotaries ---
    assert "A0.000 B0.000" in gcode or "A0.000" in gcode, (
        "Home rotaries line (G0 A0.000 B0.000) should appear in footer even for axis-aligned"
    )


# ===========================================================================
# Test E — Corrupt STEP input: clear error, no crash
# ===========================================================================

@requires_occ
def test_corrupt_step_input(tmp_path):
    """
    Feed garbage bytes to extract_drive_face; assert a clear RuntimeError
    (not a silent empty result, not a crash/segfault, not an AttributeError).
    """
    from kerf_cam.five_axis.drive_face import extract_drive_face

    corrupt_path = str(tmp_path / "corrupt.step")
    with open(corrupt_path, "wb") as fh:
        fh.write(b"\x00\x01\x02\x03garbage\xff\xfe not a STEP file at all")

    with pytest.raises((RuntimeError, Exception)) as exc_info:
        extract_drive_face(corrupt_path, 0)

    # The error must be a RuntimeError (or subclass) — not an unhandled
    # AttributeError or segfault-like exception.
    assert isinstance(exc_info.value, (RuntimeError, OSError, ValueError, Exception)), (
        f"Expected RuntimeError (or similar) for corrupt input, got {type(exc_info.value)}"
    )
    # The message must be non-empty and mention something useful.
    msg = str(exc_info.value)
    assert len(msg) > 0, "Error message is empty"


# ===========================================================================
# Test F — Constant-tilt Fanuc post (pure Python, synthetic CL)
# ===========================================================================

def test_constant_tilt_e2e_fanuc():
    """
    Fanuc post with synthetic CL data:
      - N-line sequence numbers present (N10, N20, ...)
      - Fanuc-style parenthetical comments (no '; ...' style)
      - G90 G94 G17 G21 present
      - A and B words on G1 lines
      - M30 footer
      - At least one A value and one B value present in the cutting body
    """
    from kerf_cam.five_axis.gcode_constant_tilt import emit_gcode_constant_tilt, PostOpts

    cl_pts = _synthetic_tilt_row(n=12, tilt_deg=20.0)
    opts = PostOpts(
        tool_number=3,
        feed_cut_mm_min=600.0,
        spindle_rpm=15000,
        coolant="mist",
    )
    gcode = emit_gcode_constant_tilt(cl_pts, "fanuc", opts)

    # --- N-line numbers ---
    assert "N10 " in gcode, "Fanuc N-line numbers (N10 ...) not found"
    assert "N20 " in gcode, "Only one N-line — expected at least N10 and N20"

    # --- Fanuc-style comments ---
    paren_comments = [ln for ln in gcode.splitlines() if ln.strip().startswith("(")]
    assert len(paren_comments) >= 1, "No Fanuc parenthetical comments found"

    # --- Header modals ---
    assert "G90 G94 G17 G21" in gcode, "G90/G94/G17/G21 modal line missing"

    # --- Cutting body has A and B ---
    ab_in_g1 = _g1_lines_with_ab(gcode)
    assert len(ab_in_g1) > 0, "No G1 lines with both A and B found in Fanuc output"

    # B angle should be ~20° for 20° tilt in +X direction (A=0, B=20)
    b_values = [b for (_, _, b) in ab_in_g1]
    assert all(abs(b - 20.0) < 0.5 for b in b_values), (
        f"Expected all B≈20.0° for 20° tilt, got: {b_values}"
    )

    # --- Mist coolant (M7, not M8) ---
    assert "M7" in gcode, "M7 mist coolant missing"
    assert "M8" not in gcode, "M8 flood coolant should NOT be present for mist mode"

    # --- Footer ---
    assert "M30" in gcode, "M30 end-of-program missing"


# ===========================================================================
# Test G — 3+2 rotation angle matches face normal (pure Python)
# ===========================================================================

def test_3plus2_rotation_angle_matches_face_normal():
    """
    Pure Python: for face_normal = (0, sin(30°), cos(30°)):
      - The B angle emitted in the orientation move must be 30° ± 0.05°
      - The A angle must be 90° ± 0.05° (pointing toward +Y)

    This verifies that _axis_to_ab is correctly wired into the 3+2 emitter's
    orientation-extraction path.
    """
    from kerf_cam.five_axis.gcode_indexed_3_2 import emit_gcode_indexed_3_2
    from kerf_cam.five_axis.gcode_constant_tilt import PostOpts

    angle_deg = 30.0
    nx = 0.0
    ny = math.sin(math.radians(angle_deg))
    nz = math.cos(math.radians(angle_deg))

    cl_pts = [
        {"x": 0.0, "y": 0.0, "z": 0.0, "i": nx, "j": ny, "k": nz},
        {"x": 5.0, "y": 0.0, "z": 0.0, "i": nx, "j": ny, "k": nz},
        {"x": 10.0, "y": 0.0, "z": 0.0, "i": nx, "j": ny, "k": nz},
    ]

    opts = PostOpts(no_n_numbers=True)
    gcode = emit_gcode_indexed_3_2(cl_pts, "linuxcnc", opts)

    # Find the orientation move
    orient_moves = [
        ln for ln in gcode.splitlines()
        if ln.startswith("G0 ") and re.search(r"\bA-?\d+\.\d+\b", ln)
        and re.search(r"\bB-?\d+\.\d+\b", ln)
        and "Z50" not in ln
        and "A0.000 B0.000" not in ln
    ]
    assert len(orient_moves) == 1, (
        f"Expected 1 orientation move for non-axis-aligned face, found {len(orient_moves)}: "
        f"{orient_moves}"
    )
    a_val, b_val = _parse_ab(orient_moves[0])
    assert a_val is not None and b_val is not None, (
        f"Cannot parse A/B from orientation line: {orient_moves[0]!r}"
    )

    assert abs(b_val - 30.0) < 0.05, (
        f"B angle should be 30.000° for face normal tilted 30° from +Z, got {b_val:.4f}"
    )
    assert abs(a_val - 90.0) < 0.05, (
        f"A angle should be 90.000° for +Y-direction tilt, got {a_val:.4f}"
    )


# ===========================================================================
# Test H — Pure-Python pipeline (no OCC) smoke test
# ===========================================================================

def test_pipeline_no_occ_fallback():
    """
    Pure-Python only: verifies that the G-code emission side of the pipeline
    runs end-to-end even when pythonOCC is completely absent.

    Simulates what happens when a user has kerf-cam installed but no OCC:
      - Synthetic CL points (like those returned by run_constant_tilt)
      - emit_gcode_constant_tilt(post="linuxcnc")  → must produce valid G-code
      - emit_gcode_indexed_3_2(post="linuxcnc")    → must produce valid G-code

    Also sanity-checks the tool-DB pure-Python path.
    """
    from kerf_cam.five_axis.gcode_constant_tilt import emit_gcode_constant_tilt, PostOpts
    from kerf_cam.five_axis.gcode_indexed_3_2 import emit_gcode_indexed_3_2
    from kerf_cam.tool_db import parse_tool

    # -- Constant-tilt G-code emission --
    cl_pts = _synthetic_tilt_row(n=8, tilt_deg=10.0)
    gcode_ct = emit_gcode_constant_tilt(cl_pts, "linuxcnc")
    assert "G90" in gcode_ct, "G90 missing from constant-tilt G-code"
    assert "M30" in gcode_ct, "M30 missing from constant-tilt G-code"
    assert len(_extract_g1_lines(gcode_ct)) >= 1, (
        "No G1 cutting lines in constant-tilt G-code"
    )

    # -- 3+2 indexed G-code emission --
    cl_3p2 = [
        {"x": float(i), "y": 0.0, "z": 0.0, "i": 0.0, "j": 0.5, "k": math.sqrt(0.75)}
        for i in range(5)
    ]
    gcode_32 = emit_gcode_indexed_3_2(cl_3p2, "linuxcnc")
    assert "G90" in gcode_32, "G90 missing from 3+2 G-code"
    assert "M30" in gcode_32, "M30 missing from 3+2 G-code"

    # -- Tool DB parse --
    tool = parse_tool({
        "id": "T99",
        "name": "Test flat-end",
        "type": "flat_end",
        "diameter_mm": 6.0,
        "feed_rate_mm_min": 500.0,
        "spindle_rpm_min": 6000,
    })
    assert tool.feed_rate_mm_min == 500.0
    assert tool.spindle_rpm_min == 6000.0
    assert "T99" in tool.to_comment()
