import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Share2, Save, Loader2, ArrowLeft, Check, X, RotateCcw, Undo2, Redo2, GitBranch, MessageSquare, PanelRightClose, PanelRightOpen, PanelLeftOpen, PanelLeftClose, Plus, Box, SlidersHorizontal, ChevronDown, ArrowRight, RotateCw, Activity as ActivityIcon, FileDown, LogOut, UserCog, Settings, CreditCard, Users } from 'lucide-react'
import { Link } from 'react-router-dom'
import { LogoWordmark } from '../components/Logo.jsx'
import FileTree from '../components/FileTree.jsx'
import Renderer from '../components/Renderer.jsx'
import CodeEditor from '../components/CodeEditor.jsx'
import ChatPanel from '../components/ChatPanel.jsx'
import ShareModal from '../components/ShareModal.jsx'
import ObjectsPanel from '../components/ObjectsPanel.jsx'
import CircuitComponentsPanel from '../components/CircuitComponentsPanel.jsx'
import ExportButton from '../components/ExportButton.jsx'
import MeasureToolbar from '../components/MeasureToolbar.jsx'
import FeatureInspector from '../components/FeatureInspector.jsx'
import AssemblyEditor from '../components/AssemblyEditor.jsx'
import DrawingView from '../components/DrawingView.jsx'
import DrawingToolbar from '../components/DrawingToolbar.jsx'
import DrawingPropertiesPanel from '../components/DrawingPropertiesPanel.jsx'
import SketchView from '../components/SketchView.jsx'
import FeatureView from '../components/FeatureView.jsx'
import SectionView from '../components/SectionView.jsx'
import CircuitEditor from '../components/CircuitEditor.jsx'
import LibraryEditor from '../components/LibraryEditor.jsx'
import MaterialEditor from '../components/MaterialEditor.jsx'
import EquationsEditor from '../components/EquationsEditor.jsx'
import ScriptEditor from '../components/ScriptEditor.jsx'
import ToleranceView from '../components/ToleranceView.jsx'
import TopoView from '../components/TopoView.jsx'
import FEMView from '../components/FEMView.jsx'
import GraphEditor from '../components/GraphEditor.jsx'
import RenderView from '../components/RenderView.jsx'
import FamilyEditor from '../components/FamilyEditor.jsx'
import ScheduleEditor from '../components/ScheduleEditor.jsx'
import ViewEditor from '../components/ViewEditor.jsx'
import SheetEditor from '../components/SheetEditor.jsx'
import MEPView from '../components/MEPView.jsx'
import StairView from '../components/StairView.jsx'
import RailingView from '../components/RailingView.jsx'
import PLCView from '../components/PLCView.jsx'
import QuadMeshView from '../components/QuadMeshView.jsx'
import PrintSliceView from '../components/PrintSliceView.jsx'
import ConfigurationsPanel from '../components/ConfigurationsPanel.jsx'
import ActivityTimeline from '../components/ActivityTimeline.jsx'
import { useWorkspace, loadFilePartsForProject } from '../store/workspace.js'
import { useWorkspaces } from '../store/workspaces.js'
import { useAuth } from '../store/auth.js'
import { useCloudConfig, GitPanel, PublishButton } from '../cloud/index.js'
import { runJscad, cancelJscad } from '../lib/jscadRunner.js'
import { getTopologyLazy } from '../lib/topology.js'
import { meshCache } from '../lib/meshCache.js'
import { distance, formatDistance } from '../lib/measure.js'
import { extractDisplayGeometryFromParts } from '../lib/femDisplacement.js'
import { exportSvg, exportPng, exportPdf } from '../lib/svgExport.js'
import { api } from '../lib/api.js'
import { readCollapsed, CHAT_COLLAPSE_KEY, GIT_COLLAPSE_KEY } from '../lib/panelCollapse.js'
import { mateRefFromPick, parseAssembly } from '../lib/assembly.js'
import { _internalLoops } from '../lib/sketchGeom2.js'
import FileEditor from '../components/FileEditor.jsx'
import { isTextCodeFile } from '../lib/editorModes.js'
import UnsavedRestoreBanner from '../components/UnsavedRestoreBanner.jsx'
import Modal from '../components/Modal.jsx'
import TopBarMoreMenu from '../components/TopBarMoreMenu.jsx'
import CAMView from '../components/CAMView.jsx'
import BIMView from '../components/BIMView.jsx'
import AirfoilPolarPlot from '../components/AirfoilPolarPlot.jsx'
import OrbitViewer from '../components/OrbitViewer.jsx'
import { fetchAirfoilPolar } from '../lib/airfoilPolarBridge.js'

// ---------------------------------------------------------------------------
// Build3DDropdown — toolbar dropdown in the sketch header that scaffolds a
// .jscad file from the current .sketch using extrude_linear or extrude_rotate.
//
// Only visible when the sketch has at least one closed loop (i.e. extrudable).
// ---------------------------------------------------------------------------

function Build3DModal({ op, sketchName, onConfirm, onClose }) {
  const isRevolve = op === 'extrude_rotate'
  const [height, setHeight] = useState('10')
  const [angle, setAngle] = useState('360')
  const [filename, setFilename] = useState(sketchName.replace(/\.sketch$/, '') + '.jscad')

  function handleSubmit(e) {
    e.preventDefault()
    const params = isRevolve
      ? { angle_deg: parseFloat(angle) || 360 }
      : { height_mm: parseFloat(height) || 10 }
    onConfirm({ op, params, filename })
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={isRevolve ? 'Revolve sketch' : 'Extrude sketch'}
      widthClass="max-w-xs"
      footer={
        <>
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded border border-ink-700 text-ink-400 text-xs hover:bg-ink-800"
          >
            Cancel
          </button>
          <button
            type="submit"
            form="build3d-form"
            className="flex-1 py-1.5 rounded bg-kerf-300/15 border border-kerf-300/40 text-kerf-200 text-xs hover:bg-kerf-300/25"
          >
            Build 3D
          </button>
        </>
      }
    >
      <form id="build3d-form" onSubmit={handleSubmit} className="flex flex-col gap-3">
        {isRevolve ? (
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-ink-400">Angle (degrees)</span>
            <input
              type="number"
              min="1"
              max="360"
              step="1"
              value={angle}
              onChange={(e) => setAngle(e.target.value)}
              className="bg-ink-800 border border-ink-700 rounded px-2 py-1 text-xs text-ink-100 outline-none focus:border-kerf-300/60"
              autoFocus
            />
          </label>
        ) : (
          <label className="flex flex-col gap-1">
            <span className="text-[11px] text-ink-400">Height (mm)</span>
            <input
              type="number"
              min="0.01"
              step="0.5"
              value={height}
              onChange={(e) => setHeight(e.target.value)}
              className="bg-ink-800 border border-ink-700 rounded px-2 py-1 text-xs text-ink-100 outline-none focus:border-kerf-300/60"
              autoFocus
            />
          </label>
        )}
        <label className="flex flex-col gap-1">
          <span className="text-[11px] text-ink-400">Output filename</span>
          <input
            type="text"
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
            className="bg-ink-800 border border-ink-700 rounded px-2 py-1 text-xs font-mono text-ink-100 outline-none focus:border-kerf-300/60"
          />
        </label>
      </form>
    </Modal>
  )
}

function Build3DDropdown({ sketch, sketchName, onBuild, disabled }) {
  const [open, setOpen] = useState(false)
  const [modal, setModal] = useState(null) // 'extrude_linear' | 'extrude_rotate'
  const wrapRef = useRef(null)

  // Close on click-outside.
  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    window.addEventListener('mousedown', handler)
    return () => window.removeEventListener('mousedown', handler)
  }, [open])

  function handleConfirm({ op, params }) {
    setModal(null)
    onBuild(op, params)
  }

  if (disabled) return null

  return (
    <>
      <div ref={wrapRef} className="relative">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="inline-flex items-center gap-1 px-2 py-1 rounded bg-amber-300/10 border border-amber-300/25 text-amber-200 hover:bg-amber-300/20 text-xs"
          title="Build a 3D part from this sketch (extrude or revolve)"
        >
          <Box size={11} />
          <span>Build 3D</span>
          <ChevronDown size={10} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
        {open && (
          <div className="absolute left-0 top-full mt-1 z-40 min-w-[160px] bg-ink-850 border border-ink-700 rounded-md shadow-lg py-1">
            <button
              type="button"
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-ink-100 hover:bg-ink-700 text-left"
              onClick={() => { setOpen(false); setModal('extrude_linear') }}
            >
              <ArrowRight size={12} className="text-amber-300" />
              <span>Extrude</span>
            </button>
            <button
              type="button"
              className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-ink-100 hover:bg-ink-700 text-left"
              onClick={() => { setOpen(false); setModal('extrude_rotate') }}
            >
              <RotateCw size={12} className="text-amber-300" />
              <span>Revolve</span>
            </button>
          </div>
        )}
      </div>
      {modal && (
        <Build3DModal
          op={modal}
          sketchName={sketchName}
          onConfirm={handleConfirm}
          onClose={() => setModal(null)}
        />
      )}
    </>
  )
}

