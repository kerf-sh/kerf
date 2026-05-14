import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronDown, ChevronRight,
  FileCode, Folder, FolderOpen, Layers,
  FilePlus, FolderPlus, Plus, Trash2, Box, Upload, Ruler, PenTool, X, RefreshCw,
  Package, Cylinder, CircuitBoard, Loader2, AlertCircle, Variable, FileBox, Cable, Scissors, Wrench,
} from 'lucide-react'
import { useWorkspace } from '../store/workspace.js'
import { FreeCADImportDialog, isFCStdFile } from './FreeCADImport.jsx'

// Build a tree from a flat list of {id, parent_id, name, kind}.
function buildTree(files) {
  const byParent = new Map()
  for (const f of files) {
    const k = f.parent_id || '__root__'
    if (!byParent.has(k)) byParent.set(k, [])
    byParent.get(k).push(f)
  }
  for (const arr of byParent.values()) {
    arr.sort((a, b) => {
      const ak = a.kind === 'folder' ? 0 : 1
      const bk = b.kind === 'folder' ? 0 : 1
      if (ak !== bk) return ak - bk
      return a.name.localeCompare(b.name)
    })
  }
  return byParent
}

function KindIcon({ kind, name, open }) {
  const cls = 'flex-shrink-0'
  if (kind === 'folder') return open
    ? <FolderOpen size={14} className={`${cls} text-kerf-400`} />
    : <Folder size={14} className={`${cls} text-ink-300`} />
  if (kind === 'assembly') return <Layers size={14} className={`${cls} text-cyan-edge`} />
  if (kind === 'drawing') return <Ruler size={14} className={`${cls} text-kerf-300`} />
  if (kind === 'sketch') return <PenTool size={14} className={`${cls} text-amber-300`} />
  if (kind === 'part') return <Package size={14} className={`${cls} text-emerald-300`} />
  if (kind === 'feature') return <Cylinder size={14} className={`${cls} text-amber-300`} />
  if (kind === 'circuit') return <CircuitBoard size={14} className={`${cls} text-cyan-edge`} />
  if (kind === 'equations') return <Variable size={14} className={`${cls} text-kerf-300`} />
  if (kind === 'wiring') return <Cable size={14} className={`${cls} text-orange-300`} />
  if (kind === 'section') return <Scissors size={14} className={`${cls} text-violet-300`} />
  if (kind === 'cam_layered') return <Layers size={14} className={`${cls} text-teal-300`} />
  if (kind === 'tool') return <Wrench size={14} className={`${cls} text-kerf-300`} />
  if (kind === 'step-ref') return (
    <span className="relative flex-shrink-0 inline-flex items-center">
      <Box size={14} className="text-cyan-edge" />
      <span className="ml-0.5 text-[9px] font-mono text-ink-300 leading-none">(ref)</span>
    </span>
  )
  const lower = (name || '').toLowerCase()
  if (lower.endsWith('.step') || lower.endsWith('.stp')) {
    return <Box size={14} className={`${cls} text-cyan-edge`} />
  }
  if (lower.endsWith('.drawing')) {
    return <Ruler size={14} className={`${cls} text-kerf-300`} />
  }
  if (lower.endsWith('.sketch')) {
    return <PenTool size={14} className={`${cls} text-amber-300`} />
  }
  if (lower.endsWith('.part')) {
    return <Package size={14} className={`${cls} text-emerald-300`} />
  }
  if (lower.endsWith('.feature')) {
    return <Cylinder size={14} className={`${cls} text-amber-300`} />
  }
  if (lower.endsWith('.circuit.tsx')) {
    return <CircuitBoard size={14} className={`${cls} text-cyan-edge`} />
  }
  if (lower.endsWith('.equations')) {
    return <Variable size={14} className={`${cls} text-kerf-300`} />
  }
  if (lower.endsWith('.wiring')) {
    return <Cable size={14} className={`${cls} text-orange-300`} />
  }
  if (lower.endsWith('.section')) {
    return <Scissors size={14} className={`${cls} text-violet-300`} />
  }
  if (lower.endsWith('.cam.layered')) {
    return <Layers size={14} className={`${cls} text-teal-300`} />
  }
  if (lower.endsWith('.tool')) {
    return <Wrench size={14} className={`${cls} text-kerf-300`} />
  }
  if (lower.endsWith('.fcstd')) {
    return <FileBox size={14} className={`${cls} text-orange-300`} />
  }
  return <FileCode size={14} className={`${cls} text-ink-200`} />
}

