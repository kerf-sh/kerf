/**
 * WiringView — renders a .wiring file (WireViz YAML) as an SVG diagram.
 *
 * Props:
 *   source     {string}  WireViz YAML source from the .wiring file content
 *   projectId  {string}  Project ID for the API call
 *   fileId     {string}  File ID for the API call
 *   className  {string}  Extra CSS classes for the container div
 *
 * Calls `POST /api/projects/{pid}/files/{fid}/wiring/run` (kerf-api thin
 * handler that forwards to the pyworker `POST /run-wireviz` route).
 *
 * The SVG is rendered inline via dangerouslySetInnerHTML so that the diagram
 * fills the available space naturally.  The source from the file is trusted
 * because it was authored by the project owner; the SVG is never user-supplied
 * from outside the project.
 */
import { useEffect, useImperativeHandle, useRef, useState } from 'react'
import { api } from '../lib/api.js'
import { snapshotSvg } from '../lib/snapshotHelpers.js'

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function WiringView({ source, projectId, fileId, className = '', viewRef }) {
  const [svg, setSvg] = useState(null)
  const [warnings, setWarnings] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const svgContainerRef = useRef(null)

  // Thumbnail capture: the SVG is injected via dangerouslySetInnerHTML
  // so we reach into the container and grab the first <svg> child.
  useImperativeHandle(viewRef, () => ({
    snapshot: (opts) => {
      const el = svgContainerRef.current?.querySelector?.('svg')
      return snapshotSvg(el, opts)
    },
  }), [])

  useEffect(() => {
    if (!source || !source.trim()) {
      setSvg(null)
      setWarnings(['No wiring source — add YAML content to the .wiring file.'])
      return
    }
    if (!projectId || !fileId) {
      setError('projectId and fileId are required to run the WireViz renderer.')
      return
    }

    let cancelled = false
    setLoading(true)
    setError(null)
    setWarnings([])
    setSvg(null)

    api.runWireviz(projectId, fileId)
      .then((data) => {
        if (cancelled) return
        setSvg(data.svg || null)
        setWarnings(data.warnings || [])
        if (!data.svg && (data.warnings || []).length === 0) {
          setWarnings(['Renderer returned an empty SVG.'])
        }
      })
      .catch((err) => {
        if (cancelled) return
        setError(err?.message || String(err))
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  // Re-run whenever the file content (source) or ids change.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [source, projectId, fileId])

  // ── Loading ────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div
        className={`flex items-center justify-center gap-3 rounded-lg border border-ink-700 bg-ink-900/50 p-8 text-ink-400 ${className}`}
      >
        <div className="w-5 h-5 border-2 border-kerf-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
        <span className="text-sm">Compiling wiring diagram…</span>
      </div>
    )
  }

  // ── Hard error (network / auth) ────────────────────────────────────────────
  if (error) {
    return (
      <div
        className={`flex flex-col items-center justify-center gap-2 rounded-lg border border-red-900/60 bg-ink-900/50 p-6 text-red-400 ${className}`}
      >
        <p className="text-sm font-medium">Render error</p>
        <p className="text-xs font-mono opacity-70 text-center max-w-sm">{error}</p>
      </div>
    )
  }

  // ── SVG result ─────────────────────────────────────────────────────────────
  return (
    <div className={`flex flex-col gap-2 ${className}`}>
      {warnings.length > 0 && (
        <ul className="rounded border border-amber-900/50 bg-amber-950/30 px-3 py-2 space-y-0.5">
          {warnings.map((w, i) => (
            <li key={i} className="text-xs text-amber-300 font-mono leading-snug">
              {w}
            </li>
          ))}
        </ul>
      )}
      {svg ? (
        <div
          ref={svgContainerRef}
          className="w-full overflow-auto rounded-lg border border-ink-700 bg-white/5 p-2"
          // SVG originates from the WireViz renderer (trusted server-side output)
          // eslint-disable-next-line react/no-danger
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      ) : (
        !loading && (
          <div
            className={`flex flex-col items-center justify-center gap-3 rounded-lg border border-ink-700 bg-ink-900/50 p-8 text-ink-400 ${className}`}
          >
            {/* Cable/harness icon */}
            <svg className="w-10 h-10 opacity-30" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M4 6h16M4 10h16M4 14h10M4 18h6" />
            </svg>
            <p className="text-sm">No diagram yet</p>
            <p className="text-xs text-center max-w-xs opacity-60">
              Add a valid WireViz YAML harness definition to this file and save.
            </p>
          </div>
        )
      )}
    </div>
  )
}
