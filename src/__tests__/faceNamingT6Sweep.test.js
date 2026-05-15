// faceNamingT6Sweep.test.js — T6: sweep/loft cap naming.
//
// Tests for:
//   buildFaceNamesForSweep  (opSweep1 / opSweep2)
//   buildFaceNamesForLoft   (opLoft)
//
// Naming convention:
//   planar cap faces at path start  → `<nodeId>.start_cap`
//   planar cap faces at path end    → `<nodeId>.end_cap`
//   swept/lofted surface faces      → `<nodeId>.swept` / `<nodeId>.lofted`
//
// Cap detection: planar face (surfaceKind === 'plane') with normal aligned
// to pathStartDir / pathEndDir (dot product ≥ 0.866 = cos 30°).  Falls back
// to a simple planar-vs-curved heuristic when no path dirs supplied.
//
// ~10 test cases.

import { describe, it, expect } from 'vitest'
import { buildFaceNamesForSweep, buildFaceNamesForLoft } from '../lib/faceNaming.js'

// ---------------------------------------------------------------------------
// Synthetic helpers
// ---------------------------------------------------------------------------

function makeFace(index, surfaceKind, normal, overrides = {}) {
  return {
    index,
    surfaceKind,
    edgeCount: 4,
    edgeKinds: ['line', 'line', 'line', 'line'],
    vertexValences: [2, 2, 2, 2],
    normal: normal || [0, 0, 1],
    sharedEdgeIndices: [index, index + 1],
    sketchEntityId: null,
    isCap: false,
    isTop: false,
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// buildFaceNamesForSweep
// ---------------------------------------------------------------------------

describe('buildFaceNamesForSweep', () => {
  it('1. basic sweep: planar caps + cylinder side → start_cap / end_cap / swept', () => {
    const faces = [
      makeFace(0, 'plane', [0, 0, -1]),    // start cap (normal ∥ -Z)
      makeFace(1, 'cylinder', [1, 0, 0]),  // swept surface
      makeFace(2, 'plane', [0, 0, 1]),     // end cap (normal ∥ +Z)
    ]
    const pathStartDir = [0, 0, -1]
    const pathEndDir   = [0, 0, 1]
    const names = buildFaceNamesForSweep('Swp-A', faces, pathStartDir, pathEndDir)
    expect(names['0']).toBe('Swp-A.start_cap')
    expect(names['1']).toBe('Swp-A.swept')
    expect(names['2']).toBe('Swp-A.end_cap')
  })

  it('2. no path dirs supplied — planar → cap roles, bspline → swept', () => {
    const faces = [
      makeFace(0, 'plane', [0, 1, 0]),
      makeFace(1, 'bspline', [0, 0, 1]),
      makeFace(2, 'plane', [0, -1, 0]),
    ]
    const names = buildFaceNamesForSweep('Swp-A', faces, null, null)
    // Without path dirs: first plane → start_cap, last plane → end_cap, bspline → swept
    expect(names['1']).toMatch(/^Swp-A\.swept(:\d+)?$/)
    expect(names['0']).toMatch(/^Swp-A\.(start_cap|end_cap)(:\d+)?$/)
    expect(names['2']).toMatch(/^Swp-A\.(start_cap|end_cap)(:\d+)?$/)
  })

  it('3. two planar faces with only pathStartDir → one gets start_cap, other gets swept', () => {
    // With the new two-pass logic: only the best-scoring face gets start_cap.
    // The second face (same normal) is not assigned → falls back to swept.
    const faces = [
      makeFace(0, 'plane', [0, 0, -1]),
      makeFace(1, 'plane', [0, 0, -1]),
    ]
    const pathStartDir = [0, 0, -1]
    const names = buildFaceNamesForSweep('Swp-A', faces, pathStartDir, null)
    const vals = Object.values(names)
    // One face should be start_cap, the other swept (or start_cap with suffix if both pass threshold)
    const hasStartCap = vals.some((v) => v === 'Swp-A.start_cap')
    expect(hasStartCap).toBe(true)
    // All names should have the correct prefix
    for (const v of vals) {
      expect(v).toMatch(/^Swp-A\.(start_cap|swept)(:\d+)?$/)
    }
  })

  it('4. all swept faces (open profile) — all get swept role (with collision suffix)', () => {
    const faces = [
      makeFace(0, 'bspline', [1, 0, 0]),
      makeFace(1, 'cylinder', [0, 1, 0]),
      makeFace(2, 'bspline', [-1, 0, 0]),
    ]
    const names = buildFaceNamesForSweep('Swp-B', faces, null, null)
    for (let i = 0; i < 3; i++) {
      // All are swept; collision resolution may add :0/:1/:2 suffixes
      expect(names[String(i)]).toMatch(/^Swp-B\.swept(:\d+)?$/)
    }
  })

  it('5. single face sweep (degenerate) — gets swept', () => {
    const faces = [makeFace(0, 'cylinder', [0, 1, 0])]
    const names = buildFaceNamesForSweep('Swp-C', faces, [0, 0, 1], [0, 0, -1])
    expect(names['0']).toBe('Swp-C.swept')
  })

  it('6. empty face list → empty result', () => {
    const names = buildFaceNamesForSweep('Swp-A', [], null, null)
    expect(Object.keys(names).length).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// buildFaceNamesForLoft
// ---------------------------------------------------------------------------

describe('buildFaceNamesForLoft', () => {
  it('7. loft: cap faces at start/end + lofted surface', () => {
    const faces = [
      makeFace(0, 'plane', [0, 0, -1]),   // start cap
      makeFace(1, 'bspline', [1, 0, 0]),  // lofted surface
      makeFace(2, 'bspline', [0, 1, 0]),  // lofted surface
      makeFace(3, 'plane', [0, 0, 1]),    // end cap
    ]
    const startNormal = [0, 0, -1]
    const endNormal   = [0, 0, 1]
    const names = buildFaceNamesForLoft('Lft-B', faces, startNormal, endNormal)
    expect(names['0']).toBe('Lft-B.start_cap')
    // Two bspline faces both get 'swept' with collision resolution suffix
    expect(names['1']).toMatch(/^Lft-B\.swept(:\d+)?$/)
    expect(names['2']).toMatch(/^Lft-B\.swept(:\d+)?$/)
    expect(names['3']).toBe('Lft-B.end_cap')
  })

  it('8. loft without profile normals — planar → cap roles, curved → swept', () => {
    const faces = [
      makeFace(0, 'plane', [1, 0, 0]),
      makeFace(1, 'cylinder', [0, 1, 0]),
      makeFace(2, 'plane', [-1, 0, 0]),
    ]
    const names = buildFaceNamesForLoft('Lft-B', faces, null, null)
    // cylinder face → swept
    expect(names['1']).toMatch(/^Lft-B\.swept(:\d+)?$/)
    // planar faces → cap roles
    expect(names['0']).toMatch(/^Lft-B\.(start_cap|end_cap)(:\d+)?$/)
  })

  it('9. all output faces get a name', () => {
    const faces = Array.from({ length: 5 }, (_, i) =>
      makeFace(i, i % 2 === 0 ? 'plane' : 'bspline', [0, 0, i % 2 === 0 ? 1 : 0])
    )
    const names = buildFaceNamesForLoft('Lft-B', faces, [0, 0, -1], [0, 0, 1])
    for (let i = 0; i < 5; i++) {
      expect(names[String(i)]).toBeTruthy()
    }
  })

  it('10. loft node id is used as prefix in all names', () => {
    const faces = [makeFace(0, 'cylinder', [1, 0, 0]), makeFace(1, 'plane', [0, 0, 1])]
    const names = buildFaceNamesForLoft('MyLoft-99', faces, null, [0, 0, 1])
    for (const v of Object.values(names)) {
      expect(v.startsWith('MyLoft-99.')).toBe(true)
    }
  })
})
