// faceNamingT3Booleans.test.js — T3: boundary-face naming for boolean ops.
//
// Tests for traceBooleanResult() in faceNaming.js.
//
// All tests use synthetic FaceDescriptors and ModifiedMaps (no OCCT WASM).
// The OCCT class used for parent→child tracking is BRepAlgoAPI_Cut_3 /
// Fuse_3 / Common_3, each of which inherits Modified() / Generated() from
// BRepAlgoAPI_BooleanOperation.  extractModifiedMap() in occtWorker.js calls
// those callbacks and packages the result into the ModifiedMap structure
// consumed by traceBooleanResult here.
//
// Scenarios:
//   1. Cut — face survives from A (unmodified)     → inherits A name
//   2. Cut — face survives from B (unmodified)     → inherits B name
//   3. Cut — new boundary face with no parent      → boundary.<topoHash>
//   4. Cut — split face with two parents           → cut.<hash> (topo-hash fallback)
//   5. Fuse — face inherited from A                → A name
//   6. Fuse — face inherited from B                → B name
//   7. Fuse — new boundary at union                → boundary.<hash>
//   8. Common — face from A survives               → A name
//   9. Common — face from B survives               → B name
//  10. Common — new face generated                 → boundary.<hash>
//  11. Empty inputs — all generated                → boundary.<hash> for every face
//  12. Collision resolution — two faces get same hash → :0 / :1 suffix
//  13. Cut — A face modified (trimmed), single parent → inherits A name
//  14. Empty face list                             → empty result
//  15. All faces generated                         → all get boundary hashes

import { describe, it, expect } from 'vitest'
import { traceBooleanResult } from '../lib/faceNaming.js'

// ---------------------------------------------------------------------------
// Synthetic helpers
// ---------------------------------------------------------------------------

function makeFace(index, overrides = {}) {
  return {
    index,
    surfaceKind: 'plane',
    edgeCount: 4,
    edgeKinds: ['line', 'line', 'line', 'line'],
    vertexValences: [2, 2, 2, 2],
    normal: [0, 0, 1],
    sharedEdgeIndices: [index, index + 1],
    sketchEntityId: null,
    isCap: false,
    isTop: false,
    ...overrides,
  }
}

function makeModifiedMap(modified = {}, generated = [], deletedInputs = new Set()) {
  return { modified, generated, deletedInputs }
}

