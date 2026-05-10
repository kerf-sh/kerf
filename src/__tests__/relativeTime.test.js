// relativeTime.test.js — boundary tests for the History-panel "5m ago"
// formatter and its companions (dayLabel, dayKey).
//
// These are pure helpers over Date.now() — the test mocks Date.now via
// vi.useFakeTimers / vi.setSystemTime so the boundaries (just-now, minutes,
// hours, days, fallback to locale date) can be checked deterministically.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { relativeTime, dayLabel, dayKey } from '../lib/relativeTime.js'

const NOW = new Date('2026-05-09T12:00:00Z').getTime()

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date(NOW))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('relativeTime', () => {
  it('returns empty string for null/undefined/empty input', () => {
    expect(relativeTime(null)).toBe('')
    expect(relativeTime(undefined)).toBe('')
    expect(relativeTime('')).toBe('')
  })

  it('returns empty string for an unparseable date', () => {
    expect(relativeTime('not-a-date')).toBe('')
  })

  it('returns "just now" for events under 5 seconds old', () => {
    const t = new Date(NOW - 2_000).toISOString() // 2s ago
    expect(relativeTime(t)).toBe('just now')
  })

  it('returns seconds for events between 5 and 60 seconds old', () => {
    const t = new Date(NOW - 30_000).toISOString() // 30s ago
    expect(relativeTime(t)).toBe('30s ago')
  })

  it('returns minutes for events between 1 minute and 1 hour old', () => {
    const t = new Date(NOW - 5 * 60_000).toISOString() // 5m ago
    expect(relativeTime(t)).toBe('5m ago')
  })

  it('returns hours for events between 1 hour and 1 day old', () => {
    const t = new Date(NOW - 3 * 60 * 60_000).toISOString() // 3h ago
    expect(relativeTime(t)).toBe('3h ago')
  })

  it('returns days for events between 1 day and 7 days old', () => {
    const t = new Date(NOW - 3 * 24 * 60 * 60_000).toISOString() // 3d ago
    expect(relativeTime(t)).toBe('3d ago')
  })

  it('falls back to a locale date for events older than 7 days', () => {
    const iso = new Date(NOW - 30 * 24 * 60 * 60_000).toISOString()
    const out = relativeTime(iso)
    // Not one of the relative-token shapes — must be the locale date string.
    expect(out).not.toBe('just now')
    expect(out).not.toMatch(/\b\d+[smhd] ago\b/)
    expect(out.length).toBeGreaterThan(0)
  })
})

describe('dayLabel', () => {
  it('returns "Today" for the same local day', () => {
    const t = new Date(NOW - 60 * 60_000).toISOString() // 1h earlier, same day
    expect(dayLabel(t)).toBe('Today')
  })

  it('returns "Yesterday" for the previous local day', () => {
    const t = new Date(NOW - 24 * 60 * 60_000).toISOString()
    expect(dayLabel(t)).toBe('Yesterday')
  })

  it('returns empty string for null and unparseable input', () => {
    expect(dayLabel(null)).toBe('')
    expect(dayLabel('garbage')).toBe('')
  })
})

describe('dayKey', () => {
  it('returns local YYYY-MM-DD for a valid ISO timestamp', () => {
    // Use a UTC-noon timestamp so any reasonable local zone resolves to the
    // same calendar day — the regex check stays portable across CI zones.
    const key = dayKey('2026-05-09T12:00:00Z')
    expect(key).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })

  it('returns empty string for null and invalid input', () => {
    expect(dayKey(null)).toBe('')
    expect(dayKey('')).toBe('')
    expect(dayKey('not-a-date')).toBe('')
  })
})
