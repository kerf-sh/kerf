import { forwardRef, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { sheetDimensions, titleBlockLayout, scaleBarGeometry } from '../lib/sheetFrames.js'
import {
  projectFile, projectFileWithHLR, projectionLabel,
} from '../lib/projection.js'
import { applyMatrixToGeom } from '../lib/geom3.js'
import {
  hatchPatternId, hatchPatternDef, symbolGlyph, balloonGlyph,
  CENTER_DASH, zigzagPoints, detectCenterlines,
} from '../lib/annotations.js'
import { autoLabel, hasManualOverride, ordinatePickLabels } from '../lib/dimensions.js'
import {
  extractSnapTargets, resolveSnap, snapLabel, SNAP_COLOR, SNAP_MARKER_MM,
} from '../lib/drawingSnap.js'
import { Plus, X as XIcon } from 'lucide-react'

// Drawing renderer — a single SVG element. Renders the sheet, each view's
// projected polylines, the title block, dimensions, and now annotations and
// transient measure overlays. Handles pan (middle-mouse / space-drag), zoom
// (wheel), dimension/annotation selection, and the click-click-drag dimension
// authoring flow.
//
// Coordinates: the SVG's viewBox is in PAGE MILLIMETRES. Everything we draw
// (sheet, views, dimensions, annotations) lives in mm. Pan/zoom adjusts the
// viewBox origin and size only. This means stroke widths scale with zoom — we
// counter that with `vector-effect="non-scaling-stroke"` so technical
// drawings keep crisp 1px-equivalent lines no matter the zoom.

const SHEET_FILL = '#ffffff'
const SHEET_BORDER = '#1a1f2a'
const VISIBLE_STROKE = '#0c1118'
const HIDDEN_STROKE = '#5a6478'
const SILHOUETTE_STROKE = '#0c1118'
const DIM_STROKE = '#1a3680'
const DIM_SELECTED = '#ffd633'

// Annotation defaults (matches the contract).
const ANN_STROKE = '#d9a800'      // kerf-500
const ANN_SELECTED_STROKE = '#ffd633'
const ANN_DEFAULT_WIDTH = 0.3     // mm
const ANN_DEFAULT_TEXT_SIZE = 3.5 // mm
const ANN_HANDLE_FILL = '#ffd633'
const ANN_HANDLE_STROKE = '#1a1f2a'

// Stroke widths in MM (roughly converted to "pen weight"; vector-effect
// keeps them at the same on-screen pixel weight regardless of zoom). The
// numbers are chosen to look right on-screen at the default fit-zoom.
const VISIBLE_W = 0.4
const HIDDEN_W = 0.25
const SILHOUETTE_W = 0.55

// Approximate text height in mm for dimension labels.
const DIM_TEXT_MM = 3.2

// Tool category helpers.
const TWO_POINT_DIMS = new Set(['linear', 'aligned', 'radius', 'diameter'])
const MULTI_POINT_DIMS = new Set(['baseline', 'chain', 'ordinate'])
const DIM_TOOLS = new Set([...TWO_POINT_DIMS, 'angular', ...MULTI_POINT_DIMS])
const MEASURE_TOOLS = new Set(['measure-distance', 'measure-angle'])
const SYMBOL_TOOLS = new Set(['surface_finish', 'weld', 'gdt', 'balloon'])
const ANN_PLACE_TOOLS = new Set(['leader', 'note', 'text', 'centerline', 'break'])
function isSnappingTool(t) {
  return DIM_TOOLS.has(t) || MEASURE_TOOLS.has(t)
    || t === 'leader' || t === 'centerline' || t === 'break'
    || SYMBOL_TOOLS.has(t)
}

const DrawingView = forwardRef(function DrawingView({
  drawing,
  partsByFileId,
  topologiesByFileId,
  selectedDimensionId,
  onSelectDimension,
  selectedAnnotationId,
  onSelectAnnotation,
  // Tool mode — see DrawingToolbar.jsx for the full enum.
  tool = 'pointer',
  onAddDimension,
  onDeleteDimension,
  onAddAnnotation,
  onUpdateAnnotation,
  onDeleteAnnotation,
  onAddCenterline,
  onAddBreak,
  onAddSymbol,
  onSelectSheet,
  onAddSheet,
  onRemoveSheet,
  onResetTool,
}, ref) {
  // Resolve the active sheet from the multi-sheet drawing object. New
  // canonical shape: drawing.sheets = [{ id, frame, views, dimensions, ... }];
  // legacy parses still produce sheets[0] from top-level fields.
  const sheets = drawing.sheets && drawing.sheets.length > 0 ? drawing.sheets : [drawing]
  const sheetIdx = Math.min(drawing.currentSheet ?? 0, sheets.length - 1)
  const sheet = sheets[sheetIdx] || sheets[0]
  const frame = sheet?.frame || drawing.frame || { size: 'A3', orientation: 'landscape' }
  const sheetViews = sheet?.views || []
  const sheetDims = sheet?.dimensions || []
  const sheetAnns = sheet?.annotations || []
  const sheetCenters = sheet?.centerlines || []
  const sheetBreaks = sheet?.breaks || []
  const sheetSymbols = sheet?.symbols || []
  // Pan/zoom: viewBox position + size, in mm. We key the state by sheet size
  // so a frame change cleanly resets the zoom (instead of fighting with a
  // setState-in-effect, which lints as a cascading-render anti-pattern).
  const { w: sheetW, h: sheetH } = sheetDimensions(frame.size, frame.orientation)
  const sheetKey = `${sheetW}x${sheetH}`
  const [viewBoxState, setViewBoxState] = useState(() => ({
    key: sheetKey, vb: initialViewBox(sheetW, sheetH),
  }))
  const viewBox = viewBoxState.key === sheetKey
    ? viewBoxState.vb
    : initialViewBox(sheetW, sheetH)
  const setViewBox = useCallback((next) => {
    setViewBoxState((s) => {
      const base = s.key === sheetKey ? s.vb : initialViewBox(sheetW, sheetH)
      const vb = typeof next === 'function' ? next(base) : next
      return { key: sheetKey, vb }
    })
  }, [sheetKey, sheetW, sheetH])

  // Pan state.
  const panRef = useRef({ active: false, x: 0, y: 0, vbX: 0, vbY: 0 })
  const spaceRef = useRef(false)
  // Mirror spaceRef into state for the cursor styling — we can't read refs
  // during render. The keyboard handlers update both.
  const [spaceHeld, setSpaceHeld] = useState(false)

  // Transient measurement state — never committed to the drawing.
  // Distance:  { kind: 'distance', viewId?, a:{x,y}, b?:{x,y}, scale }
  // Angle:     { kind: 'angle', viewId?, vertex:{x,y}, a?:{x,y}, b?:{x,y} }
  // Keyed by tool so a tool switch transparently clears the value WITHOUT
  // a setState-in-effect (which lints as a cascading-render anti-pattern).
  const [measureState, setMeasureState] = useState({ tool, value: null })
  const measure = measureState.tool === tool ? measureState.value : null
  const setMeasure = useCallback((nextOrFn) => {
    setMeasureState((s) => {
      const base = s.tool === tool ? s.value : null
      const value = typeof nextOrFn === 'function' ? nextOrFn(base) : nextOrFn
      return { tool, value }
    })
  }, [tool])

  // Annotation drag/edit state. Used for the polyline-in-progress AND for
  // dragging existing annotations / handles in pointer mode. Same
  // tool-keyed pattern as `measureState`.
  // {kind, payload} forms:
  //   {kind:'polyline-draft', viewId?, points:[{x,y}]}
  //   {kind:'rect-draft', viewId?, start:{x,y}, end:{x,y}}
  //   {kind:'circle-draft', viewId?, center:{x,y}, radius}
  //   {kind:'leader-draft', viewId?, from:{x,y}}
  //   {kind:'drag-ann', annId, mode:'move'|'handle', handleIdx?, startMm, startAnn}
  const [annDraftState, setAnnDraftState] = useState({ tool, value: null })
  // Drag-ann is intentionally allowed in any tool (pointer drag); accept the
  // value across tool changes when its kind is 'drag-ann'.
  const annDraft = (annDraftState.tool === tool || annDraftState.value?.kind === 'drag-ann')
    ? annDraftState.value : null
  const setAnnDraft = useCallback((nextOrFn) => {
    setAnnDraftState((s) => {
      const base = (s.tool === tool || s.value?.kind === 'drag-ann') ? s.value : null
      const value = typeof nextOrFn === 'function' ? nextOrFn(base) : nextOrFn
      return { tool, value }
    })
  }, [tool])

  // Inline text input state for text/leader annotations. Rendered as a DOM
  // overlay (not SVG) so the user gets browser-native input handling.
  // {kind:'text'|'leader', viewId?, mmX, mmY, screenLeft, screenTop, value, from?, to?}
  const [textInput, setTextInput] = useState(null)

  // Cursor readout state. Updated on every mousemove inside the SVG.
  // Hidden when the user leaves the SVG entirely.
  const [hudPos, setHudPos] = useState(null) // {x, y} in page mm

  useEffect(() => {
    function down(e) {
      if (e.code === 'Space') {
        spaceRef.current = true
        setSpaceHeld(true)
      }
    }
    function up(e) {
      if (e.code === 'Space') {
        spaceRef.current = false
        setSpaceHeld(false)
      }
    }
    function key(e) {
      // If the user is typing in the inline annotation input, swallow keys
      // so they don't trigger Esc/Delete on the canvas.
      if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) {
        return
      }
      if (e.key === 'Delete' || e.key === 'Backspace') {
        if (selectedDimensionId && onDeleteDimension) onDeleteDimension(selectedDimensionId)
        if (selectedAnnotationId && onDeleteAnnotation) onDeleteAnnotation(selectedAnnotationId)
      }
      if (e.key === 'Escape') {
        onSelectDimension?.(null)
        onSelectAnnotation?.(null)
        setMeasure(null)
        setAnnDraft(null)
        setTextInput(null)
        onResetTool?.()
      }
    }
    window.addEventListener('keydown', down)
    window.addEventListener('keyup', up)
    window.addEventListener('keydown', key)
    return () => {
      window.removeEventListener('keydown', down)
      window.removeEventListener('keyup', up)
      window.removeEventListener('keydown', key)
    }
  }, [
    selectedDimensionId, onDeleteDimension, onSelectDimension, onResetTool,
    selectedAnnotationId, onDeleteAnnotation, onSelectAnnotation,
    setMeasure, setAnnDraft,
  ])

  // Note: tool-keyed `measureState` and `annDraftState` above auto-clear
  // when the user switches tools — no setState-in-effect needed. The text
  // input is closed explicitly on commit/cancel/Esc, so it stays open
  // across an accidental tool change while the user is typing.

  const svgRef = useRef(null)
  // Forward the SVG ref for export.
  useEffect(() => {
    if (typeof ref === 'function') ref(svgRef.current)
    else if (ref) ref.current = svgRef.current
  }, [ref])

  // Build per-source BVH maps so the cross-part HLR pass can ray-test against
  // every other part's geometry. We lazy-import three-mesh-bvh to keep it out
  // of the main bundle until the user opens a drawing. BVHs are cached in a
  // module-scoped WeakMap keyed by part identity, so opening multiple views
  // of the same source file builds each BVH only once.
  const [bvhsByFileId, setBvhsByFileId] = useState(() => new Map())
  useEffect(() => {
    let cancelled = false
    ;(async () => {
      const next = new Map()
      const allFileIds = []
      for (const fid of partsByFileId?.keys?.() || []) allFileIds.push(fid)
      if (allFileIds.length === 0) {
        if (!cancelled) setBvhsByFileId(next)
        return
      }
      const bvhMod = await import('three-mesh-bvh')
      for (const fid of allFileIds) {
        const parts = partsByFileId.get(fid) || []
        const map = new Map()
        for (const p of parts) {
          if (!p.geom) continue
          const bvh = getOrBuildBVH(p, bvhMod)
          if (bvh) map.set(p.id, bvh)
        }
        next.set(fid, map)
      }
      if (!cancelled) setBvhsByFileId(next)
    })().catch((err) => {
      console.warn('DrawingView: BVH build failed', err)
    })
    return () => { cancelled = true }
  }, [partsByFileId])

  // Project everything once, indexed by view id. Use the HLR-aware path when
  // BVHs are ready; fall back to the basic projector while they're loading.
  //
  // Per-part filter: when `view.part_id` is set and not '*', we filter both
  // the parts list AND the BVH map down to that single part. The HLR pass
  // then only sees that part for both edge-projection and occlusion testing
  // — a hidden sibling never occludes its sibling, and only the named part's
  // edges are projected.
  const projectedByView = useMemo(() => {
    const m = new Map()
    for (const v of sheetViews) {
      const allParts = partsByFileId?.get?.(v.source_file_id) || []
      const tops = topologiesByFileId?.get?.(v.source_file_id) || new Map()
      const allBvhs = bvhsByFileId.get(v.source_file_id)
      const wantPart = v.part_id && v.part_id !== '*' ? v.part_id : null
      const parts = wantPart ? allParts.filter((p) => p?.id === wantPart) : allParts
      let bvhs = allBvhs
      if (wantPart && allBvhs) {
        bvhs = new Map()
        const b = allBvhs.get(wantPart)
        if (b) bvhs.set(wantPart, b)
      }
      if (bvhs && bvhs.size > 0) {
        m.set(v.id, projectFileWithHLR(parts, tops, v.projection, bvhs))
      } else {
        m.set(v.id, projectFile(parts, tops, v.projection))
      }
    }
    return m
  }, [sheetViews, partsByFileId, topologiesByFileId, bvhsByFileId])

  // Per-view snap-target lists. Lazy: only built when any snapping tool is
  // active. Keyed by view id; the cursor handler scans every view's list to
  // pick the closest snap. Recomputed when the projection or view position
  // changes (the page-mm coords depend on view.position + view.scale).
  const snappingActive = isSnappingTool(tool)
  const snapTargetsByView = useMemo(() => {
    if (!snappingActive) return null
    const out = new Map()
    for (const v of sheetViews) {
      const proj = projectedByView.get(v.id)
      if (!proj) continue
      out.set(v.id, extractSnapTargets(v, proj))
    }
    return out
  }, [snappingActive, sheetViews, projectedByView])

  // ---- Pan + zoom handlers ----
  const onPointerDown = useCallback((e) => {
    // Middle-mouse OR space+left starts pan.
    if (e.button === 1 || (e.button === 0 && spaceRef.current)) {
      panRef.current = { active: true, x: e.clientX, y: e.clientY, vbX: viewBox.x, vbY: viewBox.y }
      svgRef.current?.setPointerCapture?.(e.pointerId)
      e.preventDefault()
    }
  }, [viewBox.x, viewBox.y])

  const onPointerMove = useCallback((e) => {
    const p = panRef.current
    if (!p.active) return
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    // pixels → mm: viewBox.w mm spans rect.width px.
    const sx = viewBox.w / rect.width
    const sy = viewBox.h / rect.height
    setViewBox((vb) => ({
      ...vb,
      x: p.vbX - (e.clientX - p.x) * sx,
      y: p.vbY - (e.clientY - p.y) * sy,
    }))
  }, [viewBox.w, viewBox.h, setViewBox])

  const onPointerUp = useCallback((e) => {
    if (panRef.current.active) {
      panRef.current.active = false
      svgRef.current?.releasePointerCapture?.(e.pointerId)
    }
  }, [])

  const onWheel = useCallback((e) => {
    e.preventDefault()
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    // Mouse position in mm.
    const mx = viewBox.x + ((e.clientX - rect.left) / rect.width) * viewBox.w
    const my = viewBox.y + ((e.clientY - rect.top) / rect.height) * viewBox.h
    // Zoom in on scroll up, out on scroll down. Soft clamp.
    const factor = e.deltaY < 0 ? 0.85 : 1.15
    const newW = Math.max(20, Math.min(sheetW * 5, viewBox.w * factor))
    const newH = newW * (viewBox.h / viewBox.w)
    setViewBox({
      x: mx - ((e.clientX - rect.left) / rect.width) * newW,
      y: my - ((e.clientY - rect.top) / rect.height) * newH,
      w: newW,
      h: newH,
    })
  }, [viewBox, sheetW, setViewBox])

  // Convert client coords to page mm (helper for click + snap).
  const clientToMm = useCallback((cx, cy) => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return [0, 0]
    return [
      viewBox.x + ((cx - rect.left) / rect.width) * viewBox.w,
      viewBox.y + ((cy - rect.top) / rect.height) * viewBox.h,
    ]
  }, [viewBox])

  // Find which view (if any) contains the page-mm point — needed because
  // dimensions live in PAGE-MM coords but are bound to a specific view id.
  const findViewAt = useCallback((pageX, pageY) => {
    for (const v of sheetViews) {
      const proj = projectedByView.get(v.id)
      if (!proj?.bbox) continue
      const w = (proj.bbox.max[0] - proj.bbox.min[0]) / v.scale
      const h = (proj.bbox.max[1] - proj.bbox.min[1]) / v.scale
      const x0 = v.position[0]
      const y0 = v.position[1]
      // Inflate hit-box by 8mm so dimensions can be placed just outside the
      // projected geometry without missing the view.
      const pad = 8
      if (pageX >= x0 - pad && pageX <= x0 + w + pad && pageY >= y0 - pad && pageY <= y0 + h + pad) {
        return v
      }
    }
    return null
  }, [sheetViews, projectedByView])

  // Page-mm tolerance equivalent to SNAP_PIXELS screen-px at the current
  // zoom. Recomputed lazily inside the cursor handler so we don't have to
  // memoize against rect.width.
  const computeSnapTolMm = useCallback(() => {
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect || rect.width <= 0) return 5
    // 12 screen-px → mm. viewBox.w mm spans rect.width px.
    return (12 * viewBox.w) / rect.width
  }, [viewBox.w])

  // Snap a page-mm point to the nearest TechDraw-style snap target across
  // every view on the active sheet. Returns { x, y, kind, viewId }; kind is
  // 'free' when nothing wins.
  const findSnap = useCallback((pageX, pageY, view) => {
    if (!snapTargetsByView) return null
    const tolMm = computeSnapTolMm()
    const lists = []
    // Hit-view first (so its viewId wins ties for the result), then any
    // others in case the cursor sits on an edge of a neighbour.
    if (view) {
      const t = snapTargetsByView.get(view.id)
      if (t) lists.push(t)
    }
    for (const [vid, t] of snapTargetsByView.entries()) {
      if (view && vid === view.id) continue
      lists.push(t)
    }
    const snap = resolveSnap(lists, pageX, pageY, { tolMm })
    if (!snap) {
      return { viewId: view?.id || null, x: pageX, y: pageY, kind: 'free' }
    }
    return {
      viewId: snap.viewId || view?.id || null,
      x: snap.x, y: snap.y, kind: snap.kind,
    }
  }, [snapTargetsByView, computeSnapTolMm])

  // ---- Dimension authoring state (transient — never committed to drawing
  // until the third click). Keyed by the active tool so a tool switch resets
  // the draft cleanly without a setState-in-effect (which lints as a
  // cascading-render anti-pattern).
  const [draftState, setDraftState] = useState({ tool, draft: null })
  const draft = draftState.tool === tool ? draftState.draft : null
  const setDraft = useCallback((next) => {
    setDraftState({
      tool,
      draft: typeof next === 'function' ? next(draft) : next,
    })
  }, [tool, draft])
  const [hover, setHover] = useState(null) // {x,y,kind,viewId} for snap indicator

  // Helper: snap-and-find-view in one go (used by every click handler).
  // `altKey=true` (or holding Alt during the click) disables snapping for
  // that pick, returning the raw page-mm position with kind='free'.
  // Snapping runs even when the cursor isn't strictly inside a view's
  // bbox so origin snaps and near-edge snaps still work.
  const snapAt = useCallback((cx, cy, altKey = false) => {
    const [px, py] = clientToMm(cx, cy)
    const view = findViewAt(px, py)
    if (isSnappingTool(tool) && !altKey) {
      const snap = findSnap(px, py, view)
      if (snap && snap.kind && snap.kind !== 'free') {
        return { ...snap, viewId: snap.viewId || view?.id || null, page: [px, py] }
      }
    }
    return { viewId: view?.id || null, x: px, y: py, kind: 'free', page: [px, py] }
  }, [clientToMm, findViewAt, findSnap, tool])

  // Click handler — dispatches based on the active tool.
  const onSvgClick = useCallback((e) => {
    if (panRef.current.active) return
    if (spaceRef.current) return // space-drag pan, swallow

    // Pointer mode: clear selection (annotation/dimension click handlers
    // stopPropagation before this fires).
    if (tool === 'pointer') {
      onSelectDimension?.(null)
      onSelectAnnotation?.(null)
      return
    }

    const sn = snapAt(e.clientX, e.clientY, e.altKey)

    // ---- Measure tools (transient) ----
    if (tool === 'measure-distance') {
      // Need a view to convert page-mm → model-mm correctly. If no view at
      // the click point we can still measure on the page in raw page-mm.
      const view = sheetViews.find((v) => v.id === sn.viewId) || null
      const scale = view?.scale ?? 1
      if (!measure || measure.kind !== 'distance' || measure.b) {
        // Start fresh.
        setMeasure({ kind: 'distance', viewId: sn.viewId, a: { x: sn.x, y: sn.y }, scale })
      } else {
        // Lock the second point.
        setMeasure({ ...measure, b: { x: sn.x, y: sn.y } })
      }
      return
    }
    if (tool === 'measure-angle') {
      if (!measure || measure.kind !== 'angle' || measure.b) {
        setMeasure({ kind: 'angle', viewId: sn.viewId, vertex: { x: sn.x, y: sn.y } })
      } else if (!measure.a) {
        setMeasure({ ...measure, a: { x: sn.x, y: sn.y } })
      } else {
        setMeasure({ ...measure, b: { x: sn.x, y: sn.y } })
      }
      return
    }

    // ---- Annotation tools ----
    if (tool === 'text' || tool === 'note') {
      // Open inline input at the click point. Capture screen-px coordinates
      // at click time so the InlineTextInput component never has to read
      // svgRef during render (lint: react-hooks/refs).
      setTextInput({
        kind: tool, viewId: sn.viewId, x: sn.x, y: sn.y,
        screenLeft: e.clientX, screenTop: e.clientY,
        value: '',
      })
      return
    }
    if (tool === 'leader') {
      if (!annDraft || annDraft.kind !== 'leader-draft') {
        setAnnDraft({ kind: 'leader-draft', viewId: sn.viewId, from: { x: sn.x, y: sn.y } })
      } else {
        setTextInput({
          kind: 'leader',
          viewId: annDraft.viewId,
          x: sn.x, y: sn.y,
          from: annDraft.from,
          to: { x: sn.x, y: sn.y },
          screenLeft: e.clientX, screenTop: e.clientY,
          value: '',
        })
        setAnnDraft(null)
      }
      return
    }
    if (tool === 'polyline') {
      if (!annDraft || annDraft.kind !== 'polyline-draft') {
        setAnnDraft({ kind: 'polyline-draft', viewId: sn.viewId, points: [{ x: sn.x, y: sn.y }] })
      } else {
        setAnnDraft({ ...annDraft, points: [...annDraft.points, { x: sn.x, y: sn.y }] })
      }
      return
    }
    if (tool === 'rect' || tool === 'ann-circle') {
      // These two use mousedown/mouseup drag — single clicks are no-op.
      return
    }
    // ---- Symbols: single click places. The symbol is anchored at the click
    // point; user can edit text/params via the property panel.
    if (SYMBOL_TOOLS.has(tool)) {
      if (tool === 'balloon') {
        onAddAnnotation?.({
          kind: 'balloon',
          view_id: sn.viewId || undefined,
          cx: sn.x, cy: sn.y,
          number: '1',
        })
      } else {
        onAddSymbol?.({
          kind: tool,
          view_id: sn.viewId || undefined,
          position: { x: sn.x, y: sn.y },
          params: tool === 'gdt' ? { characteristic: '⊥', tolerance: '0.1', datums: 'A' }
            : tool === 'weld' ? { text: '5', side: 'arrow' }
            : { ra: '3.2' },
        })
      }
      onResetTool?.()
      return
    }

    // Centerline tool: 2 clicks → custom centerline between two points.
    if (tool === 'centerline') {
      if (!annDraft || annDraft.kind !== 'centerline-draft') {
        setAnnDraft({ kind: 'centerline-draft', viewId: sn.viewId, p1: { x: sn.x, y: sn.y } })
      } else {
        onAddCenterline?.({
          view_id: annDraft.viewId || undefined,
          custom: { p1: annDraft.p1, p2: { x: sn.x, y: sn.y } },
          style: 'center_dashed',
        })
        setAnnDraft(null)
        onResetTool?.()
      }
      return
    }

    // Break tool: 2 clicks → break line between two points (zigzag).
    if (tool === 'break') {
      if (!annDraft || annDraft.kind !== 'break-draft') {
        setAnnDraft({ kind: 'break-draft', viewId: sn.viewId, p1: { x: sn.x, y: sn.y } })
      } else {
        const p1 = annDraft.p1
        const p2 = { x: sn.x, y: sn.y }
        const dx = Math.abs(p2.x - p1.x)
        const dy = Math.abs(p2.y - p1.y)
        onAddBreak?.({
          view_id: annDraft.viewId || undefined,
          p1, p2,
          orientation: dx >= dy ? 'horizontal' : 'vertical',
          style: 'zigzag',
        })
        setAnnDraft(null)
        onResetTool?.()
      }
      return
    }

    // ---- Dimension authoring ----
    // Fall through to dimension flow for remaining tools.
    if (!sn.viewId) return

    // Angular tool: 3 clicks → vertex, a (first arm), b (second arm).
    if (tool === 'angular') {
      if (!draft) {
        setDraft({ stage: 1, kind: 'angular', viewId: sn.viewId, vertex: { x: sn.x, y: sn.y } })
        return
      }
      if (draft.stage === 1) {
        setDraft({ ...draft, stage: 2, a: { x: sn.x, y: sn.y } })
        return
      }
      if (draft.stage === 2) {
        const b = { x: sn.x, y: sn.y }
        const r = Math.max(4, Math.hypot(b.x - draft.vertex.x, b.y - draft.vertex.y))
        onAddDimension?.({
          view_id: draft.viewId,
          kind: 'angular',
          vertex: draft.vertex,
          a: draft.a,
          b,
          radius: r,
        })
        setDraft(null)
        onResetTool?.()
      }
      return
    }

    // Multi-pick dimensions (baseline / chain / ordinate). Click each pick;
    // double-click commits.
    if (MULTI_POINT_DIMS.has(tool)) {
      if (!draft) {
        setDraft({ stage: 1, kind: tool, viewId: sn.viewId, picks: [{ x: sn.x, y: sn.y }] })
      } else {
        // Append a pick. Stay in this state until double-click.
        setDraft({ ...draft, picks: [...(draft.picks || []), { x: sn.x, y: sn.y }] })
      }
      return
    }

    // Linear / aligned / radius / diameter — 3 clicks: a, b, offset.
    if (TWO_POINT_DIMS.has(tool)) {
      if (!draft) {
        setDraft({ stage: 1, viewId: sn.viewId, a: { x: sn.x, y: sn.y } })
        return
      }
      if (draft.stage === 1) {
        setDraft({ ...draft, stage: 2, b: { x: sn.x, y: sn.y } })
        return
      }
      if (draft.stage === 2) {
        const offset = perpendicularOffset(draft.a, draft.b, [sn.page[0], sn.page[1]])
        onAddDimension?.({
          view_id: draft.viewId,
          kind: tool,
          a: draft.a,
          b: draft.b,
          offset,
        })
        setDraft(null)
        onResetTool?.()
      }
    }
  }, [
    tool, draft, setDraft, snapAt, sheetViews, measure, annDraft,
    onAddDimension, onAddAnnotation, onAddCenterline, onAddBreak, onAddSymbol,
    onSelectDimension, onSelectAnnotation, onResetTool,
    setMeasure, setAnnDraft,
  ])

  // Double-click commits a polyline-draft (≥2 points needed) OR a multi-pick
  // dimension-draft (baseline/chain/ordinate). Order matters: dimension
  // drafts are caught first since they live in `draft` not `annDraft`.
  const onSvgDoubleClick = useCallback((e) => {
    if (draft && MULTI_POINT_DIMS.has(tool)) {
      const picks = draft.picks || []
      if (picks.length < 2) {
        if (tool === 'ordinate' && picks.length >= 1) {
          // Ordinate is OK with a single pick — no need to abort.
        } else {
          setDraft(null); return
        }
      }
      e.preventDefault()
      const payload = {
        view_id: draft.viewId,
        kind: tool,
        picks,
      }
      if (tool === 'ordinate') {
        // Use the first pick as the implied origin unless explicitly set.
        payload.origin = draft.origin || picks[0]
      }
      onAddDimension?.(payload)
      setDraft(null)
      onResetTool?.()
      return
    }
    if (tool !== 'polyline' || !annDraft || annDraft.kind !== 'polyline-draft') return
    if ((annDraft.points || []).length < 2) {
      // Cancel — single-point polyline isn't useful.
      setAnnDraft(null)
      return
    }
    e.preventDefault()
    onAddAnnotation?.({
      kind: 'polyline',
      view_id: annDraft.viewId || undefined,
      points: annDraft.points,
    })
    setAnnDraft(null)
    onResetTool?.()
  }, [tool, annDraft, onAddAnnotation, onResetTool, setAnnDraft])

  // Mousedown for rect/circle annotations + annotation drag in pointer mode.
  const onSvgMouseDown = useCallback((e) => {
    if (panRef.current.active || spaceRef.current) return
    if (tool === 'rect') {
      const sn = snapAt(e.clientX, e.clientY, e.altKey)
      setAnnDraft({ kind: 'rect-draft', viewId: sn.viewId, start: { x: sn.x, y: sn.y }, end: { x: sn.x, y: sn.y } })
    } else if (tool === 'ann-circle') {
      const sn = snapAt(e.clientX, e.clientY, e.altKey)
      setAnnDraft({ kind: 'circle-draft', viewId: sn.viewId, center: { x: sn.x, y: sn.y }, radius: 0 })
    }
  }, [tool, snapAt, setAnnDraft])

  const onSvgMouseUp = useCallback((e) => {
    // Commit rect/circle drafts on mouseup.
    if (annDraft?.kind === 'rect-draft') {
      const sn = snapAt(e.clientX, e.clientY, e.altKey)
      const x = Math.min(annDraft.start.x, sn.x)
      const y = Math.min(annDraft.start.y, sn.y)
      const width = Math.abs(sn.x - annDraft.start.x)
      const height = Math.abs(sn.y - annDraft.start.y)
      if (width > 0.5 && height > 0.5) {
        onAddAnnotation?.({
          kind: 'rect',
          view_id: annDraft.viewId || undefined,
          x, y, width, height,
        })
      }
      setAnnDraft(null)
      onResetTool?.()
    } else if (annDraft?.kind === 'circle-draft') {
      const sn = snapAt(e.clientX, e.clientY, e.altKey)
      const r = Math.hypot(sn.x - annDraft.center.x, sn.y - annDraft.center.y)
      if (r > 0.5) {
        onAddAnnotation?.({
          kind: 'circle',
          view_id: annDraft.viewId || undefined,
          cx: annDraft.center.x,
          cy: annDraft.center.y,
          r,
        })
      }
      setAnnDraft(null)
      onResetTool?.()
    } else if (annDraft?.kind === 'drag-ann') {
      // Drag finished — already mutated through pointermove, just clear.
      setAnnDraft(null)
    }
  }, [annDraft, snapAt, onAddAnnotation, onResetTool, setAnnDraft])

  const onSvgPointerMove = useCallback((e) => {
    onPointerMove(e)
    const [px, py] = clientToMm(e.clientX, e.clientY)
    setHudPos({ x: px, y: py })
    if (panRef.current.active) return

    // Live snap indicator (only for tools that snap; Alt disables snapping).
    if (isSnappingTool(tool) && !e.altKey) {
      const view = findViewAt(px, py)
      const snap = findSnap(px, py, view)
      // Only show a marker when an actual hard feature was hit — kind='free'
      // means the cursor is in empty space and we shouldn't decorate it.
      if (snap && snap.kind && snap.kind !== 'free') {
        setHover(snap)
      } else {
        setHover(null)
      }
    } else {
      setHover(null)
    }

    // Live update for in-progress annotation drafts (rect/circle drag).
    if (annDraft?.kind === 'rect-draft') {
      setAnnDraft({ ...annDraft, end: { x: px, y: py } })
    } else if (annDraft?.kind === 'circle-draft') {
      setAnnDraft({ ...annDraft, radius: Math.hypot(px - annDraft.center.x, py - annDraft.center.y) })
    } else if (annDraft?.kind === 'drag-ann') {
      // Translate or modify the dragged annotation.
      const dx = px - annDraft.startMm.x
      const dy = py - annDraft.startMm.y
      const ann = annDraft.startAnn
      let patch = null
      if (annDraft.mode === 'move') {
        patch = translateAnnotation(ann, dx, dy)
      } else if (annDraft.mode === 'handle') {
        patch = transformAnnotation(ann, annDraft.handleIdx, dx, dy, { x: px, y: py })
      }
      if (patch) onUpdateAnnotation?.(ann.id, patch)
    }
  }, [tool, clientToMm, findViewAt, findSnap, onPointerMove, annDraft, onUpdateAnnotation, setAnnDraft])

  const onSvgMouseLeave = useCallback((e) => {
    onPointerUp(e)
    setHudPos(null)
    setHover(null)
  }, [onPointerUp])

  // Title-block layout, computed from frame.
  const block = useMemo(
    () => titleBlockLayout(frame.size, frame.orientation, frame.template),
    [frame.size, frame.orientation, frame.template],
  )

  const annotations = useMemo(() => sheetAnns, [sheetAnns])

  // Hatch patterns required for any section view on the active sheet.
  const hatchPatterns = useMemo(() => {
    const m = new Map()
    for (const v of sheetViews) {
      if (!v.is_section) continue
      const sp = v.hatch_spacing || 2.5
      const ang = v.hatch_angle ?? 45
      const id = hatchPatternId(sp, ang)
      if (!m.has(id)) m.set(id, hatchPatternDef(sp, ang))
    }
    return m
  }, [sheetViews])

  // Auto-detect centerlines for each view (lightweight: only when no
  // user-placed centerlines exist for that view, to avoid duplicates).
  const autoCenterlines = useMemo(() => {
    const out = []
    const userByView = new Map()
    for (const c of sheetCenters) {
      if (c.view_id) userByView.set(c.view_id, true)
    }
    for (const v of sheetViews) {
      if (userByView.has(v.id)) continue
      const proj = projectedByView.get(v.id)
      if (!proj) continue
      const segs = proj.polylines
        .filter((p) => p.kind === 'silhouette' || p.kind === 'visible')
        .map((p) => p.points)
      const found = detectCenterlines(segs)
      // Convert from projection-local model coords to page-mm via the view's
      // projected bbox + scale.
      const minU = proj.bbox?.min?.[0] ?? 0
      const minV = proj.bbox?.min?.[1] ?? 0
      const tx = v.position[0]
      const ty = v.position[1]
      for (const c of found) {
        out.push({
          id: `auto-${v.id}-${c.cx.toFixed(1)}-${c.cy.toFixed(1)}`,
          view_id: v.id,
          auto: true,
          cx: tx + (c.cx - minU) / v.scale,
          cy: ty + (c.cy - minV) / v.scale,
          r: c.r / v.scale,
          style: 'center_dashed',
        })
      }
    }
    return out
  }, [sheetCenters, sheetViews, projectedByView])

  // Begin dragging an annotation in pointer mode (move). Called from a
  // mousedown handler on the annotation's group.
  const beginAnnotationDrag = useCallback((annId, e) => {
    if (tool !== 'pointer') return
    e.stopPropagation()
    onSelectAnnotation?.(annId)
    const ann = annotations.find((a) => a.id === annId)
    if (!ann) return
    const [px, py] = clientToMm(e.clientX, e.clientY)
    setAnnDraft({
      kind: 'drag-ann',
      annId,
      mode: 'move',
      startMm: { x: px, y: py },
      startAnn: ann,
    })
  }, [tool, onSelectAnnotation, annotations, clientToMm, setAnnDraft])

  const beginHandleDrag = useCallback((annId, handleIdx, e) => {
    if (tool !== 'pointer') return
    e.stopPropagation()
    const ann = annotations.find((a) => a.id === annId)
    if (!ann) return
    const [px, py] = clientToMm(e.clientX, e.clientY)
    setAnnDraft({
      kind: 'drag-ann',
      annId,
      mode: 'handle',
      handleIdx,
      startMm: { x: px, y: py },
      startAnn: ann,
    })
  }, [tool, annotations, clientToMm, setAnnDraft])

  return (
    <div className="w-full h-full bg-ink-950 overflow-hidden relative">
      <svg
        ref={svgRef}
        width="100%"
        height="100%"
        viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
        preserveAspectRatio="xMidYMid meet"
        onPointerDown={onPointerDown}
        onPointerMove={onSvgPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onSvgMouseLeave}
        onMouseDown={onSvgMouseDown}
        onMouseUp={onSvgMouseUp}
        onWheel={onWheel}
        onClick={onSvgClick}
        onDoubleClick={onSvgDoubleClick}
        style={{
          cursor: tool !== 'pointer' ? 'crosshair' : (spaceHeld ? 'grab' : 'default'),
          touchAction: 'none',
          background: '#1c2030',
        }}
      >
        {/* Marker for arrowheads on dimension lines. */}
        <defs>
          <marker id="dim-arrow" viewBox="0 0 10 10" refX="10" refY="5"
                  markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={DIM_STROKE} />
          </marker>
          <marker id="dim-arrow-sel" viewBox="0 0 10 10" refX="10" refY="5"
                  markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={DIM_SELECTED} />
          </marker>
          <marker id="ann-arrow" viewBox="0 0 10 10" refX="10" refY="5"
                  markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={ANN_STROKE} />
          </marker>
          <marker id="ann-arrow-sel" viewBox="0 0 10 10" refX="10" refY="5"
                  markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={ANN_SELECTED_STROKE} />
          </marker>
          {/* Hatch patterns for section views. */}
          {Array.from(hatchPatterns.values()).map((p) => (
            <pattern
              key={p.id}
              id={p.id}
              width={p.width}
              height={p.height}
              patternUnits={p.patternUnits}
              patternTransform={p.patternTransform}
            >
              <line
                x1={p.line.x1} y1={p.line.y1}
                x2={p.line.x2} y2={p.line.y2}
                stroke={p.line.stroke}
                strokeWidth={p.line.strokeWidth}
              />
            </pattern>
          ))}
        </defs>

        {/* Sheet rect. */}
        <rect
          x={0} y={0} width={sheetW} height={sheetH}
          fill={SHEET_FILL} stroke={SHEET_BORDER}
          strokeWidth={0.3} vectorEffect="non-scaling-stroke"
        />

        {/* Margin guide (thin grey rectangle just inside the sheet). */}
        <rect
          x={5} y={5} width={sheetW - 10} height={sheetH - 10}
          fill="none" stroke="#dde2eb"
          strokeWidth={0.2} vectorEffect="non-scaling-stroke"
        />

        {/* Views. */}
        {sheetViews.map((view) => (
          <ViewGroup
            key={view.id}
            view={view}
            projection={projectedByView.get(view.id)}
          />
        ))}

        {/* Centerlines (auto-detected + user-placed). Rendered after views so
            they sit on top of the projected geometry. */}
        {[...autoCenterlines, ...sheetCenters].map((c) => {
          // Auto entries already carry cx/cy/r in page-mm; user entries may
          // have either custom {p1,p2} or a circle ref.
          if (c.cx != null && c.r != null) {
            // Cross + circle pair.
            return (
              <g key={c.id} pointerEvents="none">
                <circle
                  cx={c.cx} cy={c.cy} r={c.r}
                  fill="none" stroke={DIM_STROKE} strokeWidth={0.2}
                  strokeDasharray={CENTER_DASH}
                  vectorEffect="non-scaling-stroke"
                />
                <line x1={c.cx - c.r * 1.2} y1={c.cy} x2={c.cx + c.r * 1.2} y2={c.cy}
                  stroke={DIM_STROKE} strokeWidth={0.18}
                  strokeDasharray={CENTER_DASH}
                  vectorEffect="non-scaling-stroke" />
                <line x1={c.cx} y1={c.cy - c.r * 1.2} x2={c.cx} y2={c.cy + c.r * 1.2}
                  stroke={DIM_STROKE} strokeWidth={0.18}
                  strokeDasharray={CENTER_DASH}
                  vectorEffect="non-scaling-stroke" />
              </g>
            )
          }
          if (c.custom?.p1 && c.custom?.p2) {
            return (
              <line key={c.id}
                x1={c.custom.p1.x} y1={c.custom.p1.y}
                x2={c.custom.p2.x} y2={c.custom.p2.y}
                stroke={DIM_STROKE} strokeWidth={0.25}
                strokeDasharray={CENTER_DASH}
                vectorEffect="non-scaling-stroke" />
            )
          }
          return null
        })}

        {/* Break lines. Render zigzag polylines per stored break entry. */}
        {sheetBreaks.map((b) => {
          if (!b.p1 || !b.p2) return null
          const pts = zigzagPoints(b.p1, b.p2, { peaks: 4, amplitude: 1.4 })
          const ptStr = pts.map((p) => `${p.x},${p.y}`).join(' ')
          return (
            <polyline key={b.id} points={ptStr}
              fill="none" stroke={ANN_STROKE} strokeWidth={0.35}
              vectorEffect="non-scaling-stroke" />
          )
        })}

        {/* Title block. */}
        <TitleBlock block={block} frame={frame} />

        {/* Scale bar — bottom-left corner of the sheet. Reflects the active
            sheet's scale_label, falling back to the largest view's scale. */}
        <ScaleBar frame={frame} sheetW={sheetW} sheetH={sheetH} views={sheetViews} />

        {/* Dimensions. */}
        {sheetDims.map((d) => (
          <DimensionGlyph
            key={d.id}
            dim={d}
            view={sheetViews.find((v) => v.id === d.view_id)}
            selected={d.id === selectedDimensionId}
            onSelect={(e) => {
              e.stopPropagation()
              onSelectDimension?.(d.id)
              onSelectAnnotation?.(null)
            }}
            onDelete={() => onDeleteDimension?.(d.id)}
          />
        ))}

        {/* Annotations — rendered after views so they sit on top. */}
        {annotations.map((a) => (
          <AnnotationGlyph
            key={a.id}
            ann={a}
            selected={a.id === selectedAnnotationId}
            onSelect={(e) => {
              e.stopPropagation()
              onSelectAnnotation?.(a.id)
              onSelectDimension?.(null)
            }}
            onDragStart={(e) => beginAnnotationDrag(a.id, e)}
            onHandleDown={(idx, e) => beginHandleDrag(a.id, idx, e)}
          />
        ))}

        {/* Symbols — surface_finish / weld / gdt. */}
        {sheetSymbols.map((s) => (
          <SymbolGlyph
            key={s.id}
            sym={s}
            selected={s.id === selectedAnnotationId}
            onSelect={(e) => {
              e.stopPropagation()
              onSelectAnnotation?.(s.id)
              onSelectDimension?.(null)
            }}
          />
        ))}

        {/* In-progress dimension preview. */}
        {draft && (
          <DraftDimension
            draft={draft}
            hover={hover}
          />
        )}

        {/* In-progress annotation preview. */}
        {annDraft && annDraft.kind !== 'drag-ann' && (
          <DraftAnnotation draft={annDraft} hover={hover} />
        )}

        {/* Transient measurement overlay. */}
        {measure && (
          <MeasureOverlay
            measure={measure}
            hover={hover}
            views={sheetViews}
          />
        )}

        {/* Snap indicator. */}
        {hover && hover.kind && hover.kind !== 'free' && (
          <SnapMarker hover={hover} />
        )}
      </svg>

      {/* Inline text input overlay for text/leader annotations. Rendered as
          a positioned DOM input (not SVG) so the user gets native typing UX.
          Position is captured at click time as screen-px so the component
          never has to read the SVG ref during render. */}
      {textInput && (
        <InlineTextInput
          textInput={textInput}
          containerRef={svgRef}
          onCommit={(value) => {
            const v = (value || '').trim()
            if (v) {
              if (textInput.kind === 'text') {
                onAddAnnotation?.({
                  kind: 'text',
                  view_id: textInput.viewId || undefined,
                  x: textInput.x,
                  y: textInput.y,
                  text: v,
                })
              } else if (textInput.kind === 'note') {
                onAddAnnotation?.({
                  kind: 'note',
                  view_id: textInput.viewId || undefined,
                  x: textInput.x,
                  y: textInput.y,
                  text: v,
                })
              } else if (textInput.kind === 'leader') {
                onAddAnnotation?.({
                  kind: 'leader',
                  view_id: textInput.viewId || undefined,
                  from: textInput.from,
                  to: textInput.to,
                  text: v,
                })
              }
            }
            setTextInput(null)
            onResetTool?.()
          }}
          onCancel={() => {
            setTextInput(null)
            onResetTool?.()
          }}
        />
      )}

      {/* Cursor coordinate readout — bottom-left, monospace. */}
      {hudPos && (
        <div
          className="absolute bottom-3 left-3 z-10 px-2 py-1 rounded text-[10px] font-mono text-kerf-300 pointer-events-none"
          style={{ background: 'rgba(0,0,0,0.6)' }}
        >
          {`x: ${hudPos.x.toFixed(2)}  y: ${hudPos.y.toFixed(2)}`}
        </div>
      )}

      {/* Hint chip at the bottom — explains the current tool's flow. */}
      <div className="absolute bottom-3 left-1/2 -translate-x-1/2 px-3 py-1 rounded-md bg-ink-900/85 border border-ink-700 text-[11px] font-mono text-kerf-300 backdrop-blur shadow-lg">
        {toolHint(tool, draft, measure, annDraft)}
      </div>

      {/* Sheet tab bar — bottom edge. Only renders when there's more than one
          sheet OR when a sheet handler is wired (so a single-sheet drawing
          can still surface the "+ New sheet" button). */}
      {(sheets.length > 1 || onAddSheet) && (
        <div className="absolute bottom-0 left-0 right-0 z-10 flex items-center gap-1 px-3 py-1.5 bg-ink-900/85 border-t border-ink-700 backdrop-blur text-[11px]">
          {sheets.map((s, i) => (
            <button
              key={s.id || i}
              type="button"
              onClick={() => onSelectSheet?.(i)}
              onDoubleClick={() => {
                if (sheets.length > 1 && confirm(`Delete sheet ${i + 1}?`)) onRemoveSheet?.(i)
              }}
              title={s.frame?.title || `Sheet ${i + 1}`}
              className={`px-2 py-0.5 rounded font-mono transition-colors ${
                i === sheetIdx
                  ? 'bg-kerf-300 text-ink-950'
                  : 'bg-ink-800 text-ink-300 hover:bg-ink-700 hover:text-kerf-300 border border-ink-700'
              }`}
            >
              {s.frame?.title?.slice(0, 24) || `Sheet ${i + 1}`}
            </button>
          ))}
          {onAddSheet && (
            <button
              type="button"
              onClick={() => onAddSheet?.()}
              title="New sheet"
              className="ml-1 p-1 rounded bg-ink-800 text-ink-400 hover:text-kerf-300 hover:bg-ink-700 border border-ink-700"
            >
              <Plus size={11} />
            </button>
          )}
          {sheets.length > 1 && (
            <button
              type="button"
              onClick={() => onRemoveSheet?.(sheetIdx)}
              title="Delete this sheet"
              className="ml-1 p-1 rounded bg-ink-800 text-ink-400 hover:text-amber-300 hover:bg-ink-700 border border-ink-700"
            >
              <XIcon size={11} />
            </button>
          )}
        </div>
      )}
    </div>
  )
})

