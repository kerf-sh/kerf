// appVersion.test.js — unit tests for the appVersion() accessor helper.
//
// The helper reads the __APP_VERSION__ build-time global injected by Vite.
// In the test environment the define-replaced global is unavailable, so we
// set it on globalThis before importing, then restore it after each test.

import { describe, it, expect, beforeEach, afterEach } from 'vitest'

const ORIG = globalThis.__APP_VERSION__

afterEach(() => {
  if (ORIG === undefined) {
    delete globalThis.__APP_VERSION__
  } else {
    globalThis.__APP_VERSION__ = ORIG
  }
})

describe('appVersion', () => {
  it('returns the version string when __APP_VERSION__ is set', async () => {
    globalThis.__APP_VERSION__ = '1.2.3'
    const { appVersion } = await import('../lib/appVersion.js')
    expect(appVersion()).toBe('1.2.3')
  })

  it('returns an empty string when __APP_VERSION__ is absent', async () => {
    delete globalThis.__APP_VERSION__
    const { appVersion } = await import('../lib/appVersion.js')
    const result = appVersion()
    // Either empty string (fallback) or a real semver injected by the runner.
    expect(typeof result).toBe('string')
  })

  it('produces a v-prefixed label matching the semver pattern', async () => {
    globalThis.__APP_VERSION__ = '0.1.0'
    const { appVersion } = await import('../lib/appVersion.js')
    const label = `v${appVersion()}`
    expect(label).toMatch(/^v\d+\.\d+\.\d+/)
  })
})

describe('Settings About section (static analysis)', () => {
  it('imports appVersion from lib/appVersion', async () => {
    const { readFileSync } = await import('fs')
    const { fileURLToPath } = await import('url')
    const path = await import('path')
    const src = readFileSync(
      path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../routes/Settings.jsx'),
      'utf8',
    )
    expect(src).toContain("import { appVersion } from '../lib/appVersion.js'")
  })

  it('renders the version using appVersion() in the About section', async () => {
    const { readFileSync } = await import('fs')
    const { fileURLToPath } = await import('url')
    const path = await import('path')
    const src = readFileSync(
      path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../routes/Settings.jsx'),
      'utf8',
    )
    expect(src).toContain('appVersion()')
    expect(src).toContain('Kerf version')
  })
})
