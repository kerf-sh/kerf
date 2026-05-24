"""
kerf_cad_core._linalg — canonical pure-Python linear algebra primitives.

No numpy/scipy dependency. All functions operate on plain Python lists or
tuples so they can be used from constrained environments or embedded solvers.

Shared by:
  - kerf_cad_core.mbd.solver   (planar MBD solver)
  - kerf_cad_core.robotics.arm (DH / FK / Jacobian)

kerf-motion re-exports the quaternion / Mat3 / Vec3 helpers that it already
defines internally in body.py (identical semantics, tuple-based); cross-
package dedup is noted in the module-level docstring rather than introducing
a new package dependency.

Public API
----------
Dense matrix (list-of-lists), general dimension:
  matmul(A, B)               → list[list[float]]   matrix multiply A(m×k) @ B(k×n)
  matvec(A, x)               → list[float]          A(m×n) @ x(n,)
  transpose(A)               → list[list[float]]

Vector helpers (list[float]):
  vadd(a, b)                 → list[float]
  vsub(a, b)                 → list[float]
  vscale(s, a)               → list[float]
  vdot(a, b)                 → float
  vnorm(a)                   → float

Initializers:
  zeros(n)                   → list[float]
  eye(n)                     → list[list[float]]

Linear system solver:
  lu_solve(A, b)             → list[float] | None   LU with partial pivoting

3-D vector / Mat3 / quaternion (tuple-based, compatible with kerf_motion.body):
  Vec3 = tuple[float, float, float]
  Mat3 = tuple[tuple[float,float,float], ...]
  Quat = tuple[float, float, float, float]  # (w, x, y, z)

  cross3(a, b)               → list[float]   (also works for tuple input)
  dot3(a, b)                 → float
  norm3(v)                   → float
  quat_mul(p, q)             → Quat
  quat_norm(q)               → float
  quat_normalize(q)          → Quat
  quat_to_rotmat(q)          → Mat3

4×4 homogeneous transforms (list-of-lists):
  identity4()                → list[list[float]]
  mat4_mul(A, B)             → list[list[float]]
  mat4_col(T, j)             → list[float]

Determinant / misc:
  det_square(M)              → float   (n×n Gaussian elimination)
  mat_mul_rect(A, B)         → list[list[float]]   alias for matmul
  mat_transpose(A)           → list[list[float]]   alias for transpose

Author: imranparuk
"""

from __future__ import annotations

import math
from typing import List, Optional, Tuple

# ---------------------------------------------------------------------------
# Type aliases (for readability in type annotations)
# ---------------------------------------------------------------------------

Vec3 = Tuple[float, float, float]
Mat3 = Tuple[Tuple[float, float, float],
             Tuple[float, float, float],
             Tuple[float, float, float]]
Quat = Tuple[float, float, float, float]  # (w, x, y, z)
_Mat4 = List[List[float]]

# ---------------------------------------------------------------------------
# General dense matrix helpers (list-of-lists)
# ---------------------------------------------------------------------------


def matmul(A: List[List[float]], B: List[List[float]]) -> List[List[float]]:
    """Matrix multiply A (m×k) @ B (k×n) → (m×n)."""
    m, k = len(A), len(A[0])
    n = len(B[0])
    C = [[0.0] * n for _ in range(m)]
    for i in range(m):
        for j in range(n):
            s = 0.0
            for p in range(k):
                s += A[i][p] * B[p][j]
            C[i][j] = s
    return C


# Alias used by arm.py internals
mat_mul_rect = matmul


def matvec(A: List[List[float]], x: List[float]) -> List[float]:
    """Matrix-vector product A (m×n) @ x (n,) → (m,)."""
    m = len(A)
    y = [0.0] * m
    for i in range(m):
        s = 0.0
        for j, xj in enumerate(x):
            s += A[i][j] * xj
        y[i] = s
    return y


def transpose(A: List[List[float]]) -> List[List[float]]:
    """Transpose a matrix."""
    if not A:
        return []
    m, n = len(A), len(A[0])
    return [[A[i][j] for i in range(m)] for j in range(n)]


# Alias
mat_transpose = transpose

# ---------------------------------------------------------------------------
# Vector helpers
# ---------------------------------------------------------------------------


def vadd(a: List[float], b: List[float]) -> List[float]:
    return [a[i] + b[i] for i in range(len(a))]


def vsub(a: List[float], b: List[float]) -> List[float]:
    return [a[i] - b[i] for i in range(len(a))]


def vscale(s: float, a: List[float]) -> List[float]:
    return [s * v for v in a]


def vdot(a: List[float], b: List[float]) -> float:
    return sum(ai * bi for ai, bi in zip(a, b))


def vnorm(a: List[float]) -> float:
    return math.sqrt(sum(v * v for v in a))


def zeros(n: int) -> List[float]:
    return [0.0] * n


def eye(n: int) -> List[List[float]]:
    I = [[0.0] * n for _ in range(n)]
    for i in range(n):
        I[i][i] = 1.0
    return I


# ---------------------------------------------------------------------------
# Linear system solver: LU decomposition with partial pivoting
# ---------------------------------------------------------------------------


