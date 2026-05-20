/**
 * dfmOverlay.test.js — vitest tests for src/lib/dfmOverlay.js
 *
 * Uses stubbed Three.js objects so no WebGL context is required.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'

// ---------------------------------------------------------------------------
// Three.js stub — must be defined before importing the module under test
// ---------------------------------------------------------------------------

vi.mock('three', () => {
  class FakeGeometry {
    dispose() {}
  }
  class FakeMaterial {
    constructor(opts) { Object.assign(this, opts) }
    dispose() {}
  }
  class FakeMesh {
    constructor(geo, mat) {
      this.geometry = geo
      this.material = mat
      this.position = { set: vi.fn() }
      this.renderOrder = 0
      this.userData = {}
    }
  }
  class FakeScene {
    constructor() { this.children = [] }
    add(obj) { this.children.push(obj) }
    remove(obj) { this.children = this.children.filter((c) => c !== obj) }
  }
  class FakeCamera {}
  class FakeVector2 {
    constructor() { this.x = 0; this.y = 0 }
  }
  class FakeRaycaster {
    constructor() { this._hits = [] }
    setFromCamera() {}
    intersectObjects() { return this._hits }
  }
  // FakeRenderer — no DOM, no WebGL
  class FakeRenderer {
    constructor() {
      this.domElement = {
        getBoundingClientRect: () => ({ left: 0, top: 0, width: 800, height: 600 }),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      }
    }
  }
  return {
    SphereGeometry: FakeGeometry,
    MeshBasicMaterial: FakeMaterial,
    Mesh: FakeMesh,
    Scene: FakeScene,
    Camera: FakeCamera,
    Vector2: FakeVector2,
    Raycaster: FakeRaycaster,
    WebGLRenderer: FakeRenderer,
  }
})

// Import AFTER the mock is registered so the overlay uses fake THREE classes.
import { attachDfmOverlay, detachDfmOverlay, refreshDfm, severityColor, dfmIssueSrText, Z_INDEX } from './dfmOverlay.js'
import * as THREE from 'three'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeScene()    { return new THREE.Scene() }
function makeCamera()   { return new THREE.Camera() }
function makeRenderer() { return new THREE.WebGLRenderer() }

function makeIssue(overrides = {}) {
  return {
    kind: 'thin_wall',
    position: [1, 2, 3],
    severity: 'warning',
    value: 0.5,
    suggestion: 'Increase wall thickness.',
    ...overrides,
  }
}

// Stub document.body.appendChild used by _buildTooltip and _buildSrLive inside
// dfmOverlay.  jsdom is not available in the default vitest node environment so
// we patch the minimal surface the overlay touches.
function makeFakeEl() {
  return {
    style: { cssText: '', display: 'none', left: '', top: '' },
    innerHTML: '',
    textContent: '',
    parentNode: null,
    _attrs: {},
    setAttribute(k, v) { this._attrs[k] = v },
    getAttribute(k) { return this._attrs[k] ?? null },
  }
}

function stubDocument() {
  const origDoc = globalThis.document
  globalThis.document = {
    createElement: () => {
      const el = makeFakeEl()
      return el
    },
    body: {
      appendChild: (el) => {
        el.parentNode = { removeChild: vi.fn() }
        return el
      },
    },
  }
  return () => { globalThis.document = origDoc }
}

// ---------------------------------------------------------------------------
// severityColor
// ---------------------------------------------------------------------------

describe('severityColor', () => {
  it('returns red for error', () => {
    expect(severityColor('error')).toBe(0xef4444)
  })

  it('returns amber for warning', () => {
    expect(severityColor('warning')).toBe(0xf59e0b)
  })

  it('returns blue for info', () => {
    expect(severityColor('info')).toBe(0x60a5fa)
  })

  it('returns grey for unknown severity', () => {
    expect(severityColor('critical')).toBe(0x9ca3af)
    expect(severityColor(undefined)).toBe(0x9ca3af)
  })
})

// ---------------------------------------------------------------------------
// attachDfmOverlay / detachDfmOverlay
// ---------------------------------------------------------------------------

describe('attachDfmOverlay', () => {
  let restoreDoc

  beforeEach(() => {
    restoreDoc = stubDocument()
  })

  afterEach(() => {
    detachDfmOverlay()
    restoreDoc()
    vi.restoreAllMocks()
  })

  it('adds one marker per valid issue', () => {
    const scene = makeScene()
    const issues = [makeIssue(), makeIssue({ position: [4, 5, 6], kind: 'sharp_corner' })]
    attachDfmOverlay(scene, makeCamera(), makeRenderer(), issues)
    expect(scene.children).toHaveLength(2)
  })

  it('skips issues with missing position', () => {
    const scene = makeScene()
    const issues = [
      makeIssue(),
      { kind: 'bad', severity: 'error', suggestion: '' },  // no position
    ]
    attachDfmOverlay(scene, makeCamera(), makeRenderer(), issues)
    expect(scene.children).toHaveLength(1)
  })

  it('handles empty issues array', () => {
    const scene = makeScene()
    attachDfmOverlay(scene, makeCamera(), makeRenderer(), [])
    expect(scene.children).toHaveLength(0)
  })

  it('handles null issues gracefully', () => {
    const scene = makeScene()
    attachDfmOverlay(scene, makeCamera(), makeRenderer(), null)
    expect(scene.children).toHaveLength(0)
  })

  it('replaces prior overlay on re-attach', () => {
    const scene = makeScene()
    attachDfmOverlay(scene, makeCamera(), makeRenderer(), [makeIssue()])
    attachDfmOverlay(scene, makeCamera(), makeRenderer(), [makeIssue(), makeIssue({ position: [7, 8, 9] })])
    expect(scene.children).toHaveLength(2)
  })

  it('marker count equals issues length', () => {
    const scene = makeScene()
    const issues = [makeIssue(), makeIssue({ position: [4, 5, 6] }), makeIssue({ position: [7, 8, 9] })]
    attachDfmOverlay(scene, makeCamera(), makeRenderer(), issues)
    expect(scene.children).toHaveLength(issues.length)
  })
})

// ---------------------------------------------------------------------------
// detachDfmOverlay
// ---------------------------------------------------------------------------

describe('detachDfmOverlay', () => {
  let restoreDoc

  beforeEach(() => { restoreDoc = stubDocument() })

  afterEach(() => {
    detachDfmOverlay()
    restoreDoc()
    vi.restoreAllMocks()
  })

  it('removes all markers from scene', () => {
    const scene = makeScene()
    attachDfmOverlay(scene, makeCamera(), makeRenderer(), [makeIssue(), makeIssue({ position: [4, 5, 6] })])
    detachDfmOverlay()
    expect(scene.children).toHaveLength(0)
  })

  it('calling detach twice does not throw', () => {
    attachDfmOverlay(makeScene(), makeCamera(), makeRenderer(), [makeIssue()])
    detachDfmOverlay()
    expect(() => detachDfmOverlay()).not.toThrow()
  })

  it('unregisters mousemove listener', () => {
    const renderer = makeRenderer()
    attachDfmOverlay(makeScene(), makeCamera(), renderer, [makeIssue()])
    detachDfmOverlay()
    expect(renderer.domElement.removeEventListener).toHaveBeenCalledWith('mousemove', expect.any(Function))
  })
})

// ---------------------------------------------------------------------------
// refreshDfm
// ---------------------------------------------------------------------------

describe('refreshDfm', () => {
  let restoreDoc

  beforeEach(() => { restoreDoc = stubDocument() })

  afterEach(() => {
    detachDfmOverlay()
    restoreDoc()
    vi.restoreAllMocks()
  })

  it('swaps markers without leaking old ones', () => {
    const scene = makeScene()
    attachDfmOverlay(scene, makeCamera(), makeRenderer(), [makeIssue()])
    refreshDfm([makeIssue(), makeIssue({ position: [4, 5, 6] })])
    expect(scene.children).toHaveLength(2)
  })

  it('refreshing to empty removes all markers', () => {
    const scene = makeScene()
    attachDfmOverlay(scene, makeCamera(), makeRenderer(), [makeIssue(), makeIssue({ position: [4, 5, 6] })])
    refreshDfm([])
    expect(scene.children).toHaveLength(0)
  })

  it('does not throw when called before attach', () => {
    expect(() => refreshDfm([makeIssue()])).not.toThrow()
  })

  it('severity colour applied — error marker uses error colour', () => {
    const scene = makeScene()
    attachDfmOverlay(scene, makeCamera(), makeRenderer(), [makeIssue({ severity: 'error' })])
    const marker = scene.children[0]
    expect(marker.material.color).toBe(severityColor('error'))
  })
})

// ---------------------------------------------------------------------------
// Z_INDEX token
// ---------------------------------------------------------------------------

describe('Z_INDEX', () => {
  it('exports a frozen token object', () => {
    expect(Z_INDEX).toBeDefined()
    expect(Object.isFrozen(Z_INDEX)).toBe(true)
  })

  it('tooltip layer is higher than overlay layer', () => {
    expect(Z_INDEX.tooltip).toBeGreaterThan(Z_INDEX.overlay)
  })

  it('tooltip layer is higher than modal layer', () => {
    expect(Z_INDEX.tooltip).toBeGreaterThan(Z_INDEX.modal)
  })

  it('tooltip z-index is not the legacy hard-coded 9999', () => {
    expect(Z_INDEX.tooltip).not.toBe(9999)
  })

  it('tooltip cssText uses the Z_INDEX.tooltip token value', () => {
    const restoreDoc = stubDocument()
    try {
      let capturedCssText = ''
      const origCreateElement = globalThis.document.createElement
      globalThis.document.createElement = () => {
        const el = makeFakeEl()
        Object.defineProperty(el.style, 'cssText', {
          set(v) { capturedCssText += v },
          get() { return capturedCssText },
          configurable: true,
        })
        return el
      }
      attachDfmOverlay(makeScene(), makeCamera(), makeRenderer(), [])
      expect(capturedCssText).toContain(`z-index:${Z_INDEX.tooltip}`)
    } finally {
      detachDfmOverlay()
      restoreDoc()
    }
  })
})

// ---------------------------------------------------------------------------
// dfmIssueSrText
// ---------------------------------------------------------------------------

describe('dfmIssueSrText', () => {
  it('includes severity and kind', () => {
    const text = dfmIssueSrText({ severity: 'warning', kind: 'thin_wall', value: 0.5, suggestion: 'Increase thickness.' })
    expect(text).toContain('warning')
    expect(text).toContain('thin_wall')
  })

  it('includes formatted value', () => {
    const text = dfmIssueSrText({ severity: 'error', kind: 'undercut', value: 1.23456 })
    expect(text).toContain('1.235')
  })

  it('includes suggestion', () => {
    const text = dfmIssueSrText({ severity: 'info', kind: 'draft_angle', suggestion: 'Add draft.' })
    expect(text).toContain('Add draft.')
  })

  it('defaults severity to info when missing', () => {
    const text = dfmIssueSrText({ kind: 'thin_wall' })
    expect(text).toMatch(/^DFM info/)
  })

  it('omits value section when value is null/undefined', () => {
    const text = dfmIssueSrText({ severity: 'warning', kind: 'overhang' })
    expect(text).not.toContain('value')
  })
})

// ---------------------------------------------------------------------------
// SR live region — attachment lifecycle + announcement
// ---------------------------------------------------------------------------

describe('SR live region', () => {
  let restoreDoc
  // Track all elements created via createElement so we can inspect srLive.
  let createdEls

  beforeEach(() => {
    restoreDoc = stubDocument()
    createdEls = []
    const origCreate = globalThis.document.createElement
    globalThis.document.createElement = (...args) => {
      const el = origCreate(...args)
      createdEls.push(el)
      return el
    }
  })

  afterEach(() => {
    detachDfmOverlay()
    restoreDoc()
    vi.restoreAllMocks()
  })

  function getSrLiveEl() {
    // The srLive element is the one with aria-live attribute set.
    return createdEls.find((el) => el._attrs?.['aria-live'] === 'assertive')
  }

  it('creates an aria-live=assertive element on attach', () => {
    attachDfmOverlay(makeScene(), makeCamera(), makeRenderer(), [])
    const srEl = getSrLiveEl()
    expect(srEl).toBeDefined()
    expect(srEl.getAttribute('aria-live')).toBe('assertive')
  })

  it('sets aria-atomic and role=status on the SR node', () => {
    attachDfmOverlay(makeScene(), makeCamera(), makeRenderer(), [])
    const srEl = getSrLiveEl()
    expect(srEl.getAttribute('aria-atomic')).toBe('true')
    expect(srEl.getAttribute('role')).toBe('status')
  })

  it('removes the SR live node on detach', () => {
    attachDfmOverlay(makeScene(), makeCamera(), makeRenderer(), [])
    const srEl = getSrLiveEl()
    detachDfmOverlay()
    expect(srEl.parentNode.removeChild).toHaveBeenCalledWith(srEl)
  })
})
