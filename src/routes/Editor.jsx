import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Share2, Save, Loader2, ArrowLeft, Check } from 'lucide-react'
import { LogoWordmark } from '../components/Logo.jsx'
import FileTree from '../components/FileTree.jsx'
import Renderer from '../components/Renderer.jsx'
import CodeEditor from '../components/CodeEditor.jsx'
import ChatPanel from '../components/ChatPanel.jsx'
import ShareModal from '../components/ShareModal.jsx'
import ObjectsPanel from '../components/ObjectsPanel.jsx'
import { useWorkspace } from '../store/workspace.js'
import { useAuth } from '../store/auth.js'
import { runJscad } from '../lib/jscadRunner.js'

const AUTOSAVE_MS = 500
const RUN_DEBOUNCE_MS = 350

function isStepFile(file) {
  if (!file) return false
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.step') || n.endsWith('.stp')
}

export default function Editor() {
  const { projectId, fileId } = useParams()
  const navigate = useNavigate()
  const user = useAuth((s) => s.user)
  const w = useWorkspace()
  const inputRef = useRef(null)

  // ----- Project lifecycle -----
  useEffect(() => {
    if (projectId) w.loadProject(projectId)
    return () => w.reset()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId])

  // Sync URL fileId → store.
  useEffect(() => {
    if (fileId && fileId !== w.currentFileId) w.selectFile(fileId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileId])

  // ----- Run JSCAD on content change (debounced) — JSCAD files only -----
  // STEP files have `parts` populated by `loadFileForEditor` directly; we
  // skip the runner there. Run errors are stashed on the store so they
  // survive across component-level re-renders without a setState-in-effect.
  const runTimerRef = useRef(null)
  useEffect(() => {
    if (isStepFile(w.currentFile)) return
    if (runTimerRef.current) clearTimeout(runTimerRef.current)
    const code = w.currentFileContent
    runTimerRef.current = setTimeout(async () => {
      const res = await runJscad(code)
      if (res.error) {
        // Keep last successful parts visible; just record the error.
        useWorkspace.getState().setPartsError(res.error)
      } else {
        useWorkspace.getState().setPartsError(null)
        useWorkspace.getState().setLiveParts(res.parts || [])
      }
    }, RUN_DEBOUNCE_MS)
    return () => { if (runTimerRef.current) clearTimeout(runTimerRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [w.currentFileContent, w.currentFile?.id])

  // ----- Autosave (debounced) -----
  const saveTimerRef = useRef(null)
  useEffect(() => {
    if (!w.dirty) return
    if (isStepFile(w.currentFile)) return
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current)
    saveTimerRef.current = setTimeout(() => {
      w.saveFile()
    }, AUTOSAVE_MS)
    return () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [w.currentFileContent, w.dirty])

  // ----- Keyboard shortcuts -----
  useEffect(() => {
    function onKey(e) {
      const meta = e.metaKey || e.ctrlKey
      if (meta && e.key.toLowerCase() === 's') {
        e.preventDefault()
        w.saveFile()
      } else if (meta && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ----- Renderer click → store, auto-attach to chat -----
  const handlePick = useCallback((id) => {
    w.pickPart(id)
    if (id) w.attachPickedToChat()
    // eslint-disable-next-line react-hooks/exhaustive-deps
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

  const editorErrors = useMemo(
    () => w.partsError ? [w.partsError] : [],
    [w.partsError],
  )
  const saveStatus = w.saving ? 'saving' : w.dirty ? 'dirty' : 'saved'

  // Visibility set for the current file (may be undefined).
  const hiddenIds = useMemo(() => {
    return w.hiddenPartIds.get(w.currentFileId) || new Set()
  }, [w.hiddenPartIds, w.currentFileId])

  const handleImportStep = useCallback(async (browserFile, parentId) => {
    if (!browserFile) return
    await w.uploadAsset(browserFile, { kind: 'step', parent_id: parentId || null })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const stepFile = isStepFile(w.currentFile)

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
        <LogoWordmark />
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
      <div className="flex-1 grid min-h-0" style={{ gridTemplateColumns: '240px 1fr 380px' }}>
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
          <div style={{ height: `${100 - leftSplitPct}%` }} className="min-h-0">
            <ObjectsPanel
              parts={w.parts}
              hiddenIds={hiddenIds}
              selectedId={w.pickedPart?.part_id}
              onToggleVisibility={(id) => w.togglePartVisibility(w.currentFileId, id)}
              onSelect={(id) => w.pickPart(id)}
              onIsolate={(id) => w.isolatePart(w.currentFileId, id)}
              onShowAll={() => w.showAllParts(w.currentFileId)}
            />
          </div>
        </aside>

        {/* Center: renderer + editor */}
        <main id="editor-center" className="flex flex-col min-w-0 min-h-0 relative">
          <div style={{ height: `${splitPct}%` }} className="min-h-0 relative">
            <Renderer
              parts={w.parts}
              selectedId={w.pickedPart?.part_id}
              hiddenIds={hiddenIds}
              onPick={handlePick}
              className="w-full h-full"
            />
          </div>
          <div
            onMouseDown={onSplitMouseDown}
            className="h-1.5 bg-ink-800 hover:bg-kerf-300/40 cursor-row-resize flex-shrink-0 transition-colors"
            title="Drag to resize"
          />
          <div style={{ height: `${100 - splitPct}%` }} className="min-h-0 flex flex-col">
            <div className="flex items-center justify-between px-3 py-1.5 bg-ink-900 border-b border-ink-800 text-[11px] text-ink-400">
              <span className="font-mono">{w.currentFile?.name || '(no file)'}</span>
              <span className="text-ink-500">{stepFile ? 'STEP (binary)' : 'JSCAD'}</span>
            </div>
            <div className="flex-1 min-h-0">
              {stepFile ? (
                <div className="h-full flex items-center justify-center text-xs text-ink-500 px-6 text-center">
                  STEP files are binary. The 3D view above is the only view.
                </div>
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
        </main>

        {/* Right: chat */}
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
      </div>

      {showShare && projectId && (
        <ShareModal projectId={projectId} onClose={() => setShowShare(false)} />
      )}
    </div>
  )
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
