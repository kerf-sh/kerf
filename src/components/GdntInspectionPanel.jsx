// GdntInspectionPanel — read-only panel that renders a GD&T inspection report.
//
// Accepts the JSON payload returned by the `gdnt_build_report` LLM tool
// (kerf-gdnt package). Renders a table of inspection rows with pass/fail
// status per feature-control-frame. When no data is present it shows an
// empty-state prompt.
//
// Props:
//   report  — parsed inspection report object (from file content JSON) or null
//   raw     — raw string content of the .gdnt file (for parse fallback)

import { CheckCircle, XCircle, AlertTriangle, Shield } from 'lucide-react'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseReport(raw) {
  if (!raw || typeof raw !== 'string' || !raw.trim()) return null
  try {
    const doc = JSON.parse(raw)
    // Accept either a top-level report object or a direct rows array.
    if (Array.isArray(doc)) return { rows: doc }
    if (doc && typeof doc === 'object') return doc
  } catch (_) {
    return null
  }
  return null
}

function PassBadge({ pass }) {
  if (pass === true) {
    return (
      <span className="inline-flex items-center gap-1 text-emerald-400 font-medium text-[11px]">
        <CheckCircle size={11} />
        PASS
      </span>
    )
  }
  if (pass === false) {
    return (
      <span className="inline-flex items-center gap-1 text-red-400 font-medium text-[11px]">
        <XCircle size={11} />
        FAIL
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1 text-ink-500 font-medium text-[11px]">
      <AlertTriangle size={11} />
      N/A
    </span>
  )
}

function FcfChip({ fcf }) {
  if (!fcf) return <span className="text-ink-500 italic">—</span>
  const symbol = fcf.unicode || fcf.symbol_code || '?'
  const zone   = fcf.tolerance_zone ?? ''
  const mods   = (fcf.modifiers || []).join(' ')
  const datums = (fcf.datum_references || []).map((d) => d.datum_label || d).join(' | ')
  return (
    <span className="inline-flex items-center gap-1 font-mono text-kerf-300 text-[11px]">
      <span>{symbol}</span>
      {zone ? <span className="text-ink-200">{zone}</span> : null}
      {mods ? <span className="text-ink-500 text-[10px]">{mods}</span> : null}
      {datums ? <span className="text-ink-400 text-[10px]">| {datums}</span> : null}
    </span>
  )
}

function InspectionTable({ rows }) {
  if (!rows || rows.length === 0) {
    return (
      <div className="text-[11px] text-ink-500 italic py-4 text-center">
        No inspection rows — run <code className="text-kerf-300">gdnt_build_report</code> to generate results.
      </div>
    )
  }

  return (
    <div className="overflow-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-ink-800 text-ink-500 uppercase tracking-wider text-[10px]">
            <th className="text-left py-1.5 px-2 font-medium">Feature</th>
            <th className="text-left py-1.5 px-2 font-medium">FCF</th>
            <th className="text-right py-1.5 px-2 font-medium">Measured</th>
            <th className="text-right py-1.5 px-2 font-medium">Tolerance</th>
            <th className="text-center py-1.5 px-2 font-medium">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const measured = row.measured_value ?? row.actual
            const tol      = row.tolerance_value ?? row.tolerance
            const pass     = row.pass
            return (
              <tr key={row.feature_id || i} className="border-b border-ink-800/50 hover:bg-ink-900/40">
                <td className="py-1.5 px-2 font-mono text-ink-200">{row.feature_id || row.feature || `feat-${i + 1}`}</td>
                <td className="py-1.5 px-2"><FcfChip fcf={row.fcf} /></td>
                <td className="py-1.5 px-2 text-right font-mono text-ink-100">
                  {measured != null ? Number(measured).toFixed(4) : '—'}
                </td>
                <td className="py-1.5 px-2 text-right font-mono text-ink-400">
                  {tol != null ? Number(tol).toFixed(4) : '—'}
                </td>
                <td className="py-1.5 px-2 text-center"><PassBadge pass={pass} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function SummaryBar({ rows }) {
  if (!rows || rows.length === 0) return null
  const passed  = rows.filter((r) => r.pass === true).length
  const failed  = rows.filter((r) => r.pass === false).length
  const unknown = rows.length - passed - failed
  return (
    <div className="flex items-center gap-4 text-[11px] px-3 py-2 border-b border-ink-800 bg-ink-950">
      <span className="text-ink-500">Total: <strong className="text-ink-200">{rows.length}</strong></span>
      {passed  > 0 && <span className="text-emerald-400">Passed: <strong>{passed}</strong></span>}
      {failed  > 0 && <span className="text-red-400">Failed: <strong>{failed}</strong></span>}
      {unknown > 0 && <span className="text-ink-500">N/A: <strong>{unknown}</strong></span>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export default function GdntInspectionPanel({ report, raw }) {
  const parsed = report ?? parseReport(raw)
  const rows   = parsed?.rows ?? parsed?.inspection_rows ?? []
  const date   = parsed?.date ?? parsed?.report_date ?? ''
  const part   = parsed?.part_name ?? parsed?.part ?? ''

  return (
    <div className="flex flex-col h-full bg-ink-950 text-ink-100">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-ink-800">
        <Shield size={14} className="text-kerf-400 shrink-0" />
        <span className="text-[12px] font-medium text-ink-100 truncate">
          GD&amp;T Inspection Report
        </span>
        {part && <span className="text-[11px] text-ink-500 truncate ml-1">— {part}</span>}
        {date && <span className="text-[10px] text-ink-600 ml-auto shrink-0">{date}</span>}
      </div>

      {/* Summary bar */}
      <SummaryBar rows={rows} />

      {/* Table */}
      <div className="flex-1 overflow-auto">
        {parsed ? (
          <InspectionTable rows={rows} />
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-ink-600">
            <Shield size={28} className="opacity-30" />
            <p className="text-[12px]">No inspection data.</p>
            <p className="text-[11px] text-ink-700">
              Use <code className="text-kerf-500">gdnt_build_report</code> in chat to generate a report.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