// SketchBacklink chip — rendered on .jscad file rows that import a .sketch.
// `sketchName` is the basename of the first imported sketch, e.g. "bracket.sketch".
function SketchBacklinkChip({ sketchName }) {
  if (!sketchName) return null
  return (
    <span
      className="flex-shrink-0 text-[10px] text-ink-500 font-mono leading-none px-1 py-0.5 rounded bg-ink-800/60 border border-ink-700/50 ml-1 truncate max-w-[80px]"
      title={`Imports sketch: ${sketchName}`}
    >
      ← {sketchName}
    </span>
  )
}

function Node({ file, depth, byParent, expanded, toggle, currentFileId, onSelect, onCreate, onRename, onDelete, onImportStep, renamingId, setRenamingId, jscadSketchLinks }) {
  const [menu, setMenu] = useState(null) // {x, y}
  const inputRef = useRef(null)
  const isRenaming = renamingId === file.id
  const isFolder = file.kind === 'folder'
  const isOpen = expanded.has(file.id)
  const children = byParent.get(file.id) || []
  const isCurrent = file.id === currentFileId

  useEffect(() => {
    if (isRenaming) {
      // Focus + select base name (before dot).
      const el = inputRef.current
      if (el) {
        el.focus()
        const dot = file.name.lastIndexOf('.')
        if (dot > 0) el.setSelectionRange(0, dot)
        else el.select()
      }
    }
  }, [isRenaming, file.name])

  function commitRename(ev) {
    const next = ev.target.value.trim()
    setRenamingId(null)
    if (next && next !== file.name) onRename?.(file.id, next)
  }

  function onRowClick() {
    if (isFolder) toggle(file.id)
    else onSelect?.(file.id)
  }

  function onKey(e) {
    if (e.key === 'F2') {
      e.preventDefault()
      setRenamingId(file.id)
    } else if (e.key === 'Enter' && !isFolder) {
      onSelect?.(file.id)
    } else if (e.key === 'Delete') {
      onDelete?.(file.id)
    }
  }

  return (
    <div>
      <div
        className={`group flex items-center gap-1 pr-2 py-[3px] cursor-pointer rounded-sm select-none ${
          isCurrent ? 'bg-kerf-300/15 text-kerf-100' : 'hover:bg-ink-800 text-ink-200'
        }`}
        style={{ paddingLeft: 6 + depth * 12 }}
        onClick={onRowClick}
        onDoubleClick={(e) => { e.stopPropagation(); setRenamingId(file.id) }}
        onContextMenu={(e) => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY }) }}
        tabIndex={0}
        onKeyDown={onKey}
      >
        {isFolder ? (
          <span className="text-ink-400 flex-shrink-0">
            {isOpen ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
          </span>
        ) : <span className="w-3 flex-shrink-0" />}
        <KindIcon kind={file.kind} name={file.name} open={isOpen} />
        {isRenaming ? (
          <input
            ref={inputRef}
            defaultValue={file.name}
            className="flex-1 bg-ink-950 border border-kerf-300/50 rounded px-1 text-xs font-mono outline-none text-ink-100 min-w-0"
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commitRename(e)
              else if (e.key === 'Escape') setRenamingId(null)
              e.stopPropagation()
            }}
            onClick={(e) => e.stopPropagation()}
          />
        ) : (
          <span className="flex-1 text-xs font-mono truncate min-w-0">{file.name}</span>
        )}
        {!isRenaming && jscadSketchLinks?.get(file.id) && (
          <SketchBacklinkChip sketchName={jscadSketchLinks.get(file.id)} />
        )}
        {!isRenaming && file.tessellation_status === 'running' && (
          <span title="Generating preview mesh (server-side STEP tessellation)" className="flex-shrink-0 text-cyan-edge">
            <Loader2 size={11} className="animate-spin" />
          </span>
        )}
        {!isRenaming && file.tessellation_status === 'queued' && (
          <span title="Queued for server-side STEP tessellation" className="flex-shrink-0 text-ink-400">
            <Loader2 size={11} className="animate-spin opacity-60" />
          </span>
        )}
        {!isRenaming && file.tessellation_status === 'error' && (
          <span title="Server-side STEP tessellation failed (in-browser parse will be used)" className="flex-shrink-0 text-amber-400">
            <AlertCircle size={11} />
          </span>
        )}
        {!isRenaming && (
          <div className="flex items-center gap-0.5 flex-shrink-0">
            {isFolder && (
              <button
                type="button"
                className="opacity-0 group-hover:opacity-100 text-ink-400 hover:text-kerf-300 p-0.5 rounded hover:bg-ink-700"
                title="New file in folder"
                onClick={(e) => {
                  e.stopPropagation()
                  if (!isOpen) toggle(file.id)
                  onCreate?.(file.id, 'file')
                }}
              >
                <Plus size={12} />
              </button>
            )}
            <button
              type="button"
              className="opacity-0 group-hover:opacity-100 text-ink-400 hover:text-red-400 p-0.5 rounded hover:bg-ink-700"
              title={isFolder ? 'Delete folder (and contents)' : 'Delete file'}
              onClick={(e) => {
                e.stopPropagation()
                onDelete?.(file.id)
              }}
            >
              <Trash2 size={12} />
            </button>
          </div>
        )}
      </div>
      {isFolder && isOpen && children.map((c) => (
        <Node
          key={c.id}
          file={c}
          depth={depth + 1}
          byParent={byParent}
          expanded={expanded}
          toggle={toggle}
          currentFileId={currentFileId}
          onSelect={onSelect}
          onCreate={onCreate}
          onRename={onRename}
          onDelete={onDelete}
          onImportStep={onImportStep}
          renamingId={renamingId}
          setRenamingId={setRenamingId}
          jscadSketchLinks={jscadSketchLinks}
        />
      ))}
      {menu && (
        <ContextMenu
          x={menu.x} y={menu.y}
          onClose={() => setMenu(null)}
          onRename={() => { setRenamingId(file.id); setMenu(null) }}
          onDelete={() => { onDelete?.(file.id); setMenu(null) }}
          onNewFile={isFolder ? () => { onCreate?.(file.id, 'file'); setMenu(null) } : null}
          onNewFolder={isFolder ? () => { onCreate?.(file.id, 'folder'); setMenu(null) } : null}
          onNewAssembly={isFolder ? () => { onCreate?.(file.id, 'assembly'); setMenu(null) } : null}
          onNewDrawing={isFolder ? () => { onCreate?.(file.id, 'drawing'); setMenu(null) } : null}
          onNewSketch={isFolder ? () => { onCreate?.(file.id, 'sketch'); setMenu(null) } : null}
          onNewFeature={isFolder ? () => { onCreate?.(file.id, 'feature'); setMenu(null) } : null}
          onNewSection={isFolder ? () => { onCreate?.(file.id, 'section'); setMenu(null) } : null}
          onNewCircuit={isFolder ? () => { onCreate?.(file.id, 'circuit'); setMenu(null) } : null}
          onNewPart={isFolder ? () => { onCreate?.(file.id, 'part'); setMenu(null) } : null}
          onImportStep={isFolder ? () => { onImportStep?.(file.id); setMenu(null) } : null}
        />
      )}
    </div>
  )
}

