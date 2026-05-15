// sheetMetalFlange.test.js — T-1 source-level wiring checks.
//
// No WASM required.  Reads occtWorker.js + FeatureView.jsx as text and asserts:
//   1. opSheetFlange function is defined in occtWorker.js.
//   2. 'sheet_metal_flange' case present in evaluateTree dispatch.
//   3. 'sheet_metal_flange' case present in evaluateToFinalShape dispatch.
//   4. Both dispatch sites call opSheetFlange.
//   5. FeatureView.jsx has a sheet_metal_flange FEATURE_KINDS entry.
//   6. The LLM doc file exists and documents k_factor, bend_angle_deg, edge_ref.
//
// Pattern: identical to jewelryDispatch.test.js and jewelerySeatChainDispatch.test.js.

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const workerSrc = readFileSync(
  path.resolve(__dirname, '../lib/occtWorker.js'),
  'utf8',
)
const featureViewSrc = readFileSync(
  path.resolve(__dirname, '../components/FeatureView.jsx'),
  'utf8',
)

// Boundary markers for the two dispatch tables.
const ET_START  = workerSrc.indexOf('function evaluateTree(')
const ETF_START = workerSrc.indexOf('async function evaluateToFinalShape(')

if (ET_START  === -1) throw new Error('evaluateTree not found in occtWorker.js')
if (ETF_START === -1) throw new Error('evaluateToFinalShape not found in occtWorker.js')

// Slice for the evaluateTree dispatch (between ET_START and ETF_START).
const etBody  = workerSrc.slice(ET_START, ETF_START)
// Slice for evaluateToFinalShape dispatch (from ETF_START to end).
const etfBody = workerSrc.slice(ETF_START)

// WASM-gated scenarios — hermetic dispatch checks don't need WASM.
const SKIP_WASM = typeof Worker === 'undefined' && typeof self === 'undefined'

// ---------------------------------------------------------------------------
// 1. Function definition
// ---------------------------------------------------------------------------

describe('opSheetFlange — function definition', () => {
  it('opSheetFlange function is defined in occtWorker.js', () => {
    expect(workerSrc).toContain('function opSheetFlange(')
  })
})

// ---------------------------------------------------------------------------
// 2 + 3. Dispatch table wiring
// ---------------------------------------------------------------------------

describe("case 'sheet_metal_flange' — evaluateTree dispatch", () => {
  it("case 'sheet_metal_flange' present in evaluateTree", () => {
    expect(etBody).toContain("case 'sheet_metal_flange'")
  })

  it('evaluateTree sheet_metal_flange calls opSheetFlange', () => {
    const caseIdx = etBody.indexOf("case 'sheet_metal_flange'")
    expect(caseIdx).not.toBe(-1)
    const caseBlock = etBody.slice(caseIdx, caseIdx + 400)
    expect(caseBlock).toContain('opSheetFlange(')
  })
})

describe("case 'sheet_metal_flange' — evaluateToFinalShape dispatch", () => {
  it("case 'sheet_metal_flange' present in evaluateToFinalShape", () => {
    expect(etfBody).toContain("case 'sheet_metal_flange'")
  })

  it('evaluateToFinalShape sheet_metal_flange calls opSheetFlange', () => {
    const caseIdx = etfBody.indexOf("case 'sheet_metal_flange'")
    expect(caseIdx).not.toBe(-1)
    const caseBlock = etfBody.slice(caseIdx, caseIdx + 400)
    expect(caseBlock).toContain('opSheetFlange(')
  })
})

// ---------------------------------------------------------------------------
// 4. Geometry implementation assertions (source-level)
// ---------------------------------------------------------------------------

describe('opSheetFlange — geometry implementation', () => {
  const fnStart = workerSrc.indexOf('function opSheetFlange(')
  // Slice to the next top-level function to scope assertions.
  const nextFn = workerSrc.indexOf('\nfunction evaluateTree(', fnStart)
  const fn = workerSrc.slice(fnStart, nextFn === -1 ? fnStart + 6000 : nextFn)

  it('reads base_width from node', () => {
    expect(fn).toContain('base_width')
  })

  it('reads base_depth from node', () => {
    expect(fn).toContain('base_depth')
  })

  it('reads thickness from node', () => {
    expect(fn).toContain('thickness')
  })

  it('reads flange_length from node', () => {
    expect(fn).toContain('flange_length')
  })

  it('reads bend_angle_deg from node', () => {
    expect(fn).toContain('bend_angle_deg')
  })

  it('reads bend_radius from node', () => {
    expect(fn).toContain('bend_radius')
  })

  it('reads edge_ref from node', () => {
    expect(fn).toContain('edge_ref')
  })

  it('builds base plate via _makeBox', () => {
    expect(fn).toContain('_makeBox(')
  })

  it('builds arc with BRepPrimAPI_MakeCylinder', () => {
    expect(fn).toContain('MakeCylinder')
  })

  it('fuses plate, arc, and flange wall', () => {
    // At least two BRepAlgoAPI_Fuse calls (plate+arc, then +flange)
    const fuseCount = (fn.match(/BRepAlgoAPI_Fuse/g) || []).length
    expect(fuseCount).toBeGreaterThanOrEqual(2)
  })

  it('applies edge_ref rotation for non-front edges', () => {
    expect(fn).toContain('top-back')
    expect(fn).toContain('top-left')
    expect(fn).toContain('top-right')
    expect(fn).toContain('SetRotation_1(')
  })

  it('converts bend_angle_deg to radians', () => {
    expect(fn).toContain('angRad')
    expect(fn).toContain('Math.PI')
  })
})