export default DrawingView

// ---------------------------------------------------------------------------
// Sub-components

function ViewGroup({ view, projection }) {
  if (!projection || !projection.bbox) {
    // Empty placeholder so the view still has a hit-box on the sheet.
    return (
      <g>
        <rect x={view.position[0]} y={view.position[1]} width={60} height={40}
              fill="none" stroke="#dde2eb" strokeDasharray="2,2"
              strokeWidth={0.2} vectorEffect="non-scaling-stroke" />
        <text
          x={view.position[0] + 30} y={view.position[1] + 22}
          textAnchor="middle"
          fontSize={3} fill="#7782a3"
          fontFamily="ui-monospace, Menlo, monospace"
        >
          (empty)
        </text>
      </g>
    )
  }
  // Translate so projected bbox.min lands at view.position, scaled by 1/scale.
  const { min, max } = projection.bbox
  const tx = view.position[0]
  const ty = view.position[1]
  const sw = 1 / view.scale
  return (
    <g transform={`translate(${tx} ${ty}) scale(${sw} ${sw}) translate(${-min[0]} ${-min[1]})`}>
      {/* Section hatch — fills the projected bbox with a 45° pattern. We use
          a coarse rect rather than computing per-face cut polygons; the
          projected silhouette/visible edges drawn over the top mask it where
          it "shouldn't" appear. v1 trade-off: simple + fast, looks right for
          most parts. */}
      {view.is_section && (
        <rect
          x={min[0]} y={min[1]}
          width={max[0] - min[0]} height={max[1] - min[1]}
          fill={`url(#${hatchPatternId(view.hatch_spacing || 2.5, view.hatch_angle ?? 45)})`}
          stroke="none"
          opacity={0.65}
        />
      )}
      {projection.polylines.length === 0 && (
        // Sources resolved but the projector found no projectable edges
        // (e.g. all edges classified as smooth tessellation noise, or the
        // part has no real BREP edges). Emit a placeholder so the user
        // knows the view is "alive" but empty.
        <g>
          <rect x={min[0]} y={min[1]}
            width={Math.max(40 * view.scale, max[0] - min[0])}
            height={Math.max(20 * view.scale, max[1] - min[1])}
            fill="none" stroke="#dde2eb" strokeDasharray="2,2"
            strokeWidth={0.2} vectorEffect="non-scaling-stroke" />
          <g transform={`translate(${(min[0] + max[0]) / 2} ${(min[1] + max[1]) / 2}) scale(${view.scale} ${view.scale})`}>
            <text x={0} y={0} textAnchor="middle"
              fontSize={3} fill="#7782a3"
              fontFamily="ui-monospace, Menlo, monospace">
              0 edges projected
            </text>
          </g>
        </g>
      )}
      {projection.polylines.map((pl, i) => {
        const stroke = pl.kind === 'hidden' ? HIDDEN_STROKE
          : pl.kind === 'silhouette' ? SILHOUETTE_STROKE
          : VISIBLE_STROKE
        // strokeWidth + dasharray are in PAGE-MM directly. With
        // `vector-effect="non-scaling-stroke"` the SVG renderer factors out
        // the local scale(1/view.scale) transform when computing both, so
        // we don't pre-multiply by view.scale (doing so makes lines
        // invisibly thin at small auto-fit scales).
        const w = pl.kind === 'hidden' ? HIDDEN_W
          : pl.kind === 'silhouette' ? SILHOUETTE_W
          : VISIBLE_W
        const dash = pl.kind === 'hidden' ? '1.6,1.2' : null
        return (
          <line
            key={i}
            x1={pl.points[0][0]} y1={pl.points[0][1]}
            x2={pl.points[1][0]} y2={pl.points[1][1]}
            stroke={stroke}
            strokeWidth={w}
            strokeDasharray={dash || undefined}
            vectorEffect="non-scaling-stroke"
          />
        )
      })}
      {/* View label below the bbox. Drawn in *page-mm* via an inverse scale
          so the text doesn't get squashed when view.scale ≠ 1. */}
      <ViewLabel view={view} bbox={projection.bbox} />
    </g>
  )
}

