"""Pytest config: add every plugin's src/ to sys.path so kerf_*.* imports
resolve without requiring `pip install -e` of each plugin.

T8 additions
------------
Exposes pytest fixtures used by test_5axis_e2e.py:
  step_fixture_path  — path to a 50×50×10 box STEP file with a slot pocket
                       cut through the top face.  Generated via pythonOCC
                       at test-collection time; cached in a module-scoped
                       tmp-directory so it is created once per session.
                       The fixture is skipped (pytest.skip) when pythonOCC
                       is not installed.

  stl_fixture_path   — ASCII STL of the same box, used by the 3+2 indexed
                       pipeline which operates on mesh data.

The fixture generation uses a 50×50×10 box with a 10×30×5 mm slot pocket
cut from the top face (BRepAlgoAPI_Cut).  Face ordering after the boolean
gives us a curved-ish interior face suitable for constant-tilt finishing.
"""
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_PLUGIN_ROOT = os.path.dirname(_HERE)
_PACKAGES_ROOT = os.path.dirname(_PLUGIN_ROOT)

if os.path.basename(_PACKAGES_ROOT) == "packages":
    for entry in os.listdir(_PACKAGES_ROOT):
        if not entry.startswith("kerf-"):
            continue
        src = os.path.join(_PACKAGES_ROOT, entry, "src")
        if os.path.isdir(src) and src not in sys.path:
            sys.path.insert(0, src)


# ---------------------------------------------------------------------------
# Optional pythonOCC probe
# ---------------------------------------------------------------------------

_has_occ = False
try:
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox  # noqa: F401
    _has_occ = True
except ImportError:
    pass


# ---------------------------------------------------------------------------
# T8 fixture: STEP solid (50×50×10 box with 10×30×5 slot)
# ---------------------------------------------------------------------------

def _build_slotted_box_step(path: str) -> None:
    """Write a 50×50×10 mm box with a 10×30×5 mm slot to *path* as STEP."""
    from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCC.Core.gp import gp_Vec, gp_Pnt
    from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCC.Core.gp import gp_Trsf
    from OCC.Core.STEPControl import STEPControl_Writer
    from OCC.Core.IFSelect import IFSelect_RetDone

    # Main box: 50 x 50 x 10 mm, origin at (0,0,0)
    box = BRepPrimAPI_MakeBox(50.0, 50.0, 10.0).Shape()

    # Slot tool: 10 x 30 x 5 mm, centred on top face at (20, 10, 5)
    slot_tool = BRepPrimAPI_MakeBox(10.0, 30.0, 5.0).Shape()
    trsf = gp_Trsf()
    trsf.SetTranslation(gp_Vec(20.0, 10.0, 5.0))
    from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
    slot_positioned = BRepBuilderAPI_Transform(slot_tool, trsf, True).Shape()

    # Boolean cut: box minus slot
    cut = BRepAlgoAPI_Cut(box, slot_positioned)
    cut.Build()
    if not cut.IsDone():
        # Fall back to plain box if boolean fails
        result_shape = box
    else:
        result_shape = cut.Shape()

    writer = STEPControl_Writer()
    writer.Transfer(result_shape, 0)
    status = writer.Write(path)
    if status != IFSelect_RetDone:
        raise RuntimeError(f"STEP write failed (status={status}) for {path!r}")


