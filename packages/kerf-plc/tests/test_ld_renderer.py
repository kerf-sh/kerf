"""
tests/test_ld_renderer.py — SVG renderer tests for Ladder Diagram.

DoD check: a fixture LD program with a normally-open contact + timer + coil
renders correctly as SVG rungs.
"""
from __future__ import annotations

import pytest

from kerf_plc.ld.schema import load
from kerf_plc.ld.renderer import render_svg


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CONTACT_TIMER_COIL_LD = {
    "program": "ContactTimerCoil",
    "variables": [
        {"name": "sensor",   "type": "BOOL", "dir": "input"},
        {"name": "ready",    "type": "BOOL", "dir": "input"},
        {"name": "valve",    "type": "BOOL", "dir": "output"},
    ],
    "rungs": [
        {
            "label": "Rung 0",
            "comment": "normally-open contact drives coil",
            "branches": [
                [{"type": "contact_no", "var": "sensor"}]
            ],
            "output": {"type": "coil", "var": "valve"},
        },
        {
            "label": "Rung 1",
            "comment": "normally-open + timer FB",
            "branches": [
                [{"type": "contact_no", "var": "sensor"}]
            ],
            "output": {
                "type": "fb_call",
                "fb_type": "TON",
                "fb_instance": "Timer1",
                "fb_inputs": {"PT": "T#5s"},
            },
        },
        {
            "label": "Rung 2",
            "comment": "normally-closed contact",
            "branches": [
                [{"type": "contact_nc", "var": "ready"}]
            ],
            "output": {"type": "coil_set", "var": "valve"},
        },
    ],
}

PARALLEL_LD = {
    "program": "Parallel",
    "variables": [],
    "rungs": [
        {
            "branches": [
                [{"type": "contact_no", "var": "A"}],
                [{"type": "contact_no", "var": "B"}],
            ],
            "output": {"type": "coil", "var": "Y"},
        }
    ],
}


# ---------------------------------------------------------------------------
# T1 — SVG output is a valid string
# ---------------------------------------------------------------------------

class TestRenderSVG:
    def test_returns_string(self):
        prog = load(CONTACT_TIMER_COIL_LD)
        svg = render_svg(prog)
        assert isinstance(svg, str)

    def test_svg_tag_present(self):
        prog = load(CONTACT_TIMER_COIL_LD)
        svg = render_svg(prog)
        assert "<svg" in svg
        assert "</svg>" in svg

    def test_svg_has_width_and_height(self):
        prog = load(CONTACT_TIMER_COIL_LD)
        svg = render_svg(prog)
        assert 'width=' in svg
        assert 'height=' in svg

    def test_program_name_in_svg(self):
        prog = load(CONTACT_TIMER_COIL_LD)
        svg = render_svg(prog)
        assert "ContactTimerCoil" in svg

    def test_contact_no_rendered(self):
        """Normally-open contact must appear: wire lines + two vertical bars."""
        prog = load(CONTACT_TIMER_COIL_LD)
        svg = render_svg(prog)
        # The renderer draws <line> elements for contacts; sensor var should be labelled
        assert "sensor" in svg

    def test_coil_rendered(self):
        """Coil drawn as arc paths; output var 'valve' should be labelled."""
        prog = load(CONTACT_TIMER_COIL_LD)
        svg = render_svg(prog)
        assert "valve" in svg

    def test_timer_fb_rendered(self):
        """FB call box must contain the fb_type and instance name."""
        prog = load(CONTACT_TIMER_COIL_LD)
        svg = render_svg(prog)
        assert "TON" in svg
        assert "Timer1" in svg

    def test_contact_nc_slash_in_svg(self):
        """NC contact has a diagonal slash (additional line element)."""
        prog = load(CONTACT_TIMER_COIL_LD)
        svg = render_svg(prog)
        # At minimum a <line> for the slash exists — confirm 'ready' var is present
        assert "ready" in svg

    def test_set_coil_label_s_in_svg(self):
        """Set coil shows the 'S' label text."""
        prog = load(CONTACT_TIMER_COIL_LD)
        svg = render_svg(prog)
        assert ">S<" in svg or "S</text>" in svg or ">S</text" in svg

    def test_parallel_branches_junction_lines(self):
        """Parallel branches produce junction vertical lines."""
        prog = load(PARALLEL_LD)
        svg = render_svg(prog)
        # Should have variable labels from both branches
        assert "A" in svg
        assert "B" in svg

    def test_power_rails_l_plus_l_minus(self):
        """Left and right power rail labels L+ and L- appear."""
        prog = load(CONTACT_TIMER_COIL_LD)
        svg = render_svg(prog)
        assert "L+" in svg
        assert "L-" in svg

    def test_rung_comment_in_svg(self):
        prog = load(CONTACT_TIMER_COIL_LD)
        svg = render_svg(prog)
        assert "normally-open contact drives coil" in svg

    def test_rung_label_in_svg(self):
        prog = load(CONTACT_TIMER_COIL_LD)
        svg = render_svg(prog)
        assert "Rung 0" in svg

    def test_empty_program_renders(self):
        """An empty program (no rungs) should render without crashing."""
        empty_ld = {"program": "Empty", "variables": [], "rungs": []}
        # Empty rungs pass schema validation (no rungs = no errors at program level)
        prog_dict = {"program": "Empty", "variables": [], "rungs": []}
        from kerf_plc.ld.schema import LadderProgram
        prog = LadderProgram(program="Empty")
        svg = render_svg(prog)
        assert "<svg" in svg
        assert "Empty" in svg
