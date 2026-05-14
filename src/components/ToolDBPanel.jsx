// ToolDBPanel — sidebar panel for managing .tool files in a project.
//
// Shows a list of all tools with a small SVG profile thumbnail, name,
// and key dimensions. Provides Add / Edit / Delete actions.
//
// Props:
//   projectId   : string
//   tools       : array of tool objects (fetched externally or passed in)
//   onAddTool   : (toolData) => void  — called when user confirms Add/Edit
//   onDeleteTool: (toolId) => void
//   readOnly    : bool (optional, default false)

import { useState, useRef } from 'react'
import { Plus, Trash2, Pencil, Wrench, X } from 'lucide-react'

// ---------------------------------------------------------------------------
// SVG tool profile thumbnails (one per type)
// ---------------------------------------------------------------------------

function ToolProfileSvg({ tool }) {
  const { type, diameter_mm, ball_radius_mm, corner_radius_mm, flute_length_mm, overall_length_mm } = tool
  const w = 40
  const h = 60
  const cx = w / 2
  const diam = diameter_mm || 6
  const r = diam / 2
  // Normalise widths to a 0..18 px range for display.
  const scale = Math.min(18 / r, 3.5)
  const halfW = r * scale
  const fullH = h - 8

  if (type === 'ball_end') {
    const br = (ball_radius_mm || r) * scale
    const flH = Math.min((flute_length_mm || diam * 4) * scale * 0.6, fullH - br * 2)
    const shankH = fullH - flH - br
    return (
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
        <rect x={cx - halfW * 0.7} y={4} width={halfW * 1.4} height={shankH} rx="2" fill="#6b7280" />
        <rect x={cx - halfW} y={4 + shankH} width={halfW * 2} height={flH} rx="1" fill="#a78bfa" />
        <ellipse cx={cx} cy={4 + shankH + flH + br * 0.5} rx={halfW} ry={br} fill="#7c3aed" />
      </svg>
    )
  }
  if (type === 'flat_end') {
    const flH = Math.min((flute_length_mm || diam * 4) * scale * 0.6, fullH - 6)
    const shankH = fullH - flH
    return (
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
        <rect x={cx - halfW * 0.7} y={4} width={halfW * 1.4} height={shankH} rx="2" fill="#6b7280" />
        <rect x={cx - halfW} y={4 + shankH} width={halfW * 2} height={flH} fill="#10b981" />
        <rect x={cx - halfW} y={4 + shankH + flH} width={halfW * 2} height={3} fill="#059669" />
      </svg>
    )
  }
  if (type === 'bull_end') {
    const cr = (corner_radius_mm || r * 0.2) * scale
    const flH = Math.min((flute_length_mm || diam * 4) * scale * 0.6, fullH - 8)
    const shankH = fullH - flH - cr
    return (
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
        <rect x={cx - halfW * 0.7} y={4} width={halfW * 1.4} height={shankH} rx="2" fill="#6b7280" />
        <rect x={cx - halfW} y={4 + shankH} width={halfW * 2} height={flH} rx="0" fill="#f59e0b" />
        <rect x={cx - halfW} y={4 + shankH + flH} width={halfW * 2} height={cr} rx={`0 0 ${cr} ${cr}`} fill="#d97706" />
      </svg>
    )
  }
  if (type === 'chamfer' || type === 'engraver') {
    const tipH = halfW * 1.5
    const shankH = fullH - tipH
    const pts = `${cx - halfW * 0.7},${4 + shankH} ${cx + halfW * 0.7},${4 + shankH} ${cx},${4 + shankH + tipH}`
    return (
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
        <rect x={cx - halfW * 0.7} y={4} width={halfW * 1.4} height={shankH} rx="2" fill="#6b7280" />
        <polygon points={pts} fill={type === 'engraver' ? '#f43f5e' : '#3b82f6'} />
      </svg>
    )
  }
  if (type === 'drill') {
    const tipH = halfW * 1.2
    const flH = Math.min((flute_length_mm || diam * 5) * scale * 0.5, fullH - tipH - 4)
    const shankH = fullH - flH - tipH
    const pts = `${cx - halfW},${4 + shankH + flH} ${cx + halfW},${4 + shankH + flH} ${cx},${4 + shankH + flH + tipH}`
    return (
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
        <rect x={cx - halfW * 0.7} y={4} width={halfW * 1.4} height={shankH} rx="2" fill="#6b7280" />
        <rect x={cx - halfW} y={4 + shankH} width={halfW * 2} height={flH} fill="#06b6d4" />
        <polygon points={pts} fill="#0891b2" />
      </svg>
    )
  }
  if (type === 'face_mill') {
    return (
      <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
        <rect x={cx - halfW * 0.5} y={4} width={halfW} height={fullH - 12} rx="2" fill="#6b7280" />
        <rect x={cx - halfW * 1.4} y={4 + fullH - 12} width={halfW * 2.8} height={12} rx="2" fill="#8b5cf6" />
      </svg>
    )
  }
  // Fallback generic
  return (
    <svg width={w} height={h} viewBox={`0 0 ${w} ${h}`}>
      <rect x={cx - halfW} y={4} width={halfW * 2} height={fullH} rx="3" fill="#4b5563" />
    </svg>
  )
}


