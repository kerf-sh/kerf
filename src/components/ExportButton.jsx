import { useEffect, useMemo, useRef, useState } from 'react'
import { FileDown, ChevronDown, Camera, Loader2 } from 'lucide-react'
import { useWorkspace } from '../store/workspace.js'
import { api } from '../lib/api.js'
import { exportParts, downloadBlob, FORMATS, sanitizeFilename } from '../lib/exporters.js'

// Click-outside hook (mirrors ChatPanel's).
function useClickOutside(ref, onOutside, enabled) {
  useEffect(() => {
    if (!enabled) return
    function handle(e) {
      if (ref.current && !ref.current.contains(e.target)) onOutside()
    }
    function escListener(e) { if (e.key === 'Escape') onOutside() }
    document.addEventListener('mousedown', handle)
    document.addEventListener('keydown', escListener)
    return () => {
      document.removeEventListener('mousedown', handle)
      document.removeEventListener('keydown', escListener)
    }
  }, [ref, onOutside, enabled])
}

function isStepFile(file) {
  if (!file) return false
  const n = (file.name || '').toLowerCase()
  return n.endsWith('.step') || n.endsWith('.stp')
}

// Export the visible 3D parts of the currently-open file. Pulls everything
// from the workspace store so the top bar can mount this with no props.
// Hides itself when there are no parts (e.g. drawing/folder/empty file).
export default function ExportButton({ onCaptureHero }) {
  const parts = useWorkspace((s) => s.parts)
  const hiddenIds = useWorkspace((s) => s.hiddenPartIds)
  const projectId = useWorkspace((s) => s.projectId)
  const currentFile = useWorkspace((s) => s.currentFile)
  const currentFileId = useWorkspace((s) => s.currentFileId)

  const [open, setOpen] = useState(false)
  const [error, setError] = useState(null)
  const [heroBusy, setHeroBusy] = useState(false)
  const wrapRef = useRef(null)
  useClickOutside(wrapRef, () => setOpen(false), open)

  useEffect(() => {
    if (!error) return
    const t = setTimeout(() => setError(null), 4000)
    return () => clearTimeout(t)
  }, [error])

  const stepFile = isStepFile(currentFile)
  const visibleParts = useMemo(() => {
    const hidden = hiddenIds?.get(currentFileId) || new Set()
    return (parts || []).filter((p) => !hidden.has(p.id))
  }, [parts, hiddenIds, currentFileId])
  const visibleCount = visibleParts.length

  const availableFormats = useMemo(
    () => FORMATS.filter((f) => !(stepFile && f.jscadOnly)),
    [stepFile],
  )

  // Hide entirely when nothing is renderable (drawings, folders, empty files).
  if (!parts || parts.length === 0) return null

  async function doExport(formatId) {
    setOpen(false)
    try {
      if (visibleParts.length === 0) {
        setError('No visible parts to export')
        return
      }
      const baseName = currentFile?.name || 'export'
      const { blob, filename } = await exportParts(visibleParts, formatId, { baseName })
      downloadBlob(blob, filename)
    } catch (err) {
      setError(err?.message || 'Export failed')
    }
  }

  async function doCaptureHero() {
    if (!onCaptureHero || heroBusy) return
    setOpen(false)
    setHeroBusy(true)
    try {
      const blob = await onCaptureHero()
      if (blob) {
        downloadBlob(blob, `kerf-hero-${Date.now()}.png`)
      } else {
        setError('Nothing to capture')
      }
    } catch (err) {
      setError(err?.message || 'Hero capture failed')
    } finally {
      setHeroBusy(false)
    }
  }

  async function downloadOriginalStep() {
    if (!projectId || !currentFileId) return
    try {
      const buf = await api.downloadFileURL(projectId, currentFileId)
      const blob = new Blob([buf], { type: 'application/step' })
      const filename = sanitizeFilename(currentFile?.name || 'model.step')
      downloadBlob(blob, filename)
    } catch (err) {
      setError(err?.message || 'Download failed')
    }
  }

  // STEP files collapse to a single download-original action (no re-export).
  if (stepFile) {
    return (
      <div className="relative">
        <button
          type="button"
          onClick={downloadOriginalStep}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-ink-700 bg-ink-850 text-ink-200 text-xs hover:border-ink-600 hover:text-kerf-300"
          title="Download original .step file"
        >
          <FileDown size={12} />
          Download .step
        </button>
        {error && <ErrorToast message={error} onDismiss={() => setError(null)} />}
      </div>
    )
  }

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={visibleCount === 0}
        className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md border border-ink-700 bg-ink-850 text-ink-200 text-xs hover:border-ink-600 hover:text-kerf-300 disabled:opacity-40 disabled:hover:text-ink-200 disabled:hover:border-ink-700"
        title={visibleCount === 0 ? 'Nothing visible to export' : `Export ${visibleCount} visible part${visibleCount === 1 ? '' : 's'}`}
      >
        <FileDown size={12} />
        Export
        <ChevronDown size={11} className="text-ink-400" />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1.5 z-30 w-56 rounded-lg border border-ink-700 bg-ink-900 shadow-2xl shadow-black/50 overflow-hidden">
          <div className="px-3 py-1.5 border-b border-ink-800 text-[10px] uppercase tracking-wider text-ink-500 font-semibold flex items-center justify-between">
            <span>Export visible parts</span>
            <span className="font-mono normal-case tracking-normal text-ink-400">{visibleCount}</span>
          </div>
          <div className="max-h-[60vh] overflow-auto py-1">
            {availableFormats.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => doExport(f.id)}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-[12px] text-ink-100 hover:bg-ink-800 hover:text-kerf-300"
              >
                <span className="flex-1 truncate">{f.label}</span>
                <span className="font-mono text-[10px] text-ink-500">.{f.ext}</span>
              </button>
            ))}
          </div>
          {onCaptureHero && (
            <div className="border-t border-ink-800 py-1">
              <button
                type="button"
                onClick={doCaptureHero}
                disabled={heroBusy}
                title="Render a 2048×2048 marketing shot (bloom + ACES tonemap, no UI chrome) and download a PNG"
                className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-[12px] text-ink-100 hover:bg-ink-800 hover:text-kerf-300 disabled:opacity-50 disabled:hover:bg-transparent disabled:hover:text-ink-100"
              >
                {heroBusy
                  ? <Loader2 size={12} className="animate-spin text-ink-400" />
                  : <Camera size={12} className="text-ink-400" />}
                <span className="flex-1 truncate">{heroBusy ? 'Rendering…' : 'Capture hero image'}</span>
                <span className="font-mono text-[10px] text-ink-500">.png</span>
              </button>
            </div>
          )}
        </div>
      )}

      {error && <ErrorToast message={error} onDismiss={() => setError(null)} />}
    </div>
  )
}

function ErrorToast({ message, onDismiss }) {
  return (
    <div className="absolute right-0 top-full mt-1.5 z-40 w-64 px-3 py-2 rounded-md border border-red-800/60 bg-red-950/80 text-[11px] text-red-200 shadow-xl flex items-center justify-between gap-2">
      <span className="truncate">{message}</span>
      <button
        type="button"
        onClick={onDismiss}
        className="text-red-300 hover:text-red-100 flex-shrink-0 text-[14px] leading-none"
        title="Dismiss"
      >×</button>
    </div>
  )
}
