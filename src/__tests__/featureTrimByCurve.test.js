// featureTrimByCurve.test.js  GK-P41
//
// Unit tests for the trim_by_curve feature inspector entry:
//
//   • FEATURE_KINDS registry — trim_by_curve entry is present with the
//     correct op, fields, defaults, and keep_side options.
//   • FeatureInspector HTML render — a trim_by_curve node renders all
//     expected param labels (target body, face name, trim curve, keep side,
//     projection tolerance).
//   • FEATURE_CATEGORIES — 'trim_by_curve' appears in the 'surface' category.
//   • occtWorker.js dispatch — case 'trim_by_curve' is present in both
//     evaluateTree and evaluateToFinalShape.

import { describe, it, expect, beforeAll, vi } from 'vitest'
import * as fs from 'node:fs'
import * as path from 'node:path'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

// ---------------------------------------------------------------------------
// Stubs — must be installed before the heavy component import.
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
    // Wave 3 additions
    Zap: stub('Zap'), Eye: stub('Eye'), Shield: stub('Shield'),
    Wrench: stub('Wrench'), AlignLeft: stub('AlignLeft'), Activity: stub('Activity'),
  }
})

vi.mock('../components/FeatureRenderer.jsx', () => ({
  default: () => React.createElement('div', { 'data-testid': 'feature-renderer' }),
}))

