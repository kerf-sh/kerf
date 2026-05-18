// Slice 8 (frontend): password-reset + verification API wiring and the
// soft unverified banner. @testing-library/react isn't available here
// (see freecadImport.test.jsx), so this pins the fetch contract + the
// route/banner wiring at the source level.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const read = (p) => readFileSync(join(root, p), 'utf8')

describe('auth email API client', () => {
  let api, lastFetch

  beforeEach(async () => {
    vi.resetModules()
    lastFetch = vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok' }),
    }))
    globalThis.fetch = lastFetch
    api = (await import('../lib/api.js')).api
  })

  afterEach(() => {
    vi.restoreAllMocks()
    delete globalThis.fetch
  })

  function call() {
    const [url, init] = lastFetch.mock.calls[0]
    return { url, init, body: init.body ? JSON.parse(init.body) : null }
  }

  it('forgotPassword POSTs the email, no auth', async () => {
    await api.forgotPassword('a@b.com')
    const { url, init, body } = call()
    expect(url).toContain('/auth/forgot-password')
    expect(init.method).toBe('POST')
    expect(body).toEqual({ email: 'a@b.com' })
  })

  it('resetPassword POSTs token + password', async () => {
    await api.resetPassword('tok123', 'longenough1')
    const { url, init, body } = call()
    expect(url).toContain('/auth/reset-password')
    expect(init.method).toBe('POST')
    expect(body).toEqual({ token: 'tok123', password: 'longenough1' })
  })

  it('requestVerification POSTs to the resend endpoint', async () => {
    await api.requestVerification()
    const { url, init } = call()
    expect(url).toContain('/auth/request-verification')
    expect(init.method).toBe('POST')
  })
})

describe('email UI wiring (source contract)', () => {
  it('App routes /forgot-password and /reset-password publicly', () => {
    const app = read('App.jsx')
    expect(app).toContain('path="/forgot-password"')
    expect(app).toContain('path="/reset-password"')
  })

  it('Layout shows a soft unverified banner gated on email_verified', () => {
    const layout = read('components/Layout.jsx')
    expect(layout).toContain('UnverifiedBanner')
    // Soft: only when explicitly false (OAuth/verified users excluded).
    expect(layout).toContain('user.email_verified !== false')
    expect(layout).toContain('requestVerification')
  })

  it('Login links to the forgot-password page', () => {
    expect(read('routes/Login.jsx')).toContain('to="/forgot-password"')
  })
})
