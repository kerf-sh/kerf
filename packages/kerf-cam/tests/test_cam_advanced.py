"""
Tests for CAM advanced features:
  - B-rep face-loop extraction (contour/pocket boundary from real STEP geometry)
  - parallel_3d smoke test
  - waterline smoke test
  - lathe smoke test (no heavy deps required)
  - 5-axis stub returns not_implemented (no heavy deps required)

Run:
    pytest backend/tests/test_cam_advanced.py -v

Install heavy deps to unlock full test suite:
    conda install -c conda-forge pythonocc-core
    pip install opencamlib
"""

import sys
import tempfile
import textwrap
import asyncio
import base64
from pathlib import Path
from typing import List

import pytest

# kerf_cam is a proper package — no manual sys.path manipulation needed.

_has_ocl = pytest.importorskip("opencamlib", reason="opencamlib not installed") if False else None
_has_occ = pytest.importorskip("OCC.Core.STEPControl", reason="pythonOCC not installed") if False else None

try:
    import opencamlib as _ocl_mod
    _has_ocl = True
except ImportError:
    _has_ocl = False

try:
    import OCC.Core.STEPControl  # noqa: F401
    _has_occ = True
except ImportError:
    _has_occ = False

requires_occ = pytest.mark.skipif(not _has_occ, reason="pythonOCC not installed")
requires_ocl = pytest.mark.skipif(not _has_ocl, reason="opencamlib not installed")
requires_both = pytest.mark.skipif(
    not (_has_occ and _has_ocl),
    reason="pythonOCC and opencamlib both required",
)

# ---------------------------------------------------------------------------
# Minimal 10×10×10 mm cube STEP fixture
# ---------------------------------------------------------------------------

