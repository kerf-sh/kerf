"""geom.io — pure-Python geometry import/export sub-package.

Modules
-------
iges        IGES 144 trimmed-surface reader/writer (GK-49).
step_read   Pure-Python STEP AP203/214 B-rep reader (GK-47).
step_write  Pure-Python STEP AP214 B-rep writer (GK-48).
threemf     3MF read/write (sealed manifold + materials + colour + thumbnail) (GK-78).
gltf        glTF 2.0 / GLB mesh + PBR materials reader/writer (GK-79).
obj         Wavefront OBJ mesh + groups + mtllib reader/writer (GK-80).
)
stl         STL read (binary + ASCII) + write (GK-81).
"""
from kerf_cad_core.geom.io.iges import (
    IgesReadError,
    IgesWriteError,
    TrimmedSurface,
    write_iges,
    read_iges,
)
from kerf_cad_core.geom.io.step_read import (
    read_step,
    StepReadError,
)
from kerf_cad_core.geom.io.step_write import (
    write_step,
    StepWriteError,
)
# GK-78: 3MF read/write
from kerf_cad_core.geom.io.threemf import (
    read_threemf,
    write_threemf,
    ThreeMFReadError,
    ThreeMFWriteError,
)
# GK-79: glTF 2.0 / GLB read + write
from kerf_cad_core.geom.io.gltf import (
    read_gltf,
    write_gltf,
    GltfReadError,
    GltfWriteError,
)
# GK-80: Wavefront OBJ read + write
from kerf_cad_core.geom.io.obj import (
    read_obj,
    write_obj,
    ObjReadError,
    ObjWriteError,
)
# GK-81: STL read (binary + ASCII) + write
from kerf_cad_core.geom.io.stl import (
    read_stl,
    write_stl,
    StlReadError,
    StlWriteError,
)
# GK-126: PLY read + write (mesh + per-vertex colour; ASCII + binary)
from kerf_cad_core.geom.io.ply import (
    read_ply,
    write_ply,
    PlyReadError,
    PlyWriteError,
)

# GK-125: DXF read+write
from kerf_cad_core.geom.io.dxf import read_dxf, write_dxf, DxfReadError, DxfWriteError

from kerf_cad_core.geom.io.rhino3dm import read_3dm, Rhino3dmReadError

__all__ = [
    "read_3dm","Rhino3dmReadError",
    "read_dxf","write_dxf","DxfReadError","DxfWriteError",
    "IgesReadError",
    "IgesWriteError",
    "TrimmedSurface",
    "write_iges",
    "read_iges",
    "read_step",
    "StepReadError",
    "write_step",
    "StepWriteError",
    # GK-78
    "read_threemf",
    "write_threemf",
    "ThreeMFReadError",
    "ThreeMFWriteError",
    # GK-79
    "read_gltf",
    "write_gltf",
    "GltfReadError",
    "GltfWriteError",
    # GK-80
    "read_obj",
    "write_obj",
    "ObjReadError",
    "ObjWriteError",
    # GK-81
    "read_stl",
    "write_stl",
    "StlReadError",
    "StlWriteError",
    # GK-126
    "read_ply",
    "write_ply",
    "PlyReadError",
    "PlyWriteError",
]
