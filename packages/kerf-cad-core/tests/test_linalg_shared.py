"""
test_linalg_shared.py — verify shared _linalg primitives and cross-module behavioral parity.

Coverage:
  L01  matvec correctness (hand-computed 3×3)
  L02  matmul correctness (hand-computed 2×3 @ 3×2)
  L03  transpose correctness
  L04  lu_solve exactness (2×2 known system)
  L05  lu_solve returns None for singular matrix
  L06  quaternion-to-rotation-matrix (identity quaternion → identity matrix)
  L07  quaternion-to-rotation-matrix (90° about z-axis)
  L08  quaternion multiply: q⊗q_inv = identity
  L09  quat_normalize idempotent on unit quaternion
  L10  4×4 compose/identity: T @ I == T
  L11  4×4 mat4_mul: known 45° rotation block
  L12  cross3 correctness (x×y = z)
  L13  det_square: 3×3 known determinant
  L14  det_square: singular → 0.0

Behavioral parity:
  P01  2-link arm FK via arm.fk_chain (unchanged public API, known end-effector position)
  P02  MBD free-fall: body y = -½g·t² after refactor (unchanged numerical result)
  P03  kerf_motion RigidBody state_derivatives unchanged (free-body torque-free spin)
"""
from __future__ import annotations

import math
import pytest

from kerf_cad_core._linalg import (
    matvec, matmul, transpose, lu_solve,
    quat_to_rotmat, quat_mul, quat_normalize, quat_norm,
    identity4, mat4_mul,
    cross3, dot3, norm3,
    det_square,
    zeros, eye,
)
from kerf_cad_core.robotics.arm import fk_chain
from kerf_cad_core.mbd.solver import Body, GravityForce, MBDSystem, simulate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _approx_matrix(A, B, tol=1e-12):
    """Assert two matrices (list-of-lists or tuples) are element-wise close."""
    for i, (ra, rb) in enumerate(zip(A, B)):
        for j, (a, b) in enumerate(zip(ra, rb)):
            assert abs(a - b) <= tol, (
                f"[{i}][{j}]: got {a}, expected {b}, diff={abs(a-b):.2e}"
            )


# ---------------------------------------------------------------------------
# L01 — matvec correctness
# ---------------------------------------------------------------------------

def test_L01_matvec():
    A = [[1.0, 2.0, 3.0],
         [4.0, 5.0, 6.0],
         [7.0, 8.0, 9.0]]
    x = [1.0, 0.0, -1.0]
    # hand: row0: 1-3=-2, row1: 4-6=-2, row2: 7-9=-2
    result = matvec(A, x)
    assert result == [-2.0, -2.0, -2.0]


# ---------------------------------------------------------------------------
# L02 — matmul correctness
# ---------------------------------------------------------------------------

def test_L02_matmul():
    A = [[1.0, 2.0, 3.0],
         [4.0, 5.0, 6.0]]
    B = [[7.0, 8.0],
         [9.0, 10.0],
         [11.0, 12.0]]
    C = matmul(A, B)
    # row0: [1*7+2*9+3*11, 1*8+2*10+3*12] = [58, 64]
    # row1: [4*7+5*9+6*11, 4*8+5*10+6*12] = [139, 154]
    assert C[0] == [58.0, 64.0]
    assert C[1] == [139.0, 154.0]


# ---------------------------------------------------------------------------
# L03 — transpose
# ---------------------------------------------------------------------------

def test_L03_transpose():
    A = [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]
    At = transpose(A)
    assert At == [[1.0, 3.0, 5.0], [2.0, 4.0, 6.0]]


# ---------------------------------------------------------------------------
# L04 — lu_solve exactness
# ---------------------------------------------------------------------------

def test_L04_lu_solve_2x2():
    A = [[2.0, 1.0], [5.0, 3.0]]
    b = [1.0, 2.0]
    x = lu_solve(A, b)
    assert x is not None
    assert abs(x[0] - 1.0) < 1e-12
    assert abs(x[1] - (-1.0)) < 1e-12


# ---------------------------------------------------------------------------
# L05 — lu_solve returns None for singular matrix
# ---------------------------------------------------------------------------

def test_L05_lu_solve_singular():
    A = [[1.0, 2.0], [2.0, 4.0]]
    b = [1.0, 2.0]
    x = lu_solve(A, b)
    assert x is None


