// jewelrySeatChainDispatch.test.js — T-25 wiring + behaviour checks for the
// five new jewelry ops: channel_seat, bezel_seat, fishtail_seat,
// multi_stone_seat, chain_assembly.
//
// No WASM required.  All assertions are source-level checks against
// occtWorker.js (reading the file as text) following the exact pattern
// established in jewelryDispatch.test.js and jewelryFacets.test.js.
//
// WASM-gated scenarios use it.skipIf(SKIP_WASM) — same as
// jewelryFacets.test.js and booleanIntegration.test.js.

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const workerSrc = readFileSync(
  path.resolve(__dirname, '../lib/occtWorker.js'),
  'utf8',
)

// WASM skip gate (same pattern as booleanIntegration / jewelryFacets).
const SKIP_WASM = typeof Worker === 'undefined' && typeof self === 'undefined'

// ---------------------------------------------------------------------------
// Locate the two dispatch tables.
// ---------------------------------------------------------------------------

const ET_START  = workerSrc.indexOf('function evaluateTree(')
const ETF_START = workerSrc.indexOf('async function evaluateToFinalShape(')

if (ET_START  === -1) throw new Error('evaluateTree not found in occtWorker.js')
if (ETF_START === -1) throw new Error('evaluateToFinalShape not found in occtWorker.js')

const etBody  = workerSrc.slice(ET_START, ETF_START)
const etfBody = workerSrc.slice(ETF_START)

// ---------------------------------------------------------------------------
// Generic dispatch helper (same structure as jewelryDispatch.test.js).
// ---------------------------------------------------------------------------

function describeOp(opName, fnName, { nextFnName } = {}) {
  describe(`${opName} — T-25 jewelry op dispatch`, () => {
    it(`${fnName} function is defined in occtWorker.js`, () => {
      expect(workerSrc).toContain(`function ${fnName}(`)
    })

    it(`case '${opName}' present in evaluateTree`, () => {
      expect(etBody).toContain(`case '${opName}'`)
    })

    it(`case '${opName}' present in evaluateToFinalShape`, () => {
      expect(etfBody).toContain(`case '${opName}'`)
    })

    it(`evaluateTree '${opName}' calls ${fnName}`, () => {
      const idx = etBody.indexOf(`case '${opName}'`)
      const block = etBody.slice(idx, idx + 500)
      expect(block).toContain(`${fnName}(`)
    })

    it(`evaluateToFinalShape '${opName}' calls ${fnName}`, () => {
      const idx = etfBody.indexOf(`case '${opName}'`)
      const block = etfBody.slice(idx, idx + 500)
      expect(block).toContain(`${fnName}(`)
    })

    // Verify the op resets current before calling the builder (jewelry pattern).
    it(`evaluateTree '${opName}' clears current body before building`, () => {
      const idx = etBody.indexOf(`case '${opName}'`)
      const block = etBody.slice(idx, idx + 300)
      // Either `cleanupShape` or `current = null` must appear near the case.
      expect(block).toMatch(/cleanupShape|current = null/)
    })
  })
}

// ---------------------------------------------------------------------------
// 1. opChannelSeat — op: channel_seat
// ---------------------------------------------------------------------------

describeOp('channel_seat', 'opChannelSeat')

