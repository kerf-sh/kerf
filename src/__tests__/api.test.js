// api.test.js — coverage for the REST client in src/lib/api.js.
//
// Strategy:
//   - Mock `useAuth` so the request() helper sees a deterministic token state.
//   - Mock global.fetch with vi.fn so we can capture the URL + init + body
//     each call site builds, plus stub Response objects to drive the
//     happy path / 401-refresh path / error path.
//   - We exercise URL builders (the meatiest behavioural surface) and the
//     ApiError class. We deliberately don't exercise the chunked upload path
//     here — it deserves its own slice if it ever gets coverage, and the
//     ROI on testing the SHA-256 + worklist plumbing inside this slice is
//     too low.

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// Mutable mock state for the auth store; we re-assign per-test via setState().
const authState = {
  accessToken: 'tok-A',
  refreshToken: 'r-A',
  setSession: vi.fn(),
  logout: vi.fn(),
}

vi.mock('../store/auth.js', () => ({
  useAuth: {
    getState: () => authState,
  },
}))

let api
let ApiError
// Whatever VITE_API_URL is set to in the test runner — api.js prefixes every
// path with it. We detect it dynamically from the first fetch call so the
// suite stays portable across env files.
const API_URL = import.meta.env.VITE_API_URL || ''

beforeEach(async () => {
  // Reset module cache so the in-flight `refreshing` promise from a prior
  // test never leaks.
  vi.resetModules()
  authState.accessToken = 'tok-A'
  authState.refreshToken = 'r-A'
  authState.setSession = vi.fn()
  authState.logout = vi.fn()
  globalThis.fetch = vi.fn()
  const mod = await import('../lib/api.js')
  api = mod.api
  ApiError = mod.ApiError
})

afterEach(() => {
  vi.restoreAllMocks()
  delete globalThis.fetch
})

function jsonRes(body, { status = 200 } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: 'OK',
    json: async () => body,
    text: async () => JSON.stringify(body),
    arrayBuffer: async () => new ArrayBuffer(8),
  }
}

function errRes(status, payload) {
  const text = typeof payload === 'string' ? payload : JSON.stringify(payload)
  return {
    ok: false,
    status,
    statusText: 'Error',
    json: async () => (typeof payload === 'string' ? null : payload),
    text: async () => text,
  }
}

describe('ApiError', () => {
  it('captures status and message', () => {
    const err = new ApiError(403, 'forbidden')
    expect(err).toBeInstanceOf(Error)
    expect(err.status).toBe(403)
    expect(err.message).toBe('forbidden')
  })
})

