// jewelryDeferredOps2.test.js — T-26 dispatch + structure checks for the
// new jewelry ops wired in occtWorker.js:
//   Pieces:          pendant, earrings, brooch, cufflink, bangle
//   Decorative:      decorative_apply
//   Gem-seat v2:     pave_field_seat, cluster_halo_seat, gypsy_seat, baguette_channel_seat
//   Settings v3/v4:  jewelry_prong_variant, jewelry_head_gallery, jewelry_under_bezel,
//                    jewelry_peg_setting, jewelry_coronet, jewelry_suspension_mount,
//                    jewelry_vtip_protector, jewelry_bombe_cluster, jewelry_patterned_bezel,
//                    jewelry_trellis_prong, jewelry_bar_channel_graduated
//
// No WASM required.  All assertions are source-level checks following the
// exact pattern from jewelrySeatChainDispatch.test.js.

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

const workerSrc = readFileSync(
  path.resolve(__dirname, '../lib/occtWorker.js'),
  'utf8',
)

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
// Generic dispatch helper (mirrors jewelrySeatChainDispatch.test.js pattern).
// ---------------------------------------------------------------------------

function describeOp(opName, fnName) {
  describe(`${opName} — T-26 jewelry op dispatch`, () => {
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
      const block = etBody.slice(idx, idx + 600)
      expect(block).toContain(`${fnName}(`)
    })

    it(`evaluateToFinalShape '${opName}' calls ${fnName}`, () => {
      const idx = etfBody.indexOf(`case '${opName}'`)
      const block = etfBody.slice(idx, idx + 600)
      expect(block).toContain(`${fnName}(`)
    })

    it(`evaluateTree '${opName}' clears current body before building`, () => {
      const idx = etBody.indexOf(`case '${opName}'`)
      const block = etBody.slice(idx, idx + 400)
      expect(block).toMatch(/cleanupShape|current = null/)
    })
  })
}

// ---------------------------------------------------------------------------
// 1. Piece ops (pieces.py)
// ---------------------------------------------------------------------------

describeOp('pendant',  'opPendant')
describeOp('earrings', 'opEarrings')
describeOp('brooch',   'opBrooch')
describeOp('cufflink', 'opCufflink')
describeOp('bangle',   'opBangle')

// ---------------------------------------------------------------------------
// 2. Decorative apply (decorative.py)
// ---------------------------------------------------------------------------

describeOp('decorative_apply', 'opDecorativeApply')

// ---------------------------------------------------------------------------
// 3. Gem-seat v2 ops (gem_seat.py new additions)
// ---------------------------------------------------------------------------

describeOp('pave_field_seat',      'opPaveFieldSeat')
describeOp('cluster_halo_seat',    'opClusterHaloSeat')
describeOp('gypsy_seat',           'opGypsySeat')
describeOp('baguette_channel_seat','opBaguetteChannelSeat')

// ---------------------------------------------------------------------------
// 4. Settings v3/v4 ops (settings.py)
// ---------------------------------------------------------------------------

describeOp('jewelry_prong_variant',       'opJewelryProngVariant')
describeOp('jewelry_head_gallery',        'opJewelryHeadGallery')
describeOp('jewelry_under_bezel',         'opJewelryUnderBezel')
describeOp('jewelry_peg_setting',         'opJewelryPegSetting')
describeOp('jewelry_coronet',             'opJewelryCoronet')
describeOp('jewelry_suspension_mount',    'opJewelrySuspensionMount')
describeOp('jewelry_vtip_protector',      'opJewelryVtipProtector')
describeOp('jewelry_bombe_cluster',       'opJewelryBombeCluster')
describeOp('jewelry_patterned_bezel',     'opJewelryPatternedBezel')
describeOp('jewelry_trellis_prong',       'opJewelryTrellisProng')
describeOp('jewelry_bar_channel_graduated','opJewelryBarChannelGraduated')

// ---------------------------------------------------------------------------
// 5. Op function structure checks — key node-spec fields are read
// ---------------------------------------------------------------------------

describe('opPendant — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opPendant(')
  const FN_END   = workerSrc.indexOf('\nfunction opEarrings(')
  if (FN_START === -1) throw new Error('opPendant not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads width_mm from node', () => expect(fn).toContain('width_mm'))
  it('reads height_mm from node', () => expect(fn).toContain('height_mm'))
  it('reads thickness_mm from node', () => expect(fn).toContain('thickness_mm'))
  it('reads bail_wire_gauge_mm from node', () => expect(fn).toContain('bail_wire_gauge_mm'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
  it('has graceful fallback (try/catch)', () => expect(fn).toContain('catch'))
})

