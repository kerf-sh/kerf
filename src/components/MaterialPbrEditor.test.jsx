// MaterialPbrEditor.test.jsx — vitest tests for the PBR editor component.
//
// Uses react-dom/server (renderToStaticMarkup) — same pattern as Loader.test.jsx.
// No @testing-library/react dependency.

import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import MaterialPbrEditor from './MaterialPbrEditor.jsx'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function render(props = {}) {
  return renderToStaticMarkup(<MaterialPbrEditor {...props} />)
}

// ---------------------------------------------------------------------------
// Rendering smoke tests
// ---------------------------------------------------------------------------

describe('MaterialPbrEditor render', () => {
  it('renders without throwing', () => {
    expect(() => render()).not.toThrow()
  })

  it('renders the data-testid root', () => {
    const html = render()
    expect(html).toMatch(/data-testid="material-pbr-editor"/)
  })

  it('shows "PBR" section label in header', () => {
    const html = render()
    expect(html).toMatch(/PBR/)
  })

  it('shows the material name in the header', () => {
    const html = render({ material: { name: 'Titanium' } })
    expect(html).toContain('Titanium')
  })

  it('falls back to "Untitled" when material has no name', () => {
    const html = render({ material: {} })
    expect(html).toContain('Untitled')
  })

  it('renders the preview sphere', () => {
    const html = render()
    expect(html).toMatch(/data-testid="preview-sphere"/)
    expect(html).toMatch(/aria-label="PBR material preview sphere"/)
  })

  it('renders the Save as… button', () => {
    const html = render()
    expect(html).toMatch(/data-testid="save-as-button"/)
    expect(html).toMatch(/Save as/)
  })
})

// ---------------------------------------------------------------------------
// Slider presence
// ---------------------------------------------------------------------------

describe('MaterialPbrEditor sliders', () => {
  const EXPECTED_SLIDERS = [
    'slider-base_color',  // color input
    'slider-metalness',
    'slider-roughness',
    'slider-ior',
    'slider-transmission',
    'slider-clearcoat',
    'slider-sheen',
    'slider-anisotropy',
    'slider-subsurface',
  ]

  it('renders a control for each expected PBR property', () => {
    const html = render()
    for (const testid of EXPECTED_SLIDERS) {
      expect(html, `missing ${testid}`).toMatch(
        new RegExp(`data-testid="${testid}"`)
      )
    }
  })

  it('metalness slider has min=0 max=1', () => {
    const html = render()
    // Attributes can appear in any order in the tag; check each separately
    expect(html).toMatch(/slider-metalness/)
    expect(html).toMatch(/min="0"[^>]*data-testid="slider-metalness"|data-testid="slider-metalness"[^>]*min="0"/)
    expect(html).toMatch(/max="1"[^>]*data-testid="slider-metalness"|data-testid="slider-metalness"[^>]*max="1"/)
  })

  it('roughness slider has min=0 max=1', () => {
    const html = render()
    expect(html).toMatch(/slider-roughness/)
    // The slider tag must have min="0" and max="1" somewhere within it
    expect(html).toContain('data-testid="slider-roughness"')
    const roughnessTag = html.match(/<input[^>]*slider-roughness[^>]*>/)?.[0] ?? ''
    expect(roughnessTag).toMatch(/min="0"/)
    expect(roughnessTag).toMatch(/max="1"/)
  })

  it('ior slider has min=1 max=3', () => {
    const html = render()
    expect(html).toContain('data-testid="slider-ior"')
    const iorTag = html.match(/<input[^>]*slider-ior[^>]*>/)?.[0] ?? ''
    expect(iorTag).toMatch(/min="1"/)
    expect(iorTag).toMatch(/max="3"/)
  })

  it('anisotropy slider has min=-1 max=1', () => {
    const html = render()
    expect(html).toContain('data-testid="slider-anisotropy"')
    const anisoTag = html.match(/<input[^>]*slider-anisotropy[^>]*>/)?.[0] ?? ''
    expect(anisoTag).toMatch(/min="-1"/)
    expect(anisoTag).toMatch(/max="1"/)
  })

  it('all 8 range sliders are rendered', () => {
    const html = render()
    const rangeCount = (html.match(/type="range"/g) || []).length
    expect(rangeCount).toBe(8)
  })
})