describe('URL builders + request shape', () => {
  it('login posts JSON to /auth/login with no auth header', async () => {
    fetch.mockResolvedValueOnce(jsonRes({ access_token: 't', user: { id: 'u1' } }))
    await api.login('alice@example.com', 'secret')
    expect(fetch).toHaveBeenCalledTimes(1)
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe(`${API_URL}/auth/login`)
    expect(init.method).toBe('POST')
    expect(init.headers.authorization).toBeUndefined()
    expect(JSON.parse(init.body)).toEqual({ email: 'alice@example.com', password: 'secret' })
  })

  it('me sends a Bearer token from the auth store', async () => {
    fetch.mockResolvedValueOnce(jsonRes({ id: 'u1' }))
    await api.me()
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe(`${API_URL}/api/me`)
    expect(init.headers.authorization).toBe('Bearer tok-A')
  })

  it('googleAuthUrl is a synchronous URL (no fetch)', () => {
    expect(api.googleAuthUrl()).toBe(`${API_URL}/auth/google/start`)
    expect(fetch).not.toHaveBeenCalled()
  })

  it('listProjects appends a single tag query param', async () => {
    fetch.mockResolvedValueOnce(jsonRes([]))
    await api.listProjects('ws-1', { tag: 'fixture' })
    const [url] = fetch.mock.calls[0]
    expect(url).toBe(`${API_URL}/api/projects?workspace_id=ws-1&tag=fixture`)
  })

  it('listProjects ANDs multiple tag filters by repeating the param', async () => {
    fetch.mockResolvedValueOnce(jsonRes([]))
    await api.listProjects(null, { tag: ['a', 'b'] })
    const [url] = fetch.mock.calls[0]
    // No workspace_id, two `tag=` params (in order).
    expect(url).toBe(`${API_URL}/api/projects?tag=a&tag=b`)
  })

  it('listProjects with no opts hits the bare endpoint', async () => {
    fetch.mockResolvedValueOnce(jsonRes([]))
    await api.listProjects()
    expect(fetch.mock.calls[0][0]).toBe(`${API_URL}/api/projects`)
  })

  it('createProject accepts a positional (name, description) shape', async () => {
    fetch.mockResolvedValueOnce(jsonRes({ id: 'p1' }))
    await api.createProject('hello', 'world')
    const [, init] = fetch.mock.calls[0]
    expect(JSON.parse(init.body)).toEqual({ name: 'hello', description: 'world' })
  })

  it('createProject accepts a body-object shape verbatim', async () => {
    fetch.mockResolvedValueOnce(jsonRes({ id: 'p1' }))
    await api.createProject({ workspace_id: 'w', name: 'n', tags: ['t1'] })
    const [, init] = fetch.mock.calls[0]
    expect(JSON.parse(init.body)).toEqual({ workspace_id: 'w', name: 'n', tags: ['t1'] })
  })

  it('encodes workspace slugs in path params', async () => {
    fetch.mockResolvedValueOnce(jsonRes({}))
    await api.getWorkspace('ws/with space')
    expect(fetch.mock.calls[0][0]).toBe(`${API_URL}/api/workspaces/ws%2Fwith%20space`)
  })

  it('inviteWorkspaceMember POSTs to the correct nested URL', async () => {
    fetch.mockResolvedValueOnce(jsonRes({}))
    await api.inviteWorkspaceMember('acme', 'bob@x.com', 'editor')
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe(`${API_URL}/api/workspaces/acme/members`)
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual({ email: 'bob@x.com', role: 'editor' })
  })

  it('getActivity falls back to limit=50 when omitted and skips before= when null', async () => {
    fetch.mockResolvedValueOnce(jsonRes({ events: [] }))
    await api.getActivity('p1')
    expect(fetch.mock.calls[0][0]).toBe(`${API_URL}/api/projects/p1/activity?limit=50`)
  })

  it('getActivity URL-encodes the before cursor', async () => {
    fetch.mockResolvedValueOnce(jsonRes({ events: [] }))
    await api.getActivity('p1', '2026-05-09T12:00:00Z', 25)
    expect(fetch.mock.calls[0][0]).toBe(`${API_URL}/api/projects/p1/activity?limit=25&before=2026-05-09T12%3A00%3A00Z`)
  })

  it('admin.listPublishers builds a multi-key query string', async () => {
    fetch.mockResolvedValueOnce(jsonRes({ publishers: [] }))
    await api.admin.listPublishers({ search: 'a&b', verifiedOnly: true, cursor: 'cur', limit: 20 })
    expect(fetch.mock.calls[0][0]).toBe(
      `${API_URL}/api/admin/publishers?search=a%26b&verified_only=true&cursor=cur&limit=20`,
    )
  })

  it('deleteMe encodes the confirm marker into the query string', async () => {
    fetch.mockResolvedValueOnce({ ok: true, status: 204, statusText: 'No Content' })
    const res = await api.deleteMe()
    expect(fetch.mock.calls[0][0]).toBe(`${API_URL}/api/me?confirm=DELETE`)
    expect(fetch.mock.calls[0][1].method).toBe('DELETE')
    // 204 → null per request()'s contract.
    expect(res).toBeNull()
  })
})

describe('error mapping', () => {
  it('throws ApiError with the JSON-decoded `error` field', async () => {
    fetch.mockResolvedValueOnce(errRes(409, { error: 'project name taken' }))
    await expect(api.createProject('dup')).rejects.toMatchObject({
      status: 409,
      message: 'project name taken',
    })
  })

  it('falls back to raw text body when the response is not JSON', async () => {
    fetch.mockResolvedValueOnce(errRes(500, 'boom'))
    await expect(api.me()).rejects.toMatchObject({ status: 500, message: 'boom' })
  })
})

