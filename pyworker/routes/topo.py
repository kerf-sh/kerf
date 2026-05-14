"""
Topology optimization SIMP loop via FEniCSx.

POST /run-topo
Body: {
    "project_id": str,
    "topo_file_id": str,
    "feature_file_id": str,
    "material_file_id": str,
    "volume_fraction": float | [{body_tag, volume_fraction}],
    "penalization_power": int,
    "filter_radius_mm": float | [{body_tag, filter_radius_mm}],
    "smoothing_iterations": int,           # default 3; Laplacian passes before STEP export
    "max_iterations": int,
    "convergence_tolerance": float,
    "step_b64": str,                       # base64 STEP bytes of design domain
    "boundary_conditions": [...],          # [{type, face_tag, components?}]
    "loads": [...]                         # [{type, face_tag, fx?, fy?, fz?, pressure?}]
}

Algorithm (SIMP with Optimality Criteria update + Heaviside filter):

1.  Decode step_b64 → STEP file.  Feed to Gmsh OCC importer to build tet mesh.
    Fall back to unit-cube mesh when step_b64 is absent or Gmsh unavailable.
    Multi-body: occ.fragment() merges bodies; per-body physical groups tracked.
2.  Material properties from request (E, nu, rho).
3.  Boundary conditions: fixed faces (Dirichlet) + applied loads (Neumann).
    Pulled from boundary_conditions / loads in the request body.
4.  Initialize density field ρᵢ = V_target everywhere (per-body when specified).
5.  Repeat for i = 1 … max_iterations:
    a.  SIMP stiffness:  K_e(ρᵢ) = ρᵢ^p · K_solid
    b.  Assemble K = Σ K_e(ρᵢ)  (linear elastic)
    c.  Solve K · u = F  →  displacement field u
    d.  Compliance:  C = Fᵀ · u
    e.  Sensitivity via adjoint method:
            ∂C/∂ρ = −p · ρ^(p−1) · uᵀ · K_solid · u
    f.  Heaviside filter (cylinder kernel, per-body R when specified):
            ∂Ĉ/∂ρ = (Σⱼ w_ij · ρⱼ · |∂C/∂ρⱼ|) / (Σⱼ w_ij · ρⱼ)
            w_ij = max(0, R − |x_i − x_j|)
    g.  OC update per body (bisection on λ to enforce per-body volume fraction):
            ρ_new = ρ · (−∂C/∂ρ / (λ · V_target))^move
            λ found by bisection: Σ ρ_new = V · V_target
            move = 0.2  (move limit)
            ρ_new = clamp(ρ_new, 0.001, 1.0)
    h.  Heaviside projection (β grows each iteration):
            ρ_proj = tanh(β · ρ) / tanh(β)  (β starts at 5, grows ×1.5/iter, max 20)
    i.  Convergence:  |C_new − C_old| / C_old < tolerance  →  break
6.  Marching cubes at ρ_threshold = 0.5 on final density field → triangle mesh.
7.  Laplacian smoothing (smoothing_iterations passes, boundary-preserving).
8.  NURBS surface fitting per connected component (GeomAPI_PointsToBSplineSurface);
    falls back to faceted face for any component where fitting fails.
    Sew all surfaces into a compound shell; export via STEPControl_Writer.
9.  Return JSON { status, step_b64, final_compliance,
                  final_volume_fraction, iterations, density_field }.
"""

import base64
import math
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator

router = APIRouter()

# ── dependency availability gates ──────────────────────────────────────────────

_DOLFINX_AVAILABLE = False
try:
    import dolfinx  # noqa: F401
    _DOLFINX_AVAILABLE = True
except ImportError:
    pass

_GMSH_AVAILABLE = False
try:
    import gmsh  # noqa: F401
    _GMSH_AVAILABLE = True
except ImportError:
    pass

_OCC_AVAILABLE = False
try:
    from OCC.Core.BRep import BRep_Builder
    from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeFace
    from OCC.Core.TopoDS import TopoDS_Shell, TopoDS_Compound
    from OCC.Core.gp import gp_Pnt, gp_Ax3, gp_Dir, gp_XYZ
    from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
    from OCC.Core.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCC.Core.IFSelect import IFSelect_RetDone
    _OCC_AVAILABLE = True
except ImportError:
    pass

# ── SIMP constants ─────────────────────────────────────────────────────────────

P = 3
MOVE = 0.2
RHO_MIN = 0.001
RHO_MAX = 1.0
RHO_THRESHOLD = 0.5
BETA_START = 5.0
BETA_MAX = 20.0
BETA_GROW = 1.5


# ── request model ──────────────────────────────────────────────────────────────