// ---------------------------------------------------------------------------
// Loading from T-115 BIM catalogue
// ---------------------------------------------------------------------------

describe('MaterialPbrEditor loading from T-115 catalogue', () => {
  const glassMaterial = {
    name: 'Float Glass',
    category: 'building/glazing',
    color_hex: '#c8e8f0',
    pbr: {
      metalness: 0,
      roughness: 0.05,
      ior: 1.52,
      transmission: 0.95,
      clearcoat: 0,
      sheen: 0,
      anisotropy: 0,
      subsurface: 0,
      base_color: [0.78, 0.91, 0.94],
    },
  }

  it('renders without error for a BIM catalogue entry', () => {
    expect(() => render({ material: glassMaterial })).not.toThrow()
  })

  it('shows the material name', () => {
    const html = render({ material: glassMaterial })
    expect(html).toContain('Float Glass')
  })

  it('sets the roughness slider value from catalogue', () => {
    const html = render({ material: glassMaterial })
    const tag = html.match(/<input[^>]*slider-roughness[^>]*>/)?.[0] ?? ''
    expect(tag).toMatch(/value="0.05"/)
  })

  it('sets the ior slider value from catalogue', () => {
    const html = render({ material: glassMaterial })
    const tag = html.match(/<input[^>]*slider-ior[^>]*>/)?.[0] ?? ''
    expect(tag).toMatch(/value="1.52"/)
  })

  it('sets the transmission slider value from catalogue', () => {
    const html = render({ material: glassMaterial })
    const tag = html.match(/<input[^>]*slider-transmission[^>]*>/)?.[0] ?? ''
    expect(tag).toMatch(/value="0.95"/)
  })
})

// ---------------------------------------------------------------------------
// Loading from T-214 flat PBR shape
// ---------------------------------------------------------------------------

describe('MaterialPbrEditor loading from flat PBR (T-214)', () => {
  const flatMaterial = {
    name: 'Brushed Steel',
    metalness: 0.9,
    roughness: 0.4,
    ior: 2.5,
    transmission: 0,
    clearcoat: 0,
    sheen: 0,
    anisotropy: 0.5,
    subsurface: 0,
    base_color: [0.7, 0.7, 0.75],
    color_hex: '#b2b2bf',
  }

  it('renders without error', () => {
    expect(() => render({ material: flatMaterial })).not.toThrow()
  })

  it('loads metalness from flat shape', () => {
    const html = render({ material: flatMaterial })
    const tag = html.match(/<input[^>]*slider-metalness[^>]*>/)?.[0] ?? ''
    expect(tag).toMatch(/value="0.9"/)
  })

  it('loads anisotropy from flat shape', () => {
    const html = render({ material: flatMaterial })
    const tag = html.match(/<input[^>]*slider-anisotropy[^>]*>/)?.[0] ?? ''
    expect(tag).toMatch(/value="0.5"/)
  })
})

// ---------------------------------------------------------------------------
// Close button
// ---------------------------------------------------------------------------

describe('MaterialPbrEditor close button', () => {
  it('renders close button when onClose is provided', () => {
    const html = render({ onClose: vi.fn() })
    expect(html).toMatch(/data-testid="pbr-close"/)
    expect(html).toMatch(/aria-label="Close PBR editor"/)
  })

  it('does not render close button when onClose is not provided', () => {
    const html = render({})
    expect(html).not.toMatch(/data-testid="pbr-close"/)
  })
})

// ---------------------------------------------------------------------------
// Null / edge-case material
// ---------------------------------------------------------------------------

describe('MaterialPbrEditor edge cases', () => {
  it('renders with null material', () => {
    expect(() => render({ material: null })).not.toThrow()
  })

  it('renders with undefined material', () => {
    expect(() => render({ material: undefined })).not.toThrow()
  })

  it('renders with empty object material', () => {
    expect(() => render({ material: {} })).not.toThrow()
  })

  it('accepts className prop', () => {
    const html = render({ className: 'test-extra-class' })
    expect(html).toMatch(/test-extra-class/)
  })
})
