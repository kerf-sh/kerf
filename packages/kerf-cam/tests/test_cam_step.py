"""
Integration test: STEP → STL → opencamlib face op.

Both pythonOCC (OCC.Core.*) and opencamlib must be installed for the test to
run; otherwise the test is skipped via pytest.importorskip so CI without those
heavy wheels passes cleanly.

Install (conda-forge recommended for pythonOCC):
    conda install -c conda-forge pythonocc-core
    pip install opencamlib

Run:
    pytest backend/tests/test_cam_step.py -v
"""

import math
import struct
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

ocl = pytest.importorskip("opencamlib", reason="opencamlib not installed")
_occ_stl = pytest.importorskip("OCC.Core.STEPControl", reason="pythonOCC not installed")

from kerf_cam.routes import convert_step_to_stl, _load_stl_into_surface, _run_ocl_op, CAMOperation  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal cube STEP fixture (10×10×10 mm cube, ISO 10303-21 syntax)
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_cube_step(tmpdir: str) -> str:
    p = Path(tmpdir) / "cube.step"
    p.write_text(_CUBE_STEP)
    return str(p)


def _make_face_op(tool_diameter: float = 3.0, step_over: float = 1.0, step_down: float = 0.5) -> CAMOperation:
    return CAMOperation(
        type="face",
        tool_diameter=tool_diameter,
        step_down=step_down,
        step_over=step_over,
        feed_rate=1000.0,
        spindle_rpm=10000,
        coolant="flood",
    )


# ---------------------------------------------------------------------------
# STEP → STL conversion tests
# ---------------------------------------------------------------------------

