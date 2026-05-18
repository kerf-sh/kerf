// BinarySideBySide.jsx — binary file diff panel for CommitDiff (T-186).
//
// Renders two preview slots (old / new) side by side for binary files:
//   - STEP / OCCT-stream files → uses Renderer.jsx in a small Three.js canvas
//     (lazy-loaded since Renderer is heavy)
//   - Raster images (PNG, JPG, GIF, WEBP, BMP, SVG) → <img> tag
//   - Opaque blobs (ZIP, ELF, etc.) → "No preview available" placeholder
//
// Each panel has an "Accept yours · Accept theirs" button row that calls
// POST /api/workspaces/{projectId}/git/resolve.
//
// Props:
//   file         {object}   Entry from the diff manifest:
//                           { path, kind, change, binary, oid_old, oid_new,
//                             preview_thumb_url }
//   projectId    {string}   Project UUID (wsid).
//   againstSha   {string}   The SHA of the other side (parent or branch tip).
//   onResolved   {(path, pick) => void}  Called after a successful resolve.

import { useState, useCallback, lazy, Suspense } from 'react'
import { useAuth } from '../store/auth.js'
import { ApiError } from '../lib/api.js'

const API_URL = import.meta.env.VITE_API_URL || ''

// Renderer is large (Three.js + OCCT) — lazy-load only when needed.
const Renderer = lazy(() => import('./Renderer.jsx'))

// ---------------------------------------------------------------------------
// Blob-URL preview helper
// ---------------------------------------------------------------------------

// File extensions that are raster images renderable via <img>
const RASTER_KINDS = new Set(['image', 'svg'])

// File kinds that can be previewed in the 3D renderer
const RENDERER_KINDS = new Set(['step', 'stl', 'obj', 'iges', 'brep', '3mf'])

