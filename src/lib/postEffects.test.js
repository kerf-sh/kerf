/**
 * postEffects.test.js — Vitest suite for the post-effects stack module.
 *
 * All Three.js pass constructors are stubbed so no GPU or DOM is required.
 * Tests cover:
 *   - POST_EFFECTS has exactly 6 entries with the correct keys
 *   - clampSettings: in-range values pass through unchanged
 *   - clampSettings: out-of-range values clamp to bounds
 *   - clampSettings: NaN values snap to DEFAULT_SETTINGS
 *   - makeEffectStack: returns a chain array of expected length when each effect is enabled
 *   - makeEffectStack: dispose() clears the chain
 */

import { describe, it, expect, vi } from 'vitest'
import {
  POST_EFFECTS,
  DEFAULT_SETTINGS,
  clampSettings,
  makeEffectStack,
} from './postEffects.js'

// ── Stub pass constructors ────────────────────────────────────────────────────

/**
 * Create a minimal fake Three.js Pass with a uniforms map and a dispose spy.
 */
function makePass(name, uniformKeys = []) {
  return class FakePass {
    constructor(...args) {
      this._name = name
      this._args = args
      this.uniforms = {}
      for (const k of uniformKeys) this.uniforms[k] = { value: null }
      this.dispose = vi.fn()
    }
  }
}

const FakeSSAOPass        = makePass('SSAOPass')
const FakeBokehPass       = makePass('BokehPass')
const FakeUnrealBloomPass = makePass('UnrealBloomPass')

// ShaderPass copies the shader's uniforms on construction
class FakeShaderPass {
  constructor(shader) {
    this._shader = shader
    this.uniforms = {}
    if (shader && shader.uniforms) {
      for (const [k, v] of Object.entries(shader.uniforms)) {
        this.uniforms[k] = { value: v.value }
      }
    }
    this.dispose = vi.fn()
  }
}

const FakeRGBShiftShader = {
  name: 'RGBShiftShader',
  uniforms: { tDiffuse: { value: null }, amount: { value: 0.005 }, angle: { value: 0.0 } },
  vertexShader: '',
  fragmentShader: '',
}

const FakeVignetteShader = {
  name: 'VignetteShader',
  uniforms: { tDiffuse: { value: null }, offset: { value: 1.0 }, darkness: { value: 1.0 } },
  vertexShader: '',
  fragmentShader: '',
}

const FakeFilmPass = makePass('FilmPass')

class FakeVector2 {
  constructor(x = 0, y = 0) { this.x = x; this.y = y }
}

/** Build a _passes injection object with all stubs. */
const ALL_PASSES = {
  SSAOPass:        FakeSSAOPass,
  BokehPass:       FakeBokehPass,
  UnrealBloomPass: FakeUnrealBloomPass,
  ShaderPass:      FakeShaderPass,
  RGBShiftShader:  FakeRGBShiftShader,
  VignetteShader:  FakeVignetteShader,
  FilmPass:        FakeFilmPass,
  Vector2:         FakeVector2,
}

/** Build a minimal fake renderer that returns the given size. */
function makeRenderer(w = 512, h = 512) {
  return {
    getSize(v2) { v2.x = w; v2.y = h; return v2 },
  }
}

function makeScene() { return {} }
function makeCamera() { return { aspect: 1, fov: 45, near: 0.1, far: 1000 } }

// ── 1. POST_EFFECTS registry ──────────────────────────────────────────────────

describe('POST_EFFECTS', () => {
  it('has exactly 6 entries', () => {
    expect(POST_EFFECTS).toHaveLength(6)
  })

  it('contains bloom', () => expect(POST_EFFECTS).toContain('bloom'))
  it('contains dof',   () => expect(POST_EFFECTS).toContain('dof'))
  it('contains vignette', () => expect(POST_EFFECTS).toContain('vignette'))
  it('contains grain', () => expect(POST_EFFECTS).toContain('grain'))
  it('contains ssao',  () => expect(POST_EFFECTS).toContain('ssao'))
  it('contains chromatic', () => expect(POST_EFFECTS).toContain('chromatic'))
})

// ── 2. clampSettings — pass-through for valid values ─────────────────────────

