import { useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Landing from './routes/Landing.jsx'
import Pricing from './routes/Pricing.jsx'
import DocsHome from './routes/Docs/index.jsx'
import DocsArticle from './routes/Docs/Article.jsx'
import Login from './routes/Login.jsx'
import Signup from './routes/Signup.jsx'
import AuthCallback from './routes/AuthCallback.jsx'
import Projects from './routes/Projects.jsx'
import Editor from './routes/Editor.jsx'
import Library from './routes/Library.jsx'
import LibraryPart from './routes/LibraryPart.jsx'
import BOMPage from './routes/BOM.jsx'
import Profile from './routes/Profile.jsx'
import WorkspaceSettings from './routes/WorkspaceSettings.jsx'
import WorkspaceMembers from './routes/WorkspaceMembers.jsx'
import AdminDistributors from './routes/AdminDistributors.jsx'
import AdminPublishers from './routes/AdminPublishers.jsx'
import ProtectedRoute from './routes/ProtectedRoute.jsx'
import ShortcutsModal from './components/ShortcutsModal.jsx'
import { useAuth } from './store/auth.js'
import { api } from './lib/api.js'
import {
  useCloudConfig,
  BillingPanel,
  Workshop,
  WorkshopListing,
  AdminEmail,
} from './cloud/index.js'

export default function App() {
  const { cloudEnabled, localMode, ready: cloudConfigReady } = useCloudConfig()
  const tryBootstrap = useAuth((s) => s.tryBootstrap)
  const tryBootstrapLocal = useAuth((s) => s.tryBootstrapLocal)
  const setSession = useAuth((s) => s.setSession)
  const refreshToken = useAuth((s) => s.refreshToken)
  const accessToken = useAuth((s) => s.accessToken)
  const [bootstrapping, setBootstrapping] = useState(true)

  // On mount: wait for /api/config (so we know local_mode), then hit
  // /api/bootstrap. If the backend has a state.json (the brew/curl-install
  // path) the store is seeded with a refresh token, exchange it for an
  // access token. Otherwise, when local_mode is on we POST to
  // /auth/bootstrap-local to auto-create a singleton account so the user
  // never sees /login.
  useEffect(() => {
    if (!cloudConfigReady) return
    let cancelled = false
    ;(async () => {
      try {
        await tryBootstrap()
        const { refreshToken: rt, accessToken: at } = useAuth.getState()
        if (rt && !at && !cancelled) {
          // Have a refresh token but no access token — exchange it.
          try {
            await api.refresh()
            // refresh() leaves accessToken/user populated on success.
          } catch {
            // If the refresh failed (e.g. token expired/revoked), drop
            // the dead refresh token so the user lands on /login (or
            // we re-bootstrap below in local mode).
            setSession({ accessToken: null, refreshToken: null, user: null })
          }
        }
        // Local-mode auto-account: if we still don't have a session
        // and the cloud config says local_mode is on, mint one. The
        // endpoint 404s on cloud builds so this is OSS-only by design.
        if (!cancelled && localMode) {
          const { accessToken: at2 } = useAuth.getState()
          if (!at2) {
            await tryBootstrapLocal()
          }
        }
      } finally {
        if (!cancelled) setBootstrapping(false)
      }
    })()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cloudConfigReady, localMode])

  // While the bootstrap probe is in flight we deliberately render nothing —
  // showing /login for a frame before silently logging the user in is the
  // exact UX we're trying to avoid. The probe is fast (one local HTTP
  // round trip) so the blank frame is imperceptible in practice.
  if (bootstrapping && !accessToken && !refreshToken) {
    return null
  }

  // In local mode the marketing landing + login/signup pages don't apply —
  // there's exactly one user, the auto-bootstrap above has already minted
  // their session, send them straight to /projects. Cloud builds keep the
  // existing public surface (Landing, Login, Signup, Pricing, Docs).
  const localShortcut = localMode && accessToken
  return (
    <>
    <ShortcutsModal />
    <Routes>
      <Route
        path="/"
        element={localShortcut ? <Navigate to="/projects" replace /> : <Landing />}
      />
      <Route
        path="/login"
        element={localShortcut ? <Navigate to="/projects" replace /> : <Login />}
      />
      <Route
        path="/signup"
        element={localShortcut ? <Navigate to="/projects" replace /> : <Signup />}
      />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/pricing" element={<Pricing />} />
      <Route path="/docs" element={<DocsHome />} />
      <Route path="/docs/:slug" element={<DocsArticle />} />
      {cloudEnabled && <Route path="/workshop" element={<Workshop />} />}
      {cloudEnabled && (
        <Route path="/workshop/:slug" element={<WorkshopListing />} />
      )}

      <Route element={<ProtectedRoute />}>
        <Route path="/profile" element={<Profile />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/w/:workspaceSlug/projects" element={<Projects />} />
        <Route path="/w/:workspaceSlug/settings" element={<WorkspaceSettings />} />
        <Route path="/w/:workspaceSlug/members" element={<WorkspaceMembers />} />
        <Route path="/projects/:projectId" element={<Editor />} />
        <Route path="/projects/:projectId/files/:fileId" element={<Editor />} />
        <Route path="/projects/:projectId/bom" element={<BOMPage />} />
        {cloudEnabled && <Route path="/library" element={<Library />} />}
        {cloudEnabled && <Route path="/library/:slug" element={<LibraryPart />} />}
        <Route path="/admin/distributors" element={<AdminDistributors />} />
        <Route path="/admin/publishers" element={<AdminPublishers />} />
        {cloudEnabled && <Route path="/admin/email" element={<AdminEmail />} />}
        {cloudEnabled && <Route path="/billing" element={<BillingPanel />} />}
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
    </>
  )
}