// ---------------------------------------------------------------------------
// Required fields per type
// ---------------------------------------------------------------------------

const TYPE_FIELDS = {
  ball_end:  ['ball_radius_mm'],
  flat_end:  [],
  bull_end:  ['corner_radius_mm'],
  chamfer:   ['included_angle_deg'],
  drill:     [],
  face_mill: [],
  engraver:  ['included_angle_deg'],
}

const TOOL_TYPES = ['ball_end', 'flat_end', 'bull_end', 'chamfer', 'drill', 'face_mill', 'engraver']

const FIELD_META = {
  ball_radius_mm:      { label: 'Ball radius (mm)',        type: 'number', step: '0.001', min: '0.001' },
  corner_radius_mm:    { label: 'Corner radius (mm)',      type: 'number', step: '0.001', min: '0.001' },
  included_angle_deg:  { label: 'Included angle (°)',      type: 'number', step: '1', min: '1', max: '179' },
  diameter_mm:         { label: 'Diameter (mm)',           type: 'number', step: '0.001', min: '0.001' },
  flute_length_mm:     { label: 'Flute length (mm)',       type: 'number', step: '0.1', min: '0.1' },
  shank_diameter_mm:   { label: 'Shank diameter (mm)',     type: 'number', step: '0.001', min: '0.001' },
  overall_length_mm:   { label: 'Overall length (mm)',     type: 'number', step: '0.1', min: '0.1' },
  flute_count:         { label: 'Flute count',             type: 'integer', min: '1' },
  material:            { label: 'Material',                type: 'text' },
  spindle_rpm_min:     { label: 'Spindle RPM min',         type: 'number', step: '100', min: '1' },
  spindle_rpm_max:     { label: 'Spindle RPM max',         type: 'number', step: '100', min: '1' },
  feed_rate_mm_min:    { label: 'Feed rate (mm/min)',      type: 'number', step: '10', min: '1' },
  plunge_rate_mm_min:  { label: 'Plunge rate (mm/min)',    type: 'number', step: '10', min: '1' },
  notes:               { label: 'Notes',                   type: 'text' },
}

const OPTIONAL_FIELDS = [
  'flute_length_mm', 'shank_diameter_mm', 'overall_length_mm',
  'flute_count', 'material',
  'spindle_rpm_min', 'spindle_rpm_max',
  'feed_rate_mm_min', 'plunge_rate_mm_min',
  'notes',
]


// ---------------------------------------------------------------------------
// ToolForm — Add / Edit modal form
// ---------------------------------------------------------------------------

