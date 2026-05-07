// LibraryPicker — modal version of the parts catalog. Used by
// AssemblyEditor's "Add component" affordance to drop a Library Part
// into the current assembly without leaving the editor.
//
// Two data sources, presented side-by-side:
//   1. The current project's `kind='part'` files (always visible —
//      doesn't require cloud).
//   2. The global Library catalog (cloud-only; falls back to "this
//      project only" when the cloud bundle is absent).
//
// Props:
//   - onSelect(row): called with the picked row. The row shape is the
//     normalized union of the two sources — both forms expose
//     `file_id`, `project_id`, `name`, and (when known) the catalog
//     fields. The caller is responsible for inserting the Component.
//   - onClose(): dismiss without picking.
//   - currentProjectId: scopes the "this project" list. Required.

import { useEffect, useMemo, useState } from 'react'
import { Loader2, Package, Search, Star, X } from 'lucide-react'
import { ApiError } from '../lib/api.js'
import { api } from '../lib/api.js'
import { library } from '../cloud/api.js'
import { useCloudConfig } from '../cloud/useCloudConfig.js'

const CATEGORY_OPTIONS = [
  { id: 'all', label: 'All' },
  { id: 'fastener', label: 'Fasteners' },
  { id: 'electronic', label: 'Electronics' },
  { id: 'mechanical', label: 'Mechanical' },
  { id: 'connector', label: 'Connectors' },
  { id: 'sensor', label: 'Sensors' },
  { id: 'actuator', label: 'Actuators' },
  { id: 'enclosure', label: 'Enclosures' },
]

function VerifiedBadge() {
  return (
    <span
      title="Verified publisher"
      className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-kerf-300/20 text-kerf-300 border border-kerf-300/30 flex-shrink-0"
    >
      <Star size={8} className="fill-current" />
    </span>
  )
}

// Normalize a project-local kind='part' file into the same shape the
// /api/library/parts endpoint returns. The Part metadata lives in the
// file's content blob as JSON; we parse defensively so a malformed
// content string doesn't take the picker down.
function normalizeProjectPart(file, projectId) {
  let meta = {}
  if (typeof file.content === 'string' && file.content.trim()) {
    try { meta = JSON.parse(file.content) || {} }
    catch { meta = {} }
  }
  return {
    file_id: file.id,
    project_id: projectId,
    name: meta.name || file.name?.replace(/\.[^.]+$/, '') || file.name || 'Untitled part',
    manufacturer: meta.manufacturer || '',
    mpn: meta.mpn || '',
    category: meta.category || '',
    primary_photo_url: '',
    author: { user_id: '', name: 'this project', is_verified_publisher: false },
    _local: true,
  }
}