// ---------------------------------------------------------------------------
// 1. Cut — face survives from A (unmodified, not in modified, not in generated)
// ---------------------------------------------------------------------------
describe('traceBooleanResult', () => {
  it('1. cut: face survives unchanged from A — inherits A name', () => {
    const faceNamesA = { '0': 'Pad-A.TopCap', '1': 'Pad-A.Side.seg-0' }
    const faceNamesB = { '0': 'Pad-B.TopCap' }
    const outputFaces = [makeFace(0), makeFace(1)]
    // Face 0 and 1 from A are in modified[0]→[0] and modified[1]→[1]
    // (OCCT marks surviving faces as Modified with themselves as output).
    const modMap = makeModifiedMap({ 0: [0], 1: [1] }, [])
    const names = traceBooleanResult('Cut-F', 'cut', faceNamesA, faceNamesB, outputFaces, modMap)
    expect(names['0']).toBe('Pad-A.TopCap')
    expect(names['1']).toBe('Pad-A.Side.seg-0')
  })

  // ---------------------------------------------------------------------------
  // 2. Cut — face survives from B (offset by aCount)
  // ---------------------------------------------------------------------------
  it('2. cut: face survives from B — inherits B name', () => {
    const faceNamesA = { '0': 'Pad-A.TopCap' }     // 1 face in A
    const faceNamesB = { '0': 'Pad-B.BottomCap' }  // 1 face in B, offset by 1
    const outputFaces = [makeFace(0)]
    // B face 0 maps to output face 0; B is offset by aCount=1 → input index 1
    const modMap = makeModifiedMap({ 1: [0] }, [])
    const names = traceBooleanResult('Cut-F', 'cut', faceNamesA, faceNamesB, outputFaces, modMap)
    expect(names['0']).toBe('Pad-B.BottomCap')
  })

  // ---------------------------------------------------------------------------
  // 3. Cut — genuinely new boundary face (generated, no parent)
  // ---------------------------------------------------------------------------
  it('3. cut: new boundary face — gets boundary.<hash>', () => {
    const faceNamesA = { '0': 'Pad-A.TopCap' }
    const faceNamesB = { '0': 'Pad-B.TopCap' }
    const outputFaces = [makeFace(0), makeFace(1, { surfaceKind: 'cylinder', sharedEdgeIndices: [10, 11] })]
    const modMap = makeModifiedMap({ 0: [0] }, [1])
    const names = traceBooleanResult('Cut-F', 'cut', faceNamesA, faceNamesB, outputFaces, modMap)
    expect(names['0']).toBe('Pad-A.TopCap')
    expect(names['1']).toMatch(/^Cut-F\.boundary\.[a-f0-9h]+$/)
  })

  // ---------------------------------------------------------------------------
  // 4. Cut — split face with two parents (topo-hash fallback)
  // ---------------------------------------------------------------------------
  it('4. cut: split face from two parents — cut.<hash> fallback', () => {
    const faceNamesA = { '0': 'Pad-A.TopCap', '1': 'Pad-A.Side.seg-0' }
    const faceNamesB = { '0': 'Pad-B.TopCap' }
    const outputFaces = [makeFace(0)]
    // Both A face 0 and A face 1 map to output face 0 (split scenario)
    const modMap = makeModifiedMap({ 0: [0], 1: [0] }, [])
    const names = traceBooleanResult('Cut-F', 'cut', faceNamesA, faceNamesB, outputFaces, modMap)
    // Should use A-side lineage with a cut qualifier
    expect(names['0']).toMatch(/^Cut-F\.cut\.|^Pad-A\./)
  })

  // ---------------------------------------------------------------------------
  // 5. Fuse — face inherited from A
  // ---------------------------------------------------------------------------
  it('5. fuse: face from A — inherits A name', () => {
    const faceNamesA = { '0': 'Pad-A.TopCap' }
    const faceNamesB = {}
    const outputFaces = [makeFace(0)]
    const modMap = makeModifiedMap({ 0: [0] }, [])
    const names = traceBooleanResult('Fuse-G', 'fuse', faceNamesA, faceNamesB, outputFaces, modMap)
    expect(names['0']).toBe('Pad-A.TopCap')
  })

  // ---------------------------------------------------------------------------
  // 6. Fuse — face inherited from B
  // ---------------------------------------------------------------------------
  it('6. fuse: face from B — inherits B name', () => {
    const faceNamesA = { '0': 'Pad-A.TopCap' }   // 1 face in A
    const faceNamesB = { '0': 'Pad-B.Side.seg-0' }
    const outputFaces = [makeFace(0), makeFace(1)]
    // A face 0 → output 0;  B face 0 (offset 1) → output 1
    const modMap = makeModifiedMap({ 0: [0], 1: [1] }, [])
    const names = traceBooleanResult('Fuse-G', 'fuse', faceNamesA, faceNamesB, outputFaces, modMap)
    expect(names['0']).toBe('Pad-A.TopCap')
    expect(names['1']).toBe('Pad-B.Side.seg-0')
  })

  // ---------------------------------------------------------------------------
  // 7. Fuse — new boundary face at union
  // ---------------------------------------------------------------------------
  it('7. fuse: new boundary face — boundary.<hash>', () => {
    const faceNamesA = {}
    const faceNamesB = {}
    const outputFaces = [makeFace(0, { surfaceKind: 'plane', sharedEdgeIndices: [5, 6, 7] })]
    const modMap = makeModifiedMap({}, [0])
    const names = traceBooleanResult('Fuse-G', 'fuse', faceNamesA, faceNamesB, outputFaces, modMap)
    expect(names['0']).toMatch(/^Fuse-G\.boundary\.[a-f0-9h]+$/)
  })

  // ---------------------------------------------------------------------------
  // 8. Common — face from A survives
  // ---------------------------------------------------------------------------
  it('8. common: face from A survives — A name', () => {
    const faceNamesA = { '0': 'Pad-A.BottomCap', '1': 'Pad-A.Side.seg-1' }
    const faceNamesB = {}
    const outputFaces = [makeFace(0), makeFace(1)]
    const modMap = makeModifiedMap({ 0: [0], 1: [1] }, [])
    const names = traceBooleanResult('Cmn-H', 'common', faceNamesA, faceNamesB, outputFaces, modMap)
    expect(names['0']).toBe('Pad-A.BottomCap')
    expect(names['1']).toBe('Pad-A.Side.seg-1')
  })

  // ---------------------------------------------------------------------------
  // 9. Common — face from B survives
  // ---------------------------------------------------------------------------
  it('9. common: face from B survives — B name', () => {
    const faceNamesA = {}                          // 0 faces in A
    const faceNamesB = { '0': 'Pad-B.TopCap' }
    const outputFaces = [makeFace(0)]
    // B face 0 offset 0 (aCount=0) → input index 0 → output 0
    const modMap = makeModifiedMap({ 0: [0] }, [])
    const names = traceBooleanResult('Cmn-H', 'common', faceNamesA, faceNamesB, outputFaces, modMap)
    expect(names['0']).toBe('Pad-B.TopCap')
  })

  // ---------------------------------------------------------------------------
  // 10. Common — new face generated
  // ---------------------------------------------------------------------------
  it('10. common: generated face — boundary.<hash>', () => {
    const faceNamesA = {}
    const faceNamesB = {}
    const outputFaces = [makeFace(0)]
    const modMap = makeModifiedMap({}, [0])
    const names = traceBooleanResult('Cmn-H', 'common', faceNamesA, faceNamesB, outputFaces, modMap)
    expect(names['0']).toMatch(/^Cmn-H\.boundary\.[a-f0-9h]+$/)
  })

  // ---------------------------------------------------------------------------
  // 11. Empty inputs — all generated → all get boundary hashes
  // ---------------------------------------------------------------------------
  it('11. empty inputs: all faces generated', () => {
    const outputFaces = [makeFace(0), makeFace(1, { edgeKinds: ['circle', 'line'] })]
    const modMap = makeModifiedMap({}, [0, 1])
    const names = traceBooleanResult('Cut-F', 'cut', {}, {}, outputFaces, modMap)
    expect(Object.keys(names).length).toBe(2)
    expect(names['0']).toMatch(/^Cut-F\.boundary\./)
    expect(names['1']).toMatch(/^Cut-F\.boundary\./)
  })

  // ---------------------------------------------------------------------------
  // 12. Collision resolution — same hash → :0 / :1 suffix
  // ---------------------------------------------------------------------------
  it('12. collision resolution — two identical generated faces get :0/:1', () => {
    // Two faces with identical topology → same hash → collision resolution
    const face = (idx) => makeFace(idx, { surfaceKind: 'plane', edgeCount: 4,
      edgeKinds: ['line', 'line', 'line', 'line'], sharedEdgeIndices: [0, 1, 2, 3] })
    const outputFaces = [face(0), face(1)]
    const modMap = makeModifiedMap({}, [0, 1])
    const names = traceBooleanResult('Cut-F', 'cut', {}, {}, outputFaces, modMap)
    // Both have the same topology → same hash → one gets :0, the other :1
    const vals = Object.values(names)
    const base = vals[0].replace(/:0$/, '').replace(/:1$/, '')
    expect(vals[0]).toBe(`${base}:0`)
    expect(vals[1]).toBe(`${base}:1`)
  })

  // ---------------------------------------------------------------------------
  // 13. Cut — A face modified (trimmed), single parent → inherits A name
  // ---------------------------------------------------------------------------
  it('13. cut: trimmed face with single parent — inherits parent name', () => {
    const faceNamesA = { '0': 'Pad-A.Side.seg-2' }
    const faceNamesB = {}
    const outputFaces = [makeFace(0, { surfaceKind: 'plane', edgeKinds: ['line', 'line', 'bspline'] })]
    const modMap = makeModifiedMap({ 0: [0] }, [])
    const names = traceBooleanResult('Cut-F', 'cut', faceNamesA, faceNamesB, outputFaces, modMap)
    expect(names['0']).toBe('Pad-A.Side.seg-2')
  })

  // ---------------------------------------------------------------------------
  // 14. Empty face list → empty result
  // ---------------------------------------------------------------------------
  it('14. empty face list → empty names object', () => {
    const names = traceBooleanResult('Cut-F', 'cut', {}, {}, [], { modified: {}, generated: [], deletedInputs: new Set() })
    expect(Object.keys(names).length).toBe(0)
  })

  // ---------------------------------------------------------------------------
  // 15. All faces generated — each gets a unique boundary hash
  // ---------------------------------------------------------------------------
  it('15. multiple generated faces with different topology → distinct names', () => {
    const outputFaces = [
      makeFace(0, { surfaceKind: 'plane',    edgeKinds: ['line', 'line', 'line', 'line'], sharedEdgeIndices: [0, 1] }),
      makeFace(1, { surfaceKind: 'cylinder', edgeKinds: ['circle', 'line'], sharedEdgeIndices: [2, 3] }),
      makeFace(2, { surfaceKind: 'plane',    edgeKinds: ['line', 'bspline', 'line'], sharedEdgeIndices: [4, 5] }),
    ]
    const modMap = makeModifiedMap({}, [0, 1, 2])
    const names = traceBooleanResult('Fuse-G', 'fuse', {}, {}, outputFaces, modMap)
    const vals = Object.values(names)
    // All three should have distinct names (different topology)
    const uniq = new Set(vals)
    expect(uniq.size).toBe(3)
    for (const v of vals) {
      expect(v).toMatch(/^Fuse-G\.boundary\./)
    }
  })
})
