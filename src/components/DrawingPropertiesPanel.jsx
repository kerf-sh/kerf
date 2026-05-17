import { useEffect, useRef, useState } from 'react'
import { Plus, Trash2, Eye, EyeOff, Loader2, Scissors } from 'lucide-react'
import { PROJECTIONS, projectionLabel } from '../lib/projection.js'
import { sheetDimensions, titleBlockLayout, TEMPLATES, parseScaleString } from '../lib/sheetFrames.js'
import { useWorkspace, loadFilePartsForProject } from '../store/workspace.js'

// Right-side floating panel for editing the drawing's frame and managing
// views. Compact on purpose so it doesn't dominate the sheet.

const SHEET_OPTIONS = ['A4', 'A3', 'A2', 'A1', 'A0', 'ANSI_A', 'ANSI_B', 'ANSI_C', 'ANSI_D']
const TEMPLATE_LABELS = { default: 'Default', iso: 'ISO', ansi: 'ANSI', kerf: 'Kerf' }

// Module-level cache of resolved part_id lists keyed by `${file_id}::${hash}`.
// Lets the panel populate the part dropdown instantly when the user reopens
// the form for a source file we've already inspected. Hash isn't easy to
// compute without the file content; for now we just key by file_id and rely
// on cache invalidation via a soft TTL when content changes during edit.
const partListCache = new Map()

