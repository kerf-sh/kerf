import { forwardRef, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
  Send, Star, MessageSquarePlus, MessageSquare, Trash2, Plus,
  Code as CodeIcon, ChevronDown, ChevronRight, Check, X, Sparkles,
  FolderTree, FileText, FilePen, Pencil, FilePlus, FileX, Search,
  Box, ShieldCheck, Wrench, Loader2, Square,
  TriangleAlert,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeHighlight from 'rehype-highlight'
import PartChip from './PartChip.jsx'
import { api } from '../lib/api.js'
import { useWorkspace } from '../store/workspace.js'
import usePrefersReducedMotion from '../lib/usePrefersReducedMotion.js'

const PROVIDER_LABELS = {
  anthropic: 'Anthropic',
  openai: 'OpenAI',
  moonshot: 'Moonshot',
  gemini: 'Google',
}

// ---------- click-outside hook ----------

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

// ---------- model picker (popover) ----------

function ModelPicker({ models, selectedId, onSelect, disabled }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)
  useClickOutside(wrapRef, () => setOpen(false), open)

  const current = useMemo(() => models.find((m) => m.id === selectedId), [models, selectedId])

  const grouped = useMemo(() => {
    const map = new Map()
    for (const m of models) {
      if (!map.has(m.provider)) map.set(m.provider, [])
      map.get(m.provider).push(m)
    }
    return Array.from(map.entries())
  }, [models])

  if (!models.length) return null

  // Stable DOM id for aria-activedescendant (sanitise the model id for use as
  // an HTML id — replace anything that isn't alphanumeric or dash/underscore).
  const activeOptionId = selectedId
    ? `model-option-${selectedId.replace(/[^a-zA-Z0-9_-]/g, '_')}`
    : undefined

  return (
    <div ref={wrapRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={`Model: ${current?.label || 'pick model'}`}
        className="group inline-flex items-center gap-1.5 px-2 py-1 rounded-md border border-ink-700 bg-ink-900/80 text-[11px] font-mono text-ink-200 hover:bg-ink-800 hover:border-ink-600 disabled:opacity-50 transition-colors"
        title="Pick model"
      >
        <Sparkles size={11} className="text-kerf-300" />
        <span className="max-w-[140px] truncate">{current?.label || 'pick model'}</span>
        <ChevronDown size={11} className="text-ink-400 group-hover:text-ink-200" />
      </button>

      {open && (
        <div
          role="listbox"
          aria-label="Select model"
          aria-activedescendant={activeOptionId}
          className="absolute bottom-full left-0 mb-1.5 z-30 w-64 rounded-lg border border-ink-700 bg-ink-900 shadow-2xl shadow-black/50 overflow-hidden"
        >
          <div className="max-h-[60vh] overflow-auto py-1">
            {grouped.map(([provider, ms]) => (
              <div key={provider} className="py-1">
                <div className="px-3 py-1 text-[10px] uppercase tracking-wider text-ink-500 font-semibold">
                  {PROVIDER_LABELS[provider] || provider}
                </div>
                {ms.map((m) => {
                  const active = m.id === selectedId
                  const optionId = `model-option-${m.id.replace(/[^a-zA-Z0-9_-]/g, '_')}`
                  return (
                    <div
                      key={m.id}
                      id={optionId}
                      role="option"
                      aria-selected={active}
                      onClick={() => { onSelect(m.id); setOpen(false) }}
                      className={`w-full flex items-center gap-2 px-3 py-1.5 text-left text-[12px] font-mono cursor-pointer ${
                        active ? 'bg-kerf-300/10 text-kerf-100' : 'text-ink-100 hover:bg-ink-800'
                      }`}
                    >
                      <span className="flex-1 truncate">{m.label}</span>
                      {m.is_default && !active && (
                        <span className="text-[9px] uppercase tracking-wider text-ink-500">default</span>
                      )}
                      {active && <Check size={12} className="text-kerf-300" />}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------- thread switcher (popover at top) ----------

function ThreadSwitcher({ threads, currentThreadId, onSelect, onCreate, onToggleStar, onDelete }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)
  useClickOutside(wrapRef, () => setOpen(false), open)

  const sorted = useMemo(() => {
    const ts = [...(threads || [])]
    ts.sort((a, b) => {
      if (a.is_starred !== b.is_starred) return a.is_starred ? -1 : 1
      const at = new Date(a.last_message_at || a.created_at || 0).getTime()
      const bt = new Date(b.last_message_at || b.created_at || 0).getTime()
      return bt - at
    })
    return ts
  }, [threads])

  const current = sorted.find((t) => t.id === currentThreadId)

  return (
    <div ref={wrapRef} className="relative border-b border-ink-800 bg-ink-900">
      <div className="flex items-stretch">
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          className="flex-1 flex items-center gap-2 px-3 py-2 text-left hover:bg-ink-800 transition-colors min-w-0"
          title="Switch thread"
        >
          <MessageSquare size={13} className="text-ink-400 flex-shrink-0" />
          <span className="text-sm text-ink-100 truncate flex-1">
            {current?.title || (sorted.length === 0 ? 'No threads — start typing to begin' : 'Pick a thread')}
          </span>
          {current?.is_starred && (
            <Star size={11} fill="currentColor" className="text-kerf-300 flex-shrink-0" />
          )}
          <span className="text-[10px] text-ink-500 font-mono flex-shrink-0">{sorted.length}</span>
          <ChevronDown size={12} className={`text-ink-400 flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
        <button
          type="button"
          onClick={() => { onCreate(); setOpen(false) }}
          className="px-3 border-l border-ink-800 text-ink-300 hover:bg-ink-800 hover:text-kerf-300 transition-colors"
          title="New thread"
        >
          <MessageSquarePlus size={14} />
        </button>
      </div>

      {open && (
        <div className="absolute top-full left-0 right-0 z-30 max-h-80 overflow-auto border-t border-b border-ink-700 bg-ink-900 shadow-2xl shadow-black/50">
          {sorted.length === 0 ? (
            <div className="p-6 text-center text-xs text-ink-400">
              <MessageSquare size={20} className="mx-auto mb-2 text-ink-600" />
              No threads yet. Send a message to create one.
            </div>
          ) : sorted.map((t) => {
            const active = t.id === currentThreadId
            return (
              <div
                key={t.id}
                onClick={() => { onSelect(t.id); setOpen(false) }}
                className={`group flex items-center gap-2 px-3 py-2 cursor-pointer text-sm border-l-2 ${
                  active
                    ? 'bg-kerf-300/10 border-kerf-300 text-kerf-100'
                    : 'border-transparent text-ink-100 hover:bg-ink-800'
                }`}
              >
                <MessageSquare size={12} className="text-ink-500 flex-shrink-0" />
                <span className="flex-1 truncate">{t.title || 'Untitled'}</span>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onToggleStar(t.id) }}
                  className={`flex-shrink-0 p-1 rounded hover:bg-ink-700 ${
                    t.is_starred ? 'text-kerf-300' : 'text-ink-500 opacity-0 group-hover:opacity-100 hover:text-kerf-300'
                  }`}
                  title={t.is_starred ? 'Unstar' : 'Star'}
                >
                  <Star size={11} fill={t.is_starred ? 'currentColor' : 'none'} />
                </button>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); if (confirm('Delete this thread?')) onDelete(t.id) }}
                  className="flex-shrink-0 p-1 rounded text-ink-500 opacity-0 group-hover:opacity-100 hover:bg-ink-700 hover:text-red-400"
                  title="Delete thread"
                >
                  <Trash2 size={11} />
                </button>
              </div>
            )
          })}
          <button
            type="button"
            onClick={() => { onCreate(); setOpen(false) }}
            className="w-full flex items-center gap-2 px-3 py-2 text-sm text-ink-300 hover:bg-ink-800 hover:text-kerf-300 border-t border-ink-800"
          >
            <Plus size={12} /> New thread
          </button>
        </div>
      )}
    </div>
  )
}

// ---------- markdown renderer ----------

// Flatten a React-node children value (string | element | array thereof) down
// to its concatenated text content. Used to detect "is this code block long
// enough to warrant the block treatment?" without naively String()ing the
// React tree — that's how we got `[object Object],[object Object],…` in the
// rendered output. We do NOT use this for rendering; rendering passes the
// real `children` so syntax-highlight spans survive.
export function childrenToText(node) {
  if (node == null || node === false) return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(childrenToText).join('')
  if (typeof node === 'object' && node.props && 'children' in node.props) {
    return childrenToText(node.props.children)
  }
  return ''
}

const MD_COMPONENTS = {
  // ReactMarkdown 9+ tells us inline vs block by checking children for newlines
  // / className. We detect block-ness by the presence of a `language-*` class.
  code({ inline, className, children, node: _node, ...rest }) {  // eslint-disable-line no-unused-vars
    // ^ `node` is react-markdown's hast AST node — if we let it through
    //   `...rest` it ends up as a DOM attribute serialising to
    //   `node="[object Object]"` (the exact symptom users saw).
    // ReactMarkdown 9+ in combination with rehype-highlight passes an
    // ARRAY of React nodes (one <span> per syntax-highlighted token) as
    // `children` for fenced code blocks. The previous implementation did
    // `String(children || '')` which converts the array to
    // "[object Object],[object Object],…" — the exact unreadable output
    // users saw in the chat. We must NOT stringify the React tree.
    //
    // Detect block-ness from the className (language-X) or by flattening
    // children to text only for the "looks like a block?" heuristic — but
    // when we render, we always render the React `children` directly so
    // the hljs spans (and any other rehype-injected markup) survive.
    const flatText = childrenToText(children)
    const langMatch = /language-([\w-]+)/.exec(className || '')
    const lang = langMatch ? langMatch[1] : ''
    const looksBlock = !inline && (lang || flatText.includes('\n'))
    if (!looksBlock) {
      return (
        <code className="px-1 py-0.5 rounded bg-ink-800 text-ink-100 font-mono text-[12px]" {...rest}>
          {children}
        </code>
      )
    }
    return (
      <div className="my-2 first:mt-0 last:mb-0 -mx-1 rounded-md overflow-hidden border border-ink-700 bg-ink-950">
        <div className="flex items-center justify-between px-2 py-1 bg-ink-900 border-b border-ink-700 text-[10px] uppercase tracking-wider text-ink-400">
          <span className="flex items-center gap-1.5">
            <CodeIcon size={10} />
            {lang || 'code'}
          </span>
        </div>
        <pre className="p-2 m-0 text-[12px] font-mono text-ink-100 overflow-x-auto whitespace-pre">
          <code className={`font-mono ${className || ''}`} {...rest}>
            {children}
          </code>
        </pre>
      </div>
    )
  },
  // Skip the default <pre> wrapper — `code` above handles its own wrapper.
  pre({ children }) { return <>{children}</> },
  a({ href, children, ...rest }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-kerf-300 underline underline-offset-2 hover:text-kerf-200"
        {...rest}
      >
        {children}
      </a>
    )
  },
  p({ children }) {
    return <p className="leading-relaxed my-1.5 first:mt-0 last:mb-0">{children}</p>
  },
  ul({ children }) {
    return <ul className="list-disc pl-5 my-1.5 space-y-0.5 first:mt-0 last:mb-0">{children}</ul>
  },
  ol({ children }) {
    return <ol className="list-decimal pl-5 my-1.5 space-y-0.5 first:mt-0 last:mb-0">{children}</ol>
  },
  li({ children }) {
    return <li className="leading-relaxed">{children}</li>
  },
  h1({ children }) { return <h1 className="text-base font-semibold mt-2 mb-1.5 first:mt-0">{children}</h1> },
  h2({ children }) { return <h2 className="text-sm font-semibold mt-2 mb-1.5 first:mt-0">{children}</h2> },
  h3({ children }) { return <h3 className="text-[13px] font-mono font-semibold mt-2 mb-1 first:mt-0 text-kerf-100">{children}</h3> },
  h4({ children }) { return <h4 className="text-[12px] font-mono font-semibold mt-1.5 mb-1 first:mt-0 text-kerf-100">{children}</h4> },
  h5({ children }) { return <h5 className="text-[12px] font-mono font-semibold mt-1.5 mb-1 first:mt-0 uppercase tracking-wider text-ink-300">{children}</h5> },
  h6({ children }) { return <h6 className="text-[11px] font-mono font-semibold mt-1.5 mb-1 first:mt-0 uppercase tracking-wider text-ink-400">{children}</h6> },
  blockquote({ children }) {
    return (
      <blockquote className="border-l-2 border-kerf-300/60 pl-3 my-2 text-ink-300 italic">
        {children}
      </blockquote>
    )
  },
  table({ children }) {
    return (
      <div className="my-2 overflow-x-auto -mx-1">
        <table className="text-[12px] font-mono border-collapse">
          {children}
        </table>
      </div>
    )
  },
  thead({ children }) { return <thead className="text-ink-300 border-b border-ink-700">{children}</thead> },
  tbody({ children }) { return <tbody>{children}</tbody> },
  tr({ children }) { return <tr className="border-b border-ink-800/80 last:border-0">{children}</tr> },
  th({ children }) { return <th className="text-left px-2 py-1 font-semibold">{children}</th> },
  td({ children }) { return <td className="px-2 py-1 align-top">{children}</td> },
  hr() { return <hr className="my-3 border-ink-700" /> },
}

export function Markdown({ text }) {
  if (!text) return null
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[[rehypeHighlight, { detect: true, ignoreMissing: true }]]}
      components={MD_COMPONENTS}
    >
      {text}
    </ReactMarkdown>
  )
}

// ---------- tool-call chips ----------

const TOOL_ICONS = {
  list_files: FolderTree,
  read_file: FileText,
  write_file: FilePen,
  edit_file: Pencil,
  create_file: FilePlus,
  delete_file: FileX,
  search_code: Search,
  import_step: Box,
  validate_jscad: ShieldCheck,
}

function ToolIcon({ name, size = 13, className = 'text-kerf-300 flex-shrink-0' }) {
  const Icon = TOOL_ICONS[name] || Wrench
  return <Icon size={size} className={className} />
}

// Try to JSON.parse; if it fails, return the raw string.
function parseMaybe(value) {
  if (value == null) return null
  if (typeof value !== 'string') return value
  try { return JSON.parse(value) } catch { return value }
}

// Compact one-liner derived from the call's args + result.
function toolSummary(name, args, parsedResult) {
  const a = args || {}
  switch (name) {
    case 'read_file': return a.path || ''
    case 'edit_file': return `${a.path || ''} · 1 edit`
    case 'write_file': {
      const bytes = typeof a.content === 'string'
        ? new TextEncoder().encode(a.content).length
        : (a.bytes || 0)
      return `${a.path || ''}${bytes ? ` · ${bytes}B` : ''}`
    }
    case 'create_file': return a.path || a.name || ''
    case 'delete_file': return a.path || ''
    case 'search_code': {
      const m = parsedResult && Array.isArray(parsedResult.matches)
        ? parsedResult.matches.length
        : (parsedResult && typeof parsedResult.count === 'number' ? parsedResult.count : null)
      return `${a.query || ''}${m != null ? ` · ${m} matches` : ''}`
    }
    case 'list_files': {
      const files = parsedResult && Array.isArray(parsedResult.files)
        ? parsedResult.files.length
        : (Array.isArray(parsedResult) ? parsedResult.length : null)
      return files != null ? `${files} files` : (a.path || '/')
    }
    case 'import_step': return a.name || a.path || ''
    case 'validate_jscad': return a.path || ''
    default: {
      // Generic: show the first short string-valued arg.
      for (const [k, v] of Object.entries(a)) {
        if (typeof v === 'string' && v.length < 80) return `${k}: ${v}`
      }
      return ''
    }
  }
}

// Naive but readable JSON pretty-printer with subtle syntax tinting.
function PrettyJson({ value }) {
  if (value === undefined) return null
  let text
  if (typeof value === 'string') text = value
  else {
    try { text = JSON.stringify(value, null, 2) }
    catch { text = String(value) }
  }
  return (
    <pre className="m-0 p-2 text-[11px] font-mono text-ink-100 leading-relaxed overflow-x-auto whitespace-pre-wrap break-words bg-ink-950 rounded border border-ink-800">
      {text}
    </pre>
  )
}

function StatusDot({ state }) {
  if (state === 'pending') {
    return <span className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse flex-shrink-0" title="Running" />
  }
  if (state === 'error') {
    return <X size={12} className="text-red-400 flex-shrink-0" />
  }
  return <Check size={12} className="text-emerald-400 flex-shrink-0" />
}

function ToolCallChip({ call }) {
  const [open, setOpen] = useState(false)
  const args = call.arguments || {}
  const parsedResult = parseMaybe(call.resultContent)
  const isError = !!(parsedResult && typeof parsedResult === 'object' && parsedResult.error)
  let state = 'success'
  if (call.pending) state = 'pending'
  else if (isError) state = 'error'
  const summary = toolSummary(call.name, args, parsedResult)

  return (
    <div className="rounded-lg border border-ink-700 bg-ink-900/60 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-2.5 py-1.5 text-left hover:bg-ink-800/60 transition-colors"
      >
        {open
          ? <ChevronDown size={12} className="text-ink-500 flex-shrink-0" />
          : <ChevronRight size={12} className="text-ink-500 flex-shrink-0" />}
        <ToolIcon name={call.name} />
        <span className="text-[12px] font-mono text-ink-100 flex-shrink-0">{call.name}</span>
        {summary && (
          <>
            <span className="text-ink-600 flex-shrink-0">·</span>
            <span className="text-[11px] font-mono text-ink-300 truncate min-w-0">{summary}</span>
          </>
        )}
        <span className="flex-1" />
        {call.durationMs != null && (
          <span className="text-[10px] font-mono text-ink-500 flex-shrink-0">{call.durationMs}ms</span>
        )}
        <StatusDot state={state} />
      </button>
      {open && (
        <div className="px-2.5 pb-2 pt-1 border-t border-ink-800 space-y-1.5">
          <div>
            <div className="text-[10px] uppercase tracking-wider text-ink-500 mb-1">args</div>
            <PrettyJson value={args} />
          </div>
          {call.resultContent !== undefined && (
            <div>
              <div className="text-[10px] uppercase tracking-wider text-ink-500 mb-1">result</div>
              <PrettyJson value={parsedResult} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ---------- assistant + tool pairing ----------
//
// The backend persists tool exchanges as separate rows:
//   - `assistant` row may carry `tool_calls: [{id, name, arguments}]`
//   - `tool` row carries `tool_call_id` linking back, `content` is JSON string.
//
// We collapse a stretch of [assistant(with tool_calls) + tool(s) + ...]
// into "groups". Each group is rendered as: assistant-text bubble (if any)
// followed by a stack of ToolCallChips.

function buildRenderItems(messages) {
  const items = []
  const byCallId = new Map()
  for (const m of messages || []) {
    if (m.role === 'tool') {
      byCallId.set(m.tool_call_id, m)
    }
  }
  for (const m of messages || []) {
    if (m.role === 'tool') {
      // Already absorbed into the matching assistant group.
      continue
    }
    if (m.role === 'assistant' && Array.isArray(m.tool_calls) && m.tool_calls.length) {
      // First emit the assistant's text (if any) as a normal bubble.
      if (m.content && m.content.trim()) {
        items.push({ kind: 'message', message: { ...m, tool_calls: undefined } })
      }
      // Then emit a chip group.
      const calls = m.tool_calls.map((c) => {
        const toolMsg = byCallId.get(c.id)
        const argsParsed = typeof c.arguments === 'string' ? parseMaybe(c.arguments) : c.arguments
        return {
          id: c.id,
          name: c.name,
          arguments: argsParsed && typeof argsParsed === 'object' ? argsParsed : {},
          resultContent: toolMsg ? toolMsg.content : undefined,
          durationMs: toolMsg?.duration_ms ?? c.duration_ms ?? null,
          pending: !toolMsg && !!m._pending,
        }
      })
      items.push({ kind: 'tool-group', id: m.id, calls, model: m.model })
      continue
    }
    items.push({ kind: 'message', message: m })
  }
  return items
}

// ---------- live streaming tool chip list ----------

/**
 * ToolChipList — rendered inside a streaming assistant message to show
 * live tool-call progress.
 *
 * chips: [{ tool_use_id, name, status: 'queued'|'running'|'done'|'error', content_preview? }]
 */
// Human labels for the tool-use chips. The model surface uses
// snake_case ids (read_file, run_compute(engine=...)) which look
// engineery in a chat bubble; map them to verbs the user understands.
const TOOL_VERB = {
  read_file:        'Reading',
  write_file:       'Writing',
  edit_file:        'Editing',
  list_files:       'Listing files',
  search_files:     'Searching files',
  create_file:      'Creating',
  describe_part:    'Inspecting',
  search_kerf_docs: 'Searching docs',
  import_step:      'Importing STEP',
  export_artifact:  'Exporting',
  run_compute:      'Computing',
  poll_compute:     'Checking compute',
}

function _humanToolLabel(chip) {
  const verb = TOOL_VERB[chip.name] || chip.name
  // Extract a short target hint from the input if available — file path
  // basename or engine name. Keeps each chip to a single line.
  let hint = ''
  if (chip.input) {
    if (chip.input.path) {
      const p = String(chip.input.path)
      hint = p.split('/').filter(Boolean).pop() || ''
    } else if (chip.input.engine) {
      hint = String(chip.input.engine)
    } else if (chip.input.query) {
      hint = String(chip.input.query).slice(0, 30)
    }
  }
  return hint ? `${verb} ${hint}` : verb
}

function ToolChipList({ chips }) {
  if (!chips || chips.length === 0) return null
  return (
    <div
      data-testid="tool-chip-list"
      className="flex flex-col gap-1 mt-2 mb-0.5"
    >
      {chips.map((chip) => {
        const label = _humanToolLabel(chip)
        const status = chip.status || 'queued'
        return (
          <div
            key={chip.tool_use_id}
            data-testid="tool-chip"
            data-status={status}
            className={`flex items-center gap-2 px-2.5 py-1.5 rounded-lg border text-[11px] transition-colors ${
              status === 'running'
                ? 'border-kerf-300/40 bg-kerf-300/10 text-kerf-200'
                : status === 'done'
                ? 'border-ink-700 bg-ink-900/50 text-ink-300'
                : status === 'error'
                ? 'border-red-500/40 bg-red-500/10 text-red-200'
                : 'border-ink-800 bg-ink-900/30 text-ink-400'
            }`}
          >
            <span
              className={`grid place-items-center w-5 h-5 rounded-md shrink-0 ${
                status === 'running' ? 'bg-kerf-300/20 text-kerf-300'
                : status === 'done'    ? 'bg-ink-800 text-emerald-400'
                : status === 'error'   ? 'bg-red-500/20 text-red-300'
                :                        'bg-ink-800/60 text-ink-500'
              }`}
            >
              {status === 'running' ? (
                <Loader2 size={11} className="animate-spin" />
              ) : status === 'done' ? (
                <Check size={11} />
              ) : status === 'error' ? (
                <TriangleAlert size={11} />
              ) : (
                <span className="w-1.5 h-1.5 rounded-full bg-current opacity-50" />
              )}
            </span>
            <span className="flex-1 min-w-0 truncate font-medium tracking-tight">
              {label}
            </span>
            <span className="font-mono text-[10px] uppercase tracking-wider opacity-60 shrink-0">
              {status === 'running' ? '…' : status === 'done' ? 'ok' : status === 'error' ? 'err' : 'queued'}
            </span>
          </div>
        )
      })}
    </div>
  )
}

// ---------- message bubble ----------

function MessageBlock({ message, modelLookup, isLatestAssistant, onRetry }) {
  const isUser = message.role === 'user'
  const showBadge = !isUser && message.model && message.model !== 'none'
  const badgeProvider = showBadge ? (modelLookup?.[message.model]?.provider || '') : ''

  return (
    <div className={`flex flex-col gap-1.5 ${isUser ? 'items-end' : 'items-start'}`}>
      {!isUser && (
        <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-ink-500">
          <Sparkles size={10} className="text-kerf-300" />
          <span>Kerf</span>
          {showBadge && (
            <>
              <span className="text-ink-600">·</span>
              <span className="font-mono normal-case tracking-normal text-ink-400">
                {message.model}{badgeProvider ? ` · ${PROVIDER_LABELS[badgeProvider] || badgeProvider}` : ''}
              </span>
            </>
          )}
        </div>
      )}
      {Array.isArray(message.part_refs) && message.part_refs.length > 0 && (
        <div className="flex flex-wrap gap-1 max-w-[88%]">
          {message.part_refs.map((r, i) => (
            <PartChip key={i} partId={r.part_id} fileName={r.label} />
          ))}
        </div>
      )}
      <div
        className={`max-w-[88%] rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
          isUser
            ? 'bg-kerf-300/15 border border-kerf-300/30 text-ink-100 rounded-br-sm'
            : 'bg-ink-800 border border-ink-700 text-ink-100 rounded-bl-sm'
        }`}
        {...(!isUser && isLatestAssistant
          ? { 'aria-live': 'polite', 'aria-atomic': 'false', 'data-live-region': 'assistant-reply' }
          : {})}
      >
        {isUser ? (
          <div className="whitespace-pre-wrap break-words">{message.content}</div>
        ) : (
          <>
            {(message.content || message._streaming) && (
              <Markdown text={message.content || ''} />
            )}
            {message._streaming && !message.content && (
              <span className="text-ink-500 animate-pulse text-xs">…</span>
            )}
            {Array.isArray(message._toolChips) && message._toolChips.length > 0 && (
              <ToolChipList chips={message._toolChips} />
            )}
          </>
        )}
      </div>
      {message._pending && (
        <div className="text-[10px] text-ink-500">sending…</div>
      )}
      {message._error && (
        <div
          role="alert"
          data-testid="chat-message-error"
          className="max-w-[88%] mt-1 rounded-md border border-red-500/40 bg-red-500/10 px-2.5 py-1.5 text-[11px] text-red-300 flex items-start gap-1.5"
        >
          <TriangleAlert size={12} className="mt-0.5 shrink-0" />
          <div className="leading-snug flex-1">
            <div className="font-medium text-red-200">
              {isUser ? 'Message failed to send' : 'Reply interrupted'}
            </div>
            <div className="text-red-300/90 break-words">{message._error}</div>
            {!isUser && onRetry && (
              <button
                type="button"
                data-testid="chat-message-retry"
                onClick={onRetry}
                className="mt-1.5 inline-flex items-center gap-1 px-2 py-0.5 rounded bg-red-500/20 border border-red-500/30 text-red-200 hover:bg-red-500/30 transition-colors text-[10px] font-medium"
              >
                Retry
              </button>
            )}
            {isUser && (
              <div className="text-red-300/70 mt-0.5">Try sending it again.</div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

function ToolGroup({ calls, model, modelLookup }) {
  const showBadge = model && model !== 'none'
  const badgeProvider = showBadge ? (modelLookup?.[model]?.provider || '') : ''
  return (
    <div className="flex flex-col gap-1.5 items-start">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-ink-500">
        <Wrench size={10} className="text-kerf-300" />
        <span>Tools</span>
        {showBadge && (
          <>
            <span className="text-ink-600">·</span>
            <span className="font-mono normal-case tracking-normal text-ink-400">
              {model}{badgeProvider ? ` · ${PROVIDER_LABELS[badgeProvider] || badgeProvider}` : ''}
            </span>
          </>
        )}
      </div>
      <div className="flex flex-col gap-1.5 max-w-[92%] w-full">
        {calls.map((c) => <ToolCallChip key={c.id} call={c} />)}
      </div>
    </div>
  )
}

// ---------- input ----------

const ChatInput = forwardRef(function ChatInput({
  pendingPartRefs, onRemoveRef, onSubmit, sending, disabled,
  models, selectedModelId, onSelectModel,
}, ref) {
  const [value, setValue] = useState('')
  const internalRef = useRef(null)
  const taRef = ref || internalRef

  useLayoutEffect(() => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = Math.min(ta.scrollHeight, 240) + 'px'
  }, [value, taRef])

  function submit() {
    const v = value.trim()
    if (!v || sending || disabled) return
    onSubmit(v)
    setValue('')
  }

  function onKey(e) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault()
      submit()
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const canSend = !!value.trim() && !sending && !disabled

  return (
    <div className="border-t border-ink-800 bg-ink-900 p-3">
      {pendingPartRefs.length > 0 && (
        <div className="flex flex-wrap gap-1 mb-2">
          {pendingPartRefs.map((r, i) => (
            <PartChip
              key={`${r.file_id}:${r.part_id}:${i}`}
              partId={r.part_id}
              fileName={r.label}
              onRemove={() => onRemoveRef(i)}
            />
          ))}
        </div>
      )}
      <div className="rounded-xl border border-ink-700 bg-ink-850 focus-within:border-kerf-300/50 transition-colors">
        <textarea
          ref={taRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKey}
          placeholder={disabled ? 'Loading…' : 'Ask Kerf to refine the model…'}
          aria-label="Chat message"
          rows={2}
          disabled={disabled}
          className="w-full resize-none bg-transparent text-sm text-ink-100 placeholder:text-ink-500 outline-none font-sans leading-relaxed px-3 py-2.5"
        />
        <div className="flex items-center justify-between gap-2 px-2 py-1.5 border-t border-ink-800/80 bg-ink-900/40">
          <div className="flex items-center gap-2 min-w-0">
            <ModelPicker
              models={models}
              selectedId={selectedModelId}
              onSelect={onSelectModel}
              disabled={disabled}
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-ink-500 hidden sm:inline">
              <kbd className="px-1 py-0.5 rounded bg-ink-800 border border-ink-700 font-mono text-[9px] text-ink-400">↵</kbd> send
            </span>
            <button
              type="button"
              onClick={submit}
              disabled={!canSend}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-kerf-300 text-ink-950 text-xs font-semibold hover:bg-kerf-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
              title="Send (Enter)"
            >
              <Send size={12} />
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  )
})

// ---------- root ----------

// Collapse is owned by the topbar toggle in Editor.jsx — when collapsed the
// parent grid drops the entire 380px column, so this component never has to
// render anything narrower than its full width. Keeping a second collapse
// here used to leave an empty grid track behind.

const ChatPanel = forwardRef(function ChatPanel({
  threads, currentThreadId, messages, pendingPartRefs,
  onSelectThread, onCreateThread, onToggleStar, onDeleteThread,
  onSend, onRemovePartRef, onCancelStream, sending, loadingMessages,
}, inputRef) {
  const scrollRef = useRef(null)
  const [models, setModels] = useState([])
  const setThreadModel = useWorkspace((s) => s.setThreadModel)
  const [pendingModel, setPendingModel] = useState(null)
  const [sendError, setSendError] = useState(null)
  const reduced = usePrefersReducedMotion()

  useEffect(() => {
    let cancelled = false
    api.listModels()
      .then((list) => {
        if (cancelled) return
        // /api/models returns { models: [...] }; tolerate a bare array
        // too. Treating the object as non-array gave models=[] →
        // ModelPicker rendered null → no model dropdown at all.
        const arr = Array.isArray(list) ? list : (list?.models || [])
        setModels(arr)
      })
      .catch(() => { if (!cancelled) setModels([]) })
    return () => { cancelled = true }
  }, [])

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, sending])

  // Derive send-failure from the latest user message that carries _error.
  // This surfaces the error as a transient banner near the input; it is
  // cleared the moment the user fires the next send (see handleSend).
  useEffect(() => {
    const msgs = messages || []
    const failed = msgs.slice().reverse().find((m) => m.role === 'user' && m._error && !m._pending)
    setSendError(failed ? (failed._error || 'Send failed') : null)
  }, [messages])

  const defaultModelId = useMemo(() => {
    if (!models.length) return null
    return (models.find((m) => m.is_default) || models[0]).id
  }, [models])

  const modelLookup = useMemo(() => {
    const o = {}
    for (const m of models) o[m.id] = m
    return o
  }, [models])

  const currentThread = useMemo(
    () => (threads || []).find((t) => t.id === currentThreadId) || null,
    [threads, currentThreadId],
  )

  const selectedModelId = useMemo(() => {
    if (!models.length) return null
    if (currentThread?.model && modelLookup[currentThread.model]) return currentThread.model
    if (pendingModel && modelLookup[pendingModel]) return pendingModel
    return defaultModelId
  }, [models, currentThread, pendingModel, modelLookup, defaultModelId])

  const handleSelectModel = useCallback((modelId) => {
    if (!modelId) return
    if (currentThreadId) {
      setThreadModel(currentThreadId, modelId)
    } else {
      setPendingModel(modelId)
    }
  }, [currentThreadId, setThreadModel])

  const handleSend = useCallback((content) => {
    setSendError(null)
    onSend(content, { model: selectedModelId })
  }, [onSend, selectedModelId])

  const renderItems = useMemo(() => buildRenderItems(messages), [messages])

  // Build a mapping from each render-item index to the preceding user
  // message content — used to wire up the retry button on errored assistant
  // messages so we can re-send the same prompt without needing the store.
  const retryContentByIndex = useMemo(() => {
    const map = {}
    let lastUserContent = null
    for (let i = 0; i < renderItems.length; i++) {
      const item = renderItems[i]
      if (item.kind === 'message' && item.message.role === 'user') {
        lastUserContent = item.message.content || null
      } else if (item.kind === 'message' && item.message.role === 'assistant' && item.message._error) {
        map[i] = lastUserContent
      }
    }
    return map
  }, [renderItems])

  return (
    <div className="h-full w-full flex flex-col bg-ink-900 min-h-0 overflow-hidden">
      <ThreadSwitcher
        threads={threads}
        currentThreadId={currentThreadId}
        onSelect={onSelectThread}
        onCreate={onCreateThread}
        onToggleStar={onToggleStar}
        onDelete={onDeleteThread}
      />

      <div ref={scrollRef} className="flex-1 overflow-auto px-3 py-4 flex flex-col gap-3 min-h-0">
        {loadingMessages ? (
          <div className="text-xs text-ink-400 text-center py-8">Loading messages…</div>
        ) : renderItems.length === 0 ? (
          <EmptyState hasThreads={(threads || []).length > 0} />
        ) : (() => {
          // Find the index of the last assistant message block so we can mark
          // it with aria-live="polite" for screen-reader streaming announcement.
          let lastAssistantIdx = -1
          for (let i = renderItems.length - 1; i >= 0; i--) {
            if (renderItems[i].kind === 'message' && renderItems[i].message.role === 'assistant') {
              lastAssistantIdx = i
              break
            }
          }
          return renderItems.map((item, i) => {
            if (item.kind === 'tool-group') {
              return <ToolGroup key={`tg-${item.id || i}`} calls={item.calls} model={item.model} modelLookup={modelLookup} />
            }
            const retryContent = retryContentByIndex[i]
            const onRetry = retryContent != null
              ? () => handleSend(retryContent)
              : undefined
            return (
              <MessageBlock
                key={item.message.id || i}
                message={item.message}
                modelLookup={modelLookup}
                isLatestAssistant={i === lastAssistantIdx}
                onRetry={onRetry}
              />
            )
          })
        })()}
        {sending && (() => {
          // Check if there is an in-progress streaming message with live chips.
          const streamingMsg = messages && messages.find((m) => m._streaming)
          const hasChips = streamingMsg && Array.isArray(streamingMsg._toolChips) && streamingMsg._toolChips.length > 0
          // Only show the "thinking" indicator when there's no streaming message
          // taking up space in the list (the streaming message renders itself).
          const showThinking = !streamingMsg
          return (
            <div className="flex items-center gap-2 text-[11px] text-ink-400">
              {showThinking && (
                <>
                  <Sparkles size={11} className={reduced ? 'text-kerf-300' : 'text-kerf-300 animate-pulse'} />
                  <span className={reduced ? undefined : 'animate-pulse'}>Kerf is thinking…</span>
                </>
              )}
              {onCancelStream && (
                <button
                  type="button"
                  data-testid="cancel-stream-btn"
                  onClick={onCancelStream}
                  className="ml-auto flex items-center gap-1 px-2 py-0.5 rounded border border-ink-700 bg-ink-800 text-ink-300 hover:bg-ink-700 hover:text-ink-100 transition-colors text-[10px]"
                  title="Stop generating"
                >
                  <Square size={9} />
                  Stop
                </button>
              )}
            </div>
          )
        })()}
      </div>

      {sendError && (
        <div
          role="alert"
          aria-live="assertive"
          data-testid="chat-send-error-banner"
          className="mx-3 mb-1 rounded-md border border-red-500/40 bg-red-500/10 px-2.5 py-1.5 text-[11px] text-red-300 flex items-center gap-1.5"
        >
          <TriangleAlert size={12} className="shrink-0 text-red-400" />
          <span className="flex-1 leading-snug">
            Couldn&apos;t send — {sendError}
          </span>
          <button
            type="button"
            data-testid="chat-send-error-dismiss"
            onClick={() => setSendError(null)}
            aria-label="Dismiss error"
            className="shrink-0 p-0.5 rounded hover:bg-red-500/20 text-red-400 hover:text-red-200 transition-colors"
          >
            <X size={11} />
          </button>
        </div>
      )}

      <ChatInput
        ref={inputRef}
        pendingPartRefs={pendingPartRefs}
        onRemoveRef={onRemovePartRef}
        onSubmit={handleSend}
        sending={sending}
        disabled={loadingMessages}
        models={models}
        selectedModelId={selectedModelId}
        onSelectModel={handleSelectModel}
      />
    </div>
  )
})

function EmptyState({ hasThreads }) {
  return (
    <div className="m-auto max-w-xs text-center text-ink-400">
      <div className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-kerf-300/10 border border-kerf-300/30 mb-3">
        <Sparkles size={16} className="text-kerf-300" />
      </div>
      <div className="text-sm text-ink-200 mb-1.5 font-medium">
        {hasThreads ? 'New conversation' : 'Start chatting with Kerf'}
      </div>
      <div className="text-xs text-ink-400 leading-relaxed">
        Click parts in the 3D view to reference them, then describe what you want changed.
      </div>
      <div className="mt-4 text-[10px] uppercase tracking-wider text-ink-500">
        Try
      </div>
      <div className="mt-1.5 flex flex-col gap-1 text-[11px] font-mono text-ink-300">
        <div className="px-2 py-1 rounded bg-ink-800/60 border border-ink-700">make the base 6mm taller</div>
        <div className="px-2 py-1 rounded bg-ink-800/60 border border-ink-700">add a 2mm fillet to the peg</div>
      </div>
    </div>
  )
}

export default ChatPanel
