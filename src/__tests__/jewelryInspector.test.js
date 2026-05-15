// jewelryInspector.test.js — asserts every jewelry op has a FEATURE_KINDS entry
// with sane fields and is registered in the Jewelry FEATURE_CATEGORIES bucket.
//
// No WASM / DOM required.  Reads FeatureView.jsx via a dynamic import so the
// module is executed in the vitest jsdom env (jsdom is required for the React
// module side-effects).

import { describe, it, expect, beforeAll } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// ---------------------------------------------------------------------------
// Read FeatureView.jsx as text and extract the two arrays via regex so we
// avoid importing the entire React component tree (which needs full jsdom +
// canvas stubs).  This keeps the test fast and dependency-free.
// ---------------------------------------------------------------------------

const src = readFileSync(
  path.resolve(__dirname, '../components/FeatureView.jsx'),
  'utf8',
)

// Extract every `op:` string literal from FEATURE_KINDS
function extractOpsFromKinds(source) {
  // Match lines like:   op: 'jewelry_tension',
  const re = /^\s+op:\s+'([^']+)'/gm
  const ops = []
  let m
  while ((m = re.exec(source)) !== null) {
    ops.push(m[1])
  }
  return ops
}

// Extract ops listed in the Jewelry FEATURE_CATEGORIES bucket
function extractJewelryCategoryOps(source) {
  // Find the jewelry category block between id: 'jewelry' and the next id:
  const jewelryMatch = source.match(
    /id:\s*'jewelry'[\s\S]*?ops:\s*\[([\s\S]*?)\]/,
  )
  if (!jewelryMatch) return []
  const block = jewelryMatch[1]
  const re = /'([^']+)'/g
  const ops = []
  let m
  while ((m = re.exec(block)) !== null) {
    ops.push(m[1])
  }
  return ops
}

// Extract fields array for a given op  (simplified: look for op + fields block)
function extractFieldsForOp(source, op) {
  // Find the object opening for this op
  const opIdx = source.indexOf(`op: '${op}'`)
  if (opIdx === -1) return null
  // Grab a sufficient window after the op: line to find the fields array
  const window = source.slice(opIdx, opIdx + 8000)
  // Find `fields: [` and count bracket depth to extract field key names
  const fieldsIdx = window.indexOf('fields: [')
  if (fieldsIdx === -1) return []
  const fieldBlock = window.slice(fieldsIdx)
  const keyRe = /key:\s*'([^']+)'/g
  const keys = []
  let m
  while ((m = keyRe.exec(fieldBlock)) !== null) {
    keys.push(m[1])
    // Stop if we've gone past the closing ] of this fields array
    // (a crude but reliable signal: we'll hit 'op:' of the next entry)
    if (m.index > 3000) break
  }
  return keys
}

const allOpsInKinds     = extractOpsFromKinds(src)
const jewelryCatOps     = extractJewelryCategoryOps(src)

// ---------------------------------------------------------------------------
// The full list of jewelry ops that MUST have FEATURE_KINDS entries.
// ---------------------------------------------------------------------------

