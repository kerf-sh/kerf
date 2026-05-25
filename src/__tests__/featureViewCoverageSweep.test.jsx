/**
 * featureViewCoverageSweep.test.jsx
 *
 * Verifies the FeatureView wiring pass that added:
 *   Mechanical / solids:
 *     feature_draft, feature_mirror, feature_tapped_hole, feature_thread_external,
 *     feature_hole_pattern_from_sketch, sheet_metal_flat_pattern, sheet_metal_unfold
 *   Gears:
 *     gear_spur, gear_helical, gear_internal, gear_rack
 *   Jewelry gem-seat cuts:
 *     jewelry_cut_baguette_channel_seat, jewelry_cut_cluster_halo_seat,
 *     jewelry_cut_gypsy_seat, jewelry_cut_multi_stone_seat, jewelry_cut_pave_field_seat
 *   BIM elements:
 *     bim_make_grid, bim_make_framing, bim_make_wall, bim_make_slab
 *
 * Tests:
 *   1. Each new op is present in FEATURE_KINDS with label, icon, defaults, fields.
 *   2. Each new op is in the expected FEATURE_CATEGORIES category.
 *   3. The "gears" and "bim" categories exist.
 *   4. Sheet metal coverage additions are in the 'sheetmetal' category.
 */

import { describe, it, expect, vi, beforeAll } from 'vitest'
import React from 'react'

// ---------------------------------------------------------------------------
// Stubs — must match the full set of icons used by FeatureView
// ---------------------------------------------------------------------------

vi.mock('lucide-react', () => {
  const stub = (name) => () => React.createElement('span', { 'data-icon': name })
  return {
    Trash2: stub('Trash2'), ChevronUp: stub('ChevronUp'), ChevronDown: stub('ChevronDown'),
    Box: stub('Box'), Circle: stub('Circle'), RotateCcw: stub('RotateCcw'),
    Disc: stub('Disc'), Layers: stub('Layers'), Drill: stub('Drill'),
    Sigma: stub('Sigma'), AlertTriangle: stub('AlertTriangle'), Loader2: stub('Loader2'),
    Play: stub('Play'), Move: stub('Move'), Crosshair: stub('Crosshair'),
    GitBranch: stub('GitBranch'), Repeat: stub('Repeat'), FlipHorizontal: stub('FlipHorizontal'),
    PencilLine: stub('PencilLine'), Pointer: stub('Pointer'), Waves: stub('Waves'),
    Layers3: stub('Layers3'), Aperture: stub('Aperture'), Plus: stub('Plus'),
    X: stub('X'), ChevronRight: stub('ChevronRight'), LayoutGrid: stub('LayoutGrid'),
    Combine: stub('Combine'), Scissors: stub('Scissors'), Grid3x3: stub('Grid3x3'),
    MoreHorizontal: stub('MoreHorizontal'), SlidersHorizontal: stub('SlidersHorizontal'),
    Zap: stub('Zap'), Eye: stub('Eye'), Shield: stub('Shield'),
    Wrench: stub('Wrench'), AlignLeft: stub('AlignLeft'), Activity: stub('Activity'),
    CheckCircle: stub('CheckCircle'), XCircle: stub('XCircle'), Wrench2: stub('Wrench2'),
  }
})

vi.mock('../components/FeatureRenderer.jsx', () => ({
  default: () => React.createElement('div', { 'data-testid': 'feature-renderer' }),
}))

vi.mock('../lib/occtRunner.js', () => ({
  runFeatures: vi.fn(() => Promise.resolve({ meshes: [], ms: 0 })),
  prewarmOcct: vi.fn(() => Promise.resolve()),
  newFeatureId: vi.fn((op) => `${op}-test`),
  requestFaceOutline: vi.fn(() => Promise.resolve(null)),
}))

