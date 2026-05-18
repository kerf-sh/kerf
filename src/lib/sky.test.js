/**
 * sky.test.js — Vitest unit tests for elevationAzimuthToDirection.
 *
 * Three.js is mocked below so no GPU / DOM is required.
 */

import { describe, it, expect, vi, beforeAll } from 'vitest'

// ── Minimal THREE stubs ────────────────────────────────────────────────────────

// We provide a real-math Vector3 stub so that the direction calculations can
// be verified numerically without requiring a full Three.js environment.

class Vector3Stub {
  constructor(x = 0, y = 0, z = 0) {
    this.x = x
    this.y = y
    this.z = z
  }
  normalize() {
    const len = Math.sqrt(this.x ** 2 + this.y ** 2 + this.z ** 2)
    if (len > 0) {
      this.x /= len
      this.y /= len
      this.z /= len
    }
    return this
  }
  copy(v) {
    this.x = v.x
    this.y = v.y
    this.z = v.z
    return this
  }
}

// Stub Sky class with the minimum uniform surface needed by createProceduralSky.
function makeSkySurfaceUniform(initial = 0) {
  return { value: initial }
}

class SkyStub {
  constructor() {
    this.isSky = true
    this.scale = { setScalar() {} }
    this.material = {
      uniforms: {
        turbidity:       makeSkySurfaceUniform(1),
        rayleigh:        makeSkySurfaceUniform(1),
        mieCoefficient:  makeSkySurfaceUniform(0),
        mieDirectionalG: makeSkySurfaceUniform(0),
        sunPosition:     { value: new Vector3Stub() },
      },
    }
  }
}

vi.mock('three/examples/jsm/objects/Sky.js', () => ({ Sky: SkyStub }))
vi.mock('three', () => ({ Vector3: Vector3Stub }))

// ── Import the module under test AFTER mocks are registered ───────────────────

const { elevationAzimuthToDirection, createProceduralSky } = await import('./sky.js')

// ── Helpers ────────────────────────────────────────────────────────────────────

const SQRT2_OVER_2 = Math.SQRT2 / 2   // ≈ 0.7071067811865476

// ── Tests: elevationAzimuthToDirection ────────────────────────────────────────

describe('elevationAzimuthToDirection', () => {
  it('elevation=0 → y-component is 0 (sun on the horizon)', () => {
    const dir = elevationAzimuthToDirection(0, 0)
    expect(dir.y).toBeCloseTo(0, 12)
  })

  it('elevation=90 → direction is (0, 1, 0) (sun at zenith)', () => {
    const dir = elevationAzimuthToDirection(90, 0)
    expect(dir.x).toBeCloseTo(0, 12)
    expect(dir.y).toBeCloseTo(1, 12)
    expect(dir.z).toBeCloseTo(0, 12)
  })

  it('elevation=45, azimuth=0 → direction is (√2/2, √2/2, 0)', () => {
    const dir = elevationAzimuthToDirection(45, 0)
    expect(Math.abs(dir.x - SQRT2_OVER_2)).toBeLessThan(1e-12)
    expect(Math.abs(dir.y - SQRT2_OVER_2)).toBeLessThan(1e-12)
    expect(Math.abs(dir.z)).toBeLessThan(1e-12)
  })

  it('returns a unit vector (length ≈ 1) for arbitrary angles', () => {
    const dir = elevationAzimuthToDirection(33, 127)
    const len = Math.sqrt(dir.x ** 2 + dir.y ** 2 + dir.z ** 2)
    expect(len).toBeCloseTo(1, 12)
  })
})

// ── Tests: createProceduralSky ─────────────────────────────────────────────────

describe('createProceduralSky', () => {
  it('returns a sky object and a sunPosition Vector3', () => {
    const { sky, sunPosition } = createProceduralSky()
    expect(sky).toBeDefined()
    expect(sky.isSky).toBe(true)
    expect(sunPosition).toBeInstanceOf(Vector3Stub)
  })

  it('sets turbidity uniform from options', () => {
    const { sky } = createProceduralSky({ turbidity: 5 })
    expect(sky.material.uniforms.turbidity.value).toBe(5)
  })

  it('sets rayleigh uniform from options', () => {
    const { sky } = createProceduralSky({ rayleigh: 2 })
    expect(sky.material.uniforms.rayleigh.value).toBe(2)
  })

  it('sets mieCoefficient uniform from options', () => {
    const { sky } = createProceduralSky({ mieCoefficient: 0.01 })
    expect(sky.material.uniforms.mieCoefficient.value).toBe(0.01)
  })

  it('sets mieDirectionalG uniform from options', () => {
    const { sky } = createProceduralSky({ mieDirectionalG: 0.9 })
    expect(sky.material.uniforms.mieDirectionalG.value).toBe(0.9)
  })

  it('sunPosition y ≈ 0 when elevation is 0', () => {
    const { sunPosition } = createProceduralSky({ elevation_deg: 0, azimuth_deg: 0 })
    expect(sunPosition.y).toBeCloseTo(0, 12)
  })

  it('sunPosition y ≈ 1 when elevation is 90', () => {
    const { sunPosition } = createProceduralSky({ elevation_deg: 90, azimuth_deg: 0 })
    expect(sunPosition.y).toBeCloseTo(1, 12)
  })

  it('uses defaults when called with no arguments', () => {
    const { sky, sunPosition } = createProceduralSky()
    expect(sky.material.uniforms.turbidity.value).toBe(10)
    expect(sky.material.uniforms.rayleigh.value).toBe(3)
    // elevation default is 15° → y = sin(15° in rad) > 0
    expect(sunPosition.y).toBeGreaterThan(0)
  })
})