def lu_solve(A: List[List[float]], b: List[float]) -> Optional[List[float]]:
    """
    Solve Ax = b via LU decomposition with partial pivoting.

    Returns None if the system is singular (|pivot| < 1e-14).
    A is NOT modified (a copy is made internally).
    """
    n = len(A)
    M = [row[:] for row in A]
    r = b[:]

    for col in range(n):
        max_val = abs(M[col][col])
        max_row = col
        for row in range(col + 1, n):
            if abs(M[row][col]) > max_val:
                max_val = abs(M[row][col])
                max_row = row
        if max_val < 1e-14:
            return None
        if max_row != col:
            M[col], M[max_row] = M[max_row], M[col]
            r[col], r[max_row] = r[max_row], r[col]
        pivot = M[col][col]
        for row in range(col + 1, n):
            factor = M[row][col] / pivot
            M[row][col] = factor
            for k in range(col + 1, n):
                M[row][k] -= factor * M[col][k]
            r[row] -= factor * r[col]

    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        s = r[i]
        for j in range(i + 1, n):
            s -= M[i][j] * x[j]
        x[i] = s / M[i][i]
    return x


# ---------------------------------------------------------------------------
# 3-D vector helpers (cross product, dot, norm)
# ---------------------------------------------------------------------------


def cross3(a: List[float], b: List[float]) -> List[float]:
    """Cross product of two 3-vectors (list or tuple)."""
    return [
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    ]


def dot3(a: List[float], b: List[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def norm3(v: List[float]) -> float:
    return math.sqrt(dot3(v, v))


# ---------------------------------------------------------------------------
# Quaternion helpers  (w, x, y, z)  — matches kerf_motion.body conventions
# ---------------------------------------------------------------------------


def quat_mul(p: Quat, q: Quat) -> Quat:
    """Hamilton product p ⊗ q."""
    pw, px, py, pz = p
    qw, qx, qy, qz = q
    return (
        pw * qw - px * qx - py * qy - pz * qz,
        pw * qx + px * qw + py * qz - pz * qy,
        pw * qy - px * qz + py * qw + pz * qx,
        pw * qz + px * qy - py * qx + pz * qw,
    )


def quat_norm(q: Quat) -> float:
    return math.sqrt(q[0] ** 2 + q[1] ** 2 + q[2] ** 2 + q[3] ** 2)


def quat_normalize(q: Quat) -> Quat:
    n = quat_norm(q)
    if n < 1e-300:
        return (1.0, 0.0, 0.0, 0.0)
    return (q[0] / n, q[1] / n, q[2] / n, q[3] / n)


def quat_to_rotmat(q: Quat) -> Mat3:
    """Convert unit quaternion to 3×3 rotation matrix (body→world)."""
    qw, qx, qy, qz = q
    return (
        (1 - 2 * (qy * qy + qz * qz),  2 * (qx * qy - qz * qw),       2 * (qx * qz + qy * qw)),
        (2 * (qx * qy + qz * qw),       1 - 2 * (qx * qx + qz * qz),   2 * (qy * qz - qx * qw)),
        (2 * (qx * qz - qy * qw),       2 * (qy * qz + qx * qw),       1 - 2 * (qx * qx + qy * qy)),
    )


# ---------------------------------------------------------------------------
# 4×4 homogeneous transform helpers (list-of-lists)
# ---------------------------------------------------------------------------


def identity4() -> _Mat4:
    """Return a 4×4 identity matrix."""
    return [
        [1.0, 0.0, 0.0, 0.0],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]


def mat4_mul(A: _Mat4, B: _Mat4) -> _Mat4:
    """Multiply two 4×4 matrices."""
    C = [[0.0] * 4 for _ in range(4)]
    for i in range(4):
        for j in range(4):
            s = 0.0
            for k in range(4):
                s += A[i][k] * B[k][j]
            C[i][j] = s
    return C


def mat4_col(T: _Mat4, j: int) -> List[float]:
    """Extract column j (0-indexed) from a 4×4 matrix as a list."""
    return [T[i][j] for i in range(4)]


# ---------------------------------------------------------------------------
# Determinant helpers
# ---------------------------------------------------------------------------


def _det3x3(m: List[List[float]]) -> float:
    """Determinant of a 3×3 matrix."""
    a, b, c = m[0], m[1], m[2]
    return (
        a[0] * (b[1] * c[2] - b[2] * c[1])
        - a[1] * (b[0] * c[2] - b[2] * c[0])
        + a[2] * (b[0] * c[1] - b[1] * c[0])
    )


def det_square(M: List[List[float]]) -> float:
    """Determinant of an n×n matrix via Gaussian elimination."""
    n = len(M)
    if n == 3:
        return _det3x3(M)
    A = [row[:] for row in M]
    det = 1.0
    for col in range(n):
        max_row = col
        max_val = abs(A[col][col])
        for row in range(col + 1, n):
            if abs(A[row][col]) > max_val:
                max_val = abs(A[row][col])
                max_row = row
        if max_row != col:
            A[col], A[max_row] = A[max_row], A[col]
            det *= -1.0
        pivot = A[col][col]
        if abs(pivot) < 1e-15:
            return 0.0
        det *= pivot
        for row in range(col + 1, n):
            factor = A[row][col] / pivot
            for k in range(col, n):
                A[row][k] -= factor * A[col][k]
    return det
