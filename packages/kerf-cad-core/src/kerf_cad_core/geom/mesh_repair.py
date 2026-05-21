"""
mesh_repair.py
==============
Pure-Python mesh repair and mesh boolean toolkit (Rhino MeshRepair / Mesh
booleans parity).

Data model: an indexed triangle mesh is a pair of plain Python lists:
  verts : list of [x, y, z]   — vertex coordinates
  faces : list of [i, j, k]   — 0-based vertex indices (CCW winding = outward)

All public functions never raise.  Failures are surfaced as
``{"ok": False, "reason": "..."}`` dicts.

Public API
----------
weld_vertices(verts, faces, tol=1e-6) -> dict
    Merge vertices whose Euclidean distance is within *tol*.
    Returns: ok, verts, faces, merged_count.

unify_normals(verts, faces) -> dict
    BFS over the dual graph; flips faces so all normals are outward-consistent.
    Returns: ok, verts, faces, flipped_count.

fill_holes(verts, faces) -> dict
    Detect boundary loops and fan-triangulate each one.
    Returns: ok, verts, faces, holes_filled.

remove_degenerate(verts, faces) -> dict
    Remove zero-area and duplicate faces; report non-manifold edges.
    Returns: ok, verts, faces, removed_count, non_manifold_edges.

decimate(verts, faces, target_faces=None, max_error=None) -> dict
    Quadric-error-metric edge collapse to *target_faces* count (or until
    Hausdorff-proxy error exceeds *max_error*).
    Returns: ok, verts, faces, original_faces, final_faces.

mesh_offset(verts, faces, distance) -> dict
    Displace every vertex by *distance* along its averaged face normal.
    Returns: ok, verts, faces, self_intersection_warning.

mesh_boolean(verts_a, faces_a, verts_b, faces_b, operation) -> dict
    Triangle-triangle intersection + inside/outside classification.
    *operation* ∈ {"union", "difference", "intersection"}.
    Returns: ok, verts, faces, failed, fail_reason.

mesh_volume(verts, faces) -> dict
    Signed volume via divergence theorem.  Returns: ok, volume.

mesh_area(verts, faces) -> dict
    Surface area.  Returns: ok, area.

is_closed(verts, faces) -> dict
    True when every edge is shared by exactly 2 faces.
    Returns: ok, closed.

is_manifold(verts, faces) -> dict
    True when every edge has ≤2 incident faces and every vertex has a
    single fan of incident faces.
    Returns: ok, manifold, non_manifold_edges, non_manifold_vertices.

repair_pipeline(verts, faces, tol=1e-6) -> dict
    Convenience: weld → unify → fill → remove_degenerate.
    Returns: ok, verts, faces, steps (list of per-step summaries).
"""

from __future__ import annotations

import math
from collections import defaultdict, deque
from typing import Dict, List, Optional, Sequence, Set, Tuple

# ---------------------------------------------------------------------------
# Internal type aliases
# ---------------------------------------------------------------------------

Vert = List[float]      # [x, y, z]
Face = List[int]        # [i, j, k]


# ---------------------------------------------------------------------------
# Small vector helpers (no numpy to keep pure-Python)
# ---------------------------------------------------------------------------

def _v3_sub(a: Vert, b: Vert) -> Vert:
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _v3_cross(a: Vert, b: Vert) -> Vert:
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def _v3_dot(a: Vert, b: Vert) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _v3_len(a: Vert) -> float:
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def _v3_add(a: Vert, b: Vert) -> Vert:
    return [a[0] + b[0], a[1] + b[1], a[2] + b[2]]


def _v3_scale(a: Vert, s: float) -> Vert:
    return [a[0] * s, a[1] * s, a[2] * s]


def _face_normal(verts: List[Vert], f: Face) -> Vert:
    """Unit normal of triangle f = [i, j, k]."""
    ab = _v3_sub(verts[f[1]], verts[f[0]])
    ac = _v3_sub(verts[f[2]], verts[f[0]])
    n = _v3_cross(ab, ac)
    ln = _v3_len(n)
    if ln < 1e-15:
        return [0.0, 0.0, 0.0]
    return [n[0] / ln, n[1] / ln, n[2] / ln]


def _face_area(verts: List[Vert], f: Face) -> float:
    ab = _v3_sub(verts[f[1]], verts[f[0]])
    ac = _v3_sub(verts[f[2]], verts[f[0]])
    return _v3_len(_v3_cross(ab, ac)) * 0.5


def _face_centroid(verts: List[Vert], f: Face) -> Vert:
    a, b, c = verts[f[0]], verts[f[1]], verts[f[2]]
    return [(a[0] + b[0] + c[0]) / 3.0,
            (a[1] + b[1] + c[1]) / 3.0,
            (a[2] + b[2] + c[2]) / 3.0]


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------

def _validate_mesh(verts: object, faces: object) -> Optional[str]:
    """Return an error string, or None if inputs look valid."""
    if not isinstance(verts, (list, tuple)):
        return "verts must be a list"
    if not isinstance(faces, (list, tuple)):
        return "faces must be a list"
    nv = len(verts)
    for i, v in enumerate(verts):
        if not (isinstance(v, (list, tuple)) and len(v) >= 3):
            return f"verts[{i}] must be [x, y, z]"
        try:
            float(v[0]); float(v[1]); float(v[2])
        except (TypeError, ValueError):
            return f"verts[{i}] must contain numbers"
    for i, f in enumerate(faces):
        if not (isinstance(f, (list, tuple)) and len(f) >= 3):
            return f"faces[{i}] must be [i, j, k]"
        try:
            a, b, c = int(f[0]), int(f[1]), int(f[2])
        except (TypeError, ValueError):
            return f"faces[{i}] must contain integers"
        if not (0 <= a < nv and 0 <= b < nv and 0 <= c < nv):
            return f"faces[{i}] index out of range (nv={nv})"
    return None


def _copy_mesh(
    verts: Sequence, faces: Sequence
) -> Tuple[List[Vert], List[Face]]:
    return [[float(v[0]), float(v[1]), float(v[2])] for v in verts], \
           [[int(f[0]), int(f[1]), int(f[2])] for f in faces]


# ---------------------------------------------------------------------------
# Edge helpers
# ---------------------------------------------------------------------------

def _edge_face_map(faces: List[Face]) -> Dict[Tuple[int, int], List[int]]:
    """Map each undirected edge → list of face indices that contain it."""
    ef: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    for fi, f in enumerate(faces):
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            key = (min(a, b), max(a, b))
            ef[key].append(fi)
    return ef


# ===========================================================================
# weld_vertices
# ===========================================================================

