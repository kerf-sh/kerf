import { useAuth } from '../store/auth.js'

const API_URL = import.meta.env.VITE_API_URL || ''

// Single in-flight refresh promise to coalesce concurrent 401s.
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

async function request(path, { method = 'GET', body, headers = {}, auth = true, raw = false } = {}) {
  const url = path.startsWith('http') ? path : `${API_URL}${path}`
  const h = { 'content-type': 'application/json', ...headers }
  if (auth) {
    const token = useAuth.getState().accessToken
    if (token) h.authorization = `Bearer ${token}`
  }
  let res = await fetch(url, {
    method,
    headers: h,
    body: body == null ? undefined : (typeof body === 'string' ? body : JSON.stringify(body)),
  })

  if (res.status === 401 && auth && useAuth.getState().refreshToken) {
    try {
      const newToken = await refreshAccessToken()
      h.authorization = `Bearer ${newToken}`
      res = await fetch(url, {
        method,
        headers: h,
        body: body == null ? undefined : (typeof body === 'string' ? body : JSON.stringify(body)),
      })
    } catch {
      // fall through to error below
    }
  }

  if (raw) return res
  if (!res.ok) {
    const text = await res.text()
    let msg = text
    try { msg = JSON.parse(text).error || text } catch { /* ignore */ }
    throw new ApiError(res.status, msg || res.statusText)
  }
  if (res.status === 204) return null
  return res.json()
}

export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status }
}

