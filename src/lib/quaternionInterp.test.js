// quaternionInterp.test.js — Vitest unit tests for quaternion arithmetic and slerp.
//
// All functions under test are pure JS — no Three.js dependency, no DOM.

import { describe, it, expect } from 'vitest'
import {
  slerp,
  qmul,
  qconj,
  qrotate,
  qangle,
  qnorm,
  qnormalize,
  qdot,
} from './quaternionInterp.js'

// ── Helpers ────────────────────────────────────────────────────────────────────

const I = { w: 1, x: 0, y: 0, z: 0 } // identity quaternion

function closeTo(a, b, eps = 1e-10) {
  return (
    Math.abs(a.w - b.w) < eps &&
    Math.abs(a.x - b.x) < eps &&
    Math.abs(a.y - b.y) < eps &&
    Math.abs(a.z - b.z) < eps
  )
}

// 90° rotation around Z axis
const Q_Z90 = qnormalize({ w: Math.cos(Math.PI / 4), x: 0, y: 0, z: Math.sin(Math.PI / 4) })

// 180° rotation around X axis
const Q_X180 = qnormalize({ w: 0, x: 1, y: 0, z: 0 })

// Arbitrary unit quaternion
const Q_ARB = qnormalize({ w: 0.5, x: 0.5, y: 0.5, z: 0.5 })

// ── 1. slerp boundary conditions ───────────────────────────────────────────────

describe('slerp boundary conditions', () => {
  it('slerp(I, q, 0) === I', () => {
    const result = slerp(I, Q_Z90, 0)
    expect(result.w).toBeCloseTo(I.w, 10)
    expect(result.x).toBeCloseTo(I.x, 10)
    expect(result.y).toBeCloseTo(I.y, 10)
    expect(result.z).toBeCloseTo(I.z, 10)
  })

  it('slerp(I, q, 1) === q (Z90)', () => {
    const result = slerp(I, Q_Z90, 1)
    expect(result.w).toBeCloseTo(Q_Z90.w, 10)
    expect(result.x).toBeCloseTo(Q_Z90.x, 10)
    expect(result.y).toBeCloseTo(Q_Z90.y, 10)
    expect(result.z).toBeCloseTo(Q_Z90.z, 10)
  })

  it('slerp(I, q, 1) === q (X180)', () => {
    const result = slerp(I, Q_X180, 1)
    // Both (0,1,0,0) and its negation represent the same rotation — accept both
    const pos = closeTo(result, Q_X180, 1e-10)
    const neg = closeTo(result, { w: -Q_X180.w, x: -Q_X180.x, y: -Q_X180.y, z: -Q_X180.z }, 1e-10)
    expect(pos || neg).toBe(true)
  })

  it('slerp(I, q, 1) === q (arbitrary)', () => {
    const result = slerp(I, Q_ARB, 1)
    expect(result.w).toBeCloseTo(Q_ARB.w, 10)
    expect(result.x).toBeCloseTo(Q_ARB.x, 10)
    expect(result.y).toBeCloseTo(Q_ARB.y, 10)
    expect(result.z).toBeCloseTo(Q_ARB.z, 10)
  })

  it('slerp midpoint has equal angular distance to both endpoints', () => {
    const mid = slerp(I, Q_Z90, 0.5)
    const d0 = qangle(I, mid)
    const d1 = qangle(mid, Q_Z90)
    expect(d0).toBeCloseTo(d1, 10)
  })
})

// ── 2. slerp produces unit quaternions ────────────────────────────────────────

describe('slerp output is always unit norm', () => {
  const ts = [0, 0.1, 0.25, 0.5, 0.75, 0.9, 1]
  for (const t of ts) {
    it(`|slerp(I, Q_ARB, ${t})| ≈ 1`, () => {
      const r = slerp(I, Q_ARB, t)
      expect(qnorm(r)).toBeCloseTo(1, 12)
    })
  }
})

// ── 3. slerp angular distance is monotonic in t ───────────────────────────────

describe('slerp angular distance is monotonic in t', () => {
  it('distance from start grows monotonically as t increases from 0 to 1', () => {
    const ts = [0, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9, 1]
    const angles = ts.map((t) => qangle(I, slerp(I, Q_Z90, t)))
    for (let i = 1; i < angles.length; i++) {
      expect(angles[i]).toBeGreaterThanOrEqual(angles[i - 1] - 1e-12)
    }
  })

  it('distance to end shrinks monotonically as t increases from 0 to 1', () => {
    const ts = [0, 0.1, 0.3, 0.5, 0.7, 0.9, 1]
    const angles = ts.map((t) => qangle(slerp(I, Q_Z90, t), Q_Z90))
    for (let i = 1; i < angles.length; i++) {
      expect(angles[i]).toBeLessThanOrEqual(angles[i - 1] + 1e-12)
    }
  })
})

