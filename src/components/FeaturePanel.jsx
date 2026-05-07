// FeaturePanel — FreeCAD PartDesign-style features for Kerf.
//
// Mounted next to (or as a tab beside) ObjectsPanel when the active file is a
// JSCAD `.jscad` file. Lets the user go from a 2D sketch → 3D feature without
// hand-editing JSCAD.
//
// Each feature opens a small modal:
//   1. Pick a source sketch (from the project's `.sketch` files).
//   2. Set parameters (length / axis / segments / target Object for Pocket).
//   3. See a live JSCAD code preview.
//   4. Confirm → emit the code into the active `.jscad` file via
//      `appendObjectEntry` / `replaceObjectEntry` from `lib/jscadObjectOps.js`,
//      and add the `import <var> from '/path.sketch'` line if it's missing.
//      Saves through the workspace store so a `file_revisions` row is
//      written and Cmd+Z naturally undoes the operation.
//
// We deliberately don't touch the sketcher, the assembly editor, or the LLM
// system prompt. Generated code is plain, readable JSCAD: the user can open
// the file and tweak by hand at any time.
//
// Pocket target replacement: we REPLACE the target Object's entry with one
// whose geom is `subtract(<oldGeomExpr>, extrudeLinear({height:N}, profile))`.
// This keeps the part count stable (no orphan `_base` entries) and the
// rendered scene just has a hole through the original object — the most
// intuitive behaviour for users coming from FreeCAD/Onshape. If the user
// wants the unmodified base back, Cmd+Z restores it from the revision.

import { useEffect, useMemo, useState } from 'react'
import {
  Box, Square, RotateCw, Layers, Route, Sparkles,
  X, Check, AlertTriangle,
} from 'lucide-react'
import { useWorkspace } from '../store/workspace.js'
import {
  listObjectIds,
  mintFeatureId,
  appendObjectEntry,
  replaceObjectEntry,
  readObjectGeomExpr,
  ensureSketchImport,
} from '../lib/jscadObjectOps.js'

// ---------------------------------------------------------------------------
// Feature catalogue. Order = display order.

const FEATURES = [
  {
    id: 'pad',
    label: 'Pad',
    icon: Box,
    needsSketch: true,
    needsTarget: false,
    blurb: 'Extrude a sketch profile by N mm.',
  },
  {
    id: 'pocket',
    label: 'Pocket',
    icon: Square,
    needsSketch: true,
    needsTarget: true,
    blurb: 'Subtract a Pad-shaped tool from a target Object.',
  },
  {
    id: 'revolve',
    label: 'Revolve',
    icon: RotateCw,
    needsSketch: true,
    needsTarget: false,
    blurb: 'Spin a sketch profile around an axis.',
  },
  {
    id: 'loft',
    label: 'Loft',
    icon: Layers,
    needsSketch: true,
    needsTarget: false,
    extraSketches: 1,
    blurb: 'Connect two sketch profiles with a body.',
  },
  {
    id: 'sweep',
    label: 'Sweep',
    icon: Route,
    needsSketch: true,
    needsTarget: false,
    blurb: 'Sweep a profile a fixed distance along Z (path-on-Z stub).',
  },
]

// ---------------------------------------------------------------------------
// Path utilities. AssemblyEditor has its own copy; we duplicate the (tiny)
// builder here rather than introducing a cross-component import.

function filePath(file, all) {
  if (!file) return ''
  const byId = new Map((all || []).map((f) => [f.id, f]))
  const parts = []
  let cur = file
  for (let i = 0; i < 64 && cur; i++) {
    parts.unshift(cur.name)
    cur = cur.parent_id ? byId.get(cur.parent_id) : null
  }
  return '/' + parts.join('/')
}

// ---------------------------------------------------------------------------
// Code preview generator. Pure: feature config + params → multi-line string.
// We always render the full file delta (import line + new entry) so the user
// sees the complete change before confirming.

