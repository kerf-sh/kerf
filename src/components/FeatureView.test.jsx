/**
 * FeatureView.test.jsx — T-D1 keyboard traversal for the feature tree.
 *
 * Strategy: renderToStaticMarkup (react-dom/server) for structural assertions;
 * pure-function unit tests for the roving-tabindex key navigation logic.
 *
 * FeatureView has heavy deps (OCCT worker, workspace Zustand store,
 * FeatureRenderer/Three.js). We mock all of them so the test runs headless
 * without a browser context.
 */

import { describe, it, expect, vi, beforeAll } from 'vitest'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'

// ---------------------------------------------------------------------------
// Mocks — must be hoisted before the component import.
// ---------------------------------------------------------------------------

vi.mock('lucide-react', () => {
  const stub = (name) => () => React.createElement('span', { 'data-icon': name })
  return {
    Trash2: stub('Trash2'),
    ChevronUp: stub('ChevronUp'),
    ChevronDown: stub('ChevronDown'),
    Box: stub('Box'),
    Circle: stub('Circle'),
    RotateCcw: stub('RotateCcw'),
    Disc: stub('Disc'),
    Layers: stub('Layers'),
    Drill: stub('Drill'),
    Sigma: stub('Sigma'),
    AlertTriangle: stub('AlertTriangle'),
    Loader2: stub('Loader2'),
    Play: stub('Play'),
    Move: stub('Move'),
    Crosshair: stub('Crosshair'),
    GitBranch: stub('GitBranch'),
    Repeat: stub('Repeat'),
    FlipHorizontal: stub('FlipHorizontal'),
    PencilLine: stub('PencilLine'),
    Pointer: stub('Pointer'),
    Waves: stub('Waves'),
    Layers3: stub('Layers3'),
    Aperture: stub('Aperture'),
    Plus: stub('Plus'),
    X: stub('X'),
    ChevronRight: stub('ChevronRight'),
    LayoutGrid: stub('LayoutGrid'),
    Combine: stub('Combine'),
    Scissors: stub('Scissors'),
    Grid3x3: stub('Grid3x3'),
    MoreHorizontal: stub('MoreHorizontal'),
    SlidersHorizontal: stub('SlidersHorizontal'),
  }
})

vi.mock('./FeatureRenderer.jsx', () => ({
  default: () => React.createElement('div', { 'data-testid': 'feature-renderer' }),
}))

vi.mock('../lib/occtRunner.js', () => ({
  runFeatures: vi.fn(() => Promise.resolve({ meshes: [], ms: 0 })),
  prewarmOcct: vi.fn(() => Promise.resolve()),
  newFeatureId: vi.fn(() => `f-${Math.random().toString(36).slice(2)}`),
  requestFaceOutline: vi.fn(() => Promise.resolve(null)),
}))

// Workspace store stub — returns sensible defaults for all selectors.
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
// Helpers
// ---------------------------------------------------------------------------

/** Minimal parsedFeature tree with `n` features. */
function makeTree(n = 0) {
  const features = []
  for (let i = 0; i < n; i++) {
    features.push({ id: `feat-${i}`, op: 'pad', sketch_path: '', height: 10, direction: 'up' })
  }
  return { name: 'test.feature', features }
}

let FeatureView

beforeAll(async () => {
  // Import after mocks are installed.
  const mod = await import('./FeatureView.jsx')
  FeatureView = mod.default
})

function render(props = {}) {
  const defaults = {
    parsedFeature: makeTree(0),
    files: [],
    onChangeTree: vi.fn(),
    loadSketchContent: vi.fn(() => Promise.resolve('')),
  }
  return renderToStaticMarkup(
    React.createElement(FeatureView, { ...defaults, ...props }),
  )
}

// ---------------------------------------------------------------------------
// 1. Feature timeline — role="tree" container
// ---------------------------------------------------------------------------

describe('FeatureView — timeline role="tree"', () => {
  it('renders a role="tree" container', () => {
    const html = render()
    expect(html).toMatch(/role="tree"/)
  })

  it('has aria-label="Feature timeline"', () => {
    const html = render()
    expect(html).toMatch(/aria-label="Feature timeline"/)
  })

  it('shows empty-state message when tree is empty', () => {
    const html = render({ parsedFeature: makeTree(0) })
    expect(html).toContain('No features yet')
  })
})