function MenuItem({ icon: Icon, label, action }) {
  if (!action) return null
  return (
    <button
      type="button"
      onClick={action}
      className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-ink-100 hover:bg-ink-700 text-left"
    >
      <Icon size={12} className="text-ink-300" />
      {label}
    </button>
  )
}

// Inline progress / cancel / retry strip for the in-flight chunked STEP
// upload. Lives at the top of the tree; reads/writes via the workspace
// store so it doesn't need the parent to thread props down.
function UploadProgressStrip({ onRetry }) {
  const progress = useWorkspace((s) => s.uploadProgress)
  const cancelUpload = useWorkspace((s) => s.cancelUpload)
  const dismiss = useWorkspace((s) => s.dismissUploadError)
  if (!progress) return null
  const { filename, received, total, status, error, totalBytes, bytes } = progress
  const isError = status === 'error'
  // Pre-progress state ('hashing' / first chunk pending) → indeterminate.
  // Otherwise show received/total chunks. We clamp the displayed pct against
  // totalBytes so resumed uploads (where some bytes were already on the
  // server) read past 0% on the first tick.
  let pct = 0
  if (total > 0) pct = Math.round((received / total) * 100)
  else if (totalBytes > 0 && bytes > 0) pct = Math.round((bytes / totalBytes) * 100)
  return (
    <div className={`mx-2 my-2 px-2 py-2 rounded border text-[11px] ${
      isError ? 'border-red-600/50 bg-red-950/30 text-red-200' : 'border-kerf-300/30 bg-ink-850 text-ink-200'
    }`}>
      <div className="flex items-center gap-2">
        <Box size={12} className="flex-shrink-0 text-cyan-edge" />
        <span className="flex-1 truncate font-mono text-[11px]">{filename}</span>
        {isError ? (
          <>
            <button
              type="button"
              className="p-0.5 rounded hover:bg-ink-700 text-ink-300 hover:text-kerf-300"
              title="Retry"
              onClick={() => onRetry?.()}
            >
              <RefreshCw size={11} />
            </button>
            <button
              type="button"
              className="p-0.5 rounded hover:bg-ink-700 text-ink-300 hover:text-red-400"
              title="Dismiss"
              onClick={() => dismiss()}
            >
              <X size={11} />
            </button>
          </>
        ) : (
          <button
            type="button"
            className="p-0.5 rounded hover:bg-ink-700 text-ink-300 hover:text-red-400"
            title="Cancel upload"
            onClick={() => cancelUpload()}
          >
            <X size={11} />
          </button>
        )}
      </div>
      <div className="mt-1 h-1 rounded bg-ink-800 overflow-hidden">
        <div
          className={`h-full transition-all duration-150 ${
            isError ? 'bg-red-500/70' : status === 'hashing' ? 'bg-kerf-300/40' : 'bg-kerf-300'
          }`}
          style={{ width: `${Math.max(2, pct)}%` }}
        />
      </div>
      <div className="mt-1 flex items-center justify-between text-[10px] text-ink-400">
        <span>
          {isError ? error
            : status === 'hashing' ? 'hashing…'
            : total > 0 ? `${received} / ${total} chunks (${pct}%)`
            : 'starting…'}
        </span>
      </div>
    </div>
  )
}

