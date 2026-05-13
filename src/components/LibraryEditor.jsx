// LibraryEditor — visual editor for a Part (kind='part') file.
//
// Three-column layout, mirroring AssemblyEditor's density:
//
//   [ Metadata form ] [ 3D preview ] [ Photos / Distributors / Where used ]
//
// All edits flow through `useWorkspace.updatePart(patch)` so the existing
// revision recorder picks them up — Cmd+Z works without any extra wiring.
//
// 3D preview: if the Part has a `model_storage_key`, we fetch the binary
// from the auth-protected `/api/blobs/<key>` route and parse it via the
// existing STEP loader (`lib/stepLoader.js`). The preview reuses our
// `Renderer` component.
//
// Photos panel: a square-thumbnail gallery with primary/remove kebab menus.
// Thumbnails are auth-fetched and turned into blob URLs (the `/api/blobs/`
// route requires a bearer token). Upload calls
// `api.uploadPartPhoto(projectId, fileId, blob)`; the backend resizes
// and pushes a new entry into the Part's photos[].
//
// Distributors panel: rows of {name, sku?, url, price_usd?} editable in
// place. Validation: name + url required (the workspace auto-saves so the
// user sees their work persist; validation errors render inline but don't
// block the save).
//
// Where used: walks `useWorkspace.files` for kind='assembly', parses each
// assembly's content, and lists those that reference the current Part's
// file id.

import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Package, Camera, ExternalLink, Star, Trash2, Plus, Upload,
  AlertTriangle, Layers, Eye, Lock, Globe, X, MoreHorizontal,
  RefreshCw, Loader2, Clock,
} from 'lucide-react'
import { useWorkspace } from '../store/workspace.js'
import { useAuth } from '../store/auth.js'
import { validatePart, PART_VISIBILITY_VALUES } from '../lib/part.js'
import { api } from '../lib/api.js'
import { loadStep } from '../lib/stepLoader.js'
import Renderer from './Renderer.jsx'

const API_URL = import.meta.env.VITE_API_URL || ''
const ACCEPTED_PHOTO_TYPES = ['image/jpeg', 'image/png', 'image/webp']
const ACCEPTED_MODEL_EXT = ['.step', '.stp', '.glb']

export default function LibraryEditor() {
  const projectId = useWorkspace((s) => s.projectId)
  const currentFile = useWorkspace((s) => s.currentFile)
  const currentPart = useWorkspace((s) => s.currentPart)
  const updatePart = useWorkspace((s) => s.updatePart)
  const replacePartModel = useWorkspace((s) => s.replacePartModel)
  const files = useWorkspace((s) => s.files)
  const navigate = useNavigate()

  // Validation surface used by the metadata form. Re-runs on every change
  // because validatePart is cheap.
  const validation = useMemo(() => {
    if (!currentPart) return { ok: true }
    return validatePart(currentPart)
  }, [currentPart])

  // Material files with computed full paths for the material_path field.
  const materialFilesWithPaths = useMemo(() => {
    if (!files.length) return []
    const byId = new Map(files.map((f) => [f.id, f]))
    return files
      .filter((f) => f?.kind === 'material')
      .map((f) => {
        const parts = [f.name]
        let cur = f
        for (let i = 0; i < 64 && cur?.parent_id; i++) {
          const p = byId.get(cur.parent_id)
          if (!p) break
          parts.unshift(p.name)
          cur = p
        }
        return { ...f, materialPath: '/' + parts.join('/') }
      })
  }, [files])

  if (!currentPart || !currentFile) {
    return (
      <div className="h-full flex items-center justify-center text-xs text-ink-500">
        Loading Part…
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-ink-950 text-ink-100 min-h-0">
      <Header part={currentPart} onOpenBOM={() => navigate(`/projects/${projectId}/bom`)} />

      <div className="flex-1 grid min-h-0" style={{ gridTemplateColumns: '320px 1fr 340px' }}>
        {/* Left: metadata form */}
        <aside className="border-r border-ink-800 overflow-y-auto min-h-0">
          <MetadataForm
            part={currentPart}
            onChange={updatePart}
            errors={validation.ok ? [] : validation.errors}
            materialFiles={materialFilesWithPaths}
          />
        </aside>

        {/* Center: 3D preview / model attach */}
        <main className="min-w-0 min-h-0 relative bg-ink-950 flex flex-col">
          <ModelPreview
            part={currentPart}
            onReplaceModel={replacePartModel}
          />
        </main>

        {/* Right: photos + distributors + where-used */}
        <aside className="border-l border-ink-800 overflow-y-auto min-h-0">
          <PhotosPanel
            projectId={projectId}
            fileId={currentFile.id}
            photos={currentPart.photos || []}
            onChange={updatePart}
          />
          <DistributorsPanel
            distributors={currentPart.distributors || []}
            onChange={(next) => updatePart({ distributors: next })}
            projectId={projectId}
            fileId={currentFile.id}
            onRefreshed={(parsed) => {
              if (parsed && Array.isArray(parsed.distributors)) {
                updatePart({ distributors: parsed.distributors })
              }
            }}
          />
          <WhereUsedPanel
            files={files}
            currentFileId={currentFile.id}
            onOpen={(fileId) => navigate(`/projects/${projectId}/files/${fileId}`)}
          />
        </aside>
      </div>
    </div>
  )
}

// -- Header --------------------------------------------------------------

function Header({ part, onOpenBOM }) {
  return (
    <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800 flex-shrink-0">
      <div className="flex items-center gap-2 min-w-0">
        <Package size={14} className="text-kerf-300 flex-shrink-0" />
        <span className="text-xs font-semibold uppercase tracking-wider text-ink-300">
          Library
        </span>
        <span className="text-[11px] text-ink-500 truncate">
          {part.name || <span className="italic">unnamed</span>}
        </span>
        {part.mpn && (
          <span className="text-[10px] text-ink-500 font-mono">· {part.mpn}</span>
        )}
        <VisibilityBadge value={part.visibility || 'private'} />
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onOpenBOM}
          className="text-[11px] text-ink-400 hover:text-kerf-300 inline-flex items-center gap-1"
          title="Open Bill of Materials"
        >
          <Layers size={11} />
          BOM
        </button>
      </div>
    </div>
  )
}