def _build_slotted_box_stl(shape, path: str) -> None:
    """Tessellate *shape* and write ASCII STL to *path*."""
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.TopLoc import TopLoc_Location

    BRepMesh_IncrementalMesh(shape, 0.5)  # 0.5 mm deflection

    triangles = []
    exp = TopExp_Explorer(shape, TopAbs_FACE)
    while exp.More():
        face = exp.Current()
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation(face, location)
        if triangulation is not None:
            trsf = location.IsIdentity() and None or location.IsIdentity()
            for i in range(1, triangulation.NbTriangles() + 1):
                tri = triangulation.Triangle(i)
                n1, n2, n3 = tri.Get()
                p1 = triangulation.Node(n1)
                p2 = triangulation.Node(n2)
                p3 = triangulation.Node(n3)
                triangles.append((
                    (p1.X(), p1.Y(), p1.Z()),
                    (p2.X(), p2.Y(), p2.Z()),
                    (p3.X(), p3.Y(), p3.Z()),
                ))
        exp.Next()

    with open(path, "w") as fh:
        fh.write("solid kerf_test_fixture\n")
        for v0, v1, v2 in triangles:
            # Simple facet normal (cross product)
            ax, ay, az = v1[0]-v0[0], v1[1]-v0[1], v1[2]-v0[2]
            bx, by, bz = v2[0]-v0[0], v2[1]-v0[1], v2[2]-v0[2]
            nx = ay*bz - az*by
            ny = az*bx - ax*bz
            nz = ax*by - ay*bx
            import math
            mag = math.sqrt(nx*nx + ny*ny + nz*nz)
            if mag > 1e-12:
                nx, ny, nz = nx/mag, ny/mag, nz/mag
            fh.write(f"  facet normal {nx:.6f} {ny:.6f} {nz:.6f}\n")
            fh.write("    outer loop\n")
            fh.write(f"      vertex {v0[0]:.6f} {v0[1]:.6f} {v0[2]:.6f}\n")
            fh.write(f"      vertex {v1[0]:.6f} {v1[1]:.6f} {v1[2]:.6f}\n")
            fh.write(f"      vertex {v2[0]:.6f} {v2[1]:.6f} {v2[2]:.6f}\n")
            fh.write("    endloop\n")
            fh.write("  endfacet\n")
        fh.write("endsolid kerf_test_fixture\n")


# Module-level cache so fixtures are built once per pytest session.
_FIXTURE_CACHE: dict = {}


@pytest.fixture(scope="session")
def step_fixture_path(tmp_path_factory):
    """Session-scoped STEP file path for the slotted box test solid.

    Skips the test if pythonOCC is not installed.
    """
    if not _has_occ:
        pytest.skip("pythonOCC not installed — OCC-dependent fixture unavailable")

    if "step" not in _FIXTURE_CACHE:
        tmpdir = tmp_path_factory.mktemp("cam_fixtures")
        step_path = str(tmpdir / "test_solid.step")
        _build_slotted_box_step(step_path)
        _FIXTURE_CACHE["step"] = step_path

    return _FIXTURE_CACHE["step"]


@pytest.fixture(scope="session")
def stl_fixture_path(tmp_path_factory):
    """Session-scoped ASCII STL file path for the slotted box test solid.

    Skips the test if pythonOCC is not installed.
    """
    if not _has_occ:
        pytest.skip("pythonOCC not installed — OCC-dependent fixture unavailable")

    if "stl" not in _FIXTURE_CACHE:
        from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeBox
        from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Cut
        from OCC.Core.gp import gp_Vec
        from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCC.Core.gp import gp_Trsf

        box = BRepPrimAPI_MakeBox(50.0, 50.0, 10.0).Shape()
        slot_tool = BRepPrimAPI_MakeBox(10.0, 30.0, 5.0).Shape()
        trsf = gp_Trsf()
        trsf.SetTranslation(gp_Vec(20.0, 10.0, 5.0))
        slot_positioned = BRepBuilderAPI_Transform(slot_tool, trsf, True).Shape()

        cut = BRepAlgoAPI_Cut(box, slot_positioned)
        cut.Build()
        shape = cut.Shape() if cut.IsDone() else box

        tmpdir = tmp_path_factory.mktemp("cam_fixtures_stl")
        stl_path = str(tmpdir / "test_solid.stl")
        _build_slotted_box_stl(shape, stl_path)
        _FIXTURE_CACHE["stl"] = stl_path

    return _FIXTURE_CACHE["stl"]
