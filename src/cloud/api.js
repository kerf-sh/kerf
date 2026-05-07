// Billing API helpers for the hosted (cloud) tier.
//
// Mirrors the patterns in src/lib/api.js: same fetch wrapper for bearer auth
// and refresh-on-401, same ApiError shape. We intentionally re-import the
// `request` style logic via a thin wrapper exported alongside `api` instead
// of duplicating the refresh dance — but src/lib/api.js doesn't export
// `request` directly, so we replicate just enough here. If src/lib/api.js
// gains an exported request(), swap to that and delete the local copy.

import { useAuth } from '../store/auth.js'
import { ApiError } from '../lib/api.js'

const API_URL = import.meta.env.VITE_API_URL || ''

let refreshing = null

async function refreshAccessToken() {
  if (refreshing) return refreshing
  const { refreshToken, setSession, logout } = useAuth.getState()
  if (!refreshToken) throw new Error('no refresh token')

  refreshing = (async () => {
    const res = await fetch(`${API_URL}/auth/refresh`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    })
    if (!res.ok) {
      logout()
      throw new Error('refresh failed')
    }
    const data = await res.json()
    setSession({
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
      user: data.user,
    })
    return data.access_token
  })().finally(() => { refreshing = null })

  return refreshing
}

async function request(path, { method = 'GET', body, headers = {}, auth = true } = {}) {
  const url = path.startsWith('http') ? path : `${API_URL}${path}`
  const h = { 'content-type': 'application/json', ...headers }
  if (auth) {
    const token = useAuth.getState().accessToken
    if (token) h.authorization = `Bearer ${token}`
  }
  const send = () => fetch(url, {
    method,
    headers: h,
    body: body == null ? undefined : (typeof body === 'string' ? body : JSON.stringify(body)),
  })

  let res = await send()
  if (res.status === 401 && auth && useAuth.getState().refreshToken) {
    try {
      const newToken = await refreshAccessToken()
      h.authorization = `Bearer ${newToken}`
      res = await send()
    } catch { /* fall through */ }
  }

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    let msg = text
    try { msg = JSON.parse(text).error || text } catch { /* ignore */ }
    throw new ApiError(res.status, msg || res.statusText)
  }
  if (res.status === 204) return null
  return res.json()
}

// GET /api/billing/me
// → { credits_usd, recent_invoices: [...], recent_usage: [...], fx_rate?, fx_quoted_at? }
export function getBillingMe() {
  return request('/api/billing/me')
}

// POST /api/billing/topup
// → { authorization_url, reference, amount_usd, amount_zar, fx_rate }
// Caller is expected to redirect via window.location.assign(authorization_url).
export function topUp(amountUSD) {
  return request('/api/billing/topup', {
    method: 'POST',
    body: { amount_usd: Number(amountUSD) },
  })
}

// GET /api/billing/usage?from=ISO&to=ISO
export function getUsage(from, to) {
  const q = new URLSearchParams()
  if (from) q.set('from', from)
  if (to) q.set('to', to)
  const qs = q.toString()
  return request(`/api/billing/usage${qs ? `?${qs}` : ''}`)
}

// GET /api/billing/pricing — current rate card. Returns { models: [...], storage_usd_per_gb_month }.
// Optional today; PlanSelector falls back to the hardcoded constant if this 404s.
export function getPricing() {
  return request('/api/billing/pricing')
}

// ---- Workshop ----
// All endpoints sit under /api/workshop; the public ones (list/get)
// pass auth=false so the request still works for signed-out visitors.
// The backend uses OptionalAuth on those routes so a logged-in caller
// still sees liked_by_me populated; we keep auth=true here to forward
// the bearer token whenever it's present.

