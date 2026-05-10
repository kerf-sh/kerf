// Gumball pure-helper unit tests (Phase 4b).
//
// Covers the math the Gumball component pulls out as exported helpers so the
// React/three.js shell can stay un-tested at this level:
//
//   * averagePoints         — vertex averaging used to derive a face centroid
//                             when OCCT didn't supply one.
//   * computeFaceCentroid   — picks faceMeta.centroid first, falls back to
//                             averaging the face's expanded triangle verts.
//   * projectScreenDeltaToAxis — maps cursor pixel-deltas into world units
//                             along a world-axis projected to screen.
//   * angleBetweenScreenDeltas — radians between two cursor offsets relative
//                             to a rotation center, normalized to [-π, π].

import { describe, it, expect } from 'vitest'
import * as THREE from 'three'
import {
  averagePoints,
  computeFaceCentroid,
  projectScreenDeltaToAxis,
  angleBetweenScreenDeltas,
  projectScreenDeltaToRadialDistance,
  computeRadialBasis,
} from '../components/Gumball.jsx'

describe('Gumball helpers', () => {
  it('averagePoints averages componentwise and handles empty input', () => {
    expect(averagePoints([])).toEqual([0, 0, 0])
    const c = averagePoints([[0, 0, 0], [2, 4, 6]])
    expect(c).toEqual([1, 2, 3])
  })

  it('computeFaceCentroid prefers the OCCT-supplied centroid', () => {
    const part = {
      faceMeta: [
        { id: 7, centroid: [10, 20, 30] },
        { id: 8, centroid: [0, 0, 0] },
      ],
      // Triangle data also present; should be ignored when faceMeta has it.
      positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
      faceIdPerTri: new Uint32Array([7]),
    }
    expect(computeFaceCentroid(part, 7)).toEqual([10, 20, 30])
  })

  it('computeFaceCentroid falls back to averaging triangle vertices', () => {
    // Two triangles for face 5: (0,0,0)-(1,0,0)-(0,1,0) and (1,0,0)-(1,1,0)-(0,1,0).
    // Together their 6 vertices average to ((0+1+0+1+1+0)/6, (0+0+1+0+1+1)/6, 0)
    // = (3/6, 3/6, 0) = (0.5, 0.5, 0).
    const part = {
      faceMeta: [{ id: 5 /* no centroid field */ }],
      positions: new Float32Array([
        0, 0, 0, 1, 0, 0, 0, 1, 0,
        1, 0, 0, 1, 1, 0, 0, 1, 0,
      ]),
      faceIdPerTri: new Uint32Array([5, 5]),
    }
    const c = computeFaceCentroid(part, 5)
    expect(c[0]).toBeCloseTo(0.5, 6)
    expect(c[1]).toBeCloseTo(0.5, 6)
    expect(c[2]).toBeCloseTo(0, 6)
  })

  it('computeFaceCentroid returns null for unknown faces with no triangle hits', () => {
    const part = {
      faceMeta: [],
      positions: new Float32Array([0, 0, 0, 1, 0, 0, 0, 1, 0]),
      faceIdPerTri: new Uint32Array([0]),
    }
    expect(computeFaceCentroid(part, 99)).toBeNull()
  })

  it('projectScreenDeltaToAxis maps pixel-delta to world-axis units', () => {
    // Axis points horizontally to the right in screen space, span 100 pixels.
    // origin at (50,50), tip at (150,50). A 100-pixel rightward drag should
    // map to 1 world unit along the axis.
    const d = projectScreenDeltaToAxis(100, 0, [50, 50], [150, 50])
    expect(d).toBeCloseTo(1, 6)
    // Perpendicular drag → 0 (drag is along screen-Y, axis is along screen-X).
    const dPerp = projectScreenDeltaToAxis(0, 100, [50, 50], [150, 50])
    expect(dPerp).toBeCloseTo(0, 6)
    // Reverse: dragging left projects negative.
    const dRev = projectScreenDeltaToAxis(-50, 0, [50, 50], [150, 50])
    expect(dRev).toBeCloseTo(-0.5, 6)
  })

  it('projectScreenDeltaToAxis returns 0 for a degenerate axis', () => {
    expect(projectScreenDeltaToAxis(20, 30, [0, 0], [0, 0])).toBe(0)
  })

  it('angleBetweenScreenDeltas returns signed radians', () => {
    // Start at (1,0), end at (0,1) → +90° = +π/2.
    expect(angleBetweenScreenDeltas(1, 0, 0, 1)).toBeCloseTo(Math.PI / 2, 6)
    // Start at (1,0), end at (0,-1) → -90° = -π/2.
    expect(angleBetweenScreenDeltas(1, 0, 0, -1)).toBeCloseTo(-Math.PI / 2, 6)
    // No movement → 0.
    expect(angleBetweenScreenDeltas(1, 0, 1, 0)).toBeCloseTo(0, 6)
  })
})

// Camera helper: build a perspective camera looking at the world origin from
// `+Z` so the world XY plane projects 1:1 (modulo perspective) onto the
// viewport. We update its matrices manually since there's no render loop.
function makeCamera({ pos = [0, 0, 10], target = [0, 0, 0], aspect = 1, w = 800, h = 800 } = {}) {
  const cam = new THREE.PerspectiveCamera(45, aspect, 0.1, 1000)
  cam.position.set(pos[0], pos[1], pos[2])
  cam.lookAt(target[0], target[1], target[2])
  cam.updateMatrixWorld(true)
  cam.updateProjectionMatrix()
  return { cam, w, h }
}