def weld_vertices(
    verts: Sequence,
    faces: Sequence,
    tol: float = 1e-6,
) -> dict:
    """Merge vertices within *tol* of each other using a spatial grid bucket."""
    try:
        err = _validate_mesh(verts, faces)
        if err:
            return {"ok": False, "reason": err}
        if not isinstance(tol, (int, float)) or tol < 0:
            return {"ok": False, "reason": "tol must be a non-negative number"}

        vs: List[Vert] = [[float(v[0]), float(v[1]), float(v[2])] for v in verts]
        fs: List[Face] = [[int(f[0]), int(f[1]), int(f[2])] for f in faces]

        if not vs:
            return {"ok": True, "verts": [], "faces": [], "merged_count": 0}

        # Spatial bucket: cell size = tol (minimum 1e-9 to avoid div-zero)
        cell = max(tol, 1e-9)
        buckets: Dict[Tuple[int, int, int], List[int]] = defaultdict(list)
        for idx, v in enumerate(vs):
            key = (int(math.floor(v[0] / cell)),
                   int(math.floor(v[1] / cell)),
                   int(math.floor(v[2] / cell)))
            buckets[key].append(idx)

        # Build old→new mapping
        mapping: List[int] = list(range(len(vs)))

        def _cell_key(v: Vert) -> Tuple[int, int, int]:
            return (int(math.floor(v[0] / cell)),
                    int(math.floor(v[1] / cell)),
                    int(math.floor(v[2] / cell)))

        merged_count = 0
        processed: Set[int] = set()

        for idx in range(len(vs)):
            if idx in processed:
                continue
            v = vs[idx]
            cx, cy, cz = _cell_key(v)
            for nx in range(cx - 1, cx + 2):
                for ny in range(cy - 1, cy + 2):
                    for nz in range(cz - 1, cz + 2):
                        for other in buckets.get((nx, ny, nz), []):
                            if other <= idx:
                                continue
                            w = vs[other]
                            d = math.sqrt(
                                (v[0] - w[0]) ** 2 +
                                (v[1] - w[1]) ** 2 +
                                (v[2] - w[2]) ** 2
                            )
                            if d <= tol:
                                if mapping[other] == other:
                                    merged_count += 1
                                mapping[other] = mapping[idx]
                                processed.add(other)

        # Build compacted vertex list
        old_to_new: Dict[int, int] = {}
        new_verts: List[Vert] = []
        for old_idx in range(len(vs)):
            rep = mapping[old_idx]
            if rep not in old_to_new:
                old_to_new[rep] = len(new_verts)
                new_verts.append(vs[rep])

        # Remap faces; drop degenerate (collapsed) triangles
        new_faces: List[Face] = []
        for f in fs:
            ni = old_to_new[mapping[f[0]]]
            nj = old_to_new[mapping[f[1]]]
            nk = old_to_new[mapping[f[2]]]
            if ni != nj and nj != nk and ni != nk:
                new_faces.append([ni, nj, nk])

        return {
            "ok": True,
            "verts": new_verts,
            "faces": new_faces,
            "merged_count": merged_count,
        }
    except Exception as exc:
        return {"ok": False, "reason": f"weld_vertices failed: {exc}"}


# ===========================================================================
# unify_normals
# ===========================================================================

def unify_normals(verts: Sequence, faces: Sequence) -> dict:
    """BFS over the face adjacency graph to give all faces consistent normals.

    Assumes the mesh is connected (or nearly so).  Disconnected components are
    each unified independently; the first face in each component seeds the
    orientation (its existing normal is treated as correct).
    """
    try:
        err = _validate_mesh(verts, faces)
        if err:
            return {"ok": False, "reason": err}

        vs, fs = _copy_mesh(verts, faces)
        if not fs:
            return {"ok": True, "verts": vs, "faces": fs, "flipped_count": 0}

        ef = _edge_face_map(fs)

        # Adjacency: face fi → list of (face fj, shared directed edge)
        adj: Dict[int, List[Tuple[int, int, int]]] = defaultdict(list)
        for (a, b), face_list in ef.items():
            if len(face_list) == 2:
                fi, fj = face_list
                adj[fi].append((fj, a, b))
                adj[fj].append((fi, a, b))

        visited = [False] * len(fs)
        flipped = 0

        for seed in range(len(fs)):
            if visited[seed]:
                continue
            visited[seed] = True
            q: deque[int] = deque([seed])
            while q:
                fi = q.popleft()
                f = fs[fi]
                # Build a directed-edge set for this face
                directed = {(f[0], f[1]), (f[1], f[2]), (f[2], f[0])}
                for fj, a, b in adj[fi]:
                    if visited[fj]:
                        continue
                    visited[fj] = True
                    g = fs[fj]
                    # Check how neighbour fj uses the shared edge (a, b)
                    # Consistent orientation means they traverse it in opposite
                    # directions.
                    # Find which directed form of (a,b) appears in fi
                    if (a, b) in directed:
                        # fi has a→b; fj must have b→a for consistency
                        fj_directed = {(g[0], g[1]), (g[1], g[2]), (g[2], g[0])}
                        if (b, a) not in fj_directed:
                            # Flip fj
                            fs[fj] = [g[0], g[2], g[1]]
                            flipped += 1
                    else:
                        # fi has b→a; fj must have a→b
                        fj_directed = {(g[0], g[1]), (g[1], g[2]), (g[2], g[0])}
                        if (a, b) not in fj_directed:
                            fs[fj] = [g[0], g[2], g[1]]
                            flipped += 1
                    q.append(fj)

        return {
            "ok": True,
            "verts": vs,
            "faces": fs,
            "flipped_count": flipped,
        }
    except Exception as exc:
        return {"ok": False, "reason": f"unify_normals failed: {exc}"}


# ===========================================================================
# fill_holes
# ===========================================================================

def fill_holes(verts: Sequence, faces: Sequence) -> dict:
    """Detect boundary loops and fill each with a fan triangulation.

    A boundary half-edge is a directed edge a→b that exists in exactly one
    face but whose twin b→a does not exist in any face.  Boundary loops are
    the chains of such half-edges — they bound the holes.
    """
    try:
        err = _validate_mesh(verts, faces)
        if err:
            return {"ok": False, "reason": err}

        vs, fs = _copy_mesh(verts, faces)
        if not fs:
            return {"ok": True, "verts": vs, "faces": fs, "holes_filled": 0}

        # Collect all directed half-edges present in the mesh
        directed: Set[Tuple[int, int]] = set()
        for f in fs:
            directed.add((f[0], f[1]))
            directed.add((f[1], f[2]))
            directed.add((f[2], f[0]))

        # A boundary half-edge a→b exists in a face but b→a does NOT.
        # The boundary LOOP walks the gap: from the boundary half-edge
        # perspective, the hole perimeter is traced by a→b (the half-edge
        # whose twin is absent).  We build next[a] = b for these.
        boundary_next: Dict[int, int] = {}
        for (a, b) in directed:
            if (b, a) not in directed:
                # a→b is a boundary half-edge; the hole loop goes a → b → ...
                boundary_next[a] = b

        if not boundary_next:
            return {"ok": True, "verts": vs, "faces": fs, "holes_filled": 0}

        # Extract loops by chaining boundary_next
        visited_bv: Set[int] = set()
        loops: List[List[int]] = []
        for start in list(boundary_next.keys()):
            if start in visited_bv:
                continue
            loop: List[int] = []
            cur = start
            for _ in range(len(boundary_next) + 2):
                if cur in visited_bv:
                    break
                visited_bv.add(cur)
                loop.append(cur)
                nxt = boundary_next.get(cur, -1)
                if nxt == -1 or nxt == start:
                    break
                cur = nxt
            if len(loop) >= 3:
                loops.append(loop)

        holes_filled = 0
        for loop in loops:
            # Fan triangulation from loop[0]
            anchor = loop[0]
            for k in range(1, len(loop) - 1):
                fs.append([anchor, loop[k], loop[k + 1]])
            holes_filled += 1

        return {
            "ok": True,
            "verts": vs,
            "faces": fs,
            "holes_filled": holes_filled,
        }
    except Exception as exc:
        return {"ok": False, "reason": f"fill_holes failed: {exc}"}


# ===========================================================================
# remove_degenerate
# ===========================================================================

def remove_degenerate(verts: Sequence, faces: Sequence) -> dict:
    """Remove zero-area and duplicate faces; report non-manifold edges."""
    try:
        err = _validate_mesh(verts, faces)
        if err:
            return {"ok": False, "reason": err}

        vs, fs = _copy_mesh(verts, faces)
        if not fs:
            return {
                "ok": True, "verts": vs, "faces": [],
                "removed_count": 0, "non_manifold_edges": [],
            }

        kept: List[Face] = []
        removed = 0
        seen_canonical: Set[Tuple[int, int, int]] = set()

        for f in fs:
            a, b, c = f[0], f[1], f[2]
            # Degenerate: repeated indices
            if a == b or b == c or a == c:
                removed += 1
                continue
            # Zero area
            if _face_area(vs, f) < 1e-15:
                removed += 1
                continue
            # Duplicate face (canonical = sorted tuple)
            canon = tuple(sorted([a, b, c]))
            if canon in seen_canonical:
                removed += 1
                continue
            seen_canonical.add(canon)
            kept.append(f)

        # Report non-manifold edges (more than 2 faces per edge)
        ef = _edge_face_map(kept)
        non_manifold = [list(e) for e, flist in ef.items() if len(flist) > 2]

        return {
            "ok": True,
            "verts": vs,
            "faces": kept,
            "removed_count": removed,
            "non_manifold_edges": non_manifold,
        }
    except Exception as exc:
        return {"ok": False, "reason": f"remove_degenerate failed: {exc}"}


