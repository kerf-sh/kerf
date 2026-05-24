/**
 * wave3UiWiring.test.jsx — Wave 3 UI-wiring tests.
 *
 * Tests:
 *   1. FeatureView FEATURE_KINDS includes newly wired ops
 *      (rib, helix, multi_transform, zebra_analysis, class_a_check,
 *       global_continuity_audit, blend_srf_g3, g3_chain_blend, fit_surface)
 *   2. FEATURE_CATEGORIES includes each new op in the expected category
 *   3. GdntInspectionPanel renders correctly for mock data + empty state
 *   4. WoodworkingCutListPanel renders correctly for mock data + empty state
 *   5. MotionResultsPanel renders correctly for mock data + empty state
 */

import { describe, it, expect, vi, beforeAll } from 'vitest'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

// ---------------------------------------------------------------------------
// Mocks for FeatureView deps
// ---------------------------------------------------------------------------

vi.mock('lucide-react', () => {
  const stub = (name) => () => React.createElement('span', { 'data-icon': name })
  // Explicit list of every icon used by FeatureView + the three new panels.
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
// Helpers
// ---------------------------------------------------------------------------

let FEATURE_KINDS = []
let FEATURE_CATEGORIES = []
let GdntInspectionPanel
let WoodworkingCutListPanel
let MotionResultsPanel

beforeAll(async () => {
  // Import panels directly — they have no heavy deps.
  ;[
    { default: GdntInspectionPanel },
    { default: WoodworkingCutListPanel },
    { default: MotionResultsPanel },
  ] = await Promise.all([
    import('../components/GdntInspectionPanel.jsx'),
    import('../components/WoodworkingCutListPanel.jsx'),
    import('../components/MotionResultsPanel.jsx'),
  ])

  // Import FEATURE_KINDS and FEATURE_CATEGORIES via named exports.
  const fv = await import('../components/FeatureView.jsx')
  FEATURE_KINDS = fv.FEATURE_KINDS
  FEATURE_CATEGORIES = fv.FEATURE_CATEGORIES
})

// ---------------------------------------------------------------------------
// 1. FeatureView FEATURE_KINDS / FEATURE_CATEGORIES catalog checks
// ---------------------------------------------------------------------------

describe('FeatureView — FEATURE_KINDS catalog', () => {
  it('exports FEATURE_KINDS array', () => {
    expect(Array.isArray(FEATURE_KINDS)).toBe(true)
    expect(FEATURE_KINDS.length).toBeGreaterThan(50)
  })

  // All new ops must be present.
  const NEW_OPS = [
    'rib',
    'helix',
    'multi_transform',
    'zebra_analysis',
    'class_a_check',
    'global_continuity_audit',
    'blend_srf_g3',
    'g3_chain_blend',
    'fit_surface',
  ]

  for (const op of NEW_OPS) {
    it(`includes op "${op}"`, () => {
      const found = FEATURE_KINDS.find((k) => k.op === op)
      expect(found).toBeTruthy()
    })

    it(`op "${op}" has label, icon, defaults, and fields`, () => {
      const found = FEATURE_KINDS.find((k) => k.op === op)
      expect(found.label).toBeTruthy()
      expect(found.icon).toBeTruthy()
      expect(found.defaults).toBeDefined()
      expect(Array.isArray(found.fields)).toBe(true)
    })
  }
})

describe('FeatureView — FEATURE_CATEGORIES catalog', () => {
  it('exports FEATURE_CATEGORIES array', () => {
    expect(Array.isArray(FEATURE_CATEGORIES)).toBe(true)
  })

  it('has Analysis category', () => {
    const cat = FEATURE_CATEGORIES.find((c) => c.id === 'analysis')
    expect(cat).toBeTruthy()
    expect(cat.label).toBe('Analysis')
  })

  it('Analysis category contains zebra_analysis, class_a_check, global_continuity_audit', () => {
    const cat = FEATURE_CATEGORIES.find((c) => c.id === 'analysis')
    expect(cat.ops).toContain('zebra_analysis')
    expect(cat.ops).toContain('class_a_check')
    expect(cat.ops).toContain('global_continuity_audit')
  })

  it('sketch category contains rib and helix', () => {
    const cat = FEATURE_CATEGORIES.find((c) => c.id === 'sketch')
    expect(cat.ops).toContain('rib')
    expect(cat.ops).toContain('helix')
  })

  it('pattern category contains multi_transform', () => {
    const cat = FEATURE_CATEGORIES.find((c) => c.id === 'pattern')
    expect(cat.ops).toContain('multi_transform')
  })

  it('surface category contains blend_srf_g3, g3_chain_blend, fit_surface', () => {
    const cat = FEATURE_CATEGORIES.find((c) => c.id === 'surface')
    expect(cat.ops).toContain('blend_srf_g3')
    expect(cat.ops).toContain('g3_chain_blend')
    expect(cat.ops).toContain('fit_surface')
  })
})

// ---------------------------------------------------------------------------
// 2. GdntInspectionPanel
// ---------------------------------------------------------------------------

describe('GdntInspectionPanel', () => {
  it('renders empty state when no data provided', () => {
    const html = renderToStaticMarkup(
      React.createElement(GdntInspectionPanel, {}),
    )
    expect(html).toContain('gdnt_build_report')
  })

  it('renders header', () => {
    const html = renderToStaticMarkup(
      React.createElement(GdntInspectionPanel, {}),
    )
    expect(html).toMatch(/GD.*T Inspection Report/i)
  })

  it('renders inspection rows from report prop', () => {
    const report = {
      part_name: 'Housing',
      rows: [
        {
          feature_id: 'D1',
          fcf: { unicode: '⊙', symbol_code: 'roundness', tolerance_zone: '0.01' },
          measured_value: 0.008,
          tolerance_value: 0.01,
          pass: true,
        },
        {
          feature_id: 'F2',
          fcf: { unicode: '▱', symbol_code: 'flatness', tolerance_zone: '0.02' },
          measured_value: 0.025,
          tolerance_value: 0.02,
          pass: false,
        },
      ],
    }
    const html = renderToStaticMarkup(
      React.createElement(GdntInspectionPanel, { report }),
    )
    expect(html).toContain('D1')
    expect(html).toContain('F2')
    expect(html).toContain('PASS')
    expect(html).toContain('FAIL')
    expect(html).toContain('Housing')
  })

  it('renders summary bar counts', () => {
    const report = {
      rows: [
        { feature_id: 'A', measured_value: 0.005, tolerance_value: 0.01, pass: true },
        { feature_id: 'B', measured_value: 0.015, tolerance_value: 0.01, pass: false },
      ],
    }
    const html = renderToStaticMarkup(
      React.createElement(GdntInspectionPanel, { report }),
    )
    expect(html).toContain('Passed')
    expect(html).toContain('Failed')
  })

  it('parses raw JSON string', () => {
    const raw = JSON.stringify({
      rows: [{ feature_id: 'X1', pass: true, measured_value: 0.001, tolerance_value: 0.01 }],
    })
    const html = renderToStaticMarkup(
      React.createElement(GdntInspectionPanel, { raw }),
    )
    expect(html).toContain('X1')
  })

  it('renders empty table message for report with empty rows', () => {
    const html = renderToStaticMarkup(
      React.createElement(GdntInspectionPanel, { report: { rows: [] } }),
    )
    expect(html).toContain('gdnt_build_report')
  })
})

// ---------------------------------------------------------------------------
// 3. WoodworkingCutListPanel
// ---------------------------------------------------------------------------

describe('WoodworkingCutListPanel', () => {
  it('renders empty state when no data provided', () => {
    const html = renderToStaticMarkup(
      React.createElement(WoodworkingCutListPanel, {}),
    )
    expect(html).toContain('woodworking_cut_list')
  })

  it('renders header', () => {
    const html = renderToStaticMarkup(
      React.createElement(WoodworkingCutListPanel, {}),
    )
    expect(html).toContain('Cut List')
  })

  it('renders board rows from cutList prop', () => {
    const cutList = {
      stock_length_mm: 2400,
      boards: [
        {
          board_id: 1,
          pieces: [{ label: 'Side A', length_mm: 600 }, { label: 'Side B', length_mm: 600 }],
          used_mm: 1200,
          waste_mm: 1200,
          utilisation_pct: 50,
        },
        {
          board_id: 2,
          pieces: [{ label: 'Top', length_mm: 2200 }],
          used_mm: 2200,
          waste_mm: 200,
          utilisation_pct: 91.7,
        },
      ],
    }
    const html = renderToStaticMarkup(
      React.createElement(WoodworkingCutListPanel, { cutList }),
    )
    expect(html).toContain('#1')
    expect(html).toContain('#2')
    expect(html).toContain('2 pieces')
    expect(html).toContain('1 piece')
  })

  it('renders utilisation percentage', () => {
    const cutList = {
      stock_length_mm: 2400,
      boards: [{ board_id: 1, pieces: [], used_mm: 2000, waste_mm: 400, utilisation_pct: 83.3 }],
    }
    const html = renderToStaticMarkup(
      React.createElement(WoodworkingCutListPanel, { cutList }),
    )
    expect(html).toContain('83.3')
  })

  it('parses raw JSON string', () => {
    const raw = JSON.stringify({
      stock_length_mm: 2400,
      boards: [{ board_id: 1, pieces: [], used_mm: 1200, waste_mm: 1200, utilisation_pct: 50 }],
    })
    const html = renderToStaticMarkup(
      React.createElement(WoodworkingCutListPanel, { raw }),
    )
    expect(html).toContain('#1')
  })

  it('renders stock length in header', () => {
    const cutList = { stock_length_mm: 3000, boards: [] }
    const html = renderToStaticMarkup(
      React.createElement(WoodworkingCutListPanel, { cutList }),
    )
    expect(html).toContain('3000')
  })
})

// ---------------------------------------------------------------------------
// 4. MotionResultsPanel
// ---------------------------------------------------------------------------

describe('MotionResultsPanel', () => {
  it('renders empty state when no data provided', () => {
    const html = renderToStaticMarkup(
      React.createElement(MotionResultsPanel, {}),
    )
    expect(html).toContain('simulate_motion')
  })

  it('renders header', () => {
    const html = renderToStaticMarkup(
      React.createElement(MotionResultsPanel, {}),
    )
    expect(html).toContain('Motion')
  })

  it('renders trajectory table for simulate_motion result', () => {
    const result = {
      bodies: [{ name: 'Block' }, { name: 'Pendulum' }],
      trajectories: [
        {
          positions: [[0, 0, 0], [0.1, 0, -0.01], [0.5, 0, -0.1]],
          velocities: [[0, 0, 0], [0.2, 0, -0.1], [1.0, 0, -0.5]],
        },
        {
          positions: [[1, 0, 0], [1.1, 0, 0.1]],
          velocities: [[0, 0, 0], [0.5, 0, 0.5]],
        },
      ],
      t_end: 1.0,
      dt: 0.01,
    }
    const html = renderToStaticMarkup(
      React.createElement(MotionResultsPanel, { result }),
    )
    expect(html).toContain('Block')
    expect(html).toContain('Pendulum')
    expect(html).toContain('Simulation trajectories')
  })

  it('renders IK result for solve_ik output', () => {
    const result = {
      joint_angles_rad: [0.5, -0.3, 1.2],
      reachable: true,
      target: [0.3, 0.0, 0.2],
    }
    const html = renderToStaticMarkup(
      React.createElement(MotionResultsPanel, { result }),
    )
    expect(html).toContain('IK result')
    expect(html).toContain('Reachable')
    expect(html).toContain('J1=')
  })

  it('renders workspace cloud panel for compute_workspace output', () => {
    const result = {
      workspace_cloud: [[0,0,0],[0.1,0.1,0.1],[0.2,0.2,0.2]],
    }
    const html = renderToStaticMarkup(
      React.createElement(MotionResultsPanel, { result }),
    )
    expect(html).toContain('Workspace cloud')
    expect(html).toContain('3')
  })

  it('parses raw JSON string', () => {
    const raw = JSON.stringify({
      joint_angles_rad: [1.0, 2.0],
      reachable: false,
      target: [1, 0, 0],
    })
    const html = renderToStaticMarkup(
      React.createElement(MotionResultsPanel, { raw }),
    )
    expect(html).toContain('IK result')
    expect(html).toContain('Unreachable')
  })

  it('renders step count in trajectory table', () => {
    const result = {
      bodies: [{ name: 'Body A' }],
      trajectories: [{ positions: new Array(100).fill([0, 0, 0]), velocities: [] }],
      t_end: 1.0,
      dt: 0.01,
    }
    const html = renderToStaticMarkup(
      React.createElement(MotionResultsPanel, { result }),
    )
    expect(html).toContain('100')
  })
})
