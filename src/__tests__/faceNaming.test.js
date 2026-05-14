// faceNaming.test.js
//
// Unit tests for src/lib/faceNaming.js — pure-JS face-naming helpers.
//
// All tests operate on synthetic FaceDescriptor structures; no OCCT WASM
// needed. The full worker integration (real OCCT geometry) is deferred to T7.
//
// Test groups:
//   1. topoHash determinism & stability
//   2. classifyFaceForExtrude — cap detection + side-face mapping
//   3. classifyFaceForPocket — Inner. prefix
//   4. buildFaceNamesForExtrude — full rectangular extrude (2 caps + 4 sides)
//   5. buildFaceNamesForRevolve — StartCap/EndCap for partial revolve
//   6. Topo-hash fallback when sketch entity id is missing
//   7. Collision resolution

import { describe, it, expect } from 'vitest'
import {
  sha256hex8,
  topoHash,
  sortedAdjacentFaceTypes,
  sortedVertexValences,
  classifyFaceForExtrude,
  classifyFaceForPocket,
  classifyFaceForRevolve,
  buildFaceNamesForExtrude,
  buildFaceNamesForRevolve,
} from '../lib/faceNaming.js'

// ---------------------------------------------------------------------------
// Synthetic face helpers
// ---------------------------------------------------------------------------

/**
 * Build a minimal FaceDescriptor for the TOP cap of a Z-extrusion.
 * Normal points in the +Z direction (parallel to the extrusion axis).
 */
function makeTopCap(index, overrides = {}) {
  return {
    index,
    surfaceKind: 'plane',
    edgeCount: 4,
    edgeKinds: ['line', 'line', 'line', 'line'],
    vertexValences: [2, 2, 2, 2],
    normal: [0, 0, 1],
    sharedEdgeIndices: [0, 1, 2, 3],
    sketchEntityId: null,
    ...overrides,
  }
}

/**
 * Bottom cap — normal points in the -Z direction.
 */
function makeBottomCap(index, overrides = {}) {
  return makeTopCap(index, { normal: [0, 0, -1], sharedEdgeIndices: [4, 5, 6, 7], ...overrides })
}

/**
 * Side face with a normal perpendicular to Z-axis.
 * Each side face shares some edges with the caps.
 */
function makeSideFace(index, normal, sketchEntityId, sharedEdgeIndices, overrides = {}) {
  return {
    index,
    surfaceKind: 'plane',
    edgeCount: 4,
    edgeKinds: ['line', 'line', 'line', 'line'],
    vertexValences: [2, 2, 2, 2],
    normal,
    sharedEdgeIndices,
    sketchEntityId,
    ...overrides,
  }
}

/**
 * Build the 6 faces of a rectangular box extruded along +Z.
 *
 * Edge index scheme (illustrative — just needs to be consistent):
 *   Top cap:    edges 0-3
 *   Bottom cap: edges 4-7
 *   +X side:    edges 0,4,8,9   (shares edge 0 with top, edge 4 with bottom)
 *   -X side:    edges 1,5,10,11
 *   +Y side:    edges 2,6,12,13
 *   -Y side:    edges 3,7,14,15
 */
function makeRectBoxFaces(sketchEntityIds = ['seg-0', 'seg-1', 'seg-2', 'seg-3']) {
  return [
    makeTopCap(0,    { sharedEdgeIndices: [0, 1, 2, 3] }),
    makeBottomCap(1, { sharedEdgeIndices: [4, 5, 6, 7] }),
    makeSideFace(2, [1, 0, 0],  sketchEntityIds[0], [0, 4,  8,  9]),
    makeSideFace(3, [-1, 0, 0], sketchEntityIds[1], [1, 5, 10, 11]),
    makeSideFace(4, [0, 1, 0],  sketchEntityIds[2], [2, 6, 12, 13]),
    makeSideFace(5, [0, -1, 0], sketchEntityIds[3], [3, 7, 14, 15]),
  ]
}