function PartRow({ row, onSelect }) {
  const verified = !!row.author?.is_verified_publisher
  return (
    <button
      type="button"
      onClick={() => onSelect(row)}
      className="w-full text-left px-3 py-2 rounded-md border border-ink-800 bg-ink-900 hover:border-kerf-300/40 hover:bg-ink-850 transition-colors flex items-center gap-3"
    >
      <div className="w-12 h-12 rounded bg-ink-800 overflow-hidden flex-shrink-0 grid place-items-center">
        {row.primary_photo_url ? (
          // eslint-disable-next-line jsx-a11y/alt-text
          <img src={row.primary_photo_url} alt="" className="w-full h-full object-cover" />
        ) : (
          <Package size={16} className="text-ink-500" />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 min-w-0">
          <span className="text-sm font-semibold text-ink-100 truncate">
            {row.name || 'Untitled'}
          </span>
          {verified && <VerifiedBadge />}
        </div>
        {(row.manufacturer || row.mpn) && (
          <p className="text-[11px] font-mono text-ink-400 truncate">
            {[row.manufacturer, row.mpn].filter(Boolean).join(' · ')}
          </p>
        )}
        <p className="text-[10px] text-ink-500 truncate">
          {row._local ? 'In this project' : (row.author?.name || 'unknown')}
          {row.category ? ` · ${row.category}` : ''}
        </p>
      </div>
    </button>
  )
}

export default function LibraryPicker({ onSelect, onClose, currentProjectId }) {
  const { cloudEnabled } = useCloudConfig()
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [category, setCategory] = useState('all')

  const [projectFiles, setProjectFiles] = useState(null)
  const [projectErr, setProjectErr] = useState(null)
  const [globalRows, setGlobalRows] = useState(null)
  const [globalLoading, setGlobalLoading] = useState(false)
  const [globalErr, setGlobalErr] = useState(null)

  // Esc-to-close.
  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Debounce search input.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 200)
    return () => clearTimeout(t)
  }, [search])

  // Project-local parts — fire once on mount; kind=part files in the
  // current project. We deliberately call listFiles instead of taking
  // the workspace-store snapshot so this component stays usable in any
  // route, not only the active editor.
  useEffect(() => {
    if (!currentProjectId) return
    let cancelled = false
    api.listFiles(currentProjectId)
      .then((files) => {
        if (cancelled) return
        const parts = (files || []).filter((f) => f.kind === 'part' && !f.deleted_at)
        setProjectFiles(parts)
        setProjectErr(null)
      })
      .catch((err) => {
        if (cancelled) return
        setProjectFiles([])
        setProjectErr(err instanceof ApiError ? err.message : 'Could not load project parts.')
      })
    return () => { cancelled = true }
  }, [currentProjectId])

  // Global Library catalog — cloud-only. Re-fires on filter changes.
  useEffect(() => {
    if (!cloudEnabled) {
      setGlobalRows([])
      return
    }
    let cancelled = false
    setGlobalLoading(true)
    library
      .listParts({
        search: debouncedSearch || undefined,
        category: category === 'all' ? undefined : category,
      })
      .then((resp) => {
        if (cancelled) return
        setGlobalRows(resp?.rows || [])
        setGlobalErr(null)
      })
      .catch((err) => {
        if (cancelled) return
        setGlobalRows([])
        setGlobalErr(err instanceof ApiError ? err.message : 'Could not load library.')
      })
      .finally(() => { if (!cancelled) setGlobalLoading(false) })
    return () => { cancelled = true }
  }, [cloudEnabled, debouncedSearch, category])

  // Filter project-local parts client-side so the user gets the same
  // search affordance for both groups.
  const filteredProject = useMemo(() => {
    if (!projectFiles) return null
    const norm = projectFiles.map((f) => normalizeProjectPart(f, currentProjectId))
    let rows = norm
    if (debouncedSearch) {
      const q = debouncedSearch.toLowerCase()
      rows = rows.filter((r) =>
        (r.name || '').toLowerCase().includes(q) ||
        (r.manufacturer || '').toLowerCase().includes(q) ||
        (r.mpn || '').toLowerCase().includes(q),
      )
    }
    if (category !== 'all') {
      rows = rows.filter((r) => (r.category || '').toLowerCase() === category)
    }
    return rows
  }, [projectFiles, currentProjectId, debouncedSearch, category])

  // Globals minus anything we already showed in the project section to
  // avoid double-listing the user's own work.
  const filteredGlobal = useMemo(() => {
    if (!globalRows) return null
    const localIds = new Set((filteredProject || []).map((r) => r.file_id))
    return globalRows.filter((r) => !localIds.has(r.file_id))
  }, [globalRows, filteredProject])

  return (
    <div
      className="fixed inset-0 z-50 bg-ink-950/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl bg-ink-900 border border-ink-700 rounded-xl shadow-2xl flex flex-col max-h-[85vh]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-ink-800">
          <div>
            <h2 className="text-base font-semibold text-ink-100">Add component</h2>
            <p className="text-[11px] text-ink-400 mt-0.5">
              Pick a Part from this project or the Library.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-ink-800 text-ink-300 hover:text-ink-100"
            title="Close"
          >
            <X size={16} />
          </button>
        </div>

        {/* Search + filter */}
        <div className="px-4 pt-3 pb-2 border-b border-ink-800 flex flex-col gap-2">
          <div className="relative">
            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-500 pointer-events-none" />
            <input
              autoFocus
              type="search"
              placeholder="Search parts…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full h-9 bg-ink-950 border border-ink-800 rounded-md pl-9 pr-3 text-sm text-ink-100 placeholder:text-ink-500 outline-none focus:border-kerf-300/60"
            />
          </div>
          <div className="flex items-center gap-1 overflow-x-auto pb-0.5">
            {CATEGORY_OPTIONS.map((opt) => (
              <button
                key={opt.id}
                type="button"
                onClick={() => setCategory(opt.id)}
                className={
                  'h-7 px-2.5 rounded-full text-[11px] font-medium transition-colors whitespace-nowrap border ' +
                  (category === opt.id
                    ? 'bg-ink-100 text-ink-950 border-ink-100'
                    : 'text-ink-300 hover:text-ink-100 border-ink-800 hover:border-ink-700 bg-ink-900')
                }
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto min-h-0 px-4 py-3 space-y-4">
          {/* Project-local section */}
          <section>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] uppercase tracking-wider text-ink-500">
                In this project
              </span>
              {filteredProject && (
                <span className="text-[10px] text-ink-500">
                  {filteredProject.length} part{filteredProject.length === 1 ? '' : 's'}
                </span>
              )}
            </div>
            {projectErr && (
              <p className="text-[11px] text-red-300">{projectErr}</p>
            )}
            {!filteredProject && !projectErr && (
              <div className="flex items-center gap-2 py-2 text-xs text-ink-400">
                <Loader2 size={12} className="animate-spin" /> Loading…
              </div>
            )}
            {filteredProject && filteredProject.length === 0 && (
              <p className="text-[11px] text-ink-500">No Parts in this project.</p>
            )}
            {filteredProject && filteredProject.length > 0 && (
              <div className="space-y-1.5">
                {filteredProject.map((row) => (
                  <PartRow key={row.file_id} row={row} onSelect={onSelect} />
                ))}
              </div>
            )}
          </section>

          {/* Global Library section */}
          {cloudEnabled && (
            <section>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[10px] uppercase tracking-wider text-ink-500">
                  Library
                </span>
                {filteredGlobal && (
                  <span className="text-[10px] text-ink-500">
                    {filteredGlobal.length} part{filteredGlobal.length === 1 ? '' : 's'}
                  </span>
                )}
              </div>
              {globalErr && (
                <p className="text-[11px] text-red-300">{globalErr}</p>
              )}
              {globalLoading && !filteredGlobal && (
                <div className="flex items-center gap-2 py-2 text-xs text-ink-400">
                  <Loader2 size={12} className="animate-spin" /> Loading…
                </div>
              )}
              {filteredGlobal && filteredGlobal.length === 0 && !globalLoading && (
                <p className="text-[11px] text-ink-500">No matches.</p>
              )}
              {filteredGlobal && filteredGlobal.length > 0 && (
                <div className="space-y-1.5">
                  {filteredGlobal.map((row) => (
                    <PartRow key={row.file_id} row={row} onSelect={onSelect} />
                  ))}
                </div>
              )}
            </section>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-ink-800 flex items-center justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1.5 rounded-md text-xs text-ink-300 hover:bg-ink-800"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}