class BoundaryCondition(BaseModel):
    type: str = "fixed"
    face_tag: int = 1
    components: Optional[List[str]] = None

class Load(BaseModel):
    type: str = "force"
    face_tag: int = 2
    fx: float = 0.0
    fy: float = -1.0
    fz: float = 0.0
    pressure: float = 0.0

class BodyVolumeFraction(BaseModel):
    body_tag: int
    volume_fraction: float = Field(gt=0, lt=1)

class BodyFilterRadius(BaseModel):
    body_tag: int
    filter_radius_mm: float = Field(gt=0)

class TopoRequest(BaseModel):
    project_id: str
    topo_file_id: str
    feature_file_id: str
    material_file_id: str
    # volume_fraction accepts scalar (legacy) or per-body list
    volume_fraction: Union[float, List[BodyVolumeFraction]] = Field(default=0.3)
    penalization_power: int = Field(default=3, gt=0)
    # filter_radius_mm accepts scalar (legacy) or per-body list
    filter_radius_mm: Union[float, List[BodyFilterRadius]] = Field(default=1.5)
    smoothing_iterations: int = Field(default=3, ge=0)
    max_iterations: int = Field(gt=0)
    convergence_tolerance: float = Field(gt=0)
    step_b64: str = ""
    boundary_conditions: List[BoundaryCondition] = Field(default_factory=list)
    loads: List[Load] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_scalar_volume_fraction(cls, data: Any) -> Any:
        # Accept legacy scalar volume_fraction; leave lists as-is
        if isinstance(data, dict):
            vf = data.get("volume_fraction")
            if isinstance(vf, (int, float)):
                # store as float; kept as scalar for single-body path
                pass
            fr = data.get("filter_radius_mm")
            if isinstance(fr, (int, float)):
                pass
        return data

    def volume_fraction_for_body(self, body_tag: Optional[int]) -> float:
        """Return volume fraction for the given body, or the global scalar."""
        if isinstance(self.volume_fraction, list):
            for entry in self.volume_fraction:
                if entry.body_tag == body_tag:
                    return entry.volume_fraction
            # fall back to first entry if body not found
            return self.volume_fraction[0].volume_fraction if self.volume_fraction else 0.3
        return float(self.volume_fraction)

    def filter_radius_for_body(self, body_tag: Optional[int]) -> float:
        """Return filter radius for the given body, or the global scalar."""
        if isinstance(self.filter_radius_mm, list):
            for entry in self.filter_radius_mm:
                if entry.body_tag == body_tag:
                    return entry.filter_radius_mm
            return self.filter_radius_mm[0].filter_radius_mm if self.filter_radius_mm else 1.5
        return float(self.filter_radius_mm)


# ── pure-Python SIMP helpers (no heavy deps) ───────────────────────────────────

def _heaviside_filter(rho, coords, R):
    """
    Cylinder filter: push intermediate densities toward 0/1.

    w_ij = max(0, R - |x_i - x_j|)
    rho_filtered_i = (sum_j w_ij * rho_j) / (sum_j w_ij)
    """
    n = len(rho)
    w_sum = [0.0] * n
    w_rho = [0.0] * n
    for i in range(n):
        xi = coords[i]
        for j in range(n):
            xj = coords[j]
            dist = math.sqrt(
                (xi[0] - xj[0]) ** 2
                + (xi[1] - xj[1]) ** 2
                + (xi[2] - xj[2]) ** 2
            )
            wij = max(0.0, R - dist)
            w_sum[i] += wij
            w_rho[i] += wij * rho[j]
    filtered = [0.0] * n
    for i in range(n):
        if w_sum[i] > 0:
            filtered[i] = w_rho[i] / w_sum[i]
    return filtered


def _oc_update(rho, sens, V_target, V_total, move=MOVE):
    """
    Optimality Criteria update with bisection on λ.

    Constraints: Σ ρᵢ = V · V_target
    ρ_new = clamp(ρ · (−∂C/∂ρ / (λ · V_target))^move, ρ_min, ρ_max)
    """
    rho_new = [0.0] * len(rho)
    l = 1e-9
    r = 1e3
    for _ in range(60):
        lam = (l + r) / 2.0
        numerator = 0.0
        for i in range(len(rho)):
            ratio = -sens[i] / (lam * V_target)
            if ratio <= 0:
                nr = RHO_MIN
            else:
                nr = rho[i] * (ratio ** move)
                nr = max(RHO_MIN, min(RHO_MAX, nr))
            rho_new[i] = nr
            numerator += nr
        if abs(numerator - V_total) < 1e-6:
            break
        if numerator > V_total:
            r = lam
        else:
            l = lam
    return rho_new