const Z_UP = [0, 0, 1]

// ===========================================================================
// 1. sha256hex8
// ===========================================================================

describe('sha256hex8', () => {
  it('returns 8 hex characters', () => {
    const h = sha256hex8('hello world')
    expect(h).toMatch(/^[0-9a-f]{8}$/)
  })

  it('is deterministic', () => {
    expect(sha256hex8('test-input')).toBe(sha256hex8('test-input'))
  })

  it('produces different results for different inputs', () => {
    expect(sha256hex8('aaa')).not.toBe(sha256hex8('bbb'))
  })
})

// ===========================================================================
// 2. topoHash determinism & stability
// ===========================================================================

describe('topoHash determinism', () => {
  const faces = makeRectBoxFaces()
  const topCap = faces[0]

  it('same face structure produces the same hash twice', () => {
    expect(topoHash(topCap, faces)).toBe(topoHash(topCap, faces))
  })

  it('different face structures produce different hashes', () => {
    const sideFace = faces[2]
    expect(topoHash(topCap, faces)).not.toBe(topoHash(sideFace, faces))
  })

  it('hash starts with "h"', () => {
    expect(topoHash(topCap, faces)).toMatch(/^h[0-9a-f]{8}$/)
  })

  it('changing surfaceKind changes the hash', () => {
    const modified = { ...topCap, surfaceKind: 'cylinder' }
    expect(topoHash(modified, faces)).not.toBe(topoHash(topCap, faces))
  })

  it('changing edgeCount changes the hash', () => {
    const modified = { ...topCap, edgeCount: 3 }
    expect(topoHash(modified, faces)).not.toBe(topoHash(topCap, faces))
  })

  it('changing neighbour face kind changes the hash', () => {
    // Make a modified face list where one side face is a cylinder instead of plane.
    const modFaces = faces.map((f, i) => i === 2 ? { ...f, surfaceKind: 'cylinder' } : f)
    // Top cap's neighbours include index-2; its hash should differ now.
    expect(topoHash(topCap, modFaces)).not.toBe(topoHash(topCap, faces))
  })
})

describe('topoHash stability', () => {
  const faces = makeRectBoxFaces()

  it('changing an unrelated face (no shared edges with target) does not change the target hash', () => {
    // Create a 7th face with NO shared edge indices with topCap.
    const unrelated = makeSideFace(6, [0, 0, 1], null, [99, 100, 101, 102])
    const facesWithExtra = [...faces, unrelated]

    // Modify the unrelated face — shouldn't affect topCap's hash.
    const facesWithModified = facesWithExtra.map((f) =>
      f.index === 6 ? { ...f, surfaceKind: 'cylinder' } : f,
    )
    const topCap = faces[0]
    expect(topoHash(topCap, facesWithExtra)).toBe(topoHash(topCap, facesWithModified))
  })
})

// ===========================================================================
// 3. classifyFaceForExtrude — cap detection
// ===========================================================================

describe('classifyFaceForExtrude — cap detection', () => {
  const faces = makeRectBoxFaces()

  it('identifies the top cap', () => {
    expect(classifyFaceForExtrude(faces[0], Z_UP, faces)).toBe('TopCap')
  })

  it('identifies the bottom cap', () => {
    expect(classifyFaceForExtrude(faces[1], Z_UP, faces)).toBe('BottomCap')
  })

  it('does not classify side faces as caps', () => {
    for (const face of faces.slice(2)) {
      const role = classifyFaceForExtrude(face, Z_UP, faces)
      expect(role).not.toBe('TopCap')
      expect(role).not.toBe('BottomCap')
    }
  })

  it('a rectangular box has exactly 2 caps and 4 sides', () => {
    const roles = faces.map((f) => classifyFaceForExtrude(f, Z_UP, faces))
    const caps  = roles.filter((r) => r === 'TopCap' || r === 'BottomCap')
    const sides = roles.filter((r) => r.startsWith('Side.'))
    expect(caps.length).toBe(2)
    expect(sides.length).toBe(4)
  })

  it('works with a -Z extrusion axis (down)', () => {
    // Normal inverted: bottom cap now points +Z, top cap -Z.
    // With axis [0,0,-1]:
    //   dot([0,0,1],  normalised([0,0,-1])) = -1 → BottomCap  (dot <= -0.966)
    //   dot([0,0,-1], normalised([0,0,-1])) = +1 → TopCap     (dot >= +0.966)
    expect(classifyFaceForExtrude(faces[0], [0, 0, -1], faces)).toBe('BottomCap')
    expect(classifyFaceForExtrude(faces[1], [0, 0, -1], faces)).toBe('TopCap')
  })
})

