/**
 * AtopileEditor.jsx
 *
 * IDE editor for `.ato` (atopile) hardware-description files.
 *
 * Layout:
 *   ┌─────────────────────────────────────────────────────────┐
 *   │ Source │ Circuit │               ← top tabs             │
 *   ├─────────────────────────────────────────────────────────┤
 *   │                                                         │
 *   │  active view (full-bleed)                               │
 *   │                                                         │
 *   └─────────────────────────────────────────────────────────┘
 *
 * Source tab:
 *   Monaco editor with the `atopile` language (syntax highlighting for
 *   keywords, operators, number+unit literals, comments, strings).
 *   On every keystroke the source is debounce-compiled via the backend
 *   POST /atopile/compile endpoint.  The last good circuit result is
 *   retained while a new compile is in flight so the Circuit tab never
 *   shows a blank canvas.
 *
 * Circuit tab:
 *   Renders the Circuit JSON produced by the compile step using the
 *   existing SchematicView and PCBView components — zero new renderers.
 *
 * TODO (parent must wire):
 *   - Register `.ato` as a file kind in the FileTree `KIND_ORDER` constant.
 *   - Add `'atopile'` to the `FILE_KINDS` allow-list in routes.py so the
 *     create-file endpoint accepts it.
 *   - Add the MIME / extension mapping so the file-type router redirects
 *     `.ato` files to <AtopileEditor>.  (The `.ato` MIME type is not yet
 *     registered in elementTypes.js / the file-router.)
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import Editor from '@monaco-editor/react'
import { AlertTriangle, FileCode, CircuitBoard, Loader2 } from 'lucide-react'
import SchematicView from './SchematicView.jsx'
import PCBView from './PCBView.jsx'
import { useWorkspace } from '../store/workspace.js'
import { registerAtopileLanguage, LANGUAGE_ID } from '../lib/atopileMonacoLanguage.js'
import { compileAtopile } from '../lib/atopileCompileBridge.js'

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const COMPILE_DEBOUNCE_MS = 400

const MONACO_OPTIONS = {
  minimap: { enabled: false },
  fontFamily:
    'JetBrains Mono, Geist Mono, ui-monospace, SF Mono, Menlo, monospace',
  fontSize: 13,
  lineNumbers: 'on',
  scrollBeyondLastLine: false,
  smoothScrolling: true,
  cursorBlinking: 'smooth',
  renderLineHighlight: 'line',
  tabSize: 4,
  wordWrap: 'off',
  padding: { top: 12, bottom: 12 },
  automaticLayout: true,
}

const TABS = [
  { id: 'source',  label: 'Source',  Icon: FileCode },
  { id: 'circuit', label: 'Circuit', Icon: CircuitBoard },
]

// ---------------------------------------------------------------------------
// AtopileEditor component
// ---------------------------------------------------------------------------

/**
 * @param {object}  props
 * @param {string}  props.value         - Current .ato source text
 * @param {Function} props.onChange     - Called with new source on edit
 * @param {boolean} [props.readOnly]    - Prevent edits
 * @param {string}  [props.readOnlyReason] - Banner message when readOnly
 */
