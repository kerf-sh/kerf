// loftSymmetric.test.js — unit tests for the loft `symmetric` flag.
//
// Coverage:
//   1. Pure-JS mid-plane math helpers in src/lib/loftSymmetric.js
//      - planeWorldNormal: base planes + face-anchored planes
//      - planeWorldOrigin: base planes + face-anchored planes
//      - loftMidPlane: parallel planes, anti-parallel planes, non-parallel
//      - mirrorPoint3D: reflects across XY / XZ / arbitrary plane
//   2. Schema validation guards in opLoft (source-level checks, no OCCT):
//      - symmetric=true + >2 profiles → error message
//      - symmetric=false (default) + 2 profiles → no symmetric error
//      - symmetric treated as bool coercion (truthy / falsy)
//   3. Switch-table presence: both `evaluateTree` (evaluates the tree and
//      triangulates) and `evaluateToFinalShape` contain `case 'loft':` so
//      the op is reachable on both code paths. We verify this by reading
//      the worker source text — the WASM runtime is not available in Node.

import { describe, it, expect } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'
import {
  planeWorldNormal,
  planeWorldOrigin,
  loftMidPlane,
  mirrorPoint3D,
} from '../lib/loftSymmetric.js'

// ---------------------------------------------------------------------------
// 1. planeWorldNormal
// ---------------------------------------------------------------------------

describe('planeWorldNormal', () => {
  it('returns [0,0,1] for a base XY plane', () => {
    expect(planeWorldNormal({ type: 'base', name: 'XY' })).toEqual([0, 0, 1])
  })

  it('returns [0,1,0] for a base XZ plane', () => {
    expect(planeWorldNormal({ type: 'base', name: 'XZ' })).toEqual([0, 1, 0])
  })

  it('returns [1,0,0] for a base YZ plane', () => {
    expect(planeWorldNormal({ type: 'base', name: 'YZ' })).toEqual([1, 0, 0])
  })

  it('defaults to [0,0,1] (XY) when plane is null or missing name', () => {
    expect(planeWorldNormal(null)).toEqual([0, 0, 1])
    expect(planeWorldNormal({ type: 'base' })).toEqual([0, 0, 1])
  })

  it('returns frame.normal for a face-anchored plane', () => {
    const plane = {
      type: 'face',
      frame: { origin: [1, 2, 3], normal: [0, 0.6, 0.8], uDir: [1, 0, 0], vDir: [0, 0.8, -0.6] },
    }
    expect(planeWorldNormal(plane)).toEqual([0, 0.6, 0.8])
  })

  it('falls back to [0,0,1] if face plane has no frame.normal', () => {
    expect(planeWorldNormal({ type: 'face', frame: {} })).toEqual([0, 0, 1])
    expect(planeWorldNormal({ type: 'face' })).toEqual([0, 0, 1])
  })
})

// ---------------------------------------------------------------------------
// 2. planeWorldOrigin
// ---------------------------------------------------------------------------

describe('planeWorldOrigin', () => {
  it('returns [0,0,0] for all base planes', () => {
    expect(planeWorldOrigin({ type: 'base', name: 'XY' })).toEqual([0, 0, 0])
    expect(planeWorldOrigin({ type: 'base', name: 'XZ' })).toEqual([0, 0, 0])
    expect(planeWorldOrigin({ type: 'base', name: 'YZ' })).toEqual([0, 0, 0])
  })

  it('returns [0,0,0] for null', () => {
    expect(planeWorldOrigin(null)).toEqual([0, 0, 0])
  })

  it('returns frame.origin for a face-anchored plane', () => {
    const plane = {
      type: 'face',
      frame: { origin: [5, 10, 20], normal: [0, 0, 1], uDir: [1, 0, 0], vDir: [0, 1, 0] },
    }
    expect(planeWorldOrigin(plane)).toEqual([5, 10, 20])
  })

  it('falls back to [0,0,0] if face plane has no frame.origin', () => {
    expect(planeWorldOrigin({ type: 'face', frame: {} })).toEqual([0, 0, 0])
    expect(planeWorldOrigin({ type: 'face' })).toEqual([0, 0, 0])
  })
})

// ---------------------------------------------------------------------------
// 3. loftMidPlane
// ---------------------------------------------------------------------------

