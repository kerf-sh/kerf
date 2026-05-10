// MaterialEditor — full-bleed editor for `.material` JSON files.
//
// File shape (mirrors src/lib/material.js + backend/internal/llm/docs/material.md):
//
//   { version: 1, name: 'AISI 1018 Steel', category: 'metal/steel/carbon',
//     common_names: ['mild steel'], color_hex: '#7d8088',
//     mechanical: { E_GPa, G_GPa, nu, yield_MPa, ultimate_MPa, elongation_pct },
//     thermal:    { alpha_per_K, k_W_mK, cp_J_kgK, T_min_C, T_max_C },
//     physical:   { rho_kg_m3 },
//     callout: 'AISI 1018', notes: '…' }
//
// Edits flow through `useWorkspace.editContent(json)` so the existing
// autosave loop persists them and Cmd+Z works without extra wiring —
// same pattern EquationsEditor uses.

import { useEffect, useMemo, useState } from 'react'
import { Atom, AlertTriangle } from 'lucide-react'
import { useWorkspace } from '../store/workspace.js'
import {
  parseMaterial, serializeMaterial, MATERIAL_FIELD_META,
} from '../lib/material.js'

export default function MaterialEditor() {
  const currentFile = useWorkspace((s) => s.currentFile)
  const currentFileContent = useWorkspace((s) => s.currentFileContent)
  const editContent = useWorkspace((s) => s.editContent)

  // Local copy of the parsed doc. The store's `currentFileContent` is the
  // source of truth; we re-parse on external changes (revision restore /
  // LLM tool edits) but otherwise let the user type freely against the
  // local copy and only commit serialized JSON to the store.
  const [doc, setDoc] = useState(() => parseMaterial(currentFileContent || ''))

  useEffect(() => {
    setDoc(parseMaterial(currentFileContent || ''))
  }, [currentFileContent])

  // Detect a top-level JSON parse failure on the original content so the
  // user sees something better than silently-empty fields.
  const parseError = useMemo(() => {
    if (!currentFileContent) return null
    try { JSON.parse(currentFileContent); return null }
    catch (e) { return e?.message || 'Invalid JSON' }
  }, [currentFileContent])

  function commit(next) {
    setDoc(next)
    if (typeof editContent === 'function') {
      editContent(serializeMaterial(next))
    }
  }

  function setTopField(key, value) {
    commit({ ...doc, [key]: value })
  }
  function setGroupField(group, key, value) {
    commit({ ...doc, [group]: { ...(doc[group] || {}), [key]: value } })
  }

  return (
    <div className="h-full flex flex-col bg-ink-950 text-ink-100 min-h-0">
      <Header file={currentFile} doc={doc} />

      {parseError && (
        <div className="px-4 py-2 bg-red-950/40 border-b border-red-900/60 text-xs text-red-300 flex items-center gap-2">
          <AlertTriangle size={12} />
          <span>{parseError}</span>
        </div>
      )}

      <div className="flex-1 min-h-0 overflow-auto">
        <div className="max-w-3xl mx-auto px-6 py-5 space-y-6">
          {/* Top row: name + category breadcrumb + callout */}
          <section className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Field label="Name" required>
              <Input
                value={doc.name || ''}
                onChange={(v) => setTopField('name', v)}
                placeholder="AISI 1018 Steel"
              />
            </Field>
            <Field label="Drawing callout">
              <Input
                value={doc.callout || ''}
                onChange={(v) => setTopField('callout', v)}
                placeholder="AISI 1018"
                mono
              />
            </Field>
            <Field label="Category">
              <Input
                value={doc.category || ''}
                onChange={(v) => setTopField('category', v)}
                placeholder="metal/steel/carbon"
                mono
              />
            </Field>
            <Field label="Common names (comma-separated)">
              <Input
                value={(doc.common_names || []).join(', ')}
                onChange={(v) => setTopField(
                  'common_names',
                  v.split(',').map((s) => s.trim()).filter(Boolean),
                )}
                placeholder="mild steel, low-carbon steel"
              />
            </Field>
            <Field label="Color (hex)">
              <ColorRow
                value={doc.color_hex || ''}
                onChange={(v) => setTopField('color_hex', v)}
              />
            </Field>
          </section>

          {/* Mechanical */}
          <NumericSection
            title="Mechanical"
            fields={MATERIAL_FIELD_META.mechanical}
            values={doc.mechanical || {}}
            onChange={(k, v) => setGroupField('mechanical', k, v)}
          />

          {/* Thermal */}
          <NumericSection
            title="Thermal"
            fields={MATERIAL_FIELD_META.thermal}
            values={doc.thermal || {}}
            onChange={(k, v) => setGroupField('thermal', k, v)}
          />

          {/* Physical */}
          <NumericSection
            title="Physical"
            fields={MATERIAL_FIELD_META.physical}
            values={doc.physical || {}}
            onChange={(k, v) => setGroupField('physical', k, v)}
          />

          {/* Notes */}
          <section>
            <SectionHeading>Notes</SectionHeading>
            <Textarea
              value={doc.notes || ''}
              onChange={(v) => setTopField('notes', v)}
              placeholder="Source / heat treatment / vendor notes. Cite a handbook or MatWeb URL when possible."
              rows={5}
            />
          </section>
        </div>
      </div>
    </div>
  )
}