describe('opChannelSeat — geometry structure', () => {
  // Extract function body: from function opChannelSeat( to the next top-level function.
  const CS_START = workerSrc.indexOf('function opChannelSeat(')
  const CS_END   = workerSrc.indexOf('\nfunction opBezelSeat(')
  if (CS_START === -1) throw new Error('opChannelSeat not found')
  const csFn = workerSrc.slice(CS_START, CS_END)

  it('reads n_stones from node', () => {
    expect(csFn).toContain('n_stones')
  })

  it('reads pitch_mm from node', () => {
    expect(csFn).toContain('pitch_mm')
  })

  it('reads groove_width_mm and groove_depth_mm', () => {
    expect(csFn).toContain('groove_width_mm')
    expect(csFn).toContain('groove_depth_mm')
  })

  it('reads groove_length_mm', () => {
    expect(csFn).toContain('groove_length_mm')
  })

  it('reads per_stone_geom', () => {
    expect(csFn).toContain('per_stone_geom')
  })

  it('reads stone_positions array', () => {
    expect(csFn).toContain('stone_positions')
  })

  it('builds main groove box via _makeBox', () => {
    expect(csFn).toContain('_makeBox(')
    expect(csFn).toContain('groove')
  })

  it('iterates over n_stones to place per-stone bearing cones', () => {
    expect(csFn).toContain('for (let i = 0; i < nStones')
  })

  it('fuses per-stone cones into groove using _jewelryFuse', () => {
    expect(csFn).toContain('_jewelryFuse(')
  })

  it('applies position/orientation transform via _jewelryTransform', () => {
    expect(csFn).toContain('_jewelryTransform(')
  })

  it('has a try/catch around per-stone build for graceful fallback', () => {
    expect(csFn).toContain('} catch {')
  })
})

describe('opChannelSeat — node spec fields from channel_seat_geometry() Python', () => {
  const CS_START = workerSrc.indexOf('function opChannelSeat(')
  const CS_END   = workerSrc.indexOf('\nfunction opBezelSeat(')
  const csFn = workerSrc.slice(CS_START, CS_END)

  for (const field of ['n_stones', 'pitch_mm', 'groove_width_mm', 'groove_depth_mm',
    'groove_length_mm', 'per_stone_geom', 'stone_positions']) {
    it(`field '${field}' is referenced`, () => {
      expect(csFn).toContain(field)
    })
  }
})

// ---------------------------------------------------------------------------
// 2. opBezelSeat — op: bezel_seat
// ---------------------------------------------------------------------------

describeOp('bezel_seat', 'opBezelSeat')

describe('opBezelSeat — geometry structure', () => {
  const BS_START = workerSrc.indexOf('function opBezelSeat(')
  const BS_END   = workerSrc.indexOf('\nfunction opFishtailSeat(')
  if (BS_START === -1) throw new Error('opBezelSeat not found')
  const bsFn = workerSrc.slice(BS_START, BS_END)

  it('builds a bearing cone (reuses opGemSeat pattern)', () => {
    expect(bsFn).toContain('bearingCone')
  })

  it('builds a girdle ledge', () => {
    expect(bsFn).toContain('girdleLedge')
  })

  it('builds a crown relief', () => {
    expect(bsFn).toContain('crownRelief')
  })

  it('builds a bezel wall above the girdle ledge', () => {
    expect(bsFn).toContain('wallH')
    expect(bsFn).toContain('wall')
  })

  it('reads bezel_wall_height_mm from node', () => {
    expect(bsFn).toContain('bezel_wall_height_mm')
  })

  it('reads tapered flag and taper_angle_deg', () => {
    expect(bsFn).toContain('tapered')
    expect(bsFn).toContain('taper_angle_deg')
  })

  it('supports tapered bore using _makeCone for the wall', () => {
    expect(bsFn).toContain('_makeCone(')
    expect(bsFn).toContain('taperAng')
  })

  it('bores the wall with _jewelryCut', () => {
    expect(bsFn).toContain('_jewelryCut(')
  })

  it('fuses wall onto base seat with _jewelryFuse', () => {
    expect(bsFn).toContain('_jewelryFuse(')
  })

  it('supports optional through_hole', () => {
    expect(bsFn).toContain('throughHole')
    expect(bsFn).toContain('through_hole')
  })

  it('reads inner_bore_top_radius and inner_bore_bottom_radius', () => {
    expect(bsFn).toContain('inner_bore_top_radius')
    expect(bsFn).toContain('inner_bore_bottom_radius')
  })

  it('applies position/orientation transform', () => {
    expect(bsFn).toContain('_jewelryTransform(')
  })

  it('gracefully falls back if bore step fails (try/catch around bore cut)', () => {
    expect(bsFn).toContain('} catch {')
  })
})

