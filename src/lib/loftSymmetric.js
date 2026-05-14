// loftSymmetric.js — pure-JS helpers for the symmetric loft mid-plane
// computation. These functions contain no OCCT calls so they can be unit-
// tested in Node/Vitest without the WASM runtime.
//
// The OCCT worker (opLoft) uses inlined equivalents of _loftPlaneNormal
// / _loftPlaneOrigin / _mirrorWireAcrossPlane; this module exists so the
// mid-plane math is separately testable without spinning up WASM.

/**
 * Return the world-space normal [x, y, z] for a sketch plane spec.
 *
 * @param {object|null} plane  – Kerf sketch plane object
 *   { type: 'base', name: 'XY'|'XZ'|'YZ' }
 *   { type: 'face', frame: { origin, normal, uDir, vDir } }
 * @returns {number[]} unit normal vector
 */
export function planeWorldNormal(plane) {
  if (plane && plane.type === 'face' && Array.isArray(plane.frame?.normal)) {
    return plane.frame.normal.slice()
  }
  const name = ((plane && plane.name) || 'XY').toUpperCase()
  if (name === 'XZ') return [0, 1, 0]
  if (name === 'YZ') return [1, 0, 0]
  return [0, 0, 1] // XY (default)
}

/**
 * Return the world-space origin [x, y, z] for a sketch plane spec.
 * Base planes (XY/XZ/YZ) always sit at the world origin in Kerf's model;
 * face-anchored planes carry their origin in `plane.frame.origin`.
 *
 * @param {object|null} plane
 * @returns {number[]}
 */
export function planeWorldOrigin(plane) {
  if (plane && plane.type === 'face' && Array.isArray(plane.frame?.origin)) {
    return plane.frame.origin.slice()
  }
  return [0, 0, 0]
}

/**
 * Compute the mid-plane between two parallel sketch planes.
 *
 * Returns `{ origin, normal }` in world space, or `null` if the planes are
 * not parallel (|dot| must be ≥ 1 − tolerance).
 *
 * @param {object} plane0  – first sketch plane spec
 * @param {object} plane1  – second sketch plane spec
 * @param {number} [tol=1e-4]  – parallelism tolerance on |dot(n0,n1)| − 1
 * @returns {{ origin: number[], normal: number[] } | null}
 */
export function loftMidPlane(plane0, plane1, tol = 1e-4) {
  const n0 = planeWorldNormal(plane0)
  const n1 = planeWorldNormal(plane1)
  const dot = n0[0] * n1[0] + n0[1] * n1[1] + n0[2] * n1[2]
  if (Math.abs(Math.abs(dot) - 1) > tol) return null

  const o0 = planeWorldOrigin(plane0)
  const o1 = planeWorldOrigin(plane1)
  const midOrigin = [
    (o0[0] + o1[0]) / 2,
    (o0[1] + o1[1]) / 2,
    (o0[2] + o1[2]) / 2,
  ]
  return { origin: midOrigin, normal: n0 }
}

/**
 * Mirror a 2D point [x, y] across a line through `lineOrigin` with the
 * given `lineDir` (both in 2D). Used for visualisation / unit-test
 * validation without needing OCCT.
 *
 * Formula: p' = 2(p·d̂)d̂ − p  (in the frame centred at lineOrigin)
 *
 * @param {number[]} p        – [x, y]
 * @param {number[]} lineOrigin – [ox, oy]
 * @param {number[]} lineDir    – [dx, dy] (need not be unit)
 * @returns {number[]} mirrored point
 */
export function mirrorPoint2D(p, lineOrigin, lineDir) {
  const rx = p[0] - lineOrigin[0]
  const ry = p[1] - lineOrigin[1]
  const len = Math.hypot(lineDir[0], lineDir[1]) || 1
  const dx = lineDir[0] / len
  const dy = lineDir[1] / len
  const dot2 = rx * dx + ry * dy
  const mx = 2 * dot2 * dx - rx
  const my = 2 * dot2 * dy - ry
  return [mx + lineOrigin[0], my + lineOrigin[1]]
}

/**
 * Mirror a 3D point [x, y, z] across a plane defined by `planeOrigin` and
 * `planeNormal`. Used for unit-test validation without OCCT.
 *
 * Formula: p' = p − 2 * ((p−o)·n̂) * n̂
 *
 * @param {number[]} p            – [x, y, z]
 * @param {number[]} planeOrigin  – [ox, oy, oz]
 * @param {number[]} planeNormal  – [nx, ny, nz] (need not be unit)
 * @returns {number[]} mirrored point
 */
export function mirrorPoint3D(p, planeOrigin, planeNormal) {
  const len = Math.hypot(...planeNormal) || 1
  const nx = planeNormal[0] / len
  const ny = planeNormal[1] / len
  const nz = planeNormal[2] / len
  const d = (p[0] - planeOrigin[0]) * nx +
            (p[1] - planeOrigin[1]) * ny +
            (p[2] - planeOrigin[2]) * nz
  return [
    p[0] - 2 * d * nx,
    p[1] - 2 * d * ny,
    p[2] - 2 * d * nz,
  ]
}