export default function DrawingPropertiesPanel({
  drawing,
  files,            // full project file list (used for the "add view" picker)
  selectedAnnotationId,
  selectedDimensionId,
  onUpdateAnnotation,
  onDeleteAnnotation,
  onUpdateDimension,
  onDeleteDimension,
  onUpdateFrame,    // (patch) → void
  onAddView,        // ({source_file_id, part_id, projection}) → void
  onUpdateView,     // (viewId, patch) → void
  onRemoveView,     // (viewId) → void
  onUpdateSymbol,
  onRemoveSymbol,
  onRemoveCenterline,
  onRemoveBreak,
  onAddSheet,
  onRemoveSheet,
  onExportSvg,
  onExportPng,
  onExportPdf,
}) {
  // Resolve the active sheet (multi-sheet shape).
  const sheets = drawing.sheets || [drawing]
  const sheetIdx = Math.min(drawing.currentSheet ?? 0, sheets.length - 1)
  const sheet = sheets[sheetIdx] || sheets[0]
  const annotations = sheet?.annotations || []
  const dimensions = sheet?.dimensions || []
  const symbols = sheet?.symbols || []
  const centerlines = sheet?.centerlines || []
  const breaks = sheet?.breaks || []
  const views = sheet?.views || []
  const frame = sheet?.frame || drawing.frame || { size: 'A3', orientation: 'landscape' }

  const selectedAnnotation = annotations.find((a) => a.id === selectedAnnotationId) || null
  const selectedSymbol = symbols.find((y) => y.id === selectedAnnotationId) || null
  const selectedDimension = dimensions.find((d) => d.id === selectedDimensionId) || null
  const selectedView = views.find((v) => v.id === selectedAnnotationId) || null
  const selectedCenterline = centerlines.find((c) => c.id === selectedAnnotationId) || null
  const selectedBreak = breaks.find((b) => b.id === selectedAnnotationId) || null

  const [open, setOpen] = useState(true)
  const [adding, setAdding] = useState(false)
  const sourceFiles = (files || []).filter(
    (f) => f.kind === 'file' || f.kind === 'step',
  )
  const allFiles = useWorkspace((s) => s.files)
  const projectId = useWorkspace((s) => s.projectId)
  const addViews = useWorkspace((s) => s.addViews)

  const materialFiles = allFiles?.filter((f) => f?.kind === 'material') || []

  return (
    <div className="absolute top-3 right-3 z-10 w-72 max-w-[calc(100vw-1.5rem)] rounded-md bg-ink-900/95 border border-ink-700 backdrop-blur shadow-xl text-ink-100 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((s) => !s)}
        aria-expanded={open}
        aria-controls="drawing-panel-body"
        className="w-full flex items-center justify-between px-3 py-2 text-[11px] uppercase tracking-wider font-semibold text-ink-300 hover:text-kerf-300 hover:bg-ink-800/60 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
      >
        Drawing
        <span className="text-ink-500" aria-hidden="true">{open ? '−' : '+'}</span>
      </button>
      {open && (
        <div id="drawing-panel-body" className="border-t border-ink-800 overflow-y-auto max-h-[calc(100vh-6rem)]">
          {/* Sheet picker — only shown for multi-sheet drawings. */}
          {sheets.length > 1 && (
            <Section title={`Sheets (${sheets.length})`}>
              <div className="flex flex-wrap gap-1">
                {sheets.map((s, i) => (
                  <span
                    key={s.id || i}
                    className={`px-1.5 py-0.5 rounded text-[10px] font-mono ${
                      i === sheetIdx ? 'bg-kerf-300 text-ink-950' : 'bg-ink-800 text-ink-300'
                    }`}
                  >
                    {s.frame?.title?.slice(0, 18) || `Sheet ${i + 1}`}
                  </span>
                ))}
              </div>
            </Section>
          )}

          {/* Frame editor. */}
          <Section title="Frame">
            <Row label="Title">
              <input
                value={frame.title || ''}
                onChange={(e) => onUpdateFrame?.({ title: e.target.value })}
                className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
              />
            </Row>
            <Row label="Size">
              <select
                value={frame.size}
                onChange={(e) => onUpdateFrame?.({ size: e.target.value })}
                className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
              >
                {SHEET_OPTIONS.map((s) => (
                  <option key={s} value={s}>{s.replace('_', ' ')}</option>
                ))}
              </select>
              <select
                value={frame.orientation}
                onChange={(e) => onUpdateFrame?.({ orientation: e.target.value })}
                className="ml-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
              >
                <option value="landscape">Landscape</option>
                <option value="portrait">Portrait</option>
              </select>
            </Row>
            <Row label="Template">
              <select
                value={frame.template || 'default'}
                onChange={(e) => onUpdateFrame?.({ template: e.target.value })}
                className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
              >
                {TEMPLATES.map((t) => (
                  <option key={t} value={t}>{TEMPLATE_LABELS[t] || t}</option>
                ))}
              </select>
            </Row>
            <Row label="Author">
              <input
                value={frame.author || ''}
                onChange={(e) => onUpdateFrame?.({ author: e.target.value })}
                className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
              />
            </Row>
            <Row label="Date">
              <input
                value={frame.date || ''}
                onChange={(e) => onUpdateFrame?.({ date: e.target.value })}
                className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
                placeholder="YYYY-MM-DD"
              />
            </Row>
            <Row label="Scale">
              <input
                value={frame.scale_label || ''}
                onChange={(e) => {
                  const v = e.target.value
                  const patch = { scale_label: v }
                  // Also push to all views' scale if it parses cleanly.
                  const sc = parseScaleString(v)
                  if (sc != null) {
                    for (const view of views) {
                      onUpdateView?.(view.id, { scale: sc })
                    }
                  }
                  onUpdateFrame?.(patch)
                }}
                className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
                placeholder="1:1"
              />
            </Row>
            <Row label="Sheet">
              <input
                value={frame.sheet_number || ''}
                onChange={(e) => onUpdateFrame?.({ sheet_number: e.target.value })}
                className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
                placeholder="1/1"
              />
            </Row>
            <Row label="Notes">
              <input
                value={frame.notes || ''}
                onChange={(e) => onUpdateFrame?.({ notes: e.target.value })}
                className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
              />
            </Row>
            <Row label="Material">
              <select
                value={frame.material || ''}
                onChange={(e) => onUpdateFrame?.({ material: e.target.value || undefined })}
                className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
              >
                <option value="">— none —</option>
                {materialFiles.map((f) => (
                  <option key={f.id} value={f.name?.replace(/\.material$/, '') || f.id}>
                    {f.name?.replace(/\.material$/, '') || f.id}
                  </option>
                ))}
              </select>
            </Row>
          </Section>

          {/* Selected dimension inspector. */}
          {selectedDimension && (
            <DimensionInspector
              dim={selectedDimension}
              onUpdate={(patch) => onUpdateDimension?.(selectedDimension.id, patch)}
              onDelete={() => onDeleteDimension?.(selectedDimension.id)}
            />
          )}

          {/* Selected annotation inspector. */}
          {selectedAnnotation && (
            <AnnotationInspector
              ann={selectedAnnotation}
              onUpdate={(patch) => onUpdateAnnotation?.(selectedAnnotation.id, patch)}
              onDelete={() => onDeleteAnnotation?.(selectedAnnotation.id)}
            />
          )}

          {/* Selected symbol inspector. */}
          {selectedSymbol && (
            <SymbolInspector
              sym={selectedSymbol}
              onUpdate={(patch) => onUpdateSymbol?.(selectedSymbol.id, patch)}
              onDelete={() => onRemoveSymbol?.(selectedSymbol.id)}
            />
          )}

          {/* View list. */}
          <Section
            title={`Views (${views.length})`}
            action={
              <button
                type="button"
                onClick={() => setAdding(true)}
                title="Add view"
                aria-label="Add view"
                className="p-0.5 rounded hover:bg-ink-700 text-ink-300 hover:text-kerf-300 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
              >
                <Plus size={12} aria-hidden="true" />
              </button>
            }
          >
            {views.map((v) => {
              const file = (files || []).find((f) => f.id === v.source_file_id)
              const partLabel = v.part_id && v.part_id !== '*' ? ` · ${v.part_id}` : ''
              return (
                <div key={v.id} className="flex items-center gap-1.5 py-1 text-[11px] text-ink-200">
                  <button
                    type="button"
                    title={v.show_hidden === false ? 'Hidden lines off' : 'Hidden lines on'}
                    aria-label={v.show_hidden === false ? 'Show hidden lines' : 'Hide hidden lines'}
                    onClick={() => onUpdateView?.(v.id, { show_hidden: !v.show_hidden })}
                    className="text-ink-400 hover:text-kerf-300 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none rounded"
                  >
                    {v.show_hidden === false ? <EyeOff size={11} aria-hidden="true" /> : <Eye size={11} aria-hidden="true" />}
                  </button>
                  <button
                    type="button"
                    title={v.is_section ? 'Section view (hatched)' : 'Toggle section'}
                    aria-label={v.is_section ? 'Disable section view' : 'Enable section view'}
                    onClick={() => onUpdateView?.(v.id, { is_section: !v.is_section })}
                    className={`${v.is_section ? 'text-kerf-300' : 'text-ink-500'} hover:text-kerf-300 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none rounded`}
                  >
                    <Scissors size={11} aria-hidden="true" />
                  </button>
                  <span className="truncate flex-1 font-mono">
                    {projectionLabel(v.projection)} · {file?.name || '?'}{partLabel}
                  </span>
                  <button
                    type="button"
                    title="Remove view"
                    aria-label="Remove view"
                    onClick={() => onRemoveView?.(v.id)}
                    className="text-ink-500 hover:text-kerf-300 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none rounded"
                  >
                    <Trash2 size={11} aria-hidden="true" />
                  </button>
                </div>
              )
            })}
            {adding && (
              <AddViewForm
                files={sourceFiles}
                projectId={projectId}
                drawing={drawing}
                onCancel={() => setAdding(false)}
                onAdd={(payload) => {
                  onAddView?.(payload)
                  setAdding(false)
                }}
                onAddStandardViews={(specs) => {
                  addViews(specs)
                  setAdding(false)
                }}
              />
            )}
            {views.length === 0 && !adding && (
              <p className="text-[10px] text-ink-500 py-1">
                No views yet — click + to add one.
              </p>
            )}
          </Section>

          {/* Centerline / break / symbol summary. Compact rows so the panel
              doesn't dominate; deletion runs through the trash button. */}
          {(centerlines.length > 0 || breaks.length > 0 || symbols.length > 0) && (
            <Section title="Annotations summary">
              {centerlines.map((c) => (
                <div key={c.id} className="flex items-center gap-1.5 py-0.5 text-[11px] text-ink-300">
                  <span className="flex-1 font-mono truncate">center · {c.id.slice(-4)}</span>
                  <button type="button" onClick={() => onRemoveCenterline?.(c.id)}
                    aria-label="Remove centerline"
                    className="text-ink-500 hover:text-amber-300 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none rounded">
                    <Trash2 size={11} aria-hidden="true" />
                  </button>
                </div>
              ))}
              {breaks.map((b) => (
                <div key={b.id} className="flex items-center gap-1.5 py-0.5 text-[11px] text-ink-300">
                  <span className="flex-1 font-mono truncate">break · {b.orientation}</span>
                  <button type="button" onClick={() => onRemoveBreak?.(b.id)}
                    aria-label="Remove break line"
                    className="text-ink-500 hover:text-amber-300 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none rounded">
                    <Trash2 size={11} aria-hidden="true" />
                  </button>
                </div>
              ))}
              {symbols.map((s) => (
                <div key={s.id} className="flex items-center gap-1.5 py-0.5 text-[11px] text-ink-300">
                  <span className="flex-1 font-mono truncate">{s.kind}</span>
                  <button type="button" onClick={() => onRemoveSymbol?.(s.id)}
                    aria-label={`Remove ${s.kind} symbol`}
                    className="text-ink-500 hover:text-amber-300 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none rounded">
                    <Trash2 size={11} aria-hidden="true" />
                  </button>
                </div>
              ))}
            </Section>
          )}

          {/* Export. */}
          <Section title="Export">
            <div className="flex gap-1.5">
              <button
                type="button"
                onClick={onExportSvg}
                aria-label="Export as SVG"
                className="flex-1 px-2 py-1 rounded bg-ink-800 text-ink-100 text-[11px] hover:bg-ink-700 hover:text-kerf-300 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
              >
                SVG
              </button>
              <button
                type="button"
                onClick={onExportPng}
                aria-label="Export as PNG"
                className="flex-1 px-2 py-1 rounded bg-ink-800 text-ink-100 text-[11px] hover:bg-ink-700 hover:text-kerf-300 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
              >
                PNG
              </button>
              <button
                type="button"
                onClick={onExportPdf}
                aria-label="Export as PDF"
                className="flex-1 px-2 py-1 rounded bg-ink-800 text-ink-100 text-[11px] hover:bg-ink-700 hover:text-kerf-300 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
              >
                PDF
              </button>
            </div>
          </Section>
        </div>
      )}
    </div>
  )
}