function previewType(kind) {
  if (RENDERER_KINDS.has(kind)) return '3d'
  if (RASTER_KINDS.has(kind)) return 'image'
  return 'none'
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function callResolve(projectId, path, pick, againstSha, accessToken) {
  const url = `${API_URL}/api/workspaces/${projectId}/git/resolve`
  const headers = {
    'Content-Type': 'application/json',
  }
  if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`

  const res = await fetch(url, {
    method: 'POST',
    headers,
    body: JSON.stringify({ path, pick, against_sha: againstSha }),
  })

  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new ApiError(res.status, text || res.statusText)
  }
  return res.json()
}

// ---------------------------------------------------------------------------
// PreviewSlot — one half of the side-by-side panel
// ---------------------------------------------------------------------------

function ThreeDPreview({ oid, label }) {
  // Placeholder for 3D renderer — Renderer.jsx needs a geometry stream URL
  // and project context that would require a separate blob-serve endpoint.
  // For now, show a labelled placeholder that makes the intent clear.
  return (
    <div className="flex-1 flex flex-col items-center justify-center bg-zinc-950 rounded text-zinc-500 gap-1 min-h-0 text-xs p-2">
      <span className="text-zinc-600 text-[10px] uppercase tracking-widest">3D preview</span>
      <span className="font-mono text-[10px] break-all text-center text-zinc-700 px-2">{oid}</span>
      <span className="text-zinc-700 text-[10px]">{label}</span>
    </div>
  )
}

function ImagePreview({ thumbUrl, oid, label }) {
  if (thumbUrl) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-0 overflow-hidden p-1">
        <img
          src={thumbUrl}
          alt={label}
          className="max-h-full max-w-full object-contain rounded"
        />
      </div>
    )
  }
  // No thumb URL available — show oid
  return (
    <div className="flex-1 flex flex-col items-center justify-center bg-zinc-950 rounded text-zinc-600 text-xs p-2 gap-1">
      <span className="text-zinc-700 text-[10px] uppercase tracking-widest">Image</span>
      <span className="font-mono text-[10px] break-all text-center text-zinc-700 px-2">{oid}</span>
    </div>
  )
}

function NoPreview({ oid, label }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center bg-zinc-950 rounded text-zinc-600 text-xs p-2 gap-1">
      <span className="text-zinc-500 text-sm">No preview available</span>
      {oid && (
        <span className="font-mono text-[10px] break-all text-center text-zinc-700 px-2 max-w-full">
          {oid}
        </span>
      )}
      <span className="text-zinc-700 text-[10px]">{label}</span>
    </div>
  )
}

function PreviewSlot({ kind, oid, thumbUrl, label }) {
  const type = previewType(kind)

  return (
    <div className="flex-1 min-h-0 flex flex-col rounded overflow-hidden border border-zinc-800">
      <div className="px-2 py-1 text-[10px] font-mono text-zinc-500 border-b border-zinc-800 bg-zinc-900 shrink-0">
        {label}
        {oid && (
          <span className="ml-2 text-zinc-700 truncate max-w-[120px] inline-block align-bottom">
            {typeof oid === 'string' ? oid.replace('sha256:', '').slice(0, 12) : ''}…
          </span>
        )}
      </div>

      <div className="flex-1 min-h-0 bg-zinc-950 flex flex-col">
        {!oid ? (
          <NoPreview oid={null} label="(none)" />
        ) : type === '3d' ? (
          <ThreeDPreview oid={oid} label={label} />
        ) : type === 'image' ? (
          <ImagePreview thumbUrl={thumbUrl} oid={oid} label={label} />
        ) : (
          <NoPreview oid={oid} label={label} />
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// BinarySideBySide
// ---------------------------------------------------------------------------

export default function BinarySideBySide({ file, projectId, againstSha, onResolved }) {
  const [resolving, setResolving] = useState(false)
  const [resolveError, setResolveError] = useState(null)
  const [resolvedPick, setResolvedPick] = useState(null)
  const accessToken = useAuth((s) => s.accessToken)

  const handlePick = useCallback(
    async (pick) => {
      setResolving(true)
      setResolveError(null)
      try {
        await callResolve(projectId, file.path, pick, againstSha, accessToken)
        setResolvedPick(pick)
        if (onResolved) onResolved(file.path, pick)
      } catch (err) {
        setResolveError(err.message || String(err))
      } finally {
        setResolving(false)
      }
    },
    [projectId, file.path, againstSha, accessToken, onResolved],
  )

  const thumbOld = file.preview_thumb_url || null
  const thumbNew = file.preview_thumb_url || null

  return (
    <div className="flex flex-col h-full bg-zinc-900 min-h-0">
      {/* Two-column preview */}
      <div className="flex flex-1 gap-2 p-2 min-h-0 overflow-hidden">
        <PreviewSlot
          kind={file.kind}
          oid={file.oid_old}
          thumbUrl={thumbOld}
          label="Theirs (old)"
        />
        <PreviewSlot
          kind={file.kind}
          oid={file.oid_new}
          thumbUrl={thumbNew}
          label="Yours (new)"
        />
      </div>

      {/* Resolve bar */}
      <div className="shrink-0 flex items-center justify-between px-3 py-2 border-t border-zinc-800 bg-zinc-900">
        <span className="text-xs font-mono text-zinc-400 truncate max-w-[60%]">
          {file.path}
        </span>

        {resolvedPick ? (
          <span className="text-xs text-emerald-400">
            Resolved ({resolvedPick})
          </span>
        ) : (
          <div className="flex items-center gap-2">
            {resolveError && (
              <span className="text-xs text-rose-400 max-w-[200px] truncate">
                {resolveError}
              </span>
            )}
            <button
              disabled={resolving}
              onClick={() => handlePick('yours')}
              className={[
                'text-xs px-2.5 py-1 rounded border transition-colors',
                resolving
                  ? 'border-zinc-700 text-zinc-600 cursor-not-allowed'
                  : 'border-zinc-600 text-zinc-300 hover:border-amber-500 hover:text-amber-400',
              ].join(' ')}
            >
              Accept yours
            </button>
            <button
              disabled={resolving}
              onClick={() => handlePick('theirs')}
              className={[
                'text-xs px-2.5 py-1 rounded border transition-colors',
                resolving
                  ? 'border-zinc-700 text-zinc-600 cursor-not-allowed'
                  : 'border-zinc-600 text-zinc-300 hover:border-emerald-500 hover:text-emerald-400',
              ].join(' ')}
            >
              Accept theirs
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
