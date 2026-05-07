// SketchView — parametric 2D sketcher.
//
// Mounted by Editor.jsx when `currentFile.kind === 'sketch'`. Owns:
//   * The SVG canvas (pan + zoom, screen → world conversion).
//   * The active "tool" state machine (line / circle / arc / rectangle / etc).
//   * The selection set + the dimension/constraint inspector.
//   * Solver invocation: every entity-add or value change triggers a debounced
//     `solveSketch()` and applies the returned numeric coordinates back into
//     the sketch.
//
// The sketch JSON IS the file content. We write through `updateSketch()` from
// the workspace store, which handles persistence + revisions.

import { useCallback, useEffect, useRef, useState, useMemo } from 'react'
import {
  MousePointer2, Slash, Circle as CircleIcon, Spline, Square, Dot,
  MoveHorizontal, MoveVertical, Triangle, Equal, Anchor,
  Ruler, RotateCcw, Trash2, Lock, AlertTriangle, Check,
  Scissors, ArrowRightToLine, GitMerge, Hexagon, Waves,
  FlipHorizontal2, Grid3x3, RotateCw, Pin, Magnet, BookmarkPlus,
  Unlock,
} from 'lucide-react'
import * as THREE from 'three'
import {
  parseSketch, serializeSketch, solveSketch, solveWithDrag,
} from '../lib/sketchSolver.js'
import {
  addPoint, addLine, addCircle, addArc, addEllipse, addBspline,
  addConstraint,
  setPointXY, toggleConstruction, toggleConstructionMany, setConstraintValue,
  deleteEntities, deleteConstraint, snapTarget, ensurePointAt,
  trimAt, extendTo, filletCorner,
  mirrorEntities, linearPattern, polarPattern,
} from '../lib/sketchEdit.js'
import { tessellateEllipse, tessellateBspline } from '../lib/sketchGeom2.js'
import { geom3ToBufferGeometry } from '../lib/geom3.js'

const DEBOUNCE_SOLVE_MS = 80
const DEFAULT_VIEW = { cx: 0, cy: 0, scale: 6 } // world units per pixel: scale=6 → 1mm = 6px

// ---------------------------------------------------------------------------
// Tool palette buttons.

const TOOLS = [
  { id: 'select',   key: 'S',   icon: MousePointer2, label: 'Select',                category: 'tool' },
  { id: 'point',    key: 'P',   icon: Dot,           label: 'Point',                 category: 'tool' },
  { id: 'line',     key: 'L',   icon: Slash,         label: 'Line',                  category: 'tool' },
  { id: 'circle',   key: 'C',   icon: CircleIcon,    label: 'Circle',                category: 'tool' },
  { id: 'arc',      key: 'A',   icon: Spline,        label: 'Arc (3-point)',         category: 'tool' },
  { id: 'rect',     key: 'R',   icon: Square,        label: 'Rectangle',             category: 'tool' },
  { id: 'ellipse',  key: 'shift+E', icon: Hexagon,   label: 'Ellipse (Shift+E)',     category: 'tool' },
  { id: 'bspline',  key: 'B',   icon: Waves,         label: 'B-spline (cubic)',      category: 'tool' },
]

// 2D-edit tools — modal interactions launched from the palette.
const EDIT_TOOLS = [
  { id: 'trim',    key: 'T',        icon: Scissors,           label: 'Trim (T)' },
  { id: 'extend',  key: 'E',        icon: ArrowRightToLine,   label: 'Extend (E)' },
  { id: 'fillet',  key: 'F',        icon: GitMerge,           label: 'Fillet (F)' },
  { id: 'mirror',  key: 'M',        icon: FlipHorizontal2,    label: 'Mirror (M)' },
  { id: 'linear',  key: 'shift+L',  icon: Grid3x3,            label: 'Linear pattern (Shift+L)' },
  { id: 'polar',   key: 'shift+P',  icon: RotateCw,           label: 'Polar pattern (Shift+P)' },
]

const CONSTRAINTS = [
  { id: 'horizontal',    key: 'H',   icon: MoveHorizontal, label: 'Horizontal' },
  { id: 'vertical',      key: 'V',   icon: MoveVertical,   label: 'Vertical' },
  { id: 'coincident',    key: '',    icon: Anchor,         label: 'Coincident' },
  { id: 'parallel',      key: '',    icon: Equal,          label: 'Parallel' },
  { id: 'perpendicular', key: '',    icon: Triangle,       label: 'Perpendicular' },
  { id: 'tangent',       key: '',    icon: RotateCcw,      label: 'Tangent' },
  { id: 'equal_length',  key: '',    icon: Equal,          label: 'Equal length' },
  { id: 'equal_radius',  key: '',    icon: Equal,          label: 'Equal radius' },
  { id: 'symmetric',     key: '',    icon: FlipHorizontal2, label: 'Symmetric (2 pts + line)' },
  { id: 'block',         key: '',    icon: Pin,            label: 'Block (pin in place)' },
  { id: 'point_on_line', key: '',    icon: Magnet,         label: 'Point on line' },
  { id: 'point_on_arc',  key: '',    icon: BookmarkPlus,   label: 'Point on arc/circle' },
  { id: 'distance',      key: 'D',   icon: Ruler,          label: 'Dimension (auto)' },
]

// ---------------------------------------------------------------------------
// Main component.

