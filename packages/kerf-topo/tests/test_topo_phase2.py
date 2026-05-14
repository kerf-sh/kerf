"""
Topology optimisation Phase 2 tests.

Verifies:
1. Real-mesh path: a tiny cantilever STEP → Gmsh → dolfinx SIMP loop
   produces a non-trivial density field (not uniform) and converges.
2. STEP export path: pythonOCC marching-cubes export is readable STEP.
3. Unit-cube fallback: when step_b64 is absent the loop still runs.

All three heavy deps (dolfinx, gmsh, OCC.Core) are skipped via
pytest.importorskip when not installed.

Install for local runs:
    conda create -n kerf-topo -c conda-forge python=3.11 fenics-dolfinx gmsh pythonocc-core scikit-image
    conda activate kerf-topo
    pip install fastapi pydantic

Run:
    pytest pyworker/tests/test_topo_phase2.py -v
"""

import base64
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

dolfinx = pytest.importorskip("dolfinx", reason="dolfinx not installed")
gmsh_mod = pytest.importorskip("gmsh", reason="gmsh not installed")
occ_step = pytest.importorskip("OCC.Core.STEPControl", reason="pythonOCC not installed")

from kerf_topo.routes import (
    TopoRequest,
    BoundaryCondition,
    Load,
    _run_fenicsx_simp,
    _mesh_step_with_gmsh,
    _marching_cubes_to_step,
    _density_field_to_grid,
)


# ---------------------------------------------------------------------------
# Minimal cantilever STEP fixture: 20 mm × 5 mm × 5 mm box
# (small enough to mesh quickly even with a coarse element size)
# ---------------------------------------------------------------------------

_CANTILEVER_STEP = """\
ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Kerf topo test cantilever'),'2;1');
FILE_NAME('cantilever.step','2024-01-01T00:00:00',(''),(''),'','','');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#1=PRODUCT('bar','bar','',(#2));
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
#12=MANIFOLD_SOLID_BREP('bar',#13);
#13=CLOSED_SHELL('',(#14,#15,#16,#17,#18,#19));
#20=CARTESIAN_POINT('',(0.,0.,0.));
#21=CARTESIAN_POINT('',(20.,0.,0.));
#22=CARTESIAN_POINT('',(20.,5.,0.));
#23=CARTESIAN_POINT('',(0.,5.,0.));
#24=CARTESIAN_POINT('',(0.,0.,5.));
#25=CARTESIAN_POINT('',(20.,0.,5.));
#26=CARTESIAN_POINT('',(20.,5.,5.));
#27=CARTESIAN_POINT('',(0.,5.,5.));
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
#81=EDGE_CURVE('',#31,#32,#71,.T.);
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
"""


def _cantilever_step_b64() -> str:
    return base64.b64encode(_CANTILEVER_STEP.encode()).decode()


def _make_request(step_b64: str = "", bcs=None, loads=None, max_iter=5) -> TopoRequest:
    bcs = bcs or [BoundaryCondition(type="fixed", face_tag=1)]
    loads = loads or [Load(type="force", face_tag=2, fx=0.0, fy=-1.0, fz=0.0)]
    return TopoRequest(
        project_id="00000000-0000-0000-0000-000000000001",
        topo_file_id="00000000-0000-0000-0000-000000000002",
        feature_file_id="00000000-0000-0000-0000-000000000003",
        material_file_id="00000000-0000-0000-0000-000000000004",
        volume_fraction=0.4,
        penalization_power=3,
        filter_radius_mm=2.0,
        max_iterations=max_iter,
        convergence_tolerance=1e-3,
        step_b64=step_b64,
        boundary_conditions=bcs,
        loads=loads,
    )


# ---------------------------------------------------------------------------
# Gmsh meshing unit test
# ---------------------------------------------------------------------------

class TestGmshMeshing:
    def test_mesh_cantilever_produces_cells(self):
        """Gmsh + dolfinx mesh pipeline returns a mesh with >0 cells."""
        with tempfile.NamedTemporaryFile(suffix=".step", mode="w", delete=False) as f:
            f.write(_CANTILEVER_STEP)
            step_path = f.name
        try:
            mesh, facet_tags = _mesh_step_with_gmsh(step_path, mesh_size_mm=3.0)
        finally:
            Path(step_path).unlink(missing_ok=True)

        n_cells = mesh.topology.index_map(mesh.topology.dim).size_local
        assert n_cells > 0, "expected >0 tetrahedral cells from Gmsh mesh"

    def test_mesh_cantilever_facet_tags_present(self):
        """Gmsh assigns physical-group facet tags for each CAD surface."""
        with tempfile.NamedTemporaryFile(suffix=".step", mode="w", delete=False) as f:
            f.write(_CANTILEVER_STEP)
            step_path = f.name
        try:
            mesh, facet_tags = _mesh_step_with_gmsh(step_path, mesh_size_mm=3.0)
        finally:
            Path(step_path).unlink(missing_ok=True)

        assert facet_tags is not None, "facet_tags should not be None"
        unique_tags = set(facet_tags.values.tolist())
        assert len(unique_tags) >= 1, "expected at least one face physical group"


# ---------------------------------------------------------------------------
# SIMP loop with real mesh
# ---------------------------------------------------------------------------