// -- Header --------------------------------------------------------------

function Header({ file, doc }) {
  return (
    <div className="flex items-center justify-between gap-3 px-4 py-2.5 border-b border-ink-800 bg-ink-900/40 flex-shrink-0">
      <div className="flex items-center gap-2 min-w-0">
        <Atom size={14} className="text-kerf-300 shrink-0" />
        <span className="text-xs font-semibold uppercase tracking-wider text-ink-300">
          Material
        </span>
        <span className="text-[11px] text-ink-500 truncate">
          {doc.name || file?.name || <span className="italic">unnamed</span>}
        </span>
        {doc.callout && (
          <span className="text-[10px] text-ink-500 font-mono">· {doc.callout}</span>
        )}
      </div>
      {doc.color_hex && (
        <span
          className="w-4 h-4 rounded border border-ink-700 flex-shrink-0"
          style={{ background: doc.color_hex }}
          title={doc.color_hex}
        />
      )}
    </div>
  )
}

// -- Numeric section -----------------------------------------------------

function NumericSection({ title, fields, values, onChange }) {
  return (
    <section>
      <SectionHeading>{title}</SectionHeading>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {fields.map((f) => (
          <NumericField
            key={f.key}
            label={f.label}
            unit={f.unit}
            value={values[f.key]}
            onChange={(v) => onChange(f.key, v)}
          />
        ))}
      </div>
    </section>
  )
}

function SectionHeading({ children }) {
  return (
    <div className="mb-2 text-[10px] uppercase tracking-wider text-ink-500 font-medium">
      {children}
    </div>
  )
}

// valueToText: prop → input string. Null / undefined → '' so the input
// renders the placeholder ("—") rather than the literal "null".
function valueToText(v) {
  return v === null || v === undefined ? '' : String(v)
}

// NumericField — string-backed numeric input. Empty / non-numeric values
// commit as null (the canonical "unknown" representation in the file
// shape) so consumers can render them as "—".
function NumericField({ label, unit, value, onChange }) {
  // Local string state so the user can type "1.7e-6" through intermediate
  // states like "1.7e-" without us reverting their input.
  const [draft, setDraft] = useState(() => valueToText(value))

  // External change → resync. setState-in-effect mirrors what
  // EquationsEditor does for its parsed-doc slot; same trade-off: we
  // accept one extra render to absorb prop changes (revision restore /
  // LLM tool edits / undo).
  useEffect(() => {
    setDraft(valueToText(value))
  }, [value])

  function commit(s) {
    setDraft(s)
    const trimmed = s.trim()
    if (trimmed === '') {
      onChange(null)
      return
    }
    const n = Number(trimmed)
    onChange(Number.isFinite(n) ? n : null)
  }

  return (
    <label className="block">
      <div className="flex items-baseline justify-between mb-1">
        <span className="text-[10px] uppercase tracking-wider text-ink-500 font-medium">{label}</span>
        {unit && <span className="text-[10px] text-ink-600 font-mono">{unit}</span>}
      </div>
      <input
        type="text"
        inputMode="decimal"
        value={draft}
        onChange={(e) => commit(e.target.value)}
        placeholder="—"
        className="w-full bg-ink-900 border border-ink-800 rounded px-2 py-1.5 text-xs text-ink-100 outline-none focus:border-kerf-300/60 placeholder:text-ink-600 font-mono"
      />
    </label>
  )
}

// -- Generic field primitives -------------------------------------------

function Field({ label, required, children }) {
  return (
    <label className="block">
      <div className="text-[10px] uppercase tracking-wider text-ink-500 font-medium mb-1">
        {label}{required && <span className="text-amber-400 ml-0.5">*</span>}
      </div>
      {children}
    </label>
  )
}

function Input({ value, onChange, placeholder, mono = false }) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={`w-full bg-ink-900 border border-ink-800 rounded px-2 py-1.5 text-xs text-ink-100 outline-none focus:border-kerf-300/60 placeholder:text-ink-600 ${mono ? 'font-mono' : ''}`}
    />
  )
}

function Textarea({ value, onChange, placeholder, rows = 4 }) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      className="w-full bg-ink-900 border border-ink-800 rounded px-2 py-1.5 text-xs text-ink-100 outline-none focus:border-kerf-300/60 placeholder:text-ink-600 resize-y"
    />
  )
}

// ColorRow — text input + adjacent native color picker. Both bind the
// same hex string; the picker normalises to a `#rrggbb` value.
function ColorRow({ value, onChange }) {
  const safe = /^#[0-9a-fA-F]{6}$/.test(value || '') ? value : '#7d8088'
  return (
    <div className="flex items-center gap-2">
      <input
        type="text"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder="#7d8088"
        className="flex-1 bg-ink-900 border border-ink-800 rounded px-2 py-1.5 text-xs text-ink-100 outline-none focus:border-kerf-300/60 placeholder:text-ink-600 font-mono"
      />
      <input
        type="color"
        value={safe}
        onChange={(e) => onChange(e.target.value)}
        className="w-9 h-7 rounded border border-ink-800 bg-ink-900 cursor-pointer"
        title="Pick color"
        aria-label="Pick material color"
      />
    </div>
  )
}
