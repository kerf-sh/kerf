// useCloudConfig.test.js — verifies the /api/config consumer surfaces
// OAuth availability fields (googleEnabled, githubEnabled, githubClientId)
// from the runtime response, and that secrets are never present.
//
// Strategy:
//   - Mock global.fetch to return a controlled JSON payload.
//   - Import the store module fresh per test via vi.resetModules() so the
//     singleton state doesn't bleed between cases.
//   - Exercise both the "server has new flags" path and the backwards-compat
//     "older server binary, flags absent" path.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

async function freshStore() {
  vi.resetModules()
  const mod = await import('../cloud/useCloudConfig.js')
  return mod
}

function mockConfigFetch(payload, { status = 200 } = {}) {
  globalThis.fetch = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  })
}

beforeEach(() => {
  // Hermetic: a developer's local .env may define VITE_GOOGLE_CLIENT_ID,
  // which feeds the build-time googleEnabled fallback. Stub it empty so
  // googleEnabled is driven solely by the mocked /api/config payload
  // (matching CI, where no real client id is present).
  vi.stubEnv('VITE_GOOGLE_CLIENT_ID', '')
  // Each test supplies its own fetch mock.
  globalThis.fetch = vi.fn()
})

afterEach(() => {
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
  delete globalThis.fetch
})

describe('/api/config OAuth fields — full server response', () => {
  it('googleEnabled is true when google_enabled=true in response', async () => {
    mockConfigFetch({
      cloud_enabled: true,
      local_mode: false,
      google_client_id: 'goog-abc.apps.googleusercontent.com',
      google_enabled: true,
      github_enabled: false,
      github_client_id: '',
    })
    const { getCloudConfig } = await freshStore()
    await getCloudConfig().fetch()
    const s = getCloudConfig()
    expect(s.googleEnabled).toBe(true)
    expect(s.googleClientId).toBe('goog-abc.apps.googleusercontent.com')
  })

  it('googleEnabled is false when google_enabled=false in response', async () => {
    mockConfigFetch({
      cloud_enabled: true,
      local_mode: false,
      google_client_id: '',
      google_enabled: false,
      github_enabled: false,
      github_client_id: '',
    })
    const { getCloudConfig } = await freshStore()
    await getCloudConfig().fetch()
    const s = getCloudConfig()
    expect(s.googleEnabled).toBe(false)
    expect(s.googleClientId).toBe('')
  })

  it('githubEnabled is true when github_enabled=true in response', async () => {
    mockConfigFetch({
      cloud_enabled: true,
      local_mode: false,
      google_enabled: false,
      github_enabled: true,
      github_client_id: 'Iv1.github-client-id',
    })
    const { getCloudConfig } = await freshStore()
    await getCloudConfig().fetch()
    const s = getCloudConfig()
    expect(s.githubEnabled).toBe(true)
    expect(s.githubClientId).toBe('Iv1.github-client-id')
  })

  it('githubEnabled is false when github_enabled=false', async () => {
    mockConfigFetch({
      cloud_enabled: false,
      local_mode: true,
      github_enabled: false,
      github_client_id: '',
    })
    const { getCloudConfig } = await freshStore()
    await getCloudConfig().fetch()
    const s = getCloudConfig()
    expect(s.githubEnabled).toBe(false)
    expect(s.githubClientId).toBe('')
  })

  it('response never carries a client secret field', async () => {
    // The response we parse should not propagate any secret-named key into
    // the store. We verify by checking none of these keys land on the store.
    mockConfigFetch({
      cloud_enabled: true,
      local_mode: false,
      google_client_id: 'goog-abc.apps.googleusercontent.com',
      google_enabled: true,
      google_client_secret: 'SHOULD_NOT_APPEAR',
      github_enabled: true,
      github_client_id: 'Iv1.abc',
      github_client_secret: 'SHOULD_NOT_APPEAR',
    })
    const { getCloudConfig } = await freshStore()
    await getCloudConfig().fetch()
    const s = getCloudConfig()
    expect(s).not.toHaveProperty('google_client_secret')
    expect(s).not.toHaveProperty('googleClientSecret')
    expect(s).not.toHaveProperty('github_client_secret')
    expect(s).not.toHaveProperty('githubClientSecret')
  })

  it('existing fields (cloudEnabled, localMode, paystackPublicKey) are unchanged', async () => {
    mockConfigFetch({
      cloud_enabled: true,
      local_mode: false,
      google_enabled: false,
      github_enabled: false,
      paystack_public_key: 'pk_test_abc',
    })
    const { getCloudConfig } = await freshStore()
    await getCloudConfig().fetch()
    const s = getCloudConfig()
    expect(s.cloudEnabled).toBe(true)
    expect(s.localMode).toBe(false)
    expect(s.paystackPublicKey).toBe('pk_test_abc')
    expect(s.ready).toBe(true)
  })
})

describe('/api/config OAuth fields — backwards-compat (older server)', () => {
  it('googleEnabled falls back to whether google_client_id is non-empty', async () => {
    // Older binary: no google_enabled / github_enabled fields in response.
    mockConfigFetch({
      cloud_enabled: true,
      local_mode: false,
      google_client_id: 'goog-abc.apps.googleusercontent.com',
    })
    const { getCloudConfig } = await freshStore()
    await getCloudConfig().fetch()
    const s = getCloudConfig()
    // Falls back to !!googleClientId
    expect(s.googleEnabled).toBe(true)
    expect(s.githubEnabled).toBe(false)
  })

  it('googleEnabled is false when google_client_id absent in older response', async () => {
    mockConfigFetch({
      cloud_enabled: false,
      local_mode: true,
    })
    const { getCloudConfig } = await freshStore()
    await getCloudConfig().fetch()
    const s = getCloudConfig()
    expect(s.googleEnabled).toBe(false)
    expect(s.githubEnabled).toBe(false)
  })
})

describe('/api/config failure handling', () => {
  it('resets to OSS defaults (googleEnabled=false, githubEnabled=false) on fetch error', async () => {
    globalThis.fetch = vi.fn().mockRejectedValue(new Error('network error'))
    const { getCloudConfig } = await freshStore()
    await getCloudConfig().fetch()
    const s = getCloudConfig()
    expect(s.ready).toBe(true)
    expect(s.googleEnabled).toBe(false)
    expect(s.githubEnabled).toBe(false)
    expect(s.cloudEnabled).toBe(false)
  })
})