function Section({ title, action, children }) {
  return (
    <div className="px-3 py-2 border-b border-ink-800 last:border-b-0">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[10px] uppercase tracking-wider font-semibold text-ink-400">
          {title}
        </span>
        {action}
      </div>
      <div className="space-y-1">
        {children}
      </div>
    </div>
  )
}

function Row({ label, children }) {
  return (
    <div className="flex flex-col">
      <span className="text-xs text-ink-400 mb-1">{label}</span>
      <div className="flex items-center gap-1.5">
        {children}
      </div>
    </div>
  )
}

function AddViewForm({ files, projectId, drawing, onCancel, onAdd, onAddStandardViews }) {
  // Coalesce sourceId + part_id into one piece of state so changing the
  // source naturally resets part_id without a setState-in-effect cascade.
  const [pick, setPick] = useState(() => ({ sourceId: files[0]?.id || '', partId: '*' }))
  const [projection, setProjection] = useState('front')
  // Per-source-id loader state keyed by sourceId. The effect only mutates
  // state when a fetch finishes — never synchronously to react to a prop
  // change — keeping the effect cascading-render-clean.
  const [loaderState, setLoaderState] = useState({ sourceId: null, status: 'idle', ids: null, bbox: null, error: null })
  const lastReqRef = useRef(0)
  const { sourceId, partId } = pick

  // Re-load part list when sourceId changes. The effect uses only async
  // setState (resolved/rejected promises) to avoid the
  // setState-in-effect cascading-render lint. While the loader is
  // mid-flight we derive "loading" by comparing loaderState.sourceId to
  // the live sourceId — a mismatch means the user just switched sources.
  useEffect(() => {
    if (!sourceId || !projectId) return
    const cached = partListCache.get(sourceId)
    let cancelled = false
    const reqId = ++lastReqRef.current
    const promise = cached
      ? Promise.resolve({ parts: cached._parts, ids: cached.ids, bbox: cached.bbox, fromCache: true })
      : loadFilePartsForProject(projectId, sourceId).then((parts) => {
          const ids = (parts || []).map((p) => p?.id).filter(Boolean)
          const bbox = estimateBBox(parts)
          partListCache.set(sourceId, { ids, bbox, _parts: null })
          return { parts, ids, bbox, fromCache: false }
        })
    promise.then((res) => {
      if (cancelled || lastReqRef.current !== reqId) return
      setLoaderState({ sourceId, status: 'ready', ids: res.ids, bbox: res.bbox, error: null })
    }).catch((err) => {
      if (cancelled || lastReqRef.current !== reqId) return
      setLoaderState({ sourceId, status: 'error', ids: [], bbox: null, error: err?.message || 'Failed to load' })
    })
    return () => { cancelled = true }
  }, [sourceId, projectId])

  // Derived: when loaderState lags behind the live sourceId we're mid-load.
  const synced = loaderState.sourceId === sourceId
  const partIds = synced ? loaderState.ids : null
  const loadingParts = !synced || (synced && loaderState.status === 'loading')
  const partsError = synced ? loaderState.error : null
  const estBbox = synced ? loaderState.bbox : null

  // The part dropdown options narrow when a specific part_id is selected.
  // For standard-views we need both source AND part picked (where '*' counts
  // as "picked").
  const canAdd = !!sourceId
  const canStandard = !!sourceId && partId !== ''

  return (
    <div className="mt-1 p-1.5 rounded bg-ink-950/60 border border-ink-800 space-y-1">
      <select
        value={sourceId}
        onChange={(e) => setPick({ sourceId: e.target.value, partId: '*' })}
        className="w-full h-8 bg-ink-900 border border-ink-800 rounded px-2 text-[11px] text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
      >
        {files.map((f) => (
          <option key={f.id} value={f.id}>{f.name}</option>
        ))}
      </select>
      <div className="flex items-center gap-1">
        <select
          value={partId}
          onChange={(e) => setPick({ sourceId, partId: e.target.value })}
          disabled={loadingParts}
          className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-[11px] text-ink-100 disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
        >
          <option value="*">* (all parts)</option>
          {(partIds || []).map((id) => (
            <option key={id} value={id}>{id}</option>
          ))}
        </select>
        {loadingParts && <Loader2 size={11} className="animate-spin text-ink-400" />}
      </div>
      {partsError && (
        <p className="text-[10px] text-amber-300 truncate" title={partsError}>{partsError}</p>
      )}
      <select
        value={projection}
        onChange={(e) => setProjection(e.target.value)}
        className="w-full h-8 bg-ink-900 border border-ink-800 rounded px-2 text-[11px] text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
      >
        {PROJECTIONS.map((p) => (
          <option key={p} value={p}>{projectionLabel(p)}</option>
        ))}
      </select>
      <div className="flex gap-1.5">
        <button
          type="button"
          onClick={() => canAdd && onAdd({ source_file_id: sourceId, part_id: partId, projection })}
          disabled={!canAdd}
          className="flex-1 px-2 py-0.5 rounded bg-kerf-300 text-ink-950 text-[11px] font-medium hover:bg-kerf-200 disabled:opacity-40 focus-visible:ring-2 focus-visible:ring-ink-950 focus-visible:outline-none"
        >
          Add
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="flex-1 px-2 py-0.5 rounded bg-ink-800 text-ink-200 text-[11px] hover:bg-ink-700 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
        >
          Cancel
        </button>
      </div>
      {/* Standard-view shortcuts. Visible once a source AND part (or '*') are picked. */}
      {canStandard && (
        <div className="pt-1 border-t border-ink-800/80 flex flex-col gap-1">
          <span className="text-[10px] uppercase tracking-wider text-ink-500">Standard views</span>
          <button
            type="button"
            onClick={() => {
              const specs = layoutStandardViews({
                drawing,
                source_file_id: sourceId,
                part_id: partId,
                bbox: estBbox,
                layout: '3',
              })
              onAddStandardViews(specs)
            }}
            className="px-2 py-0.5 rounded bg-ink-800 text-ink-100 text-[11px] hover:bg-ink-700 hover:text-kerf-300"
          >
            3-view (Front / Top / Right)
          </button>
          <button
            type="button"
            onClick={() => {
              const specs = layoutStandardViews({
                drawing,
                source_file_id: sourceId,
                part_id: partId,
                bbox: estBbox,
                layout: '6',
              })
              onAddStandardViews(specs)
            }}
            className="px-2 py-0.5 rounded bg-ink-800 text-ink-100 text-[11px] hover:bg-ink-700 hover:text-kerf-300"
          >
            6-view (+ Left / Back / Bottom)
          </button>
        </div>
      )}
    </div>
  )
}