function ViewLabel({ view, bbox }) {
  // We're inside a transformed group already (model-units). Place the text
  // anchor at bbox.min.x, bbox.max.y + small gap; counter-scale so the text
  // appears at constant page-mm size regardless of view.scale.
  const x = bbox.min[0]
  const y = bbox.max[1] + 4 * view.scale
  const cs = view.scale // counter-scale: outer scale is 1/view.scale, so we multiply by view.scale to neutralize
  const labelText = `${view.label || projectionLabel(view.projection)} · ${formatScale(view.scale)}`
  return (
    <g transform={`translate(${x} ${y}) scale(${cs} ${cs})`}>
      <text
        x={0} y={0}
        fontSize={3} fill="#1a1f2a"
        fontFamily="ui-monospace, Menlo, monospace"
      >
        {labelText}
      </text>
    </g>
  )
}

function TitleBlock({ block, frame }) {
  const valueOf = (key) => frame[key] || ''
  return (
    <g transform={`translate(${block.x} ${block.y})`}>
      <rect
        x={0} y={0} width={block.w} height={block.h}
        fill="#fafbfd" stroke={SHEET_BORDER}
        strokeWidth={0.4} vectorEffect="non-scaling-stroke"
      />
      {block.cells.map((c, i) => (
        <g key={i}>
          <rect
            x={c.x} y={c.y} width={c.w} height={c.h}
            fill="none" stroke={SHEET_BORDER}
            strokeWidth={0.25} vectorEffect="non-scaling-stroke"
          />
          <text
            x={c.x + 1} y={c.y + 2.4}
            fontSize={1.6} fill="#5a6478"
            fontFamily="ui-sans-serif, system-ui"
            style={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}
          >
            {c.label}
          </text>
          <text
            x={c.x + c.w / 2} y={c.y + c.h / 2 + 1.4}
            textAnchor="middle"
            fontSize={c.key === 'title' ? 4 : 3}
            fontWeight={c.key === 'title' ? 600 : 400}
            fill={SHEET_BORDER}
            fontFamily="ui-monospace, Menlo, monospace"
          >
            {valueOf(c.key)}
          </text>
        </g>
      ))}
    </g>
  )
}

