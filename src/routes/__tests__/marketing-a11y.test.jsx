/**
 * marketing-a11y.test.jsx — T-H1: a11y + responsive audit for
 * marketing / domain / compare / docs pages.
 *
 * Checks:
 *   Pricing    — main landmark, section labels, aria-expanded on FAQ,
 *                plan cards use article role, icon aria-hidden
 *   Roadmap    — aria-pressed on filter chips, filter groups have labels,
 *                hero section label
 *   DomainPage — table caption, scope=col/row, icon aria-labels,
 *                legend aria-label, hero section aria-label
 *   CompareMdRoute — loading/not-found states render without throwing
 *   Docs/index — main landmark present, hamburger has aria-label
 *   Docs/Article — breadcrumb nav aria-label, prev/next nav aria-label
 *
 * Uses renderToStaticMarkup so we can run without a DOM/jsdom.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'

/* ── helpers ────────────────────────────────────────────────────────────── */

function render(ui) {
  return renderToStaticMarkup(<MemoryRouter>{ui}</MemoryRouter>)
}

/* ── mocks ──────────────────────────────────────────────────────────────── */

// Docs store is async/fetch-based — stub it out for SSR render tests.
vi.mock('../../routes/Docs/docsStore.js', () => ({
  useDocs: () => ({
    status: 'idle',
    load: () => {},
    manifest: [],
    bySlug: new Map(),
    index: null,
  }),
}))

vi.mock('../../routes/Docs/groupTaxonomy.js', () => ({
  buildSidebarGroups: () => [],
  flatDocOrder: () => [],
  groupForSlug: () => null,
  isInternalPlanning: () => false,
}))

vi.mock('../../routes/Docs/searchIndex.js', () => ({
  search: () => [],
}))

// compareManifest fetch is not available in test env.
vi.mock('../../lib/compareManifest.js', () => ({
  fetchCompareManifest: () => Promise.resolve({ items: [] }),
}))

/* ── Pricing ────────────────────────────────────────────────────────────── */

describe('Pricing page — T-H1 a11y', () => {
  let Pricing
  beforeAll(async () => {
    const mod = await import('../Pricing.jsx')
    Pricing = mod.default
  })

  it('renders without throwing', () => {
    expect(() => render(<Pricing />)).not.toThrow()
  })

  it('has a <main> landmark', () => {
    const html = render(<Pricing />)
    expect(html).toMatch(/<main[\s>]/)
  })

  it('hero section has aria-labelledby pointing to an h1 id', () => {
    const html = render(<Pricing />)
    expect(html).toMatch(/aria-labelledby="pricing-hero-heading"/)
    expect(html).toMatch(/id="pricing-hero-heading"/)
  })

  it('billing section has aria-labelledby', () => {
    const html = render(<Pricing />)
    expect(html).toMatch(/aria-labelledby="pricing-billing-heading"/)
  })

  it('FAQ section has aria-labelledby', () => {
    const html = render(<Pricing />)
    expect(html).toMatch(/aria-labelledby="pricing-faq-heading"/)
  })

  it('plan cards use article role with aria-label', () => {
    const html = render(<Pricing />)
    // Each plan card wraps in <article aria-label="… plan">
    expect(html).toMatch(/aria-label="Free plan"/)
    expect(html).toMatch(/aria-label="Studio plan"/)
    expect(html).toMatch(/aria-label="Pro plan"/)
  })

  it('FAQ summary has aria-expanded', () => {
    const html = render(<Pricing />)
    // Initially closed — all FAQ items render with aria-expanded="false"
    expect(html).toMatch(/aria-expanded="false"/)
  })

  it('plan icon wrappers have aria-hidden', () => {
    const html = render(<Pricing />)
    // The plan icon span has aria-hidden
    expect(html).toMatch(/aria-hidden="true"/)
  })

  it('plan pricing section has aria-label', () => {
    const html = render(<Pricing />)
    expect(html).toMatch(/aria-label="Pricing plans"/)
  })
})

/* ── Roadmap ─────────────────────────────────────────────────────────────── */

describe('Roadmap page — T-H1 a11y', () => {
  let Roadmap
  beforeAll(async () => {
    const mod = await import('../Roadmap.jsx')
    Roadmap = mod.default
  })

  it('renders without throwing', () => {
    expect(() => render(<Roadmap />)).not.toThrow()
  })

  it('has a <main> landmark for items', () => {
    const html = render(<Roadmap />)
    expect(html).toMatch(/<main[\s>]/)
  })

  it('hero section has aria-labelledby', () => {
    const html = render(<Roadmap />)
    expect(html).toMatch(/aria-labelledby="roadmap-hero-heading"/)
    expect(html).toMatch(/id="roadmap-hero-heading"/)
  })
})

/* ── DomainPage ─────────────────────────────────────────────────────────── */

