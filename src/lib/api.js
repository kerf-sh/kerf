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
  logout: () => {
    const { refreshToken, logout } = useAuth.getState()
    logout()
    if (refreshToken) {
      return request('/auth/logout', { method: 'POST', body: { refresh_token: refreshToken }, auth: false }).catch(() => {})
    }
  },

  // ---- Projects ----
  listProjects: () => request('/api/projects'),
  createProject: (name, description) =>
    request('/api/projects', { method: 'POST', body: { name, description } }),
  getProject: (id) => request(`/api/projects/${id}`),
  updateProject: (id, patch) =>
    request(`/api/projects/${id}`, { method: 'PATCH', body: patch }),
  deleteProject: (id) =>
    request(`/api/projects/${id}`, { method: 'DELETE' }),

  // ---- Files / Assemblies ----
  listFiles: (projectId) => request(`/api/projects/${projectId}/files`),
  createFile: (projectId, { name, kind = 'file', parent_id = null, content = '' }) =>
    request(`/api/projects/${projectId}/files`, { method: 'POST', body: { name, kind, parent_id, content } }),
  getFile: (projectId, fileId) => request(`/api/projects/${projectId}/files/${fileId}`),
  updateFile: (projectId, fileId, patch) =>
    request(`/api/projects/${projectId}/files/${fileId}`, { method: 'PATCH', body: patch }),
  deleteFile: (projectId, fileId) =>
    request(`/api/projects/${projectId}/files/${fileId}`, { method: 'DELETE' }),

  // ---- Chat ----
  listMessages: (projectId, threadId) =>
    request(`/api/projects/${projectId}/threads/${threadId}/messages`),
  sendMessage: (projectId, threadId, { content, part_refs }) =>
    request(`/api/projects/${projectId}/threads/${threadId}/messages`, {
      method: 'POST',
      body: { content, part_refs },
    }),

  // ---- Threads ----
  listThreads: (projectId, fileId) => {
    const q = fileId ? `?file_id=${fileId}` : ''
    return request(`/api/projects/${projectId}/threads${q}`)
  },
  createThread: (projectId, { title, file_id } = {}) =>
    request(`/api/projects/${projectId}/threads`, {
      method: 'POST',
      body: { title, file_id },
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
}