export default function AtopileEditor({
  value,
  onChange,
  readOnly = false,
  readOnlyReason = null,
}) {
  const [activeTab, setActiveTab] = useState('source')
  const [compiling, setCompiling] = useState(false)
  const [circuit, setCircuit] = useState(null)       // last successful Circuit JSON
  const [compileErrors, setCompileErrors] = useState([])
  const [compileWarnings, setCompileWarnings] = useState([])

  const debounceTimer = useRef(null)
  const abortRef = useRef(null)

  // ── Compile on source change ────────────────────────────────────────────

  const triggerCompile = useCallback((source) => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = setTimeout(async () => {
      // Cancel any in-flight compile
      if (abortRef.current) abortRef.current.abort()
      const controller = new AbortController()
      abortRef.current = controller

      setCompiling(true)
      const result = await compileAtopile(source, { signal: controller.signal })
      if (controller.signal.aborted) return

      setCompiling(false)
      if (result.ok) {
        setCircuit(result.circuit)
        setCompileErrors([])
        setCompileWarnings(result.warnings ?? [])
      } else {
        setCompileErrors((result.errors ?? []).map((e) => e.message))
        setCompileWarnings([])
        // Keep last good circuit so the Circuit tab doesn't go blank
      }
    }, COMPILE_DEBOUNCE_MS)
  }, [])

  useEffect(() => {
    if (value) triggerCompile(value)
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current)
      if (abortRef.current) abortRef.current.abort()
    }
  }, [value, triggerCompile])

  // ── Monaco lifecycle ────────────────────────────────────────────────────

  const handleBeforeMount = useCallback((monaco) => {
    registerAtopileLanguage(monaco)
  }, [])

  const handleMount = useCallback((editor) => {
    const set = (focused) =>
      useWorkspace.getState().setEditorFocused(focused)
    editor.onDidFocusEditorText(() => set(true))
    editor.onDidBlurEditorText(() => set(false))
  }, [])

  // ── Render ──────────────────────────────────────────────────────────────

  const hasErrors = compileErrors.length > 0

  return (
    <div className="flex flex-col h-full bg-ink-900">
      {/* Tab bar */}
      <div className="flex items-center border-b border-ink-700 px-2 gap-1 flex-shrink-0">
        {TABS.map(({ id, label, Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={[
              'flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t transition-colors',
              activeTab === id
                ? 'text-white border-b-2 border-blue-500'
                : 'text-ink-400 hover:text-ink-200',
            ].join(' ')}
          >
            <Icon size={13} />
            {label}
            {id === 'circuit' && compiling && (
              <Loader2 size={11} className="animate-spin ml-0.5 text-blue-400" />
            )}
          </button>
        ))}
      </div>

      {/* Error / warning banners (always visible, regardless of tab) */}
      {hasErrors && (
        <div className="flex items-start gap-2 px-3 py-2 bg-red-950/60 border-b border-red-900/60 text-red-200 text-xs font-mono flex-shrink-0">
          <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
          <div className="flex-1 whitespace-pre-wrap break-words">
            {compileErrors.join('\n')}
          </div>
        </div>
      )}

      {!hasErrors && compileWarnings.length > 0 && (
        <div className="flex items-start gap-2 px-3 py-2 bg-amber-950/40 border-b border-amber-900/40 text-amber-200 text-xs flex-shrink-0">
          <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
          <div className="flex-1 break-words">
            {compileWarnings.join(' · ')}
          </div>
        </div>
      )}

      {readOnly && readOnlyReason && (
        <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-950/40 border-b border-amber-900/40 text-amber-200 text-[11px] flex-shrink-0">
          <AlertTriangle size={12} className="flex-shrink-0" />
          <span>{readOnlyReason}</span>
        </div>
      )}

      {/* Active view */}
      <div className="flex-1 min-h-0">
        {activeTab === 'source' && (
          <Editor
            height="100%"
            theme="atopile-dark"
            language={LANGUAGE_ID}
            value={value ?? ''}
            onChange={(v) => onChange?.(v ?? '')}
            options={{ ...MONACO_OPTIONS, readOnly }}
            beforeMount={handleBeforeMount}
            onMount={handleMount}
          />
        )}

        {activeTab === 'circuit' && (
          <CircuitPanel circuit={circuit} compiling={compiling} />
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CircuitPanel — renders the compiled Circuit JSON
// ---------------------------------------------------------------------------

function CircuitPanel({ circuit, compiling }) {
  if (!circuit && compiling) {
    return (
      <div className="flex items-center justify-center h-full text-ink-500 text-sm gap-2">
        <Loader2 size={16} className="animate-spin" />
        Compiling…
      </div>
    )
  }

  if (!circuit || circuit.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-ink-500 text-sm gap-2">
        <CircuitBoard size={32} className="opacity-30" />
        <span>No circuit — write a module in the Source tab</span>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 min-h-0">
        <SchematicView circuitJson={circuit} />
      </div>
    </div>
  )
}