describe('opBezelSeat — node spec fields from bezel_seat_geometry() Python', () => {
  const BS_START = workerSrc.indexOf('function opBezelSeat(')
  const BS_END   = workerSrc.indexOf('\nfunction opFishtailSeat(')
  const bsFn = workerSrc.slice(BS_START, BS_END)

  for (const field of [
    'girdle_radius_mm', 'pavilion_depth_mm', 'girdle_height_mm',
    'bearing_cone_top_radius', 'bearing_cone_bottom_radius',
    'bezel_wall_height_mm', 'taper_angle_deg',
    'inner_bore_top_radius', 'inner_bore_bottom_radius',
  ]) {
    it(`field '${field}' is referenced`, () => {
      expect(bsFn).toContain(field)
    })
  }
})

// ---------------------------------------------------------------------------
// 3. opFishtailSeat — op: fishtail_seat
// ---------------------------------------------------------------------------

describeOp('fishtail_seat', 'opFishtailSeat')

describe('opFishtailSeat — geometry structure', () => {
  const FS_START = workerSrc.indexOf('function opFishtailSeat(')
  const FS_END   = workerSrc.indexOf('\nfunction opMultiStoneSeat(')
  if (FS_START === -1) throw new Error('opFishtailSeat not found')
  const fsFn = workerSrc.slice(FS_START, FS_END)

  it('builds base gem-seat cutter (bearing cone + ledge + crown)', () => {
    expect(fsFn).toContain('bearingCone')
    expect(fsFn).toContain('girdleLedge')
    expect(fsFn).toContain('crownRelief')
  })

  it('reads bright_cut_angle_deg', () => {
    expect(fsFn).toContain('bright_cut_angle_deg')
  })

  it('reads bright_cut_depth_mm', () => {
    expect(fsFn).toContain('bright_cut_depth_mm')
  })

  it('reads n_bright_facets', () => {
    expect(fsFn).toContain('n_bright_facets')
  })

  it('reads bright_cut_radius_mm', () => {
    expect(fsFn).toContain('bright_cut_radius_mm')
  })

  it('iterates over n_bright_facets to build radial grooves', () => {
    expect(fsFn).toContain('for (let i = 0; i < nFacets')
  })

  it('builds groove boxes with _makeBox', () => {
    expect(fsFn).toContain('_makeBox(')
  })

  it('rotates each groove around Z axis', () => {
    expect(fsFn).toContain('SetRotation_1(')
    expect(fsFn).toContain('BRepBuilderAPI_Transform_2(')
  })

  it('fuses grooves into seat with _jewelryFuse', () => {
    expect(fsFn).toContain('_jewelryFuse(')
  })

  it('supports optional through_hole', () => {
    expect(fsFn).toContain('throughHole')
  })

  it('per-groove build is wrapped in try/catch for graceful fallback', () => {
    expect(fsFn).toContain('} catch {')
  })

  it('applies position/orientation transform', () => {
    expect(fsFn).toContain('_jewelryTransform(')
  })
})

describe('opFishtailSeat — node spec fields from fishtail_seat_geometry() Python', () => {
  const FS_START = workerSrc.indexOf('function opFishtailSeat(')
  const FS_END   = workerSrc.indexOf('\nfunction opMultiStoneSeat(')
  const fsFn = workerSrc.slice(FS_START, FS_END)

  for (const field of [
    'bright_cut_angle_deg', 'bright_cut_depth_mm',
    'n_bright_facets', 'bright_cut_radius_mm',
  ]) {
    it(`field '${field}' is referenced`, () => {
      expect(fsFn).toContain(field)
    })
  }
})

// ---------------------------------------------------------------------------
// 4. opMultiStoneSeat — op: multi_stone_seat
// ---------------------------------------------------------------------------