// Per-kind inspector card for a selected annotation. Each kind exposes its
// editable fields (text, font size, color, dashed toggle, etc.) plus a
// Delete button. Updates flow through onUpdate(patch).
function AnnotationInspector({ ann, onUpdate, onDelete }) {
  return (
    <Section
      title={`Annotation · ${ann.kind}`}
      action={
        <button
          type="button"
          onClick={onDelete}
          title="Delete annotation"
          aria-label="Delete annotation"
          className="p-0.5 rounded hover:bg-ink-700 text-ink-300 hover:text-amber-300 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
        >
          <Trash2 size={12} aria-hidden="true" />
        </button>
      }
    >
      {(ann.kind === 'text' || ann.kind === 'leader') && (
        <Row label="Text">
          <input
            value={ann.text || ''}
            onChange={(e) => onUpdate({ text: e.target.value })}
            className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
          />
        </Row>
      )}
      {(ann.kind === 'text' || ann.kind === 'leader') && (
        <Row label="Size">
          <input
            type="number"
            step="0.5"
            min={1}
            value={ann.fontSize ?? 3.5}
            onChange={(e) => onUpdate({ fontSize: Number(e.target.value) || 3.5 })}
            className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
          />
        </Row>
      )}
      {(ann.kind === 'text' || ann.kind === 'leader') && (
        <Row label="Color">
          <input
            type="color"
            value={ann.color || '#d9a800'}
            onChange={(e) => onUpdate({ color: e.target.value })}
            className="w-8 h-8 bg-ink-900 border border-ink-800 rounded focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
          />
          <input
            value={ann.color || '#d9a800'}
            onChange={(e) => onUpdate({ color: e.target.value })}
            className="ml-1 flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 font-mono focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
          />
        </Row>
      )}
      {ann.kind === 'leader' && (
        <Row label="Side">
          <select
            value={ann.side || 'right'}
            onChange={(e) => onUpdate({ side: e.target.value })}
            className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
          >
            <option value="left">left</option>
            <option value="right">right</option>
          </select>
        </Row>
      )}
      {(ann.kind === 'polyline' || ann.kind === 'rect' || ann.kind === 'circle') && (
        <Row label="Stroke">
          <input
            type="color"
            value={ann.stroke || '#d9a800'}
            onChange={(e) => onUpdate({ stroke: e.target.value })}
            className="w-8 h-8 bg-ink-900 border border-ink-800 rounded focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
          />
          <input
            value={ann.stroke || '#d9a800'}
            onChange={(e) => onUpdate({ stroke: e.target.value })}
            className="ml-1 flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 font-mono focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
          />
        </Row>
      )}
      {(ann.kind === 'rect' || ann.kind === 'circle') && (
        <Row label="Fill">
          <input
            value={ann.fill || ''}
            placeholder="none"
            onChange={(e) => onUpdate({ fill: e.target.value || undefined })}
            className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 font-mono focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
          />
        </Row>
      )}
      {(ann.kind === 'polyline' || ann.kind === 'rect' || ann.kind === 'circle') && (
        <Row label="Width">
          <input
            type="number"
            step="0.05"
            min={0.05}
            value={ann.width ?? 0.3}
            onChange={(e) => onUpdate({ width: Number(e.target.value) || 0.3 })}
            className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
          />
        </Row>
      )}
      {(ann.kind === 'polyline' || ann.kind === 'rect' || ann.kind === 'circle' || ann.kind === 'leader') && (
        <Row label="Dashed">
          <input
            type="checkbox"
            checked={!!ann.dashed}
            onChange={(e) => onUpdate({ dashed: e.target.checked })}
          />
        </Row>
      )}
      <button
        type="button"
        onClick={onDelete}
        className="mt-1 w-full px-2 py-1 rounded bg-ink-800 text-amber-300 text-[11px] hover:bg-ink-700 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
      >
        Delete annotation
      </button>
    </Section>
  )
}