export default function SketchView({
  sketch,                // the parsed sketch object from store
  files,                 // for the visible_3d picker
  onChange,              // (nextSketch) => void; debounced upstream
  onSolved,              // (nextSketch, status, dof, conflicts) => void
  status,                // 'fully' | 'under' | 'over' | 'conflict' | null
  dofCount,              // number
  conflicts,             // string[] of conflicting constraint ids
  loadParts,             // (fileId) => Promise<parts[]>; powers 3D backdrop
}) {
  const svgRef = useRef(null)
  const containerRef = useRef(null)
  const [view, setView] = useState(DEFAULT_VIEW)
  const [tool, setTool] = useState('select')
  const [construction, setConstruction] = useState(false)
  const [pendingPoints, setPendingPoints] = useState([]) // multi-click tools
  const [hover, setHover] = useState(null) // {x, y} world-space cursor
  const [snap, setSnap] = useState(null)   // active snap target
  const [selection, setSelection] = useState([]) // entity/constraint ids
  const [dragging, setDragging] = useState(null) // {pointId, fromX, fromY}
  const [dimensionPrompt, setDimensionPrompt] = useState(null) // {kind, refs, defaultValue}
  const [filletPrompt, setFilletPrompt] = useState(null)       // {a, b}
  const [patternPrompt, setPatternPrompt] = useState(null)     // {kind: 'linear'|'polar'|'mirror', ...}
  const [lastFilletRadius, setLastFilletRadius] = useState(1)
  // Drag-on-dimension state: { constraintId, kind, startVal, startScreen, startMouse }
  const [dimDrag, setDimDrag] = useState(null)

  // Resync when upstream sketch reference changes.
  const lastSketchRef = useRef(sketch)
  useEffect(() => {
    if (sketch !== lastSketchRef.current) {
      lastSketchRef.current = sketch
      // Clear in-progress tool state on upstream change so a stale half-drawn
      // line doesn't survive an LLM-side restore or undo.
      setPendingPoints([])
      setSelection([])
    }
  }, [sketch])

  // ---- Debounced solve ----
  const solveTimerRef = useRef(null)
  const solveSeqRef = useRef(0)
  const triggerSolve = useCallback((s) => {
    if (!s) return
    if (solveTimerRef.current) clearTimeout(solveTimerRef.current)
    const seq = ++solveSeqRef.current
    solveTimerRef.current = setTimeout(async () => {
      try {
        const res = await solveSketch(s)
        if (seq !== solveSeqRef.current) return
        if (res?.sketch) {
          onSolved?.(res.sketch, res.status, res.dofCount, res.conflicts)
        }
      } catch (err) {
        // Solver failures shouldn't break the editor — surface in console only.
        console.warn('sketchSolver: solve failed', err)
      }
    }, DEBOUNCE_SOLVE_MS)
  }, [onSolved])

  // After every onChange we kick off a solve. The change comes from a tool
  // commit or a constraint-value tweak, never from the solver itself (the
  // solver flows through onSolved).
  const commit = useCallback((next) => {
    onChange?.(next)
    triggerSolve(next)
  }, [onChange, triggerSolve])

  // ---- Coord conversion ----
  const screenToWorld = useCallback((sx, sy) => {
    const r = svgRef.current?.getBoundingClientRect()
    if (!r) return { x: 0, y: 0 }
    const cx = r.left + r.width / 2
    const cy = r.top + r.height / 2
    return {
      x: view.cx + (sx - cx) / view.scale,
      y: view.cy + (cy - sy) / view.scale, // flip Y (screen → math)
    }
  }, [view])

  const worldToScreen = useCallback((wx, wy) => {
    const r = svgRef.current?.getBoundingClientRect()
    if (!r) return { x: 0, y: 0 }
    const cx = r.width / 2
    const cy = r.height / 2
    return {
      x: cx + (wx - view.cx) * view.scale,
      y: cy - (wy - view.cy) * view.scale,
    }
  }, [view])

  // ---- Pan + zoom ----
  const panRef = useRef(null)
  function onWheel(e) {
    if (e.ctrlKey || e.metaKey) return
    e.preventDefault()
    const factor = e.deltaY < 0 ? 1.2 : 1 / 1.2
    const r = svgRef.current?.getBoundingClientRect()
    if (!r) return
    const w = screenToWorld(e.clientX, e.clientY)
    setView((v) => {
      const nextScale = Math.max(0.5, Math.min(80, v.scale * factor))
      // Keep cursor world position stable.
      const newCx = w.x - (e.clientX - (r.left + r.width / 2)) / nextScale
      const newCy = w.y + (e.clientY - (r.top + r.height / 2)) / nextScale
      return { cx: newCx, cy: newCy, scale: nextScale }
    })
  }

  // Mouse handlers ----------------------------------------------------------
  function onMouseDown(e) {
    if (e.button === 1 || (e.button === 0 && e.shiftKey)) {
      // Middle / shift+left → pan.
      panRef.current = { x: e.clientX, y: e.clientY, view }
      return
    }
    if (e.button !== 0) return
    const w = screenToWorld(e.clientX, e.clientY)
    const sn = snapTarget(sketch, w, view.scale)
    setSnap(sn)
    if (tool === 'select') {
      // Click on a point → start drag. Click on entity → select.
      const hitId = sn?.kind === 'point' ? sn.id : entityHitTest(sketch, w, view.scale)
      if (hitId) {
        const ent = sketch.entities.find((x) => x.id === hitId)
        if (ent?.type === 'point') {
          setDragging({ pointId: hitId, fromX: ent.x, fromY: ent.y })
        }
        if (e.shiftKey) setSelection((s) => s.includes(hitId) ? s.filter((x) => x !== hitId) : [...s, hitId])
        else setSelection([hitId])
      } else {
        if (!e.shiftKey) setSelection([])
      }
      return
    }
    // Tool-specific click handling.
    handleToolClick(w, sn)
  }

  function onMouseMove(e) {
    const w = screenToWorld(e.clientX, e.clientY)
    setHover(w)
    const sn = snapTarget(sketch, w, view.scale)
    setSnap(sn)
    if (panRef.current) {
      const r = svgRef.current?.getBoundingClientRect()
      if (!r) return
      const dx = (e.clientX - panRef.current.x) / view.scale
      const dy = (e.clientY - panRef.current.y) / view.scale
      setView({
        cx: panRef.current.view.cx - dx,
        cy: panRef.current.view.cy + dy,
        scale: panRef.current.view.scale,
      })
      return
    }
    if (dragging) {
      // Live-drag: update sketch + run solveWithDrag.
      const tx = sn?.kind === 'point' && sn.id !== dragging.pointId ? sn.x : w.x
      const ty = sn?.kind === 'point' && sn.id !== dragging.pointId ? sn.y : w.y
      const optimistic = setPointXY(sketch, dragging.pointId, tx, ty)
      onChange?.(optimistic)
      // Async solve; onSolved updates the displayed sketch with the
      // constraint-aware final position. We don't await to avoid stutter.
      solveWithDrag(optimistic, { pointId: dragging.pointId, x: tx, y: ty })
        .then((res) => res?.sketch && onSolved?.(res.sketch, res.status, res.dofCount, res.conflicts))
        .catch(() => {})
      return
    }
  }

  function onMouseUp() {
    if (panRef.current) panRef.current = null
    if (dragging) {
      // Final solve (no temp constraint) so the persisted sketch reflects the
      // new resting state.
      triggerSolve(sketch)
      setDragging(null)
    }
  }

  function onContextMenu(e) {
    e.preventDefault()
    setPendingPoints([])
    setTool('select')
  }

  function onDoubleClick() {
    if (tool === 'bspline' && pendingPoints.length >= 4) {
      const ids = pendingPoints.map((p) => p.id)
      const { sketch: s1 } = addBspline(sketch, ids, { construction })
      commit(s1)
      setPendingPoints([])
    }
  }

  // ---- Tool state machines -----------------------------------------------

  // Forward refs so handleToolClick (defined here) can call edit-tool
  // callbacks that are declared later without violating temporal access.
  const editHandlersRef = useRef({})
  const handleToolClick = useCallback((w, sn) => {
    if (tool === 'trim') { editHandlersRef.current.trim?.(w); return }
    if (tool === 'extend') { editHandlersRef.current.extend?.(w); return }
    if (tool === 'fillet') { editHandlersRef.current.fillet?.(w); return }
    if (tool === 'ellipse') {
      // Two clicks: center, then a point on the major axis. rx = |second − center|,
      // ry defaults to rx/2 — user tweaks via inspector if they want a different
      // minor axis. Rotation is taken from the major-axis direction.
      if (pendingPoints.length === 0) {
        const { sketch: s1, id: pid } = ensurePointAt(sketch, sn, w)
        commit(s1)
        setPendingPoints([{ id: pid }])
        return
      }
      const center = pendingPoints[0]
      const cEnt = sketch.entities.find((x) => x.id === center.id)
      if (!cEnt) { setPendingPoints([]); return }
      const dx = w.x - cEnt.x, dy = w.y - cEnt.y
      const rx = Math.max(0.01, Math.hypot(dx, dy))
      const ry = rx / 2
      const rotation = Math.atan2(dy, dx)
      const { sketch: s1 } = addEllipse(sketch, center.id, rx, ry, rotation, { construction })
      commit(s1)
      setPendingPoints([])
      return
    }
    if (tool === 'bspline') {
      // Click to add control point. Double-click (handled via dblclick) finishes.
      const { sketch: s1, id: pid } = ensurePointAt(sketch, sn, w)
      commit(s1)
      setPendingPoints([...pendingPoints, { id: pid, role: 'cp' }])
      return
    }
    if (tool === 'point') {
      const { sketch: ns, id } = ensurePointAt(sketch, sn, w)
      const finalEnt = ns.entities[ns.entities.length - 1]
      const annotated = construction
        ? toggleConstruction(ns, id)
        : ns
      commit(annotated)
      void finalEnt
      return
    }
    if (tool === 'line') {
      const { sketch: s1, id: pid } = ensurePointAt(sketch, sn, w)
      if (pendingPoints.length === 0) {
        // First click — provisionally create a point + remember it.
        commit(s1)
        setPendingPoints([{ id: pid, sketchAfter: s1 }])
        return
      }
      const start = pendingPoints[0]
      // Re-resolve start id against latest sketch (in case solver moved it).
      const { sketch: s2, id: pid2 } = ensurePointAt(s1, sn, w)
      const { sketch: s3 } = addLine(s2, start.id, pid2, { construction })
      commit(s3)
      setPendingPoints([])
      return
    }
    if (tool === 'circle') {
      // Click 1 = center, Click 2 = on-circle (defines radius).
      if (pendingPoints.length === 0) {
        const { sketch: s1, id: pid } = ensurePointAt(sketch, sn, w)
        commit(s1)
        setPendingPoints([{ id: pid }])
        return
      }
      const center = pendingPoints[0]
      const cEnt = sketch.entities.find((x) => x.id === center.id)
      const radius = cEnt ? Math.hypot(w.x - cEnt.x, w.y - cEnt.y) : 10
      const { sketch: s1 } = addCircle(sketch, center.id, radius, { construction })
      commit(s1)
      setPendingPoints([])
      return
    }
    if (tool === 'arc') {
      // 3-point arc: start, end, mid (the mid defines the curvature).
      const { sketch: s1, id: pid } = ensurePointAt(sketch, sn, w)
      if (pendingPoints.length === 0) {
        commit(s1)
        setPendingPoints([{ id: pid, role: 'start' }])
        return
      }
      if (pendingPoints.length === 1) {
        const { sketch: s2, id: pid2 } = ensurePointAt(s1, sn, w)
        commit(s2)
        setPendingPoints([...pendingPoints, { id: pid2, role: 'end' }])
        return
      }
      // Third click: derive center from the three points.
      const start = sketch.entities.find((x) => x.id === pendingPoints[0].id)
      const end = sketch.entities.find((x) => x.id === pendingPoints[1].id)
      if (!start || !end) {
        setPendingPoints([])
        return
      }
      const mid = { x: w.x, y: w.y }
      const center = circumCenter(start, end, mid)
      if (!center) {
        setPendingPoints([])
        return
      }
      // Compute sweep direction from start→mid→end.
      const ccw = signOfCross(start, mid, end) > 0
      const { sketch: sA, id: cId } = addPoint(sketch, center.x, center.y)
      const { sketch: sB } = addArc(sA, cId, pendingPoints[0].id, pendingPoints[1].id, ccw, { construction })
      commit(sB)
      setPendingPoints([])
      return
    }
    if (tool === 'rect') {
      // Two-click axis-aligned rectangle. Composed of 4 lines + 2 H + 2 V
      // constraints.
      if (pendingPoints.length === 0) {
        const { sketch: s1, id: pid } = ensurePointAt(sketch, sn, w)
        commit(s1)
        setPendingPoints([{ id: pid }])
        return
      }
      const start = sketch.entities.find((x) => x.id === pendingPoints[0].id)
      if (!start) { setPendingPoints([]); return }
      const tl = start
      const br = { x: w.x, y: w.y }
      // Construct the 4 corners (3 new + 1 existing).
      const { sketch: s1, id: trId } = addPoint(sketch, br.x, tl.y)
      const { sketch: s2, id: brId } = addPoint(s1, br.x, br.y)
      const { sketch: s3, id: blId } = addPoint(s2, tl.x, br.y)
      // 4 lines.
      const { sketch: s4, id: top } = addLine(s3, tl.id, trId, { construction })
      const { sketch: s5, id: right } = addLine(s4, trId, brId, { construction })
      const { sketch: s6, id: bottom } = addLine(s5, brId, blId, { construction })
      const { sketch: s7, id: left } = addLine(s6, blId, tl.id, { construction })
      // Constraints: 2 horizontal + 2 vertical. Avoid double-perpendicular —
      // the H/V pair fully orients the rect.
      let s8 = s7
      ;({ sketch: s8 } = addConstraint(s8, 'horizontal', { line: top }))
      ;({ sketch: s8 } = addConstraint(s8, 'horizontal', { line: bottom }))
      ;({ sketch: s8 } = addConstraint(s8, 'vertical',   { line: left }))
      ;({ sketch: s8 } = addConstraint(s8, 'vertical',   { line: right }))
      commit(s8)
      setPendingPoints([])
      return
    }
  }, [tool, sketch, pendingPoints, construction, commit])

  // ---- Constraint application from selection -----------------------------

  const applyConstraint = useCallback((kind) => {
    const sel = selection
    if (sel.length === 0) return
    const ent = sketch.entities || []
    const get = (id) => ent.find((e) => e.id === id)

    function isLine(id) { return get(id)?.type === 'line' }
    function isPoint(id) { return get(id)?.type === 'point' }
    function isCircleArc(id) { const t = get(id)?.type; return t === 'circle' || t === 'arc' }

    let next = null
    if (kind === 'horizontal' || kind === 'vertical') {
      for (const id of sel) if (isLine(id)) {
        ;({ sketch: next } = addConstraint(next || sketch, kind, { line: id }))
      }
    } else if (kind === 'parallel' || kind === 'perpendicular' || kind === 'equal_length') {
      const lines = sel.filter(isLine)
      if (lines.length >= 2) {
        ;({ sketch: next } = addConstraint(sketch, kind, { a: lines[0], b: lines[1] }))
      }
    } else if (kind === 'tangent') {
      if (sel.length >= 2) {
        ;({ sketch: next } = addConstraint(sketch, 'tangent', { a: sel[0], b: sel[1] }))
      }
    } else if (kind === 'equal_radius') {
      const cs = sel.filter(isCircleArc)
      if (cs.length >= 2) {
        ;({ sketch: next } = addConstraint(sketch, 'equal_radius', { a: cs[0], b: cs[1] }))
      }
    } else if (kind === 'coincident') {
      const ps = sel.filter(isPoint)
      if (ps.length >= 2) {
        ;({ sketch: next } = addConstraint(sketch, 'coincident', { a: ps[0], b: ps[1] }))
      }
    } else if (kind === 'symmetric') {
      // Need 2 points + 1 line.
      const ps = sel.filter(isPoint)
      const lns = sel.filter(isLine)
      if (ps.length >= 2 && lns.length >= 1) {
        ;({ sketch: next } = addConstraint(sketch, 'symmetric', { a: ps[0], b: ps[1], line: lns[0] }))
      }
    } else if (kind === 'block') {
      // Pin everything in the selection in place.
      ;({ sketch: next } = addConstraint(sketch, 'block', { refs: sel.slice() }))
    } else if (kind === 'point_on_line') {
      const ps = sel.filter(isPoint)
      const lns = sel.filter(isLine)
      if (ps.length >= 1 && lns.length >= 1) {
        ;({ sketch: next } = addConstraint(sketch, 'point_on_line', { point: ps[0], line: lns[0] }))
      }
    } else if (kind === 'point_on_arc') {
      const ps = sel.filter(isPoint)
      const cs = sel.filter(isCircleArc)
      if (ps.length >= 1 && cs.length >= 1) {
        ;({ sketch: next } = addConstraint(sketch, 'point_on_arc', { point: ps[0], arc: cs[0] }))
      }
    } else if (kind === 'distance') {
      // Auto-pick by selection types.
      if (sel.length === 1 && isCircleArc(sel[0])) {
        // Radius dimension prompt.
        const e = get(sel[0])
        const v = e?.radius || 10
        setDimensionPrompt({ kind: 'radius', refs: { circle: sel[0] }, defaultValue: v })
        return
      }
      if (sel.length === 2 && sel.every(isLine)) {
        setDimensionPrompt({ kind: 'angle', refs: { a: sel[0], b: sel[1] }, defaultValue: 90 })
        return
      }
      if (sel.length === 2 && sel.every(isPoint)) {
        const a = get(sel[0]); const b = get(sel[1])
        const v = a && b ? Math.hypot(a.x - b.x, a.y - b.y) : 10
        setDimensionPrompt({ kind: 'distance', refs: { a: sel[0], b: sel[1] }, defaultValue: round(v) })
        return
      }
      if (sel.length === 1 && isLine(sel[0])) {
        const ln = get(sel[0])
        const p1 = get(ln.p1); const p2 = get(ln.p2)
        const v = p1 && p2 ? Math.hypot(p1.x - p2.x, p1.y - p2.y) : 10
        // Treat line-length dimension as a p2p_distance between its endpoints.
        setDimensionPrompt({ kind: 'distance', refs: { a: ln.p1, b: ln.p2 }, defaultValue: round(v) })
        return
      }
    }
    if (next) {
      commit(next)
      setSelection([])
    }
  }, [selection, sketch, commit])

  // Commit a dimension prompt.
  const commitDimension = useCallback((value) => {
    if (!dimensionPrompt) return
    let next = null
    if (dimensionPrompt.kind === 'distance') {
      ;({ sketch: next } = addConstraint(sketch, 'distance', { ...dimensionPrompt.refs, value }))
    } else if (dimensionPrompt.kind === 'angle') {
      ;({ sketch: next } = addConstraint(sketch, 'angle', { ...dimensionPrompt.refs, value }))
    } else if (dimensionPrompt.kind === 'radius') {
      ;({ sketch: next } = addConstraint(sketch, 'radius', { ...dimensionPrompt.refs, value }))
    }
    if (next) commit(next)
    setDimensionPrompt(null)
    setSelection([])
  }, [dimensionPrompt, sketch, commit])

  // ---- Toggle construction on selection ----------------------------------

  const flipConstructionOnSelection = useCallback(() => {
    if (selection.length === 0) return
    const next = toggleConstructionMany(sketch, selection)
    commit(next)
  }, [selection, sketch, commit])

  // ---- Pattern launchers --------------------------------------------------

  const openMirror = useCallback(() => {
    // Selection requires at least one entity to mirror plus an axis. Axis is
    // derived from a selected line (preferred) or two selected points.
    if (selection.length < 2) return
    const ent = sketch.entities || []
    const get = (id) => ent.find((e) => e.id === id)
    const lines = selection.filter((id) => get(id)?.type === 'line')
    const points = selection.filter((id) => get(id)?.type === 'point')
    let axis = null
    let consumed = new Set()
    if (lines.length >= 1) {
      const ln = get(lines[0])
      const p1 = get(ln.p1); const p2 = get(ln.p2)
      if (p1 && p2) {
        axis = { a: { x: p1.x, y: p1.y }, b: { x: p2.x, y: p2.y }, lineId: ln.id }
        consumed.add(lines[0])
      }
    } else if (points.length >= 2) {
      const a = get(points[0]); const b = get(points[1])
      axis = { a: { x: a.x, y: a.y }, b: { x: b.x, y: b.y }, lineId: null }
      consumed.add(points[0]); consumed.add(points[1])
    }
    if (!axis) return
    const targetIds = selection.filter((id) => !consumed.has(id))
    if (targetIds.length === 0) return
    setPatternPrompt({ kind: 'mirror', axis, targetIds, addSymmetric: true })
  }, [selection, sketch])

  const openLinearPattern = useCallback(() => {
    if (selection.length === 0) return
    const ent = sketch.entities || []
    const get = (id) => ent.find((e) => e.id === id)
    // Allow patterning any kind of entity (including points).
    const targetIds = selection.filter((id) => !!get(id))
    if (targetIds.length === 0) return
    setPatternPrompt({
      kind: 'linear', targetIds,
      dx: 10, dy: 0, count: 3,
    })
  }, [selection, sketch])

  const openPolarPattern = useCallback(() => {
    if (selection.length === 0) return
    const ent = sketch.entities || []
    const get = (id) => ent.find((e) => e.id === id)
    // First point in selection becomes the center; remaining are patterned.
    const points = selection.filter((id) => get(id)?.type === 'point')
    let center = { x: 0, y: 0 }
    let consumed = new Set()
    if (points.length >= 1) {
      const p = get(points[0])
      if (p) { center = { x: p.x, y: p.y }; consumed.add(points[0]) }
    }
    const targetIds = selection.filter((id) => !consumed.has(id))
    if (targetIds.length === 0) return
    setPatternPrompt({
      kind: 'polar', targetIds, center,
      totalAngleDeg: 360, count: 6,
    })
  }, [selection, sketch])

  const commitPattern = useCallback((prompt, opts = {}) => {
    if (!prompt) return
    let next = null
    if (prompt.kind === 'mirror') {
      const r = mirrorEntities(sketch, prompt.targetIds, prompt.axis.a, prompt.axis.b, {
        addSymmetric: !!opts.addSymmetric && !!prompt.axis.lineId,
        axisLineId: prompt.axis.lineId,
      })
      next = r.sketch
    } else if (prompt.kind === 'linear') {
      const r = linearPattern(sketch, prompt.targetIds, opts.dx, opts.dy, Math.max(2, opts.count|0))
      next = r.sketch
    } else if (prompt.kind === 'polar') {
      const r = polarPattern(sketch, prompt.targetIds, prompt.center,
        (opts.totalAngleDeg * Math.PI) / 180, Math.max(2, opts.count|0))
      next = r.sketch
    }
    if (next) commit(next)
    setPatternPrompt(null)
    setSelection([])
  }, [sketch, commit])

  // ---- Fillet ------------------------------------------------------------

  const openFilletFromSelection = useCallback(() => {
    const ent = sketch.entities || []
    const get = (id) => ent.find((e) => e.id === id)
    const lines = selection.filter((id) => get(id)?.type === 'line')
    if (lines.length >= 2) {
      setFilletPrompt({ a: lines[0], b: lines[1], radius: lastFilletRadius })
    } else {
      setTool('fillet')
      setPendingPoints([])
    }
  }, [selection, sketch, lastFilletRadius])

  const commitFillet = useCallback((radius) => {
    if (!filletPrompt) return
    const r = filletCorner(sketch, filletPrompt.a, filletPrompt.b, Number(radius) || lastFilletRadius)
    if (r.sketch !== sketch) commit(r.sketch)
    setLastFilletRadius(Number(radius) || lastFilletRadius)
    setFilletPrompt(null)
    setSelection([])
  }, [filletPrompt, sketch, commit, lastFilletRadius])

  // ---- Trim / Extend invocation from canvas click -----------------------

  const trimAtClick = useCallback((world) => {
    const id = entityHitTest(sketch, world, view.scale)
    if (!id) return
    const next = trimAt(sketch, id, world)
    if (next !== sketch) commit(next)
  }, [sketch, view.scale, commit])

  // For Extend the user selects two entities sequentially: first the entity
  // to extend, then the target.
  const [extendState, setExtendState] = useState(null) // { extendId, near }
  const handleExtendClick = useCallback((world) => {
    const id = entityHitTest(sketch, world, view.scale)
    if (!id) return
    if (!extendState) {
      setExtendState({ extendId: id, near: world })
      return
    }
    const { extendId, near } = extendState
    setExtendState(null)
    if (extendId === id) return
    const next = extendTo(sketch, extendId, id, near)
    if (next !== sketch) commit(next)
  }, [sketch, view.scale, commit, extendState])

  const handleFilletClick = useCallback((world) => {
    const id = entityHitTest(sketch, world, view.scale)
    if (!id) return
    const ent = (sketch.entities || []).find((e) => e.id === id)
    if (!ent || ent.type !== 'line') return
    if (pendingPoints.length === 0) {
      setPendingPoints([{ id }])
    } else {
      const a = pendingPoints[0].id
      const b = id
      if (a === b) return
      setPendingPoints([])
      setFilletPrompt({ a, b, radius: lastFilletRadius })
    }
  }, [sketch, view.scale, pendingPoints, lastFilletRadius])

  // Keep the ref pointed at the live callbacks so handleToolClick stays valid.
  useEffect(() => {
    editHandlersRef.current = {
      trim: trimAtClick, extend: handleExtendClick, fillet: handleFilletClick,
    }
  }, [trimAtClick, handleExtendClick, handleFilletClick])

  // ---- Delete selected ----------------------------------------------------

  const onDelete = useCallback(() => {
    if (selection.length === 0) return
    // If a selection is a constraint id, drop just it; otherwise treat as
    // entity deletion (with cascade).
    const consSet = new Set((sketch.constraints || []).map((c) => c.id))
    let next = sketch
    const toDeleteEntities = []
    for (const id of selection) {
      if (consSet.has(id)) next = deleteConstraint(next, id)
      else toDeleteEntities.push(id)
    }
    if (toDeleteEntities.length > 0) next = deleteEntities(next, toDeleteEntities)
    commit(next)
    setSelection([])
  }, [selection, sketch, commit])

  // ---- Keyboard shortcuts ------------------------------------------------
  useEffect(() => {
    function onKey(e) {
      // Ignore typing in inputs/textareas.
      const t = e.target
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return
      const k = e.key.toLowerCase()
      const shift = e.shiftKey
      // Match shift+letter combos first.
      if (shift) {
        if (k === 't') { e.preventDefault(); flipConstructionOnSelection(); return }
        if (k === 'e') { e.preventDefault(); setTool('ellipse'); setPendingPoints([]); return }
        if (k === 'l') { e.preventDefault(); openLinearPattern(); return }
        if (k === 'p') { e.preventDefault(); openPolarPattern(); return }
      }
      const tools = TOOLS.find((x) => x.key && !x.key.includes('shift+') && x.key.toLowerCase() === k)
      if (tools) { e.preventDefault(); setTool(tools.id); setPendingPoints([]); return }
      if (k === 'h') { e.preventDefault(); applyConstraint('horizontal'); return }
      if (k === 'v') { e.preventDefault(); applyConstraint('vertical'); return }
      if (k === 'd') { e.preventDefault(); applyConstraint('distance'); return }
      if (k === 'm') { e.preventDefault(); openMirror(); return }
      if (k === 't') { e.preventDefault(); setTool('trim'); setPendingPoints([]); return }
      if (k === 'e') { e.preventDefault(); setTool('extend'); setPendingPoints([]); return }
      if (k === 'f') { e.preventDefault(); openFilletFromSelection(); return }
      if (e.key === 'Escape') {
        e.preventDefault()
        setPendingPoints([]); setTool('select'); setSelection([])
        setFilletPrompt(null); setPatternPrompt(null); setDimensionPrompt(null)
        setExtendState(null)
        return
      }
      if (e.key === 'Delete' || e.key === 'Backspace') { e.preventDefault(); onDelete(); return }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applyConstraint, onDelete, selection, sketch])

  // ---- Drag-on-dimension to edit value -----------------------------------
  // Click-and-hold on a dimension's label, drag right/up to increase, left/
  // down to decrease. Sensitivity scales with current value so small values
  // change in fine increments. Solver re-runs on every delta tick.
  const onDimensionDragStart = useCallback((constraint, e) => {
    const startMouseX = e.clientX
    const startVal = Number(constraint.value) || 0
    setDimDrag({ id: constraint.id, kind: constraint.type, startVal })
    function step(curMouseX) {
      const dx = curMouseX - startMouseX
      // For angle, use 0.5°/px. For distance/radius/diameter, scale = max(0.1, |val|/100) per px.
      let next
      if (constraint.type === 'angle') {
        next = startVal + dx * 0.5
      } else {
        const sens = Math.max(0.05, Math.abs(startVal) / 100)
        next = startVal + dx * sens
      }
      // Clamp non-negative for radius/diameter/distance.
      if (constraint.type === 'radius' || constraint.type === 'diameter' || constraint.type === 'distance') {
        next = Math.max(0.001, next)
      }
      // Snap to 2 decimal places to make the label readable.
      next = Math.round(next * 100) / 100
      const nextSketch = setConstraintValue(sketch, constraint.id, next)
      // Optimistic display + debounced solve.
      onChange?.(nextSketch)
      triggerSolve(nextSketch)
    }
    function onMove(ev) { step(ev.clientX) }
    function onUp() {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
      setDimDrag(null)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [sketch, onChange, triggerSolve])

  // ---- Render ------------------------------------------------------------

  // Status badge color.
  const statusColor =
    status === 'fully' ? 'text-emerald-400'
    : status === 'over' || status === 'conflict' ? 'text-red-400'
    : status === 'under' ? 'text-kerf-300'
    : 'text-ink-500'
  const statusLabel =
    status === 'fully' ? 'Fully constrained'
    : status === 'over' ? 'Over-constrained'
    : status === 'conflict' ? 'Conflict'
    : status === 'under' ? `Under-constrained · DOF ${Math.max(0, dofCount)}`
    : 'Solving…'

  return (
    <div className="h-full flex bg-ink-950 text-ink-100 min-h-0 relative" ref={containerRef}>
      {/* Left palette */}
      <div className="w-12 flex-shrink-0 flex flex-col items-center py-2 gap-1 border-r border-ink-800 overflow-y-auto">
        {TOOLS.map((t) => (
          <ToolButton key={t.id} tool={t} active={tool === t.id} onClick={() => { setTool(t.id); setPendingPoints([]) }} />
        ))}
        <div className="w-7 my-1 border-t border-ink-800" />
        {EDIT_TOOLS.map((t) => (
          <ToolButton
            key={t.id}
            tool={t}
            active={tool === t.id}
            onClick={() => {
              if (t.id === 'mirror') openMirror()
              else if (t.id === 'linear') openLinearPattern()
              else if (t.id === 'polar') openPolarPattern()
              else if (t.id === 'fillet') openFilletFromSelection()
              else { setTool(t.id); setPendingPoints([]) }
            }}
          />
        ))}
        <div className="w-7 my-1 border-t border-ink-800" />
        <ToolButton
          tool={{ id: 'construction', icon: Lock, label: `Construction mode — ${construction ? 'on' : 'off'}` }}
          active={construction}
          onClick={() => setConstruction((v) => !v)}
        />
        <ToolButton
          tool={{ id: 'flip-construction', icon: Unlock, label: 'Toggle construction on selection (Shift+T)' }}
          onClick={flipConstructionOnSelection}
          disabled={selection.length === 0}
        />
        <div className="w-7 my-1 border-t border-ink-800" />
        {CONSTRAINTS.map((c) => (
          <ToolButton
            key={c.id}
            tool={{ ...c, label: c.key ? `${c.label} (${c.key})` : c.label }}
            onClick={() => applyConstraint(c.id)}
            disabled={selection.length === 0 && c.id !== 'distance'}
          />
        ))}
      </div>

      {/* Canvas */}
      <div className="flex-1 min-w-0 min-h-0 relative bg-ink-950">
        {/* 3D backdrop (semi-transparent reference geometry) */}
        <SketchBackdrop3D
          sketch={sketch}
          view={view}
          loadParts={loadParts}
        />
        <svg
          ref={svgRef}
          className="w-full h-full select-none relative z-[1]"
          style={{ background: 'transparent' }}
          onWheel={onWheel}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={() => { setHover(null); setSnap(null); panRef.current = null; setDragging(null) }}
          onContextMenu={onContextMenu}
          onDoubleClick={onDoubleClick}
          style={{ cursor: dimDrag ? 'ew-resize' : tool === 'select' ? (dragging ? 'grabbing' : 'default') : 'crosshair' }}
        >
          <SketchGrid view={view} svgRef={svgRef} />
          <SketchAxes view={view} svgRef={svgRef} />
          <SketchEntities
            sketch={sketch}
            view={view}
            worldToScreen={worldToScreen}
            selection={selection}
            conflicts={conflicts || []}
            status={status}
            onDimensionDragStart={onDimensionDragStart}
          />
          {/* Pending preview (dashed) */}
          <PendingPreview
            tool={tool}
            sketch={sketch}
            pendingPoints={pendingPoints}
            hover={hover}
            worldToScreen={worldToScreen}
          />
          {/* Snap marker */}
          {snap && hover && <SnapMarker snap={snap} worldToScreen={worldToScreen} />}
        </svg>

        {/* Status badge bottom-left */}
        <div className="absolute bottom-3 left-3 px-2 py-1 rounded-md bg-ink-900/85 border border-ink-800 text-[11px] flex items-center gap-1.5 backdrop-blur">
          {status === 'fully' && <Check size={11} className={statusColor} />}
          {status === 'over' || status === 'conflict' ? <AlertTriangle size={11} className={statusColor} /> : null}
          <span className={statusColor}>{statusLabel}</span>
        </div>

        {/* Construction-mode banner */}
        {construction && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 px-2 py-1 rounded-md bg-kerf-300/15 border border-kerf-300/40 text-[11px] text-kerf-300">
            Construction mode — next entity will be reference geometry
          </div>
        )}

        {/* Dimension prompt */}
        {dimensionPrompt && (
          <DimensionPrompt
            spec={dimensionPrompt}
            onCommit={commitDimension}
            onCancel={() => setDimensionPrompt(null)}
          />
        )}

        {/* Fillet prompt */}
        {filletPrompt && (
          <FilletPrompt
            initial={lastFilletRadius}
            onCommit={commitFillet}
            onCancel={() => setFilletPrompt(null)}
          />
        )}

        {/* Pattern prompt */}
        {patternPrompt && (
          <PatternPrompt
            spec={patternPrompt}
            onCommit={(opts) => commitPattern(patternPrompt, opts)}
            onCancel={() => setPatternPrompt(null)}
          />
        )}

        {/* Tool hint banner */}
        {(tool === 'trim' || tool === 'extend' || tool === 'fillet') && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 px-2 py-1 rounded-md bg-amber-300/15 border border-amber-300/40 text-[11px] text-amber-200 z-[3]">
            {tool === 'trim' && 'Trim — click any segment between two intersections'}
            {tool === 'extend' && (extendState
              ? 'Extend — click the target entity to extend to'
              : 'Extend — click the entity to extend (near the end)')}
            {tool === 'fillet' && (pendingPoints.length === 0
              ? 'Fillet — click first line'
              : 'Fillet — click second line of the corner')}
          </div>
        )}
      </div>

      {/* Right inspector */}
      <SketchInspector
        sketch={sketch}
        files={files}
        selection={selection}
        onSelect={setSelection}
        onChange={commit}
        onDelete={onDelete}
      />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Sub-components.

function ToolButton({ tool, active, onClick, disabled }) {
  const Icon = tool.icon
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={tool.label}
      className={`w-9 h-9 rounded flex items-center justify-center
        ${active ? 'bg-kerf-300/20 text-kerf-300 ring-1 ring-kerf-300/40' : 'text-ink-300 hover:bg-ink-800 hover:text-kerf-300'}
        ${disabled ? 'opacity-30 cursor-not-allowed hover:bg-transparent' : ''}`}
    >
      <Icon size={14} />
    </button>
  )
}

// Render an infinite-feel grid behind the sketch entities. We compute the
// world-space bounds of the visible canvas and emit minor gridlines every
// `step` mm. Step adapts to zoom so the grid never gets too dense.
function SketchGrid({ view, svgRef }) {
  const r = svgRef.current?.getBoundingClientRect()
  if (!r) return null
  // Choose step so it's ~50px on screen.
  const target = 50
  const raw = target / view.scale
  const step = niceStep(raw)
  const halfW = r.width / view.scale / 2
  const halfH = r.height / view.scale / 2
  const minX = view.cx - halfW
  const maxX = view.cx + halfW
  const minY = view.cy - halfH
  const maxY = view.cy + halfH
  const lines = []
  let i = 0
  for (let x = Math.ceil(minX / step) * step; x <= maxX; x += step) {
    const sx = (x - view.cx) * view.scale + r.width / 2
    lines.push(<line key={`vx${i++}`} x1={sx} x2={sx} y1={0} y2={r.height} stroke="#1a1d24" strokeWidth={0.5} />)
  }
  i = 0
  for (let y = Math.ceil(minY / step) * step; y <= maxY; y += step) {
    const sy = -(y - view.cy) * view.scale + r.height / 2
    lines.push(<line key={`hy${i++}`} x1={0} x2={r.width} y1={sy} y2={sy} stroke="#1a1d24" strokeWidth={0.5} />)
  }
  return <g>{lines}</g>
}

function niceStep(raw) {
  const log = Math.log10(raw)
  const exp = Math.floor(log)
  const frac = log - exp
  const m = frac < 0.176 ? 1 : frac < 0.5 ? 2 : frac < 0.85 ? 5 : 10
  return m * Math.pow(10, exp)
}

function SketchAxes({ view, svgRef }) {
  const r = svgRef.current?.getBoundingClientRect()
  if (!r) return null
  const cx = r.width / 2 - view.cx * view.scale
  const cy = r.height / 2 + view.cy * view.scale
  return (
    <g>
      <line x1={0} x2={r.width} y1={cy} y2={cy} stroke="#2c333d" strokeWidth={1} />
      <line x1={cx} x2={cx} y1={0} y2={r.height} stroke="#2c333d" strokeWidth={1} />
    </g>
  )
}

// Render every entity. Color reflects constraint state.
function SketchEntities({ sketch, view, worldToScreen, selection, conflicts, status, onDimensionDragStart }) {
  const ent = sketch.entities || []
  const cons = sketch.constraints || []
  const conflictSet = new Set(conflicts || [])
  const selSet = new Set(selection || [])
  const pointById = new Map()
  for (const e of ent) if (e.type === 'point') pointById.set(e.id, e)

  function colorFor(e) {
    if (conflictSet.has(e.id)) return '#ef4444' // red
    if (e.construction) return status === 'fully' ? '#a3a8b3' : '#6b7280'
    if (status === 'over' || status === 'conflict') return '#ef4444'
    if (status === 'fully') return '#34d399' // emerald-400
    return '#5BB0FF' // kerf-300-ish
  }

  return (
    <g>
      {/* Lines */}
      {ent.filter((e) => e.type === 'line').map((e) => {
        const p1 = pointById.get(e.p1)
        const p2 = pointById.get(e.p2)
        if (!p1 || !p2) return null
        const a = worldToScreen(p1.x, p1.y)
        const b = worldToScreen(p2.x, p2.y)
        const col = colorFor(e)
        const sel = selSet.has(e.id)
        return (
          <line key={e.id}
            x1={a.x} y1={a.y} x2={b.x} y2={b.y}
            stroke={col}
            strokeWidth={sel ? 2 : 1.5}
            strokeDasharray={e.construction ? '4 3' : null}
            data-id={e.id}
          />
        )
      })}
      {/* Circles */}
      {ent.filter((e) => e.type === 'circle').map((e) => {
        const c = pointById.get(e.center)
        if (!c) return null
        const s = worldToScreen(c.x, c.y)
        const col = colorFor(e)
        const sel = selSet.has(e.id)
        return (
          <circle key={e.id}
            cx={s.x} cy={s.y}
            r={(e.radius || 0) * view.scale}
            stroke={col}
            strokeWidth={sel ? 2 : 1.5}
            strokeDasharray={e.construction ? '4 3' : null}
            fill="none"
            data-id={e.id}
          />
        )
      })}
      {/* Arcs (rendered via path) */}
      {ent.filter((e) => e.type === 'arc').map((e) => {
        const c = pointById.get(e.center)
        const s = pointById.get(e.start)
        const en = pointById.get(e.end)
        if (!c || !s || !en) return null
        const r = Math.hypot(s.x - c.x, s.y - c.y)
        const startA = Math.atan2(s.y - c.y, s.x - c.x)
        const endA = Math.atan2(en.y - c.y, en.x - c.x)
        const sweep = e.sweep_ccw ? 1 : 0
        const a = worldToScreen(s.x, s.y)
        const b = worldToScreen(en.x, en.y)
        let largeArc = 0
        let dA = endA - startA
        if (e.sweep_ccw && dA < 0) dA += Math.PI * 2
        if (!e.sweep_ccw && dA > 0) dA -= Math.PI * 2
        if (Math.abs(dA) > Math.PI) largeArc = 1
        const col = colorFor(e)
        const sel = selSet.has(e.id)
        return (
          <path key={e.id}
            d={`M ${a.x} ${a.y} A ${r * view.scale} ${r * view.scale} 0 ${largeArc} ${sweep === 1 ? 0 : 1} ${b.x} ${b.y}`}
            stroke={col} strokeWidth={sel ? 2 : 1.5}
            strokeDasharray={e.construction ? '4 3' : null}
            fill="none" data-id={e.id}
          />
        )
      })}
      {/* Ellipses */}
      {ent.filter((e) => e.type === 'ellipse').map((e) => {
        const c = pointById.get(e.center)
        if (!c) return null
        const samples = tessellateEllipse(c.x, c.y, e.rx || 1, e.ry || 1, e.rotation || 0, 96)
        const d = samples.map((p, i) => `${i === 0 ? 'M' : 'L'} ${worldToScreen(p[0], p[1]).x} ${worldToScreen(p[0], p[1]).y}`).join(' ') + ' Z'
        const col = colorFor(e)
        const sel = selSet.has(e.id)
        return (
          <path key={e.id} d={d}
            stroke={col} strokeWidth={sel ? 2 : 1.5}
            strokeDasharray={e.construction ? '4 3' : null}
            fill="none" data-id={e.id} />
        )
      })}
      {/* B-splines */}
      {ent.filter((e) => e.type === 'bspline').map((e) => {
        const cps = (e.controls || []).map((id) => pointById.get(id)).filter(Boolean)
        if (cps.length < 4) return null
        const samples = tessellateBspline(cps, 16)
        const d = samples.map((p, i) => {
          const s = worldToScreen(p[0], p[1])
          return `${i === 0 ? 'M' : 'L'} ${s.x} ${s.y}`
        }).join(' ')
        const col = colorFor(e)
        const sel = selSet.has(e.id)
        return (
          <g key={e.id}>
            <path d={d}
              stroke={col} strokeWidth={sel ? 2 : 1.5}
              strokeDasharray={e.construction ? '4 3' : null}
              fill="none" data-id={e.id} />
            {/* Control polygon (faint dashed) */}
            <path
              d={cps.map((p, i) => {
                const s = worldToScreen(p.x, p.y)
                return `${i === 0 ? 'M' : 'L'} ${s.x} ${s.y}`
              }).join(' ')}
              stroke="#3a4150" strokeWidth={0.75} strokeDasharray="2 3"
              fill="none"
            />
          </g>
        )
      })}
      {/* Points (drawn last so they sit on top) */}
      {ent.filter((e) => e.type === 'point').map((e) => {
        const s = worldToScreen(e.x, e.y)
        const col = colorFor(e)
        const sel = selSet.has(e.id)
        return (
          <circle key={e.id}
            cx={s.x} cy={s.y} r={sel ? 3.5 : 2.5}
            fill={col}
            stroke={sel ? '#fff' : 'none'} strokeWidth={1}
            data-id={e.id}
          />
        )
      })}
      {/* Dimensional constraint labels */}
      {cons.map((c) => (
        <DimensionLabel
          key={c.id} c={c} sketch={sketch}
          worldToScreen={worldToScreen}
          onDragStart={onDimensionDragStart}
        />
      ))}
    </g>
  )
}

function DimensionLabel({ c, sketch, worldToScreen, onDragStart }) {
  // Place a label between the two referenced entities for distance/angle/radius.
  let pos = null
  let label = null
  if (c.type === 'distance' || c.type === 'distance_x' || c.type === 'distance_y') {
    const a = (sketch.entities || []).find((x) => x.id === c.a)
    const b = (sketch.entities || []).find((x) => x.id === c.b)
    if (!a || !b || a.type !== 'point' || b.type !== 'point') return null
    pos = worldToScreen((a.x + b.x) / 2, (a.y + b.y) / 2)
    const tag = c.type === 'distance_x' ? 'X ' : c.type === 'distance_y' ? 'Y ' : ''
    label = `${tag}${(c.value ?? 0).toFixed(2)} mm`
  } else if (c.type === 'radius' || c.type === 'diameter') {
    const circle = (sketch.entities || []).find((x) => x.id === c.circle)
    if (!circle) return null
    const center = (sketch.entities || []).find((x) => x.id === circle.center)
    if (!center) return null
    pos = worldToScreen(center.x + (circle.radius || 0) / 2, center.y)
    label = `${c.type === 'radius' ? 'R' : 'D'} ${(c.value ?? 0).toFixed(2)}`
  } else if (c.type === 'angle') {
    // Place at midpoint of the first referenced line.
    const a = (sketch.entities || []).find((x) => x.id === c.a)
    if (!a || a.type !== 'line') return null
    const p1 = (sketch.entities || []).find((x) => x.id === a.p1)
    const p2 = (sketch.entities || []).find((x) => x.id === a.p2)
    if (!p1 || !p2) return null
    pos = worldToScreen((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)
    label = `${(c.value ?? 0).toFixed(1)}°`
  }
  if (!pos || !label) return null
  // Choose a wider rect for X/Y labels
  const w = label.length * 5 + 14
  return (
    <g
      transform={`translate(${pos.x},${pos.y})`}
      style={{ cursor: 'ew-resize', pointerEvents: 'all' }}
      onMouseDown={(e) => {
        if (e.button !== 0) return
        e.preventDefault()
        e.stopPropagation()
        onDragStart?.(c, e)
      }}
    >
      <rect x={-w / 2} y={-8} width={w} height={14} rx={2}
        fill="rgba(15,18,23,0.92)" stroke="#3a4150" />
      <text x={0} y={3} textAnchor="middle" fontSize={9} fill="#cbd1da">{label}</text>
    </g>
  )
}

function SnapMarker({ snap, worldToScreen }) {
  const s = worldToScreen(snap.x, snap.y)
  if (snap.kind === 'point') return <rect x={s.x - 5} y={s.y - 5} width={10} height={10} fill="none" stroke="#fbbf24" strokeWidth={1} />
  if (snap.kind === 'midpoint') return <polygon points={`${s.x},${s.y - 6} ${s.x + 6},${s.y + 4} ${s.x - 6},${s.y + 4}`} fill="none" stroke="#fbbf24" strokeWidth={1} />
  if (snap.kind === 'center') return <g><line x1={s.x - 6} y1={s.y - 6} x2={s.x + 6} y2={s.y + 6} stroke="#fbbf24" strokeWidth={1} /><line x1={s.x - 6} y1={s.y + 6} x2={s.x + 6} y2={s.y - 6} stroke="#fbbf24" strokeWidth={1} /></g>
  if (snap.kind === 'grid') return <circle cx={s.x} cy={s.y} r={3} fill="none" stroke="#fbbf24" strokeWidth={1} />
  return null
}

function PendingPreview({ tool, sketch, pendingPoints, hover, worldToScreen }) {
  if (!hover || pendingPoints.length === 0) return null
  if (tool === 'line' && pendingPoints.length === 1) {
    const start = sketch.entities.find((e) => e.id === pendingPoints[0].id)
    if (!start) return null
    const a = worldToScreen(start.x, start.y)
    const b = worldToScreen(hover.x, hover.y)
    return <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#fbbf24" strokeWidth={1} strokeDasharray="3 2" />
  }
  if (tool === 'circle' && pendingPoints.length === 1) {
    const start = sketch.entities.find((e) => e.id === pendingPoints[0].id)
    if (!start) return null
    const cs = worldToScreen(start.x, start.y)
    // Convert world-radius to pixel radius via two world points 1mm apart.
    const ref = worldToScreen(start.x + 1, start.y)
    const pxPerMm = Math.hypot(ref.x - cs.x, ref.y - cs.y) || 1
    const r = Math.hypot(hover.x - start.x, hover.y - start.y) * pxPerMm
    return <circle cx={cs.x} cy={cs.y} r={r} fill="none" stroke="#fbbf24" strokeWidth={1} strokeDasharray="3 2" />
  }
  if (tool === 'rect' && pendingPoints.length === 1) {
    const start = sketch.entities.find((e) => e.id === pendingPoints[0].id)
    if (!start) return null
    const a = worldToScreen(start.x, start.y)
    const b = worldToScreen(hover.x, hover.y)
    return <rect x={Math.min(a.x, b.x)} y={Math.min(a.y, b.y)} width={Math.abs(a.x - b.x)} height={Math.abs(a.y - b.y)} fill="none" stroke="#fbbf24" strokeWidth={1} strokeDasharray="3 2" />
  }
  if (tool === 'arc' && pendingPoints.length >= 1) {
    const start = sketch.entities.find((e) => e.id === pendingPoints[0].id)
    if (!start) return null
    const a = worldToScreen(start.x, start.y)
    const b = worldToScreen(hover.x, hover.y)
    return <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#fbbf24" strokeWidth={1} strokeDasharray="3 2" />
  }
  if (tool === 'ellipse' && pendingPoints.length === 1) {
    const center = sketch.entities.find((e) => e.id === pendingPoints[0].id)
    if (!center) return null
    const cs = worldToScreen(center.x, center.y)
    const ref = worldToScreen(center.x + 1, center.y)
    const pxPerMm = Math.hypot(ref.x - cs.x, ref.y - cs.y) || 1
    const dx = hover.x - center.x, dy = hover.y - center.y
    const rx = Math.max(0.01, Math.hypot(dx, dy)) * pxPerMm
    const ry = rx / 2
    const rot = (Math.atan2(dy, dx) * 180) / Math.PI
    return <ellipse cx={cs.x} cy={cs.y} rx={rx} ry={ry}
      transform={`rotate(${-rot} ${cs.x} ${cs.y})`}
      fill="none" stroke="#fbbf24" strokeWidth={1} strokeDasharray="3 2" />
  }
  if (tool === 'bspline' && pendingPoints.length >= 1) {
    const cps = pendingPoints.map((p) => sketch.entities.find((e) => e.id === p.id)).filter(Boolean)
    if (cps.length < 1) return null
    const pts = [...cps, hover]
    const d = pts.map((p, i) => {
      const s = worldToScreen(p.x, p.y)
      return `${i === 0 ? 'M' : 'L'} ${s.x} ${s.y}`
    }).join(' ')
    return <path d={d} fill="none" stroke="#fbbf24" strokeWidth={1} strokeDasharray="3 2" />
  }
  return null
}

function DimensionPrompt({ spec, onCommit, onCancel }) {
  const [text, setText] = useState(String(spec.defaultValue || 0))
  return (
    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-ink-900 border border-kerf-300/40 rounded-md p-3 shadow-2xl flex items-center gap-2">
      <span className="text-[11px] uppercase tracking-wider text-ink-400">
        {spec.kind === 'angle' ? 'Angle (deg)' : spec.kind === 'radius' ? 'Radius (mm)' : 'Distance (mm)'}
      </span>
      <input
        autoFocus
        type="text"
        inputMode="decimal"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); const v = Number(text); if (Number.isFinite(v)) onCommit(v) }
          if (e.key === 'Escape') { e.preventDefault(); onCancel() }
        }}
        className="w-24 bg-ink-950 border border-ink-800 rounded px-2 py-1 text-xs font-mono text-ink-100 outline-none focus:border-kerf-300/60"
      />
      <button
        type="button"
        className="px-2 py-1 rounded bg-kerf-300 text-ink-950 text-[11px] font-medium"
        onClick={() => { const v = Number(text); if (Number.isFinite(v)) onCommit(v) }}
      >Set</button>
      <button
        type="button"
        className="px-2 py-1 rounded text-ink-400 hover:text-ink-100 text-[11px]"
        onClick={onCancel}
      >Cancel</button>
    </div>
  )
}

