import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.jsx'
import { listDirty, reconcile } from './lib/localStash.js'
import { useAuth } from './store/auth.js'

// ── L1 stash: load-time reconcile ─────────────────────────────────────────────
// After auth resolves, replay any dirty L1 entries to the server (handles
// crash / forced-close recovery). postRevision is the lightweight fire-and-
// forget save; the T-184 autosave scheduler owns the real debounced path.
async function _reconcileOnLoad() {
  const { accessToken, user } = useAuth.getState()
  if (!accessToken || !user) return
  // Derive the current workspace from the URL if available (editor path:
  // /projects/:projectId). For pages without a project context, reconcile is
  // a no-op because there are no dirty entries for workspaceId=undefined.
  const match = window.location.pathname.match(/\/projects\/([^/]+)/)
  const workspaceId = match ? match[1] : null
  if (!workspaceId) return

  const API_URL = import.meta.env.VITE_API_URL || ''
  await reconcile(workspaceId, async (filePath, bytes) => {
    const res = await fetch(
      `${API_URL}/api/workspaces/${workspaceId}/files/${encodeURIComponent(filePath)}`,
      {
        method: 'POST',
        headers: {
          'content-type': 'application/octet-stream',
          authorization: `Bearer ${accessToken}`,
        },
        body: bytes,
      },
    )
    if (!res.ok) throw new Error(`reconcile: server returned ${res.status}`)
  })
}

// ── L1 stash: beforeunload guard ──────────────────────────────────────────────
// Fire the browser "unsaved changes" prompt ONLY when L1 has dirty entries.
// Browsers no longer honour custom messages; just triggering preventDefault
// is enough to show the native dialog.
window.addEventListener('beforeunload', (event) => {
  listDirty().then((dirty) => {
    if (dirty.length > 0) {
      event.preventDefault()
    }
  })
})

// Subscribe to auth changes so reconcile runs once after the user logs in.
useAuth.subscribe((state, prev) => {
  if (state.accessToken && !prev.accessToken) {
    _reconcileOnLoad().catch(() => {/* reconcile failures are non-fatal */})
  }
})

// Also attempt reconcile immediately in case auth is already resolved
// (e.g. persisted refresh token that was exchanged before this listener ran).
_reconcileOnLoad().catch(() => {/* non-fatal */})

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