function DimensionGlyph({ dim, view, selected, onSelect, onDelete }) {
  if (!view) return null
  const stroke = selected ? DIM_SELECTED : DIM_STROKE
  const arrow = selected ? 'url(#dim-arrow-sel)' : 'url(#dim-arrow)'

  if (dim.kind === 'linear' || dim.kind === 'aligned') {
    const { ax, ay, bx, by, lx1, ly1, lx2, ly2, mx, my, valueText, perp } =
      computeLinearDim(dim, view)
    const labelText = hasManualOverride(dim) ? (dim.value || dim.text_override) : valueText
    const angle = Math.atan2(perp[1], perp[0]) * 180 / Math.PI
    return (
      <g
        onClick={onSelect}
        onContextMenu={(e) => { e.preventDefault(); if (selected) onDelete?.() }}
        style={{ cursor: 'pointer' }}
      >
        {/* Extension lines from a/b out to the dim line. */}
        <line x1={ax} y1={ay} x2={lx1} y2={ly1}
              stroke={stroke} strokeWidth={0.2} vectorEffect="non-scaling-stroke" />
        <line x1={bx} y1={by} x2={lx2} y2={ly2}
              stroke={stroke} strokeWidth={0.2} vectorEffect="non-scaling-stroke" />
        {/* Dim line with double-ended arrows. */}
        <line x1={lx1} y1={ly1} x2={lx2} y2={ly2}
              stroke={stroke} strokeWidth={0.3} vectorEffect="non-scaling-stroke"
              markerStart={arrow} markerEnd={arrow} />
        {/* Value text along the dim line. */}
        <text
          x={mx} y={my - 0.8}
          textAnchor="middle"
          transform={`rotate(${angle > 90 || angle < -90 ? angle + 180 : angle} ${mx} ${my})`}
          fontSize={DIM_TEXT_MM} fill={stroke}
          fontFamily="ui-monospace, Menlo, monospace"
          fontWeight={600}
        >
          {labelText}
        </text>
        {hasManualOverride(dim) && <ManualFlag x={mx + 7} y={my - 0.4} stroke={stroke} />}
      </g>
    )
  }
  if (dim.kind === 'angular') {
    const ang = computeAngularDim(dim)
    if (!ang) return null
    const { cx, cy, r, a0, a1, mx, my, valueText, ax, ay, bx, by } = ang
    const labelText = hasManualOverride(dim) ? (dim.value || dim.text_override) : valueText
    // Choose the shorter sweep direction for "large-arc" / "sweep" SVG flags.
    let delta = a1 - a0
    while (delta > Math.PI) delta -= 2 * Math.PI
    while (delta < -Math.PI) delta += 2 * Math.PI
    const large = Math.abs(delta) > Math.PI ? 1 : 0
    const sweep = delta >= 0 ? 1 : 0
    const x0 = cx + r * Math.cos(a0)
    const y0 = cy + r * Math.sin(a0)
    const x1 = cx + r * Math.cos(a1)
    const y1 = cy + r * Math.sin(a1)
    // Arm "extension" lines from vertex out to (and just past) the arc.
    const extPad = 1.5 // mm past the arc, like linear extension overshoot
    const armEnd = (px, py) => {
      const dx = px - cx, dy = py - cy
      const L = Math.hypot(dx, dy) || 1
      const ext = Math.max(r + extPad, L)
      return [cx + dx / L * ext, cy + dy / L * ext]
    }
    const [ex1, ey1] = armEnd(ax, ay)
    const [ex2, ey2] = armEnd(bx, by)
    return (
      <g onClick={onSelect} onContextMenu={(e) => { e.preventDefault(); if (selected) onDelete?.() }} style={{ cursor: 'pointer' }}>
        {/* Extension lines from vertex toward each arm endpoint. */}
        <line x1={cx} y1={cy} x2={ex1} y2={ey1}
              stroke={stroke} strokeWidth={0.2} vectorEffect="non-scaling-stroke" />
        <line x1={cx} y1={cy} x2={ex2} y2={ey2}
              stroke={stroke} strokeWidth={0.2} vectorEffect="non-scaling-stroke" />
        {/* Arc with arrowheads at each end. */}
        <path d={`M ${x0} ${y0} A ${r} ${r} 0 ${large} ${sweep} ${x1} ${y1}`}
              fill="none" stroke={stroke} strokeWidth={0.3}
              vectorEffect="non-scaling-stroke"
              markerStart={arrow} markerEnd={arrow} />
        <text x={mx} y={my} textAnchor="middle" fontSize={DIM_TEXT_MM}
              fill={stroke} fontFamily="ui-monospace, Menlo, monospace" fontWeight={600}>
          {labelText}
        </text>
      </g>
    )
  }
  if (dim.kind === 'radius' || dim.kind === 'diameter') {
    // a = center, b = point on edge. Leader from center to edge plus prefix.
    const ax = dim.a.x, ay = dim.a.y
    const bx = dim.b.x, by = dim.b.y
    const r = Math.hypot(bx - ax, by - ay) * (view.scale || 1)
    const value = dim.kind === 'diameter' ? 2 * r : r
    const prefix = dim.kind === 'diameter' ? '⌀ ' : 'R '
    const auto = prefix + value.toFixed(2)
    const labelText = hasManualOverride(dim) ? (dim.value || dim.text_override) : auto
    // Leader line goes from b outward by `offset` along the radial direction.
    const dx = bx - ax, dy = by - ay
    const dl = Math.hypot(dx, dy) || 1
    const ux = dx / dl
    const uy = dy / dl
    const lx = bx + ux * Math.max(8, dim.offset || 8)
    const ly = by + uy * Math.max(8, dim.offset || 8)
    return (
      <g onClick={onSelect} onContextMenu={(e) => { e.preventDefault(); if (selected) onDelete?.() }} style={{ cursor: 'pointer' }}>
        {/* For diameter, draw a full diameter line through the center. */}
        {dim.kind === 'diameter' && (
          <line x1={ax - ux * dl} y1={ay - uy * dl} x2={bx} y2={by}
            stroke={stroke} strokeWidth={0.3} vectorEffect="non-scaling-stroke"
            markerStart={arrow} markerEnd={arrow} />
        )}
        {dim.kind === 'radius' && (
          <line x1={ax} y1={ay} x2={bx} y2={by}
            stroke={stroke} strokeWidth={0.3} vectorEffect="non-scaling-stroke"
            markerEnd={arrow} />
        )}
        <line x1={bx} y1={by} x2={lx} y2={ly}
              stroke={stroke} strokeWidth={0.3} vectorEffect="non-scaling-stroke" />
        <text x={lx} y={ly - 1} textAnchor="middle"
              fontSize={DIM_TEXT_MM} fill={stroke}
              fontFamily="ui-monospace, Menlo, monospace" fontWeight={600}>
          {labelText}
        </text>
        {hasManualOverride(dim) && <ManualFlag x={lx} y={ly - 4} stroke={stroke} />}
      </g>
    )
  }
  if (dim.kind === 'baseline' || dim.kind === 'chain') {
    return (
      <g onClick={onSelect} onContextMenu={(e) => { e.preventDefault(); if (selected) onDelete?.() }} style={{ cursor: 'pointer' }}>
        {renderChainOrBaseline(dim, view, stroke, arrow)}
        {hasManualOverride(dim) && (
          <ManualFlag x={(dim.picks?.[0]?.x ?? 0) + 2} y={(dim.picks?.[0]?.y ?? 0) - 4} stroke={stroke} />
        )}
      </g>
    )
  }
  if (dim.kind === 'ordinate') {
    const labels = ordinatePickLabels(dim, view)
    return (
      <g onClick={onSelect} onContextMenu={(e) => { e.preventDefault(); if (selected) onDelete?.() }} style={{ cursor: 'pointer' }}>
        {labels.map((l, i) => (
          <g key={i}>
            <circle cx={l.pick.x} cy={l.pick.y} r={0.6} fill={stroke} />
            <text x={l.pick.x} y={l.pick.y - 2.6} textAnchor="middle"
              fontSize={DIM_TEXT_MM * 0.85} fill={stroke}
              fontFamily="ui-monospace, Menlo, monospace" fontWeight={600}>
              {l.x}
            </text>
            <text x={l.pick.x + 2} y={l.pick.y + 1.2}
              fontSize={DIM_TEXT_MM * 0.85} fill={stroke}
              fontFamily="ui-monospace, Menlo, monospace" fontWeight={600}>
              {l.y}
            </text>
          </g>
        ))}
        {/* Origin marker. */}
        {dim.origin && (
          <g>
            <circle cx={dim.origin.x} cy={dim.origin.y} r={1.4}
              fill="none" stroke={stroke} strokeWidth={0.3}
              vectorEffect="non-scaling-stroke" />
            <line x1={dim.origin.x - 2} y1={dim.origin.y}
              x2={dim.origin.x + 2} y2={dim.origin.y}
              stroke={stroke} strokeWidth={0.25}
              vectorEffect="non-scaling-stroke" />
            <line x1={dim.origin.x} y1={dim.origin.y - 2}
              x2={dim.origin.x} y2={dim.origin.y + 2}
              stroke={stroke} strokeWidth={0.25}
              vectorEffect="non-scaling-stroke" />
          </g>
        )}
        {hasManualOverride(dim) && (
          <ManualFlag x={(dim.picks?.[0]?.x ?? 0) + 2} y={(dim.picks?.[0]?.y ?? 0) - 8} stroke={stroke} />
        )}
      </g>
    )
  }
  return null
}