describe('opEarrings — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opEarrings(')
  const FN_END   = workerSrc.indexOf('\nfunction opBrooch(')
  if (FN_START === -1) throw new Error('opEarrings not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads face_diameter_mm from node', () => expect(fn).toContain('face_diameter_mm'))
  it('reads wire_gauge_mm from node', () => expect(fn).toContain('wire_gauge_mm'))
  it('reads style from node', () => expect(fn).toContain('node.style'))
  it('handles hoop/huggie style', () => expect(fn).toContain('hoop'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
  it('has graceful fallback', () => expect(fn).toContain('catch'))
})

describe('opBangle — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opBangle(')
  const FN_END   = workerSrc.indexOf('\nfunction opDecorativeApply(')
  if (FN_START === -1) throw new Error('opBangle not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads inner_diameter_mm from node', () => expect(fn).toContain('inner_diameter_mm'))
  it('reads width_mm from node', () => expect(fn).toContain('width_mm'))
  it('handles open_cuff form', () => expect(fn).toContain('open_cuff'))
  it('calls BRepPrimAPI_MakeRevol or torus fallback', () =>
    expect(fn).toMatch(/MakeRevol|MakeTorus/))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
})

describe('opDecorativeApply — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opDecorativeApply(')
  const FN_END   = workerSrc.indexOf('\nfunction opPaveFieldSeat(')
  if (FN_START === -1) throw new Error('opDecorativeApply not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads feature from node', () => expect(fn).toContain('node.feature'))
  it('reads decorative_hints from node', () => expect(fn).toContain('decorative_hints'))
  it('handles surface_texture feature', () => expect(fn).toContain('surface_texture'))
  it('handles milgrain/beading bead chain', () => expect(fn).toContain('bead_diameter_mm'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
  it('has graceful fallback', () => expect(fn).toContain('catch'))
})

describe('opPaveFieldSeat — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opPaveFieldSeat(')
  const FN_END   = workerSrc.indexOf('\nfunction opClusterHaloSeat(')
  if (FN_START === -1) throw new Error('opPaveFieldSeat not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads per_seat_geom from node', () => expect(fn).toContain('per_seat_geom'))
  it('reads stone_positions from node', () => expect(fn).toContain('stone_positions'))
  it('reads field_width_mm from node', () => expect(fn).toContain('field_width_mm'))
  it('handles empty positions gracefully', () => expect(fn).toContain('positions.length === 0'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
})

describe('opClusterHaloSeat — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opClusterHaloSeat(')
  const FN_END   = workerSrc.indexOf('\nfunction opGypsySeat(')
  if (FN_START === -1) throw new Error('opClusterHaloSeat not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads center_seat_geom from node', () => expect(fn).toContain('center_seat_geom'))
  it('reads accent_seat_geom from node', () => expect(fn).toContain('accent_seat_geom'))
  it('reads accent_positions from node', () => expect(fn).toContain('accent_positions'))
  it('builds center seat', () => expect(fn).toContain('_oneSeat(csg'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
  it('has graceful fallback', () => expect(fn).toContain('catch'))
})

describe('opGypsySeat — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opGypsySeat(')
  const FN_END   = workerSrc.indexOf('\nfunction opBaguetteChannelSeat(')
  if (FN_START === -1) throw new Error('opGypsySeat not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads girdle_radius_mm from node', () => expect(fn).toContain('girdle_radius_mm'))
  it('reads countersink_angle_deg from node', () => expect(fn).toContain('countersink_angle_deg'))
  it('reads countersink_depth_mm from node', () => expect(fn).toContain('countersink_depth_mm'))
  it('builds bearing cone', () => expect(fn).toContain('_makeCone'))
  it('builds girdle ledge', () => expect(fn).toContain('_makeCylinder'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
})

describe('opBaguetteChannelSeat — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opBaguetteChannelSeat(')
  const FN_END   = workerSrc.indexOf('\nfunction opJewelryProngVariant(')
  if (FN_START === -1) throw new Error('opBaguetteChannelSeat not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads cutter_length_mm from node', () => expect(fn).toContain('cutter_length_mm'))
  it('reads cutter_width_mm from node', () => expect(fn).toContain('cutter_width_mm'))
  it('reads stone_positions from node', () => expect(fn).toContain('stone_positions'))
  it('builds main groove box', () => expect(fn).toContain('_makeBox'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
})