describe('clampSettings — valid values pass through', () => {
  it('returns bloom.threshold unchanged when in [0, 1]', () => {
    const out = clampSettings({ bloom: { threshold: 0.5 } })
    expect(out.bloom.threshold).toBeCloseTo(0.5)
  })

  it('returns dof.focal_distance unchanged when >= 0', () => {
    const out = clampSettings({ dof: { focal_distance: 5.0 } })
    expect(out.dof.focal_distance).toBeCloseTo(5.0)
  })

  it('returns dof.aperture unchanged when in [0.001, 0.1]', () => {
    const out = clampSettings({ dof: { aperture: 0.05 } })
    expect(out.dof.aperture).toBeCloseTo(0.05)
  })

  it('returns vignette.intensity unchanged when in [0, 1]', () => {
    const out = clampSettings({ vignette: { intensity: 0.3 } })
    expect(out.vignette.intensity).toBeCloseTo(0.3)
  })

  it('returns grain.intensity unchanged when in [0, 0.5]', () => {
    const out = clampSettings({ grain: { intensity: 0.2 } })
    expect(out.grain.intensity).toBeCloseTo(0.2)
  })

  it('returns ssao.radius unchanged when in [0, 2]', () => {
    const out = clampSettings({ ssao: { radius: 1.0 } })
    expect(out.ssao.radius).toBeCloseTo(1.0)
  })

  it('returns ssao.intensity unchanged when in [0, 2]', () => {
    const out = clampSettings({ ssao: { intensity: 1.5 } })
    expect(out.ssao.intensity).toBeCloseTo(1.5)
  })

  it('returns chromatic.amount unchanged when in [0, 0.05]', () => {
    const out = clampSettings({ chromatic: { amount: 0.02 } })
    expect(out.chromatic.amount).toBeCloseTo(0.02)
  })
})

// ── 3. clampSettings — values clamp to bounds ─────────────────────────────────

describe('clampSettings — out-of-range clamping', () => {
  it('clamps bloom.threshold above 1 to 1', () => {
    const out = clampSettings({ bloom: { threshold: 2.5 } })
    expect(out.bloom.threshold).toBe(1)
  })

  it('clamps bloom.threshold below 0 to 0', () => {
    const out = clampSettings({ bloom: { threshold: -0.5 } })
    expect(out.bloom.threshold).toBe(0)
  })

  it('clamps dof.focal_distance below 0 to 0', () => {
    const out = clampSettings({ dof: { focal_distance: -10 } })
    expect(out.dof.focal_distance).toBe(0)
  })

  it('clamps dof.aperture below 0.001 to 0.001', () => {
    const out = clampSettings({ dof: { aperture: 0 } })
    expect(out.dof.aperture).toBe(0.001)
  })

  it('clamps dof.aperture above 0.1 to 0.1', () => {
    const out = clampSettings({ dof: { aperture: 1.0 } })
    expect(out.dof.aperture).toBe(0.1)
  })

  it('clamps vignette.intensity above 1 to 1', () => {
    const out = clampSettings({ vignette: { intensity: 5.0 } })
    expect(out.vignette.intensity).toBe(1)
  })

  it('clamps vignette.intensity below 0 to 0', () => {
    const out = clampSettings({ vignette: { intensity: -1 } })
    expect(out.vignette.intensity).toBe(0)
  })

  it('clamps grain.intensity above 0.5 to 0.5', () => {
    const out = clampSettings({ grain: { intensity: 2.0 } })
    expect(out.grain.intensity).toBe(0.5)
  })

  it('clamps grain.intensity below 0 to 0', () => {
    const out = clampSettings({ grain: { intensity: -0.1 } })
    expect(out.grain.intensity).toBe(0)
  })

  it('clamps ssao.radius above 2 to 2', () => {
    const out = clampSettings({ ssao: { radius: 99 } })
    expect(out.ssao.radius).toBe(2)
  })

  it('clamps ssao.radius below 0 to 0', () => {
    const out = clampSettings({ ssao: { radius: -1 } })
    expect(out.ssao.radius).toBe(0)
  })

  it('clamps ssao.intensity above 2 to 2', () => {
    const out = clampSettings({ ssao: { intensity: 10 } })
    expect(out.ssao.intensity).toBe(2)
  })

  it('clamps ssao.intensity below 0 to 0', () => {
    const out = clampSettings({ ssao: { intensity: -5 } })
    expect(out.ssao.intensity).toBe(0)
  })

  it('clamps chromatic.amount above 0.05 to 0.05', () => {
    const out = clampSettings({ chromatic: { amount: 1.0 } })
    expect(out.chromatic.amount).toBe(0.05)
  })

  it('clamps chromatic.amount below 0 to 0', () => {
    const out = clampSettings({ chromatic: { amount: -0.1 } })
    expect(out.chromatic.amount).toBe(0)
  })
})

