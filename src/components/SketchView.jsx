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
  Unlock, Crosshair, CircleDashed, CircleDot, Download,
} from 'lucide-react'
import * as THREE from 'three'
import {
  parseSketch, serializeSketch, solveSketch, solveWithDrag,
  planeFaceFrame,
} from '../lib/sketchSolver.js'
import {
  addPoint, addLine, addCircle, addArc, addEllipse, addBspline,
  addConstraint, addExternalCurve,
  setPointXY, toggleConstruction, toggleConstructionMany, setConstraintValue,
  deleteEntities, deleteConstraint, snapTarget, ensurePointAt,
  trimAt, extendTo, filletCorner,
  mirrorEntities, linearPattern, polarPattern,
} from '../lib/sketchEdit.js'
import { tessellateEllipse, tessellateBspline } from '../lib/sketchGeom2.js'
import { geom3ToBufferGeometry } from '../lib/geom3.js'
import {
  projectLineDraft, describeLineDraft,
  friendlyConstraintLabel, formatConstraintValue,
  constraintEntityRefs,
} from '../lib/sketchUI.js'

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
  { id: 'trim',        key: 'T',        icon: Scissors,           label: 'Trim (T)' },
  { id: 'extend',      key: 'E',        icon: ArrowRightToLine,   label: 'Extend (E)' },
  { id: 'fillet',      key: 'F',        icon: GitMerge,           label: 'Fillet (F)' },
  { id: 'mirror',      key: 'M',        icon: FlipHorizontal2,    label: 'Mirror (M)' },
  { id: 'linear',      key: 'shift+L',  icon: Grid3x3,            label: 'Linear pattern (Shift+L)' },
  { id: 'polar',       key: 'shift+P',  icon: RotateCw,           label: 'Polar pattern (Shift+P)' },
  { id: 'project_edge', key: 'shift+I', icon: Download,          label: 'Project Edge (Shift+I)' },
]

