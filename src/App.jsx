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
import ScrollToTop from './components/ScrollToTop.jsx'

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
const ForgotPassword = lazy(() => import('./routes/ForgotPassword.jsx'))
const ResetPassword = lazy(() => import('./routes/ResetPassword.jsx'))
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
// All per-vendor compare pages were migrated from JSX → markdown.
// CompareMdRoute now handles every /compare/:slug — fetches the .md
// from public/compare/, parses, and renders. Freecad.jsx is kept as it
// exports shared sub-components (Section, CompareTable, etc.) consumed
// by index.jsx.
const CompareMdRoute = lazy(() => import('./routes/compare/CompareMdRoute.jsx'))
// New sector domain pages (T-182)
const CompositesPage = lazy(() => import('./routes/domains/Composites.jsx'))
const DentalPage = lazy(() => import('./routes/domains/Dental.jsx'))
const OpticsPage = lazy(() => import('./routes/domains/Optics.jsx'))
const HorologyPage = lazy(() => import('./routes/domains/Horology.jsx'))
const PipingPage = lazy(() => import('./routes/domains/Piping.jsx'))
const PackagingPage = lazy(() => import('./routes/domains/Packaging.jsx'))
const MoldPage = lazy(() => import('./routes/domains/Mold.jsx'))
const WoodworkingPage = lazy(() => import('./routes/domains/Woodworking.jsx'))
const MarinePage = lazy(() => import('./routes/domains/Marine.jsx'))
const CivilPage = lazy(() => import('./routes/domains/Civil.jsx'))
const SiliconPage = lazy(() => import('./routes/domains/Silicon.jsx'))
const FirmwarePage = lazy(() => import('./routes/domains/Firmware.jsx'))
const AerospacePage = lazy(() => import('./routes/domains/Aerospace.jsx'))
const PLCPage = lazy(() => import('./routes/domains/PLC.jsx'))
const MotionSimPage = lazy(() => import('./routes/domains/MotionSim.jsx'))
const FemCfdPage = lazy(() => import('./routes/domains/FemCfd.jsx'))
const TextilesPage = lazy(() => import('./routes/domains/Textiles.jsx'))
const NotFound = lazy(() => import('./routes/NotFound.jsx'))

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
const UsagePage = lazy(() =>
  import('./cloud/UsageWidget.jsx').then((m) => ({ default: m.UsagePage })),
)

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
    <ScrollToTop />
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
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
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
      {/* All explicit /compare/<vendor> routes collapsed into the
          markdown-driven catch-all (commit 80fa444). CompareMdRoute
          fetches the .md from public/compare/ and renders <CompareMd>
          via the `/compare/:slug` route registered below. */}
      {/* Markdown-driven compare pages — falls through to legacy JSX if a .md is missing */}
      <Route path="/compare/:slug" element={<CompareMdRoute />} />
      {cloudEnabled && <Route path="/workshop" element={<Workshop />} />}
      {cloudEnabled && (
        <Route path="/workshop/:slug" element={<WorkshopListing />} />
      )}
      <Route path="/domains/jewelry" element={<JewelryDomainPage />} />
      <Route path="/jewelry-configurator" element={<JewelryConfigurator />} />
      <Route path="/share/:token" element={<JewelryShare />} />
      <Route path="/domains/architecture" element={<Architecture />} />
      <Route path="/domains/composites" element={<CompositesPage />} />
      <Route path="/domains/dental" element={<DentalPage />} />
      <Route path="/domains/optics" element={<OpticsPage />} />
      <Route path="/domains/horology" element={<HorologyPage />} />
      <Route path="/domains/piping" element={<PipingPage />} />
      <Route path="/domains/packaging" element={<PackagingPage />} />
      <Route path="/domains/mold" element={<MoldPage />} />
      <Route path="/domains/woodworking" element={<WoodworkingPage />} />
      <Route path="/domains/marine" element={<MarinePage />} />
      <Route path="/domains/civil" element={<CivilPage />} />
      <Route path="/domains/silicon" element={<SiliconPage />} />
      <Route path="/domains/firmware" element={<FirmwarePage />} />
      <Route path="/domains/aerospace" element={<AerospacePage />} />
      <Route path="/domains/plc" element={<PLCPage />} />
      <Route path="/domains/motion" element={<MotionSimPage />} />
      <Route path="/domains/femcfd" element={<FemCfdPage />} />
      <Route path="/domains/textiles" element={<TextilesPage />} />

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
        {cloudEnabled && <Route path="/usage" element={<UsagePage />} />}
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
    </Suspense>
    </>
  )
}