function FilletPrompt({ initial, onCommit, onCancel }) {
  const [text, setText] = useState(String(initial || 1))
  return (
    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-ink-900 border border-kerf-300/40 rounded-md p-3 shadow-2xl flex items-center gap-2 z-[5]">
      <span className="text-[11px] uppercase tracking-wider text-ink-400">Fillet radius (mm)</span>
      <input
        autoFocus
        type="text"
        inputMode="decimal"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') { e.preventDefault(); const v = Number(text); if (v > 0) onCommit(v) }
          if (e.key === 'Escape') { e.preventDefault(); onCancel() }
        }}
        className="w-20 bg-ink-950 border border-ink-800 rounded px-2 py-1 text-xs font-mono text-ink-100 outline-none focus:border-kerf-300/60"
      />
      <button type="button" className="px-2 py-1 rounded bg-kerf-300 text-ink-950 text-[11px] font-medium"
        onClick={() => { const v = Number(text); if (v > 0) onCommit(v) }}>Apply</button>
      <button type="button" className="px-2 py-1 rounded text-ink-400 hover:text-ink-100 text-[11px]"
        onClick={onCancel}>Cancel</button>
    </div>
  )
}

function PatternPrompt({ spec, onCommit, onCancel }) {
  const [count, setCount] = useState(spec.count || 3)
  const [dx, setDx] = useState(spec.dx ?? 10)
  const [dy, setDy] = useState(spec.dy ?? 0)
  const [angleDeg, setAngleDeg] = useState(spec.totalAngleDeg ?? 360)
  const [addSymmetric, setAddSymmetric] = useState(spec.addSymmetric ?? true)
  const isMirror = spec.kind === 'mirror'
  const isLinear = spec.kind === 'linear'
  const isPolar = spec.kind === 'polar'
  function submit() {
    if (isMirror) onCommit({ addSymmetric })
    else if (isLinear) onCommit({ dx: Number(dx), dy: Number(dy), count: Number(count) | 0 })
    else if (isPolar) onCommit({ totalAngleDeg: Number(angleDeg), count: Number(count) | 0 })
  }
  return (
    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-ink-900 border border-kerf-300/40 rounded-md p-4 shadow-2xl space-y-2 z-[5] w-72">
      <div className="text-[11px] uppercase tracking-wider text-ink-400">
        {isMirror ? 'Mirror' : isLinear ? 'Linear pattern' : 'Polar pattern'}
      </div>
      {isLinear && (
        <>
          <NumField label="dx (mm)" value={dx} onChange={setDx} />
          <NumField label="dy (mm)" value={dy} onChange={setDy} />
          <NumField label="count" value={count} onChange={setCount} />
        </>
      )}
      {isPolar && (
        <>
          <NumField label="total angle (deg)" value={angleDeg} onChange={setAngleDeg} />
          <NumField label="count" value={count} onChange={setCount} />
          <div className="text-[10px] text-ink-500">
            Center: ({spec.center?.x?.toFixed?.(2)}, {spec.center?.y?.toFixed?.(2)})
          </div>
        </>
      )}
      {isMirror && (
        <>
          <div className="text-[11px] text-ink-300">
            Mirroring {spec.targetIds.length} entit{spec.targetIds.length === 1 ? 'y' : 'ies'} across selected axis.
          </div>
          {spec.axis.lineId && (
            <label className="flex items-center gap-2 text-[11px] text-ink-200">
              <input type="checkbox" checked={addSymmetric}
                onChange={(e) => setAddSymmetric(e.target.checked)} className="accent-kerf-300" />
              Add symmetric constraints
            </label>
          )}
        </>
      )}
      <div className="flex justify-end gap-2 pt-1">
        <button type="button" className="px-2 py-1 rounded text-ink-400 hover:text-ink-100 text-[11px]"
          onClick={onCancel}>Cancel</button>
        <button type="button" className="px-2 py-1 rounded bg-kerf-300 text-ink-950 text-[11px] font-medium"
          onClick={submit}>Apply</button>
      </div>
    </div>
  )
}