function VisibilityBadge({ value }) {
  const map = {
    private:  { Icon: Lock,  label: 'Private',  cls: 'text-ink-500 border-ink-700' },
    unlisted: { Icon: Eye,   label: 'Unlisted', cls: 'text-amber-300 border-amber-500/30' },
    public:   { Icon: Globe, label: 'Public',   cls: 'text-kerf-300 border-kerf-300/40' },
  }
  const e = map[value] || map.private
  const Icon = e.Icon
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[9px] uppercase tracking-wider font-medium ${e.cls}`}>
      <Icon size={9} />
      {e.label}
    </span>
  )
}

// -- Metadata form -------------------------------------------------------

function MetadataForm({ part, onChange, errors, materialFiles = [] }) {
  return (
    <div className="px-4 py-4 space-y-4">
      <div className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">
        Metadata
      </div>

      <Field label="Name" required>
        <Input
          value={part.name || ''}
          onChange={(v) => onChange({ name: v })}
          placeholder="10kΩ resistor 0805"
        />
      </Field>

      <Field label="Description">
        <Textarea
          value={part.description || ''}
          onChange={(v) => onChange({ description: v })}
          placeholder="Surface-mount precision resistor"
          rows={2}
        />
      </Field>

      <div className="grid grid-cols-2 gap-2">
        <Field label="Category">
          <Input
            value={part.category || ''}
            onChange={(v) => onChange({ category: v })}
            placeholder="resistor"
          />
        </Field>
        <Field label="Value">
          <Input
            value={part.value || ''}
            onChange={(v) => onChange({ value: v })}
            placeholder="10kΩ"
          />
        </Field>
      </div>

      <Field label="Manufacturer">
        <Input
          value={part.manufacturer || ''}
          onChange={(v) => onChange({ manufacturer: v })}
          placeholder="Yageo"
        />
      </Field>

      <Field label="MPN">
        <Input
          value={part.mpn || ''}
          onChange={(v) => onChange({ mpn: v })}
          placeholder="RC0805FR-0710KL"
          mono
        />
      </Field>

      <Field label="Datasheet URL">
        <Input
          value={part.datasheet_url || ''}
          onChange={(v) => onChange({ datasheet_url: v })}
          placeholder="https://…"
          type="url"
        />
        {part.datasheet_url && (
          <a
            href={part.datasheet_url}
            target="_blank"
            rel="noreferrer"
            className="mt-1 inline-flex items-center gap-1 text-[10px] text-ink-400 hover:text-kerf-300"
          >
            <ExternalLink size={9} />
            Open
          </a>
        )}
      </Field>

      <Field label="Visibility">
        <select
          value={part.visibility || 'private'}
          onChange={(e) => onChange({ visibility: e.target.value })}
          className="w-full bg-ink-900 border border-ink-800 rounded px-2 py-1.5 text-xs text-ink-100 outline-none focus:border-kerf-300/60"
        >
          {PART_VISIBILITY_VALUES.map((v) => (
            <option key={v} value={v}>
              {v[0].toUpperCase() + v.slice(1)}
            </option>
          ))}
        </select>
        <p className="mt-1 text-[10px] text-ink-500">
          Public Parts in published projects appear in /workshop/parts.
        </p>
      </Field>

      <Field label="Default Material">
        <select
          value={part.material_path || ''}
          onChange={(e) => onChange({ material_path: e.target.value || undefined })}
          className="w-full bg-ink-900 border border-ink-800 rounded px-2 py-1.5 text-xs text-ink-100 outline-none focus:border-kerf-300/60"
        >
          <option value="">— none —</option>
          {materialFiles.map((f) => (
            <option key={f.id} value={f.materialPath || `/${f.name}`}>
              {f.name?.replace(/\.material$/, '') || f.id}
            </option>
          ))}
        </select>
        <p className="mt-1 text-[10px] text-ink-500">
          Material used for BOM and drawing callouts.
        </p>
      </Field>

      {errors.length > 0 && (
        <div className="rounded border border-amber-500/30 bg-amber-500/5 px-2.5 py-1.5">
          <div className="flex items-start gap-1.5">
            <AlertTriangle size={11} className="text-amber-400 mt-0.5 flex-shrink-0" />
            <ul className="flex-1 min-w-0 text-[10px] text-amber-200/90 space-y-0.5">
              {errors.map((e, i) => <li key={i}>{e}</li>)}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}

function Field({ label, required, children }) {
  return (
    <label className="block">
      <div className="text-[10px] uppercase tracking-wider text-ink-500 font-medium mb-1">
        {label}{required && <span className="text-amber-400 ml-0.5">*</span>}
      </div>
      {children}
    </label>
  )
}

function Input({ value, onChange, placeholder, type = 'text', mono = false }) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={`w-full bg-ink-900 border border-ink-800 rounded px-2 py-1.5 text-xs text-ink-100 outline-none focus:border-kerf-300/60 placeholder:text-ink-600 ${mono ? 'font-mono' : ''}`}
    />
  )
}

function Textarea({ value, onChange, placeholder, rows = 2 }) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      className="w-full bg-ink-900 border border-ink-800 rounded px-2 py-1.5 text-xs text-ink-100 outline-none focus:border-kerf-300/60 placeholder:text-ink-600 resize-none"
    />
  )
}

// -- 3D preview ----------------------------------------------------------

function ModelPreview({ part, onReplaceModel }) {
  const [parts, setParts] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const fileInputRef = useRef(null)

  // Fetch + parse on storage_key change. We re-derive on the cached binary
  // when present (the underlying loadStep memoizes on SHA-256 of the bytes).
  useEffect(() => {
    const key = part?.model_storage_key
    if (!key) {
      setParts([])
      setError(null)
      setLoading(false)
      return undefined
    }
    let cancelled = false
    setLoading(true)
    setError(null)
    ;(async () => {
      try {
        const token = useAuth.getState().accessToken
        const headers = {}
        if (token) headers.authorization = `Bearer ${token}`
        const res = await fetch(`${API_URL}/api/blobs/${encodeURI(key)}`, { headers })
        if (!res.ok) throw new Error(`fetch ${res.status}`)
        const buf = await res.arrayBuffer()
        const out = await loadStep(buf)
        if (cancelled) return
        setParts(out.parts || [])
      } catch (err) {
        if (cancelled) return
        setError(err?.message || String(err))
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [part?.model_storage_key])

  const onPickModel = (browserFile) => {
    if (!browserFile) return
    const lower = (browserFile.name || '').toLowerCase()
    if (!ACCEPTED_MODEL_EXT.some((e) => lower.endsWith(e))) {
      setError('Choose a .step, .stp, or .glb file')
      return
    }
    onReplaceModel(browserFile)
  }

  if (!part?.model_storage_key) {
    return (
      <div className="flex-1 min-h-0 flex items-center justify-center px-6 text-center">
        <div>
          <div className="w-16 h-16 mx-auto rounded-full bg-ink-900 border border-ink-800 flex items-center justify-center mb-3">
            <Upload size={20} className="text-ink-600" />
          </div>
          <div className="text-sm text-ink-300 mb-1">No 3D model attached</div>
          <div className="text-[11px] text-ink-500 max-w-xs mb-3">
            Drop a STEP / GLB to give this Part a 3D representation. Assemblies will render the model when this Part is referenced.
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept=".step,.stp,.glb,model/step,model/gltf-binary"
            className="hidden"
            onChange={(e) => onPickModel(e.target.files?.[0])}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-kerf-300 text-ink-950 text-xs font-medium hover:bg-kerf-200"
          >
            <Upload size={12} />
            Attach model
          </button>
          {error && (
            <div className="mt-3 text-[11px] text-amber-300">{error}</div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 min-h-0 relative">
      {loading ? (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-ink-500">
          Loading model…
        </div>
      ) : error ? (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-amber-300 px-6 text-center">
          {error}
        </div>
      ) : (
        <Renderer
          parts={parts}
          selectedId={null}
          hiddenIds={new Set()}
          onPick={() => {}}
          className="w-full h-full"
        />
      )}
      <div className="absolute top-2 right-2">
        <input
          ref={fileInputRef}
          type="file"
          accept=".step,.stp,.glb,model/step,model/gltf-binary"
          className="hidden"
          onChange={(e) => onPickModel(e.target.files?.[0])}
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-ink-900/90 backdrop-blur border border-ink-800 text-[10px] text-ink-300 hover:text-kerf-300 hover:border-kerf-300/40"
        >
          <Upload size={10} />
          Replace
        </button>
      </div>
    </div>
  )
}

// -- Photos panel --------------------------------------------------------

function PhotosPanel({ projectId, fileId, photos, onChange }) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [enlarged, setEnlarged] = useState(null) // {storage_key, mime_type, ...}
  const fileInputRef = useRef(null)

  // Re-fetch the Part doc after a server-side mutation so the photos array
  // reflects the canonical server shape (the backend may promote a new
  // photo to primary, etc.).
  const reloadPart = async () => {
    try {
      const fresh = await api.getFile(projectId, fileId)
      const parsed = JSON.parse(fresh.content || '{}')
      onChange({ photos: Array.isArray(parsed.photos) ? parsed.photos : [] })
    } catch { /* tolerate */ }
  }

  const handlePick = async (browserFile) => {
    setError(null)
    if (!browserFile) return
    if (!ACCEPTED_PHOTO_TYPES.includes(browserFile.type)) {
      setError('JPEG / PNG / WebP only')
      return
    }
    if (browserFile.size > 5 * 1024 * 1024) {
      setError('Photo must be < 5 MB')
      return
    }
    setBusy(true)
    try {
      await api.uploadPartPhoto(projectId, fileId, browserFile)
      await reloadPart()
    } catch (err) {
      setError(err?.message || 'Upload failed')
    } finally {
      setBusy(false)
    }
  }

  const handleSetPrimary = async (storageKey) => {
    setBusy(true)
    setError(null)
    try {
      await api.setPrimaryPartPhoto(projectId, fileId, storageKey)
      await reloadPart()
    } catch (err) {
      setError(err?.message || 'Failed to set primary')
    } finally {
      setBusy(false)
    }
  }

  const handleRemove = async (storageKey) => {
    if (!confirm('Remove this photo?')) return
    setBusy(true)
    setError(null)
    try {
      await api.deletePartPhoto(projectId, fileId, storageKey)
      await reloadPart()
    } catch (err) {
      setError(err?.message || 'Failed to remove')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="px-4 py-4 border-b border-ink-800">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1.5">
          <Camera size={11} className="text-kerf-300" />
          <span className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">
            Photos
          </span>
          <span className="text-[10px] text-ink-600">{photos.length}</span>
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_PHOTO_TYPES.join(',')}
          className="hidden"
          onChange={(e) => handlePick(e.target.files?.[0])}
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={busy}
          className="inline-flex items-center gap-1 text-[10px] text-ink-400 hover:text-kerf-300 disabled:opacity-50"
        >
          <Plus size={10} />
          Add
        </button>
      </div>

      {photos.length === 0 ? (
        <div className="text-[11px] text-ink-600 italic">
          No photos yet — add a product shot.
        </div>
      ) : (
        <div className="grid grid-cols-3 gap-2">
          {photos.map((p) => (
            <PhotoTile
              key={p.storage_key}
              photo={p}
              onEnlarge={() => setEnlarged(p)}
              onSetPrimary={() => handleSetPrimary(p.storage_key)}
              onRemove={() => handleRemove(p.storage_key)}
              disabled={busy}
            />
          ))}
        </div>
      )}

      {error && (
        <div className="mt-2 text-[10px] text-amber-300">{error}</div>
      )}

      {enlarged && (
        <PhotoLightbox photo={enlarged} onClose={() => setEnlarged(null)} />
      )}
    </div>
  )
}

function PhotoTile({ photo, onEnlarge, onSetPrimary, onRemove, disabled }) {
  const [src, setSrc] = useState(null)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    if (!photo?.storage_key) return undefined
    let cancelled = false
    let url = null
    ;(async () => {
      try {
        const token = useAuth.getState().accessToken
        const headers = {}
        if (token) headers.authorization = `Bearer ${token}`
        const res = await fetch(`${API_URL}/api/blobs/${encodeURI(photo.storage_key)}`, { headers })
        if (!res.ok) return
        const blob = await res.blob()
        if (cancelled) return
        url = URL.createObjectURL(blob)
        setSrc(url)
      } catch { /* tolerate */ }
    })()
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [photo?.storage_key])

  return (
    <div className="relative group aspect-square rounded overflow-hidden bg-ink-850 border border-ink-800">
      {src ? (
        <button
          type="button"
          onClick={onEnlarge}
          className="block w-full h-full"
        >
          <img
            src={src}
            alt={photo.caption || ''}
            className="w-full h-full object-cover"
          />
        </button>
      ) : (
        <div className="w-full h-full animate-pulse" />
      )}
      {photo.primary && (
        <div className="absolute top-1 left-1 inline-flex items-center gap-0.5 px-1 py-0.5 rounded bg-kerf-300/90 text-ink-950">
          <Star size={8} fill="currentColor" />
        </div>
      )}
      <button
        type="button"
        onClick={() => setMenuOpen((v) => !v)}
        disabled={disabled}
        className="absolute top-1 right-1 p-0.5 rounded bg-ink-950/70 backdrop-blur text-ink-200 hover:text-kerf-300 opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-50"
        aria-label="Photo actions"
      >
        <MoreHorizontal size={11} />
      </button>
      {menuOpen && (
        <div
          className="absolute top-6 right-1 z-10 rounded-md bg-ink-900 border border-ink-700 shadow-xl py-1 min-w-[120px]"
          onMouseLeave={() => setMenuOpen(false)}
        >
          {!photo.primary && (
            <button
              type="button"
              onClick={() => { setMenuOpen(false); onSetPrimary() }}
              className="w-full text-left px-2.5 py-1 text-[11px] text-ink-200 hover:bg-ink-800 hover:text-kerf-300 inline-flex items-center gap-1.5"
            >
              <Star size={10} />
              Set primary
            </button>
          )}
          <button
            type="button"
            onClick={() => { setMenuOpen(false); onRemove() }}
            className="w-full text-left px-2.5 py-1 text-[11px] text-ink-200 hover:bg-ink-800 hover:text-red-300 inline-flex items-center gap-1.5"
          >
            <Trash2 size={10} />
            Remove
          </button>
        </div>
      )}
    </div>
  )
}

function PhotoLightbox({ photo, onClose }) {
  const [src, setSrc] = useState(null)
  useEffect(() => {
    if (!photo?.storage_key) return undefined
    let cancelled = false
    let url = null
    ;(async () => {
      try {
        const token = useAuth.getState().accessToken
        const headers = {}
        if (token) headers.authorization = `Bearer ${token}`
        const res = await fetch(`${API_URL}/api/blobs/${encodeURI(photo.storage_key)}`, { headers })
        if (!res.ok) return
        const blob = await res.blob()
        if (cancelled) return
        url = URL.createObjectURL(blob)
        setSrc(url)
      } catch { /* tolerate */ }
    })()
    return () => {
      cancelled = true
      if (url) URL.revokeObjectURL(url)
    }
  }, [photo?.storage_key])

  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-ink-950/80 backdrop-blur-sm p-8"
      onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <button
        type="button"
        onClick={onClose}
        className="absolute top-4 right-4 p-1.5 rounded-md text-ink-300 hover:text-ink-100 hover:bg-ink-800/80"
        aria-label="Close"
      >
        <X size={18} />
      </button>
      {src && (
        <img
          src={src}
          alt={photo.caption || ''}
          className="max-w-full max-h-full object-contain rounded shadow-2xl"
        />
      )}
    </div>
  )
}

// -- Distributors panel --------------------------------------------------

function DistributorsPanel({ distributors, onChange, projectId, fileId, onRefreshed }) {
  const [adding, setAdding] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [refreshError, setRefreshError] = useState(null)
  const [refreshNote, setRefreshNote] = useState(null)

  const update = (idx, patch) => {
    const next = distributors.map((d, i) => i === idx ? { ...d, ...patch } : d)
    onChange(next)
  }
  const remove = (idx) => {
    onChange(distributors.filter((_, i) => i !== idx))
  }
  const add = (row) => {
    onChange([...distributors, row])
    setAdding(false)
  }

  // Manual refresh: hits POST /distributors/refresh, parses the
  // returned Part JSON, and reseeds the local distributors array via
  // onRefreshed. Errors surface in a small inline note (admin not
  // configured → 502 with a hint).
  const handleRefresh = async () => {
    if (!projectId || !fileId || refreshing) return
    setRefreshing(true)
    setRefreshError(null)
    setRefreshNote(null)
    try {
      const out = await api.refreshPartDistributors(projectId, fileId)
      let parsed = null
      try { parsed = JSON.parse(out?.content || '{}') } catch { /* ignore */ }
      if (typeof onRefreshed === 'function') onRefreshed(parsed)
      const n = Number(out?.updated || 0)
      setRefreshNote(n > 0
        ? `Refreshed ${n} distributor${n === 1 ? '' : 's'}.`
        : 'No distributor entries needed updating.')
    } catch (err) {
      // 502/503 typically means no credentials configured. Hint at
      // the admin path so the user knows where to look.
      const hint = err?.status === 502 || err?.status === 503
        ? ' — check that an admin has configured the distributor at /admin/distributors.'
        : ''
      setRefreshError((err?.message || 'Refresh failed') + hint)
    } finally {
      setRefreshing(false)
    }
  }

  return (
    <div className="px-4 py-4 border-b border-ink-800">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-1.5">
          <ExternalLink size={11} className="text-kerf-300" />
          <span className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">
            Distributors
          </span>
          <span className="text-[10px] text-ink-600">{distributors.length}</span>
        </div>
        <div className="flex items-center gap-2">
          {distributors.length > 0 && (
            <button
              type="button"
              onClick={handleRefresh}
              disabled={refreshing}
              title="Refresh prices and stock from configured distributor APIs"
              className="inline-flex items-center gap-1 text-[10px] text-ink-400 hover:text-kerf-300 disabled:opacity-50"
            >
              {refreshing ? (
                <Loader2 size={10} className="animate-spin" />
              ) : (
                <RefreshCw size={10} />
              )}
              Refresh prices
            </button>
          )}
          <button
            type="button"
            onClick={() => setAdding(true)}
            className="inline-flex items-center gap-1 text-[10px] text-ink-400 hover:text-kerf-300"
          >
            <Plus size={10} />
            Add
          </button>
        </div>
      </div>

      {refreshError && (
        <div className="mb-2 text-[10px] text-amber-300">
          {refreshError}
        </div>
      )}
      {refreshNote && !refreshError && (
        <div className="mb-2 text-[10px] text-kerf-300">
          {refreshNote}
        </div>
      )}

      {distributors.length === 0 && !adding ? (
        <div className="text-[11px] text-ink-600 italic">
          No distributors. Add a Digi-Key / Mouser / LCSC URL.
        </div>
      ) : (
        <ul className="space-y-2">
          {distributors.map((d, i) => (
            <DistributorRow
              key={`${d.name}::${d.sku || ''}::${i}`}
              row={d}
              onChange={(patch) => update(i, patch)}
              onRemove={() => remove(i)}
            />
          ))}
        </ul>
      )}

      {adding && (
        <div className="mt-2">
          <DistributorEditor
            initial={{ name: '', sku: '', url: '', price_usd: undefined }}
            onSave={add}
            onCancel={() => setAdding(false)}
          />
        </div>
      )}
    </div>
  )
}

function DistributorRow({ row, onChange, onRemove }) {
  const [expanded, setExpanded] = useState(false)
  const fetchedAtRel = formatFetchedAt(row.fetched_at)
  return (
    <li className="rounded border border-ink-800 bg-ink-900/50">
      <div className="flex items-center gap-1.5 px-2 py-1.5">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex-1 min-w-0 text-left"
        >
          <div className="flex items-center gap-1.5">
            <span className="text-[11px] text-ink-100 font-medium truncate">{row.name || 'unnamed'}</span>
            {row.sku && (
              <span className="text-[10px] text-ink-500 font-mono truncate">· {row.sku}</span>
            )}
          </div>
          <div className="flex items-center gap-1.5 mt-0.5">
            {row.url && (
              <span className="text-[10px] text-ink-500 truncate flex-1">{row.url}</span>
            )}
          </div>
          <div className="flex items-center gap-2 mt-0.5 text-[10px] text-ink-500">
            {typeof row.price_usd === 'number' && (
              <span className="tabular-nums text-kerf-300">
                ${row.price_usd < 1 ? row.price_usd.toFixed(4) : row.price_usd.toFixed(2)}
              </span>
            )}
            {typeof row.stock === 'number' && (
              <span className="font-mono">{row.stock.toLocaleString()} in stock</span>
            )}
            {fetchedAtRel && (
              <span
                className={`inline-flex items-center gap-0.5 ${
                  fetchedAtRel.stale ? 'text-amber-400' : 'text-ink-600'
                }`}
                title={`Last priced ${fetchedAtRel.absolute}`}
              >
                <Clock size={9} />
                {fetchedAtRel.relative}
              </span>
            )}
          </div>
        </button>
        {row.url && (
          <a
            href={row.url}
            target="_blank"
            rel="noreferrer"
            className="p-1 rounded text-ink-500 hover:text-kerf-300"
            title="Open"
          >
            <ExternalLink size={10} />
          </a>
        )}
        <button
          type="button"
          onClick={onRemove}
          className="p-1 rounded text-ink-500 hover:text-red-300"
          title="Remove"
        >
          <Trash2 size={10} />
        </button>
      </div>
      {expanded && (
        <div className="px-2 pb-2 space-y-1.5 border-t border-ink-800 pt-2">
          <div className="grid grid-cols-2 gap-1.5">
            <SmallInput
              label="Name"
              value={row.name || ''}
              onChange={(v) => onChange({ name: v })}
              placeholder="digikey"
            />
            <SmallInput
              label="SKU"
              value={row.sku || ''}
              onChange={(v) => onChange({ sku: v })}
              placeholder="311-…"
              mono
            />
          </div>
          <SmallInput
            label="URL"
            value={row.url || ''}
            onChange={(v) => onChange({ url: v })}
            placeholder="https://…"
          />
          <SmallInput
            label="Price (USD)"
            value={row.price_usd ?? ''}
            onChange={(v) => {
              const n = Number(v)
              onChange({ price_usd: Number.isFinite(n) && v !== '' ? n : undefined })
            }}
            placeholder="0.014"
            type="number"
          />
        </div>
      )}
    </li>
  )
}

function DistributorEditor({ initial, onSave, onCancel }) {
  const [draft, setDraft] = useState(initial)
  const valid = (draft.name || '').trim() && /^https?:\/\//i.test(draft.url || '')
  return (
    <div className="rounded border border-kerf-300/40 bg-ink-900 p-2 space-y-1.5">
      <div className="grid grid-cols-2 gap-1.5">
        <SmallInput
          label="Name"
          value={draft.name}
          onChange={(v) => setDraft((s) => ({ ...s, name: v }))}
          placeholder="digikey"
          autoFocus
        />
        <SmallInput
          label="SKU"
          value={draft.sku}
          onChange={(v) => setDraft((s) => ({ ...s, sku: v }))}
          placeholder="311-…"
          mono
        />
      </div>
      <SmallInput
        label="URL"
        value={draft.url}
        onChange={(v) => setDraft((s) => ({ ...s, url: v }))}
        placeholder="https://…"
      />
      <SmallInput
        label="Price (USD)"
        value={draft.price_usd ?? ''}
        onChange={(v) => {
          const n = Number(v)
          setDraft((s) => ({ ...s, price_usd: Number.isFinite(n) && v !== '' ? n : undefined }))
        }}
        placeholder="0.014"
        type="number"
      />
      <div className="flex items-center justify-end gap-1.5 pt-1">
        <button
          type="button"
          onClick={onCancel}
          className="px-2 py-0.5 text-[10px] text-ink-400 hover:text-ink-200"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => valid && onSave({
            name: draft.name.trim(),
            sku: (draft.sku || '').trim() || undefined,
            url: draft.url.trim(),
            price_usd: draft.price_usd,
          })}
          disabled={!valid}
          className="px-2 py-0.5 text-[10px] rounded bg-kerf-300 text-ink-950 font-medium disabled:opacity-40 disabled:cursor-not-allowed hover:bg-kerf-200"
        >
          Save
        </button>
      </div>
    </div>
  )
}

function SmallInput({ label, value, onChange, placeholder, type = 'text', mono = false, autoFocus = false }) {
  return (
    <label className="block">
      <div className="text-[9px] uppercase tracking-wider text-ink-500 mb-0.5">{label}</div>
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        autoFocus={autoFocus}
        className={`w-full bg-ink-950 border border-ink-800 rounded px-1.5 py-1 text-[11px] text-ink-100 outline-none focus:border-kerf-300/60 placeholder:text-ink-600 ${mono ? 'font-mono' : ''}`}
      />
    </label>
  )
}

// -- Where used panel ----------------------------------------------------

function WhereUsedPanel({ files, currentFileId, onOpen }) {
  // An assembly references this Part if any of its components has
  // file_id === currentFileId. We parse content lazily on render — the
  // file list usually has content cached on the row.
  const refs = useMemo(() => {
    const out = []
    for (const f of files || []) {
      if (f?.kind !== 'assembly') continue
      const components = parseAssemblyComponents(f.content)
      const matches = components.filter((c) => c.file_id === currentFileId)
      if (matches.length > 0) {
        out.push({ file: f, count: matches.length })
      }
    }
    return out
  }, [files, currentFileId])

  return (
    <div className="px-4 py-4">
      <div className="flex items-center gap-1.5 mb-3">
        <Layers size={11} className="text-kerf-300" />
        <span className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">
          Where used
        </span>
        <span className="text-[10px] text-ink-600">{refs.length}</span>
      </div>
      {refs.length === 0 ? (
        <div className="text-[11px] text-ink-600 italic">
          Not yet referenced from any assembly.
        </div>
      ) : (
        <ul className="space-y-1">
          {refs.map(({ file, count }) => (
            <li key={file.id}>
              <button
                type="button"
                onClick={() => onOpen(file.id)}
                className="w-full text-left px-2 py-1.5 rounded hover:bg-ink-900 group flex items-center justify-between gap-2"
              >
                <span className="text-[11px] text-ink-200 group-hover:text-kerf-300 truncate">
                  {file.name}
                </span>
                <span className="text-[10px] text-ink-500 font-mono flex-shrink-0">
                  ×{count}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// formatFetchedAt: returns {relative, absolute, stale} for a distributor
// fetched_at ISO string. `stale` is true when the value is > 7 days old
// — matches the BOM panel's stale-warning threshold so the two surfaces
// agree.
function formatFetchedAt(iso) {
  if (!iso) return null
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return null
  const ageMs = Date.now() - t
  const days = Math.floor(ageMs / (24 * 60 * 60 * 1000))
  const stale = days >= 7
  let relative
  if (days === 0) {
    const hr = Math.floor(ageMs / (60 * 60 * 1000))
    if (hr <= 0) relative = 'fresh'
    else relative = `${hr}h ago`
  } else if (days === 1) relative = '1 day ago'
  else relative = `${days} days ago`
  let absolute
  try { absolute = new Date(iso).toLocaleString() } catch { absolute = iso }
  return { relative, absolute, stale }
}

// parseAssemblyComponents: a small mirror of the backend helper. We don't
// import lib/assembly.js here because that module pulls in matrix math we
// don't need on this code path — the where-used count only cares about
// references, not transforms.
function parseAssemblyComponents(content) {
  if (!content || typeof content !== 'string') return []
  let parsed
  try { parsed = JSON.parse(content) } catch { return [] }
  if (!parsed || typeof parsed !== 'object') return []
  if (Array.isArray(parsed.components)) return parsed.components
  if (Array.isArray(parsed.children)) return parsed.children
  return []
}