// ── 4. qmul(q, qconj(q)) = I ──────────────────────────────────────────────────

describe('qmul(q, qconj(q)) = I', () => {
  const cases = [
    ['identity', I],
    ['Z90', Q_Z90],
    ['X180', Q_X180],
    ['arbitrary', Q_ARB],
  ]

  for (const [label, q] of cases) {
    it(`q * q* = I for ${label}`, () => {
      const r = qmul(q, qconj(q))
      expect(r.w).toBeCloseTo(1, 10)
      expect(r.x).toBeCloseTo(0, 10)
      expect(r.y).toBeCloseTo(0, 10)
      expect(r.z).toBeCloseTo(0, 10)
    })
  }
})

// ── 5. qrotate(I, v) = v ──────────────────────────────────────────────────────

describe('qrotate(I, v) = v', () => {
  const vectors = [
    [1, 0, 0],
    [0, 1, 0],
    [0, 0, 1],
    [1, 2, 3],
    [-4, 0.5, 7],
  ]

  for (const v of vectors) {
    it(`I rotates [${v}] to itself`, () => {
      const [rx, ry, rz] = qrotate(I, v)
      expect(rx).toBeCloseTo(v[0], 10)
      expect(ry).toBeCloseTo(v[1], 10)
      expect(rz).toBeCloseTo(v[2], 10)
    })
  }
})

// ── 6. qrotate correctness for known rotations ────────────────────────────────

describe('qrotate correctness', () => {
  it('Z90 rotates +X to +Y', () => {
    const [rx, ry, rz] = qrotate(Q_Z90, [1, 0, 0])
    expect(rx).toBeCloseTo(0, 10)
    expect(ry).toBeCloseTo(1, 10)
    expect(rz).toBeCloseTo(0, 10)
  })

  it('Z90 rotates +Y to -X', () => {
    const [rx, ry, rz] = qrotate(Q_Z90, [0, 1, 0])
    expect(rx).toBeCloseTo(-1, 10)
    expect(ry).toBeCloseTo(0, 10)
    expect(rz).toBeCloseTo(0, 10)
  })

  it('X180 rotates +Y to -Y', () => {
    const [rx, ry, rz] = qrotate(Q_X180, [0, 1, 0])
    expect(rx).toBeCloseTo(0, 10)
    expect(ry).toBeCloseTo(-1, 10)
    expect(rz).toBeCloseTo(0, 10)
  })

  it('X180 preserves the +X axis', () => {
    const [rx, ry, rz] = qrotate(Q_X180, [1, 0, 0])
    expect(rx).toBeCloseTo(1, 10)
    expect(ry).toBeCloseTo(0, 10)
    expect(rz).toBeCloseTo(0, 10)
  })
})

// ── 7. qmul associativity ─────────────────────────────────────────────────────

describe('qmul associativity', () => {
  it('(a*b)*c = a*(b*c)', () => {
    const a = Q_Z90
    const b = Q_ARB
    const c = Q_X180
    const lhs = qmul(qmul(a, b), c)
    const rhs = qmul(a, qmul(b, c))
    expect(lhs.w).toBeCloseTo(rhs.w, 10)
    expect(lhs.x).toBeCloseTo(rhs.x, 10)
    expect(lhs.y).toBeCloseTo(rhs.y, 10)
    expect(lhs.z).toBeCloseTo(rhs.z, 10)
  })
})

// ── 8. slerp handles identical quaternions (degenerate case) ──────────────────

describe('slerp degenerate: q0 === q1', () => {
  it('returns q when both endpoints are the same', () => {
    const result = slerp(Q_ARB, Q_ARB, 0.5)
    expect(result.w).toBeCloseTo(Q_ARB.w, 10)
    expect(result.x).toBeCloseTo(Q_ARB.x, 10)
    expect(result.y).toBeCloseTo(Q_ARB.y, 10)
    expect(result.z).toBeCloseTo(Q_ARB.z, 10)
  })
})

// ── 9. qdot / qangle ──────────────────────────────────────────────────────────

describe('qdot and qangle', () => {
  it('qdot(I, I) = 1', () => {
    expect(qdot(I, I)).toBeCloseTo(1, 12)
  })

  it('qangle(I, I) = 0', () => {
    expect(qangle(I, I)).toBeCloseTo(0, 12)
  })

  it('qangle(I, Q_Z90) ≈ π/2', () => {
    expect(qangle(I, Q_Z90)).toBeCloseTo(Math.PI / 2, 10)
  })
})
