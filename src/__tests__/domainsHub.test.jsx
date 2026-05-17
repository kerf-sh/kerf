/**
 * domainsHub.test.jsx
 *
 * Tests for the /domains hub page (src/routes/domains/index.jsx).
 *
 * Strategy (no jsdom in this project):
 *   - Import the page module's exported data (DOMAINS_META, DOMAINS,
 *     buildDomainsJsonLd) and assert the data layer that drives the page.
 *   - Read the source files to assert link targets, the new route wiring,
 *     the Header change, and the responsive grid markup — the same
 *     source-level pattern the other domain-page suites use.
 */

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import { resolve } from 'path'
import {
  DOMAINS_META,
  DOMAINS,
  buildDomainsJsonLd,
} from '../routes/domains/index.jsx'

const HUB_SRC = readFileSync(
  resolve(__dirname, '../routes/domains/index.jsx'),
  'utf8',
)
const APP_SRC = readFileSync(resolve(__dirname, '../App.jsx'), 'utf8')
const HEADER_SRC = readFileSync(
  resolve(__dirname, '../components/Header.jsx'),
  'utf8',
)

/* -------------------------------------------------------------------------- */
/* Meta / SEO                                                                  */
/* -------------------------------------------------------------------------- */

describe('DOMAINS_META', () => {
  it('title is a non-empty string ≤60 characters', () => {
    expect(typeof DOMAINS_META.title).toBe('string')
    expect(DOMAINS_META.title.length).toBeGreaterThan(0)
    expect(DOMAINS_META.title.length).toBeLessThanOrEqual(60)
  })

  it('description is a non-empty string ≤155 characters', () => {
    expect(typeof DOMAINS_META.description).toBe('string')
    expect(DOMAINS_META.description.length).toBeGreaterThan(0)
    expect(DOMAINS_META.description.length).toBeLessThanOrEqual(155)
  })

  it('canonicalUrl is exactly https://kerf.sh/domains', () => {
    expect(DOMAINS_META.canonicalUrl).toBe('https://kerf.sh/domains')
  })

  it('ogImage is an https kerf.sh URL', () => {
    expect(DOMAINS_META.ogImage).toMatch(/^https:\/\/kerf\.sh\//)
  })
})

/* -------------------------------------------------------------------------- */
/* Domain data                                                                 */
/* -------------------------------------------------------------------------- */

describe('DOMAINS', () => {
  it('covers the five live domains plus civil and product', () => {
    const slugs = DOMAINS.map((d) => d.slug)
    expect(slugs).toEqual(
      expect.arrayContaining([
        'jewelry',
        'mechanical',
        'electronics',
        'architecture',
        'automotive',
        'civil',
        'product',
      ]),
    )
  })

  it('has the five live domains linking to their /domains/<slug> page', () => {
    for (const slug of [
      'jewelry',
      'mechanical',
      'electronics',
      'architecture',
      'automotive',
    ]) {
      const d = DOMAINS.find((x) => x.slug === slug)
      expect(d).toBeDefined()
      expect(d.status).toBe('live')
      expect(d.to).toBe(`/domains/${slug}`)
    }
  })

  it('marks civil and product as in-progress, pointing at /roadmap', () => {
    for (const slug of ['civil', 'product']) {
      const d = DOMAINS.find((x) => x.slug === slug)
      expect(d).toBeDefined()
      expect(d.status).toBe('in-progress')
      expect(d.to).toBe('/roadmap')
    }
  })

  it('every domain has a non-empty name, blurb and icon component', () => {
    for (const d of DOMAINS) {
      expect(d.name.length).toBeGreaterThan(0)
      expect(d.blurb.length).toBeGreaterThan(0)
      expect(typeof d.Icon).not.toBe('undefined')
    }
  })

  it('all slugs are unique', () => {
    const slugs = DOMAINS.map((d) => d.slug)
    expect(new Set(slugs).size).toBe(slugs.length)
  })
})

/* -------------------------------------------------------------------------- */
/* JSON-LD ItemList                                                            */
/* -------------------------------------------------------------------------- */

describe('buildDomainsJsonLd', () => {
  it('returns a WebPage whose name matches the meta title', () => {
    const ld = buildDomainsJsonLd()
    expect(ld['@type']).toBe('WebPage')
    expect(ld.name).toBe(DOMAINS_META.title)
    expect(ld.url).toBe(DOMAINS_META.canonicalUrl)
  })

  it('mainEntity is an ItemList with one element per domain', () => {
    const ld = buildDomainsJsonLd()
    expect(ld.mainEntity['@type']).toBe('ItemList')
    expect(ld.mainEntity.itemListElement.length).toBe(DOMAINS.length)
    expect(ld.mainEntity.numberOfItems).toBe(DOMAINS.length)
  })

  it('each ItemList item has position, name, description and url', () => {
    const ld = buildDomainsJsonLd()
    ld.mainEntity.itemListElement.forEach((item, i) => {
      expect(item['@type']).toBe('ListItem')
      expect(item.position).toBe(i + 1)
      expect(item.name.length).toBeGreaterThan(0)
      expect(item.description.length).toBeGreaterThan(0)
      expect(item.url).toMatch(/^https:\/\/kerf\.sh\//)
    })
  })
})

/* -------------------------------------------------------------------------- */
/* Page module + source                                                        */
/* -------------------------------------------------------------------------- */

describe('Domains hub module', () => {
  it('exports a default component function', async () => {
    const mod = await import('../routes/domains/index.jsx')
    expect(typeof mod.default).toBe('function')
  })

  it('renders Header and Footer', () => {
    expect(HUB_SRC).toMatch(/import Header/)
    expect(HUB_SRC).toMatch(/import Footer/)
  })

  it('links to every live domain page', () => {
    expect(HUB_SRC).toMatch(/\/domains\/jewelry/)
    expect(HUB_SRC).toMatch(/\/domains\/mechanical/)
    expect(HUB_SRC).toMatch(/\/domains\/electronics/)
    expect(HUB_SRC).toMatch(/\/domains\/architecture/)
    expect(HUB_SRC).toMatch(/\/domains\/automotive/)
  })

  it('points the in-progress domains at /roadmap, not fabricated pages', () => {
    expect(HUB_SRC).toMatch(/\/roadmap/)
    expect(HUB_SRC).not.toMatch(/\/domains\/civil/)
    expect(HUB_SRC).not.toMatch(/\/domains\/product/)
  })

  it('uses a responsive grid that collapses to one column on mobile', () => {
    expect(HUB_SRC).toMatch(/grid-cols-1/)
    expect(HUB_SRC).toMatch(/lg:grid-cols-3/)
  })

  it('uses the kerf-sh/kerf GitHub URL only', () => {
    expect(HUB_SRC).toMatch(/github\.com\/kerf-sh\/kerf/)
    expect(HUB_SRC).not.toMatch(/github\.com\/(?!kerf-sh\/kerf)/)
  })

  it('contains no cloud-internal or pricing-margin terms', () => {
    expect(HUB_SRC).not.toMatch(/Paystack/)
    expect(HUB_SRC).not.toMatch(/bunny\.net/)
    expect(HUB_SRC).not.toMatch(/go-git/)
    expect(HUB_SRC).not.toMatch(/20% markup/)
  })
})

/* -------------------------------------------------------------------------- */
/* Routing + header wiring                                                      */
/* -------------------------------------------------------------------------- */

describe('Domains hub wiring', () => {
  it('App.jsx registers the /domains route to DomainsHub', () => {
    expect(APP_SRC).toMatch(
      /DomainsHub\s*=\s*lazy\(\(\)\s*=>\s*import\('\.\/routes\/domains\/index\.jsx'\)\)/,
    )
    expect(APP_SRC).toMatch(/<Route path="\/domains" element=\{<DomainsHub \/>\} \/>/)
  })

  it('App.jsx has no merge conflict markers', () => {
    expect(APP_SRC).not.toMatch(/<<<<<<<|>>>>>>>|^=======$/m)
  })

  it('Header points the Domains nav item at the hub', () => {
    expect(HEADER_SRC).toMatch(/\{ label: 'Domains', to: '\/domains' \}/)
    expect(HEADER_SRC).not.toMatch(/to: '\/domains\/jewelry'/)
  })
})
