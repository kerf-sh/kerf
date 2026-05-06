import { forwardRef, useEffect, useMemo, useRef, useState } from 'react'
import {
  Send, Star, MessageSquarePlus, MessageSquare, Trash2, Plus,
  ChevronUp, ChevronDown, Code as CodeIcon, FileDown,
} from 'lucide-react'
import PartChip from './PartChip.jsx'

// Extract ```jscad fenced blocks; return [{type:'text'|'jscad', content}, ...].
function parseMessage(text) {
  if (!text) return []
  const out = []
  const re = /```(\w+)?\n([\s\S]*?)```/g
  let lastIdx = 0
  let m
  while ((m = re.exec(text)) !== null) {
    if (m.index > lastIdx) {
      out.push({ type: 'text', content: text.slice(lastIdx, m.index) })
    }
    const lang = (m[1] || '').toLowerCase()
    out.push({
      type: (lang === 'jscad' || lang === 'js' || lang === 'javascript') ? 'jscad' : 'code',
      lang,
      content: m[2],
    })
    lastIdx = m.index + m[0].length
  }
  if (lastIdx < text.length) out.push({ type: 'text', content: text.slice(lastIdx) })
  return out
}

const ChatInput = forwardRef(function ChatInput({
  pendingPartRefs, onRemoveRef, onSubmit, sending, disabled,
}, ref) {
  const [value, setValue] = useState('')

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

  return (
    <div className="border-t border-ink-800 bg-ink-900 p-2">
      {pendingPartRefs.length > 0 && (
        <div className="flex flex-wrap gap-1 px-1 pb-2">
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
      <div className="flex items-end gap-2 bg-ink-850 border border-ink-700 rounded-lg p-2 focus-within:border-kerf-300/60 transition-colors">
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKey}
          placeholder={disabled ? 'Loading…' : 'Ask Kerf to refine the model…'}
          rows={2}
          disabled={disabled}
          className="flex-1 resize-none bg-transparent text-sm text-ink-100 placeholder:text-ink-400 outline-none font-sans leading-snug max-h-40"
        />
        <button
          type="button"
          onClick={submit}
          disabled={!value.trim() || sending || disabled}
          className="p-1.5 rounded-md bg-kerf-300 text-ink-950 hover:bg-kerf-200 disabled:opacity-30 disabled:cursor-not-allowed flex-shrink-0"
          title="Send (Enter)"
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  )
})

function MessageBlock({ message, onApply }) {
  const isUser = message.role === 'user'
  const blocks = useMemo(() => parseMessage(message.content || ''), [message.content])
  return (
    <div className={`flex flex-col gap-1.5 ${isUser ? 'items-end' : 'items-start'}`}>
      <div className={`text-[10px] uppercase tracking-wider ${isUser ? 'text-kerf-300' : 'text-ink-400'}`}>
        {isUser ? 'You' : 'Kerf'}
        {message._pending && ' · sending…'}
        {message._error && <span className="text-red-400 normal-case"> · {message._error}</span>}
      </div>
      {message.part_refs && message.part_refs.length > 0 && (
        <div className="flex flex-wrap gap-1 max-w-[88%]">
          {message.part_refs.map((r, i) => (
            <PartChip key={i} partId={r.part_id} fileName={r.label} />
          ))}
        </div>
      )}
      <div className={`max-w-[88%] rounded-lg px-3 py-2 text-sm ${
        isUser
          ? 'bg-kerf-300/15 border border-kerf-300/30 text-ink-100'
          : 'bg-ink-800 border border-ink-700 text-ink-100'
      }`}>
        {blocks.map((b, i) => {
          if (b.type === 'text') {
            return <div key={i} className="whitespace-pre-wrap break-words leading-relaxed">{b.content}</div>
          }
          return (
            <div key={i} className="my-2 first:mt-0 last:mb-0 rounded-md overflow-hidden border border-ink-700">
              <div className="flex items-center justify-between px-2 py-1 bg-ink-900 border-b border-ink-700 text-[10px] uppercase tracking-wider text-ink-400">
                <span className="flex items-center gap-1.5">
                  <CodeIcon size={10} />
                  {b.lang || 'code'}
                </span>
                {b.type === 'jscad' && onApply && (
                  <button
                    type="button"
                    onClick={() => onApply(b.content)}
                    className="flex items-center gap-1 px-2 py-0.5 rounded bg-kerf-300/20 text-kerf-200 hover:bg-kerf-300/30 normal-case text-[11px]"
                    title="Apply to current file"
                  >
                    <FileDown size={10} />
                    Apply to file
                  </button>
                )}
              </div>
              <pre className="p-2 m-0 text-xs font-mono text-ink-100 overflow-x-auto bg-ink-950 whitespace-pre">{b.content}</pre>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function ThreadList({ threads, currentThreadId, onSelect, onCreate, onToggleStar, onDelete, collapsed, setCollapsed }) {
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

  return (
    <div className="border-b border-ink-800 bg-ink-900">
      <div className="flex items-center justify-between px-3 py-2">
        <button
          type="button"
          className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-400 hover:text-ink-200"
          onClick={() => setCollapsed((c) => !c)}
        >
          {collapsed ? <ChevronDown size={12} /> : <ChevronUp size={12} />}
          Threads ({sorted.length})
        </button>
        <button
          type="button"
          onClick={onCreate}
          className="p-1 rounded hover:bg-ink-700 text-ink-300 hover:text-kerf-300"
          title="New thread"
        >
          <MessageSquarePlus size={13} />
        </button>
      </div>
      {!collapsed && (
        <div className="max-h-44 overflow-auto pb-1">
          {sorted.length === 0 ? (
            <div className="px-3 py-3 text-xs text-ink-400 text-center">
              <button
                type="button"
                onClick={onCreate}
                className="inline-flex items-center gap-1 text-kerf-300 hover:underline"
              >
                <Plus size={12} /> Start a thread
              </button>
            </div>
          ) : sorted.map((t) => {
            const active = t.id === currentThreadId
            return (
              <div
                key={t.id}
                onClick={() => onSelect(t.id)}
                className={`group flex items-center gap-1.5 px-3 py-1.5 cursor-pointer text-xs ${
                  active ? 'bg-kerf-300/10 text-kerf-100 border-l-2 border-kerf-300' : 'text-ink-200 hover:bg-ink-800 border-l-2 border-transparent'
                }`}
              >
                <MessageSquare size={11} className="flex-shrink-0 text-ink-400" />
                <span className="flex-1 truncate">{t.title || 'Untitled'}</span>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onToggleStar(t.id) }}
                  className={`flex-shrink-0 ${t.is_starred ? 'text-kerf-300' : 'text-ink-500 opacity-0 group-hover:opacity-100 hover:text-kerf-300'}`}
                  title={t.is_starred ? 'Unstar' : 'Star'}
                >
                  <Star size={11} fill={t.is_starred ? 'currentColor' : 'none'} />
                </button>
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onDelete(t.id) }}
                  className="flex-shrink-0 text-ink-500 opacity-0 group-hover:opacity-100 hover:text-red-400"
                  title="Delete thread"
                >
                  <Trash2 size={11} />
                </button>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

const ChatPanel = forwardRef(function ChatPanel({
  threads, currentThreadId, messages, pendingPartRefs,
  onSelectThread, onCreateThread, onToggleStar, onDeleteThread,
  onSend, onRemovePartRef, onApplyCode, sending, loadingMessages,
}, inputRef) {
  const scrollRef = useRef(null)
  const [collapsed, setCollapsed] = useState(false)

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, sending])

  return (
    <div className="h-full flex flex-col bg-ink-900 border-l border-ink-800 min-h-0">
      <ThreadList
        threads={threads}
        currentThreadId={currentThreadId}
        onSelect={onSelectThread}
        onCreate={onCreateThread}
        onToggleStar={onToggleStar}
        onDelete={onDeleteThread}
        collapsed={collapsed}
        setCollapsed={setCollapsed}
      />
      <div ref={scrollRef} className="flex-1 overflow-auto p-3 flex flex-col gap-3 min-h-0">
        {loadingMessages ? (
          <div className="text-xs text-ink-400 text-center py-8">Loading messages…</div>
        ) : messages.length === 0 ? (
          <div className="text-center text-ink-400 text-xs py-12">
            <MessageSquare size={20} className="mx-auto mb-2 text-ink-500" />
            <div>No messages yet.</div>
            <div className="mt-1 text-ink-500">
              Click parts in the viewport to reference them in your message.
            </div>
          </div>
        ) : messages.map((m) => (
          <MessageBlock key={m.id} message={m} onApply={onApplyCode} />
        ))}
        {sending && (
          <div className="text-[10px] uppercase tracking-wider text-ink-400 animate-pulse">
            Kerf is thinking…
          </div>
        )}
      </div>
      <ChatInput
        ref={inputRef}
        pendingPartRefs={pendingPartRefs}
        onRemoveRef={onRemovePartRef}
        onSubmit={onSend}
        sending={sending}
        disabled={loadingMessages}
      />
    </div>
  )
})

export default ChatPanel