function ToolForm({ initial, onSubmit, onClose }) {
  const [form, setForm] = useState(() => {
    const base = {
      id: '', name: '', type: 'ball_end', diameter_mm: '',
      ball_radius_mm: '', corner_radius_mm: '', included_angle_deg: '',
      flute_length_mm: '', shank_diameter_mm: '', overall_length_mm: '',
      flute_count: '', material: '', spindle_rpm_min: '', spindle_rpm_max: '',
      feed_rate_mm_min: '', plunge_rate_mm_min: '', notes: '',
    }
    if (initial) {
      Object.keys(base).forEach((k) => {
        if (initial[k] != null) base[k] = String(initial[k])
      })
    }
    return base
  })

  const [errors, setErrors] = useState({})
  const typeFields = TYPE_FIELDS[form.type] || []

  function set(k, v) {
    setForm((f) => ({ ...f, [k]: v }))
    setErrors((e) => { const next = { ...e }; delete next[k]; return next })
  }

  function validate() {
    const errs = {}
    if (!form.id.trim()) errs.id = 'Required'
    if (!form.name.trim()) errs.name = 'Required'
    if (!form.diameter_mm || isNaN(parseFloat(form.diameter_mm)) || parseFloat(form.diameter_mm) <= 0) {
      errs.diameter_mm = 'Must be > 0'
    }
    for (const f of typeFields) {
      if (!form[f] || isNaN(parseFloat(form[f])) || parseFloat(form[f]) <= 0) {
        errs[f] = 'Required and must be > 0'
      }
    }
    // ball_radius ≤ diameter/2
    if (form.type === 'ball_end' && form.ball_radius_mm && form.diameter_mm) {
      const br = parseFloat(form.ball_radius_mm)
      const d = parseFloat(form.diameter_mm)
      if (!isNaN(br) && !isNaN(d) && br > d / 2 + 1e-9) {
        errs.ball_radius_mm = `Must be ≤ diameter/2 (${(d / 2).toFixed(3)})`
      }
    }
    return errs
  }

  function handleSubmit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    const out = { id: form.id.trim(), name: form.name.trim(), type: form.type }
    out.diameter_mm = parseFloat(form.diameter_mm)
    for (const f of typeFields) {
      out[f] = parseFloat(form[f])
    }
    for (const f of OPTIONAL_FIELDS) {
      if (form[f] !== '' && form[f] != null) {
        const meta = FIELD_META[f]
        if (meta?.type === 'integer') out[f] = parseInt(form[f], 10)
        else if (meta?.type === 'number') out[f] = parseFloat(form[f])
        else out[f] = form[f]
      }
    }
    onSubmit(out)
  }

  function Field({ fieldKey, required }) {
    const meta = FIELD_META[fieldKey] || { label: fieldKey, type: 'text' }
    const err = errors[fieldKey]
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        <label style={{ fontSize: 11, color: '#9ca3af', display: 'flex', gap: 4, alignItems: 'center' }}>
          {meta.label}
          {required && <span style={{ color: '#f87171' }}>*</span>}
        </label>
        <input
          type={meta.type === 'integer' ? 'number' : meta.type === 'number' ? 'number' : 'text'}
          value={form[fieldKey]}
          onChange={(e) => set(fieldKey, e.target.value)}
          step={meta.step}
          min={meta.min}
          max={meta.max}
          style={{
            background: '#1f2937', border: `1px solid ${err ? '#f87171' : '#374151'}`,
            borderRadius: 4, color: '#e5e7eb', padding: '3px 8px', fontSize: 12, outline: 'none',
          }}
        />
        {err && <span style={{ fontSize: 10, color: '#f87171' }}>{err}</span>}
      </div>
    )
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ background: '#111827', border: '1px solid #374151', borderRadius: 10, padding: 24, width: 420, maxHeight: '90vh', overflowY: 'auto', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: 13, color: '#e5e7eb' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
          <span style={{ fontWeight: 700, fontSize: 14 }}>{initial ? 'Edit Tool' : 'Add Tool'}</span>
          <button type="button" onClick={onClose} style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer', padding: 2 }}>
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <label style={{ fontSize: 11, color: '#9ca3af' }}>Tool ID <span style={{ color: '#f87171' }}>*</span></label>
              <input
                value={form.id}
                onChange={(e) => set('id', e.target.value)}
                placeholder="T1"
                style={{ background: '#1f2937', border: `1px solid ${errors.id ? '#f87171' : '#374151'}`, borderRadius: 4, color: '#e5e7eb', padding: '3px 8px', fontSize: 12, outline: 'none' }}
              />
              {errors.id && <span style={{ fontSize: 10, color: '#f87171' }}>{errors.id}</span>}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <label style={{ fontSize: 11, color: '#9ca3af' }}>Type <span style={{ color: '#f87171' }}>*</span></label>
              <select
                value={form.type}
                onChange={(e) => set('type', e.target.value)}
                style={{ background: '#1f2937', border: '1px solid #374151', borderRadius: 4, color: '#e5e7eb', padding: '3px 8px', fontSize: 12, outline: 'none' }}
              >
                {TOOL_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            <label style={{ fontSize: 11, color: '#9ca3af' }}>Name <span style={{ color: '#f87171' }}>*</span></label>
            <input
              value={form.name}
              onChange={(e) => set('name', e.target.value)}
              placeholder={`${form.diameter_mm || '6'}mm ${form.type}`}
              style={{ background: '#1f2937', border: `1px solid ${errors.name ? '#f87171' : '#374151'}`, borderRadius: 4, color: '#e5e7eb', padding: '3px 8px', fontSize: 12, outline: 'none' }}
            />
            {errors.name && <span style={{ fontSize: 10, color: '#f87171' }}>{errors.name}</span>}
          </div>

          <Field fieldKey="diameter_mm" required />

          {typeFields.map(f => <Field key={f} fieldKey={f} required />)}

          <div style={{ borderTop: '1px solid #1f2937', paddingTop: 8, marginTop: 4 }}>
            <div style={{ fontSize: 11, color: '#6b7280', marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Optional</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {OPTIONAL_FIELDS.filter(f => f !== 'notes').map(f => <Field key={f} fieldKey={f} />)}
            </div>
            <div style={{ marginTop: 8 }}>
              <Field fieldKey="notes" />
            </div>
          </div>

          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
            <button type="button" onClick={onClose} style={{ padding: '6px 14px', background: '#1f2937', border: '1px solid #374151', borderRadius: 5, color: '#9ca3af', fontSize: 12, cursor: 'pointer' }}>
              Cancel
            </button>
            <button type="submit" style={{ padding: '6px 14px', background: '#4c1d95', border: 'none', borderRadius: 5, color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
              {initial ? 'Save' : 'Add Tool'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
// ToolCard
// ---------------------------------------------------------------------------

function ToolCard({ tool, onEdit, onDelete }) {
  const [hovered, setHovered] = useState(false)

  function fmtNum(v) {
    if (v == null) return null
    return Number(v).toFixed(3).replace(/\.?0+$/, '')
  }

  const dims = []
  if (tool.diameter_mm != null) dims.push(`ø${fmtNum(tool.diameter_mm)} mm`)
  if (tool.ball_radius_mm != null) dims.push(`r=${fmtNum(tool.ball_radius_mm)} mm`)
  if (tool.corner_radius_mm != null) dims.push(`cr=${fmtNum(tool.corner_radius_mm)} mm`)
  if (tool.included_angle_deg != null) dims.push(`${fmtNum(tool.included_angle_deg)}°`)
  if (tool.flute_count) dims.push(`${tool.flute_count}-fl`)

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: 'flex', alignItems: 'flex-start', gap: 10,
        padding: '8px 10px', borderRadius: 6,
        border: `1px solid ${hovered ? '#4c1d95' : '#1f2937'}`,
        background: hovered ? '#0f0a1a' : '#0d1117',
        transition: 'border-color 0.15s, background 0.15s',
      }}
    >
      <div style={{ flexShrink: 0, opacity: 0.9 }}>
        <ToolProfileSvg tool={tool} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 11, fontWeight: 700, color: '#c4b5fd', fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>{tool.id}</span>
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              type="button"
              onClick={() => onEdit(tool)}
              title="Edit tool"
              style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', padding: 2, display: 'flex', alignItems: 'center' }}
            >
              <Pencil size={12} />
            </button>
            <button
              type="button"
              onClick={() => onDelete(tool.id)}
              title="Delete tool"
              style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer', padding: 2, display: 'flex', alignItems: 'center' }}
            >
              <Trash2 size={12} />
            </button>
          </div>
        </div>
        <div style={{ fontSize: 12, color: '#f3f4f6', marginTop: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {tool.name}
        </div>
        <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2, fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace' }}>
          {dims.join(' · ')}
        </div>
        {tool.type && (
          <span style={{ fontSize: 10, color: '#6b7280', marginTop: 3, display: 'inline-block', padding: '1px 5px', background: '#1f2937', borderRadius: 3 }}>
            {tool.type.replace(/_/g, ' ')}
          </span>
        )}
        {hovered && tool.feed_rate_mm_min != null && (
          <div style={{ marginTop: 4, fontSize: 10, color: '#6b7280' }}>
            feed {tool.feed_rate_mm_min} mm/min
            {tool.spindle_rpm_min != null && ` · ${tool.spindle_rpm_min} RPM`}
          </div>
        )}
      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
// ToolPicker — compact dropdown for CAM job inspector
// ---------------------------------------------------------------------------

export function ToolPicker({ tools = [], value, onChange, disabled }) {
  const [hoverTool, setHoverTool] = useState(null)

  const selected = tools.find((t) => t.id === value)

  return (
    <div style={{ position: 'relative', display: 'inline-block', width: '100%' }}>
      <select
        value={value || ''}
        onChange={(e) => onChange(e.target.value || null)}
        disabled={disabled}
        style={{
          width: '100%', background: '#1f2937', border: '1px solid #374151',
          borderRadius: 4, color: '#e5e7eb', padding: '3px 6px', fontSize: 12, outline: 'none',
        }}
        title={selected ? `${selected.id} — ${selected.name}` : 'Select tool'}
      >
        <option value="">— manual params —</option>
        {tools.map((t) => (
          <option key={t.id} value={t.id}>
            {t.id} · {t.name}
          </option>
        ))}
      </select>
    </div>
  )
}


// ---------------------------------------------------------------------------
// ToolDBPanel (main export)
// ---------------------------------------------------------------------------

export default function ToolDBPanel({ tools = [], onAddTool, onDeleteTool, readOnly = false }) {
  const [modal, setModal] = useState(null)  // null | { mode: 'add' | 'edit', tool?: object }

  function handleAdd() {
    setModal({ mode: 'add' })
  }

  function handleEdit(tool) {
    setModal({ mode: 'edit', tool })
  }

  function handleDelete(toolId) {
    if (window.confirm(`Delete tool ${toolId}?`)) {
      onDeleteTool?.(toolId)
    }
  }

  function handleSubmit(data) {
    onAddTool?.(data)
    setModal(null)
  }

  return (
    <div
      style={{
        fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        fontSize: 13, color: '#e5e7eb',
        display: 'flex', flexDirection: 'column', gap: 10,
        padding: 12,
      }}
      data-testid="tool-db-panel"
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #1f2937', paddingBottom: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <Wrench size={13} style={{ color: '#a78bfa' }} />
          <span style={{ fontWeight: 600, fontSize: 13, color: '#f3f4f6' }}>Tool Library</span>
        </div>
        {!readOnly && (
          <button
            type="button"
            onClick={handleAdd}
            style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '4px 10px', background: '#4c1d95', border: 'none', borderRadius: 5, color: '#fff', fontSize: 11, fontWeight: 600, cursor: 'pointer' }}
          >
            <Plus size={11} />
            Add tool
          </button>
        )}
      </div>

      {/* Tool list */}
      {tools.length === 0 ? (
        <div style={{ color: '#6b7280', fontSize: 12, padding: '12px 0', textAlign: 'center' }}>
          No tools yet.{!readOnly && ' Click "Add tool" to create one.'}
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {tools.map((tool) => (
            <ToolCard
              key={tool.id}
              tool={tool}
              onEdit={readOnly ? () => {} : handleEdit}
              onDelete={readOnly ? () => {} : handleDelete}
            />
          ))}
        </div>
      )}

      {/* Add/Edit modal */}
      {modal && (
        <ToolForm
          initial={modal.mode === 'edit' ? modal.tool : null}
          onSubmit={handleSubmit}
          onClose={() => setModal(null)}
        />
      )}
    </div>
  )
}
