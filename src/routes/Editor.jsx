import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Share2, Save, Loader2, ArrowLeft, Check, History, X, RotateCcw, Undo2, Redo2, GitBranch, Clock, MessageSquare, PanelRightClose, PanelRightOpen, Plus, Box, SlidersHorizontal } from 'lucide-react'
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
import CircuitEditor from '../components/CircuitEditor.jsx'
import LibraryEditor from '../components/LibraryEditor.jsx'
import MaterialEditor from '../components/MaterialEditor.jsx'
import EquationsEditor from '../components/EquationsEditor.jsx'
import ScriptEditor from '../components/ScriptEditor.jsx'
import ConfigurationsPanel from '../components/ConfigurationsPanel.jsx'
import ActivityTimeline from '../components/ActivityTimeline.jsx'
import { useWorkspace, loadFilePartsForProject } from '../store/workspace.js'
import { useAuth } from '../store/auth.js'
import { useCloudConfig, GitPanel, PublishButton } from '../cloud/index.js'
import { runJscad, cancelJscad } from '../lib/jscadRunner.js'
import { getTopologyLazy } from '../lib/topology.js'
import { meshCache } from '../lib/meshCache.js'
import { distance, formatDistance } from '../lib/measure.js'
import { exportSvg, exportPng, exportPdf } from '../lib/svgExport.js'
import { api } from '../lib/api.js'

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