// Tiny "M" badge drawn next to manual-override dimensions to flag the value
// as user-set (vs. auto-measured). 2.6mm tall, monospaced.
function ManualFlag({ x, y, stroke }) {
  return (
    <g pointerEvents="none">
      <rect x={x - 1.4} y={y - 2.0} width={2.8} height={2.6}
        fill="rgba(255,214,51,0.18)"
        stroke={stroke} strokeWidth={0.15}
        vectorEffect="non-scaling-stroke" />
      <text x={x} y={y - 0.05} textAnchor="middle"
        fontSize={1.6} fill={stroke}
        fontFamily="ui-monospace, Menlo, monospace"
        fontWeight={700}>M</text>
    </g>
  )
}

// Render a baseline or chain dimension chain. Baseline: every segment shares
// picks[0] as its left endpoint. Chain: each segment is picks[i] → picks[i+1].
// Each segment is drawn as a short dim line offset perpendicular by `offset`.
function renderChainOrBaseline(dim, view, stroke, arrow) {
  const picks = dim.picks || []
  if (picks.length < 2) return null
  const offset = Number(dim.offset) || 8
  const scale = view?.scale || 1
  // We use the dominant axis (horizontal vs vertical) of the first segment to
  // choose the direction of the dim line. The offset is perpendicular to that
  // axis. This works for the typical case (a row of holes laid horizontally
  // or vertically) — anything more exotic is handled by mixing user-placed
  // linear dims.
  const dx = picks[picks.length - 1].x - picks[0].x
  const dy = picks[picks.length - 1].y - picks[0].y
  const horiz = Math.abs(dx) >= Math.abs(dy)
  const elems = []
  for (let i = 0; i < picks.length; i++) {
    const p = picks[i]
    // Extension line from each pick.
    if (horiz) {
      elems.push(
        <line key={`ext-${i}`}
          x1={p.x} y1={p.y} x2={p.x} y2={p.y - offset}
          stroke={stroke} strokeWidth={0.2}
          vectorEffect="non-scaling-stroke" />,
      )
    } else {
      elems.push(
        <line key={`ext-${i}`}
          x1={p.x} y1={p.y} x2={p.x + offset} y2={p.y}
          stroke={stroke} strokeWidth={0.2}
          vectorEffect="non-scaling-stroke" />,
      )
    }
  }
  // Each measurement.
  if (dim.kind === 'baseline') {
    const base = picks[0]
    let stack = 0
    for (let i = 1; i < picks.length; i++) {
      stack += 4
      const lvl = offset + stack
      const a = base, b = picks[i]
      // Baseline dim line at the stacked level.
      const y1 = horiz ? base.y - lvl : base.y
      const x1 = horiz ? base.x : base.x + lvl
      const y2 = horiz ? b.y - lvl : b.y
      const x2 = horiz ? b.x : b.x + lvl
      const d = (horiz ? (b.x - base.x) : (b.y - base.y)) * scale
      const mx = (x1 + x2) / 2
      const my = (y1 + y2) / 2
      elems.push(
        <g key={`b-${i}`}>
          <line x1={x1} y1={y1} x2={x2} y2={y2}
            stroke={stroke} strokeWidth={0.3}
            vectorEffect="non-scaling-stroke"
            markerStart={arrow} markerEnd={arrow} />
          <text x={mx} y={my - 0.6} textAnchor="middle"
            fontSize={DIM_TEXT_MM * 0.85} fill={stroke}
            fontFamily="ui-monospace, Menlo, monospace" fontWeight={600}>
            {Math.abs(d).toFixed(2)}
          </text>
        </g>,
      )
    }
  } else {
    // Chain — consecutive segments at the same level.
    for (let i = 1; i < picks.length; i++) {
      const a = picks[i - 1]
      const b = picks[i]
      const x1 = horiz ? a.x : a.x + offset
      const y1 = horiz ? a.y - offset : a.y
      const x2 = horiz ? b.x : b.x + offset
      const y2 = horiz ? b.y - offset : b.y
      const d = (horiz ? (b.x - a.x) : (b.y - a.y)) * scale
      const mx = (x1 + x2) / 2
      const my = (y1 + y2) / 2
      elems.push(
        <g key={`c-${i}`}>
          <line x1={x1} y1={y1} x2={x2} y2={y2}
            stroke={stroke} strokeWidth={0.3}
            vectorEffect="non-scaling-stroke"
            markerStart={arrow} markerEnd={arrow} />
          <text x={mx} y={my - 0.6} textAnchor="middle"
            fontSize={DIM_TEXT_MM * 0.85} fill={stroke}
            fontFamily="ui-monospace, Menlo, monospace" fontWeight={600}>
            {Math.abs(d).toFixed(2)}
          </text>
        </g>,
      )
    }
  }
  return elems
}