// Estimate a 3D bbox from a parts list. Walks each part's geom positions if
// available; otherwise returns a generic 80mm cube. Coarse on purpose — used
// only for the auto-fit scale in standard-view layout.
function estimateBBox(parts) {
  let minX = Infinity, minY = Infinity, minZ = Infinity
  let maxX = -Infinity, maxY = -Infinity, maxZ = -Infinity
  let any = false
  for (const p of parts || []) {
    const g = p?.geom
    if (!g) continue
    // Three.js BufferGeometry path.
    if (g.isBufferGeometry && g.attributes?.position) {
      const arr = g.attributes.position.array
      for (let i = 0; i < arr.length; i += 3) {
        const x = arr[i], y = arr[i + 1], z = arr[i + 2]
        if (x < minX) minX = x; if (x > maxX) maxX = x
        if (y < minY) minY = y; if (y > maxY) maxY = y
        if (z < minZ) minZ = z; if (z > maxZ) maxZ = z
      }
      any = true
      continue
    }
    // JSCAD Geom3 — array of polygons each with .vertices [{0:x,1:y,2:z}].
    if (Array.isArray(g.polygons)) {
      for (const poly of g.polygons) {
        const verts = poly?.vertices
        if (!Array.isArray(verts)) continue
        for (const v of verts) {
          const x = v[0], y = v[1], z = v[2]
          if (!Number.isFinite(x)) continue
          if (x < minX) minX = x; if (x > maxX) maxX = x
          if (y < minY) minY = y; if (y > maxY) maxY = y
          if (z < minZ) minZ = z; if (z > maxZ) maxZ = z
          any = true
        }
      }
    }
  }
  if (!any) return { min: [-40, -40, -40], max: [40, 40, 40] }
  return { min: [minX, minY, minZ], max: [maxX, maxY, maxZ] }
}

