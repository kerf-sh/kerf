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
  // GET /api/workshop/?page=&sort=&tag=
  // `tag` is an optional string or string[] of tag filters; multiple tags
  // are ANDed server-side. Omit for the unfiltered "All" view. Free-form
  // (no enum validation) so any tag the user wrote on a project is valid.
  list({ page = 1, sort = 'newest', tag } = {}) {
    const q = new URLSearchParams()
    if (page) q.set('page', String(page))
    if (sort) q.set('sort', sort)
    const tags = Array.isArray(tag) ? tag : (tag ? [tag] : [])
    for (const t of tags) {
      if (t) q.append('tag', t)
    }
    return request(`/api/workshop/?${q.toString()}`)
  },

  // GET /api/workshop/:slug
  get(slug) {
    return request(`/api/workshop/${encodeURIComponent(slug)}`)
  },

  // POST /api/workshop/publish — owner-only. Idempotent: republishing
  // an already-listed project just updates title/description.
  // `readme` may be a string to supply an explicit README (overrides AI gen).
  // `generateReadme` defaults to true; pass false to skip AI generation.
  publish({ projectId, title, description, readme, generateReadme = true }) {
    return request('/api/workshop/publish', {
      method: 'POST',
      body: {
        project_id: projectId,
        title: title || '',
        description: description || '',
        ...(readme != null ? { readme } : {}),
        generate_readme: generateReadme,
      },
    })
  },

  // POST /api/workshop/regenerate-readme — owner-only. Replaces the stored
  // README with a freshly AI-generated version. Returns {project_id, readme,
  // readme_generated_at}.
  regenerateReadme(projectId) {
    return request('/api/workshop/regenerate-readme', {
      method: 'POST',
      body: { project_id: projectId },
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

  // GET /api/library/parts/:slug — single Part detail row. Phase 3 of the
  // Library split ships the route + frontend; the backend handler arrives
  // in Phase 4. Until then this 404s and the `/library/:slug` route
  // surfaces a "Part not found" empty state. The detail row is expected
  // to be a superset of the listParts() row shape: same fields plus the
  // parsed JSON `content` (description, datasheet_url, photos[],
  // distributors[]) and the source project's slug for "view in workshop".
  getPart(slug) {
    return request(`/api/library/parts/${encodeURIComponent(slug)}`)
  },

  // POST /api/library/submissions — manufacturer-PR submission flow
  // (Library Phase 3, ROADMAP row 73). Auth required (any role). The row
  // lands in library_part_submissions.status='pending' and surfaces on the
  // admin queue at /api/admin/library/submissions. `targetWorkspaceSlug`
  // names the curated Library workspace the contribution targets (e.g.
  // 'kerf-system'); `payload` is a Part-shape JSON object with at minimum
  // {name, manufacturer, mpn, category, description}. Returns {id} on 201.
  submitPart({ targetWorkspaceSlug, payload }) {
    return request('/api/library/submissions', {
      method: 'POST',
      body: {
        target_workspace_slug: targetWorkspaceSlug,
        payload,
      },
    })
  },

  /** POST /api/projects/:pid/files/:fid/derived — derived-artifacts cache lookup
   *  (ROADMAP row 67 Phase 2). Returns {cached, derivedKind, payload, error?}
   *  where payload is a Uint8Array on hit, null otherwise. A 501 response is
   *  the documented "compile-on-demand-not-yet-wired" miss and is mapped to
   *  {cached:false, ...} (NOT thrown) so callers can fall through. Other
   *  failures (network/auth/4xx) throw an ApiError. */
  async lookupDerivedArtifact({ projectId, fileId, derivedKind }) {
    let body
    try {
      body = await request(
        `/api/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(fileId)}/derived`,
        { method: 'POST', body: { derived_kind: derivedKind } },
      )
    } catch (err) {
      if (err instanceof ApiError && err.status === 501) {
        return { cached: false, derivedKind, payload: null, error: err.message }
      }
      throw err
    }
    const cached = !!(body && body.cached)
    const kind = (body && body.derived_kind) || derivedKind
    let payload = null
    if (cached && body && typeof body.payload_b64 === 'string' && body.payload_b64) {
      try {
        const bin = atob(body.payload_b64)
        const arr = new Uint8Array(bin.length)
        for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i)
        payload = arr
      } catch {
        return { cached: false, derivedKind: kind, payload: null, error: 'invalid base64' }
      }
    }
    return { cached: cached && payload != null, derivedKind: kind, payload }
  },

  /** POST /api/projects/:pid/files/:fid/derived/store — derived-artifacts
   *  cache populate (ROADMAP row 67 Phase 2, write-back half). Pairs with
   *  `lookupDerivedArtifact`: after a successful local recompile of a
   *  cross-project source, callers fire-and-forget this helper so the next
   *  consumer skips the recompile cost. `payload` is a Uint8Array (raw
   *  encoded artifact bytes); we base64-encode it inline. The backend caps
   *  decoded payloads at 16 MiB and returns {stored:true, derived_kind,
   *  payload_size_bytes} on 200; non-200s throw ApiError so the caller's
   *  fire-and-forget try/catch can swallow them. */
  async storeDerivedArtifact({ projectId, fileId, derivedKind, payload }) {
    if (!(payload instanceof Uint8Array)) {
      throw new TypeError('storeDerivedArtifact: payload must be a Uint8Array')
    }
    let payloadB64
    if (typeof Buffer !== 'undefined') {
      payloadB64 = Buffer.from(payload).toString('base64')
    } else {
      // Browser path: btoa over the byte string. Chunk to avoid blowing the
      // call stack on multi-MB payloads (apply()'s arg limit is ~64k on V8).
      let bin = ''
      const CHUNK = 0x8000
      for (let i = 0; i < payload.length; i += CHUNK) {
        bin += String.fromCharCode.apply(null, payload.subarray(i, i + CHUNK))
      }
      payloadB64 = btoa(bin)
    }
    const body = await request(
      `/api/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(fileId)}/derived/store`,
      { method: 'POST', body: { derived_kind: derivedKind, payload_b64: payloadB64 } },
    )
    return {
      stored: !!(body && body.stored),
      payloadSize: (body && Number(body.payload_size_bytes)) || 0,
    }
  },

  /** GET /api/projects/:pid/files/:fid/diff?against=<rev> — returns component count
   *  delta + BOM total delta vs a revision (or the immediately preceding one if
   *  the rev id is omitted). Used by the assembly editor's 'out of date' chip
   *  tooltip (ROADMAP row 68 Phase 3). Returns { componentsAdded, componentsRemoved,
   *  componentsDelta, bomTotalDeltaUsd, against } — re-cased from the snake_case
   *  backend payload. Throws ApiError on non-200. */
  async diffFile({ projectId, fileId, against }) {
    const qs = against ? `?against=${encodeURIComponent(against)}` : ''
    const body = await request(
      `/api/projects/${encodeURIComponent(projectId)}/files/${encodeURIComponent(fileId)}/diff${qs}`,
    )
    return {
      componentsAdded: (body && body.components_added) || 0,
      componentsRemoved: (body && body.components_removed) || 0,
      componentsDelta: (body && body.components_delta) || 0,
      bomTotalDeltaUsd: body && body.bom_total_delta_usd != null ? Number(body.bom_total_delta_usd) : null,
      against: (body && body.against) || null,
    }
  },
}

// ---- Admin: Library submissions queue ----
// Library Phase 3 (ROADMAP row 73). All routes require account_role='admin'
// or 'system' — the backend re-checks on every endpoint, the frontend just
// uses these helpers behind the AdminPublishers-style gate.
export const adminLibrary = {
  // GET /api/admin/library/submissions?status=pending&page=&page_size=
  // → { submissions: [...], page, page_size, has_more }
  listSubmissions: ({ status = 'pending', page = 1, pageSize } = {}) => {
    const q = new URLSearchParams()
    if (status) q.set('status', status)
    if (page) q.set('page', String(page))
    if (pageSize) q.set('page_size', String(pageSize))
    const qs = q.toString()
    return request(`/api/admin/library/submissions${qs ? `?${qs}` : ''}`)
  },

  // PUT /api/admin/library/submissions/:id { action, review_note }
  // action ∈ 'approve'|'reject'. On approve, the payload is copied as a new
  // kind='part' file in the target workspace's library project.
  reviewSubmission: (id, { action, reviewNote }) =>
    request(`/api/admin/library/submissions/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: { action, review_note: reviewNote || '' },
    }),
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

  // ---- T-146 provider mirror endpoints ----

  // GET /git/providers
  // → { providers: [{ id, name, label, icon_url? }] }
  // Only returns providers the server has env-credentials for.
  listProviders: () =>
    request('/api/git/providers'),

  // GET /projects/:pid/git/provider/status
  // → { connected, provider_id?, remote_url?, kerf_git_retained, note, last_sync_at? }
  providerStatus: (projectId) =>
    request(`/api/projects/${encodeURIComponent(projectId)}/git/provider/status`),

  // POST /projects/:pid/git/provider/connect
  // body: { provider_id, remote_url }
  // → { connected: true, provider_id, remote_url, kerf_git_retained, note }
  providerConnect: (projectId, providerId, remoteUrl) =>
    request(
      `/api/projects/${encodeURIComponent(projectId)}/git/provider/connect`,
      { method: 'POST', body: { provider_id: providerId, remote_url: remoteUrl } },
    ),

  // POST /projects/:pid/git/provider/disconnect
  // → { connected: false, kerf_git_retained: true, note }
  providerDisconnect: (projectId) =>
    request(
      `/api/projects/${encodeURIComponent(projectId)}/git/provider/disconnect`,
      { method: 'POST' },
    ),
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
