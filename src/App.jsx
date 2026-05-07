import { useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Landing from './routes/Landing.jsx'
import Login from './routes/Login.jsx'
import Signup from './routes/Signup.jsx'
import AuthCallback from './routes/AuthCallback.jsx'
import Projects from './routes/Projects.jsx'
import Editor from './routes/Editor.jsx'
import Library from './routes/Library.jsx'
import BOMPage from './routes/BOM.jsx'
import AdminDistributors from './routes/AdminDistributors.jsx'
import AdminPublishers from './routes/AdminPublishers.jsx'
import ProtectedRoute from './routes/ProtectedRoute.jsx'
import ShortcutsModal from './components/ShortcutsModal.jsx'
import { useAuth } from './store/auth.js'
import { api } from './lib/api.js'
import {
  useCloudConfig,
  BillingPanel,
  PlanSelector,
  Workshop,
  WorkshopListing,
  AdminEmail,
} from './cloud/index.js'

export default function App() {
  const { cloudEnabled } = useCloudConfig()
  const tryBootstrap = useAuth((s) => s.tryBootstrap)
  const setSession = useAuth((s) => s.setSession)
  const refreshToken = useAuth((s) => s.refreshToken)
  const accessToken = useAuth((s) => s.accessToken)
  const [bootstrapping, setBootstrapping] = useState(true)

  // On mount: hit /api/bootstrap. If the backend has a state.json (the
  // brew/curl-install path) the store is seeded with a refresh token.
  // We then refresh once to obtain an access token + user row, so the
  // rest of the app sees a fully-authed session without the user ever
  // touching the login screen.
  useEffect(() => {
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
            // the dead refresh token so the user lands on /login.
            setSession({ accessToken: null, refreshToken: null, user: null })
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
  }, [])

  // While the bootstrap probe is in flight we deliberately render nothing —
  // showing /login for a frame before silently logging the user in is the
  // exact UX we're trying to avoid. The probe is fast (one local HTTP
  // round trip) so the blank frame is imperceptible in practice.
  if (bootstrapping && !accessToken && !refreshToken) {
    return null
  }

  return (
    <>
    <ShortcutsModal />
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/auth/callback" element={<AuthCallback />} />
      <Route path="/pricing" element={<PlanSelector />} />
      {cloudEnabled && <Route path="/workshop" element={<Workshop />} />}
      {cloudEnabled && (
        <Route path="/workshop/:slug" element={<WorkshopListing />} />
      )}

      <Route element={<ProtectedRoute />}>
        <Route path="/projects" element={<Projects />} />
        <Route path="/projects/:projectId" element={<Editor />} />
        <Route path="/projects/:projectId/files/:fileId" element={<Editor />} />
        <Route path="/projects/:projectId/bom" element={<BOMPage />} />
        {cloudEnabled && <Route path="/library" element={<Library />} />}
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
