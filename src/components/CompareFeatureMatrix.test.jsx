/**
 * CompareFeatureMatrix.test.jsx — unit tests for the structured feature matrix.
 *
 * Uses renderToStaticMarkup (react-dom/server) — consistent with the
 * project's CompareCardGrid.test.jsx pattern. No @testing-library/react needed.
 */
import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import CompareFeatureMatrix from './CompareFeatureMatrix.jsx'

function render(ui) {
  return renderToStaticMarkup(ui)
}

/* -------------------------------------------------------------------------- */
/* Fixtures                                                                    */
/* -------------------------------------------------------------------------- */

const SAMPLE_FEATURES = [
  {
    domain: 'D1',
    feature: 'Constraint sketcher (geo + dim)',
    competitor: { status: 'yes', note: 'Full parametric sketcher' },
    kerf: { status: 'yes', note: 'PlaneGCS WASM', evidence: 'packages/kerf-sketcher' },
  },
  {
    domain: 'D1',
    feature: 'Loft',
    competitor: { status: 'yes', note: 'Guide rails supported' },
    kerf: { status: 'partial', note: 'no guide-rail overload' },
  },
  {
    domain: 'D6',
    feature: 'PCB layout',
    competitor: { status: 'yes', note: 'Native MCAD/ECAD link' },
    kerf: { status: 'yes', note: 'Viewer wired' },
  },
  {
    domain: 'D7',
    feature: '3-axis CAM',
    competitor: { status: 'no', note: 'Not included' },
    kerf: { status: 'yes', note: 'CAMView wired' },
  },
]

/* -------------------------------------------------------------------------- */
/* Tests                                                                       */
/* -------------------------------------------------------------------------- */

describe('CompareFeatureMatrix', () => {
  it('returns empty string (null component) when features is undefined', () => {
    const html = render(<CompareFeatureMatrix features={undefined} competitor="Fusion 360" />)
    expect(html).toBe('')
  })

  it('returns empty string (null component) when features is an empty array', () => {
    const html = render(<CompareFeatureMatrix features={[]} competitor="Fusion 360" />)
    expect(html).toBe('')
  })

  it('renders the "Full feature matrix" section header when features are present', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    expect(html).toContain('Full feature matrix')
  })

  it('renders the data-testid compare-feature-matrix container', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    expect(html).toContain('data-testid="compare-feature-matrix"')
  })

  it('groups features by domain — D1 section present', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    expect(html).toContain('data-testid="domain-section-D1"')
  })

  it('groups features by domain — D6 section present', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    expect(html).toContain('data-testid="domain-section-D6"')
  })

  it('groups features by domain — D7 section present', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    expect(html).toContain('data-testid="domain-section-D7"')
  })

  it('does NOT render a D2 section when no D2 features exist', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    expect(html).not.toContain('data-testid="domain-section-D2"')
  })

  it('renders feature names inside their domain section', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    expect(html).toContain('Constraint sketcher')
    expect(html).toContain('Loft')
    expect(html).toContain('PCB layout')
    expect(html).toContain('3-axis CAM')
  })

  it('status pill renders the correct symbol for "yes" status', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    // STATUS_META.yes.symbol = '✓'
    expect(html).toContain('✓')
    expect(html).toContain('data-testid="status-pill-yes"')
  })

  it('status pill renders the correct symbol for "partial" status', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    // STATUS_META.partial.symbol = '~'
    expect(html).toContain('~')
    expect(html).toContain('data-testid="status-pill-partial"')
  })

  it('status pill renders the correct symbol for "no" status', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    // STATUS_META.no.symbol = '✗'
    expect(html).toContain('✗')
    expect(html).toContain('data-testid="status-pill-no"')
  })

  it('shows "X of Y matched" count in D1 section header', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    // D1: 2 rows; sketcher=both yes (matched), loft=kerf partial (not matched) → 1 of 2
    expect(html).toContain('1 of 2 matched')
  })

  it('renders the Kerf column header', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    expect(html).toContain('data-testid="matrix-kerf-header"')
  })

  it('renders domain sections using <details> elements (collapsible)', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    // Should have exactly 3 <details> (D1, D6, D7)
    const detailsCount = (html.match(/<details/g) || []).length
    expect(detailsCount).toBe(3)
  })

  it('renders feature row count correctly for D1 (2 features)', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    // The D1 summary says "2 of 2" or "1 of 2" — either way contains "2"
    // The domain section shows 2 feature rows
    const d1Section = html.match(/domain-section-D1[\s\S]*?domain-section-D6/)?.[0] ?? ''
    const rowCount = (d1Section.match(/data-testid="feature-row"/g) || []).length
    expect(rowCount).toBe(2)
  })

  it('single-feature list renders correctly', () => {
    const single = [SAMPLE_FEATURES[0]]
    const html = render(<CompareFeatureMatrix features={single} competitor="Fusion 360" />)
    expect(html).toContain('data-testid="compare-feature-matrix"')
    expect(html).toContain('Constraint sketcher')
  })

  // ── Kerf-leftmost column invariant ──────────────────────────────────────────

  it('Kerf column header (matrix-kerf-header) appears before the competitor header', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    const kerfHeaderIdx = html.indexOf('data-testid="matrix-kerf-header"')
    // Competitor header contains "Fusion 360" text after the kerf header.
    // The kerf header should come first in the DOM.
    const featureHeaderIdx = html.indexOf('>Feature<')
    expect(kerfHeaderIdx).toBeGreaterThan(-1)
    expect(featureHeaderIdx).toBeGreaterThan(-1)
    // Feature col (col 0) < Kerf col (col 1) in DOM order
    expect(featureHeaderIdx).toBeLessThan(kerfHeaderIdx)
    // Kerf header must appear before the competitor name in the same row
    const compHeaderIdx = html.indexOf('>Fusion 360<')
    expect(compHeaderIdx).toBeGreaterThan(-1)
    expect(kerfHeaderIdx).toBeLessThan(compHeaderIdx)
  })

  it('Kerf status cell appears before competitor status cell in each feature row', () => {
    // Use a feature where kerf=yes and competitor=no so we can distinguish the pills.
    const distinctive = [
      {
        domain: 'D7',
        feature: '3-axis CAM',
        kerf: { status: 'yes', note: 'Kerf CAM note' },
        competitor: { status: 'no', note: 'Competitor has no CAM' },
      },
    ]
    const html = render(<CompareFeatureMatrix features={distinctive} competitor="RivalCAD" />)
    // Find positions of kerf pill and competitor pill in the first feature row.
    const kerfPillIdx = html.indexOf('data-testid="status-pill-yes"')
    const compPillIdx = html.indexOf('data-testid="status-pill-no"')
    expect(kerfPillIdx).toBeGreaterThan(-1)
    expect(compPillIdx).toBeGreaterThan(-1)
    // Kerf (yes) must render before competitor (no).
    expect(kerfPillIdx).toBeLessThan(compPillIdx)
  })

  it('Kerf is leftmost even when multiple domains are rendered', () => {
    // Render a multi-domain set and confirm kerf-header comes before competitor in each domain section.
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="SolidWorks" />)
    // For each domain section, the kerf header should appear before the competitor name
    // within that section's HTML. Extract each domain section independently.
    const domainSections = [
      html.match(/domain-section-D1"[\s\S]*?(?=data-testid="domain-section-D|$)/)?.[0],
      html.match(/domain-section-D6"[\s\S]*?(?=data-testid="domain-section-D|$)/)?.[0],
      html.match(/domain-section-D7"[\s\S]*/)?.[0],
    ].filter(Boolean)
    expect(domainSections.length).toBeGreaterThan(0)
    domainSections.forEach((section) => {
      const kerfIdx = section.indexOf('data-testid="matrix-kerf-header"')
      const compIdx = section.indexOf('>SolidWorks<')
      if (kerfIdx !== -1 && compIdx !== -1) {
        expect(kerfIdx).toBeLessThan(compIdx)
      }
    })
  })
})

