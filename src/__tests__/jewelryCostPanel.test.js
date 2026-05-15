// jewelryCostPanel.test.js — unit tests for JewelryCostPanel data model
// and cost math.
//
// No React rendering required. We test the pure-JS model logic copied from
// JewelryCostPanel.jsx, matching the Python model in metal_cost.py.

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// ---------------------------------------------------------------------------
// Source inspection helpers
// ---------------------------------------------------------------------------

const panelSrc = readFileSync(
  path.resolve(__dirname, '../components/JewelryCostPanel.jsx'), 'utf8',
)

const apiSrc = readFileSync(
  path.resolve(__dirname, '../lib/api.js'), 'utf8',
)

const llmDocSrc = (() => {
  try {
    return readFileSync(
      path.resolve(__dirname, '../../packages/kerf-chat/llm_docs/jewelry_metal_cost.md'), 'utf8',
    )
  } catch { return '' }
})()

// ---------------------------------------------------------------------------
// Pure-JS cost model (mirrors JewelryCostPanel.jsx)
// ---------------------------------------------------------------------------

const GRAMS_PER_DWT = 1.55517384
const GRAMS_PER_OZT = 31.1034768

const DENSITY = {
  '10k_yellow': 11.57, '14k_yellow': 13.07, '18k_yellow': 15.58,
  '22k_yellow': 17.80, '24k_yellow': 19.32,
  '10k_white':  11.61, '14k_white':  13.25, '18k_white':  15.60,
  '10k_rose':   11.59, '14k_rose':   13.20, '18k_rose':   15.45,
  platinum_950: 21.40, palladium_950: 11.00,
  sterling_925: 10.36, fine_silver:   10.49,
  titanium:     4.51,  brass:         8.53,  bronze: 8.78,
}

function localEstimate(volumeMm3, metalKey, pricePerGram = 0, labor = 0, finishing = 0, allowancePct = 15) {
  const d = DENSITY[metalKey]
  if (!d || volumeMm3 <= 0) return null
  const netG   = d * (volumeMm3 / 1000)
  const grossG = netG * (1 + allowancePct / 100)
  const metalCost = grossG * pricePerGram
  const total = metalCost + labor + finishing
  return {
    net_grams:   netG,
    net_dwt:     netG / GRAMS_PER_DWT,
    net_ozt:     netG / GRAMS_PER_OZT,
    gross_grams: grossG,
    gross_dwt:   grossG / GRAMS_PER_DWT,
    gross_ozt:   grossG / GRAMS_PER_OZT,
    metal_cost:  metalCost,
    labor,
    finishing,
    total_cost:  total,
    allowance_pct: allowancePct,
  }
}

// ---------------------------------------------------------------------------
// Helper: approximate equality
// ---------------------------------------------------------------------------

function near(a, b, rel = 1e-4) {
  if (b === 0) return Math.abs(a) < 1e-10
  return Math.abs(a - b) / Math.abs(b) < rel
}

// ---------------------------------------------------------------------------
// 1. Density table sanity
// ---------------------------------------------------------------------------

describe('DENSITY table', () => {
  it('has positive densities for all metals', () => {
    for (const [k, v] of Object.entries(DENSITY)) {
      expect(v).toBeGreaterThan(0)
    }
  })

  it('platinum_950 is heavier than 18k_yellow', () => {
    expect(DENSITY.platinum_950).toBeGreaterThan(DENSITY['18k_yellow'])
  })

  it('sterling_925 density is ~10.36', () => {
    expect(DENSITY.sterling_925).toBeCloseTo(10.36, 1)
  })

  it('24k_yellow (pure gold) density ~19.32', () => {
    expect(DENSITY['24k_yellow']).toBeCloseTo(19.32, 1)
  })

  it('gold karat density increases with purity', () => {
    const d = (k) => DENSITY[k]
    expect(d('10k_yellow')).toBeLessThan(d('14k_yellow'))
    expect(d('14k_yellow')).toBeLessThan(d('18k_yellow'))
    expect(d('18k_yellow')).toBeLessThan(d('22k_yellow'))
    expect(d('22k_yellow')).toBeLessThan(d('24k_yellow'))
  })
})

// ---------------------------------------------------------------------------
// 2. Unit conversion constants
// ---------------------------------------------------------------------------

describe('Unit conversion constants', () => {
  it('GRAMS_PER_DWT matches NIST value', () => {
    expect(GRAMS_PER_DWT).toBeCloseTo(1.55517384, 6)
  })

  it('GRAMS_PER_OZT matches NIST value', () => {
    expect(GRAMS_PER_OZT).toBeCloseTo(31.1034768, 5)
  })

  it('20 dwt == 1 ozt', () => {
    expect(20 * GRAMS_PER_DWT).toBeCloseTo(GRAMS_PER_OZT, 6)
  })
})