describe('projectScreenDeltaToRadialDistance', () => {
  it('returns 0 for a zero pixel-delta', () => {
    const { cam, w, h } = makeCamera()
    const r = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 1, 0], cam, 0, 0, w, h)
    expect(r).toBe(0)
  })

  it('matches the analytically-derived radius for cursor moves along the radial axis', () => {
    // Edge axis = +Y, camera looking down -Z from (0,0,10). The helper picks
    // radial = normalize(cross(axis, cameraForward)) = cross(+Y, -Z) = -X. Its
    // screen basis is (tipPx - midPx) where tip = mid + radial = (-1,0,0).
    // We drive the drag along that *same* screen-direction so the dot product
    // is positive and the resulting radius is +1 world unit.
    const { cam, w, h } = makeCamera()
    const mid = new THREE.Vector3(0, 0, 0).project(cam)
    const tip = new THREE.Vector3(-1, 0, 0).project(cam)
    const midPx = [(mid.x * 0.5 + 0.5) * w, (-mid.y * 0.5 + 0.5) * h]
    const tipPx = [(tip.x * 0.5 + 0.5) * w, (-tip.y * 0.5 + 0.5) * h]
    const dxPx = tipPx[0] - midPx[0]
    const dyPx = tipPx[1] - midPx[1]
    const r = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 1, 0], cam, dxPx, dyPx, w, h)
    expect(r).toBeCloseTo(1, 3)
  })

  it('clamps negative results (radius cannot be negative)', () => {
    const { cam, w, h } = makeCamera()
    // Drag opposite the helper's basis direction (which points along screen
    // -X for an edge along +Y under our camera) → negative scalar → clamped 0.
    const r = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 1, 0], cam, +150, 0, w, h)
    expect(r).toBe(0)
  })

  it('scales linearly with pixel delta (twice the drag → twice the radius)', () => {
    const { cam, w, h } = makeCamera()
    // Drag along the helper's positive basis direction (-screen-X for our
    // setup) so we get strictly positive radii.
    const r1 = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 1, 0], cam, -100, 0, w, h)
    const r2 = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 1, 0], cam, -200, 0, w, h)
    const r4 = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 1, 0], cam, -400, 0, w, h)
    expect(r1).toBeGreaterThan(0)
    expect(r2 / r1).toBeCloseTo(2, 3)
    expect(r4 / r1).toBeCloseTo(4, 3)
  })

  it('handles an edge parallel to the camera-forward axis without throwing', () => {
    // Camera at +Z looking at origin → forward = -Z. Edge axis = (0,0,1) is
    // parallel to the camera axis, so cross(axis, fwd) is degenerate. The
    // helper must fall back to cross-with-camera-up and produce a finite,
    // non-negative result.
    const { cam, w, h } = makeCamera()
    let result
    expect(() => {
      result = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 0, 1], cam, 50, 0, w, h)
    }).not.toThrow()
    expect(Number.isFinite(result)).toBe(true)
    expect(result).toBeGreaterThanOrEqual(0)
  })

  it('returns 0 for a degenerate (zero-length) edge axis', () => {
    const { cam, w, h } = makeCamera()
    const r = projectScreenDeltaToRadialDistance([0, 0, 0], [0, 0, 0], cam, 100, 50, w, h)
    expect(r).toBe(0)
  })
})

describe('computeRadialBasis', () => {
  it('picks a unit vector perpendicular to both the edge axis and camera forward', () => {
    const { cam } = makeCamera()
    const r = computeRadialBasis([0, 1, 0], cam)
    expect(r).not.toBeNull()
    // Camera forward is -Z, edge axis is +Y → cross(+Y, -Z) = -X. Result is
    // unit length and orthogonal to the edge axis.
    expect(r.length()).toBeCloseTo(1, 6)
    expect(r.dot(new THREE.Vector3(0, 1, 0))).toBeCloseTo(0, 6)
  })

  it('returns null for a degenerate edge axis', () => {
    const { cam } = makeCamera()
    expect(computeRadialBasis([0, 0, 0], cam)).toBeNull()
  })

  it('falls back to camera-up when the edge is parallel to camera forward', () => {
    const { cam } = makeCamera()
    // Edge axis = +Z, camera forward = -Z → cross is degenerate, fall back.
    const r = computeRadialBasis([0, 0, 1], cam)
    expect(r).not.toBeNull()
    expect(r.length()).toBeCloseTo(1, 6)
    // Still orthogonal to the edge axis.
    expect(r.dot(new THREE.Vector3(0, 0, 1))).toBeCloseTo(0, 6)
  })

  it('rotates with the camera (re-derives basis given a fresh camera state)', () => {
    // Same edge axis, two different camera positions → different bases.
    const a = makeCamera({ pos: [0, 0, 10] })
    const b = makeCamera({ pos: [10, 0, 0] })
    const ra = computeRadialBasis([0, 1, 0], a.cam)
    const rb = computeRadialBasis([0, 1, 0], b.cam)
    expect(ra).not.toBeNull()
    expect(rb).not.toBeNull()
    // Distinct camera states → distinct radial vectors.
    const dot = ra.dot(rb)
    expect(Math.abs(dot)).toBeLessThan(0.99)
  })
})