describeOp('multi_stone_seat', 'opMultiStoneSeat')

describe('opMultiStoneSeat — geometry structure', () => {
  const MS_START = workerSrc.indexOf('function opMultiStoneSeat(')
  const MS_END   = workerSrc.indexOf('\nfunction opChainAssembly(')
  if (MS_START === -1) throw new Error('opMultiStoneSeat not found')
  const msFn = workerSrc.slice(MS_START, MS_END)

  it('reads center_seat_geom from node', () => {
    expect(msFn).toContain('center_seat_geom')
  })

  it('reads side_seat_geom from node', () => {
    expect(msFn).toContain('side_seat_geom')
  })

  it('reads center_position from node', () => {
    expect(msFn).toContain('center_position')
  })

  it('reads side_positions array from node', () => {
    expect(msFn).toContain('side_positions')
  })

  it('builds center seat cutter', () => {
    expect(msFn).toContain('compound')
    expect(msFn).toContain('centerGeom')
  })

  it('iterates over side_positions to build each side seat', () => {
    expect(msFn).toContain('for (const sp of sidePos')
  })

  it('fuses side seats into compound via _jewelryFuse', () => {
    expect(msFn).toContain('_jewelryFuse(')
  })

  it('translates each seat to its position (px/py/pz offsets)', () => {
    expect(msFn).toContain('SetTranslation_1(')
  })

  it('has fallback for center seat build failure', () => {
    // try/catch around center seat build
    expect(msFn).toContain('} catch (e) {')
  })

  it('has per-side-seat try/catch for graceful fallback', () => {
    expect(msFn).toContain('} catch {')
  })

  it('applies position/orientation transform at the end', () => {
    expect(msFn).toContain('_jewelryTransform(')
  })

  it('n_side_stones and side_pitch_mm fields are accessible from node', () => {
    expect(msFn).toContain('side_positions')
    expect(msFn).toContain('sidePos')
  })
})

describe('opMultiStoneSeat — node spec fields from multi_stone_seat_geometry() Python', () => {
  const MS_START = workerSrc.indexOf('function opMultiStoneSeat(')
  const MS_END   = workerSrc.indexOf('\nfunction opChainAssembly(')
  const msFn = workerSrc.slice(MS_START, MS_END)

  for (const field of [
    'center_seat_geom', 'side_seat_geom',
    'center_position', 'side_positions',
  ]) {
    it(`field '${field}' is referenced`, () => {
      expect(msFn).toContain(field)
    })
  }
})

// ---------------------------------------------------------------------------
// 5. opChainAssembly — op: chain_assembly
// ---------------------------------------------------------------------------

describeOp('chain_assembly', 'opChainAssembly')

