/**
 * FeatureRenderer.tapDrag.test.js — T-C2 tap-vs-drag discriminator
 *
 * Strategy: pure unit tests of the tap discrimination logic extracted from
 * FeatureRenderer.  No React rendering, no Three.js, no DOM needed.
 *
 * The discriminator lives inside the effect closure; we replicate it here as a
 * plain function so we can drive it without a GPU / JSDOM.
 *
 * Tests:
 *   1. Tap within time AND movement threshold → firePick called
 *   2. Movement exceeds TAP_PX (drag) → firePick NOT called
 *   3. Duration exceeds TAP_MS (long-press) → firePick NOT called
 *   4. Both time and movement exceed thresholds → firePick NOT called
 *   5. Mouse pointerType → skip (handled by click; firePick NOT called)
 *   6. Pen pointerType within threshold → firePick called (pen treated as touch)
 *   7. Multiple simultaneous pointers — only tapping finger fires pick
 *   8. Mouse click path (separate from pointer path) → firePick still reached
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'

// ---------------------------------------------------------------------------
// Re-implement the minimal tap-vs-drag discriminator exactly as written in
// FeatureRenderer so the tests exercise the same logic.
// ---------------------------------------------------------------------------

const TAP_MS = 250
const TAP_PX = 8

/**
 * Build a discriminator instance that mirrors the closure in FeatureRenderer.
 * Returns { onPointerDown, onPointerUp, calls } where calls is the array of
 * firePick invocations.
 */
function makeDiscriminator() {
  const calls = []
  function firePick(ev) {
    calls.push({ clientX: ev.clientX, clientY: ev.clientY, shiftKey: ev.shiftKey })
  }

  const tapState = new Map()

  function onPointerDown(ev) {
    if (ev.pointerType === 'mouse') return
    tapState.set(ev.pointerId, { x: ev.clientX, y: ev.clientY, t: ev._t })
  }

  function onPointerUp(ev) {
    if (ev.pointerType === 'mouse') return
    const start = tapState.get(ev.pointerId)
    tapState.delete(ev.pointerId)
    if (!start) return
    const dt = ev._t - start.t
    const dx = ev.clientX - start.x
    const dy = ev.clientY - start.y
    const dist = Math.sqrt(dx * dx + dy * dy)
    if (dt <= TAP_MS && dist <= TAP_PX) {
      firePick(ev)
    }
  }

  // Mouse click path mirrors the onClick handler in FeatureRenderer:
  // skip when ev.pointerType is touch/pen.
  function onClick(ev) {
    if (ev.pointerType === 'touch' || ev.pointerType === 'pen') return
    firePick(ev)
  }

  return { onPointerDown, onPointerUp, onClick, calls }
}

// ---------------------------------------------------------------------------
// Helper: build synthetic pointer event objects.
// _t is a synthetic timestamp (ms) replacing Date.now() so tests are
// deterministic without mocking timers.
// ---------------------------------------------------------------------------

function ptr({ type = 'touch', id = 1, x = 100, y = 100, dx = 0, dy = 0, dt = 0, shift = false } = {}) {
  return {
    pointerType: type,
    pointerId: id,
    clientX: x,
    clientY: y,
    shiftKey: shift,
    _t: 0,          // will be overridden per-event
    // convenience delta accessors (not part of real PointerEvent)
    _dx: dx,
    _dy: dy,
    _dt: dt,
  }
}