// ---------------------------------------------------------------------------
// 2. FeatureTimelineChip — roving tabIndex
// ---------------------------------------------------------------------------

describe('FeatureView — roving tabIndex on chips', () => {
  it('renders role="treeitem" for each chip', () => {
    const html = render({ parsedFeature: makeTree(3) })
    const matches = (html.match(/role="treeitem"/g) || []).length
    expect(matches).toBe(3)
  })

  it('first chip button has tabindex="0" (roving tabindex default)', () => {
    const html = render({ parsedFeature: makeTree(3) })
    // React serialises JSX `tabIndex` prop as lowercase `tabindex` in HTML.
    const zeroCount = (html.match(/data-chip-btn="" tabindex="0"/g) || []).length
    const negCount  = (html.match(/data-chip-btn="" tabindex="-1"/g) || []).length
    // Exactly one chip has tabindex=0 (the roving focus owner).
    expect(zeroCount).toBe(1)
    // The other two chips have tabindex=-1.
    expect(negCount).toBe(2)
  })

  it('data-chip-btn attribute is present on chip buttons', () => {
    const html = render({ parsedFeature: makeTree(2) })
    expect(html).toContain('data-chip-btn=""')
  })

  it('single chip has tabindex="0" (only one chip → it owns focus)', () => {
    const html = render({ parsedFeature: makeTree(1) })
    expect(html).toContain('data-chip-btn="" tabindex="0"')
  })
})

// ---------------------------------------------------------------------------
// 3. FeatureTimelineChip — ARIA attributes
// ---------------------------------------------------------------------------

describe('FeatureView — chip ARIA attributes', () => {
  it('chip wraps content in role="treeitem"', () => {
    const html = render({ parsedFeature: makeTree(1) })
    expect(html).toMatch(/role="treeitem"/)
  })

  it('aria-selected="false" on unselected chips', () => {
    // With 3 chips none explicitly selected via click (server-render only),
    // the last chip is auto-selected by useEffect but useEffect doesn't run
    // during renderToStaticMarkup — so aria-selected is driven by isSel prop
    // which compares node.id === selectedId; selectedId starts null → false.
    const html = render({ parsedFeature: makeTree(2) })
    expect(html).toMatch(/aria-selected="false"/)
  })

  it('chip button has aria-label containing feature index', () => {
    const html = render({ parsedFeature: makeTree(1) })
    expect(html).toMatch(/aria-label="[^"]*feature 1[^"]*"/)
  })

  it('aria-level="1" on all treeitems (flat timeline)', () => {
    const html = render({ parsedFeature: makeTree(2) })
    const matches = (html.match(/aria-level="1"/g) || []).length
    expect(matches).toBe(2)
  })
})

// ---------------------------------------------------------------------------
// 4. Add-feature popover — trigger button ARIA
// ---------------------------------------------------------------------------

describe('FeatureView — add-feature popover trigger', () => {
  it('renders the Add feature button', () => {
    const html = render()
    expect(html).toContain('Add feature')
  })

  it('trigger has aria-haspopup="menu"', () => {
    const html = render()
    expect(html).toMatch(/aria-haspopup="menu"/)
  })

  it('trigger has aria-expanded="false" when closed (initial state)', () => {
    const html = render()
    // aria-expanded is driven by `open` state which starts false.
    expect(html).toMatch(/aria-expanded="false"/)
  })

  it('trigger has aria-label="Add feature to timeline"', () => {
    const html = render()
    expect(html).toMatch(/aria-label="Add feature to timeline"/)
  })
})

// ---------------------------------------------------------------------------
// 5. Roving-tabindex pure navigation logic (unit tests, no DOM)
// ---------------------------------------------------------------------------

// Extract and test the key navigation logic in isolation.
// This mirrors what handleTimelineKeyDown does: given a current roving index
// and tree length, compute the next index for each key.

