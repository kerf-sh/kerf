/**
 * domainSwitcher.test.jsx
 *
 * Smoke tests for the shared DomainSwitcher tab strip.
 *
 * No jsdom in this project, so we assert the exported DOMAIN_TABS data
 * and the declarative source shape (links for all five domains, the
 * active-marking branch, horizontal-scroll on narrow screens), and that
 * every domain page imports and renders the switcher.
 */

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import { DOMAIN_TABS } from '../components/domains/DomainSwitcher.jsx'

const SWITCHER_SRC = readFileSync(
  resolve(__dirname, '../components/domains/DomainSwitcher.jsx'),
  'utf8',
)

const DOMAIN_PAGES = {
  jewelry: 'Jewelry.jsx',
  mechanical: 'Mechanical.jsx',
  electronics: 'Electronics.jsx',
  architecture: 'Architecture.jsx',
  automotive: 'Automotive.jsx',
}

/* -------------------------------------------------------------------------- */
/* DOMAIN_TABS data                                                            */
/* -------------------------------------------------------------------------- */

describe('DOMAIN_TABS', () => {
  it('contains every live domain in canonical order', () => {
    expect(DOMAIN_TABS.map((t) => t.slug)).toEqual([
      'jewelry',
      'mechanical',
      'electronics',
      'architecture',
      'automotive',
      'civil',
      'composites',
      'dental',
      'optics',
      'horology',
      'piping',
      'packaging',
      'mold',
      'woodworking',
      'marine',
      'silicon',
      'firmware',
      'aerospace',
    ])
  })

  it('every tab has a slug and a human label', () => {
    for (const t of DOMAIN_TABS) {
      expect(t.slug.length).toBeGreaterThan(0)
      expect(t.label.length).toBeGreaterThan(0)
    }
  })
})

/* -------------------------------------------------------------------------- */
/* Component source                                                            */
/* -------------------------------------------------------------------------- */

describe('DomainSwitcher component', () => {
  it('exports a default function', () => {
    expect(SWITCHER_SRC).toMatch(/export default function DomainSwitcher/)
  })

  it('accepts an `active` prop and marks the current tab', () => {
    expect(SWITCHER_SRC).toMatch(/active/)
    expect(SWITCHER_SRC).toMatch(/aria-current="page"/)
    expect(SWITCHER_SRC).toMatch(/tab\.slug === active/)
  })

  it('renders react-router Links to every domain page', () => {
    expect(SWITCHER_SRC).toMatch(/to=\{`\/domains\/\$\{tab\.slug\}`\}/)
  })

  it('scrolls horizontally on narrow screens', () => {
    expect(SWITCHER_SRC).toMatch(/overflow-x-auto/)
  })

  it('uses ink-* / kerf-* / edge tokens — no raw hex in className', () => {
    const classMatches =
      SWITCHER_SRC.match(/className="[^"]*#[0-9a-fA-F]{3,6}[^"]*"/g) || []
    expect(classMatches).toHaveLength(0)
  })
})

/* -------------------------------------------------------------------------- */
/* Every domain page renders the switcher                                      */
/* -------------------------------------------------------------------------- */

describe('domain pages render DomainSwitcher', () => {
  for (const [slug, file] of Object.entries(DOMAIN_PAGES)) {
    it(`${file} imports and renders <DomainSwitcher active="${slug}" />`, () => {
      const src = readFileSync(
        resolve(__dirname, `../routes/domains/${file}`),
        'utf8',
      )
      expect(src).toMatch(
        /import DomainSwitcher from '\.\.\/\.\.\/components\/domains\/DomainSwitcher\.jsx'/,
      )
      expect(src).toMatch(
        new RegExp(`<DomainSwitcher active="${slug}" ?/>`),
      )
    })
  }
})