function NumField({ label, value, onChange }) {
  return (
    <label className="flex items-center justify-between gap-2">
      <span className="text-[11px] text-ink-400">{label}</span>
      <input
        type="text"
        inputMode="decimal"
        value={String(value)}
        onChange={(e) => onChange(e.target.value)}
        className="w-24 bg-ink-950 border border-ink-800 rounded px-2 py-1 text-xs font-mono text-ink-100 outline-none focus:border-kerf-300/60"
      />
    </label>
  )
}

// ---------------------------------------------------------------------------
// 3D backdrop — three.js scene rendered behind the SVG, showing the
// `sketch.visible_3d` parts at semi-transparent reference opacity. The
// camera is locked to the sketch plane (XY for v2). Re-renders on parts /
// view (zoom) changes; pans are applied to the scene's frustum so 3D content
// stays aligned with the SVG world coordinates.
function SketchBackdrop3D({ sketch, view, loadParts }) {
  const mountRef = useRef(null)
  const stateRef = useRef(null)
  const visibleIds = useMemo(() => sketch?.visible_3d || [], [sketch?.visible_3d])

  // Setup scene once.
  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.setPixelRatio(window.devicePixelRatio || 1)
    renderer.setClearColor(0x000000, 0)
    mount.appendChild(renderer.domElement)
    renderer.domElement.style.display = 'block'
    renderer.domElement.style.width = '100%'
    renderer.domElement.style.height = '100%'
    const scene = new THREE.Scene()
    // Orthographic camera looking down +Z (XY plane).
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, -10000, 10000)
    camera.position.set(0, 0, 100)
    camera.up.set(0, 1, 0)
    camera.lookAt(0, 0, 0)
    scene.add(new THREE.AmbientLight(0xffffff, 0.6))
    const dir = new THREE.DirectionalLight(0xffffff, 0.4)
    dir.position.set(50, 50, 100)
    scene.add(dir)
    const meshGroup = new THREE.Group()
    const edgeGroup = new THREE.Group()
    scene.add(meshGroup, edgeGroup)
    const ro = new ResizeObserver(() => {
      const r = mount.getBoundingClientRect()
      renderer.setSize(r.width, r.height, false)
      // re-frame on resize too (handled in second effect)
      stateRef.current.dirty = true
    })
    ro.observe(mount)
    stateRef.current = { renderer, scene, camera, meshGroup, edgeGroup, ro, dirty: true }
    let raf = 0
    function tick() {
      const s = stateRef.current
      if (!s) return
      if (s.dirty) {
        // Apply view transform.
        const r = mount.getBoundingClientRect()
        const halfW = (r.width / view.scale) / 2
        const halfH = (r.height / view.scale) / 2
        camera.left = view.cx - halfW
        camera.right = view.cx + halfW
        camera.bottom = view.cy - halfH
        camera.top = view.cy + halfH
        camera.updateProjectionMatrix()
        s.dirty = false
      }
      renderer.render(scene, camera)
      raf = requestAnimationFrame(tick)
    }
    tick()
    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      renderer.dispose()
      mount.removeChild(renderer.domElement)
      stateRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Mark dirty on view change.
  useEffect(() => {
    if (stateRef.current) stateRef.current.dirty = true
  }, [view])

  // Load parts for visible_3d; rebuild meshes whenever it changes.
  useEffect(() => {
    const s = stateRef.current
    if (!s) return
    const { meshGroup, edgeGroup } = s
    // Clear.
    while (meshGroup.children.length) {
      const m = meshGroup.children[0]
      meshGroup.remove(m); m.geometry?.dispose(); m.material?.dispose()
    }
    while (edgeGroup.children.length) {
      const m = edgeGroup.children[0]
      edgeGroup.remove(m); m.geometry?.dispose(); m.material?.dispose()
    }
    if (!loadParts) { s.dirty = true; return }
    let cancelled = false
    ;(async () => {
      for (const fileId of visibleIds) {
        try {
          const parts = await loadParts(fileId)
          if (cancelled) return
          for (const p of parts || []) {
            if (!p?.geom) continue
            let geom
            if (p.geom.isBufferGeometry) geom = p.geom.clone()
            else geom = geom3ToBufferGeometry(p.geom)
            if (!geom) continue
            const mat = new THREE.MeshStandardMaterial({
              color: 0x6b9bc9, transparent: true, opacity: 0.3,
              roughness: 0.6, metalness: 0.1, depthWrite: false,
            })
            const mesh = new THREE.Mesh(geom, mat)
            meshGroup.add(mesh)
            // Wireframe edges for definition.
            const eg = new THREE.EdgesGeometry(geom, 25)
            const edgeMat = new THREE.LineBasicMaterial({
              color: 0x8aa9ce, transparent: true, opacity: 0.45, depthWrite: false,
            })
            edgeGroup.add(new THREE.LineSegments(eg, edgeMat))
          }
        } catch (err) {
          console.warn('SketchBackdrop3D: load failed', fileId, err)
        }
      }
      s.dirty = true
    })()
    return () => { cancelled = true }
  }, [visibleIds, loadParts])

  return (
    <div
      ref={mountRef}
      className="absolute inset-0 z-0 pointer-events-none"
      style={{ opacity: 0.85 }}
    />
  )
}

