/**
 * dirtyTimer.js — T-185
 *
 * Tracks the timestamp of the last deliberate commit per workspace and emits a
 * custom DOM event `uncommitted-too-long` once the workspace has been dirty
 * (i.e. no deliberate commit) for longer than WARN_AFTER_MS.
 *
 * Usage:
 *
 *   import { DirtyTimer } from './dirtyTimer'
 *
 *   const timer = new DirtyTimer()
 *
 *   // Call this whenever a deliberate commit lands:
 *   timer.markCommit(workspaceId)
 *
 *   // The timer fires window event 'uncommitted-too-long'
 *   // with { detail: { workspaceId, dirtyMs } } after WARN_AFTER_MS.
 *
 * The timer is safe to use in test environments — pass a custom `emitter`
 * function instead of the default `window.dispatchEvent`.
 */

export const WARN_AFTER_MS = 30 * 60 * 1000  // 30 minutes
const TICK_INTERVAL_MS = 60 * 1000            // check every 60 s

export class DirtyTimer {
  /**
   * @param {object} opts
   * @param {(event: CustomEvent) => void} [opts.emitter]   Override event dispatch (for tests)
   * @param {number}  [opts.warnAfterMs]   Threshold in ms before warning (default 30 min)
   */
  constructor({ emitter = null, warnAfterMs = WARN_AFTER_MS } = {}) {
    /** @type {Map<string, number>} workspaceId → timestamp of last deliberate commit (ms) */
    this._lastCommitAt = new Map()
    /** @type {Set<string>} workspaces that have already had the warning fired this dirty window */
    this._warned = new Set()
    this._warnAfterMs = warnAfterMs
    this._emitter = emitter || ((e) => typeof window !== 'undefined' && window.dispatchEvent(e))
    this._intervalId = null
  }

  /**
   * Record a deliberate commit for a workspace.
   * Resets the dirty clock and clears any previous warning state.
   *
   * @param {string} workspaceId
   */
  markCommit(workspaceId) {
    this._lastCommitAt.set(workspaceId, Date.now())
    this._warned.delete(workspaceId)
    if (this._intervalId === null) {
      this._startTicking()
    }
  }

  /**
   * Manually register a workspace without resetting the clock.
   * Call this on mount to start tracking a workspace that may already be dirty.
   *
   * @param {string} workspaceId
   * @param {number} [lastCommitAt]  Epoch ms of the last known deliberate commit.
   *                                 Defaults to now (optimistically clean).
   */
  watchWorkspace(workspaceId, lastCommitAt = Date.now()) {
    if (!this._lastCommitAt.has(workspaceId)) {
      this._lastCommitAt.set(workspaceId, lastCommitAt)
    }
    if (this._intervalId === null) {
      this._startTicking()
    }
  }

  /**
   * Stop tracking a workspace (e.g. on unmount).
   * @param {string} workspaceId
   */
  unwatchWorkspace(workspaceId) {
    this._lastCommitAt.delete(workspaceId)
    this._warned.delete(workspaceId)
    if (this._lastCommitAt.size === 0) {
      this._stopTicking()
    }
  }

  /** Stop the internal polling interval. */
  destroy() {
    this._stopTicking()
    this._lastCommitAt.clear()
    this._warned.clear()
  }

  // ── internals ───────────────────────────────────────────────────────────────

  _startTicking() {
    if (this._intervalId !== null) return
    this._intervalId = setInterval(() => this._tick(), TICK_INTERVAL_MS)
  }

  _stopTicking() {
    if (this._intervalId !== null) {
      clearInterval(this._intervalId)
      this._intervalId = null
    }
  }

  _tick() {
    const now = Date.now()
    for (const [wsId, lastAt] of this._lastCommitAt) {
      const dirtyMs = now - lastAt
      if (dirtyMs >= this._warnAfterMs && !this._warned.has(wsId)) {
        this._warned.add(wsId)
        this._emitter(
          new CustomEvent('uncommitted-too-long', {
            detail: { workspaceId: wsId, dirtyMs },
            bubbles: true,
            cancelable: false,
          })
        )
      }
    }
  }
}

/** Module-level singleton for convenience. */
export const dirtyTimer = new DirtyTimer()
