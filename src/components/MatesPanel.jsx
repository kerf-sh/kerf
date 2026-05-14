// MatesPanel — collapsible panel for 3D assembly mate constraints.
//
// Props:
//   mates         — array of mate objects
//   components    — array of component rows (for display reference)
//   onChangeMates — called when mates list changes
//   onToast       — optional (mate solve errors are shown inline, not as toasts)
//
// Each mate: { id, type, a:{component_id, feature, feature_id}, b:{...}, value?, unit? }

import { useState } from 'react'
import { ChevronDown, ChevronRight, Link2, Plus, Trash2, Loader2 } from 'lucide-react'
import { addMate, removeMate } from '../lib/assembly.js'

const MATE_TYPES = ['coincident', 'concentric', 'parallel', 'perpendicular', 'distance', 'angle', 'tangent']
const FEATURE_TYPES = ['face', 'edge', 'vertex', 'axis']
const DIMENSIONAL = new Set(['distance', 'angle'])

const EMPTY_FORM = {
  type: 'coincident',
  a_component_id: '',
  a_feature: 'face',
  a_feature_id: '',
  b_component_id: '',
  b_feature: 'face',
  b_feature_id: '',
  value: '',
  unit: 'mm',
}

export default function MatesPanel({ mates = [], components = [], onChangeMates, onToast, projectId, fileId }) {
  const [open, setOpen] = useState(false)
  const [adding, setAdding] = useState(false)
  const [form, setForm] = useState(EMPTY_FORM)
  const [solving, setSolving] = useState(false)
  const [solveResult, setSolveResult] = useState(null)
  const [solveError, setSolveError] = useState(null)

  function handleDelete(mateId) {
    const newMates = removeMate(mates, mateId)
    onChangeMates(newMates)
  }

  function handleAdd() {
    if (!form.a_component_id || !form.a_feature_id || !form.b_component_id || !form.b_feature_id) return
    const mate = {
      type: form.type,
      a: { component_id: form.a_component_id, feature: form.a_feature, feature_id: form.a_feature_id },
      b: { component_id: form.b_component_id, feature: form.b_feature, feature_id: form.b_feature_id },
    }
    if (DIMENSIONAL.has(form.type) && form.value !== '') {
      mate.value = parseFloat(form.value) || 0
      mate.unit = form.unit
    }
    const newMates = addMate(mates, mate)
    onChangeMates(newMates)
    setAdding(false)
    setForm(EMPTY_FORM)
    // Trigger solve
    triggerSolve()
  }

  async function triggerSolve() {
    if (!projectId || !fileId) return
    setSolving(true)
    setSolveError(null)
    try {
      const resp = await fetch(`/api/projects/${projectId}/files/${fileId}/solve-mates`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
        credentials: 'include',
      })
      if (resp.ok) {
        const data = await resp.json()
        setSolveResult(data)
      } else if (resp.status !== 404) {
        setSolveError(`Solve failed (${resp.status})`)
      }
    } catch {
      // Network error or pyworker not running — silent
    } finally {
      setSolving(false)
    }
  }

  const isDimensional = DIMENSIONAL.has(form.type)

  return (
    <div className="border-t border-ink-800">
      {/* Header */}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-ink-800/40 transition-colors"
      >
        {open ? <ChevronDown size={12} className="text-ink-400 shrink-0" /> : <ChevronRight size={12} className="text-ink-400 shrink-0" />}
        <Link2 size={12} className="text-kerf-300 shrink-0" />
        <span className="text-[11px] font-medium text-ink-200 flex-1">Mates</span>
        <span className="text-[10px] text-ink-500 tabular-nums">{mates.length}</span>
        {solving && <Loader2 size={10} className="text-kerf-300 animate-spin shrink-0" />}
      </button>

      {open && (
        <div className="px-3 pb-3 space-y-1.5">
          {/* Mate list */}
          {mates.length === 0 && !adding && (
            <div className="text-[11px] text-ink-500 italic py-1">No mates — add one to constrain components.</div>
          )}
          {mates.map((m) => (
            <div key={m.id} className="flex items-center gap-2 bg-ink-900 rounded px-2 py-1.5 border border-ink-800">
              <span className="text-[10px] uppercase tracking-wider text-kerf-300 font-medium w-20 shrink-0">{m.type}</span>
              <span className="text-[10px] text-ink-400 flex-1 truncate">
                {m.a?.component_id || '?'}<span className="text-ink-600">.</span>{m.a?.feature_id || '?'}
                <span className="text-ink-600 mx-1">→</span>
                {m.b?.component_id || '?'}<span className="text-ink-600">.</span>{m.b?.feature_id || '?'}
                {m.value != null && <span className="ml-1 text-ink-500">= {m.value} {m.unit || ''}</span>}
              </span>
              <button
                type="button"
                onClick={() => handleDelete(m.id)}
                className="text-ink-600 hover:text-red-400 transition-colors shrink-0"
                title="Delete mate"
              >
                <Trash2 size={11} />
              </button>
            </div>
          ))}

          {/* Solve result summary */}
          {solveResult && (
            <div className={`text-[10px] rounded px-2 py-1 border ${solveResult.solved ? 'bg-green-950/40 border-green-800/50 text-green-300' : 'bg-amber-950/40 border-amber-800/50 text-amber-300'}`}>
              {solveResult.solved
                ? `Solved in ${solveResult.iterations} iter.`
                : `Not converged (${solveResult.error || 'check mates'})`}
            </div>
          )}
          {solveError && (
            <div className="text-[10px] text-red-400 px-1">{solveError}</div>
          )}

          {/* Add mate form */}
          {adding ? (
            <div className="border border-ink-700 rounded p-2 space-y-2 bg-ink-900/60">
              <div className="flex gap-2 items-center">
                <label className="text-[10px] text-ink-400 w-8 shrink-0">Type</label>
                <select
                  value={form.type}
                  onChange={(e) => setForm((f) => ({ ...f, type: e.target.value }))}
                  className="flex-1 bg-ink-800 border border-ink-700 rounded px-1.5 py-0.5 text-[11px] text-ink-100"
                >
                  {MATE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <RefRow label="A" prefix="a" form={form} setForm={setForm} />
              <RefRow label="B" prefix="b" form={form} setForm={setForm} />
              {isDimensional && (
                <div className="flex gap-2 items-center">
                  <label className="text-[10px] text-ink-400 w-8 shrink-0">Val</label>
                  <input
                    type="number"
                    value={form.value}
                    onChange={(e) => setForm((f) => ({ ...f, value: e.target.value }))}
                    placeholder="0"
                    className="flex-1 bg-ink-800 border border-ink-700 rounded px-1.5 py-0.5 text-[11px] text-ink-100"
                  />
                  <select
                    value={form.unit}
                    onChange={(e) => setForm((f) => ({ ...f, unit: e.target.value }))}
                    className="w-16 bg-ink-800 border border-ink-700 rounded px-1 py-0.5 text-[11px] text-ink-100"
                  >
                    <option value="mm">mm</option>
                    <option value="inch">in</option>
                    <option value="deg">deg</option>
                    <option value="rad">rad</option>
                  </select>
                </div>
              )}
              <div className="flex gap-1.5 justify-end">
                <button
                  type="button"
                  onClick={() => { setAdding(false); setForm(EMPTY_FORM) }}
                  className="px-2 py-0.5 rounded text-[11px] text-ink-400 hover:text-ink-200"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleAdd}
                  disabled={!form.a_component_id || !form.a_feature_id || !form.b_component_id || !form.b_feature_id}
                  className="px-2 py-0.5 rounded text-[11px] bg-kerf-300 text-ink-950 font-medium hover:bg-kerf-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Add
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setAdding(true)}
              className="flex items-center gap-1 text-[11px] text-ink-400 hover:text-kerf-300 transition-colors py-0.5"
            >
              <Plus size={11} />
              Add mate
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function RefRow({ label, prefix, form, setForm }) {
  return (
    <div className="flex gap-1 items-start">
      <span className="text-[10px] text-ink-400 w-8 shrink-0 pt-1">{label}</span>
      <div className="flex-1 grid grid-cols-3 gap-1">
        <input
          value={form[`${prefix}_component_id`]}
          onChange={(e) => setForm((f) => ({ ...f, [`${prefix}_component_id`]: e.target.value }))}
          placeholder="comp-id"
          className="bg-ink-800 border border-ink-700 rounded px-1.5 py-0.5 text-[11px] text-ink-100 placeholder-ink-600"
        />
        <select
          value={form[`${prefix}_feature`]}
          onChange={(e) => setForm((f) => ({ ...f, [`${prefix}_feature`]: e.target.value }))}
          className="bg-ink-800 border border-ink-700 rounded px-1 py-0.5 text-[11px] text-ink-100"
        >
          {FEATURE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <input
          value={form[`${prefix}_feature_id`]}
          onChange={(e) => setForm((f) => ({ ...f, [`${prefix}_feature_id`]: e.target.value }))}
          placeholder="face-id"
          className="bg-ink-800 border border-ink-700 rounded px-1.5 py-0.5 text-[11px] text-ink-100 placeholder-ink-600"
        />
      </div>
    </div>
  )
}