export const api = {
  // ---- Auth ----
  register: (email, password, name) =>
    request('/auth/register', { method: 'POST', body: { email, password, name }, auth: false }),
  login: (email, password) =>
    request('/auth/login', { method: 'POST', body: { email, password }, auth: false }),
  googleAuthUrl: () => `${API_URL}/auth/google/start`,
  refresh: () => refreshAccessToken(),
  me: () => request('/api/me'),
  updateMe: (patch) => request('/api/me', { method: 'PATCH', body: patch }),
  changePassword: (current_password, new_password) =>
    request('/api/me/password', { method: 'POST', body: { current_password, new_password } }),
  deleteMe: () => request('/api/me?confirm=DELETE', { method: 'DELETE' }),
  logout: () => {
    const { refreshToken, logout } = useAuth.getState()
    logout()
    if (refreshToken) {
      return request('/auth/logout', { method: 'POST', body: { refresh_token: refreshToken }, auth: false }).catch(() => {})
    }
  },

  // ---- Workspaces ----
  listWorkspaces: () => request('/api/workspaces'),
  getWorkspace: (slug) => request(`/api/workspaces/${encodeURIComponent(slug)}`),
  createWorkspace: (body) => request('/api/workspaces', { method: 'POST', body }),
  updateWorkspace: (slug, patch) =>
    request(`/api/workspaces/${encodeURIComponent(slug)}`, { method: 'PATCH', body: patch }),
  deleteWorkspace: (slug) =>
    request(`/api/workspaces/${encodeURIComponent(slug)}`, { method: 'DELETE' }),
  inviteWorkspaceMember: (slug, email, role) =>
    request(`/api/workspaces/${encodeURIComponent(slug)}/members`, { method: 'POST', body: { email, role } }),
  removeWorkspaceMember: (slug, userId) =>
    request(`/api/workspaces/${encodeURIComponent(slug)}/members/${encodeURIComponent(userId)}`, { method: 'DELETE' }),
  changeWorkspaceMemberRole: (slug, userId, role) =>
    request(`/api/workspaces/${encodeURIComponent(slug)}/members/${encodeURIComponent(userId)}`, { method: 'PATCH', body: { role } }),
  uploadWorkspaceAvatar: async (slug, blob) => {
    const fd = new FormData()
    const name = (blob && blob.name) || 'avatar.png'
    fd.append('file', blob, name)
    const url = `${API_URL}/api/workspaces/${encodeURIComponent(slug)}/avatar`
    const token = useAuth.getState().accessToken
    const headers = {}
    if (token) headers.authorization = `Bearer ${token}`
    let res = await fetch(url, { method: 'POST', headers, body: fd })
    if (res.status === 401 && useAuth.getState().refreshToken) {
      try {
        const newToken = await refreshAccessToken()
        headers.authorization = `Bearer ${newToken}`
        res = await fetch(url, { method: 'POST', headers, body: fd })
      } catch { /* fall through */ }
    }
    if (!res.ok) {
      const text = await res.text()
      let msg = text
      try { msg = JSON.parse(text).error || text } catch { /* ignore */ }
      throw new ApiError(res.status, msg || res.statusText)
    }
    return res.json()
  },
  deleteWorkspaceAvatar: (slug) =>
    request(`/api/workspaces/${encodeURIComponent(slug)}/avatar`, { method: 'DELETE' }),

  // ---- Projects ----
  // listProjects(workspaceId, { tag })
  // - workspaceId: optional. When set, scopes the listing to that workspace.
  // - tag: optional string or string[] of tag filters; multiple tags are
  //   ANDed server-side (every tag must be present on the row).
  listProjects: (workspaceId, opts = {}) => {
    const q = new URLSearchParams()
    if (workspaceId) q.set('workspace_id', workspaceId)
    const tags = Array.isArray(opts.tag) ? opts.tag : (opts.tag ? [opts.tag] : [])
    for (const t of tags) {
      if (t) q.append('tag', t)
    }
    const qs = q.toString()
    return request(`/api/projects${qs ? `?${qs}` : ''}`)
  },
  // createProject — body is `{ workspace_id, name, description, tags?, starter? }`.
  // - tags: array of free-form strings; the backend trims+dedupes.
  // - starter: "jscad" | "circuit" | "blank"; defaults to "jscad" server-side.
  // Old (name, description) positional shape is still accepted for
  // back-compat — the workspace store fills workspace_id when it's missing.
  createProject: (nameOrBody, description) => {
    if (nameOrBody && typeof nameOrBody === 'object') {
      return request('/api/projects', { method: 'POST', body: nameOrBody })
    }
    const body = { name: nameOrBody, description }
    return request('/api/projects', { method: 'POST', body })
  },
  getProject: (id) => request(`/api/projects/${id}`),
  updateProject: (id, patch) =>
    request(`/api/projects/${id}`, { method: 'PATCH', body: patch }),
  deleteProject: (id) =>
    request(`/api/projects/${id}`, { method: 'DELETE' }),

  // Upload a JPEG thumbnail rendered client-side. Multipart, so we
  // bypass the JSON request() helper.
  uploadProjectThumbnail: async (projectId, blob) => {
    const fd = new FormData()
    fd.append('file', blob, 'thumbnail.jpg')
    const url = `${API_URL}/api/projects/${projectId}/thumbnail`
    const token = useAuth.getState().accessToken
    const headers = {}
    if (token) headers.authorization = `Bearer ${token}`
    let res = await fetch(url, { method: 'POST', headers, body: fd })
    if (res.status === 401 && useAuth.getState().refreshToken) {
      try {
        const newToken = await refreshAccessToken()
        headers.authorization = `Bearer ${newToken}`
        res = await fetch(url, { method: 'POST', headers, body: fd })
      } catch { /* fall through */ }
    }
    if (!res.ok) {
      const text = await res.text().catch(() => '')
      throw new ApiError(res.status, text || res.statusText)
    }
    return res.json()
  },

  // ---- Workshop Gallery Images ----
  // Multi-image gallery on a project, separate from the single auto-
  // captured `thumbnail_storage_key`. Drives the Workshop publish flow's
  // cover-art picker + the public listing's image carousel.
  workshopImages: {
    list: (pid) => request(`/api/projects/${pid}/workshop-images`),
    upload: async (pid, file, caption) => {
      const fd = new FormData()
      fd.append('file', file)
      if (caption) fd.append('caption', caption)
      const url = `${API_URL}/api/projects/${pid}/workshop-images`
      const token = useAuth.getState().accessToken
      const headers = {}
      if (token) headers.authorization = `Bearer ${token}`
      let res = await fetch(url, { method: 'POST', headers, body: fd })
      if (res.status === 401 && useAuth.getState().refreshToken) {
        try {
          const newToken = await refreshAccessToken()
          headers.authorization = `Bearer ${newToken}`
          res = await fetch(url, { method: 'POST', headers, body: fd })
        } catch { /* fall through */ }
      }
      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new ApiError(res.status, text || res.statusText)
      }
      return res.json()
    },
    remove: (pid, id) =>
      request(`/api/projects/${pid}/workshop-images/${id}`, { method: 'DELETE' }),
    update: (pid, id, patch) =>
      request(`/api/projects/${pid}/workshop-images/${id}`, { method: 'PATCH', body: patch }),
    // Toggle this image as the gallery primary.  Calling it on the already-
    // primary image unpins it (toggle semantics — matches the backend).
    setPrimary: (pid, id) =>
      request(`/api/projects/${pid}/workshop-images/${id}/set-primary`, { method: 'POST' }),
  },

  // ---- Files / Assemblies ----
  listFiles: (projectId) => request(`/api/projects/${projectId}/files`),
  createFile: (projectId, { name, kind = 'file', parent_id = null, content = '' }) =>
    request(`/api/projects/${projectId}/files`, { method: 'POST', body: { name, kind, parent_id, content } }),
  getFile: (projectId, fileId) => request(`/api/projects/${projectId}/files/${fileId}`),
  updateFile: (projectId, fileId, patch) =>
    request(`/api/projects/${projectId}/files/${fileId}`, { method: 'PATCH', body: patch }),
  deleteFile: (projectId, fileId) =>
    request(`/api/projects/${projectId}/files/${fileId}`, { method: 'DELETE' }),

  // Upload a binary asset (e.g. STEP file). The backend should return a File row.
  // We use multipart/form-data; do NOT set content-type — the browser will set
  // the correct boundary header automatically.
  uploadAsset: async (projectId, file, { kind = 'step', parent_id = null } = {}) => {
    const fd = new FormData()
    fd.append('file', file)
    fd.append('name', file.name)
    fd.append('kind', kind)
    if (parent_id) fd.append('parent_id', parent_id)
    const url = `${API_URL}/api/projects/${projectId}/assets`
    const token = useAuth.getState().accessToken
    const headers = {}
    if (token) headers.authorization = `Bearer ${token}`
    let res = await fetch(url, { method: 'POST', headers, body: fd })
    if (res.status === 401 && useAuth.getState().refreshToken) {
      try {
        const newToken = await refreshAccessToken()
        headers.authorization = `Bearer ${newToken}`
        res = await fetch(url, { method: 'POST', headers, body: fd })
      } catch { /* fall through */ }
    }
    if (!res.ok) {
      const text = await res.text()
      let msg = text
      try { msg = JSON.parse(text).error || text } catch { /* ignore */ }
      throw new ApiError(res.status, msg || res.statusText)
    }
    return res.json()
  },

  // Download a binary file. Returns an ArrayBuffer; uses bearer auth.
  downloadFileURL: async (projectId, fileId) => {
    const url = `${API_URL}/api/projects/${projectId}/files/${fileId}/download`
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
    return res.arrayBuffer()
  },

  // ---- Chat ----
  listMessages: (projectId, threadId) =>
    request(`/api/projects/${projectId}/threads/${threadId}/messages`),
  sendMessage: (projectId, threadId, { content, part_refs, model }) =>
    request(`/api/projects/${projectId}/threads/${threadId}/messages`, {
      method: 'POST',
      body: { content, part_refs, model },
    }),

  // ---- Threads ----
  listThreads: (projectId, fileId) => {
    const q = fileId ? `?file_id=${fileId}` : ''
    return request(`/api/projects/${projectId}/threads${q}`)
  },
  createThread: (projectId, { title, file_id, model } = {}) =>
    request(`/api/projects/${projectId}/threads`, {
      method: 'POST',
      body: { title, file_id, model },
    }),
  updateThread: (projectId, threadId, patch) =>
    request(`/api/projects/${projectId}/threads/${threadId}`, {
      method: 'PATCH',
      body: patch,
    }),
  deleteThread: (projectId, threadId) =>
    request(`/api/projects/${projectId}/threads/${threadId}`, { method: 'DELETE' }),

  // ---- Members ----
  listMembers: (projectId) => request(`/api/projects/${projectId}/members`),
  inviteMember: (projectId, { email, role }) =>
    request(`/api/projects/${projectId}/members`, {
      method: 'POST',
      body: { email, role },
    }),
  updateMember: (projectId, userId, { role }) =>
    request(`/api/projects/${projectId}/members/${userId}`, {
      method: 'PATCH',
      body: { role },
    }),
  removeMember: (projectId, userId) =>
    request(`/api/projects/${projectId}/members/${userId}`, { method: 'DELETE' }),

  // ---- Share Links ----
  listShareLinks: (projectId) => request(`/api/projects/${projectId}/share/links`),
  createShareLink: (projectId, { role, expires_at, max_uses } = {}) =>
    request(`/api/projects/${projectId}/share/links`, {
      method: 'POST',
      body: { role, expires_at, max_uses },
    }),
  revokeShareLink: (projectId, linkId) =>
    request(`/api/projects/${projectId}/share/links/${linkId}`, { method: 'DELETE' }),
  getShareInfo: (token) =>
    request(`/api/share/${token}`, { auth: false }),
  acceptShareLink: (token) =>
    request(`/api/share/${token}/accept`, { method: 'POST' }),

  // ---- Models ----
  listModels: () => request('/api/models'),

  // Chunked, resumable binary upload (Phase 2). Used for STEP files; see
  // ROADMAP.md "Performance roadmap". Computes a SHA-256 of the file, asks the backend for a
  // session (which may resume an existing one), uploads any missing chunks
  // with bounded concurrency + per-chunk retry, then finalizes.
  //
  // onProgress({received, total, bytes}) fires after each chunk completes.
  uploadAssetChunked: (projectId, file, opts = {}) =>
    uploadAssetChunked(projectId, file, opts),
  cancelUpload: (projectId, uploadId) => cancelUpload(projectId, uploadId),

  // ---- Bill of Materials ----
  getBOM: (projectId) => request(`/api/projects/${projectId}/bom`),

  // ---- Activity timeline ----
  // Per-project merged feed of recent events (file revisions, chat messages,
  // file lifecycle, project_created). `before` is an ISO timestamp returned
  // as `next_cursor` by the previous page; pass it to walk further back.
  getActivity: (projectId, before, limit) =>
    request(`/api/projects/${projectId}/activity?limit=${limit ?? 50}${before ? `&before=${encodeURIComponent(before)}` : ''}`),

  // ---- Library: Part photos ----
  // Multipart upload of a single image. Backend resizes (longest side ≤
  // 1024 px), stores as JPEG, and appends to the Part's photos array. The
  // first photo on a Part is auto-promoted to primary.
  uploadPartPhoto: async (projectId, fileId, blob) => {
    const fd = new FormData()
    const name = (blob && blob.name) || 'photo.jpg'
    fd.append('file', blob, name)
    const url = `${API_URL}/api/projects/${projectId}/files/${fileId}/photos`
    const token = useAuth.getState().accessToken
    const headers = {}
    if (token) headers.authorization = `Bearer ${token}`
    let res = await fetch(url, { method: 'POST', headers, body: fd })
    if (res.status === 401 && useAuth.getState().refreshToken) {
      try {
        const newToken = await refreshAccessToken()
        headers.authorization = `Bearer ${newToken}`
        res = await fetch(url, { method: 'POST', headers, body: fd })
      } catch { /* fall through */ }
    }
    if (!res.ok) {
      const text = await res.text()
      let msg = text
      try { msg = JSON.parse(text).error || text } catch { /* ignore */ }
      throw new ApiError(res.status, msg || res.statusText)
    }
    return res.json()
  },
  deletePartPhoto: (projectId, fileId, storageKey) =>
    request(`/api/projects/${projectId}/files/${fileId}/photos?key=${encodeURIComponent(storageKey)}`,
      { method: 'DELETE' }),
  setPrimaryPartPhoto: (projectId, fileId, storageKey) =>
    request(`/api/projects/${projectId}/files/${fileId}/photos/primary?key=${encodeURIComponent(storageKey)}`,
      { method: 'PATCH' }),

  // ---- Library: Part 3D model ----
  // Thin wrapper around the chunked upload helper that returns a
  // {storage_key, mime_type} pair. Used by LibraryEditor's "Attach model"
  // affordance — the workspace store also has a higher-level
  // `replacePartModel` action that wraps this with revision recording.
  uploadPartModel: async (projectId, blob, fileName, opts = {}) => {
    const file = blob instanceof File
      ? blob
      : new File([blob], fileName || 'model.step', { type: blob.type || 'model/step' })
    const created = await uploadAssetChunked(projectId, file, {
      kind: 'step',
      parent_id: null,
      ...opts,
    })
    return created
  },

  // ---- File revisions (per-file undo history) ----
  listRevisions: (projectId, fileId, limit) =>
    request(`/api/projects/${projectId}/files/${fileId}/revisions${limit ? `?limit=${limit}` : ''}`),
  getRevision: (projectId, fileId, revisionId) =>
    request(`/api/projects/${projectId}/files/${fileId}/revisions/${revisionId}`),
  // Lazy-load the full reconstructed content for a single revision.
  // The list endpoint intentionally omits content; call this only when the
  // user explicitly requests it (e.g. "Show full content" in the panel).
  getRevisionContent: (projectId, fileId, revisionId) =>
    request(`/api/projects/${projectId}/files/${fileId}/revisions/${revisionId}/content`),
  restoreRevision: (projectId, fileId, revisionId) =>
    request(`/api/projects/${projectId}/files/${fileId}/restore/${revisionId}`, { method: 'POST' }),

  // ---- Avatar ----
  // Upload a new avatar from the user's local picker. The backend
  // resizes server-side (256x256, JPEG q=85) and returns the updated
  // user row with a freshly resolved avatar_url.
  uploadAvatar: async (blob) => {
    const fd = new FormData()
    const name = (blob && blob.name) || 'avatar.jpg'
    fd.append('file', blob, name)
    const url = `${API_URL}/api/me/avatar`
    const token = useAuth.getState().accessToken
    const headers = {}
    if (token) headers.authorization = `Bearer ${token}`
    let res = await fetch(url, { method: 'POST', headers, body: fd })
    if (res.status === 401 && useAuth.getState().refreshToken) {
      try {
        const newToken = await refreshAccessToken()
        headers.authorization = `Bearer ${newToken}`
        res = await fetch(url, { method: 'POST', headers, body: fd })
      } catch { /* fall through */ }
    }
    if (!res.ok) {
      const text = await res.text()
      let msg = text
      try { msg = JSON.parse(text).error || text } catch { /* ignore */ }
      throw new ApiError(res.status, msg || res.statusText)
    }
    return res.json()
  },
  deleteAvatar: () => request('/api/me/avatar', { method: 'DELETE' }),

  // ---- API Tokens ----
  createAPIToken: (name) => request('/api-tokens', { method: 'POST', body: { name } }),
  listAPITokens: () => request('/api-tokens'),
  revokeAPIToken: (tokenID) => request(`/api-tokens/${encodeURIComponent(tokenID)}`, { method: 'DELETE' }),

  // ---- Admin: distributor credentials (Library Phase 2) ----
  // All admin-only (account_role='admin'). The list endpoint returns
  // unconfigured rows too, so the UI can render a stub "configure"
  // affordance for each known distributor.
  admin: {
    listDistributors: () => request('/api/admin/distributors'),
    updateDistributor: (name, payload) =>
      request(`/api/admin/distributors/${encodeURIComponent(name)}`, {
        method: 'PUT',
        body: payload,
      }),
    deleteDistributor: (name) =>
      request(`/api/admin/distributors/${encodeURIComponent(name)}`, {
        method: 'DELETE',
      }),

    // Library Phase 3: verified-publisher curation. The backend
    // returns user rows with a library_count rollup and a
    // next_cursor for pagination. Search filters on email + name
    // server-side; verified_only=true narrows to flagged accounts.
    listPublishers: ({ search, verifiedOnly, cursor, limit } = {}) => {
      const qs = []
      if (search) qs.push(`search=${encodeURIComponent(search)}`)
      if (verifiedOnly) qs.push('verified_only=true')
      if (cursor) qs.push(`cursor=${encodeURIComponent(cursor)}`)
      if (limit) qs.push(`limit=${limit}`)
      const tail = qs.length ? `?${qs.join('&')}` : ''
      return request(`/api/admin/publishers${tail}`)
    },
    setPublisherVerified: (userId, isVerified) =>
      request(`/api/admin/publishers/${encodeURIComponent(userId)}`, {
        method: 'PUT',
        body: { is_verified_publisher: !!isVerified },
      }),
  },

  // ---- Library Phase 2: per-Part distributor refresh ----
  // Synchronous. The endpoint returns {updated: N, content: "<JSON>"}.
  refreshPartDistributors: (projectId, fileId) =>
    request(
      `/api/projects/${projectId}/files/${fileId}/distributors/refresh`,
      { method: 'POST' },
    ),

  // ---- Tolerance stack-up run ----
  runTolerance: (projectId, fileId, { method = 'monte_carlo', samples = 10000, rss_k = 3.0 } = {}) =>
    request(
      `/api/projects/${projectId}/files/${fileId}/tolerance/run`,
      { method: 'POST', body: { method, samples, rss_k } },
    ),

  // ---- FreeCAD import ----
  // Kick off a FreeCAD import given a blob/asset id returned by uploadAsset
  // or uploadAssetChunked. Calls the import_freecad_project LLM tool via the
  // standard project-level tool-call route.
  importFreecadProject: (projectId, fileBlobId, opts = {}) =>
    request(`/api/projects/${projectId}/imports/freecad`, {
      method: 'POST',
      body: {
        file_blob_id: fileBlobId,
        import_folder: opts.importFolder ?? '/freecad_import',
        mode: opts.mode ?? 'project',
      },
    }),

  // ---- IFC import ----
  // Import a .ifc file into a project as a .bim architecture file.
  // Returns { created_file, stats, warnings, import_folder }.
  importIFC: (projectId, fileBlobId, opts = {}) =>
    request(`/api/projects/${projectId}/imports/ifc`, {
      method: 'POST',
      body: {
        file_blob_id: fileBlobId,
        import_folder: opts.importFolder ?? '/ifc_import',
        mode: opts.mode ?? 'project',
      },
    }),

  // ---- Wiring diagram render ----
  // POSTs to the kerf-api thin handler which forwards to pyworker /run-wireviz.
  // Returns { svg: string|null, warnings: string[] }.
  runWireviz: (projectId, fileId) =>
    request(`/api/projects/${projectId}/files/${fileId}/wiring/run`, { method: 'POST' }),

  // ---- PLC lint ----
  // POSTs ST source directly to pyworker POST /lint-plc via the kerf-api thin
  // handler.  Returns { diagnostics: [...], warnings: [...] }.
  lintPLC: (projectId, source) =>
    request(`/api/projects/${projectId}/plc/lint`, {
      method: 'POST',
      body: { source },
    }),

  // ---- 3D-print slicing (kerf-slicing plugin, CuraEngine subprocess) ----
  // Slices the STL mesh referenced by the .print config file via the
  // pyworker POST /run-print-slice route. Returns G-code metadata + preview.
  // Response shape: { gcode, layer_count, print_time_s, filament_mm,
  //                   gcode_bytes, warnings, error }
  runPrintSlice: (projectId, fileId) =>
    request(`/api/projects/${projectId}/files/${fileId}/print-slice`, {
      method: 'POST',
    }),
}