// KIND_ROWS is the master catalog of "+ New" dropdown entries. With
// project types removed (May 2026), CreateMenu shows the full union
// unconditionally — every project can create every canonical kind.
// `hint` doubles as the row tooltip explaining what the kind is for.
const KIND_ROWS = {
  folder:    { icon: FolderPlus,   label: 'Folder',    hint: 'Group related files' },
  file:      { icon: FilePlus,     label: 'File',      hint: 'Generic .jscad code module',                color: 'text-kerf-300' },
  sketch:    { icon: PenTool,      label: 'Sketch',    hint: '2D parametric profile for features',        color: 'text-amber-300' },
  assembly:  { icon: Layers,       label: 'Assembly',  hint: 'Compose parts and sub-assemblies',          color: 'text-cyan-edge' },
  drawing:   { icon: Ruler,        label: 'Drawing',   hint: '2D technical drawing with views & dims',    color: 'text-kerf-300' },
  feature:   { icon: Cylinder,     label: 'Feature',   hint: 'OCCT B-rep timeline (extrude, fillet, …)',  color: 'text-amber-300' },
  part:      { icon: Package,      label: 'Part',      hint: 'Library Part with metadata for the BOM',    color: 'text-emerald-300' },
  circuit:   { icon: CircuitBoard, label: 'Circuit',   hint: 'tscircuit electronics (.circuit.tsx)',      color: 'text-cyan-edge' },
  equations: { icon: Variable,     label: 'Equations', hint: 'Project-level named parameters (.equations)', color: 'text-kerf-300' },
  wiring:    { icon: Cable,        label: 'Wiring',    hint: 'Cable harness / wiring diagram (.wiring)',  color: 'text-orange-300' },
  section:     { icon: Scissors,    label: 'Section',       hint: 'Plane cross-section outline (.section)',         color: 'text-violet-300' },
  cam_layered: { icon: Layers,      label: 'Layered CAM',   hint: 'Stacked Z-slice contours for layered milling',  color: 'text-teal-300' },
  tool:        { icon: Wrench,      label: 'Tool',          hint: 'CNC tool definition for CAM (.tool)',           color: 'text-kerf-300' },
}

