/**
 * dirtyTimer.test.js — T-185
 *
 * Tests for DirtyTimer.  Uses vitest fake timers so we never wait real time.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { DirtyTimer, WARN_AFTER_MS } from './dirtyTimer'

const WS = 'ws-test-001'
const TICK = 60_000  // matches TICK_INTERVAL_MS inside DirtyTimer

// Helper: advance fake timers and flush microtasks
async function advance(ms) {
  vi.advanceTimersByTime(ms)
  await Promise.resolve()
}

describe('DirtyTimer', () => {
  let events
  let emitter
  let timer

  beforeEach(() => {
    vi.useFakeTimers()
    events = []
    emitter = (e) => events.push(e)
    timer = new DirtyTimer({ emitter })
  })

  afterEach(() => {
    timer.destroy()
    vi.useRealTimers()
  })

  // ── 1. No event before warn threshold ───────────────────────────────────────

  it('does NOT emit before WARN_AFTER_MS has elapsed', async () => {
    timer.markCommit(WS)
    // advance just under the threshold (29 min)
    await advance(29 * 60_000)
    // tick fires every 60s — 29 ticks have fired
    expect(events).toHaveLength(0)
  })

  // ── 2. Event fires once WARN_AFTER_MS has elapsed ───────────────────────────

  it('emits uncommitted-too-long after WARN_AFTER_MS', async () => {
    timer.markCommit(WS)
    await advance(WARN_AFTER_MS + TICK)
    expect(events).toHaveLength(1)
    expect(events[0].type).toBe('uncommitted-too-long')
    expect(events[0].detail.workspaceId).toBe(WS)
    expect(events[0].detail.dirtyMs).toBeGreaterThanOrEqual(WARN_AFTER_MS)
  })

  // ── 3. markCommit resets the clock (no double-fire) ─────────────────────────

  it('markCommit resets the dirty clock — warning does not fire again until another threshold elapses', async () => {
    timer.markCommit(WS)
    await advance(WARN_AFTER_MS + TICK)   // fires once
    expect(events).toHaveLength(1)

    // User commits — reset
    timer.markCommit(WS)
    await advance(29 * 60_000)             // not yet another 30 min
    expect(events).toHaveLength(1)         // no second event

    await advance(WARN_AFTER_MS)           // now another 30 min past second commit
    expect(events).toHaveLength(2)
  })

  // ── 4. Warning fires only once per dirty window (idempotent) ────────────────

  it('emits at most one event per dirty window even over multiple ticks', async () => {
    timer.markCommit(WS)
    // advance well past the threshold — many ticks
    await advance(WARN_AFTER_MS + 10 * TICK)
    expect(events).toHaveLength(1)
  })

  // ── 5. watchWorkspace with stale lastCommitAt triggers immediately ───────────

  it('fires immediately on next tick when watchWorkspace is given a stale timestamp', async () => {
    const staleTs = Date.now() - (WARN_AFTER_MS + 5 * 60_000)
    timer.watchWorkspace(WS, staleTs)
    await advance(TICK)   // first tick
    expect(events).toHaveLength(1)
  })

  // ── 6. unwatchWorkspace stops tracking ──────────────────────────────────────

  it('stops emitting after unwatchWorkspace', async () => {
    timer.markCommit(WS)
    timer.unwatchWorkspace(WS)
    await advance(WARN_AFTER_MS + 10 * TICK)
    expect(events).toHaveLength(0)
  })

  // ── 7. Multiple workspaces tracked independently ─────────────────────────────

  it('tracks multiple workspaces independently', async () => {
    const WS2 = 'ws-test-002'
    // WS1 committed 35 min ago, WS2 committed just now
    timer.watchWorkspace(WS, Date.now() - 35 * 60_000)
    timer.markCommit(WS2)

    await advance(TICK)   // WS1 over threshold, WS2 not
    expect(events).toHaveLength(1)
    expect(events[0].detail.workspaceId).toBe(WS)
  })
})