export default function Editor() {
  const { projectId, fileId } = useParams()
  const navigate = useNavigate()
  const user = useAuth((s) => s.user)
  const w = useWorkspace()
  const inputRef = useRef(null)
  const rendererRef = useRef(null)

  // ----- Project lifecycle -----
  useEffect(() => {
    if (projectId) w.loadProject(projectId)
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
  // Renders the scene and uploads a JPEG to the project so the projects
  // list can <img> it. We only fire when:
  //   * a JSCAD/assembly file is open (drawings + STEP excluded)
  //   * the file is currently saved + clean (saveStatus === 'saved')
  //   * the renderer has parts to draw
  //   * 2 seconds have elapsed since the most recent edit/save settle
  const thumbTimerRef = useRef(null)
  const thumbInFlightRef = useRef(false)
  useEffect(() => {
    if (!projectId) return
    if (!rendererRef.current) return
    if (isStepFile(w.currentFile)) return
    if (isDrawingFile(w.currentFile)) return
    if (w.dirty || w.saving) return
    if (!w.parts || w.parts.length === 0) return
    if (thumbTimerRef.current) clearTimeout(thumbTimerRef.current)
    thumbTimerRef.current = setTimeout(async () => {
      if (thumbInFlightRef.current) return
      thumbInFlightRef.current = true
      try {
        const blob = await rendererRef.current?.snapshot?.({ size: 512, quality: 0.7 })
        if (blob) await api.uploadProjectThumbnail(projectId, blob)
      } catch {
        // Best-effort — never surface a thumbnail error to the user.
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
        else if (e.key === 'Escape') { useWorkspace.getState().clearSelectedFeatures() }
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

  // Renderer feature click → store. shift adds; non-shift swaps.
  const handlePickFeature = useCallback((partId, kind, featureId, shift) => {
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
  const [splitPct, setSplitPct] = useState(60) // top half = renderer
  const draggingRef = useRef(false)
  function onSplitMouseDown(e) {
    e.preventDefault()
    draggingRef.current = true
    document.body.style.cursor = 'row-resize'
  }
  useEffect(() => {
    function move(e) {
      if (!draggingRef.current) return
      const container = document.getElementById('editor-center')
      if (!container) return
      const r = container.getBoundingClientRect()
      const pct = ((e.clientY - r.top) / r.height) * 100
      setSplitPct(Math.min(85, Math.max(15, pct)))
    }
    function up() {
      if (draggingRef.current) {
        draggingRef.current = false
        document.body.style.cursor = ''
      }
    }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
    return () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
    }
  }, [])

  // ----- Tab in the left rail's bottom section: Objects | Features -----
  // ----- Vertical split between FileTree & ObjectsPanel in left rail -----
  const [leftSplitPct, setLeftSplitPct] = useState(60) // top = FileTree
  const leftDraggingRef = useRef(false)
  function onLeftSplitMouseDown(e) {
    e.preventDefault()
    leftDraggingRef.current = true
    document.body.style.cursor = 'row-resize'
  }
  useEffect(() => {
    function move(e) {
      if (!leftDraggingRef.current) return
      const container = document.getElementById('editor-left')
      if (!container) return
      const r = container.getBoundingClientRect()
      const pct = ((e.clientY - r.top) / r.height) * 100
      setLeftSplitPct(Math.min(85, Math.max(20, pct)))
    }
    function up() {
      if (leftDraggingRef.current) {
        leftDraggingRef.current = false
        document.body.style.cursor = ''
      }
    }
    window.addEventListener('mousemove', move)
    window.addEventListener('mouseup', up)
    return () => {
      window.removeEventListener('mousemove', move)
      window.removeEventListener('mouseup', up)
    }
  }, [])

  const [showShare, setShowShare] = useState(false)
  const [chatCollapsed, setChatCollapsed] = useState(() => {
    try { return localStorage.getItem('kerf:chatCollapsed') === '1' } catch { return false }
  })
  useEffect(() => {
    try { localStorage.setItem('kerf:chatCollapsed', chatCollapsed ? '1' : '0') } catch {}
  }, [chatCollapsed])
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
  const drawingFile = isDrawingFile(w.currentFile)
  const sketchFile = isSketchFile(w.currentFile)
  const featureFile = isFeatureFile(w.currentFile)
  const circuitFile = isCircuitFile(w.currentFile)
  const partFile = isPartFile(w.currentFile)
  const materialFile = isMaterialFile(w.currentFile)
  const equationsFile = isEquationsFile(w.currentFile)
  const scriptFile = isScriptFile(w.currentFile)
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
      <header className="flex items-center gap-3 h-12 px-3 border-b border-ink-800 bg-ink-900 flex-shrink-0">
        <button
          type="button"
          onClick={() => navigate('/projects')}
          className="p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300"
          title="Back to projects"
        >
          <ArrowLeft size={15} />
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

        <button
          type="button"
          onClick={() => w.undoLastRevision()}
          disabled={!w.currentFileId}
          title="Undo (Cmd+Z)"
          className="p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300 disabled:opacity-40 disabled:hover:bg-transparent"
        >
          <Undo2 size={14} />
        </button>
        <button
          type="button"
          onClick={() => w.redoRevision()}
          disabled={!w.currentFileId || (w.redoStack?.length ?? 0) === 0}
          title="Redo (Cmd+Shift+Z)"
          className="p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300 disabled:opacity-40 disabled:hover:bg-transparent"
        >
          <Redo2 size={14} />
        </button>
        <button
          type="button"
          onClick={() => w.openRevisionDrawer()}
          disabled={!w.currentFileId}
          title="History"
          className="p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300 disabled:opacity-40 disabled:hover:bg-transparent"
        >
          <History size={14} />
        </button>

        <button
          type="button"
          onClick={() => w.openActivity()}
          disabled={!projectId}
          title="Activity"
          className="p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300 disabled:opacity-40 disabled:hover:bg-transparent"
        >
          <Clock size={14} />
        </button>

        {cloudEnabled && (
          <button
            type="button"
            onClick={() => w.openGitPanel()}
            disabled={!projectId}
            title="Git"
            className="p-1.5 rounded hover:bg-ink-800 text-ink-300 hover:text-kerf-300 disabled:opacity-40 disabled:hover:bg-transparent"
          >
            <GitBranch size={14} />
          </button>
        )}

        <ExportButton />

        {cloudEnabled && w.project && (
          <PublishButton project={w.project} />
        )}

        <button
          type="button"
          onClick={() => setChatCollapsed((v) => !v)}
          title={chatCollapsed ? 'Open chat' : 'Hide chat'}
          className={`p-1.5 rounded hover:bg-ink-800 ${chatCollapsed ? 'text-ink-300 hover:text-kerf-300' : 'text-kerf-300'}`}
        >
          {chatCollapsed ? <PanelRightOpen size={14} /> : <PanelRightClose size={14} />}
        </button>

        <button
          type="button"
          onClick={() => setShowShare(true)}
          disabled={!projectId}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-kerf-300 text-ink-950 text-xs font-medium hover:bg-kerf-200 disabled:opacity-40"
        >
          <Share2 size={12} />
          Share
        </button>

        <div
          className="w-7 h-7 rounded-full bg-ink-700 flex items-center justify-center text-[11px] text-ink-100 font-semibold flex-shrink-0"
          title={user?.email}
        >
          {user?.avatar_url
            ? <img src={user.avatar_url} alt="" className="w-full h-full rounded-full object-cover" />
            : ((user?.name || user?.email || '?').slice(0, 1).toUpperCase())}
        </div>
      </header>

      {/* ---------- Main grid ---------- */}
      <div className="flex-1 grid min-h-0" style={{ gridTemplateColumns: chatCollapsed ? '240px 1fr' : '240px 1fr 380px' }}>
        {/* Left: file tree (top) + objects panel (bottom) */}
        <aside id="editor-left" className="border-r border-ink-800 min-h-0 flex flex-col overflow-hidden">
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
            onMouseDown={onLeftSplitMouseDown}
            className="h-1.5 bg-ink-800 hover:bg-kerf-300/40 cursor-row-resize flex-shrink-0 transition-colors"
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
          ) : scriptFile ? (
            <div className="flex-1 min-h-0 relative">
              <ScriptEditor
                content={w.currentFileContent}
                fileName={w.currentFile?.name}
                file={w.currentFile}
                onChange={(v) => w.editContent(v)}
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
              </div>
              <div className="flex-1 min-h-0 relative">
                <SketchView
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
              <CircuitEditor />
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
          ) : drawingFile && w.parsedDrawing ? (
            <div className="flex-1 min-h-0 relative">
              <DrawingView
                ref={drawingSvgRef}
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
          ) : (
          <>
          <div style={{ height: `${splitPct}%` }} className="min-h-0 relative">
            <Renderer
              ref={rendererRef}
              parts={w.parts}
              selectedId={w.pickedPart?.part_id}
              selectedComponentId={assemblyFile ? w.selectedComponentId : null}
              hiddenIds={hiddenIds}
              onPick={handlePick}
              mode={w.measureMode}
              selectedFeatures={w.selectedFeatures}
              onPickFeature={handlePickFeature}
              className="w-full h-full"
            />
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
            onMouseDown={onSplitMouseDown}
            className="h-1.5 bg-ink-800 hover:bg-kerf-300/40 cursor-row-resize flex-shrink-0 transition-colors"
            title="Drag to resize"
          />
          <div style={{ height: `${100 - splitPct}%` }} className="min-h-0 flex flex-col">
            <div className="flex items-center justify-between px-3 py-1.5 bg-ink-900 border-b border-ink-800 text-[11px] text-ink-400">
              <span className="font-mono">{w.currentFile?.name || '(no file)'}</span>
              <span className="text-ink-500">
                {stepFile ? 'STEP (binary)' : assemblyFile ? 'Assembly' : 'JSCAD'}
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

        {/* Right: chat (hidden entirely when collapsed — center expands into the space). */}
        {!chatCollapsed && (
          <aside className="min-h-0 overflow-hidden">
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
              onSend={(content, opts) => w.sendMessage(content, opts)}
            />
          </aside>
        )}
      </div>

      {showShare && projectId && (
        <ShareModal projectId={projectId} onClose={() => setShowShare(false)} />
      )}

      {w.revisionDrawerOpen && (
        <RevisionDrawer
          revisions={w.revisions}
          loading={w.loadingRevisions}
          onRestore={(id) => w.restoreRevision(id)}
          onClose={() => w.closeRevisionDrawer()}
        />
      )}

      {cloudEnabled && w.gitOpen && projectId && (
        <GitPanel projectId={projectId} onClose={() => w.closeGitPanel()} />
      )}

      {projectId && (
        <ActivityTimeline
          projectId={projectId}
          open={w.activityOpen}
          onClose={() => w.closeActivity()}
        />
      )}
    </div>
  )
}

function relativeTime(iso) {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return ''
  const ms = Date.now() - t
  const s = Math.round(ms / 1000)
  if (s < 5) return 'just now'
  if (s < 60) return `${s}s ago`
  const m = Math.round(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h}h ago`
  const d = Math.round(h / 24)
  if (d < 7) return `${d}d ago`
  return new Date(iso).toLocaleDateString()
}

function sourceTag(source) {
  switch (source) {
    case 'user':    return { icon: '👤', label: 'You',     className: 'text-kerf-300' }
    case 'llm':     return { icon: '✨', label: 'AI',      className: 'text-purple-300' }
    case 'tool':    return { icon: '🔧', label: 'Tool',    className: 'text-amber-300' }
    case 'restore': return { icon: '↩',  label: 'Restore', className: 'text-blue-300' }
    default:        return { icon: '•',  label: source || 'Edit', className: 'text-ink-400' }
  }
}

function RevisionDrawer({ revisions, loading, onRestore, onClose }) {
  return (
    <div className="absolute top-12 right-0 bottom-0 w-80 z-30 bg-ink-900 border-l border-ink-800 shadow-2xl flex flex-col">
      <div className="flex items-center justify-between h-10 px-3 border-b border-ink-800 flex-shrink-0">
        <div className="flex items-center gap-2 text-xs font-medium text-ink-200 uppercase tracking-wider">
          <History size={13} className="text-kerf-300" />
          History
        </div>
        <button
          type="button"
          onClick={onClose}
          className="p-1 rounded text-ink-400 hover:text-ink-100 hover:bg-ink-800"
          aria-label="Close history"
        >
          <X size={14} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="p-3 space-y-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-14 rounded bg-ink-850 animate-pulse" />
            ))}
          </div>
        ) : revisions.length === 0 ? (
          <div className="p-6 text-center text-xs text-ink-500">
            No history yet — make a change to see it here.
          </div>
        ) : (
          <ul className="divide-y divide-ink-850">
            {revisions.map((r, i) => {
              const tag = sourceTag(r.source)
              const isCurrent = i === 0
              const preview = (r.content_preview || '').replace(/\s+/g, ' ').trim()
              const truncated = preview.length > 80 ? preview.slice(0, 80) + '…' : preview
              return (
                <li
                  key={r.id}
                  className={`px-3 py-2 ${isCurrent ? 'bg-ink-850/60' : 'hover:bg-ink-850/40'}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className={`text-[10px] uppercase tracking-wider font-medium ${tag.className}`}>
                        {tag.icon} {tag.label}
                      </span>
                      {r.user_name && (
                        <span className="text-[10px] text-ink-500 truncate">· {r.user_name}</span>
                      )}
                      {isCurrent && (
                        <span className="text-[9px] uppercase tracking-wider text-kerf-300/80 ml-1">current</span>
                      )}
                    </div>
                    <span className="text-[10px] text-ink-500 flex-shrink-0">{relativeTime(r.created_at)}</span>
                  </div>
                  <div className="mt-1 font-mono text-[10px] text-ink-400 line-clamp-2 break-all">
                    {truncated || <span className="italic text-ink-600">(empty)</span>}
                  </div>
                  {!isCurrent && (
                    <div className="mt-1.5">
                      <button
                        type="button"
                        onClick={() => onRestore(r.id)}
                        className="inline-flex items-center gap-1 text-[10px] text-kerf-300 hover:text-kerf-200"
                      >
                        <RotateCcw size={10} />
                        Restore
                      </button>
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        )}
      </div>
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