export const workshop = {
  // GET /api/workshop/?page=&sort=&type=
  // `type` is the optional project_type filter ('mechanical' / 'electronics'
  // / 'architecture'). Omit (or pass falsy) for the unfiltered
  // "All" view. The backend validates against the same small enum.
  list({ page = 1, sort = 'newest', type } = {}) {
    const q = new URLSearchParams()
    if (page) q.set('page', String(page))
    if (sort) q.set('sort', sort)
    if (type) q.set('type', type)
    return request(`/api/workshop/?${q.toString()}`)
  },

  // GET /api/workshop/:slug
  get(slug) {
    return request(`/api/workshop/${encodeURIComponent(slug)}`)
  },

  // POST /api/workshop/publish — owner-only. Idempotent: republishing
  // an already-listed project just updates title/description.
  publish({ projectId, title, description }) {
    return request('/api/workshop/publish', {
      method: 'POST',
      body: {
        project_id: projectId,
        title: title || '',
        description: description || '',
      },
    })
  },

  // DELETE /api/workshop/:slug — owner-only.
  unpublish(slug) {
    return request(`/api/workshop/${encodeURIComponent(slug)}`, { method: 'DELETE' })
  },

  // POST /api/workshop/:slug/like — toggles. Returns {liked_by_me, likes_count}.
  toggleLike(slug) {
    return request(`/api/workshop/${encodeURIComponent(slug)}/like`, { method: 'POST' })
  },

  // POST /api/workshop/:slug/fork — clones the listing's project under
  // the caller. Returns {project_id, truncated}.
  fork(slug, projectName) {
    return request(`/api/workshop/${encodeURIComponent(slug)}/fork`, {
      method: 'POST',
      body: projectName ? { project_name: projectName } : {},
    })
  },

  // GET /api/workshop/parts — DEPRECATED alias of library.listParts.
  // Kept around for one release while callers migrate. New code should
  // use library.listParts() instead.
  listParts({ search, category, verifiedOnly } = {}) {
    const q = new URLSearchParams()
    if (search) q.set('search', search)
    if (category) q.set('category', category)
    if (verifiedOnly) q.set('verified_only', 'true')
    const qs = q.toString()
    return request(`/api/workshop/parts${qs ? `?${qs}` : ''}`)
  },
}

// ---- Library ----
// Canonical home for the parts catalog. The Library is the discovery
// surface for individual Parts (M3 screws, 555 timers, etc.) — distinct
// from Workshop, which lists whole projects. Both endpoints share a SQL
// implementation in backend/cloud/workshop/handlers.go, but the Library
// route is the one new callers should use.
//
// Returned shape: { rows: [{ file_id, project_id, slug?, name,
//                            manufacturer?, mpn?, category?,
//                            primary_photo_url?, author }],
//                   limit, total }

export const library = {
  // GET /api/library/parts?search=&category=&verified_only=
  // All filters are optional; an empty payload returns the
  // verified-first, recently-updated head of the catalog (capped at 100).
  listParts({ search, category, verifiedOnly } = {}) {
    const q = new URLSearchParams()
    if (search) q.set('search', search)
    if (category) q.set('category', category)
    if (verifiedOnly) q.set('verified_only', 'true')
    const qs = q.toString()
    return request(`/api/library/parts${qs ? `?${qs}` : ''}`)
  },
}