function buildPreview({
  feature, sketchBinding, sketchPath,
  secondBinding, secondSketchPath,
  params, targetGeomExpr, featureId,
}) {
  const lines = []
  if (sketchPath) {
    lines.push(`import ${sketchBinding} from '${sketchPath}'`)
  }
  if (feature.id === 'loft' && secondSketchPath && secondBinding && secondBinding !== sketchBinding) {
    lines.push(`import ${secondBinding} from '${secondSketchPath}'`)
  }
  if (lines.length > 0) lines.push('')

  if (feature.id === 'pad') {
    const h = numberOrZero(params.height)
    lines.push('// New Object — Pad')
    lines.push(`{ id: '${featureId}',`)
    lines.push(`  geom: extrusions.extrudeLinear({ height: ${h} }, ${sketchBinding}) }`)
  } else if (feature.id === 'pocket') {
    const h = numberOrZero(params.height)
    const dz = numberOrZero(params.offset)
    const oldExpr = targetGeomExpr || '<target>'
    lines.push(`// Replace Object '${params.targetId || ''}' with itself minus a Pad-shaped tool`)
    lines.push(`{ id: '${params.targetId || featureId}',`)
    lines.push(`  geom: booleans.subtract(`)
    lines.push(`    ${indent(oldExpr, 4)},`)
    lines.push(`    transforms.translate(`)
    lines.push(`      [0, 0, ${dz}],`)
    lines.push(`      extrusions.extrudeLinear({ height: ${h} }, ${sketchBinding}),`)
    lines.push(`    ),`)
    lines.push(`  ) }`)
  } else if (feature.id === 'revolve') {
    const segs = Math.max(3, Math.round(numberOrZero(params.segments) || 64))
    const angDeg = numberOrZero(params.angleDeg) || 360
    const angRad = (angDeg * Math.PI) / 180
    lines.push('// New Object — Revolve')
    lines.push(`{ id: '${featureId}',`)
    lines.push(`  geom: extrusions.extrudeRotate(`)
    lines.push(`    { segments: ${segs}, angle: ${trimNum(angRad)} },`)
    lines.push(`    ${sketchBinding},`)
    lines.push(`  ) }`)
  } else if (feature.id === 'loft') {
    // True loft requires `slice` (not in JSCAD's public API). We approximate
    // by hulling two thin extrusions placed at different Z — produces a valid
    // Geom3 that smoothly connects the two profiles. Users who need a true
    // ruled loft can swap `hulls.hull` for a custom `extrudeFromSlices` call.
    const h = numberOrZero(params.height) || 10
    const bB = secondBinding || 'profileB'
    lines.push('// New Object — Loft (hull-based; swap for extrudeFromSlices for a ruled loft)')
    lines.push(`{ id: '${featureId}',`)
    lines.push(`  geom: hulls.hull(`)
    lines.push(`    extrusions.extrudeLinear({ height: 0.01 }, ${sketchBinding}),`)
    lines.push(`    transforms.translate(`)
    lines.push(`      [0, 0, ${h}],`)
    lines.push(`      extrusions.extrudeLinear({ height: 0.01 }, ${bB}),`)
    lines.push(`    ),`)
    lines.push(`  ) }`)
  } else if (feature.id === 'sweep') {
    // Straight-Z sweep is just an extrudeLinear. We expose it as a separate
    // feature anyway so users have a button labelled "Sweep" — non-trivial
    // 3D paths still need hand-written code.
    const len = numberOrZero(params.length) || 10
    lines.push('// New Object — Sweep (straight +Z path; for curved paths edit by hand)')
    lines.push(`{ id: '${featureId}',`)
    lines.push(`  geom: extrusions.extrudeLinear({ height: ${len} }, ${sketchBinding}) }`)
  }
  return lines.join('\n')
}

function indent(s, n) {
  const pad = ' '.repeat(n)
  return String(s).split('\n').map((ln, i) => i === 0 ? ln : pad + ln).join('\n')
}
function numberOrZero(v) {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}
function trimNum(n) {
  // Render a JS number literal; trim trailing zeros. Uses 6 decimals max so
  // π / segments don't print 16 digits.
  return String(Math.round(Number(n) * 1e6) / 1e6)
}

// ---------------------------------------------------------------------------
// Build the entry text + import to inject. Used both for preview and confirm.
//
// Returns { entryText, sourceWithImport, binding } given a feature config and
// the active source string. Returns null if anything is missing.

