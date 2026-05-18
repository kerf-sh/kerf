/**
 * renderStyles.test.js — Vitest suite for the render-style preset registry.
 *
 * All Three.js and postprocessing objects are stubbed so no DOM / GPU context
 * is required. Tests cover: style registry, getStylePass contracts, and GLSL
 * shader file presence/validity.
 */

import { describe, it, expect, vi, beforeAll } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'
import { fileURLToPath } from 'url'

// ── Three.js stub ─────────────────────────────────────────────────────────────
// Minimal stubs for the Three.js constructors used by renderStyles.js.

vi.mock('three', () => {
  class Color {
    constructor(v) { this.v = v }
  }
  class Vector2 {
    constructor(x, y) { this.x = x; this.y = y }
  }
  class Vector3 {
    constructor(x, y, z) { this.x = x; this.y = y; this.z = z }
  }
  class MeshBasicMaterial {
    constructor(opts = {}) { Object.assign(this, opts); this.isMeshBasicMaterial = true }
  }
  class ShaderMaterial {
    constructor(opts = {}) { Object.assign(this, opts); this.isShaderMaterial = true }
  }
  const UniformsUtils = {
    merge: (arr) => Object.assign({}, ...arr),
  }
  const UniformsLib = {
    lights: {},
  }
  const FrontSide  = 0
  const BackSide   = 1
  const DoubleSide = 2
  return {
    Color, Vector2, Vector3,
    MeshBasicMaterial, ShaderMaterial,
    UniformsUtils, UniformsLib,
    FrontSide, BackSide, DoubleSide,
  }
})

// ── postprocessing stubs ───────────────────────────────────────────────────────

vi.mock('three/examples/jsm/postprocessing/ShaderPass.js', () => ({
  ShaderPass: class ShaderPass {
    constructor(shader) {
      this.isShaderPass = true
      this.uniforms = shader?.uniforms ?? {}
      this.fragmentShader = shader?.fragmentShader ?? ''
      this.vertexShader   = shader?.vertexShader   ?? ''
    }
  },
}))

vi.mock('three/examples/jsm/postprocessing/RenderPass.js', () => ({
  RenderPass: class RenderPass {
    constructor(scene, camera) {
      this.isRenderPass = true
      this.scene  = scene
      this.camera = camera
    }
  },
}))

// ── Import after mocks ─────────────────────────────────────────────────────────

import { RENDER_STYLES, getStylePass } from './renderStyles.js'

// ── 1. Style registry ─────────────────────────────────────────────────────────

describe('RENDER_STYLES', () => {
  it('is an array', () => {
    expect(Array.isArray(RENDER_STYLES)).toBe(true)
  })

  it('contains exactly 6 entries', () => {
    expect(RENDER_STYLES).toHaveLength(6)
  })

  const expected = ['realistic', 'cel', 'wireframe', 'hidden-line', 'sketch', 'blueprint']
  expected.forEach((name) => {
    it(`includes style "${name}"`, () => {
      expect(RENDER_STYLES).toContain(name)
    })
  })
})

// ── 2. getStylePass contracts ─────────────────────────────────────────────────

describe('getStylePass', () => {
  it('returns null for "realistic"', () => {
    expect(getStylePass('realistic')).toBeNull()
  })

  it('returns a non-null pass object for "wireframe"', () => {
    const pass = getStylePass('wireframe')
    expect(pass).not.toBeNull()
    expect(typeof pass).toBe('object')
  })

  it('wireframe pass has type "material-replace"', () => {
    const pass = getStylePass('wireframe')
    expect(pass.type).toBe('material-replace')
  })

  it('wireframe material has wireframe:true', () => {
    const pass = getStylePass('wireframe')
    expect(pass.material.wireframe).toBe(true)
  })

  it('wireframe hiddenLine is false', () => {
    const pass = getStylePass('wireframe')
    expect(pass.hiddenLine).toBe(false)
  })

  it('hidden-line pass has hiddenLine:true', () => {
    const pass = getStylePass('hidden-line')
    expect(pass.hiddenLine).toBe(true)
  })

  it('hidden-line has a backMaterial for back-facing edges', () => {
    const pass = getStylePass('hidden-line')
    expect(pass.backMaterial).not.toBeNull()
  })

  it('cel returns an array of passes', () => {
    const passes = getStylePass('cel')
    expect(Array.isArray(passes)).toBe(true)
    expect(passes.length).toBeGreaterThanOrEqual(2)
  })

  it('cel passes include a render pass and an outline shader pass', () => {
    const passes = getStylePass('cel')
    const names = passes.map((p) => p.name ?? p.type)
    expect(names).toContain('render')
    expect(passes.some((p) => p.name === 'cel-outline')).toBe(true)
  })

  it('sketch returns an array of passes', () => {
    const passes = getStylePass('sketch')
    expect(Array.isArray(passes)).toBe(true)
    expect(passes.length).toBeGreaterThanOrEqual(3)
  })

  it('sketch passes include outline and hatch stages', () => {
    const passes = getStylePass('sketch')
    expect(passes.some((p) => p.name === 'sketch-outline')).toBe(true)
    expect(passes.some((p) => p.name === 'sketch-hatch')).toBe(true)
  })

  it('blueprint returns an array of passes', () => {
    const passes = getStylePass('blueprint')
    expect(Array.isArray(passes)).toBe(true)
    expect(passes.length).toBeGreaterThanOrEqual(2)
  })

  it('blueprint passes include a blueprint shader stage', () => {
    const passes = getStylePass('blueprint')
    expect(passes.some((p) => p.name === 'blueprint')).toBe(true)
  })

  it('throws for an unknown style name', () => {
    expect(() => getStylePass('neon')).toThrow(/unknown style/)
  })

  it('accepts optional ctx argument without throwing', () => {
    const fakeCtx = {
      renderer: { domElement: { width: 800, height: 600 } },
      scene: {},
      camera: {},
    }
    // Should not throw; RenderPass stub accepts any args.
    expect(() => getStylePass('cel', fakeCtx)).not.toThrow()
  })
})

// ── 3. Shader file validation ─────────────────────────────────────────────────

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const SHADER_DIR = path.resolve(__dirname, '../shaders')

describe('shader files', () => {
  const shaders = ['cel_outline.glsl', 'sketch_hatching.glsl', 'blueprint.glsl']

  shaders.forEach((filename) => {
    describe(filename, () => {
      let src

      beforeAll(() => {
        src = fs.readFileSync(path.join(SHADER_DIR, filename), 'utf8')
      })

      it('exists and is non-empty', () => {
        expect(src.length).toBeGreaterThan(0)
      })

      it('contains a void main() entry point', () => {
        expect(src).toMatch(/void\s+main\s*\(\s*\)/)
      })

      it('contains at least one uniform declaration', () => {
        expect(src).toMatch(/uniform\s+\w/)
      })
    })
  })
})
