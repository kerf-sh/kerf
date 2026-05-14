// matesPanel.test.js — smoke tests for the MatesPanel state operations.
//
// MatesPanel is a React component without jsdom/RTL available, so these tests
// cover the pure-function layer (addMate, removeMate, mateRefFromPick) at the
// state transitions the panel drives: Add mate, change type, delete, solve result
// shape. The viewport-pick conversion is the critical Phase 2 path.

import { describe, it, expect } from 'vitest'
import {
  addMate,
  removeMate,
  mateRefFromPick,
  parseAssembly,
  serializeAssembly,
  identityMatrix,
} from '../lib/assembly.js'

const COMP_A = 'body-front'
const COMP_B = 'body-rear'

function face(cid, fid) {
  return { component_id: cid, feature: 'face', feature_id: fid }
}

describe('MatesPanel — Add mate flow', () => {
  it('adds a coincident mate and the list grows', () => {
    const mates0 = []
    const next = addMate(mates0, { type: 'coincident', a: face(COMP_A, 'f-1'), b: face(COMP_B, 'f-2') })
    expect(next).toHaveLength(1)
    expect(next[0].type).toBe('coincident')
    expect(next[0].a.component_id).toBe(COMP_A)
    expect(next[0].b.feature).toBe('face')
  })

  it('adds each of the 7 mate types without rejection', () => {
    const TYPES = ['coincident', 'concentric', 'parallel', 'perpendicular', 'distance', 'angle', 'tangent']
    let mates = []
    for (const type of TYPES) {
      mates = addMate(mates, { type, a: face(COMP_A, 'f-1'), b: face(COMP_B, 'f-2') })
    }
    expect(mates).toHaveLength(7)
    expect(mates.map((m) => m.type)).toEqual(TYPES)
  })

  it('dimensional mate carries value; non-dimensional gets null even if supplied', () => {
    const dist = addMate([], {
      type: 'distance',
      a: face(COMP_A, 'f-1'),
      b: face(COMP_B, 'f-2'),
      value: 42,
    })
    expect(dist[0].value).toBe(42)

    const coin = addMate([], {
      type: 'coincident',
      a: face(COMP_A, 'f-1'),
      b: face(COMP_B, 'f-2'),
      value: 99,
    })
    expect(coin[0].value).toBeNull()
  })
})

describe('MatesPanel — Delete mate flow', () => {
  it('removes the matching mate by id; rest survive', () => {
    let mates = []
    mates = addMate(mates, { id: 'a', type: 'coincident', a: face(COMP_A, 'f-1'), b: face(COMP_B, 'f-2') })
    mates = addMate(mates, { id: 'b', type: 'parallel', a: face(COMP_A, 'f-3'), b: face(COMP_B, 'f-4') })
    const after = removeMate(mates, 'a')
    expect(after).toHaveLength(1)
    expect(after[0].type).toBe('parallel')
  })

  it('deleting unknown id is a no-op that still returns a new array', () => {
    const mates = addMate([], { type: 'coincident', a: face(COMP_A, 'f-1'), b: face(COMP_B, 'f-2') })
    const after = removeMate(mates, 'nope')
    expect(after).not.toBe(mates)
    expect(after).toHaveLength(1)
  })
})

describe('MatesPanel — viewport pick → ref auto-populate', () => {
  it('face pick on single-object component fills the ref correctly', () => {
    const ref = mateRefFromPick('body-front', 'face', 'face-0')
    expect(ref.component_id).toBe('body-front')
    expect(ref.feature).toBe('face')
    expect(ref.feature_id).toBe('face-0')
  })

  it('multi-object partId stripped; pick converts to addable mate', () => {
    const refA = mateRefFromPick('cap/cap-obj', 'face', 'f-1')
    const refB = mateRefFromPick('shaft', 'edge', 'e-2')
    expect(refA.component_id).toBe('cap')
    expect(refB.feature).toBe('edge')
    const mates = addMate([], { type: 'concentric', a: refA, b: refB })
    expect(mates).toHaveLength(1)
  })
})

describe('MatesPanel — solve result shape round-trip', () => {
  it('mates survive parseAssembly → serializeAssembly for all types', () => {
    const doc = {
      components: [
        { id: COMP_A, file_id: 'f1', object_id: 'obj1', transform: identityMatrix() },
        { id: COMP_B, file_id: 'f2', object_id: 'obj2', transform: identityMatrix() },
      ],
      mates: [
        { type: 'coincident', a: face(COMP_A, 'face-1'), b: face(COMP_B, 'face-2') },
        { type: 'distance', a: face(COMP_A, 'face-3'), b: face(COMP_B, 'face-4'), value: 15 },
      ],
    }
    const json = serializeAssembly(doc)
    const parsed = parseAssembly(json)
    expect(parsed.mates).toHaveLength(2)
    expect(parsed.mates[0].type).toBe('coincident')
    expect(parsed.mates[1].value).toBe(15)
  })
})
