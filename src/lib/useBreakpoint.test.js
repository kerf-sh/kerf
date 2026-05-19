/**
 * useBreakpoint.test.js — Vitest suite for the useBreakpoint hook.
 *
 * This project uses vitest with the default node environment (no jsdom).
 * window.matchMedia is NOT available by default.
 *
 * We test three things:
 *   1. getBreakpointForWidth — pure function, no DOM needed.
 *   2. BREAKPOINTS constant — shape and values.
 *   3. useBreakpoint via renderToStaticMarkup — exercises the useState
 *      initialiser path.  We install a global window.matchMedia stub before
 *      each test so the initialiser can read window.innerWidth.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'
import { getBreakpointForWidth, BREAKPOINTS, useBreakpoint } from './useBreakpoint.js'

// ── getBreakpointForWidth (pure) ──────────────────────────────────────────────

describe('getBreakpointForWidth', () => {
  it('returns null for widths below 640 (xs range)', () => {
    expect(getBreakpointForWidth(0)).toBe(null)
    expect(getBreakpointForWidth(320)).toBe(null)
    expect(getBreakpointForWidth(639)).toBe(null)
  })

  it('returns "sm" for exactly 640', () => {
    expect(getBreakpointForWidth(640)).toBe('sm')
  })

  it('returns "sm" between 640 and 767', () => {
    expect(getBreakpointForWidth(641)).toBe('sm')
    expect(getBreakpointForWidth(767)).toBe('sm')
  })

  it('returns "md" for exactly 768', () => {
    expect(getBreakpointForWidth(768)).toBe('md')
  })

  it('returns "md" between 768 and 1023', () => {
    expect(getBreakpointForWidth(769)).toBe('md')
    expect(getBreakpointForWidth(1023)).toBe('md')
  })

  it('returns "lg" for exactly 1024', () => {
    expect(getBreakpointForWidth(1024)).toBe('lg')
  })

  it('returns "lg" between 1024 and 1279', () => {
    expect(getBreakpointForWidth(1025)).toBe('lg')
    expect(getBreakpointForWidth(1279)).toBe('lg')
  })

  it('returns "xl" for exactly 1280', () => {
    expect(getBreakpointForWidth(1280)).toBe('xl')
  })

  it('returns "xl" between 1280 and 1535', () => {
    expect(getBreakpointForWidth(1281)).toBe('xl')
    expect(getBreakpointForWidth(1535)).toBe('xl')
  })

  it('returns "2xl" for exactly 1536', () => {
    expect(getBreakpointForWidth(1536)).toBe('2xl')
  })

  it('returns "2xl" for very large widths', () => {
    expect(getBreakpointForWidth(1920)).toBe('2xl')
    expect(getBreakpointForWidth(3840)).toBe('2xl')
  })
})

// ── BREAKPOINTS constant ──────────────────────────────────────────────────────

describe('BREAKPOINTS', () => {
  it('exports an array', () => {
    expect(Array.isArray(BREAKPOINTS)).toBe(true)
  })

  it('contains entries for all five named breakpoints', () => {
    const names = BREAKPOINTS.map((b) => b.name)
    expect(names).toContain('sm')
    expect(names).toContain('md')
    expect(names).toContain('lg')
    expect(names).toContain('xl')
    expect(names).toContain('2xl')
  })

  it('uses correct minWidth values per Tailwind defaults', () => {
    const map = Object.fromEntries(BREAKPOINTS.map((b) => [b.name, b.minWidth]))
    expect(map['sm']).toBe(640)
    expect(map['md']).toBe(768)
    expect(map['lg']).toBe(1024)
    expect(map['xl']).toBe(1280)
    expect(map['2xl']).toBe(1536)
  })
})

// ── useBreakpoint via renderToStaticMarkup ────────────────────────────────────
//
// We use a thin wrapper component so the hook is called inside a component
// body.  renderToStaticMarkup exercises only the useState initialiser
// (no useEffect), which is the correct contract for SSR / static render.

/**
 * Stubs globalThis.window with a minimal window-like object that provides
 * innerWidth and matchMedia so useBreakpoint's initialiser works in Node.
 */
function stubWindow(width) {
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

function BreakpointProbe() {
  const bp = useBreakpoint()
  return React.createElement('span', { 'data-bp': bp ?? 'null' })
}

function renderBreakpoint(width) {
  stubWindow(width)
  try {
    const html = renderToStaticMarkup(React.createElement(BreakpointProbe))
    const match = html.match(/data-bp="([^"]*)"/)
    return match ? match[1] : null
  } finally {
    delete globalThis.window
  }
}

describe('useBreakpoint — returns correct breakpoint per stubbed matchMedia', () => {
  it('returns null for xs widths (< 640)', () => {
    expect(renderBreakpoint(480)).toBe('null')
  })

  it('returns "sm" at 640', () => {
    expect(renderBreakpoint(640)).toBe('sm')
  })

  it('returns "md" at 768', () => {
    expect(renderBreakpoint(768)).toBe('md')
  })

  it('returns "lg" at 1024', () => {
    expect(renderBreakpoint(1024)).toBe('lg')
  })

  it('returns "xl" at 1280', () => {
    expect(renderBreakpoint(1280)).toBe('xl')
  })

  it('returns "2xl" at 1536', () => {
    expect(renderBreakpoint(1536)).toBe('2xl')
  })

  it('returns "2xl" at a very large width (4K)', () => {
    expect(renderBreakpoint(3840)).toBe('2xl')
  })

  it('returns "sm" at 767 (just below md)', () => {
    expect(renderBreakpoint(767)).toBe('sm')
  })
})

// ── useBreakpoint — no matchMedia (SSR path) ──────────────────────────────────

describe('useBreakpoint — no matchMedia', () => {
  it('returns null when window is undefined (pure SSR)', () => {
    // In the node environment window is undefined by default.
    // getBreakpointForWidth is pure so we verify the guard indirectly.
    const savedWindow = globalThis.window
    delete globalThis.window
    try {
      const html = renderToStaticMarkup(React.createElement(BreakpointProbe))
      const match = html.match(/data-bp="([^"]*)"/)
      const bp = match ? match[1] : null
      expect(bp).toBe('null')
    } finally {
      if (savedWindow !== undefined) globalThis.window = savedWindow
    }
  })
})
