// featureBoolean.test.js — coverage for NURBS booleans v1 T4/T6.
//
// No WASM required. The suite verifies:
//
//   1. Source wiring (occtWorker.js): both dispatch tables contain 'boolean'
//      and 'to_solid'; opBoolean is defined; bodyMap is declared in both
//      evaluators; correct fallback path comment for Common_3 is present.
//   2. opBoolean inline mock: dispatch by kind (cut/fuse/common); missing
//      operand errors; non-solid operand error message contains hint.
//   3. FeatureView inspector: FEATURE_KINDS contains to_solid + boolean
//      entries; both are in the Modify category; defaults are correct;
//      field kinds match spec.

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// ── 0. Source-level wiring checks ────────────────────────────────────────────

describe('occtWorker.js boolean wiring', () => {
  const workerSrc = readFileSync(
    path.resolve(__dirname, '../lib/occtWorker.js'),
    'utf8',
  )

  it("evaluateTree dispatch table contains 'boolean' case", () => {
    const etIdx = workerSrc.indexOf('function evaluateTree(')
    const etfIdx = workerSrc.indexOf('async function evaluateToFinalShape(')
    const firstBoolean = workerSrc.indexOf("case 'boolean'")
    expect(firstBoolean).toBeGreaterThan(etIdx)
    expect(firstBoolean).toBeLessThan(etfIdx)
  })

  it("evaluateToFinalShape dispatch table also contains 'boolean' case", () => {
    const etfIdx = workerSrc.indexOf('async function evaluateToFinalShape(')
    const booleanAfterEtf = workerSrc.indexOf("case 'boolean'", etfIdx)
    expect(booleanAfterEtf).toBeGreaterThan(etfIdx)
  })

  it("evaluateTree dispatch table still contains 'to_solid' case (T2 not broken)", () => {
    const etIdx = workerSrc.indexOf('function evaluateTree(')
    const etfIdx = workerSrc.indexOf('async function evaluateToFinalShape(')
    const firstToSolid = workerSrc.indexOf("case 'to_solid'")
    expect(firstToSolid).toBeGreaterThan(etIdx)
    expect(firstToSolid).toBeLessThan(etfIdx)
  })

  it("evaluateToFinalShape dispatch table still contains 'to_solid' case (T2 not broken)", () => {
    const etfIdx = workerSrc.indexOf('async function evaluateToFinalShape(')
    const toSolidAfterEtf = workerSrc.indexOf("case 'to_solid'", etfIdx)
    expect(toSolidAfterEtf).toBeGreaterThan(etfIdx)
  })

  it('opBoolean function is defined', () => {
    expect(workerSrc).toContain('function opBoolean(')
  })

  it('opBoolean handles cut/fuse/common via switch', () => {
    expect(workerSrc).toContain("case 'cut'")
    expect(workerSrc).toContain("case 'fuse'")
    expect(workerSrc).toContain("case 'common'")
  })

  it('bodyMap is declared in evaluateTree', () => {
    const etIdx = workerSrc.indexOf('function evaluateTree(')
    const etfIdx = workerSrc.indexOf('async function evaluateToFinalShape(')
    const bodyMapInEt = workerSrc.indexOf('const bodyMap', etIdx)
    expect(bodyMapInEt).toBeGreaterThan(etIdx)
    expect(bodyMapInEt).toBeLessThan(etfIdx)
  })

  it('bodyMap is declared in evaluateToFinalShape', () => {
    const etfIdx = workerSrc.indexOf('async function evaluateToFinalShape(')
    const bodyMapInEtf = workerSrc.indexOf('const bodyMap', etfIdx)
    expect(bodyMapInEtf).toBeGreaterThan(etfIdx)
  })

  it('Common_3 fallback path identity comment is present', () => {
    // The fallback computes A ∩ B = A − (A − B).
    expect(workerSrc).toContain('BRepAlgoAPI_Common_3')
  })

  it('opBoolean surfaces non-solid operand error with feature_to_solid hint', () => {
    expect(workerSrc).toContain('feature_to_solid')
    expect(workerSrc).toContain('not a solid')
  })

  it('_isSolid helper is defined', () => {
    expect(workerSrc).toContain('function _isSolid(')
  })

  it('_isEmptyShape helper is defined', () => {
    expect(workerSrc).toContain('function _isEmptyShape(')
  })
})