const CONSTRAINTS = [
  { id: 'horizontal',       key: 'H',   icon: MoveHorizontal, label: 'Horizontal' },
  { id: 'vertical',         key: 'V',   icon: MoveVertical,   label: 'Vertical' },
  { id: 'coincident',       key: '',    icon: Anchor,         label: 'Coincident' },
  { id: 'parallel',         key: '',    icon: Equal,          label: 'Parallel' },
  { id: 'perpendicular',   key: '',    icon: Triangle,       label: 'Perpendicular' },
  { id: 'tangent',          key: '',    icon: RotateCcw,      label: 'Tangent' },
  { id: 'equal_length',     key: '',    icon: Equal,          label: 'Equal length' },
  { id: 'equal_radius',     key: '',    icon: Equal,          label: 'Equal radius' },
  { id: 'symmetric',        key: '',    icon: FlipHorizontal2, label: 'Symmetric (2 pts + line)' },
  { id: 'block',            key: '',    icon: Pin,            label: 'Block (pin in place)' },
  { id: 'point_on_line',    key: '',    icon: Magnet,         label: 'Point on line' },
  { id: 'point_on_circle',  key: '',    icon: CircleDot,      label: 'Point on circle' },
  { id: 'point_on_arc',     key: '',    icon: BookmarkPlus,   label: 'Point on arc/circle' },
  { id: 'arc_on_circle',    key: '',    icon: CircleIcon,     label: 'Arc on circle' },
  { id: 'arc_on_arc',       key: '',    icon: Spline,         label: 'Arc on arc' },
  { id: 'intersection_point', key: '',   icon: Crosshair,     label: 'Intersection point' },
  { id: 'midpoint',         key: 'shift+M', icon: Crosshair,  label: 'Midpoint (point on line midpoint)' },
  { id: 'fixed',            key: 'shift+F', icon: Lock,       label: 'Fixed (lock point in place)' },
  { id: 'radius',           key: 'shift+R', icon: CircleDashed, label: 'Radius (circle/arc)' },
  { id: 'diameter',         key: 'shift+D', icon: CircleDot,   label: 'Diameter (circle/arc)' },
  { id: 'distance',         key: 'D',     icon: Ruler,        label: 'Dimension (auto)' },
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

  // Live numeric input while drawing a line (Onshape / AutoCAD-style "dynamic
  // input"). After the first click and before the second, the user can type a
  // length and/or angle to lock that part of the next endpoint. Tab toggles
  // the focused field; Enter commits the line at the typed values; Esc
  // cancels the in-flight line.
  //
  // Hold the authoritative values in a ref so typing doesn't trigger any
  // expensive canvas re-renders, AND mirror them in a small state object so
  // children can re-render based on prop diffs (and so eslint's react-hooks
  // rules don't complain about reading the ref during render). The two
  // diverge for at most one frame; that's fine for what they drive.
  const INITIAL_LINE_DRAFT = {
    length: '', angle: '',
    lockLength: false, lockAngle: false,
    snapTarget: null,        // {x, y} world-space override for the next click
    focus: 'length',         // which field has focus ('length' | 'angle')
  }
  const lineDraftRef = useRef(INITIAL_LINE_DRAFT)
  const [lineDraft, setLineDraft] = useState(INITIAL_LINE_DRAFT)
  const bumpLineDraft = useCallback(() => {
    // Mirror the ref into state so consumers reading via props see the latest.
    setLineDraft({ ...lineDraftRef.current })
  }, [])

  // Pulse-on-click highlight for constraint rows. When the user clicks a row
  // in the constraint list, we set `pulseConstraintId` so the linked entities
  // and the constraint label briefly glow. Auto-clears after ~1.4s.
  const [pulseConstraintId, setPulseConstraintId] = useState(null)
  const pulseTimerRef = useRef(null)
  const pulseConstraint = useCallback((cid) => {
    setPulseConstraintId(cid)
    if (pulseTimerRef.current) clearTimeout(pulseTimerRef.current)
    pulseTimerRef.current = setTimeout(() => setPulseConstraintId(null), 1400)
  }, [])

  // Resync when upstream sketch reference changes.
  //
  // CRITICAL: every commit / solver write-back updates the parent store, which
  // hands SketchView a fresh `sketch` prop on the next render. If we naively
  // wiped pendingPoints / selection on EVERY prop change, the second click of
  // every multi-click tool (line/circle/rect/arc/ellipse/bspline/fillet) would
  // never see its first click — pendingPoints would have been reset to [] by
  // the time the second click arrived. That's the "completely broken" bug.
  //
  // The fix: distinguish "our own commit/solve wrote this sketch back" from
  // "upstream restored / replaced the sketch externally". We accomplish this
  // by stashing every locally-produced sketch reference in `lastSketchRef`
  // BEFORE we call onChange/onSolved. When the prop arrives identical to a
  // ref we just stashed, the effect's identity check passes and we leave the
  // tool state alone. External replacements (LLM restore, file reload) still
  // trigger the wipe because they produce a sketch reference we never saw.
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
          // Stash the solver's output as our last-seen reference BEFORE
          // notifying the parent — when this same object arrives back as the
          // `sketch` prop on the next render the resync effect sees identity
          // match and preserves pendingPoints/selection.
          lastSketchRef.current = res.sketch
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
    // Stash the post-commit sketch as our last-seen reference so the resync
    // effect treats the upcoming prop change as a self-write and doesn't
    // wipe pendingPoints / selection (which would break every multi-click
    // tool — see the lastSketchRef comment above).
    lastSketchRef.current = next
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
      // Click on a point → optionally start drag. Click on entity → select.
      // Selection rules (FreeCAD-flavored, with the quality-of-life fix the
      // user asked for):
      //   - Shift+click toggles the entity in/out of the current multi-selection.
      //   - Plain click on an unselected entity → replace selection with [it].
      //   - Plain click on the *only* current selection → toggle it off (deselect).
      //   - Plain click on a point that's part of a multi-selection → keep the
      //     selection intact and start a drag of the clicked point (so the
      //     user can drag from inside their group without losing context).
      const hitId = sn?.kind === 'point' ? sn.id : entityHitTest(sketch, w, view.scale)
      if (hitId) {
        const ent = sketch.entities.find((x) => x.id === hitId)
        const wasSole = selection.length === 1 && selection[0] === hitId
        let nextSelection
        if (e.shiftKey) {
          nextSelection = selection.includes(hitId)
            ? selection.filter((x) => x !== hitId)
            : [...selection, hitId]
        } else if (wasSole) {
          nextSelection = []
        } else if (selection.includes(hitId)) {
          nextSelection = selection
        } else {
          nextSelection = [hitId]
        }
        setSelection(nextSelection)
        // Start drag only if the entity ended up selected and is a point.
        if (ent?.type === 'point' && nextSelection.includes(hitId)) {
          setDragging({ pointId: hitId, fromX: ent.x, fromY: ent.y })
        }
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
    // Refresh the line-draft snap target so the live numeric strip always
    // reflects "the next click's actual destination". When nothing is locked
    // the target IS the cursor; when length/angle are locked, the target is
    // the projected point along the locked direction at the locked length.
    if (tool === 'line' && pendingPoints.length === 1) {
      const start = sketch.entities.find((x) => x.id === pendingPoints[0].id)
      if (start) {
        const draft = lineDraftRef.current || {}
        const next = projectLineDraft(start, w, draft)
        if (next) {
          lineDraftRef.current = { ...draft, snapTarget: next }
          // Refresh the dashed preview and strip on cursor move.
          bumpLineDraft()
        }
      }
    }
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
      // Mark as a self-write so the resync effect doesn't wipe selection
      // (which would deselect the point we're actively dragging).
      lastSketchRef.current = optimistic
      onChange?.(optimistic)
      // Async solve; onSolved updates the displayed sketch with the
      // constraint-aware final position. We don't await to avoid stutter.
      solveWithDrag(optimistic, { pointId: dragging.pointId, x: tx, y: ty })
        .then((res) => {
          if (res?.sketch) {
            lastSketchRef.current = res.sketch
            onSolved?.(res.sketch, res.status, res.dofCount, res.conflicts)
          }
        })
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
    if (tool === 'project_edge') {
      // project_edge is handled via 3D backdrop clicks, not canvas clicks.
      // The backdrop will call onProjectEdge when an edge is picked.
      return
    }
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
      // First click — drop a start point (snapped if applicable) and remember
      // its id. Second click — drop an end point (or snap to an existing one)
      // and create the line connecting the two. Snapping to the start point
      // closes a loop seamlessly: ensurePointAt returns the existing id when
      // the cursor is within 8px of any point.
      if (pendingPoints.length === 0) {
        const { sketch: s1, id: pid } = ensurePointAt(sketch, sn, w)
        commit(s1)
        setPendingPoints([{ id: pid }])
        // Reset the live-numeric draft for a fresh line.
        lineDraftRef.current = {
          length: '', angle: '',
          lockLength: false, lockAngle: false,
          snapTarget: null, focus: 'length',
        }
        bumpLineDraft()
        return
      }
      const start = pendingPoints[0]
      // If the user typed a length / angle, override the cursor target. The
      // snapTarget is computed continuously by the live-input strip and
      // reflects the current cursor when nothing is locked.
      const draft = lineDraftRef.current || {}
      const target = draft.snapTarget || w
      // Resolve the second endpoint against the current sketch (which already
      // includes the first click's commit). ensurePointAt either snaps to an
      // existing point id or appends a fresh point — never both.
      const { sketch: s2, id: pid2 } = ensurePointAt(sketch, sn, target)
      // Refuse a degenerate line (start === end). Drop the pending state and
      // let the user click again — much friendlier than committing a zero-
      // length line that fails the solver in confusing ways.
      if (pid2 === start.id) {
        setPendingPoints([])
        return
      }
      const { sketch: s3, id: lineId } = addLine(s2, start.id, pid2, { construction })
      // Bake the locked Length / Angle as real constraints so future solves
      // hold those values. Length → distance(p1, p2). Angle → if cardinal
      // (0/90/180/270 within 1°) emit horizontal / vertical; otherwise emit
      // an angle constraint between this line and a reference horizontal
      // segment built from the start point. We avoid creating reference
      // entities for v1 — non-cardinal angle locks are baked into the
      // computed endpoint coords (the solver will keep them via the length
      // constraint + the point's initial position).
      let s4 = s3
      const lenVal = Number(draft.length)
      const angVal = Number(draft.angle)
      if (draft.lockLength && Number.isFinite(lenVal) && lenVal > 0) {
        ;({ sketch: s4 } = addConstraint(s4, 'distance', { a: start.id, b: pid2, value: lenVal }))
      }
      if (draft.lockAngle && Number.isFinite(angVal)) {
        const a = ((angVal % 360) + 360) % 360
        if (Math.abs(a) < 1e-3 || Math.abs(a - 180) < 1e-3) {
          ;({ sketch: s4 } = addConstraint(s4, 'horizontal', { line: lineId }))
        } else if (Math.abs(a - 90) < 1e-3 || Math.abs(a - 270) < 1e-3) {
          ;({ sketch: s4 } = addConstraint(s4, 'vertical', { line: lineId }))
        }
        // Non-cardinal angles: leave it as positional. A future revision can
        // emit a construction reference + l2l_angle constraint.
      }
      commit(s4)
      // Chain mode: keep the second endpoint as the next line's start so the
      // user can build a polyline / closed loop with N+1 clicks. ESC or right-
      // click breaks the chain (handled in onContextMenu / onKey).
      setPendingPoints([{ id: pid2 }])
      // Reset the live draft for the next segment.
      lineDraftRef.current = {
        length: '', angle: '',
        lockLength: false, lockAngle: false,
        snapTarget: null, focus: 'length',
      }
      bumpLineDraft()
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
      if (pendingPoints.length === 0) {
        const { sketch: s1, id: pid } = ensurePointAt(sketch, sn, w)
        commit(s1)
        setPendingPoints([{ id: pid, role: 'start' }])
        return
      }
      if (pendingPoints.length === 1) {
        const { sketch: s2, id: pid2 } = ensurePointAt(sketch, sn, w)
        if (pid2 === pendingPoints[0].id) return // degenerate; ignore
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
    } else if (kind === 'midpoint') {
      // Need 1 point + 1 line. The point is constrained to the midpoint
      // of the line; on solve the point will move (or stay, if already at
      // the midpoint).
      const ps = sel.filter(isPoint)
      const lns = sel.filter(isLine)
      if (ps.length >= 1 && lns.length >= 1) {
        ;({ sketch: next } = addConstraint(sketch, 'midpoint', { point: ps[0], line: lns[0] }))
      }
    } else if (kind === 'fixed') {
      // Lock every selected point at its current (x, y). We capture the
      // coords on the constraint itself so the solver pins the point even
      // if some upstream code mutates the entity's stored x/y. Mirrors how
      // `block` snapshots coordinates — but for a single point, with no
      // need to enumerate refs.
      const ps = sel.filter(isPoint)
      if (ps.length >= 1) {
        let acc = sketch
        for (const pid of ps) {
          const p = get(pid)
          if (!p) continue
          const px = typeof p.x === 'number' ? p.x : 0
          const py = typeof p.y === 'number' ? p.y : 0
          ;({ sketch: acc } = addConstraint(acc, 'fixed', { point: pid, x: px, y: py }))
        }
        next = acc
      }
    } else if (kind === 'radius') {
      // Exactly 1 circle or arc; prompt for radius value.
      const cs = sel.filter(isCircleArc)
      if (cs.length === 1) {
        const e = get(cs[0])
        const v = e?.radius || 10
        setDimensionPrompt({ kind: 'radius', refs: { circle: cs[0] }, defaultValue: round(v) })
        return
      }
    } else if (kind === 'diameter') {
      // Exactly 1 circle or arc; prompt for diameter value (= 2 × radius).
      const cs = sel.filter(isCircleArc)
      if (cs.length === 1) {
        const e = get(cs[0])
        const v = (e?.radius || 10) * 2
        setDimensionPrompt({ kind: 'diameter', refs: { circle: cs[0] }, defaultValue: round(v) })
        return
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
    } else if (dimensionPrompt.kind === 'diameter') {
      ;({ sketch: next } = addConstraint(sketch, 'diameter', { ...dimensionPrompt.refs, value }))
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
        if (k === 'm') { e.preventDefault(); applyConstraint('midpoint'); return }
        if (k === 'f') { e.preventDefault(); applyConstraint('fixed'); return }
        if (k === 'r') { e.preventDefault(); applyConstraint('radius'); return }
        if (k === 'd') { e.preventDefault(); applyConstraint('diameter'); return }
        if (k === 'i') { e.preventDefault(); setTool('project_edge'); setPendingPoints([]); return }
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
      // Optimistic display + debounced solve. Mark as self-write so the
      // resync effect doesn't drop the dimension's selection mid-drag.
      lastSketchRef.current = nextSketch
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
  // Plain-English status label per the brief. Dimensional accuracy comes
  // from planegcs's solve status; the DOF number is our heuristic estimate
  // (good enough to tell the user "you can still drag things around").
  const dofN = Math.max(0, dofCount | 0)
  const statusLabel =
    status === 'fully' ? 'Fully constrained'
    : status === 'over' ? 'Over-constrained: red'
    : status === 'conflict' ? 'Constraint conflict'
    : status === 'under' ? (dofN === 0
        ? '0 DOF remaining'
        : `${dofN} DOF remaining`)
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
          tool={tool}
          onProjectEdge={(edgeData) => {
            // Add the projected edge as an external_curve entity.
            const { sketch: next } = addExternalCurve(sketch, edgeData.fileId, edgeData.edgeId, edgeData.curveData)
            commit(next)
          }}
        />
        <svg
          ref={svgRef}
          className="w-full h-full select-none relative z-[1]"
          style={{
            background: 'transparent',
            cursor: dimDrag ? 'ew-resize' : tool === 'select' ? (dragging ? 'grabbing' : 'default') : 'crosshair',
          }}
          onWheel={onWheel}
          onMouseDown={onMouseDown}
          onMouseMove={onMouseMove}
          onMouseUp={onMouseUp}
          onMouseLeave={() => { setHover(null); setSnap(null); panRef.current = null; setDragging(null) }}
          onContextMenu={onContextMenu}
          onDoubleClick={onDoubleClick}
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
            pulseConstraintId={pulseConstraintId}
          />
          {/* Pending preview (dashed) */}
          <PendingPreview
            tool={tool}
            sketch={sketch}
            pendingPoints={pendingPoints}
            hover={hover}
            worldToScreen={worldToScreen}
            lineDraft={lineDraft}
          />
          {/* Snap marker */}
          {snap && hover && <SnapMarker snap={snap} worldToScreen={worldToScreen} />}
        </svg>

        {/* Live numeric input strip — shown while drawing the second click of
            a line. Lets the user type Length / Angle to lock the next click.
            Tab cycles fields; Enter commits at typed values; Esc cancels. */}
        {tool === 'line' && pendingPoints.length === 1 && hover && (
          <LineDraftStrip
            startEntity={sketch.entities.find((e) => e.id === pendingPoints[0].id)}
            cursor={hover}
            worldToScreen={worldToScreen}
            draft={lineDraft}
            draftRef={lineDraftRef}
            onChange={bumpLineDraft}
            onCommit={() => {
              // Synthesize a click commit at the projected target. The handler
              // path expects (world, snap); pass the locked target as both
              // the world coord and a fake null snap so the line tool falls
              // into its commit branch.
              const start = sketch.entities.find((e) => e.id === pendingPoints[0].id)
              const t = projectLineDraft(start, hover, lineDraftRef.current) || hover
              handleToolClick(t, null)
            }}
            onCancel={() => {
              // Drop pending state; keep the start point on disk (it's a real
              // ensurePointAt output and may already be referenced).
              setPendingPoints([])
              lineDraftRef.current = {
                length: '', angle: '',
                lockLength: false, lockAngle: false,
                snapTarget: null, focus: 'length',
              }
              bumpLineDraft()
            }}
          />
        )}

        {/* Inline entity mini-toolbar — context-aware quick constraints for
            the current selection. Single-line / single-circle / two-line / etc.
            Hidden during tool drawing or while panning. */}
        {tool === 'select' && selection.length >= 1 && !dragging && (
          <EntityMiniToolbar
            sketch={sketch}
            selection={selection}
            worldToScreen={worldToScreen}
            onApply={applyConstraint}
            onLockLength={(lineId) => {
              const ent = sketch.entities.find((x) => x.id === lineId)
              if (!ent || ent.type !== 'line') return
              const p1 = sketch.entities.find((x) => x.id === ent.p1)
              const p2 = sketch.entities.find((x) => x.id === ent.p2)
              if (!p1 || !p2) return
              const v = round(Math.hypot(p1.x - p2.x, p1.y - p2.y))
              setDimensionPrompt({ kind: 'distance', refs: { a: ent.p1, b: ent.p2 }, defaultValue: v })
            }}
            onLockAngle={(lineId) => {
              const ent = sketch.entities.find((x) => x.id === lineId)
              if (!ent || ent.type !== 'line') return
              const p1 = sketch.entities.find((x) => x.id === ent.p1)
              const p2 = sketch.entities.find((x) => x.id === ent.p2)
              if (!p1 || !p2) return
              // No reference axis; just bind to horizontal/vertical if cardinal.
              const dx = p2.x - p1.x, dy = p2.y - p1.y
              const a = ((Math.atan2(dy, dx) * 180) / Math.PI + 360) % 360
              if (Math.abs(a) < 5 || Math.abs(a - 180) < 5) {
                applyConstraint('horizontal')
              } else if (Math.abs(a - 90) < 5 || Math.abs(a - 270) < 5) {
                applyConstraint('vertical')
              } else {
                // Fall back: prompt the user for an explicit angle by selecting
                // a second line as the reference. Surfaced as a toast.
                /* no-op */
              }
            }}
          />
        )}

        {/* Status badge bottom-left — always shows DOF / fully-constrained
            state so users know where they stand. The constraint coloring on
            entities echoes this. Plain English labels per the brief. */}
        <div className="absolute bottom-3 left-3 px-2 py-1 rounded-md bg-ink-900/85 border border-ink-800 text-[11px] flex items-center gap-1.5 backdrop-blur"
          title={
            status === 'fully' ? 'All geometry is pinned by constraints — no degrees of freedom remain.'
            : status === 'over' ? 'Too many constraints. Some are redundant or contradictory.'
            : status === 'conflict' ? 'Constraints conflict — the solver could not find a position that satisfies them all.'
            : status === 'under' ? 'Some geometry can still move. Add dimensions or geometric constraints to lock it down.'
            : 'The constraint solver is running.'
          }
        >
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

        {/* Tool hint banner — surface the next-click contract whenever a non-
            select tool is armed, so users always know what the next click does.
            Snap markers (drawn separately) provide pixel-level feedback. */}
        {tool !== 'select' && (
          <div className="absolute top-3 left-1/2 -translate-x-1/2 px-2 py-1 rounded-md bg-amber-300/15 border border-amber-300/40 text-[11px] text-amber-200 z-[3]">
            {tool === 'point' && 'Point — click to place. ESC to exit.'}
            {tool === 'line' && (pendingPoints.length === 0
              ? 'Line — click the start point. ESC to exit.'
              : 'Line — click the next endpoint (snap to start to close a loop). ESC to finish.')}
            {tool === 'circle' && (pendingPoints.length === 0
              ? 'Circle — click the center.'
              : 'Circle — click on the circumference (radius).')}
            {tool === 'rect' && (pendingPoints.length === 0
              ? 'Rectangle — click first corner.'
              : 'Rectangle — click opposite corner.')}
            {tool === 'arc' && (pendingPoints.length === 0
              ? 'Arc — click start point.'
              : pendingPoints.length === 1
                ? 'Arc — click end point.'
                : 'Arc — click a point on the arc to set curvature.')}
            {tool === 'ellipse' && (pendingPoints.length === 0
              ? 'Ellipse — click center.'
              : 'Ellipse — click a point on the major axis.')}
            {tool === 'bspline' && (pendingPoints.length < 4
              ? `B-spline — add control points (${pendingPoints.length}/4 minimum). Double-click to finish.`
              : 'B-spline — keep clicking to add control points. Double-click to finish.')}
            {tool === 'trim' && 'Trim — click any segment between two intersections'}
            {tool === 'extend' && (extendState
              ? 'Extend — click the target entity to extend to'
              : 'Extend — click the entity to extend (near the end)')}
            {tool === 'fillet' && (pendingPoints.length === 0
              ? 'Fillet — click first line'
              : 'Fillet — click second line of the corner')}
            {tool === 'project_edge' && 'Project Edge — click on an edge in the 3D backdrop to project it into the sketch'}
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
        onPulse={pulseConstraint}
        pulseConstraintId={pulseConstraintId}
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
function SketchEntities({ sketch, view, worldToScreen, selection, conflicts, status, onDimensionDragStart, pulseConstraintId }) {
  const ent = sketch.entities || []
  const cons = sketch.constraints || []
  const conflictSet = new Set(conflicts || [])
  const selSet = new Set(selection || [])
  const pointById = new Map()
  for (const e of ent) if (e.type === 'point') pointById.set(e.id, e)

  // Compute the entity ids touched by the currently-pulsing constraint so we
  // can render a pulse outline. Highlights only entity references (skipping
  // the constraint's own id).
  const pulseEntityIds = new Set()
  if (pulseConstraintId) {
    const c = cons.find((x) => x.id === pulseConstraintId)
    if (c) {
      for (const r of constraintEntityRefs(c)) if (r) pulseEntityIds.add(r)
    }
  }

  function colorFor(e) {
    if (conflictSet.has(e.id)) return '#ef4444' // red — over-constrained
    if (e.construction) return status === 'fully' ? '#a3a8b3' : '#6b7280'
    if (status === 'over' || status === 'conflict') return '#ef4444'
    if (status === 'fully') return '#34d399' // green — fully constrained
    if (status === 'under') return '#9ca3af' // gray — still has DOFs
    return '#5BB0FF' // solving / unknown — kerf-blue
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
      {/* External curves (projected 3D reference geometry — always construction/dashed) */}
      {ent.filter((e) => e.type === 'external_curve').map((e) => {
        const col = status === 'fully' ? '#a3a8b3' : '#6b7280'
        if (e.curveType === 'line' && e.p1 && e.p2) {
          const a = worldToScreen(e.p1.x, e.p1.y)
          const b = worldToScreen(e.p2.x, e.p2.y)
          return (
            <line key={e.id}
              x1={a.x} y1={a.y} x2={b.x} y2={b.y}
              stroke={col} strokeWidth={1.5} strokeDasharray="4 3"
              data-id={e.id}
            />
          )
        }
        if (e.curveType === 'circle' && e.center && e.radius != null) {
          const c = worldToScreen(e.center.x, e.center.y)
          return (
            <circle key={e.id}
              cx={c.x} cy={c.y} r={e.radius * view.scale}
              stroke={col} strokeWidth={1.5} strokeDasharray="4 3"
              fill="none" data-id={e.id}
            />
          )
        }
        if (e.curveType === 'arc' && e.center && e.radius != null && e.startAngle != null && e.endAngle != null) {
          const cx = e.center.x, cy = e.center.y
          const sa = e.startAngle, ea = e.endAngle
          const r = e.radius
          const sweepCcw = e.sweepCCw ?? true
          const a1 = worldToScreen(cx + r * Math.cos(sa), cy + r * Math.sin(sa))
          const a2 = worldToScreen(cx + r * Math.cos(ea), cy + r * Math.sin(ea))
          let largeArc = 0
          let dA = ea - sa
          if (sweepCcw && dA < 0) dA += Math.PI * 2
          if (!sweepCcw && dA > 0) dA -= Math.PI * 2
          if (Math.abs(dA) > Math.PI) largeArc = 1
          return (
            <path key={e.id}
              d={`M ${a1.x} ${a1.y} A ${r * view.scale} ${r * view.scale} 0 ${largeArc} ${sweepCcw ? 0 : 1} ${a2.x} ${a2.y}`}
              stroke={col} strokeWidth={1.5} strokeDasharray="4 3"
              fill="none" data-id={e.id}
            />
          )
        }
        if (e.curveType === 'polyline' && Array.isArray(e.points) && e.points.length >= 2) {
          const ptsStr = e.points.map((p) => {
            const s = worldToScreen(p.x, p.y)
            return `${s.x},${s.y}`
          }).join(' ')
          return (
            <polyline key={e.id}
              points={ptsStr}
              stroke={col} strokeWidth={1.5} strokeDasharray="4 3"
              fill="none" data-id={e.id}
            />
          )
        }
        return null
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
      {/* Pulse overlay — when the user clicks a constraint row in the
          sidebar, we briefly outline the affected entities with a pulsing
          colored stroke. CSS-driven so the outline animates smoothly even
          while the canvas is otherwise idle. */}
      {pulseEntityIds.size > 0 && (
        <g className="kerf-sketch-pulse" style={{ pointerEvents: 'none' }}>
          {[...pulseEntityIds].map((eid) => {
            const e = ent.find((x) => x.id === eid)
            if (!e) return null
            if (e.type === 'line') {
              const p1 = pointById.get(e.p1)
              const p2 = pointById.get(e.p2)
              if (!p1 || !p2) return null
              const a = worldToScreen(p1.x, p1.y)
              const b = worldToScreen(p2.x, p2.y)
              return <line key={'pulse-' + eid}
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                stroke="#fbbf24" strokeWidth={4}
                strokeLinecap="round" opacity={0.55} />
            }
            if (e.type === 'point') {
              const s = worldToScreen(e.x, e.y)
              return <circle key={'pulse-' + eid}
                cx={s.x} cy={s.y} r={8}
                fill="none" stroke="#fbbf24" strokeWidth={2.5}
                opacity={0.6} />
            }
            if (e.type === 'circle') {
              const c = pointById.get(e.center)
              if (!c) return null
              const s = worldToScreen(c.x, c.y)
              return <circle key={'pulse-' + eid}
                cx={s.x} cy={s.y} r={(e.radius || 0) * view.scale}
                fill="none" stroke="#fbbf24" strokeWidth={4}
                opacity={0.55} />
            }
            if (e.type === 'arc') {
              const c = pointById.get(e.center)
              const sP = pointById.get(e.start)
              const en = pointById.get(e.end)
              if (!c || !sP || !en) return null
              const r = Math.hypot(sP.x - c.x, sP.y - c.y)
              const a = worldToScreen(sP.x, sP.y)
              const b = worldToScreen(en.x, en.y)
              const sweep = e.sweep_ccw ? 1 : 0
              let dA = Math.atan2(en.y - c.y, en.x - c.x) - Math.atan2(sP.y - c.y, sP.x - c.x)
              if (e.sweep_ccw && dA < 0) dA += Math.PI * 2
              if (!e.sweep_ccw && dA > 0) dA -= Math.PI * 2
              const largeArc = Math.abs(dA) > Math.PI ? 1 : 0
              return <path key={'pulse-' + eid}
                d={`M ${a.x} ${a.y} A ${r * view.scale} ${r * view.scale} 0 ${largeArc} ${sweep === 1 ? 0 : 1} ${b.x} ${b.y}`}
                fill="none" stroke="#fbbf24" strokeWidth={4}
                strokeLinecap="round" opacity={0.55} />
            }
            return null
          })}
        </g>
      )}
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
    // c.value may be a `${param}` placeholder string — coerce safely.
    const nv = Number(c.value)
    label = Number.isFinite(nv) ? `${tag}${nv.toFixed(2)} mm` : `${tag}${String(c.value ?? '')}`
  } else if (c.type === 'radius' || c.type === 'diameter') {
    const circle = (sketch.entities || []).find((x) => x.id === c.circle)
    if (!circle) return null
    const center = (sketch.entities || []).find((x) => x.id === circle.center)
    if (!center) return null
    pos = worldToScreen(center.x + (circle.radius || 0) / 2, center.y)
    const nv = Number(c.value)
    const prefix = c.type === 'radius' ? 'R' : 'D'
    label = Number.isFinite(nv) ? `${prefix} ${nv.toFixed(2)}` : `${prefix} ${String(c.value ?? '')}`
  } else if (c.type === 'angle') {
    // Place at midpoint of the first referenced line.
    const a = (sketch.entities || []).find((x) => x.id === c.a)
    if (!a || a.type !== 'line') return null
    const p1 = (sketch.entities || []).find((x) => x.id === a.p1)
    const p2 = (sketch.entities || []).find((x) => x.id === a.p2)
    if (!p1 || !p2) return null
    pos = worldToScreen((p1.x + p2.x) / 2, (p1.y + p2.y) / 2)
    const nv = Number(c.value)
    label = Number.isFinite(nv) ? `${nv.toFixed(1)}°` : `${String(c.value ?? '')}°`
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

function PendingPreview({ tool, sketch, pendingPoints, hover, worldToScreen, lineDraft }) {
  if (!hover || pendingPoints.length === 0) return null
  if (tool === 'line' && pendingPoints.length === 1) {
    const start = sketch.entities.find((e) => e.id === pendingPoints[0].id)
    if (!start) return null
    // If a length / angle is locked, draw the preview to the projected target
    // (so the user sees exactly where the next click will land).
    const target = projectLineDraft(start, hover, lineDraft || {}) || hover
    const a = worldToScreen(start.x, start.y)
    const b = worldToScreen(target.x, target.y)
    return (
      <g>
        <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#fbbf24" strokeWidth={1} strokeDasharray="3 2" />
        {/* Endpoint marker so the locked target reads cleanly. */}
        <circle cx={b.x} cy={b.y} r={3} fill="none" stroke="#fbbf24" strokeWidth={1} />
      </g>
    )
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

// LineDraftStrip — live "dynamic input" while drawing a line. Floats near
// the cursor between the first and second click. Two fields (Length, Angle).
// Tab cycles focus; Enter commits at the typed values; Esc cancels. Typing
// in either field flips its lock to true automatically — once you've typed a
// value, you've committed to it.
//
// We mirror the AutoCAD / Onshape "dynamic input" pattern, which is much
// friendlier than FreeCAD's "draw the line, then add a constraint" two-step.
// The chosen length / angle ALSO bake themselves into permanent constraints
// when the line is committed (see the `tool === 'line'` block above).
function LineDraftStrip({ startEntity, cursor, worldToScreen, draft, draftRef, onChange, onCommit, onCancel }) {
  const lengthRef = useRef(null)
  const angleRef = useRef(null)
  // Auto-focus the chosen field on mount.
  useEffect(() => {
    if (draftRef.current?.focus === 'angle') angleRef.current?.focus()
    else lengthRef.current?.focus()
    // Mount-only: subsequent focus changes are user-driven via Tab.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (!startEntity) return null

  // Default-display values: when the user hasn't typed anything we echo the
  // live cursor measurement so they see what "no override" would mean.
  const live = describeLineDraft(startEntity, cursor)
  const lengthDisplay = draft.length !== '' ? draft.length : live.length.toFixed(2)
  const angleDisplay = draft.angle !== '' ? draft.angle : ((live.angle + 360) % 360).toFixed(1)

  // Position the strip next to the cursor (with a small offset so it doesn't
  // sit directly under the click point). Convert world → screen so a
  // pan/zoom keeps it anchored to the cursor.
  const screen = worldToScreen(cursor.x, cursor.y)

  function update(field, value) {
    draftRef.current = {
      ...draftRef.current,
      [field]: value,
      // Typing a value implicitly locks that field. Clearing the input
      // releases the lock, since an empty string is unambiguously "use cursor".
      [field === 'length' ? 'lockLength' : 'lockAngle']: value !== '',
    }
    onChange?.()
  }

  function onKey(e, field) {
    if (e.key === 'Enter') {
      e.preventDefault()
      onCommit?.()
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      onCancel?.()
      return
    }
    if (e.key === 'Tab') {
      e.preventDefault()
      const nextField = field === 'length' ? 'angle' : 'length'
      draftRef.current = { ...draftRef.current, focus: nextField }
      ;(nextField === 'length' ? lengthRef : angleRef).current?.focus()
    }
  }

  return (
    <div
      className="absolute z-[6] flex items-center gap-2 px-2 py-1 rounded-md bg-ink-900/95 border border-kerf-300/40 shadow-lg backdrop-blur"
      style={{
        left: Math.max(8, screen.x + 16),
        top: Math.max(8, screen.y + 16),
        // Don't trap pointer events on the canvas around the strip — let
        // mouse-down still register a click outside the inputs.
        pointerEvents: 'auto',
      }}
      // The canvas has mousedown handlers; clicks inside the strip should
      // not trigger them.
      onMouseDown={(e) => e.stopPropagation()}
    >
      <label className="flex items-center gap-1 text-[10px] text-ink-300">
        <span className={draft.lockLength ? 'text-kerf-300' : 'text-ink-400'}>L</span>
        <input
          ref={lengthRef}
          type="text"
          inputMode="decimal"
          value={lengthDisplay}
          onChange={(e) => update('length', e.target.value)}
          onFocus={() => { draftRef.current = { ...draftRef.current, focus: 'length' } }}
          onKeyDown={(e) => onKey(e, 'length')}
          className={`w-20 bg-ink-950 border rounded px-2 py-1 text-xs font-mono outline-none
            ${draft.lockLength ? 'border-kerf-300/60 text-kerf-100' : 'border-ink-800 text-ink-300'}`}
          title="Length in mm — type a number to lock the line's length, then click to commit. Tab → Angle."
        />
        <span className="text-ink-500">mm</span>
      </label>
      <label className="flex items-center gap-1 text-[10px] text-ink-300">
        <span className={draft.lockAngle ? 'text-kerf-300' : 'text-ink-400'}>A</span>
        <input
          ref={angleRef}
          type="text"
          inputMode="decimal"
          value={angleDisplay}
          onChange={(e) => update('angle', e.target.value)}
          onFocus={() => { draftRef.current = { ...draftRef.current, focus: 'angle' } }}
          onKeyDown={(e) => onKey(e, 'angle')}
          className={`w-20 bg-ink-950 border rounded px-2 py-1 text-xs font-mono outline-none
            ${draft.lockAngle ? 'border-kerf-300/60 text-kerf-100' : 'border-ink-800 text-ink-300'}`}
          title="Angle in degrees from +X — type a number to lock direction. Tab → Length. Enter to commit, Esc to cancel."
        />
        <span className="text-ink-500">°</span>
      </label>
      <span className="text-[9px] text-ink-500 ml-1">Tab · Enter · Esc</span>
    </div>
  )
}

// EntityMiniToolbar — inline action bar that floats next to the current
// selection, offering only the constraints that actually apply to the
// selected combination (FreeCAD surfaces every icon all the time, which is
// confusing — we filter ruthlessly).
//
// Layout:
//   - Anchored at the bbox of the selection (top-right of bbox in screen
//     space) so it never covers the geometry but stays close enough to feel
//     attached.
//   - Plain-English tooltips ("Make these equal length", "Lock to horizontal",
//     "Set length to N mm") replace FreeCAD's cryptic constraint names.
function EntityMiniToolbar({ sketch, selection, worldToScreen, onApply, onLockLength, onLockAngle }) {
  // Compute the world-space bbox of the selection.
  const ent = sketch.entities || []
  const byId = new Map(ent.map((e) => [e.id, e]))
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  function expandWith(p) {
    if (!p) return
    minX = Math.min(minX, p.x); minY = Math.min(minY, p.y)
    maxX = Math.max(maxX, p.x); maxY = Math.max(maxY, p.y)
  }
  function expandFromEntity(e) {
    if (!e) return
    if (e.type === 'point') expandWith(e)
    else if (e.type === 'line') { expandWith(byId.get(e.p1)); expandWith(byId.get(e.p2)) }
    else if (e.type === 'circle' || e.type === 'arc') {
      const c = byId.get(e.center)
      const r = e.radius || (e.type === 'arc' ? Math.hypot((byId.get(e.start)?.x ?? 0) - (c?.x ?? 0), (byId.get(e.start)?.y ?? 0) - (c?.y ?? 0)) : 0)
      if (c) {
        expandWith({ x: c.x - r, y: c.y - r })
        expandWith({ x: c.x + r, y: c.y + r })
      }
    } else if (e.type === 'ellipse') {
      const c = byId.get(e.center)
      const m = Math.max(e.rx || 1, e.ry || 1)
      if (c) {
        expandWith({ x: c.x - m, y: c.y - m })
        expandWith({ x: c.x + m, y: c.y + m })
      }
    }
  }
  for (const id of selection) expandFromEntity(byId.get(id))
  if (!Number.isFinite(minX)) return null
  const screenTopRight = worldToScreen(maxX, maxY)

  // Classify selection.
  const types = selection.map((id) => byId.get(id)?.type).filter(Boolean)
  const lines = selection.filter((id) => byId.get(id)?.type === 'line')
  const points = selection.filter((id) => byId.get(id)?.type === 'point')
  const circlesArcs = selection.filter((id) => {
    const t = byId.get(id)?.type; return t === 'circle' || t === 'arc'
  })

  const buttons = []
  // Single line — most common case. Offer length, angle (H/V), construction.
  if (lines.length === 1 && types.length === 1) {
    buttons.push({
      label: 'Set length…', short: '↔ length',
      tooltip: 'Set this line to an exact length in millimetres.',
      onClick: () => onLockLength?.(lines[0]),
    })
    buttons.push({
      label: 'Lock to horizontal', short: 'Horizontal',
      tooltip: 'Snap this line to be horizontal (parallel to +X).',
      onClick: () => onApply('horizontal'),
    })
    buttons.push({
      label: 'Lock to vertical', short: 'Vertical',
      tooltip: 'Snap this line to be vertical (parallel to +Y).',
      onClick: () => onApply('vertical'),
    })
    buttons.push({
      label: 'Auto-lock angle', short: 'Lock angle',
      tooltip: 'Snap to horizontal or vertical if the line is already close to either.',
      onClick: () => onLockAngle?.(lines[0]),
    })
  }
  // Two lines — equality / parallel / perpendicular / angle.
  if (lines.length === 2 && types.length === 2) {
    buttons.push({
      label: 'Make equal length', short: 'Equal',
      tooltip: 'Constrain both lines to the same length.',
      onClick: () => onApply('equal_length'),
    })
    buttons.push({
      label: 'Make parallel', short: 'Parallel',
      tooltip: 'Constrain the two lines to remain parallel.',
      onClick: () => onApply('parallel'),
    })
    buttons.push({
      label: 'Make perpendicular', short: 'Perp',
      tooltip: 'Constrain the two lines to meet at 90°.',
      onClick: () => onApply('perpendicular'),
    })
    buttons.push({
      label: 'Set angle…', short: 'Angle',
      tooltip: 'Set the angle between the two lines in degrees.',
      onClick: () => onApply('distance'),
    })
  }
  // Two points — coincident or distance.
  if (points.length === 2 && types.length === 2) {
    buttons.push({
      label: 'Make coincident', short: 'Snap together',
      tooltip: 'Merge the two points into a single shared point.',
      onClick: () => onApply('coincident'),
    })
    buttons.push({
      label: 'Set distance…', short: 'Distance',
      tooltip: 'Set the distance between the two points in millimetres.',
      onClick: () => onApply('distance'),
    })
  }
  // Single circle / arc — radius.
  if (circlesArcs.length === 1 && types.length === 1) {
    buttons.push({
      label: 'Set radius…', short: 'Radius',
      tooltip: 'Set the radius of this circle/arc in millimetres.',
      onClick: () => onApply('distance'),
    })
  }
  // Two circles — equal radius / tangent.
  if (circlesArcs.length === 2 && types.length === 2) {
    buttons.push({
      label: 'Make equal radius', short: 'Equal r',
      tooltip: 'Force both circles/arcs to share the same radius.',
      onClick: () => onApply('equal_radius'),
    })
    buttons.push({
      label: 'Make tangent', short: 'Tangent',
      tooltip: 'Constrain the two curves to touch at exactly one point.',
      onClick: () => onApply('tangent'),
    })
  }
  // Line + circle/arc — tangent.
  if (lines.length === 1 && circlesArcs.length === 1 && types.length === 2) {
    buttons.push({
      label: 'Make tangent', short: 'Tangent',
      tooltip: 'Make the line tangent to the circle/arc.',
      onClick: () => onApply('tangent'),
    })
  }
  // Point + line — point on line.
  if (points.length === 1 && lines.length === 1 && types.length === 2) {
    buttons.push({
      label: 'Pin point on line', short: 'On line',
      tooltip: 'Constrain the point to lie on the line.',
      onClick: () => onApply('point_on_line'),
    })
  }
  // Point + circle/arc — point on arc.
  if (points.length === 1 && circlesArcs.length === 1 && types.length === 2) {
    buttons.push({
      label: 'Pin point on arc', short: 'On arc',
      tooltip: 'Constrain the point to lie on the circle/arc.',
      onClick: () => onApply('point_on_arc'),
    })
  }

  if (buttons.length === 0) return null

  return (
    <div
      className="absolute z-[4] flex flex-wrap items-center gap-1 px-1.5 py-1 rounded-md bg-ink-900/95 border border-ink-700 shadow-lg backdrop-blur max-w-[420px]"
      style={{
        // Top-right of the bbox, plus a small gutter so it never sits on the
        // entity. Clamp to the canvas rect would be nicer; v1 lets the user's
        // browser handle clipping.
        left: Math.max(8, screenTopRight.x + 12),
        top: Math.max(8, screenTopRight.y - 30),
      }}
      onMouseDown={(e) => e.stopPropagation()}
    >
      {buttons.map((b, i) => (
        <button
          key={i}
          type="button"
          onClick={b.onClick}
          title={b.tooltip}
          className="px-2 py-0.5 rounded text-[10px] font-medium text-ink-200 hover:bg-kerf-300/15 hover:text-kerf-100 border border-transparent hover:border-kerf-300/40"
        >
          {b.short}
        </button>
      ))}
    </div>
  )
}

function DimensionPrompt({ spec, onCommit, onCancel }) {
  const [text, setText] = useState(String(spec.defaultValue || 0))
  return (
    <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-ink-900 border border-kerf-300/40 rounded-md p-3 shadow-2xl flex items-center gap-2">
      <span className="text-[11px] uppercase tracking-wider text-ink-400">
        {spec.kind === 'angle' ? 'Angle (deg)' : spec.kind === 'radius' ? 'Radius (mm)' : spec.kind === 'diameter' ? 'Diameter (mm)' : 'Distance (mm)'}
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
// 2D curve-fitting helpers (used for classifying projected edge chains).

function fitCircle2D(points) {
  if (!points || points.length < 3) return { ok: false }
  const n = points.length
  let sumX = 0, sumY = 0, sumX2 = 0, sumY2 = 0, sumXY = 0, sumX3 = 0, sumY3 = 0, sumX2Y = 0, sumXY2 = 0
  for (const p of points) {
    const x = p.x, y = p.y, x2 = x * x, y2 = y * y, xy = x * y
    sumX += x; sumY += y; sumX2 += x2; sumY2 += y2; sumXY += xy
    sumX3 += x * x2; sumY3 += y * y2; sumX2Y += x2 * y; sumXY2 += x * y2
  }
  const d = n * sumX2 - sumX * sumX
  if (Math.abs(d) < 1e-12) return { ok: false }
  const e = n * sumY2 - sumY * sumY
  if (Math.abs(e) < 1e-12) return { ok: false }
  const f = n * sumXY - sumX * sumY
  if (Math.abs(f) < 1e-12) return { ok: false }
  const g = n * sumX3 + n * sumXY2 - sumX * sumX2 - sumY * sumXY
  const h = n * sumY3 + n * sumX2Y - sumY * sumY2 - sumX * sumXY
  const denom = d * e - f * f
  if (Math.abs(denom) < 1e-12) return { ok: false }
  const D = (g * f - h * d) / denom
  const E = (h * f - g * e) / denom
  const F = -(sumX2 + sumY2 + D * sumX + E * sumY) / n
  const cx = -D / 2, cy = -E / 2
  const radius = Math.sqrt(D * D / 4 + E * E / 4 - F)
  let maxResidual = 0
  for (const p of points) {
    const dx = p.x - cx, dy = p.y - cy
    const residual = Math.abs(Math.sqrt(dx * dx + dy * dy) - radius)
    if (residual > maxResidual) maxResidual = residual
  }
  return { ok: true, center: { x: cx, y: cy }, radius, maxResidual }
}

function chainIsClosed(chain2D, tol = 0.01) {
  if (!chain2D || chain2D.length < 3) return false
  const p0 = chain2D[0], pN = chain2D[chain2D.length - 1]
  const dx = pN.x - p0.x, dy = pN.y - p0.y
  return Math.sqrt(dx * dx + dy * dy) < tol
}

// ---------------------------------------------------------------------------
// 3D backdrop — three.js scene rendered behind the SVG, showing the
// `sketch.visible_3d` parts at semi-transparent reference opacity. The
// camera is locked to the sketch plane (XY for v2). Re-renders on parts /
// view (zoom) changes; pans are applied to the scene's frustum so 3D content
// stays aligned with the SVG world coordinates.
function SketchBackdrop3D({ sketch, view, loadParts, tool, onProjectEdge }) {
  const mountRef = useRef(null)
  const stateRef = useRef(null)
  const visibleIds = useMemo(() => sketch?.visible_3d || [], [sketch?.visible_3d])

  // Compute face frame once when plane changes.
  const faceFrame = useMemo(() => planeFaceFrame(sketch?.plane), [sketch?.plane])

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
    // Orthographic camera. For face-anchored sketches, orient to face frame;
    // otherwise default to XY plane.
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, -10000, 10000)
    const frame = faceFrame
    if (frame) {
      // Position camera along the face normal, offset from origin.
      const [ox, oy, oz] = frame.origin
      const [nx, ny, nz] = frame.normal
      const CAM_DIST = 100
      camera.position.set(ox + nx * CAM_DIST, oy + ny * CAM_DIST, oz + nz * CAM_DIST)
      // Use vDir as up (face UV coordinate system).
      camera.up.set(frame.vDir[0], frame.vDir[1], frame.vDir[2])
      camera.lookAt(ox, oy, oz)
    } else {
      // Default XY plane orientation.
      camera.position.set(0, 0, 100)
      camera.up.set(0, 1, 0)
      camera.lookAt(0, 0, 0)
    }
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
    stateRef.current = { renderer, scene, camera, meshGroup, edgeGroup, ro, dirty: true, frame }
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

  // Update camera orientation when face frame changes (without re-creating the whole scene).
  useEffect(() => {
    const s = stateRef.current
    if (!s || !s.camera) return
    const cam = s.camera
    const fr = faceFrame
    if (fr) {
      const [ox, oy, oz] = fr.origin
      const [nx, ny, nz] = fr.normal
      const CAM_DIST = 100
      cam.position.set(ox + nx * CAM_DIST, oy + ny * CAM_DIST, oz + nz * CAM_DIST)
      cam.up.set(fr.vDir[0], fr.vDir[1], fr.vDir[2])
      cam.lookAt(ox, oy, oz)
      cam.updateProjectionMatrix()
    } else {
      cam.position.set(0, 0, 100)
      cam.up.set(0, 1, 0)
      cam.lookAt(0, 0, 0)
      cam.updateProjectionMatrix()
    }
    s.dirty = true
  }, [faceFrame])

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
            // Build coarse wireframe for display (threshold 25).
            const egCoarse = new THREE.EdgesGeometry(geom, 25)
            const edgeMatCoarse = new THREE.LineBasicMaterial({
              color: 0x8aa9ce, transparent: true, opacity: 0.45, depthWrite: false,
            })
            edgeGroup.add(new THREE.LineSegments(egCoarse, edgeMatCoarse))
            // Build fine wireframe for picking (threshold 1) and chain extraction.
            const egFine = new THREE.EdgesGeometry(geom, 1)
            const posAttr = egFine.attributes.position
            const numSegsFine = posAttr.count / 2
            // Index endpoints by quantized position.
            const quantize = (v) => `${Math.round(v.x * 1000)},${Math.round(v.y * 1000)},${Math.round(v.z * 1000)}`
            const endpointToSegs = new Map()
            for (let i = 0; i < numSegsFine; i++) {
              const iA = i * 2, iB = i * 2 + 1
              const keyA = quantize(new THREE.Vector3(posAttr.getX(iA), posAttr.getY(iA), posAttr.getZ(iA)))
              const keyB = quantize(new THREE.Vector3(posAttr.getX(iB), posAttr.getY(iB), posAttr.getZ(iB)))
              if (!endpointToSegs.has(keyA)) endpointToSegs.set(keyA, [])
              if (!endpointToSegs.has(keyB)) endpointToSegs.set(keyB, [])
              endpointToSegs.get(keyA).push(i)
              endpointToSegs.get(keyB).push(i)
            }
            // Build per-segment tangent vectors.
            const tangents = new Array(numSegsFine)
            for (let i = 0; i < numSegsFine; i++) {
              const iA = i * 2, iB = i * 2 + 1
              const vA = new THREE.Vector3(posAttr.getX(iA), posAttr.getY(iA), posAttr.getZ(iA))
              const vB = new THREE.Vector3(posAttr.getX(iB), posAttr.getY(iB), posAttr.getZ(iB))
              tangents[i] = new THREE.Vector3().subVectors(vB, vA).normalize()
            }
            // Walk chains: greedy walk across endpoints with valence==2 and continuous tangents.
            const visited = new Uint8Array(numSegsFine)
            const chains = []
            const segToChain = new Int32Array(numSegsFine).fill(-1)
            const COS_35 = Math.cos(Math.PI / 180 * 35)
            for (let startSeg = 0; startSeg < numSegsFine; startSeg++) {
              if (visited[startSeg]) continue
              const pts = []
              let forward = true
              let seg = startSeg
              while (seg >= 0 && !visited[seg]) {
                visited[seg] = 1
                segToChain[seg] = chains.length
                const iA = seg * 2, iB = seg * 2 + 1
                const vA = new THREE.Vector3(posAttr.getX(iA), posAttr.getY(iA), posAttr.getZ(iA))
                const vB = new THREE.Vector3(posAttr.getX(iB), posAttr.getY(iB), posAttr.getZ(iB))
                if (forward) {
                  pts.push(vA.clone())
                } else {
                  pts.push(vB.clone())
                }
                // Determine endpoints and extend.
                const endKey = forward
                  ? quantize(new THREE.Vector3(posAttr.getX(iB), posAttr.getY(iB), posAttr.getZ(iB)))
                  : quantize(new THREE.Vector3(posAttr.getX(iA), posAttr.getY(iA), posAttr.getZ(iA)))
                const neighbors = endpointToSegs.get(endKey) || []
                let nextSeg = -1
                for (const nb of neighbors) {
                  if (nb === seg || visited[nb]) continue
                  // Check valence==2 at the far endpoint.
                  const nbIA = nb * 2, nbIB = nb * 2 + 1
                  const nbKeyA = quantize(new THREE.Vector3(posAttr.getX(nbIA), posAttr.getY(nbIA), posAttr.getZ(nbIA)))
                  const nbKeyB = quantize(new THREE.Vector3(posAttr.getX(nbIB), posAttr.getY(nbIB), posAttr.getZ(nbIB)))
                  const nbEndKey = nbKeyA === endKey ? nbKeyB : nbKeyA
                  const nbEndValence = (endpointToSegs.get(nbEndKey) || []).filter(s => !visited[s] || s === nb).length
                  // Check tangent continuity.
                  const dot = tangents[seg].dot(tangents[nb])
                  if (dot > COS_35) {
                    nextSeg = nb
                    forward = (nbKeyA === endKey)
                    break
                  }
                }
                seg = nextSeg
              }
              if (pts.length >= 2) {
                chains.push({ points: pts })
              }
            }
            // Attach chains to fine LineSegments for pick resolution.
            const edgeMatFine = new THREE.LineBasicMaterial({ visible: false })
            const fineSegs = new THREE.LineSegments(egFine, edgeMatFine)
            fineSegs.userData.chains = chains
            fineSegs.userData.segToChain = segToChain
            fineSegs.userData.partMatrixWorld = mesh.matrixWorld
            edgeGroup.add(fineSegs)
          }
        } catch (err) {
          console.warn('SketchBackdrop3D: load failed', fileId, err)
        }
      }
      s.dirty = true
    })()
    return () => { cancelled = true }
  }, [visibleIds, loadParts])

  // Handle click for project_edge tool — raycast against edge LineSegments to pick
  // an edge and project both endpoints onto the sketch 2D plane.
  useEffect(() => {
    const mount = mountRef.current
    if (!mount) return
    function onClick(e) {
      if (tool !== 'project_edge') return
      const s = stateRef.current
      if (!s) return
      const rect = mount.getBoundingClientRect()
      const ndcX = ((e.clientX - rect.left) / rect.width) * 2 - 1
      const ndcY = -((e.clientY - rect.top) / rect.height) * 2 + 1
      const raycaster = new THREE.Raycaster()
      raycaster.params.Line = { threshold: 2 }
      raycaster.setFromCamera({ x: ndcX, y: ndcY }, s.camera)
      const hits = raycaster.intersectObjects(s.edgeGroup.children, true)
      if (hits.length === 0) return
      const hit = hits[0]
      const geom = hit.object.geometry
      const posAttr = geom?.attributes?.position
      if (!posAttr) return
      const segIdx = hit.faceIndex ?? 0

      // Helper: project a world-space THREE.Vector3 onto the sketch 2D plane.
      function project2D(pt) {
        const frame = faceFrame
        if (frame) {
          const [ox, oy, oz] = frame.origin
          const [ux, uy, uz] = frame.uDir
          const [vx, vy, vz] = frame.vDir
          const dx = pt.x - ox, dy = pt.y - oy, dz = pt.z - oz
          return { x: dx * ux + dy * uy + dz * uz, y: dx * vx + dy * vy + dz * vz }
        }
        return { x: pt.x, y: pt.y }
      }

      const chains = hit.object.userData.chains
      const segToChain = hit.object.userData.segToChain
      const partMatrixWorld = hit.object.userData.partMatrixWorld

      if (chains && segToChain && partMatrixWorld) {
        // Chain-based curve classification.
        const chainIdx = segToChain[segIdx]
        if (chainIdx >= 0 && chainIdx < chains.length) {
          const chain = chains[chainIdx]
          // Project all points to 2D.
          const chain2D = chain.points.map((pt) => {
            const wp = pt.clone().applyMatrix4(partMatrixWorld)
            return project2D(wp)
          })
          // Defensive downsampling for large chains.
          const pts2D = chain2D.length > 512
            ? chain2D.filter((_, i) => i % Math.ceil(chain2D.length / 64) === 0)
            : chain2D
          if (pts2D.length < 2) return
          if (pts2D.length === 2) {
            onProjectEdge?.({
              fileId: visibleIds[0] || '',
              edgeId: `edge_${segIdx}_chain${chainIdx}`,
              curveData: { curveType: 'line', p1: pts2D[0], p2: pts2D[1] },
            })
            return
          }
          const fit = fitCircle2D(pts2D)
          const closed = chainIsClosed(pts2D, 0.01)
          const tol = Math.max(0.01, fit.radius * 0.005)
          if (fit.ok && fit.maxResidual <= tol) {
            const { center, radius } = fit
            if (closed) {
              onProjectEdge?.({
                fileId: visibleIds[0] || '',
                edgeId: `edge_${segIdx}_chain${chainIdx}`,
                curveData: { curveType: 'circle', center, radius },
              })
            } else {
              const p0 = pts2D[0], pN = pts2D[pts2D.length - 1]
              let startAngle = Math.atan2(p0.y - center.y, p0.x - center.x)
              let endAngle = Math.atan2(pN.y - center.y, pN.x - center.x)
              // Signed area to determine sweep direction.
              let area = 0
              for (let i = 0; i < pts2D.length - 1; i++) {
                area += pts2D[i].x * pts2D[i + 1].y - pts2D[i + 1].x * pts2D[i].y
              }
              const sweepCCw = area >= 0
              onProjectEdge?.({
                fileId: visibleIds[0] || '',
                edgeId: `edge_${segIdx}_chain${chainIdx}`,
                curveData: { curveType: 'arc', center, radius, startAngle, endAngle, sweepCCw },
              })
            }
          } else {
            onProjectEdge?.({
              fileId: visibleIds[0] || '',
              edgeId: `edge_${segIdx}_chain${chainIdx}`,
              curveData: { curveType: 'polyline', points: pts2D },
            })
          }
          return
        }
      }

      // Fallback: single segment line.
      const iA = segIdx * 2
      const iB = segIdx * 2 + 1
      const vA = new THREE.Vector3(posAttr.getX(iA), posAttr.getY(iA), posAttr.getZ(iA))
      const vB = new THREE.Vector3(posAttr.getX(iB), posAttr.getY(iB), posAttr.getZ(iB))
      vA.applyMatrix4(hit.object.matrixWorld)
      vB.applyMatrix4(hit.object.matrixWorld)
      const p1 = project2D(vA)
      const p2 = project2D(vB)
      onProjectEdge?.({
        fileId: visibleIds[0] || '',
        edgeId: `edge_${segIdx}`,
        curveData: { curveType: 'line', p1, p2 },
      })
    }
    mount.addEventListener('click', onClick)
    return () => mount.removeEventListener('click', onClick)
  }, [tool, faceFrame, onProjectEdge, visibleIds])

  return (
    <div
      ref={mountRef}
      className="absolute inset-0 z-0"
      style={{ opacity: 0.85, pointerEvents: tool === 'project_edge' ? 'auto' : 'none' }}
    />
  )
}

// ---------------------------------------------------------------------------
// Right-rail inspector: selection details + visible-3D picker.

function SketchInspector({ sketch, files, selection, onSelect, onChange, onDelete, onPulse, pulseConstraintId }) {
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
            {cons.map((c) => {
              const pulsing = pulseConstraintId === c.id
              const label = friendlyConstraintLabel(c)
              return (
                <li key={c.id}>
                  <button
                    type="button"
                    title="Click to highlight the affected geometry. Right-click to delete."
                    onClick={() => {
                      onSelect([c.id])
                      onPulse?.(c.id)
                    }}
                    onContextMenu={(e) => {
                      e.preventDefault()
                      onChange(deleteConstraint(sketch, c.id))
                    }}
                    className={`w-full text-left px-2 py-1 rounded text-[11px] flex items-center gap-1.5 transition-colors
                      ${selection.includes(c.id) ? 'bg-kerf-300/15 text-kerf-100' : 'hover:bg-ink-800 text-ink-300'}
                      ${pulsing ? 'ring-1 ring-amber-300/80 bg-amber-300/10' : ''}`}
                  >
                    <span className="text-ink-100">{label}</span>
                    {(c.value != null) && <span className="text-kerf-200 ml-auto font-mono">{formatConstraintValue(c)}</span>}
                  </button>
                </li>
              )
            })}
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