// Compute the 2D footprint (page-mm-equivalent in model-units) for each
// standard projection, given a 3D bbox. Mirrors the projection axes in
// src/lib/projection.js.
function projectedSize(bbox, proj) {
  const dx = bbox.max[0] - bbox.min[0]
  const dy = bbox.max[1] - bbox.min[1]
  const dz = bbox.max[2] - bbox.min[2]
  switch (proj) {
    case 'front':  return [dx, dz]
    case 'back':   return [dx, dz]
    case 'top':    return [dx, dy]
    case 'bottom': return [dx, dy]
    case 'right':  return [dy, dz]
    case 'left':   return [dy, dz]
    default:       return [Math.max(dx, dy, dz), Math.max(dx, dy, dz)]
  }
}

// Build the standard-view spec list (positions + scale) for either a 3-view
// or 6-view layout. Returns a list of {source_file_id, part_id, projection,
// position, scale} ready to feed into `addViews`.
//
// First-angle layout. Spacing is ~10mm between view bboxes. Scale is chosen
// so the largest projected dimension fits inside the printable area.
function layoutStandardViews({ drawing, source_file_id, part_id, bbox, layout }) {
  const SAFE_MARGIN = 10
  // Pull the active sheet's frame (multi-sheet shape) with a back-compat
  // fallback to the legacy top-level frame.
  const sheets = drawing.sheets || [drawing]
  const activeSheet = sheets[Math.min(drawing.currentSheet ?? 0, sheets.length - 1)] || sheets[0]
  const fr = activeSheet?.frame || drawing.frame || { size: 'A3', orientation: 'landscape' }
  const { w: sheetW, h: sheetH } = sheetDimensions(fr.size, fr.orientation)
  const block = titleBlockLayout(fr.size, fr.orientation, fr.template)
  // Printable area excludes the title-block. We use the area above the block.
  const usableW = sheetW - 2 * SAFE_MARGIN
  const usableH = (sheetH - block.h - 2 * SAFE_MARGIN)
  const safeBox = bbox || { min: [-40, -40, -40], max: [40, 40, 40] }

  const set = layout === '6'
    ? ['front', 'top', 'right', 'left', 'back', 'bottom']
    : ['front', 'top', 'right']

  // Compute each projection's [w, h] in model units, then choose a uniform
  // scale that makes the worst-case grid fit inside the printable area.
  const sizes = {}
  for (const p of set) sizes[p] = projectedSize(safeBox, p)

  // Grid positions (page-mm offsets from Front). Front is the origin.
  const grid = layout === '6'
    ? {
        front:  { gx: 0, gy: 0 },
        top:    { gx: 0, gy: -1 },
        right:  { gx: 1, gy: 0 },
        left:   { gx: -1, gy: 0 },
        back:   { gx: 2, gy: 0 },
        bottom: { gx: 0, gy: 1 },
      }
    : {
        front: { gx: 0, gy: 0 },
        top:   { gx: 0, gy: -1 },
        right: { gx: 1, gy: 0 },
      }

  // Step size = max projected dimension across the set + spacing. A uniform
  // step keeps the grid square; we pick it from the worst-case footprint.
  let maxFootprint = 0
  for (const p of set) {
    const [w, h] = sizes[p]
    if (w > maxFootprint) maxFootprint = w
    if (h > maxFootprint) maxFootprint = h
  }
  // Scale = model-units / page-mm. We want maxFootprint / scale (= page-mm)
  // small enough that the grid fits.
  // Grid extent in page-mm:
  //   - 3-view: width = 2 cells (front + right), height = 2 cells (front + top)
  //   - 6-view: width = 4 cells (left..back), height = 3 cells (top..bottom)
  const cellsW = layout === '6' ? 4 : 2
  const cellsH = layout === '6' ? 3 : 2
  // Scale so each cell footprint (maxFootprint model units) fits in
  // (usable / cells - spacing) page-mm.
  const cellTargetW = (usableW - (cellsW - 1) * SAFE_MARGIN) / cellsW
  const cellTargetH = (usableH - (cellsH - 1) * SAFE_MARGIN) / cellsH
  const cellTarget = Math.min(cellTargetW, cellTargetH)
  let scale = maxFootprint > 0 ? maxFootprint / Math.max(10, cellTarget) : 1
  if (!Number.isFinite(scale) || scale <= 0) scale = 1

  // step = max view extent in page-mm + spacing (page-mm). Use the largest
  // projected dimension scaled.
  const stepPageMm = (maxFootprint / scale) + SAFE_MARGIN

  // Top-left of the grid box: centre the layout horizontally above the title
  // block (printable area above the title block).
  const gridW = cellsW * stepPageMm - SAFE_MARGIN
  const gridH = cellsH * stepPageMm - SAFE_MARGIN
  // Front cell origin: top-left of front view's bbox in page-mm.
  // Anchor so the grid fits in usable area.
  const gridX0 = SAFE_MARGIN + Math.max(0, (usableW - gridW) / 2)
  const gridY0 = SAFE_MARGIN + Math.max(0, (usableH - gridH) / 2)

  // Front position offset within grid:
  //   3-view grid (cellsW=2, cellsH=2): Front at (col=0, row=1) — bottom-left
  //   6-view grid (cellsW=4, cellsH=3): Front at (col=1, row=1) — middle, with
  //                                     Left to its left and Back two columns right.
  const frontCol = layout === '6' ? 1 : 0
  const frontRow = 1
  const frontX = gridX0 + frontCol * stepPageMm
  const frontY = gridY0 + frontRow * stepPageMm

  const specs = []
  for (const p of set) {
    const g = grid[p]
    const x = frontX + g.gx * stepPageMm
    const y = frontY + g.gy * stepPageMm
    specs.push({
      source_file_id,
      part_id,
      projection: p,
      position: [x, y],
      scale,
    })
  }
  return specs
}

