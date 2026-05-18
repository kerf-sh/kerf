import { describe, it, expect, vi, beforeEach } from 'vitest'

// ---------------------------------------------------------------------------
// Mock THREE before importing the module under test.
// vi.mock factories are hoisted to the top of the file by vitest, so all
// class definitions must live *inside* the factory (no outer references).
// ---------------------------------------------------------------------------

vi.mock('three', () => {
  class FakeLight {
    constructor(color, intensity) {
      this.color = color
      this.intensity = intensity
      this.position = { set: vi.fn() }
      this.castShadow = false
      this.shadow = { mapSize: {} }
      this._disposed = false
    }
    dispose() { this._disposed = true }
  }

  class DirectionalLight extends FakeLight {
    constructor(color, intensity) { super(color, intensity); this.type = 'DirectionalLight' }
  }

  class RectAreaLight extends FakeLight {
    constructor(color, intensity, w, h) {
      super(color, intensity)
      this.width = w
      this.height = h
      this.type = 'RectAreaLight'
    }
    lookAt(...args) { this.lookedAt = args }
  }

  class PointLight extends FakeLight {
    constructor(color, intensity, distance) {
      super(color, intensity)
      this.distance = distance
      this.type = 'PointLight'
    }
  }

  class SpotLight extends FakeLight {
    constructor(color, intensity) {
      super(color, intensity)
      this.type = 'SpotLight'
      this.angle = 0
      const target = new FakeLight()
      target.position = { set: vi.fn() }
      this.target = target
    }
  }

  return { DirectionalLight, RectAreaLight, PointLight, SpotLight }
})

vi.mock('three/examples/jsm/lights/RectAreaLightUniformsLib.js', () => ({
  RectAreaLightUniformsLib: { init: vi.fn() },
}))

// Import the module under test *after* mocks are registered.
import { applyDocLightsToScene } from './applyDocLightsToScene.js'
import * as THREE from 'three'