describe('401 refresh flow', () => {
  it('refreshes the access token and retries the request once', async () => {
    // 1st call: 401. 2nd call: refresh → 200 + new tokens. 3rd call: retry → 200.
    fetch
      .mockResolvedValueOnce(errRes(401, 'expired'))
      .mockResolvedValueOnce(jsonRes({ access_token: 'tok-B', refresh_token: 'r-B', user: { id: 'u1' } }))
      .mockResolvedValueOnce(jsonRes({ id: 'u1', name: 'me' }))
    const me = await api.me()
    expect(me).toEqual({ id: 'u1', name: 'me' })
    expect(fetch).toHaveBeenCalledTimes(3)
    expect(fetch.mock.calls[1][0]).toBe(`${API_URL}/auth/refresh`)
    expect(authState.setSession).toHaveBeenCalledWith({
      accessToken: 'tok-B',
      refreshToken: 'r-B',
      user: { id: 'u1' },
    })
    // The retry uses the new token.
    expect(fetch.mock.calls[2][1].headers.authorization).toBe('Bearer tok-B')
  })

  it('logs out + bubbles the original 401 when refresh itself fails', async () => {
    fetch
      .mockResolvedValueOnce(errRes(401, 'expired'))
      .mockResolvedValueOnce(errRes(403, 'no refresh'))
    await expect(api.me()).rejects.toMatchObject({ status: 401 })
    expect(authState.logout).toHaveBeenCalledTimes(1)
  })
})

/* -------------------------------------------------------------------------- */
/* Timeout + network-error surfacing                                          */
/* -------------------------------------------------------------------------- */
//
// Regression coverage for the "chat hangs on 'Kerf is thinking…' forever"
// bug. The fetch helper now aborts after CHAT_TIMEOUT_MS for sendMessage and
// DEFAULT_TIMEOUT_MS for everything else, and converts the AbortError /
// generic TypeError into an ApiError(status=0) so the chat UI can render a
// "Try again" alert instead of spinning indefinitely.

describe('request timeouts', () => {
  it('aborts the fetch when it does not resolve within timeoutMs', async () => {
    // Simulate a fetch that resolves only when its AbortSignal fires.
    fetch.mockImplementationOnce((url, init) => {
      return new Promise((_resolve, reject) => {
        init.signal.addEventListener('abort', () => {
          const e = new Error('aborted')
          e.name = 'AbortError'
          reject(e)
        })
      })
    })
    vi.useFakeTimers()
    try {
      // Attach a catch handler synchronously so the rejection is never
      // un-observed while we advance the fake clock.
      const captured = api
        .sendMessage('p1', 't1', { content: 'hi', part_refs: [], model: 'm1' })
        .then((v) => ({ ok: true, v }), (e) => ({ ok: false, e }))
      // The bug case was: fetch never resolves, no timeout, sending: true forever.
      // CHAT_TIMEOUT_MS is 180_000ms. Advancing past it should reject.
      await vi.advanceTimersByTimeAsync(180_001)
      const result = await captured
      expect(result.ok).toBe(false)
      expect(result.e).toMatchObject({
        status: 0,
        message: expect.stringMatching(/timed out/i),
      })
    } finally {
      vi.useRealTimers()
    }
  })

  it('passes an AbortSignal to fetch when timeoutMs > 0', async () => {
    fetch.mockResolvedValueOnce(jsonRes({ id: 'u1' }))
    await api.me()
    const init = fetch.mock.calls[0][1]
    expect(init.signal).toBeInstanceOf(AbortSignal)
  })

  it('surfaces a generic network error as ApiError(0)', async () => {
    fetch.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(api.me()).rejects.toMatchObject({
      status: 0,
      message: expect.stringMatching(/Failed to fetch|Network error/i),
    })
  })

  it('default timeout still applies to non-chat calls (≈60s)', async () => {
    fetch.mockImplementationOnce((url, init) => {
      return new Promise((_resolve, reject) => {
        init.signal.addEventListener('abort', () => {
          const e = new Error('aborted')
          e.name = 'AbortError'
          reject(e)
        })
      })
    })
    vi.useFakeTimers()
    try {
      const captured = api.me().then((v) => ({ ok: true, v }), (e) => ({ ok: false, e }))
      await vi.advanceTimersByTimeAsync(60_001)
      const result = await captured
      expect(result.ok).toBe(false)
      expect(result.e).toMatchObject({ status: 0, message: /timed out/i })
    } finally {
      vi.useRealTimers()
    }
  })
})