// ---------------------------------------------------------------------------
// Right-rail inspector: selection details + visible-3D picker.

function SketchInspector({ sketch, files, selection, onSelect, onChange, onDelete }) {
  const cons = sketch.constraints || []

  const selectedConstraints = (cons || []).filter((c) => selection.includes(c.id))

  const eligibleFor3D = (files || []).filter((f) =>
    f.kind !== 'folder' && f.kind !== 'drawing' && f.kind !== 'sketch')

  function toggle3D(fileId) {
    const cur = sketch.visible_3d || []
    const next = cur.includes(fileId) ? cur.filter((x) => x !== fileId) : [...cur, fileId]
    onChange({ ...sketch, visible_3d: next })
  }

  return (
    <aside className="w-64 flex-shrink-0 border-l border-ink-800 flex flex-col min-h-0">
      <div className="p-2 border-b border-ink-800">
        <div className="text-[10px] uppercase tracking-wider text-ink-400 mb-1">Selection</div>
        {selection.length === 0 ? (
          <div className="text-xs text-ink-500">Nothing selected.</div>
        ) : (
          <div className="text-[11px] text-ink-200 font-mono">{selection.length} item{selection.length === 1 ? '' : 's'}</div>
        )}
      </div>

      {/* Constraint editors */}
      {selectedConstraints.length > 0 && (
        <div className="p-2 border-b border-ink-800 space-y-2 overflow-auto">
          {selectedConstraints.map((c) => (
            <ConstraintRow key={c.id} c={c}
              onChangeValue={(v) => onChange(setConstraintValue(sketch, c.id, v))}
              onDelete={() => onChange(deleteConstraint(sketch, c.id))}
            />
          ))}
        </div>
      )}

      {/* Ellipse param editor */}
      {selection.map((id) => {
        const e = (sketch.entities || []).find((x) => x.id === id)
        if (!e || e.type !== 'ellipse') return null
        return (
          <div key={`ell-${id}`} className="p-2 border-b border-ink-800 space-y-1.5">
            <div className="text-[10px] uppercase tracking-wider text-ink-400">Ellipse {e.id}</div>
            <NumField label="rx" value={e.rx?.toFixed?.(3) ?? e.rx}
              onChange={(v) => onChange({
                ...sketch,
                entities: sketch.entities.map((x) => x.id === e.id ? { ...x, rx: Number(v) || x.rx } : x),
              })} />
            <NumField label="ry" value={e.ry?.toFixed?.(3) ?? e.ry}
              onChange={(v) => onChange({
                ...sketch,
                entities: sketch.entities.map((x) => x.id === e.id ? { ...x, ry: Number(v) || x.ry } : x),
              })} />
            <NumField label="angle (rad)" value={(e.rotation || 0).toFixed(4)}
              onChange={(v) => onChange({
                ...sketch,
                entities: sketch.entities.map((x) => x.id === e.id ? { ...x, rotation: Number(v) || 0 } : x),
              })} />
          </div>
        )
      })}

      {/* Constraint list */}
      <div className="flex-1 min-h-0 overflow-auto p-2">
        <div className="text-[10px] uppercase tracking-wider text-ink-400 mb-1">All constraints ({cons.length})</div>
        {cons.length === 0 ? (
          <div className="text-[11px] text-ink-500">No constraints yet.</div>
        ) : (
          <ul className="space-y-1">
            {cons.map((c) => (
              <li key={c.id}>
                <button
                  type="button"
                  onClick={() => onSelect([c.id])}
                  className={`w-full text-left px-2 py-1 rounded text-[11px] font-mono
                    ${selection.includes(c.id) ? 'bg-kerf-300/15 text-kerf-100' : 'hover:bg-ink-800 text-ink-300'}`}
                >
                  <span className="text-ink-500">{c.type}</span>
                  {(c.value != null) && <span className="text-ink-200 ml-1">= {c.value}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* 3D context picker */}
      <div className="p-2 border-t border-ink-800 max-h-40 overflow-auto">
        <div className="text-[10px] uppercase tracking-wider text-ink-400 mb-1">3D context</div>
        {eligibleFor3D.length === 0 ? (
          <div className="text-[11px] text-ink-500">No 3D files in this project.</div>
        ) : (
          <ul className="space-y-1">
            {eligibleFor3D.map((f) => (
              <li key={f.id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={(sketch.visible_3d || []).includes(f.id)}
                  onChange={() => toggle3D(f.id)}
                  className="accent-kerf-300"
                />
                <span className="text-[11px] text-ink-200 font-mono truncate">{f.name}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {selection.length > 0 && (
        <div className="p-2 border-t border-ink-800">
          <button
            type="button"
            onClick={onDelete}
            className="w-full inline-flex items-center justify-center gap-1.5 px-2 py-1.5 rounded bg-red-950/40 border border-red-900/60 text-red-300 hover:bg-red-950/60 text-[11px]"
          >
            <Trash2 size={11} />
            Delete selection (Del)
          </button>
        </div>
      )}
    </aside>
  )
}

function ConstraintRow({ c, onChangeValue, onDelete }) {
  const editable = c.value != null
  const [draft, setDraft] = useState(c.value != null ? String(c.value) : '')
  useEffect(() => { setDraft(c.value != null ? String(c.value) : '') }, [c.value])
  return (
    <div className="border border-ink-800 rounded p-2 bg-ink-900">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[11px] font-mono text-ink-300">{c.type}</span>
        <button
          type="button"
          onClick={onDelete}
          className="text-ink-500 hover:text-red-400"
          title="Delete constraint"
        >
          <Trash2 size={11} />
        </button>
      </div>
      {editable && (
        <input
          type="text"
          inputMode="decimal"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={() => { const v = Number(draft); if (Number.isFinite(v)) onChangeValue(v) }}
          onKeyDown={(e) => { if (e.key === 'Enter') { e.target.blur() } }}
          className="w-full bg-ink-950 border border-ink-800 rounded px-2 py-1 font-mono text-[11px] text-ink-100 outline-none focus:border-kerf-300/60"
        />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Hit testing.

// Pick the first non-construction entity within ~6px of the cursor.
function entityHitTest(sketch, world, scale) {
  const TOL = 6 / scale
  const ent = sketch.entities || []
  const pointById = new Map()
  for (const e of ent) if (e.type === 'point') pointById.set(e.id, e)
  // Try lines.
  for (const e of ent) {
    if (e.type === 'line') {
      const p1 = pointById.get(e.p1)
      const p2 = pointById.get(e.p2)
      if (!p1 || !p2) continue
      if (distancePointLineSeg(world, p1, p2) < TOL) return e.id
    } else if (e.type === 'circle') {
      const c = pointById.get(e.center)
      if (!c) continue
      const d = Math.abs(Math.hypot(world.x - c.x, world.y - c.y) - (e.radius || 0))
      if (d < TOL) return e.id
    } else if (e.type === 'arc') {
      const c = pointById.get(e.center)
      const s = pointById.get(e.start)
      if (!c || !s) continue
      const r = Math.hypot(s.x - c.x, s.y - c.y)
      const d = Math.abs(Math.hypot(world.x - c.x, world.y - c.y) - r)
      if (d < TOL) return e.id
    } else if (e.type === 'ellipse') {
      const c = pointById.get(e.center)
      if (!c) continue
      // Cheap test: project into local axes, check normalized distance ≈ 1.
      const cs = Math.cos(-(e.rotation || 0))
      const sn = Math.sin(-(e.rotation || 0))
      const lx = (world.x - c.x) * cs - (world.y - c.y) * sn
      const ly = (world.x - c.x) * sn + (world.y - c.y) * cs
      const t = Math.hypot(lx / (e.rx || 1), ly / (e.ry || 1))
      const d = Math.abs(t - 1) * Math.min(e.rx || 1, e.ry || 1)
      if (d < TOL) return e.id
    } else if (e.type === 'bspline') {
      const cps = (e.controls || []).map((id) => pointById.get(id)).filter(Boolean)
      if (cps.length < 4) continue
      const samples = bsplineSamplesCache(e.id, cps)
      let best = Infinity
      for (let i = 0; i < samples.length - 1; i++) {
        const a = { x: samples[i][0], y: samples[i][1] }
        const b = { x: samples[i + 1][0], y: samples[i + 1][1] }
        const d = distancePointLineSeg(world, a, b)
        if (d < best) best = d
      }
      if (best < TOL) return e.id
    }
  }
  return null
}

// Tiny LRU cache for bspline samples — keyed by entity id, invalidated by
// control-point coordinate hash. Hit-test fires per click so re-tessellating
// 16 samples × 4-8 cps is cheap; the cache is mostly for ergonomics.
const _bsplineCache = new Map()
function bsplineSamplesCache(id, cps) {
  const sig = id + ':' + cps.map((p) => `${p.x},${p.y}`).join('|')
  const hit = _bsplineCache.get(id)
  if (hit && hit.sig === sig) return hit.samples
  const samples = tessellateBspline(cps, 16)
  _bsplineCache.set(id, { sig, samples })
  // bound size
  if (_bsplineCache.size > 64) _bsplineCache.delete(_bsplineCache.keys().next().value)
  return samples
}

function distancePointLineSeg(p, a, b) {
  const ax = a.x, ay = a.y
  const bx = b.x, by = b.y
  const dx = bx - ax, dy = by - ay
  const len2 = dx * dx + dy * dy
  if (len2 === 0) return Math.hypot(p.x - ax, p.y - ay)
  let t = ((p.x - ax) * dx + (p.y - ay) * dy) / len2
  t = Math.max(0, Math.min(1, t))
  const cx = ax + t * dx
  const cy = ay + t * dy
  return Math.hypot(p.x - cx, p.y - cy)
}

// ---------------------------------------------------------------------------
// Geometric helpers.

function circumCenter(a, b, c) {
  const d = 2 * (a.x * (b.y - c.y) + b.x * (c.y - a.y) + c.x * (a.y - b.y))
  if (Math.abs(d) < 1e-9) return null
  const ax2 = a.x * a.x + a.y * a.y
  const bx2 = b.x * b.x + b.y * b.y
  const cx2 = c.x * c.x + c.y * c.y
  const ux = (ax2 * (b.y - c.y) + bx2 * (c.y - a.y) + cx2 * (a.y - b.y)) / d
  const uy = (ax2 * (c.x - b.x) + bx2 * (a.x - c.x) + cx2 * (b.x - a.x)) / d
  return { x: ux, y: uy }
}

function signOfCross(a, b, c) {
  return Math.sign((b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x))
}

function round(v) {
  return Math.round(v * 100) / 100
}

// Re-exports used by the editor route.
export { parseSketch, serializeSketch }