// ── 4. clampSettings — NaN snaps to default ───────────────────────────────────

describe('clampSettings — NaN snaps to DEFAULT_SETTINGS', () => {
  it('bloom.threshold NaN snaps to default', () => {
    const out = clampSettings({ bloom: { threshold: NaN } })
    expect(out.bloom.threshold).toBe(DEFAULT_SETTINGS.bloom.threshold)
  })

  it('dof.focal_distance NaN snaps to default', () => {
    const out = clampSettings({ dof: { focal_distance: NaN } })
    expect(out.dof.focal_distance).toBe(DEFAULT_SETTINGS.dof.focal_distance)
  })

  it('dof.aperture NaN snaps to default', () => {
    const out = clampSettings({ dof: { aperture: NaN } })
    expect(out.dof.aperture).toBe(DEFAULT_SETTINGS.dof.aperture)
  })

  it('vignette.intensity NaN snaps to default', () => {
    const out = clampSettings({ vignette: { intensity: NaN } })
    expect(out.vignette.intensity).toBe(DEFAULT_SETTINGS.vignette.intensity)
  })

  it('grain.intensity NaN snaps to default', () => {
    const out = clampSettings({ grain: { intensity: NaN } })
    expect(out.grain.intensity).toBe(DEFAULT_SETTINGS.grain.intensity)
  })

  it('ssao.radius NaN snaps to default', () => {
    const out = clampSettings({ ssao: { radius: NaN } })
    expect(out.ssao.radius).toBe(DEFAULT_SETTINGS.ssao.radius)
  })

  it('ssao.intensity NaN snaps to default', () => {
    const out = clampSettings({ ssao: { intensity: NaN } })
    expect(out.ssao.intensity).toBe(DEFAULT_SETTINGS.ssao.intensity)
  })

  it('chromatic.amount NaN snaps to default', () => {
    const out = clampSettings({ chromatic: { amount: NaN } })
    expect(out.chromatic.amount).toBe(DEFAULT_SETTINGS.chromatic.amount)
  })
})

// ── 5. makeEffectStack — chain length ─────────────────────────────────────────

