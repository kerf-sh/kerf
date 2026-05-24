// MotionResultsPanel — read-only panel for motion / MBD simulation results.
//
// Accepts the JSON payload returned by the `simulate_motion` LLM tool
// (kerf-motion package). Renders body trajectories, final positions, and
// per-body energy summary. Also handles solve_ik / compute_workspace outputs.
//
// Props:
//   result  — parsed simulation result object or null
//   raw     — raw string content (for parse fallback)

import { Activity, AlertTriangle } from 'lucide-react'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseResult(raw) {
  if (!raw || typeof raw !== 'string' || !raw.trim()) return null
  try {
    const doc = JSON.parse(raw)
    if (doc && typeof doc === 'object') return doc
  } catch (_) {}
  return null
}

function fmtNum(v, decimals = 4) {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  return Number(v).toFixed(decimals)
}

function Vec3({ v }) {
  if (!Array.isArray(v) || v.length < 3) return <span className="text-ink-500">—</span>
  return (
    <span className="font-mono text-[10px] text-ink-200">
      ({fmtNum(v[0], 2)}, {fmtNum(v[1], 2)}, {fmtNum(v[2], 2)})
    </span>
  )
}

// ── Simulation trajectory table ───────────────────────────────────────────

function TrajectoryTable({ bodies, trajectories }) {
  if (!Array.isArray(trajectories) || trajectories.length === 0) {
    return (
      <div className="text-[11px] text-ink-500 italic py-4 text-center">
        No trajectory data — run <code className="text-kerf-300">simulate_motion</code> to generate results.
      </div>
    )
  }

  return (
    <div className="overflow-auto">
      <table className="w-full text-[11px]">
        <thead>
          <tr className="border-b border-ink-800 text-ink-500 uppercase tracking-wider text-[10px]">
            <th className="text-left py-1.5 px-2 font-medium">Body</th>
            <th className="text-right py-1.5 px-2 font-medium">Steps</th>
            <th className="text-left py-1.5 px-2 font-medium">Final pos (x, y, z)</th>
            <th className="text-left py-1.5 px-2 font-medium">Final vel (x, y, z)</th>
          </tr>
        </thead>
        <tbody>
          {trajectories.map((traj, i) => {
            const bodyName  = bodies?.[i]?.name ?? `Body ${i}`
            const steps     = Array.isArray(traj.positions) ? traj.positions.length : '—'
            const lastPos   = Array.isArray(traj.positions) && traj.positions.length > 0
              ? traj.positions[traj.positions.length - 1] : null
            const lastVel   = Array.isArray(traj.velocities) && traj.velocities.length > 0
              ? traj.velocities[traj.velocities.length - 1] : null
            return (
              <tr key={i} className="border-b border-ink-800/50 hover:bg-ink-900/40">
                <td className="py-1.5 px-2 text-ink-200">{bodyName}</td>
                <td className="py-1.5 px-2 text-right font-mono text-ink-400">{steps}</td>
                <td className="py-1.5 px-2"><Vec3 v={lastPos} /></td>
                <td className="py-1.5 px-2"><Vec3 v={lastVel} /></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

// ── IK result panel ───────────────────────────────────────────────────────

function IkResultPanel({ result }) {
  const angles = result?.joint_angles_rad ?? result?.joint_angles ?? []
  const reachable = result?.reachable
  const target = result?.target

  return (
    <div className="px-3 py-2 text-[11px]">
      <div className="mb-2 flex items-center gap-2">
        <span className="text-ink-500 text-[10px] uppercase tracking-wider">IK result</span>
        {reachable != null && (
          <span className={`text-[10px] font-medium ${reachable ? 'text-emerald-400' : 'text-red-400'}`}>
            {reachable ? 'Reachable' : 'Unreachable'}
          </span>
        )}
      </div>
      {target && (
        <div className="mb-1 text-ink-400">
          Target: <span className="text-ink-200"><Vec3 v={Array.isArray(target) ? target : null} /></span>
        </div>
      )}
      {angles.length > 0 && (
        <div>
          <div className="text-ink-500 text-[10px] mb-1">Joint angles (rad):</div>
          <div className="flex flex-wrap gap-1.5">
            {angles.map((a, i) => (
              <span key={i} className="font-mono text-kerf-300 text-[11px] bg-ink-900 px-1.5 py-0.5 rounded">
                J{i + 1}={fmtNum(a, 4)}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Workspace cloud panel ─────────────────────────────────────────────────

function WorkspacePanel({ result }) {
  const cloud = result?.workspace_cloud ?? result?.points ?? []
  const count = Array.isArray(cloud) ? cloud.length : 0

  return (
    <div className="px-3 py-2 text-[11px]">
      <div className="mb-2 text-ink-500 text-[10px] uppercase tracking-wider">Workspace cloud</div>
      <div className="text-ink-300 mb-1">
        Sampled points: <strong className="text-ink-100">{count}</strong>
      </div>
      {count > 0 && (
        <div className="text-ink-500 text-[10px]">
          (Use 3D viewport to visualise. Point cloud returned as JSON.)
        </div>
      )}
    </div>
  )
}

// ── Dispatcher ────────────────────────────────────────────────────────────

function ResultBody({ parsed }) {
  if (!parsed) return null

  // Distinguish result types by shape
  if (parsed.trajectories) {
    return (
      <>
        <div className="px-3 py-1.5 text-[10px] text-ink-500 uppercase tracking-wider font-medium border-b border-ink-800">
          Simulation trajectories
          {parsed.t_end != null && (
            <span className="ml-2 text-ink-600">t={fmtNum(parsed.t_end, 2)} s, dt={fmtNum(parsed.dt, 4)} s</span>
          )}
        </div>
        <TrajectoryTable bodies={parsed.bodies} trajectories={parsed.trajectories} />
      </>
    )
  }
  if (parsed.joint_angles_rad != null || parsed.joint_angles != null) {
    return <IkResultPanel result={parsed} />
  }
  if (parsed.workspace_cloud != null || parsed.points != null) {
    return <WorkspacePanel result={parsed} />
  }
  // Fallback: render raw JSON summary
  return (
    <div className="px-3 py-2 text-[11px] text-ink-400 font-mono whitespace-pre-wrap break-all">
      {JSON.stringify(parsed, null, 2).slice(0, 2000)}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export default function MotionResultsPanel({ result, raw }) {
  const parsed = result ?? parseResult(raw)

  return (
    <div className="flex flex-col h-full bg-ink-950 text-ink-100">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-ink-800">
        <Activity size={14} className="text-kerf-400 shrink-0" />
        <span className="text-[12px] font-medium text-ink-100 truncate">
          Motion / MBD Results
        </span>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {parsed ? (
          <ResultBody parsed={parsed} />
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-ink-600">
            <Activity size={28} className="opacity-30" />
            <p className="text-[12px]">No simulation results.</p>
            <p className="text-[11px] text-ink-700 text-center px-4">
              Use <code className="text-kerf-500">simulate_motion</code>,{' '}
              <code className="text-kerf-500">solve_ik</code>, or{' '}
              <code className="text-kerf-500">compute_workspace</code> in chat.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}
