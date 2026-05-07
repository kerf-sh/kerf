import { useEffect, useMemo, useRef, useState } from 'react'
import { Eye, EyeOff, Focus, Box, MoreVertical, Check, Copy, Trash2 } from 'lucide-react'
import { useWorkspace } from '../store/workspace.js'
import { exportParts, downloadBlob, FORMATS } from '../lib/exporters.js'
import { duplicateObject, deleteObject } from '../lib/jscadObjectOps.js'

// Palette must match Renderer.jsx so swatches line up with what's drawn.
const PALETTE = [0xc9a96b, 0x6b9bc9, 0xc96b89, 0x89c96b, 0xc9b86b, 0x9b6bc9]
function hex(c) { return '#' + c.toString(16).padStart(6, '0') }
function hexToRgb(h) {
  const m = /^#?([0-9a-f]{6})$/i.exec(h)
  if (!m) return [1, 1, 1]
  const n = parseInt(m[1], 16)
  return [((n >> 16) & 0xff) / 255, ((n >> 8) & 0xff) / 255, (n & 0xff) / 255]
}

// Per-row export submenu is rendered inline below; the big "export all" button
// lives in the top bar (ExportButton) — see Editor.jsx.

export default function ObjectsPanel({
  parts = [],
  hiddenIds,
  selectedId,
  onToggleVisibility,
  onSelect,
  onIsolate,
  onShowAll,
  // New (optional; gracefully no-op for STEP):
  onRecolorPart,
  onMovePart,
  onSetPartPosition,
  isStepFile = false,
}) {
  const [hover, setHover] = useState(null)
  const [openKebab, setOpenKebab] = useState(null)
  const [openColor, setOpenColor] = useState(null)
  const [openRowExport, setOpenRowExport] = useState(null)
  const [exportError, setExportError] = useState(null)
  const [opError, setOpError] = useState(null)
  const colorInputRefs = useRef({})
  const hidden = hiddenIds || new Set()

  // Per-row export still uses the workspace store for project context.
  const currentFile = useWorkspace((s) => s.currentFile)
  const baseName = currentFile?.name || 'export'
  // Source mutators for duplicate/delete. We pull the live content + the
  // editContent + saveFile actions so the operation goes through the same
  // PATCH path as autosave — that writes a `file_revisions` row and so
  // Cmd+Z naturally undoes the duplicate/delete.
  const currentFileContent = useWorkspace((s) => s.currentFileContent)
  const editContent = useWorkspace((s) => s.editContent)
  const saveFile = useWorkspace((s) => s.saveFile)

  // Close kebab on outside click. Row export popover is part of the kebab tree
  // so clicking outside the kebab also dismisses it.
  useEffect(() => {
    function handler() {
      setOpenKebab(null)
      setOpenRowExport(null)
    }
    window.addEventListener('click', handler)
    return () => window.removeEventListener('click', handler)
  }, [])

  // Auto-clear the transient export error toast.
  useEffect(() => {
    if (!exportError) return
    const t = setTimeout(() => setExportError(null), 4000)
    return () => clearTimeout(t)
  }, [exportError])
  useEffect(() => {
    if (!opError) return
    const t = setTimeout(() => setOpError(null), 4000)
    return () => clearTimeout(t)
  }, [opError])

  // Apply a source-string mutation: replace currentFileContent and route
  // through saveFile. The store's `editContent` flips the dirty flag; we
  // immediately call saveFile so the revision row is written without
  // waiting for the autosave timer.
  async function applySourceMutation(nextSource) {
    if (typeof nextSource !== 'string') return
    editContent(nextSource)
    // Flush the next save synchronously — saveFile reads currentFileContent
    // via the store getter, so by the time we call it the new value is
    // already in place.
    await saveFile()
  }

  function handleDuplicate(partId) {
    if (isStepFile) return
    const next = duplicateObject(currentFileContent, partId)
    if (next == null) {
      setOpError("Couldn't auto-duplicate — edit the code by hand or ask chat.")
      return
    }
    applySourceMutation(next)
  }

  function handleDeleteObject(partId) {
    if (isStepFile) return
    const next = deleteObject(currentFileContent, partId)
    if (next == null) {
      setOpError("Couldn't auto-delete — edit the code by hand or ask chat.")
      return
    }
    applySourceMutation(next)
  }

  // For STEP files we suppress the JSCAD JSON option (BufferGeometry can't
  // round-trip through JSCAD's polygon format).
  const availableFormats = useMemo(
    () => FORMATS.filter((f) => !(isStepFile && f.jscadOnly)),
    [isStepFile],
  )

  function visibleParts() {
    return parts.filter((p) => !hidden.has(p.id))
  }

  async function doExport(format, partId = null) {
    try {
      const subset = partId
        ? parts.filter((p) => p.id === partId)
        : visibleParts()
      if (subset.length === 0) {
        setExportError(partId ? 'Part not found' : 'No visible parts to export')
        return
      }
      const { blob, filename } = await exportParts(subset, format, {
        baseName,
        singlePartId: partId || null,
      })
      downloadBlob(blob, filename)
    } catch (err) {
      setExportError(err?.message || 'Export failed')
    }
  }

  // For the per-row kebab "quick export" we surface a few common formats first
  // then "More…" opens the full picker scoped to the row.
  const quickRowFormats = useMemo(
    () => availableFormats.filter((f) => ['stl-binary', 'obj', 'glb'].includes(f.id)),
    [availableFormats],
  )

  return (
    <div className="h-full flex flex-col bg-ink-900 text-ink-100 min-h-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800 flex-shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">
          Objects
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-ink-500 font-mono">
            {parts.length - hidden.size}/{parts.length}
          </span>
          {hidden.size > 0 && (
            <button
              type="button"
              onClick={onShowAll}
              className="text-[10px] text-kerf-300 hover:text-kerf-200"
              title="Show all"
            >
              show all
            </button>
          )}
          {/* Export-all moved to the top bar (ExportButton). Per-part export
              still lives in each row's kebab menu below. */}
        </div>
      </div>
      {exportError && (
        <div className="px-3 py-1.5 bg-red-900/30 border-b border-red-800/50 text-[10px] text-red-300 flex items-center justify-between gap-2">
          <span className="truncate">{exportError}</span>
          <button
            type="button"
            onClick={() => setExportError(null)}
            className="text-red-300 hover:text-red-100 flex-shrink-0"
            title="Dismiss"
          >
            <Check size={11} />
          </button>
        </div>
      )}
      {opError && (
        <div className="px-3 py-1.5 bg-amber-900/30 border-b border-amber-800/50 text-[10px] text-amber-300 flex items-center justify-between gap-2">
          <span className="truncate">{opError}</span>
          <button
            type="button"
            onClick={() => setOpError(null)}
            className="text-amber-300 hover:text-amber-100 flex-shrink-0"
            title="Dismiss"
          >
            <Check size={11} />
          </button>
        </div>
      )}
      <div className="flex-1 overflow-auto py-1 min-h-0">
        {parts.length === 0 ? (
          <div className="px-3 py-6 text-xs text-ink-500 text-center">
            <Box size={16} className="mx-auto mb-2 text-ink-700" />
            No objects in this file
          </div>
        ) : parts.map((p, i) => {
          const isHidden = hidden.has(p.id)
          const isSelected = selectedId === p.id
          const isHover = hover === p.id
          const swatchHex = p.color != null ? hex(p.color) : hex(PALETTE[i % PALETTE.length])

          return (
            <div
              key={p.id}
              onMouseEnter={() => setHover(p.id)}
              onMouseLeave={() => setHover(null)}
              onClick={() => onSelect?.(p.id)}
              className={`group flex items-center gap-1.5 px-2 py-[3px] cursor-pointer rounded-sm select-none ${
                isSelected
                  ? 'bg-kerf-300/15 text-kerf-100'
                  : 'hover:bg-ink-800 text-ink-200'
              } ${isHidden ? 'opacity-50' : ''}`}
            >
              {/* Color swatch (clickable when not STEP) */}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  if (isStepFile) return
                  setOpenColor(p.id)
                  // Trigger native color picker.
                  setTimeout(() => colorInputRefs.current[p.id]?.click(), 0)
                }}
                disabled={isStepFile}
                title={isStepFile ? 'STEP files are read-only' : 'Edit color'}
                className={`w-3 h-3 rounded-sm border border-ink-700 flex-shrink-0 ${
                  isStepFile ? 'cursor-not-allowed' : 'cursor-pointer hover:border-kerf-300'
                }`}
                style={{ backgroundColor: swatchHex }}
              />
              {/* Hidden native color input — opened above. */}
              {!isStepFile && (
                <input
                  ref={(el) => { colorInputRefs.current[p.id] = el }}
                  type="color"
                  defaultValue={swatchHex}
                  onClick={(e) => e.stopPropagation()}
                  onChange={(e) => onRecolorPart?.(p.id, hexToRgb(e.target.value))}
                  className="absolute opacity-0 w-0 h-0 pointer-events-none"
                />
              )}
              {/* Visibility toggle */}
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation()
                  onToggleVisibility?.(p.id)
                }}
                className="text-ink-300 hover:text-kerf-300 flex-shrink-0 p-0.5"
                title={isHidden ? 'Show' : 'Hide'}
              >
                {isHidden
                  ? <EyeOff size={12} />
                  : <Eye size={12} />}
              </button>
              <span className="flex-1 text-xs font-mono truncate">{p.id}</span>
              {isHover && parts.length > 1 && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    onIsolate?.(p.id)
                  }}
                  className="text-ink-400 hover:text-kerf-300 flex-shrink-0 p-0.5"
                  title="Isolate (hide others)"
                >
                  <Focus size={11} />
                </button>
              )}
              {/* Kebab menu (position quick actions + per-part export) */}
              <div className="relative flex-shrink-0">
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation()
                    setOpenKebab(openKebab === p.id ? null : p.id)
                    setOpenRowExport(null)
                  }}
                  className="text-ink-400 hover:text-kerf-300 p-0.5"
                  title="More"
                >
                  <MoreVertical size={11} />
                </button>
                {openKebab === p.id && (
                  <div
                    className="absolute right-0 top-full mt-1 z-30 w-44 rounded-md bg-ink-850 border border-ink-700 shadow-xl text-[11px] text-ink-200 py-1"
                    onClick={(e) => e.stopPropagation()}
                  >
                    {!isStepFile && (
                      <>
                        <KebabItem onClick={() => { handleDuplicate(p.id); setOpenKebab(null) }}>
                          <Copy size={11} className="text-ink-400" />
                          Duplicate
                        </KebabItem>
                        <KebabItem onClick={() => { handleDeleteObject(p.id); setOpenKebab(null) }}>
                          <Trash2 size={11} className="text-red-400" />
                          <span className="text-red-300">Delete</span>
                        </KebabItem>
                        <div className="my-1 border-t border-ink-800" />
                        <KebabItem onClick={() => { onSetPartPosition?.(p.id, [0, 0, 0]); setOpenKebab(null) }}>
                          Move to origin
                        </KebabItem>
                        <KebabItem onClick={() => { onMovePart?.(p.id, [0, 0, 5]); setOpenKebab(null) }}>
                          Bring to front (Z+5)
                        </KebabItem>
                        <KebabItem onClick={() => { onMovePart?.(p.id, [0, 0, -5]); setOpenKebab(null) }}>
                          Send to back (Z-5)
                        </KebabItem>
                        <div className="my-1 border-t border-ink-800" />
                      </>
                    )}
                    <div className="px-2.5 py-1 text-[9px] uppercase tracking-wider text-ink-500 font-semibold">
                      Export this part
                    </div>
                    {quickRowFormats.map((f) => (
                      <KebabItem
                        key={f.id}
                        onClick={() => {
                          doExport(f.id, p.id)
                          setOpenKebab(null)
                        }}
                      >
                        Export as {f.label}
                      </KebabItem>
                    ))}
                    <KebabItem
                      onClick={() => {
                        setOpenRowExport(p.id)
                      }}
                    >
                      More formats…
                    </KebabItem>
                    {openRowExport === p.id && (
                      <div className="absolute left-full top-0 ml-1 z-40">
                        <div
                          className="w-44 rounded-md bg-ink-850 border border-ink-700 shadow-xl text-[11px] text-ink-200 py-1"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div className="px-2.5 py-1 text-[9px] uppercase tracking-wider text-ink-500 font-semibold">
                            Export {p.id} as
                          </div>
                          {availableFormats.map((f) => (
                            <button
                              key={f.id}
                              type="button"
                              onClick={() => {
                                doExport(f.id, p.id)
                                setOpenKebab(null)
                                setOpenRowExport(null)
                              }}
                              className="w-full text-left px-2.5 py-1 hover:bg-ink-800 hover:text-kerf-300 flex items-center gap-2"
                            >
                              <span className="flex-1 truncate">{f.label}</span>
                              <span className="text-ink-500 font-mono text-[10px]">.{f.ext}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
      {openColor && null /* state is managed via the input itself */}
    </div>
  )
}

function KebabItem({ children, onClick }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full text-left px-2.5 py-1 hover:bg-ink-800 hover:text-kerf-300 flex items-center gap-2"
    >
      {children}
    </button>
  )
}