describe('makeEffectStack — chain length', () => {
  const renderer = makeRenderer()
  const scene    = makeScene()
  const camera   = makeCamera()

  it('returns an empty chain when all effects are disabled', () => {
    const settings = {
      bloom: { enabled: false },
      dof: { enabled: false },
      vignette: { enabled: false },
      grain: { enabled: false },
      ssao: { enabled: false },
      chromatic: { enabled: false },
    }
    const { chain } = makeEffectStack({ renderer, scene, camera, settings, _passes: ALL_PASSES })
    expect(chain).toHaveLength(0)
  })

  it('returns 1 pass when only bloom is enabled', () => {
    const settings = {
      ...DEFAULT_SETTINGS,
      bloom: { ...DEFAULT_SETTINGS.bloom, enabled: true },
      dof: { enabled: false },
      vignette: { enabled: false },
      grain: { enabled: false },
      ssao: { enabled: false },
      chromatic: { enabled: false },
    }
    const { chain } = makeEffectStack({ renderer, scene, camera, settings, _passes: ALL_PASSES })
    expect(chain).toHaveLength(1)
  })

  it('returns 1 pass when only ssao is enabled', () => {
    const settings = {
      ...DEFAULT_SETTINGS,
      bloom: { enabled: false },
      dof: { enabled: false },
      vignette: { enabled: false },
      grain: { enabled: false },
      ssao: { ...DEFAULT_SETTINGS.ssao, enabled: true },
      chromatic: { enabled: false },
    }
    const { chain } = makeEffectStack({ renderer, scene, camera, settings, _passes: ALL_PASSES })
    expect(chain).toHaveLength(1)
  })

  it('returns 1 pass when only dof is enabled', () => {
    const settings = {
      ...DEFAULT_SETTINGS,
      bloom: { enabled: false },
      dof: { ...DEFAULT_SETTINGS.dof, enabled: true },
      vignette: { enabled: false },
      grain: { enabled: false },
      ssao: { enabled: false },
      chromatic: { enabled: false },
    }
    const { chain } = makeEffectStack({ renderer, scene, camera, settings, _passes: ALL_PASSES })
    expect(chain).toHaveLength(1)
  })

  it('returns 1 pass when only vignette is enabled', () => {
    const settings = {
      ...DEFAULT_SETTINGS,
      bloom: { enabled: false },
      dof: { enabled: false },
      vignette: { ...DEFAULT_SETTINGS.vignette, enabled: true },
      grain: { enabled: false },
      ssao: { enabled: false },
      chromatic: { enabled: false },
    }
    const { chain } = makeEffectStack({ renderer, scene, camera, settings, _passes: ALL_PASSES })
    expect(chain).toHaveLength(1)
  })

  it('returns 1 pass when only grain is enabled', () => {
    const settings = {
      ...DEFAULT_SETTINGS,
      bloom: { enabled: false },
      dof: { enabled: false },
      vignette: { enabled: false },
      grain: { ...DEFAULT_SETTINGS.grain, enabled: true },
      ssao: { enabled: false },
      chromatic: { enabled: false },
    }
    const { chain } = makeEffectStack({ renderer, scene, camera, settings, _passes: ALL_PASSES })
    expect(chain).toHaveLength(1)
  })

  it('returns 1 pass when only chromatic is enabled', () => {
    const settings = {
      ...DEFAULT_SETTINGS,
      bloom: { enabled: false },
      dof: { enabled: false },
      vignette: { enabled: false },
      grain: { enabled: false },
      ssao: { enabled: false },
      chromatic: { ...DEFAULT_SETTINGS.chromatic, enabled: true },
    }
    const { chain } = makeEffectStack({ renderer, scene, camera, settings, _passes: ALL_PASSES })
    expect(chain).toHaveLength(1)
  })

  it('returns 6 passes when all effects are enabled', () => {
    const settings = {
      bloom:    { ...DEFAULT_SETTINGS.bloom,    enabled: true },
      dof:      { ...DEFAULT_SETTINGS.dof,      enabled: true },
      vignette: { ...DEFAULT_SETTINGS.vignette, enabled: true },
      grain:    { ...DEFAULT_SETTINGS.grain,    enabled: true },
      ssao:     { ...DEFAULT_SETTINGS.ssao,     enabled: true },
      chromatic:{ ...DEFAULT_SETTINGS.chromatic,enabled: true },
    }
    const { chain } = makeEffectStack({ renderer, scene, camera, settings, _passes: ALL_PASSES })
    expect(chain).toHaveLength(6)
  })

  it('chain is ordered: SSAO first when both ssao + bloom enabled', () => {
    const settings = {
      bloom:    { ...DEFAULT_SETTINGS.bloom,    enabled: true },
      dof:      { enabled: false },
      vignette: { enabled: false },
      grain:    { enabled: false },
      ssao:     { ...DEFAULT_SETTINGS.ssao,     enabled: true },
      chromatic:{ enabled: false },
    }
    const { chain } = makeEffectStack({ renderer, scene, camera, settings, _passes: ALL_PASSES })
    expect(chain[0]).toBeInstanceOf(FakeSSAOPass)
    expect(chain[1]).toBeInstanceOf(FakeUnrealBloomPass)
  })
})

// ── 6. makeEffectStack — dispose ──────────────────────────────────────────────

describe('makeEffectStack — dispose', () => {
  it('dispose() calls dispose on each pass', () => {
    const settings = {
      bloom:    { ...DEFAULT_SETTINGS.bloom,    enabled: true },
      dof:      { enabled: false },
      vignette: { ...DEFAULT_SETTINGS.vignette, enabled: true },
      grain:    { enabled: false },
      ssao:     { enabled: false },
      chromatic:{ enabled: false },
    }
    const renderer = makeRenderer()
    const { chain, dispose } = makeEffectStack({
      renderer, scene: makeScene(), camera: makeCamera(), settings, _passes: ALL_PASSES,
    })
    expect(chain).toHaveLength(2)
    for (const p of chain) {
      expect(typeof p.dispose).toBe('function')
    }
    dispose()
    expect(chain).toHaveLength(0)
  })
})
