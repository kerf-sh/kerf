// AssemblyEditor — visual editor for an assembly file's components.
//
// Vocabulary (CONTRACT.md): a Part is a whole .jscad file; an Object is one
// entry in its exported array; a Component is an Assembly's instance of a
// single Object placed at a transform.
//
// This component exposes Position / Rotation / Scale fields per row and
// debounces every change into the parent's onChange (which writes to the
// store + persists). Selecting a row highlights its part in the renderer.
//
// Insert flow:
//   - "Add component" opens a Part picker. Picking a Part with a single
//     Object adds it directly. Picking one with 2+ Objects opens an Insert
//     dialog where the user chooses which Objects to place and whether they
//     should share a transform (rigid group) or each get identity.
//
// Legacy `*` migration: components with object_id === "*" are auto-expanded
// on first display once the source's Object list resolves. The expanded list
// is emitted via onChange so the next save migrates the file.
//
// We intentionally keep the in-memory representation as the rich
// {position, rotationDeg, scale} tuple per row and re-compose into the
// 16-number transform on every emit — that way decompose round-trips
// cleanly even when the underlying matrix gets edited from JSON view.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Eye, EyeOff, GripVertical, Layers, Plus, Trash2, ChevronDown, ChevronRight,
  Loader2, X, Check, AlertTriangle, ExternalLink, Link2, Link2Off,
} from 'lucide-react'
import {
  composeMatrix, decomposeMatrix, identityMatrix, parseAssembly,
  serializeAssembly, cycleCheck, radToDeg, degToRad, expandWildcardComponents,
  restampExternalRefSeen, LEGACY_WILDCARD, addMate, removeMate,
} from '../lib/assembly.js'
import { loadFilePartsForProject } from '../store/workspace.js'
import { api } from '../lib/api.js'
import LibraryPicker from './LibraryPicker.jsx'
import InlineBOMPanel from './InlineBOMPanel.jsx'
import MatesPanel from './MatesPanel.jsx'

// Module-scoped cache of file_id → Promise<string[]> of object ids. Re-used
// across rows so opening the same source twice doesn't re-run JSCAD.
const objectIdCache = new Map()
function getObjectIds(projectId, fileId) {
  const k = `${projectId}::${fileId}`
  let p = objectIdCache.get(k)
  if (p) return p
  p = (async () => {
    try {
      const parts = await loadFilePartsForProject(projectId, fileId)
      return (parts || []).map((x) => x.id).filter(Boolean)
    } catch (err) {
      console.warn('AssemblyEditor: failed to load source objects', err)
      return []
    }
  })()
  objectIdCache.set(k, p)
  return p
}

const DEBOUNCE_MS = 350

// Decompose a row-major 16-array → editor row state.
function fromTransform(t) {
  const d = decomposeMatrix(Array.isArray(t) && t.length === 16 ? t : identityMatrix())
  // Uniform scale heuristic: if all 3 are equal-ish, expose one number;
  // otherwise the editor falls back to the first axis (and we keep the row's
  // matrix authoritative — power-users can edit the JSON view for anisotropy).
  const sX = Number(d.scale[0]) || 1
  const sY = Number(d.scale[1]) || 1
  const sZ = Number(d.scale[2]) || 1
  const uniformScale = (Math.abs(sX - sY) < 1e-6 && Math.abs(sX - sZ) < 1e-6) ? sX : sX
  return {
    position: [d.position[0], d.position[1], d.position[2]],
    rotationDeg: [radToDeg(d.rotationEuler[0]), radToDeg(d.rotationEuler[1]), radToDeg(d.rotationEuler[2])],
    scale: uniformScale,
  }
}

function toTransform({ position, rotationDeg, scale }) {
  return composeMatrix({
    position,
    rotationEuler: [degToRad(rotationDeg[0] || 0), degToRad(rotationDeg[1] || 0), degToRad(rotationDeg[2] || 0)],
    scale: Number(scale) || 1,
  })
}

// Build an editor "view" of components — augments raw rows with TRS so the
// inputs can be controlled. Memoized off the assembly.components reference.
function deriveRows(assembly) {
  return (assembly.components || []).map((c) => ({
    id: c.id,
    file_id: c.file_id,
    object_id: c.object_id || LEGACY_WILDCARD,
    visible: c.visible !== false,
    color: c.color || null,
    params: c.params || null,
    // Preserve cross-project external_ref so the row can show the freshness
    // chip and the resolver can still dispatch via loadExternalParts. The
    // editor doesn't expose an external_ref editor yet — we just round-trip
    // the blob untouched.
    external_ref: c.external_ref || null,
    ...fromTransform(c.transform),
  }))
}

// Reverse: rows → assembly JSON object (same shape parseAssembly accepts).
function rowsToAssembly(rows) {
  return {
    components: rows.map((r) => {
      const out = {
        id: r.id,
        file_id: r.file_id,
        object_id: r.object_id || LEGACY_WILDCARD,
        transform: toTransform(r),
      }
      if (r.visible === false) out.visible = false
      if (r.color) out.color = r.color
      if (r.params) out.params = r.params
      if (r.external_ref) out.external_ref = r.external_ref
      return out
    }),
  }
}