function DraftDimension({ draft, hover }) {
  const stroke = '#ffd633'

  // Angular has a different draft shape (vertex / a / b instead of a / b / offset).
  if (draft.kind === 'angular') {
    const v = draft.vertex
    if (draft.stage === 1) {
      const hx = hover?.x ?? v.x
      const hy = hover?.y ?? v.y
      return (
        <g pointerEvents="none">
          <circle cx={v.x} cy={v.y} r={1.0} fill={stroke} />
          <line x1={v.x} y1={v.y} x2={hx} y2={hy}
                stroke={stroke} strokeDasharray="1.5,1.5"
                strokeWidth={0.25} vectorEffect="non-scaling-stroke" />
        </g>
      )
    }
    if (draft.stage === 2) {
      const a = draft.a
      const hx = hover?.x ?? a.x
      const hy = hover?.y ?? a.y
      // Rubber-band the second arm + a preview arc whose radius is the
      // distance from vertex to cursor.
      const r = Math.max(4, Math.hypot(hx - v.x, hy - v.y))
      const a0 = Math.atan2(a.y - v.y, a.x - v.x)
      const a1 = Math.atan2(hy - v.y, hx - v.x)
      let delta = a1 - a0
      while (delta > Math.PI) delta -= 2 * Math.PI
      while (delta < -Math.PI) delta += 2 * Math.PI
      const large = Math.abs(delta) > Math.PI ? 1 : 0
      const sweep = delta >= 0 ? 1 : 0
      const x0 = v.x + r * Math.cos(a0)
      const y0 = v.y + r * Math.sin(a0)
      const x1 = v.x + r * Math.cos(a1)
      const y1 = v.y + r * Math.sin(a1)
      return (
        <g pointerEvents="none">
          <circle cx={v.x} cy={v.y} r={1.0} fill={stroke} />
          <circle cx={a.x} cy={a.y} r={1.0} fill={stroke} />
          <line x1={v.x} y1={v.y} x2={a.x} y2={a.y}
                stroke={stroke} strokeWidth={0.25} vectorEffect="non-scaling-stroke" />
          <line x1={v.x} y1={v.y} x2={hx} y2={hy}
                stroke={stroke} strokeDasharray="1.5,1.5"
                strokeWidth={0.25} vectorEffect="non-scaling-stroke" />
          <path d={`M ${x0} ${y0} A ${r} ${r} 0 ${large} ${sweep} ${x1} ${y1}`}
                fill="none" stroke={stroke} strokeDasharray="1,1"
                strokeWidth={0.25} vectorEffect="non-scaling-stroke" />
        </g>
      )
    }
    return null
  }

  // Multi-pick draft (baseline / chain / ordinate). Show the picks so far
  // plus a rubber-band line to the cursor.
  if (draft.kind === 'baseline' || draft.kind === 'chain' || draft.kind === 'ordinate') {
    const picks = draft.picks || []
    const last = picks[picks.length - 1] || { x: 0, y: 0 }
    return (
      <g pointerEvents="none">
        {picks.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={0.9} fill={stroke} />
        ))}
        {hover && (
          <line x1={last.x} y1={last.y} x2={hover.x} y2={hover.y}
            stroke={stroke} strokeDasharray="1.5,1.5"
            strokeWidth={0.25} vectorEffect="non-scaling-stroke" />
        )}
      </g>
    )
  }

  // Linear / aligned / radius / diameter.
  if (draft.stage === 1) {
    // Just the first endpoint, plus a rubber-band line to the cursor.
    const cx = hover?.x ?? draft.a.x
    const cy = hover?.y ?? draft.a.y
    return (
      <g pointerEvents="none">
        <circle cx={draft.a.x} cy={draft.a.y} r={1.0} fill={stroke} />
        <line x1={draft.a.x} y1={draft.a.y} x2={cx} y2={cy}
              stroke={stroke} strokeDasharray="1.5,1.5"
              strokeWidth={0.25} vectorEffect="non-scaling-stroke" />
      </g>
    )
  }
  if (draft.stage === 2) {
    return (
      <g pointerEvents="none">
        <circle cx={draft.a.x} cy={draft.a.y} r={1.0} fill={stroke} />
        <circle cx={draft.b.x} cy={draft.b.y} r={1.0} fill={stroke} />
        <line x1={draft.a.x} y1={draft.a.y} x2={draft.b.x} y2={draft.b.y}
              stroke={stroke} strokeWidth={0.3} vectorEffect="non-scaling-stroke" />
        {hover && (
          <line x1={(draft.a.x + draft.b.x) / 2} y1={(draft.a.y + draft.b.y) / 2}
                x2={hover.x} y2={hover.y}
                stroke={stroke} strokeDasharray="1.5,1.5"
                strokeWidth={0.25} vectorEffect="non-scaling-stroke" />
        )}
      </g>
    )
  }
  return null
}

// Annotation glyph — renders one persisted annotation. In pointer mode it's
// click-to-select and drag-to-move; selection highlight + handles are drawn
// only when `selected`.
function AnnotationGlyph({ ann, selected, onSelect, onDragStart, onHandleDown }) {
  const stroke = selected ? ANN_SELECTED_STROKE : (ann.stroke || ANN_STROKE)
  const sw = ann.width ?? ANN_DEFAULT_WIDTH
  const dashed = ann.dashed ? '2,1.5' : undefined
  const cursor = 'pointer'
  const onMouseDown = (e) => {
    // Only initiate drag on left button.
    if (e.button !== 0) return
    onDragStart?.(e)
  }

  if (ann.kind === 'text') {
    const fs = ann.fontSize || ANN_DEFAULT_TEXT_SIZE
    const color = ann.color || stroke
    return (
      <g style={{ cursor }} onClick={onSelect} onMouseDown={onMouseDown}>
        <text
          x={ann.x} y={ann.y}
          fontSize={fs} fill={color}
          fontFamily="ui-monospace, Menlo, monospace"
        >
          {ann.text || ''}
        </text>
        {selected && <Handle cx={ann.x} cy={ann.y} onMouseDown={(e) => onHandleDown?.(0, e)} />}
      </g>
    )
  }
  if (ann.kind === 'leader') {
    const fs = ann.fontSize || ANN_DEFAULT_TEXT_SIZE
    const color = ann.color || stroke
    const arrow = selected ? 'url(#ann-arrow-sel)' : 'url(#ann-arrow)'
    const f = ann.from || { x: 0, y: 0 }
    const t = ann.to || { x: 10, y: 10 }
    const side = ann.side || (t.x >= f.x ? 'right' : 'left')
    const labelDx = side === 'left' ? -1 : 1
    const anchor = side === 'left' ? 'end' : 'start'
    return (
      <g style={{ cursor }} onClick={onSelect} onMouseDown={onMouseDown}>
        <line x1={f.x} y1={f.y} x2={t.x} y2={t.y}
              stroke={stroke} strokeWidth={sw}
              vectorEffect="non-scaling-stroke"
              markerStart={arrow}
              strokeDasharray={dashed} />
        <text
          x={t.x + labelDx} y={t.y - 0.5}
          fontSize={fs} fill={color} textAnchor={anchor}
          fontFamily="ui-monospace, Menlo, monospace"
        >
          {ann.text || ''}
        </text>
        {selected && (
          <>
            <Handle cx={f.x} cy={f.y} onMouseDown={(e) => onHandleDown?.(0, e)} />
            <Handle cx={t.x} cy={t.y} onMouseDown={(e) => onHandleDown?.(1, e)} />
          </>
        )}
      </g>
    )
  }
  if (ann.kind === 'polyline') {
    const pts = (ann.points || []).map((p) => `${p.x},${p.y}`).join(' ')
    return (
      <g style={{ cursor }} onClick={onSelect} onMouseDown={onMouseDown}>
        <polyline
          points={pts}
          fill="none"
          stroke={stroke}
          strokeWidth={sw}
          vectorEffect="non-scaling-stroke"
          strokeDasharray={dashed}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {selected && (ann.points || []).map((p, i) => (
          <Handle key={i} cx={p.x} cy={p.y} onMouseDown={(e) => onHandleDown?.(i, e)} />
        ))}
      </g>
    )
  }
  if (ann.kind === 'rect') {
    const x = ann.x ?? 0, y = ann.y ?? 0
    const w = ann.width ?? 0, h = ann.height ?? 0
    return (
      <g style={{ cursor }} onClick={onSelect} onMouseDown={onMouseDown}>
        <rect x={x} y={y} width={w} height={h}
              fill={ann.fill || 'none'}
              stroke={stroke}
              strokeWidth={sw}
              vectorEffect="non-scaling-stroke"
              strokeDasharray={dashed} />
        {selected && (
          <>
            <Handle cx={x} cy={y} onMouseDown={(e) => onHandleDown?.(0, e)} />
            <Handle cx={x + w} cy={y} onMouseDown={(e) => onHandleDown?.(1, e)} />
            <Handle cx={x + w} cy={y + h} onMouseDown={(e) => onHandleDown?.(2, e)} />
            <Handle cx={x} cy={y + h} onMouseDown={(e) => onHandleDown?.(3, e)} />
          </>
        )}
      </g>
    )
  }
  if (ann.kind === 'circle') {
    const cx = ann.cx ?? 0, cy = ann.cy ?? 0, r = ann.r ?? 0
    return (
      <g style={{ cursor }} onClick={onSelect} onMouseDown={onMouseDown}>
        <circle cx={cx} cy={cy} r={r}
                fill={ann.fill || 'none'}
                stroke={stroke}
                strokeWidth={sw}
                vectorEffect="non-scaling-stroke"
                strokeDasharray={dashed} />
        {selected && (
          <>
            {/* center + 4 cardinal handles for resize */}
            <Handle cx={cx} cy={cy} onMouseDown={(e) => onHandleDown?.(0, e)} />
            <Handle cx={cx + r} cy={cy} onMouseDown={(e) => onHandleDown?.(1, e)} />
            <Handle cx={cx} cy={cy + r} onMouseDown={(e) => onHandleDown?.(2, e)} />
            <Handle cx={cx - r} cy={cy} onMouseDown={(e) => onHandleDown?.(3, e)} />
            <Handle cx={cx} cy={cy - r} onMouseDown={(e) => onHandleDown?.(4, e)} />
          </>
        )}
      </g>
    )
  }
  if (ann.kind === 'note') {
    // Boxed note — text inside a thin rectangle, anchored at (x,y) top-left.
    const fs = ann.fontSize || ANN_DEFAULT_TEXT_SIZE
    const text = ann.text || ''
    const padX = 1.4, padY = 0.8
    const w = Math.max(4, text.length * fs * 0.55) + padX * 2
    const h = fs + padY * 2
    return (
      <g style={{ cursor }} onClick={onSelect} onMouseDown={onMouseDown}>
        <rect x={ann.x} y={ann.y - fs * 0.85} width={w} height={h}
          fill="rgba(255,253,235,0.9)" stroke={stroke} strokeWidth={0.25}
          vectorEffect="non-scaling-stroke" />
        <text x={ann.x + padX} y={ann.y + padY * 0.4}
          fontSize={fs} fill={stroke}
          fontFamily="ui-sans-serif, system-ui">{text}</text>
        {selected && <Handle cx={ann.x} cy={ann.y} onMouseDown={(e) => onHandleDown?.(0, e)} />}
      </g>
    )
  }
  if (ann.kind === 'balloon') {
    const cx = ann.cx ?? 0, cy = ann.cy ?? 0
    const num = String(ann.number ?? ann.text ?? '?')
    const r = ann.r || 4.5
    return (
      <g style={{ cursor }} onClick={onSelect} onMouseDown={onMouseDown}>
        {ann.leader && (
          <line
            x1={ann.leader.x} y1={ann.leader.y}
            x2={cx} y2={cy}
            stroke={stroke} strokeWidth={0.3}
            vectorEffect="non-scaling-stroke"
            markerStart={selected ? 'url(#ann-arrow-sel)' : 'url(#ann-arrow)'}
          />
        )}
        <circle cx={cx} cy={cy} r={r}
          fill="#ffffff" stroke={stroke} strokeWidth={0.4}
          vectorEffect="non-scaling-stroke" />
        <text x={cx} y={cy + 1.4} textAnchor="middle"
          fontSize={4.5} fill={stroke}
          fontFamily="ui-sans-serif, system-ui" fontWeight={600}>
          {num}
        </text>
        {selected && <Handle cx={cx} cy={cy} onMouseDown={(e) => onHandleDown?.(0, e)} />}
      </g>
    )
  }
  return null
}