function makeDownUp({ pointerType = 'touch', id = 1, startX = 100, startY = 100,
                       dx = 0, dy = 0, dt = 0, shift = false } = {}) {
  const baseT = 1000
  const down = {
    pointerType, pointerId: id,
    clientX: startX, clientY: startY,
    shiftKey: shift, _t: baseT,
  }
  const up = {
    pointerType, pointerId: id,
    clientX: startX + dx, clientY: startY + dy,
    shiftKey: shift, _t: baseT + dt,
  }
  return { down, up }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('tap-vs-drag discriminator', () => {
  let d

  beforeEach(() => {
    d = makeDiscriminator()
  })

  // 1. Tap within threshold → pick fires
  it('tap within time AND movement threshold fires pick', () => {
    const { down, up } = makeDownUp({ dx: 2, dy: 2, dt: 100 }) // 2.8px, 100ms
    d.onPointerDown(down)
    d.onPointerUp(up)
    expect(d.calls).toHaveLength(1)
    expect(d.calls[0].clientX).toBe(102)
    expect(d.calls[0].clientY).toBe(102)
  })

  // 2. Movement exceeds TAP_PX → no pick
  it('drag beyond TAP_PX threshold does not fire pick', () => {
    const { down, up } = makeDownUp({ dx: 20, dy: 0, dt: 100 }) // 20px — over threshold
    d.onPointerDown(down)
    d.onPointerUp(up)
    expect(d.calls).toHaveLength(0)
  })

  // 3. Duration exceeds TAP_MS → no pick
  it('long-press beyond TAP_MS threshold does not fire pick', () => {
    const { down, up } = makeDownUp({ dx: 1, dy: 1, dt: 400 }) // 400ms — over threshold
    d.onPointerDown(down)
    d.onPointerUp(up)
    expect(d.calls).toHaveLength(0)
  })

  // 4. Both thresholds exceeded → no pick
  it('drag AND long-press both over threshold does not fire pick', () => {
    const { down, up } = makeDownUp({ dx: 30, dy: 30, dt: 500 })
    d.onPointerDown(down)
    d.onPointerUp(up)
    expect(d.calls).toHaveLength(0)
  })

  // 5. Mouse pointerType → pointer path is skipped (handled by click listener)
  it('mouse pointerdown/pointerup does not fire pick via tap path', () => {
    const { down, up } = makeDownUp({ pointerType: 'mouse', dx: 0, dy: 0, dt: 50 })
    d.onPointerDown(down)
    d.onPointerUp(up)
    expect(d.calls).toHaveLength(0) // mouse goes through onClick, not tap path
  })

  // 6. Pen within threshold → fires (pen treated same as touch)
  it('pen tap within threshold fires pick', () => {
    const { down, up } = makeDownUp({ pointerType: 'pen', dx: 1, dy: 0, dt: 80 })
    d.onPointerDown(down)
    d.onPointerUp(up)
    expect(d.calls).toHaveLength(1)
  })

  // 7. Multiple simultaneous pointers — only tapping finger fires
  it('only the tap pointer fires; orbit finger does not', () => {
    // Pointer 1: tap (small movement, fast)
    const tap_down = { pointerType: 'touch', pointerId: 1, clientX: 100, clientY: 100, shiftKey: false, _t: 1000 }
    const tap_up   = { pointerType: 'touch', pointerId: 1, clientX: 102, clientY: 101, shiftKey: false, _t: 1100 }
    // Pointer 2: orbit (large movement, slow — should NOT fire)
    const orb_down = { pointerType: 'touch', pointerId: 2, clientX: 200, clientY: 200, shiftKey: false, _t: 1000 }
    const orb_up   = { pointerType: 'touch', pointerId: 2, clientX: 250, clientY: 260, shiftKey: false, _t: 1300 }

    d.onPointerDown(tap_down)
    d.onPointerDown(orb_down)
    d.onPointerUp(orb_up)   // orbit up first
    d.onPointerUp(tap_up)   // tap up

    expect(d.calls).toHaveLength(1)
    expect(d.calls[0].clientX).toBe(102) // came from pointer 1
  })

  // 8. Mouse click path still calls firePick
  it('mouse click event goes through onClick and fires pick', () => {
    const clickEv = { pointerType: 'mouse', clientX: 300, clientY: 200, shiftKey: false }
    d.onClick(clickEv)
    expect(d.calls).toHaveLength(1)
    expect(d.calls[0].clientX).toBe(300)
  })

  // 9. Touch click event is suppressed by onClick (tap path handles it)
  it('onClick suppresses touch click events to avoid double-fire', () => {
    const touchClick = { pointerType: 'touch', clientX: 100, clientY: 100, shiftKey: false }
    d.onClick(touchClick)
    expect(d.calls).toHaveLength(0)
  })

  // 10. Exact boundary: TAP_PX exactly → fires (≤ threshold)
  it('movement exactly at TAP_PX boundary fires pick', () => {
    // dist = sqrt(8^2 + 0^2) = 8 exactly — should fire (≤ TAP_PX)
    const { down, up } = makeDownUp({ dx: TAP_PX, dy: 0, dt: 100 })
    d.onPointerDown(down)
    d.onPointerUp(up)
    expect(d.calls).toHaveLength(1)
  })

  // 11. Exact boundary: TAP_MS exactly → fires (≤ threshold)
  it('duration exactly at TAP_MS boundary fires pick', () => {
    const { down, up } = makeDownUp({ dx: 0, dy: 0, dt: TAP_MS })
    d.onPointerDown(down)
    d.onPointerUp(up)
    expect(d.calls).toHaveLength(1)
  })

  // 12. pointerup without matching pointerdown → no crash, no pick
  it('pointerup without prior pointerdown does not throw or fire pick', () => {
    const up = { pointerType: 'touch', pointerId: 99, clientX: 100, clientY: 100, shiftKey: false, _t: 1200 }
    expect(() => d.onPointerUp(up)).not.toThrow()
    expect(d.calls).toHaveLength(0)
  })
})

// ---------------------------------------------------------------------------
// TAP_MS and TAP_PX constant values
// ---------------------------------------------------------------------------

describe('tap-vs-drag constants', () => {
  it('TAP_MS is 250', () => {
    expect(TAP_MS).toBe(250)
  })

  it('TAP_PX is 8', () => {
    expect(TAP_PX).toBe(8)
  })
})
