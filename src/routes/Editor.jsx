import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Share2, Save, Loader2, ArrowLeft, Check } from 'lucide-react'
import { LogoWordmark } from '../components/Logo.jsx'
import FileTree from '../components/FileTree.jsx'
import Renderer from '../components/Renderer.jsx'
import CodeEditor from '../components/CodeEditor.jsx'
import ChatPanel from '../components/ChatPanel.jsx'
import ShareModal from '../components/ShareModal.jsx'
import { useWorkspace } from '../store/workspace.js'
import { useAuth } from '../store/auth.js'
import { runJscad } from '../lib/jscadRunner.js'

const AUTOSAVE_MS = 500
const RUN_DEBOUNCE_MS = 350

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

  // ----- Run JSCAD on content change (debounced) -----
  const [parts, setParts] = useState([])
  const [runError, setRunError] = useState(null)
  const runTimerRef = useRef(null)
  useEffect(() => {
    if (runTimerRef.current) clearTimeout(runTimerRef.current)
    const code = w.currentFileContent
    runTimerRef.current = setTimeout(async () => {
      const res = await runJscad(code)
      if (res.error) {
        setRunError(res.error)
        // Keep last successful parts visible.
      } else {
        setRunError(null)
        setParts(res.parts || [])
      }
    }, RUN_DEBOUNCE_MS)
    return () => { if (runTimerRef.current) clearTimeout(runTimerRef.current) }
  }, [w.currentFileContent])

  // ----- Autosave (debounced) -----
  const saveTimerRef = useRef(null)
  useEffect(() => {
    if (!w.dirty) return
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

  const handleApplyCode = useCallback((code) => {
    w.editContent(code)
    // Save right away so the renderer + future chat see the new content.
    setTimeout(() => w.saveFile(), 0)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ----- Top bar: editable project name -----
  // We render the editing input under a `key` of the project name so React
  // remounts it (with a fresh defaultValue) whenever the project changes —
  // avoiding a setState-in-effect to keep nameDraft synced.
  const [editingName, setEditingName] = useState(false)
  const nameInputRef = useRef(null)
  function commitName() {
    setEditingName(false)
    const next = nameInputRef.current?.value?.trim()
    if (next && next !== w.project?.name) w.updateProjectName(next)
  }

  // ----- Resizable split between renderer & editor (vertical) -----
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

  const [showShare, setShowShare] = useState(false)

  const editorErrors = useMemo(() => runError ? [runError] : [], [runError])
  const saveStatus = w.saving ? 'saving' : w.dirty ? 'dirty' : 'saved'

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
        {/* Left: file tree */}
        <aside className="border-r border-ink-800 min-h-0 overflow-hidden">
          <FileTree
            files={w.files}
            currentFileId={w.currentFileId}
            onSelect={(id) => w.selectFile(id)}
            onCreate={(parentId, kind) => w.createFile(parentId, kind)}
            onRename={(id, name) => w.renameFile(id, name)}
            onDelete={(id) => {
              if (confirm('Delete this file?')) w.deleteFile(id)
            }}
          />
        </aside>

        {/* Center: renderer + editor */}
        <main id="editor-center" className="flex flex-col min-w-0 min-h-0 relative">
          <div style={{ height: `${splitPct}%` }} className="min-h-0 relative">
            <Renderer
              parts={parts}
              selectedId={w.pickedPart?.part_id}
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
              <span className="text-ink-500">JSCAD</span>
            </div>
            <div className="flex-1 min-h-0">
              <CodeEditor
                value={w.currentFileContent}
                onChange={(v) => w.editContent(v)}
                errors={editorErrors}
                readOnly={!w.currentFileId || w.currentFile?.kind === 'folder'}
              />
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
            onSend={(content) => w.sendMessage(content)}
            onApplyCode={handleApplyCode}
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