def _heaviside_projection(rho, beta):
    """Regularized Heaviside projection: ρ_proj = tanh(β·ρ) / tanh(β)."""
    out = [0.0] * len(rho)
    tanh_beta = math.tanh(beta)
    for i in range(len(rho)):
        out[i] = math.tanh(beta * rho[i]) / tanh_beta
    return out


# ── Gmsh meshing ───────────────────────────────────────────────────────────────

def _mesh_step_with_gmsh(step_path: str, mesh_size_mm: float = 5.0):
    """
    Import a STEP file via Gmsh OCC and generate a tetrahedral mesh.

    Returns (mesh, face_tags_map, body_cell_map) where:
      - mesh is a dolfinx Mesh
      - face_tags_map is dolfinx meshtags for boundary facets
      - body_cell_map is a dict {body_tag: np.ndarray of local cell indices}
        (empty dict when only one volume is present)

    When multiple OCC volumes are present, occ.fragment() is called first so
    that bodies share nodes at their interfaces — enabling conformal coupling
    of density DOFs in the SIMP FEM solve.

    mesh_size_mm controls the maximum element size.
    """
    import gmsh
    import numpy as np
    from mpi4py import MPI
    import dolfinx.io

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    gmsh.option.setNumber("Mesh.CharacteristicSizeMax", mesh_size_mm)
    gmsh.option.setNumber("Mesh.Algorithm3D", 10)

    try:
        gmsh.model.occ.importShapes(step_path)
        gmsh.model.occ.synchronize()

        volumes = gmsh.model.getEntities(3)
        if not volumes:
            raise RuntimeError("STEP file contains no 3-D volumes")

        # Fragment all volumes so interface nodes are shared (conformal mesh).
        # Required for multi-body: shared interface DOFs couple displacement
        # fields across bodies without constraint equations.
        if len(volumes) > 1:
            vol_tags = [(3, tag) for (_, tag) in volumes]
            gmsh.model.occ.fragment(vol_tags, [])
            gmsh.model.occ.synchronize()
            volumes = gmsh.model.getEntities(3)

        surfaces = gmsh.model.getEntities(2)
        if surfaces:
            for i, (dim, tag) in enumerate(surfaces, start=1):
                gmsh.model.addPhysicalGroup(dim, [tag], tag=i, name=f"face_{i}")

        body_phys_tags = {}
        for vol_idx, (_, vol_tag) in enumerate(volumes, start=1):
            phys_tag = 1000 + vol_idx
            gmsh.model.addPhysicalGroup(3, [vol_tag], tag=phys_tag, name=f"body_{vol_idx}")
            body_phys_tags[vol_idx] = phys_tag

        # Single physical group for all volumes so dolfinx reads the whole mesh.
        all_vols = [tag for (_, tag) in volumes]
        gmsh.model.addPhysicalGroup(3, all_vols, tag=1, name="volume")

        gmsh.model.mesh.generate(3)

        with tempfile.NamedTemporaryFile(suffix=".msh", delete=False) as f:
            msh_path = f.name
        gmsh.write(msh_path)
    finally:
        gmsh.finalize()

    mesh, cell_tags, facet_tags = dolfinx.io.gmshio.read_from_msh(
        msh_path,
        MPI.COMM_WORLD,
        gdim=3,
    )
    Path(msh_path).unlink(missing_ok=True)

    # Build body→cell mapping from cell_tags when multiple bodies exist.
    body_cell_map: Dict[int, Any] = {}
    if cell_tags is not None and len(body_phys_tags) > 1:
        import numpy as np
        for body_idx, phys_tag in body_phys_tags.items():
            mask = cell_tags.values == phys_tag
            body_cell_map[body_idx] = cell_tags.indices[mask]

    return mesh, facet_tags, body_cell_map


# ── Laplacian mesh smoothing ───────────────────────────────────────────────────

def _laplacian_smooth(verts, faces, iterations: int):
    """
    Laplacian smoothing of a triangle mesh.

    Boundary vertices (edges shared by exactly one face) are held fixed so
    the mesh footprint does not shrink.  Returns a new (N, 3) vertex array;
    `faces` is unchanged.

    Uses numpy for efficiency; called after marching-cubes before STEP export.
    """
    import numpy as np

    verts = np.array(verts, dtype=float)
    faces = np.array(faces)
    n = len(verts)

    # Build adjacency list
    adj: List[set] = [set() for _ in range(n)]
    edge_count: Dict[tuple, int] = {}
    for tri in faces:
        for a, b in [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]:
            key = (min(a, b), max(a, b))
            edge_count[key] = edge_count.get(key, 0) + 1
            adj[a].add(b)
            adj[b].add(a)

    # Boundary vertices: incident to at least one edge shared by exactly 1 face
    boundary = set()
    for (a, b), cnt in edge_count.items():
        if cnt == 1:
            boundary.add(a)
            boundary.add(b)

    for _ in range(iterations):
        new_verts = verts.copy()
        for i in range(n):
            if i in boundary or not adj[i]:
                continue
            nbrs = list(adj[i])
            new_verts[i] = verts[nbrs].mean(axis=0)
        verts = new_verts

    return verts


