/**
 * clouds.test.js — Vitest suite for the volumetric / billboard cloud layer.
 *
 * THREE.js objects are stubbed in-process; no DOM or GPU required.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { CLOUD_KINDS, CLOUD_DEFAULTS, noise2d, buildCloudMesh } from './clouds.js'

// ── THREE stub ────────────────────────────────────────────────────────────────

class FakeBufferAttribute {
  constructor(array, itemSize) {
    this.array    = array
    this.itemSize = itemSize
  }
}

class FakeBufferGeometry {
  constructor() {
    this.attributes = {}
  }
  setAttribute(name, attr) {
    this.attributes[name] = attr
  }
}

class FakeMaterial {
  constructor(opts = {}) {
    Object.assign(this, opts)
  }
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

beforeEach(() => {
  globalThis.THREE = fakeThree
})

afterEach(() => {
  delete globalThis.THREE
})

// ── CLOUD_KINDS ───────────────────────────────────────────────────────────────

describe('CLOUD_KINDS', () => {
  it('has exactly 4 entries', () => {
    expect(CLOUD_KINDS).toHaveLength(4)
  })

  it('contains none, scattered, overcast, storm in that order', () => {
    expect(CLOUD_KINDS).toEqual(['none', 'scattered', 'overcast', 'storm'])
  })
})

// ── CLOUD_DEFAULTS ────────────────────────────────────────────────────────────

describe('CLOUD_DEFAULTS', () => {
  it('has a key for each CLOUD_KIND', () => {
    for (const kind of CLOUD_KINDS) {
      expect(CLOUD_DEFAULTS).toHaveProperty(kind)
    }
  })

  it('none kind has density=0 and opacity_max=0', () => {
    expect(CLOUD_DEFAULTS.none.density).toBe(0)
    expect(CLOUD_DEFAULTS.none.opacity_max).toBe(0)
  })

  it('scattered has lower density than overcast', () => {
    expect(CLOUD_DEFAULTS.scattered.density).toBeLessThan(CLOUD_DEFAULTS.overcast.density)
  })

  it('storm has the highest opacity_max', () => {
    const maxOpacity = Math.max(...CLOUD_KINDS.map((k) => CLOUD_DEFAULTS[k].opacity_max))
    expect(CLOUD_DEFAULTS.storm.opacity_max).toBe(maxOpacity)
  })
})

// ── noise2d ───────────────────────────────────────────────────────────────────

describe('noise2d', () => {
  it('returns a number in [0, 1)', () => {
    const v = noise2d(1.5, 2.7, 0)
    expect(v).toBeGreaterThanOrEqual(0)
    expect(v).toBeLessThan(1)
  })

  it('is deterministic — same inputs always give the same output', () => {
    const a = noise2d(3.14, 2.72, 7)
    const b = noise2d(3.14, 2.72, 7)
    expect(a).toBe(b)
  })

  it('different seeds produce different values for the same (x, y)', () => {
    const v0 = noise2d(1, 1, 0)
    const v1 = noise2d(1, 1, 1)
    expect(v0).not.toBe(v1)
  })

  it('different (x, y) positions give different values for the same seed', () => {
    const v1 = noise2d(0,   0,   42)
    const v2 = noise2d(1,   0,   42)
    const v3 = noise2d(0,   1,   42)
    const v4 = noise2d(1,   1,   42)
    // All four should be distinct (hash collision probability is negligible)
    const unique = new Set([v1, v2, v3, v4])
    expect(unique.size).toBe(4)
  })

  it('lattice points at integer coordinates are deterministic', () => {
    expect(noise2d(0, 0, 99)).toBe(noise2d(0, 0, 99))
    expect(noise2d(10, 20, 99)).toBe(noise2d(10, 20, 99))
  })

  it('handles negative coordinates', () => {
    const v = noise2d(-5, -3, 1)
    expect(v).toBeGreaterThanOrEqual(0)
    expect(v).toBeLessThan(1)
  })

  it('fractional seeds are floor-coerced (integer part only)', () => {
    // seed is coerced to int via |0; 5.9 → 5, same as 5
    expect(noise2d(1, 1, 5)).toBe(noise2d(1, 1, 5.9))
  })
})

// ── buildCloudMesh ────────────────────────────────────────────────────────────

describe('buildCloudMesh', () => {
  it('returns null for kind=none', () => {
    expect(buildCloudMesh({ kind: 'none' })).toBeNull()
  })

  it('returns a Mesh for kind=scattered', () => {
    const mesh = buildCloudMesh({ kind: 'scattered' })
    expect(mesh).toBeInstanceOf(FakeMesh)
  })

  it('returns a Mesh for kind=overcast', () => {
    const mesh = buildCloudMesh({ kind: 'overcast' })
    expect(mesh).toBeInstanceOf(FakeMesh)
  })

  it('returns a Mesh for kind=storm', () => {
    const mesh = buildCloudMesh({ kind: 'storm' })
    expect(mesh).toBeInstanceOf(FakeMesh)
  })

  it('mesh has a BufferGeometry', () => {
    const mesh = buildCloudMesh({ kind: 'scattered' })
    expect(mesh.geometry).toBeInstanceOf(FakeBufferGeometry)
  })

  it('geometry has position, uv, and cloudOpacity attributes', () => {
    const mesh = buildCloudMesh({ kind: 'scattered' })
    expect(mesh.geometry.attributes).toHaveProperty('position')
    expect(mesh.geometry.attributes).toHaveProperty('uv')
    expect(mesh.geometry.attributes).toHaveProperty('cloudOpacity')
  })

  it('position attribute has the right number of vertices (density * 6)', () => {
    const density = 10
    const mesh = buildCloudMesh({ kind: 'scattered', density })
    const pos = mesh.geometry.attributes.position
    // Float32Array length = density * 6 * 3 (xyz)
    expect(pos.array.length).toBe(density * 6 * 3)
  })

  it('cloudOpacity values are non-zero when kind != none', () => {
    const mesh = buildCloudMesh({ kind: 'scattered', density: 20, opacity_max: 0.55, seed: 1 })
    const opacities = mesh.geometry.attributes.cloudOpacity.array
    const hasNonZero = Array.from(opacities).some((v) => v > 0)
    expect(hasNonZero).toBe(true)
  })

  it('all cloudOpacity values are <= opacity_max', () => {
    const opacityMax = 0.7
    const mesh = buildCloudMesh({ kind: 'overcast', density: 30, opacity_max: opacityMax })
    const opacities = mesh.geometry.attributes.cloudOpacity.array
    for (const v of opacities) {
      expect(v).toBeLessThanOrEqual(opacityMax + 1e-6)
    }
  })

  it('mesh userData.isClouds is true', () => {
    const mesh = buildCloudMesh({ kind: 'scattered' })
    expect(mesh.userData.isClouds).toBe(true)
  })

  it('mesh userData.cloudKind matches the supplied kind', () => {
    const mesh = buildCloudMesh({ kind: 'storm' })
    expect(mesh.userData.cloudKind).toBe('storm')
  })

  it('defaults to kind=scattered when called with no args', () => {
    const mesh = buildCloudMesh()
    expect(mesh).not.toBeNull()
    expect(mesh.userData.cloudKind).toBe('scattered')
  })

  it('uses CLOUD_DEFAULTS density when none supplied', () => {
    const mesh = buildCloudMesh({ kind: 'scattered' })
    const expected = CLOUD_DEFAULTS.scattered.density
    expect(mesh.userData.cloudDensity).toBe(expected)
  })

  it('custom density overrides the default', () => {
    const mesh = buildCloudMesh({ kind: 'scattered', density: 7 })
    expect(mesh.userData.cloudDensity).toBe(7)
    expect(mesh.geometry.attributes.position.array.length).toBe(7 * 6 * 3)
  })

  it('throws when THREE is unavailable', () => {
    delete globalThis.THREE
    expect(() => buildCloudMesh({ kind: 'scattered' })).toThrow('THREE.js not available')
    // Restore for afterEach
    globalThis.THREE = fakeThree
  })
})