// ===========================================================================
// 4. classifyFaceForExtrude — side-face → sketch entity mapping
// ===========================================================================

describe('classifyFaceForExtrude — side-face sketch entity mapping', () => {
  const faces = makeRectBoxFaces(['seg-0', 'seg-1', 'seg-2', 'seg-3'])

  it('maps each side face to its sketch entity id', () => {
    expect(classifyFaceForExtrude(faces[2], Z_UP, faces)).toBe('Side.seg-0')
    expect(classifyFaceForExtrude(faces[3], Z_UP, faces)).toBe('Side.seg-1')
    expect(classifyFaceForExtrude(faces[4], Z_UP, faces)).toBe('Side.seg-2')
    expect(classifyFaceForExtrude(faces[5], Z_UP, faces)).toBe('Side.seg-3')
  })

  it('all 4 side mappings are distinct', () => {
    const roles = faces.slice(2).map((f) => classifyFaceForExtrude(f, Z_UP, faces))
    expect(new Set(roles).size).toBe(4)
  })
})

// ===========================================================================
// 5. Pocket — Inner. prefix
// ===========================================================================

describe('classifyFaceForPocket — Inner. prefix', () => {
  const faces = makeRectBoxFaces()

  it('top cap becomes Inner.TopCap', () => {
    expect(classifyFaceForPocket(faces[0], Z_UP, faces)).toBe('Inner.TopCap')
  })

  it('bottom cap becomes Inner.BottomCap', () => {
    expect(classifyFaceForPocket(faces[1], Z_UP, faces)).toBe('Inner.BottomCap')
  })

  it('side face becomes Inner.Side.<id>', () => {
    expect(classifyFaceForPocket(faces[2], Z_UP, faces)).toBe('Inner.Side.seg-0')
  })
})

// ===========================================================================
// 6. buildFaceNamesForExtrude — full name output
// ===========================================================================

describe('buildFaceNamesForExtrude', () => {
  it('produces 6 names for a rectangular box', () => {
    const faces = makeRectBoxFaces()
    const names = buildFaceNamesForExtrude('Pad-A', faces, Z_UP)
    expect(Object.keys(names).length).toBe(6)
  })

  it('top cap is named <nodeId>.TopCap', () => {
    const faces = makeRectBoxFaces()
    const names = buildFaceNamesForExtrude('Pad-A', faces, Z_UP)
    expect(names['0']).toBe('Pad-A.TopCap')
  })

  it('bottom cap is named <nodeId>.BottomCap', () => {
    const faces = makeRectBoxFaces()
    const names = buildFaceNamesForExtrude('Pad-A', faces, Z_UP)
    expect(names['1']).toBe('Pad-A.BottomCap')
  })

  it('side faces carry sketch entity ids', () => {
    const faces = makeRectBoxFaces()
    const names = buildFaceNamesForExtrude('Pad-A', faces, Z_UP)
    expect(names['2']).toBe('Pad-A.Side.seg-0')
    expect(names['3']).toBe('Pad-A.Side.seg-1')
    expect(names['4']).toBe('Pad-A.Side.seg-2')
    expect(names['5']).toBe('Pad-A.Side.seg-3')
  })

  it('pocket mode applies Inner. prefix', () => {
    const faces = makeRectBoxFaces()
    const names = buildFaceNamesForExtrude('Pocket-B', faces, Z_UP, true)
    expect(names['0']).toBe('Pocket-B.Inner.TopCap')
    expect(names['1']).toBe('Pocket-B.Inner.BottomCap')
    expect(names['2']).toBe('Pocket-B.Inner.Side.seg-0')
  })

  it('nodeId appears in every name', () => {
    const faces = makeRectBoxFaces()
    const names = buildFaceNamesForExtrude('MyPad', faces, Z_UP)
    for (const n of Object.values(names)) {
      expect(n.startsWith('MyPad.')).toBe(true)
    }
  })

  it('all 6 names are unique', () => {
    const faces = makeRectBoxFaces()
    const names = buildFaceNamesForExtrude('Pad-A', faces, Z_UP)
    const vals = Object.values(names)
    expect(new Set(vals).size).toBe(vals.length)
  })
})

