// FirmwareDebugPanel — RTOS-aware debug side-panel.
//
// Surfaces live RTOS task list, per-task stack high-watermark, mutex /
// semaphore / queue state, and dependency edges.
//
// Cloud path: the backend returns the JTAG sentinel and the panel renders
// a "JTAG requires the local Kerf CLI" notice instead of task data.
//
// Stack warning: any task with < 10 % stack free is highlighted with a
// warning badge.

import { useCallback, useEffect, useState } from 'react'
import {
  AlertTriangle, Bug, ChevronRight, Loader2, RefreshCw, X,
} from 'lucide-react'
import {
  attachDebugSession,
  fetchDebugSnapshot,
  isJtagSentinel,
  JTAG_CLOUD_SENTINEL,
} from '../lib/firmwareDebugBridge.js'

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SentinelBanner({ message }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 text-[12px] text-amber-200 mx-3 mt-3">
      <AlertTriangle size={14} className="mt-0.5 shrink-0 text-amber-400" />
      <span>{message || JTAG_CLOUD_SENTINEL}</span>
    </div>
  )
}

function ErrorBanner({ message, onDismiss }) {
  if (!message) return null
  return (
    <div className="flex items-start gap-2 rounded-md border border-red-500/30 bg-red-500/10 px-3 py-2 text-[11px] text-red-200 mx-3 mt-2">
      <AlertTriangle size={12} className="mt-0.5 shrink-0" />
      <span className="flex-1 break-words">{message}</span>
      {onDismiss && (
        <button onClick={onDismiss} className="text-red-300 hover:text-white ml-1">
          <X size={10} />
        </button>
      )}
    </div>
  )
}

function StackWarningBadge() {
  return (
    <span className="inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[9px] font-semibold bg-red-500/20 text-red-300 border border-red-500/30">
      <AlertTriangle size={8} />
      LOW STACK
    </span>
  )
}