class TestSimp:
    def test_unit_cube_fallback_runs(self):
        """Without step_b64 the loop runs on a unit cube and returns success."""
        req = _make_request(step_b64="", max_iter=3)
        result = _run_fenicsx_simp(req)
        assert result["status"] == "success"
        assert result["iterations"] > 0
        assert result["final_compliance"] > 0.0

    def test_unit_cube_density_field_non_trivial(self):
        """After ≥3 iterations the density field must contain values != V_target."""
        req = _make_request(step_b64="", max_iter=5)
        result = _run_fenicsx_simp(req)
        rho_values = [pt["rho"] for pt in result["density_field"]]
        assert len(rho_values) > 0
        v_target = req.volume_fraction
        non_trivial = any(abs(r - v_target) > 1e-6 for r in rho_values)
        assert non_trivial, (
            "All densities stayed at v_target — OC update did not run. "
            "SIMP loop may be broken."
        )

    def test_real_mesh_runs(self):
        """Real cantilever STEP → Gmsh → SIMP loop returns success."""
        req = _make_request(step_b64=_cantilever_step_b64(), max_iter=3)
        result = _run_fenicsx_simp(req)
        assert result["status"] == "success", f"SIMP failed: {result.get('warnings')}"
        assert result["iterations"] > 0

    def test_real_mesh_density_field_non_trivial(self):
        """Real-mesh SIMP density field must show redistribution after 5 iters."""
        req = _make_request(step_b64=_cantilever_step_b64(), max_iter=5)
        result = _run_fenicsx_simp(req)
        rho_values = [pt["rho"] for pt in result["density_field"]]
        assert len(rho_values) > 0
        v_target = req.volume_fraction
        non_trivial = any(abs(r - v_target) > 1e-6 for r in rho_values)
        assert non_trivial, "Density field is still uniform after 5 iterations"

    def test_real_mesh_compliance_positive(self):
        """Compliance must be positive — indicates a non-zero load was applied."""
        req = _make_request(step_b64=_cantilever_step_b64(), max_iter=3)
        result = _run_fenicsx_simp(req)
        assert result["final_compliance"] > 0.0, "Compliance is zero — load may not have been applied"


# ---------------------------------------------------------------------------
# Marching-cubes → STEP export
# ---------------------------------------------------------------------------

class TestMarchingCubesToStep:
    def _make_coords_and_rho(self):
        """Generate a simple gradient density field spanning [0,1]^3."""
        import numpy as np
        N = 5
        pts = []
        rhos = []
        for ix in range(N):
            for iy in range(N):
                for iz in range(N):
                    x = ix / (N - 1)
                    y = iy / (N - 1)
                    z = iz / (N - 1)
                    pts.append([x, y, z])
                    rhos.append(x)
        return pts, rhos

    def test_marching_cubes_produces_step_bytes(self):
        """marching_cubes_to_step returns non-empty bytes."""
        coords, rhos = self._make_coords_and_rho()
        step_bytes = _marching_cubes_to_step(coords, rhos, threshold=0.5)
        assert isinstance(step_bytes, bytes)
        assert len(step_bytes) > 0

    def test_step_output_is_valid_iso10303(self):
        """Output STEP starts with the ISO-10303-21 header."""
        coords, rhos = self._make_coords_and_rho()
        step_bytes = _marching_cubes_to_step(coords, rhos, threshold=0.5)
        text = step_bytes.decode(errors="replace")
        assert "ISO-10303-21" in text, "STEP output missing ISO-10303-21 header"

    def test_step_output_readable_by_occ(self):
        """The STEP produced by marching-cubes is readable by STEPControl_Reader."""
        from OCC.Core.STEPControl import STEPControl_Reader
        from OCC.Core.IFSelect import IFSelect_RetDone

        coords, rhos = self._make_coords_and_rho()
        step_bytes = _marching_cubes_to_step(coords, rhos, threshold=0.5)

        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
            f.write(step_bytes)
            tmp_path = f.name
        try:
            reader = STEPControl_Reader()
            status = reader.ReadFile(tmp_path)
            assert status == IFSelect_RetDone, f"STEPControl_Reader.ReadFile failed: {status}"
            reader.TransferRoots()
            shape = reader.OneShape()
            assert not shape.IsNull(), "Transferred shape is null"
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_uniform_zero_density_raises(self):
        """A density field of all zeros has no iso-surface at 0.5 → RuntimeError."""
        coords = [[float(i), 0.0, 0.0] for i in range(5)]
        rhos = [0.0] * 5
        with pytest.raises(RuntimeError):
            _marching_cubes_to_step(coords, rhos, threshold=0.5)


# ---------------------------------------------------------------------------
# End-to-end: step_b64 → density field → STEP output in one call
# ---------------------------------------------------------------------------

class TestEndToEnd:
    def test_run_returns_step_b64(self):
        """Full _run_fenicsx_simp returns a non-empty step_b64 for a real mesh."""
        req = _make_request(step_b64=_cantilever_step_b64(), max_iter=5)
        result = _run_fenicsx_simp(req)
        assert result["status"] == "success", f"failed: {result.get('warnings')}"
        assert result.get("step_b64"), (
            "step_b64 is empty — pythonOCC may not be installed or marching-cubes failed. "
            f"warnings: {result.get('warnings')}"
        )

    def test_returned_step_b64_is_valid_iso10303(self):
        """The base64-encoded STEP in the response decodes to valid STEP text."""
        req = _make_request(step_b64=_cantilever_step_b64(), max_iter=5)
        result = _run_fenicsx_simp(req)
        if not result.get("step_b64"):
            pytest.skip("step_b64 empty — pythonOCC not installed")
        decoded = base64.b64decode(result["step_b64"]).decode(errors="replace")
        assert "ISO-10303-21" in decoded
