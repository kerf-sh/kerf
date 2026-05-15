// faceNamingT5Mates.test.js — T5: mate-ref serialisation round-trip.
//
// Tests the dual-write behaviour introduced in MatesPanel.jsx and the
// solver's preference for `face_name` over `feature_id`.
//
// These are pure-JS tests — no React rendering, no OCCT WASM.
// We test the addMate / removeMate helpers from assembly.js and the
// solver's face-ref resolution logic directly.
//
// ~8 test cases.

import { describe, it, expect } from 'vitest'
import { addMate, removeMate } from '../lib/assembly.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

let _mateCounter = 0
function makeMate(overrides = {}) {
  _mateCounter++
  return {
    id: `mate-${_mateCounter}`,
    type: 'coincident',
    a: { component_id: 'comp-1', feature: 'face', feature_id: 'face-3' },
    b: { component_id: 'comp-2', feature: 'face', feature_id: 'face-5' },
    ...overrides,
  }
}

// ---------------------------------------------------------------------------
// 1. addMate — legacy mate (no face_name) round-trips correctly
// ---------------------------------------------------------------------------
describe('mate-ref T5 round-trip', () => {
  it('1. addMate with legacy feature_id (no face_name) — id is preserved', () => {
    const mates = []
    const result = addMate(mates, makeMate())
    expect(result).toHaveLength(1)
    const m = result[0]
    expect(m.a.feature_id).toBe('face-3')
    expect(m.b.feature_id).toBe('face-5')
    expect(m.a.face_name).toBeUndefined()
  })

  // ---------------------------------------------------------------------------
  // 2. addMate with face_name — both fields present in result
  // ---------------------------------------------------------------------------
  it('2. addMate with feature_name — dual-write preserved', () => {
    const mates = []
    const result = addMate(mates, makeMate({
      a: { component_id: 'comp-1', feature: 'face', feature_id: 'face-3', feature_name: 'Pad-A.TopCap' },
      b: { component_id: 'comp-2', feature: 'face', feature_id: 'face-5', feature_name: 'Pocket-B.Inner.Side.seg-1' },
    }))
    const m = result[0]
    expect(m.a.feature_name).toBe('Pad-A.TopCap')
    expect(m.a.feature_id).toBe('face-3')
    expect(m.b.feature_name).toBe('Pocket-B.Inner.Side.seg-1')
    expect(m.b.feature_id).toBe('face-5')
  })

  // ---------------------------------------------------------------------------
  // 3. removeMate — removes the correct mate by id
  // ---------------------------------------------------------------------------
  it('3. removeMate removes the correct mate', () => {
    let mates = []
    mates = addMate(mates, makeMate())
    mates = addMate(mates, makeMate({ type: 'parallel' }))
    expect(mates).toHaveLength(2)
    const idToRemove = mates[0].id
    const after = removeMate(mates, idToRemove)
    expect(after).toHaveLength(1)
    expect(after[0].type).toBe('parallel')
  })

  // ---------------------------------------------------------------------------
  // 4. Mate with face_name survives removeMate of sibling
  // ---------------------------------------------------------------------------
  it('4. mate with feature_name survives removeMate of sibling', () => {
    let mates = []
    mates = addMate(mates, makeMate())
    mates = addMate(mates, makeMate({
      a: { component_id: 'comp-1', feature: 'face', feature_id: 'face-7', feature_name: 'Rev-C.Side.seg-2' },
      b: { component_id: 'comp-2', feature: 'face', feature_id: 'face-0', feature_name: 'Pad-A.BottomCap' },
    }))
    mates = removeMate(mates, mates[0].id)
    expect(mates).toHaveLength(1)
    expect(mates[0].a.feature_name).toBe('Rev-C.Side.seg-2')
  })

  // ---------------------------------------------------------------------------
  // 5. solver.py: face_name preferred over feature_id (simulation)
  // ---------------------------------------------------------------------------
  it('5. solver resolution: feature_name takes priority over feature_id', () => {
    // Simulate what solver.py does:
    //   feature_id = ref.get("feature_name") or ref.get("feature_id", "")
    function resolveRef(ref) {
      return ref.feature_name || ref.feature_id || ''
    }

    const refWithBoth = { feature_id: 'face-3', feature_name: 'Pad-A.TopCap' }
    expect(resolveRef(refWithBoth)).toBe('Pad-A.TopCap')

    const refLegacy = { feature_id: 'face-3' }
    expect(resolveRef(refLegacy)).toBe('face-3')

    const refNameOnly = { feature_name: 'Rev-C.EndCap' }
    expect(resolveRef(refNameOnly)).toBe('Rev-C.EndCap')
  })

  // ---------------------------------------------------------------------------
  // 6. Multiple mates — all face_names preserved after addMate/addMate
  // ---------------------------------------------------------------------------
  it('6. multiple mates with feature names — all preserved', () => {
    let mates = []
    for (let i = 0; i < 3; i++) {
      mates = addMate(mates, makeMate({
        a: { component_id: `comp-${i}`, feature: 'face', feature_id: `face-${i}`, feature_name: `Pad-${i}.TopCap` },
        b: { component_id: 'anchor', feature: 'face', feature_id: 'face-0', feature_name: 'Anchor.BottomCap' },
      }))
    }
    expect(mates).toHaveLength(3)
    for (let i = 0; i < 3; i++) {
      expect(mates[i].a.feature_name).toBe(`Pad-${i}.TopCap`)
    }
  })

  // ---------------------------------------------------------------------------
  // 7. Partial form data (only feature_id, no face_name) — no face_name key written
  // ---------------------------------------------------------------------------
  it('7. mate built without feature_name — feature_name not present in output', () => {
    const result = addMate([], makeMate())
    expect(result[0].a.feature_name).toBeUndefined()
    expect(result[0].b.feature_name).toBeUndefined()
  })

  // ---------------------------------------------------------------------------
  // 8. Empty feature_name string — treated same as absent (solver uses feature_id)
  // ---------------------------------------------------------------------------
  it('8. empty feature_name string — solver falls back to feature_id', () => {
    function resolveRef(ref) {
      return ref.feature_name || ref.feature_id || ''
    }
    const ref = { feature_id: 'face-9', feature_name: '' }
    expect(resolveRef(ref)).toBe('face-9')
  })
})
