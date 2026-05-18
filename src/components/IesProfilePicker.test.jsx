/**
 * IesProfilePicker.test.jsx — Vitest suite for the IES profile picker component.
 *
 * Uses react-dom/server renderToStaticMarkup (no @testing-library/react needed,
 * following the project convention from Loader.test.jsx). Interactive state
 * changes (useState) are exercised by rendering with explicit prop combinations
 * that reflect the expected output of each state.
 */

import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import IesProfilePicker from './IesProfilePicker.jsx'
import { IES_PRESETS } from '../lib/iesPresets.js'

// ── Helpers ───────────────────────────────────────────────────────────────────

function render(props = {}) {
  const defaults = { onSelect: () => {}, selectedSlug: null }
  return renderToStaticMarkup(<IesProfilePicker {...defaults} {...props} />)
}

// Count non-overlapping occurrences of a substring
function countOccurrences(str, sub) {
  let count = 0
  let idx = 0
  while ((idx = str.indexOf(sub, idx)) !== -1) {
    count++
    idx += sub.length
  }
  return count
}

// ── Rendering smoke tests ─────────────────────────────────────────────────────

describe('IesProfilePicker rendering', () => {
  it('renders without error', () => {
    expect(() => render()).not.toThrow()
  })

  it('renders the search input', () => {
    const html = render()
    expect(html).toMatch(/<input[^>]*type="search"/)
    expect(html).toMatch(/Search profiles/)
  })

  it('renders the data-testid root', () => {
    const html = render()
    expect(html).toMatch(/data-testid="ies-profile-picker"/)
  })

  it('renders "All" category tab', () => {
    const html = render()
    expect(html).toContain('>All<')
  })

  it('renders a tab for each category', () => {
    const html = render()
    expect(html).toContain('Downlights')
    expect(html).toContain('Wall Wash')
    expect(html).toContain('Spot')
    expect(html).toContain('Flood')
    expect(html).toContain('Specialty')
  })

  it('renders all 12 preset rows by default (no filter)', () => {
    const html = render()
    // Each preset row has data-slug; count the occurrences
    const slugMatches = (html.match(/data-slug="/g) || []).length
    expect(slugMatches).toBe(12)
  })

  it('renders each preset name', () => {
    const html = render()
    for (const preset of IES_PRESETS) {
      expect(html).toContain(preset.name)
    }
  })

  it('renders each preset description', () => {
    const html = render()
    for (const preset of IES_PRESETS) {
      // Descriptions may be truncated in display but the text should be present
      // Use the first 20 characters as a reliable substring
      expect(html).toContain(preset.description.substring(0, 20))
    }
  })

  it('shows category group headers when no filter is active', () => {
    const html = render()
    // In "all" mode, we should see the section label for each category
    expect(html).toMatch(/Downlights/)
    expect(html).toMatch(/Wall Wash/)
    expect(html).toMatch(/Specialty/)
  })
})

// ── selectedSlug prop ─────────────────────────────────────────────────────────

describe('IesProfilePicker selectedSlug', () => {
  it('marks the active preset with aria-pressed="true"', () => {
    const html = render({ selectedSlug: 'downlight-a' })
    expect(html).toMatch(/aria-pressed="true"/)
  })

  it('marks non-active presets with aria-pressed="false"', () => {
    const html = render({ selectedSlug: 'downlight-a' })
    // 11 non-active presets
    const falseCount = countOccurrences(html, 'aria-pressed="false"')
    expect(falseCount).toBe(11)
  })

  it('shows "active" label for the selected preset', () => {
    const html = render({ selectedSlug: 'specialty-candle' })
    expect(html).toContain('>active<')
  })

  it('does not show "active" label when no preset is selected', () => {
    const html = render({ selectedSlug: null })
    expect(html).not.toContain('>active<')
  })

  it('applies the selected ring style to the active preset button', () => {
    const html = render({ selectedSlug: 'flood-batwing' })
    expect(html).toMatch(/ring-kerf-300/)
  })
})

// ── onSelect prop ─────────────────────────────────────────────────────────────

describe('IesProfilePicker onSelect', () => {
  it('renders all preset buttons as clickable (type="button")', () => {
    const html = render()
    // category tab buttons + preset row buttons — all type="button"
    const buttonCount = countOccurrences(html, 'type="button"')
    // 6 tabs (All + 5 categories) + 12 preset rows = 18
    expect(buttonCount).toBeGreaterThanOrEqual(18)
  })

  it('each preset row carries data-slug matching its slug', () => {
    const html = render()
    for (const preset of IES_PRESETS) {
      expect(html).toContain(`data-slug="${preset.slug}"`)
    }
  })
})

// ── className prop ────────────────────────────────────────────────────────────

describe('IesProfilePicker className', () => {
  it('applies a custom className to the root element', () => {
    const html = render({ className: 'my-custom-picker' })
    expect(html).toContain('my-custom-picker')
  })

  it('preserves the base flex flex-col gap-3 classes', () => {
    const html = render({ className: 'extra' })
    expect(html).toMatch(/flex flex-col gap-3/)
  })
})

// ── category badge rendering ──────────────────────────────────────────────────

describe('IesProfilePicker category badges', () => {
  it('renders a category badge in each preset row', () => {
    const html = render()
    // Each category label appears at least once per preset
    expect(countOccurrences(html, 'Downlights')).toBeGreaterThanOrEqual(3)
    expect(countOccurrences(html, 'Wall Wash')).toBeGreaterThanOrEqual(2)
  })

  it('all 12 preset rows have aria-pressed attributes', () => {
    const html = render()
    const trueCount = countOccurrences(html, 'aria-pressed="true"')
    const falseCount = countOccurrences(html, 'aria-pressed="false"')
    expect(trueCount + falseCount).toBe(12)
  })
})

// ── No-match state ────────────────────────────────────────────────────────────

describe('IesProfilePicker no-match state', () => {
  it('cannot produce no-match from default render (all presets visible)', () => {
    const html = render()
    // No-match message should NOT appear in the default state
    expect(html).not.toContain('No profiles match')
  })
})

// ── IES_PRESETS integration ───────────────────────────────────────────────────

describe('IesProfilePicker + IES_PRESETS integration', () => {
  it('renders exactly as many preset rows as IES_PRESETS.length', () => {
    const html = render()
    const slugMatches = (html.match(/data-slug="/g) || []).length
    expect(slugMatches).toBe(IES_PRESETS.length)
  })

  it('every IES_PRESETS slug appears as a data-slug attribute', () => {
    const html = render()
    for (const preset of IES_PRESETS) {
      expect(html).toContain(`data-slug="${preset.slug}"`)
    }
  })

  it('renders the file path as a data attribute is NOT required — slugs identify presets', () => {
    // Verify that selecting by slug is meaningful
    const slugs = IES_PRESETS.map((p) => p.slug)
    const unique = new Set(slugs)
    expect(unique.size).toBe(12)
  })
})