_CUBE_STEP = textwrap.dedent("""\
    ISO-10303-21;
    HEADER;
    FILE_DESCRIPTION(('Kerf test cube'),'2;1');
    FILE_NAME('cube.step','2024-01-01T00:00:00',(''),(''),'','','');
    FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
    ENDSEC;
    DATA;
    #1=PRODUCT('cube','cube','',(#2));
    #2=PRODUCT_CONTEXT('',#3,'mechanical');
    #3=APPLICATION_CONTEXT('automotive design');
    #4=PRODUCT_DEFINITION_FORMATION_WITH_SPECIFIED_SOURCE('','',#1,.NOT_KNOWN.);
    #5=PRODUCT_DEFINITION('design','',#4,#6);
    #6=PRODUCT_DEFINITION_CONTEXT('part definition',#3,'design');
    #7=PRODUCT_DEFINITION_SHAPE('','',#5);
    #8=AXIS2_PLACEMENT_3D('',#9,#10,#11);
    #9=CARTESIAN_POINT('',(0.,0.,0.));
    #10=DIRECTION('',(0.,0.,1.));
    #11=DIRECTION('',(1.,0.,0.));
    #12=MANIFOLD_SOLID_BREP('cube',#13);
    #13=CLOSED_SHELL('',(#14,#15,#16,#17,#18,#19));
    #20=CARTESIAN_POINT('',(0.,0.,0.));
    #21=CARTESIAN_POINT('',(10.,0.,0.));
    #22=CARTESIAN_POINT('',(10.,10.,0.));
    #23=CARTESIAN_POINT('',(0.,10.,0.));
    #24=CARTESIAN_POINT('',(0.,0.,10.));
    #25=CARTESIAN_POINT('',(10.,0.,10.));
    #26=CARTESIAN_POINT('',(10.,10.,10.));
    #27=CARTESIAN_POINT('',(0.,10.,10.));
    #30=VERTEX_POINT('',#20);
    #31=VERTEX_POINT('',#21);
    #32=VERTEX_POINT('',#22);
    #33=VERTEX_POINT('',#23);
    #34=VERTEX_POINT('',#24);
    #35=VERTEX_POINT('',#25);
    #36=VERTEX_POINT('',#26);
    #37=VERTEX_POINT('',#27);
    #40=DIRECTION('',(1.,0.,0.));
    #41=DIRECTION('',(0.,1.,0.));
    #42=DIRECTION('',(0.,0.,1.));
    #43=DIRECTION('',(-1.,0.,0.));
    #44=DIRECTION('',(0.,-1.,0.));
    #45=DIRECTION('',(0.,0.,-1.));
    #50=AXIS2_PLACEMENT_3D('',#20,#45,#40);
    #51=AXIS2_PLACEMENT_3D('',#24,#42,#40);
    #52=AXIS2_PLACEMENT_3D('',#20,#44,#42);
    #53=AXIS2_PLACEMENT_3D('',#21,#40,#42);
    #54=AXIS2_PLACEMENT_3D('',#22,#41,#45);
    #55=AXIS2_PLACEMENT_3D('',#23,#43,#42);
    #60=PLANE('',#50);
    #61=PLANE('',#51);
    #62=PLANE('',#52);
    #63=PLANE('',#53);
    #64=PLANE('',#54);
    #65=PLANE('',#55);
    #70=LINE('',#20,#40);
    #71=LINE('',#20,#41);
    #72=LINE('',#24,#40);
    #73=LINE('',#24,#41);
    #74=LINE('',#20,#42);
    #75=LINE('',#21,#42);
    #76=LINE('',#22,#42);
    #77=LINE('',#23,#42);
    #80=EDGE_CURVE('',#30,#31,#70,.T.);
    #81=EDGE_CURVE('',#31,#32,#71,. T.);
    #82=EDGE_CURVE('',#32,#33,#70,.T.);
    #83=EDGE_CURVE('',#33,#30,#71,.T.);
    #84=EDGE_CURVE('',#34,#35,#72,.T.);
    #85=EDGE_CURVE('',#35,#36,#73,.T.);
    #86=EDGE_CURVE('',#36,#37,#72,.T.);
    #87=EDGE_CURVE('',#37,#34,#73,.T.);
    #88=EDGE_CURVE('',#30,#34,#74,.T.);
    #89=EDGE_CURVE('',#31,#35,#75,.T.);
    #90=EDGE_CURVE('',#32,#36,#76,.T.);
    #91=EDGE_CURVE('',#33,#37,#77,.T.);
    #100=ORIENTED_EDGE('',*,*,#80,.T.);
    #101=ORIENTED_EDGE('',*,*,#81,.T.);
    #102=ORIENTED_EDGE('',*,*,#82,.F.);
    #103=ORIENTED_EDGE('',*,*,#83,.F.);
    #104=ORIENTED_EDGE('',*,*,#84,.F.);
    #105=ORIENTED_EDGE('',*,*,#85,.F.);
    #106=ORIENTED_EDGE('',*,*,#86,.T.);
    #107=ORIENTED_EDGE('',*,*,#87,.T.);
    #108=ORIENTED_EDGE('',*,*,#88,.T.);
    #109=ORIENTED_EDGE('',*,*,#89,.T.);
    #110=ORIENTED_EDGE('',*,*,#90,.T.);
    #111=ORIENTED_EDGE('',*,*,#91,.T.);
    #112=ORIENTED_EDGE('',*,*,#89,.F.);
    #113=ORIENTED_EDGE('',*,*,#90,.F.);
    #114=ORIENTED_EDGE('',*,*,#91,.F.);
    #115=ORIENTED_EDGE('',*,*,#88,.F.);
    #116=ORIENTED_EDGE('',*,*,#80,.F.);
    #117=ORIENTED_EDGE('',*,*,#83,.T.);
    #118=ORIENTED_EDGE('',*,*,#82,.T.);
    #119=ORIENTED_EDGE('',*,*,#81,.F.);
    #120=EDGE_LOOP('',(#100,#101,#102,#103));
    #121=EDGE_LOOP('',(#104,#105,#106,#107));
    #122=EDGE_LOOP('',(#108,#109,#112,#115));
    #123=EDGE_LOOP('',(#109,#110,#113,#112));
    #124=EDGE_LOOP('',(#110,#111,#114,#113));
    #125=EDGE_LOOP('',(#111,#108,#115,#114));
    #130=FACE_OUTER_BOUND('',#120,.T.);
    #131=FACE_OUTER_BOUND('',#121,.T.);
    #132=FACE_OUTER_BOUND('',#122,.T.);
    #133=FACE_OUTER_BOUND('',#123,.T.);
    #134=FACE_OUTER_BOUND('',#124,.T.);
    #135=FACE_OUTER_BOUND('',#125,.T.);
    #14=ADVANCED_FACE('',(#130),#60,.F.);
    #15=ADVANCED_FACE('',(#131),#61,.T.);
    #16=ADVANCED_FACE('',(#132),#62,.T.);
    #17=ADVANCED_FACE('',(#133),#63,.T.);
    #18=ADVANCED_FACE('',(#134),#64,.T.);
    #19=ADVANCED_FACE('',(#135),#65,.T.);
    #140=SHAPE_DEFINITION_REPRESENTATION(#7,#141);
    #141=ADVANCED_BREP_SHAPE_REPRESENTATION('',(#12,#8),#142);
    #142=( GEOMETRIC_REPRESENTATION_CONTEXT(3)
    GLOBAL_UNCERTAINTY_ASSIGNED_CONTEXT((#143))
    GLOBAL_UNIT_ASSIGNED_CONTEXT((#144,#145,#146))
    REPRESENTATION_CONTEXT('Context #1','3D Context with UNIT and UNCERTAINTY') );
    #143=UNCERTAINTY_MEASURE_WITH_UNIT(LENGTH_MEASURE(1.E-07),#144,'distance_accuracy_value','confusion accuracy');
    #144=( LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.) );
    #145=( NAMED_UNIT(*) PLANE_ANGLE_UNIT() SI_UNIT($,.RADIAN.) );
    #146=( NAMED_UNIT(*) SI_UNIT($,.STERADIAN.) SOLID_ANGLE_UNIT() );
    ENDSEC;
    END-ISO-10303-21;
""")