// Inspector for a selected dimension. Edit kind-specific fields including
// the auto-vs-manual override flag (clearing `value` returns to auto-measured).
function DimensionInspector({ dim, onUpdate, onDelete }) {
  return (
    <Section
      title={`Dimension · ${dim.kind}`}
      action={
        <button
          type="button"
          onClick={onDelete}
          title="Delete dimension"
          aria-label="Delete dimension"
          className="p-0.5 rounded hover:bg-ink-700 text-ink-300 hover:text-amber-300 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
        >
          <Trash2 size={12} aria-hidden="true" />
        </button>
      }
    >
      <Row label="Mode">
        <select
          value={dim.value != null || dim.text_override ? 'manual' : 'auto'}
          onChange={(e) => {
            if (e.target.value === 'auto') {
              onUpdate({ value: null, text_override: '' })
            } else {
              onUpdate({ value: dim.value || dim.text_override || '' })
            }
          }}
          className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
        >
          <option value="auto">auto-measured</option>
          <option value="manual">manual override</option>
        </select>
      </Row>
      <Row label="Value">
        <input
          value={dim.value ?? dim.text_override ?? ''}
          placeholder="auto"
          onChange={(e) => onUpdate({ value: e.target.value || null, text_override: '' })}
          className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 font-mono focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
        />
      </Row>
      {(dim.kind === 'linear' || dim.kind === 'aligned' ||
        dim.kind === 'radius' || dim.kind === 'diameter' ||
        dim.kind === 'baseline' || dim.kind === 'chain') && (
        <Row label="Offset">
          <input
            type="number"
            step="0.5"
            value={Number.isFinite(dim.offset) ? dim.offset : 8}
            onChange={(e) => onUpdate({ offset: Number(e.target.value) })}
            className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 font-mono focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
          />
        </Row>
      )}
      {dim.kind === 'angular' && (
        <Row label="Radius">
          <input
            type="number"
            step="1"
            min={1}
            value={Number.isFinite(dim.radius) ? dim.radius : 10}
            onChange={(e) => onUpdate({ radius: Number(e.target.value) })}
            className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 font-mono focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
          />
        </Row>
      )}
    </Section>
  )
}