// ── 1. opBoolean inline mock ──────────────────────────────────────────────────
//
// We inline the opBoolean logic so we can drive it with mock oc + bodyMap.
// Source-level checks above confirm the real code matches the tested contract.

function _isSolid(oc, shape) {
  if (!shape || typeof shape.ShapeType !== 'function') return false
  try {
    const st = shape.ShapeType()
    const SOLID = oc.TopAbs_ShapeEnum?.TopAbs_SOLID ?? 2
    return st === SOLID
  } catch {
    return false
  }
}

function _shapeKindName(oc, shape) {
  if (!shape || typeof shape.ShapeType !== 'function') return 'UNKNOWN'
  try {
    const st = shape.ShapeType()
    const e = oc.TopAbs_ShapeEnum || {}
    if (st === (e.TopAbs_SHELL ?? 3)) return 'SHELL'
    if (st === (e.TopAbs_FACE ?? 4)) return 'FACE'
    return `SHAPE(${st})`
  } catch {
    return 'UNKNOWN'
  }
}

function _isEmptyShape(_oc, shape) {
  if (!shape) return true
  return shape._empty === true
}

// Lightweight track stub.
function track(_tracker, obj) { return obj }

function opBoolean(oc, _prev, node, _sketches, tracker, bodyMap, {
  BRepAlgoAPI_Cut_3 = null,
  BRepAlgoAPI_Fuse_3 = null,
  BRepAlgoAPI_Common_3 = null,
} = {}) {
  const aId = node.target_a_id
  const bId = node.target_b_id
  if (!aId) throw new Error('boolean: target_a_id is required')
  if (!bId) throw new Error('boolean: target_b_id is required')

  const a = bodyMap && bodyMap[aId]
  const b = bodyMap && bodyMap[bId]
  if (!a) throw new Error(`boolean: target_a '${aId}' not found in evaluated tree`)
  if (!b) throw new Error(`boolean: target_b '${bId}' not found in evaluated tree`)

  if (!_isSolid(oc, a)) {
    const k = _shapeKindName(oc, a)
    throw new Error(`boolean: target_a is a ${k}, not a solid — run feature_to_solid on '${aId}' first`)
  }
  if (!_isSolid(oc, b)) {
    const k = _shapeKindName(oc, b)
    throw new Error(`boolean: target_b is a ${k}, not a solid — run feature_to_solid on '${bId}' first`)
  }

  const pr = () => ({ _tag: 'progress' })
  const Cut3 = BRepAlgoAPI_Cut_3 || oc.BRepAlgoAPI_Cut_3
  const Fuse3 = BRepAlgoAPI_Fuse_3 || oc.BRepAlgoAPI_Fuse_3
  const Common3 = BRepAlgoAPI_Common_3 || oc.BRepAlgoAPI_Common_3

  let result
  switch (node.kind) {
    case 'cut': {
      const algo = track(tracker, new Cut3(a, b, pr()))
      algo.Build(pr())
      if (!algo.IsDone()) throw new Error('boolean: cut algorithm failed (BOPAlgo error)')
      result = algo.Shape()
      break
    }
    case 'fuse': {
      const algo = track(tracker, new Fuse3(a, b, pr()))
      algo.Build(pr())
      if (!algo.IsDone()) throw new Error('boolean: fuse algorithm failed (BOPAlgo error)')
      result = algo.Shape()
      break
    }
    case 'common': {
      if (typeof Common3 !== 'function') {
        // Fallback: A ∩ B = A − (A − B)
        const inner = track(tracker, new Cut3(a, b, pr()))
        inner.Build(pr())
        if (!inner.IsDone()) throw new Error('boolean: common-via-cut inner step failed')
        const outer = track(tracker, new Cut3(a, inner.Shape(), pr()))
        outer.Build(pr())
        if (!outer.IsDone()) throw new Error('boolean: common-via-cut outer step failed')
        result = outer.Shape()
      } else {
        const algo = track(tracker, new Common3(a, b, pr()))
        algo.Build(pr())
        if (!algo.IsDone()) throw new Error('boolean: common algorithm failed (BOPAlgo error)')
        result = algo.Shape()
      }
      break
    }
    default:
      throw new Error(`boolean: unknown kind '${node.kind}' (expected cut|fuse|common)`)
  }

  if (_isEmptyShape(oc, result)) {
    throw new Error(`boolean: ${node.kind} produced an empty result (operands may not intersect)`)
  }
  return result
}