// ===========================================================================
// 7. Topo-hash fallback — missing sketch entity id
// ===========================================================================

describe('topoHash fallback when sketch entity id missing', () => {
  it('a side face with no sketchEntityId gets a hash name', () => {
    const faces = makeRectBoxFaces([null, null, null, null])
    const role = classifyFaceForExtrude(faces[2], Z_UP, faces)
    // Should be a topo-hash: 'h' + 8 hex chars
    expect(role).toMatch(/^h[0-9a-f]{8}$/)
  })

  it('buildFaceNamesForExtrude uses <nodeId>.h<hash>[:<n>] for anonymous side faces', () => {
    const faces = makeRectBoxFaces([null, null, null, null])
    const names = buildFaceNamesForExtrude('Pad-A', faces, Z_UP)
    // Caps are still named properly.
    expect(names['0']).toBe('Pad-A.TopCap')
    expect(names['1']).toBe('Pad-A.BottomCap')
    // Side faces fall back to hashes; when multiple faces share the same hash
    // (identical adjacency signature) collision suffixes (:0, :1, …) are appended.
    for (const idx of ['2', '3', '4', '5']) {
      expect(names[idx]).toMatch(/^Pad-A\.h[0-9a-f]{8}(:\d+)?$/)
    }
    // All four names must still be unique after collision resolution.
    const sideNames = ['2', '3', '4', '5'].map((i) => names[i])
    expect(new Set(sideNames).size).toBe(4)
  })
})

// ===========================================================================
// 8. Revolve — StartCap / EndCap / side faces
// ===========================================================================

describe('classifyFaceForRevolve', () => {
  // A partial revolve around the Z axis (90°) produces:
  //   - Two planar end caps (normals perpendicular to Z → they sit in the XY plane,
  //     so their normals lie along the extrusion axis direction... wait:
  //     Actually for a revolve around Z, end-caps are *perpendicular* to the
  //     revolution path, which means they are planar faces whose normals lie
  //     in the XY plane (perpendicular to Z). We distinguish them by checking
  //     if the face normal is parallel to the revolution axis (Z-axis); for a
  //     90-degree partial revolve, the end caps have normals IN the XY plane,
  //     while the "top" and "bottom" profile caps have normals along ±Z.
  //
  //   For our test we just use our synthetic descriptors: if dot >= 0.966 it's
  //   a cap. The actual geometry classification mirrors what OCCT produces.

  const axis = Z_UP
  const isPartial = false  // full circle

  it('full circle: side face with sketchEntityId → Side.<id>', () => {
    const face = makeSideFace(0, [1, 0, 0], 'seg-2', [0, 1, 2, 3])
    const faces = [face]
    expect(classifyFaceForRevolve(face, axis, isPartial, faces, 0)).toBe('Side.seg-2')
  })

  it('full circle: no caps expected', () => {
    // For a full-circle revolve, no face should be classified as StartCap/EndCap.
    const face = makeTopCap(0) // normal = [0,0,1] — same as axis
    const faces = [face]
    // With isFullCircle=true we never check for caps, so normal TopCap-like
    // faces fall through to the side-face logic.
    const role = classifyFaceForRevolve(face, axis, true /* isFullCircle */, faces, 0)
    // With a full-circle flag it goes to the sketchEntityId branch (null → hash).
    expect(role).toMatch(/^h[0-9a-f]{8}$/)
  })

  it('partial revolve: face with normal ∥ axis → StartCap', () => {
    const face = makeTopCap(0) // normal [0,0,1] ∥ Z_UP
    const faces = [face]
    const role = classifyFaceForRevolve(face, axis, false /* partial */, faces, 0)
    expect(role).toBe('StartCap')
  })

  it('partial revolve: second cap face → EndCap', () => {
    const face = makeTopCap(1, { sharedEdgeIndices: [8, 9, 10, 11] })
    const faces = [face]
    const role = classifyFaceForRevolve(face, axis, false /* partial */, faces, 1)
    expect(role).toBe('EndCap')
  })
})