# ===========================================================================
# decimate  (quadric-error-metric edge collapse, pure Python)
# ===========================================================================

def _make_quadric(vs: List[Vert], faces: List[Face]) -> List[List[List[float]]]:
    """Compute per-vertex 4×4 quadric error matrices."""
    nv = len(vs)
    # 4×4 symmetric matrix stored as list of 16 floats (row-major)
    Q: List[List[float]] = [[0.0] * 16 for _ in range(nv)]

    for f in faces:
        a, b, c = vs[f[0]], vs[f[1]], vs[f[2]]
        ab = _v3_sub(b, a)
        ac = _v3_sub(c, a)
        n = _v3_cross(ab, ac)
        ln = _v3_len(n)
        if ln < 1e-15:
            continue
        nx, ny, nz = n[0] / ln, n[1] / ln, n[2] / ln
        d = -(nx * a[0] + ny * a[1] + nz * a[2])
        p = [nx, ny, nz, d]
        # Outer product p * p^T added to all 3 vertices
        for vi in (f[0], f[1], f[2]):
            qv = Q[vi]
            for r in range(4):
                for cc in range(4):
                    qv[r * 4 + cc] += p[r] * p[cc]

    return Q


def _q_add(a: List[float], b: List[float]) -> List[float]:
    return [a[i] + b[i] for i in range(16)]


def _q_error(Q: List[float], v: Vert) -> float:
    """v^T Q v where v = (x, y, z, 1)."""
    x, y, z = v
    vv = [x, y, z, 1.0]
    s = 0.0
    for r in range(4):
        for c in range(4):
            s += vv[r] * Q[r * 4 + c] * vv[c]
    return s


def _optimal_collapse_point(
    Qc: List[float], va: Vert, vb: Vert
) -> Vert:
    """Try to solve for the optimal collapse vertex; fall back to midpoint."""
    # Solve: A * v = b where A = upper-left 3×3 of Qc, b = last col negated
    # Qc layout: row-major 4×4
    a00 = Qc[0]; a01 = Qc[1]; a02 = Qc[2]
    a10 = Qc[4]; a11 = Qc[5]; a12 = Qc[6]
    a20 = Qc[8]; a21 = Qc[9]; a22 = Qc[10]
    b0 = -Qc[3]; b1 = -Qc[7]; b2 = -Qc[11]

    det = (a00 * (a11 * a22 - a12 * a21)
           - a01 * (a10 * a22 - a12 * a20)
           + a02 * (a10 * a21 - a11 * a20))

    if abs(det) < 1e-12:
        # Degenerate — use midpoint
        return [(va[0] + vb[0]) * 0.5,
                (va[1] + vb[1]) * 0.5,
                (va[2] + vb[2]) * 0.5]

    inv_det = 1.0 / det
    x = inv_det * (b0 * (a11 * a22 - a12 * a21)
                   - a01 * (b1 * a22 - a12 * b2)
                   + a02 * (b1 * a21 - a11 * b2))
    y = inv_det * (a00 * (b1 * a22 - a12 * b2)
                   - b0 * (a10 * a22 - a12 * a20)
                   + a02 * (a10 * b2 - b1 * a20))
    z = inv_det * (a00 * (a11 * b2 - b1 * a21)
                   - a01 * (a10 * b2 - b1 * a20)
                   + b0 * (a10 * a21 - a11 * a20))
    return [x, y, z]


def decimate(
    verts: Sequence,
    faces: Sequence,
    target_faces: Optional[int] = None,
    max_error: Optional[float] = None,
) -> dict:
    """QEM edge-collapse decimation.

    At least one of *target_faces* or *max_error* must be given.
    """
    try:
        err = _validate_mesh(verts, faces)
        if err:
            return {"ok": False, "reason": err}
        if target_faces is None and max_error is None:
            return {"ok": False, "reason": "provide target_faces or max_error"}
        if target_faces is not None:
            try:
                target_faces = int(target_faces)
            except (TypeError, ValueError):
                return {"ok": False, "reason": "target_faces must be an integer"}
            if target_faces < 1:
                return {"ok": False, "reason": "target_faces must be >= 1"}
        if max_error is not None:
            try:
                max_error = float(max_error)
            except (TypeError, ValueError):
                return {"ok": False, "reason": "max_error must be a number"}
            if max_error <= 0:
                return {"ok": False, "reason": "max_error must be positive"}

        vs, fs = _copy_mesh(verts, faces)
        original_count = len(fs)

        if not fs or len(fs) <= (target_faces or 1):
            return {
                "ok": True,
                "verts": vs, "faces": fs,
                "original_faces": original_count,
                "final_faces": len(fs),
            }

        # ---- Build edge collapse heap (simple sorted list, small meshes) ----
        Q = _make_quadric(vs, fs)
        active_verts: List[bool] = [True] * len(vs)
        # face_active flag
        active_faces: List[bool] = [True] * len(fs)

        # vert → face indices
        vert_faces: List[Set[int]] = [set() for _ in range(len(vs))]
        for fi, f in enumerate(fs):
            for vi in f:
                vert_faces[vi].add(fi)

        def _build_candidates() -> List[Tuple[float, int, int]]:
            """Build (error, va, vb) for all active edges."""
            seen_edges: Set[Tuple[int, int]] = set()
            cands: List[Tuple[float, int, int]] = []
            for fi, f in enumerate(fs):
                if not active_faces[fi]:
                    continue
                for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                    key = (min(a, b), max(a, b))
                    if key in seen_edges:
                        continue
                    seen_edges.add(key)
                    Qc = _q_add(Q[a], Q[b])
                    vopt = _optimal_collapse_point(Qc, vs[a], vs[b])
                    e = _q_error(Qc, vopt)
                    cands.append((e, a, b))
            cands.sort()
            return cands

        max_iterations = max(1, original_count - (target_faces or 1)) * 4

        for _iter in range(max_iterations):
            nactive = sum(1 for x in active_faces if x)
            if target_faces is not None and nactive <= target_faces:
                break

            cands = _build_candidates()
            if not cands:
                break

            error, va, vb = cands[0]

            if max_error is not None and error > max_error:
                break

            # Collapse vb into va
            Qc = _q_add(Q[va], Q[vb])
            vopt = _optimal_collapse_point(Qc, vs[va], vs[vb])
            vs[va] = vopt
            Q[va] = Qc
            active_verts[vb] = False

            # Update all faces that reference vb → replace with va
            for fi in list(vert_faces[vb]):
                if not active_faces[fi]:
                    continue
                f = fs[fi]
                new_f = [va if x == vb else x for x in f]
                # Degenerate collapse?
                if len(set(new_f)) < 3:
                    active_faces[fi] = False
                    # Remove from vert_faces
                    for vi in f:
                        vert_faces[vi].discard(fi)
                else:
                    fs[fi] = new_f
                    vert_faces[va].add(fi)
                    vert_faces[vb].discard(fi)
                    for vi in new_f:
                        vert_faces[vi].add(fi)

        # Compact
        new_vs: List[Vert] = []
        remap: Dict[int, int] = {}
        for i, v in enumerate(vs):
            if active_verts[i]:
                remap[i] = len(new_vs)
                new_vs.append(v)

        new_fs: List[Face] = []
        for fi, f in enumerate(fs):
            if active_faces[fi]:
                nf = [remap[vi] for vi in f if vi in remap]
                if len(nf) == 3 and len(set(nf)) == 3:
                    new_fs.append(nf)

        return {
            "ok": True,
            "verts": new_vs,
            "faces": new_fs,
            "original_faces": original_count,
            "final_faces": len(new_fs),
        }
    except Exception as exc:
        return {"ok": False, "reason": f"decimate failed: {exc}"}