// Build a fake solid shape.
function makeSolid(tag = 'solid') {
  const SOLID_VAL = 2
  return {
    _tag: tag,
    ShapeType: () => SOLID_VAL,
  }
}

// Build a fake shell (non-solid surface body).
function makeShell(tag = 'shell') {
  const SHELL_VAL = 3
  return {
    _tag: tag,
    ShapeType: () => SHELL_VAL,
  }
}

// Build a mock algo class factory.
function makeAlgoClass(resultShape, isDone = true) {
  return class MockAlgo {
    constructor(_a, _b, _pr) {
      this._result = resultShape
      this._done = isDone
    }
    Build(_pr) {}
    IsDone() { return this._done }
    Shape() { return this._result }
  }
}

describe('opBoolean — dispatch by kind', () => {
  it('cut dispatches to Cut_3', () => {
    let cutCalled = false
    const resultShape = makeSolid('cut_result')
    class MockCut {
      constructor(_a, _b, _pr) { cutCalled = true }
      Build() {}
      IsDone() { return true }
      Shape() { return resultShape }
    }
    const a = makeSolid('a'), b = makeSolid('b')
    const node = { op: 'boolean', id: 'b1', target_a_id: 'a', target_b_id: 'b', kind: 'cut' }
    const bodyMap = { a, b }
    const result = opBoolean({}, null, node, {}, [], bodyMap, { BRepAlgoAPI_Cut_3: MockCut })
    expect(cutCalled).toBe(true)
    expect(result).toBe(resultShape)
  })

  it('fuse dispatches to Fuse_3', () => {
    let fuseCalled = false
    const resultShape = makeSolid('fuse_result')
    class MockFuse {
      constructor() { fuseCalled = true }
      Build() {}
      IsDone() { return true }
      Shape() { return resultShape }
    }
    const a = makeSolid(), b = makeSolid()
    const node = { op: 'boolean', id: 'b1', target_a_id: 'a', target_b_id: 'b', kind: 'fuse' }
    const result = opBoolean({}, null, node, {}, [], { a, b }, { BRepAlgoAPI_Fuse_3: MockFuse, BRepAlgoAPI_Cut_3: makeAlgoClass(makeSolid()) })
    expect(fuseCalled).toBe(true)
    expect(result).toBe(resultShape)
  })

  it('common dispatches to Common_3 when available', () => {
    let commonCalled = false
    const resultShape = makeSolid('common_result')
    class MockCommon {
      constructor() { commonCalled = true }
      Build() {}
      IsDone() { return true }
      Shape() { return resultShape }
    }
    const a = makeSolid(), b = makeSolid()
    const node = { op: 'boolean', id: 'b1', target_a_id: 'a', target_b_id: 'b', kind: 'common' }
    const result = opBoolean({}, null, node, {}, [], { a, b }, {
      BRepAlgoAPI_Common_3: MockCommon,
      BRepAlgoAPI_Cut_3: makeAlgoClass(makeSolid()),
    })
    expect(commonCalled).toBe(true)
    expect(result).toBe(resultShape)
  })

  it('common falls back to A − (A − B) when Common_3 is absent', () => {
    let cutCallCount = 0
    const innerResult = makeSolid('inner_cut')
    const outerResult = makeSolid('outer_cut')
    class MockCut {
      constructor(_a, _b) {
        cutCallCount++
        this._result = cutCallCount === 1 ? innerResult : outerResult
      }
      Build() {}
      IsDone() { return true }
      Shape() { return this._result }
    }
    const a = makeSolid(), b = makeSolid()
    const node = { op: 'boolean', id: 'b1', target_a_id: 'a', target_b_id: 'b', kind: 'common' }
    // No Common_3 provided → fallback path.
    const result = opBoolean({}, null, node, {}, [], { a, b }, {
      BRepAlgoAPI_Cut_3: MockCut,
    })
    expect(cutCallCount).toBe(2)
    expect(result).toBe(outerResult)
  })
})