// Symbol glyph — surface_finish, weld, gdt. Renders SVG primitives produced
// by `symbolGlyph(kind, params)` translated to the symbol's anchor.
function SymbolGlyph({ sym, selected, onSelect }) {
  const stroke = selected ? ANN_SELECTED_STROKE : '#0c1118'
  const g = symbolGlyph(sym.kind, sym.params || {})
  const tx = sym.position?.x ?? 0
  const ty = sym.position?.y ?? 0
  return (
    <g style={{ cursor: 'pointer' }} onClick={onSelect}
       transform={`translate(${tx} ${ty})`}>
      {g.elements.map((e, i) => {
        if (e.type === 'line') {
          return <line key={i}
            x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2}
            stroke={selected ? ANN_SELECTED_STROKE : e.stroke}
            strokeWidth={e.width} vectorEffect="non-scaling-stroke" />
        }
        if (e.type === 'polyline') {
          const pts = e.points.map((p) => `${p[0]},${p[1]}`).join(' ')
          return <polyline key={i} points={pts}
            fill={e.fill || 'none'} stroke={selected ? ANN_SELECTED_STROKE : e.stroke}
            strokeWidth={e.width} strokeLinejoin="round" strokeLinecap="round"
            vectorEffect="non-scaling-stroke" />
        }
        if (e.type === 'rect') {
          return <rect key={i} x={e.x} y={e.y} width={e.w} height={e.h}
            fill={e.fill || 'none'} stroke={selected ? ANN_SELECTED_STROKE : e.stroke}
            strokeWidth={e.width} vectorEffect="non-scaling-stroke" />
        }
        if (e.type === 'circle') {
          return <circle key={i} cx={e.cx} cy={e.cy} r={e.r}
            fill={e.fill || 'none'} stroke={selected ? ANN_SELECTED_STROKE : e.stroke}
            strokeWidth={e.width} vectorEffect="non-scaling-stroke" />
        }
        if (e.type === 'text') {
          return <text key={i} x={e.x} y={e.y}
            textAnchor={e.anchor || 'start'}
            fontSize={e.fontSize}
            fill={selected ? ANN_SELECTED_STROKE : '#0c1118'}
            fontFamily={e.mono ? 'ui-monospace, Menlo, monospace' : 'ui-sans-serif, system-ui'}
            fontWeight={600}>
            {e.text}
          </text>
        }
        return null
      })}
      {selected && (
        <rect x={-1} y={-1}
          width={(g.bbox?.w || 6) + 2} height={(g.bbox?.h || 6) + 2}
          fill="none" stroke={ANN_SELECTED_STROKE} strokeWidth={0.3}
          strokeDasharray="1,1" vectorEffect="non-scaling-stroke" />
      )}
    </g>
  )
}

// Scale bar — bottom-left corner of the sheet. Rules off `frame.scale_label`
// when present, otherwise infers from the largest view's scale.
function ScaleBar({ frame, sheetW, sheetH, views }) {
  const SHEET_BORDER_LOCAL = '#1a1f2a'
  // Determine the page→model scale from the first view; fall back to 1.
  const scale = (views?.[0]?.scale) || 1
  const geom = scaleBarGeometry(scale, { totalLengthMm: 50 })
  const x = 8
  const y = sheetH - 12
  const labelText = frame?.scale_label || geom.label
  return (
    <g pointerEvents="none">
      <text x={x} y={y - 2.5}
        fontSize={2.2} fill={SHEET_BORDER_LOCAL}
        fontFamily="ui-monospace, Menlo, monospace" fontWeight={700}>
        {`Scale ${labelText}`}
      </text>
      {Array.from({ length: geom.bars }).map((_, i) => (
        <rect key={i}
          x={x + i * geom.tile} y={y}
          width={geom.tile} height={1.6}
          fill={i % 2 === 0 ? SHEET_BORDER_LOCAL : '#ffffff'}
          stroke={SHEET_BORDER_LOCAL} strokeWidth={0.2}
          vectorEffect="non-scaling-stroke" />
      ))}
      {Array.from({ length: geom.bars + 1 }).map((_, i) => (
        <text key={`t-${i}`}
          x={x + i * geom.tile} y={y + 4.2}
          textAnchor="middle"
          fontSize={1.6} fill={SHEET_BORDER_LOCAL}
          fontFamily="ui-monospace, Menlo, monospace">
          {(i * geom.unit).toFixed(geom.unit < 1 ? 1 : 0)}
        </text>
      ))}
    </g>
  )
}

function Handle({ cx, cy, onMouseDown }) {
  return (
    <rect
      x={cx - 0.9} y={cy - 0.9} width={1.8} height={1.8}
      fill={ANN_HANDLE_FILL} stroke={ANN_HANDLE_STROKE}
      strokeWidth={0.2} vectorEffect="non-scaling-stroke"
      style={{ cursor: 'grab' }}
      onMouseDown={onMouseDown}
    />
  )
}

function DraftAnnotation({ draft }) {
  const stroke = ANN_SELECTED_STROKE
  if (draft.kind === 'rect-draft') {
    const x = Math.min(draft.start.x, draft.end.x)
    const y = Math.min(draft.start.y, draft.end.y)
    const w = Math.abs(draft.end.x - draft.start.x)
    const h = Math.abs(draft.end.y - draft.start.y)
    return (
      <rect x={x} y={y} width={w} height={h}
            fill="none" stroke={stroke} strokeWidth={0.3}
            strokeDasharray="1.5,1.5" vectorEffect="non-scaling-stroke"
            pointerEvents="none" />
    )
  }
  if (draft.kind === 'circle-draft') {
    return (
      <circle cx={draft.center.x} cy={draft.center.y} r={draft.radius}
              fill="none" stroke={stroke} strokeWidth={0.3}
              strokeDasharray="1.5,1.5" vectorEffect="non-scaling-stroke"
              pointerEvents="none" />
    )
  }
  if (draft.kind === 'polyline-draft') {
    if (!draft.points?.length) return null
    const pts = draft.points.map((p) => `${p.x},${p.y}`).join(' ')
    return (
      <g pointerEvents="none">
        <polyline points={pts} fill="none" stroke={stroke}
                  strokeWidth={0.3} strokeDasharray="1.5,1.5"
                  vectorEffect="non-scaling-stroke" />
        {draft.points.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={0.7} fill={stroke} />
        ))}
      </g>
    )
  }
  if (draft.kind === 'leader-draft') {
    return (
      <g pointerEvents="none">
        <circle cx={draft.from.x} cy={draft.from.y} r={0.8} fill={stroke} />
      </g>
    )
  }
  if (draft.kind === 'centerline-draft') {
    return (
      <g pointerEvents="none">
        <circle cx={draft.p1.x} cy={draft.p1.y} r={0.8} fill={stroke} />
      </g>
    )
  }
  if (draft.kind === 'break-draft') {
    return (
      <g pointerEvents="none">
        <circle cx={draft.p1.x} cy={draft.p1.y} r={0.8} fill={stroke} />
      </g>
    )
  }
  return null
}

function MeasureOverlay({ measure, hover, views }) {
  const stroke = '#ffd633'
  if (measure.kind === 'distance') {
    const a = measure.a
    // Live-cursor end if no second click yet.
    const b = measure.b || (hover ? { x: hover.x, y: hover.y } : a)
    const dx = b.x - a.x
    const dy = b.y - a.y
    const pageDist = Math.hypot(dx, dy) // in page-mm
    // Convert page-mm → model mm using the view's scale (page-mm * scale).
    const view = views?.find((v) => v.id === measure.viewId)
    const modelDist = pageDist * (view?.scale || measure.scale || 1)
    const mx = (a.x + b.x) / 2
    const my = (a.y + b.y) / 2
    const text = `${modelDist.toFixed(3)} mm`
    return (
      <g pointerEvents="none">
        <line x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={stroke} strokeWidth={0.4}
              vectorEffect="non-scaling-stroke" />
        <circle cx={a.x} cy={a.y} r={0.9} fill={stroke} />
        <circle cx={b.x} cy={b.y} r={0.9} fill={stroke} />
        <rect x={mx - 12} y={my - 4.2} width={24} height={4}
              fill="rgba(0,0,0,0.65)" rx={0.6} />
        <text x={mx} y={my - 1.2} textAnchor="middle"
              fontSize={2.6} fill={stroke}
              fontFamily="ui-monospace, Menlo, monospace"
              fontWeight={600}>
          {text}
        </text>
      </g>
    )
  }
  if (measure.kind === 'angle') {
    const v = measure.vertex
    const a = measure.a || (hover ? { x: hover.x, y: hover.y } : v)
    const b = measure.b || (hover ? { x: hover.x, y: hover.y } : a)
    const a0 = Math.atan2(a.y - v.y, a.x - v.x)
    const a1 = Math.atan2(b.y - v.y, b.x - v.x)
    let delta = a1 - a0
    while (delta > Math.PI) delta -= 2 * Math.PI
    while (delta < -Math.PI) delta += 2 * Math.PI
    const r = Math.max(8, Math.min(40,
      Math.min(Math.hypot(a.x - v.x, a.y - v.y), Math.hypot(b.x - v.x, b.y - v.y))))
    const large = Math.abs(delta) > Math.PI ? 1 : 0
    const sweep = delta >= 0 ? 1 : 0
    const x0 = v.x + r * Math.cos(a0)
    const y0 = v.y + r * Math.sin(a0)
    const x1 = v.x + r * Math.cos(a1)
    const y1 = v.y + r * Math.sin(a1)
    const am = a0 + delta / 2
    const labelR = r + 4
    const lx = v.x + labelR * Math.cos(am)
    const ly = v.y + labelR * Math.sin(am)
    const deg = Math.abs(delta) * 180 / Math.PI
    return (
      <g pointerEvents="none">
        <circle cx={v.x} cy={v.y} r={0.9} fill={stroke} />
        <line x1={v.x} y1={v.y} x2={a.x} y2={a.y}
              stroke={stroke} strokeWidth={0.3}
              strokeDasharray={measure.a ? undefined : '1.5,1.5'}
              vectorEffect="non-scaling-stroke" />
        {measure.a && (
          <line x1={v.x} y1={v.y} x2={b.x} y2={b.y}
                stroke={stroke} strokeWidth={0.3}
                strokeDasharray={measure.b ? undefined : '1.5,1.5'}
                vectorEffect="non-scaling-stroke" />
        )}
        {measure.a && (
          <path d={`M ${x0} ${y0} A ${r} ${r} 0 ${large} ${sweep} ${x1} ${y1}`}
                fill="none" stroke={stroke} strokeWidth={0.3}
                vectorEffect="non-scaling-stroke" />
        )}
        {measure.a && (
          <>
            <rect x={lx - 8} y={ly - 4.2} width={16} height={4}
                  fill="rgba(0,0,0,0.65)" rx={0.6} />
            <text x={lx} y={ly - 1.2} textAnchor="middle"
                  fontSize={2.6} fill={stroke}
                  fontFamily="ui-monospace, Menlo, monospace"
                  fontWeight={600}>
              {`${deg.toFixed(2)}°`}
            </text>
          </>
        )}
      </g>
    )
  }
  return null
}

// Inline DOM input overlaid on the SVG. Rendered as a positioned absolute
// HTML input so the user gets standard typing/selection behavior. Position
// is captured in client-px at click time (textInput.screenLeft/Top) and we
// convert to container-relative px in an effect so we never have to read a
// ref during render.
function InlineTextInput({ textInput, containerRef, onCommit, onCancel }) {
  const inputRef = useRef(null)
  const [val, setVal] = useState(textInput?.value || '')
  const [pos, setPos] = useState(null)

  useEffect(() => {
    inputRef.current?.focus()
    inputRef.current?.select()
    // Compute position relative to the container (the SVG's bounding rect
    // approximates the container's positioned ancestor closely enough; the
    // input is absolutely positioned inside the same wrapper as the SVG).
    const rect = containerRef.current?.getBoundingClientRect()
    if (!rect) return
    setPos({
      left: textInput.screenLeft - rect.left,
      top: textInput.screenTop - rect.top - 8,
    })
  }, [containerRef, textInput.screenLeft, textInput.screenTop])

  if (!pos) return null
  return (
    <input
      ref={inputRef}
      value={val}
      onChange={(e) => setVal(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') onCommit(val)
        else if (e.key === 'Escape') onCancel()
      }}
      onBlur={() => onCommit(val)}
      placeholder={textInput.kind === 'leader' ? 'leader text…' : 'text…'}
      className="absolute z-20 px-1.5 py-0.5 text-xs font-mono bg-ink-950/95 border border-kerf-300 text-kerf-300 outline-none rounded"
      style={{
        left: `${pos.left}px`,
        top: `${pos.top}px`,
        minWidth: '120px',
      }}
    />
  )
}

// ---------------------------------------------------------------------------
// Annotation drag/transform helpers

// Translate every coordinate-bearing field on the annotation by (dx, dy).
function translateAnnotation(ann, dx, dy) {
  switch (ann.kind) {
    case 'text':
    case 'note':
      return { x: ann.x + dx, y: ann.y + dy }
    case 'leader':
      return {
        from: { x: ann.from.x + dx, y: ann.from.y + dy },
        to: { x: ann.to.x + dx, y: ann.to.y + dy },
      }
    case 'polyline':
      return { points: (ann.points || []).map((p) => ({ x: p.x + dx, y: p.y + dy })) }
    case 'rect':
      return { x: ann.x + dx, y: ann.y + dy }
    case 'circle':
    case 'balloon':
      return { cx: ann.cx + dx, cy: ann.cy + dy }
    default:
      return null
  }
}