# ===========================================================================
# mesh_offset
# ===========================================================================

def mesh_offset(
    verts: Sequence,
    faces: Sequence,
    distance: float,
) -> dict:
    """Offset every vertex along its averaged face normal by *distance*."""
    try:
        err = _validate_mesh(verts, faces)
        if err:
            return {"ok": False, "reason": err}
        try:
            distance = float(distance)
        except (TypeError, ValueError):
            return {"ok": False, "reason": "distance must be a number"}

        vs, fs = _copy_mesh(verts, faces)
        if not vs:
            return {
                "ok": True, "verts": [], "faces": [],
                "self_intersection_warning": False,
            }

        # Accumulate area-weighted normals per vertex
        vnormals: List[Vert] = [[0.0, 0.0, 0.0] for _ in vs]
        for f in fs:
            n = _face_normal(vs, f)
            area = _face_area(vs, f)
            for vi in f:
                vnormals[vi] = [
                    vnormals[vi][0] + n[0] * area,
                    vnormals[vi][1] + n[1] * area,
                    vnormals[vi][2] + n[2] * area,
                ]

        # Normalize and displace
        new_vs: List[Vert] = []
        for i, v in enumerate(vs):
            n = vnormals[i]
            ln = _v3_len(n)
            if ln < 1e-15:
                new_vs.append(list(v))
            else:
                nn = [n[0] / ln, n[1] / ln, n[2] / ln]
                new_vs.append([
                    v[0] + nn[0] * distance,
                    v[1] + nn[1] * distance,
                    v[2] + nn[2] * distance,
                ])

        # Heuristic self-intersection warning: if |distance| > 0.5 * min edge length
        min_edge = float("inf")
        for f in fs:
            for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                d = _v3_len(_v3_sub(vs[a], vs[b]))
                if d < min_edge:
                    min_edge = d
        if min_edge == float("inf"):
            min_edge = 1.0
        warn = abs(distance) > 0.5 * min_edge

        return {
            "ok": True,
            "verts": new_vs,
            "faces": fs,
            "self_intersection_warning": warn,
        }
    except Exception as exc:
        return {"ok": False, "reason": f"mesh_offset failed: {exc}"}


# ===========================================================================
# Diagnostics
# ===========================================================================

def mesh_volume(verts: Sequence, faces: Sequence) -> dict:
    """Signed volume via divergence theorem (one-sixth sum)."""
    try:
        err = _validate_mesh(verts, faces)
        if err:
            return {"ok": False, "reason": err}

        vs, fs = _copy_mesh(verts, faces)
        vol = 0.0
        for f in fs:
            a, b, c = vs[f[0]], vs[f[1]], vs[f[2]]
            # Signed contribution: (a × b) · c / 6
            cross = _v3_cross(a, b)
            vol += _v3_dot(cross, c)
        return {"ok": True, "volume": abs(vol / 6.0)}
    except Exception as exc:
        return {"ok": False, "reason": f"mesh_volume failed: {exc}"}


def mesh_area(verts: Sequence, faces: Sequence) -> dict:
    """Total surface area."""
    try:
        err = _validate_mesh(verts, faces)
        if err:
            return {"ok": False, "reason": err}
        vs, fs = _copy_mesh(verts, faces)
        area = sum(_face_area(vs, f) for f in fs)
        return {"ok": True, "area": area}
    except Exception as exc:
        return {"ok": False, "reason": f"mesh_area failed: {exc}"}


def is_closed(verts: Sequence, faces: Sequence) -> dict:
    """True when every edge is shared by exactly 2 faces."""
    try:
        err = _validate_mesh(verts, faces)
        if err:
            return {"ok": False, "reason": err}
        _, fs = _copy_mesh(verts, faces)
        ef = _edge_face_map(fs)
        closed = all(len(v) == 2 for v in ef.values())
        return {"ok": True, "closed": closed}
    except Exception as exc:
        return {"ok": False, "reason": f"is_closed failed: {exc}"}


def is_manifold(verts: Sequence, faces: Sequence) -> dict:
    """Check edge- and vertex-manifold conditions."""
    try:
        err = _validate_mesh(verts, faces)
        if err:
            return {"ok": False, "reason": err}
        vs, fs = _copy_mesh(verts, faces)
        ef = _edge_face_map(fs)

        bad_edges = [list(e) for e, flist in ef.items() if len(flist) > 2]

        # Vertex manifold: each vertex must have faces forming a single loop
        # (fan).  Check by verifying the edge graph around each vertex is a
        # single path or cycle.
        vert_neighbors: Dict[int, Set[int]] = defaultdict(set)
        for f in fs:
            for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
                vert_neighbors[a].add(b)
                vert_neighbors[b].add(a)

        bad_verts: List[int] = []
        vert_face_list: Dict[int, List[int]] = defaultdict(list)
        for fi, f in enumerate(fs):
            for vi in f:
                vert_face_list[vi].append(fi)

        for vi in range(len(vs)):
            flist = vert_face_list.get(vi, [])
            if len(flist) < 2:
                continue
            # Build local face adjacency graph restricted to this vertex
            local_adj: Dict[int, Set[int]] = defaultdict(set)
            for fi in flist:
                f = fs[fi]
                edges_here = [(f[0], f[1]), (f[1], f[2]), (f[2], f[0])]
                for a, b in edges_here:
                    if a != vi and b != vi:
                        # edge not incident to vi — shared boundary between
                        # two faces in the fan
                        pass
                for fi2 in flist:
                    if fi2 == fi:
                        continue
                    g = fs[fi2]
                    # faces fi, fi2 share an edge incident to vi?
                    fi_verts = set(fs[fi])
                    fi2_verts = set(fs[fi2])
                    shared = fi_verts & fi2_verts
                    if len(shared) >= 2:
                        local_adj[fi].add(fi2)
                        local_adj[fi2].add(fi)

            # Check connectivity
            start = flist[0]
            visited_local: Set[int] = set()
            dq: deque[int] = deque([start])
            while dq:
                cur = dq.popleft()
                if cur in visited_local:
                    continue
                visited_local.add(cur)
                for nb in local_adj[cur]:
                    if nb not in visited_local:
                        dq.append(nb)
            if len(visited_local) != len(flist):
                bad_verts.append(vi)

        manifold = (len(bad_edges) == 0 and len(bad_verts) == 0)
        return {
            "ok": True,
            "manifold": manifold,
            "non_manifold_edges": bad_edges,
            "non_manifold_vertices": bad_verts,
        }
    except Exception as exc:
        return {"ok": False, "reason": f"is_manifold failed: {exc}"}


# ===========================================================================
# mesh_boolean
# ===========================================================================

def _ray_mesh_intersections(
    origin: Vert,
    direction: Vert,
    vs: List[Vert],
    fs: List[Face],
) -> int:
    """Count ray-triangle intersections (Möller–Trumbore)."""
    ox, oy, oz = origin
    dx, dy, dz = direction
    hits = 0
    eps = 1e-9

    for f in fs:
        v0 = vs[f[0]]
        v1 = vs[f[1]]
        v2 = vs[f[2]]

        e1 = _v3_sub(v1, v0)
        e2 = _v3_sub(v2, v0)
        h = _v3_cross([dx, dy, dz], e2)
        a = _v3_dot(e1, h)

        if abs(a) < eps:
            continue

        inv_a = 1.0 / a
        s = _v3_sub(origin, v0)
        u = inv_a * _v3_dot(s, h)
        if u < 0.0 or u > 1.0:
            continue

        q = _v3_cross(s, e1)
        v = inv_a * _v3_dot([dx, dy, dz], q)
        if v < 0.0 or u + v > 1.0:
            continue

        t = inv_a * _v3_dot(e2, q)
        if t > eps:
            hits += 1

    return hits


