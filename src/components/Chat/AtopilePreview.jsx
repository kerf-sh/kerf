// TODO(parent): wire into <ChatMessage> renderer — detect ```ato code fences
// in the message body (using detectAtopile from ../../lib/detectAtopile.js)
// and replace the raw code block node with <AtopilePreview source={raw} />.
// The projectId prop comes from the nearest chat context / workspace store.

/**
 * AtopilePreview.jsx
 *
 * Chat-message renderer for inline `.ato` code snippets.
 *
 * When the LLM emits a ```ato ... ``` code fence in a chat reply,
 * AtopilePreview:
 *   1. Extracts the raw atopile source via `extractAtopileSource`.
 *   2. Calls the backend POST /atopile/compile via `compileAtopile`.
 *   3. Renders the resulting Circuit JSON using the existing
 *      `CircuitJsonPreview` component (schematic + PCB tabs, pan/zoom).
 *
 * While the compile is in flight a spinner is shown.  On error an inline
 * error banner is rendered instead of the preview.  The raw source is
 * always accessible in the collapsed code block below the preview.
 *
 * Props:
 *   source     {string}   — raw atopile source text (with or without fence)
 *   projectId  {string?}  — current project id forwarded to CircuitJsonPreview
 *                           (enables the "Open in editor" button)
 *
 * Note: compile is triggered once on mount (and whenever `source` changes).
 * The AbortController is cleaned up on unmount to avoid state-setting on an
 * unmounted component.
 */

import { useEffect, useRef, useState } from 'react'
import { AlertTriangle, Loader2, ChevronDown, ChevronRight, FileCode } from 'lucide-react'
import { extractAtopileSource } from '../../lib/detectAtopile.js'
import { compileAtopile } from '../../lib/atopileCompileBridge.js'
import CircuitJsonPreview from './CircuitJsonPreview.jsx'

// ---------------------------------------------------------------------------
// AtopilePreview
// ---------------------------------------------------------------------------

export default function AtopilePreview({ source, projectId }) {
  const [status, setStatus] = useState('idle') // 'idle' | 'compiling' | 'ok' | 'error'
  const [circuit, setCircuit] = useState(null)
  const [errors, setErrors] = useState([])
  const [warnings, setWarnings] = useState([])
  const [sourceExpanded, setSourceExpanded] = useState(false)

  const abortRef = useRef(null)

  // ── Compile on mount / source change ──────────────────────────────────

  useEffect(() => {
    const raw = extractAtopileSource(source)
    if (!raw) {
      setStatus('error')
      setErrors([{ message: 'Empty or invalid atopile source.' }])
      return
    }

    // Cancel any previous in-flight request
    if (abortRef.current) {
      abortRef.current.abort()
    }
    const controller = new AbortController()
    abortRef.current = controller

    setStatus('compiling')
    setCircuit(null)
    setErrors([])
    setWarnings([])

    compileAtopile(raw, { signal: controller.signal }).then((result) => {
      if (controller.signal.aborted) return

      if (result.ok) {
        setCircuit(result.circuit)
        setWarnings(result.warnings ?? [])
        setStatus('ok')
      } else {
        // Suppress the abort pseudo-error — component is unmounting
        const errs = result.errors ?? []
        if (errs.length === 1 && errs[0]?.message === 'aborted') return
        setErrors(errs)
        setStatus('error')
      }
    })

    return () => {
      controller.abort()
    }
  }, [source])

  // ── Render helpers ─────────────────────────────────────────────────────

  const rawSource = extractAtopileSource(source) ?? source ?? ''

  return (
    <div className="my-2 rounded-lg border border-ink-700 bg-ink-950 overflow-hidden text-sm">
      {/* Header bar */}
      <div className="flex items-center gap-2 px-3 py-2 bg-ink-900/70 border-b border-ink-800">
        <FileCode size={13} className="text-kerf-400 shrink-0" />
        <span className="text-[11px] font-medium text-kerf-300 tracking-wide">atopile preview</span>

        {status === 'compiling' && (
          <span className="flex items-center gap-1 ml-1 text-ink-400 text-[11px]">
            <Loader2 size={11} className="animate-spin" />
            compiling…
          </span>
        )}

        {warnings.length > 0 && status === 'ok' && (
          <span className="flex items-center gap-1 ml-1 text-amber-400 text-[11px]">
            <AlertTriangle size={11} />
            {warnings.length} warning{warnings.length !== 1 ? 's' : ''}
          </span>
        )}
      </div>

      {/* Circuit preview — rendered once compile succeeds */}
      {status === 'ok' && Array.isArray(circuit) && circuit.length > 0 && (
        <CircuitJsonPreview circuitJson={circuit} projectId={projectId} />
      )}

      {/* Empty circuit result from a successful compile */}
      {status === 'ok' && (!Array.isArray(circuit) || circuit.length === 0) && (
        <div className="flex items-center gap-2 px-3 py-3 text-ink-500 text-xs">
          <AlertTriangle size={13} />
          Compiled successfully but produced no circuit elements.
        </div>
      )}

      {/* Compile-in-progress placeholder */}
      {status === 'compiling' && (
        <div className="flex items-center justify-center h-24 text-ink-500 text-xs gap-2">
          <Loader2 size={14} className="animate-spin" />
          Compiling .ato source…
        </div>
      )}

      {/* Error banner */}
      {status === 'error' && errors.length > 0 && (
        <div className="flex flex-col gap-1 px-3 py-2.5 bg-red-950/40 border-b border-red-900/40">
          {errors.map((err, i) => (
            <div
              key={i}
              className="flex items-start gap-2 text-red-400 text-[11px]"
            >
              <AlertTriangle size={11} className="mt-0.5 shrink-0" />
              <span>
                {err.line != null && err.col != null
                  ? `Line ${err.line}:${err.col} — `
                  : err.line != null
                  ? `Line ${err.line} — `
                  : ''}
                {err.message}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Warning details (collapsible) */}
      {warnings.length > 0 && (
        <div className="px-3 py-1.5 bg-amber-950/20 border-b border-amber-900/20">
          {warnings.map((w, i) => (
            <p key={i} className="text-[11px] text-amber-400/80">{w}</p>
          ))}
        </div>
      )}

      {/* Raw source collapsible */}
      <div className="border-t border-ink-800">
        <button
          type="button"
          onClick={() => setSourceExpanded((v) => !v)}
          className="flex items-center gap-1.5 w-full px-3 py-1.5 text-[11px] text-ink-500 hover:text-ink-300 hover:bg-ink-900/40 transition-colors text-left"
        >
          {sourceExpanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
          {sourceExpanded ? 'Hide' : 'Show'} source
        </button>
        {sourceExpanded && (
          <pre className="px-3 pb-3 pt-0 text-[11px] text-ink-300 overflow-x-auto font-mono leading-relaxed whitespace-pre">
            {rawSource}
          </pre>
        )}
      </div>
    </div>
  )
}