// Inspector for surface_finish / weld / gdt symbols. v1 surfaces the most
// common params via simple text inputs.
function SymbolInspector({ sym, onUpdate, onDelete }) {
  const params = sym.params || {}
  const keys = sym.kind === 'surface_finish' ? [['ra', 'Ra']]
    : sym.kind === 'weld' ? [['text', 'Size'], ['side', 'Side']]
    : sym.kind === 'gdt' ? [['characteristic', 'Symbol'], ['tolerance', 'Tol'], ['datums', 'Datums']]
    : []
  return (
    <Section
      title={`Symbol · ${sym.kind}`}
      action={
        <button
          type="button"
          onClick={onDelete}
          title="Delete symbol"
          aria-label="Delete symbol"
          className="p-0.5 rounded hover:bg-ink-700 text-ink-300 hover:text-amber-300 focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
        >
          <Trash2 size={12} aria-hidden="true" />
        </button>
      }
    >
      {keys.map(([k, label]) => (
        <Row key={k} label={label}>
          <input
            value={params[k] ?? ''}
            onChange={(e) => onUpdate({ params: { ...params, [k]: e.target.value } })}
            className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 font-mono focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
          />
        </Row>
      ))}
      <Row label="X">
        <input
          type="number" step="0.5"
          value={Number.isFinite(sym.position?.x) ? sym.position.x : 0}
          onChange={(e) => onUpdate({ position: { ...sym.position, x: Number(e.target.value) } })}
          className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 font-mono focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
        />
      </Row>
      <Row label="Y">
        <input
          type="number" step="0.5"
          value={Number.isFinite(sym.position?.y) ? sym.position.y : 0}
          onChange={(e) => onUpdate({ position: { ...sym.position, y: Number(e.target.value) } })}
          className="flex-1 h-8 bg-ink-900 border border-ink-800 rounded px-2 text-xs text-ink-100 font-mono focus-visible:ring-2 focus-visible:ring-kerf-300 focus-visible:outline-none"
        />
      </Row>
    </Section>
  )
}