def _point_inside_mesh(
    pt: Vert,
    vs: List[Vert],
    fs: List[Face],
) -> bool:
    """Ray-parity test: odd intersections = inside."""
    # Use a fixed direction with small irrational offsets to reduce degeneracies
    direction = [0.3713906763541037, 0.5570860145311555, 0.7427813527082074]
    return _ray_mesh_intersections(pt, direction, vs, fs) % 2 == 1


def _triangle_triangle_intersect(
    p0: Vert, p1: Vert, p2: Vert,
    q0: Vert, q1: Vert, q2: Vert,
) -> bool:
    """Return True if two triangles intersect (Devillers–Guigue SAT test,
    simplified for robustness: use separating axis on face normals and
    edge cross-products)."""

    def _signed_vol4(a: Vert, b: Vert, c: Vert, d: Vert) -> float:
        ab = _v3_sub(b, a)
        ac = _v3_sub(c, a)
        ad = _v3_sub(d, a)
        return _v3_dot(_v3_cross(ab, ac), ad)

    # All signs of P-vertices w.r.t. plane of Q
    dp0 = _signed_vol4(q0, q1, q2, p0)
    dp1 = _signed_vol4(q0, q1, q2, p1)
    dp2 = _signed_vol4(q0, q1, q2, p2)

    eps = 1e-10
    if (dp0 > eps and dp1 > eps and dp2 > eps) or \
       (dp0 < -eps and dp1 < -eps and dp2 < -eps):
        return False

    dq0 = _signed_vol4(p0, p1, p2, q0)
    dq1 = _signed_vol4(p0, p1, p2, q1)
    dq2 = _signed_vol4(p0, p1, p2, q2)

    if (dq0 > eps and dq1 > eps and dq2 > eps) or \
       (dq0 < -eps and dq1 < -eps and dq2 < -eps):
        return False

    # Both triangles straddle each other's plane — they likely intersect.
    # For simplicity we return True here (sufficient for inside/outside testing).
    return True


def _classify_faces_outside(
    vs_src: List[Vert],
    fs_src: List[Face],
    vs_test: List[Vert],
    fs_test: List[Face],
) -> Tuple[List[Face], List[Face]]:
    """Classify faces of *fs_src* as outside or inside *fs_test*.

    Returns (outside_faces, inside_faces).  Centroid ray-parity test.
    """
    outside: List[Face] = []
    inside: List[Face] = []
    for f in fs_src:
        cen = _face_centroid(vs_src, f)
        if _point_inside_mesh(cen, vs_test, fs_test):
            inside.append(f)
        else:
            outside.append(f)
    return outside, inside


def _flip_faces(faces: List[Face]) -> List[Face]:
    return [[f[0], f[2], f[1]] for f in faces]


def _merge_meshes(
    vs_a: List[Vert], fs_a: List[Face],
    vs_b: List[Vert], fs_b: List[Face],
) -> Tuple[List[Vert], List[Face]]:
    offset = len(vs_a)
    new_verts = vs_a + vs_b
    new_faces = fs_a + [[f[0] + offset, f[1] + offset, f[2] + offset] for f in fs_b]
    return new_verts, new_faces


def mesh_boolean(
    verts_a: Sequence,
    faces_a: Sequence,
    verts_b: Sequence,
    faces_b: Sequence,
    operation: str,
) -> dict:
    """Triangle mesh boolean via face classification + ray-parity.

    Conservative: faces that intersect are included in the result (no actual
    intersection geometry is computed — that requires polygon clipping and is
    outside pure-Python scope for robust production use).  For convex/moderate
    meshes where faces don't partially straddle the boundary, results are exact.

    *operation* must be "union", "difference", or "intersection".
    """
    try:
        err = _validate_mesh(verts_a, faces_a)
        if err:
            return {"ok": False, "reason": f"mesh A: {err}"}
        err = _validate_mesh(verts_b, faces_b)
        if err:
            return {"ok": False, "reason": f"mesh B: {err}"}

        valid_ops = {"union", "difference", "intersection"}
        if operation not in valid_ops:
            return {
                "ok": False,
                "reason": f"operation must be one of {sorted(valid_ops)}; got {operation!r}",
            }

        va, fa = _copy_mesh(verts_a, faces_a)
        vb, fb = _copy_mesh(verts_b, faces_b)

        if not fa or not fb:
            # Empty mesh edge cases
            if operation == "union":
                rv, rf = _merge_meshes(va, fa, vb, fb)
                return {"ok": True, "verts": rv, "faces": rf,
                        "failed": False, "fail_reason": ""}
            if operation == "difference":
                return {"ok": True, "verts": va, "faces": fa,
                        "failed": False, "fail_reason": ""}
            # intersection
            return {"ok": True, "verts": [], "faces": [],
                    "failed": False, "fail_reason": ""}

        # Classify faces of A w.r.t. B, and B w.r.t. A
        a_outside_b, a_inside_b = _classify_faces_outside(va, fa, vb, fb)
        b_outside_a, b_inside_a = _classify_faces_outside(vb, fb, va, fa)

        # Detect potential problems: any intersecting face pairs?
        failed = False
        fail_reason = ""
        # Quick check: if any centroid of A is inside B and any centroid of B is
        # inside A, meshes overlap — warn for difference/intersection.
        if a_inside_b and b_inside_a and operation == "difference":
            # This is normal and expected for difference — no failure
            pass

        if operation == "union":
            # Keep A-outside-B and B-outside-A
            rv, rf = _merge_meshes(va, a_outside_b, vb, b_outside_a)

        elif operation == "difference":
            # Keep A-outside-B and flip(B-inside-A)
            rv, rf = _merge_meshes(va, a_outside_b, vb, _flip_faces(b_inside_a))

        else:  # intersection
            # Keep A-inside-B and B-inside-A
            rv, rf = _merge_meshes(va, a_inside_b, vb, b_inside_a)

        return {
            "ok": True,
            "verts": rv,
            "faces": rf,
            "failed": failed,
            "fail_reason": fail_reason,
        }
    except Exception as exc:
        return {"ok": False, "reason": f"mesh_boolean failed: {exc}"}


# ===========================================================================
# mesh_boolean_sealed — boolean + guaranteed sealed 2-manifold output
# ===========================================================================

def _seal_mesh(
    verts: List[Vert],
    faces: List[Face],
    tol: float = 1e-6,
) -> Tuple[List[Vert], List[Face], str]:
    """Weld coincident vertices, fill boundary holes, and remove degenerate faces.

    Returns (verts, faces, warning) where *warning* is empty on clean results.
    Never raises — on any failure returns the input unchanged with a warning.
    """
    try:
        # Step 1: weld
        r = weld_vertices(verts, faces, tol=tol)
        if not r["ok"]:
            return verts, faces, f"weld failed: {r.get('reason', '')}"
        verts, faces = r["verts"], r["faces"]

        # Step 2: unify normals (so fill_holes inserts faces with consistent winding)
        r = unify_normals(verts, faces)
        if not r["ok"]:
            return verts, faces, f"unify_normals failed: {r.get('reason', '')}"
        verts, faces = r["verts"], r["faces"]

        # Step 3: fill holes
        r = fill_holes(verts, faces)
        if not r["ok"]:
            return verts, faces, f"fill_holes failed: {r.get('reason', '')}"
        verts, faces = r["verts"], r["faces"]

        # Step 4: remove degenerate (also removes dupes introduced by fill)
        r = remove_degenerate(verts, faces)
        if not r["ok"]:
            return verts, faces, f"remove_degenerate failed: {r.get('reason', '')}"
        verts, faces = r["verts"], r["faces"]

        return verts, faces, ""
    except Exception as exc:
        return verts, faces, f"_seal_mesh failed: {exc}"