describe('opJewelryProngVariant — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opJewelryProngVariant(')
  const FN_END   = workerSrc.indexOf('\nfunction opJewelryHeadGallery(')
  if (FN_START === -1) throw new Error('opJewelryProngVariant not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads variant from node', () => expect(fn).toContain('node.variant'))
  it('reads stone_diameter from node', () => expect(fn).toContain('stone_diameter'))
  it('reads prong_count from node', () => expect(fn).toContain('prong_count'))
  it('reads wire_gauge from node', () => expect(fn).toContain('wire_gauge'))
  it('delegates to opJewelryProngHead', () => expect(fn).toContain('opJewelryProngHead'))
  it('handles double_prong variant', () => expect(fn).toContain('double_prong'))
  it('handles claw_prong variant', () => expect(fn).toContain('claw_prong'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
  it('has graceful fallback', () => expect(fn).toContain('catch'))
})

describe('opJewelryHeadGallery — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opJewelryHeadGallery(')
  const FN_END   = workerSrc.indexOf('\nfunction opJewelryUnderBezel(')
  if (FN_START === -1) throw new Error('opJewelryHeadGallery not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads head_diameter from node', () => expect(fn).toContain('head_diameter'))
  it('reads head_height from node', () => expect(fn).toContain('head_height'))
  it('reads gallery_height from node', () => expect(fn).toContain('gallery_height'))
  it('reads gallery_style from node', () => expect(fn).toContain('gallery_style'))
  it('handles scalloped style', () => expect(fn).toContain('scalloped'))
  it('uses _jewelryCut for inner bore', () => expect(fn).toContain('_jewelryCut'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
})

describe('opJewelryUnderBezel — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opJewelryUnderBezel(')
  const FN_END   = workerSrc.indexOf('\nfunction opJewelryPegSetting(')
  if (FN_START === -1) throw new Error('opJewelryUnderBezel not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads stone_diameter from node', () => expect(fn).toContain('stone_diameter'))
  it('reads wall_thickness from node', () => expect(fn).toContain('wall_thickness'))
  it('reads collet_height from node', () => expect(fn).toContain('collet_height'))
  it('reads base_diameter from node', () => expect(fn).toContain('base_diameter'))
  it('cuts inner bore', () => expect(fn).toContain('_jewelryCut'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
})

describe('opJewelryCoronet — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opJewelryCoronet(')
  const FN_END   = workerSrc.indexOf('\nfunction opJewelrySuspensionMount(')
  if (FN_START === -1) throw new Error('opJewelryCoronet not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads stone_diameter from node', () => expect(fn).toContain('stone_diameter'))
  it('reads prong_count from node', () => expect(fn).toContain('prong_count'))
  it('reads crown_height from node', () => expect(fn).toContain('crown_height'))
  it('reads taper from node', () => expect(fn).toContain('node.taper'))
  it('reads wire_gauge from node', () => expect(fn).toContain('wire_gauge'))
  it('builds base collet ring', () => expect(fn).toContain('_jewelryCut'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
})

describe('opJewelrySuspensionMount — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opJewelrySuspensionMount(')
  const FN_END   = workerSrc.indexOf('\nfunction opJewelryVtipProtector(')
  if (FN_START === -1) throw new Error('opJewelrySuspensionMount not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads stone_diameter from node', () => expect(fn).toContain('stone_diameter'))
  it('reads seat_depth from node', () => expect(fn).toContain('seat_depth'))
  it('reads ring_wire_diameter from node', () => expect(fn).toContain('ring_wire_diameter'))
  it('reads ring_inner_diameter from node', () => expect(fn).toContain('ring_inner_diameter'))
  it('reads bail_height from node', () => expect(fn).toContain('bail_height'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
  it('has graceful fallback', () => expect(fn).toContain('catch'))
})

describe('opJewelryBombeCluster — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opJewelryBombeCluster(')
  const FN_END   = workerSrc.indexOf('\nfunction opJewelryPatternedBezel(')
  if (FN_START === -1) throw new Error('opJewelryBombeCluster not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads dome_radius from node', () => expect(fn).toContain('dome_radius'))
  it('reads stone_size from node', () => expect(fn).toContain('stone_size'))
  it('reads cap_half_angle_deg from node', () => expect(fn).toContain('cap_half_angle_deg'))
  it('reads base_height from node', () => expect(fn).toContain('base_height'))
  it('reads positions from node', () => expect(fn).toContain('node.positions'))
  it('builds spherical cap', () => expect(fn).toContain('MakeSphere'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
})

