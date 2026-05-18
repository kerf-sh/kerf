/**
 * RenderStylePicker.test.jsx — Vitest suite for the render-style picker UI.
 *
 * Uses react-dom/server (renderToStaticMarkup) to test the rendered HTML
 * structure without a DOM or browser, following the pattern in Loader.test.jsx.
 * Interaction tests (click, keyboard) are omitted here as they require
 * @testing-library/react which is not a project dependency.
 */

import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

// ── Stub lucide-react icons ───────────────────────────────────────────────────
// lucide-react ships SVG components; stub them for static render speed.

vi.mock('lucide-react', () => ({
  ChevronDown: ({ size, className, 'aria-hidden': ah }) =>
    `<svg data-icon="chevron-down" width="${size}" class="${className ?? ''}" aria-hidden="${ah ?? false}"></svg>`,
  Check: ({ size, className, 'aria-hidden': ah }) =>
    `<svg data-icon="check" width="${size}" class="${className ?? ''}" aria-hidden="${ah ?? false}"></svg>`,
}))

// ── Stub three (imported transitively via renderStyles.js) ────────────────────

vi.mock('three', () => {
  class Color { constructor(v) { this.v = v } }
  class Vector2 { constructor(x, y) { this.x = x; this.y = y } }
  class Vector3 { constructor(x, y, z) { this.x = x; this.y = y; this.z = z } }
  class MeshBasicMaterial { constructor(o={}) { Object.assign(this, o) } }
  class ShaderMaterial { constructor(o={}) { Object.assign(this, o) } }
  const UniformsUtils = { merge: (a) => Object.assign({}, ...a) }
  const UniformsLib   = { lights: {} }
  return { Color, Vector2, Vector3, MeshBasicMaterial, ShaderMaterial, UniformsUtils, UniformsLib, FrontSide: 0, BackSide: 1, DoubleSide: 2 }
})

vi.mock('three/examples/jsm/postprocessing/ShaderPass.js', () => ({
  ShaderPass: class { constructor(s) { this.isShaderPass = true; this.uniforms = s?.uniforms ?? {} } },
}))

vi.mock('three/examples/jsm/postprocessing/RenderPass.js', () => ({
  RenderPass: class { constructor() { this.isRenderPass = true } },
}))

// ── Import after mocks ─────────────────────────────────────────────────────────

import RenderStylePicker from './RenderStylePicker.jsx'
import { RENDER_STYLES } from '../lib/renderStyles.js'

// ── 1. Default render (closed state) ─────────────────────────────────────────

describe('RenderStylePicker (closed)', () => {
  it('renders a root element with data-testid="render-style-picker"', () => {
    const html = renderToStaticMarkup(<RenderStylePicker />)
    expect(html).toMatch(/data-testid="render-style-picker"/)
  })

  it('renders a trigger button', () => {
    const html = renderToStaticMarkup(<RenderStylePicker />)
    expect(html).toMatch(/<button/)
  })

  it('trigger has aria-haspopup="listbox"', () => {
    const html = renderToStaticMarkup(<RenderStylePicker />)
    expect(html).toMatch(/aria-haspopup="listbox"/)
  })

  it('trigger has aria-expanded="false" when closed', () => {
    const html = renderToStaticMarkup(<RenderStylePicker />)
    expect(html).toMatch(/aria-expanded="false"/)
  })

  it('shows the active style label in the button', () => {
    const html = renderToStaticMarkup(<RenderStylePicker activeStyle="cel" />)
    expect(html).toContain('Cel')
  })

  it('defaults to "realistic" label when no activeStyle supplied', () => {
    const html = renderToStaticMarkup(<RenderStylePicker />)
    expect(html).toContain('Realistic')
  })

  it('accepts a custom className on the root', () => {
    const html = renderToStaticMarkup(<RenderStylePicker className="test-extra" />)
    expect(html).toContain('test-extra')
  })

  it('does not render the dropdown listbox when closed (static render defaults to closed)', () => {
    const html = renderToStaticMarkup(<RenderStylePicker />)
    // Static markup renders initial state (closed) — listbox should not appear.
    expect(html).not.toMatch(/role="listbox"/)
  })
})

// ── 2. All styles are present in RENDER_STYLES ────────────────────────────────

describe('RENDER_STYLES (via import in component test)', () => {
  it('exports RENDER_STYLES array', () => {
    expect(Array.isArray(RENDER_STYLES)).toBe(true)
  })

  const names = ['realistic', 'cel', 'wireframe', 'hidden-line', 'sketch', 'blueprint']
  names.forEach((n) => {
    it(`RENDER_STYLES contains "${n}"`, () => {
      expect(RENDER_STYLES).toContain(n)
    })
  })
})

// ── 3. Component renders each activeStyle without throwing ────────────────────

describe('RenderStylePicker activeStyle prop', () => {
  RENDER_STYLES.forEach((style) => {
    it(`renders without error for activeStyle="${style}"`, () => {
      expect(() => renderToStaticMarkup(<RenderStylePicker activeStyle={style} />)).not.toThrow()
    })
  })
})

// ── 4. aria-label on the trigger ──────────────────────────────────────────────

describe('RenderStylePicker aria-label', () => {
  it('includes the active style name in aria-label', () => {
    const html = renderToStaticMarkup(<RenderStylePicker activeStyle="blueprint" />)
    expect(html).toMatch(/aria-label="Render style: Blueprint"/)
  })
})
