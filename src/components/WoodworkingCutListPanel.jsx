// WoodworkingCutListPanel — read-only panel that renders a woodworking cut list.
//
// Accepts the JSON payload returned by the `woodworking_cut_list` LLM tool
// (kerf-woodworking package). Renders a table of board assignments with
// utilisation, waste, and off-cut summary.
//
// Props:
//   cutList  — parsed cut-list result object or null
//   raw      — raw string content (for parse fallback)

import { Layers, AlertTriangle } from 'lucide-react'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseCutList(raw) {
  if (!raw || typeof raw !== 'string' || !raw.trim()) return null
  try {
    const doc = JSON.parse(raw)
    if (doc && typeof doc === 'object') return doc
  } catch (_) {}
  return null
}

function fmtMm(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  return `${Number(v).toFixed(0)} mm`
}

function fmtPct(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  return `${Number(v).toFixed(1)} %`
}

function UtilBar({ pct }) {
  const clamped = Math.min(100, Math.max(0, pct ?? 0))
  const color = clamped >= 85 ? '#34d399' : clamped >= 60 ? '#fbbf24' : '#f87171'
  return (
    <div className="flex items-center gap-1.5">
      <div className="flex-1 h-1.5 rounded-full bg-ink-800 overflow-hidden">
        <div style={{ width: `${clamped}%`, backgroundColor: color }} className="h-full rounded-full transition-all" />
      </div>
      <span className="text-[10px] font-mono text-ink-400 w-10 text-right">{fmtPct(pct)}</span>
    </div>
  )
}

function BoardTable({ boards, stockLength }) {
  if (!boards || boards.length === 0) {
    return (
      <div className="text-[11px] text-ink-500 italic py-4 text-center">
        No boards — run <code className="text-kerf-300">woodworking_cut_list</code> to generate assignments.
      </div>
    )
  }

  return (
    <div className="overflow-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-ink-800 text-ink-500 uppercase tracking-wider text-[10px]">
            <th className="text-left py-1.5 px-2 font-medium">Board</th>
            <th className="text-left py-1.5 px-2 font-medium">Pieces</th>
            <th className="text-right py-1.5 px-2 font-medium">Used</th>
            <th className="text-right py-1.5 px-2 font-medium">Waste</th>
            <th className="text-left py-1.5 px-3 font-medium w-32">Utilisation</th>
          </tr>
        </thead>
        <tbody>
          {boards.map((board, i) => {
            const pieces   = Array.isArray(board.pieces) ? board.pieces : []
            const usedMm   = board.used_mm ?? board.used_length_mm
            const wasteMm  = board.waste_mm ?? board.waste_length_mm
            const pct      = board.utilisation_pct ?? board.utilisation
            return (
              <tr key={board.board_id ?? i} className="border-b border-ink-800/50 hover:bg-ink-900/40">
                <td className="py-1.5 px-2 font-mono text-ink-200">
                  #{board.board_id ?? (i + 1)}
                  {stockLength ? <span className="text-ink-600 text-[10px] ml-1">/ {fmtMm(stockLength)}</span> : null}
                </td>
                <td className="py-1.5 px-2 text-ink-300">
                  {pieces.length > 0 ? (
                    <span title={pieces.map((p) => p.label || p.piece_label || p).join(', ')}>
                      {pieces.length} piece{pieces.length !== 1 ? 's' : ''}
                    </span>
                  ) : '—'}
                </td>
                <td className="py-1.5 px-2 text-right font-mono text-ink-200">{fmtMm(usedMm)}</td>
                <td className="py-1.5 px-2 text-right font-mono text-ink-500">{fmtMm(wasteMm)}</td>
                <td className="py-1.5 px-2 px-3 w-32"><UtilBar pct={pct} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function PieceTable({ pieces }) {
  if (!pieces || pieces.length === 0) return null

  return (
    <div className="overflow-auto border-t border-ink-800">
      <div className="px-3 py-1.5 text-[10px] text-ink-500 uppercase tracking-wider font-medium">
        Required pieces
      </div>
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-ink-800 text-ink-500 text-[10px]">
            <th className="text-left py-1 px-2 font-medium">Label</th>
            <th className="text-right py-1 px-2 font-medium">Length</th>
            <th className="text-right py-1 px-2 font-medium">Qty</th>
            <th className="text-left py-1 px-2 font-medium">Grain</th>
            <th className="text-left py-1 px-2 font-medium">Board</th>
          </tr>
        </thead>
        <tbody>
          {pieces.map((p, i) => (
            <tr key={p.label ?? i} className="border-b border-ink-800/40 hover:bg-ink-900/30">
              <td className="py-1 px-2 text-ink-200">{p.label || `piece-${i + 1}`}</td>
              <td className="py-1 px-2 text-right font-mono text-ink-100">{fmtMm(p.length_mm)}</td>
              <td className="py-1 px-2 text-right font-mono text-ink-400">{p.quantity ?? 1}</td>
              <td className="py-1 px-2 text-ink-500 text-[10px]">{p.grain_direction ?? '—'}</td>
              <td className="py-1 px-2 text-ink-500 font-mono text-[10px]">{p.board_id != null ? `#${p.board_id}` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SummaryBar({ result }) {
  const boards = result?.boards ?? []
  const total  = result?.total_boards ?? boards.length
  const waste  = result?.total_waste_mm ?? null
  const utilPct = result?.overall_utilisation_pct ?? null
  if (total === 0 && waste == null) return null

  return (
    <div className="flex items-center gap-4 text-[11px] px-3 py-2 border-b border-ink-800 bg-ink-950">
      {total > 0 && <span className="text-ink-400">Boards: <strong className="text-ink-200">{total}</strong></span>}
      {waste != null && <span className="text-ink-400">Waste: <strong className="text-ink-200">{fmtMm(waste)}</strong></span>}
      {utilPct != null && (
        <span className="text-ink-400 ml-auto">
          Overall util: <strong className={utilPct >= 85 ? 'text-emerald-400' : utilPct >= 60 ? 'text-yellow-400' : 'text-red-400'}>
            {fmtPct(utilPct)}
          </strong>
        </span>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export default function WoodworkingCutListPanel({ cutList, raw }) {
  const parsed = cutList ?? parseCutList(raw)
  const boards = parsed?.boards ?? []
  const pieces = parsed?.pieces ?? parsed?.required_pieces ?? []
  const stockLength = parsed?.stock_length_mm

  return (
    <div className="flex flex-col h-full bg-ink-950 text-ink-100">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-ink-800">
        <Layers size={14} className="text-kerf-400 shrink-0" />
        <span className="text-[12px] font-medium text-ink-100 truncate">
          Cut List
        </span>
        {stockLength && (
          <span className="text-[11px] text-ink-500 ml-1">
            — {fmtMm(stockLength)} stock
          </span>
        )}
      </div>

      {/* Summary bar */}
      {parsed && <SummaryBar result={parsed} />}

      {/* Content */}
      <div className="flex-1 overflow-auto flex flex-col">
        {parsed ? (
          <>
            <BoardTable boards={boards} stockLength={stockLength} />
            <PieceTable pieces={pieces} />
          </>
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-ink-600">
            <Layers size={28} className="opacity-30" />
            <p className="text-[12px]">No cut list data.</p>
            <p className="text-[11px] text-ink-700">
              Use <code className="text-kerf-500">woodworking_cut_list</code> in chat to optimise your cut plan.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
