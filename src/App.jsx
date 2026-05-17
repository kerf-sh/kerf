import { useEffect, useState, lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'

// ── eager (lightweight, shell-critical) ───────────────────────────────────
// ProtectedRoute is a tiny wrapper used to gate the /projects, /editor, etc.
// sub-tree — it has to render synchronously so React Router can resolve the
// nested <Outlet/>. ShortcutsModal is mounted on every page and would just be
// a flicker if lazy.
import ProtectedRoute from './routes/ProtectedRoute.jsx'
import ShortcutsModal from './components/ShortcutsModal.jsx'
import RouteFallback from './components/RouteFallback.jsx'

// ── lazy (route-level code splitting) ─────────────────────────────────────
// Every route below is converted from an eager `import X from '...'` to
// `const X = lazy(() => import('...'))` so each route ships as its own chunk
// and the initial bundle no longer drags in Editor + tscircuit + Monaco for
// users who only hit /landing or /docs. Suspense is wired with RouteFallback
// (the kerf-Loader-backed fallback) below.
const Landing = lazy(() => import('./routes/Landing.jsx'))
const DomainsHub = lazy(() => import('./routes/domains/index.jsx'))
const JewelryDomainPage = lazy(() => import('./routes/domains/Jewelry.jsx'))
const Architecture = lazy(() => import('./routes/domains/Architecture.jsx'))
const Automotive = lazy(() => import('./routes/domains/Automotive.jsx'))
const Pricing = lazy(() => import('./routes/Pricing.jsx'))
const Roadmap = lazy(() => import('./routes/Roadmap.jsx'))
const DocsHome = lazy(() => import('./routes/Docs/index.jsx'))
const DocsArticle = lazy(() => import('./routes/Docs/Article.jsx'))
const Login = lazy(() => import('./routes/Login.jsx'))
const Signup = lazy(() => import('./routes/Signup.jsx'))
const AuthCallback = lazy(() => import('./routes/AuthCallback.jsx'))
const Projects = lazy(() => import('./routes/Projects.jsx'))
const Editor = lazy(() => import('./routes/Editor.jsx'))
const Library = lazy(() => import('./routes/Library.jsx'))
const LibraryPart = lazy(() => import('./routes/LibraryPart.jsx'))
const BOMPage = lazy(() => import('./routes/BOM.jsx'))
const Profile = lazy(() => import('./routes/Profile.jsx'))
const WorkspaceSettings = lazy(() => import('./routes/WorkspaceSettings.jsx'))
const WorkspaceMembers = lazy(() => import('./routes/WorkspaceMembers.jsx'))
const AdminDistributors = lazy(() => import('./routes/AdminDistributors.jsx'))
const AdminPublishers = lazy(() => import('./routes/AdminPublishers.jsx'))
const Mechanical = lazy(() => import('./routes/domains/Mechanical.jsx'))
const JewelryConfigurator = lazy(() => import('./routes/JewelryConfigurator.jsx'))
const JewelryShare = lazy(() => import('./routes/JewelryShare.jsx'))
const Electronics = lazy(() => import('./routes/domains/Electronics.jsx'))
const CompareHub = lazy(() => import('./routes/compare/index.jsx'))
const FreecadPage = lazy(() => import('./routes/compare/Freecad.jsx'))
const KicadPage = lazy(() => import('./routes/compare/Kicad.jsx'))
const RhinoPage = lazy(() => import('./routes/compare/Rhino.jsx'))
const RevitPage = lazy(() => import('./routes/compare/Revit.jsx'))
const FusionPage = lazy(() => import('./routes/compare/Fusion.jsx'))
// New compare pages landed in the refactor branch (May 2026). These slot in
// alongside the original five — same shape, separate chunks.
const SolidworksPage = lazy(() => import('./routes/compare/Solidworks.jsx'))
const OnshapePage = lazy(() => import('./routes/compare/Onshape.jsx'))
const AltiumPage = lazy(() => import('./routes/compare/Altium.jsx'))
const MatrixGoldPage = lazy(() => import('./routes/compare/MatrixGold.jsx'))
const BlenderPage = lazy(() => import('./routes/compare/Blender.jsx'))
const AutocadPage = lazy(() => import('./routes/compare/Autocad.jsx'))
const InventorPage = lazy(() => import('./routes/compare/Inventor.jsx'))
const Civil3dPage = lazy(() => import('./routes/compare/Civil3d.jsx'))
const Max3dsPage = lazy(() => import('./routes/compare/Max3ds.jsx'))

// Cloud surface — these come from the cloud/ open-core split and may be
// stubs on OSS builds. useCloudConfig stays eager (we need it before any
// route renders) but is imported from its own file so the cloud-index
// barrel doesn't end up in the initial chunk; the route components
// themselves lazy-import their own modules and become their own chunks.
import { useCloudConfig } from './cloud/useCloudConfig.js'
const BillingPanel = lazy(() =>
  import('./cloud/BillingPanel.jsx').then((m) => ({ default: m.BillingPanel })),
)
const Workshop = lazy(() =>
  import('./cloud/Workshop.jsx').then((m) => ({ default: m.Workshop })),
)
const WorkshopListing = lazy(() =>
  import('./cloud/WorkshopListing.jsx').then((m) => ({ default: m.WorkshopListing })),
)
const AdminEmail = lazy(() => import('./cloud/AdminEmail.jsx'))

import { useAuth } from './store/auth.js'
import { api } from './lib/api.js'

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
    <Suspense fallback={<RouteFallback />}>
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
      {cloudEnabled && <Route path="/pricing" element={<Pricing />} />}
      <Route path="/roadmap" element={<Roadmap />} />
      <Route path="/domains" element={<DomainsHub />} />
      <Route path="/domains/automotive" element={<Automotive />} />
      <Route path="/docs" element={<DocsHome />} />
      <Route path="/docs/:slug" element={<DocsArticle />} />
      <Route path="/domains/electronics" element={<Electronics />} />
      <Route path="/domains/mechanical" element={<Mechanical />} />
      <Route path="/compare" element={<CompareHub />} />
      <Route path="/compare/freecad" element={<FreecadPage />} />
      <Route path="/compare/kicad" element={<KicadPage />} />
      <Route path="/compare/rhino" element={<RhinoPage />} />
      <Route path="/compare/revit" element={<RevitPage />} />
      <Route path="/compare/fusion" element={<FusionPage />} />
      <Route path="/compare/solidworks" element={<SolidworksPage />} />
      <Route path="/compare/onshape" element={<OnshapePage />} />
      <Route path="/compare/altium" element={<AltiumPage />} />
      <Route path="/compare/matrixgold" element={<MatrixGoldPage />} />
      <Route path="/compare/blender" element={<BlenderPage />} />
      <Route path="/compare/autocad" element={<AutocadPage />} />
      <Route path="/compare/inventor" element={<InventorPage />} />
      <Route path="/compare/civil3d" element={<Civil3dPage />} />
      <Route path="/compare/max3ds" element={<Max3dsPage />} />
      {cloudEnabled && <Route path="/workshop" element={<Workshop />} />}
      {cloudEnabled && (
        <Route path="/workshop/:slug" element={<WorkshopListing />} />
      )}
      <Route path="/domains/jewelry" element={<JewelryDomainPage />} />
      <Route path="/jewelry-configurator" element={<JewelryConfigurator />} />
      <Route path="/share/:token" element={<JewelryShare />} />
      <Route path="/domains/architecture" element={<Architecture />} />

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
    </Suspense>
    </>
  )
}
