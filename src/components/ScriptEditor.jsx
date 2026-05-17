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

import Editor from '@monaco-editor/react'
import { AlertTriangle, Code, Terminal } from 'lucide-react'

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
      </div>

      {isPython ? (
        <div className="px-4 py-3 border-b border-ink-800 bg-cyan-950/20 flex-shrink-0">
          <div className="flex items-start gap-2 text-[11px] text-cyan-200">
            <Terminal size={12} className="text-cyan-400 shrink-0 mt-0.5" />
            <div>
              <div className="font-medium text-cyan-300">
                Run on your machine via kerf-sdk
              </div>
              <div className="text-cyan-200/70 mt-0.5 space-y-1">
                <div>
                  Edit in your own IDE, then run against this workspace over HTTP/JSON-RPC:
                </div>
                <code className="block font-mono text-[10px] text-cyan-100 bg-cyan-950/40 rounded px-2 py-1 mt-1 whitespace-pre">
                  {`pip install kerf-sdk\nkerf run ${fileName || 'script.script.py'} --project <project-id>`}
                </code>
                <div className="text-cyan-200/60">
                  Works against local install (<span className="font-mono">localhost:8080</span>) or cloud.
                </div>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="px-4 py-3 border-b border-ink-800 bg-amber-950/20 flex-shrink-0">
          <div className="flex items-start gap-2 text-[11px] text-amber-200">
            <AlertTriangle size={12} className="text-amber-400 shrink-0 mt-0.5" />
            <div>
              <div className="font-medium text-amber-300">
                In-app script editing is read-only — automate with the Python SDK
              </div>
              <div className="text-amber-200/70 mt-0.5">
                Scripting runs on your machine, not in the browser:
                {' '}<span className="font-mono">pip install kerf-sdk</span>, then
                drive this instance over HTTP/JSON-RPC. The in-app
                {' '}<span className="font-mono">.script</span> kind round-trips
                and stores fine but is intentionally a read-only stub here.
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