// ---------------------------------------------------------------------------
// Fake scene helper.
// ---------------------------------------------------------------------------
function makeScene() {
  const objects = []
  return {
    add: vi.fn((...args) => objects.push(...args)),
    remove: vi.fn((obj) => {
      const i = objects.indexOf(obj)
      if (i !== -1) objects.splice(i, 1)
    }),
    _objects: objects,
  }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('applyDocLightsToScene', () => {
  let scene

  beforeEach(() => {
    scene = makeScene()
  })

  // --- empty input ---

  it('returns empty array and adds no lights for empty docLights', () => {
    const handles = applyDocLightsToScene(scene, [], { target: [0, 0, 0], prevHandles: [] })
    expect(handles).toHaveLength(0)
    expect(scene.add).not.toHaveBeenCalled()
  })

  it('returns empty array for null / undefined docLights', () => {
    const handles = applyDocLightsToScene(scene, null, { prevHandles: [] })
    expect(handles).toHaveLength(0)
    expect(scene.add).not.toHaveBeenCalled()
  })

  // --- disposal of previous handles ---

  it('disposes and removes previous handles before adding new ones', () => {
    const prev1 = new THREE.DirectionalLight('#fff', 1)
    const prev2 = new THREE.PointLight('#fff', 1, 0)

    const removeOrder = []
    scene.remove = vi.fn((_obj) => removeOrder.push('remove'))

    const docLights = [{ kind: 'sun', direction: [0, -1, 0], intensity: 1 }]
    applyDocLightsToScene(scene, docLights, { target: [0, 0, 0], prevHandles: [prev1, prev2] })

    // Both prev lights must have been disposed.
    expect(prev1._disposed).toBe(true)
    expect(prev2._disposed).toBe(true)

    // remove() must have been called twice (for the two prev handles).
    expect(removeOrder).toHaveLength(2)

    // The new light must have been added after removal.
    expect(scene.add).toHaveBeenCalled()
  })

  // --- 'sun' kind ---

  it("maps kind='sun' to DirectionalLight with castShadow=true", () => {
    const docLights = [
      { kind: 'sun', direction: [0, -1, 0], intensity: 3, color: '#ffddaa' },
    ]
    const handles = applyDocLightsToScene(scene, docLights, { target: [0, 0, 0], prevHandles: [] })

    expect(handles).toHaveLength(1)
    const light = handles[0]
    expect(light).toBeInstanceOf(THREE.DirectionalLight)
    expect(light.castShadow).toBe(true)
    expect(light.intensity).toBe(3)
    expect(light.color).toBe('#ffddaa')
  })

  it('positions sun light by inverting direction × 10000 from target', () => {
    const docLights = [{ kind: 'sun', direction: [0, -1, 0], intensity: 1 }]
    const handles = applyDocLightsToScene(scene, docLights, { target: [10, 20, 30], prevHandles: [] })

    const light = handles[0]
    // direction [0,-1,0] normalised → [0,-1,0]
    // inverted → [0,+1,0] × 10000 → [0, 10000, 0]
    // + target [10,20,30] → [10, 10020, 30]
    expect(light.position.set).toHaveBeenCalledWith(10, 10020, 30)
  })

  // --- 'area' kind ---

  it("maps kind='area' to RectAreaLight", () => {
    const docLights = [
      { kind: 'area', position: [100, 200, 300], size_mm: 500, intensity: 2, color: '#e8f0ff' },
    ]
    const handles = applyDocLightsToScene(scene, docLights, { target: [0, 0, 0], prevHandles: [] })

    expect(handles).toHaveLength(1)
    const light = handles[0]
    expect(light).toBeInstanceOf(THREE.RectAreaLight)
    expect(light.width).toBe(500)
    expect(light.height).toBe(500)
    expect(light.intensity).toBe(2)
  })

  it('calls lookAt on RectAreaLight toward target', () => {
    const docLights = [
      { kind: 'area', position: [0, 1000, 0], size_mm: 500, intensity: 1 },
    ]
    const handles = applyDocLightsToScene(scene, docLights, { target: [5, 10, 15], prevHandles: [] })

    const light = handles[0]
    expect(light.lookedAt).toEqual([5, 10, 15])
  })

  // --- 'point' kind ---

  it("maps kind='point' to PointLight", () => {
    const docLights = [
      { kind: 'point', position: [50, 50, 50], intensity: 1.5, distance: 2000, color: '#ffffff' },
    ]
    const handles = applyDocLightsToScene(scene, docLights, { target: [0, 0, 0], prevHandles: [] })

    expect(handles).toHaveLength(1)
    const light = handles[0]
    expect(light).toBeInstanceOf(THREE.PointLight)
    expect(light.intensity).toBe(1.5)
    expect(light.distance).toBe(2000)
    expect(light.position.set).toHaveBeenCalledWith(50, 50, 50)
  })

  // --- 'spot' kind ---

  it("maps kind='spot' to SpotLight", () => {
    const docLights = [
      { kind: 'spot', position: [0, 5000, 0], angle: Math.PI / 6, intensity: 4 },
    ]
    const handles = applyDocLightsToScene(scene, docLights, { target: [0, 0, 0], prevHandles: [] })

    // handles includes the SpotLight + its target object
    const spotLight = handles.find((h) => h instanceof THREE.SpotLight)
    expect(spotLight).toBeDefined()
    expect(spotLight.angle).toBeCloseTo(Math.PI / 6)
    expect(spotLight.intensity).toBe(4)
  })

  it('defaults spot angle to π/4 when not provided', () => {
    const docLights = [{ kind: 'spot', position: [0, 3000, 0] }]
    const handles = applyDocLightsToScene(scene, docLights, { target: [0, 0, 0], prevHandles: [] })

    const spotLight = handles.find((h) => h instanceof THREE.SpotLight)
    expect(spotLight.angle).toBeCloseTo(Math.PI / 4)
  })

  // --- mixed kinds ---

  it('handles multiple lights of different kinds in one call', () => {
    const docLights = [
      { kind: 'sun', direction: [-1, -1, 0], intensity: 5 },
      { kind: 'point', position: [0, 200, 0], intensity: 2 },
    ]
    const handles = applyDocLightsToScene(scene, docLights, { target: [0, 0, 0], prevHandles: [] })

    const sun = handles.find((h) => h instanceof THREE.DirectionalLight)
    const pt = handles.find((h) => h instanceof THREE.PointLight)
    expect(sun).toBeDefined()
    expect(pt).toBeDefined()
  })

  // --- unknown kind — skipped silently ---

  it('skips unknown kinds without throwing', () => {
    const docLights = [{ kind: 'laser', intensity: 10 }]
    expect(() =>
      applyDocLightsToScene(scene, docLights, { target: [0, 0, 0], prevHandles: [] }),
    ).not.toThrow()
    expect(scene.add).not.toHaveBeenCalled()
  })

  // --- returns new handles ---

  it('returns new handles that can be passed as prevHandles next call', () => {
    const first = applyDocLightsToScene(scene, [{ kind: 'sun', direction: [0, -1, 0] }], {
      target: [0, 0, 0],
      prevHandles: [],
    })
    expect(first.length).toBeGreaterThan(0)

    // Second call should dispose the first batch.
    const second = applyDocLightsToScene(scene, [], { target: [0, 0, 0], prevHandles: first })
    expect(first[0]._disposed).toBe(true)
    expect(second).toHaveLength(0)
  })
})