// ---------------------------------------------------------------------------
// 3. Weight math
// ---------------------------------------------------------------------------

describe('localEstimate — weight', () => {
  it('1 cm³ (1000 mm³) of sterling silver ≈ 10.36 g', () => {
    const r = localEstimate(1000, 'sterling_925')
    expect(r.net_grams).toBeCloseTo(10.36, 1)
  })

  it('300 mm³ of 18k_yellow ≈ 4.674 g', () => {
    const r = localEstimate(300, '18k_yellow')
    expect(r.net_grams).toBeCloseTo(4.674, 2)
  })

  it('dwt is grams / GRAMS_PER_DWT', () => {
    const r = localEstimate(500, '14k_yellow')
    expect(r.net_dwt).toBeCloseTo(r.net_grams / GRAMS_PER_DWT, 5)
  })

  it('ozt is grams / GRAMS_PER_OZT', () => {
    const r = localEstimate(500, '14k_yellow')
    expect(r.net_ozt).toBeCloseTo(r.net_grams / GRAMS_PER_OZT, 5)
  })

  it('unknown metal returns null', () => {
    expect(localEstimate(1000, 'unobtanium')).toBeNull()
  })

  it('zero volume returns null', () => {
    expect(localEstimate(0, '14k_yellow')).toBeNull()
  })

  it('negative volume returns null', () => {
    expect(localEstimate(-100, '14k_yellow')).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// 4. Casting allowance
// ---------------------------------------------------------------------------

describe('localEstimate — casting allowance', () => {
  it('default 15% allowance: gross = net * 1.15', () => {
    const r = localEstimate(1000, '14k_yellow', 0, 0, 0, 15)
    expect(r.gross_grams).toBeCloseTo(r.net_grams * 1.15, 5)
  })

  it('0% allowance: gross == net', () => {
    const r = localEstimate(1000, '14k_yellow', 0, 0, 0, 0)
    expect(r.gross_grams).toBeCloseTo(r.net_grams, 5)
  })

  it('20% allowance: gross = net * 1.20', () => {
    const r = localEstimate(1000, '14k_yellow', 0, 0, 0, 20)
    expect(r.gross_grams).toBeCloseTo(r.net_grams * 1.20, 5)
  })

  it('allowance_pct stored in result', () => {
    const r = localEstimate(1000, '14k_yellow', 0, 0, 0, 12)
    expect(r.allowance_pct).toBe(12)
  })
})

// ---------------------------------------------------------------------------
// 5. Cost math
// ---------------------------------------------------------------------------

describe('localEstimate — cost', () => {
  it('metal_cost = gross_grams * price_per_gram', () => {
    const r = localEstimate(1000, '18k_yellow', 38, 0, 0)
    expect(r.metal_cost).toBeCloseTo(r.gross_grams * 38, 4)
  })

  it('total_cost = metal_cost + labor + finishing', () => {
    const r = localEstimate(300, '18k_yellow', 38, 80, 20)
    expect(r.total_cost).toBeCloseTo(r.metal_cost + r.labor + r.finishing, 4)
  })

  it('zero price gives zero metal_cost', () => {
    const r = localEstimate(1000, 'platinum_950', 0, 0, 0)
    expect(r.metal_cost).toBe(0)
  })

  it('worked example: 300 mm³ 18k yellow at $38/g + $80 labor + $20 finishing', () => {
    const r = localEstimate(300, '18k_yellow', 38, 80, 20)
    // net ≈ 4.674g, gross ≈ 5.375g, metal_cost ≈ $204.26, total ≈ $304.26
    expect(r.net_grams).toBeCloseTo(4.674, 2)
    expect(r.gross_grams).toBeCloseTo(5.375, 2)
    expect(r.metal_cost).toBeCloseTo(r.gross_grams * 38, 2)
    expect(r.total_cost).toBeCloseTo(r.metal_cost + 80 + 20, 2)
  })

  it('platinum heavier and costlier than sterling for same volume and price', () => {
    const pt  = localEstimate(1000, 'platinum_950', 1)
    const ag  = localEstimate(1000, 'sterling_925', 1)
    expect(pt.net_grams).toBeGreaterThan(ag.net_grams)
    expect(pt.metal_cost).toBeGreaterThan(ag.metal_cost)
  })
})

// ---------------------------------------------------------------------------
// 6. JewelryCostPanel.jsx source checks
// ---------------------------------------------------------------------------

describe('JewelryCostPanel.jsx — component source', () => {
  it('file exists and is non-empty', () => {
    expect(panelSrc.length).toBeGreaterThan(0)
  })

  it('imports Scale icon from lucide-react', () => {
    expect(panelSrc).toContain('Scale')
    expect(panelSrc).toContain('lucide-react')
  })

  it('imports api from lib/api.js', () => {
    expect(panelSrc).toContain("from '../lib/api.js'")
  })

  it('calls api.jewelryMetalCost', () => {
    expect(panelSrc).toContain('api.jewelryMetalCost')
  })

  it('exports default JewelryCostPanel function', () => {
    expect(panelSrc).toContain('export default function JewelryCostPanel')
  })

  it('includes volume_mm3 input', () => {
    expect(panelSrc).toContain('volumeMm3')
  })

  it('includes casting allowance input', () => {
    expect(panelSrc).toContain('allowancePct')
  })

  it('displays net weight in grams, dwt, and ozt', () => {
    expect(panelSrc).toContain('net_grams')
    expect(panelSrc).toContain('net_dwt')
    expect(panelSrc).toContain('net_ozt')
  })

  it('displays gross casting weight', () => {
    expect(panelSrc).toContain('gross_grams')
  })

  it('renders metal selector with gold options', () => {
    expect(panelSrc).toContain('18k_yellow')
    expect(panelSrc).toContain('platinum_950')
    expect(panelSrc).toContain('sterling_925')
  })

  it('renders labor and finishing inputs', () => {
    expect(panelSrc).toContain('labor')
    expect(panelSrc).toContain('finishing')
  })

  it('includes multi-metal comparison table component', () => {
    expect(panelSrc).toContain('CompareTable')
  })

  it('has DENSITY table with all key metals', () => {
    const denseIdx = panelSrc.indexOf('const DENSITY')
    const block = panelSrc.slice(denseIdx, denseIdx + 2000)
    for (const key of ['18k_yellow', 'platinum_950', 'sterling_925', 'titanium']) {
      expect(block).toContain(key)
    }
  })
})

// ---------------------------------------------------------------------------
// 7. api.js jewelryMetalCost entry
// ---------------------------------------------------------------------------

describe('api.js — jewelryMetalCost', () => {
  it('method exists in api object', () => {
    expect(apiSrc).toContain('jewelryMetalCost')
  })

  it('calls the /jewelry/metal-cost endpoint', () => {
    const idx = apiSrc.indexOf('jewelryMetalCost')
    const block = apiSrc.slice(idx, idx + 200)
    expect(block).toContain('jewelry/metal-cost')
  })

  it('uses POST method', () => {
    const idx = apiSrc.indexOf('jewelryMetalCost')
    const block = apiSrc.slice(idx, idx + 200)
    expect(block).toContain("'POST'")
  })
})

// ---------------------------------------------------------------------------
// 8. LLM doc
// ---------------------------------------------------------------------------

describe('LLM doc jewelry_metal_cost.md', () => {
  it('file exists', () => {
    expect(llmDocSrc.length).toBeGreaterThan(0)
  })

  it('documents the jewelry_metal_cost tool name', () => {
    expect(llmDocSrc).toContain('jewelry_metal_cost')
  })

  it('documents dwt conversion', () => {
    expect(llmDocSrc).toContain('dwt')
    expect(llmDocSrc).toContain('1.55517384')
  })

  it('documents troy ounce conversion', () => {
    expect(llmDocSrc).toContain('31.1034768')
  })

  it('documents casting allowance rationale', () => {
    expect(llmDocSrc).toContain('casting')
    expect(llmDocSrc).toContain('sprue')
  })

  it('includes worked example', () => {
    expect(llmDocSrc).toContain('300')
    expect(llmDocSrc).toContain('18k')
  })

  it('documents density table with platinum_950', () => {
    expect(llmDocSrc).toContain('platinum_950')
    expect(llmDocSrc).toContain('21.40')
  })
})

// ---------------------------------------------------------------------------
// 9. Python plugin registration
// ---------------------------------------------------------------------------

describe('Python plugin — tool module registration', () => {
  const pluginSrc = readFileSync(
    path.resolve(__dirname, '../../packages/kerf-cad-core/src/kerf_cad_core/plugin.py'),
    'utf8',
  )

  it("_TOOL_MODULES includes 'kerf_cad_core.jewelry.tool_metal_cost'", () => {
    expect(pluginSrc).toContain('kerf_cad_core.jewelry.tool_metal_cost')
  })
})
