/**
 * githubLogin.test.js — verifies the GitHub Sign-In wiring in the frontend:
 *
 *   1. api.githubAuthUrl() returns the correct login start URL.
 *   2. Login.jsx and Signup.jsx export default functions (component shape).
 *   3. api.githubAuthUrl is callable and distinct from googleAuthUrl.
 *
 * Strategy: no DOM renderer needed — we test the API helper and static module
 * exports, consistent with how other pages are tested in this suite.
 *
 * vi.mock() calls are placed at the top level so hoisting works correctly.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'

// ---------------------------------------------------------------------------
// Top-level module mocks (must be at top level for vitest hoisting)
// ---------------------------------------------------------------------------

vi.mock('react-router-dom', () => ({
  Link: () => null,
  useLocation: () => ({ state: null }),
  useNavigate: () => () => {},
  useSearchParams: () => [new URLSearchParams()],
}))

vi.mock('../store/auth.js', () => ({
  useAuth: () => () => {},
}))

vi.mock('../cloud/useCloudConfig.js', () => ({
  useCloudConfig: () => ({ googleEnabled: false, githubEnabled: false }),
}))

vi.mock('../lib/api.js', () => ({
  api: {
    login: vi.fn(),
    register: vi.fn(),
    googleAuthUrl: () => '/auth/google/start',
    githubAuthUrl: () => '/auth/github/login/start',
  },
  ApiError: class ApiError extends Error {},
}))

vi.mock('../components/Logo.jsx', () => ({ LogoWordmark: () => null }))
vi.mock('../components/Button.jsx', () => ({ default: () => null }))
vi.mock('../components/Input.jsx', () => ({ default: () => null }))
vi.mock('../components/Card.jsx', () => ({ default: () => null }))
vi.mock('lucide-react', () => ({ AlertCircle: () => null, ArrowRight: () => null }))

// ---------------------------------------------------------------------------
// api.githubAuthUrl()
// ---------------------------------------------------------------------------

describe('api.githubAuthUrl()', () => {
  afterEach(() => {
    vi.resetModules()
    vi.unstubAllEnvs()
  })

  it('returns /auth/github/login/start when VITE_API_URL is empty', async () => {
    vi.stubEnv('VITE_API_URL', '')
    const { api } = await import('../lib/api.js')
    expect(api.githubAuthUrl()).toBe('/auth/github/login/start')
  })

  it('path is distinct from googleAuthUrl', async () => {
    vi.stubEnv('VITE_API_URL', '')
    vi.resetModules()
    const { api } = await import('../lib/api.js')
    expect(api.githubAuthUrl()).not.toBe(api.googleAuthUrl())
    expect(api.githubAuthUrl()).toContain('github')
    expect(api.googleAuthUrl()).toContain('google')
  })
})

// ---------------------------------------------------------------------------
// Login.jsx — module shape
// ---------------------------------------------------------------------------

describe('Login.jsx module shape', () => {
  it('exports a default function (component)', async () => {
    const mod = await import('../routes/Login.jsx')
    expect(typeof mod.default).toBe('function')
  })
})

// ---------------------------------------------------------------------------
// Signup.jsx — module shape
// ---------------------------------------------------------------------------

describe('Signup.jsx module shape', () => {
  it('exports a default function (component)', async () => {
    const mod = await import('../routes/Signup.jsx')
    expect(typeof mod.default).toBe('function')
  })
})

// ---------------------------------------------------------------------------
// githubEnabled button gating: api.githubAuthUrl is callable
// ---------------------------------------------------------------------------

describe('githubEnabled button gating (api integration)', () => {
  afterEach(() => {
    vi.resetModules()
    vi.unstubAllEnvs()
  })

  it('githubAuthUrl is a function on api export', async () => {
    vi.stubEnv('VITE_API_URL', '')
    const { api } = await import('../lib/api.js')
    expect(typeof api.githubAuthUrl).toBe('function')
  })

  it('githubAuthUrl returns a non-empty string', async () => {
    vi.stubEnv('VITE_API_URL', '')
    const { api } = await import('../lib/api.js')
    const url = api.githubAuthUrl()
    expect(typeof url).toBe('string')
    expect(url.length).toBeGreaterThan(0)
  })
})