# ── connected components of a triangle mesh ───────────────────────────────────

def _connected_components(verts, faces):
    """
    BFS over shared edges to group triangle indices into connected components.

    Returns a list of lists, each being the face indices of one component.
    """
    import numpy as np

    n_faces = len(faces)
    # Map edge → list of face indices
    edge_to_faces: Dict[tuple, List[int]] = {}
    for fi, tri in enumerate(faces):
        for a, b in [(tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])]:
            key = (min(a, b), max(a, b))
            edge_to_faces.setdefault(key, []).append(fi)

    # Adjacency between faces
    face_adj: List[List[int]] = [[] for _ in range(n_faces)]
    for face_list in edge_to_faces.values():
        for i in range(len(face_list)):
            for j in range(i + 1, len(face_list)):
                face_adj[face_list[i]].append(face_list[j])
                face_adj[face_list[j]].append(face_list[i])

    visited = [False] * n_faces
    components = []
    for start in range(n_faces):
        if visited[start]:
            continue
        comp = []
        queue = [start]
        visited[start] = True
        while queue:
            fi = queue.pop()
            comp.append(fi)
            for nb in face_adj[fi]:
                if not visited[nb]:
                    visited[nb] = True
                    queue.append(nb)
        components.append(comp)
    return components


# ── NURBS surface fitting for one mesh component ──────────────────────────────

def _fit_nurbs_face(comp_verts):
    """
    Fit a B-spline surface to the point cloud of one iso-surface component.

    Strategy:
      1. Find the principal plane via PCA of the point cloud.
      2. Project all points onto that plane to get (u, v) parameters.
      3. Sample a regular grid in (u, v) and project each grid point back to
         the nearest mesh point in 3-D.
      4. Feed the 3-D grid to GeomAPI_PointsToBSplineSurface.

    Returns an OCC TopoDS_Face, or raises on failure (caller falls back to
    the existing faceted approach for this component).

    Only called when len(comp_verts) >= 9 (need at least a 3×3 grid).
    """
    import numpy as np
    from OCC.Core.TColgp import TColgp_Array2OfPnt
    from OCC.Core.GeomAPI import GeomAPI_PointsToBSplineSurface
    from OCC.Core.Approx import Approx_ParametrizationType
    from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCC.Core.gp import gp_Pnt

    pts = np.array(comp_verts)
    centroid = pts.mean(axis=0)
    centered = pts - centroid

    # PCA: dominant plane normal = smallest eigenvector
    _, _, Vt = np.linalg.svd(centered, full_matrices=False)
    normal = Vt[2]          # least-variance direction
    u_axis = Vt[0]          # most-variance direction
    v_axis = Vt[1]

    # Project to 2-D plane coordinates
    u_coords = centered @ u_axis
    v_coords = centered @ v_axis

    # Grid size: clamp to a range that keeps the solve tractable
    grid_n = max(3, min(10, int(math.sqrt(len(pts) / 2))))

    u_min, u_max = u_coords.min(), u_coords.max()
    v_min, v_max = v_coords.min(), v_coords.max()
    if u_max - u_min < 1e-10 or v_max - v_min < 1e-10:
        raise ValueError("degenerate plane projection")

    u_lin = np.linspace(u_min, u_max, grid_n)
    v_lin = np.linspace(v_min, v_max, grid_n)

    # For each grid cell, pick the nearest original point in 3-D
    from scipy.spatial import cKDTree  # type: ignore
    tree = cKDTree(pts)

    occ_array = TColgp_Array2OfPnt(1, grid_n, 1, grid_n)
    for iu, u in enumerate(u_lin):
        for iv, v in enumerate(v_lin):
            query_3d = centroid + u * u_axis + v * v_axis
            _, idx = tree.query(query_3d)
            p = pts[idx]
            occ_array.SetValue(iu + 1, iv + 1, gp_Pnt(p[0], p[1], p[2]))

    fitter = GeomAPI_PointsToBSplineSurface(
        occ_array,
        Approx_ParametrizationType.Approx_ChordLength,
        3, 8,   # degree min/max
        3,      # continuity (GeomAbs_C2 = 3)
        1e-2,   # tolerance
    )
    if not fitter.IsDone():
        raise RuntimeError("GeomAPI_PointsToBSplineSurface did not converge")

    surface = fitter.Surface()
    face_maker = BRepBuilderAPI_MakeFace(surface, 1e-6)
    if not face_maker.IsDone():
        raise RuntimeError("BRepBuilderAPI_MakeFace failed for B-spline surface")
    return face_maker.Face()


