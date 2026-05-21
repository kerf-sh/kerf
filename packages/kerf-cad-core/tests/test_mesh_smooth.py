"""
GK-111: Mesh smoothing (Laplacian + Taubin λ|μ no-shrink).

Oracle contracts
----------------
1. Taubin smoothing of a noisy sphere reduces per-vertex normal variance
   without shrinking the bounding radius > tol.
2. Laplacian smoothing visibly shrinks the sphere (bounding radius decreases
   by at least 1 % after 20 iterations) — contrast check showing the two
   methods differ.
3. Edge cases: empty mesh, single face, bad method/iterations return gracefully.
4. Faces are never modified (only vertex positions change).
5. mesh_smooth is importable from kerf_cad_core.geom.
"""

from __future__ import annotations

import math
import pytest

from kerf_cad_core.geom.mesh_repair import mesh_smooth


# ---------------------------------------------------------------------------
# Mesh factories
# ---------------------------------------------------------------------------

def _icosphere(subdivisions: int = 2, radius: float = 1.0):
    """Subdivided icosphere (pure Python, no deps)."""
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    base_verts = [
        [-1,  phi, 0], [ 1,  phi, 0], [-1, -phi, 0], [ 1, -phi, 0],
        [ 0, -1,  phi], [ 0,  1,  phi], [ 0, -1, -phi], [ 0,  1, -phi],
        [ phi, 0, -1], [ phi, 0,  1], [-phi, 0, -1], [-phi, 0,  1],
    ]

    def _norm(v):
        d = math.sqrt(v[0]**2 + v[1]**2 + v[2]**2)
        return [v[0]/d, v[1]/d, v[2]/d]

    vs = [_norm(v) for v in base_verts]
    fs = [
        [0, 11, 5], [0, 5, 1], [0, 1, 7], [0, 7, 10], [0, 10, 11],
        [1, 5, 9], [5, 11, 4], [11, 10, 2], [10, 7, 6], [7, 1, 8],
        [3, 9, 4], [3, 4, 2], [3, 2, 6], [3, 6, 8], [3, 8, 9],
        [4, 9, 5], [2, 4, 11], [6, 2, 10], [8, 6, 7], [9, 8, 1],
    ]

    for _ in range(subdivisions):
        midpoint_cache: dict = {}

        def _midpoint(a: int, b: int) -> int:
            key = (min(a, b), max(a, b))
            if key in midpoint_cache:
                return midpoint_cache[key]
            va, vb = vs[a], vs[b]
            mid = _norm([(va[0]+vb[0])*0.5, (va[1]+vb[1])*0.5, (va[2]+vb[2])*0.5])
            idx = len(vs)
            vs.append(mid)
            midpoint_cache[key] = idx
            return idx

        new_fs = []
        for f in fs:
            a, b, c = f
            ab = _midpoint(a, b)
            bc = _midpoint(b, c)
            ca = _midpoint(c, a)
            new_fs.extend([
                [a, ab, ca],
                [b, bc, ab],
                [c, ca, bc],
                [ab, bc, ca],
            ])
        fs = new_fs

    vs = [[v[0]*radius, v[1]*radius, v[2]*radius] for v in vs]
    return vs, fs


def _add_noise(verts, amplitude: float = 0.05, seed: int = 42):
    """Add deterministic pseudo-random noise to vertex positions."""
    import random
    rng = random.Random(seed)
    return [
        [v[0] + rng.gauss(0, amplitude),
         v[1] + rng.gauss(0, amplitude),
         v[2] + rng.gauss(0, amplitude)]
        for v in verts
    ]


def _face_normal(verts, f):
    ax, ay, az = verts[f[0]]
    bx, by, bz = verts[f[1]]
    cx, cy, cz = verts[f[2]]
    ux, uy, uz = bx-ax, by-ay, bz-az
    vx, vy, vz = cx-ax, cy-ay, cz-az
    nx = uy*vz - uz*vy
    ny = uz*vx - ux*vz
    nz = ux*vy - uy*vx
    length = math.sqrt(nx*nx + ny*ny + nz*nz)
    if length < 1e-15:
        return [0.0, 0.0, 0.0]
    return [nx/length, ny/length, nz/length]


