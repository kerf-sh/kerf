/**
 * ResponsiveContainer.test.jsx — Vitest suite for ResponsiveContainer.
 *
 * Runs under vitest's default node environment (no jsdom).  We install a
 * minimal globalThis.window stub with innerWidth + matchMedia before each
 * test group so that useBreakpoint's useState initialiser can derive the
 * correct breakpoint.
 *
 * Components are rendered via renderToStaticMarkup (react-dom/server) which
 * exercises only the synchronous render path — sufficient for asserting CSS
 * class presence and ARIA/data-* attribute values.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'
import ResponsiveContainer from './ResponsiveContainer.jsx'

// ── window stub helpers ────────────────────────────────────────────────────────

let savedWindow

function stubWidth(width) {
  globalThis.window = {
    innerWidth: width,
    matchMedia: vi.fn((query) => {
      const match = query.match(/\(min-width:\s*(\d+)px\)/)
      const minWidth = match ? parseInt(match[1], 10) : 0
      return {
        matches: width >= minWidth,
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      }
    }),
  }
}

beforeEach(() => {
  savedWindow = globalThis.window
})

afterEach(() => {
  globalThis.window = savedWindow
})

// ── Rendering ─────────────────────────────────────────────────────────────────

describe('ResponsiveContainer — renders', () => {
  it('renders a div wrapper', () => {
    stubWidth(400)
    const html = renderToStaticMarkup(React.createElement(ResponsiveContainer))
    expect(html).toMatch(/^<div/)
  })

  it('renders children', () => {
    stubWidth(400)
    const html = renderToStaticMarkup(
      React.createElement(ResponsiveContainer, null,
        React.createElement('span', { id: 'child' }, 'hello'),
      ),
    )
    expect(html).toContain('id="child"')
    expect(html).toContain('hello')
  })

  it('merges custom className', () => {
    stubWidth(400)
    const html = renderToStaticMarkup(
      React.createElement(ResponsiveContainer, { className: 'my-custom-class' }),
    )
    expect(html).toContain('my-custom-class')
  })

  it('exposes data-layout attribute', () => {
    stubWidth(400)
    const html = renderToStaticMarkup(React.createElement(ResponsiveContainer))
    expect(html).toMatch(/data-layout="(col|row)"/)
  })

  it('exposes data-breakpoint attribute', () => {
    stubWidth(400)
    const html = renderToStaticMarkup(React.createElement(ResponsiveContainer))
    expect(html).toMatch(/data-breakpoint="/)
  })
})

// ── flex-col at small widths ──────────────────────────────────────────────────

describe('ResponsiveContainer — flex-col below stackedAt', () => {
  it('uses flex-col at 400 px (xs, default stackedAt=md)', () => {
    stubWidth(400)
    const html = renderToStaticMarkup(React.createElement(ResponsiveContainer))
    expect(html).toContain('flex-col')
    expect(html).not.toContain('flex-row')
  })

  it('uses flex-col at 640 px (sm, default stackedAt=md)', () => {
    stubWidth(640)
    const html = renderToStaticMarkup(React.createElement(ResponsiveContainer))
    expect(html).toContain('flex-col')
    expect(html).not.toContain('flex-row')
  })

  it('uses flex-col at 767 px (just below md, default stackedAt=md)', () => {
    stubWidth(767)
    const html = renderToStaticMarkup(React.createElement(ResponsiveContainer))
    expect(html).toContain('flex-col')
    expect(html).not.toContain('flex-row')
  })

  it('has data-layout="col" below stackedAt', () => {
    stubWidth(400)
    const html = renderToStaticMarkup(React.createElement(ResponsiveContainer))
    expect(html).toContain('data-layout="col"')
  })
})

// ── flex-row at or above stackedAt ────────────────────────────────────────────

describe('ResponsiveContainer — flex-row at/above stackedAt', () => {
  it('uses flex-row at exactly 768 px (md, default stackedAt=md)', () => {
    stubWidth(768)
    const html = renderToStaticMarkup(React.createElement(ResponsiveContainer))
    expect(html).toContain('flex-row')
    expect(html).not.toContain('flex-col')
  })

  it('uses flex-row at 1024 px (lg, default stackedAt=md)', () => {
    stubWidth(1024)
    const html = renderToStaticMarkup(React.createElement(ResponsiveContainer))
    expect(html).toContain('flex-row')
  })

  it('uses flex-row at 1920 px (2xl, default stackedAt=md)', () => {
    stubWidth(1920)
    const html = renderToStaticMarkup(React.createElement(ResponsiveContainer))
    expect(html).toContain('flex-row')
  })

  it('has data-layout="row" at/above stackedAt', () => {
    stubWidth(768)
    const html = renderToStaticMarkup(React.createElement(ResponsiveContainer))
    expect(html).toContain('data-layout="row"')
  })
})

// ── custom stackedAt values ───────────────────────────────────────────────────

describe('ResponsiveContainer — custom stackedAt', () => {
  it('stacks at sm: flex-col below 640', () => {
    stubWidth(639)
    const html = renderToStaticMarkup(
      React.createElement(ResponsiveContainer, { stackedAt: 'sm' }),
    )
    expect(html).toContain('flex-col')
  })

  it('stacks at sm: flex-row at 640', () => {
    stubWidth(640)
    const html = renderToStaticMarkup(
      React.createElement(ResponsiveContainer, { stackedAt: 'sm' }),
    )
    expect(html).toContain('flex-row')
  })

  it('stacks at lg: flex-col at 768', () => {
    stubWidth(768)
    const html = renderToStaticMarkup(
      React.createElement(ResponsiveContainer, { stackedAt: 'lg' }),
    )
    expect(html).toContain('flex-col')
  })

  it('stacks at lg: flex-row at 1024', () => {
    stubWidth(1024)
    const html = renderToStaticMarkup(
      React.createElement(ResponsiveContainer, { stackedAt: 'lg' }),
    )
    expect(html).toContain('flex-row')
  })

  it('stacks at xl: flex-col at 1024', () => {
    stubWidth(1024)
    const html = renderToStaticMarkup(
      React.createElement(ResponsiveContainer, { stackedAt: 'xl' }),
    )
    expect(html).toContain('flex-col')
  })

  it('stacks at xl: flex-row at 1280', () => {
    stubWidth(1280)
    const html = renderToStaticMarkup(
      React.createElement(ResponsiveContainer, { stackedAt: 'xl' }),
    )
    expect(html).toContain('flex-row')
  })

  it('stacks at 2xl: flex-col at 1280', () => {
    stubWidth(1280)
    const html = renderToStaticMarkup(
      React.createElement(ResponsiveContainer, { stackedAt: '2xl' }),
    )
    expect(html).toContain('flex-col')
  })

  it('stacks at 2xl: flex-row at 1536', () => {
    stubWidth(1536)
    const html = renderToStaticMarkup(
      React.createElement(ResponsiveContainer, { stackedAt: '2xl' }),
    )
    expect(html).toContain('flex-row')
  })
})

// ── SSR / no matchMedia (null breakpoint) ─────────────────────────────────────

describe('ResponsiveContainer — SSR / no matchMedia', () => {
  it('defaults to flex-col when window is undefined', () => {
    delete globalThis.window
    const html = renderToStaticMarkup(React.createElement(ResponsiveContainer))
    expect(html).toContain('flex-col')
  })
})

// ── gap prop ─────────────────────────────────────────────────────────────────

describe('ResponsiveContainer — gap prop', () => {
  it('applies default gap-4 class', () => {
    stubWidth(400)
    const html = renderToStaticMarkup(React.createElement(ResponsiveContainer))
    expect(html).toContain('gap-4')
  })

  it('accepts a custom gap class', () => {
    stubWidth(400)
    const html = renderToStaticMarkup(
      React.createElement(ResponsiveContainer, { gap: 'gap-8' }),
    )
    expect(html).toContain('gap-8')
  })
})