# ── marching-cubes → STEP export (with smoothing + NURBS) ────────────────────

def _density_field_to_grid(coords, rho_array, grid_n=30):
    """
    Voxelise a scattered density field onto a regular 3-D grid for marching cubes.

    Returns (grid, spacing, origin) where grid has shape (grid_n, grid_n, grid_n).
    """
    import numpy as np

    coords = np.asarray(coords)
    rho = np.asarray(rho_array)

    mn = coords.min(axis=0)
    mx = coords.max(axis=0)
    span = mx - mn
    span[span == 0] = 1.0

    gi = np.floor(((coords - mn) / span) * (grid_n - 1)).astype(int)
    gi = np.clip(gi, 0, grid_n - 1)

    grid = np.zeros((grid_n, grid_n, grid_n), dtype=float)
    count = np.zeros_like(grid)
    np.add.at(grid, (gi[:, 0], gi[:, 1], gi[:, 2]), rho)
    np.add.at(count, (gi[:, 0], gi[:, 1], gi[:, 2]), 1)
    mask = count > 0
    grid[mask] /= count[mask]

    spacing = span / (grid_n - 1)
    return grid, spacing, mn


def _marching_cubes_to_step(
    coords,
    rho_array,
    threshold=RHO_THRESHOLD,
    smoothing_iterations: int = 3,
) -> bytes:
    """
    Threshold the density field, run marching cubes, apply Laplacian smoothing,
    then attempt NURBS surface fitting per connected component.

    For each component:
      - If the component has >= 9 vertices and scipy is available, attempt
        GeomAPI_PointsToBSplineSurface fitting.
      - If fitting fails for any component, fall back to one triangular OCC
        face per triangle in that component (same as the pre-NURBS behaviour).

    The result is never worse than the old faceted export.
    Returns raw STEP bytes.
    """
    from skimage.measure import marching_cubes
    import numpy as np
    from OCC.Core.BRep import BRep_Builder
    from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Sewing, BRepBuilderAPI_MakeFace
    from OCC.Core.TopoDS import TopoDS_Compound
    from OCC.Core.gp import gp_Pnt
    from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_MakePolygon
    from OCC.Core.STEPControl import STEPControl_Writer, STEPControl_AsIs
    from OCC.Core.IFSelect import IFSelect_RetDone

    _SCIPY_AVAILABLE = False
    try:
        import scipy  # noqa: F401
        _SCIPY_AVAILABLE = True
    except ImportError:
        pass

    grid, spacing, origin = _density_field_to_grid(coords, rho_array)

    try:
        verts, faces, normals, _ = marching_cubes(grid, level=threshold, spacing=tuple(spacing))
    except ValueError:
        raise RuntimeError(
            "marching_cubes: no iso-surface found at threshold "
            f"{threshold} — density field may be uniform or not converged"
        )

    if len(faces) == 0:
        raise RuntimeError("marching_cubes produced zero triangles")

    verts = verts + origin  # shift to world coordinates

    if smoothing_iterations > 0:
        verts = _laplacian_smooth(verts, faces, smoothing_iterations)

    sewer = BRepBuilderAPI_Sewing(1e-3)
    components = _connected_components(verts, faces)

    for comp_face_indices in components:
        nurbs_face = None

        if _SCIPY_AVAILABLE:
            comp_vert_idx = set()
            for fi in comp_face_indices:
                comp_vert_idx.update(faces[fi].tolist())
            comp_verts_3d = [verts[i].tolist() for i in comp_vert_idx]

            if len(comp_verts_3d) >= 9:
                try:
                    nurbs_face = _fit_nurbs_face(comp_verts_3d)
                except Exception:
                    nurbs_face = None

        if nurbs_face is not None:
            sewer.Add(nurbs_face)
        else:
            # Faceted fallback for this component
            for fi in comp_face_indices:
                tri = faces[fi]
                p0, p1, p2 = (verts[i] for i in tri)
                poly = BRepBuilderAPI_MakePolygon()
                poly.Add(gp_Pnt(float(p0[0]), float(p0[1]), float(p0[2])))
                poly.Add(gp_Pnt(float(p1[0]), float(p1[1]), float(p1[2])))
                poly.Add(gp_Pnt(float(p2[0]), float(p2[1]), float(p2[2])))
                poly.Close()
                if not poly.IsDone():
                    continue
                wire = poly.Wire()
                face_maker = BRepBuilderAPI_MakeFace(wire)
                if not face_maker.IsDone():
                    continue
                sewer.Add(face_maker.Face())

    sewer.Perform()
    sewn = sewer.SewedShape()

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    builder.Add(compound, sewn)

    writer = STEPControl_Writer()
    writer.Transfer(compound, STEPControl_AsIs)

    with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
        step_path = f.name
    try:
        status = writer.Write(step_path)
        if status != IFSelect_RetDone:
            raise RuntimeError(f"STEPControl_Writer.Write failed with status {status}")
        return Path(step_path).read_bytes()
    finally:
        Path(step_path).unlink(missing_ok=True)