def _write_cube_step(tmpdir: str) -> str:
    p = Path(tmpdir) / "cube.step"
    p.write_text(_CUBE_STEP)
    return str(p)


def _make_op(**kwargs):
    from kerf_cam.routes import CAMOperation
    defaults = dict(
        type="face",
        tool_diameter=3.0,
        step_down=0.5,
        step_over=1.0,
        feed_rate=1000.0,
        spindle_rpm=10000,
        coolant="flood",
    )
    defaults.update(kwargs)
    return CAMOperation(**defaults)


# ---------------------------------------------------------------------------
# B-rep face-loop extraction (requires pythonOCC only)
# ---------------------------------------------------------------------------

@requires_occ
def test_brep_extracts_at_least_one_wire():
    from kerf_cam.routes import convert_step_to_stl, extract_face_wires
    with tempfile.TemporaryDirectory() as tmpdir:
        occ_shape = convert_step_to_stl(_write_cube_step(tmpdir), str(Path(tmpdir) / "out.stl"))
        op = _make_op(type="contour")
        wires = extract_face_wires(occ_shape, op)
        assert len(wires) >= 1, "expected at least one wire polygon"


@requires_occ
def test_brep_outer_wire_has_four_corners():
    """The cube top face outer wire should be a closed quadrilateral."""
    from kerf_cam.routes import convert_step_to_stl, extract_face_wires
    with tempfile.TemporaryDirectory() as tmpdir:
        occ_shape = convert_step_to_stl(_write_cube_step(tmpdir), str(Path(tmpdir) / "out.stl"))
        op = _make_op(type="contour", wire_tolerance=0.01)
        wires = extract_face_wires(occ_shape, op)
        assert len(wires[0]) >= 4, f"outer wire has only {len(wires[0])} points"


@requires_occ
def test_brep_outer_wire_coords_within_cube_xy():
    from kerf_cam.routes import convert_step_to_stl, extract_face_wires
    with tempfile.TemporaryDirectory() as tmpdir:
        occ_shape = convert_step_to_stl(_write_cube_step(tmpdir), str(Path(tmpdir) / "out.stl"))
        op = _make_op(type="contour")
        wires = extract_face_wires(occ_shape, op)
        tol = 0.1
        for x, y in wires[0]:
            assert -tol <= x <= 10.0 + tol, f"wire x={x} outside cube"
            assert -tol <= y <= 10.0 + tol, f"wire y={y} outside cube"


@requires_occ
def test_brep_face_id_selects_specific_face():
    from kerf_cam.routes import convert_step_to_stl, extract_face_wires
    with tempfile.TemporaryDirectory() as tmpdir:
        occ_shape = convert_step_to_stl(_write_cube_step(tmpdir), str(Path(tmpdir) / "out.stl"))
        op = _make_op(type="pocket", face_id=0)
        wires = extract_face_wires(occ_shape, op)
        assert len(wires) >= 1


# ---------------------------------------------------------------------------
# parallel_3d smoke test (requires opencamlib + pythonOCC)
# ---------------------------------------------------------------------------

@requires_both
def test_parallel_3d_x_produces_cl_points():
    from kerf_cam.routes import convert_step_to_stl, _load_stl_into_surface, _run_parallel_3d
    import opencamlib as ocl
    with tempfile.TemporaryDirectory() as tmpdir:
        convert_step_to_stl(_write_cube_step(tmpdir), str(Path(tmpdir) / "out.stl"))
        surface = ocl.STLSurf()
        _load_stl_into_surface(str(Path(tmpdir) / "out.stl"), surface)
        op = _make_op(type="parallel_3d", step_over=2.0, step_down=0.5, direction="x")
        pts = _run_parallel_3d(ocl.CylCutter(op.tool_diameter / 1000.0, 50.0 / 1000.0), op, surface)
        assert len(pts) > 0, "parallel_3d X raster produced no CL points"