// ---- Git ----
// All endpoints sit under /api/projects/:pid/git. Auth is required for every
// route. The server-side implementation lives in backend/cloud/git/ — this
// frontend wrapper assumes the contract documented in the cloud roadmap and
// gracefully surfaces 4xx errors to callers via ApiError.
export const git = {
  // POST /init — create an empty repo backing the project. 204 on success.
  init: (projectId) =>
    request(`/api/projects/${projectId}/git/init`, { method: 'POST' }),

  // POST /import — clone an existing GitHub repo into the project. Body:
  // {github_url, branch?}. Private repos require the caller to have linked
  // their GitHub account first (see githubOAuth.startUrl).
  importRepo: (projectId, body) =>
    request(`/api/projects/${projectId}/git/import`, {
      method: 'POST',
      body,
    }),

  // POST /connect — link the project to an existing GitHub repo (no clone).
  // Body: {github_owner, github_repo}.
  connect: (projectId, body) =>
    request(`/api/projects/${projectId}/git/connect`, {
      method: 'POST',
      body,
    }),

  // GET /log?branch=&limit= — newest-first commit list for the given branch.
  log: (projectId, branch, limit = 50) => {
    const q = new URLSearchParams()
    if (branch) q.set('branch', branch)
    if (limit) q.set('limit', String(limit))
    return request(`/api/projects/${projectId}/git/log?${q.toString()}`)
  },

  // GET /branches — [{name, head_sha, is_default}].
  branches: (projectId) =>
    request(`/api/projects/${projectId}/git/branches`),

  // POST /branches {name, from_sha?} — create a new branch at the given
  // commit (or the current HEAD if from_sha is omitted).
  createBranch: (projectId, name, from_sha) =>
    request(`/api/projects/${projectId}/git/branches`, {
      method: 'POST',
      body: from_sha ? { name, from_sha } : { name },
    }),

  // POST /checkout {branch, force?} — switch the working tree. 409 with
  // {has_uncommitted: true} if there are unstaged changes and force≠true.
  checkout: (projectId, branch, force = false) =>
    request(`/api/projects/${projectId}/git/checkout`, {
      method: 'POST',
      body: { branch, force },
    }),

  // POST /commit {message, branch?} — stage all and commit. 201 {sha}.
  commit: (projectId, message, branch) =>
    request(`/api/projects/${projectId}/git/commit`, {
      method: 'POST',
      body: branch ? { message, branch } : { message },
    }),

  // POST /merge {from_branch, into_branch} — fast-forward when possible,
  // 409 {conflicts: [paths]} on conflict.
  merge: (projectId, from_branch, into_branch) =>
    request(`/api/projects/${projectId}/git/merge`, {
      method: 'POST',
      body: { from_branch, into_branch },
    }),

  // POST /push — push every branch to the linked GitHub remote.
  push: (projectId) =>
    request(`/api/projects/${projectId}/git/push`, { method: 'POST' }),

  // POST /pull {branch?} — fetch + fast-forward. 409 {ahead, behind} on
  // diverged history.
  pull: (projectId, branch) =>
    request(`/api/projects/${projectId}/git/pull`, {
      method: 'POST',
      body: branch ? { branch } : {},
    }),

  // GET /diff/:sha — unified diff string. We fetch raw text instead of JSON.
  diff: async (projectId, sha) => {
    const url = `${API_URL}/api/projects/${projectId}/git/diff/${encodeURIComponent(sha)}`
    const token = useAuth.getState().accessToken
    const headers = {}
    if (token) headers.authorization = `Bearer ${token}`
    let res = await fetch(url, { headers })
    if (res.status === 401 && useAuth.getState().refreshToken) {
      try {
        const newToken = await refreshAccessToken()
        headers.authorization = `Bearer ${newToken}`
        res = await fetch(url, { headers })
      } catch { /* fall through */ }
    }
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new ApiError(res.status, text || res.statusText)
    }
    return res.text()
  },

  // DELETE /repo — tear down the repo and clear the link.
  deleteRepo: (projectId) =>
    request(`/api/projects/${projectId}/git/repo`, { method: 'DELETE' }),
}

// GitHub OAuth — top-level (not project-scoped). The start URL is meant to
// be assigned to window.location so the browser follows the 302 to GitHub.
export const githubOAuth = {
  startUrl: (redirect) => {
    const r = redirect || (typeof window !== 'undefined' ? window.location.href : '/')
    return `${API_URL}/auth/github/start?redirect=${encodeURIComponent(r)}`
  },
  unlink: () => request('/auth/github', { method: 'DELETE' }),
}

// ---- Admin: transactional email ----
// Mirrors the shape of api.admin.* in src/lib/api.js but lives here
// because the backend endpoints are cloud-only (built behind the
// `cloud` Go build tag). All routes require account_role='admin'.
export const adminEmail = {
  // GET /api/admin/email/providers
  // → { providers: [{provider, enabled, has_secret, rate_limit_per_minute,
  //                  last_used_at?, updated_at, active}], active }
  listProviders: () => request('/api/admin/email/providers'),

  // PUT /api/admin/email/providers/:provider
  // body: { enabled, rate_limit_per_minute, secret: { api_key?, from_email,
  //          from_name?, region?, smtp_host?, smtp_port?, smtp_username?,
  //          smtp_password? } }
  upsertProvider: (provider, payload) =>
    request(`/api/admin/email/providers/${encodeURIComponent(provider)}`, {
      method: 'PUT',
      body: payload,
    }),

  // DELETE /api/admin/email/providers/:provider — idempotent.
  deleteProvider: (provider) =>
    request(`/api/admin/email/providers/${encodeURIComponent(provider)}`, {
      method: 'DELETE',
    }),

  // POST /api/admin/email/test  { to, template, vars? }
  // Renders + enqueues a single send. Returns { status: "queued" }.
  testSend: ({ to, template, vars }) =>
    request('/api/admin/email/test', {
      method: 'POST',
      body: { to, template, vars: vars || {} },
    }),

  // GET /api/admin/email/log?limit=50&before=<iso>
  // → { entries: [{id, user_id?, template, to_email, provider?, status,
  //                error?, sent_at?, created_at}] }
  log: ({ limit = 50, before } = {}) => {
    const q = new URLSearchParams()
    if (limit) q.set('limit', String(limit))
    if (before) q.set('before', before)
    return request(`/api/admin/email/log?${q.toString()}`)
  },
}