// Apply a handle-drag transform. `handleIdx` matches the order handles are
// drawn in AnnotationGlyph above. `mm` is the cursor position in page-mm.
function transformAnnotation(ann, handleIdx, dx, dy, mm) {
  switch (ann.kind) {
    case 'text':
    case 'note':
      return { x: ann.x + dx, y: ann.y + dy }
    case 'balloon':
      return { cx: ann.cx + dx, cy: ann.cy + dy }
    case 'leader':
      if (handleIdx === 0) return { from: { x: mm.x, y: mm.y } }
      if (handleIdx === 1) return { to: { x: mm.x, y: mm.y } }
      return null
    case 'polyline': {
      const pts = (ann.points || []).map((p, i) =>
        i === handleIdx ? { x: mm.x, y: mm.y } : p)
      return { points: pts }
    }
    case 'rect': {
      // 0=tl, 1=tr, 2=br, 3=bl
      const x0 = ann.x, y0 = ann.y, x1 = ann.x + ann.width, y1 = ann.y + ann.height
      let nx0 = x0, ny0 = y0, nx1 = x1, ny1 = y1
      if (handleIdx === 0) { nx0 = mm.x; ny0 = mm.y }
      else if (handleIdx === 1) { nx1 = mm.x; ny0 = mm.y }
      else if (handleIdx === 2) { nx1 = mm.x; ny1 = mm.y }
      else if (handleIdx === 3) { nx0 = mm.x; ny1 = mm.y }
      const x = Math.min(nx0, nx1)
      const y = Math.min(ny0, ny1)
      return { x, y, width: Math.abs(nx1 - nx0), height: Math.abs(ny1 - ny0) }
    }
    case 'circle':
      if (handleIdx === 0) {
        // Move center.
        return { cx: ann.cx + dx, cy: ann.cy + dy }
      }
      // Cardinal handles → resize.
      return { r: Math.max(0.5, Math.hypot(mm.x - ann.cx, mm.y - ann.cy)) }
    default:
      return null
  }
}

// ---------------------------------------------------------------------------
// Geometry helpers

function initialViewBox(sheetW, sheetH) {
  // Frame the whole sheet with a small margin.
  const pad = 20
  return { x: -pad, y: -pad, w: sheetW + 2 * pad, h: sheetH + 2 * pad }
}

// Module-scoped per-part BVH cache. Keyed by part.geom (the underlying
// JSCAD Geom3 or Three BufferGeometry) so two views of the same part reuse
// the same BVH. WeakMap → eligible for GC when the underlying geom is
// dropped from the source-parts map.
const bvhCache = new WeakMap()
function getOrBuildBVH(part, bvhMod) {
  const geom = part?.geom
  if (!geom) return null
  const cached = bvhCache.get(geom)
  if (cached) return cached
  // three-mesh-bvh's MeshBVH operates on a BufferGeometry. JSCAD parts give
  // us a Geom3 — convert via the same helper the renderer uses. STEP parts
  // are already a BufferGeometry; `applyMatrixToGeom(g, undefined)` clones
  // it without modifying positions.
  let bg
  if (geom.isBufferGeometry) {
    bg = geom
  } else {
    bg = applyMatrixToGeom(geom, null)
  }
  if (!bg) return null
  try {
    const bvh = new bvhMod.MeshBVH(bg)
    bvhCache.set(geom, bvh)
    return bvh
  } catch (err) {
    console.warn('DrawingView: failed to build BVH for part', part.id, err)
    return null
  }
}

// Signed perpendicular distance from `p` to the line a-b. Positive when on
// one side, negative on the other.
function perpendicularOffset(a, b, p) {
  const dx = b.x - a.x
  const dy = b.y - a.y
  const L = Math.hypot(dx, dy) || 1
  const nx = -dy / L
  const ny = dx / L
  return (p[0] - a.x) * nx + (p[1] - a.y) * ny
}

function computeLinearDim(dim, view) {
  // For 'linear' we use the AXIS-ALIGNED component (always horizontal or
  // vertical depending on whether |dx| > |dy|). For 'aligned' we use the
  // direction of a-b directly.
  const a = dim.a
  const b = dim.b
  let dx = b.x - a.x
  let dy = b.y - a.y
  if (dim.kind === 'linear') {
    if (Math.abs(dx) >= Math.abs(dy)) { dy = 0 } else { dx = 0 }
  }
  const L = Math.hypot(dx, dy) || 1
  const ux = dx / L
  const uy = dy / L
  // Perpendicular (left of a→b in screen-y-down).
  const nx = -uy
  const ny = ux
  // Project a and b onto the perpendicular axis through... actually, we just
  // offset each endpoint by `dim.offset` along (nx, ny) to get the dim line
  // endpoints. Linear vs aligned only affects the "value" we report:
  // linear = signed |dx| or |dy|, aligned = full distance.
  const lx1 = a.x + nx * dim.offset
  const ly1 = a.y + ny * dim.offset
  const lx2 = b.x + nx * dim.offset
  const ly2 = b.y + ny * dim.offset
  // For linear: snap the two ends back onto the axis-aligned line that
  // passes through midpoint(a,b).
  let value
  if (dim.kind === 'linear') {
    value = Math.hypot(dx, dy)
  } else {
    value = Math.hypot(b.x - a.x, b.y - a.y)
  }
  // Apply the view's scale to convert page-mm length → model units.
  const modelValue = value * view.scale
  const valueText = modelValue.toFixed(modelValue >= 10 ? 2 : 3) + ' mm'
  const mx = (lx1 + lx2) / 2
  const my = (ly1 + ly2) / 2
  return {
    ax: a.x, ay: a.y, bx: b.x, by: b.y,
    lx1, ly1, lx2, ly2, mx, my,
    valueText, perp: [nx, ny],
  }
}

function computeAngularDim(dim) {
  // Three-point angular dim: `vertex` is the apex, `a` and `b` are arm
  // endpoints, `radius` is the arc radius (independent of arm length so the
  // user can place the arc tighter or looser than the construction lines).
  const v = dim.vertex
  if (!v) return null
  const ax = dim.a?.x, ay = dim.a?.y
  const bx = dim.b?.x, by = dim.b?.y
  if (!Number.isFinite(ax) || !Number.isFinite(bx)) return null
  const cx = v.x, cy = v.y
  const r = Number(dim.radius) > 0 ? dim.radius : 10
  const a0 = Math.atan2(ay - cy, ax - cx)
  const a1 = Math.atan2(by - cy, bx - cx)
  // Midpoint angle for label placement — use the shorter arc.
  let delta = a1 - a0
  while (delta > Math.PI) delta -= 2 * Math.PI
  while (delta < -Math.PI) delta += 2 * Math.PI
  const am = a0 + delta / 2
  const mx = cx + (r + 4) * Math.cos(am)
  const my = cy + (r + 4) * Math.sin(am)
  const deg = Math.abs(delta) * 180 / Math.PI
  const valueText = deg.toFixed(1) + '°'
  return { cx, cy, r, a0, a1, mx, my, valueText, ax, ay, bx, by }
}

function formatScale(scale) {
  // Return "1:N" or "N:1" depending on which side is bigger. Approximate
  // with rounded ratios.
  if (scale >= 1) {
    const n = Math.round(scale)
    return n === 1 ? '1:1' : `1:${n}`
  }
  const n = Math.round(1 / scale)
  return n === 1 ? '1:1' : `${n}:1`
}

// SnapMarker — renders the per-kind glyph (square / triangle / circle / X
// / cross) at the snapped position, plus a tiny label below it. Sizing is
// in PAGE-MM; non-scaling-stroke keeps lines crisp at every zoom.
function SnapMarker({ hover }) {
  const r = SNAP_MARKER_MM
  const stroke = SNAP_COLOR
  const labelDx = 0
  const labelDy = -r * 1.6
  const labelText = snapLabel(hover.kind)
  let glyph = null
  if (hover.kind === 'endpoint') {
    // Filled square — hardest geometric feature.
    glyph = (
      <rect x={hover.x - r * 0.6} y={hover.y - r * 0.6}
        width={r * 1.2} height={r * 1.2}
        fill={stroke} stroke={stroke} strokeWidth={0.25}
        vectorEffect="non-scaling-stroke" />
    )
  } else if (hover.kind === 'midpoint') {
    // Triangle pointing up.
    const a = `${hover.x},${hover.y - r * 0.8}`
    const b = `${hover.x - r * 0.7},${hover.y + r * 0.55}`
    const c = `${hover.x + r * 0.7},${hover.y + r * 0.55}`
    glyph = (
      <polygon points={`${a} ${b} ${c}`}
        fill="none" stroke={stroke} strokeWidth={0.4}
        vectorEffect="non-scaling-stroke" />
    )
  } else if (hover.kind === 'center') {
    // Filled circle.
    glyph = (
      <circle cx={hover.x} cy={hover.y} r={r * 0.55}
        fill={stroke} stroke={stroke} strokeWidth={0.25}
        vectorEffect="non-scaling-stroke" />
    )
  } else if (hover.kind === 'intersection') {
    // X mark.
    glyph = (
      <g>
        <line x1={hover.x - r * 0.7} y1={hover.y - r * 0.7}
          x2={hover.x + r * 0.7} y2={hover.y + r * 0.7}
          stroke={stroke} strokeWidth={0.5}
          vectorEffect="non-scaling-stroke" />
        <line x1={hover.x - r * 0.7} y1={hover.y + r * 0.7}
          x2={hover.x + r * 0.7} y2={hover.y - r * 0.7}
          stroke={stroke} strokeWidth={0.5}
          vectorEffect="non-scaling-stroke" />
      </g>
    )
  } else if (hover.kind === 'origin') {
    // Plus inscribed in a circle.
    glyph = (
      <g>
        <circle cx={hover.x} cy={hover.y} r={r * 0.7}
          fill="none" stroke={stroke} strokeWidth={0.4}
          vectorEffect="non-scaling-stroke" />
        <line x1={hover.x - r} y1={hover.y} x2={hover.x + r} y2={hover.y}
          stroke={stroke} strokeWidth={0.35}
          vectorEffect="non-scaling-stroke" />
        <line x1={hover.x} y1={hover.y - r} x2={hover.x} y2={hover.y + r}
          stroke={stroke} strokeWidth={0.35}
          vectorEffect="non-scaling-stroke" />
      </g>
    )
  }
  return (
    <g pointerEvents="none">
      {glyph}
      {labelText && (
        <text x={hover.x + labelDx} y={hover.y + labelDy}
          textAnchor="middle"
          fontSize={2.2} fill={stroke}
          fontFamily="ui-monospace, Menlo, monospace"
          fontWeight={600}>
          {labelText}
        </text>
      )}
    </g>
  )
}

function toolHint(tool, draft, measure, annDraft) {
  if (tool === 'pointer') return 'pan: middle-mouse / space-drag · zoom: scroll · click to select · Del to remove'
  if (tool === 'measure-distance') {
    if (!measure || measure.b) return 'Measure distance · click first point (snaps)'
    return 'Measure distance · click second point · Esc to clear'
  }
  if (tool === 'measure-angle') {
    if (!measure || measure.b) return 'Measure angle · click vertex'
    if (!measure.a) return 'Measure angle · click first arm'
    return 'Measure angle · click second arm · Esc to clear'
  }
  if (tool === 'text') return 'Text · click to place; type then Enter'
  if (tool === 'note') return 'Note · click to place a boxed note; type then Enter'
  if (tool === 'leader') {
    if (!annDraft) return 'Leader · click arrow tip (snaps)'
    return 'Leader · click label position; type then Enter'
  }
  if (tool === 'polyline') {
    if (!annDraft) return 'Polyline · click first point'
    return `Polyline · ${annDraft.points.length} pts · click to add · double-click to finish`
  }
  if (tool === 'rect') return 'Rectangle · click-drag to draw'
  if (tool === 'ann-circle') return 'Circle · click center, drag for radius'
  if (tool === 'centerline') {
    if (!annDraft) return 'Centerline · click first endpoint'
    return 'Centerline · click second endpoint'
  }
  if (tool === 'break') {
    if (!annDraft) return 'Break line · click first endpoint'
    return 'Break line · click second endpoint'
  }
  if (tool === 'balloon') return 'Balloon · click to place a numbered callout'
  if (tool === 'surface_finish') return 'Surface finish · click to place'
  if (tool === 'weld') return 'Weld symbol · click to place'
  if (tool === 'gdt') return 'GD&T frame · click to place'
  if (tool === 'angular') {
    if (!draft) return 'Angular · click the angle vertex (snaps to vertex/edge)'
    if (draft.stage === 1) return 'Angular · click first arm endpoint'
    return 'Angular · click second arm endpoint (distance from vertex sets arc radius)'
  }
  if (MULTI_POINT_DIMS.has(tool)) {
    const kind = tool[0].toUpperCase() + tool.slice(1)
    if (!draft) return `${kind} · click first pick`
    return `${kind} · ${(draft.picks || []).length} picks · click to add · double-click to finish`
  }
  if (TWO_POINT_DIMS.has(tool)) {
    const kind = tool[0].toUpperCase() + tool.slice(1)
    if (!draft) return `${kind} dimension · click first point (snaps · Alt = free)`
    if (draft.stage === 1) return `${kind} · click second point`
    return `${kind} · click to set offset`
  }
  return ''
}
