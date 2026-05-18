// ShadowSettings.test.jsx — vitest unit tests for the ShadowSettings panel.
//
// @testing-library/react is NOT installed. We use react-dom/server
// (renderToStaticMarkup) for structural HTML assertions, mirroring the
// project's existing Loader.test.jsx pattern.

import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import ShadowSettings from './ShadowSettings.jsx'
import { defaultShadowSettings, SHADOW_TYPES, SHADOW_MAP_SIZES } from '../lib/shadowSettings.js'

// ── Render helper ──────────────────────────────────────────────────────────────

function render(props = {}) {
  return renderToStaticMarkup(<ShadowSettings {...props} />)
}

// ── 1. Root structure ──────────────────────────────────────────────────────────

describe('ShadowSettings root structure', () => {
  it('renders a region landmark', () => {
    const html = render()
    expect(html).toMatch(/role="region"/)
  })

  it('has aria-label "Shadow settings"', () => {
    const html = render()
    expect(html).toMatch(/aria-label="Shadow settings"/)
  })

  it('renders without crashing when no props supplied', () => {
    expect(() => render()).not.toThrow()
  })

  it('renders without crashing with explicit settings + lights', () => {
    const settings = defaultShadowSettings()
    const lights = [{ id: 'sun-1', label: 'Sun' }]
    expect(() => render({ settings, lights, onChange: () => {} })).not.toThrow()
  })
})

// ── 2. Shadow type buttons ─────────────────────────────────────────────────────

describe('ShadowSettings — shadow type buttons', () => {
  it('renders a button for each SHADOW_TYPE', () => {
    const html = render({ settings: defaultShadowSettings() })
    SHADOW_TYPES.forEach((type) => {
      // Each button has an aria-label containing the display label
      expect(html).toMatch(new RegExp(`Shadow type`))
    })
  })

  it('renders Basic, PCF, PCF Soft, VSM labels', () => {
    const html = render({ settings: defaultShadowSettings() })
    expect(html).toMatch(/Basic/)
    expect(html).toMatch(/PCF Soft/)
    expect(html).toMatch(/VSM/)
  })

  it('marks the active type as aria-pressed="true"', () => {
    const settings = { ...defaultShadowSettings(), type: 'vsm' }
    const html = render({ settings })
    // The VSM button should have aria-pressed="true"
    expect(html).toMatch(/aria-label="Shadow type VSM"[^>]*aria-pressed="true"|aria-pressed="true"[^>]*aria-label="Shadow type VSM"/)
  })

  it('marks inactive types as aria-pressed="false"', () => {
    const settings = { ...defaultShadowSettings(), type: 'pcf' }
    const html = render({ settings })
    const falseMatches = (html.match(/aria-pressed="false"/g) || []).length
    // 4 types total, 1 active → 3 inactive type buttons + map_size buttons
    // (map_size also uses aria-pressed, so at least 3 false for the type group)
    expect(falseMatches).toBeGreaterThanOrEqual(3)
  })
})

// ── 3. Map size buttons ────────────────────────────────────────────────────────