export default function AssemblyEditor({
  content,                  // string: the assembly file's raw JSON content
  files,                    // File[] — every file in the project (no content)
  projectId,                // string — needed to fetch source objects for the dropdown
  currentFileId,            // string — the assembly's own file id
  selectedComponentId,
  onSelectComponent,
  onChange,                 // (nextContentString) => void (debounced upstream OK; we debounce ourselves)
  onToast,                  // (msg) => void
}) {
  const parsed = useMemo(() => parseAssembly(content), [content])

  // Local rows mirror the server content but are owned by the editor so the
  // user's typing isn't fighting upstream re-renders. We resync if the
  // upstream content reference changes (e.g. LLM tool wrote the file).
  const [rows, setRows] = useState(() => deriveRows(parsed))
  // BOM overrides (BOM rework). Round-tripped through parseAssembly /
  // serializeAssembly. Authored by the inline BOM panel and serialized
  // alongside components — see emit() below.
  const [overrides, setOverrides] = useState(() => parsed.overrides || [])
  const [mates, setMates] = useState(() => parsed.mates || [])
  const [matesOpen, setMatesOpen] = useState(false)
  const [showJson, setShowJson] = useState(false)
  const [jsonDraft, setJsonDraft] = useState(content)
  const [jsonErr, setJsonErr] = useState(null)
  const [insertModal, setInsertModal] = useState(null) // { fileId, objectIds }
  const [pickerOpen, setPickerOpen] = useState(false)

  const lastEmittedRef = useRef(content)
  // Latest overrides snapshot — read by emit() so a row change in the same
  // tick as an override change still emits the right combined doc. Updated
  // on every setOverrides via emitOverrides.
  const overridesRef = useRef(overrides)
  const matesRef = useRef(mates)
  useEffect(() => { overridesRef.current = overrides }, [overrides])
  useEffect(() => { matesRef.current = mates }, [mates])
  useEffect(() => {
    // Upstream changed under us (e.g. LLM tool, undo). Reset local state.
    if (content !== lastEmittedRef.current) {
      const reparsed = parseAssembly(content)
      setRows(deriveRows(reparsed))
      setOverrides(reparsed.overrides || [])
      setMates(reparsed.mates || [])
      overridesRef.current = reparsed.overrides || []
      matesRef.current = reparsed.mates || []
      setJsonDraft(content)
      setJsonErr(null)
    }
  }, [content])

  // Debounced emit: every time `rows` changes, we re-serialize and call
  // onChange after 350ms of quiet. The overrides snapshot is pulled from a
  // ref so callers don't need to thread it through.
  const emitTimerRef = useRef(null)
  const emit = useCallback((nextRows, nextOverrides, nextMates) => {
    if (emitTimerRef.current) clearTimeout(emitTimerRef.current)
    const ov = nextOverrides !== undefined ? nextOverrides : overridesRef.current
    const ms = nextMates !== undefined ? nextMates : matesRef.current
    emitTimerRef.current = setTimeout(() => {
      const obj = rowsToAssembly(nextRows)
      obj.overrides = ov
      obj.mates = ms
      const json = serializeAssembly(obj)
      lastEmittedRef.current = json
      setJsonDraft(json)
      onChange?.(json)
    }, DEBOUNCE_MS)
  }, [onChange])
  useEffect(() => () => { if (emitTimerRef.current) clearTimeout(emitTimerRef.current) }, [])

  // Override edits are authored by the InlineBOMPanel — replace the whole
  // overrides list, update the ref so a concurrent row edit picks it up, and
  // re-emit (using the latest rows from state).
  const onChangeOverrides = useCallback((nextOverrides) => {
    overridesRef.current = nextOverrides
    setOverrides(nextOverrides)
    setRows((rs) => {
      emit(rs, nextOverrides, matesRef.current)
      return rs
    })
  }, [emit])

  // Mate edits are authored by the MatesPanel — replace the whole mates list,
  // update the ref so a concurrent row edit picks it up, and re-emit.
  const onChangeMates = useCallback((nextMates) => {
    matesRef.current = nextMates
    setMates(nextMates)
    emit(rows, overridesRef.current, nextMates)
  }, [emit])

  // Auto-expand any legacy `*` components once the source's Object list is
  // available. Only fires when there's actually a wildcard to migrate so we
  // don't pay any I/O on modern files.
  const migratedRef = useRef(false)
  useEffect(() => {
    if (migratedRef.current) return
    if (!projectId) return
    const hasWildcard = rows.some((r) => r.object_id === LEGACY_WILDCARD)
    if (!hasWildcard) return
    let cancelled = false
    ;(async () => {
      const { components, changed } = await expandWildcardComponents(
        rowsToAssembly(rows),
        (fileId) => getObjectIds(projectId, fileId),
      )
      if (cancelled || !changed) return
      migratedRef.current = true
      const next = deriveRows({ components })
      setRows(next)
      // Persist the migration. Bypass the debounce: this is one-off cleanup,
      // not user typing. Carry through any existing overrides so the migration
      // doesn't drop them.
      const json = serializeAssembly({ components, overrides: overridesRef.current })
      lastEmittedRef.current = json
      setJsonDraft(json)
      onChange?.(json)
    })()
    return () => { cancelled = true }
  }, [projectId, rows, onChange])

  // Files dropdown — exclude folders, the assembly itself, and any file that
  // would form a cycle if referenced from this assembly.
  const eligibleFiles = useMemo(() => {
    const list = (files || []).filter((f) => f.kind !== 'folder' && f.id !== currentFileId)
    // Filter out cycle-forming candidates.
    return list.filter((f) => {
      if (f.kind !== 'assembly') return true
      const ok = !cycleCheck({
        assemblyFileId: currentFileId,
        targetFileId: f.id,
        files,
        getAssemblyContent: (file) => file.content ?? null,
      })
      return ok
    })
  }, [files, currentFileId])

  // ---- Mutators ----------------------------------------------------------

  function updateRow(idx, patch) {
    setRows((rs) => {
      const next = rs.map((r, i) => i === idx ? { ...r, ...patch } : r)
      emit(next)
      return next
    })
  }

  function changeFileId(idx, nextFileId) {
    if (!nextFileId) return
    if (nextFileId === currentFileId) {
      onToast?.("Can't reference the assembly itself")
      return
    }
    if (cycleCheck({
      assemblyFileId: currentFileId,
      targetFileId: nextFileId,
      files,
      getAssemblyContent: (file) => file.content ?? null,
    })) {
      onToast?.('That would create a cycle')
      return
    }
    // Source file changes invalidate the previously selected object_id. Pick
    // the first object from the new source once we've loaded the list. Until
    // it loads we temporarily set object_id to the first source name guess —
    // the renderer will skip the row gracefully if it can't find that id.
    getObjectIds(projectId, nextFileId).then((ids) => {
      const first = ids[0] || ''
      updateRow(idx, { file_id: nextFileId, object_id: first })
    }).catch(() => {
      updateRow(idx, { file_id: nextFileId, object_id: '' })
    })
  }

  function changeObjectId(idx, nextObjectId) {
    updateRow(idx, { object_id: nextObjectId || '' })
  }

  function rename(idx, nextId) {
    const trimmed = (nextId || '').trim()
    if (!trimmed) return
    // Enforce uniqueness within the assembly.
    const taken = rows.some((r, i) => i !== idx && r.id === trimmed)
    if (taken) {
      onToast?.('Component id must be unique')
      return
    }
    // Also rebind selection if this row is selected.
    if (selectedComponentId === rows[idx].id) onSelectComponent?.(trimmed)
    updateRow(idx, { id: trimmed })
  }

  // Open the Library picker. The picker supersedes the old project-local
  // Part dropdown — it surfaces both project-local Parts and the global
  // Library so the user picks from the full catalog. Selection is
  // forwarded to onPickPart() which then runs the same Object-loading
  // dialog that startInsert used to drive directly.
  function startInsert() {
    if (!projectId) {
      onToast?.('Project not yet loaded')
      return
    }
    setPickerOpen(true)
  }

  // Called by LibraryPicker when the user clicks a row. Mirrors the
  // single-vs-multi-Object branching that the legacy startInsert had.
  async function onPickPart(row) {
    setPickerOpen(false)
    const fileId = row?.file_id
    if (!fileId) return
    // Cycle guard: importing an assembly that references this assembly
    // would loop. Mirrors the check in changeFileId.
    if (fileId === currentFileId) {
      onToast?.("Can't reference the assembly itself")
      return
    }
    if (cycleCheck({
      assemblyFileId: currentFileId,
      targetFileId: fileId,
      files,
      getAssemblyContent: (file) => file.content ?? null,
    })) {
      onToast?.('That would create a cycle')
      return
    }
    setInsertModal({ fileId, loading: true, objectIds: [] })
    try {
      const ids = await getObjectIds(projectId, fileId)
      if (ids.length === 0) {
        onToast?.(`${row.name || 'Part'} has no Objects to insert`)
        setInsertModal(null)
        return
      }
      if (ids.length === 1) {
        // Skip the dialog for single-Object Parts.
        addComponentRows(fileId, ids, { rigid: false })
        setInsertModal(null)
        return
      }
      setInsertModal({ fileId, loading: false, objectIds: ids })
    } catch (err) {
      onToast?.(err?.message || 'Failed to load Objects')
      setInsertModal(null)
    }
  }

  // After the user picks a different Part inside the dialog, re-fetch its
  // Object list.
  async function reloadInsertObjects(fileId) {
    setInsertModal((m) => m ? { ...m, fileId, loading: true, objectIds: [] } : m)
    try {
      const ids = await getObjectIds(projectId, fileId)
      setInsertModal((m) => m ? { ...m, fileId, loading: false, objectIds: ids } : m)
    } catch (err) {
      onToast?.(err?.message || 'Failed to load Objects')
      setInsertModal(null)
    }
  }

  // Add N rows: one per (objectId), all referencing the same source file.
  // `rigid` = true → all share one freshly-minted identity transform (so the
  // rows move as a group when one is dragged). `rigid` = false → each row
  // gets its own identity transform.
  function addComponentRows(fileId, objectIds, { rigid }) {
    if (!fileId || !Array.isArray(objectIds) || objectIds.length === 0) return
    const sourceFile = (files || []).find((f) => f.id === fileId)
    const baseName = (sourceFile?.name || 'component').replace(/\.[^.]+$/, '') || 'component'
    setRows((rs) => {
      const usedIds = new Set(rs.map((r) => r.id))
      const newRows = []
      // For "rigid": every row gets the same {position, rotationDeg, scale}
      // tuple — they decompose to identity now, but since we share the object
      // reference, edits to one will propagate. We don't actually share state
      // across rows (that would be confusing for editing); we just start them
      // all at identity. The "rigid" affordance is documented in CONTRACT.md
      // and is implemented by giving every row an identical transform JSON.
      // Drag-to-move on one component still moves only that one — to keep
      // them locked, the user composes a parent assembly. (See CONTRACT.md.)
      const sharedTransform = rigid ? { position: [0, 0, 0], rotationDeg: [0, 0, 0], scale: 1 } : null
      for (const oid of objectIds) {
        let id = `${baseName}-${oid}`
        let n = 1
        while (usedIds.has(id)) id = `${baseName}-${oid}-${n++}`
        usedIds.add(id)
        const trs = sharedTransform || { position: [0, 0, 0], rotationDeg: [0, 0, 0], scale: 1 }
        newRows.push({
          id,
          file_id: fileId,
          object_id: oid,
          visible: true,
          color: null,
          params: null,
          ...trs,
        })
      }
      const next = [...rs, ...newRows]
      emit(next)
      // Select the first new row.
      onSelectComponent?.(newRows[0]?.id || null)
      return next
    })
  }

  function deleteRow(idx) {
    setRows((rs) => {
      const next = rs.filter((_, i) => i !== idx)
      emit(next)
      return next
    })
    if (selectedComponentId === rows[idx]?.id) onSelectComponent?.(null)
  }

  // Acknowledge "I've seen the latest" for a tracking_latest external_ref —
  // restamps last_seen_updated_at so the amber "out of date" chip clears.
  function restampSeen(refId, newUpdatedAt) {
    if (!refId || !newUpdatedAt) return
    setRows((rs) => {
      const next = restampExternalRefSeen(rs, refId, newUpdatedAt)
      if (next === rs) return rs
      emit(next)
      return next
    })
  }

  function moveRow(from, to) {
    if (from === to || from < 0 || to < 0 || to >= rows.length) return
    setRows((rs) => {
      const next = rs.slice()
      const [m] = next.splice(from, 1)
      next.splice(to, 0, m)
      emit(next)
      return next
    })
  }

  // ---- Drag-reorder -------------------------------------------------------
  const [dragIdx, setDragIdx] = useState(null)
  const [dragOverIdx, setDragOverIdx] = useState(null)

  // ---- JSON view ----------------------------------------------------------
  function commitJson() {
    try {
      JSON.parse(jsonDraft)
    } catch (e) {
      setJsonErr(e.message || 'Invalid JSON')
      return
    }
    setJsonErr(null)
    const nextParsed = parseAssembly(jsonDraft)
    const nextRows = deriveRows(nextParsed)
    setRows(nextRows)
    const nextOv = nextParsed.overrides || []
    setOverrides(nextOv)
    overridesRef.current = nextOv
    lastEmittedRef.current = jsonDraft
    onChange?.(jsonDraft)
  }

  return (
    <div className="h-full flex flex-col bg-ink-950 text-ink-100 min-h-0">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Layers size={14} className="text-cyan-edge" />
          <span className="text-xs font-semibold uppercase tracking-wider text-ink-300">Assembly</span>
          <span className="text-[10px] text-ink-500 font-mono">{rows.length} component{rows.length === 1 ? '' : 's'}</span>
        </div>
        <button
          type="button"
          onClick={startInsert}
          className="inline-flex items-center gap-1 px-2 py-1 rounded bg-kerf-300 text-ink-950 text-[11px] font-medium hover:bg-kerf-200"
          title="Add component"
        >
          <Plus size={11} />
          Add component
        </button>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-auto min-h-0">
        {rows.length === 0 ? (
          <div className="h-full flex items-center justify-center text-xs text-ink-500 px-6 text-center">
            <div>
              <div className="mb-2">Add a component to begin.</div>
              <button
                type="button"
                onClick={startInsert}
                className="text-kerf-300 hover:underline"
              >
                Add your first component
              </button>
            </div>
          </div>
        ) : (
          <ul className="px-2 py-2 space-y-1.5">
            {rows.map((row, idx) => (
              <ComponentRow
                key={`${row.id}-${idx}`}
                row={row}
                files={eligibleFiles}
                allFiles={files}
                projectId={projectId}
                selected={selectedComponentId === row.id}
                onSelect={() => onSelectComponent?.(row.id)}
                onChangeFileId={(fid) => changeFileId(idx, fid)}
                onChangeObjectId={(oid) => changeObjectId(idx, oid)}
                onRename={(name) => rename(idx, name)}
                onPatch={(p) => updateRow(idx, p)}
                onDelete={() => deleteRow(idx)}
                onRestampSeen={(updatedAt) => restampSeen(row.id, updatedAt)}
                onDragStart={() => setDragIdx(idx)}
                onDragEnd={() => { setDragIdx(null); setDragOverIdx(null) }}
                onDragOver={(e) => { e.preventDefault(); setDragOverIdx(idx) }}
                onDrop={() => {
                  if (dragIdx != null) moveRow(dragIdx, idx)
                  setDragIdx(null); setDragOverIdx(null)
                }}
                isDragOver={dragOverIdx === idx && dragIdx !== idx}
              />
            ))}
          </ul>
        )}
      </div>

      {/* Mates panel — collapsible region for 3D assembly mates (SolveSpace solver). */}
      <MatesPanel
        mates={mates}
        components={rows}
        onChangeMates={onChangeMates}
        onToast={onToast}
      />

      {/* Inline BOM panel — collapsible region. Lazy-loads on first expand
          and refetches whenever this assembly is saved (so the rolled-up
          counts reflect the just-persisted overrides). Edits flow back into
          the assembly file's `overrides` array via onChangeOverrides. */}
      <InlineBOMPanel
        projectId={projectId}
        assemblyFileId={currentFileId}
        overrides={overrides}
        onChangeOverrides={onChangeOverrides}
      />

      {/* JSON view */}
      <div className="border-t border-ink-800 flex-shrink-0 max-h-[40%] flex flex-col min-h-0">
        <button
          type="button"
          onClick={() => setShowJson((v) => !v)}
          className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] text-ink-400 hover:text-kerf-300"
        >
          {showJson ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          JSON
        </button>
        {showJson && (
          <div className="flex-1 min-h-0 flex flex-col px-3 pb-3">
            <textarea
              value={jsonDraft}
              onChange={(e) => { setJsonDraft(e.target.value); setJsonErr(null) }}
              onBlur={commitJson}
              spellCheck={false}
              className="flex-1 min-h-0 bg-ink-900 border border-ink-800 rounded p-2 font-mono text-[11px] text-ink-100 outline-none focus:border-kerf-300/60 resize-none"
            />
            {jsonErr && <div className="text-[10px] text-red-400 mt-1">{jsonErr}</div>}
          </div>
        )}
      </div>

      {/* Library picker — first step of the Add component flow. Once
          the user picks a Part, the (existing) InsertObjectsModal opens
          for Object selection if the Part has multiple Objects. */}
      {pickerOpen && (
        <LibraryPicker
          currentProjectId={projectId}
          onSelect={onPickPart}
          onClose={() => setPickerOpen(false)}
        />
      )}

      {/* Insert dialog. The `key` ties the modal's local checkbox state to
          the source file + the resolved object list — when the user picks a
          different Part, the modal remounts so the default-all-checked
          initialization happens cleanly without a setState-in-effect. */}
      {insertModal && (
        <InsertObjectsModal
          key={`${insertModal.fileId}::${insertModal.loading ? 'L' : insertModal.objectIds.join(',')}`}
          modal={insertModal}
          eligibleFiles={eligibleFiles}
          allFiles={files}
          onPickFile={(fid) => reloadInsertObjects(fid)}
          onCancel={() => setInsertModal(null)}
          onConfirm={(objectIds, rigid) => {
            addComponentRows(insertModal.fileId, objectIds, { rigid })
            setInsertModal(null)
          }}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Insert Objects modal — picks a source Part and which Objects to instance.

function InsertObjectsModal({ modal, eligibleFiles, allFiles, onPickFile, onCancel, onConfirm }) {
  const { fileId, loading, objectIds } = modal
  // Default-all-checked is computed once from the props at mount time. The
  // parent remounts us (via `key`) when fileId / objectIds change, so we don't
  // need a setState-in-effect to keep `checked` aligned.
  const [checked, setChecked] = useState(() => new Set(objectIds))
  const [rigid, setRigid] = useState(false)

  // Esc to close.
  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onCancel() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel])

  function toggle(id) {
    setChecked((s) => {
      const next = new Set(s)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }
  function selectAll() { setChecked(new Set(objectIds)) }
  function selectNone() { setChecked(new Set()) }

  const sourceFile = (allFiles || []).find((f) => f.id === fileId)
  const sourceLabel = sourceFile?.name || '(file)'

  const orderedSelection = objectIds.filter((id) => checked.has(id))

  return (
    <div
      className="fixed inset-0 z-50 bg-ink-950/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-md bg-ink-900 border border-ink-700 rounded-xl shadow-2xl flex flex-col max-h-[80vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-ink-800">
          <h2 className="text-base font-semibold text-ink-100">Insert Objects</h2>
          <button
            type="button"
            onClick={onCancel}
            className="p-1 rounded hover:bg-ink-800 text-ink-300 hover:text-ink-100"
            title="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-4 pt-3 pb-2 flex flex-col gap-2 border-b border-ink-800">
          <label className="flex items-center gap-2 text-xs text-ink-300">
            <span className="text-[10px] uppercase tracking-wider text-ink-500 w-12 flex-shrink-0">Part</span>
            <select
              value={fileId}
              onChange={(e) => onPickFile(e.target.value)}
              className="flex-1 bg-ink-850 border border-ink-700 rounded px-2 py-1.5 text-[12px] font-mono text-ink-100 outline-none focus:border-kerf-300/60"
            >
              {eligibleFiles.map((f) => (
                <option key={f.id} value={f.id}>{filePath(f, allFiles)}</option>
              ))}
            </select>
          </label>
          <div className="text-[10px] text-ink-500 pl-14">
            {loading
              ? 'Loading Objects…'
              : `${objectIds.length} Object${objectIds.length === 1 ? '' : 's'} in ${sourceLabel}`}
          </div>
        </div>

        <div className="px-4 py-2 flex-1 overflow-auto min-h-0">
          {loading ? (
            <div className="flex items-center gap-2 py-6 justify-center text-xs text-ink-400">
              <Loader2 size={14} className="animate-spin" />
              Loading…
            </div>
          ) : objectIds.length === 0 ? (
            <div className="py-6 text-center text-xs text-ink-500">No Objects in this Part.</div>
          ) : (
            <>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] uppercase tracking-wider text-ink-500">Objects</span>
                <div className="flex items-center gap-2 text-[10px]">
                  <button type="button" onClick={selectAll} className="text-ink-400 hover:text-kerf-300">all</button>
                  <span className="text-ink-700">·</span>
                  <button type="button" onClick={selectNone} className="text-ink-400 hover:text-kerf-300">none</button>
                </div>
              </div>
              <ul className="space-y-0.5">
                {objectIds.map((oid) => (
                  <li key={oid}>
                    <label className="flex items-center gap-2 px-2 py-1 rounded hover:bg-ink-850 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={checked.has(oid)}
                        onChange={() => toggle(oid)}
                        className="accent-kerf-300"
                      />
                      <span className="text-xs font-mono text-ink-100">{oid}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>

        <div className="px-4 py-2 border-t border-ink-800 flex flex-col gap-2">
          <label className="flex items-start gap-2 text-xs text-ink-300 cursor-pointer">
            <input
              type="checkbox"
              checked={rigid}
              onChange={(e) => setRigid(e.target.checked)}
              className="accent-kerf-300 mt-0.5"
            />
            <span>
              <span className="block">Place as rigid group</span>
              <span className="text-[10px] text-ink-500">All checked Components share one starting transform.</span>
            </span>
          </label>
        </div>

        <div className="px-4 py-3 border-t border-ink-800 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            className="px-3 py-1.5 rounded-md text-xs text-ink-300 hover:bg-ink-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => onConfirm(orderedSelection, rigid)}
            disabled={loading || orderedSelection.length === 0}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md bg-kerf-300 text-ink-950 text-xs font-medium hover:bg-kerf-200 disabled:opacity-40"
          >
            <Check size={12} />
            Insert {orderedSelection.length || ''}
          </button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// One row of the components list.

function ComponentRow({
  row, files, allFiles, projectId, selected, onSelect,
  onChangeFileId, onChangeObjectId, onRename, onPatch, onDelete, onRestampSeen,
  onDragStart, onDragEnd, onDragOver, onDrop, isDragOver,
}) {
  const [editingName, setEditingName] = useState(false)
  const [showColor, setShowColor] = useState(false)
  // Resolve display name for the source dropdown's current value (might be a
  // file outside `files` if the user has selected a now-cyclic file via JSON).
  const sourceFile = (allFiles || []).find((f) => f.id === row.file_id)
  const sourceLabel = sourceFile?.name || '(missing file)'

  // Lazy-loaded list of object ids from the source file. We key the loaded
  // ids by file_id so a source-file change naturally invalidates them
  // without needing a setState-in-effect (which lints as a cascading render
  // anti-pattern).
  const [objectIdsState, setObjectIdsState] = useState({ fileId: null, ids: null })
  const [loadingIds, setLoadingIds] = useState(false)
  const objectIds = objectIdsState.fileId === row.file_id ? objectIdsState.ids : null
  const ensureObjectIds = useCallback(() => {
    if (objectIds || loadingIds || !projectId || !row.file_id) return
    const fid = row.file_id
    setLoadingIds(true)
    getObjectIds(projectId, fid)
      .then((ids) => setObjectIdsState({ fileId: fid, ids }))
      .finally(() => setLoadingIds(false))
  }, [objectIds, loadingIds, projectId, row.file_id])

  const isWildcard = row.object_id === LEGACY_WILDCARD

  return (
    <li
      onClick={onSelect}
      onDragOver={onDragOver}
      onDrop={onDrop}
      className={`group rounded-md border ${
        selected
          ? 'border-kerf-300/70 bg-kerf-300/10'
          : 'border-ink-800 bg-ink-900 hover:border-ink-700'
      } ${isDragOver ? 'ring-1 ring-kerf-300/60' : ''} transition-colors`}
    >
      {/* Row header */}
      <div className="flex items-center gap-2 px-2 py-1.5">
        <span
          draggable
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
          className="cursor-grab active:cursor-grabbing text-ink-500 hover:text-ink-300"
          title="Drag to reorder"
          onClick={(e) => e.stopPropagation()}
        >
          <GripVertical size={12} />
        </span>
        {editingName ? (
          <input
            autoFocus
            defaultValue={row.id}
            onClick={(e) => e.stopPropagation()}
            onBlur={(e) => { setEditingName(false); onRename(e.target.value) }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); setEditingName(false); onRename(e.target.value) }
              else if (e.key === 'Escape') setEditingName(false)
            }}
            className="bg-ink-950 border border-kerf-300/40 rounded px-1.5 py-0.5 text-[11px] font-mono text-ink-100 outline-none flex-shrink min-w-0"
          />
        ) : (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); setEditingName(true) }}
            className="text-[11px] font-mono text-ink-100 hover:text-kerf-300 truncate"
            title={row.object_id && !isWildcard
              ? `${sourceLabel} / ${row.object_id}`
              : sourceLabel}
          >
            {row.id}
            {row.object_id && !isWildcard && (
              <span className="text-ink-500"> · {row.object_id}</span>
            )}
            {isWildcard && (
              <span className="text-amber-400/80"> · legacy *</span>
            )}
          </button>
        )}
        {row.external_ref && (
          <ExternalRefChips
            externalRef={row.external_ref}
            onRecordSeen={onRestampSeen}
          />
        )}
        <span className="flex-1" />
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onPatch({ visible: !row.visible }) }}
          className={`p-1 rounded hover:bg-ink-800 ${row.visible ? 'text-ink-300' : 'text-ink-500'}`}
          title={row.visible ? 'Hide' : 'Show'}
        >
          {row.visible ? <Eye size={11} /> : <EyeOff size={11} />}
        </button>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); setShowColor((v) => !v) }}
          className="w-5 h-5 rounded border border-ink-700 hover:border-kerf-300 flex-shrink-0"
          style={{ backgroundColor: row.color
            ? `rgb(${Math.round(row.color[0] * 255)},${Math.round(row.color[1] * 255)},${Math.round(row.color[2] * 255)})`
            : 'transparent' }}
          title="Color override"
        />
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onDelete() }}
          className="p-1 rounded hover:bg-red-900/30 text-ink-500 hover:text-red-300"
          title="Delete component"
        >
          <Trash2 size={11} />
        </button>
      </div>

      {/* Source dropdown */}
      <div className="px-2 pb-1.5 flex items-center gap-2">
        <span className="text-[10px] text-ink-500 uppercase tracking-wider w-12 flex-shrink-0">Part</span>
        <select
          value={row.file_id}
          onClick={(e) => e.stopPropagation()}
          onChange={(e) => onChangeFileId(e.target.value)}
          className="flex-1 min-w-0 bg-ink-950 border border-ink-800 rounded px-2 py-1 text-[11px] font-mono text-ink-100 outline-none focus:border-kerf-300/60"
        >
          {/* Always include the current selection so the user sees it even
              if it'd now be excluded by the cycle check. */}
          {!files.some((f) => f.id === row.file_id) && (
            <option value={row.file_id}>{sourceLabel}</option>
          )}
          {files.map((f) => (
            <option key={f.id} value={f.id}>{filePath(f, allFiles)}</option>
          ))}
        </select>
      </div>

      {/* Object dropdown — picks a single Object id from the source's exported
          array. Loads the source's object-id list on first open. */}
      <div className="px-2 pb-1.5 flex items-center gap-2">
        <span className="text-[10px] text-ink-500 uppercase tracking-wider w-12 flex-shrink-0">Obj</span>
        <div className="flex-1 min-w-0 relative">
          <select
            value={row.object_id || ''}
            onClick={(e) => { e.stopPropagation(); ensureObjectIds() }}
            onFocus={ensureObjectIds}
            onMouseDown={ensureObjectIds}
            onChange={(e) => onChangeObjectId(e.target.value)}
            className="w-full bg-ink-950 border border-ink-800 rounded px-2 py-1 text-[11px] font-mono text-ink-100 outline-none focus:border-kerf-300/60"
          >
            {/* Always show the currently-selected object_id even if we haven't
                loaded the list yet, or it's no longer in the source. The
                wildcard option is only present when the row is still legacy
                — it lets users click through to migrate manually too. */}
            {isWildcard && (
              <option value={LEGACY_WILDCARD}>{LEGACY_WILDCARD} (legacy)</option>
            )}
            {row.object_id && !isWildcard && !(objectIds || []).includes(row.object_id) && (
              <option value={row.object_id}>{row.object_id} (missing)</option>
            )}
            {(objectIds || []).map((oid) => (
              <option key={oid} value={oid}>{oid}</option>
            ))}
          </select>
          {loadingIds && (
            <Loader2 size={11} className="animate-spin absolute right-6 top-1/2 -translate-y-1/2 text-ink-400 pointer-events-none" />
          )}
        </div>
      </div>

      {/* TRS rows */}
      <div className="px-2 pb-2 space-y-1">
        <Vec3Row
          label="Pos"
          value={row.position}
          step={1}
          onChange={(v) => onPatch({ position: v })}
        />
        <Vec3Row
          label="Rot"
          value={row.rotationDeg}
          step={5}
          unit="°"
          onChange={(v) => onPatch({ rotationDeg: v })}
        />
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-ink-500 uppercase tracking-wider w-12 flex-shrink-0">Scl</span>
          <NumberInput
            value={row.scale}
            step={0.1}
            min={0.0001}
            onChange={(v) => onPatch({ scale: v })}
          />
        </div>
      </div>

      {/* Color popover */}
      {showColor && (
        <div className="px-2 pb-2" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center gap-2 p-2 rounded bg-ink-950 border border-ink-800">
            <input
              type="color"
              value={row.color
                ? rgbToHex(row.color)
                : '#c9a96b'}
              onChange={(e) => onPatch({ color: hexToRgb(e.target.value) })}
              className="w-6 h-6 rounded cursor-pointer bg-transparent border-0"
            />
            <button
              type="button"
              onClick={() => onPatch({ color: null })}
              className="text-[10px] text-ink-400 hover:text-kerf-300"
            >
              Clear override
            </button>
          </div>
        </div>
      )}
    </li>
  )
}