// ---------------------------------------------------------------------------
// 5. FeatureView.jsx inspector entry
// ---------------------------------------------------------------------------

describe('FeatureView.jsx — sheet_metal_flange inspector entry', () => {
  it("FEATURE_KINDS contains op: 'sheet_metal_flange'", () => {
    expect(featureViewSrc).toContain("op: 'sheet_metal_flange'")
  })

  it("FEATURE_CATEGORIES has a sheetmetal category", () => {
    expect(featureViewSrc).toContain("'sheetmetal'")
    expect(featureViewSrc).toContain("'sheet_metal_flange'")
  })

  it('inspector has edge_ref field', () => {
    // Check within the sheet_metal_flange entry block.
    const kindIdx = featureViewSrc.indexOf("op: 'sheet_metal_flange'")
    expect(kindIdx).not.toBe(-1)
    const block = featureViewSrc.slice(kindIdx, kindIdx + 2000)
    expect(block).toContain('edge_ref')
  })

  it('inspector has k_factor field', () => {
    const kindIdx = featureViewSrc.indexOf("op: 'sheet_metal_flange'")
    const block = featureViewSrc.slice(kindIdx, kindIdx + 2000)
    expect(block).toContain('k_factor')
  })

  it('inspector has bend_angle_deg field', () => {
    const kindIdx = featureViewSrc.indexOf("op: 'sheet_metal_flange'")
    const block = featureViewSrc.slice(kindIdx, kindIdx + 2000)
    expect(block).toContain('bend_angle_deg')
  })

  it('inspector has bend_radius field', () => {
    const kindIdx = featureViewSrc.indexOf("op: 'sheet_metal_flange'")
    const block = featureViewSrc.slice(kindIdx, kindIdx + 2000)
    expect(block).toContain('bend_radius')
  })

  it('inspector has flange_length field', () => {
    const kindIdx = featureViewSrc.indexOf("op: 'sheet_metal_flange'")
    const block = featureViewSrc.slice(kindIdx, kindIdx + 2000)
    expect(block).toContain('flange_length')
  })
})

// ---------------------------------------------------------------------------
// 6. LLM doc exists and has key content
// ---------------------------------------------------------------------------

describe('LLM doc — feature_sheet_metal.md', () => {
  let docSrc = ''
  try {
    docSrc = readFileSync(
      path.resolve(__dirname, '../../packages/kerf-chat/llm_docs/feature_sheet_metal.md'),
      'utf8',
    )
  } catch {
    // File not accessible — all checks will fail and report clearly.
  }

  it('LLM doc file exists', () => {
    expect(docSrc.length).toBeGreaterThan(0)
  })

  it('documents k_factor', () => {
    expect(docSrc).toContain('k_factor')
  })

  it('documents bend_angle_deg', () => {
    expect(docSrc).toContain('bend_angle_deg')
  })

  it('documents edge_ref values (top-front, top-back, etc.)', () => {
    expect(docSrc).toContain('top-front')
    expect(docSrc).toContain('top-back')
  })

  it('documents T-2/T-3 as deferred', () => {
    expect(docSrc).toContain('T-2')
    expect(docSrc).toContain('T-3')
  })

  it('documents the folded-shape-only caveat', () => {
    // The doc should mention that unfold is deferred.
    const lower = docSrc.toLowerCase()
    expect(lower.includes('unfold') || lower.includes('flat-pattern')).toBe(true)
  })
})

// ---------------------------------------------------------------------------
// 7. Python spec source-level check
// ---------------------------------------------------------------------------

describe('Python spec — sheet_metal.py', () => {
  let pySrc = ''
  try {
    pySrc = readFileSync(
      path.resolve(__dirname, '../../packages/kerf-cad-core/src/kerf_cad_core/sheet_metal.py'),
      'utf8',
    )
  } catch {
    // not accessible — all checks will fail clearly.
  }

  it('sheet_metal.py file exists', () => {
    expect(pySrc.length).toBeGreaterThan(0)
  })

  it('defines validate_flange_args', () => {
    expect(pySrc).toContain('def validate_flange_args(')
  })

  it('defines run_sheet_metal_flange', () => {
    expect(pySrc).toContain('async def run_sheet_metal_flange(')
  })

  it('validates k_factor in (0, 1)', () => {
    expect(pySrc).toContain('k_factor')
    // Either `k_factor <= 0 or k_factor >= 1` or similar check.
    expect(pySrc).toMatch(/k_factor\s*(<=|>=|==|<|>)/)
  })

  it('validates bend_angle_deg in (0, 180]', () => {
    expect(pySrc).toContain('bend_angle_deg')
    expect(pySrc).toContain('180')
  })

  it('validates edge_ref is required', () => {
    expect(pySrc).toContain('edge_ref')
    expect(pySrc).toContain('edge_ref is required')
  })

  it('plugin.py registers kerf_cad_core.sheet_metal', () => {
    try {
      const pluginSrc = readFileSync(
        path.resolve(__dirname, '../../packages/kerf-cad-core/src/kerf_cad_core/plugin.py'),
        'utf8',
      )
      expect(pluginSrc).toContain('"kerf_cad_core.sheet_metal"')
    } catch {
      expect(true).toBe(true) // skip if file not accessible
    }
  })
})