const storeState = {
  featureSelection: { faceIds: new Set(), edgeIds: new Set() },
  featurePickMode: null,
  featurePickTarget: null,
  currentFile: null,
  currentFileId: null,
  setFeatureSelection: vi.fn(),
  setFeaturePickMode: vi.fn(),
  clearFeatureSelection: vi.fn(),
  createSketchOnFace: vi.fn(),
  selectFile: vi.fn(),
}
vi.mock('../store/workspace.js', () => ({
  useWorkspace: (selector) => selector(storeState),
}))

// ---------------------------------------------------------------------------
// Load FEATURE_KINDS and FEATURE_CATEGORIES
// ---------------------------------------------------------------------------

let FEATURE_KINDS = []
let FEATURE_CATEGORIES = []

beforeAll(async () => {
  const fv = await import('../components/FeatureView.jsx')
  FEATURE_KINDS = fv.FEATURE_KINDS
  FEATURE_CATEGORIES = fv.FEATURE_CATEGORIES
})

// ---------------------------------------------------------------------------
// Helper
// ---------------------------------------------------------------------------

function findKind(op) {
  return FEATURE_KINDS.find((k) => k.op === op)
}

function findCategory(id) {
  return FEATURE_CATEGORIES.find((c) => c.id === id)
}

function categoryForOp(op) {
  return FEATURE_CATEGORIES.find((c) => c.ops.includes(op))
}

// ---------------------------------------------------------------------------
// 1. FEATURE_KINDS — new ops present
// ---------------------------------------------------------------------------

const ALL_NEW_OPS = [
  // Mechanical / solids
  'feature_draft',
  'feature_mirror',
  'feature_tapped_hole',
  'feature_thread_external',
  'feature_hole_pattern_from_sketch',
  'sheet_metal_flat_pattern',
  'sheet_metal_unfold',
  // Gears
  'gear_spur',
  'gear_helical',
  'gear_internal',
  'gear_rack',
  // Jewelry gem-seat cuts
  'jewelry_cut_baguette_channel_seat',
  'jewelry_cut_cluster_halo_seat',
  'jewelry_cut_gypsy_seat',
  'jewelry_cut_multi_stone_seat',
  'jewelry_cut_pave_field_seat',
  // BIM
  'bim_make_grid',
  'bim_make_framing',
  'bim_make_wall',
  'bim_make_slab',
]

describe('FeatureView — coverage-sweep FEATURE_KINDS entries', () => {
  it('FEATURE_KINDS is a non-empty array', () => {
    expect(Array.isArray(FEATURE_KINDS)).toBe(true)
    expect(FEATURE_KINDS.length).toBeGreaterThan(50)
  })

  for (const op of ALL_NEW_OPS) {
    it(`includes op "${op}"`, () => {
      expect(findKind(op), `op "${op}" not found in FEATURE_KINDS`).toBeTruthy()
    })

    it(`op "${op}" has label, icon, defaults, and fields`, () => {
      const kind = findKind(op)
      expect(kind.label, `${op}.label`).toBeTruthy()
      expect(kind.icon,  `${op}.icon`).toBeTruthy()
      expect(kind.defaults, `${op}.defaults`).toBeDefined()
      expect(Array.isArray(kind.fields), `${op}.fields is array`).toBe(true)
      expect(kind.fields.length, `${op}.fields non-empty`).toBeGreaterThan(0)
    })
  }
})

// ---------------------------------------------------------------------------
// 2. FEATURE_CATEGORIES — ops in expected categories
// ---------------------------------------------------------------------------