// ---------------------------------------------------------------------------
// TopBarMoreMenu is now in src/components/TopBarMoreMenu.jsx (T-L2).
// ---------------------------------------------------------------------------
// EditorUserMenu — the avatar pill in the Editor's topbar with a working
// drop-down. Before this it was an inert <div> so "click profile → sign
// out" did literally nothing. Uses the same stable-listener pattern as
// src/components/Layout.jsx UserMenu (React 19 click-outside race fix).
// ---------------------------------------------------------------------------
function EditorUserMenu({ user }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)
  const openRef = useRef(false)
  const navigate = useNavigate()
  const logout = useAuth((s) => s.logout)
  const currentWorkspaceSlug = useWorkspaces((s) => s.currentSlug)
  const { cloudEnabled } = useCloudConfig()

  // Keep openRef in sync so the stable listener reads the latest value
  // without depending on `open` (and thus avoiding re-registration races
  // that were hiding the Layout.jsx dropdown — same root cause).
  useEffect(() => { openRef.current = open }, [open])

  useEffect(() => {
    function onClick(e) {
      if (!openRef.current) return
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    function onKey(e) {
      if (e.key === 'Escape' && openRef.current) setOpen(false)
    }
    document.addEventListener('click', onClick, true)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('click', onClick, true)
      document.removeEventListener('keydown', onKey)
    }
  }, [])

  const onSignOut = async () => {
    setOpen(false)
    try { await api.logout() } catch { /* tolerate network error */ }
    logout()
    navigate('/login', { replace: true })
  }

  const initial = ((user?.name || user?.email || '?').slice(0, 1) || '?').toUpperCase()

  return (
    <div className="relative" ref={wrapRef}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls="editor-user-menu"
        title={user?.email || 'Account'}
        className="w-7 h-7 rounded-full bg-ink-700 flex items-center justify-center text-[11px] text-ink-100 font-semibold flex-shrink-0 hover:bg-ink-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
      >
        {user?.avatar_url
          ? <img src={user.avatar_url} alt="" className="w-full h-full rounded-full object-cover" />
          : initial}
      </button>

      {open && (
        <div
          id="editor-user-menu"
          role="menu"
          data-testid="editor-user-menu"
          className="absolute right-0 mt-2 w-56 rounded-xl border border-ink-800 bg-ink-900/95 backdrop-blur shadow-xl shadow-black/40 py-1.5 z-50"
        >
          <div className="px-3 py-2.5 border-b border-ink-800">
            <p className="text-sm text-ink-100 truncate">{user?.name || 'Signed in'}</p>
            <p className="text-xs text-ink-400 truncate font-mono">{user?.email || ''}</p>
          </div>
          <div className="py-1">
            <Link
              to="/profile"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-100 hover:bg-ink-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
            >
              <UserCog size={14} className="text-ink-300" />
              Profile
            </Link>
          </div>
          {currentWorkspaceSlug && (
            <div className="py-1 border-t border-ink-800">
              <p className="px-3 pt-1 pb-0.5 text-[10px] font-mono uppercase tracking-[0.18em] text-ink-500">
                Workspace
              </p>
              <Link
                to={`/w/${currentWorkspaceSlug}/members`}
                role="menuitem"
                onClick={() => setOpen(false)}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-100 hover:bg-ink-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
              >
                <Users size={14} className="text-ink-300" />
                Members
              </Link>
              <Link
                to={`/w/${currentWorkspaceSlug}/settings`}
                role="menuitem"
                onClick={() => setOpen(false)}
                className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-100 hover:bg-ink-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
              >
                <Settings size={14} className="text-ink-300" />
                Workspace settings
              </Link>
              {cloudEnabled && (
                <Link
                  to="/billing"
                  role="menuitem"
                  onClick={() => setOpen(false)}
                  className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-100 hover:bg-ink-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
                >
                  <CreditCard size={14} className="text-ink-300" />
                  Billing
                </Link>
              )}
            </div>
          )}
          <div className="py-1 border-t border-ink-800">
            <Link
              to="/projects"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-100 hover:bg-ink-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
            >
              <ArrowLeft size={14} className="text-ink-300" />
              All projects
            </Link>
            <button
              type="button"
              role="menuitem"
              onClick={onSignOut}
              className="w-full flex items-center gap-2.5 px-3 py-2 text-sm text-ink-100 hover:bg-ink-800/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/50"
            >
              <LogOut size={14} className="text-ink-300" />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  )
}


const AUTOSAVE_MS = 500
// Re-eval debounce, scaled by file size. Small files feel snappy at 250ms;
// very large files spend most of that window evaluating, so we stretch the
// idle window and let the user finish their thought before re-running.
// Tiers (matched against `content.length`, which is char count — close enough
// to byte count for ASCII source we care about):
//   ≤ 10 KB              → 250 ms
//   10 KB – 50 KB        → 500 ms
//   50 KB – 200 KB       → 1500 ms
//   > 200 KB             → 3000 ms
function runDebounceFor(content) {
  const len = (content && content.length) || 0
  if (len <= 10 * 1024) return 250
  if (len <= 50 * 1024) return 500
  if (len <= 200 * 1024) return 1500
  return 3000
}
// Wait this long after the last edit/save before snapping a thumbnail —
// avoids re-uploading on every keystroke during a typing burst.
const THUMBNAIL_DEBOUNCE_MS = 2000

function isStepFile(file) {
  if (!file) return false
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.step') || n.endsWith('.stp')
}

function isAssemblyFile(file) {
  if (!file) return false
  if (file.kind === 'assembly') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.assembly')
}

function isDrawingFile(file) {
  if (!file) return false
  if (file.kind === 'drawing') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.drawing')
}

function isSketchFile(file) {
  if (!file) return false
  if (file.kind === 'sketch') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.sketch')
}

function isFeatureFile(file) {
  if (!file) return false
  if (file.kind === 'feature') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.feature')
}

function isCircuitFile(file) {
  if (!file) return false
  if (file.kind === 'circuit') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.circuit.tsx')
}

function isPartFile(file) {
  if (!file) return false
  if (file.kind === 'part') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.part')
}

function isMaterialFile(file) {
  if (!file) return false
  if (file.kind === 'material') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.material')
}

function isEquationsFile(file) {
  if (!file) return false
  if (file.kind === 'equations') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.equations')
}

function isScriptFile(file) {
  if (!file) return false
  if (file.kind === 'script') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.script.ts') || n.endsWith('.script.py')
}

function isToleranceFile(file) {
  if (!file) return false
  if (file.kind === 'tolerance') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.tolerance')
}

function isTopoFile(file) {
  if (!file) return false
  if (file.kind === 'topo') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.topo')
}

function isSubdFile(file) {
  if (!file) return false
  if (file.kind === 'subd') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.subd')
}

function isMeshFile(file) {
  if (!file) return false
  if (file.kind === 'mesh') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.mesh')
}

function isGraphFile(file) {
  if (!file) return false
  if (file.kind === 'graph') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.graph')
}

function isRenderFile(file) {
  if (!file) return false
  if (file.kind === 'render') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.render')
}

function isFamilyFile(file) {
  if (!file) return false
  if (file.kind === 'family') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.family.json')
}

function isScheduleFile(file) {
  if (!file) return false
  if (file.kind === 'schedule') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.schedule.json')
}

function isViewFile(file) {
  if (!file) return false
  if (file.kind === 'view') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.view.json')
}

function isSheetFile(file) {
  if (!file) return false
  if (file.kind === 'sheet') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.sheet.json')
}

function isMEPFile(file) {
  if (!file) return false
  if (['duct', 'pipe', 'conduit'].includes(file.kind)) return true
  const n = (file.name || '').toLowerCase()
  return n.includes('.duct.json') || n.includes('.pipe.json') || n.includes('.conduit.json')
}

function isStairFile(file) {
  if (!file) return false
  if (file.kind === 'stair') return true
  const n = (file.name || '').toLowerCase()
  return n.includes('.stair.json')
}

function isRailingFile(file) {
  if (!file) return false
  if (file.kind === 'railing') return true
  const n = (file.name || '').toLowerCase()
  return n.includes('.railing.json')
}

function isFemFile(file) {
  if (!file) return false
  if (file.kind === 'fem') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.fem')
}

function isSectionFile(file) {
  if (!file) return false
  if (file.kind === 'section') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.section')
}

function isPLCFile(file) {
  if (!file) return false
  if (file.kind === 'plc_st') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.plc.st')
}

function isQuadMeshFile(file) {
  if (!file) return false
  if (file.kind === 'quadmesh') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.quadmesh')
}

function isPrintFile(file) {
  if (!file) return false
  if (file.kind === 'print') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.print')
}

function isCAMFile(file) {
  if (!file) return false
  if (file.kind === 'cam') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.cam')
}

function isBIMFile(file) {
  if (!file) return false
  if (file.kind === 'bim') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.bim')
}

function isAirfoilFile(file) {
  if (!file) return false
  if (file.kind === 'airfoil') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.airfoil')
}

function isOrbitFile(file) {
  if (!file) return false
  if (file.kind === 'orbit') return true
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.orbit')
}

// ---------------------------------------------------------------------------
// ActivityTimelineBody — the ActivityTimeline panel body without its own outer
// drawer wrapper. Rendered inside the unified right drawer's content area when
// the activity tab is active. All data comes from the workspace store.
// ---------------------------------------------------------------------------
function ActivityTimelineBody({ projectId }) {
  // Render the full ActivityTimeline but pass `open={true}` so it always shows
  // its content. The onClose callback routes to the unified drawer close action.
  const closeRightDrawer = useWorkspace((s) => s.closeRightDrawer)
  return (
    <ActivityTimeline
      projectId={projectId}
      open={true}
      onClose={closeRightDrawer}
    />
  )
}

// ---------------------------------------------------------------------------
// AirfoilFileView — wrapper that parses a .airfoil JSON file and fetches
// polar data from the aero endpoint before rendering AirfoilPolarPlot.
//
// .airfoil file shape (JSON):
//   { airfoil: "naca0012", alpha_range: [-10, 15, 1] }
// Falls back to showing the raw content as code when parsing fails.
// ---------------------------------------------------------------------------
// ---------------------------------------------------------------------------
// BIMFileView — compiles a .bim file to IFC4 (POST /compile-ifc) and renders
// the result via BIMView. Replaces the previous hardcoded ifc_base64={null}.
// ---------------------------------------------------------------------------
function BIMFileView({ content, fileName, viewRef }) {
  const [ifc, setIfc] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    setIfc(null)
    setError(null)
    if (!content) return
    let cancelled = false
    setLoading(true)
    api.compileIfc(content)
      .then((data) => {
        if (cancelled) return
        setLoading(false)
        if (data?.errors?.length) { setError(data.errors.join('; ')); return }
        setIfc(data?.ifc_base64 || null)
      })
      .catch((err) => {
        if (!cancelled) { setError(err?.message || String(err)); setLoading(false) }
      })
    return () => { cancelled = true }
  }, [content])

  return (
    <div className="flex-1 min-h-0 relative">
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center gap-2 text-ink-400 text-sm">
          <div className="w-4 h-4 border-2 border-kerf-400 border-t-transparent rounded-full animate-spin" />
          Compiling IFC…
        </div>
      )}
      {error && (
        <div className="absolute top-3 left-3 z-20 text-red-400 text-xs font-mono max-w-sm">
          IFC compile failed: {error}
        </div>
      )}
      <BIMView viewRef={viewRef} ifc_base64={ifc} className="w-full h-full" />
      <div className="absolute bottom-1 left-2 text-[11px] text-ink-600 font-mono pointer-events-none">{fileName || ''}</div>
    </div>
  )
}

