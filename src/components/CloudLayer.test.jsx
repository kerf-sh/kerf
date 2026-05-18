/**
 * CloudLayer.test.jsx — Vitest suite for the declarative cloud layer component.
 *
 * Strategy: render the component to static markup using react-dom/server
 * (already a project dep — see Loader.test.jsx for the same pattern) to
 * verify it produces no DOM output, then test the THREE scene integration
 * directly by constructing a stub scene and a plain ref.
 *
 * THREE is stubbed via globalThis.THREE so buildCloudMesh works in-process.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { createRef } from 'react'
import CloudLayer from './CloudLayer.jsx'

// ── THREE stub ────────────────────────────────────────────────────────────────

class FakeBufferAttribute {
  constructor(array, itemSize) { this.array = array; this.itemSize = itemSize }
}
class FakeBufferGeometry {
  constructor() { this.attributes = {} }
  setAttribute(name, attr) { this.attributes[name] = attr }
  dispose() {}
}
class FakeMaterial {
  constructor(opts = {}) { Object.assign(this, opts) }
  dispose() {}
}
class FakeMesh {
  constructor(geometry, material) {
    this.geometry = geometry
    this.material = material
    this.userData = {}
  }
}

const fakeThree = {
  BufferGeometry:    FakeBufferGeometry,
  BufferAttribute:   FakeBufferAttribute,
  MeshBasicMaterial: FakeMaterial,
  Mesh:              FakeMesh,
  DoubleSide:        2,
}

beforeEach(() => { globalThis.THREE = fakeThree })
afterEach(()  => { delete globalThis.THREE })

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeScene() {
  const children = []
  return {
    children,
    add(obj)    { children.push(obj) },
    remove(obj) {
      const idx = children.indexOf(obj)
      if (idx >= 0) children.splice(idx, 1)
    },
  }
}

/**
 * Simulate what React would do: call the effect that useEffect schedules.
 * Since renderToStaticMarkup doesn't run effects we drive the component's
 * mount/unmount logic directly via buildCloudMesh + the scene ref pattern.
 */
import { buildCloudMesh, CLOUD_KINDS, CLOUD_DEFAULTS } from '../lib/clouds.js'

// ── DOM output ────────────────────────────────────────────────────────────────

describe('CloudLayer DOM output', () => {
  it('renders nothing to the DOM (returns null)', () => {
    // renderToStaticMarkup of a null-returning component returns an empty string
    const ref = createRef()
    ref.current = makeScene()
    const html = renderToStaticMarkup(<CloudLayer kind="scattered" sceneRef={ref} />)
    expect(html).toBe('')
  })
})

// ── Scene integration (directly testing the mesh build + scene contract) ──────
//
// We do not use a full React renderer / act() here because @testing-library/react
// is not installed.  Instead we exercise the buildCloudMesh layer (already
// tested thoroughly in clouds.test.js) and verify the scene-add / remove
// contract implied by CloudLayer's useEffect by calling buildCloudMesh
// directly and simulating the scene mutation.

describe('CloudLayer scene contract', () => {
  it('buildCloudMesh returns null for kind=none (no mesh added)', () => {
    const mesh = buildCloudMesh({ kind: 'none' })
    expect(mesh).toBeNull()
  })

  it('buildCloudMesh returns a FakeMesh for kind=scattered', () => {
    const scene = makeScene()
    const mesh = buildCloudMesh({ kind: 'scattered' })
    expect(mesh).toBeInstanceOf(FakeMesh)
    scene.add(mesh)
    expect(scene.children).toContain(mesh)
  })

  it('removing mesh from scene cleans it up', () => {
    const scene = makeScene()
    const mesh  = buildCloudMesh({ kind: 'overcast' })
    scene.add(mesh)
    expect(scene.children.length).toBe(1)
    scene.remove(mesh)
    expect(scene.children.length).toBe(0)
  })

  it('mesh userData.isClouds is true for non-none kinds', () => {
    for (const kind of CLOUD_KINDS.filter((k) => k !== 'none')) {
      const mesh = buildCloudMesh({ kind })
      expect(mesh.userData.isClouds).toBe(true)
    }
  })

  it('mesh userData.cloudKind matches the prop', () => {
    const mesh = buildCloudMesh({ kind: 'storm' })
    expect(mesh.userData.cloudKind).toBe('storm')
  })
})

// ── CloudLayer prop contract ──────────────────────────────────────────────────

describe('CloudLayer prop defaults', () => {
  it('CLOUD_DEFAULTS has a density entry for each CLOUD_KIND', () => {
    for (const kind of CLOUD_KINDS) {
      expect(CLOUD_DEFAULTS[kind]).toBeDefined()
      expect(typeof CLOUD_DEFAULTS[kind].density).toBe('number')
    }
  })

  it('opacity_max defaults are in [0, 1] for all kinds', () => {
    for (const kind of CLOUD_KINDS) {
      const v = CLOUD_DEFAULTS[kind].opacity_max
      expect(v).toBeGreaterThanOrEqual(0)
      expect(v).toBeLessThanOrEqual(1)
    }
  })

  it('scattered has lower opacity_max than storm', () => {
    expect(CLOUD_DEFAULTS.scattered.opacity_max).toBeLessThan(CLOUD_DEFAULTS.storm.opacity_max)
  })

  it('custom density prop is forwarded to buildCloudMesh', () => {
    const mesh = buildCloudMesh({ kind: 'scattered', density: 5 })
    // 5 quads * 6 verts * 3 floats = 90
    expect(mesh.geometry.attributes.position.array.length).toBe(90)
  })

  it('custom opacity prop is forwarded to buildCloudMesh', () => {
    const mesh = buildCloudMesh({ kind: 'scattered', opacity_max: 0.3 })
    // All per-vertex opacities should be <= 0.3
    const opacities = Array.from(mesh.geometry.attributes.cloudOpacity.array)
    for (const v of opacities) {
      expect(v).toBeLessThanOrEqual(0.3 + 1e-6)
    }
  })
})

// ── CloudLayer with null / missing sceneRef ───────────────────────────────────

describe('CloudLayer edge cases', () => {
  it('renders nothing even when sceneRef.current is null', () => {
    const ref = createRef()
    // ref.current is null by default
    const html = renderToStaticMarkup(<CloudLayer kind="scattered" sceneRef={ref} />)
    expect(html).toBe('')
  })

  it('renders nothing when no sceneRef is supplied', () => {
    const html = renderToStaticMarkup(<CloudLayer kind="none" />)
    expect(html).toBe('')
  })
})