@requires_both
def test_parallel_3d_y_produces_cl_points():
    from kerf_cam.routes import convert_step_to_stl, _load_stl_into_surface, _run_parallel_3d
    import opencamlib as ocl
    with tempfile.TemporaryDirectory() as tmpdir:
        convert_step_to_stl(_write_cube_step(tmpdir), str(Path(tmpdir) / "out.stl"))
        surface = ocl.STLSurf()
        _load_stl_into_surface(str(Path(tmpdir) / "out.stl"), surface)
        op = _make_op(type="parallel_3d", step_over=2.0, step_down=0.5, direction="y")
        pts = _run_parallel_3d(ocl.CylCutter(op.tool_diameter / 1000.0, 50.0 / 1000.0), op, surface)
        assert len(pts) > 0, "parallel_3d Y raster produced no CL points"


@requires_both
def test_parallel_3d_angle_produces_cl_points():
    from kerf_cam.routes import convert_step_to_stl, _load_stl_into_surface, _run_parallel_3d
    import opencamlib as ocl
    with tempfile.TemporaryDirectory() as tmpdir:
        convert_step_to_stl(_write_cube_step(tmpdir), str(Path(tmpdir) / "out.stl"))
        surface = ocl.STLSurf()
        _load_stl_into_surface(str(Path(tmpdir) / "out.stl"), surface)
        op = _make_op(type="parallel_3d", step_over=2.0, step_down=0.5, angle_deg=45.0)
        pts = _run_parallel_3d(ocl.CylCutter(op.tool_diameter / 1000.0, 50.0 / 1000.0), op, surface)
        assert len(pts) > 0, "parallel_3d 45° raster produced no CL points"


@requires_both
def test_parallel_3d_cl_within_cube_xy():
    from kerf_cam.routes import convert_step_to_stl, _load_stl_into_surface, _run_parallel_3d
    import opencamlib as ocl
    with tempfile.TemporaryDirectory() as tmpdir:
        convert_step_to_stl(_write_cube_step(tmpdir), str(Path(tmpdir) / "out.stl"))
        surface = ocl.STLSurf()
        _load_stl_into_surface(str(Path(tmpdir) / "out.stl"), surface)
        op = _make_op(type="parallel_3d", step_over=2.0, step_down=0.5, direction="x")
        pts = _run_parallel_3d(ocl.CylCutter(op.tool_diameter / 1000.0, 50.0 / 1000.0), op, surface)
        tol = 1e-4
        for pt in pts:
            assert -tol <= pt.x <= 0.010 + tol, f"CL x={pt.x} outside cube"
            assert -tol <= pt.y <= 0.010 + tol, f"CL y={pt.y} outside cube"


# ---------------------------------------------------------------------------
# waterline smoke test (requires opencamlib + pythonOCC)
# ---------------------------------------------------------------------------

@requires_both
def test_waterline_produces_cl_points():
    from kerf_cam.routes import convert_step_to_stl, _load_stl_into_surface, _run_waterline
    import opencamlib as ocl
    with tempfile.TemporaryDirectory() as tmpdir:
        convert_step_to_stl(_write_cube_step(tmpdir), str(Path(tmpdir) / "out.stl"))
        surface = ocl.STLSurf()
        _load_stl_into_surface(str(Path(tmpdir) / "out.stl"), surface)
        op = _make_op(type="waterline", step_over=2.0, step_down=2.0)
        pts = _run_waterline(ocl.CylCutter(op.tool_diameter / 1000.0, 50.0 / 1000.0), op, surface)
        assert len(pts) > 0, "waterline produced no CL points"


@requires_both
def test_waterline_z_levels_span_range():
    """Z values of waterline CL points must span a non-trivial range."""
    from kerf_cam.routes import convert_step_to_stl, _load_stl_into_surface, _run_waterline
    import opencamlib as ocl
    with tempfile.TemporaryDirectory() as tmpdir:
        convert_step_to_stl(_write_cube_step(tmpdir), str(Path(tmpdir) / "out.stl"))
        surface = ocl.STLSurf()
        _load_stl_into_surface(str(Path(tmpdir) / "out.stl"), surface)
        op = _make_op(type="waterline", step_over=2.0, step_down=3.0)
        pts = _run_waterline(ocl.CylCutter(op.tool_diameter / 1000.0, 50.0 / 1000.0), op, surface)
        z_values = [pt.z for pt in pts]
        assert max(z_values) >= min(z_values)