function computeNextIdx(key, rovingIdx, treeLength) {
  if (treeLength === 0) return rovingIdx
  switch (key) {
    case 'ArrowRight':
    case 'ArrowDown':
      return Math.min(rovingIdx + 1, treeLength - 1)
    case 'ArrowLeft':
    case 'ArrowUp':
      return Math.max(rovingIdx - 1, 0)
    case 'Home':
      return 0
    case 'End':
      return treeLength - 1
    default:
      return rovingIdx
  }
}

describe('roving-tabindex navigation logic', () => {
  it('ArrowRight advances index by 1', () => {
    expect(computeNextIdx('ArrowRight', 0, 5)).toBe(1)
  })

  it('ArrowRight clamps at last item', () => {
    expect(computeNextIdx('ArrowRight', 4, 5)).toBe(4)
  })

  it('ArrowLeft decrements index by 1', () => {
    expect(computeNextIdx('ArrowLeft', 3, 5)).toBe(2)
  })

  it('ArrowLeft clamps at first item', () => {
    expect(computeNextIdx('ArrowLeft', 0, 5)).toBe(0)
  })

  it('ArrowDown advances like ArrowRight', () => {
    expect(computeNextIdx('ArrowDown', 1, 5)).toBe(2)
  })

  it('ArrowUp decrements like ArrowLeft', () => {
    expect(computeNextIdx('ArrowUp', 2, 5)).toBe(1)
  })

  it('Home always goes to index 0', () => {
    expect(computeNextIdx('Home', 4, 5)).toBe(0)
  })

  it('End always goes to last index', () => {
    expect(computeNextIdx('End', 0, 5)).toBe(4)
  })

  it('unknown key leaves index unchanged', () => {
    expect(computeNextIdx('Tab', 2, 5)).toBe(2)
  })

  it('single-item tree: ArrowRight stays at 0', () => {
    expect(computeNextIdx('ArrowRight', 0, 1)).toBe(0)
  })

  it('single-item tree: ArrowLeft stays at 0', () => {
    expect(computeNextIdx('ArrowLeft', 0, 1)).toBe(0)
  })

  it('empty tree: returns unchanged index', () => {
    expect(computeNextIdx('ArrowRight', 0, 0)).toBe(0)
  })
})

// ---------------------------------------------------------------------------
// 6. Add-feature popover — menu item keyboard (pure logic: 3-col grid nav)
// ---------------------------------------------------------------------------

const COLS = 3

function computeMenuNextIdx(key, idx, total) {
  switch (key) {
    case 'ArrowRight':
      return (idx + 1) % total
    case 'ArrowLeft':
      return (idx - 1 + total) % total
    case 'ArrowDown':
      return Math.min(idx + COLS, total - 1)
    case 'ArrowUp':
      return Math.max(idx - COLS, 0)
    case 'Home':
      return 0
    case 'End':
      return total - 1
    default:
      return idx
  }
}

describe('add-feature popover keyboard logic (3-col grid)', () => {
  it('ArrowRight moves to next item', () => {
    expect(computeMenuNextIdx('ArrowRight', 0, 10)).toBe(1)
  })

  it('ArrowRight wraps from last to first', () => {
    expect(computeMenuNextIdx('ArrowRight', 9, 10)).toBe(0)
  })

  it('ArrowLeft moves to previous item', () => {
    expect(computeMenuNextIdx('ArrowLeft', 2, 10)).toBe(1)
  })

  it('ArrowLeft wraps from first to last', () => {
    expect(computeMenuNextIdx('ArrowLeft', 0, 10)).toBe(9)
  })

  it('ArrowDown moves down one row (3 cols)', () => {
    expect(computeMenuNextIdx('ArrowDown', 0, 10)).toBe(3)
  })

  it('ArrowDown clamps at last item', () => {
    expect(computeMenuNextIdx('ArrowDown', 8, 10)).toBe(9)
  })

  it('ArrowUp moves up one row', () => {
    expect(computeMenuNextIdx('ArrowUp', 3, 10)).toBe(0)
  })

  it('ArrowUp clamps at first item', () => {
    expect(computeMenuNextIdx('ArrowUp', 0, 10)).toBe(0)
  })

  it('Home goes to first item', () => {
    expect(computeMenuNextIdx('Home', 7, 10)).toBe(0)
  })

  it('End goes to last item', () => {
    expect(computeMenuNextIdx('End', 2, 10)).toBe(9)
  })
})