def _normal_variance(verts, faces):
    """Mean squared deviation of face normals from their mean direction."""
    normals = [_face_normal(verts, f) for f in faces]
    if not normals:
        return 0.0
    mx = sum(n[0] for n in normals) / len(normals)
    my = sum(n[1] for n in normals) / len(normals)
    mz = sum(n[2] for n in normals) / len(normals)
    var = sum(
        (n[0]-mx)**2 + (n[1]-my)**2 + (n[2]-mz)**2
        for n in normals
    ) / len(normals)
    return var


def _bounding_radius(verts):
    """Max distance from the origin."""
    return max(math.sqrt(v[0]**2 + v[1]**2 + v[2]**2) for v in verts)


# ---------------------------------------------------------------------------
# Main oracle tests (GK-111)
# ---------------------------------------------------------------------------

class TestTaubinNoShrink:
    """Taubin smoothing reduces normal variance without shrinking bounding radius."""

    def test_taubin_reduces_normal_variance(self):
        """After 20 Taubin iterations, face-normal variance is strictly lower."""
        verts, faces = _icosphere(subdivisions=2, radius=1.0)
        noisy = _add_noise(verts, amplitude=0.06)

        var_before = _normal_variance(noisy, faces)
        sv, sf = mesh_smooth(noisy, faces, iterations=20, method="taubin",
                             lam=0.33, mu=-0.34)
        var_after = _normal_variance(sv, sf)

        assert var_after < var_before, (
            f"Taubin smoothing should reduce normal variance: "
            f"before={var_before:.6f}, after={var_after:.6f}"
        )

    def test_taubin_no_bounding_shrink(self):
        """Taubin: bounding radius does not shrink below the true sphere radius.

        The noisy sphere has radius ~1.0 + noise; after Taubin smoothing the
        bounding radius should stay near 1.0 (not collapse toward 0).  We allow
        10 % below the base sphere radius as the shrinkage bound.
        """
        radius = 1.0
        verts, faces = _icosphere(subdivisions=2, radius=radius)
        noisy = _add_noise(verts, amplitude=0.05)

        sv, _ = mesh_smooth(noisy, faces, iterations=20, method="taubin",
                            lam=0.33, mu=-0.34)
        r_after = _bounding_radius(sv)

        tol = 0.10  # must not shrink more than 10 % below the base sphere radius
        assert r_after >= radius * (1.0 - tol), (
            f"Taubin bounding radius collapsed too far below sphere radius: "
            f"r_after={r_after:.4f}, threshold={radius * (1.0 - tol):.4f}"
        )

    def test_taubin_faces_unchanged(self):
        """Faces must be identical before and after Taubin smoothing."""
        verts, faces = _icosphere(subdivisions=1)
        sv, sf = mesh_smooth(verts, faces, iterations=5, method="taubin")
        assert sf == [[int(f[0]), int(f[1]), int(f[2])] for f in faces]

    def test_taubin_vertex_count_unchanged(self):
        """Smoothing never adds or removes vertices."""
        verts, faces = _icosphere(subdivisions=2)
        sv, _ = mesh_smooth(verts, faces, iterations=10)
        assert len(sv) == len(verts)


class TestLaplacianShrink:
    """Laplacian smoothing visibly shrinks the mesh (contrast check)."""

    def test_laplacian_shrinks_bounding_radius(self):
        """After 20 Laplacian iterations on a sphere, bounding radius shrinks > 1 %."""
        verts, faces = _icosphere(subdivisions=2, radius=1.0)

        r_before = _bounding_radius(verts)
        sv, _ = mesh_smooth(verts, faces, iterations=20, method="laplacian",
                            lam=0.5)
        r_after = _bounding_radius(sv)

        assert r_after < r_before * 0.99, (
            f"Laplacian smoothing should shrink the sphere: "
            f"before={r_before:.4f}, after={r_after:.4f}"
        )

    def test_laplacian_reduces_normal_variance(self):
        """Laplacian also reduces normal variance (it is a smoother)."""
        verts, faces = _icosphere(subdivisions=2, radius=1.0)
        noisy = _add_noise(verts, amplitude=0.06)

        var_before = _normal_variance(noisy, faces)
        sv, sf = mesh_smooth(noisy, faces, iterations=10, method="laplacian", lam=0.5)
        var_after = _normal_variance(sv, sf)

        assert var_after < var_before, (
            f"Laplacian should reduce normal variance: "
            f"before={var_before:.6f}, after={var_after:.6f}"
        )

    def test_taubin_shrinks_less_than_laplacian(self):
        """Taubin bounding radius >= Laplacian bounding radius after same iterations."""
        verts, faces = _icosphere(subdivisions=2, radius=1.0)

        sv_t, _ = mesh_smooth(verts, faces, iterations=20, method="taubin",
                              lam=0.33, mu=-0.34)
        sv_l, _ = mesh_smooth(verts, faces, iterations=20, method="laplacian",
                              lam=0.33)

        r_taubin = _bounding_radius(sv_t)
        r_laplacian = _bounding_radius(sv_l)

        assert r_taubin > r_laplacian, (
            f"Taubin should shrink less than Laplacian: "
            f"r_taubin={r_taubin:.4f}, r_laplacian={r_laplacian:.4f}"
        )


