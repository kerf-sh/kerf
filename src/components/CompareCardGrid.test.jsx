/**
 * CompareCardGrid.test.jsx — unit tests for the compare card grid.
 *
 * Uses renderToStaticMarkup (react-dom/server) — consistent with the
 * project's Loader.test.jsx pattern. No @testing-library/react needed.
 */
import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import CompareCardGrid from './CompareCardGrid.jsx'

/** Wrap in a MemoryRouter so <Link> renders without error. */
function render(ui) {
  return renderToStaticMarkup(<MemoryRouter>{ui}</MemoryRouter>)
}

const ITEMS = [
  {
    slug: 'freecad',
    competitor: 'FreeCAD',
    category: 'cad-mechanical',
    hero_tagline: 'Open-source parametric B-rep modeller',
  },
  {
    slug: 'fusion',
    competitor: 'Fusion 360',
    category: 'cad-mechanical',
    hero_tagline: 'Cloud-connected mechanical CAD',
  },
  {
    slug: 'kicad',
    competitor: 'KiCad',
    category: 'cad-electronics',
    hero_tagline: 'Open-source EDA suite',
  },
]

describe('CompareCardGrid', () => {
  it('renders N cards from N items', () => {
    const html = render(<CompareCardGrid items={ITEMS} />)
    const cards = html.match(/data-testid="compare-card"/g) || []
    expect(cards).toHaveLength(ITEMS.length)
  })

  it('renders 1 card from 1 item', () => {
    const html = render(<CompareCardGrid items={[ITEMS[0]]} />)
    const cards = html.match(/data-testid="compare-card"/g) || []
    expect(cards).toHaveLength(1)
  })

  it('each card shows "Kerf vs ..." text for each competitor', () => {
    const html = render(<CompareCardGrid items={ITEMS} />)
    ITEMS.forEach((item) => {
      expect(html).toContain(`Kerf vs ${item.competitor}`)
    })
  })

  it('each card has an "Open →" label', () => {
    const html = render(<CompareCardGrid items={ITEMS} />)
    const opens = html.match(/Open →/g) || []
    expect(opens).toHaveLength(ITEMS.length)
  })

  it('each card links to /compare/<slug>', () => {
    const html = render(<CompareCardGrid items={ITEMS} />)
    ITEMS.forEach((item) => {
      expect(html).toContain(`/compare/${item.slug}`)
    })
  })

  it('each card shows the hero_tagline', () => {
    const html = render(<CompareCardGrid items={ITEMS} />)
    ITEMS.forEach((item) => {
      expect(html).toContain(item.hero_tagline)
    })
  })

  it('each card has an aria-label with the competitor name', () => {
    const html = render(<CompareCardGrid items={ITEMS} />)
    ITEMS.forEach((item) => {
      expect(html).toContain(`Kerf vs ${item.competitor} comparison`)
    })
  })

  it('renders the grid container with data-testid', () => {
    const html = render(<CompareCardGrid items={ITEMS} />)
    expect(html).toMatch(/data-testid="compare-card-grid"/)
  })

  it('empty items renders the empty state message', () => {
    const html = render(<CompareCardGrid items={[]} />)
    expect(html).toMatch(/No comparisons match your search/)
  })

  it('null items renders the empty state message', () => {
    const html = render(<CompareCardGrid items={null} />)
    expect(html).toMatch(/No comparisons match your search/)
  })

  it('cards use the expected responsive grid classes', () => {
    const html = render(<CompareCardGrid items={ITEMS} />)
    expect(html).toMatch(/grid-cols-1/)
    expect(html).toMatch(/sm:grid-cols-2/)
  })

  it('category badge renders for cad-mechanical', () => {
    const html = render(
      <CompareCardGrid
        items={[
          {
            slug: 'freecad',
            competitor: 'FreeCAD',
            category: 'cad-mechanical',
            hero_tagline: 'Open-source parametric B-rep modeller',
          },
        ]}
      />,
    )
    expect(html).toMatch(/Mechanical/)
  })

  it('category badge renders for cad-electronics', () => {
    const html = render(
      <CompareCardGrid
        items={[
          {
            slug: 'kicad',
            competitor: 'KiCad',
            category: 'cad-electronics',
            hero_tagline: 'Open-source EDA suite',
          },
        ]}
      />,
    )
    expect(html).toMatch(/Electronics/)
  })
})