// ---------------------------------------------------------------------------
// Chunked upload helpers (Phase 2)
// ---------------------------------------------------------------------------

// CHUNK_CONCURRENCY caps how many chunks can be in flight at once. 3 is the
// sweet spot for typical home-broadband upstream — more pipelined transfers
// rarely beat the single-stream throughput once link buffer fills.
const CHUNK_CONCURRENCY = 3
// Per-chunk retry policy. Three retries with exponential backoff (250 / 500 /
// 1000 ms) before we surface the error to the caller.
const CHUNK_RETRIES = 3

// Compute SHA-256 over a File, returning a 64-char lowercase hex digest.
// Web Crypto's `crypto.subtle.digest` doesn't expose an incremental API, so
// we feed it the entire ArrayBuffer in one shot. Fine within the 200 MB cap;
// switch to `js-sha256` streaming if we ever raise the cap.
async function sha256OfFile(file) {
  const buf = await file.arrayBuffer()
  const digest = await crypto.subtle.digest('SHA-256', buf)
  const bytes = new Uint8Array(digest)
  let hex = ''
  for (let i = 0; i < bytes.length; i++) {
    hex += bytes[i].toString(16).padStart(2, '0')
  }
  return hex
}

// authedFetch: a thin fetch wrapper that injects the bearer token and
// transparently refreshes on 401. Returns the raw Response so the caller
// can decide what to do (we use it for both JSON and 204 responses).
async function authedFetch(url, init = {}) {
  const token = useAuth.getState().accessToken
  const headers = { ...(init.headers || {}) }
  if (token) headers.authorization = `Bearer ${token}`
  let res = await fetch(url, { ...init, headers })
  if (res.status === 401 && useAuth.getState().refreshToken) {
    try {
      const newToken = await refreshAccessToken()
      headers.authorization = `Bearer ${newToken}`
      res = await fetch(url, { ...init, headers })
    } catch { /* fall through to caller */ }
  }
  return res
}