function buildEmission({
  feature, source, sketchPath, secondSketchPath, params,
  featureId,
}) {
  if (!source || !feature || !sketchPath) return null

  // Ensure the primary sketch import.
  const primary = ensureSketchImport(source, sketchPath)
  if (!primary) return null
  let nextSource = primary.source
  const binding = primary.binding

  // Loft's second profile (if present).
  let bindingB = null
  if (feature.id === 'loft' && secondSketchPath) {
    const second = ensureSketchImport(nextSource, secondSketchPath)
    if (second) {
      nextSource = second.source
      bindingB = second.binding
    }
  }

  let targetGeomExpr = null
  if (feature.id === 'pocket' && params.targetId) {
    targetGeomExpr = readObjectGeomExpr(nextSource, params.targetId)
  }

  // Build the entry literal — closely mirrors the preview, but emitted as one
  // logical block for the bracket-matched insertion helper.
  let entryText
  if (feature.id === 'pad') {
    const h = numberOrZero(params.height)
    entryText = `{\n      id: '${featureId}',\n      geom: extrusions.extrudeLinear({ height: ${h} }, ${binding}),\n    }`
  } else if (feature.id === 'pocket') {
    if (!targetGeomExpr) return null
    const h = numberOrZero(params.height)
    const dz = numberOrZero(params.offset)
    entryText = [
      `{`,
      `      id: '${params.targetId}',`,
      `      geom: booleans.subtract(`,
      `        ${indent(targetGeomExpr, 8)},`,
      `        transforms.translate(`,
      `          [0, 0, ${dz}],`,
      `          extrusions.extrudeLinear({ height: ${h} }, ${binding}),`,
      `        ),`,
      `      ),`,
      `    }`,
    ].join('\n')
  } else if (feature.id === 'revolve') {
    const segs = Math.max(3, Math.round(numberOrZero(params.segments) || 64))
    const angDeg = numberOrZero(params.angleDeg) || 360
    const angRad = (angDeg * Math.PI) / 180
    entryText = [
      `{`,
      `      id: '${featureId}',`,
      `      geom: extrusions.extrudeRotate(`,
      `        { segments: ${segs}, angle: ${trimNum(angRad)} },`,
      `        ${binding},`,
      `      ),`,
      `    }`,
    ].join('\n')
  } else if (feature.id === 'loft') {
    // Hull-based approximation; see preview commentary for rationale.
    const h = numberOrZero(params.height) || 10
    const bB = bindingB || 'profileB'
    entryText = [
      `{`,
      `      id: '${featureId}',`,
      `      geom: hulls.hull(`,
      `        extrusions.extrudeLinear({ height: 0.01 }, ${binding}),`,
      `        transforms.translate(`,
      `          [0, 0, ${h}],`,
      `          extrusions.extrudeLinear({ height: 0.01 }, ${bB}),`,
      `        ),`,
      `      ),`,
      `    }`,
    ].join('\n')
  } else if (feature.id === 'sweep') {
    // Straight-Z sweep collapses to an extrudeLinear.
    const len = numberOrZero(params.length) || 10
    entryText = [
      `{`,
      `      id: '${featureId}',`,
      `      geom: extrusions.extrudeLinear({ height: ${len} }, ${binding}),`,
      `    }`,
    ].join('\n')
  } else {
    return null
  }

  return {
    entryText,
    sourceWithImport: nextSource,
    binding,
    bindingB,
    targetGeomExpr,
  }
}

// ---------------------------------------------------------------------------
// Main panel.