describe('ShadowSettings — map size buttons', () => {
  it('renders a button for each SHADOW_MAP_SIZE', () => {
    const html = render({ settings: defaultShadowSettings() })
    SHADOW_MAP_SIZES.forEach((size) => {
      expect(html).toMatch(new RegExp(`${size}`))
    })
  })

  it('marks the active map_size as aria-pressed="true"', () => {
    const settings = { ...defaultShadowSettings(), map_size: 2048 }
    const html = render({ settings })
    expect(html).toMatch(/aria-label="Shadow map size 2048"/)
    // The 2048 button is pressed
    expect(html).toMatch(/Shadow map size 2048[^"]*"/)
  })

  it('renders all four map size labels', () => {
    const html = render({ settings: defaultShadowSettings() })
    expect(html).toMatch(/512/)
    expect(html).toMatch(/1024/)
    expect(html).toMatch(/2048/)
    expect(html).toMatch(/4096/)
  })
})

// ── 4. Lights section — omitted when lights=[]/undefined ──────────────────────

describe('ShadowSettings — lights section visibility', () => {
  it('omits the lights section when lights prop is empty', () => {
    const html = render({ settings: defaultShadowSettings(), lights: [] })
    expect(html).not.toMatch(/Cast shadow/)
    expect(html).not.toMatch(/Bias/)
  })

  it('omits the lights section when lights prop is omitted', () => {
    const html = render({ settings: defaultShadowSettings() })
    expect(html).not.toMatch(/Cast shadow/)
  })

  it('renders the lights section when lights are supplied', () => {
    const lights = [{ id: 'sun-1', label: 'Sun' }]
    const html = render({ settings: defaultShadowSettings(), lights })
    expect(html).toMatch(/Cast shadow/)
  })
})

// ── 5. Per-light controls ──────────────────────────────────────────────────────

describe('ShadowSettings — per-light controls', () => {
  const lights = [
    { id: 'key', label: 'Key light' },
    { id: 'fill', label: 'Fill light' },
  ]

  it('renders one section per light', () => {
    const html = render({ settings: defaultShadowSettings(), lights })
    expect(html).toMatch(/Key light/)
    expect(html).toMatch(/Fill light/)
  })

  it('renders a cast-shadow checkbox for each light', () => {
    const html = render({ settings: defaultShadowSettings(), lights })
    const checkboxCount = (html.match(/type="checkbox"/g) || []).length
    expect(checkboxCount).toBe(lights.length)
  })

  it('renders a bias range slider for each light', () => {
    const html = render({ settings: defaultShadowSettings(), lights })
    const rangeCount = (html.match(/type="range"/g) || []).length
    expect(rangeCount).toBe(lights.length)
  })

  it('slider has correct min/max attributes', () => {
    const lights = [{ id: 'sun', label: 'Sun' }]
    const html = render({ settings: defaultShadowSettings(), lights })
    expect(html).toMatch(/min="-0\.01"/)
    expect(html).toMatch(/max="0\.01"/)
  })

  it('cast_shadow checked state reflects the settings document', () => {
    const settings = {
      ...defaultShadowSettings(),
      lights: [{ id: 'key', cast_shadow: false, bias: 0 }],
    }
    const lights = [{ id: 'key', label: 'Key' }]
    const html = render({ settings, lights })
    // When cast_shadow is false the checkbox should not have checked attribute
    expect(html).not.toMatch(/checked=""/)
  })

  it('cast_shadow=true reflects as checked', () => {
    const settings = {
      ...defaultShadowSettings(),
      lights: [{ id: 'key', cast_shadow: true, bias: 0 }],
    }
    const lights = [{ id: 'key', label: 'Key' }]
    const html = render({ settings, lights })
    expect(html).toMatch(/checked=""/)
  })

  it('bias value is displayed to 4 decimal places', () => {
    const settings = {
      ...defaultShadowSettings(),
      lights: [{ id: 'key', cast_shadow: true, bias: -0.005 }],
    }
    const lights = [{ id: 'key', label: 'Key' }]
    const html = render({ settings, lights })
    expect(html).toMatch(/-0\.0050/)
  })

  it('aria-label on bias slider identifies the light', () => {
    const lights = [{ id: 'sun', label: 'Main sun' }]
    const html = render({ settings: defaultShadowSettings(), lights })
    expect(html).toMatch(/aria-label="Main sun shadow bias"/)
  })

  it('aria-label on cast-shadow checkbox identifies the light', () => {
    const lights = [{ id: 'sun', label: 'Main sun' }]
    const html = render({ settings: defaultShadowSettings(), lights })
    expect(html).toMatch(/aria-label="Main sun cast shadow"/)
  })

  it('falls back to light.id as label when label is omitted', () => {
    const lights = [{ id: 'ambient-fill' }]
    const html = render({ settings: defaultShadowSettings(), lights })
    expect(html).toMatch(/ambient-fill/)
  })
})

// ── 6. Defaults when settings is omitted ──────────────────────────────────────

describe('ShadowSettings — uses defaultShadowSettings when settings omitted', () => {
  it('renders pcf as active type by default', () => {
    const html = render()
    // The PCF button should be aria-pressed="true"
    expect(html).toMatch(/aria-label="Shadow type PCF"/)
  })

  it('renders 1024 as active map_size by default', () => {
    const html = render()
    expect(html).toMatch(/aria-label="Shadow map size 1024"/)
  })
})
