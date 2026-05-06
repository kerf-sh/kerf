import Editor from '@monaco-editor/react'
import { AlertTriangle } from 'lucide-react'

const OPTIONS = {
  minimap: { enabled: false },
  fontFamily: 'JetBrains Mono, Geist Mono, ui-monospace, SF Mono, Menlo, monospace',
  fontSize: 13,
  lineNumbers: 'on',
  scrollBeyondLastLine: false,
  smoothScrolling: true,
  cursorBlinking: 'smooth',
  renderLineHighlight: 'line',
  tabSize: 2,
  wordWrap: 'off',
  padding: { top: 12, bottom: 12 },
  automaticLayout: true,
}

export default function CodeEditor({ value, onChange, errors, readOnly = false }) {
  const errs = (errors || []).filter(Boolean)
  return (
    <div className="flex flex-col h-full bg-ink-900">
      {errs.length > 0 && (
        <div className="flex items-start gap-2 px-3 py-2 bg-red-950/60 border-b border-red-900/60 text-red-200 text-xs font-mono">
          <AlertTriangle size={14} className="mt-0.5 flex-shrink-0" />
          <div className="flex-1 whitespace-pre-wrap break-words">
            {errs.join('\n')}
          </div>
        </div>
      )}
      <div className="flex-1 min-h-0">
        <Editor
          height="100%"
          theme="vs-dark"
          language="javascript"
          value={value ?? ''}
          onChange={(v) => onChange?.(v ?? '')}
          options={{ ...OPTIONS, readOnly }}
        />
      </div>
    </div>
  )
}