function TaskStateChip({ state }) {
  const colours = {
    RUNNING:   'bg-green-500/20 text-green-300 border-green-500/30',
    READY:     'bg-blue-500/20 text-blue-300 border-blue-500/30',
    BLOCKED:   'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
    SUSPENDED: 'bg-ink-700 text-ink-400 border-ink-600',
    DELETED:   'bg-red-500/20 text-red-300 border-red-500/30',
  }
  const cls = colours[state] || colours.SUSPENDED
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-[9px] font-semibold border ${cls}`}>
      {state}
    </span>
  )
}

function TaskRow({ task }) {
  const pctFree = task.stack_pct_free ?? (
    task.stack_size > 0
      ? Math.round((task.stack_high_water / task.stack_size) * 1000) / 10
      : 100
  )
  const warn = task.stack_warning || pctFree < 10

  return (
    <div className={`flex items-center gap-2 px-3 py-2 text-[11px] border-b border-ink-800 hover:bg-ink-800/50 ${warn ? 'bg-red-950/20' : ''}`}>
      {/* Name + state */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="font-mono text-ink-100 truncate">{task.name}</span>
          <TaskStateChip state={task.state} />
          {warn && <StackWarningBadge />}
        </div>
        <div className="text-ink-500 mt-0.5">
          Priority {task.priority} · Stack {task.stack_high_water}B / {task.stack_size}B free
          ({pctFree.toFixed(1)}%)
        </div>
      </div>
      {/* Stack bar */}
      <div className="w-16 flex-shrink-0">
        <div className="h-1.5 rounded-full bg-ink-700 overflow-hidden">
          <div
            className={`h-full rounded-full ${warn ? 'bg-red-500' : 'bg-green-500'}`}
            style={{ width: `${Math.max(2, Math.min(100, pctFree))}%` }}
          />
        </div>
      </div>
    </div>
  )
}

function SyncObjectRow({ obj }) {
  return (
    <div className="px-3 py-2 text-[11px] border-b border-ink-800 hover:bg-ink-800/50">
      <div className="flex items-center gap-2">
        <span className="font-mono text-ink-100">{obj.name}</span>
        <span className="rounded px-1 py-0.5 text-[9px] font-semibold bg-ink-700 text-ink-300 border border-ink-600">
          {obj.kind}
        </span>
      </div>
      {obj.held_by && (
        <div className="text-ink-500 mt-0.5">
          Held by <span className="text-ink-200 font-mono">{obj.held_by}</span>
          {obj.waiters && obj.waiters.length > 0 && (
            <span> · Waiters: <span className="text-yellow-300 font-mono">{obj.waiters.join(', ')}</span></span>
          )}
        </div>
      )}
      {!obj.held_by && (
        <div className="text-ink-600 mt-0.5">Free</div>
      )}
    </div>
  )
}

function EdgeRow({ edge }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 text-[11px] border-b border-ink-800">
      <span className="font-mono text-ink-300">{edge.from}</span>
      <ChevronRight size={10} className="text-ink-600 flex-shrink-0" />
      <span className="font-mono text-ink-300">{edge.to}</span>
      <span className="ml-auto text-ink-500 text-[9px]">{edge.label}</span>
    </div>
  )
}

function SectionHeader({ label, count }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 bg-ink-900/60 border-b border-ink-800">
      <span className="text-[10px] font-semibold uppercase tracking-wider text-ink-400">{label}</span>
      {count != null && (
        <span className="rounded-full px-1.5 py-0.5 text-[9px] bg-ink-700 text-ink-300">{count}</span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

/**
 * FirmwareDebugPanel
 *
 * Props
 * -----
 * elfPath  : string   - path to ELF file (passed to attach)
 * target   : string   - OpenOCD target (default "stm32f4")
 * rtos     : string   - "kerfrtos" | "freertos"
 * onClose  : function - called when the × button is clicked
 *
 * For tests, the fetch layer is mocked via vi.stubGlobal.
 */
export default function FirmwareDebugPanel({
  elfPath = '',
  target = 'stm32f4',
  rtos = 'kerfrtos',
  onClose,
}) {
  const [snapshot, setSnapshot] = useState(null)
  const [loading, setLoading]   = useState(false)
  const [error, setError]       = useState(null)

  const refresh = useCallback(async () => {
    setLoading(true)
    setError(null)
    const result = await fetchDebugSnapshot()
    setLoading(false)
    if (result.ok || isJtagSentinel(result)) {
      setSnapshot(result)
    } else {
      setError(result.message || result.error || 'Failed to fetch snapshot')
    }
  }, [])

  const attach = useCallback(async () => {
    setLoading(true)
    setError(null)
    const result = await attachDebugSession({ elfPath, target, rtos })
    setLoading(false)
    setSnapshot(result)
    if (!result.ok && !isJtagSentinel(result)) {
      setError(result.message || result.error || 'Attach failed')
    }
  }, [elfPath, target, rtos])

  // On mount, try to fetch an existing snapshot first
  useEffect(() => {
    refresh()
  }, [refresh])

  const isSentinel = snapshot ? isJtagSentinel(snapshot) : false
  const tasks       = snapshot?.tasks ?? []
  const syncObjects = snapshot?.sync_objects ?? []
  const edges       = snapshot?.edges ?? []
  const warnings    = snapshot?.warnings ?? []

  // Stack warnings — tasks with < 10 % stack free
  const stackWarnings = warnings.filter(w => w.includes('stack'))

  return (
    <div className="flex flex-col h-full min-h-0 bg-ink-950 text-ink-100" data-testid="firmware-debug-panel">
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800 flex-shrink-0">
        <div className="flex items-center gap-2">
          <Bug size={14} className="text-ink-400" />
          <span className="text-[12px] font-semibold text-ink-100">RTOS Debugger</span>
          {loading && <Loader2 size={12} className="text-ink-500 animate-spin" />}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={attach}
            disabled={loading}
            className="rounded px-2 py-1 text-[10px] font-medium text-ink-300 hover:text-ink-100 hover:bg-ink-800 disabled:opacity-40"
            title="Attach to target"
          >
            Attach
          </button>
          <button
            onClick={refresh}
            disabled={loading}
            className="rounded p-1 text-ink-400 hover:text-ink-100 hover:bg-ink-800 disabled:opacity-40"
            title="Refresh snapshot"
          >
            <RefreshCw size={12} />
          </button>
          {onClose && (
            <button
              onClick={onClose}
              className="rounded p-1 text-ink-400 hover:text-ink-100 hover:bg-ink-800"
              title="Close"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto min-h-0">
        {/* JTAG sentinel */}
        {isSentinel && (
          <SentinelBanner message={snapshot?.message} />
        )}

        {/* Error */}
        <ErrorBanner message={error} onDismiss={() => setError(null)} />

        {/* Stack warnings */}
        {!isSentinel && stackWarnings.length > 0 && (
          <div className="mx-3 mt-3 rounded-md border border-red-500/30 bg-red-950/40 px-3 py-2">
            <div className="flex items-center gap-1.5 text-[10px] font-semibold text-red-300 mb-1">
              <AlertTriangle size={11} />
              STACK WARNING
            </div>
            {stackWarnings.map((w, i) => (
              <div key={i} className="text-[11px] text-red-200">{w}</div>
            ))}
          </div>
        )}

        {/* Task list */}
        {!isSentinel && tasks.length > 0 && (
          <div className="mt-2">
            <SectionHeader label="Tasks" count={tasks.length} />
            {tasks.map((task) => (
              <TaskRow key={task.name} task={task} />
            ))}
          </div>
        )}

        {/* Sync objects */}
        {!isSentinel && syncObjects.length > 0 && (
          <div className="mt-2">
            <SectionHeader label="Sync Objects" count={syncObjects.length} />
            {syncObjects.map((obj) => (
              <SyncObjectRow key={obj.name} obj={obj} />
            ))}
          </div>
        )}

        {/* Dependency edges */}
        {!isSentinel && edges.length > 0 && (
          <div className="mt-2">
            <SectionHeader label="Dependencies" count={edges.length} />
            {edges.map((edge, i) => (
              <EdgeRow key={i} edge={edge} />
            ))}
          </div>
        )}

        {/* Empty state */}
        {!isSentinel && !loading && !error && tasks.length === 0 && snapshot?.ok === false && (
          <div className="flex flex-col items-center justify-center py-12 text-ink-600 text-[12px] gap-2">
            <Bug size={24} className="text-ink-700" />
            <span>No snapshot yet — click Attach to connect</span>
          </div>
        )}

        {!isSentinel && !loading && snapshot?.ok === true && tasks.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-ink-600 text-[12px] gap-2">
            <Bug size={24} className="text-ink-700" />
            <span>No tasks found in snapshot</span>
          </div>
        )}
      </div>
    </div>
  )
}