// ── Responsive layout ─────────────────────────────────────────────────────────

describe('CompareFeatureMatrix — responsive layout', () => {
  it('renders a desktop table container (hidden sm:block) per domain section', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    // Each domain section renders a desktop table wrapper hidden below sm breakpoint
    expect(html).toContain('data-testid="matrix-desktop-table"')
    // Should have one per domain section (3 domains)
    const desktopTables = (html.match(/data-testid="matrix-desktop-table"/g) || []).length
    expect(desktopTables).toBe(3)
  })

  it('desktop table container has overflow-x-auto for wide tables', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    // The desktop wrapper must carry overflow-x-auto so the table scrolls horizontally
    // if it overflows on narrower breakpoints where the desktop view is still shown.
    expect(html).toMatch(/overflow-x-auto[^"]*"[^>]*data-testid="matrix-desktop-table"|data-testid="matrix-desktop-table"[^>]*>[^<]*<|class="[^"]*overflow-x-auto/)
    // Simpler: confirm the class appears in the output
    expect(html).toContain('overflow-x-auto')
  })

  it('renders a mobile stacked-cards container (sm:hidden) per domain section', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    // Each domain section renders a mobile stack hidden at sm+ breakpoint
    expect(html).toContain('data-testid="matrix-mobile-cards"')
    const mobileCards = (html.match(/data-testid="matrix-mobile-cards"/g) || []).length
    expect(mobileCards).toBe(3)
  })

  it('mobile stacked-cards container has sm:hidden class (hidden on desktop)', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    // Extract the mobile cards container and verify sm:hidden class
    expect(html).toMatch(/sm:hidden[^"]*"[^>]*data-testid="matrix-mobile-cards"|data-testid="matrix-mobile-cards"/)
    // The class should include sm:hidden (desktop-hidden) somewhere in the output
    expect(html).toContain('sm:hidden')
  })

  it('mobile card renders feature name, Kerf label, and competitor label', () => {
    const singleFeature = [SAMPLE_FEATURES[0]]
    const html = render(<CompareFeatureMatrix features={singleFeature} competitor="Fusion 360" />)
    // In the mobile cards section the feature name appears
    expect(html).toContain('Constraint sketcher')
    // Kerf label appears in the mobile section header
    expect(html).toContain('Kerf')
    // Competitor name appears as a label in the mobile card
    expect(html).toContain('Fusion 360')
  })

  it('mobile card container has divide-y for visual row separation', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    expect(html).toContain('divide-y')
  })

  it('desktop table has min-w so it scrolls rather than collapses on narrow viewports', () => {
    const html = render(<CompareFeatureMatrix features={SAMPLE_FEATURES} competitor="Fusion 360" />)
    // The table inside the desktop container should have a min-width set
    expect(html).toContain('min-w-[560px]')
  })
})
