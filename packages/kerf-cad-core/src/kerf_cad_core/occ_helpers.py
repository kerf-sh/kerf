"""
Shared pythonOCC helpers for Kerf CAD compute plugins.

All OCC imports are gated behind ``_OCC_AVAILABLE``.  Callers should check
that flag before calling any function here, or simply let the functions raise
``RuntimeError("pythonOCC not installed ...")`` at call time.

Public API (imported via ``kerf_cad_core`` package):

    _OCC_AVAILABLE          bool flag
    load_step(path) -> shape
    mesh_shape(shape, linear_deflection) -> None
    write_stl(shape, path, ascii_mode) -> None
    convert_step_to_stl(step_path, stl_path, linear_deflection) -> shape
"""

from __future__ import annotations

from typing import Optional

# ── OCC availability gate ──────────────────────────────────────────────────────

_OCC_AVAILABLE = False

try:
    from OCC.Core.STEPControl import STEPControl_Reader as _STEPControl_Reader
    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh as _BRepMesh_IncrementalMesh
    from OCC.Core.StlAPI import StlAPI_Writer as _StlAPI_Writer
    from OCC.Core.IFSelect import IFSelect_RetDone as _IFSelect_RetDone
    _OCC_AVAILABLE = True
except ImportError:
    pass


# ── STEP I/O ───────────────────────────────────────────────────────────────────

def load_step(step_path: str):
    """Read a STEP file and return the OCC compound shape.

    Raises RuntimeError if pythonOCC is not installed or the file cannot be
    read.  The shape can be reused across multiple operations without re-reading
    the file.
    """
    if not _OCC_AVAILABLE:
        raise RuntimeError(
            "pythonOCC not installed — cannot load STEP. "
            "Install: conda install -c conda-forge pythonocc-core"
        )

    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.IFSelect import IFSelect_RetDone

    reader = STEPControl_Reader()
    status = reader.ReadFile(step_path)
    if status != IFSelect_RetDone:
        raise RuntimeError(
            f"STEPControl_Reader failed on {step_path!r} (status={status})"
        )
    reader.TransferRoots()
    return reader.OneShape()


# ── BRep meshing ───────────────────────────────────────────────────────────────

def mesh_shape(shape, linear_deflection: float = 0.1) -> None:
    """Tessellate an OCC shape in-place using BRepMesh_IncrementalMesh.

    ``linear_deflection`` controls mesh quality: smaller = finer, slower.
    Raises RuntimeError if pythonOCC is not installed or meshing fails.
    """
    if not _OCC_AVAILABLE:
        raise RuntimeError(
            "pythonOCC not installed — cannot mesh shape. "
            "Install: conda install -c conda-forge pythonocc-core"
        )

    from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh

    mesh = BRepMesh_IncrementalMesh(shape, linear_deflection)
    mesh.Perform()
    if not mesh.IsDone():
        raise RuntimeError("BRepMesh_IncrementalMesh did not complete")


# ── STL I/O ────────────────────────────────────────────────────────────────────

def write_stl(shape, stl_path: str, ascii_mode: bool = True) -> None:
    """Write an OCC shape to an STL file.

    The shape must already be meshed (call ``mesh_shape`` first).
    Raises RuntimeError if pythonOCC is not installed or writing fails.
    """
    if not _OCC_AVAILABLE:
        raise RuntimeError(
            "pythonOCC not installed — cannot write STL. "
            "Install: conda install -c conda-forge pythonocc-core"
        )

    from OCC.Core.StlAPI import StlAPI_Writer

    writer = StlAPI_Writer()
    writer.ASCIIMode = ascii_mode
    result = writer.Write(shape, stl_path)
    if not result:
        raise RuntimeError(f"StlAPI_Writer failed writing {stl_path!r}")


# ── Combined convenience helper ────────────────────────────────────────────────

def convert_step_to_stl(
    step_path: str,
    stl_path: str,
    linear_deflection: float = 0.1,
):
    """Read a STEP file, mesh it, write an ASCII STL, and return the OCC shape.

    The shape is returned so callers can reuse it for further B-rep operations
    without re-reading the file (avoids double I/O in cam toolpath generation).

    Raises RuntimeError when pythonOCC is unavailable or any step fails.
    """
    shape = load_step(step_path)
    mesh_shape(shape, linear_deflection)
    write_stl(shape, stl_path)
    return shape