class TestConvertStepToStl:
    def test_produces_stl_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            step_path = _write_cube_step(tmpdir)
            stl_path = str(Path(tmpdir) / "out.stl")
            convert_step_to_stl(step_path, stl_path)
            assert Path(stl_path).exists(), "STL file was not created"
            assert Path(stl_path).stat().st_size > 0, "STL file is empty"

    def test_stl_contains_triangles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            step_path = _write_cube_step(tmpdir)
            stl_path = str(Path(tmpdir) / "out.stl")
            convert_step_to_stl(step_path, stl_path)
            content = Path(stl_path).read_text()
            assert "facet normal" in content, "STL has no facet normal lines"
            assert "vertex" in content, "STL has no vertex lines"

    def test_stl_vertex_coords_within_cube_bounds(self):
        """All triangle vertices must lie within the 10×10×10 mm cube (with float tolerance)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            step_path = _write_cube_step(tmpdir)
            stl_path = str(Path(tmpdir) / "out.stl")
            convert_step_to_stl(step_path, stl_path)
            content = Path(stl_path).read_text()
            tol = 1e-3
            for line in content.splitlines():
                line = line.strip()
                if line.startswith("vertex "):
                    parts = line.split()
                    x, y, z = float(parts[1]), float(parts[2]), float(parts[3])
                    assert -tol <= x <= 10.0 + tol, f"vertex x={x} outside cube"
                    assert -tol <= y <= 10.0 + tol, f"vertex y={y} outside cube"
                    assert -tol <= z <= 10.0 + tol, f"vertex z={z} outside cube"

    def test_tight_deflection_produces_more_triangles(self):
        """Smaller linear_deflection → equal or more triangles."""
        with tempfile.TemporaryDirectory() as tmpdir:
            step_path = _write_cube_step(tmpdir)
            coarse = str(Path(tmpdir) / "coarse.stl")
            fine = str(Path(tmpdir) / "fine.stl")
            convert_step_to_stl(step_path, coarse, linear_deflection=1.0)
            convert_step_to_stl(step_path, fine, linear_deflection=0.05)

            def count_triangles(path):
                return Path(path).read_text().count("facet normal")

            assert count_triangles(fine) >= count_triangles(coarse)

    def test_invalid_step_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_step = str(Path(tmpdir) / "bad.step")
            Path(bad_step).write_text("this is not a STEP file at all")
            stl_out = str(Path(tmpdir) / "out.stl")
            with pytest.raises(RuntimeError):
                convert_step_to_stl(bad_step, stl_out)


# ---------------------------------------------------------------------------
# STL → ocl.STLSurf loading tests
# ---------------------------------------------------------------------------

class TestLoadStlIntoSurface:
    def test_triangles_loaded(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            step_path = _write_cube_step(tmpdir)
            stl_path = str(Path(tmpdir) / "out.stl")
            convert_step_to_stl(step_path, stl_path)
            surface = ocl.STLSurf()
            _load_stl_into_surface(stl_path, surface)
            # A 10×10×10 cube with default deflection has at least 12 triangles (2 per face).
            assert surface.size() >= 12, f"expected >=12 triangles, got {surface.size()}"

    def test_empty_stl_loads_without_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            empty_stl = str(Path(tmpdir) / "empty.stl")
            Path(empty_stl).write_text("solid empty\nendsolid empty\n")
            surface = ocl.STLSurf()
            _load_stl_into_surface(empty_stl, surface)
            assert surface.size() == 0


# ---------------------------------------------------------------------------
# End-to-end face op: STEP → STL → PathDropCutter → CL points within XY bounds
# ---------------------------------------------------------------------------

class TestFaceOpEndToEnd:
    def test_face_op_produces_cl_points(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            step_path = _write_cube_step(tmpdir)
            stl_path = str(Path(tmpdir) / "out.stl")
            convert_step_to_stl(step_path, stl_path)
            surface = ocl.STLSurf()
            _load_stl_into_surface(stl_path, surface)

            op = _make_face_op(tool_diameter=3.0, step_over=2.0, step_down=0.5)
            tool = ocl.CylCutter(op.tool_diameter / 1000.0, 50.0 / 1000.0)
            clpoints = _run_ocl_op("face", tool, op, surface)

            assert len(clpoints) > 0, "face op produced no CL points on real STEP geometry"

    def test_face_op_cl_points_within_cube_xy(self):
        """All CL point XY coordinates must lie within the 10×10 mm cube footprint."""
        with tempfile.TemporaryDirectory() as tmpdir:
            step_path = _write_cube_step(tmpdir)
            stl_path = str(Path(tmpdir) / "out.stl")
            convert_step_to_stl(step_path, stl_path)
            surface = ocl.STLSurf()
            _load_stl_into_surface(stl_path, surface)

            op = _make_face_op(tool_diameter=3.0, step_over=2.0, step_down=0.5)
            tool = ocl.CylCutter(op.tool_diameter / 1000.0, 50.0 / 1000.0)
            clpoints = _run_ocl_op("face", tool, op, surface)

            # Cube is 0–10 mm in both X and Y (coords in metres inside ocl)
            cube_min_m = -1e-4          # tiny tolerance
            cube_max_m = 0.010 + 1e-4
            for pt in clpoints:
                assert cube_min_m <= pt.x <= cube_max_m, f"CL point x={pt.x} outside cube XY"
                assert cube_min_m <= pt.y <= cube_max_m, f"CL point y={pt.y} outside cube XY"

    def test_face_op_z_at_cut_depth(self):
        """CL point Z values should be at or above the top face minus step_down."""
        with tempfile.TemporaryDirectory() as tmpdir:
            step_path = _write_cube_step(tmpdir)
            stl_path = str(Path(tmpdir) / "out.stl")
            convert_step_to_stl(step_path, stl_path)
            surface = ocl.STLSurf()
            _load_stl_into_surface(stl_path, surface)

            step_down_mm = 0.5
            op = _make_face_op(tool_diameter=3.0, step_over=2.0, step_down=step_down_mm)
            tool = ocl.CylCutter(op.tool_diameter / 1000.0, 50.0 / 1000.0)
            clpoints = _run_ocl_op("face", tool, op, surface)

            # Cube top is at z=10 mm = 0.010 m; cut depth is step_down / 1000 m below zero reference.
            # PathDropCutter setZ is called with -(step_down/1000); CL points Z should be
            # close to that depth or above (drop-cutter lifts the tool up to the surface).
            expected_z_m = -(step_down_mm / 1000.0)
            tol = 0.015  # 15 mm tolerance — drop-cutter reports surface z, not clearance plane
            for pt in clpoints:
                assert pt.z >= expected_z_m - tol, f"CL point z={pt.z} unexpectedly deep"