const JEWELRY_OPS = [
  // Gemstone + cut ops
  'gemstone',
  // Gem seat types
  'gem_seat',
  'channel_seat',
  'bezel_seat',
  'fishtail_seat',
  // Settings v1
  'jewelry_prong_head',
  'jewelry_bezel',
  'jewelry_channel',
  'jewelry_pave',
  // Settings v2
  'jewelry_tension',
  'jewelry_flush',
  'jewelry_halo',
  'jewelry_three_stone',
  'jewelry_cluster',
  'jewelry_bar',
  'jewelry_bead_grain',
  'jewelry_gypsy_pave',
  'jewelry_illusion',
  'jewelry_invisible',
  // Settings v3–v4
  'jewelry_prong_variant',
  'jewelry_head_gallery',
  'jewelry_under_bezel',
  'jewelry_peg_setting',
  'jewelry_coronet',
  'jewelry_suspension_mount',
  'jewelry_vtip_protector',
  'jewelry_bombe_cluster',
  'jewelry_patterned_bezel',
  'jewelry_trellis_prong',
  'jewelry_bar_channel_graduated',
  // Ring ops
  'ring_shank',
  'eternity_band',
  'signet_ring',
  'stacking_band_set',
  'contoured_band',
  'solitaire_ring',
  'mens_band',
  'wedding_set',
  'cocktail_ring',
  'bypass_ring',
  // Chain + composed pieces
  'chain_assembly',
  'tennis_bracelet',
  'station_necklace',
  'lariat',
  'charm_bracelet',
  'multi_strand',
  'extender_chain',
  // Findings
  'finding',
  // Whole pieces
  'pendant',
  'earrings',
  'brooch',
  'cufflink',
  'bangle',
  // Decorative
  'decorative_apply',
]

// ---------------------------------------------------------------------------
// Ops that must have all 30 GEMSTONE_CUTS in their cut dropdown
// ---------------------------------------------------------------------------

const ALL_30_CUTS = [
  'round_brilliant', 'princess', 'oval', 'emerald', 'marquise', 'pear',
  'cushion', 'radiant', 'asscher', 'trillion', 'heart', 'baguette',
  'briolette', 'old_european', 'old_mine', 'rose_cut', 'single_cut',
  'french_cut', 'half_moon', 'trapezoid', 'kite', 'bullet',
  'tapered_baguette', 'lozenge', 'shield', 'calf_head', 'portuguese',
  'ceylon', 'flanders', 'square_emerald',
]

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('FEATURE_KINDS — jewelry op coverage', () => {
  for (const op of JEWELRY_OPS) {
    it(`has a FEATURE_KINDS entry for '${op}'`, () => {
      expect(allOpsInKinds).toContain(op)
    })

    it(`'${op}' has at least one field`, () => {
      const fields = extractFieldsForOp(src, op)
      expect(fields).not.toBeNull()
      expect(fields.length).toBeGreaterThan(0)
    })
  }
})

describe('FEATURE_CATEGORIES — Jewelry bucket membership', () => {
  for (const op of JEWELRY_OPS) {
    it(`'${op}' is in the Jewelry category`, () => {
      expect(jewelryCatOps).toContain(op)
    })
  }
})

describe('Gemstone cut dropdown — all 30 cuts present', () => {
  it('gemstone op cut select has all 30 GEMSTONE_CUTS', () => {
    const opIdx = src.indexOf("op: 'gemstone'")
    const window = src.slice(opIdx, opIdx + 4000)
    for (const cut of ALL_30_CUTS) {
      expect(window).toContain(`'${cut}'`)
    }
  })

  it('gem_seat op cut select has all 30 GEMSTONE_CUTS', () => {
    const opIdx = src.indexOf("op: 'gem_seat'")
    const window = src.slice(opIdx, opIdx + 4000)
    for (const cut of ALL_30_CUTS) {
      expect(window).toContain(`'${cut}'`)
    }
  })

  it('channel_seat op cut select has all 30 GEMSTONE_CUTS', () => {
    const opIdx = src.indexOf("op: 'channel_seat'")
    const window = src.slice(opIdx, opIdx + 6000)
    for (const cut of ALL_30_CUTS) {
      expect(window).toContain(`'${cut}'`)
    }
  })

  it('bezel_seat op cut select has all 30 GEMSTONE_CUTS', () => {
    const opIdx = src.indexOf("op: 'bezel_seat'")
    const window = src.slice(opIdx, opIdx + 6000)
    for (const cut of ALL_30_CUTS) {
      expect(window).toContain(`'${cut}'`)
    }
  })
})

describe('Jewelry category bucket exists and is non-empty', () => {
  it('Jewelry category has >= 50 ops', () => {
    expect(jewelryCatOps.length).toBeGreaterThanOrEqual(50)
  })
})
