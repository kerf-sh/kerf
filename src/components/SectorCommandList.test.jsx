// SectorCommandList.test.jsx — Vitest suite for SectorCommandList.jsx
//
// Rendering strategy: renderToStaticMarkup from react-dom/server (same pattern
// used in Loader.test.jsx — no @testing-library/react required).
// We assert on the static HTML string produced by the component.

import { describe, it, expect, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import SectorCommandList from './SectorCommandList.jsx'
import { SECTOR_COMMANDS } from '../lib/sectorCommandIndex.js'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function render(props = {}) {
  return renderToStaticMarkup(<SectorCommandList {...props} />)
}

// ---------------------------------------------------------------------------
// 1. No results / empty states
// ---------------------------------------------------------------------------

describe('SectorCommandList — empty / no results', () => {
  it('renders null (empty string) when query is empty', () => {
    expect(render({ query: '' })).toBe('')
  })

  it('renders null when query is whitespace only', () => {
    expect(render({ query: '   ' })).toBe('')
  })

  it('renders null when nothing matches the query', () => {
    expect(render({ query: 'xyzzy_nothing_matches_zzz' })).toBe('')
  })
})

// ---------------------------------------------------------------------------
// 2. Structure
// ---------------------------------------------------------------------------

describe('SectorCommandList — structure', () => {
  it('renders a <ul role="listbox"> when results are present', () => {
    const html = render({ query: 'vhdl' })
    expect(html).toMatch(/<ul[^>]*role="listbox"/)
  })

  it('renders list items with role="option"', () => {
    const html = render({ query: 'vhdl' })
    expect(html).toMatch(/role="option"/)
  })

  it('renders a data-index attribute on each item', () => {
    const html = render({ query: 'vhdl' })
    expect(html).toMatch(/data-index="0"/)
  })

  it('renders aria-label="Sector commands" on the list', () => {
    const html = render({ query: 'new' })
    expect(html).toMatch(/aria-label="Sector commands"/)
  })
})

// ---------------------------------------------------------------------------
// 3. Content correctness
// ---------------------------------------------------------------------------

describe('SectorCommandList — content', () => {
  it('"vhdl" query renders "New VHDL file" label', () => {
    const html = render({ query: 'vhdl' })
    expect(html).toContain('New VHDL file')
  })

  it('"arduino" query renders "New Arduino sketch" label', () => {
    const html = render({ query: 'arduino' })
    expect(html).toContain('New Arduino sketch')
  })

  it('shows the sector badge text for each result', () => {
    const html = render({ query: 'vhdl' })
    expect(html).toContain('silicon')
  })

  it('shows the entry description', () => {
    const html = render({ query: 'vhdl' })
    // Description contains "VHDL"
    expect(html).toContain('VHDL')
  })

  it('shows action-type icon for create_file (+)', () => {
    const html = render({ query: 'vhdl' })
    expect(html).toContain('+')
  })

  it('shows action-type icon for route (→)', () => {
    const html = render({ query: 'layout viewer' })
    expect(html).toContain('→')
  })

  it('shows action-type icon for open_docs (?)', () => {
    const html = render({ query: 'sky130' })
    expect(html).toContain('?')
  })
})

// ---------------------------------------------------------------------------
// 4. maxResults cap
// ---------------------------------------------------------------------------

describe('SectorCommandList — maxResults', () => {
  it('limits results to maxResults (default 12)', () => {
    // "new" matches many entries
    const html = render({ query: 'new', maxResults: 12 })
    const matches = (html.match(/role="option"/g) || []).length
    expect(matches).toBeLessThanOrEqual(12)
  })

  it('respects a custom maxResults of 3', () => {
    const html = render({ query: 'new', maxResults: 3 })
    const matches = (html.match(/role="option"/g) || []).length
    expect(matches).toBeLessThanOrEqual(3)
  })

  it('shows fewer results than maxResults when fewer match', () => {
    // "vhdl" should only match a handful
    const html = render({ query: 'vhdl', maxResults: 12 })
    const matches = (html.match(/role="option"/g) || []).length
    expect(matches).toBeGreaterThanOrEqual(1)
    expect(matches).toBeLessThanOrEqual(5)
  })
})

// ---------------------------------------------------------------------------
// 5. activeIndex
// ---------------------------------------------------------------------------

describe('SectorCommandList — activeIndex', () => {
  it('marks the active item with aria-selected="true"', () => {
    const html = render({ query: 'vhdl', activeIndex: 0 })
    expect(html).toMatch(/aria-selected="true"/)
  })

  it('no item is aria-selected when activeIndex is -1', () => {
    const html = render({ query: 'vhdl', activeIndex: -1 })
    expect(html).not.toMatch(/aria-selected="true"/)
  })

  it('only one item is aria-selected at a time', () => {
    const html = render({ query: 'new', activeIndex: 1 })
    const trueMatches = (html.match(/aria-selected="true"/g) || []).length
    expect(trueMatches).toBeLessThanOrEqual(1)
  })
})

// ---------------------------------------------------------------------------
// 6. className passthrough
// ---------------------------------------------------------------------------

describe('SectorCommandList — className', () => {
  it('applies a custom className to the root <ul>', () => {
    const html = render({ query: 'vhdl', className: 'my-palette-section' })
    expect(html).toMatch(/my-palette-section/)
  })
})

// ---------------------------------------------------------------------------
// 7. Custom entries override
// ---------------------------------------------------------------------------

describe('SectorCommandList — custom entries', () => {
  const CUSTOM = [
    {
      id: 'custom-entry-1',
      sector: 'silicon',
      label: 'Custom silicon command',
      description: 'A custom entry for testing',
      keywords: ['custom', 'test', 'silicon'],
      action_type: 'route',
      target: '/custom',
    },
  ]

  it('uses custom entries instead of SECTOR_COMMANDS when supplied', () => {
    const html = render({ query: 'custom', entries: CUSTOM })
    expect(html).toContain('Custom silicon command')
  })

  it('does not render default entries when custom entries are supplied', () => {
    const html = render({ query: 'vhdl', entries: CUSTOM })
    // "vhdl" should not match the custom entry
    expect(html).toBe('')
  })
})

// ---------------------------------------------------------------------------
// 8. Sector badge colours — each sector gets its own badge class
// ---------------------------------------------------------------------------

describe('SectorCommandList — sector badge labels', () => {
  const SECTOR_QUERIES = [
    { sector: 'silicon',   query: 'sky130' },
    { sector: 'firmware',  query: 'serial monitor' },
    { sector: 'aerospace', query: 'flutter' },
    { sector: 'plc',       query: 'hmi' },
    { sector: 'atopile',   query: 'ato file' },
  ]

  for (const { sector, query } of SECTOR_QUERIES) {
    it(`renders "${sector}" badge for a ${sector}-sector result`, () => {
      const html = render({ query })
      expect(html).toContain(sector)
    })
  }
})