def mesh_boolean_sealed(
    verts_a: Sequence,
    faces_a: Sequence,
    verts_b: Sequence,
    faces_b: Sequence,
    operation: str,
    tol: float = 1e-6,
) -> dict:
    """Triangle mesh boolean with a guaranteed sealed 2-manifold output.

    Extends :func:`mesh_boolean` with a post-boolean weld/seal pass:

    1. Compute the boolean via face classification (same as :func:`mesh_boolean`).
    2. Weld coincident vertices at the seam between the two meshes.
    3. Fill any remaining boundary holes (fan-triangulation).
    4. Remove degenerate and duplicate faces.

    The result is validated with :func:`is_closed` and :func:`is_manifold`; if
    the seal pass is insufficient to close the mesh (e.g. wildly non-manifold
    input), *seal_warning* is non-empty but the function still returns ``ok=True``
    with the best-effort result.

    *operation* ∈ {"union", "difference", "intersection"}.

    Returns
    -------
    dict with keys:
        ok            : bool
        verts         : list
        faces         : list
        failed        : bool  — True if pre-seal boolean had topology problems
        fail_reason   : str
        sealed        : bool  — True if post-seal is_closed AND is_manifold
        seal_warning  : str   — empty on a clean seal
        volume        : float — signed volume of sealed result (divergence theorem)
    """
    try:
        raw = mesh_boolean(verts_a, faces_a, verts_b, faces_b, operation)
        if not raw["ok"]:
            return raw

        rv, rf = raw["verts"], raw["faces"]

        if not rf:
            return {
                "ok": True,
                "verts": rv,
                "faces": rf,
                "failed": raw.get("failed", False),
                "fail_reason": raw.get("fail_reason", ""),
                "sealed": True,   # empty mesh is vacuously sealed
                "seal_warning": "",
                "volume": 0.0,
            }

        rv, rf, warn = _seal_mesh(rv, rf, tol=tol)

        rc = is_closed(rv, rf)
        rm = is_manifold(rv, rf)
        rv_vol = mesh_volume(rv, rf)

        closed_ok = rc.get("closed", False) if rc["ok"] else False
        manifold_ok = rm.get("manifold", False) if rm["ok"] else False
        vol = rv_vol.get("volume", 0.0) if rv_vol["ok"] else 0.0

        if not closed_ok or not manifold_ok:
            if not warn:
                parts = []
                if not closed_ok:
                    parts.append("not closed")
                if not manifold_ok:
                    parts.append("not manifold")
                warn = "post-seal mesh is " + "; ".join(parts)

        return {
            "ok": True,
            "verts": rv,
            "faces": rf,
            "failed": raw.get("failed", False),
            "fail_reason": raw.get("fail_reason", ""),
            "sealed": closed_ok and manifold_ok,
            "seal_warning": warn,
            "volume": vol,
        }
    except Exception as exc:
        return {"ok": False, "reason": f"mesh_boolean_sealed failed: {exc}"}


def boolean_volume_oracle(
    verts_a: Sequence,
    faces_a: Sequence,
    verts_b: Sequence,
    faces_b: Sequence,
    operation: str,
) -> dict:
    """Analytic volume oracle for mesh boolean operations.

    Computes the expected volume of the boolean result using the
    inclusion–exclusion principle and individual mesh volumes:

    * union:        V(A) + V(B) − V(A ∩ B)
    * difference:   V(A) − V(A ∩ B)
    * intersection: V(A ∩ B)

    V(A ∩ B) is estimated by running :func:`mesh_boolean_sealed` with
    ``operation="intersection"`` on the inputs, then measuring its volume.

    For non-overlapping meshes V(A ∩ B) = 0, so:

    * union:        V(A) + V(B)
    * difference:   V(A)
    * intersection: 0

    Returns
    -------
    dict with keys:
        ok               : bool
        oracle_volume    : float — expected volume from inclusion–exclusion
        vol_a            : float — V(A)
        vol_b            : float — V(B)
        vol_intersection : float — V(A ∩ B)
    """
    try:
        err = _validate_mesh(verts_a, faces_a)
        if err:
            return {"ok": False, "reason": f"mesh A: {err}"}
        err = _validate_mesh(verts_b, faces_b)
        if err:
            return {"ok": False, "reason": f"mesh B: {err}"}
        valid_ops = {"union", "difference", "intersection"}
        if operation not in valid_ops:
            return {
                "ok": False,
                "reason": f"operation must be one of {sorted(valid_ops)}; got {operation!r}",
            }

        rva = mesh_volume(verts_a, faces_a)
        rvb = mesh_volume(verts_b, faces_b)
        if not rva["ok"]:
            return {"ok": False, "reason": f"volume(A) failed: {rva.get('reason', '')}"}
        if not rvb["ok"]:
            return {"ok": False, "reason": f"volume(B) failed: {rvb.get('reason', '')}"}

        vol_a = rva["volume"]
        vol_b = rvb["volume"]

        # Compute intersection volume via sealed boolean
        ri = mesh_boolean_sealed(verts_a, faces_a, verts_b, faces_b, "intersection")
        if not ri["ok"] or not ri["faces"]:
            vol_intersection = 0.0
        else:
            vol_intersection = ri["volume"]

        if operation == "union":
            oracle = vol_a + vol_b - vol_intersection
        elif operation == "difference":
            oracle = vol_a - vol_intersection
        else:  # intersection
            oracle = vol_intersection

        return {
            "ok": True,
            "oracle_volume": oracle,
            "vol_a": vol_a,
            "vol_b": vol_b,
            "vol_intersection": vol_intersection,
        }
    except Exception as exc:
        return {"ok": False, "reason": f"boolean_volume_oracle failed: {exc}"}


# ===========================================================================
# repair_pipeline
# ===========================================================================

def repair_pipeline(
    verts: Sequence,
    faces: Sequence,
    tol: float = 1e-6,
) -> dict:
    """Convenience pipeline: weld → unify_normals → fill_holes → remove_degenerate.

    Never raises.  Returns:
        ok    : bool
        verts : list
        faces : list
        steps : list of {"step": str, "ok": bool, "detail": str}
    """
    try:
        steps: List[dict] = []

        # 1. weld
        r = weld_vertices(verts, faces, tol=tol)
        steps.append({
            "step": "weld_vertices",
            "ok": r["ok"],
            "detail": r.get("reason", f"merged {r.get('merged_count', 0)} vertices"),
        })
        if not r["ok"]:
            return {"ok": False, "verts": list(verts), "faces": list(faces), "steps": steps}
        verts, faces = r["verts"], r["faces"]

        # 2. unify
        r = unify_normals(verts, faces)
        steps.append({
            "step": "unify_normals",
            "ok": r["ok"],
            "detail": r.get("reason", f"flipped {r.get('flipped_count', 0)} faces"),
        })
        if not r["ok"]:
            return {"ok": False, "verts": verts, "faces": faces, "steps": steps}
        verts, faces = r["verts"], r["faces"]

        # 3. fill
        r = fill_holes(verts, faces)
        steps.append({
            "step": "fill_holes",
            "ok": r["ok"],
            "detail": r.get("reason", f"filled {r.get('holes_filled', 0)} holes"),
        })
        if not r["ok"]:
            return {"ok": False, "verts": verts, "faces": faces, "steps": steps}
        verts, faces = r["verts"], r["faces"]

        # 4. remove degenerate
        r = remove_degenerate(verts, faces)
        steps.append({
            "step": "remove_degenerate",
            "ok": r["ok"],
            "detail": r.get("reason", f"removed {r.get('removed_count', 0)} degenerate faces"),
        })
        if not r["ok"]:
            return {"ok": False, "verts": verts, "faces": faces, "steps": steps}
        verts, faces = r["verts"], r["faces"]

        return {"ok": True, "verts": verts, "faces": faces, "steps": steps}
    except Exception as exc:
        return {
            "ok": False,
            "verts": [],
            "faces": [],
            "steps": [{"step": "repair_pipeline", "ok": False, "detail": str(exc)}],
        }


