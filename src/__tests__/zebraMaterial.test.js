// zebraMaterial.test.js — unit tests for the ZebraMaterial factory.
//
// Three.js is not available in the Vitest (node) environment, so we provide a
// minimal stub via vi.mock. The factory is tested for its public API contract:
// correct uniform defaults, configurability, and shader string content.

import { describe, it, expect, vi, beforeEach } from 'vitest'

// vi.mock is hoisted above imports by Vitest's transform, so the factory
// function must NOT reference variables declared in this file. Everything
// must be defined inline inside the factory arrow.
vi.mock('three', () => {
  class Vector2 {
    constructor(x = 0, y = 0) { this.x = x; this.y = y }
  }
  class Vector3 {
    constructor(x = 0, y = 0, z = 0) { this.x = x; this.y = y; this.z = z }
  }
  class ShaderMaterial {
    constructor(opts) {
      Object.assign(this, opts)
      this._disposed = false
    }
    dispose() { this._disposed = true }
  }
  return {
    ShaderMaterial,
    Vector2,
    Vector3,
    DoubleSide: 2,
  }
})

import { createZebraMaterial } from '../lib/zebraMaterial.js'
import * as THREE from 'three'

describe('createZebraMaterial', () => {
  it('returns a ShaderMaterial instance', () => {
    const mat = createZebraMaterial()
    expect(mat).toBeInstanceOf(THREE.ShaderMaterial)
  })

  it('sets side to DoubleSide', () => {
    const mat = createZebraMaterial()
    expect(mat.side).toBe(THREE.DoubleSide)
  })

  it('includes vertex and fragment shader strings', () => {
    const mat = createZebraMaterial()
    expect(typeof mat.vertexShader).toBe('string')
    expect(typeof mat.fragmentShader).toBe('string')
    expect(mat.vertexShader.length).toBeGreaterThan(20)
    expect(mat.fragmentShader.length).toBeGreaterThan(20)
  })

  it('has required uniforms with correct default values', () => {
    const mat = createZebraMaterial()
    expect(mat.uniforms.stripeCount.value).toBe(8)
    expect(mat.uniforms.stripeAxis.value).toBeInstanceOf(THREE.Vector2)
    expect(mat.uniforms.stripeAxis.value.x).toBe(0)
    expect(mat.uniforms.stripeAxis.value.y).toBe(1)
    expect(mat.uniforms.color0.value).toBeInstanceOf(THREE.Vector3)
    expect(mat.uniforms.color1.value).toBeInstanceOf(THREE.Vector3)
  })

  it('default dark stripe colour is near-black', () => {
    const mat = createZebraMaterial()
    const c = mat.uniforms.color0.value
    expect(c.x).toBeLessThan(0.2)
    expect(c.y).toBeLessThan(0.2)
    expect(c.z).toBeLessThan(0.2)
  })

  it('default bright stripe colour is near-white', () => {
    const mat = createZebraMaterial()
    const c = mat.uniforms.color1.value
    expect(c.x).toBeGreaterThan(0.8)
    expect(c.y).toBeGreaterThan(0.8)
    expect(c.z).toBeGreaterThan(0.8)
  })

  it('accepts custom stripeCount', () => {
    const mat = createZebraMaterial({ stripeCount: 16 })
    expect(mat.uniforms.stripeCount.value).toBe(16)
  })

  it('accepts custom stripeAxis', () => {
    const mat = createZebraMaterial({ stripeAxis: [1, 0] })
    expect(mat.uniforms.stripeAxis.value.x).toBe(1)
    expect(mat.uniforms.stripeAxis.value.y).toBe(0)
  })

  it('accepts custom stripe colours', () => {
    const mat = createZebraMaterial({
      color0: [0.1, 0.2, 0.3],
      color1: [0.7, 0.8, 0.9],
    })
    expect(mat.uniforms.color0.value.x).toBeCloseTo(0.1)
    expect(mat.uniforms.color0.value.y).toBeCloseTo(0.2)
    expect(mat.uniforms.color0.value.z).toBeCloseTo(0.3)
    expect(mat.uniforms.color1.value.x).toBeCloseTo(0.7)
    expect(mat.uniforms.color1.value.y).toBeCloseTo(0.8)
    expect(mat.uniforms.color1.value.z).toBeCloseTo(0.9)
  })

  it('each call returns a distinct instance', () => {
    const a = createZebraMaterial()
    const b = createZebraMaterial()
    expect(a).not.toBe(b)
  })

  it('exposes a dispose() method', () => {
    const mat = createZebraMaterial()
    expect(typeof mat.dispose).toBe('function')
    mat.dispose()
    expect(mat._disposed).toBe(true)
  })

  it('fragment shader references stripeCount and stripeAxis uniforms', () => {
    const mat = createZebraMaterial()
    expect(mat.fragmentShader).toContain('stripeCount')
    expect(mat.fragmentShader).toContain('stripeAxis')
  })

  it('vertex shader outputs vViewNormal and vViewDir varyings', () => {
    const mat = createZebraMaterial()
    expect(mat.vertexShader).toContain('vViewNormal')
    expect(mat.vertexShader).toContain('vViewDir')
  })

  it('fragment shader uses reflection (reflect keyword)', () => {
    const mat = createZebraMaterial()
    expect(mat.fragmentShader).toContain('reflect')
  })
})
