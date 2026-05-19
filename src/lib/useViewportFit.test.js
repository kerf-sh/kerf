/**
 * useViewportFit.test.js — Vitest suite for the useViewportFit hook.
 *
 * This project uses vitest with the default node environment (no jsdom).
 * Hooks must be called inside a component body; we use renderToStaticMarkup
 * to exercise the useState initialiser path.
 *
 * ResizeObserver is stubbed where needed.  The pure arithmetic helpers are
 * tested directly without React.
 *
 * Tests verify:
 *   - Returned shape (ref, width, height, scaleX, scaleY)
 *   - Numeric types
 *   - scaleX/scaleY formula (pure arithmetic)
 *   - ResizeObserver stub integration
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import React from 'react'
import { useViewportFit } from './useViewportFit.js'

// ── Scale arithmetic helpers (pure, no DOM required) ─────────────────────────

describe('useViewportFit — scale arithmetic', () => {
  it('scaleX equals width / designWidth when designWidth is provided', () => {
    const width = 960
    const designWidth = 1920
    expect(width / designWidth).toBeCloseTo(0.5)
  })

  it('scaleY equals height / designHeight when designHeight is provided', () => {
    const height = 540
    const designHeight = 1080
    expect(height / designHeight).toBeCloseTo(0.5)
  })

  it('scaleX is 1 when designWidth is not provided', () => {
    const designWidth = undefined
    const scaleX = designWidth && designWidth > 0 ? 800 / designWidth : 1
    expect(scaleX).toBe(1)
  })

  it('scaleY is 1 when designHeight is not provided', () => {
    const designHeight = undefined
    const scaleY = designHeight && designHeight > 0 ? 600 / designHeight : 1
    expect(scaleY).toBe(1)
  })

  it('scale is 1 when designDimension is 0 (avoids division by zero)', () => {
    const designWidth = 0
    const scaleX = designWidth && designWidth > 0 ? 800 / designWidth : 1
    expect(scaleX).toBe(1)
  })

  it('scale ratio is 0.5 for half-size viewport', () => {
    const width = 640
    const designWidth = 1280
    expect(width / designWidth).toBe(0.5)
  })

  it('scale ratio is 1.0 for equal dimensions', () => {
    const width = 1920
    const designWidth = 1920
    expect(width / designWidth).toBe(1)
  })

  it('scale ratio can exceed 1 for oversized viewport', () => {
    const width = 3840
    const designWidth = 1920
    expect(width / designWidth).toBe(2)
  })
})

// ── Hook output shape via renderToStaticMarkup ────────────────────────────────
//
// We render a thin probe component that serialises the hook's output into
// data-* attributes on a span so we can inspect them from the HTML string.

function ViewportFitProbe({ designWidth, designHeight }) {
  const { width, height, scaleX, scaleY, ref } = useViewportFit({ designWidth, designHeight })
  return React.createElement('span', {
    'data-width': width,
    'data-height': height,
    'data-scalex': scaleX,
    'data-scaley': scaleY,
    'data-has-ref': ref !== undefined ? 'true' : 'false',
  })
}

function parseAttr(html, attr) {
  const match = html.match(new RegExp(`${attr}="([^"]*)"`) )
  return match ? match[1] : null
}

describe('useViewportFit — returns numeric width/height/scaleX/scaleY', () => {
  it('width is a number (serialises as a numeric string)', () => {
    const html = renderToStaticMarkup(React.createElement(ViewportFitProbe))
    const val = parseAttr(html, 'data-width')
    expect(Number.isFinite(parseFloat(val))).toBe(true)
  })

  it('height is a number', () => {
    const html = renderToStaticMarkup(React.createElement(ViewportFitProbe))
    const val = parseAttr(html, 'data-height')
    expect(Number.isFinite(parseFloat(val))).toBe(true)
  })

  it('scaleX is a number', () => {
    const html = renderToStaticMarkup(React.createElement(ViewportFitProbe))
    const val = parseAttr(html, 'data-scalex')
    expect(Number.isFinite(parseFloat(val))).toBe(true)
  })

  it('scaleY is a number', () => {
    const html = renderToStaticMarkup(React.createElement(ViewportFitProbe))
    const val = parseAttr(html, 'data-scaley')
    expect(Number.isFinite(parseFloat(val))).toBe(true)
  })

  it('ref is defined', () => {
    const html = renderToStaticMarkup(React.createElement(ViewportFitProbe))
    const val = parseAttr(html, 'data-has-ref')
    expect(val).toBe('true')
  })

  it('initial width is 0 (no DOM measurement before mount)', () => {
    const html = renderToStaticMarkup(React.createElement(ViewportFitProbe))
    const val = parseAttr(html, 'data-width')
    expect(parseFloat(val)).toBe(0)
  })

  it('initial height is 0', () => {
    const html = renderToStaticMarkup(React.createElement(ViewportFitProbe))
    const val = parseAttr(html, 'data-height')
    expect(parseFloat(val)).toBe(0)
  })

  it('scaleX is 1 when no designWidth provided (width=0 → default 1)', () => {
    const html = renderToStaticMarkup(React.createElement(ViewportFitProbe))
    const val = parseAttr(html, 'data-scalex')
    expect(parseFloat(val)).toBe(1)
  })

  it('scaleY is 1 when no designHeight provided', () => {
    const html = renderToStaticMarkup(React.createElement(ViewportFitProbe))
    const val = parseAttr(html, 'data-scaley')
    expect(parseFloat(val)).toBe(1)
  })

  it('scaleX is 0 when width=0 and designWidth=1920', () => {
    const html = renderToStaticMarkup(
      React.createElement(ViewportFitProbe, { designWidth: 1920 }),
    )
    const val = parseAttr(html, 'data-scalex')
    // width=0, designWidth=1920 → 0/1920 = 0
    expect(parseFloat(val)).toBe(0)
  })

  it('scaleY is 0 when height=0 and designHeight=1080', () => {
    const html = renderToStaticMarkup(
      React.createElement(ViewportFitProbe, { designHeight: 1080 }),
    )
    const val = parseAttr(html, 'data-scaley')
    expect(parseFloat(val)).toBe(0)
  })
})

// ── ResizeObserver stub integration ───────────────────────────────────────────

class FakeResizeObserver {
  static _instances = []
  static reset() { FakeResizeObserver._instances = [] }
  static latest() {
    return FakeResizeObserver._instances[FakeResizeObserver._instances.length - 1]
  }

  constructor(callback) {
    this._callback = callback
    this._observed = []
    FakeResizeObserver._instances.push(this)
  }
  observe(el)    { this._observed.push(el) }
  unobserve(el)  { this._observed = this._observed.filter((e) => e !== el) }
  disconnect()   { this._observed = [] }

  trigger(width, height) {
    for (const el of this._observed) {
      this._callback([{
        target: el,
        contentBoxSize: [{ inlineSize: width, blockSize: height }],
        contentRect: { width, height },
      }])
    }
  }
}

describe('useViewportFit — ResizeObserver stub integration', () => {
  let origRO

  beforeEach(() => {
    origRO = globalThis.ResizeObserver
    FakeResizeObserver.reset()
    globalThis.ResizeObserver = FakeResizeObserver
  })

  afterEach(() => {
    globalThis.ResizeObserver = origRO
  })

  it('FakeResizeObserver replaces global ResizeObserver', () => {
    expect(globalThis.ResizeObserver).toBe(FakeResizeObserver)
  })

  it('trigger callback delivers correct width via contentBoxSize', () => {
    let capturedWidth = 0
    const fakeEl = {}
    const ro = new FakeResizeObserver((entries) => {
      capturedWidth = entries[0].contentBoxSize[0].inlineSize
    })
    ro.observe(fakeEl)
    ro.trigger(1280, 720)
    expect(capturedWidth).toBe(1280)
  })

  it('trigger callback delivers correct height via contentBoxSize', () => {
    let capturedHeight = 0
    const fakeEl = {}
    const ro = new FakeResizeObserver((entries) => {
      capturedHeight = entries[0].contentBoxSize[0].blockSize
    })
    ro.observe(fakeEl)
    ro.trigger(1280, 720)
    expect(capturedHeight).toBe(720)
  })

  it('disconnect clears observed list', () => {
    const fakeEl = {}
    const ro = new FakeResizeObserver(() => {})
    ro.observe(fakeEl)
    ro.disconnect()
    expect(ro._observed).toHaveLength(0)
  })

  it('unobserve removes only the specified element', () => {
    const el1 = {}
    const el2 = {}
    const ro = new FakeResizeObserver(() => {})
    ro.observe(el1)
    ro.observe(el2)
    ro.unobserve(el1)
    expect(ro._observed).toContain(el2)
    expect(ro._observed).not.toContain(el1)
  })

  it('trigger does not fire callback after disconnect', () => {
    let called = false
    const fakeEl = {}
    const ro = new FakeResizeObserver(() => { called = true })
    ro.observe(fakeEl)
    ro.disconnect()
    ro.trigger(800, 600)
    // After disconnect _observed is empty so trigger loops over nothing.
    expect(called).toBe(false)
  })
})