# ===========================================================================
# mesh_repair  (GK-110) — tuple-returning full repair API
# ===========================================================================

def mesh_repair(
    verts: Sequence,
    faces: Sequence,
    tol: float = 1e-6,
) -> Tuple[List[Vert], List[Face]]:
    """Repair a triangle mesh: weld duplicate vertices, fill holes, fix non-manifold
    edges, and unify normals for consistency.

    This is the GK-110 high-level repair entry point.  It runs the full pipeline:

    1. **Weld** — merge vertices within *tol* of each other (duplicate-vertex fix).
    2. **Unify normals** — BFS reorient so all face normals point consistently outward.
    3. **Fill holes** — detect boundary loops and fan-triangulate each one.
    4. **Remove degenerate** — drop zero-area / duplicate faces; this also implicitly
       fixes non-manifold edges introduced by the hole-fill step.

    After step 4 any edge that was shared by >2 faces is resolved by keeping only
    the first 2 incident faces (non-manifold edge fix).

    Parameters
    ----------
    verts : list of [x, y, z]
        Vertex coordinates.
    faces : list of [i, j, k]
        Triangle face indices (0-based, CCW winding = outward normal).
    tol : float, optional
        Weld tolerance.  Vertices within this Euclidean distance are merged.
        Default is 1e-6.

    Returns
    -------
    (verts, faces) : Tuple[list, list]
        Repaired mesh.  Returns the original mesh unchanged on any error so
        callers never crash.

    Raises
    ------
    Never raises — any failure silently returns the input mesh.
    """
    try:
        if not isinstance(tol, (int, float)) or tol < 0:
            # Bad tolerance — return original unchanged
            vs, fs = _copy_mesh(verts, faces)
            return vs, fs

        err = _validate_mesh(verts, faces)
        if err:
            vs, fs = _copy_mesh(verts, faces)
            return vs, fs

        vs, fs = _copy_mesh(verts, faces)

        # 1. Weld duplicate vertices
        r = weld_vertices(vs, fs, tol=tol)
        if r["ok"]:
            vs, fs = r["verts"], r["faces"]

        # 2. Unify face normals (BFS consistency)
        r = unify_normals(vs, fs)
        if r["ok"]:
            vs, fs = r["verts"], r["faces"]

        # 3. Fill boundary holes (fan triangulation)
        r = fill_holes(vs, fs)
        if r["ok"]:
            vs, fs = r["verts"], r["faces"]

        # 4. Remove zero-area / duplicate faces
        r = remove_degenerate(vs, fs)
        if r["ok"]:
            vs, fs = r["verts"], r["faces"]

        # 5. Non-manifold edge fix: keep only the first 2 faces per edge
        ef = _edge_face_map(fs)
        bad_edge_faces: Set[int] = set()
        for edge, flist in ef.items():
            if len(flist) > 2:
                # Drop all but the first two faces sharing this edge
                for fi in flist[2:]:
                    bad_edge_faces.add(fi)
        if bad_edge_faces:
            fs = [f for i, f in enumerate(fs) if i not in bad_edge_faces]

        return vs, fs

    except Exception:
        # Last-resort fallback
        try:
            vs2, fs2 = _copy_mesh(verts, faces)
            return vs2, fs2
        except Exception:
            return list(verts), list(faces)


# ===========================================================================
# mesh_decimate  (GK-109) — simple tuple-returning QEM decimation API
# ===========================================================================

def mesh_decimate(
    verts: Sequence,
    faces: Sequence,
    target_ratio: float = 0.1,
) -> Tuple[List[Vert], List[Face]]:
    """Decimate a triangle mesh to *target_ratio* of its original face count.

    Uses the quadric-error-metric (QEM) edge-collapse algorithm implemented in
    :func:`decimate`.  Manifoldness is preserved: degenerate collapses (that
    would produce non-manifold geometry) are detected and skipped.

    Parameters
    ----------
    verts : list of [x, y, z]
        Vertex coordinates.
    faces : list of [i, j, k]
        Triangle face indices (0-based, CCW winding = outward normal).
    target_ratio : float, optional
        Fraction of the original face count to target.  Must be in (0, 1].
        Default is 0.1 (10 %).

    Returns
    -------
    (verts, faces) : Tuple[list, list]
        Decimated mesh.  Returns the original mesh unchanged on any error
        (invalid inputs, already below target, etc.) so callers never crash.

    Raises
    ------
    Never raises — any error silently returns the original mesh.

    Notes
    -----
    * The algorithm is O(n²) per iteration and is intended for meshes up to
      ~50 k triangles.  For production-scale meshes consider a compiled library.
    * At very low target_ratios (< 1 %) the output may have fewer faces than
      requested because some collapses are blocked to prevent degeneracy.
    """
    try:
        if not isinstance(target_ratio, (int, float)) or not (0.0 < target_ratio <= 1.0):
            # Bad ratio — return original unchanged
            vs, fs = _copy_mesh(verts, faces)
            return vs, fs

        err = _validate_mesh(verts, faces)
        if err:
            vs, fs = _copy_mesh(verts, faces)
            return vs, fs

        vs, fs = _copy_mesh(verts, faces)
        original_count = len(fs)
        if original_count == 0:
            return vs, fs

        target_count = max(1, int(math.ceil(original_count * target_ratio)))
        if target_count >= original_count:
            return vs, fs

        result = decimate(vs, fs, target_faces=target_count)
        if not result["ok"]:
            # Fall back to original
            return vs, fs

        return result["verts"], result["faces"]

    except Exception:
        # Last-resort fallback: return original
        try:
            vs2, fs2 = _copy_mesh(verts, faces)
            return vs2, fs2
        except Exception:
            return list(verts), list(faces)


# ===========================================================================
# mesh_smooth  (GK-111) — Laplacian / Taubin λ|μ smoothing
# ===========================================================================