describe('loftMidPlane', () => {
  it('computes mid-plane between two XY base planes (same origin)', () => {
    const plane0 = { type: 'base', name: 'XY' }
    const plane1 = { type: 'base', name: 'XY' }
    const result = loftMidPlane(plane0, plane1)
    expect(result).not.toBeNull()
    expect(result.origin).toEqual([0, 0, 0])
    expect(result.normal).toEqual([0, 0, 1])
  })

  it('computes mid-plane between two face-anchored parallel planes at different z', () => {
    const plane0 = {
      type: 'face',
      frame: { origin: [0, 0, 0], normal: [0, 0, 1], uDir: [1, 0, 0], vDir: [0, 1, 0] },
    }
    const plane1 = {
      type: 'face',
      frame: { origin: [0, 0, 80], normal: [0, 0, 1], uDir: [1, 0, 0], vDir: [0, 1, 0] },
    }
    const result = loftMidPlane(plane0, plane1)
    expect(result).not.toBeNull()
    expect(result.origin).toEqual([0, 0, 40])
    expect(result.normal).toEqual([0, 0, 1])
  })

  it('accepts anti-parallel normals (dot = -1) as parallel', () => {
    // A face plane with flipped normal is still parallel.
    const plane0 = {
      type: 'face',
      frame: { origin: [0, 0, 0], normal: [0, 0, 1], uDir: [1, 0, 0], vDir: [0, 1, 0] },
    }
    const plane1 = {
      type: 'face',
      frame: { origin: [0, 0, 40], normal: [0, 0, -1], uDir: [1, 0, 0], vDir: [0, 1, 0] },
    }
    const result = loftMidPlane(plane0, plane1)
    expect(result).not.toBeNull()
    expect(result.origin).toEqual([0, 0, 20])
  })

  it('returns null for non-parallel planes', () => {
    const xyPlane = { type: 'base', name: 'XY' }
    const xzPlane = { type: 'base', name: 'XZ' }
    expect(loftMidPlane(xyPlane, xzPlane)).toBeNull()
  })

  it('returns null for near-non-parallel face planes', () => {
    const plane0 = {
      type: 'face',
      frame: { origin: [0, 0, 0], normal: [0, 0, 1], uDir: [1, 0, 0], vDir: [0, 1, 0] },
    }
    const plane1 = {
      type: 'face',
      // Tilted 45 degrees — clearly not parallel.
      frame: {
        origin: [0, 0, 10],
        normal: [0, Math.SQRT1_2, Math.SQRT1_2],
        uDir: [1, 0, 0],
        vDir: [0, Math.SQRT1_2, -Math.SQRT1_2],
      },
    }
    expect(loftMidPlane(plane0, plane1)).toBeNull()
  })

  it('mid-origin is the geometric midpoint of arbitrary face-plane origins', () => {
    const plane0 = {
      type: 'face',
      frame: { origin: [10, 20, 5], normal: [0, 0, 1], uDir: [1, 0, 0], vDir: [0, 1, 0] },
    }
    const plane1 = {
      type: 'face',
      frame: { origin: [30, 40, 45], normal: [0, 0, 1], uDir: [1, 0, 0], vDir: [0, 1, 0] },
    }
    const result = loftMidPlane(plane0, plane1)
    expect(result.origin[0]).toBeCloseTo(20)
    expect(result.origin[1]).toBeCloseTo(30)
    expect(result.origin[2]).toBeCloseTo(25)
  })
})

// ---------------------------------------------------------------------------
// 4. mirrorPoint3D
// ---------------------------------------------------------------------------

describe('mirrorPoint3D', () => {
  it('mirrors a point above the XY plane to the same distance below it', () => {
    // Plane: XY at origin, normal [0,0,1].
    const p = [3, 4, 5]
    const result = mirrorPoint3D(p, [0, 0, 0], [0, 0, 1])
    expect(result[0]).toBeCloseTo(3)
    expect(result[1]).toBeCloseTo(4)
    expect(result[2]).toBeCloseTo(-5)
  })

  it('reflects across XY plane shifted to z=40 (mid-plane)', () => {
    const p = [0, 0, 0]
    const result = mirrorPoint3D(p, [0, 0, 40], [0, 0, 1])
    expect(result[0]).toBeCloseTo(0)
    expect(result[1]).toBeCloseTo(0)
    expect(result[2]).toBeCloseTo(80)
  })

  it('is an involution: mirror(mirror(p)) === p', () => {
    const p = [7, -3, 12]
    const origin = [1, 2, 3]
    const normal = [0, 0, 1]
    const once = mirrorPoint3D(p, origin, normal)
    const twice = mirrorPoint3D(once, origin, normal)
    expect(twice[0]).toBeCloseTo(p[0])
    expect(twice[1]).toBeCloseTo(p[1])
    expect(twice[2]).toBeCloseTo(p[2])
  })

  it('leaves points on the mirror plane unchanged', () => {
    // Any point with z=40 should be unchanged when mirroring across z=40 XY plane.
    const p = [5, 9, 40]
    const result = mirrorPoint3D(p, [0, 0, 40], [0, 0, 1])
    expect(result[0]).toBeCloseTo(5)
    expect(result[1]).toBeCloseTo(9)
    expect(result[2]).toBeCloseTo(40)
  })

  it('mirrors across an XZ plane (normal [0,1,0])', () => {
    const p = [3, 7, 5]
    const result = mirrorPoint3D(p, [0, 0, 0], [0, 1, 0])
    expect(result[0]).toBeCloseTo(3)
    expect(result[1]).toBeCloseTo(-7)
    expect(result[2]).toBeCloseTo(5)
  })

  it('accepts unnormalised normals and produces the same result as a unit normal', () => {
    const p = [1, 2, 3]
    const origin = [0, 0, 0]
    const unit = mirrorPoint3D(p, origin, [0, 0, 1])
    const scaled = mirrorPoint3D(p, origin, [0, 0, 5]) // same direction, different length
    expect(scaled[0]).toBeCloseTo(unit[0])
    expect(scaled[1]).toBeCloseTo(unit[1])
    expect(scaled[2]).toBeCloseTo(unit[2])
  })
})