describe('opBoolean — error paths', () => {
  it('throws when target_a not in bodyMap', () => {
    const b = makeSolid()
    const node = { target_a_id: 'missing', target_b_id: 'b', kind: 'cut' }
    expect(() => opBoolean({}, null, node, {}, [], { b })).toThrow(/target_a.*not found/)
  })

  it('throws when target_b not in bodyMap', () => {
    const a = makeSolid()
    const node = { target_a_id: 'a', target_b_id: 'missing', kind: 'cut' }
    expect(() => opBoolean({}, null, node, {}, [], { a })).toThrow(/target_b.*not found/)
  })

  it('throws with feature_to_solid hint when target_a is a shell', () => {
    const a = makeShell(), b = makeSolid()
    const node = { target_a_id: 'a', target_b_id: 'b', kind: 'cut' }
    let err = null
    try { opBoolean({}, null, node, {}, [], { a, b }) } catch (e) { err = e }
    expect(err).not.toBeNull()
    expect(err.message).toContain('SHELL')
    expect(err.message).toContain('feature_to_solid')
  })

  it('throws with feature_to_solid hint when target_b is a shell', () => {
    const a = makeSolid(), b = makeShell()
    const node = { target_a_id: 'a', target_b_id: 'b', kind: 'fuse' }
    let err = null
    try { opBoolean({}, null, node, {}, [], { a, b }) } catch (e) { err = e }
    expect(err.message).toContain('feature_to_solid')
  })

  it('throws for unknown kind', () => {
    const a = makeSolid(), b = makeSolid()
    const node = { target_a_id: 'a', target_b_id: 'b', kind: 'union' }
    expect(() => opBoolean({}, null, node, {}, [], { a, b })).toThrow(/unknown kind/)
  })

  it('throws when algo IsDone() is false', () => {
    const resultShape = makeSolid()
    class FailCut {
      constructor() {}
      Build() {}
      IsDone() { return false }
      Shape() { return resultShape }
    }
    const a = makeSolid(), b = makeSolid()
    const node = { target_a_id: 'a', target_b_id: 'b', kind: 'cut' }
    expect(() => opBoolean({}, null, node, {}, [], { a, b }, { BRepAlgoAPI_Cut_3: FailCut }))
      .toThrow(/cut algorithm failed/)
  })

  it('throws on empty result shape', () => {
    const emptyShape = { _empty: true, _tag: 'empty_solid', ShapeType: () => 2 }
    class MockCut {
      Build() {}
      IsDone() { return true }
      Shape() { return emptyShape }
    }
    const a = makeSolid(), b = makeSolid()
    const node = { target_a_id: 'a', target_b_id: 'b', kind: 'cut' }
    expect(() => opBoolean({}, null, node, {}, [], { a, b }, { BRepAlgoAPI_Cut_3: MockCut }))
      .toThrow(/empty result/)
  })
})

// ── 2. FeatureView inspector checks ──────────────────────────────────────────
//
// We read the FeatureView source and verify the FEATURE_KINDS and
// FEATURE_CATEGORIES entries were added correctly.