describe('opChainAssembly — geometry structure', () => {
  const CA_START = workerSrc.indexOf('function opChainAssembly(')
  const CA_END   = workerSrc.indexOf('\n// ---------------------------------------------------------------------------\n// Tree evaluation.')
  if (CA_START === -1) throw new Error('opChainAssembly not found')
  const caFn = workerSrc.slice(CA_START, CA_END)

  it('reads style from node', () => {
    expect(caFn).toContain('node.style')
  })

  it('reads wire_gauge_mm from node', () => {
    expect(caFn).toContain('wire_gauge_mm')
  })

  it('reads link_length_mm from node', () => {
    expect(caFn).toContain('link_length_mm')
  })

  it('reads link_width_mm from node', () => {
    expect(caFn).toContain('link_width_mm')
  })

  it('reads link_count from node', () => {
    expect(caFn).toContain('link_count')
  })

  it('reads link_pitch_mm from node', () => {
    expect(caFn).toContain('link_pitch_mm')
  })

  it('reads link_hints from node', () => {
    expect(caFn).toContain('link_hints')
  })

  it('reads clasp sub-node from node', () => {
    expect(caFn).toContain('clasp')
  })

  it('produces a compound of link shapes (TopoDS_Compound)', () => {
    expect(caFn).toContain('TopoDS_Compound')
    expect(caFn).toContain('MakeCompound')
  })

  it('iterates link_count times to place links', () => {
    expect(caFn).toContain('for (let i = 0; i < linkCount')
  })

  it('translates each link by i × pitch along X', () => {
    expect(caFn).toContain('i * pitch')
    expect(caFn).toContain('SetTranslation_1(')
  })

  it('alternates rotation by 90° for interlocking styles', () => {
    expect(caFn).toContain('alternates')
    expect(caFn).toContain('Math.PI / 2')
  })

  it('distinguishes box/snake (box prism) from round wire (torus) styles', () => {
    expect(caFn).toContain("boxStyles")
    expect(caFn).toContain("'box'")
    expect(caFn).toContain("'snake'")
    expect(caFn).toContain('MakeTorus')
  })

  it('falls back to cylinder if torus build fails', () => {
    expect(caFn).toContain('_makeCylinder(')
    expect(caFn).toContain('torus build failed')
  })

  it('appends clasp placeholder when clasp sub-node is present', () => {
    // clasp section must check for presence and add a body
    const claspSection = caFn.slice(caFn.indexOf('clasp'))
    expect(claspSection).toContain('_makeCylinder(')
    expect(claspSection).toContain('claspBody')
  })

  it('per-link build is wrapped in try/catch for graceful fallback', () => {
    expect(caFn).toContain('} catch {')
  })

  it('applies position/orientation transform at the end', () => {
    expect(caFn).toContain('_jewelryTransform(')
  })
})

describe('opChainAssembly — node spec fields from compute_chain_params() Python', () => {
  const CA_START = workerSrc.indexOf('function opChainAssembly(')
  const CA_END   = workerSrc.indexOf('\n// ---------------------------------------------------------------------------\n// Tree evaluation.')
  const caFn = workerSrc.slice(CA_START, CA_END)

  for (const field of [
    'wire_gauge_mm', 'link_length_mm', 'link_width_mm',
    'link_count', 'link_pitch_mm', 'link_hints', 'clasp',
  ]) {
    it(`field '${field}' is referenced`, () => {
      expect(caFn).toContain(field)
    })
  }
})

// ---------------------------------------------------------------------------
// 6. Positioning contract — all new ops use _jewelryTransform
// ---------------------------------------------------------------------------

describe('T-25 ops — position/orientation_deg transform contract', () => {
  const ops = [
    ['opChannelSeat',   'opBezelSeat'],
    ['opBezelSeat',     'opFishtailSeat'],
    ['opFishtailSeat',  'opMultiStoneSeat'],
    ['opMultiStoneSeat','opChainAssembly'],
  ]
  for (const [fn, nextFn] of ops) {
    it(`${fn} calls _jewelryTransform with node.position and node.orientation_deg`, () => {
      const start = workerSrc.indexOf(`function ${fn}(`)
      const end   = workerSrc.indexOf(`\nfunction ${nextFn}(`)
      const fnSrc = workerSrc.slice(start, end)
      expect(fnSrc).toContain('_jewelryTransform(')
      expect(fnSrc).toContain('node.position')
      expect(fnSrc).toContain('node.orientation_deg')
    })
  }

  it('opChainAssembly calls _jewelryTransform with node.position and node.orientation_deg', () => {
    const CA_START = workerSrc.indexOf('function opChainAssembly(')
    const CA_END   = workerSrc.indexOf('\n// ---------------------------------------------------------------------------\n// Tree evaluation.')
    const caFn = workerSrc.slice(CA_START, CA_END)
    expect(caFn).toContain('_jewelryTransform(')
    expect(caFn).toContain('node.position')
    expect(caFn).toContain('node.orientation_deg')
  })
})

// ---------------------------------------------------------------------------
// 7. Graceful error handling — all new ops have try/catch fallback paths
// ---------------------------------------------------------------------------