export default function FeaturePanel({ files = [], parts = [] }) {
  const [open, setOpen] = useState(null) // feature.id of the active modal
  const [opError, setOpError] = useState(null)

  const sketches = useMemo(
    () => (files || []).filter((f) => f.kind === 'sketch'),
    [files],
  )
  const objectIds = useMemo(() => parts.map((p) => p.id), [parts])

  useEffect(() => {
    if (!opError) return
    const t = setTimeout(() => setOpError(null), 4000)
    return () => clearTimeout(t)
  }, [opError])

  function buttonState(feature) {
    if (feature.needsSketch && sketches.length === 0) {
      return { disabled: true, hint: 'Create a sketch first.' }
    }
    if (feature.needsTarget && objectIds.length === 0) {
      return { disabled: true, hint: 'No Objects to subtract from.' }
    }
    if (feature.extraSketches && sketches.length < 1 + feature.extraSketches) {
      return { disabled: true, hint: `Loft needs ${1 + feature.extraSketches} sketches.` }
    }
    return { disabled: false, hint: feature.blurb }
  }

  return (
    <div className="h-full flex flex-col bg-ink-900 text-ink-100 min-h-0">
      <div className="flex items-center justify-between px-3 py-2 border-b border-ink-800 flex-shrink-0">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-400">
          Features
        </span>
        <span className="text-[10px] text-ink-500 font-mono">
          {sketches.length} sketch{sketches.length === 1 ? '' : 'es'}
        </span>
      </div>

      {opError && (
        <div className="px-3 py-1.5 bg-amber-900/30 border-b border-amber-800/50 text-[10px] text-amber-300 flex items-center justify-between gap-2">
          <span className="truncate">{opError}</span>
          <button
            type="button"
            onClick={() => setOpError(null)}
            className="text-amber-300 hover:text-amber-100 flex-shrink-0"
            title="Dismiss"
          >
            <Check size={11} />
          </button>
        </div>
      )}

      <div className="flex-1 overflow-auto py-1 min-h-0">
        {FEATURES.map((f) => {
          const Icon = f.icon
          const st = buttonState(f)
          return (
            <button
              key={f.id}
              type="button"
              onClick={() => !st.disabled && setOpen(f.id)}
              disabled={st.disabled}
              title={st.hint}
              className={`w-full flex items-center gap-2 px-3 py-2 text-left text-xs ${
                st.disabled
                  ? 'opacity-40 cursor-not-allowed'
                  : 'hover:bg-ink-800 hover:text-kerf-300 cursor-pointer'
              }`}
            >
              <Icon size={14} className="text-kerf-300 flex-shrink-0" />
              <span className="font-medium">{f.label}</span>
              <span className="flex-1 text-[10px] text-ink-500 truncate">
                {st.disabled ? st.hint : f.blurb}
              </span>
            </button>
          )
        })}

        <div className="my-1 border-t border-ink-800" />

        {/* "Coming soon" hints — these need a real B-rep kernel (OCCT). */}
        {['Fillet', 'Chamfer', 'Shell', 'Draft', 'Thread'].map((label) => (
          <div
            key={label}
            className="w-full flex items-center gap-2 px-3 py-2 text-left text-xs opacity-40"
            title="Needs a B-rep kernel (OCCT) — coming in v2."
          >
            <Sparkles size={14} className="text-ink-600 flex-shrink-0" />
            <span className="font-medium">{label}</span>
            <span className="flex-1 text-[10px] text-ink-600 truncate">coming soon</span>
          </div>
        ))}
      </div>

      {open && (
        <FeatureModal
          feature={FEATURES.find((f) => f.id === open)}
          sketches={sketches}
          allFiles={files}
          objectIds={objectIds}
          onCancel={() => setOpen(null)}
          onError={(msg) => setOpError(msg)}
          onClose={() => setOpen(null)}
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Modal. Each feature drives its own param fields but shares the dialog
// chrome (matched in look/feel to InsertObjectsModal).

function FeatureModal({ feature, sketches, allFiles, objectIds, onCancel, onError, onClose }) {
  const currentFileContent = useWorkspace((s) => s.currentFileContent)
  const editContent = useWorkspace((s) => s.editContent)
  const saveFile = useWorkspace((s) => s.saveFile)

  const [sketchId, setSketchId] = useState(sketches[0]?.id || '')
  const [sketchIdB, setSketchIdB] = useState(sketches[1]?.id || sketches[0]?.id || '')
  const [params, setParams] = useState(() => defaultParamsFor(feature, objectIds))
  const [submitting, setSubmitting] = useState(false)

  // Esc to close.
  useEffect(() => {
    function onKey(e) { if (e.key === 'Escape' && !submitting) onCancel() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCancel, submitting])

  const sketchFile = sketches.find((s) => s.id === sketchId) || null
  const sketchFileB = sketches.find((s) => s.id === sketchIdB) || null
  const sketchPath = sketchFile ? filePath(sketchFile, allFiles) : null
  const sketchPathB = sketchFileB ? filePath(sketchFileB, allFiles) : null

  const featureId = useMemo(
    () => mintFeatureId(currentFileContent, feature.id) || `${feature.id}-1`,
    [currentFileContent, feature.id],
  )

  // Live preview — recompute on every param change. Pure; cheap enough that we
  // don't bother memoising into a dep array beyond the inputs.
  const targetGeomExpr = useMemo(() => {
    if (feature.id !== 'pocket') return null
    if (!params.targetId) return null
    return readObjectGeomExpr(currentFileContent, params.targetId)
  }, [feature.id, params.targetId, currentFileContent])

  // Predict the binding names that ensureSketchImport will pick when we
  // confirm. We compute the second one against the source AS IF the first
  // import has already been added, so collisions are taken into account.
  const previewBinding = useMemo(() => {
    if (!sketchPath || !currentFileContent) return 'profile'
    const r = ensureSketchImport(currentFileContent, sketchPath)
    return r?.binding || 'profile'
  }, [sketchPath, currentFileContent])

  const previewSecondBinding = useMemo(() => {
    if (feature.id !== 'loft' || !sketchPathB) return null
    const first = ensureSketchImport(currentFileContent, sketchPath)
    const r = ensureSketchImport(first?.source || currentFileContent, sketchPathB)
    return r?.binding || 'profileB'
  }, [feature.id, sketchPath, sketchPathB, currentFileContent])

  const preview = useMemo(() => buildPreview({
    feature,
    sketchBinding: previewBinding,
    sketchPath,
    secondBinding: previewSecondBinding,
    secondSketchPath: sketchPathB,
    params,
    targetGeomExpr,
    featureId,
  }), [feature, previewBinding, previewSecondBinding, sketchPath, sketchPathB, params, targetGeomExpr, featureId])

  // Parse-shape sniff: bail loudly if the file isn't a `return [{id, geom}, ...]`.
  const parsedShape = useMemo(() => {
    return listObjectIds(currentFileContent) != null
  }, [currentFileContent])

  // Disable confirm when the basic prereqs aren't met.
  const blockReason = (() => {
    if (!parsedShape) return "Active file isn't a `return [{id, geom}, ...]` — edit by hand."
    if (!sketchFile) return 'Pick a sketch.'
    if (feature.extraSketches && !sketchFileB) return 'Pick a second sketch.'
    if (feature.needsTarget && !params.targetId) return 'Pick a target Object.'
    if (feature.needsTarget && !targetGeomExpr) return 'Target Object has no geom field.'
    return null
  })()

  async function handleConfirm() {
    if (blockReason) return
    setSubmitting(true)
    try {
      const emit = buildEmission({
        feature,
        source: currentFileContent,
        sketchPath,
        secondSketchPath: sketchPathB,
        params,
        featureId,
      })
      if (!emit) throw new Error("Couldn't generate code for this feature.")

      let next
      if (feature.id === 'pocket') {
        next = replaceObjectEntry(emit.sourceWithImport, params.targetId, emit.entryText)
      } else {
        next = appendObjectEntry(emit.sourceWithImport, emit.entryText)
      }
      if (next == null) throw new Error("Couldn't auto-edit — file's structure isn't recognisable.")

      editContent(next)
      await saveFile()
      onClose()
    } catch (err) {
      onError(err?.message || String(err))
      setSubmitting(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-ink-950/70 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-lg bg-ink-900 border border-ink-700 rounded-xl shadow-2xl flex flex-col max-h-[85vh]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-ink-800">
          <div className="flex items-center gap-2">
            <feature.icon size={15} className="text-kerf-300" />
            <h2 className="text-base font-semibold text-ink-100">{feature.label}</h2>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="p-1 rounded hover:bg-ink-800 text-ink-300 hover:text-ink-100"
            title="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div className="px-4 py-3 flex-1 overflow-auto min-h-0 flex flex-col gap-3">
          {/* Sketch picker */}
          <ParamRow label="Sketch">
            <select
              value={sketchId}
              onChange={(e) => setSketchId(e.target.value)}
              className="flex-1 bg-ink-850 border border-ink-700 rounded px-2 py-1.5 text-[12px] font-mono text-ink-100 outline-none focus:border-kerf-300/60"
            >
              {sketches.map((s) => (
                <option key={s.id} value={s.id}>{filePath(s, allFiles)}</option>
              ))}
            </select>
          </ParamRow>

          {feature.extraSketches > 0 && (
            <ParamRow label="Sketch B">
              <select
                value={sketchIdB}
                onChange={(e) => setSketchIdB(e.target.value)}
                className="flex-1 bg-ink-850 border border-ink-700 rounded px-2 py-1.5 text-[12px] font-mono text-ink-100 outline-none focus:border-kerf-300/60"
              >
                {sketches.map((s) => (
                  <option key={s.id} value={s.id}>{filePath(s, allFiles)}</option>
                ))}
              </select>
            </ParamRow>
          )}

          {/* Per-feature parameter rows */}
          {feature.id === 'pad' && (
            <ParamRow label="Height (mm)">
              <NumberField
                value={params.height}
                onChange={(v) => setParams({ ...params, height: v })}
              />
            </ParamRow>
          )}

          {feature.id === 'pocket' && (
            <>
              <ParamRow label="Target">
                <select
                  value={params.targetId || ''}
                  onChange={(e) => setParams({ ...params, targetId: e.target.value })}
                  className="flex-1 bg-ink-850 border border-ink-700 rounded px-2 py-1.5 text-[12px] font-mono text-ink-100 outline-none focus:border-kerf-300/60"
                >
                  {objectIds.map((id) => (
                    <option key={id} value={id}>{id}</option>
                  ))}
                </select>
              </ParamRow>
              <ParamRow label="Depth (mm)">
                <NumberField
                  value={params.height}
                  onChange={(v) => setParams({ ...params, height: v })}
                />
              </ParamRow>
              <ParamRow label="Z offset" hint="Where the tool starts on Z (negative drills DOWN into the part).">
                <NumberField
                  value={params.offset}
                  onChange={(v) => setParams({ ...params, offset: v })}
                />
              </ParamRow>
              <p className="text-[10px] text-ink-500 leading-relaxed">
                Pocket replaces <code className="text-ink-300">{params.targetId || '(target)'}</code> with itself
                minus the extruded sketch. Use Cmd+Z to recover the original Object.
              </p>
            </>
          )}

          {feature.id === 'revolve' && (
            <>
              <ParamRow label="Angle (deg)">
                <NumberField
                  value={params.angleDeg}
                  onChange={(v) => setParams({ ...params, angleDeg: v })}
                />
              </ParamRow>
              <ParamRow label="Segments">
                <NumberField
                  value={params.segments}
                  onChange={(v) => setParams({ ...params, segments: v })}
                  min={3}
                  step={1}
                />
              </ParamRow>
              <p className="text-[10px] text-ink-500 leading-relaxed">
                Spins the sketch around the world Y axis (sketch authored in the
                XY plane). For other axes, edit the generated code by hand.
              </p>
            </>
          )}

          {feature.id === 'loft' && (
            <>
              <ParamRow label="Distance (mm)">
                <NumberField
                  value={params.height}
                  onChange={(v) => setParams({ ...params, height: v })}
                />
              </ParamRow>
              <p className="text-[10px] text-ink-500 leading-relaxed">
                Connects two profiles with a straight body of the given Z
                distance. Profiles should have matching outer-loop counts for
                clean results — otherwise tweak the generated code.
              </p>
            </>
          )}

          {feature.id === 'sweep' && (
            <>
              <ParamRow label="Length (mm)">
                <NumberField
                  value={params.length}
                  onChange={(v) => setParams({ ...params, length: v })}
                />
              </ParamRow>
              <ParamRow label="Segments">
                <NumberField
                  value={params.segments}
                  onChange={(v) => setParams({ ...params, segments: v })}
                  min={2}
                  step={1}
                />
              </ParamRow>
              <p className="text-[10px] text-ink-500 leading-relaxed">
                Sweeps the profile along +Z for {numberOrZero(params.length) || 0}mm. For
                arbitrary 3D paths, edit the generated <code>callback</code>.
              </p>
            </>
          )}

          {/* Code preview */}
          <div className="mt-1">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] uppercase tracking-wider text-ink-500">Code preview</span>
              <span className="text-[10px] text-ink-600 font-mono">{featureId}</span>
            </div>
            <pre className="font-mono text-[11px] text-ink-200 bg-ink-950 border border-ink-800 rounded p-3 overflow-auto leading-snug whitespace-pre">
              {preview}
            </pre>
          </div>

          {blockReason && (
            <div className="flex items-start gap-2 px-2 py-1.5 rounded bg-amber-900/20 border border-amber-800/40 text-[11px] text-amber-300">
              <AlertTriangle size={12} className="mt-0.5 flex-shrink-0" />
              <span>{blockReason}</span>
            </div>
          )}
        </div>

        <div className="px-4 py-3 border-t border-ink-800 flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={onCancel}
            disabled={submitting}
            className="px-3 py-1.5 rounded-md text-xs text-ink-300 hover:bg-ink-800 disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleConfirm}
            disabled={submitting || !!blockReason}
            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md bg-kerf-300 text-ink-950 text-xs font-medium hover:bg-kerf-200 disabled:opacity-40"
          >
            <Check size={12} />
            {submitting ? 'Inserting…' : `Insert ${feature.label}`}
          </button>
        </div>
      </div>
    </div>
  )
}

// Default parameters for a fresh modal opening.
function defaultParamsFor(feature, objectIds) {
  switch (feature.id) {
    case 'pad':     return { height: 5 }
    case 'pocket':  return { height: 5, offset: -2.5, targetId: objectIds[0] || '' }
    case 'revolve': return { angleDeg: 360, segments: 64 }
    case 'loft':    return { height: 10 }
    case 'sweep':   return { length: 20, segments: 8 }
    default:        return {}
  }
}

// ---------------------------------------------------------------------------
// Tiny form atoms.

function ParamRow({ label, hint, children }) {
  return (
    <label className="flex items-start gap-2 text-xs text-ink-300">
      <span className="text-[10px] uppercase tracking-wider text-ink-500 w-20 pt-1.5 flex-shrink-0">
        {label}
      </span>
      <div className="flex-1 min-w-0 flex flex-col gap-1">
        <div className="flex items-center gap-2">{children}</div>
        {hint && <span className="text-[10px] text-ink-500 leading-snug">{hint}</span>}
      </div>
    </label>
  )
}

function NumberField({ value, onChange, min, max, step }) {
  const [draft, setDraft] = useState(formatNum(value))
  // Keep draft in sync if the value changes from outside (e.g. param reset).
  useEffect(() => {
    setDraft(formatNum(value))
  }, [value])

  function commit(text) {
    const n = Number(text)
    if (!Number.isFinite(n)) {
      setDraft(formatNum(value))
      return
    }
    let clamped = n
    if (min != null && clamped < min) clamped = min
    if (max != null && clamped > max) clamped = max
    onChange(clamped)
    setDraft(formatNum(clamped))
  }
  return (
    <input
      type="text"
      inputMode="decimal"
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={(e) => commit(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') { e.target.blur() }
        else if (e.key === 'ArrowUp') {
          e.preventDefault()
          commit(String((Number(draft) || 0) + (step || 1)))
        }
        else if (e.key === 'ArrowDown') {
          e.preventDefault()
          commit(String((Number(draft) || 0) - (step || 1)))
        }
      }}
      className="flex-1 bg-ink-950 border border-ink-800 rounded px-2 py-1 text-[11px] font-mono text-ink-100 outline-none focus:border-kerf-300/60"
    />
  )
}

function formatNum(n) {
  if (!Number.isFinite(n)) return '0'
  return String(Math.round(n * 10000) / 10000)
}