function AirfoilFileView({ content, fileName }) {
  const [polar, setPolar] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    setPolar(null)
    setError(null)
    let cancelled = false
    let parsed
    try { parsed = JSON.parse(content || '{}') } catch { parsed = {} }
    const airfoil = parsed.airfoil || ''
    const alphaRange = Array.isArray(parsed.alpha_range) ? parsed.alpha_range : [-10, 15, 1]
    if (!airfoil) return
    setLoading(true)
    fetchAirfoilPolar(airfoil, alphaRange)
      .then((data) => { if (!cancelled) { setPolar(data); setLoading(false) } })
      .catch((err) => { if (!cancelled) { setError(err?.message || String(err)); setLoading(false) } })
    return () => { cancelled = true }
  }, [content])

  return (
    <div className="flex-1 min-h-0 overflow-auto flex flex-col items-center justify-center gap-4 p-6 bg-ink-950">
      <div className="text-[11px] text-ink-500 font-mono mb-2">{fileName || ''}</div>
      {loading && (
        <div className="flex items-center gap-2 text-ink-400 text-sm">
          <div className="w-4 h-4 border-2 border-kerf-400 border-t-transparent rounded-full animate-spin" />
          Computing polar…
        </div>
      )}
      {error && (
        <div className="text-red-400 text-xs font-mono max-w-sm text-center">{error}</div>
      )}
      {polar && (
        <AirfoilPolarPlot polar={polar} showCD width={560} height={340} />
      )}
      {!loading && !polar && !error && (
        <div className="text-ink-500 text-xs">
          Set <code className="font-mono bg-ink-800 px-1 rounded">airfoil</code> in the file to load polar data.
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// OrbitFileView — wrapper that parses a .orbit JSON file and renders the
// satellite trajectory using OrbitViewer.
//
// .orbit file shape (JSON):
//   { trajectory: [{x, y, z}, ...] }   — pre-propagated IJK points (km)
//   OR
//   { elements: { a, e, i, Omega, omega, nu0, duration_s, n_steps } }
//   (future: fetch from /api/aero/orbit/propagate via orbitBridge)
//
// Currently renders whatever trajectory array is present in the file.
// ---------------------------------------------------------------------------
function OrbitFileView({ content, fileName }) {
  let parsed = {}
  try { parsed = JSON.parse(content || '{}') } catch { /* ignore */ }
  const trajectory = Array.isArray(parsed.trajectory) ? parsed.trajectory : []

  return (
    <div className="flex-1 min-h-0 overflow-auto flex flex-col items-center justify-center gap-4 p-6 bg-ink-950">
      <div className="text-[11px] text-ink-500 font-mono mb-2">{fileName || ''}</div>
      {trajectory.length === 0 ? (
        <div className="text-ink-500 text-xs text-center max-w-xs">
          No trajectory data yet. Add a <code className="font-mono bg-ink-800 px-1 rounded">trajectory</code> array
          (IJK km points) or use the LLM tool to propagate an orbit.
        </div>
      ) : (
        <OrbitViewer trajectory={trajectory} width={600} height={400} />
      )}
    </div>
  )
}

export default function Editor() {
  const { projectId, fileId } = useParams()
  const navigate = useNavigate()
  const user = useAuth((s) => s.user)
  const w = useWorkspace()
  const inputRef = useRef(null)
  const rendererRef = useRef(null)
  // Active view's imperative handle. Every view component sets this
  // via `viewRef` (or `ref` for the Renderer) so the thumbnail
  // useEffect below can call snapshot() without branching on kind.
  const currentViewRef = useRef(null)
  // Reset the view-ref whenever the active file changes so the
  // useEffect doesn't fire a snapshot against a unmounted view.
  // Each new view's useImperativeHandle wires the ref again on mount.
  useEffect(() => {
    currentViewRef.current = null
  }, [w.currentFile?.id, w.currentFile?.kind])

  // ----- Project lifecycle -----
  useEffect(() => {
    if (projectId) {
      w.loadProject(projectId).then(() => {
        // After files load, check IDB for any unflushed entries from a previous
        // session and surface the UnsavedRestoreBanner. This is intentionally
        // USER-INITIATED — the banner asks before replaying anything.
        w.loadUnsavedEntries()
      })
    }
    return () => {
      // Cancel any in-flight JSCAD evaluations so a slow eval from the
      // closing project can't write into the next project's parts state.
      cancelJscad()
      w.reset()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  // Sync URL fileId → store.
  useEffect(() => {
    if (fileId && fileId !== w.currentFileId) w.selectFile(fileId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId])

  // ----- Run JSCAD on content change (debounced) — JSCAD files only -----
  // STEP and Assembly files have `parts` populated by `loadFileForEditor` /
  // `editAssemblyContent` directly; we skip the JSCAD runner there. Run
  // errors are stashed on the store so they survive across component-level
  // re-renders without a setState-in-effect.
  const runTimerRef = useRef(null)
  useEffect(() => {
    if (isStepFile(w.currentFile)) return
    if (isAssemblyFile(w.currentFile)) return
    if (isDrawingFile(w.currentFile)) return
    if (isSketchFile(w.currentFile)) return
    if (isFeatureFile(w.currentFile)) return
    if (isCircuitFile(w.currentFile)) return
    if (isPartFile(w.currentFile)) return
    if (isEquationsFile(w.currentFile)) return
    if (isScriptFile(w.currentFile)) return
    if (isToleranceFile(w.currentFile)) return
    if (isTopoFile(w.currentFile)) return
    if (isSubdFile(w.currentFile)) return
    if (isMeshFile(w.currentFile)) return
    if (isGraphFile(w.currentFile)) return
    if (isRenderFile(w.currentFile)) return
    if (isFamilyFile(w.currentFile)) return
    if (isScheduleFile(w.currentFile)) return
    if (isViewFile(w.currentFile)) return
    if (isSheetFile(w.currentFile)) return
    if (isMEPFile(w.currentFile)) return
    if (isStairFile(w.currentFile)) return
    if (isRailingFile(w.currentFile)) return
    if (isFemFile(w.currentFile)) return
    if (isPLCFile(w.currentFile)) return
    if (isQuadMeshFile(w.currentFile)) return
    if (isPrintFile(w.currentFile)) return
    if (isCAMFile(w.currentFile)) return
    if (isBIMFile(w.currentFile)) return
    if (isAirfoilFile(w.currentFile)) return
    if (isOrbitFile(w.currentFile)) return
    if (runTimerRef.current) clearTimeout(runTimerRef.current)
    const code = w.currentFileContent
    const delay = runDebounceFor(code)
    runTimerRef.current = setTimeout(async () => {
      // Cache hit → skip the worker entirely. Same SHA-256 keyspace the
      // store's loadFileForEditor uses, so a typed-then-reverted edit short-
      // circuits back to the previous parts without re-running JSCAD.
      try {
        const key = await meshCache.hashContent(code)
        const hit = await meshCache.get(key)
        if (hit) {
          useWorkspace.getState().setPartsError(null)
          useWorkspace.getState().setLiveParts(hit.parts || [])
          return
        }
        const res = await runJscad(code)
        // Stale: a newer run superseded this one (also covers cancelJscad on
        // file-switch). The newer call's result will land separately.
        if (res?.stale) return
        if (res.error) {
          // Keep last successful parts visible; just record the error.
          useWorkspace.getState().setPartsError(res.error)
        } else {
          useWorkspace.getState().setPartsError(null)
          useWorkspace.getState().setLiveParts(res.parts || [])
          meshCache.put(key, res.parts || []).catch(() => {})
        }
      } catch (err) {
        useWorkspace.getState().setPartsError(err?.message || String(err))
      }
    }, delay)
    return () => { if (runTimerRef.current) clearTimeout(runTimerRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [w.currentFileContent, w.currentFile?.id])

  // ----- Autosave (debounced) -----
  const saveTimerRef = useRef(null)
  useEffect(() => {
    if (!w.dirty) return
    if (isStepFile(w.currentFile)) return
    // Drawings persist via updateDrawing() directly (per-action save) — the
    // generic content autosave path doesn't apply.
    if (isDrawingFile(w.currentFile)) return
    // Sketches persist via updateSketch() directly (per-action save).
    if (isSketchFile(w.currentFile)) return
    // Features persist via updateFeature() directly (per-action save).
    if (isFeatureFile(w.currentFile)) return
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => {
      w.saveFile()
    }, AUTOSAVE_MS)
    return () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [w.currentFileContent, w.dirty])

  // ----- Project thumbnail capture (debounced after save) -----
  // We dispatch via `currentViewRef` — every file-view component
  // (Renderer for 3D, SketchView/DrawingView/Schematic/PCB/Wiring/RF
  // for 2D & SVG, BIMView/FEMView/TopoView for their own canvases)
  // implements the same `snapshot({size, quality}) → Blob|null` shape
  // via useImperativeHandle. The Editor no longer branches on kind here.
  //
  // We still skip STEP files (binary, no view) and gate on a clean save
  // so we don't fire mid-edit. Importantly: we DON'T require
  // `w.parts.length > 0` anymore — that was specific to JSCAD/3D and
  // blocked thumbnails for sketches, drawings, schematics, etc.
  const thumbTimerRef = useRef(null)
  const thumbInFlightRef = useRef(false)
  useEffect(() => {
    if (!projectId) return
    if (!currentViewRef.current) return
    if (isStepFile(w.currentFile)) return
    if (w.dirty || w.saving) return
    if (thumbTimerRef.current) clearTimeout(thumbTimerRef.current)
    thumbTimerRef.current = setTimeout(async () => {
      if (thumbInFlightRef.current) return
      thumbInFlightRef.current = true
      try {
        const blob = await currentViewRef.current?.snapshot?.({ size: 512, quality: 0.7 })
        if (blob) await api.uploadProjectThumbnail(projectId, blob)
      } catch (err) {
        // Surface errors at console.warn rather than swallowing them —
        // the upload path can fail for a half-dozen reasons (network,
        // taint, decode) and silent failure made the original 3D-only
        // bug invisible for months.
        console.warn('[Editor] thumbnail capture failed', err)
      } finally {
        thumbInFlightRef.current = false
      }
    }, THUMBNAIL_DEBOUNCE_MS)
    return () => { if (thumbTimerRef.current) clearTimeout(thumbTimerRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, w.currentFile?.id, w.currentFile?.kind, w.dirty, w.saving, w.parts])

  // ----- Keyboard shortcuts -----
  useEffect(() => {
    function onKey(e) {
      const meta = e.metaKey || e.ctrlKey
      // Skip if user is typing in an input/textarea/contenteditable.
      const t = e.target
      const isTyping = t && (
        t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' ||
        t.isContentEditable || t.closest?.('.monaco-editor')
      )
      if (meta && e.key.toLowerCase() === 's') {
        e.preventDefault()
        w.saveFile()
      } else if (meta && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
      } else if (meta && e.key.toLowerCase() === 'z' && e.shiftKey) {
        // Cmd+Shift+Z → workspace-level redo (revision-restore). Skip when
        // typing in an HTML input/textarea so the browser's native redo wins.
        const inHtmlField = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')
        const inMonaco = t && t.closest?.('.monaco-editor')
        if (!inHtmlField && !inMonaco && !useWorkspace.getState().editorFocused) {
          e.preventDefault()
          useWorkspace.getState().redoRevision()
        }
      } else if (meta && e.key.toLowerCase() === 'z') {
        // Cmd+Z → workspace-level undo, but only when Monaco isn't focused
        // (Monaco gets its own buffer-undo) and we're not in a plain HTML
        // input/textarea (browser's native undo wins there).
        const inHtmlField = t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')
        const inMonaco = t && t.closest?.('.monaco-editor')
        if (!inHtmlField && !inMonaco && !useWorkspace.getState().editorFocused) {
          e.preventDefault()
          useWorkspace.getState().undoLastRevision()
        }
      } else if (!meta && !isTyping) {
        // Measure-mode shortcuts.
        if (e.key === '1') { e.preventDefault(); useWorkspace.getState().setMeasureMode('object') }
        else if (e.key === '2') { e.preventDefault(); useWorkspace.getState().setMeasureMode('face') }
        else if (e.key === '3') { e.preventDefault(); useWorkspace.getState().setMeasureMode('edge') }
        else if (e.key === '4') { e.preventDefault(); useWorkspace.getState().setMeasureMode('vertex') }
        else if (e.key === 'Escape') {
          useWorkspace.getState().clearSelectedFeatures()
          if (assemblyPickSideRef.current) {
            setAssemblyPickSideRef.current(null)
            setMatePickResultRef.current(null)
            assemblyPickSideRef.current = null
            useWorkspace.getState().setMeasureMode('object')
          }
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ----- Renderer click → store, auto-attach to chat -----
  // For assemblies we additionally route the click into the
  // selectedComponentId state so the assembly editor can react.
  const handlePick = useCallback((id) => {
    w.pickPart(id)
    if (id) w.attachPickedToChat()
    if (id && useWorkspace.getState().currentFile?.kind === 'assembly') {
      const part = useWorkspace.getState().parts.find((p) => p.id === id)
      if (part?.componentId) useWorkspace.getState().selectComponent(part.componentId)
    } else if (!id) {
      useWorkspace.getState().selectComponent(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ----- Assembly mate pick state -----
  // assemblyPickSide: 'a' | 'b' | null — which ref slot is waiting for a click.
  // matePickResult: { side, ref } resolved and handed to AssemblyEditor.
  // We keep assemblyPickSideRef so the keydown closure (mounted once) can read it.
  const [assemblyPickSide, setAssemblyPickSide] = useState(null)
  const [matePickResult, setMatePickResult] = useState(null)
  const assemblyPickSideRef = useRef(null)
  useEffect(() => { assemblyPickSideRef.current = assemblyPickSide }, [assemblyPickSide])
  // Stable setter refs so the once-mounted keydown handler can call them.
  const setAssemblyPickSideRef = useRef(setAssemblyPickSide)
  const setMatePickResultRef = useRef(setMatePickResult)

  // Renderer feature click → store. When assemblyPickSide is active, intercept
  // and convert to a mate ref instead of the normal measure-feature flow.
  const handlePickFeature = useCallback((partId, kind, featureId, shift) => {
    const side = assemblyPickSideRef.current
    if (side) {
      const ref = mateRefFromPick(partId, kind, featureId)
      if (ref) {
        setMatePickResultRef.current({ side, ref })
        setAssemblyPickSideRef.current(null)
        assemblyPickSideRef.current = null
        useWorkspace.getState().setMeasureMode('object')
      }
      return
    }
    useWorkspace.getState().pickFeature(partId, kind, featureId, shift)
  }, [])

  // ----- Top bar: editable project name -----
  const [editingName, setEditingName] = useState(false)
  const nameInputRef = useRef(null)
  function commitName() {
    setEditingName(false)
    const next = nameInputRef.current?.value?.trim()
    if (next && next !== w.project?.name) w.updateProjectName(next)
  }

  // ----- Vertical split between renderer & editor -----
  // T-L1: pointer-event based so touch devices can drag the resize handle.
  // setPointerCapture pins the move/up stream to the handle element, so the
  // gesture survives the pointer wandering outside the 1.5px-tall track.
  // Mouse behaviour is preserved (PointerEvent unifies mouse + touch + pen).
  const [splitPct, setSplitPct] = useState(60) // top half = renderer
  const draggingRef = useRef(false)
  function onSplitPointerDown(e) {
    e.preventDefault()
    draggingRef.current = true
    document.body.style.cursor = 'row-resize'
    try { e.currentTarget.setPointerCapture(e.pointerId) } catch {}
  }
  function onSplitPointerMove(e) {
    if (!draggingRef.current) return
    const container = document.getElementById('editor-center')
    if (!container) return
    const r = container.getBoundingClientRect()
    const pct = ((e.clientY - r.top) / r.height) * 100
    setSplitPct(Math.min(85, Math.max(15, pct)))
  }
  function onSplitPointerUp(e) {
    if (draggingRef.current) {
      draggingRef.current = false
      document.body.style.cursor = ''
    }
    try { e.currentTarget.releasePointerCapture(e.pointerId) } catch {}
  }

  // ----- Tab in the left rail's bottom section: Objects | Features -----
  // ----- Vertical split between FileTree & ObjectsPanel in left rail -----
  // T-L1: pointer-event handlers — same touch/mouse-unified pattern as above.
  const [leftSplitPct, setLeftSplitPct] = useState(60) // top = FileTree
  const leftDraggingRef = useRef(false)
  function onLeftSplitPointerDown(e) {
    e.preventDefault()
    leftDraggingRef.current = true
    document.body.style.cursor = 'row-resize'
    try { e.currentTarget.setPointerCapture(e.pointerId) } catch {}
  }
  function onLeftSplitPointerMove(e) {
    if (!leftDraggingRef.current) return
    const container = document.getElementById('editor-left')
    if (!container) return
    const r = container.getBoundingClientRect()
    const pct = ((e.clientY - r.top) / r.height) * 100
    setLeftSplitPct(Math.min(85, Math.max(20, pct)))
  }
  function onLeftSplitPointerUp(e) {
    if (leftDraggingRef.current) {
      leftDraggingRef.current = false
      document.body.style.cursor = ''
    }
    try { e.currentTarget.releasePointerCapture(e.pointerId) } catch {}
  }

  const [showShare, setShowShare] = useState(false)
  // Unified right drawer — canonical state lives in the workspace store so
  // activity, chat, and git all share one open/tab pair.
  const rightDrawer = useWorkspace((s) => s.rightDrawer)
  const openRightDrawer = useWorkspace((s) => s.openRightDrawer)
  const closeRightDrawer = useWorkspace((s) => s.closeRightDrawer)
  const setRightDrawerTab = useWorkspace((s) => s.setRightDrawerTab)
  // Backward-compat: seed "chat" tab from the old localStorage key so repeat
  // visitors who had chat open still see it open. One-time migration.
  useEffect(() => {
    const wasOpen = !readCollapsed(CHAT_COLLAPSE_KEY, false)
    if (wasOpen && !rightDrawer.open) {
      openRightDrawer('chat')
    }
    // intentionally run only once at mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  // Keep the old git collapsed key around (read-only compat for tests that
  // probe GIT_COLLAPSE_KEY) — we no longer write it.
  void GIT_COLLAPSE_KEY
  // ----- Responsive drawer state -----
  // T-L1: on < md (phone) the file-tree and chat collapse into off-canvas
  // drawers; on md ≤ width < lg (tablet) the file-tree is a drawer and chat is
  // inline-collapsible; ≥ lg both panes are inline (unchanged desktop layout).
  // These drawer-open booleans only have effect at < lg widths; the inline
  // panes always render at ≥ lg via Tailwind utility classes.
  const [treeDrawerOpen, setTreeDrawerOpen] = useState(false)
  const [chatDrawerOpen, setChatDrawerOpen] = useState(false)
  // Route-change auto-close: any time the current file/project changes,
  // collapse any open drawers so the user lands cleanly on the new canvas.
  useEffect(() => {
    setTreeDrawerOpen(false)
    setChatDrawerOpen(false)
  }, [projectId, w.currentFileId])
  // Esc closes drawers (highest priority — runs before the workspace
  // measure-mode Escape handler below). We attach a capture-phase listener
  // so it pre-empts the bubble-phase listener registered in the keyboard-
  // shortcuts effect above.
  useEffect(() => {
    if (!treeDrawerOpen && !chatDrawerOpen) return
    function onEsc(e) {
      if (e.key !== 'Escape') return
      if (treeDrawerOpen) { setTreeDrawerOpen(false); e.stopPropagation() }
      if (chatDrawerOpen) { setChatDrawerOpen(false); e.stopPropagation() }
    }
    window.addEventListener('keydown', onEsc, true)
    return () => window.removeEventListener('keydown', onEsc, true)
  }, [treeDrawerOpen, chatDrawerOpen])
  // Body scroll lock while a drawer is open (mobile only — at ≥ lg the
  // drawers are unreachable anyway).
  useEffect(() => {
    if (!treeDrawerOpen && !chatDrawerOpen) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [treeDrawerOpen, chatDrawerOpen])
  // Focus trap: when a drawer opens, send focus into it; on close, return
  // focus to the document body so the next Tab lands somewhere sane. We
  // pick the first focusable child of the drawer container.
  const treeDrawerRef = useRef(null)
  const chatDrawerRef = useRef(null)
  const treeOpenerRef = useRef(null)
  const chatOpenerRef = useRef(null)
  useEffect(() => {
    if (!treeDrawerOpen) return
    const root = treeDrawerRef.current
    if (!root) return
    const focusable = root.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
    focusable?.focus?.()
    function trap(e) {
      if (e.key !== 'Tab') return
      const items = root.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
      if (!items.length) return
      const first = items[0]
      const last = items[items.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    root.addEventListener('keydown', trap)
    return () => {
      root.removeEventListener('keydown', trap)
      treeOpenerRef.current?.focus?.()
    }
  }, [treeDrawerOpen])
  useEffect(() => {
    if (!chatDrawerOpen) return
    const root = chatDrawerRef.current
    if (!root) return
    const focusable = root.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
    focusable?.focus?.()
    function trap(e) {
      if (e.key !== 'Tab') return
      const items = root.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
      if (!items.length) return
      const first = items[0]
      const last = items[items.length - 1]
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus() }
    }
    root.addEventListener('keydown', trap)
    return () => {
      root.removeEventListener('keydown', trap)
      chatOpenerRef.current?.focus?.()
    }
  }, [chatDrawerOpen])
  // Thumbnail refresh (user-triggered "Refresh thumbnail" button in the header).
  const [thumbRefreshing, setThumbRefreshing] = useState(false)
  const [thumbToast, setThumbToast] = useState(null)
  const thumbToastTimerRef = useRef(null)
  const captureSnapshotFn = useCallback(async (opts) => {
    return currentViewRef.current?.snapshot?.(opts || { size: 512, quality: 0.7 }) ?? null
  }, [])
  const { cloudEnabled } = useCloudConfig()

  const editorErrors = useMemo(
    () => w.partsError ? [w.partsError] : [],
    [w.partsError],
  )
  const saveStatus = w.saving ? 'saving' : w.dirty ? 'dirty' : 'saved'

  // Visibility set for the current file (may be undefined).
  const hiddenIds = useMemo(() => {
    return w.hiddenPartIds.get(w.currentFileId) || new Set()
  }, [w.hiddenPartIds, w.currentFileId])

  // Per-part topologies. Lazy: nothing computes until a consumer (measure
  // tool, FeatureInspector, distance chip) calls `.get(id)`. The shape is
  // Map-compatible so all callers stay unchanged.
  const topologies = useMemo(() => getTopologyLazy(w.parts), [w.parts])

  const handleImportStep = useCallback(async (browserFile, parentId) => {
    if (!browserFile) return
    await w.uploadAsset(browserFile, { kind: 'step', parent_id: parentId || null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const stepFile = isStepFile(w.currentFile)
  const assemblyFile = isAssemblyFile(w.currentFile)

  // S2 instancing: derive the raw assembly component list so Renderer's
  // instancing planner can group identical parts into batched draw calls.
  // parseAssembly is cheap (JSON.parse + normalization); memoised off content.
  // Only computed when the current file is an assembly.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const assemblyComponents = useMemo(() => {
    if (!assemblyFile || !w.currentFileContent) return null
    try {
      const parsed = parseAssembly(w.currentFileContent)
      return parsed.components || null
    } catch {
      return null
    }
  }, [assemblyFile, w.currentFileContent])
  const drawingFile = isDrawingFile(w.currentFile)
  const sketchFile = isSketchFile(w.currentFile)
  const featureFile = isFeatureFile(w.currentFile)
  const circuitFile = isCircuitFile(w.currentFile)
  const partFile = isPartFile(w.currentFile)
  const materialFile = isMaterialFile(w.currentFile)
  const equationsFile = isEquationsFile(w.currentFile)
  const scriptFile = isScriptFile(w.currentFile)
  const toleranceFile = isToleranceFile(w.currentFile)
  const topoFile = isTopoFile(w.currentFile)
  const graphFile = isGraphFile(w.currentFile)
  const renderFile = isRenderFile(w.currentFile)
  const familyFile = isFamilyFile(w.currentFile)
  const scheduleFile = isScheduleFile(w.currentFile)
  const viewFile = isViewFile(w.currentFile)
  const sheetFile = isSheetFile(w.currentFile)
  const mepFile = isMEPFile(w.currentFile)
  const stairFile = isStairFile(w.currentFile)
  const railingFile = isRailingFile(w.currentFile)
  const femFile = isFemFile(w.currentFile)
  const sectionFile   = isSectionFile(w.currentFile)
  const plcFile       = isPLCFile(w.currentFile)
  const quadMeshFile  = isQuadMeshFile(w.currentFile)

  // Build a THREE.BufferGeometry from the current parts to pass into FEMView
  // so DeformedShapeOverlay can render the morphed surface (instead of a proxy
  // point cloud). We only do this when a .fem file is open and parts are loaded.
  // extractDisplayGeometryFromParts returns a plain { positions, indices } object;
  // we wrap it in a minimal BufferGeometry-compatible shape that FEMDeformedShape
  // expects (it reads .attributes.position.array and .index.array).
  const femDisplayGeometry = useMemo(() => {
    if (!femFile) return null
    const desc = extractDisplayGeometryFromParts(w.parts)
    if (!desc) return null
    return {
      isBufferGeometry: true,
      attributes: { position: { array: desc.positions } },
      index: desc.indices ? { array: desc.indices } : null,
    }
  }, [femFile, w.parts])

  const printFile = isPrintFile(w.currentFile)
  const camFile = isCAMFile(w.currentFile)
  const bimFile = isBIMFile(w.currentFile)
  const airfoilFile = isAirfoilFile(w.currentFile)
  const orbitFile = isOrbitFile(w.currentFile)
  // T-116: plain-text / code files — matched by extension via editorModes.js.
  // Must be checked AFTER all dedicated-extension checks above so that e.g.
  // a .json family file is not accidentally grabbed by the plain editor.
  const textCodeFile = isTextCodeFile(w.currentFile)
  // Resolver used by FeatureView to fetch sketch contents on demand. We
  // re-read the latest file content rather than relying on the cached
  // sketch parse from the workspace store (which may be stale if the user
  // edited the sketch in another tab).
  const featureSketchLoader = useCallback(async (path) => {
    if (!projectId) return ''
    const file = w.files.find((f) => {
      // Reconstruct the file's path lazily.
      if (!f) return false
      if (f.kind === 'folder') return false
      // Walk to root.
      const byId = new Map(w.files.map((x) => [x.id, x]))
      const parts = []
      let cur = f
      let safety = 0
      while (cur && safety++ < 64) {
        parts.unshift(cur.name)
        if (!cur.parent_id) break
        cur = byId.get(cur.parent_id)
      }
      return ('/' + parts.join('/')) === path
    })
    if (!file) return ''
    try {
      const fresh = await api.getFile(projectId, file.id)
      return fresh.content || ''
    } catch {
      return ''
    }
  }, [projectId, w.files])
  // Stable loadParts callback for SketchView's 3D backdrop.
  const sketchLoadParts = useCallback(
    (fileId) => projectId ? loadFilePartsForProject(projectId, fileId) : Promise.resolve([]),
    [projectId]
  )

  // Configurations / variants — derive the configuration list for the
  // open file from the relevant parsed-* slot in the workspace store. The
  // dropdown is hidden whenever the list is empty. Toggle the
  // ConfigurationsPanel (per-row editor) via a local UI flag.
  const fileConfigurations = useMemo(() => {
    if (partFile && w.currentPart) {
      return {
        list: Array.isArray(w.currentPart.configurations) ? w.currentPart.configurations : [],
        defaultId: w.currentPart.default_config || '',
      }
    }
    if (featureFile && w.currentFeature) {
      return {
        list: Array.isArray(w.currentFeature.configurations) ? w.currentFeature.configurations : [],
        defaultId: w.currentFeature.default_config || '',
      }
    }
    if (sketchFile && w.parsedSketch) {
      return {
        list: Array.isArray(w.parsedSketch.configurations) ? w.parsedSketch.configurations : [],
        defaultId: w.parsedSketch.default_config || '',
      }
    }
    return { list: [], defaultId: '' }
  }, [partFile, featureFile, sketchFile, w.currentPart, w.currentFeature, w.parsedSketch])

  // True when the current sketch has at least one closed loop — the "Build 3D"
  // dropdown is only shown when there's something to extrude.
  const sketchHasClosedLoops = useMemo(() => {
    if (!sketchFile || !w.parsedSketch) return false
    try {
      return _internalLoops(w.parsedSketch).length > 0
    } catch {
      return false
    }
  }, [sketchFile, w.parsedSketch])

  // Resolve the picked-or-default config id for the open file.
  const activeConfigId = useMemo(() => {
    if (!w.currentFileId) return ''
    const picked = w.currentConfigByFile?.[w.currentFileId] || ''
    if (picked && fileConfigurations.list.find((c) => c.id === picked)) return picked
    if (fileConfigurations.defaultId
      && fileConfigurations.list.find((c) => c.id === fileConfigurations.defaultId)) {
      return fileConfigurations.defaultId
    }
    return fileConfigurations.list[0]?.id || ''
  }, [w.currentFileId, w.currentConfigByFile, fileConfigurations])

  const [configsPanelOpen, setConfigsPanelOpen] = useState(false)
  const showConfigsHeader = (partFile || featureFile || sketchFile)

  // Helper: persist edits to the configurations array back into the open
  // file's content, via the same per-kind update path the editor uses for
  // direct field tweaks. The host slots already serialize on save.
  const handleConfigurationsChange = useCallback((next) => {
    if (partFile) {
      w.updatePart({
        configurations: next.configurations,
        default_config: next.default_config,
      })
    } else if (featureFile) {
      w.updateFeature((tree) => ({
        ...tree,
        configurations: next.configurations,
        default_config: next.default_config,
      }))
    } else if (sketchFile) {
      w.updateSketch((sk) => ({
        ...sk,
        configurations: next.configurations,
        default_config: next.default_config,
      }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [partFile, featureFile, sketchFile])

  // Drawing-only state: per-source topologies (computed lazily once per
  // source's parts) + the active dimension tool + the SVG ref for export.
  const [drawingTool, setDrawingTool] = useState('pointer')
  const drawingSvgRef = useRef(null)
  const drawingTopologies = useMemo(() => {
    if (!drawingFile) return new Map()
    const out = new Map()
    for (const [fid, parts] of w.drawingSourceParts.entries()) {
      out.set(fid, getTopologyLazy(parts))
    }
    return out
  }, [drawingFile, w.drawingSourceParts])

  return (
    <div className="h-screen flex flex-col bg-ink-950 text-ink-100 overflow-hidden">
      {/* ---------- Top bar ---------- */}
      <header className="flex items-center gap-2 sm:gap-3 h-12 px-2 sm:px-3 border-b border-ink-800 bg-ink-900 flex-shrink-0">
        <button
          type="button"
          onClick={() => navigate('/projects')}
          className="p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300"
          title="Back to projects"
          aria-label="Back to projects"
        >
          <ArrowLeft size={15} aria-hidden="true" />
        </button>
        {/* T-L1: file-tree drawer toggle — only visible < lg where the inline
            aside is hidden. Opens the off-canvas file-tree drawer. */}
        <button
          type="button"
          ref={treeOpenerRef}
          onClick={() => setTreeDrawerOpen(true)}
          className="lg:hidden p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300"
          title="Open file tree"
          aria-label="Open file tree"
          aria-expanded={treeDrawerOpen}
          aria-controls="editor-tree-drawer"
        >
          <PanelLeftOpen size={15} aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => navigate('/')}
          className="flex items-center hover:opacity-80 transition-opacity"
          title="Kerf home"
          aria-label="Kerf home"
        >
          <LogoWordmark />
        </button>
        <span className="text-ink-700">/</span>
        {editingName ? (
          <input
            key={w.project?.id}
            ref={nameInputRef}
            defaultValue={w.project?.name || ''}
            autoFocus
            onBlur={commitName}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitName()
              if (e.key === 'Escape') { setEditingName(false) }
            }}
            className="bg-ink-850 border border-kerf-300/50 rounded px-2 py-0.5 text-sm text-ink-100 outline-none w-64"
          />
        ) : (
          <button
            type="button"
            onClick={() => setEditingName(true)}
            className="text-sm text-ink-200 hover:text-kerf-300 px-1 rounded"
            title="Click to rename"
          >
            {w.project?.name || 'Loading…'}
          </button>
        )}

        <div className="flex-1" />

        <SaveIndicator status={saveStatus} />

        {/* ---------- T-L2 Priority+ icon row ----------
            Visibility classes (priority highest → lowest):
              - Undo / Redo:         always visible (P1, primary editing).
              - Export:              visible ≥ md (P2, < 768px → overflow).
              - Refresh thumbnail:   visible ≥ xl (P3, < 1280px → overflow).
              - Publish:             always visible (cloud CTA).
              - Share:               visible ≥ lg (P4, < 1024px → overflow).
              - Chat toggle:         always visible (primary navigation).
            At ≥ xl every action is inline; the overflow More menu auto-
            hides (`xl:hidden` inside TopBarMoreMenu). Down to 768px the
            inline row never overflows. Every icon-only button has an
            explicit `aria-label`.
        */}
        <button
          type="button"
          onClick={() => w.undoLastRevision()}
          disabled={!w.currentFileId}
          title="Undo (Cmd+Z)"
          aria-label="Undo"
          className="inline-flex p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300 disabled:opacity-40 disabled:hover:bg-transparent"
        >
          <Undo2 size={14} aria-hidden="true" />
        </button>
        <button
          type="button"
          onClick={() => w.redoRevision()}
          disabled={!w.currentFileId || (w.redoStack?.length ?? 0) === 0}
          title="Redo (Cmd+Shift+Z)"
          aria-label="Redo"
          className="inline-flex p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300 disabled:opacity-40 disabled:hover:bg-transparent"
        >
          <Redo2 size={14} aria-hidden="true" />
        </button>
        {/* History, Activity, and Git have moved into the unified right
            drawer tabs (Chat / Activity / Git / History). The topbar
            stays focused on undo/redo and primary actions. */}

        {/* T-L2 Export: visible ≥ md; collapses into overflow at < md */}
        <div className="hidden md:block">
          <ExportButton onCaptureHero={() => rendererRef.current?.captureHeroShot?.({})} />
        </div>

        {cloudEnabled && w.project && (
          <>
            <button
              type="button"
              disabled={thumbRefreshing || !currentViewRef.current}
              title="Refresh thumbnail from current view"
              aria-label="Refresh thumbnail"
              onClick={async () => {
                if (thumbRefreshing || !projectId) return
                setThumbRefreshing(true)
                try {
                  const blob = await captureSnapshotFn({ size: 512, quality: 0.7 })
                  if (blob) {
                    await api.uploadProjectThumbnail(projectId, blob)
                    if (thumbToastTimerRef.current) clearTimeout(thumbToastTimerRef.current)
                    setThumbToast('Thumbnail updated')
                    thumbToastTimerRef.current = setTimeout(() => setThumbToast(null), 3000)
                  }
                } catch (err) {
                  console.warn('[Editor] manual thumbnail refresh failed', err)
                } finally {
                  setThumbRefreshing(false)
                }
              }}
              className="hidden xl:inline-flex p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300 disabled:opacity-40 disabled:hover:bg-transparent"
            >
              {thumbRefreshing
                ? <Loader2 size={14} className="animate-spin" aria-hidden="true" />
                : <RotateCcw size={14} aria-hidden="true" />}
            </button>
            {thumbToast && (
              <span className="hidden sm:inline text-[11px] font-mono text-emerald-400 whitespace-nowrap">
                {thumbToast}
              </span>
            )}
            <PublishButton project={w.project} captureSnapshot={captureSnapshotFn} />
          </>
        )}

        {/* T-L2 Share: visible ≥ lg; collapses into overflow at < lg */}
        <button
          type="button"
          onClick={() => setShowShare(true)}
          disabled={!projectId}
          aria-label="Share project"
          className="hidden lg:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-kerf-300 text-ink-950 text-xs font-medium hover:bg-kerf-200 disabled:opacity-40"
        >
          <Share2 size={12} aria-hidden="true" />
          Share
        </button>

        <button
          type="button"
          ref={chatOpenerRef}
          onClick={() => {
            // On < lg we still use the off-canvas chat drawer for mobile.
            if (typeof window !== 'undefined' && window.matchMedia
                && !window.matchMedia('(min-width: 1024px)').matches) {
              setChatDrawerOpen((v) => !v)
            } else if (rightDrawer.open && rightDrawer.tab === 'chat') {
              closeRightDrawer()
            } else {
              setRightDrawerTab('chat')
            }
          }}
          title={rightDrawer.open && rightDrawer.tab === 'chat' ? 'Hide chat' : 'Open chat'}
          aria-label={rightDrawer.open && rightDrawer.tab === 'chat' ? 'Hide chat panel' : 'Open chat panel'}
          aria-expanded={rightDrawer.open && rightDrawer.tab === 'chat' || chatDrawerOpen}
          className={`inline-flex p-1.5 rounded hover:bg-ink-800 ${rightDrawer.open && rightDrawer.tab === 'chat' ? 'text-kerf-300' : 'text-ink-300 hover:text-kerf-300'}`}
        >
          {rightDrawer.open && rightDrawer.tab === 'chat'
            ? <PanelRightClose size={14} aria-hidden="true" />
            : <PanelRightOpen size={14} aria-hidden="true" />}
        </button>

        {/* ---------- T-L2 Overflow menu ----------
            Priority+ pattern: actions that don't fit inline at narrower
            viewports are mirrored here.
              - Export:            hidden < md  → menuitem
              - Share:             hidden < lg  → menuitem
              - Refresh thumbnail: hidden < xl  → menuitem (cloud only)
            The TopBarMoreMenu wrapper is `xl:hidden` so at ≥1280px all
            actions are inline and the More button disappears. */}
        <TopBarMoreMenu>
          {/* Export — visible in overflow at < md */}
          <button
            type="button"
            role="menuitem"
            onClick={() => { /* Export is handled inline — this entry surfaces it at < md. Future iteration: wire to ExportButton imperative API. */ }}
            className="md:hidden w-full flex items-center gap-2 px-3 py-1.5 text-xs text-ink-100 hover:bg-ink-700 text-left"
          >
            <FileDown size={12} className="text-ink-400" aria-hidden="true" />
            <span>Export</span>
          </button>
          {/* Share — visible in overflow at < lg */}
          <button
            type="button"
            role="menuitem"
            disabled={!projectId}
            onClick={() => setShowShare(true)}
            className="lg:hidden w-full flex items-center gap-2 px-3 py-1.5 text-xs text-ink-100 hover:bg-ink-700 text-left disabled:opacity-40"
          >
            <Share2 size={12} className="text-ink-400" aria-hidden="true" />
            <span>Share</span>
          </button>
          {/* Refresh thumbnail — visible in overflow at < xl (cloud only) */}
          {cloudEnabled && w.project && (
            <button
              type="button"
              role="menuitem"
              disabled={thumbRefreshing || !currentViewRef.current}
              onClick={async () => {
                if (thumbRefreshing || !projectId) return
                setThumbRefreshing(true)
                try {
                  const blob = await captureSnapshotFn({ size: 512, quality: 0.7 })
                  if (blob) {
                    await api.uploadProjectThumbnail(projectId, blob)
                    if (thumbToastTimerRef.current) clearTimeout(thumbToastTimerRef.current)
                    setThumbToast('Thumbnail updated')
                    thumbToastTimerRef.current = setTimeout(() => setThumbToast(null), 3000)
                  }
                } catch (err) {
                  console.warn('[Editor] manual thumbnail refresh failed', err)
                } finally {
                  setThumbRefreshing(false)
                }
              }}
              className="xl:hidden w-full flex items-center gap-2 px-3 py-1.5 text-xs text-ink-100 hover:bg-ink-700 text-left disabled:opacity-40"
            >
              {thumbRefreshing
                ? <Loader2 size={12} className="animate-spin text-ink-400" aria-hidden="true" />
                : <RotateCcw size={12} className="text-ink-400" aria-hidden="true" />}
              <span>Refresh thumbnail</span>
            </button>
          )}
        </TopBarMoreMenu>

        <EditorUserMenu user={user} />
      </header>

      {/* ---------- Main grid ----------
          T-L1 responsive shell:
          - ≥ lg: 3-pane grid `240px 1fr 380px` (chat collapsed: `240px 1fr`).
            Uses an inline `style` for grid-template-columns because Tailwind's
            JIT can NOT emit utility classes from dynamic template strings —
            the previous `lg:grid-cols-[${...}]` interpolation silently lost
            the class and the layout collapsed to a single full-width column.
          - md ≤ width < lg: single-column flex (canvas only); file-tree is a
            drawer; the inline chat pane is hidden — chat is reachable via the
            top-bar chat toggle which on < lg switches semantics to "open chat
            drawer". The chat-collapsed state and the chat-drawer-open state
            are kept separate so neither interferes with the other.
          - < md: same as md — canvas only, both panes as drawers.
          The `relative` here anchors the `fixed`-positioned drawers below. */}
      {/* The right drawer is an overlay — grid is always file-tree + canvas.
          The CSS rule in index.css sets 240px 1fr at ≥ lg. */}
      <div
        className="flex-1 grid min-h-0 relative grid-cols-1 kerf-editor-grid"
      >
        {/* Left: file tree (top) + objects panel (bottom).
            ≥ lg: inline aside, occupies the first grid column.
            < lg: hidden (drawer instance below renders the same content). */}
        <aside id="editor-left" className="hidden lg:flex border-r border-ink-800 min-h-0 flex-col overflow-hidden">
          <div style={{ height: `${leftSplitPct}%` }} className="min-h-0">
            <FileTree
              files={w.files}
              currentFileId={w.currentFileId}
              onSelect={(id) => w.selectFile(id)}
              onCreate={(parentId, kind) => w.createFile(parentId, kind)}
              onRename={(id, name) => w.renameFile(id, name)}
              onDelete={(id) => {
                if (confirm('Delete this file?')) w.deleteFile(id)
              }}
              onImportStep={handleImportStep}
            />
          </div>
          <div
            role="separator"
            aria-orientation="horizontal"
            aria-label="Resize file tree and objects panel"
            onPointerDown={onLeftSplitPointerDown}
            onPointerMove={onLeftSplitPointerMove}
            onPointerUp={onLeftSplitPointerUp}
            onPointerCancel={onLeftSplitPointerUp}
            className="h-1.5 bg-ink-800 hover:bg-kerf-300/40 cursor-row-resize flex-shrink-0 transition-colors touch-none"
            style={{ touchAction: 'none' }}
            title="Drag to resize"
          />
          <div style={{ height: `${100 - leftSplitPct}%` }} className="min-h-0 flex flex-col">
            {circuitFile ? (
              <CircuitComponentsPanel
                selectedRefdes={w.selectedCircuitRefdes}
                selectedNet={w.selectedCircuitNet}
                onSelectRefdes={(r) => w.selectCircuitRefdes(r)}
                onSelectNet={(n) => w.selectCircuitNet(n)}
              />
            ) : (
              <div className="flex-1 min-h-0">
                <ObjectsPanel
                  parts={w.parts}
                  hiddenIds={hiddenIds}
                  selectedId={w.pickedPart?.part_id}
                  onToggleVisibility={(id) => w.togglePartVisibility(w.currentFileId, id)}
                  onSelect={(id) => w.pickPart(id)}
                  onIsolate={(id) => w.isolatePart(w.currentFileId, id)}
                  onShowAll={() => w.showAllParts(w.currentFileId)}
                  onRecolorPart={(id, rgb) => w.recolorPart(id, rgb)}
                  onMovePart={(id, d) => w.movePart(id, d)}
                  onSetPartPosition={(id, p) => w.setPartPosition(id, p)}
                  isStepFile={stepFile}
                />
              </div>
            )}
          </div>
        </aside>

        {/* Center: renderer + editor (or full-bleed DrawingView/SketchView for special kinds) */}
        <main id="editor-center" className="flex flex-col min-w-0 min-h-0 relative">
          {/* Crash-recovery banner — shown when IDB has unflushed entries from a
              previous session. The user chooses Restore or Discard; no silent
              auto-replay. Separate from ConflictBanner (T-302 live OCC conflicts). */}
          <UnsavedRestoreBanner />
          {/* Configurations / variants — small chrome above the editor that
              picks the active config for the open file. Only rendered for
              file kinds that support configurations (Part / Feature /
              Sketch). The "Configure variants" button toggles the
              ConfigurationsPanel slide-out. */}
          {showConfigsHeader && (fileConfigurations.list.length > 0 || configsPanelOpen) && (
            <div className="flex items-center gap-2 border-b border-ink-800 bg-ink-900/40 px-3 py-1.5 text-[11px]">
              {fileConfigurations.list.length > 0 ? (
                <>
                  <span className="text-ink-500 uppercase tracking-wider text-[9px]">Config</span>
                  <select
                    value={activeConfigId}
                    onChange={(e) => w.setCurrentConfig(w.currentFileId, e.target.value)}
                    className="bg-ink-950 border border-ink-800 rounded px-2 py-1 text-[11px] text-ink-100 outline-none focus:border-kerf-300/60"
                  >
                    {fileConfigurations.list.map((cfg) => (
                      <option key={cfg.id} value={cfg.id}>
                        {cfg.label}{cfg.id === fileConfigurations.defaultId ? '  ★' : ''}
                      </option>
                    ))}
                  </select>
                </>
              ) : (
                <span className="text-ink-500 italic">No configurations defined.</span>
              )}
              <div className="flex-1" />
              <button
                type="button"
                onClick={() => setConfigsPanelOpen((v) => !v)}
                className={`inline-flex items-center gap-1.5 px-2 py-1 rounded border text-[10px] ${
                  configsPanelOpen
                    ? 'bg-kerf-300/10 border-kerf-300/60 text-kerf-300'
                    : 'bg-ink-900 border-ink-800 text-ink-300 hover:text-kerf-300 hover:border-kerf-300/40'
                }`}
                title="Edit configurations"
              >
                <SlidersHorizontal size={11} />
                Configure variants
              </button>
            </div>
          )}
          {showConfigsHeader && fileConfigurations.list.length === 0 && !configsPanelOpen && (
            <div className="flex items-center justify-end border-b border-ink-800 bg-ink-900/40 px-3 py-1 text-[10px]">
              <button
                type="button"
                onClick={() => setConfigsPanelOpen(true)}
                className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-ink-500 hover:text-kerf-300"
                title="Add per-file parameter overrides"
              >
                <SlidersHorizontal size={10} />
                Add variants
              </button>
            </div>
          )}
          {configsPanelOpen && showConfigsHeader && (
            <ConfigurationsPanel
              configurations={fileConfigurations.list}
              defaultConfig={fileConfigurations.defaultId}
              onChange={handleConfigurationsChange}
              onClose={() => setConfigsPanelOpen(false)}
            />
          )}
          {partFile ? (
            <div className="flex-1 min-h-0 relative">
              <LibraryEditor />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : materialFile ? (
            <div className="flex-1 min-h-0 relative">
              <MaterialEditor />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : equationsFile ? (
            <div className="flex-1 min-h-0 relative">
              <EquationsEditor />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : toleranceFile ? (
            <div className="flex-1 min-h-0 relative">
              <ToleranceView
                content={w.currentFileContent}
                fileName={w.currentFile?.name}
                projectId={projectId}
                fileId={fileId}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : graphFile ? (
            <div className="flex-1 min-h-0 relative">
              <GraphEditor
                content={w.currentFileContent}
                fileName={w.currentFile?.name}
                onContentChange={(v) => w.editContent(v)}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : familyFile ? (
            <div className="flex-1 min-h-0 relative">
              <FamilyEditor
                content={w.currentFileContent}
                fileName={w.currentFile?.name}
                onContentChange={(v) => w.editContent(v)}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : scheduleFile ? (
            <div className="flex-1 min-h-0 relative">
              <ScheduleEditor
                content={w.currentFileContent}
                fileName={w.currentFile?.name}
                onContentChange={(v) => w.editContent(v)}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : viewFile ? (
            <div className="flex-1 min-h-0 relative">
              <ViewEditor
                content={w.currentFileContent}
                fileName={w.currentFile?.name}
                onContentChange={(v) => w.editContent(v)}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : mepFile ? (
            <div className="flex-1 min-h-0 relative">
              <MEPView
                content={w.currentFileContent}
                fileName={w.currentFile?.name}
                onContentChange={(v) => w.editContent(v)}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : sheetFile ? (
            <div className="flex-1 min-h-0 relative">
              <SheetEditor
                content={w.currentFileContent}
                fileName={w.currentFile?.name}
                onContentChange={(v) => w.editContent(v)}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : renderFile ? (
            <div className="flex-1 min-h-0 relative">
              <RenderView
                content={(() => { try { return JSON.parse(w.currentFileContent || '{}') } catch { return null } })()}
                fileName={w.currentFile?.name}
                onContentChange={(v) => w.editContent(JSON.stringify(v, null, 2))}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : topoFile ? (
            <div className="flex-1 min-h-0 relative">
              <TopoView
                viewRef={currentViewRef}
                content={w.currentFileContent}
                fileName={w.currentFile?.name}
                projectId={projectId}
                fileId={w.currentFileId}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : camFile ? (
            <div className="flex-1 min-h-0 overflow-y-auto p-3">
              <CAMView
                viewRef={currentViewRef}
                file={w.currentFile}
                projectId={projectId}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : bimFile ? (
            <div className="flex-1 min-h-0 relative">
              <BIMFileView
                viewRef={currentViewRef}
                content={w.currentFileContent}
                fileName={w.currentFile?.name}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : airfoilFile ? (
            <AirfoilFileView
              viewRef={currentViewRef}
              content={w.currentFileContent}
              fileName={w.currentFile?.name}
            />
          ) : orbitFile ? (
            <OrbitFileView
              viewRef={currentViewRef}
              content={w.currentFileContent}
              fileName={w.currentFile?.name}
            />
          ) : printFile ? (
            <div className="flex-1 min-h-0 relative">
              <PrintSliceView
                content={w.currentFileContent}
                fileName={w.currentFile?.name}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : sketchFile && w.parsedSketch ? (
            <div className="flex-1 min-h-0 relative flex flex-col">
              <div className="flex items-center gap-2 border-b border-ink-800 bg-ink-900/40 px-3 py-1.5">
                <button
                  type="button"
                  onClick={() => w.createFeatureFromSketch(w.currentFileId)}
                  className="inline-flex items-center gap-1.5 px-2 py-1 rounded bg-kerf-300/10 border border-kerf-300/30 text-kerf-200 hover:bg-kerf-300/20 text-xs"
                >
                  <Plus size={11} />
                  <Box size={11} />
                  New feature from sketch
                </button>
                <Build3DDropdown
                  sketch={w.parsedSketch}
                  sketchName={w.currentFile?.name || 'untitled.sketch'}
                  disabled={!sketchHasClosedLoops}
                  onBuild={(op, params) => w.createJscadFromSketch(w.currentFileId, op, params)}
                />
              </div>
              <div className="flex-1 min-h-0 relative">
                <SketchView
                  viewRef={currentViewRef}
                  sketch={w.parsedSketch}
                  files={w.files}
                  onChange={(next) => w.updateSketch(() => next)}
                  onSolved={(next, status, dof, conflicts) =>
                    w.setSketchSolved(next, status, dof, conflicts)}
                  status={w.sketchStatus}
                  dofCount={w.sketchDof}
                  conflicts={w.sketchConflicts}
                  loadParts={sketchLoadParts}
                />
              </div>
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : circuitFile ? (
            <div className="flex-1 min-h-0 relative">
              <CircuitEditor viewRef={currentViewRef} />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : featureFile && w.currentFeature ? (
            <div className="flex-1 min-h-0 relative">
              <FeatureView
                parsedFeature={w.currentFeature}
                files={w.files}
                onChangeTree={(next) => w.updateFeature(() => next)}
                loadSketchContent={featureSketchLoader}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : sectionFile ? (
            <div className="flex-1 min-h-0 relative">
              <SectionView
                viewRef={currentViewRef}
                parsedFeature={w.currentFeature || { features: [] }}
                edgeSegments={null}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : drawingFile && w.parsedDrawing ? (
            <div className="flex-1 min-h-0 relative">
              <DrawingView
                ref={drawingSvgRef}
                viewRef={currentViewRef}
                drawing={w.parsedDrawing}
                partsByFileId={w.drawingSourceParts}
                topologiesByFileId={drawingTopologies}
                selectedDimensionId={w.selectedDimensionId}
                onSelectDimension={(id) => w.selectDimension(id)}
                selectedAnnotationId={w.selectedAnnotationId}
                onSelectAnnotation={(id) => w.selectAnnotation(id)}
                tool={drawingTool}
                onAddDimension={(payload) => w.addDimension(payload)}
                onDeleteDimension={(id) => w.deleteDimension(id)}
                onAddAnnotation={(payload) => w.addAnnotation(payload)}
                onUpdateAnnotation={(id, patch) => w.updateAnnotation(id, patch)}
                onDeleteAnnotation={(id) => w.removeAnnotation(id)}
                onAddCenterline={(payload) => w.addCenterline(payload)}
                onAddBreak={(payload) => w.addBreak(payload)}
                onAddSymbol={(payload) => w.addSymbol(payload)}
                onSelectSheet={(idx) => w.selectSheet(idx)}
                onAddSheet={() => w.addSheet({})}
                onRemoveSheet={(idx) => w.removeSheet(idx)}
                onResetTool={() => setDrawingTool('pointer')}
              />
              <DrawingToolbar
                tool={drawingTool}
                onTool={setDrawingTool}
                showSheetActions
                onAddSheet={() => w.addSheet({})}
              />
              <DrawingPropertiesPanel
                drawing={w.parsedDrawing}
                files={w.files}
                selectedAnnotationId={w.selectedAnnotationId}
                selectedDimensionId={w.selectedDimensionId}
                onUpdateAnnotation={(id, patch) => w.updateAnnotation(id, patch)}
                onDeleteAnnotation={(id) => w.removeAnnotation(id)}
                onUpdateDimension={(id, patch) => w.updateDimension(id, patch)}
                onDeleteDimension={(id) => w.deleteDimension(id)}
                onUpdateFrame={(patch) => w.updateFrame(patch)}
                onAddView={(payload) => w.addView(payload)}
                onUpdateView={(id, patch) => w.updateView(id, patch)}
                onRemoveView={(id) => w.removeView(id)}
                onUpdateSymbol={(id, patch) => w.updateSymbol(id, patch)}
                onRemoveSymbol={(id) => w.removeSymbol(id)}
                onRemoveCenterline={(id) => w.removeCenterline(id)}
                onRemoveBreak={(id) => w.removeBreak(id)}
                onAddSheet={(opts) => w.addSheet(opts || {})}
                onRemoveSheet={(idx) => w.removeSheet(idx)}
                onExportSvg={() => exportSvg(drawingSvgRef.current,
                  `${(w.currentFile?.name || 'drawing').replace(/\.[^.]+$/, '')}.svg`)}
                onExportPng={() => exportPng(drawingSvgRef.current,
                  `${(w.currentFile?.name || 'drawing').replace(/\.[^.]+$/, '')}.png`)}
                onExportPdf={() => {
                  const sh = w.parsedDrawing?.sheets?.[w.parsedDrawing?.currentSheet ?? 0]
                  return exportPdf(drawingSvgRef.current,
                    `${(w.currentFile?.name || 'drawing').replace(/\.[^.]+$/, '')}.pdf`,
                    { size: sh?.frame?.size, orientation: sh?.frame?.orientation })
                }}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : femFile ? (
            <div className="flex-1 min-h-0 overflow-y-auto p-3">
              <FEMView
                viewRef={currentViewRef}
                file={w.currentFile}
                projectId={projectId}
                geometry={femDisplayGeometry}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : plcFile ? (
            <div className="flex-1 min-h-0 relative">
              <PLCView
                viewRef={currentViewRef}
                content={w.currentFileContent}
                projectId={projectId}
                fileId={w.currentFileId}
                fileName={w.currentFile?.name}
                onContentChange={(v) => w.editContent(v)}
                className="h-full"
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : quadMeshFile ? (
            <div className="flex-1 min-h-0 relative">
              <QuadMeshView
                viewRef={currentViewRef}
                content={w.currentFileContent}
                fileName={w.currentFile?.name}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : textCodeFile ? (
            /* T-116: plain-text / code files open full-bleed in the FileEditor
               (Monaco with per-extension language mode). Changes round-trip
               through the existing workspace save path via w.editContent(). */
            <div className="flex-1 min-h-0 relative">
              <FileEditor
                content={w.currentFileContent}
                fileName={w.currentFile?.name}
                onChange={(v) => w.editContent(v)}
              />
              {w.toast && (
                <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                  onClick={() => w.dismissToast()}>
                  {w.toast}
                </div>
              )}
            </div>
          ) : (
          <>
          <div style={{ height: `${splitPct}%` }} className="min-h-0 relative">
            <Renderer
              ref={(r) => {
                rendererRef.current = r
                // Renderer is the active view for JSCAD/assembly files;
                // route thumbnail capture through its existing snapshot().
                currentViewRef.current = r
              }}
              parts={w.parts}
              selectedId={w.pickedPart?.part_id}
              selectedComponentId={assemblyFile ? w.selectedComponentId : null}
              hiddenIds={hiddenIds}
              onPick={handlePick}
              mode={w.measureMode}
              selectedFeatures={w.selectedFeatures}
              onPickFeature={handlePickFeature}
              assemblyComponents={assemblyComponents}
              className="w-full h-full"
            />
            {w.partsError && (
              <div className="pointer-events-none absolute inset-x-0 top-0 flex justify-center pt-4 z-10">
                <div className="max-w-lg w-full mx-4 px-4 py-3 rounded-lg bg-red-950/90 border border-red-700/70 text-red-300 text-[11px] font-mono shadow-lg backdrop-blur">
                  <div className="font-semibold text-red-200 mb-1">JSCAD error</div>
                  <div className="whitespace-pre-wrap break-words">{w.partsError}</div>
                </div>
              </div>
            )}
            {assemblyPickSide && (
              <div className="pointer-events-none absolute inset-x-0 top-2 flex justify-center z-20">
                <div className="pointer-events-auto flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-950/90 border border-amber-700/70 text-amber-300 text-[11px] shadow-lg">
                  <span>Click a face or edge on ref {assemblyPickSide.toUpperCase()}…</span>
                  <button
                    type="button"
                    onClick={() => {
                      assemblyPickSideRef.current = null
                      setAssemblyPickSide(null)
                      setMatePickResult(null)
                      useWorkspace.getState().setMeasureMode('object')
                    }}
                    className="text-amber-400 hover:text-amber-200 ml-1 text-[10px] underline"
                  >
                    Cancel (Esc)
                  </button>
                </div>
              </div>
            )}
            <MeasureToolbar
              mode={w.measureMode}
              onMode={(m) => w.setMeasureMode(m)}
              onClear={() => w.clearSelectedFeatures()}
              selectionCount={w.selectedFeatures.length}
            />
            {w.selectedFeatures.length === 1 && (
              <FeatureInspector
                selection={w.selectedFeatures[0]}
                parts={w.parts}
                topologies={topologies}
                onClose={() => w.clearSelectedFeatures()}
                onHidePart={(partId) => w.togglePartVisibility(w.currentFileId, partId)}
                onReferenceInChat={(partId, kind, featureId) =>
                  w.attachFeatureToChat(partId, kind, featureId)}
                onRecolorPart={(partId, rgb) => w.recolorPart(partId, rgb)}
                isStepFile={stepFile}
              />
            )}
            {w.selectedFeatures.length === 2 && (
              <SelectionDistanceChip selection={w.selectedFeatures} topologies={topologies} />
            )}
            {w.toast && (
              <div className="absolute bottom-3 right-3 z-20 px-3 py-2 rounded-md bg-ink-900 border border-kerf-300/60 text-kerf-300 text-xs shadow-xl"
                onClick={() => w.dismissToast()}>
                {w.toast}
              </div>
            )}
          </div>
          <div
            role="separator"
            aria-orientation="horizontal"
            aria-label="Resize renderer and code editor"
            onPointerDown={onSplitPointerDown}
            onPointerMove={onSplitPointerMove}
            onPointerUp={onSplitPointerUp}
            onPointerCancel={onSplitPointerUp}
            className="h-1.5 bg-ink-800 hover:bg-kerf-300/40 cursor-row-resize flex-shrink-0 transition-colors touch-none"
            style={{ touchAction: 'none' }}
            title="Drag to resize"
          />
          <div style={{ height: `${100 - splitPct}%` }} className="min-h-0 flex flex-col">
            <div className="flex items-center justify-between px-3 py-1.5 bg-ink-900 border-b border-ink-800 text-[11px] text-ink-400">
              <span className="font-mono">{w.currentFile?.name || '(no file)'}</span>
              <span className="text-ink-500">
                {stepFile ? 'STEP (binary)' : assemblyFile ? 'Assembly' : scriptFile ? 'Script' : 'JSCAD'}
              </span>
            </div>
            <div className="flex-1 min-h-0">
              {stepFile ? (
                <div className="h-full flex items-center justify-center text-xs text-ink-500 px-6 text-center">
                  STEP files are binary. The 3D view above is the only view.
                </div>
              ) : assemblyFile ? (
                <AssemblyEditor
                  content={w.currentFileContent}
                  files={w.files}
                  projectId={projectId}
                  currentFileId={w.currentFileId}
                  selectedComponentId={w.selectedComponentId}
                  onSelectComponent={(id) => w.selectComponent(id)}
                  onChange={(next) => w.editAssemblyContent(next)}
                  onToast={(msg) => useWorkspace.setState({ toast: msg })}
                  onRequestMatePick={(side) => {
                    assemblyPickSideRef.current = side
                    setAssemblyPickSide(side)
                    useWorkspace.getState().setMeasureMode('face')
                  }}
                  matePickResult={matePickResult}
                  onMatePickConsumed={() => setMatePickResult(null)}
                />
              ) : scriptFile ? (
                <ScriptEditor
                  content={w.currentFileContent}
                  fileName={w.currentFile?.name}
                  file={w.currentFile}
                  onChange={(v) => w.editContent(v)}
                />
              ) : (
                <CodeEditor
                  value={w.currentFileContent}
                  onChange={(v) => w.editContent(v)}
                  errors={editorErrors}
                  readOnly={!w.currentFileId || w.currentFile?.kind === 'folder'}
                />
              )}
            </div>
          </div>
          </>
          )}
        </main>

      </div>

      {/* ---------- Off-canvas drawers (< lg only) ----------
          Drawers are `fixed` so they overlay the canvas. The `lg:hidden`
          guarantees they're invisible (and unfocusable) on desktop ≥ 1024px
          where the inline panes own the layout. Backdrop is bg-black/40 with
          `pointer-events-auto` so clicks dismiss; the panel itself stops
          propagation so inner clicks stay inside the drawer. */}
      {treeDrawerOpen && (
        <div className="lg:hidden fixed inset-0 z-40 flex" role="presentation">
          <div
            className="absolute inset-0 bg-black/40 pointer-events-auto"
            onClick={() => setTreeDrawerOpen(false)}
            aria-hidden="true"
          />
          <div
            ref={treeDrawerRef}
            id="editor-tree-drawer"
            role="dialog"
            aria-modal="true"
            aria-label="File tree and objects"
            className="relative w-72 max-w-[85vw] h-full bg-ink-900 border-r border-ink-800 shadow-2xl flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between h-10 px-3 border-b border-ink-800 flex-shrink-0">
              <span className="text-xs font-medium text-ink-200 uppercase tracking-wider">Files</span>
              <button
                type="button"
                onClick={() => setTreeDrawerOpen(false)}
                aria-label="Close file tree drawer"
                className="p-1 rounded text-ink-400 hover:text-ink-100 hover:bg-ink-800"
              >
                <X size={14} />
              </button>
            </div>
            <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
              <div style={{ height: `${leftSplitPct}%` }} className="min-h-0">
                <FileTree
                  files={w.files}
                  currentFileId={w.currentFileId}
                  onSelect={(id) => { w.selectFile(id); setTreeDrawerOpen(false) }}
                  onCreate={(parentId, kind) => w.createFile(parentId, kind)}
                  onRename={(id, name) => w.renameFile(id, name)}
                  onDelete={(id) => { if (confirm('Delete this file?')) w.deleteFile(id) }}
                  onImportStep={handleImportStep}
                />
              </div>
              <div
                role="separator"
                aria-orientation="horizontal"
                aria-label="Resize file tree and objects panel"
                onPointerDown={onLeftSplitPointerDown}
                onPointerMove={onLeftSplitPointerMove}
                onPointerUp={onLeftSplitPointerUp}
                onPointerCancel={onLeftSplitPointerUp}
                className="h-1.5 bg-ink-800 hover:bg-kerf-300/40 cursor-row-resize flex-shrink-0 transition-colors touch-none"
                style={{ touchAction: 'none' }}
                title="Drag to resize"
              />
              <div style={{ height: `${100 - leftSplitPct}%` }} className="min-h-0 flex flex-col">
                {circuitFile ? (
                  <CircuitComponentsPanel
                    selectedRefdes={w.selectedCircuitRefdes}
                    selectedNet={w.selectedCircuitNet}
                    onSelectRefdes={(r) => w.selectCircuitRefdes(r)}
                    onSelectNet={(n) => w.selectCircuitNet(n)}
                  />
                ) : (
                  <div className="flex-1 min-h-0">
                    <ObjectsPanel
                      parts={w.parts}
                      hiddenIds={hiddenIds}
                      selectedId={w.pickedPart?.part_id}
                      onToggleVisibility={(id) => w.togglePartVisibility(w.currentFileId, id)}
                      onSelect={(id) => w.pickPart(id)}
                      onIsolate={(id) => w.isolatePart(w.currentFileId, id)}
                      onShowAll={() => w.showAllParts(w.currentFileId)}
                      onRecolorPart={(id, rgb) => w.recolorPart(id, rgb)}
                      onMovePart={(id, d) => w.movePart(id, d)}
                      onSetPartPosition={(id, p) => w.setPartPosition(id, p)}
                      isStepFile={stepFile}
                    />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {chatDrawerOpen && (
        <div className="lg:hidden fixed inset-0 z-40 flex justify-end" role="presentation">
          <div
            className="absolute inset-0 bg-black/40 pointer-events-auto"
            onClick={() => setChatDrawerOpen(false)}
            aria-hidden="true"
          />
          <div
            ref={chatDrawerRef}
            role="dialog"
            aria-modal="true"
            aria-label="Chat"
            className="relative w-[380px] max-w-[90vw] h-full bg-ink-900 border-l border-ink-800 shadow-2xl flex flex-col"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between h-10 px-3 border-b border-ink-800 flex-shrink-0">
              <span className="text-xs font-medium text-ink-200 uppercase tracking-wider">Chat</span>
              <button
                type="button"
                onClick={() => setChatDrawerOpen(false)}
                aria-label="Close chat drawer"
                className="p-1 rounded text-ink-400 hover:text-ink-100 hover:bg-ink-800"
              >
                <X size={14} />
              </button>
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              <ChatPanel
                ref={inputRef}
                threads={w.threads}
                currentThreadId={w.currentThreadId}
                messages={w.messages}
                pendingPartRefs={w.pendingPartRefs}
                sending={w.sending}
                loadingMessages={w.loadingMessages}
                onSelectThread={(id) => w.selectThread(id)}
                onCreateThread={() => w.createThread({ file_id: w.currentFileId })}
                onToggleStar={(id) => w.toggleStar(id)}
                onDeleteThread={(id) => {
                  if (confirm('Delete this thread?')) w.deleteThread(id)
                }}
                onRemovePartRef={(i) => w.removePartRef(i)}
                onSend={(content, opts) => w.sendMessageStreaming(content, opts)}
                onCancelStream={() => w.cancelStream()}
              />
            </div>
          </div>
        </div>
      )}

      {/* ---------- Unified right drawer (desktop overlay) ----------
          Positioned absolutely from the top of the main-area (below the 48px
          topbar) as a fixed-width panel on the right side. Slides in/out via
          CSS transition. Only rendered at ≥ lg — mobile uses the existing
          chat-drawer below. */}
      {rightDrawer.open && (
        <div
          data-testid="right-drawer"
          className="hidden lg:flex absolute top-12 right-0 bottom-0 w-[420px] z-30 bg-ink-900 border-l border-ink-800 shadow-2xl flex-col"
        >
          {/* Tab strip */}
          <div className="flex items-center border-b border-ink-800 flex-shrink-0 bg-ink-900">
            <button
              type="button"
              data-testid="right-drawer-tab-chat"
              onClick={() => setRightDrawerTab('chat')}
              className={`flex items-center gap-1.5 px-4 h-10 text-[11px] uppercase tracking-wider font-medium border-b-2 transition-colors ${
                rightDrawer.tab === 'chat'
                  ? 'border-kerf-300 text-kerf-300'
                  : 'border-transparent text-ink-400 hover:text-ink-200'
              }`}
            >
              <MessageSquare size={12} /> Chat
            </button>
            <button
              type="button"
              data-testid="right-drawer-tab-activity"
              onClick={() => setRightDrawerTab('activity')}
              className={`flex items-center gap-1.5 px-4 h-10 text-[11px] uppercase tracking-wider font-medium border-b-2 transition-colors ${
                rightDrawer.tab === 'activity'
                  ? 'border-kerf-300 text-kerf-300'
                  : 'border-transparent text-ink-400 hover:text-ink-200'
              }`}
            >
              <ActivityIcon size={12} /> Activity
            </button>
            {cloudEnabled && (
              <button
                type="button"
                data-testid="right-drawer-tab-git"
                onClick={() => setRightDrawerTab('git')}
                className={`flex items-center gap-1.5 px-4 h-10 text-[11px] uppercase tracking-wider font-medium border-b-2 transition-colors ${
                  rightDrawer.tab === 'git'
                    ? 'border-kerf-300 text-kerf-300'
                    : 'border-transparent text-ink-400 hover:text-ink-200'
                }`}
              >
                <GitBranch size={12} /> Git
              </button>
            )}
            <div className="flex-1" />
            <button
              type="button"
              onClick={() => closeRightDrawer()}
              className="mr-2 p-1 rounded text-ink-400 hover:text-ink-100 hover:bg-ink-800"
              aria-label="Close panel"
            >
              <X size={14} />
            </button>
          </div>

          {/* Panel body — only the active tab renders */}
          <div className="flex-1 min-h-0 overflow-hidden flex flex-col">
            {rightDrawer.tab === 'chat' && (
              <ChatPanel
                ref={inputRef}
                threads={w.threads}
                currentThreadId={w.currentThreadId}
                messages={w.messages}
                pendingPartRefs={w.pendingPartRefs}
                sending={w.sending}
                loadingMessages={w.loadingMessages}
                onSelectThread={(id) => w.selectThread(id)}
                onCreateThread={() => w.createThread({ file_id: w.currentFileId })}
                onToggleStar={(id) => w.toggleStar(id)}
                onDeleteThread={(id) => {
                  if (confirm('Delete this thread?')) w.deleteThread(id)
                }}
                onRemovePartRef={(i) => w.removePartRef(i)}
                onSend={(content, opts) => w.sendMessageStreaming(content, opts)}
                onCancelStream={() => w.cancelStream()}
              />
            )}
            {rightDrawer.tab === 'activity' && projectId && (
              <ActivityTimelineBody projectId={projectId} />
            )}
            {rightDrawer.tab === 'git' && cloudEnabled && projectId && (
              <GitPanel
                projectId={projectId}
                onClose={() => closeRightDrawer()}
              />
            )}
          </div>
        </div>
      )}

      {showShare && projectId && (
        <ShareModal projectId={projectId} onClose={() => setShowShare(false)} />
      )}
    </div>
  )
}

function SelectionDistanceChip({ selection, topologies }) {
  const [a, b] = selection
  const ta = topologies.get(a.partId)
  const tb = topologies.get(b.partId)
  if (!ta || !tb) return null
  const da = lookupFeatureLocal(a, ta)
  const db = lookupFeatureLocal(b, tb)
  if (!da || !db) return null
  const r = distance({ ...a, data: da }, { ...b, data: db })
  return (
    <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-10 flex items-center gap-2 px-3 py-1.5 rounded-md bg-ink-900/90 border border-kerf-300/60 backdrop-blur shadow-xl">
      <span className="text-[10px] text-ink-500 uppercase tracking-wider">{r.hint}</span>
      <span className="text-sm font-mono text-kerf-300 font-semibold">{formatDistance(r.value)}</span>
    </div>
  )
}
function lookupFeatureLocal(sel, t) {
  if (sel.kind === 'face') return t.faces.find((x) => x.id === sel.featureId) || null
  if (sel.kind === 'edge') return t.edges.find((x) => x.id === sel.featureId) || null
  if (sel.kind === 'vertex') return t.vertices.find((x) => x.id === sel.featureId) || null
  return null
}

function SaveIndicator({ status }) {
  if (status === 'saving') return (
    <span className="inline-flex items-center gap-1 text-[11px] text-ink-400">
      <Loader2 size={11} className="animate-spin" />
      Saving…
    </span>
  )
  if (status === 'dirty') return (
    <span className="inline-flex items-center gap-1 text-[11px] text-kerf-400">
      <Save size={11} />
      Unsaved
    </span>
  )
  return (
    <span className="inline-flex items-center gap-1 text-[11px] text-ink-500">
      <Check size={11} />
      Saved
    </span>
  )
}