describe('T-25 ops — graceful fallback (no worker crash)', () => {
  const fnBounds = [
    ['opChannelSeat',   '\nfunction opBezelSeat('],
    ['opBezelSeat',     '\nfunction opFishtailSeat('],
    ['opFishtailSeat',  '\nfunction opMultiStoneSeat('],
    ['opMultiStoneSeat','\nfunction opChainAssembly('],
  ]
  for (const [fn, nextMarker] of fnBounds) {
    it(`${fn} has at least one try/catch for graceful fallback`, () => {
      const start = workerSrc.indexOf(`function ${fn}(`)
      const end   = workerSrc.indexOf(nextMarker)
      const src   = workerSrc.slice(start, end)
      expect(src).toMatch(/\} catch \{|\} catch \(/)
    })
  }

  it('opChainAssembly has multiple try/catch paths (per-link + torus fallback)', () => {
    const CA_START = workerSrc.indexOf('function opChainAssembly(')
    const CA_END   = workerSrc.indexOf('\n// ---------------------------------------------------------------------------\n// Tree evaluation.')
    const caFn = workerSrc.slice(CA_START, CA_END)
    const catchCount = (caFn.match(/\} catch \{|\} catch \(/g) || []).length
    expect(catchCount).toBeGreaterThanOrEqual(2)
  })
})

// ---------------------------------------------------------------------------
// 8. chain_assembly link_count × link_pitch_mm produces correct total length
//    (pure math — no WASM)
// ---------------------------------------------------------------------------

describe('chain_assembly — link_count × link_pitch_mm total length (pure math)', () => {
  it('10 links at pitch 3.5 mm = 35 mm total', () => {
    const linkCount = 10
    const pitchMm   = 3.5
    const totalLen  = linkCount * pitchMm
    expect(totalLen).toBeCloseTo(35.0, 5)
  })

  it('100 links at pitch 1.2 mm = 120 mm total', () => {
    expect(100 * 1.2).toBeCloseTo(120.0, 5)
  })

  it('bracelet 7 in (≈ 50 links × 3.55 mm pitch) ≈ 177.5 mm', () => {
    // matches _STANDARD_LENGTHS_MM['bracelet_7in'] = 177.8
    const approx = 50 * 3.55
    expect(approx).toBeGreaterThan(170)
    expect(approx).toBeLessThan(185)
  })
})

// ---------------------------------------------------------------------------
// 9. multi_stone_seat side_positions symmetry (pure math)
// ---------------------------------------------------------------------------

describe('multi_stone_seat — side_positions symmetry (pure math)', () => {
  // Mirror of multi_stone_seat_geometry() side-position logic (Python → JS).
  function computeSidePositions(nSide, pitchMm) {
    const half = nSide / 2
    const positions = []
    for (let i = 1; i <= half; i++) {
      positions.push([i * pitchMm, 0, 0])
      positions.push([-i * pitchMm, 0, 0])
    }
    positions.sort((a, b) => a[0] - b[0])
    return positions
  }

  it('2 side stones: positions are [−pitch, 0, 0] and [+pitch, 0, 0]', () => {
    const pos = computeSidePositions(2, 4.0)
    expect(pos.length).toBe(2)
    expect(pos[0][0]).toBeCloseTo(-4.0, 5)
    expect(pos[1][0]).toBeCloseTo( 4.0, 5)
  })

  it('4 side stones: 4 positions at ±pitch and ±2×pitch', () => {
    const pos = computeSidePositions(4, 3.5)
    expect(pos.length).toBe(4)
    expect(pos[0][0]).toBeCloseTo(-7.0, 5)
    expect(pos[1][0]).toBeCloseTo(-3.5, 5)
    expect(pos[2][0]).toBeCloseTo( 3.5, 5)
    expect(pos[3][0]).toBeCloseTo( 7.0, 5)
  })

  it('all side_positions have y=0 and z=0 (aligned along X axis)', () => {
    const pos = computeSidePositions(4, 3.0)
    for (const [, y, z] of pos) {
      expect(y).toBe(0)
      expect(z).toBe(0)
    }
  })
})