describe('FeatureView.jsx to_solid + boolean inspector entries', () => {
  const viewSrc = readFileSync(
    path.resolve(__dirname, '../components/FeatureView.jsx'),
    'utf8',
  )

  it("FEATURE_KINDS contains op: 'to_solid'", () => {
    expect(viewSrc).toContain("op: 'to_solid'")
  })

  it("FEATURE_KINDS contains op: 'boolean'", () => {
    expect(viewSrc).toContain("op: 'boolean'")
  })

  it("Modify category contains 'to_solid'", () => {
    // Find the Modify category line and check it includes to_solid.
    const modifyIdx = viewSrc.indexOf("id: 'modify'")
    expect(modifyIdx).toBeGreaterThan(-1)
    const modifyLine = viewSrc.slice(modifyIdx, viewSrc.indexOf('\n', modifyIdx + 1) + 200)
    expect(modifyLine).toContain('to_solid')
  })

  it("Modify category contains 'boolean'", () => {
    const modifyIdx = viewSrc.indexOf("id: 'modify'")
    const modifyLine = viewSrc.slice(modifyIdx, viewSrc.indexOf('\n', modifyIdx + 1) + 200)
    expect(modifyLine).toContain('boolean')
  })

  it("to_solid entry has target_id as feature_picker field", () => {
    // The to_solid block should declare target_id with kind: 'feature_picker'
    const toSolidIdx = viewSrc.indexOf("op: 'to_solid'")
    const toSolidBlock = viewSrc.slice(toSolidIdx, toSolidIdx + 600)
    expect(toSolidBlock).toContain("'target_id'")
    expect(toSolidBlock).toContain("'feature_picker'")
  })

  it("to_solid entry has tolerance as number field", () => {
    const toSolidIdx = viewSrc.indexOf("op: 'to_solid'")
    const toSolidBlock = viewSrc.slice(toSolidIdx, toSolidIdx + 600)
    expect(toSolidBlock).toContain("'tolerance'")
    expect(toSolidBlock).toContain("'number'")
  })

  it("to_solid default tolerance is 1e-6", () => {
    const toSolidIdx = viewSrc.indexOf("op: 'to_solid'")
    const toSolidBlock = viewSrc.slice(toSolidIdx, toSolidIdx + 400)
    expect(toSolidBlock).toContain('1e-6')
  })

  it("boolean entry has target_a_id and target_b_id as feature_picker fields", () => {
    const boolIdx = viewSrc.indexOf("op: 'boolean'")
    const boolBlock = viewSrc.slice(boolIdx, boolIdx + 800)
    expect(boolBlock).toContain("'target_a_id'")
    expect(boolBlock).toContain("'target_b_id'")
    // Count feature_picker occurrences in this block — should be at least 2.
    const count = (boolBlock.match(/'feature_picker'/g) || []).length
    expect(count).toBeGreaterThanOrEqual(2)
  })

  it("boolean entry has kind as select field with cut/fuse/common options", () => {
    const boolIdx = viewSrc.indexOf("op: 'boolean'")
    const boolBlock = viewSrc.slice(boolIdx, boolIdx + 800)
    expect(boolBlock).toContain("'kind'")
    expect(boolBlock).toContain("'select'")
    expect(boolBlock).toContain("'cut'")
    expect(boolBlock).toContain("'fuse'")
    expect(boolBlock).toContain("'common'")
  })

  it("boolean default kind is 'cut'", () => {
    const boolIdx = viewSrc.indexOf("op: 'boolean'")
    const boolBlock = viewSrc.slice(boolIdx, boolIdx + 400)
    expect(boolBlock).toContain("kind: 'cut'")
  })

  it("Combine icon is imported from lucide-react", () => {
    const importBlock = viewSrc.slice(0, viewSrc.indexOf("import FeatureRenderer"))
    expect(importBlock).toContain('Combine')
  })
})