describe('FeatureView — coverage-sweep FEATURE_CATEGORIES membership', () => {
  // Mechanical / solids → 'modify'
  const MODIFY_OPS = [
    'feature_draft', 'feature_mirror',
    'feature_tapped_hole', 'feature_thread_external', 'feature_hole_pattern_from_sketch',
  ]
  for (const op of MODIFY_OPS) {
    it(`"${op}" is in the 'modify' category`, () => {
      const cat = findCategory('modify')
      expect(cat, "'modify' category not found").toBeTruthy()
      expect(cat.ops, `${op} not in modify`).toContain(op)
    })
  }

  // Sheet metal additions → 'sheetmetal'
  const SHEETMETAL_OPS = ['sheet_metal_flat_pattern', 'sheet_metal_unfold']
  for (const op of SHEETMETAL_OPS) {
    it(`"${op}" is in the 'sheetmetal' category`, () => {
      const cat = findCategory('sheetmetal')
      expect(cat, "'sheetmetal' category not found").toBeTruthy()
      expect(cat.ops, `${op} not in sheetmetal`).toContain(op)
    })
  }

  // Gears → 'gears'
  const GEAR_OPS = ['gear_spur', 'gear_helical', 'gear_internal', 'gear_rack']
  for (const op of GEAR_OPS) {
    it(`"${op}" is in the 'gears' category`, () => {
      const cat = findCategory('gears')
      expect(cat, "'gears' category not found").toBeTruthy()
      expect(cat.ops, `${op} not in gears`).toContain(op)
    })
  }

  // Jewelry gem-seat cuts → 'jewelry'
  const JEWELRY_SEAT_OPS = [
    'jewelry_cut_baguette_channel_seat',
    'jewelry_cut_cluster_halo_seat',
    'jewelry_cut_gypsy_seat',
    'jewelry_cut_multi_stone_seat',
    'jewelry_cut_pave_field_seat',
  ]
  for (const op of JEWELRY_SEAT_OPS) {
    it(`"${op}" is in the 'jewelry' category`, () => {
      const cat = findCategory('jewelry')
      expect(cat, "'jewelry' category not found").toBeTruthy()
      expect(cat.ops, `${op} not in jewelry`).toContain(op)
    })
  }

  // BIM → 'bim'
  const BIM_OPS = ['bim_make_grid', 'bim_make_framing', 'bim_make_wall', 'bim_make_slab']
  for (const op of BIM_OPS) {
    it(`"${op}" is in the 'bim' category`, () => {
      const cat = findCategory('bim')
      expect(cat, "'bim' category not found").toBeTruthy()
      expect(cat.ops, `${op} not in bim`).toContain(op)
    })
  }
})

// ---------------------------------------------------------------------------
// 3. New category structure
// ---------------------------------------------------------------------------

describe('FeatureView — new category structure', () => {
  it("'gears' category exists with label 'Gears'", () => {
    const cat = findCategory('gears')
    expect(cat).toBeTruthy()
    expect(cat.label).toBe('Gears')
  })

  it("'bim' category exists with label 'BIM'", () => {
    const cat = findCategory('bim')
    expect(cat).toBeTruthy()
    expect(cat.label).toBe('BIM')
  })

  it("'sheetmetal' category contains all 6 ops (including 2 new)", () => {
    const cat = findCategory('sheetmetal')
    expect(cat.ops).toContain('sheet_metal_flange')
    expect(cat.ops).toContain('sheet_metal_flat_pattern')
    expect(cat.ops).toContain('sheet_metal_unfold')
  })

  it("'modify' category contains all original + 5 new ops", () => {
    const cat = findCategory('modify')
    // Original ops preserved
    expect(cat.ops).toContain('fillet')
    expect(cat.ops).toContain('chamfer')
    // New ops added
    expect(cat.ops).toContain('feature_draft')
    expect(cat.ops).toContain('feature_tapped_hole')
  })
})

// ---------------------------------------------------------------------------
// 4. Spot-check field correctness for key entries
// ---------------------------------------------------------------------------

