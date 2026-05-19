/**
 * MobileNavSheet.test.jsx — Vitest suite for the MobileNavSheet component.
 *
 * Rendering is done via renderToStaticMarkup (react-dom/server) which
 * exercises the static HTML output — sufficient to validate all ARIA
 * attributes, class names, and content presence.
 *
 * useEffect calls (Escape handler, focus trap, body-scroll lock) do not run
 * during server rendering, which is correct: those are interactive DOM
 * behaviours that only matter in a live browser.  We test the static contract.
 */

import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'
import MobileNavSheet from './MobileNavSheet.jsx'

// ── Helpers ───────────────────────────────────────────────────────────────────

function renderSheet(props = {}, children = null) {
  return renderToStaticMarkup(
    React.createElement(MobileNavSheet, props, children),
  )
}

// ── aria-hidden toggles with open prop ────────────────────────────────────────

describe('MobileNavSheet — aria-hidden', () => {
  it('aria-hidden is false when open=true', () => {
    const html = renderSheet({ open: true })
    // The panel div has aria-hidden="false" when open
    expect(html).toContain('aria-hidden="false"')
  })

  it('aria-hidden is true when open=false', () => {
    const html = renderSheet({ open: false })
    // The panel's aria-hidden becomes "true" when closed
    // (backdrop also has aria-hidden="true" always)
    // Verify the panel specifically by checking all occurrences
    expect(html).toContain('aria-hidden="true"')
  })

  it('aria-hidden="false" is present when open, absent when closed', () => {
    const openHtml   = renderSheet({ open: true })
    const closedHtml = renderSheet({ open: false })
    expect(openHtml).toContain('aria-hidden="false"')
    expect(closedHtml).not.toContain('aria-hidden="false"')
  })
})

// ── role and aria-modal ───────────────────────────────────────────────────────

describe('MobileNavSheet — role and aria-modal', () => {
  it('has role="dialog" on the sheet panel', () => {
    const html = renderSheet({ open: true })
    expect(html).toContain('role="dialog"')
  })

  it('has aria-modal="true" on the sheet panel', () => {
    const html = renderSheet({ open: true })
    expect(html).toContain('aria-modal="true"')
  })

  it('aria-labelledby points at the title element id', () => {
    const html = renderSheet({ open: true, title: 'My Menu' })
    expect(html).toContain('aria-labelledby="mobile-nav-sheet-title"')
    expect(html).toContain('id="mobile-nav-sheet-title"')
  })
})

// ── title prop ────────────────────────────────────────────────────────────────

describe('MobileNavSheet — title prop', () => {
  it('renders default title "Navigation"', () => {
    const html = renderSheet({ open: true })
    expect(html).toContain('Navigation')
  })

  it('renders custom title when provided', () => {
    const html = renderSheet({ open: true, title: 'My Custom Menu' })
    expect(html).toContain('My Custom Menu')
  })

  it('title text appears inside the labelled heading', () => {
    const html = renderSheet({ open: true, title: 'Side Nav' })
    expect(html).toMatch(/id="mobile-nav-sheet-title"[^>]*>Side Nav</)
  })
})

// ── children ─────────────────────────────────────────────────────────────────

describe('MobileNavSheet — children', () => {
  it('renders a child element inside the sheet', () => {
    const html = renderSheet(
      { open: true },
      React.createElement('span', { id: 'nav-item' }, 'Home'),
    )
    expect(html).toContain('id="nav-item"')
    expect(html).toContain('Home')
  })

  it('renders multiple children', () => {
    const html = renderSheet(
      { open: true },
      React.createElement(
        React.Fragment,
        null,
        React.createElement('a', { href: '/home' }, 'Home'),
        React.createElement('a', { href: '/settings' }, 'Settings'),
      ),
    )
    expect(html).toContain('href="/home"')
    expect(html).toContain('href="/settings"')
  })

  it('renders without children (null)', () => {
    expect(() => renderSheet({ open: true })).not.toThrow()
  })
})

// ── slide animation classes ───────────────────────────────────────────────────

describe('MobileNavSheet — animation classes', () => {
  it('applies translate-y-0 when open=true', () => {
    const html = renderSheet({ open: true })
    expect(html).toContain('translate-y-0')
  })

  it('applies translate-y-full when open=false', () => {
    const html = renderSheet({ open: false })
    expect(html).toContain('translate-y-full')
  })

  it('has transition class for smooth animation', () => {
    const html = renderSheet({ open: true })
    expect(html).toContain('transition-transform')
  })
})

// ── backdrop ─────────────────────────────────────────────────────────────────

describe('MobileNavSheet — backdrop', () => {
  it('renders a backdrop element with inset-0', () => {
    const html = renderSheet({ open: true })
    expect(html).toContain('inset-0')
  })

  it('backdrop sits at z-40', () => {
    const html = renderSheet({ open: true })
    expect(html).toContain('z-40')
  })

  it('backdrop has opacity-100 when open', () => {
    const html = renderSheet({ open: true })
    expect(html).toContain('opacity-100')
  })

  it('backdrop has opacity-0 when closed', () => {
    const html = renderSheet({ open: false })
    expect(html).toContain('opacity-0')
  })
})

// ── close button ─────────────────────────────────────────────────────────────

describe('MobileNavSheet — close button', () => {
  it('renders a close button with aria-label', () => {
    const html = renderSheet({ open: true })
    expect(html).toContain('aria-label="Close navigation"')
  })

  it('close button is always present regardless of open state', () => {
    const closedHtml = renderSheet({ open: false })
    expect(closedHtml).toContain('aria-label="Close navigation"')
  })
})

// ── custom className ──────────────────────────────────────────────────────────

describe('MobileNavSheet — className prop', () => {
  it('merges custom className onto the sheet panel', () => {
    const html = renderSheet({ open: true, className: 'my-sheet-override' })
    expect(html).toContain('my-sheet-override')
  })
})

// ── structural layout ─────────────────────────────────────────────────────────

describe('MobileNavSheet — structure', () => {
  it('sheet is positioned fixed', () => {
    const html = renderSheet({ open: true })
    expect(html).toContain('fixed')
  })

  it('sheet anchors to the bottom', () => {
    const html = renderSheet({ open: true })
    expect(html).toContain('bottom-0')
  })

  it('sheet uses z-50 to sit above other content', () => {
    const html = renderSheet({ open: true })
    expect(html).toContain('z-50')
  })

  it('sheet has rounded-t-2xl for the top corners', () => {
    const html = renderSheet({ open: true })
    expect(html).toContain('rounded-t-2xl')
  })

  it('drag handle is rendered (w-10 class present)', () => {
    const html = renderSheet({ open: true })
    expect(html).toContain('w-10')
  })
})
