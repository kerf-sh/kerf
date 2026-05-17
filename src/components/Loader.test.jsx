// Loader.test.jsx — vitest smoke tests for the Kerf-branded triangles loader.
//
// We follow the project's existing test pattern (see freecadImport.test.jsx):
// @testing-library/react is NOT installed and adding it would violate the
// "no new npm deps" constraint. Instead we render the component to a static
// HTML string with react-dom/server (already a project dep) and assert
// structurally via substring + regex matches. This is enough to lock down
// the public API: role, aria-label, sr-only label, size scaling, custom
// className, full-page overlay shape, and inline-vs-block variant.

import { describe, it, expect } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import Loader, { FullPageLoader, InlineLoader } from './Loader.jsx'

// ── 1. Loader (default export) ─────────────────────────────────────────────

describe('Loader', () => {
  it('renders an SVG', () => {
    const html = renderToStaticMarkup(<Loader />)
    expect(html).toMatch(/<svg\b/)
  })

  it('wraps content in role="status"', () => {
    const html = renderToStaticMarkup(<Loader />)
    expect(html).toMatch(/role="status"/)
  })

  it('uses the supplied label as aria-label', () => {
    const html = renderToStaticMarkup(<Loader label="Compiling kernel" />)
    expect(html).toMatch(/aria-label="Compiling kernel"/)
  })

  it('defaults aria-label to "Loading…"', () => {
    const html = renderToStaticMarkup(<Loader />)
    expect(html).toMatch(/aria-label="Loading[……]"/)
  })

  it('renders a visually-hidden sr-only label', () => {
    const html = renderToStaticMarkup(<Loader label="Crunching" />)
    expect(html).toMatch(/class="sr-only"[^>]*>Crunching</)
  })

  it('respects aria-live="polite" for non-intrusive announcements', () => {
    const html = renderToStaticMarkup(<Loader />)
    expect(html).toMatch(/aria-live="polite"/)
  })

  it('scales the SVG width/height attributes from the size prop', () => {
    const html64 = renderToStaticMarkup(<Loader size={64} />)
    expect(html64).toMatch(/width="64"/)
    expect(html64).toMatch(/height="64"/)
    const html16 = renderToStaticMarkup(<Loader size={16} />)
    expect(html16).toMatch(/width="16"/)
    expect(html16).toMatch(/height="16"/)
  })

  it('defaults size to 48', () => {
    const html = renderToStaticMarkup(<Loader />)
    expect(html).toMatch(/width="48"/)
    expect(html).toMatch(/height="48"/)
  })

  it('uses a 0 0 100 100 viewBox so geometry scales with size', () => {
    const html = renderToStaticMarkup(<Loader />)
    expect(html).toMatch(/viewBox="0 0 100 100"/)
  })

  it('renders three <polygon> triangles', () => {
    const html = renderToStaticMarkup(<Loader />)
    const matches = html.match(/<polygon\b/g) || []
    expect(matches.length).toBe(3)
  })

  it('accepts and merges a custom className on the wrapper', () => {
    const html = renderToStaticMarkup(<Loader className="my-test-extra" />)
    expect(html).toMatch(/my-test-extra/)
  })

  it('marks the SVG aria-hidden so screen readers skip the decoration', () => {
    const html = renderToStaticMarkup(<Loader />)
    // svg should carry aria-hidden so the sr-only span carries the label
    expect(html).toMatch(/<svg[^>]*aria-hidden="true"/)
  })

  it('includes the inline animation keyframes for self-containment', () => {
    const html = renderToStaticMarkup(<Loader />)
    expect(html).toMatch(/@keyframes kerf-loader-pulse/)
  })

  it('honours prefers-reduced-motion via a media query block', () => {
    const html = renderToStaticMarkup(<Loader />)
    expect(html).toMatch(/prefers-reduced-motion: reduce/)
  })

  it('inline variant (default) yields an inline-flex wrapper', () => {
    const html = renderToStaticMarkup(<Loader />)
    expect(html).toMatch(/inline-flex/)
  })

  it('block variant yields a padded flex column wrapper', () => {
    const html = renderToStaticMarkup(<Loader variant="block" />)
    expect(html).toMatch(/flex-col/)
    expect(html).toMatch(/py-6/)
  })
})

// ── 2. FullPageLoader (named export) ───────────────────────────────────────

describe('FullPageLoader', () => {
  it('uses a fixed-overlay wrapper that covers the viewport', () => {
    const html = renderToStaticMarkup(<FullPageLoader />)
    expect(html).toMatch(/fixed/)
    expect(html).toMatch(/inset-0/)
  })

  it('places content with grid place-items-center and a dark backdrop', () => {
    const html = renderToStaticMarkup(<FullPageLoader />)
    expect(html).toMatch(/grid/)
    expect(html).toMatch(/place-items-center/)
    expect(html).toMatch(/bg-ink-950\/95/)
  })

  it('sits above app chrome via z-50', () => {
    const html = renderToStaticMarkup(<FullPageLoader />)
    expect(html).toMatch(/z-50/)
  })

  it('renders role="status" and the supplied label', () => {
    const html = renderToStaticMarkup(<FullPageLoader label="Loading project" />)
    expect(html).toMatch(/role="status"/)
    expect(html).toMatch(/aria-label="Loading project"/)
    expect(html).toContain('Loading project')
  })

  it('renders the optional sub line when supplied', () => {
    const html = renderToStaticMarkup(
      <FullPageLoader label="Loading" sub="Warming the OCCT kernel…" />
    )
    expect(html).toContain('Warming the OCCT kernel')
  })

  it('omits the sub line when not supplied', () => {
    const html = renderToStaticMarkup(<FullPageLoader label="Loading" />)
    expect(html).not.toMatch(/text-ink-400/)
  })

  it('renders three triangles, same as the inline variant', () => {
    const html = renderToStaticMarkup(<FullPageLoader />)
    const matches = html.match(/<polygon\b/g) || []
    expect(matches.length).toBe(3)
  })
})

// ── 3. InlineLoader (named export) ─────────────────────────────────────────

describe('InlineLoader', () => {
  it('pins variant to inline regardless of caller', () => {
    const html = renderToStaticMarkup(<InlineLoader variant="block" />)
    // InlineLoader forces variant='inline', so we should still see inline-flex
    // and NOT the block variant's py-6 padding.
    expect(html).toMatch(/inline-flex/)
    expect(html).not.toMatch(/py-6/)
  })

  it('forwards size to the underlying Loader', () => {
    const html = renderToStaticMarkup(<InlineLoader size={32} />)
    expect(html).toMatch(/width="32"/)
    expect(html).toMatch(/height="32"/)
  })

  it('forwards label to the underlying Loader', () => {
    const html = renderToStaticMarkup(<InlineLoader label="Saving" />)
    expect(html).toMatch(/aria-label="Saving"/)
    expect(html).toMatch(/>Saving</)
  })
})
