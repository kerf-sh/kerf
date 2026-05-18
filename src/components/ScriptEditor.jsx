// ScriptEditor — editable viewer for `.script.ts` and `.script.py` files.
//
// File shape: kind='script' with an extension field (.ts or .py). The TypeScript
// variant (Phase 1 stub) runs in the browser via esbuild-wasm. The Python
// variant (.script.py) is server-side — the editor is editable and content
// is saved via the normal file patch endpoint; the user interacts with the
// running workspace via `pip install kerf-sdk`.
//
// Wired:
//   - editContent path (writable editor; changes persist via saveFile)
//   - Monaco language mode based on file extension (typescript | python)

import { useState } from 'react'
import Editor from '@monaco-editor/react'
import { Code, Terminal, Info } from 'lucide-react'

const MONACO_OPTIONS = {
  readOnly: false,
  minimap: { enabled: false },
  fontFamily: 'JetBrains Mono, Geist Mono, ui-monospace, SF Mono, Menlo, monospace',
  fontSize: 12,
  lineNumbers: 'on',
  scrollBeyondLastLine: false,
  renderLineHighlight: 'none',
  tabSize: 2,
  wordWrap: 'on',
  padding: { top: 8, bottom: 8 },
  automaticLayout: true,
}

function scriptExtension(file) {
  if (!file) return 'ts'
  if (file.extension) return file.extension
  const n = (file.name || '').toLowerCase()
  if (n.endsWith('.script.py')) return 'py'
  return 'ts'
}

function languageFor(ext) {
  return ext === 'py' ? 'python' : 'typescript'
}

export default function ScriptEditor({ content, fileName, file, onChange }) {
  const src = typeof content === 'string' ? content : ''
  const ext = scriptExtension(file)
  const lang = languageFor(ext)
  const isPython = ext === 'py'
  // Collapsed by default — the "how it runs" blurb is reference, not
  // something the user needs every time. Saves vertical space.
  const [showInfo, setShowInfo] = useState(false)

  return (
    <div className="h-full flex flex-col bg-ink-950 text-ink-100 min-h-0">
      <div className="flex items-center gap-2 px-4 py-2.5 border-b border-ink-800 bg-ink-900/40 flex-shrink-0">
        <Code size={14} className="text-kerf-300 shrink-0" />
        <span className="text-xs font-semibold uppercase tracking-wider text-ink-300">
          Script
        </span>
        <span className="text-[11px] text-ink-500 truncate min-w-0">
          {fileName || ''}
        </span>
        <span className="ml-2 text-[10px] uppercase tracking-wider text-kerf-300 border border-kerf-300/40 rounded px-1.5 py-0.5">
          .script.{isPython ? 'py' : 'ts'}
        </span>
        <button
          type="button"
          onClick={() => setShowInfo((v) => !v)}
          aria-expanded={showInfo}
          title={showInfo ? 'Hide how scripts run' : 'How scripts run (Kerf SDK)'}
          className="ml-auto inline-flex items-center gap-1 text-[10px] text-ink-400 hover:text-kerf-300 border border-ink-700 hover:border-ink-600 rounded px-1.5 py-0.5 transition-colors shrink-0"
        >
          <Info size={11} />
          {showInfo ? 'Hide' : 'How it runs'}
        </button>
      </div>

      {showInfo && (
      <div className="px-4 py-3 border-b border-ink-800 bg-ink-900/40 flex-shrink-0">
        <div className="flex items-start gap-2 text-[11px] text-ink-300">
          <Terminal size={12} className="text-kerf-300 shrink-0 mt-0.5" />
          <div className="space-y-1 min-w-0">
            <div className="font-medium text-ink-100">
              Editable here · runs via the Kerf SDK on your machine
            </div>
            <div className="text-ink-400">
              Type and it saves with the project. Scripts execute through
              the SDK (not the browser) — drive this workspace over
              HTTP/JSON-RPC:
            </div>
            <code className="block font-mono text-[10px] text-kerf-200 bg-ink-950/60 rounded px-2 py-1 whitespace-pre">
              {`pip install kerf-sdk\nkerf run ${fileName || (isPython ? 'script.script.py' : 'script.script.ts')} --project <project-id>`}
            </code>
            <div className="text-ink-500">
              The 3D model renders in the viewport above — this script
              edits alongside it.
            </div>
          </div>
        </div>
      </div>
      )}

      <div className="flex-1 min-h-0">
        <Editor
          height="100%"
          theme="vs-dark"
          language={lang}
          value={src}
          options={MONACO_OPTIONS}
          onChange={onChange}
        />
      </div>
    </div>
  )
}
