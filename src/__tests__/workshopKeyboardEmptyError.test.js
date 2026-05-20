// T-G1: Workshop listing keyboard + empty/error states
//
// Pure source-analysis tests — no DOM or React rendering required.
// Covers:
//   1. ImageCarousel keyboard navigation (onKeyDown handlers, roving tabindex)
//   2. Thumb strip role=tablist / role=tab / aria-selected / tabIndex roving
//   3. aria-live counter on the main image
//   4. WorkshopListing error-kind state: not_found (404), private (403), generic
//   5. Workshop index: differentiated empty state (no filter vs filtered)
//   6. Workshop index: role=alert on the error banner

import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import path from 'path'
import { describe, it, expect } from 'vitest'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const wl = readFileSync(path.resolve(__dirname, '../cloud/WorkshopListing.jsx'), 'utf8')
const ws = readFileSync(path.resolve(__dirname, '../cloud/Workshop.jsx'), 'utf8')

// ---------------------------------------------------------------------------
// 1. ImageCarousel keyboard navigation
// ---------------------------------------------------------------------------

describe('ImageCarousel — keyboard navigation', () => {
  it('defines an onMainKeyDown handler for ArrowLeft / ArrowRight', () => {
    expect(wl).toContain('onMainKeyDown')
    expect(wl).toContain("e.key === 'ArrowLeft'")
    expect(wl).toContain("e.key === 'ArrowRight'")
  })

  it('attaches onKeyDown to the carousel wrapper', () => {
    expect(wl).toContain('onKeyDown={onMainKeyDown}')
  })

  it('wraps the carousel in an aria region with an accessible label', () => {
    expect(wl).toContain('role="region"')
    expect(wl).toContain('aria-label="Image gallery"')
  })
})

// ---------------------------------------------------------------------------
// 2. Thumb strip roving tabindex
// ---------------------------------------------------------------------------

describe('ImageCarousel — thumb strip roving tabindex', () => {
  it('thumb strip has role=tablist with an accessible label', () => {
    expect(wl).toContain('role="tablist"')
    expect(wl).toContain('aria-label="Gallery thumbnails"')
  })

  it('each thumb has role=tab', () => {
    expect(wl).toContain('role="tab"')
  })

  it('each thumb has aria-selected', () => {
    expect(wl).toContain('aria-selected={i === idx}')
  })

  it('active thumb has tabIndex=0, others -1 (roving tabindex)', () => {
    expect(wl).toContain('tabIndex={i === idx ? 0 : -1}')
  })

  it('onThumbKeyDown handles ArrowLeft / ArrowRight / Enter / Space', () => {
    expect(wl).toContain('onThumbKeyDown')
    expect(wl).toContain("e.key === 'Enter'")
    expect(wl).toContain("e.key === ' '")
  })
})

// ---------------------------------------------------------------------------
// 3. aria-live counter
// ---------------------------------------------------------------------------

describe('ImageCarousel — aria-live counter', () => {
  it('position counter has aria-live=polite', () => {
    expect(wl).toContain('aria-live="polite"')
  })

  it('position counter has aria-atomic=true', () => {
    expect(wl).toContain('aria-atomic="true"')
  })
})

// ---------------------------------------------------------------------------
// 4. WorkshopListing — differentiated error states
// ---------------------------------------------------------------------------

describe('WorkshopListing — error-kind state', () => {
  it('tracks errorKind state', () => {
    expect(wl).toContain('errorKind')
    expect(wl).toContain("setErrorKind(null)")
  })

  it('maps 404 to not_found kind', () => {
    expect(wl).toContain("err.status === 404")
    expect(wl).toContain("setErrorKind('not_found')")
  })

  it('maps 403 to private kind', () => {
    expect(wl).toContain("err.status === 403")
    expect(wl).toContain("setErrorKind('private')")
  })

  it('falls back to generic kind for other errors', () => {
    expect(wl).toContain("setErrorKind('generic')")
  })

  it('renders a not-found card with data-testid', () => {
    expect(wl).toContain('data-testid="workshop-state-not-found"')
    expect(wl).toContain('Listing not found')
  })

  it('renders a private card with data-testid', () => {
    expect(wl).toContain('data-testid="workshop-state-private"')
    expect(wl).toContain('Private listing')
  })

  it('renders a generic error card with data-testid', () => {
    expect(wl).toContain('data-testid="workshop-state-error"')
  })
})

// ---------------------------------------------------------------------------
// 5 & 6. Workshop index — empty + error states
// ---------------------------------------------------------------------------

describe('Workshop index — empty states', () => {
  it('shows a filtered-empty card when tags are active but no results', () => {
    expect(ws).toContain('data-testid="workshop-empty-filtered"')
    expect(ws).toContain('No listings match your filter')
  })

  it('shows the base empty card when no tags active', () => {
    expect(ws).toContain('data-testid="workshop-empty"')
    expect(ws).toContain('Nothing published yet')
  })

  it('filtered-empty card guards on activeTags.length > 0', () => {
    expect(ws).toContain('activeTags.length > 0')
  })

  it('filtered-empty card offers a clear-filters action', () => {
    expect(ws).toContain('clear all filters')
    expect(ws).toContain('clearTags')
  })
})

describe('Workshop index — error banner a11y', () => {
  it('error banner has role=alert for screen readers', () => {
    expect(ws).toContain('role="alert"')
    expect(ws).toContain('data-testid="workshop-error-banner"')
  })
})