class TestMeshSmoothEdgeCases:
    """Edge cases and input validation for mesh_smooth."""

    def test_empty_mesh_returns_empty(self):
        """Empty mesh must return empty without raising."""
        vs, fs = mesh_smooth([], [])
        assert vs == []
        assert fs == []

    def test_single_triangle_no_crash(self):
        """Single triangle returns unchanged (isolated vertex — no neighbours to average)."""
        verts = [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]
        faces = [[0, 1, 2]]
        sv, sf = mesh_smooth(verts, faces, iterations=5)
        assert len(sv) == 3
        assert len(sf) == 1

    def test_bad_method_returns_original(self):
        """Unknown method string returns original mesh unchanged."""
        verts, faces = _icosphere(subdivisions=1)
        sv, sf = mesh_smooth(verts, faces, method="bogus")
        assert len(sv) == len(verts)
        assert sf == [[int(f[0]), int(f[1]), int(f[2])] for f in faces]

    def test_zero_iterations_returns_original(self):
        """iterations=0 is invalid — returns original unchanged."""
        verts, faces = _icosphere(subdivisions=1)
        sv, sf = mesh_smooth(verts, faces, iterations=0)
        assert len(sv) == len(verts)

    def test_negative_iterations_returns_original(self):
        """Negative iterations returns original unchanged."""
        verts, faces = _icosphere(subdivisions=1)
        sv, sf = mesh_smooth(verts, faces, iterations=-5)
        assert len(sv) == len(verts)

    def test_bad_verts_returns_gracefully(self):
        """Invalid verts type returns gracefully without raising."""
        sv, sf = mesh_smooth("not_a_list", [[0, 1, 2]])
        # Must not raise; returns something
        assert sv is not None

    def test_one_iteration_changes_verts(self):
        """One iteration of Laplacian must move at least one vertex on an icosphere."""
        verts, faces = _icosphere(subdivisions=1)
        sv, _ = mesh_smooth(verts, faces, iterations=1, method="laplacian", lam=0.5)
        changed = any(
            abs(sv[i][0] - verts[i][0]) > 1e-12 or
            abs(sv[i][1] - verts[i][1]) > 1e-12 or
            abs(sv[i][2] - verts[i][2]) > 1e-12
            for i in range(len(verts))
        )
        assert changed, "At least one vertex should move after 1 Laplacian iteration"

    def test_default_method_is_taubin(self):
        """Default method is taubin (no shrink)."""
        verts, faces = _icosphere(subdivisions=2, radius=1.0)
        r_before = _bounding_radius(verts)
        sv, _ = mesh_smooth(verts, faces, iterations=20)  # default method
        r_after = _bounding_radius(sv)
        # Taubin default — radius must not collapse
        assert r_after >= r_before * 0.90, (
            f"Default (Taubin) should not collapse sphere: "
            f"before={r_before:.4f}, after={r_after:.4f}"
        )


class TestMeshSmoothExport:
    """Verify mesh_smooth is exported correctly from kerf_cad_core.geom."""

    def test_importable_from_geom(self):
        from kerf_cad_core.geom import mesh_smooth as ms
        assert callable(ms)

    def test_in_all(self):
        import kerf_cad_core.geom as geom
        assert "mesh_smooth" in geom.__all__