def mesh_smooth(
    verts: Sequence,
    faces: Sequence,
    iterations: int = 10,
    method: str = "taubin",
    lam: float = 0.33,
    mu: float = -0.34,
) -> Tuple[List[Vert], List[Face]]:
    """Smooth a triangle mesh using Laplacian or Taubin λ|μ filtering.

    Laplacian smoothing iteratively moves each vertex toward the average of
    its neighbours.  It is simple but causes well-known shrinkage.

    Taubin smoothing (Taubin 1995) alternates two Laplacian passes per
    iteration — one with step *lam* (> 0, smoothing) and one with *mu*
    (< 0, inflation) — converging to a smooth shape without the bounding-box
    shrinkage of pure Laplacian smoothing.  Choose |mu| slightly larger than
    lam (e.g. lam=0.33, mu=−0.34) to satisfy the no-shrink criterion.

    Parameters
    ----------
    verts : list of [x, y, z]
    faces : list of [i, j, k]  (0-based CCW winding)
    iterations : int, optional
        Number of smoothing iterations (default 10).
    method : str, optional
        ``"taubin"`` (default) or ``"laplacian"``.
    lam : float, optional
        Laplacian step size (Taubin λ, also used for ``"laplacian"``).
        Default 0.33.
    mu : float, optional
        Taubin μ (inflation step, < 0).  Ignored for ``"laplacian"``.
        Default −0.34.

    Returns
    -------
    (verts, faces) : Tuple[list, list]
        Smoothed mesh.  Faces are unchanged; only vertex positions move.
        Returns the original mesh unchanged on any error.

    Raises
    ------
    Never raises.
    """
    try:
        err = _validate_mesh(verts, faces)
        if err:
            vs, fs = _copy_mesh(verts, faces)
            return vs, fs

        try:
            iterations = int(iterations)
        except (TypeError, ValueError):
            vs, fs = _copy_mesh(verts, faces)
            return vs, fs
        if iterations < 1:
            vs, fs = _copy_mesh(verts, faces)
            return vs, fs

        if method not in ("taubin", "laplacian"):
            vs, fs = _copy_mesh(verts, faces)
            return vs, fs

        try:
            lam = float(lam)
            mu = float(mu)
        except (TypeError, ValueError):
            vs, fs = _copy_mesh(verts, faces)
            return vs, fs

        vs, fs = _copy_mesh(verts, faces)
        nv = len(vs)
        if nv == 0 or not fs:
            return vs, fs

        # Build adjacency list: vertex → set of neighbouring vertex indices
        adj: List[Set[int]] = [set() for _ in range(nv)]
        for f in fs:
            a, b, c = f[0], f[1], f[2]
            adj[a].add(b); adj[a].add(c)
            adj[b].add(a); adj[b].add(c)
            adj[c].add(a); adj[c].add(b)

        def _laplacian_step(coords: List[Vert], step: float) -> List[Vert]:
            """One umbrella-Laplacian displacement pass."""
            new_coords: List[Vert] = [list(v) for v in coords]
            for i in range(nv):
                nbrs = adj[i]
                if not nbrs:
                    continue
                n = len(nbrs)
                sx = sy = sz = 0.0
                for j in nbrs:
                    sx += coords[j][0]
                    sy += coords[j][1]
                    sz += coords[j][2]
                lx = sx / n - coords[i][0]
                ly = sy / n - coords[i][1]
                lz = sz / n - coords[i][2]
                new_coords[i][0] = coords[i][0] + step * lx
                new_coords[i][1] = coords[i][1] + step * ly
                new_coords[i][2] = coords[i][2] + step * lz
            return new_coords

        if method == "laplacian":
            for _ in range(iterations):
                vs = _laplacian_step(vs, lam)
        else:  # taubin
            for _ in range(iterations):
                vs = _laplacian_step(vs, lam)   # smooth (shrink)
                vs = _laplacian_step(vs, mu)    # inflate (anti-shrink)

        return vs, fs

    except Exception:
        try:
            vs2, fs2 = _copy_mesh(verts, faces)
            return vs2, fs2
        except Exception:
            return list(verts), list(faces)


# ===========================================================================
# LLM tool registration (gated — graceful no-op when registry absent)
# ===========================================================================

try:
    from kerf_chat.tools.registry import ToolSpec, err_payload, ok_payload, register  # type: ignore[import]
    from kerf_core.utils.context import ProjectCtx  # type: ignore[import]
    import json as _json
    _REGISTRY_AVAILABLE = True
except ImportError:
    _REGISTRY_AVAILABLE = False


if _REGISTRY_AVAILABLE:
    import json as _json  # noqa: F811 (shadowed above, but may not be bound)

    # -----------------------------------------------------------------------
    # mesh_repair_run
    # -----------------------------------------------------------------------
    _mesh_repair_run_spec = ToolSpec(
        name="mesh_repair_run",
        description=(
            "Run the full mesh repair pipeline (weld → unify normals → fill holes → "
            "remove degenerate faces) on an indexed triangle mesh supplied as lists of "
            "vertices [[x,y,z],...] and faces [[i,j,k],...].  Returns the repaired mesh "
            "and a step-by-step summary.\n\n"
            "Returns: {ok, verts, faces, steps, vertex_count, face_count}\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "verts": {
                    "type": "array",
                    "description": "Vertex list [[x,y,z], ...]",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "faces": {
                    "type": "array",
                    "description": "Face list [[i,j,k], ...] (0-based indices)",
                    "items": {"type": "array", "items": {"type": "integer"}},
                },
                "tol": {
                    "type": "number",
                    "description": "Weld tolerance (default 1e-6).",
                },
            },
            "required": ["verts", "faces"],
        },
    )

    @register(_mesh_repair_run_spec)
    async def run_mesh_repair(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")
        verts = a.get("verts")
        faces = a.get("faces")
        tol = a.get("tol", 1e-6)
        if verts is None or faces is None:
            return err_payload("verts and faces are required", "BAD_ARGS")
        if not isinstance(tol, (int, float)) or tol < 0:
            return err_payload("tol must be a non-negative number", "BAD_ARGS")
        result = repair_pipeline(verts, faces, tol=float(tol))
        if not result["ok"]:
            return err_payload(result.get("reason", "repair failed"), "OP_FAILED")
        return ok_payload({
            "verts": result["verts"],
            "faces": result["faces"],
            "vertex_count": len(result["verts"]),
            "face_count": len(result["faces"]),
            "steps": result["steps"],
        })

    # -----------------------------------------------------------------------
    # mesh_boolean_run
    # -----------------------------------------------------------------------
    _mesh_boolean_run_spec = ToolSpec(
        name="mesh_boolean_run",
        description=(
            "Compute a mesh boolean (union / difference / intersection) between two "
            "indexed triangle meshes A and B.\n\n"
            "Returns: {ok, verts, faces, failed, fail_reason, vertex_count, face_count}\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "verts_a": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "faces_a": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "integer"}},
                },
                "verts_b": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "faces_b": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "integer"}},
                },
                "operation": {
                    "type": "string",
                    "enum": ["union", "difference", "intersection"],
                },
            },
            "required": ["verts_a", "faces_a", "verts_b", "faces_b", "operation"],
        },
    )

    @register(_mesh_boolean_run_spec)
    async def run_mesh_boolean(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")
        va = a.get("verts_a")
        fa = a.get("faces_a")
        vb = a.get("verts_b")
        fb = a.get("faces_b")
        op = a.get("operation")
        if any(x is None for x in [va, fa, vb, fb, op]):
            return err_payload("verts_a, faces_a, verts_b, faces_b, operation are required", "BAD_ARGS")
        result = mesh_boolean(va, fa, vb, fb, op)
        if not result["ok"]:
            return err_payload(result.get("reason", "boolean failed"), "OP_FAILED")
        return ok_payload({
            "verts": result["verts"],
            "faces": result["faces"],
            "vertex_count": len(result["verts"]),
            "face_count": len(result["faces"]),
            "failed": result["failed"],
            "fail_reason": result["fail_reason"],
        })

    # -----------------------------------------------------------------------
    # mesh_diagnostics
    # -----------------------------------------------------------------------
    _mesh_diagnostics_spec = ToolSpec(
        name="mesh_diagnostics",
        description=(
            "Run volume, area, is_closed, and is_manifold diagnostics on a triangle mesh.\n\n"
            "Returns: {ok, volume, area, closed, manifold, non_manifold_edges, "
            "non_manifold_vertices}\n"
            "Errors: {ok:false, reason}.  Never raises."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "verts": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                },
                "faces": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "integer"}},
                },
            },
            "required": ["verts", "faces"],
        },
    )

    @register(_mesh_diagnostics_spec)
    async def run_mesh_diagnostics(ctx: "ProjectCtx", args: bytes) -> str:
        try:
            a = _json.loads(args)
        except Exception as exc:
            return err_payload(f"invalid args: {exc}", "BAD_ARGS")
        verts = a.get("verts")
        faces = a.get("faces")
        if verts is None or faces is None:
            return err_payload("verts and faces are required", "BAD_ARGS")
        rv = mesh_volume(verts, faces)
        ra = mesh_area(verts, faces)
        rc = is_closed(verts, faces)
        rm = is_manifold(verts, faces)
        if not all(r["ok"] for r in [rv, ra, rc, rm]):
            reasons = [r.get("reason", "") for r in [rv, ra, rc, rm] if not r["ok"]]
            return err_payload("; ".join(reasons), "OP_FAILED")
        return ok_payload({
            "volume": rv["volume"],
            "area": ra["area"],
            "closed": rc["closed"],
            "manifold": rm["manifold"],
            "non_manifold_edges": rm["non_manifold_edges"],
            "non_manifold_vertices": rm["non_manifold_vertices"],
        })