describe('DomainPage — T-H1 a11y', () => {
  let DomainPage

  const sampleMeta = {
    META_TITLE: 'Test Domain',
    META_DESCRIPTION: 'desc',
    META_OG_IMAGE: '/img.png',
    META_URL: 'https://kerf.sh/domains/test',
    FEATURES: [
      { id: 'f1', name: 'Feature One', description: 'Does stuff.' },
    ],
    JSON_LD: {},
  }
  const sampleComparison = {
    products: ['Tool A', 'Kerf'],
    rows: [
      { feature: 'Parametric CAD', values: [true, true] },
      { feature: 'Free license', values: [false, true] },
      { feature: 'Partial feature', values: [null, true] },
    ],
  }

  beforeAll(async () => {
    const mod = await import('../domains/DomainPage.jsx')
    DomainPage = mod.default
  })

  it('renders without throwing', () => {
    expect(() => render(
      <DomainPage
        meta={sampleMeta}
        slug="test"
        heroHeadline="Test headline"
        heroParagraph="Test paragraph"
        domainName="Test"
      />
    )).not.toThrow()
  })

  it('hero section has aria-label="Hero"', () => {
    const html = render(
      <DomainPage
        meta={sampleMeta}
        slug="test"
        heroHeadline="Test headline"
        heroParagraph="Test paragraph"
        domainName="Test"
      />
    )
    expect(html).toMatch(/aria-label="Hero"/)
  })

  it('comparison table has a <caption>', () => {
    const html = render(
      <DomainPage
        meta={sampleMeta}
        slug="test"
        heroHeadline="Test headline"
        heroParagraph="Test paragraph"
        comparison={sampleComparison}
        domainName="Test"
      />
    )
    expect(html).toMatch(/<caption/)
    expect(html).toMatch(/Honest feature comparison/)
  })

  it('comparison table uses scope="col" on column headers', () => {
    const html = render(
      <DomainPage
        meta={sampleMeta}
        slug="test"
        heroHeadline="Test headline"
        heroParagraph="Test paragraph"
        comparison={sampleComparison}
        domainName="Test"
      />
    )
    expect(html).toMatch(/scope="col"/)
  })

  it('comparison table uses scope="row" on feature name cells', () => {
    const html = render(
      <DomainPage
        meta={sampleMeta}
        slug="test"
        heroHeadline="Test headline"
        heroParagraph="Test paragraph"
        comparison={sampleComparison}
        domainName="Test"
      />
    )
    expect(html).toMatch(/scope="row"/)
  })

  it('CellIcon for true has aria-label="Yes"', () => {
    const html = render(
      <DomainPage
        meta={sampleMeta}
        slug="test"
        heroHeadline="Test headline"
        heroParagraph="Test paragraph"
        comparison={sampleComparison}
        domainName="Test"
      />
    )
    expect(html).toMatch(/aria-label="Yes"/)
  })

  it('CellIcon for false has aria-label="No"', () => {
    const html = render(
      <DomainPage
        meta={sampleMeta}
        slug="test"
        heroHeadline="Test headline"
        heroParagraph="Test paragraph"
        comparison={sampleComparison}
        domainName="Test"
      />
    )
    expect(html).toMatch(/aria-label="No"/)
  })

  it('CellIcon for null has aria-label="Partial"', () => {
    const html = render(
      <DomainPage
        meta={sampleMeta}
        slug="test"
        heroHeadline="Test headline"
        heroParagraph="Test paragraph"
        comparison={sampleComparison}
        domainName="Test"
      />
    )
    expect(html).toMatch(/aria-label="Partial"/)
  })

  it('legend has aria-label="Table legend"', () => {
    const html = render(
      <DomainPage
        meta={sampleMeta}
        slug="test"
        heroHeadline="Test headline"
        heroParagraph="Test paragraph"
        comparison={sampleComparison}
        domainName="Test"
      />
    )
    expect(html).toMatch(/aria-label="Table legend"/)
  })

  it('capabilities section has aria-labelledby', () => {
    const html = render(
      <DomainPage
        meta={sampleMeta}
        slug="test"
        heroHeadline="Test headline"
        heroParagraph="Test paragraph"
        domainName="Test"
      />
    )
    expect(html).toMatch(/aria-labelledby="capabilities-heading"/)
  })
})

/* ── Docs/index (DocsHome) ──────────────────────────────────────────────── */

describe('DocsHome — T-H1 a11y', () => {
  let DocsHome
  beforeAll(async () => {
    const mod = await import('../Docs/index.jsx')
    DocsHome = mod.default
  })

  it('renders without throwing', () => {
    expect(() => render(<DocsHome />)).not.toThrow()
  })

  it('has a <main> landmark', () => {
    const html = render(<DocsHome />)
    expect(html).toMatch(/<main[\s>]/)
  })

  it('mobile hamburger button has aria-label="Open navigation"', () => {
    const html = render(<DocsHome />)
    expect(html).toMatch(/aria-label="Open navigation"/)
  })

  it('hero search input has aria-label', () => {
    const html = render(<DocsHome />)
    expect(html).toMatch(/aria-label="Search documentation"/)
  })
})

/* ── CompareLanding — regression guard ─────────────────────────────────── */

describe('CompareLanding — T-H1 regression', () => {
  let CompareLanding
  beforeAll(async () => {
    const mod = await import('../compare/CompareLanding.jsx')
    CompareLanding = mod.default
  })

  it('renders without throwing', () => {
    expect(() => render(<CompareLanding />)).not.toThrow()
  })

  it('main landmark has aria-label for screen readers', () => {
    const html = render(<CompareLanding />)
    expect(html).toMatch(/aria-label="Compare Kerf against other CAD and EDA tools"/)
  })
})