describe('FeatureView — spot-check field structure', () => {
  it('gear_spur has module, teeth, pressure_angle_deg, face_width fields', () => {
    const kind = findKind('gear_spur')
    const keys = kind.fields.map((f) => f.key)
    expect(keys).toContain('module')
    expect(keys).toContain('teeth')
    expect(keys).toContain('pressure_angle_deg')
    expect(keys).toContain('face_width')
  })

  it('gear_helical has helix_angle_deg field', () => {
    const kind = findKind('gear_helical')
    const keys = kind.fields.map((f) => f.key)
    expect(keys).toContain('helix_angle_deg')
  })

  it('feature_draft has angle_deg and pull_direction fields', () => {
    const kind = findKind('feature_draft')
    const keys = kind.fields.map((f) => f.key)
    expect(keys).toContain('angle_deg')
    expect(keys).toContain('pull_direction')
  })

  it('feature_mirror has source_feature_id and mirror_plane fields', () => {
    const kind = findKind('feature_mirror')
    const keys = kind.fields.map((f) => f.key)
    expect(keys).toContain('source_feature_id')
    expect(keys).toContain('mirror_plane')
  })

  it('feature_tapped_hole has designation, depth, hole_type fields', () => {
    const kind = findKind('feature_tapped_hole')
    const keys = kind.fields.map((f) => f.key)
    expect(keys).toContain('designation')
    expect(keys).toContain('depth')
    expect(keys).toContain('hole_type')
  })

  it('feature_hole_pattern_from_sketch has sketch_picker field', () => {
    const kind = findKind('feature_hole_pattern_from_sketch')
    const sketchField = kind.fields.find((f) => f.kind === 'sketch_picker')
    expect(sketchField).toBeTruthy()
  })

  it('sheet_metal_flat_pattern has k_factor and bend_angle_deg fields', () => {
    const kind = findKind('sheet_metal_flat_pattern')
    const keys = kind.fields.map((f) => f.key)
    expect(keys).toContain('k_factor')
    expect(keys).toContain('bend_angle_deg')
  })

  it('jewelry_cut_baguette_channel_seat has length_mm, width_mm, n_stones fields', () => {
    const kind = findKind('jewelry_cut_baguette_channel_seat')
    const keys = kind.fields.map((f) => f.key)
    expect(keys).toContain('length_mm')
    expect(keys).toContain('width_mm')
    expect(keys).toContain('n_stones')
  })

  it('jewelry_cut_pave_field_seat has arrangement select field', () => {
    const kind = findKind('jewelry_cut_pave_field_seat')
    const arrField = kind.fields.find((f) => f.key === 'arrangement')
    expect(arrField).toBeTruthy()
    expect(arrField.kind).toBe('select')
  })

  it('bim_make_wall has height_m and preset_name fields', () => {
    const kind = findKind('bim_make_wall')
    const keys = kind.fields.map((f) => f.key)
    expect(keys).toContain('height_m')
    expect(keys).toContain('preset_name')
  })

  it('bim_make_grid has mode, n_cols, bay_width_m fields', () => {
    const kind = findKind('bim_make_grid')
    const keys = kind.fields.map((f) => f.key)
    expect(keys).toContain('mode')
    expect(keys).toContain('n_cols')
    expect(keys).toContain('bay_width_m')
  })

  it('bim_make_framing has column_section and beam_section text fields', () => {
    const kind = findKind('bim_make_framing')
    const colField = kind.fields.find((f) => f.key === 'column_section')
    const beamField = kind.fields.find((f) => f.key === 'beam_section')
    expect(colField).toBeTruthy()
    expect(beamField).toBeTruthy()
    expect(colField.kind).toBe('text')
    expect(beamField.kind).toBe('text')
  })
})

// ---------------------------------------------------------------------------
// 5. Every new op is in exactly one category (no orphans, no doubles)
// ---------------------------------------------------------------------------

describe('FeatureView — no new op is orphaned from categories', () => {
  for (const op of ALL_NEW_OPS) {
    it(`op "${op}" appears in at least one category`, () => {
      const cat = categoryForOp(op)
      expect(cat, `"${op}" has no category`).toBeTruthy()
    })
  }
})