async function readErrorJSON(res) {
  const text = await res.text().catch(() => '')
  let msg = text || res.statusText
  let code
  try {
    const j = JSON.parse(text)
    msg = j.error || msg
    code = j.code
  } catch { /* not JSON */ }
  const err = new ApiError(res.status, msg)
  if (code) err.code = code
  return err
}

// uploadAssetChunked: the main entry point — see api.uploadAssetChunked.
async function uploadAssetChunked(projectId, file, { kind = 'step', parent_id = null, onProgress, onInit, signal } = {}) {
  if (!file) throw new Error('uploadAssetChunked: file required')

  const sha256 = await sha256OfFile(file)

  // 1. Init / resume.
  const initRes = await authedFetch(`${API_URL}/api/projects/${projectId}/uploads`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      filename: file.name,
      size: file.size,
      mime: file.type || 'model/step',
      sha256,
    }),
  })
  if (!initRes.ok) throw await readErrorJSON(initRes)
  const init = await initRes.json()
  const { upload_id: uploadId, chunk_size: chunkSize, total_chunks: totalChunks } = init
  let received = new Set((init.received_chunks || []).map((n) => Number(n)))
  // Surface the upload_id so the caller (e.g. workspace store) can wire a
  // proper DELETE on cancel.
  if (typeof onInit === 'function') {
    try { onInit({ uploadId, chunkSize, totalChunks }) } catch { /* swallow */ }
  }

  // Helper: drive a clean abort by DELETE-ing the session on the server,
  // then surfacing a recognisable error to the caller.
  async function abortAndThrow() {
    try {
      await authedFetch(`${API_URL}/api/projects/${projectId}/uploads/${uploadId}`, {
        method: 'DELETE',
      })
    } catch { /* best-effort */ }
    const err = new Error('upload aborted')
    err.aborted = true
    throw err
  }

  // 2. If the server says we're already complete (idempotent re-upload of
  // the same SHA), skip straight to finalize.
  if (!init.complete) {
    // 3. Build the missing-chunk worklist.
    const missing = []
    for (let i = 0; i < totalChunks; i++) {
      if (!received.has(i)) missing.push(i)
    }

    // 4. Bounded concurrency loop. We pull from the worklist via a shared
    // index so each "worker" simply asks for the next item to do.
    const total = totalChunks
    const fireProgress = () => {
      if (typeof onProgress === 'function') {
        const r = received.size
        onProgress({
          received: r,
          total,
          bytes: Math.min(file.size, r * chunkSize),
        })
      }
    }
    fireProgress() // initial tick (for resumed uploads, this could be > 0).

    if (signal?.aborted) await abortAndThrow()

    let nextIdx = 0
    let firstError = null
    const workers = []
    const concurrency = Math.min(CHUNK_CONCURRENCY, missing.length || 1)
    for (let w = 0; w < concurrency; w++) {
      workers.push((async () => {
        while (firstError == null) {
          if (signal?.aborted) {
            firstError = new Error('upload aborted')
            firstError.aborted = true
            return
          }
          const myIdx = nextIdx++
          if (myIdx >= missing.length) return
          const chunkIndex = missing[myIdx]
          const start = chunkIndex * chunkSize
          const end = Math.min(file.size, start + chunkSize)
          const blob = file.slice(start, end)
          try {
            await uploadOneChunk(projectId, uploadId, chunkIndex, blob, signal)
            received.add(chunkIndex)
            fireProgress()
          } catch (err) {
            firstError = err
            return
          }
        }
      })())
    }
    await Promise.all(workers)
    if (firstError) {
      if (firstError.aborted || signal?.aborted) await abortAndThrow()
      throw firstError
    }
  }

  if (signal?.aborted) await abortAndThrow()

  // 5. Finalize.
  const finRes = await authedFetch(`${API_URL}/api/projects/${projectId}/uploads/${uploadId}/finalize`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ kind, parent_id }),
  })
  if (!finRes.ok) throw await readErrorJSON(finRes)
  return finRes.json()
}