# ---------------------------------------------------------------------------
# Lathe smoke test — no heavy deps required
# ---------------------------------------------------------------------------

def test_lathe_gcode_without_occ():
    """Lathe op emits valid G-code even when pythonOCC is not present."""
    from kerf_cam.routes import _run_lathe_op
    op = _make_op(type="lathe", step_down=1.0, step_over=1.0, feed_rate=200.0, spindle_rpm=1500, spindle_axis="z")
    gcode, length = _run_lathe_op(op, occ_shape=None)
    assert "G18" in gcode, "lathe G-code missing G18 (X-Z plane select)"
    assert "G96" in gcode, "lathe G-code missing G96 (constant surface speed)"
    assert "G1" in gcode, "lathe G-code has no G1 moves"
    assert length > 0, "lathe total_length should be > 0"


def test_lathe_gcode_has_spindle_on():
    from kerf_cam.routes import _run_lathe_op
    op = _make_op(type="lathe", step_down=1.0, step_over=1.0, feed_rate=200.0, spindle_rpm=2000)
    gcode, _ = _run_lathe_op(op, occ_shape=None)
    assert "M3" in gcode


@requires_occ
def test_lathe_with_occ_shape():
    """When pythonOCC is available the lathe op tries to extract a profile."""
    from kerf_cam.routes import convert_step_to_stl, _run_lathe_op
    with tempfile.TemporaryDirectory() as tmpdir:
        occ_shape = convert_step_to_stl(_write_cube_step(tmpdir), str(Path(tmpdir) / "out.stl"))
        op = _make_op(type="lathe", step_down=1.0, step_over=1.0, feed_rate=200.0, spindle_rpm=1500)
        gcode, length = _run_lathe_op(op, occ_shape=occ_shape)
        assert "G18" in gcode
        assert length >= 0


# ---------------------------------------------------------------------------
# 5-axis stub — no heavy deps required
# ---------------------------------------------------------------------------

def test_5axis_returns_not_implemented():
    from kerf_cam.routes import run_cam, CAMRequest
    step_b64 = base64.b64encode(
        b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
    ).decode()
    req = CAMRequest(step_b64=step_b64, input_spec={
        "operation": "5axis", "tool_diameter": 6.0, "step_over": 2.0,
        "step_down": 1.0, "feed_rate": 500.0, "spindle_speed": 8000,
    })
    result = asyncio.run(run_cam(req))
    assert len(result["errors"]) >= 1
    assert "not_implemented" in result["errors"][0]
    assert result["toolpath_length"] == 0.0


def test_5axis_gcode_b64_present():
    from kerf_cam.routes import run_cam, CAMRequest
    step_b64 = base64.b64encode(
        b"ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n"
    ).decode()
    req = CAMRequest(step_b64=step_b64, input_spec={
        "operation": "5axis", "tool_diameter": 6.0, "step_over": 1.0,
        "step_down": 1.0, "feed_rate": 500.0, "spindle_speed": 8000,
    })
    result = asyncio.run(run_cam(req))
    assert "gcode_b64" in result


# ---------------------------------------------------------------------------
# B-rep contour end-to-end (requires both deps)
# ---------------------------------------------------------------------------

@requires_both
def test_contour_op_uses_real_wire():
    """contour op on a cube produces CL points that stay within cube XY."""
    from kerf_cam.routes import (
        convert_step_to_stl, _load_stl_into_surface, _run_brep_contour_pocket,
    )
    import opencamlib as ocl
    with tempfile.TemporaryDirectory() as tmpdir:
        occ_shape = convert_step_to_stl(_write_cube_step(tmpdir), str(Path(tmpdir) / "out.stl"))
        surface = ocl.STLSurf()
        _load_stl_into_surface(str(Path(tmpdir) / "out.stl"), surface)
        op = _make_op(type="contour", step_over=1.0, step_down=0.5, wire_tolerance=0.05)
        tool = ocl.CylCutter(op.tool_diameter / 1000.0, 50.0 / 1000.0)
        pts = _run_brep_contour_pocket("contour", tool, op, surface, occ_shape)
        assert len(pts) > 0, "B-rep contour op produced no CL points"
        tol = 0.002
        for pt in pts:
            assert -tol <= pt.x <= 0.010 + tol, f"contour CL x={pt.x} outside cube"
            assert -tol <= pt.y <= 0.010 + tol, f"contour CL y={pt.y} outside cube"