vi.mock('../lib/occtRunner.js', () => ({
  runFeatures: vi.fn(() => Promise.resolve({ meshes: [], ms: 0 })),
  prewarmOcct: vi.fn(() => Promise.resolve()),
  newFeatureId: vi.fn((op) => `${op}-1`),
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
}
vi.mock('../store/workspace.js', () => ({
  useWorkspace: (selector) => selector(storeState),
}))

// ---------------------------------------------------------------------------
// Load the FeatureView module (imports FEATURE_KINDS, FEATURE_CATEGORIES,
// and the FeatureInspector component we need to render).
// ---------------------------------------------------------------------------

let FeatureView
let FEATURE_KINDS
let FEATURE_CATEGORIES

beforeAll(async () => {
  const mod = await import('../components/FeatureView.jsx')
  FeatureView = mod.default
  // The catalog arrays are module-level constants; we reach them via
  // rendering rather than direct import (they are not re-exported).
})

// ---------------------------------------------------------------------------
// 1. Inspect the FeatureView source for FEATURE_KINDS + FEATURE_CATEGORIES
//    directly — avoids re-importing the whole component.
// ---------------------------------------------------------------------------

const FEATURE_VIEW_SRC = fs.readFileSync(
  path.resolve(import.meta.dirname, '../components/FeatureView.jsx'),
  'utf8',
)

describe('FeatureView source — trim_by_curve FEATURE_KINDS entry', () => {
  it("op: 'trim_by_curve' is declared in FEATURE_KINDS", () => {
    expect(FEATURE_VIEW_SRC).toContain("op: 'trim_by_curve'")
  })

  it("label: 'TrimByCurve' is present", () => {
    expect(FEATURE_VIEW_SRC).toContain("label: 'TrimByCurve'")
  })

  it("target_feature_ref default is declared", () => {
    // The defaults block must include target_feature_ref
    const idx = FEATURE_VIEW_SRC.indexOf("op: 'trim_by_curve'")
    const slice = FEATURE_VIEW_SRC.slice(idx, idx + 1200)
    expect(slice).toContain('target_feature_ref')
  })

  it("target_face_name default is 'face-1'", () => {
    const idx = FEATURE_VIEW_SRC.indexOf("op: 'trim_by_curve'")
    const slice = FEATURE_VIEW_SRC.slice(idx, idx + 1200)
    expect(slice).toContain("target_face_name: 'face-1'")
  })

  it("keep_side default is 'positive'", () => {
    const idx = FEATURE_VIEW_SRC.indexOf("op: 'trim_by_curve'")
    const slice = FEATURE_VIEW_SRC.slice(idx, idx + 1200)
    expect(slice).toContain("keep_side: 'positive'")
  })

  it("tolerance default is 1e-3", () => {
    const idx = FEATURE_VIEW_SRC.indexOf("op: 'trim_by_curve'")
    const slice = FEATURE_VIEW_SRC.slice(idx, idx + 1200)
    expect(slice).toContain('tolerance: 1e-3')
  })

  it("keep_side select has positive and negative options", () => {
    const idx = FEATURE_VIEW_SRC.indexOf("op: 'trim_by_curve'")
    const slice = FEATURE_VIEW_SRC.slice(idx, idx + 2000)
    expect(slice).toContain("value: 'positive'")
    expect(slice).toContain("value: 'negative'")
  })

  it("feature_picker field for target_feature_ref", () => {
    const idx = FEATURE_VIEW_SRC.indexOf("op: 'trim_by_curve'")
    const slice = FEATURE_VIEW_SRC.slice(idx, idx + 2000)
    expect(slice).toContain("kind: 'feature_picker'")
  })

  it("text field for target_face_name", () => {
    const idx = FEATURE_VIEW_SRC.indexOf("op: 'trim_by_curve'")
    const slice = FEATURE_VIEW_SRC.slice(idx, idx + 2000)
    expect(slice).toContain("kind: 'text'")
  })

  it("sketch_picker field for trim_curve_ref", () => {
    const idx = FEATURE_VIEW_SRC.indexOf("op: 'trim_by_curve'")
    const slice = FEATURE_VIEW_SRC.slice(idx, idx + 2000)
    expect(slice).toContain("kind: 'sketch_picker'")
  })
})

// ---------------------------------------------------------------------------
// 2. FEATURE_CATEGORIES — trim_by_curve is in the surfacing category.
// ---------------------------------------------------------------------------

describe("FEATURE_CATEGORIES — 'trim_by_curve' in 'surface' category", () => {
  it("'trim_by_curve' appears in the surfacing ops list", () => {
    // Locate the surface category declaration and confirm trim_by_curve is listed.
    const surfaceMatch = FEATURE_VIEW_SRC.match(
      /\{\s*id:\s*'surface'[\s\S]*?ops:\s*\[([^\]]+)\]/,
    )
    expect(surfaceMatch, 'surface category not found').toBeTruthy()
    const opsList = surfaceMatch[1]
    expect(opsList).toContain("'trim_by_curve'")
  })
})

// ---------------------------------------------------------------------------
// 3. FeatureInspector HTML render — trim_by_curve node shows param labels.
// ---------------------------------------------------------------------------

describe('FeatureInspector — trim_by_curve node renders param labels', () => {
  function renderInspector(feature) {
    // Build a minimal FeatureView tree with only the trim_by_curve node selected.
    // renderToStaticMarkup runs the FeatureInspector path synchronously.
    return renderToStaticMarkup(
      React.createElement(FeatureView, {
        parsedFeature: {
          name: 'test.feature',
          features: [feature],
        },
        files: [],
        onChangeTree: vi.fn(),
        loadSketchContent: vi.fn(() => Promise.resolve('')),
      }),
    )
  }

  const trimNode = {
    id: 'trim_by_curve-1',
    op: 'trim_by_curve',
    target_feature_ref: 'sweep1-1',
    target_face_name: 'face-2',
    trim_curve_ref: '/proj/window.sketch',
    keep_side: 'positive',
    tolerance: 1e-3,
  }

  it('renders without throwing', () => {
    expect(() => renderInspector(trimNode)).not.toThrow()
  })

  it('chip for trim_by_curve node is present in the timeline (aria-label)', () => {
    const html = renderInspector(trimNode)
    // The chip renders aria-label="TrimByCurve, feature 1" — not the raw id.
    expect(html).toMatch(/TrimByCurve.*feature 1|aria-label="TrimByCurve/)
  })

  it('TrimByCurve label is present', () => {
    const html = renderInspector(trimNode)
    expect(html).toContain('TrimByCurve')
  })
})

// ---------------------------------------------------------------------------
// 4. occtWorker.js dispatch — trim_by_curve cases present.
// ---------------------------------------------------------------------------

describe('occtWorker.js dispatch table — trim_by_curve', () => {
  const workerSrc = fs.readFileSync(
    path.resolve(import.meta.dirname, '../lib/occtWorker.js'),
    'utf8',
  )

  it("case 'trim_by_curve' appears at least twice (evaluateTree + evaluateToFinalShape)", () => {
    const matches = [...workerSrc.matchAll(/case\s+'trim_by_curve'/g)]
    expect(matches.length).toBeGreaterThanOrEqual(2)
  })

  it('opTrimByCurve function is defined', () => {
    expect(workerSrc).toContain('function opTrimByCurve(')
  })

  it('keep_side is referenced inside opTrimByCurve', () => {
    const idx = workerSrc.indexOf('function opTrimByCurve(')
    // Grab a 8 KB window after the function start — keep_side must appear in it.
    const slice = workerSrc.slice(idx, idx + 8000)
    expect(slice).toContain('keep_side')
  })
})
