// faceNamingT4Patterns.test.js — T4: pattern feature face naming.
//
// Tests for:
//   buildFaceNamesForPattern  (LinearPattern / PolarPattern)
//   buildFaceNamesForMirror   (MirrorPattern)
//
// Convention:
//   LinearPattern / PolarPattern:
//     instance N, local face index L → "<patternNodeId>.<N>/<seedFaceName>"
//   MirrorPattern:
//     original faces → seed name (unchanged)
//     mirrored faces → "<patternNodeId>.mirror/<seedFaceName>"
//
// ~10 test cases.

import { describe, it, expect } from 'vitest'
import { buildFaceNamesForPattern, buildFaceNamesForMirror } from '../lib/faceNaming.js'

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

// Seed shape: Pad-A with 6 faces (TopCap, BottomCap, 4 side faces)
const seedFaceNames6 = {
  '0': 'Pad-A.TopCap',
  '1': 'Pad-A.BottomCap',
  '2': 'Pad-A.Side.seg-0',
  '3': 'Pad-A.Side.seg-1',
  '4': 'Pad-A.Side.seg-2',
  '5': 'Pad-A.Side.seg-3',
}

// ---------------------------------------------------------------------------
// buildFaceNamesForPattern — LinearPattern / PolarPattern
// ---------------------------------------------------------------------------

describe('buildFaceNamesForPattern', () => {
  it('1. LinearPattern count=2, seed 6 faces → 12 output faces with instance prefix', () => {
    const seedCount = 6
    const count = 2
    const outputFaces = Array.from({ length: 12 }, (_, i) => makeFace(i))
    const names = buildFaceNamesForPattern('LinPat-D', count, seedFaceNames6, outputFaces, seedCount)
    // Instance 0: faces 0-5
    expect(names['0']).toBe('LinPat-D.0/Pad-A.TopCap')
    expect(names['1']).toBe('LinPat-D.0/Pad-A.BottomCap')
    expect(names['2']).toBe('LinPat-D.0/Pad-A.Side.seg-0')
    expect(names['5']).toBe('LinPat-D.0/Pad-A.Side.seg-3')
    // Instance 1: faces 6-11
    expect(names['6']).toBe('LinPat-D.1/Pad-A.TopCap')
    expect(names['7']).toBe('LinPat-D.1/Pad-A.BottomCap')
    expect(names['11']).toBe('LinPat-D.1/Pad-A.Side.seg-3')
  })

  it('2. PolarPattern count=3 → 3 instances each with correct prefix', () => {
    const seedCount = 2
    const seedNames = { '0': 'Rev-C.StartCap', '1': 'Rev-C.EndCap' }
    const count = 3
    const outputFaces = Array.from({ length: 6 }, (_, i) => makeFace(i))
    const names = buildFaceNamesForPattern('PolPat-E', count, seedNames, outputFaces, seedCount)
    expect(names['0']).toBe('PolPat-E.0/Rev-C.StartCap')
    expect(names['1']).toBe('PolPat-E.0/Rev-C.EndCap')
    expect(names['2']).toBe('PolPat-E.1/Rev-C.StartCap')
    expect(names['3']).toBe('PolPat-E.1/Rev-C.EndCap')
    expect(names['4']).toBe('PolPat-E.2/Rev-C.StartCap')
    expect(names['5']).toBe('PolPat-E.2/Rev-C.EndCap')
  })

  it('3. Pattern count=1 (single instance) → just instance 0 prefix', () => {
    const seedCount = 1
    const seedNames = { '0': 'Pad-A.TopCap' }
    const outputFaces = [makeFace(0)]
    const names = buildFaceNamesForPattern('LinPat-D', 1, seedNames, outputFaces, seedCount)
    expect(names['0']).toBe('LinPat-D.0/Pad-A.TopCap')
  })

  it('4. Pattern with empty seed names falls back to topo-hash', () => {
    const seedCount = 2
    const outputFaces = [makeFace(0), makeFace(1)]
    const names = buildFaceNamesForPattern('LinPat-D', 1, {}, outputFaces, seedCount)
    // Should produce something with topo-hash fallback (may have :0/:1 collision suffix)
    expect(names['0']).toMatch(/^LinPat-D\.0\/h[a-f0-9]+(:\d+)?$|^LinPat-D\.[a-f0-9h]+(:\d+)?$/)
  })

  it('5. All 12 output faces have non-empty names', () => {
    const seedCount = 6
    const outputFaces = Array.from({ length: 12 }, (_, i) => makeFace(i))
    const names = buildFaceNamesForPattern('LinPat-D', 2, seedFaceNames6, outputFaces, seedCount)
    for (let i = 0; i < 12; i++) {
      expect(names[String(i)]).toBeTruthy()
    }
  })
})

// ---------------------------------------------------------------------------
// buildFaceNamesForMirror — MirrorPattern
// ---------------------------------------------------------------------------

describe('buildFaceNamesForMirror', () => {
  it('6. MirrorPattern: original faces keep seed names', () => {
    const seedCount = 6
    const outputFaces = Array.from({ length: 12 }, (_, i) => makeFace(i))
    const names = buildFaceNamesForMirror('Mir-E', seedFaceNames6, outputFaces, seedCount)
    // Original faces 0-5 keep their seed names
    expect(names['0']).toBe('Pad-A.TopCap')
    expect(names['1']).toBe('Pad-A.BottomCap')
    expect(names['5']).toBe('Pad-A.Side.seg-3')
  })

  it('7. MirrorPattern: mirrored faces get mirror/ prefix', () => {
    const seedCount = 6
    const outputFaces = Array.from({ length: 12 }, (_, i) => makeFace(i))
    const names = buildFaceNamesForMirror('Mir-E', seedFaceNames6, outputFaces, seedCount)
    // Mirrored faces 6-11 get mirror/<seedName>
    expect(names['6']).toBe('Mir-E.mirror/Pad-A.TopCap')
    expect(names['7']).toBe('Mir-E.mirror/Pad-A.BottomCap')
    expect(names['11']).toBe('Mir-E.mirror/Pad-A.Side.seg-3')
  })

  it('8. MirrorPattern with 2 faces — single TopCap + mirror/TopCap', () => {
    const seedCount = 1
    const seedNames = { '0': 'Pad-A.TopCap' }
    const outputFaces = [makeFace(0), makeFace(1)]
    const names = buildFaceNamesForMirror('Mir-E', seedNames, outputFaces, seedCount)
    expect(names['0']).toBe('Pad-A.TopCap')
    expect(names['1']).toBe('Mir-E.mirror/Pad-A.TopCap')
  })

  it('9. MirrorPattern with empty seed names falls back to topo-hash', () => {
    const seedCount = 1
    const outputFaces = [makeFace(0), makeFace(1)]
    const names = buildFaceNamesForMirror('Mir-E', {}, outputFaces, seedCount)
    // Falls back to topo-hash
    expect(names['0']).toMatch(/^Mir-E\.[a-f0-9h]+$/)
    expect(names['1']).toMatch(/^Mir-E\.mirror\/h[a-f0-9]+$/)
  })

  it('10. All output faces have non-empty names after mirror', () => {
    const seedCount = 6
    const outputFaces = Array.from({ length: 12 }, (_, i) => makeFace(i))
    const names = buildFaceNamesForMirror('Mir-E', seedFaceNames6, outputFaces, seedCount)
    for (let i = 0; i < 12; i++) {
      expect(names[String(i)]).toBeTruthy()
    }
  })
})