# ---------------------------------------------------------------------------
# L06 — quat_to_rotmat: identity quaternion → identity matrix
# ---------------------------------------------------------------------------

def test_L06_quat_to_rotmat_identity():
    q = (1.0, 0.0, 0.0, 0.0)
    R = quat_to_rotmat(q)
    I3 = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))
    _approx_matrix(R, I3)


# ---------------------------------------------------------------------------
# L07 — quat_to_rotmat: 90° rotation about z-axis
# ---------------------------------------------------------------------------

def test_L07_quat_to_rotmat_90z():
    # q = (cos45°, 0, 0, sin45°)
    s = math.sqrt(2.0) / 2.0
    q = (s, 0.0, 0.0, s)
    R = quat_to_rotmat(q)
    # Expected: Rz(90°) = [[0,-1,0],[1,0,0],[0,0,1]]
    expected = (
        (0.0, -1.0, 0.0),
        (1.0,  0.0, 0.0),
        (0.0,  0.0, 1.0),
    )
    _approx_matrix(R, expected, tol=1e-10)


# ---------------------------------------------------------------------------
# L08 — quat_mul: q ⊗ q_conj ≈ identity
# ---------------------------------------------------------------------------

def test_L08_quat_mul_inverse():
    q = (0.5, 0.5, 0.5, 0.5)
    q = quat_normalize(q)
    q_conj = (q[0], -q[1], -q[2], -q[3])
    result = quat_mul(q, q_conj)
    assert abs(result[0] - 1.0) < 1e-14
    assert abs(result[1]) < 1e-14
    assert abs(result[2]) < 1e-14
    assert abs(result[3]) < 1e-14


# ---------------------------------------------------------------------------
# L09 — quat_normalize idempotent
# ---------------------------------------------------------------------------

def test_L09_quat_normalize_idempotent():
    q = (3.0, 1.0, -2.0, 0.5)
    qn = quat_normalize(q)
    assert abs(quat_norm(qn) - 1.0) < 1e-15
    qnn = quat_normalize(qn)
    for a, b in zip(qn, qnn):
        assert abs(a - b) < 1e-15


# ---------------------------------------------------------------------------
# L10 — mat4_mul: T @ identity4 == T
# ---------------------------------------------------------------------------