// uploadOneChunk: PUT a single chunk with retries + exponential backoff.
async function uploadOneChunk(projectId, uploadId, chunkIndex, blob, signal) {
  let attempt = 0
  let lastErr
  while (attempt <= CHUNK_RETRIES) {
    if (signal?.aborted) throw new Error('upload aborted')
    try {
      const url = `${API_URL}/api/projects/${projectId}/uploads/${uploadId}/chunks/${chunkIndex}`
      const res = await authedFetch(url, {
        method: 'PUT',
        headers: { 'content-type': 'application/octet-stream' },
        body: blob,
        signal,
      })
      if (res.ok || res.status === 204) return
      // Non-retryable client errors: don't bother retrying.
      if (res.status >= 400 && res.status < 500 && res.status !== 408 && res.status !== 429) {
        throw await readErrorJSON(res)
      }
      lastErr = await readErrorJSON(res)
    } catch (err) {
      lastErr = err
    }
    attempt++
    if (attempt > CHUNK_RETRIES) break
    const backoffMs = 250 * (2 ** (attempt - 1))
    await new Promise((r) => setTimeout(r, backoffMs))
  }
  throw lastErr || new Error(`chunk ${chunkIndex} upload failed`)
}

// cancelUpload: best-effort DELETE of an in-flight upload session.
export async function cancelUpload(projectId, uploadId) {
  try {
    await authedFetch(`${API_URL}/api/projects/${projectId}/uploads/${uploadId}`, {
      method: 'DELETE',
    })
  } catch { /* best-effort */ }
}