// Canonical menu order: folder + generic file first (basic primitives),
// followed by domain-specific kinds in roughly mechanical → drawings →
// library → electronics order. The `step` and `jscad` aliases are
// import-only / synthetic and intentionally absent here.
const KIND_ORDER = ['folder', 'file', 'sketch', 'assembly', 'drawing', 'feature', 'section', 'cam_layered', 'part', 'circuit', 'equations', 'wiring', 'tool']

// CreateMenu — single "+ New" dropdown that replaces the row of icon
// buttons in the FileTree header. Shows the full union of canonical
// kinds; STEP import is appended as a separate row. Closes on
// click-outside / Escape.
function CreateMenu({ onCreate, openImportPicker, openKicadPicker, openFreecadPicker }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)
  const visibleKinds = KIND_ORDER

  useEffect(() => {
    if (!open) return
    const onDoc = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('mousedown', onDoc)
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('mousedown', onDoc)
      window.removeEventListener('keydown', onKey)
    }
  }, [open])

  const pick = (action) => {
    setOpen(false)
    setTimeout(action, 0)
  }

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium text-ink-200 hover:text-kerf-300 hover:bg-ink-800 border border-ink-700 hover:border-ink-600"
        title="Create a new file or folder, or import a STEP file"
      >
        <Plus size={12} />
        <span>New</span>
        <ChevronDown size={11} className={`transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <div
          className="absolute right-0 top-full mt-1 z-40 min-w-[220px] bg-ink-850 border border-ink-700 rounded-md shadow-lg py-1"
          onClick={(e) => e.stopPropagation()}
        >
          {visibleKinds.map((kind, i) => {
            const row = KIND_ROWS[kind]
            // Insert a separator after the last basic (folder/file) entry
            // when transitioning to the domain-specific kinds — preserves
            // the visual grouping the menu had pre-refactor.
            const isBasic = kind === 'file' || kind === 'folder'
            const prevBasic = i > 0 && (visibleKinds[i - 1] === 'file' || visibleKinds[i - 1] === 'folder')
            const showSeparator = !isBasic && prevBasic
            return (
              <span key={kind}>
                {showSeparator && <div className="my-1 border-t border-ink-800" />}
                <CreateRow
                  icon={row.icon}
                  label={row.label}
                  hint={row.hint}
                  color={row.color}
                  onClick={() => pick(() => onCreate?.(null, kind))}
                />
              </span>
            )
          })}
          <div className="my-1 border-t border-ink-800" />
          <CreateRow icon={Upload} label="Upload STEP" hint="import binary CAD" color="text-cyan-edge"
            onClick={() => pick(() => openImportPicker?.())} />
          <CreateRow icon={CircuitBoard} label="Import KiCad" hint=".kicad_sch / .kicad_pcb" color="text-cyan-edge"
            onClick={() => pick(() => openKicadPicker?.())} />
          <CreateRow icon={FileBox} label="Import FreeCAD" hint=".FCStd — FreeCAD 0.19+" color="text-orange-300"
            onClick={() => pick(() => openFreecadPicker?.())} />
        </div>
      )}
    </div>
  )
}

function CreateRow({ icon: Icon, label, hint, color = 'text-ink-200', onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={hint ? `${label} — ${hint}` : label}
      className="w-full flex items-start gap-2.5 px-3 py-1.5 text-left hover:bg-ink-800 group"
    >
      <Icon size={14} className={`mt-0.5 ${color}`} />
      <span className="flex-1 min-w-0">
        <span className="block text-[12px] text-ink-100 group-hover:text-kerf-200">{label}</span>
        {hint && <span className="block text-[10px] text-ink-400 leading-tight">{hint}</span>}
      </span>
    </button>
  )
}

function ContextMenu({ x, y, onClose, onRename, onDelete, onNewFile, onNewFolder, onNewAssembly, onNewDrawing, onNewSketch, onNewPart, onNewFeature, onNewSection, onNewCircuit, onImportStep }) {
  useEffect(() => {
    const close = () => onClose()
    window.addEventListener('click', close)
    window.addEventListener('contextmenu', close)
    return () => {
      window.removeEventListener('click', close)
      window.removeEventListener('contextmenu', close)
    }
  }, [onClose])

  return (
    <div
      className="fixed z-50 min-w-[170px] bg-ink-850 border border-ink-700 rounded-md shadow-lg py-1"
      style={{ left: x, top: y }}
      onClick={(e) => e.stopPropagation()}
      onContextMenu={(e) => { e.preventDefault(); e.stopPropagation() }}
    >
      <MenuItem icon={FilePlus} label="New file" action={onNewFile} />
      <MenuItem icon={FolderPlus} label="New folder" action={onNewFolder} />
      <MenuItem icon={Layers} label="New assembly" action={onNewAssembly} />
      <MenuItem icon={Ruler} label="New drawing" action={onNewDrawing} />
      <MenuItem icon={PenTool} label="New sketch" action={onNewSketch} />
      <MenuItem icon={Cylinder} label="New feature" action={onNewFeature} />
      <MenuItem icon={Scissors} label="New section" action={onNewSection} />
      <MenuItem icon={CircuitBoard} label="New circuit" action={onNewCircuit} />
      <MenuItem icon={Package} label="New part" action={onNewPart} />
      <MenuItem icon={Box} label="Import .step…" action={onImportStep} />
      {(onNewFile || onNewFolder || onNewAssembly || onNewDrawing || onNewSketch || onNewPart || onNewFeature || onNewCircuit || onImportStep) && <div className="my-1 border-t border-ink-700" />}
      <MenuItem icon={FileCode} label="Rename (F2)" action={onRename} />
      <MenuItem icon={Trash2} label="Delete" action={onDelete} />
    </div>
  )
}

export default function FileTree({ files, currentFileId, onSelect, onCreate, onRename, onDelete, onImportStep, onImportKicad, onImportFreecad, jscadSketchLinks }) {
  const byParent = useMemo(() => buildTree(files || []), [files])
  const roots = byParent.get('__root__') || []
  const [expanded, setExpanded] = useState(() => new Set(
    (files || []).filter((f) => f.kind === 'folder').map((f) => f.id),
  ))
  const [renamingId, setRenamingId] = useState(null)
  const [menu, setMenu] = useState(null)
  const [kicadImporting, setKicadImporting] = useState(false)
  const [freecadDialogOpen, setFreecadDialogOpen] = useState(false)
  const [kicadError, setKicadError] = useState(null)
  const fileInputRef = useRef(null)
  const kicadInputRef = useRef(null)
  const importTargetRef = useRef(null) // parent_id at the time the picker opened
  // Stash the last-picked browser File alongside its parent so the upload
  // progress strip's "Retry" button can re-fire the import without making
  // the user re-pick the file.
  const lastPickRef = useRef(null) // {file, parentId} | null
  const w = useWorkspace()
  // Subscribe to the jscadSketchLinks map from the workspace store so the
  // backlink chips update when new .jscad files are opened / created.
  const storeLinks = useWorkspace((s) => s.jscadSketchLinks)
  // Caller can pass an explicit map (useful for tests); fall back to the store.
  const resolvedLinks = jscadSketchLinks || storeLinks

  const toggle = (id) => setExpanded((s) => {
    const next = new Set(s)
    if (next.has(id)) next.delete(id); else next.add(id)
    return next
  })

  function openImportPicker(parentId = null) {
    importTargetRef.current = parentId
    if (fileInputRef.current) {
      fileInputRef.current.value = '' // reset so same file can be re-picked
      fileInputRef.current.click()
    }
  }

  function openKicadPicker() {
    if (kicadInputRef.current) {
      kicadInputRef.current.value = ''
      kicadInputRef.current.click()
    }
  }

  function openFreecadPicker() {
    setFreecadDialogOpen(true)
  }

  function onFilePicked(e) {
    const file = e.target.files?.[0]
    if (!file) return
    lastPickRef.current = { file, parentId: importTargetRef.current }
    onImportStep?.(file, importTargetRef.current)
  }

  async function onKicadFilePicked(e) {
    const file = e.target.files?.[0]
    if (!file) return
    setKicadImporting(true)
    setKicadError(null)
    try {
      if (onImportKicad) {
        await onImportKicad(file)
      } else {
        // Default: call the API directly using the workspace project id
        const { projectId, accessToken } = w
        const API_URL = import.meta.env.VITE_API_URL || ''
        const form = new FormData()
        form.append('file', file, file.name)
        const resp = await fetch(`${API_URL}/api/projects/${projectId}/imports/kicad`, {
          method: 'POST',
          headers: { authorization: `Bearer ${accessToken}` },
          body: form,
        })
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({ detail: resp.statusText }))
          throw new Error(err.detail || `HTTP ${resp.status}`)
        }
        const data = await resp.json()
        w.setState({ toast: `KiCad imported → ${data.filename}` })
        // Refresh file list
        w.loadFiles?.()
      }
    } catch (err) {
      setKicadError(err.message || 'KiCad import failed')
    } finally {
      setKicadImporting(false)
    }
  }

  function retryLastImport() {
    const last = lastPickRef.current
    if (!last) return
    onImportStep?.(last.file, last.parentId)
  }

  return (
    <div className="h-full flex flex-col bg-ink-900 text-ink-100 min-h-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800 flex-shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">Files</span>
        <CreateMenu
          onCreate={onCreate}
          openImportPicker={() => openImportPicker(null)}
          openKicadPicker={openKicadPicker}
          openFreecadPicker={openFreecadPicker}
        />
      </div>
      <input
        ref={fileInputRef}
        type="file"
        accept=".step,.stp,model/step"
        className="hidden"
        onChange={onFilePicked}
      />
      <input
        ref={kicadInputRef}
        type="file"
        accept=".kicad_sch,.kicad_pcb,.zip"
        className="hidden"
        onChange={onKicadFilePicked}
      />
      {kicadImporting && (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-ink-850 border-b border-ink-700 text-[11px] text-ink-300">
          <Loader2 size={12} className="animate-spin text-kerf-300 shrink-0" />
          <span>Importing KiCad…</span>
        </div>
      )}
      {kicadError && (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-red-950/40 border-b border-red-700/50 text-[11px] text-red-200">
          <AlertCircle size={12} className="shrink-0" />
          <span className="flex-1 truncate">{kicadError}</span>
          <button type="button" onClick={() => setKicadError(null)} className="hover:text-red-100"><X size={11} /></button>
        </div>
      )}
      <UploadProgressStrip onRetry={retryLastImport} />
      {freecadDialogOpen && (
        <FreeCADImportDialog
          projectId={w.projectId ?? null}
          open={freecadDialogOpen}
          onClose={() => setFreecadDialogOpen(false)}
          onImported={(result) => {
            setFreecadDialogOpen(false)
            onImportFreecad?.(result)
            w.loadFiles?.()
          }}
        />
      )}
      <div
        className="flex-1 overflow-auto py-1 min-h-0"
        onContextMenu={(e) => {
          if (e.target === e.currentTarget) {
            e.preventDefault()
            setMenu({ x: e.clientX, y: e.clientY })
          }
        }}
        onDragOver={(e) => {
          // Accept .FCStd drags onto the tree background.
          const items = e.dataTransfer?.items
          if (items) {
            for (const item of items) {
              if (item.kind === 'file') { e.preventDefault(); break }
            }
          }
        }}
        onDrop={(e) => {
          const file = e.dataTransfer?.files?.[0]
          if (!file) return
          if (isFCStdFile(file)) {
            e.preventDefault()
            setFreecadDialogOpen(true)
            // Defer: dialog is now open — user can see the drop zone.
            // We auto-trigger the import directly without re-picking.
            // Store the dropped file so the dialog can kick off immediately.
            // We use a small trick: open the dialog and programmatically
            // start the import by dispatching a synthetic CustomEvent that
            // FreeCADImportDialog listens for via the window.
            window.dispatchEvent(new CustomEvent('kerf:fcstd-drop', { detail: { file } }))
          }
        }}
      >
        {roots.length === 0 ? (
          <div className="px-3 py-6 text-xs text-ink-400 text-center">
            No files yet.<br />
            <button
              type="button"
              className="mt-2 text-kerf-300 hover:underline"
              onClick={() => onCreate?.(null, 'file')}
            >
              Create one
            </button>
          </div>
        ) : roots.map((f) => (
          <Node
            key={f.id}
            file={f}
            depth={0}
            byParent={byParent}
            expanded={expanded}
            toggle={toggle}
            currentFileId={currentFileId}
            onSelect={onSelect}
            onCreate={onCreate}
            onRename={onRename}
            onDelete={onDelete}
            onImportStep={openImportPicker}
            renamingId={renamingId}
            setRenamingId={setRenamingId}
            jscadSketchLinks={resolvedLinks}
          />
        ))}
      </div>
      {menu && (
        <ContextMenu
          x={menu.x} y={menu.y}
          onClose={() => setMenu(null)}
          onNewFile={() => { onCreate?.(null, 'file'); setMenu(null) }}
          onNewFolder={() => { onCreate?.(null, 'folder'); setMenu(null) }}
          onNewAssembly={() => { onCreate?.(null, 'assembly'); setMenu(null) }}
          onNewDrawing={() => { onCreate?.(null, 'drawing'); setMenu(null) }}
          onNewSketch={() => { onCreate?.(null, 'sketch'); setMenu(null) }}
          onNewFeature={() => { onCreate?.(null, 'feature'); setMenu(null) }}
          onNewCircuit={() => { onCreate?.(null, 'circuit'); setMenu(null) }}
          onNewPart={() => { onCreate?.(null, 'part'); setMenu(null) }}
          onImportStep={() => { openImportPicker(null); setMenu(null) }}
        />
      )}
    </div>
  )
}