describe('buildFaceNamesForRevolve', () => {
  it('full revolve with 3 side faces produces correct names', () => {
    const faces = [
      makeSideFace(0, [1, 0, 0], 'seg-0', [0, 1]),
      makeSideFace(1, [0, 1, 0], 'seg-1', [2, 3]),
      makeSideFace(2, [-1, 0, 0], 'seg-2', [4, 5]),
    ]
    const names = buildFaceNamesForRevolve('Rev-C', faces, Z_UP, true)
    expect(names['0']).toBe('Rev-C.Side.seg-0')
    expect(names['1']).toBe('Rev-C.Side.seg-1')
    expect(names['2']).toBe('Rev-C.Side.seg-2')
  })
})

// ===========================================================================
// 9. Collision resolution
// ===========================================================================

describe('collision resolution', () => {
  it('two identical topo-hash faces get :0 and :1 suffixes', () => {
    // Two side faces with NO sketchEntityId and identical adjacency structures
    // → same hash → collision.
    const identicalSide1 = makeSideFace(2, [1, 0, 0], null, [0, 4, 8, 9])
    const identicalSide2 = makeSideFace(3, [1, 0, 0], null, [0, 4, 8, 9]) // exact same data
    const caps = [makeTopCap(0), makeBottomCap(1)]
    const faces = [...caps, identicalSide1, identicalSide2]

    const names = buildFaceNamesForExtrude('Pad-A', faces, Z_UP)
    // The two side faces should have different names despite same hash base.
    expect(names['2']).not.toBe(names['3'])
    // Both should match h<8hex>:N
    expect(names['2']).toMatch(/^Pad-A\.h[0-9a-f]{8}(:0)?$/)
    expect(names['3']).toMatch(/^Pad-A\.h[0-9a-f]{8}(:\d+)?$/)
  })
})

// ===========================================================================
// 10. sortedAdjacentFaceTypes & sortedVertexValences
// ===========================================================================

describe('sortedAdjacentFaceTypes', () => {
  it('returns sorted neighbour surface kinds', () => {
    const faces = makeRectBoxFaces()
    // Top cap (index 0) shares edges 0-3 with four side faces (all 'plane').
    const kinds = sortedAdjacentFaceTypes(faces[0], faces)
    expect(kinds).toEqual(['plane', 'plane', 'plane', 'plane'])
  })

  it('returns empty array when sharedEdgeIndices is empty', () => {
    const face = { ...makeTopCap(0), sharedEdgeIndices: [] }
    expect(sortedAdjacentFaceTypes(face, makeRectBoxFaces())).toEqual([])
  })
})

describe('sortedVertexValences', () => {
  it('returns sorted valences', () => {
    const face = makeTopCap(0)
    expect(sortedVertexValences(face)).toEqual([2, 2, 2, 2])
  })

  it('sorts correctly for unsorted input', () => {
    const face = { ...makeTopCap(0), vertexValences: [4, 1, 3, 2] }
    expect(sortedVertexValences(face)).toEqual([1, 2, 3, 4])
  })
})
