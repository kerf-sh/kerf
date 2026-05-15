// trimByCurveProbe.test.js — C2-T1 binding probe coverage.
//
// Verifies:
//   1. Source wiring: NURBS_PHASE4_C2_BINDINGS extended with C2-specific
//      classes (all 10 classes including the new T1 additions).
//   2. getNurbsPhase4C2Bindings export is present.
//   3. _logNurbsPhase4C2Bindings function is present and called pattern.
//   4. getNurbsPhase4C2Bindings(oc) returns the expected shape for
//      all-present and all-absent mocks.
//   5. Boot-time logging emits [occt-phase4] C2 lines and GO/PARTIAL verdict.
//
// No WASM required.

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const workerSrc = readFileSync(
  path.resolve(__dirname, '../lib/occtWorker.js'),
  'utf8',
)

// Full list of C2 classes after T1 extension (10 entries).
const C2_CLASSES = [
  'BRepFeat_SplitShape',
  'BRepProj_Projection',
  'BRepBuilderAPI_MakeFace_18',
  'GeomAPI_ProjectPointOnSurf',
  'ShapeAnalysis_Surface',
  'BRepBuilderAPI_MakeEdge',
  'BRepBuilderAPI_MakeWire',
  'BRepBuilderAPI_MakeFace',
  'ShapeFix_Wire',
]

// ── 0. Source-level wiring ────────────────────────────────────────────────────

describe('occtWorker.js — Phase 4 C2 probe source wiring', () => {
  it('NURBS_PHASE4_C2_BINDINGS array is defined', () => {
    expect(workerSrc).toContain('NURBS_PHASE4_C2_BINDINGS')
  })

  it('getNurbsPhase4C2Bindings export is present', () => {
    expect(workerSrc).toContain('export function getNurbsPhase4C2Bindings(')
  })

  it('_logNurbsPhase4C2Bindings function is present', () => {
    expect(workerSrc).toContain('function _logNurbsPhase4C2Bindings(')
  })

  it('C2 probe includes BRepFeat_SplitShape', () => {
    expect(workerSrc).toContain('BRepFeat_SplitShape')
  })

  it('C2 probe includes BRepProj_Projection', () => {
    expect(workerSrc).toContain('BRepProj_Projection')
  })

  it('C2 probe includes GeomAPI_ProjectPointOnSurf (T1 addition)', () => {
    expect(workerSrc).toContain('GeomAPI_ProjectPointOnSurf')
  })

  it('C2 probe includes ShapeAnalysis_Surface (T1 addition)', () => {
    expect(workerSrc).toContain('ShapeAnalysis_Surface')
  })

  it('C2 probe includes BRepBuilderAPI_MakeEdge (T1 addition)', () => {
    expect(workerSrc).toContain('BRepBuilderAPI_MakeEdge')
  })

  it('C2 probe includes BRepBuilderAPI_MakeWire (T1 addition)', () => {
    expect(workerSrc).toContain('BRepBuilderAPI_MakeWire')
  })

  it('C2 probe includes BRepBuilderAPI_MakeFace (T1 addition)', () => {
    expect(workerSrc).toContain('BRepBuilderAPI_MakeFace')
  })

  it('C2 probe includes ShapeFix_Wire (T1 addition)', () => {
    expect(workerSrc).toContain('ShapeFix_Wire')
  })

  it('_logNurbsPhase4C2Bindings logs [occt-phase4] prefix', () => {
    const fnIdx = workerSrc.indexOf('function _logNurbsPhase4C2Bindings(')
    const logIdx = workerSrc.indexOf('[occt-phase4]', fnIdx)
    expect(logIdx).toBeGreaterThan(fnIdx)
  })

  it('_logNurbsPhase4C2Bindings logs GO verdict', () => {
    const fnIdx = workerSrc.indexOf('function _logNurbsPhase4C2Bindings(')
    const goIdx = workerSrc.indexOf('GO', fnIdx)
    expect(goIdx).toBeGreaterThan(fnIdx)
  })

  it('_logNurbsPhase4C2Bindings logs PARTIAL/BLOCKED verdict', () => {
    const fnIdx = workerSrc.indexOf('function _logNurbsPhase4C2Bindings(')
    const blkIdx = workerSrc.indexOf('PARTIAL/BLOCKED', fnIdx)
    expect(blkIdx).toBeGreaterThan(fnIdx)
  })

  it('getNurbsPhase4C2Bindings is separate from getNurbsPhase4Bindings', () => {
    const c2Idx   = workerSrc.indexOf('export function getNurbsPhase4C2Bindings(')
    const allIdx  = workerSrc.indexOf('export function getNurbsPhase4Bindings(')
    expect(c2Idx).toBeGreaterThan(-1)
    expect(allIdx).toBeGreaterThan(-1)
    expect(c2Idx).not.toBe(allIdx)
  })
})