def test_L10_mat4_mul_identity():
    T = [
        [1.0, 0.0, 0.0, 3.0],
        [0.0, 1.0, 0.0, 4.0],
        [0.0, 0.0, 1.0, 5.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    result = mat4_mul(T, identity4())
    _approx_matrix(result, T)


# ---------------------------------------------------------------------------
# L11 — mat4_mul: known 45° rotation block
# ---------------------------------------------------------------------------

def test_L11_mat4_mul_rotation_block():
    c = math.cos(math.pi / 4)
    s = math.sin(math.pi / 4)
    Rz45 = [
        [ c, -s, 0.0, 0.0],
        [ s,  c, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    # Rz45 @ Rz45 = Rz90
    R90 = mat4_mul(Rz45, Rz45)
    assert abs(R90[0][0] - 0.0) < 1e-14
    assert abs(R90[0][1] - (-1.0)) < 1e-14
    assert abs(R90[1][0] - 1.0) < 1e-14
    assert abs(R90[1][1] - 0.0) < 1e-14


# ---------------------------------------------------------------------------
# L12 — cross3: x × y = z
# ---------------------------------------------------------------------------

def test_L12_cross3():
    x = [1.0, 0.0, 0.0]
    y = [0.0, 1.0, 0.0]
    z = cross3(x, y)
    assert abs(z[0] - 0.0) < 1e-15
    assert abs(z[1] - 0.0) < 1e-15
    assert abs(z[2] - 1.0) < 1e-15


# ---------------------------------------------------------------------------
# L13 — det_square: 3×3 known
# ---------------------------------------------------------------------------

def test_L13_det_square_3x3():
    # det([[1,2,3],[4,5,6],[7,8,10]]) = 1*(50-48) - 2*(40-42) + 3*(32-35) = 2+4-9 = -3
    M = [[1.0, 2.0, 3.0],
         [4.0, 5.0, 6.0],
         [7.0, 8.0, 10.0]]
    d = det_square(M)
    assert abs(d - (-3.0)) < 1e-12


# ---------------------------------------------------------------------------
# L14 — det_square: singular → 0.0
# ---------------------------------------------------------------------------

def test_L14_det_square_singular():
    M = [[1.0, 2.0], [2.0, 4.0]]
    d = det_square(M)
    assert d == 0.0


# ---------------------------------------------------------------------------
# P01 — 2-link arm FK: known end-effector position (behavioral parity)
# ---------------------------------------------------------------------------

def test_P01_2link_arm_fk():
    """
    2R planar arm, both links length 1.0, joints at 0°.
    End effector should be at (2, 0, 0).
    DH: a=1, alpha=0, d=0, theta_offset=0 for each link.
    """
    dh = [[1.0, 0.0, 0.0, 0.0],
          [1.0, 0.0, 0.0, 0.0]]
    angles = [0.0, 0.0]
    result = fk_chain(dh, angles)
    assert result["ok"] is True
    T = result["T"]
    assert abs(T[0][3] - 2.0) < 1e-12, f"x={T[0][3]}"
    assert abs(T[1][3] - 0.0) < 1e-12, f"y={T[1][3]}"
    assert abs(T[2][3] - 0.0) < 1e-12, f"z={T[2][3]}"

    # Now q1=90°: end effector should be at (0, 1+1, 0) = (0, 2, 0) ... actually
    # with DH link in plane: q1=90° → link1 goes along y, then q2=0 → link2 also along y
    angles2 = [math.pi / 2, 0.0]
    r2 = fk_chain(dh, angles2)
    assert r2["ok"] is True
    T2 = r2["T"]
    assert abs(T2[0][3] - 0.0) < 1e-12, f"x={T2[0][3]}"
    assert abs(T2[1][3] - 2.0) < 1e-12, f"y={T2[1][3]}"


# ---------------------------------------------------------------------------
# P02 — MBD free-fall: y = -½g·t² (behavioral parity after refactor)
# ---------------------------------------------------------------------------

def test_P02_mbd_free_fall_y():
    """Free body under gravity: y(t) = -½ g t², same as before refactor."""
    g = 9.80665
    sys = MBDSystem()
    b = sys.add_body(Body(mass=1.0, inertia=0.1))
    sys.add_force(GravityForce(gx=0.0, gy=-g))
    result = simulate(sys, t_end=0.5, dt=0.001)
    assert result["ok"] is True
    for q, t in zip(result["q"], result["t"]):
        if t < 0.01:
            continue
        y_mbd = q[3 * b + 1]
        y_exact = -0.5 * g * t ** 2
        err = abs(y_mbd - y_exact) / max(abs(y_exact), 1e-9)
        assert err < 0.01, f"Free fall error {err:.4f} at t={t:.3f}"


# ---------------------------------------------------------------------------
# P03 — kerf_motion RigidBody: torque-free spin conserves angular momentum
# ---------------------------------------------------------------------------

def test_P03_motion_rigidbody_torque_free_spin():
    """
    A torque-free spinning body should conserve |L| = |I·ω| in world frame.
    Uses kerf_motion.body directly (no kerf-cad-core dependency required).
    """
    from kerf_motion.body import RigidBody, mat3_vec, vec3_norm

    Ixx, Iyy, Izz = 1.0, 2.0, 3.0
    I_tensor = ((Ixx, 0.0, 0.0), (0.0, Iyy, 0.0), (0.0, 0.0, Izz))
    body = RigidBody(
        mass=1.0,
        inertia_tensor=I_tensor,
        angular_velocity=(1.0, 0.0, 0.0),  # spin about principal x-axis
    )

    # state_derivatives with zero force/torque
    derivs = body.state_derivatives((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    # domega = I_inv @ (tau - omega × I·omega) = I_inv @ (0 - (1,0,0)×(Ixx,0,0))
    # omega × I·omega = (1,0,0) × (1,0,0) = (0,0,0) for principal axis
    # → domega = 0 → spin is stable
    domega = derivs[10:13]
    assert abs(domega[0]) < 1e-12, f"domega_x={domega[0]}"
    assert abs(domega[1]) < 1e-12, f"domega_y={domega[1]}"
    assert abs(domega[2]) < 1e-12, f"domega_z={domega[2]}"