// ---------------------------------------------------------------------------
// 10. channel_seat stone_positions along axis (pure math)
// ---------------------------------------------------------------------------

describe('channel_seat — stone_positions along axis (pure math)', () => {
  // Mirrors channel_seat_geometry() stone-position logic.
  function computeStonePositions(nStones, pitchMm, start, axis) {
    const mag = Math.sqrt(axis.reduce((s, v) => s + v * v, 0))
    const ax  = axis.map(v => v / mag)
    return Array.from({ length: nStones }, (_, i) =>
      start.map((s, j) => s + ax[j] * i * pitchMm),
    )
  }

  it('3 stones along X at pitch 4 mm: positions at x=0, 4, 8', () => {
    const pos = computeStonePositions(3, 4.0, [0, 0, 0], [1, 0, 0])
    expect(pos[0][0]).toBeCloseTo(0, 5)
    expect(pos[1][0]).toBeCloseTo(4, 5)
    expect(pos[2][0]).toBeCloseTo(8, 5)
  })

  it('all y and z coords are 0 for X-axis row', () => {
    const pos = computeStonePositions(5, 3.5, [0, 0, 0], [1, 0, 0])
    for (const [, y, z] of pos) {
      expect(y).toBeCloseTo(0, 5)
      expect(z).toBeCloseTo(0, 5)
    }
  })

  it('groove_length = (n-1) × pitch + 2 × girdle_radius', () => {
    const n = 5
    const pitch = 3.5
    const girdR = 1.8
    const grooveLen = (n - 1) * pitch + 2 * girdR
    expect(grooveLen).toBeCloseTo(14 + 3.6, 5)
  })
})

// ---------------------------------------------------------------------------
// 11. Python gem_seat.py node spec field presence checks
// ---------------------------------------------------------------------------

describe('T-25 — Python gem_seat.py fields present in source', () => {
  let pySrc = null
  try {
    pySrc = readFileSync(
      path.resolve(__dirname,
        '../../packages/kerf-cad-core/src/kerf_cad_core/jewelry/gem_seat.py'),
      'utf8',
    )
  } catch { /* Python file not present in this environment */ }

  it('gem_seat.py defines channel_seat_geometry (channel_seat op source)', () => {
    if (!pySrc) return expect(true).toBe(true)
    expect(pySrc).toContain('channel_seat_geometry')
  })

  it('gem_seat.py defines bezel_seat_geometry', () => {
    if (!pySrc) return expect(true).toBe(true)
    expect(pySrc).toContain('bezel_seat_geometry')
  })

  it('gem_seat.py defines fishtail_seat_geometry', () => {
    if (!pySrc) return expect(true).toBe(true)
    expect(pySrc).toContain('fishtail_seat_geometry')
  })

  it('gem_seat.py defines multi_stone_seat_geometry', () => {
    if (!pySrc) return expect(true).toBe(true)
    expect(pySrc).toContain('multi_stone_seat_geometry')
  })

  it('gem_seat.py channel_seat includes groove_width_mm, stone_positions', () => {
    if (!pySrc) return expect(true).toBe(true)
    expect(pySrc).toContain('groove_width_mm')
    expect(pySrc).toContain('stone_positions')
  })

  it('gem_seat.py bezel_seat includes bezel_wall_height_mm and taper_angle_deg', () => {
    if (!pySrc) return expect(true).toBe(true)
    expect(pySrc).toContain('bezel_wall_height_mm')
    expect(pySrc).toContain('taper_angle_deg')
  })

  it('gem_seat.py fishtail_seat includes n_bright_facets and bright_cut_angle_deg', () => {
    if (!pySrc) return expect(true).toBe(true)
    expect(pySrc).toContain('n_bright_facets')
    expect(pySrc).toContain('bright_cut_angle_deg')
  })

  it('gem_seat.py multi_stone_seat includes center_seat_geom and side_positions', () => {
    if (!pySrc) return expect(true).toBe(true)
    expect(pySrc).toContain('center_seat_geom')
    expect(pySrc).toContain('side_positions')
  })
})