# ── main SIMP loop ─────────────────────────────────────────────────────────────

def _run_fenicsx_simp(req: TopoRequest) -> dict:
    """
    Run SIMP topology optimization via FEniCSx.

    When step_b64 is provided and Gmsh is available, meshes the STEP geometry.
    Otherwise falls back to a structured unit-cube mesh (Phase 1 behaviour).

    Multi-body: when the STEP has multiple OCC volumes, occ.fragment() produces
    a conformal mesh and per-body OC updates use the body-specific volume
    fraction and filter radius from req.volume_fraction / req.filter_radius_mm.
    """
    import dolfinx
    import dolfinx.mesh
    import dolfinx.fem
    import dolfinx.fem.petsc
    import dolfinx.io
    from mpi4py import MPI
    import ufl
    import numpy as np

    comm = MPI.COMM_WORLD
    warnings = []

    facet_tags = None
    body_cell_map: Dict[int, Any] = {}

    if req.step_b64 and _GMSH_AVAILABLE:
        step_bytes = base64.b64decode(req.step_b64)
        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as f:
            step_path = f.name
            f.write(step_bytes)
        try:
            mesh, facet_tags, body_cell_map = _mesh_step_with_gmsh(
                step_path,
                mesh_size_mm=req.filter_radius_for_body(None) * 3.0,
            )
        except Exception as exc:
            warnings.append(f"Gmsh meshing failed ({exc}); falling back to unit-cube mesh")
            mesh = dolfinx.mesh.create_unit_cube(comm, 10, 10, 10)
            facet_tags = None
            body_cell_map = {}
        finally:
            Path(step_path).unlink(missing_ok=True)
    else:
        if req.step_b64 and not _GMSH_AVAILABLE:
            warnings.append("Gmsh not installed; using unit-cube mesh. Install: pip install gmsh")
        mesh = dolfinx.mesh.create_unit_cube(comm, 10, 10, 10)
        facet_tags = None
        body_cell_map = {}

    V = dolfinx.fem.functionspace(mesh, ("Lagrange", 1, (3,)))
    Q = dolfinx.fem.functionspace(mesh, ("DG", 0))

    p = req.penalization_power
    n_cells = mesh.topology.index_map(mesh.topology.dim).size_local

    # Per-body volume targets: each body enforces its own V_target independently.
    # Single-body (or no body_cell_map): entire domain with one V_target.
    if body_cell_map:
        body_tags_sorted = sorted(body_cell_map.keys())
        body_V_targets = {bt: req.volume_fraction_for_body(bt) for bt in body_tags_sorted}
        body_V_totals = {
            bt: len(body_cell_map[bt]) * body_V_targets[bt]
            for bt in body_tags_sorted
        }
    else:
        body_tags_sorted = []
        V_target_global = req.volume_fraction_for_body(None)
        V_total_global = n_cells * V_target_global

    E0 = 200e3
    E_min = 1e-3 * E0
    nu = 0.3

    def epsilon(v):
        return ufl.sym(ufl.grad(v))

    def sigma(v, rho_val):
        E = E_min + (rho_val ** p) * (E0 - E_min)
        lam = E * nu / ((1 + nu) * (1 - 2 * nu))
        mu = E / (2 * (1 + nu))
        return lam * ufl.tr(epsilon(v)) * ufl.Identity(3) + 2 * mu * epsilon(v)

    fdim = mesh.topology.dim - 1

    bcs = []
    if req.boundary_conditions and facet_tags is not None:
        for bc_spec in req.boundary_conditions:
            tag = bc_spec.face_tag
            facets = facet_tags.find(tag)
            if len(facets) == 0:
                warnings.append(f"BC face_tag={tag} matched no facets in mesh")
                continue
            dofs = dolfinx.fem.locate_dofs_topological(V, fdim, facets)
            u_zero = dolfinx.fem.Function(V)
            u_zero.x.array[:] = 0.0
            bcs.append(dolfinx.fem.dirichletbc(u_zero, dofs))
    else:
        def left_boundary(x):
            return np.isclose(x[0], 0.0)
        left_facets = dolfinx.mesh.locate_entities_boundary(mesh, fdim, left_boundary)
        bc_dofs = dolfinx.fem.locate_dofs_topological(V, fdim, left_facets)
        u_zero = dolfinx.fem.Function(V)
        u_zero.x.array[:] = 0.0
        bcs.append(dolfinx.fem.dirichletbc(u_zero, bc_dofs))

    load_measures = []
    if req.loads and facet_tags is not None:
        for load_spec in req.loads:
            tag = load_spec.face_tag
            load_facets = facet_tags.find(tag)
            if len(load_facets) == 0:
                warnings.append(f"Load face_tag={tag} matched no facets in mesh")
                continue
            ft = dolfinx.mesh.meshtags(
                mesh, fdim,
                load_facets,
                np.full(len(load_facets), tag, dtype=np.int32),
            )
            ds_part = ufl.Measure("ds", domain=mesh, subdomain_data=ft)
            if load_spec.type == "force":
                trac = dolfinx.fem.Constant(
                    mesh,
                    dolfinx.default_scalar_type((load_spec.fx, load_spec.fy, load_spec.fz)),
                )
            else:
                trac = dolfinx.fem.Constant(
                    mesh,
                    dolfinx.default_scalar_type((0.0, load_spec.pressure, 0.0)),
                )
            load_measures.append((trac, ds_part, tag))
    else:
        def right_boundary(x):
            return np.isclose(x[0], 1.0)
        right_facets = dolfinx.mesh.locate_entities_boundary(mesh, fdim, right_boundary)
        rt = dolfinx.mesh.meshtags(
            mesh, fdim,
            np.concatenate([right_facets]),
            np.ones(len(right_facets), dtype=np.int32),
        )
        ds_default = ufl.Measure("ds", domain=mesh, subdomain_data=rt)
        f_trac = dolfinx.fem.Constant(
            mesh, dolfinx.default_scalar_type((0.0, -1.0, 0.0))
        )
        load_measures.append((f_trac, ds_default, 1))

    u = dolfinx.fem.Function(V)
    v = ufl.TestFunction(V)
    du = ufl.TrialFunction(V)

    compliance_history = []
    rho = dolfinx.fem.Function(Q)
    coords = Q.tabulate_dof_coordinates()

    # Initialize density: per-body targets when available
    if body_cell_map and body_tags_sorted:
        rho.x.array[:] = req.volume_fraction_for_body(body_tags_sorted[0])
        for bt in body_tags_sorted:
            cell_idx = body_cell_map[bt]
            rho.x.array[cell_idx] = req.volume_fraction_for_body(bt)
    else:
        rho.x.array[:] = V_target_global

    rho_array = rho.x.array.copy()

    final_compliance = 0.0
    final_iter = 0
    beta = BETA_START

    for iteration in range(req.max_iterations):
        rho.x.array[:] = rho_array
        a = ufl.inner(sigma(du, rho), epsilon(v)) * ufl.dx

        L = None
        for trac, ds_part, tag in load_measures:
            term = ufl.inner(trac, v) * ds_part(tag)
            L = term if L is None else L + term
        if L is None:
            L = ufl.inner(dolfinx.fem.Constant(mesh, dolfinx.default_scalar_type((0.0, 0.0, 0.0))), v) * ufl.dx

        problem = dolfinx.fem.petsc.LinearProblem(
            a, L, bcs=bcs,
            petsc_options={"ksp_type": "cg", "pc_type": "gamg", "ksp_rtol": 1e-8},
        )
        u = problem.solve()

        compliance_forms = []
        for trac, ds_part, tag in load_measures:
            compliance_forms.append(dolfinx.fem.form(ufl.inner(trac, u) * ds_part(tag)))
        C = sum(dolfinx.fem.assemble_scalar(cf) for cf in compliance_forms)
        compliance_history.append(float(C))
        final_compliance = float(C)
        final_iter = iteration + 1

        sigma_solid = lambda v: (E0 - E_min) * (
            nu / ((1 + nu) * (1 - 2 * nu)) * ufl.tr(epsilon(v)) * ufl.Identity(3)
            + 1 / (1 + nu) * epsilon(v)
        )
        sens_expr = dolfinx.fem.Expression(
            -p * rho ** (p - 1) * ufl.inner(sigma_solid(u), epsilon(u)),
            Q.element.interpolation_points(),
        )
        sens_fn = dolfinx.fem.Function(Q)
        sens_fn.interpolate(sens_expr)
        sens = sens_fn.x.array.tolist()
        coords_list = coords.tolist()

        if body_cell_map and body_tags_sorted:
            # Per-body OC update with body-specific V_target and filter radius
            rho_new = list(rho_array)
            for bt in body_tags_sorted:
                cell_idx = body_cell_map[bt].tolist()
                R = req.filter_radius_for_body(bt)
                bdy_rho = [rho_array[i] for i in cell_idx]
                bdy_sens = [sens[i] for i in cell_idx]
                bdy_coords = [coords_list[i] for i in cell_idx]
                bdy_V_target = body_V_targets[bt]
                bdy_V_total = body_V_totals[bt]
                bdy_filtered = _heaviside_filter(bdy_rho, bdy_coords, R)
                bdy_updated = _oc_update(bdy_filtered, bdy_sens, bdy_V_target, bdy_V_total)
                for local_j, global_i in enumerate(cell_idx):
                    rho_new[global_i] = bdy_updated[local_j]
        else:
            R = req.filter_radius_for_body(None)
            rho_f = _heaviside_filter(rho_array.tolist(), coords_list, R)
            rho_new = _oc_update(rho_f, sens, V_target_global, V_total_global)

        beta = min(beta * BETA_GROW, BETA_MAX)
        rho_proj = _heaviside_projection(rho_new, beta)
        rho_proj = [max(RHO_MIN, min(RHO_MAX, r)) for r in rho_proj]

        if len(compliance_history) >= 2:
            rel_change = abs(compliance_history[-1] - compliance_history[-2]) / (abs(compliance_history[-2]) + 1e-12)
            if rel_change < req.convergence_tolerance:
                rho_array = np.array(rho_proj)
                break

        rho_array = np.array(rho_proj)

    density_field = []
    for i, (coord, r) in enumerate(zip(coords.tolist(), rho_array)):
        entry = {"x": coord[0], "y": coord[1], "z": coord[2], "rho": float(r)}
        # Tag entries with body membership for multi-body results
        if body_cell_map:
            for bt, cell_idx in body_cell_map.items():
                if i in set(cell_idx.tolist()):
                    entry["body_tag"] = bt
                    break
        density_field.append(entry)

    final_vol_frac = float(sum(rho_array) / len(rho_array)) if len(rho_array) else req.volume_fraction_for_body(None)

    output_step_b64 = ""
    if _OCC_AVAILABLE:
        try:
            step_bytes = _marching_cubes_to_step(
                coords.tolist(),
                rho_array.tolist(),
                smoothing_iterations=req.smoothing_iterations,
            )
            output_step_b64 = base64.b64encode(step_bytes).decode()
        except Exception as exc:
            warnings.append(f"marching-cubes STEP export failed: {exc}")
    else:
        warnings.append(
            "pythonOCC not installed — STEP export skipped. "
            "Install: conda install -c conda-forge pythonocc-core"
        )

    return {
        "status": "success",
        "output_mesh_file_id": "",
        "step_b64": output_step_b64,
        "final_compliance": final_compliance,
        "final_volume_fraction": final_vol_frac,
        "iterations": final_iter,
        "density_field": density_field,
        "warnings": warnings,
    }


# ── route ──────────────────────────────────────────────────────────────────────

@router.post("/run-topo")
async def run_topo(req: TopoRequest):
    """
    Run SIMP topology optimization.

    When dolfinx is available, runs the full SIMP loop.
    When step_b64 + gmsh are available, meshes the real geometry; otherwise
    falls back to a unit-cube domain.
    When pythonOCC is available, exports the density threshold as a STEP file
    (NURBS surfaces where fitting succeeds, faceted fallback otherwise) and
    returns it in step_b64.
    When dolfinx is not installed, returns ENGINE_PENDING_WARNING.
    """
    if not _DOLFINX_AVAILABLE:
        return {
            "status": "pending",
            "output_mesh_file_id": "",
            "step_b64": "",
            "final_compliance": 0.0,
            "final_volume_fraction": 0.0,
            "iterations": 0,
            "warnings": ["Engine pending — FEniCSx not yet deployed."],
        }

    try:
        result = _run_fenicsx_simp(req)
        return result
    except Exception as exc:
        return {
            "status": "error",
            "output_mesh_file_id": "",
            "step_b64": "",
            "final_compliance": 0.0,
            "final_volume_fraction": 0.0,
            "iterations": 0,
            "warnings": [f"SIMP loop error: {exc}"],
        }
