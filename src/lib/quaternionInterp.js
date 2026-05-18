// quaternionInterp.js — Pure-JS quaternion arithmetic and slerp.
//
// No Three.js dependencies. All functions are deterministic and stateless.
//
// Quaternion convention: { w, x, y, z } where w is the scalar part.

/**
 * qnorm — return the Euclidean norm of a quaternion.
 * @param {{ w: number, x: number, y: number, z: number }} q
 * @returns {number}
 */
export function qnorm(q) {
  return Math.sqrt(q.w * q.w + q.x * q.x + q.y * q.y + q.z * q.z)
}

/**
 * qnormalize — return a unit quaternion in the same direction as q.
 * @param {{ w: number, x: number, y: number, z: number }} q
 * @returns {{ w: number, x: number, y: number, z: number }}
 */
export function qnormalize(q) {
  const n = qnorm(q)
  if (n < 1e-14) return { w: 1, x: 0, y: 0, z: 0 }
  return { w: q.w / n, x: q.x / n, y: q.y / n, z: q.z / n }
}

/**
 * qconj — quaternion conjugate (i.e. inverse for unit quaternions).
 * @param {{ w: number, x: number, y: number, z: number }} q
 * @returns {{ w: number, x: number, y: number, z: number }}
 */
export function qconj(q) {
  return { w: q.w, x: -q.x, y: -q.y, z: -q.z }
}

/**
 * qmul — Hamilton product of two quaternions.
 * @param {{ w: number, x: number, y: number, z: number }} a
 * @param {{ w: number, x: number, y: number, z: number }} b
 * @returns {{ w: number, x: number, y: number, z: number }}
 */
export function qmul(a, b) {
  return {
    w: a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
    x: a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
    y: a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
    z: a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
  }
}

/**
 * qrotate — rotate a 3-vector v by unit quaternion q using the sandwich
 * product q * [0, v] * q*.
 * @param {{ w: number, x: number, y: number, z: number }} q  — unit quaternion
 * @param {[number, number, number]} v  — 3-vector [x, y, z]
 * @returns {[number, number, number]}
 */
export function qrotate(q, v) {
  const p = { w: 0, x: v[0], y: v[1], z: v[2] }
  const r = qmul(qmul(q, p), qconj(q))
  return [r.x, r.y, r.z]
}

/**
 * qdot — dot product of two quaternions (treated as 4-vectors).
 * @param {{ w: number, x: number, y: number, z: number }} a
 * @param {{ w: number, x: number, y: number, z: number }} b
 * @returns {number}
 */
export function qdot(a, b) {
  return a.w * b.w + a.x * b.x + a.y * b.y + a.z * b.z
}

/**
 * slerp — spherical linear interpolation between two unit quaternions.
 *
 * @param {{ w: number, x: number, y: number, z: number }} q0  — start attitude
 * @param {{ w: number, x: number, y: number, z: number }} q1  — end attitude
 * @param {number} t  — interpolation parameter in [0, 1]
 * @returns {{ w: number, x: number, y: number, z: number }}
 */
export function slerp(q0, q1, t) {
  // Ensure unit quaternions
  const a = qnormalize(q0)
  let b = qnormalize(q1)

  let dot = qdot(a, b)

  // If dot is negative, negate b to take the shorter arc on S^3.
  if (dot < 0) {
    b = { w: -b.w, x: -b.x, y: -b.y, z: -b.z }
    dot = -dot
  }

  // Clamp to avoid numerical issues with acos at edges.
  dot = Math.min(dot, 1)

  // When quaternions are very close, fall back to linear interpolation to
  // avoid division by sin(theta) ≈ 0.
  if (dot > 1 - 1e-10) {
    return qnormalize({
      w: a.w + t * (b.w - a.w),
      x: a.x + t * (b.x - a.x),
      y: a.y + t * (b.y - a.y),
      z: a.z + t * (b.z - a.z),
    })
  }

  const theta = Math.acos(dot)        // angle between the two quaternions
  const sinTheta = Math.sin(theta)

  const s0 = Math.sin((1 - t) * theta) / sinTheta
  const s1 = Math.sin(t * theta) / sinTheta

  return {
    w: s0 * a.w + s1 * b.w,
    x: s0 * a.x + s1 * b.x,
    y: s0 * a.y + s1 * b.y,
    z: s0 * a.z + s1 * b.z,
  }
}

/**
 * qangle — angular distance (in radians) between two unit quaternions.
 * Returns a value in [0, π].
 * @param {{ w: number, x: number, y: number, z: number }} a
 * @param {{ w: number, x: number, y: number, z: number }} b
 * @returns {number}
 */
export function qangle(a, b) {
  let dot = Math.abs(qdot(qnormalize(a), qnormalize(b)))
  dot = Math.min(dot, 1)
  return 2 * Math.acos(dot)
}