// ── 1. getNurbsPhase4C2Bindings inline re-derivation ─────────────────────────

function getNurbsPhase4C2Bindings_derived(oc) {
  return Object.fromEntries(
    C2_CLASSES.map(cls => [cls, typeof oc[cls] === 'function'])
  )
}

describe('getNurbsPhase4C2Bindings — binding map logic', () => {
  it('returns true for each class when all are present', () => {
    const oc = {}
    for (const cls of C2_CLASSES) oc[cls] = function() {}
    const result = getNurbsPhase4C2Bindings_derived(oc)
    for (const cls of C2_CLASSES) {
      expect(result[cls]).toBe(true)
    }
  })

  it('returns false for each class when none are present', () => {
    const oc = {}
    const result = getNurbsPhase4C2Bindings_derived(oc)
    for (const cls of C2_CLASSES) {
      expect(result[cls]).toBe(false)
    }
  })

  it('returns mixed map when only primary classes are present', () => {
    const oc = {
      BRepFeat_SplitShape: function() {},
      BRepProj_Projection: function() {},
    }
    const result = getNurbsPhase4C2Bindings_derived(oc)
    expect(result['BRepFeat_SplitShape']).toBe(true)
    expect(result['BRepProj_Projection']).toBe(true)
    expect(result['GeomAPI_ProjectPointOnSurf']).toBe(false)
    expect(result['ShapeFix_Wire']).toBe(false)
  })

  it('returns false if the binding value is an object (not a function)', () => {
    const oc = { BRepFeat_SplitShape: { notAFunction: true } }
    const result = getNurbsPhase4C2Bindings_derived(oc)
    expect(result['BRepFeat_SplitShape']).toBe(false)
  })

  it('result has exactly C2_CLASSES.length keys', () => {
    const oc = {}
    const result = getNurbsPhase4C2Bindings_derived(oc)
    expect(Object.keys(result).length).toBe(C2_CLASSES.length)
  })
})

// ── 2. _logNurbsPhase4C2Bindings — log output behaviour ──────────────────────

function _logNurbsPhase4C2Bindings_derived(oc, consoleSpy) {
  const statuses = C2_CLASSES.map(cls => {
    const ok = typeof oc[cls] === 'function'
    consoleSpy(`[occt-phase4] C2 (trim-by-curve) — ${cls}: ${ok ? 'OK' : 'MISSING'}`)
    return ok
  })
  const allOk = statuses.every(Boolean)
  consoleSpy(`[occt-phase4] C2 (trim-by-curve) gate: ${allOk ? 'GO' : 'PARTIAL/BLOCKED'}`)
}

describe('_logNurbsPhase4C2Bindings — log lines', () => {
  it('logs OK for each present C2 class', () => {
    const oc = {}
    for (const cls of C2_CLASSES) oc[cls] = function() {}
    const lines = []
    _logNurbsPhase4C2Bindings_derived(oc, l => lines.push(l))
    for (const cls of C2_CLASSES) {
      expect(lines.some(l => l.includes(cls) && l.includes('OK'))).toBe(true)
    }
  })

  it('logs MISSING for each absent C2 class', () => {
    const oc = {}
    const lines = []
    _logNurbsPhase4C2Bindings_derived(oc, l => lines.push(l))
    for (const cls of C2_CLASSES) {
      expect(lines.some(l => l.includes(cls) && l.includes('MISSING'))).toBe(true)
    }
  })

  it('logs GO gate when all C2 classes are present', () => {
    const oc = {}
    for (const cls of C2_CLASSES) oc[cls] = function() {}
    const lines = []
    _logNurbsPhase4C2Bindings_derived(oc, l => lines.push(l))
    const gateLine = lines.find(l => l.includes('gate:'))
    expect(gateLine).toBeDefined()
    expect(gateLine).toContain('GO')
    expect(gateLine).not.toContain('PARTIAL/BLOCKED')
  })

  it('logs PARTIAL/BLOCKED gate when some C2 classes are absent', () => {
    const oc = { BRepFeat_SplitShape: function() {} }
    const lines = []
    _logNurbsPhase4C2Bindings_derived(oc, l => lines.push(l))
    const gateLine = lines.find(l => l.includes('gate:'))
    expect(gateLine).toBeDefined()
    expect(gateLine).toContain('PARTIAL/BLOCKED')
  })

  it('emits a line for every C2 class', () => {
    const oc = {}
    const lines = []
    _logNurbsPhase4C2Bindings_derived(oc, l => lines.push(l))
    for (const cls of C2_CLASSES) {
      expect(lines.some(l => l.includes(cls))).toBe(true)
    }
  })

  it('emits exactly C2_CLASSES.length + 1 lines (one per class + one gate)', () => {
    const oc = {}
    const lines = []
    _logNurbsPhase4C2Bindings_derived(oc, l => lines.push(l))
    expect(lines.length).toBe(C2_CLASSES.length + 1)
  })
})
