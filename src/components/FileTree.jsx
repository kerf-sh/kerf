import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ChevronDown, ChevronRight,
  FileCode, Folder, FolderOpen, Layers,
  FilePlus, FolderPlus, Plus, Trash2, Box, Upload,
} from 'lucide-react'

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
  const lower = (name || '').toLowerCase()
  if (lower.endsWith('.step') || lower.endsWith('.stp')) {
    return <Box size={14} className={`${cls} text-cyan-edge`} />
  }
  return <FileCode size={14} className={`${cls} text-ink-200`} />
}

function Node({ file, depth, byParent, expanded, toggle, currentFileId, onSelect, onCreate, onRename, onDelete, onImportStep, renamingId, setRenamingId }) {
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
          <span className="flex-1 text-xs font-mono truncate">{file.name}</span>
        )}
        {isFolder && (
          <button
            type="button"
            className="opacity-0 group-hover:opacity-100 text-ink-400 hover:text-kerf-300"
            title="New file"
            onClick={(e) => {
              e.stopPropagation()
              if (!isOpen) toggle(file.id)
              onCreate?.(file.id, 'file')
            }}
          >
            <Plus size={12} />
          </button>
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

function ContextMenu({ x, y, onClose, onRename, onDelete, onNewFile, onNewFolder, onNewAssembly, onImportStep }) {
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
      <MenuItem icon={Box} label="Import .step…" action={onImportStep} />
      {(onNewFile || onNewFolder || onNewAssembly || onImportStep) && <div className="my-1 border-t border-ink-700" />}
      <MenuItem icon={FileCode} label="Rename (F2)" action={onRename} />
      <MenuItem icon={Trash2} label="Delete" action={onDelete} />
    </div>
  )
}

export default function FileTree({ files, currentFileId, onSelect, onCreate, onRename, onDelete, onImportStep }) {
  const byParent = useMemo(() => buildTree(files || []), [files])
  const roots = byParent.get('__root__') || []
  const [expanded, setExpanded] = useState(() => new Set(
    (files || []).filter((f) => f.kind === 'folder').map((f) => f.id),
  ))
  const [renamingId, setRenamingId] = useState(null)
  const [menu, setMenu] = useState(null)
  const fileInputRef = useRef(null)
  const importTargetRef = useRef(null) // parent_id at the time the picker opened

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

  function onFilePicked(e) {
    const file = e.target.files?.[0]
    if (!file) return
    onImportStep?.(file, importTargetRef.current)
  }

  return (
    <div className="h-full flex flex-col bg-ink-900 text-ink-100 min-h-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800 flex-shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">Files</span>
        <div className="flex items-center gap-1">
          <button
            type="button"
            className="p-1 rounded hover:bg-ink-700 text-ink-300 hover:text-kerf-300"
            title="Import .step / .stp"
            onClick={() => openImportPicker(null)}
          >
            <Upload size={13} />
          </button>
          <button
            type="button"
            className="p-1 rounded hover:bg-ink-700 text-ink-300 hover:text-kerf-300"
            title="New file"
            onClick={() => onCreate?.(null, 'file')}
          >
            <FilePlus size={13} />
          </button>
          <button
            type="button"
            className="p-1 rounded hover:bg-ink-700 text-ink-300 hover:text-kerf-300"
            title="New folder"
            onClick={() => onCreate?.(null, 'folder')}
          >
            <FolderPlus size={13} />
          </button>
        </div>
      </div>
      <input
        ref={fileInputRef}
        type="file"
        accept=".step,.stp,model/step"
        className="hidden"
        onChange={onFilePicked}
      />
      <div
        className="flex-1 overflow-auto py-1 min-h-0"
        onContextMenu={(e) => {
          if (e.target === e.currentTarget) {
            e.preventDefault()
            setMenu({ x: e.clientX, y: e.clientY })
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
          onImportStep={() => { openImportPicker(null); setMenu(null) }}
        />
      )}
    </div>
  )
}
