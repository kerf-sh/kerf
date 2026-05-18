/**
 * HdriPicker.test.jsx — Vitest suite for the HDRI sky preset picker component.
 *
 * Uses react-dom/server renderToStaticMarkup (no @testing-library required),
 * following the established pattern in Loader.test.jsx.
 */

import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import HdriPicker from './HdriPicker.jsx'
import { HDRI_PRESETS } from '../lib/hdriPresets.js'

// ── Rendering ─────────────────────────────────────────────────────────────────

describe('HdriPicker rendering', () => {
  it('renders without crashing', () => {
    const html = renderToStaticMarkup(<HdriPicker />)
    expect(typeof html).toBe('string')
    expect(html.length).toBeGreaterThan(0)
  })

  it('renders a wrapper with role="group"', () => {
    const html = renderToStaticMarkup(<HdriPicker />)
    expect(html).toMatch(/role="group"/)
  })

  it('renders an aria-label on the group', () => {
    const html = renderToStaticMarkup(<HdriPicker />)
    expect(html).toMatch(/aria-label="HDRI sky preset"/)
  })

  it('renders one button per preset (5 total)', () => {
    const html = renderToStaticMarkup(<HdriPicker />)
    const buttons = html.match(/<button\b/g) || []
    expect(buttons.length).toBe(HDRI_PRESETS.length)
  })

  it('each button has an aria-label mentioning the preset name', () => {
    const html = renderToStaticMarkup(<HdriPicker />)
    HDRI_PRESETS.forEach((p) => {
      expect(html).toContain(`Select HDRI preset: ${p.name}`)
    })
  })

  it('all buttons have type="button"', () => {
    const html = renderToStaticMarkup(<HdriPicker />)
    const typeButtons = html.match(/type="button"/g) || []
    expect(typeButtons.length).toBe(HDRI_PRESETS.length)
  })

  it('renders preset names as visible text', () => {
    const html = renderToStaticMarkup(<HdriPicker />)
    HDRI_PRESETS.forEach((p) => {
      expect(html).toContain(p.name)
    })
  })

  it('accepts an extra className on the wrapper', () => {
    const html = renderToStaticMarkup(<HdriPicker className="my-test-class" />)
    expect(html).toContain('my-test-class')
  })
})

// ── Selection state ───────────────────────────────────────────────────────────

describe('HdriPicker selection', () => {
  it('no preset has aria-pressed="true" when value is null', () => {
    const html = renderToStaticMarkup(<HdriPicker value={null} />)
    expect(html).not.toMatch(/aria-pressed="true"/)
  })

  it('the matching preset button has aria-pressed="true" when value is set', () => {
    const html = renderToStaticMarkup(<HdriPicker value="sunset" />)
    // There should be exactly one aria-pressed="true"
    const truePresses = html.match(/aria-pressed="true"/g) || []
    expect(truePresses.length).toBe(1)
  })

  it('other preset buttons have aria-pressed="false" when one is selected', () => {
    const html = renderToStaticMarkup(<HdriPicker value="overcast" />)
    const falsePresses = html.match(/aria-pressed="false"/g) || []
    expect(falsePresses.length).toBe(HDRI_PRESETS.length - 1)
  })

  it('selected button title includes the preset description', () => {
    const preset = HDRI_PRESETS.find((p) => p.slug === 'clear-noon')
    const html = renderToStaticMarkup(<HdriPicker value="clear-noon" />)
    expect(html).toContain(preset.description)
  })

  it('renders the check badge svg only for the selected preset', () => {
    const html = renderToStaticMarkup(<HdriPicker value="studio-soft" />)
    // The check badge is a small svg inside the selected button
    const svgs = html.match(/<svg\b/g) || []
    expect(svgs.length).toBe(1)
  })
})

// ── Thumbnail handling ────────────────────────────────────────────────────────

describe('HdriPicker thumbnails', () => {
  it('renders an <img> for each preset that has a thumbnail_url', () => {
    const withThumbs = HDRI_PRESETS.filter((p) => p.thumbnail_url !== null)
    const html = renderToStaticMarkup(<HdriPicker />)
    const imgs = html.match(/<img\b/g) || []
    expect(imgs.length).toBe(withThumbs.length)
  })
})