// ExternalRefChips — shows the cross-project source as an emerald "↗ project"
// pill, plus an amber "source advanced" warning when the live source's
// updated_at is newer than the component's last_seen_updated_at.
//
// Strategy A from ROADMAP row 68 Phase 2: live-fetch comparison. We hit
// `api.getProject(ref.project_id)` + `api.getFile(ref.project_id, ref.file_id)`
// once on mount per ref change. If the fetch fails (auth, network, deleted
// source), we render nothing — never break the row.
//
// On first sighting (no last_seen_updated_at recorded yet) we record the
// current updated_at as the baseline so the chip stays clean until the
// source actually advances. The "Update component" CTA is deferred — for v1
// the warning chip just logs to the console on click.
function ExternalRefChips({ externalRef, onRecordSeen }) {
  const [projectName, setProjectName] = useState(null)
  const [liveUpdatedAt, setLiveUpdatedAt] = useState(null)
  const [fetchFailed, setFetchFailed] = useState(false)

  const projectId = externalRef?.project_id
  const fileId = externalRef?.file_id
  const pin = externalRef?.pin
  const lastSeen = externalRef?.last_seen_updated_at || ''

  useEffect(() => {
    if (!projectId || !fileId) return undefined
    let cancelled = false
    ;(async () => {
      try {
        const [project, file] = await Promise.all([
          api.getProject(projectId).catch(() => null),
          api.getFile(projectId, fileId),
        ])
        if (cancelled) return
        if (project?.name) setProjectName(project.name)
        const ua = file?.updated_at || null
        setLiveUpdatedAt(ua)
        // First sighting: record the baseline so we don't immediately flag the
        // very first render as stale. Subsequent advances will surface.
        if (ua && !lastSeen && typeof onRecordSeen === 'function') {
          onRecordSeen(ua)
        }
      } catch (_err) {
        if (!cancelled) setFetchFailed(true)
      }
    })()
    return () => { cancelled = true }
    // We deliberately omit lastSeen/onRecordSeen to avoid refiring on the
    // baseline-write round-trip. The ref-id pair is the load key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, fileId])

  if (fetchFailed) return null
  // Only show chips for tracking_latest pins — pinned-revision refs by
  // definition can't go stale.
  const isTracking = pin === 'tracking_latest'
  const stale = isTracking && lastSeen && liveUpdatedAt && liveUpdatedAt > lastSeen

  return (
    <span className="inline-flex items-center gap-1 ml-1" onClick={(e) => e.stopPropagation()}>
      <span
        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-950/40 border border-emerald-900/60 text-emerald-300 text-[10px] font-mono"
        title={projectName ? `Cross-project source: ${projectName}` : 'Cross-project source'}
      >
        <ExternalLink size={9} />
        {projectName || '…'}
      </span>
      {stale && (
        <button
          type="button"
          onClick={() => {
            // Acknowledge: restamp last_seen_updated_at to the live value so
            // the chip clears. A future slice can layer in a richer diff view.
            if (typeof onRecordSeen === 'function' && liveUpdatedAt) {
              onRecordSeen(liveUpdatedAt)
            }
          }}
          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-amber-950/40 border border-amber-900/60 text-amber-300 text-[10px] font-mono hover:bg-amber-900/40"
          title={`Source advanced since you last viewed it (${lastSeen} → ${liveUpdatedAt}). Click to acknowledge.`}
        >
          <AlertTriangle size={9} />
          out of date
        </button>
      )}
    </span>
  )
}

function Vec3Row({ label, value, step = 1, unit = '', onChange }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-[10px] text-ink-500 uppercase tracking-wider w-12 flex-shrink-0">{label}</span>
      <div className="flex-1 grid grid-cols-3 gap-1 min-w-0">
        {['x', 'y', 'z'].map((axis, i) => (
          <NumberInput
            key={axis}
            value={value[i]}
            step={step}
            unit={unit}
            label={axis.toUpperCase()}
            onChange={(v) => {
              const next = value.slice()
              next[i] = v
              onChange(next)
            }}
          />
        ))}
      </div>
    </div>
  )
}

function NumberInput({ value, step = 1, min, max, unit = '', label, onChange }) {
  // Local string state so users can type minus signs / partial decimals
  // without us reformatting underneath them. We commit to a number on blur or
  // when the parsed value differs from the prop.
  const [draft, setDraft] = useState(formatNum(value))
  const lastValRef = useRef(value)
  useEffect(() => {
    if (lastValRef.current !== value) {
      setDraft(formatNum(value))
      lastValRef.current = value
    }
  }, [value])

  function commit(text) {
    const n = Number(text)
    if (!Number.isFinite(n)) {
      setDraft(formatNum(value))
      return
    }
    let clamped = n
    if (min != null && clamped < min) clamped = min
    if (max != null && clamped > max) clamped = max
    if (clamped !== value) onChange(clamped)
    setDraft(formatNum(clamped))
    lastValRef.current = clamped
  }

  return (
    <div className="relative flex items-center">
      {label && (
        <span className="absolute left-1.5 text-[9px] text-ink-500 pointer-events-none">{label}</span>
      )}
      <input
        type="text"
        inputMode="decimal"
        value={draft}
        onClick={(e) => e.stopPropagation()}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={(e) => commit(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.target.blur() }
          else if (e.key === 'ArrowUp') { e.preventDefault(); commit(String((Number(draft) || 0) + step)) }
          else if (e.key === 'ArrowDown') { e.preventDefault(); commit(String((Number(draft) || 0) - step)) }
        }}
        className={`w-full bg-ink-950 border border-ink-800 rounded ${label ? 'pl-5' : 'pl-1.5'} pr-1.5 py-1 text-[11px] font-mono text-ink-100 outline-none focus:border-kerf-300/60`}
      />
      {unit && (
        <span className="absolute right-1.5 text-[9px] text-ink-500 pointer-events-none">{unit}</span>
      )}
    </div>
  )
}

function formatNum(n) {
  if (!Number.isFinite(n)) return '0'
  // Trim to 4 decimals, then strip trailing zeros.
  return String(Math.round(n * 10000) / 10000)
}

function rgbToHex([r, g, b]) {
  const c = (n) => Math.round(n * 255).toString(16).padStart(2, '0')
  return `#${c(r)}${c(g)}${c(b)}`
}
function hexToRgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex)
  if (!m) return [1, 1, 1]
  const v = parseInt(m[1], 16)
  return [((v >> 16) & 0xff) / 255, ((v >> 8) & 0xff) / 255, (v & 0xff) / 255]
}

// Build "/path/to/file.jscad" for display.
function filePath(file, all) {
  if (!file) return ''
  const byId = new Map((all || []).map((f) => [f.id, f]))
  const parts = []
  let cur = file
  for (let i = 0; i < 64 && cur; i++) {
    parts.unshift(cur.name)
    cur = cur.parent_id ? byId.get(cur.parent_id) : null
  }
  return '/' + parts.join('/')
}