describe('opJewelryPatternedBezel — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opJewelryPatternedBezel(')
  const FN_END   = workerSrc.indexOf('\nfunction opJewelryTrellisProng(')
  if (FN_START === -1) throw new Error('opJewelryPatternedBezel not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads stone_diameter from node', () => expect(fn).toContain('stone_diameter'))
  it('reads pattern from node', () => expect(fn).toContain('node.pattern'))
  it('reads petal_count from node', () => expect(fn).toContain('petal_count'))
  it('delegates to opJewelryBezel', () => expect(fn).toContain('opJewelryBezel'))
  it('handles lotus/star pattern', () => expect(fn).toContain('lotus'))
  it('handles compass pattern', () => expect(fn).toContain('compass'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
})

describe('opJewelryTrellisProng — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opJewelryTrellisProng(')
  const FN_END   = workerSrc.indexOf('\nfunction opJewelryBarChannelGraduated(')
  if (FN_START === -1) throw new Error('opJewelryTrellisProng not found')
  const fn = workerSrc.slice(FN_START, FN_END)

  it('reads stone_diameter from node', () => expect(fn).toContain('stone_diameter'))
  it('reads wire_gauge from node', () => expect(fn).toContain('wire_gauge'))
  it('reads weave_style from node', () => expect(fn).toContain('weave_style'))
  it('reads cross_height from node', () => expect(fn).toContain('cross_height'))
  it('delegates to opJewelryProngHead', () => expect(fn).toContain('opJewelryProngHead'))
  it('adds cross-bar geometry for x_cross', () => expect(fn).toContain('x_cross'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
})

describe('opJewelryBarChannelGraduated — geometry structure', () => {
  const FN_START = workerSrc.indexOf('function opJewelryBarChannelGraduated(')
  const FN_END   = workerSrc.indexOf('\n// ---------------------------------------------------------------------------\n// T-1  opSheetFlange')
  if (FN_START === -1) throw new Error('opJewelryBarChannelGraduated not found')
  const fn = workerSrc.slice(FN_START, FN_END !== -1 ? FN_END : FN_START + 3000)

  it('reads stones array from node (stone_count is in stones list)', () => expect(fn).toContain('node.stones'))
  it('reads largest_diameter from node', () => expect(fn).toContain('largest_diameter'))
  it('reads bar_width from node', () => expect(fn).toContain('bar_width'))
  it('reads bar_height from node', () => expect(fn).toContain('bar_height'))
  it('reads floor_thickness from node', () => expect(fn).toContain('floor_thickness'))
  it('builds channel floor', () => expect(fn).toContain('_makeBox'))
  it('calls _jewelryTransform', () => expect(fn).toContain('_jewelryTransform'))
})

// ---------------------------------------------------------------------------
// 6. Helper reuse checks — no new kernel primitives added
// ---------------------------------------------------------------------------

describe('T-26 helper reuse — no new kernel primitives', () => {
  const t26Start = workerSrc.indexOf('// T-26  Jewelry deferred ops 2')
  const t26End   = workerSrc.indexOf('\n// ---------------------------------------------------------------------------\n// T-1  opSheetFlange')
  if (t26Start === -1) throw new Error('T-26 block not found')
  const t26 = workerSrc.slice(t26Start, t26End !== -1 ? t26End : t26Start + 100000)

  it('reuses _makeCylinder helper', () => expect(t26).toContain('_makeCylinder('))
  it('reuses _makeBox helper', () => expect(t26).toContain('_makeBox('))
  it('reuses _makeCone helper', () => expect(t26).toContain('_makeCone('))
  it('reuses _jewelryFuse helper', () => expect(t26).toContain('_jewelryFuse('))
  it('reuses _jewelryCut helper', () => expect(t26).toContain('_jewelryCut('))
  it('reuses _jewelryTransform helper', () => expect(t26).toContain('_jewelryTransform('))
  it('reuses opJewelryProngHead for variant/trellis ops', () => expect(t26).toContain('opJewelryProngHead('))
  it('reuses opJewelryBezel for patterned bezel', () => expect(t26).toContain('opJewelryBezel('))
})