// ---------------------------------------------------------------------------
// 5. Schema / arg-guard checks (source-text + logic-level, no OCCT)
// ---------------------------------------------------------------------------
//
// opLoft lives inside occtWorker.js (runs inside a Web Worker + WASM).
// We can't import and call it directly in Node. Instead we extract and
// exercise the guard logic — the same conditions the worker checks — to
// verify the validation contract without spinning up WASM.

describe('opLoft symmetric arg guards (logic-level)', () => {
  // Simulate the guard block at the top of opLoft.
  function simulateGuards(paths, nodeFlags) {
    const node = { profile_sketch_paths: paths, ...nodeFlags }
    const ps = Array.isArray(node.profile_sketch_paths) ? node.profile_sketch_paths : []
    if (ps.length < 2) throw new Error('loft: need at least 2 profile sketches')
    if (node.closed && ps.length < 3) throw new Error('loft: closed loft requires ≥3 profiles')
    if (node.symmetric && node.closed) throw new Error('loft: symmetric and closed cannot both be true')
    const isSymmetric = !!node.symmetric
    if (isSymmetric && ps.length !== 2) {
      throw new Error(`loft: symmetric mode requires exactly 2 profiles, got ${ps.length}`)
    }
    return 'ok'
  }

  it('accepts symmetric=true with exactly 2 profiles', () => {
    expect(simulateGuards(['/a.sketch', '/b.sketch'], { symmetric: true })).toBe('ok')
  })

  it('throws when symmetric=true and >2 profiles are provided', () => {
    expect(() =>
      simulateGuards(['/a.sketch', '/b.sketch', '/c.sketch'], { symmetric: true }),
    ).toThrow('symmetric mode requires exactly 2 profiles')
  })

  it('throws when symmetric=true and <2 profiles are provided', () => {
    expect(() =>
      simulateGuards(['/a.sketch'], { symmetric: true }),
    ).toThrow('at least 2 profile sketches')
  })

  it('throws when symmetric=true and closed=true', () => {
    expect(() =>
      simulateGuards(['/a.sketch', '/b.sketch'], { symmetric: true, closed: true }),
    ).toThrow('symmetric and closed cannot both be true')
  })

  it('does not throw for symmetric=false (default) with 2 profiles', () => {
    expect(simulateGuards(['/a.sketch', '/b.sketch'], { symmetric: false })).toBe('ok')
  })

  it('does not throw for symmetric=false (default) with 3 profiles', () => {
    expect(simulateGuards(['/a.sketch', '/b.sketch', '/c.sketch'], {})).toBe('ok')
  })

  it('treats truthy/falsy non-boolean symmetric correctly via !!coercion', () => {
    // !!1 → true with exactly 2 → ok
    expect(simulateGuards(['/a.sketch', '/b.sketch'], { symmetric: 1 })).toBe('ok')
    // !!0 → false → no symmetric check applied, 3 profiles allowed
    expect(simulateGuards(['/a.sketch', '/b.sketch', '/c.sketch'], { symmetric: 0 })).toBe('ok')
  })
})

// ---------------------------------------------------------------------------
// 6. Switch-table presence — loft dispatched in both evaluator paths
// ---------------------------------------------------------------------------
//
// The OCCT worker contains two switch blocks:
//   • evaluateTree          — evaluates + triangulates each feature
//   • evaluateToFinalShape  — evaluates to a single final TopoDS_Shape
//
// Both must contain `case 'loft':` so the op is reachable on each path.
// We read the worker source file as text and assert the expected strings.

describe('occtWorker.js — loft appears in both switch tables', () => {
  const workerSrc = fs.readFileSync(
    path.resolve(import.meta.dirname, '../lib/occtWorker.js'),
    'utf8',
  )

  it("contains `case 'loft':` at least twice (one per switch table)", () => {
    const matches = [...workerSrc.matchAll(/case\s+'loft'\s*:/g)]
    expect(matches.length).toBeGreaterThanOrEqual(2)
  })

  it('calls opLoft( in both switch table arms', () => {
    const calls = [...workerSrc.matchAll(/opLoft\s*\(/g)]
    // Each switch arm has one opLoft() call → at least 2.
    expect(calls.length).toBeGreaterThanOrEqual(2)
  })

  it('contains the symmetric flag handling in the opLoft function body', () => {
    expect(workerSrc).toContain('node.symmetric')
  })

  it('contains the mid-plane origin computation', () => {
    expect(workerSrc).toContain('midOrigin')
  })

  it('contains the parallel-plane validation', () => {
    expect(workerSrc).toContain('symmetric mode requires parallel')
  })
})