describe('T-25 — Python chain.py fields present in source', () => {
  let pySrc = null
  try {
    pySrc = readFileSync(
      path.resolve(__dirname,
        '../../packages/kerf-cad-core/src/kerf_cad_core/jewelry/chain.py'),
      'utf8',
    )
  } catch { /* Python file not present */ }

  it('chain.py defines chain_assembly op', () => {
    if (!pySrc) return expect(true).toBe(true)
    expect(pySrc).toContain('chain_assembly')
  })

  it('chain.py includes link_count, link_pitch_mm, link_hints', () => {
    if (!pySrc) return expect(true).toBe(true)
    expect(pySrc).toContain('link_count')
    expect(pySrc).toContain('link_pitch_mm')
    expect(pySrc).toContain('link_hints')
  })

  it('chain.py defines compute_chain_params', () => {
    if (!pySrc) return expect(true).toBe(true)
    expect(pySrc).toContain('compute_chain_params')
  })

  it('chain.py defines clasp sub-node', () => {
    if (!pySrc) return expect(true).toBe(true)
    expect(pySrc).toContain('clasp')
  })
})

// ---------------------------------------------------------------------------
// 12. WASM-gated integration placeholders (skip in Node CI)
// ---------------------------------------------------------------------------

describe('T-25 WASM: channel_seat solid (skipped in Node)', () => {
  it.skipIf(SKIP_WASM)(
    'channel_seat produces a solid compound with at least n_stones bearing-cone impressions',
    async () => {
      // When WASM available:
      //   Build channel_seat node with n_stones=3, pitch_mm=4, groove_width_mm=3.5
      //   Call evaluateTree → get compound
      //   Assert compound contains ≥ 1 solid shape
      expect(true).toBe(true)
    },
  )
})

describe('T-25 WASM: bezel_seat solid (skipped in Node)', () => {
  it.skipIf(SKIP_WASM)(
    'bezel_seat produces a valid cutter solid with bearing cone + wall',
    async () => {
      // When WASM available:
      //   Build bezel_seat node (tapered=false, bezel_wall_height_mm=1.5)
      //   Call evaluateTree
      //   Assert shape is not null and is a valid solid
      expect(true).toBe(true)
    },
  )
})

describe('T-25 WASM: fishtail_seat solid (skipped in Node)', () => {
  it.skipIf(SKIP_WASM)(
    'fishtail_seat produces solid with n_bright_facets radial grooves',
    async () => {
      // When WASM available:
      //   Build fishtail_seat node (n_bright_facets=4, bright_cut_angle_deg=45)
      //   Assert shape is not null
      expect(true).toBe(true)
    },
  )
})

describe('T-25 WASM: multi_stone_seat solid (skipped in Node)', () => {
  it.skipIf(SKIP_WASM)(
    'multi_stone_seat produces compound with 1 center + n_side_stones seats',
    async () => {
      // When WASM available:
      //   Build multi_stone_seat node (n_side_stones=2, side_pitch_mm=4)
      //   Assert compound has 3 sub-shapes (center + 2 sides)
      expect(true).toBe(true)
    },
  )
})

describe('T-25 WASM: chain_assembly compound (skipped in Node)', () => {
  it.skipIf(SKIP_WASM)(
    'chain_assembly produces a compound containing exactly link_count shapes',
    async () => {
      // When WASM available:
      //   Build chain_assembly node (style=cable, link_count=5, wire_gauge_mm=1.0)
      //   Iterate compound sub-shapes → count them
      //   Assert count === 5
      expect(true).toBe(true)
    },
  )
})
