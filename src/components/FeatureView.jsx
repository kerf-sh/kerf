// FeatureView — editor for `.feature` files (OCCT B-rep timeline + Phase 3
// direct modeling on top).
//
// Layout:
//   * top      — single unified toolbar: Add-feature popover + file name +
//                feature timeline (chips) on the left; pick-mode controls
//                (Faces / Edges / Push-Pull / Sketch-on-face) on the right.
//   * center   — FeatureRenderer (Phase 3): clickable faces + edges, hover
//                highlight, push/pull drag, sketch-on-face, etc.
//   * right    — FeatureInspector for the selected feature. When the
//                inspector has selection-driven fields (Fillet/Chamfer
//                edges, Shell faces, pattern axes, ...) it shows the current
//                viewport selection and a "Pick in viewport" button that
//                arms a one-shot pick.
//   * bottom   — eval status, vertex/body count, viewport selection summary,
//                error banner, re-evaluate.
//
// Selection lifecycle:
//   - Selection is per-file, session-only (lives in the workspace store at
//     `featureSelection`). On file switch we clear it.
//   - Face/edge ids are NOT stable across structural feature edits — adding
//     or removing features re-runs the OCCT evaluator and edge ids shuffle
//     in TopExp explorer order. We display a yellow banner "Selections may
//     reset after structural changes" to set expectations. A future polish
//     would pin selections to (face_centroid, normal) tuples for soft-
//     persistence.
//
// Push/pull UX:
//   - Toolbar button "Push/Pull" toggles a special pick mode. When armed,
//     hovering a face highlights it amber. Mousedown anchors the drag,
//     mouse-move projects screen delta onto the face's normal direction
//     (SketchUp-style). Release commits — append a `push_pull` feature node
//     to the tree (positive distance → fuse outward, negative → cut inward).
//     The face's id is captured at click time; the worker re-evaluates on
//     commit and the topology re-numbers, so the inspector can't "edit" a
//     completed push/pull (it's stored as a generic node and the user has
//     to re-pick the face if they want to change the distance).
//
// Sketch-on-face UX:
//   - Toolbar button "Sketch on face" arms a one-shot face pick. Click a
//     face → modal asks for a sketch name + parent folder → creates a new
//     sketch file with `plane: {type:'face', file_id, feature_node_id,
//     face_id}`. The sketcher reads this and builds a world-space transform
//     from the OCCT face frame.

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Trash2, ChevronUp, ChevronDown, Box, Circle, RotateCcw,
  Disc, Layers, Drill, Sigma, AlertTriangle, Loader2, Play,
  Move, Crosshair, GitBranch, Repeat, FlipHorizontal,
  PencilLine, Pointer, Waves, Layers3, Aperture, Plus,
  X, ChevronRight, LayoutGrid, Combine, Scissors, Grid3x3,
  MoreHorizontal, SlidersHorizontal, Zap, Eye, Shield,
  Wrench, AlignLeft, Activity,
} from 'lucide-react'
import FeatureRenderer from './FeatureRenderer.jsx'
import {
  runFeatures, prewarmOcct, newFeatureId,
  requestFaceOutline,
} from '../lib/occtRunner.js'
import { useWorkspace } from '../store/workspace.js'

// Catalog of feature operations the LLM tools also expose. Each entry
// describes the icon, default param values, and the schema for the right-
// hand parameter inspector.
const FEATURE_KINDS = [
  {
    op: 'pad',
    label: 'Pad',
    icon: Box,
    defaults: { sketch_path: '', height: 10, direction: 'up' },
    fields: [
      { key: 'sketch_path', kind: 'sketch_picker', label: 'Sketch' },
      { key: 'height', kind: 'number', label: 'Height (mm)', min: 0.001 },
      { key: 'direction', kind: 'select', label: 'Direction', options: [
        { value: 'up', label: 'Up (+Z)' },
        { value: 'down', label: 'Down (-Z)' },
        { value: 'symmetric', label: 'Symmetric' },
      ] },
    ],
  },
  {
    op: 'boss_with_draft',
    label: 'Boss + draft',
    icon: Box,
    defaults: {
      sketch_path: '',
      height: 10,
      direction: 'up',
      draft_angle_deg: 3,
      draft_direction: 'outward',
    },
    fields: [
      { key: 'sketch_path', kind: 'sketch_picker', label: 'Sketch' },
      { key: 'height', kind: 'number', label: 'Height (mm)', min: 0.001 },
      { key: 'direction', kind: 'select', label: 'Direction', options: [
        { value: 'up', label: 'Up (+Z)' },
        { value: 'down', label: 'Down (-Z)' },
        { value: 'symmetric', label: 'Symmetric' },
      ] },
      { key: 'draft_angle_deg', kind: 'number', label: 'Draft angle (°)', min: -30, max: 30 },
      { key: 'draft_direction', kind: 'select', label: 'Draft direction', options: [
        { value: 'outward', label: 'Outward (widen away from sketch)' },
        { value: 'inward', label: 'Inward (narrow toward sketch)' },
      ] },
    ],
  },
  {
    op: 'pocket',
    label: 'Pocket',
    icon: Disc,
    defaults: { sketch_path: '', depth: 5, target_id: '' },
    fields: [
      { key: 'sketch_path', kind: 'sketch_picker', label: 'Sketch' },
      { key: 'depth', kind: 'number', label: 'Depth (mm)', min: 0.001 },
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
    ],
  },
  {
    op: 'cut_from_sketch',
    label: 'Cut from sketch',
    icon: Disc,
    defaults: { target_id: '', target_face_id: -1, target_face_name: '', sketch_path: '', depth: 5, reverse: false },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'target_face_id', kind: 'face_picker_single', label: 'Face' },
      { key: 'sketch_path', kind: 'sketch_picker', label: 'Sketch' },
      { key: 'depth', kind: 'number', label: 'Depth (mm)', min: 0.001 },
      { key: 'reverse', kind: 'bool', label: 'Reverse direction' },
    ],
  },
  {
    op: 'revolve',
    label: 'Revolve',
    icon: RotateCcw,
    defaults: { sketch_path: '', axis: 'z', angle_deg: 360 },
    fields: [
      { key: 'sketch_path', kind: 'sketch_picker', label: 'Sketch' },
      { key: 'axis', kind: 'select', label: 'Axis', options: [
        { value: 'x', label: 'X' },
        { value: 'y', label: 'Y' },
        { value: 'z', label: 'Z' },
      ] },
      { key: 'angle_deg', kind: 'number', label: 'Angle (deg)', min: 1, max: 360 },
    ],
  },
  {
    op: 'fillet',
    label: 'Fillet',
    icon: Circle,
    defaults: { target_id: '', edge_filter: 'all', radius: 1, edge_ids: [] },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'edge_filter', kind: 'select', label: 'Edges', options: [
        { value: 'all', label: 'All' },
        { value: 'horizontal', label: 'Horizontal' },
        { value: 'vertical', label: 'Vertical' },
        { value: 'manual', label: 'Manual (pick)' },
      ] },
      { key: 'edge_ids', kind: 'edge_picker', label: 'Picked edges',
        showWhen: (n) => n.edge_filter === 'manual' },
      { key: 'radius', kind: 'number', label: 'Radius (mm)', min: 0.001 },
    ],
  },
  {
    op: 'chamfer',
    label: 'Chamfer',
    icon: Sigma,
    defaults: { target_id: '', edge_filter: 'all', distance: 1, edge_ids: [] },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'edge_filter', kind: 'select', label: 'Edges', options: [
        { value: 'all', label: 'All' },
        { value: 'horizontal', label: 'Horizontal' },
        { value: 'vertical', label: 'Vertical' },
        { value: 'manual', label: 'Manual (pick)' },
      ] },
      { key: 'edge_ids', kind: 'edge_picker', label: 'Picked edges',
        showWhen: (n) => n.edge_filter === 'manual' },
      { key: 'distance', kind: 'number', label: 'Distance (mm)', min: 0.001 },
    ],
  },
  {
    op: 'shell',
    label: 'Shell',
    icon: Layers,
    defaults: { target_id: '', thickness: 1, face_ids: [] },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'face_ids', kind: 'face_picker', label: 'Faces to remove' },
      { key: 'thickness', kind: 'number', label: 'Thickness (mm)', min: 0.001 },
    ],
  },
  {
    op: 'hole',
    label: 'Hole',
    icon: Drill,
    defaults: { sketch_path: '', target_id: '', diameter: 3, depth: 5 },
    fields: [
      { key: 'sketch_path', kind: 'sketch_picker', label: 'Center sketch' },
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'diameter', kind: 'number', label: 'Diameter (mm)', min: 0.001 },
      { key: 'depth', kind: 'number', label: 'Depth (mm)', min: 0.001 },
    ],
  },
  {
    op: 'hole_pattern',
    label: 'Hole pattern',
    icon: LayoutGrid,
    defaults: { target_id: '', sketch_path: '', diameter: 3, depth: 5 },
    fields: [
      { key: 'sketch_path', kind: 'sketch_picker', label: 'Points sketch' },
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'diameter', kind: 'number', label: 'Diameter (mm)', min: 0.001 },
      { key: 'depth', kind: 'number', label: 'Depth (mm)', min: 0.001 },
    ],
  },
  {
    op: 'linear_pattern',
    label: 'Linear pat.',
    icon: Repeat,
    defaults: { direction: 'x', count: 3, spacing: 10 },
    fields: [
      { key: 'direction', kind: 'axis_picker', label: 'Direction (axis or edge)' },
      { key: 'count', kind: 'number', label: 'Count', min: 2, step: 1 },
      { key: 'spacing', kind: 'number', label: 'Spacing (mm)' },
    ],
  },
  {
    op: 'polar_pattern',
    label: 'Polar pat.',
    icon: GitBranch,
    defaults: { axis: 'z', count: 6, total_angle_deg: 360 },
    fields: [
      { key: 'axis', kind: 'axis_picker', label: 'Axis (axis or edge)' },
      { key: 'count', kind: 'number', label: 'Count', min: 2, step: 1 },
      { key: 'total_angle_deg', kind: 'number', label: 'Total angle (deg)', min: 1, max: 360 },
    ],
  },
  {
    op: 'mirror_pattern',
    label: 'Mirror',
    icon: FlipHorizontal,
    // T6: plane_face_name dual-writes the persistent face name alongside the
    // plane field (which can be a numeric face id when picked from the viewport).
    defaults: { plane: 'xy', plane_face_name: '' },
    fields: [
      { key: 'plane', kind: 'plane_picker', label: 'Plane (axis-pair or face)' },
    ],
  },
  {
    op: 'push_pull',
    label: 'Push/Pull',
    icon: Move,
    defaults: { face_id: -1, face_name: '', distance: 0 },
    fields: [
      { key: 'face_id', kind: 'face_picker_single', label: 'Face' },
      { key: 'distance', kind: 'number', label: 'Distance (mm) — negative = into body' },
    ],
  },
  // Phase 4 starter — Rhino-flavored ops. Worker has full implementations;
  // inspector here uses the simplest field kinds. Loft + variable-radius-
  // fillet expose minimal v1 UIs; richer multi-profile reordering and
  // per-vertex-radius editors are follow-up polish.
  {
    op: 'sweep1',
    label: 'Sweep1',
    icon: Waves,
    defaults: { profile_sketch_path: '', path_sketch_path: '', twist_deg: 0, scale_end: 1, mode: 'auto' },
    fields: [
      { key: 'profile_sketch_path', kind: 'sketch_picker', label: 'Profile sketch' },
      { key: 'path_sketch_path', kind: 'sketch_picker', label: 'Path sketch' },
      { key: 'twist_deg', kind: 'number', label: 'Twist (°)', step: 1 },
      { key: 'scale_end', kind: 'number', label: 'End scale', min: 0.001, step: 0.05 },
      { key: 'mode', kind: 'select', label: 'Mode', options: [
        { value: 'auto', label: 'Auto' },
        { value: 'frenet', label: 'Frenet' },
        { value: 'corrected_frenet', label: 'Corrected Frenet' },
      ] },
    ],
  },
  {
    op: 'sweep2',
    label: 'Sweep2',
    icon: Waves,
    defaults: { profile_sketch_path: '', rail1_sketch_path: '', rail2_sketch_path: '', twist_deg: 0, scale_end: 1, mode: 'auto' },
    fields: [
      { key: 'profile_sketch_path', kind: 'sketch_picker', label: 'Profile sketch' },
      { key: 'rail1_sketch_path', kind: 'sketch_picker', label: 'Rail 1 sketch' },
      { key: 'rail2_sketch_path', kind: 'sketch_picker', label: 'Rail 2 sketch' },
      { key: 'twist_deg', kind: 'number', label: 'Twist (°)', step: 1 },
      { key: 'scale_end', kind: 'number', label: 'End scale', min: 0.001, step: 0.05 },
      { key: 'mode', kind: 'select', label: 'Mode', options: [
        { value: 'auto', label: 'Auto' },
        { value: 'frenet', label: 'Frenet' },
      ] },
    ],
  },
  {
    op: 'loft',
    label: 'Loft',
    icon: Layers3,
    defaults: { profile_sketch_paths: [], ruled: false, symmetric: false, closed: false, continuity: 'C0' },
    fields: [
      { key: 'profile_sketch_paths', kind: 'sketch_path_list', label: 'Profile sketches (≥2, ordered)' },
      { key: 'ruled', kind: 'bool', label: 'Ruled (linear blends)' },
      { key: 'symmetric', kind: 'bool', label: 'Symmetric (mid-plane)' },
      { key: 'closed', kind: 'bool', label: 'Closed loop (≥3 profiles)' },
      { key: 'continuity', kind: 'select', label: 'Continuity', options: [
        { value: 'C0', label: 'C0 (position)' },
        { value: 'C1', label: 'C1 (tangent)' },
        { value: 'C2', label: 'C2 (curvature)' },
      ] },
    ],
  },
  {
    op: 'variable_radius_fillet',
    label: 'Var. fillet',
    icon: Aperture,
    defaults: { target_id: '', edges: [] },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'edges', kind: 'edge_radius_list', label: 'Picked edges + radii' },
    ],
  },
  {
    op: 'network_srf',
    label: 'NetworkSrf',
    icon: Layers3,
    defaults: { u_curves: [], v_curves: [], continuity: 'C1' },
    fields: [
      { key: 'u_curves', kind: 'sketch_path_list', label: 'U-direction sketches (≥2)' },
      { key: 'v_curves', kind: 'sketch_path_list', label: 'V-direction sketches (≥2)' },
      { key: 'continuity', kind: 'select', label: 'Continuity', options: [
        { value: 'C0', label: 'C0 (position)' },
        { value: 'C1', label: 'C1 (tangent)' },
        { value: 'C2', label: 'C2 (curvature)' },
      ] },
    ],
  },
  {
    op: 'blend_srf',
    label: 'BlendSrf',
    icon: Waves,
    defaults: { target_id: '', edge1_id: -1, edge2_id: -1, continuity: 'G1' },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Target body' },
      { key: 'edge1_id', kind: 'number', label: 'Edge 1 id', step: 1 },
      { key: 'edge2_id', kind: 'number', label: 'Edge 2 id', step: 1 },
      { key: 'continuity', kind: 'select', label: 'Continuity', options: [
        { value: 'G0', label: 'G0 (position)' },
        { value: 'G1', label: 'G1 (tangent)' },
        { value: 'G2', label: 'G2 (curvature)' },
      ] },
    ],
  },
  // NURBS booleans v1 — T6: to_solid + boolean inspector entries
  {
    op: 'to_solid',
    label: 'To Solid',
    icon: Box,
    defaults: { target_id: '', tolerance: 1e-6 },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Surface body to cap' },
      { key: 'tolerance', kind: 'number', label: 'Sewing tolerance (mm)', min: 1e-9, step: 1e-7 },
    ],
  },
  {
    op: 'boolean',
    label: 'Boolean',
    icon: Combine,
    defaults: { target_a_id: '', target_b_id: '', kind: 'cut' },
    fields: [
      { key: 'target_a_id', kind: 'feature_picker', label: 'A (kept on cut)' },
      { key: 'target_b_id', kind: 'feature_picker', label: 'B (subtracted on cut)' },
      { key: 'kind', kind: 'select', label: 'Operation', options: [
        { value: 'cut',    label: 'Cut (A − B)' },
        { value: 'fuse',   label: 'Fuse (A ∪ B)' },
        { value: 'common', label: 'Common (A ∩ B)' },
      ] },
    ],
  },
  // NURBS Phase 4 C1-T4 — surface_boolean inspector entry.
  //
  // Conceptual sibling to `boolean` (solid CSG) but works directly on
  // Face / Shell / Solid operands — no feature_to_solid pre-step needed.
  // Returns a compound of trimmed face fragments rather than a closed solid.
  // Ideal for jewelry-CAD surface-direct workflows (blend cut by sweep, etc.).
  //
  // Differences vs `boolean`:
  //   - Accepts any topology (Face / Shell / Solid) — no solid enforcement.
  //   - Returns a compound of trimmed fragments, not a closed solid.
  //   - `tolerance` tunes the BOPAlgo intersection tolerance (fuzziness).
  //   - `fuzzy_value` passes directly to BRepAlgoAPI_*::SetFuzzyValue when
  //     the binding exposes it; raise to 1e-3 if tangent-intersection face
  //     fragments go missing.
  //   - If the worker logs a C1-T10 escalation, the current WASM build does
  //     not support non-solid operands — fall back to feature_boolean with a
  //     feature_to_solid pre-pass.
  {
    op: 'surface_boolean',
    label: 'SurfaceBoolean',
    icon: Combine,
    defaults: { target_a_id: '', target_b_id: '', kind: 'cut', tolerance: 1e-3 },
    caption: (
      'Surface-direct boolean — accepts Face/Shell/Solid operands without a ' +
      'feature_to_solid pre-step. Returns trimmed face fragments. ' +
      'Use when operating on raw NURBS surfaces (sweeps, blends, networks). ' +
      'For solid-on-solid CSG use the regular Boolean op instead.'
    ),
    fields: [
      { key: 'target_a_id', kind: 'feature_picker', label: 'A (surface/solid, kept on cut)' },
      { key: 'target_b_id', kind: 'feature_picker', label: 'B (surface/solid, tool on cut)' },
      { key: 'kind', kind: 'select', label: 'Operation', options: [
        { value: 'cut',    label: 'Cut (A − B)' },
        { value: 'fuse',   label: 'Fuse (A ∪ B)' },
        { value: 'common', label: 'Common (A ∩ B)' },
      ] },
      { key: 'tolerance', kind: 'number', label: 'Tolerance (mm)', min: 1e-9, step: 1e-4 },
      { key: 'fuzzy_value', kind: 'number', label: 'Fuzzy value (optional)', min: 0, step: 1e-4 },
    ],
  },
  // NURBS Phase 4 C2-T7/GK-P41 — trim_by_curve inspector entry.
  //
  // Projects a 3D cutter curve onto a NURBS face and splits it, keeping one
  // side. surface-direct trim — no solid round-trip needed.
  // Params: target feature body ref, face name (positional face-N), curve ref
  // (.sketch path or feature id), keep_side (positive/negative), tolerance.
  // WARNING: trim invalidates positional face-N IDs — re-identify faces in the
  // inspector after a trim step.
  {
    op: 'trim_by_curve',
    label: 'TrimByCurve',
    icon: Crosshair,
    caption: (
      'Project a 3D curve onto a NURBS face and split it, keeping one side. ' +
      'WARNING: trim invalidates positional face-N IDs — re-identify faces in ' +
      'the inspector after trimming. Use keep_side to pick the half to retain.'
    ),
    defaults: {
      target_feature_ref: '',
      target_face_name: 'face-1',
      trim_curve_ref: '',
      keep_side: 'positive',
      tolerance: 1e-3,
    },
    fields: [
      { key: 'target_feature_ref', kind: 'feature_picker', label: 'Target body' },
      { key: 'target_face_name',   kind: 'text',           label: 'Face name (e.g. face-1)' },
      { key: 'trim_curve_ref',     kind: 'sketch_picker',  label: 'Trim curve (.sketch or feature id)' },
      { key: 'keep_side', kind: 'select', label: 'Keep side', options: [
        { value: 'positive', label: 'Positive (Left)' },
        { value: 'negative', label: 'Negative (Right)' },
      ] },
      { key: 'tolerance', kind: 'number', label: 'Projection tolerance (mm)', min: 1e-9, step: 1e-4 },
    ],
  },
  // Slicing v0.2 — plane cross-section via BRepAlgoAPI_Section.
  // Returns a compound of intersection edges (1D outline, not a solid).
  // Inspector: target solid picker + plane point/normal xyz inputs.
  // Section-plane gumball is deferred to v0.3 (TODO: add drag-to-reposition
  // gumball in Gumball.jsx that snaps to face plane when armed).
  {
    op: 'section',
    label: 'Section',
    icon: Scissors,
    defaults: {
      target_solid_ref: '',
      plane: { point: [0, 0, 0], normal: [0, 0, 1] },
    },
    fields: [
      { key: 'target_solid_ref', kind: 'feature_picker', label: 'Target solid' },
      { key: 'plane.point[0]',  kind: 'number', label: 'Plane point X (mm)' },
      { key: 'plane.point[1]',  kind: 'number', label: 'Plane point Y (mm)' },
      { key: 'plane.point[2]',  kind: 'number', label: 'Plane point Z (mm)' },
      { key: 'plane.normal[0]', kind: 'number', label: 'Normal X' },
      { key: 'plane.normal[1]', kind: 'number', label: 'Normal Y' },
      { key: 'plane.normal[2]', kind: 'number', label: 'Normal Z' },
    ],
  },
  // Quad remesh v1 — Instant Meshes subprocess (MIT).
  // Remeshes a triangle mesh into a quad-dominant topology.
  // Requires the `instant-meshes` binary on PATH; degrades gracefully when absent.
  {
    op: 'quad_remesh',
    label: 'Quad Remesh',
    icon: Grid3x3,
    defaults: {
      target_feature_ref:  '',
      target_vertex_count: 5000,
      crease_angle_deg:    20,
      align_to_boundary:   true,
      smoothness_iters:    2,
    },
    fields: [
      { key: 'target_feature_ref',  kind: 'feature_picker', label: 'Source mesh / solid' },
      { key: 'target_vertex_count', kind: 'number', label: 'Target vertex count',   min: 1, step: 500 },
      { key: 'crease_angle_deg',    kind: 'number', label: 'Crease angle (°)',       min: 0, max: 180, step: 1 },
      { key: 'smoothness_iters',    kind: 'number', label: 'Smoothing iterations',  min: 0, max: 6, step: 1 },
      { key: 'align_to_boundary',   kind: 'boolean', label: 'Align to boundary' },
    ],
  },
  // Jewelry settings — prong head, bezel, channel, pavé.
  // Stone setting generators for production jewelry CAD workflows.
  {
    op: 'jewelry_prong_head',
    label: 'Prong Head',
    icon: Circle,
    defaults: {
      stone_diameter: 6.5,
      prong_count: 6,
      prong_wire_diameter: 1.0,
      prong_height: 2.0,
      head_style: 'standard',
      basket_rail_count: 1,
      seat_angle_deg: 15,
    },
    fields: [
      { key: 'stone_diameter',      kind: 'number', label: 'Stone diameter (mm)',      min: 0.1, step: 0.1 },
      { key: 'prong_count',         kind: 'select', label: 'Prong count', options: [
        { value: 4, label: '4-prong' },
        { value: 6, label: '6-prong' },
      ] },
      { key: 'prong_wire_diameter', kind: 'number', label: 'Prong wire dia. (mm)',     min: 0.1, step: 0.05 },
      { key: 'prong_height',        kind: 'number', label: 'Prong height (mm)',        min: 0.1, step: 0.1 },
      { key: 'head_style',          kind: 'select', label: 'Head style', options: [
        { value: 'standard',  label: 'Standard' },
        { value: 'basket',    label: 'Basket' },
        { value: 'trellis',   label: 'Trellis' },
        { value: 'cathedral', label: 'Cathedral' },
      ] },
      { key: 'basket_rail_count', kind: 'number', label: 'Basket rail count', min: 0, step: 1 },
      { key: 'seat_angle_deg',    kind: 'number', label: 'Seat angle (°)',    min: 1, max: 45, step: 1 },
    ],
  },
  {
    op: 'jewelry_bezel',
    label: 'Bezel',
    icon: Circle,
    defaults: {
      stone_diameter: 6.5,
      wall_thickness: 0.5,
      bezel_height: 3.0,
      bearing_ledge_height: 1.2,
      bezel_style: 'full',
      partial_opening_deg: 60,
      taper_angle_deg: 0,
    },
    fields: [
      { key: 'stone_diameter',       kind: 'number', label: 'Stone diameter (mm)',    min: 0.1, step: 0.1 },
      { key: 'wall_thickness',       kind: 'number', label: 'Wall thickness (mm)',    min: 0.1, step: 0.05 },
      { key: 'bezel_height',         kind: 'number', label: 'Bezel height (mm)',      min: 0.1, step: 0.1 },
      { key: 'bearing_ledge_height', kind: 'number', label: 'Bearing ledge ht. (mm)', min: 0.05, step: 0.05 },
      { key: 'bezel_style',          kind: 'select', label: 'Style', options: [
        { value: 'full',    label: 'Full' },
        { value: 'partial', label: 'Partial' },
        { value: 'collet',  label: 'Collet' },
        { value: 'tapered', label: 'Tapered' },
      ] },
      { key: 'partial_opening_deg', kind: 'number', label: 'Opening angle (°)', min: 1, max: 359, step: 5,
        showWhen: (n) => n.bezel_style === 'partial' },
      { key: 'taper_angle_deg', kind: 'number', label: 'Taper angle (°)', min: 0, max: 30, step: 1,
        showWhen: (n) => n.bezel_style === 'tapered' || n.bezel_style === 'collet' },
    ],
  },
  {
    op: 'jewelry_channel',
    label: 'Channel',
    icon: Layers,
    defaults: {
      stone_diameter: 2.5,
      stone_count: 7,
      stone_spacing: 2.8,
      rail_height: 1.5,
      rail_thickness: 0.5,
      floor_thickness: 0.4,
    },
    fields: [
      { key: 'stone_diameter',  kind: 'number', label: 'Stone diameter (mm)', min: 0.1, step: 0.1 },
      { key: 'stone_count',     kind: 'number', label: 'Stone count',         min: 1, step: 1 },
      { key: 'stone_spacing',   kind: 'number', label: 'C-to-C spacing (mm)', min: 0.1, step: 0.05 },
      { key: 'rail_height',     kind: 'number', label: 'Rail height (mm)',    min: 0.1, step: 0.1 },
      { key: 'rail_thickness',  kind: 'number', label: 'Rail thickness (mm)', min: 0.1, step: 0.05 },
      { key: 'floor_thickness', kind: 'number', label: 'Floor thickness (mm)', min: 0.1, step: 0.05 },
    ],
  },
  {
    op: 'jewelry_pave',
    label: 'Pavé Array',
    icon: LayoutGrid,
    defaults: {
      region_width: 10.0,
      region_height: 10.0,
      stone_diameter: 1.5,
      stone_spacing: 0.2,
      edge_margin: 0.5,
      surface_normal: [0, 0, 1],
      surface_origin: [0, 0, 0],
    },
    fields: [
      { key: 'region_width',   kind: 'number', label: 'Region width (mm)',   min: 0.1, step: 0.5 },
      { key: 'region_height',  kind: 'number', label: 'Region height (mm)',  min: 0.1, step: 0.5 },
      { key: 'stone_diameter', kind: 'number', label: 'Stone diameter (mm)', min: 0.1, step: 0.05 },
      { key: 'stone_spacing',  kind: 'number', label: 'Stone spacing (mm)',  min: 0, step: 0.05 },
      { key: 'edge_margin',    kind: 'number', label: 'Edge margin (mm)',    min: 0, step: 0.1 },
    ],
  },
  // NURBS Phase 4 C4 — curvature comb overlay (visualisation-only).
  // GeomAbs_G3 doesn't exist in stock OCCT — overlay lets users EYEBALL
  // G3 continuity at face junctions instead of enforcing it algorithmically.
  {
    op: 'surface_curvature_combs',
    label: 'CurvatureCombs',
    icon: Waves,
    defaults: {
      target_feature_ref: '',
      target_face_name: '',
      uv_density: 0.1,
      scale_factor: 10,
      show_combs: true,
    },
    caption: (
      'Curvature-comb overlay — renders principal-curvature combs on NURBS faces ' +
      '(blue=concave, red=convex, white=flat). ' +
      'Use to eyeball G2/G3 continuity at face junctions. ' +
      'Viz-only: stock OCCT has no GeomAbs_G3.'
    ),
    fields: [
      { key: 'target_feature_ref', kind: 'feature_picker', label: 'Target surface/solid' },
      { key: 'target_face_name',   kind: 'text',    label: 'Face name (blank = all faces)' },
      { key: 'uv_density',         kind: 'number',  label: 'UV density', min: 0.01, max: 0.5, step: 0.01 },
      { key: 'scale_factor',       kind: 'number',  label: 'Scale factor', min: 0.1, step: 1 },
      { key: 'show_combs',         kind: 'boolean', label: 'Show combs' },
    ],
  },
  // ── Jewelry ──────────────────────────────────────────────────────────────
  {
    op: 'gemstone',
    label: 'Gemstone',
    icon: Disc,
    defaults: {
      cut: 'round_brilliant',
      diameter_mm: 6.5,
      material: 'diamond',
    },
    fields: [
      { key: 'cut', kind: 'select', label: 'Cut', options: [
        { value: 'round_brilliant',  label: 'Round brilliant' },
        { value: 'princess',         label: 'Princess' },
        { value: 'oval',             label: 'Oval' },
        { value: 'emerald',          label: 'Emerald' },
        { value: 'marquise',         label: 'Marquise' },
        { value: 'pear',             label: 'Pear' },
        { value: 'cushion',          label: 'Cushion' },
        { value: 'radiant',          label: 'Radiant' },
        { value: 'asscher',          label: 'Asscher' },
        { value: 'trillion',         label: 'Trillion' },
        { value: 'heart',            label: 'Heart' },
        { value: 'baguette',         label: 'Baguette' },
        { value: 'briolette',        label: 'Briolette' },
        { value: 'old_european',     label: 'Old European' },
        { value: 'old_mine',         label: 'Old Mine' },
        { value: 'rose_cut',         label: 'Rose cut' },
        { value: 'single_cut',       label: 'Single cut' },
        { value: 'french_cut',       label: 'French cut' },
        { value: 'half_moon',        label: 'Half moon' },
        { value: 'trapezoid',        label: 'Trapezoid' },
        { value: 'kite',             label: 'Kite' },
        { value: 'bullet',           label: 'Bullet' },
        { value: 'tapered_baguette', label: 'Tapered baguette' },
        { value: 'lozenge',          label: 'Lozenge' },
        { value: 'shield',           label: 'Shield' },
        { value: 'calf_head',        label: 'Calf head' },
        { value: 'portuguese',       label: 'Portuguese' },
        { value: 'ceylon',           label: 'Ceylon' },
        { value: 'flanders',         label: 'Flanders' },
        { value: 'square_emerald',   label: 'Square emerald' },
      ] },
      { key: 'diameter_mm',         kind: 'number',  label: 'Diameter / long-axis (mm)', min: 0.5 },
      { key: 'material',            kind: 'text',    label: 'Material' },
      { key: 'table_pct',           kind: 'number',  label: 'Table %',        min: 30, max: 90 },
      { key: 'crown_angle_deg',     kind: 'number',  label: 'Crown angle (°)', min: 10, max: 50 },
      { key: 'pavilion_angle_deg',  kind: 'number',  label: 'Pavilion angle (°)', min: 30, max: 55 },
      { key: 'girdle_pct',          kind: 'number',  label: 'Girdle %',        min: 0.5, max: 10 },
    ],
  },
  {
    op: 'gem_seat',
    label: 'Gem seat',
    icon: Disc,
    defaults: {
      cut: 'round_brilliant',
      diameter_mm: 6.5,
      girdle_clearance_mm: 0.05,
      through_hole: false,
    },
    caption: (
      'Gem-seat cutter solid: bearing cone + girdle ledge + crown relief. ' +
      'Subtract from host solid with a boolean cut to set the stone.'
    ),
    fields: [
      { key: 'cut', kind: 'select', label: 'Cut', options: [
        { value: 'round_brilliant',  label: 'Round brilliant' },
        { value: 'princess',         label: 'Princess' },
        { value: 'oval',             label: 'Oval' },
        { value: 'emerald',          label: 'Emerald' },
        { value: 'marquise',         label: 'Marquise' },
        { value: 'pear',             label: 'Pear' },
        { value: 'cushion',          label: 'Cushion' },
        { value: 'radiant',          label: 'Radiant' },
        { value: 'asscher',          label: 'Asscher' },
        { value: 'trillion',         label: 'Trillion' },
        { value: 'heart',            label: 'Heart' },
        { value: 'baguette',         label: 'Baguette' },
        { value: 'briolette',        label: 'Briolette' },
        { value: 'old_european',     label: 'Old European' },
        { value: 'old_mine',         label: 'Old Mine' },
        { value: 'rose_cut',         label: 'Rose cut' },
        { value: 'single_cut',       label: 'Single cut' },
        { value: 'french_cut',       label: 'French cut' },
        { value: 'half_moon',        label: 'Half moon' },
        { value: 'trapezoid',        label: 'Trapezoid' },
        { value: 'kite',             label: 'Kite' },
        { value: 'bullet',           label: 'Bullet' },
        { value: 'tapered_baguette', label: 'Tapered baguette' },
        { value: 'lozenge',          label: 'Lozenge' },
        { value: 'shield',           label: 'Shield' },
        { value: 'calf_head',        label: 'Calf head' },
        { value: 'portuguese',       label: 'Portuguese' },
        { value: 'ceylon',           label: 'Ceylon' },
        { value: 'flanders',         label: 'Flanders' },
        { value: 'square_emerald',   label: 'Square emerald' },
      ] },
      { key: 'diameter_mm',          kind: 'number',  label: 'Diameter / long-axis (mm)', min: 0.5 },
      { key: 'girdle_clearance_mm',  kind: 'number',  label: 'Girdle clearance (mm)', min: 0, step: 0.01 },
      { key: 'culet_clearance_mm',   kind: 'number',  label: 'Culet clearance (mm)',  min: 0, step: 0.01 },
      { key: 'crown_relief_mm',      kind: 'number',  label: 'Crown relief (mm)',     min: 0, step: 0.05 },
      { key: 'through_hole',         kind: 'boolean', label: 'Through-hole for light' },
    ],
  },
  // Ring shank builder: swept band along the finger circle.
  // Size is auto-converted to inner diameter; profile/shoulder control
  // the cross-section shape and how the band meets the setting.
  {
    op: 'ring_shank',
    label: 'Ring Shank',
    icon: Circle,
    defaults: {
      ring_size: 7,
      system: 'us',
      band_width: 4.0,
      thickness: 1.8,
      profile: 'comfort_fit',
      taper_ratio: 1.0,
      shoulder_style: 'plain',
    },
    caption: (
      'Parametric ring band swept along the finger circle. ' +
      'Profile controls the cross-section shape; shoulder_style controls ' +
      'how the band meets a head/setting (plain, cathedral, split_shank, bypass). ' +
      'All dimensions in mm; ring_size auto-converts to inner diameter.'
    ),
    fields: [
      { key: 'ring_size', kind: 'number', label: 'Ring size', min: 0 },
      { key: 'system', kind: 'select', label: 'Size system', options: [
        { value: 'us',  label: 'US (0–16)' },
        { value: 'uk',  label: 'UK / AU (A–Z+)' },
        { value: 'eu',  label: 'EU (circumference mm)' },
        { value: 'jp',  label: 'JP (1–30)' },
      ] },
      { key: 'band_width', kind: 'number', label: 'Band width (mm)', min: 0.1, step: 0.5 },
      { key: 'thickness',  kind: 'number', label: 'Wall thickness (mm)', min: 0.1, step: 0.1 },
      { key: 'profile', kind: 'select', label: 'Profile', options: [
        { value: 'comfort_fit', label: 'Comfort fit (rounded inside)' },
        { value: 'd_shape',     label: 'D-shape (flat outside)' },
        { value: 'flat',        label: 'Flat' },
        { value: 'half_round',  label: 'Half round' },
        { value: 'knife_edge',  label: 'Knife edge' },
        { value: 'euro',        label: 'Euro (square-ish)' },
        { value: 'tapered',     label: 'Tapered' },
      ] },
      { key: 'taper_ratio', kind: 'number', label: 'Taper ratio (1=uniform)', min: 0.1, max: 1.0, step: 0.05 },
      { key: 'shoulder_style', kind: 'select', label: 'Shoulder style', options: [
        { value: 'plain',       label: 'Plain' },
        { value: 'cathedral',   label: 'Cathedral' },
        { value: 'split_shank', label: 'Split shank' },
        { value: 'bypass',      label: 'Bypass' },
      ] },
    ],
  },
  // ── Jewelry settings v1–v2 (tension, flush, halo, three-stone, cluster, bar, bead, gypsy, illusion, invisible) ──

  {
    op: 'jewelry_tension',
    label: 'Tension Setting',
    icon: Circle,
    defaults: { stone_diameter: 6.5, band_thickness: 3.0, gap: 5.5, rail_width: 0.5, rail_depth: 0.3 },
    fields: [
      { key: 'stone_diameter', kind: 'number', label: 'Stone diameter (mm)', min: 0.1, step: 0.1 },
      { key: 'band_thickness', kind: 'number', label: 'Band thickness (mm)',  min: 0.1, step: 0.1 },
      { key: 'gap',            kind: 'number', label: 'Gap between ends (mm)', min: 0.1, step: 0.1 },
      { key: 'rail_width',     kind: 'number', label: 'Rail width (mm)',       min: 0.1, step: 0.05 },
      { key: 'rail_depth',     kind: 'number', label: 'Rail depth (mm)',       min: 0.1, step: 0.05 },
    ],
  },
  {
    op: 'jewelry_flush',
    label: 'Flush / Gypsy',
    icon: Disc,
    defaults: { stone_diameter: 4.0, seat_depth: 2.0, bevel_width: 0.2, bevel_angle_deg: 45 },
    caption: 'Flush (gypsy) setting — drilled seat + chamfered opening. Subtract from host solid with a boolean cut.',
    fields: [
      { key: 'stone_diameter',  kind: 'number', label: 'Stone diameter (mm)', min: 0.1, step: 0.1 },
      { key: 'seat_depth',      kind: 'number', label: 'Seat depth (mm)',      min: 0.1, step: 0.1 },
      { key: 'bevel_width',     kind: 'number', label: 'Bevel width (mm)',     min: 0.05, step: 0.05 },
      { key: 'bevel_angle_deg', kind: 'number', label: 'Bevel angle (°)',      min: 1, max: 89, step: 1 },
    ],
  },
  {
    op: 'jewelry_halo',
    label: 'Halo Setting',
    icon: Disc,
    defaults: { center_diameter: 6.5, halo_stone_size: 1.3, halo_stone_count: 18, halo_gap: 0.2, halo_metal_width: 0.4 },
    caption: 'Halo — ring of accent stones around a center seat. Add a prong head or bezel for the center stone separately.',
    fields: [
      { key: 'center_diameter',    kind: 'number', label: 'Center stone dia. (mm)', min: 0.5, step: 0.1 },
      { key: 'halo_stone_size',    kind: 'number', label: 'Accent stone dia. (mm)', min: 0.1, step: 0.1 },
      { key: 'halo_stone_count',   kind: 'number', label: 'Accent stone count',     min: 3, step: 1 },
      { key: 'halo_gap',           kind: 'number', label: 'Gap center→halo (mm)',   min: 0, step: 0.05 },
      { key: 'halo_metal_width',   kind: 'number', label: 'Halo frame width (mm)',  min: 0.1, step: 0.05 },
    ],
  },
  {
    op: 'jewelry_three_stone',
    label: 'Three Stone',
    icon: Layers,
    defaults: { center_diameter: 6.5, side_diameter: 4.0, stone_spacing: 0.2, base_height: 3.0 },
    fields: [
      { key: 'center_diameter', kind: 'number', label: 'Center stone dia. (mm)', min: 0.5, step: 0.1 },
      { key: 'side_diameter',   kind: 'number', label: 'Side stone dia. (mm)',   min: 0.5, step: 0.1 },
      { key: 'stone_spacing',   kind: 'number', label: 'Stone gap (mm)',          min: 0, step: 0.05 },
      { key: 'base_height',     kind: 'number', label: 'Gallery base height (mm)', min: 0.1, step: 0.1 },
    ],
  },
  {
    op: 'jewelry_cluster',
    label: 'Cluster',
    icon: LayoutGrid,
    defaults: { cluster_diameter: 10.0, stone_size: 1.5, stone_count: 7, dome_height: 1.0 },
    fields: [
      { key: 'cluster_diameter', kind: 'number', label: 'Cluster diameter (mm)', min: 0.1, step: 0.5 },
      { key: 'stone_size',       kind: 'number', label: 'Stone size (mm)',        min: 0.1, step: 0.1 },
      { key: 'stone_count',      kind: 'number', label: 'Stone count',            min: 1, step: 1 },
      { key: 'dome_height',      kind: 'number', label: 'Dome height (mm)',       min: 0, step: 0.1 },
    ],
  },
  {
    op: 'jewelry_bar',
    label: 'Bar Setting',
    icon: Layers,
    defaults: { stone_diameter: 2.5, bar_width: 0.6, bar_height: 0.8, stone_count: 5, pitch: 3.0 },
    fields: [
      { key: 'stone_diameter', kind: 'number', label: 'Stone dia. (mm)',       min: 0.1, step: 0.1 },
      { key: 'bar_width',      kind: 'number', label: 'Bar width (mm)',        min: 0.1, step: 0.05 },
      { key: 'bar_height',     kind: 'number', label: 'Bar height (mm)',       min: 0.1, step: 0.1 },
      { key: 'stone_count',    kind: 'number', label: 'Stone count',           min: 1, step: 1 },
      { key: 'pitch',          kind: 'number', label: 'C-to-C pitch (mm)',     min: 0.1, step: 0.1 },
    ],
  },
  {
    op: 'jewelry_bead_grain',
    label: 'Bead / Grain',
    icon: LayoutGrid,
    defaults: { stone_diameter: 2.0, bead_count_per_stone: 4, bead_diameter: 0.5, field_layout: 'line' },
    fields: [
      { key: 'stone_diameter',       kind: 'number', label: 'Stone dia. (mm)',          min: 0.1, step: 0.1 },
      { key: 'bead_count_per_stone', kind: 'number', label: 'Beads per stone',          min: 2, step: 1 },
      { key: 'bead_diameter',        kind: 'number', label: 'Bead dia. (mm)',           min: 0.1, step: 0.05 },
      { key: 'field_layout', kind: 'select', label: 'Layout', options: [
        { value: 'line', label: 'Line (single row)' },
        { value: 'grid', label: 'Grid (rectangular)' },
      ] },
    ],
  },
  {
    op: 'jewelry_gypsy_pave',
    label: 'Gypsy Pavé',
    icon: Disc,
    defaults: { stone_diameter: 3.0, seat_depth: 1.5, star_ray_count: 8 },
    caption: 'Gypsy-pavé (star setting) — flush seat + V-cut star rays. Minimum 4 rays.',
    fields: [
      { key: 'stone_diameter',  kind: 'number', label: 'Stone dia. (mm)',  min: 0.1, step: 0.1 },
      { key: 'seat_depth',      kind: 'number', label: 'Seat depth (mm)',  min: 0.1, step: 0.1 },
      { key: 'star_ray_count',  kind: 'number', label: 'Star ray count',   min: 4, step: 1 },
    ],
  },
  {
    op: 'jewelry_illusion',
    label: 'Illusion',
    icon: Disc,
    defaults: { stone_diameter: 3.0, plate_diameter: 8.0, facet_count: 12 },
    caption: 'Illusion (miracle-plate) setting — faceted metal plate makes a small stone appear larger.',
    fields: [
      { key: 'stone_diameter',  kind: 'number', label: 'Stone dia. (mm)',    min: 0.1, step: 0.1 },
      { key: 'plate_diameter',  kind: 'number', label: 'Plate dia. (mm)',    min: 0.2, step: 0.1 },
      { key: 'facet_count',     kind: 'number', label: 'Plate facet count',  min: 4, step: 1 },
    ],
  },
  {
    op: 'jewelry_invisible',
    label: 'Invisible Setting',
    icon: LayoutGrid,
    defaults: { stone_size: 3.0, rail_width: 0.3, rail_height: 1.0, grid_rows: 2, grid_cols: 3 },
    caption: 'Invisible setting — princess stones on concealed rails; no visible metal between stones.',
    fields: [
      { key: 'stone_size',   kind: 'number', label: 'Stone side (mm)',   min: 0.1, step: 0.1 },
      { key: 'rail_width',   kind: 'number', label: 'Rail width (mm)',   min: 0.1, step: 0.05 },
      { key: 'rail_height',  kind: 'number', label: 'Rail height (mm)',  min: 0.1, step: 0.1 },
      { key: 'grid_rows',    kind: 'number', label: 'Grid rows',         min: 1, step: 1 },
      { key: 'grid_cols',    kind: 'number', label: 'Grid columns',      min: 1, step: 1 },
    ],
  },

  // ── Jewelry settings v3–v4 ──────────────────────────────────────────────

  {
    op: 'jewelry_prong_variant',
    label: 'Prong Variant',
    icon: Circle,
    defaults: { variant: 'double_prong', stone_diameter: 6.5, prong_count: 6, wire_gauge: 1.0, prong_height: 2.0, variant_param: 0.0, variant_profile: 'round' },
    fields: [
      { key: 'variant', kind: 'select', label: 'Variant', options: [
        { value: 'double_prong',    label: 'Double prong' },
        { value: 'claw_prong',      label: 'Claw prong' },
        { value: 'v_prong',         label: 'V prong (pointed stones)' },
        { value: 'fishtail_prong',  label: 'Fishtail prong' },
        { value: 'split_prong',     label: 'Split prong' },
        { value: 'decorative_prong',label: 'Decorative prong' },
      ] },
      { key: 'stone_diameter', kind: 'number', label: 'Stone dia. (mm)',    min: 0.1, step: 0.1 },
      { key: 'prong_count',    kind: 'number', label: 'Prong count',        min: 2, step: 1 },
      { key: 'wire_gauge',     kind: 'number', label: 'Wire gauge (mm)',     min: 0.1, step: 0.05 },
      { key: 'prong_height',   kind: 'number', label: 'Prong height (mm)',   min: 0.1, step: 0.1 },
      { key: 'variant_param',  kind: 'number', label: 'Variant param',       min: 0, step: 0.05 },
      { key: 'variant_profile', kind: 'select', label: 'Decorative profile',
        showWhen: (n) => n.variant === 'decorative_prong',
        options: [
          { value: 'round',    label: 'Round' },
          { value: 'tapered',  label: 'Tapered' },
          { value: 'filigree', label: 'Filigree' },
          { value: 'star',     label: 'Star' },
          { value: 'leaf',     label: 'Leaf' },
        ],
      },
    ],
  },
  {
    op: 'jewelry_head_gallery',
    label: 'Head + Gallery',
    icon: Circle,
    defaults: { head_diameter: 8.0, head_height: 3.0, gallery_height: 1.5, gallery_style: 'plain', motif_pitch: 0 },
    fields: [
      { key: 'head_diameter',   kind: 'number', label: 'Head diameter (mm)',  min: 0.1, step: 0.1 },
      { key: 'head_height',     kind: 'number', label: 'Head height (mm)',    min: 0.1, step: 0.1 },
      { key: 'gallery_height',  kind: 'number', label: 'Gallery height (mm)', min: 0.1, step: 0.1 },
      { key: 'gallery_style', kind: 'select', label: 'Gallery style', options: [
        { value: 'plain',        label: 'Plain' },
        { value: 'scalloped',    label: 'Scalloped' },
        { value: 'milgrain_edge',label: 'Milgrain edge' },
        { value: 'pierced',      label: 'Pierced' },
        { value: 'filigree',     label: 'Filigree' },
      ] },
      { key: 'motif_pitch', kind: 'number', label: 'Motif pitch (mm)', min: 0, step: 0.1,
        showWhen: (n) => n.gallery_style !== 'plain' },
    ],
  },
  {
    op: 'jewelry_under_bezel',
    label: 'Under-Bezel',
    icon: Circle,
    defaults: { stone_diameter: 6.5, wall_thickness: 0.5, collet_height: 2.0, base_diameter: 9.0, base_thickness: 0.5 },
    caption: 'Sub-collet: raises the stone above the shank. Use as a secondary support under bezels or halos.',
    fields: [
      { key: 'stone_diameter',  kind: 'number', label: 'Stone dia. (mm)',    min: 0.1, step: 0.1 },
      { key: 'wall_thickness',  kind: 'number', label: 'Wall thickness (mm)', min: 0.1, step: 0.05 },
      { key: 'collet_height',   kind: 'number', label: 'Collet height (mm)', min: 0.1, step: 0.1 },
      { key: 'base_diameter',   kind: 'number', label: 'Base dia. (mm)',     min: 0.1, step: 0.1 },
      { key: 'base_thickness',  kind: 'number', label: 'Base thickness (mm)', min: 0.1, step: 0.05 },
    ],
  },
  {
    op: 'jewelry_peg_setting',
    label: 'Peg Setting',
    icon: Circle,
    defaults: { stone_diameter: 5.0, peg_diameter: 1.0, peg_length: 10.0, base_diameter: 3.0, base_thickness: 0.5 },
    caption: 'Peg (post) setting for earrings and pendants — cylindrical post with stone cup at top.',
    fields: [
      { key: 'stone_diameter', kind: 'number', label: 'Stone dia. (mm)',  min: 0.1, step: 0.1 },
      { key: 'peg_diameter',   kind: 'number', label: 'Peg dia. (mm)',    min: 0.1, step: 0.05 },
      { key: 'peg_length',     kind: 'number', label: 'Peg length (mm)',  min: 0.1, step: 0.5 },
      { key: 'base_diameter',  kind: 'number', label: 'Base dia. (mm)',   min: 0.1, step: 0.1 },
      { key: 'base_thickness', kind: 'number', label: 'Base thick. (mm)', min: 0.1, step: 0.05 },
    ],
  },
  {
    op: 'jewelry_coronet',
    label: 'Coronet',
    icon: Circle,
    defaults: { stone_diameter: 6.5, prong_count: 8, crown_height: 3.0, taper: 0.3, wire_gauge: 1.0 },
    caption: 'Crown (coronet) setting — tapered prong wires lean inward for a regal Victorian silhouette.',
    fields: [
      { key: 'stone_diameter', kind: 'number', label: 'Stone dia. (mm)',   min: 0.1, step: 0.1 },
      { key: 'prong_count',    kind: 'number', label: 'Prong count',       min: 3, step: 1 },
      { key: 'crown_height',   kind: 'number', label: 'Crown height (mm)', min: 0.1, step: 0.1 },
      { key: 'taper',          kind: 'number', label: 'Inward taper (mm)', min: 0, step: 0.05 },
      { key: 'wire_gauge',     kind: 'number', label: 'Wire gauge (mm)',   min: 0.1, step: 0.05 },
    ],
  },
  {
    op: 'jewelry_suspension_mount',
    label: 'Suspension Mount',
    icon: Circle,
    defaults: { stone_diameter: 5.0, seat_style: 'bezel_cup', seat_depth: 2.0, ring_wire_diameter: 1.0, ring_inner_diameter: 3.0, bail_height: 2.0 },
    caption: 'Articulated dangle mount for drop earrings and pendants — seat + pivot jump-ring.',
    fields: [
      { key: 'stone_diameter',     kind: 'number', label: 'Stone dia. (mm)',         min: 0.1, step: 0.1 },
      { key: 'seat_style', kind: 'select', label: 'Seat style', options: [
        { value: 'bezel_cup', label: 'Bezel cup' },
        { value: 'prong_cup', label: 'Prong cup (4 prongs)' },
        { value: 'claw_cup',  label: 'Claw cup' },
      ] },
      { key: 'seat_depth',         kind: 'number', label: 'Seat depth (mm)',         min: 0.1, step: 0.1 },
      { key: 'ring_wire_diameter', kind: 'number', label: 'Ring wire dia. (mm)',     min: 0.1, step: 0.05 },
      { key: 'ring_inner_diameter',kind: 'number', label: 'Ring inner dia. (mm)',    min: 0.1, step: 0.1 },
      { key: 'bail_height',        kind: 'number', label: 'Bail height (mm)',        min: 0.1, step: 0.1 },
    ],
  },
  {
    op: 'jewelry_vtip_protector',
    label: 'V-Tip Protector',
    icon: Circle,
    defaults: { stone_shape: 'pear', tip_count: 1, tip_width: 0.6, tip_length: 1.0, wall_thickness: 0.3, seat_angle_deg: 55 },
    caption: 'V-tip metal caps for pointed fancy-cut stones (pear, marquise, heart, trillion) — prevent chipping.',
    fields: [
      { key: 'stone_shape', kind: 'select', label: 'Stone shape', options: [
        { value: 'pear',     label: 'Pear' },
        { value: 'marquise', label: 'Marquise' },
        { value: 'heart',    label: 'Heart' },
        { value: 'trillion', label: 'Trillion' },
      ] },
      { key: 'tip_count',       kind: 'number', label: 'Tip count',          min: 1, step: 1 },
      { key: 'tip_width',       kind: 'number', label: 'Tip width (mm)',     min: 0.1, step: 0.05 },
      { key: 'tip_length',      kind: 'number', label: 'Tip length (mm)',    min: 0.1, step: 0.1 },
      { key: 'wall_thickness',  kind: 'number', label: 'Wall thick. (mm)',   min: 0.1, step: 0.05 },
      { key: 'seat_angle_deg',  kind: 'number', label: 'Seat angle (°)',     min: 1, max: 179, step: 1 },
    ],
  },
  {
    op: 'jewelry_bombe_cluster',
    label: 'Bombé Cluster',
    icon: LayoutGrid,
    defaults: { dome_radius: 8.0, stone_size: 1.5, stone_count: 12, cap_half_angle_deg: 60, base_height: 1.0 },
    caption: 'Bombé (dome) cluster — stones distributed over a spherical-cap surface via Fibonacci spiral.',
    fields: [
      { key: 'dome_radius',         kind: 'number', label: 'Dome radius (mm)',        min: 0.1, step: 0.5 },
      { key: 'stone_size',          kind: 'number', label: 'Stone size (mm)',         min: 0.1, step: 0.1 },
      { key: 'stone_count',         kind: 'number', label: 'Stone count',             min: 1, step: 1 },
      { key: 'cap_half_angle_deg',  kind: 'number', label: 'Cap half-angle (°)',      min: 1, max: 89, step: 1 },
      { key: 'base_height',         kind: 'number', label: 'Base ring height (mm)',   min: 0, step: 0.1 },
    ],
  },
  {
    op: 'jewelry_patterned_bezel',
    label: 'Patterned Bezel',
    icon: Circle,
    defaults: { stone_diameter: 6.5, wall_thickness: 0.5, bezel_height: 3.0, bearing_ledge_height: 1.2, pattern: 'lotus', petal_count: 8 },
    fields: [
      { key: 'stone_diameter',       kind: 'number', label: 'Stone dia. (mm)',        min: 0.1, step: 0.1 },
      { key: 'wall_thickness',       kind: 'number', label: 'Wall thick. (mm)',       min: 0.1, step: 0.05 },
      { key: 'bezel_height',         kind: 'number', label: 'Bezel height (mm)',      min: 0.1, step: 0.1 },
      { key: 'bearing_ledge_height', kind: 'number', label: 'Bearing ledge ht. (mm)', min: 0.05, step: 0.05 },
      { key: 'pattern', kind: 'select', label: 'Pattern', options: [
        { value: 'lotus',   label: 'Lotus (floral petals)' },
        { value: 'compass', label: 'Compass (ray projections)' },
        { value: 'star',    label: 'Star (V-notch peaks)' },
        { value: 'plain',   label: 'Plain' },
      ] },
      { key: 'petal_count', kind: 'number', label: 'Petal / motif count', min: 3, step: 1,
        showWhen: (n) => n.pattern !== 'plain' },
    ],
  },
  {
    op: 'jewelry_trellis_prong',
    label: 'Trellis Prong',
    icon: Circle,
    defaults: { stone_diameter: 6.5, prong_count: 6, wire_gauge: 1.0, prong_height: 2.5, weave_style: 'x_cross', cross_height: 1.2 },
    caption: 'Trellis (cross-prong) basket — interwoven crossing prong wires around the stone.',
    fields: [
      { key: 'stone_diameter', kind: 'number', label: 'Stone dia. (mm)',    min: 0.1, step: 0.1 },
      { key: 'prong_count',    kind: 'number', label: 'Prong count (even)', min: 4, step: 2 },
      { key: 'wire_gauge',     kind: 'number', label: 'Wire gauge (mm)',    min: 0.1, step: 0.05 },
      { key: 'prong_height',   kind: 'number', label: 'Prong height (mm)',  min: 0.1, step: 0.1 },
      { key: 'weave_style', kind: 'select', label: 'Weave style', options: [
        { value: 'x_cross',  label: 'X-cross (plain weave)' },
        { value: 'diagonal', label: 'Diagonal (twill)' },
        { value: 'square',   label: 'Square (with cross-bars)' },
      ] },
      { key: 'cross_height', kind: 'number', label: 'Cross height (mm)', min: 0.01, step: 0.1 },
    ],
  },
  {
    op: 'jewelry_bar_channel_graduated',
    label: 'Grad. Bar Channel',
    icon: Layers,
    defaults: { stone_count: 5, largest_diameter: 3.0, smallest_diameter: 1.5, stone_spacing: 0.15, bar_width: 0.6, bar_height: 0.8, floor_thickness: 0.4 },
    caption: 'Graduated bar-channel row — stones taper from largest (centre) to smallest (ends) with bar pillars.',
    fields: [
      { key: 'stone_count',        kind: 'number', label: 'Stone count',             min: 1, step: 1 },
      { key: 'largest_diameter',   kind: 'number', label: 'Largest stone dia. (mm)', min: 0.1, step: 0.1 },
      { key: 'smallest_diameter',  kind: 'number', label: 'Smallest stone dia. (mm)', min: 0.1, step: 0.1 },
      { key: 'stone_spacing',      kind: 'number', label: 'Stone gap (mm)',          min: 0, step: 0.05 },
      { key: 'bar_width',          kind: 'number', label: 'Bar width (mm)',          min: 0.1, step: 0.05 },
      { key: 'bar_height',         kind: 'number', label: 'Bar height (mm)',         min: 0.1, step: 0.1 },
      { key: 'floor_thickness',    kind: 'number', label: 'Floor thickness (mm)',    min: 0.1, step: 0.05 },
    ],
  },

  // ── Gem seat types (channel_seat, bezel_seat, fishtail_seat, multi_stone_seat, pave_field_seat, cluster_halo_seat, gypsy_seat, baguette_channel_seat) ──

  {
    op: 'channel_seat',
    label: 'Channel Seat',
    icon: Layers,
    defaults: { cut: 'round_brilliant', diameter_mm: 2.5, n_stones: 7, pitch_mm: 2.8, girdle_clearance_mm: 0.05, crown_relief_mm: 0.3 },
    caption: 'Continuous bearing groove for a row of N stones. Use auto_cut_host_id to subtract from host.',
    fields: [
      { key: 'cut', kind: 'select', label: 'Cut', options: [
        { value: 'round_brilliant', label: 'Round brilliant' }, { value: 'princess', label: 'Princess' },
        { value: 'oval', label: 'Oval' }, { value: 'emerald', label: 'Emerald' },
        { value: 'marquise', label: 'Marquise' }, { value: 'pear', label: 'Pear' },
        { value: 'cushion', label: 'Cushion' }, { value: 'radiant', label: 'Radiant' },
        { value: 'asscher', label: 'Asscher' }, { value: 'trillion', label: 'Trillion' },
        { value: 'heart', label: 'Heart' }, { value: 'baguette', label: 'Baguette' },
        { value: 'briolette', label: 'Briolette' }, { value: 'old_european', label: 'Old European' },
        { value: 'old_mine', label: 'Old Mine' }, { value: 'rose_cut', label: 'Rose cut' },
        { value: 'single_cut', label: 'Single cut' }, { value: 'french_cut', label: 'French cut' },
        { value: 'half_moon', label: 'Half moon' }, { value: 'trapezoid', label: 'Trapezoid' },
        { value: 'kite', label: 'Kite' }, { value: 'bullet', label: 'Bullet' },
        { value: 'tapered_baguette', label: 'Tapered baguette' }, { value: 'lozenge', label: 'Lozenge' },
        { value: 'shield', label: 'Shield' }, { value: 'calf_head', label: 'Calf head' },
        { value: 'portuguese', label: 'Portuguese' }, { value: 'ceylon', label: 'Ceylon' },
        { value: 'flanders', label: 'Flanders' }, { value: 'square_emerald', label: 'Square emerald' },
      ] },
      { key: 'diameter_mm', kind: 'number', label: 'Stone dia. (mm)', min: 0.1, step: 0.1 },
      { key: 'n_stones',    kind: 'number', label: 'Stone count',     min: 1, step: 1 },
      { key: 'pitch_mm',    kind: 'number', label: 'C-to-C pitch (mm)', min: 0.1, step: 0.05 },
      { key: 'girdle_clearance_mm', kind: 'number', label: 'Girdle clearance (mm)', min: 0, step: 0.01 },
      { key: 'crown_relief_mm',     kind: 'number', label: 'Crown relief (mm)',     min: 0, step: 0.05 },
      { key: 'auto_cut_host_id',    kind: 'feature_picker', label: 'Auto-cut host body' },
    ],
  },
  {
    op: 'bezel_seat',
    label: 'Bezel Seat',
    icon: Circle,
    defaults: { cut: 'round_brilliant', diameter_mm: 6.5, bezel_wall_height_mm: 1.0, tapered: false, taper_angle_deg: 5, girdle_clearance_mm: 0.08, crown_relief_mm: 0.2 },
    caption: 'Inner bearing ledge for bezel / collet. Set tapered=true for collet-style tapered bore.',
    fields: [
      { key: 'cut', kind: 'select', label: 'Cut', options: [
        { value: 'round_brilliant', label: 'Round brilliant' }, { value: 'princess', label: 'Princess' },
        { value: 'oval', label: 'Oval' }, { value: 'emerald', label: 'Emerald' },
        { value: 'marquise', label: 'Marquise' }, { value: 'pear', label: 'Pear' },
        { value: 'cushion', label: 'Cushion' }, { value: 'radiant', label: 'Radiant' },
        { value: 'asscher', label: 'Asscher' }, { value: 'trillion', label: 'Trillion' },
        { value: 'heart', label: 'Heart' }, { value: 'baguette', label: 'Baguette' },
        { value: 'briolette', label: 'Briolette' }, { value: 'old_european', label: 'Old European' },
        { value: 'old_mine', label: 'Old Mine' }, { value: 'rose_cut', label: 'Rose cut' },
        { value: 'single_cut', label: 'Single cut' }, { value: 'french_cut', label: 'French cut' },
        { value: 'half_moon', label: 'Half moon' }, { value: 'trapezoid', label: 'Trapezoid' },
        { value: 'kite', label: 'Kite' }, { value: 'bullet', label: 'Bullet' },
        { value: 'tapered_baguette', label: 'Tapered baguette' }, { value: 'lozenge', label: 'Lozenge' },
        { value: 'shield', label: 'Shield' }, { value: 'calf_head', label: 'Calf head' },
        { value: 'portuguese', label: 'Portuguese' }, { value: 'ceylon', label: 'Ceylon' },
        { value: 'flanders', label: 'Flanders' }, { value: 'square_emerald', label: 'Square emerald' },
      ] },
      { key: 'diameter_mm',          kind: 'number',  label: 'Stone dia. (mm)',          min: 0.1, step: 0.1 },
      { key: 'bezel_wall_height_mm', kind: 'number',  label: 'Wall height above girdle (mm)', min: 0.1, step: 0.1 },
      { key: 'tapered',              kind: 'boolean', label: 'Tapered bore (collet)' },
      { key: 'taper_angle_deg',      kind: 'number',  label: 'Taper angle (°)', min: 0.1, max: 30, step: 0.5,
        showWhen: (n) => n.tapered },
      { key: 'girdle_clearance_mm',  kind: 'number',  label: 'Girdle clearance (mm)', min: 0, step: 0.01 },
      { key: 'crown_relief_mm',      kind: 'number',  label: 'Crown relief (mm)',     min: 0, step: 0.05 },
      { key: 'auto_cut_host_id',     kind: 'feature_picker', label: 'Auto-cut host body' },
    ],
  },
  {
    op: 'fishtail_seat',
    label: 'Fishtail Seat',
    icon: Disc,
    defaults: { cut: 'round_brilliant', diameter_mm: 2.0, bright_cut_angle_deg: 45, bright_cut_depth_mm: 0.15, n_bright_facets: 4 },
    caption: 'Fishtail (bright-cut) accent seat with radial V-cut grooves. Common for pavé accent stones.',
    fields: [
      { key: 'cut', kind: 'select', label: 'Cut', options: [
        { value: 'round_brilliant', label: 'Round brilliant' }, { value: 'princess', label: 'Princess' },
        { value: 'oval', label: 'Oval' }, { value: 'marquise', label: 'Marquise' },
        { value: 'cushion', label: 'Cushion' },
      ] },
      { key: 'diameter_mm',           kind: 'number', label: 'Stone dia. (mm)',     min: 0.1, step: 0.1 },
      { key: 'bright_cut_angle_deg',  kind: 'number', label: 'Bright-cut angle (°)', min: 1, max: 89, step: 1 },
      { key: 'bright_cut_depth_mm',   kind: 'number', label: 'Bright-cut depth (mm)', min: 0.01, step: 0.01 },
      { key: 'n_bright_facets',       kind: 'number', label: 'Bright-cut facets',   min: 1, step: 1 },
      { key: 'auto_cut_host_id',      kind: 'feature_picker', label: 'Auto-cut host body' },
    ],
  },

  // ── Ring ops v3–v4 ───────────────────────────────────────────────────────

  {
    op: 'eternity_band',
    label: 'Eternity Band',
    icon: Circle,
    defaults: { ring_size: 7, system: 'us', stone_diameter_mm: 2.0, coverage: 'full', setting_style: 'channel', band_width_mm: 3.0, thickness_mm: 1.2, stone_spacing_mm: 0.1 },
    fields: [
      { key: 'ring_size',  kind: 'number',  label: 'Ring size', min: 0 },
      { key: 'system',     kind: 'select',  label: 'Size system', options: [
        { value: 'us', label: 'US' }, { value: 'uk', label: 'UK/AU' }, { value: 'eu', label: 'EU' }, { value: 'jp', label: 'JP' },
      ] },
      { key: 'stone_diameter_mm', kind: 'number', label: 'Stone dia. (mm)', min: 0.1, step: 0.1 },
      { key: 'coverage', kind: 'select', label: 'Coverage', options: [
        { value: 'full',          label: 'Full (360°)' },
        { value: 'half',          label: 'Half (180°)' },
        { value: 'three_quarter', label: 'Three-quarter (270°)' },
      ] },
      { key: 'setting_style', kind: 'select', label: 'Setting style', options: [
        { value: 'channel',      label: 'Channel' },
        { value: 'shared_prong', label: 'Shared prong' },
        { value: 'pave',         label: 'Pavé' },
      ] },
      { key: 'band_width_mm',     kind: 'number', label: 'Band width (mm)',    min: 0.1, step: 0.5 },
      { key: 'thickness_mm',      kind: 'number', label: 'Wall thickness (mm)', min: 0.1, step: 0.1 },
      { key: 'stone_spacing_mm',  kind: 'number', label: 'Stone gap (mm)',      min: 0, step: 0.05 },
    ],
  },
  {
    op: 'signet_ring',
    label: 'Signet Ring',
    icon: Circle,
    defaults: { ring_size: 7, system: 'us', face_shape: 'oval', face_length_mm: 12.0, face_width_mm: 10.0, face_height_mm: 3.0, intaglio_depth_mm: 0, band_width_mm: 4.0, thickness_mm: 1.8, shoulder_style: 'plain' },
    fields: [
      { key: 'ring_size',     kind: 'number',  label: 'Ring size', min: 0 },
      { key: 'system',        kind: 'select',  label: 'Size system', options: [
        { value: 'us', label: 'US' }, { value: 'uk', label: 'UK/AU' }, { value: 'eu', label: 'EU' }, { value: 'jp', label: 'JP' },
      ] },
      { key: 'face_shape', kind: 'select', label: 'Face shape', options: [
        { value: 'flat',    label: 'Flat' },
        { value: 'oval',    label: 'Oval' },
        { value: 'cushion', label: 'Cushion' },
      ] },
      { key: 'face_length_mm',    kind: 'number', label: 'Seal length (mm)', min: 0.1, step: 0.5 },
      { key: 'face_width_mm',     kind: 'number', label: 'Seal width (mm)',  min: 0.1, step: 0.5 },
      { key: 'face_height_mm',    kind: 'number', label: 'Seal height (mm)', min: 0.1, step: 0.1 },
      { key: 'intaglio_depth_mm', kind: 'number', label: 'Intaglio depth (mm)', min: 0, step: 0.1 },
      { key: 'band_width_mm',     kind: 'number', label: 'Band width (mm)',  min: 0.1, step: 0.5 },
      { key: 'thickness_mm',      kind: 'number', label: 'Wall thick. (mm)', min: 0.1, step: 0.1 },
      { key: 'shoulder_style', kind: 'select', label: 'Shoulder style', options: [
        { value: 'plain',       label: 'Plain' }, { value: 'cathedral', label: 'Cathedral' },
        { value: 'split_shank', label: 'Split shank' }, { value: 'bypass', label: 'Bypass' },
      ] },
    ],
  },
  {
    op: 'stacking_band_set',
    label: 'Stacking Band Set',
    icon: Circle,
    defaults: { ring_size: 7, system: 'us', band_count: 3, band_width_mm: 2.0, thickness_mm: 1.4, profile: 'flat', nest_gap_mm: 0.1, include_wishbone: false },
    fields: [
      { key: 'ring_size',     kind: 'number', label: 'Ring size', min: 0 },
      { key: 'system',        kind: 'select', label: 'Size system', options: [
        { value: 'us', label: 'US' }, { value: 'uk', label: 'UK/AU' }, { value: 'eu', label: 'EU' }, { value: 'jp', label: 'JP' },
      ] },
      { key: 'band_count',    kind: 'number', label: 'Band count', min: 1, max: 8, step: 1 },
      { key: 'band_width_mm', kind: 'number', label: 'Band width (mm)',    min: 0.1, step: 0.5 },
      { key: 'thickness_mm',  kind: 'number', label: 'Wall thickness (mm)', min: 0.1, step: 0.1 },
      { key: 'profile', kind: 'select', label: 'Profile', options: [
        { value: 'flat',        label: 'Flat' }, { value: 'half_round',  label: 'Half round' },
        { value: 'knife_edge',  label: 'Knife edge' }, { value: 'euro', label: 'Euro' },
        { value: 'comfort_fit', label: 'Comfort fit' }, { value: 'd_shape', label: 'D-shape' },
        { value: 'cigar_band',  label: 'Cigar band' }, { value: 'concave', label: 'Concave' },
      ] },
      { key: 'nest_gap_mm',       kind: 'number',  label: 'Nest gap (mm)',    min: 0, step: 0.05 },
      { key: 'include_wishbone',  kind: 'boolean', label: 'Include wishbone/contour band' },
    ],
  },
  {
    op: 'contoured_band',
    label: 'Contoured Band',
    icon: Circle,
    defaults: { ring_size: 7, system: 'us', notch_depth_mm: 1.2, notch_width_mm: 3.0, match_radius_mm: 10.5, contour_style: 'curved', band_width_mm: 3.5, thickness_mm: 1.6, profile: 'flat', shoulder_style: 'plain' },
    caption: 'Shadow / contoured wedding band shaped to hug an engagement ring.',
    fields: [
      { key: 'ring_size',      kind: 'number', label: 'Ring size', min: 0 },
      { key: 'system',         kind: 'select', label: 'Size system', options: [
        { value: 'us', label: 'US' }, { value: 'uk', label: 'UK/AU' }, { value: 'eu', label: 'EU' }, { value: 'jp', label: 'JP' },
      ] },
      { key: 'contour_style', kind: 'select', label: 'Contour style', options: [
        { value: 'curved',  label: 'Curved arc (shadow band)' },
        { value: 'notched', label: 'Notched (V/U centre)' },
      ] },
      { key: 'notch_depth_mm',   kind: 'number', label: 'Notch depth (mm)',  min: 0.01, step: 0.1 },
      { key: 'notch_width_mm',   kind: 'number', label: 'Notch width (mm)',  min: 0.01, step: 0.1 },
      { key: 'match_radius_mm',  kind: 'number', label: 'Match radius (mm)', min: 0.1, step: 0.5 },
      { key: 'band_width_mm',    kind: 'number', label: 'Band width (mm)',   min: 0.1, step: 0.5 },
      { key: 'thickness_mm',     kind: 'number', label: 'Wall thick. (mm)',  min: 0.1, step: 0.1 },
      { key: 'profile', kind: 'select', label: 'Profile', options: [
        { value: 'flat',        label: 'Flat' }, { value: 'half_round', label: 'Half round' },
        { value: 'comfort_fit', label: 'Comfort fit' }, { value: 'd_shape', label: 'D-shape' },
        { value: 'euro',        label: 'Euro' },
      ] },
      { key: 'shoulder_style', kind: 'select', label: 'Shoulder style', options: [
        { value: 'plain', label: 'Plain' }, { value: 'cathedral', label: 'Cathedral' },
        { value: 'split_shank', label: 'Split shank' }, { value: 'bypass', label: 'Bypass' },
      ] },
    ],
  },
  {
    op: 'solitaire_ring',
    label: 'Solitaire Ring',
    icon: Circle,
    defaults: { ring_size: 7, system: 'us', shank_profile: 'comfort_fit', shoulder_style: 'cathedral', band_width_mm: 3.0, thickness_mm: 1.6, head_height_mm: 5.0, center_stone_diameter_mm: 6.5, taper_ratio: 1.0 },
    fields: [
      { key: 'ring_size',    kind: 'number', label: 'Ring size', min: 0 },
      { key: 'system',       kind: 'select', label: 'Size system', options: [
        { value: 'us', label: 'US' }, { value: 'uk', label: 'UK/AU' }, { value: 'eu', label: 'EU' }, { value: 'jp', label: 'JP' },
      ] },
      { key: 'shank_profile', kind: 'select', label: 'Shank profile', options: [
        { value: 'comfort_fit', label: 'Comfort fit' }, { value: 'd_shape', label: 'D-shape' },
        { value: 'flat', label: 'Flat' }, { value: 'half_round', label: 'Half round' },
        { value: 'knife_edge', label: 'Knife edge' }, { value: 'euro', label: 'Euro' },
        { value: 'tapered', label: 'Tapered' },
      ] },
      { key: 'shoulder_style', kind: 'select', label: 'Shoulder style', options: [
        { value: 'plain', label: 'Plain' }, { value: 'cathedral', label: 'Cathedral' },
        { value: 'split_shank', label: 'Split shank' }, { value: 'bypass', label: 'Bypass' },
      ] },
      { key: 'band_width_mm',            kind: 'number', label: 'Band width (mm)',         min: 0.1, step: 0.5 },
      { key: 'thickness_mm',             kind: 'number', label: 'Wall thick. (mm)',         min: 0.1, step: 0.1 },
      { key: 'head_height_mm',           kind: 'number', label: 'Head height (mm)',         min: 0.1, step: 0.5 },
      { key: 'center_stone_diameter_mm', kind: 'number', label: 'Centre stone dia. (mm)',   min: 0.1, step: 0.1 },
      { key: 'taper_ratio',              kind: 'number', label: 'Taper ratio (1=uniform)',  min: 0.1, max: 1.0, step: 0.05 },
    ],
  },
  {
    op: 'mens_band',
    label: "Men's Band",
    icon: Circle,
    defaults: { ring_size: 10, system: 'us', profile: 'comfort_fit', band_width_mm: 8.0, thickness_mm: 2.0, taper_ratio: 1.0, groove_depth_mm: 0, groove_width_mm: 1.5, milgrain_edges: false, surface_finish: 'polished' },
    fields: [
      { key: 'ring_size',   kind: 'number', label: 'Ring size', min: 0 },
      { key: 'system',      kind: 'select', label: 'Size system', options: [
        { value: 'us', label: 'US' }, { value: 'uk', label: 'UK/AU' }, { value: 'eu', label: 'EU' }, { value: 'jp', label: 'JP' },
      ] },
      { key: 'profile', kind: 'select', label: 'Profile', options: [
        { value: 'comfort_fit', label: 'Comfort fit' }, { value: 'euro', label: 'Euro' },
        { value: 'd_shape', label: 'D-shape' }, { value: 'flat', label: 'Flat' },
        { value: 'cigar_band', label: 'Cigar band' }, { value: 'bombe', label: 'Bombé' },
        { value: 'concave', label: 'Concave' }, { value: 'square', label: 'Square' },
        { value: 'half_round', label: 'Half round' },
      ] },
      { key: 'band_width_mm', kind: 'number', label: 'Band width (mm)',    min: 0.1, step: 0.5 },
      { key: 'thickness_mm',  kind: 'number', label: 'Wall thick. (mm)',   min: 0.1, step: 0.1 },
      { key: 'taper_ratio',   kind: 'number', label: 'Taper ratio',        min: 0.1, max: 1.0, step: 0.05 },
      { key: 'groove_depth_mm', kind: 'number',  label: 'Groove depth (mm, 0=none)', min: 0, step: 0.1 },
      { key: 'groove_width_mm', kind: 'number',  label: 'Groove width (mm)',         min: 0.1, step: 0.1,
        showWhen: (n) => n.groove_depth_mm > 0 },
      { key: 'milgrain_edges', kind: 'boolean', label: 'Milgrain edges' },
      { key: 'surface_finish', kind: 'select', label: 'Surface finish', options: [
        { value: 'polished', label: 'Polished' }, { value: 'matte', label: 'Matte' },
        { value: 'hammered', label: 'Hammered' }, { value: 'satin', label: 'Satin' },
        { value: 'brushed',  label: 'Brushed' },
      ] },
    ],
  },
  {
    op: 'wedding_set',
    label: 'Wedding Set',
    icon: Circle,
    defaults: { ring_size: 7, system: 'us', eng_profile: 'comfort_fit', eng_shoulder_style: 'cathedral', eng_band_width_mm: 2.5, eng_thickness_mm: 1.6, band_profile: 'flat', band_width_mm: 3.0, band_thickness_mm: 1.6, contour_style: 'curved', notch_depth_mm: 1.2, notch_width_mm: 2.5 },
    caption: 'Engagement ring + matched contoured wedding band as a paired output node.',
    fields: [
      { key: 'ring_size', kind: 'number', label: 'Ring size', min: 0 },
      { key: 'system',    kind: 'select', label: 'Size system', options: [
        { value: 'us', label: 'US' }, { value: 'uk', label: 'UK/AU' }, { value: 'eu', label: 'EU' }, { value: 'jp', label: 'JP' },
      ] },
      { key: 'eng_profile', kind: 'select', label: 'Eng. profile', options: [
        { value: 'comfort_fit', label: 'Comfort fit' }, { value: 'd_shape', label: 'D-shape' },
        { value: 'flat', label: 'Flat' }, { value: 'half_round', label: 'Half round' },
        { value: 'knife_edge', label: 'Knife edge' }, { value: 'euro', label: 'Euro' },
      ] },
      { key: 'eng_shoulder_style', kind: 'select', label: 'Eng. shoulder', options: [
        { value: 'plain', label: 'Plain' }, { value: 'cathedral', label: 'Cathedral' },
        { value: 'split_shank', label: 'Split shank' },
      ] },
      { key: 'eng_band_width_mm', kind: 'number', label: 'Eng. band width (mm)', min: 0.1, step: 0.5 },
      { key: 'eng_thickness_mm',  kind: 'number', label: 'Eng. thickness (mm)',  min: 0.1, step: 0.1 },
      { key: 'band_profile', kind: 'select', label: 'Band profile', options: [
        { value: 'flat', label: 'Flat' }, { value: 'half_round', label: 'Half round' },
        { value: 'comfort_fit', label: 'Comfort fit' },
      ] },
      { key: 'band_width_mm',     kind: 'number', label: 'Band width (mm)',    min: 0.1, step: 0.5 },
      { key: 'band_thickness_mm', kind: 'number', label: 'Band thickness (mm)', min: 0.1, step: 0.1 },
      { key: 'contour_style', kind: 'select', label: 'Contour style', options: [
        { value: 'curved',  label: 'Curved arc' }, { value: 'notched', label: 'Notched' },
      ] },
      { key: 'notch_depth_mm', kind: 'number', label: 'Notch depth (mm)', min: 0.01, step: 0.1 },
      { key: 'notch_width_mm', kind: 'number', label: 'Notch width (mm)', min: 0.01, step: 0.1 },
    ],
  },
  {
    op: 'cocktail_ring',
    label: 'Cocktail Ring',
    icon: Circle,
    defaults: { ring_size: 7, system: 'us', shank_profile: 'tapered', shoulder_style: 'plain', band_width_mm: 4.0, thickness_mm: 1.8, taper_ratio: 0.7, mount_style: 'dome', mount_diameter_mm: 18.0, mount_height_mm: 8.0, stone_diameter_mm: 14.0 },
    fields: [
      { key: 'ring_size',  kind: 'number', label: 'Ring size', min: 0 },
      { key: 'system',     kind: 'select', label: 'Size system', options: [
        { value: 'us', label: 'US' }, { value: 'uk', label: 'UK/AU' }, { value: 'eu', label: 'EU' }, { value: 'jp', label: 'JP' },
      ] },
      { key: 'shank_profile', kind: 'select', label: 'Shank profile', options: [
        { value: 'tapered', label: 'Tapered' }, { value: 'comfort_fit', label: 'Comfort fit' },
        { value: 'd_shape', label: 'D-shape' }, { value: 'flat', label: 'Flat' },
      ] },
      { key: 'shoulder_style', kind: 'select', label: 'Shoulder style', options: [
        { value: 'plain', label: 'Plain' }, { value: 'cathedral', label: 'Cathedral' },
        { value: 'split_shank', label: 'Split shank' },
      ] },
      { key: 'band_width_mm',      kind: 'number', label: 'Band width (mm)',    min: 0.1, step: 0.5 },
      { key: 'thickness_mm',       kind: 'number', label: 'Wall thick. (mm)',   min: 0.1, step: 0.1 },
      { key: 'taper_ratio',        kind: 'number', label: 'Taper ratio',        min: 0.1, max: 1.0, step: 0.05 },
      { key: 'mount_style', kind: 'select', label: 'Mount style', options: [
        { value: 'dome',    label: 'Dome' }, { value: 'cluster', label: 'Cluster' },
        { value: 'bezel',   label: 'Bezel' }, { value: 'prong',   label: 'Prong' },
      ] },
      { key: 'mount_diameter_mm',  kind: 'number', label: 'Mount dia. (mm)',    min: 0.1, step: 0.5 },
      { key: 'mount_height_mm',    kind: 'number', label: 'Mount height (mm)',  min: 0.1, step: 0.5 },
      { key: 'stone_diameter_mm',  kind: 'number', label: 'Stone dia. (mm)',    min: 0.1, step: 0.5 },
    ],
  },
  {
    op: 'bypass_ring',
    label: 'Bypass Ring',
    icon: Circle,
    defaults: { ring_size: 7, system: 'us', cross_style: 'crossover', profile: 'half_round', band_width_mm: 3.0, thickness_mm: 1.5, bypass_offset_mm: 4.0, overlap_deg: 20, stone_a_diameter_mm: 6.0, stone_b_diameter_mm: 6.0, mount_height_mm: 4.5 },
    caption: 'Two-element crossover or toi-et-moi ring with two stone mount attach-points.',
    fields: [
      { key: 'ring_size', kind: 'number', label: 'Ring size', min: 0 },
      { key: 'system',    kind: 'select', label: 'Size system', options: [
        { value: 'us', label: 'US' }, { value: 'uk', label: 'UK/AU' }, { value: 'eu', label: 'EU' }, { value: 'jp', label: 'JP' },
      ] },
      { key: 'cross_style', kind: 'select', label: 'Style', options: [
        { value: 'crossover',   label: 'Crossover' },
        { value: 'toi_et_moi',  label: 'Toi et moi' },
      ] },
      { key: 'profile', kind: 'select', label: 'Arm profile', options: [
        { value: 'half_round', label: 'Half round' }, { value: 'comfort_fit', label: 'Comfort fit' },
        { value: 'd_shape', label: 'D-shape' }, { value: 'flat', label: 'Flat' },
      ] },
      { key: 'band_width_mm',       kind: 'number', label: 'Arm width (mm)',     min: 0.1, step: 0.5 },
      { key: 'thickness_mm',        kind: 'number', label: 'Arm thickness (mm)', min: 0.1, step: 0.1 },
      { key: 'bypass_offset_mm',    kind: 'number', label: 'Bypass offset (mm)', min: 0.1, step: 0.5 },
      { key: 'overlap_deg',         kind: 'number', label: 'Overlap (°)',         min: 0, max: 90, step: 1 },
      { key: 'stone_a_diameter_mm', kind: 'number', label: 'Stone A dia. (mm)',  min: 0.1, step: 0.1 },
      { key: 'stone_b_diameter_mm', kind: 'number', label: 'Stone B dia. (mm)',  min: 0.1, step: 0.1 },
      { key: 'mount_height_mm',     kind: 'number', label: 'Mount height (mm)', min: 0.1, step: 0.5 },
    ],
  },

  // ── Chain styles + composed pieces ─────────────────────────────────────

  {
    op: 'chain_assembly',
    label: 'Chain',
    icon: Layers,
    defaults: { style: 'cable', wire_gauge_mm: 1.0, total_length_mm: 457, open_ends: true, graduated: false },
    fields: [
      { key: 'style', kind: 'select', label: 'Chain style', options: [
        { value: 'cable',       label: 'Cable (alternating ovals)' },
        { value: 'curb',        label: 'Curb (flat twisted)' },
        { value: 'figaro',      label: 'Figaro (3+1 repeat)' },
        { value: 'rope',        label: 'Rope (helix)' },
        { value: 'box',         label: 'Box (square tube links)' },
        { value: 'snake',       label: 'Snake (scalloped)' },
        { value: 'byzantine',   label: 'Byzantine (4-link weave)' },
        { value: 'mariner',     label: 'Mariner / anchor' },
        { value: 'rolo',        label: 'Rolo / belcher' },
        { value: 'bismark',     label: 'Bismark (multi-row)' },
        { value: 'wheat',       label: 'Wheat / spiga' },
        { value: 'herringbone', label: 'Herringbone (flat woven)' },
        { value: 'omega',       label: 'Omega (plate spine)' },
        { value: 'popcorn',     label: 'Popcorn (spheroidal links)' },
        { value: 'ball',        label: 'Ball / bead chain' },
        { value: 'singapore',   label: 'Singapore (twisted curb)' },
      ] },
      { key: 'wire_gauge_mm',    kind: 'number', label: 'Wire gauge (mm)',       min: 0.1, step: 0.1 },
      { key: 'total_length_mm',  kind: 'number', label: 'Total length (mm)',     min: 1, step: 10 },
      { key: 'link_length_mm',   kind: 'number', label: 'Link length (mm)',      min: 0.1, step: 0.1 },
      { key: 'link_width_mm',    kind: 'number', label: 'Link width (mm)',       min: 0.1, step: 0.1 },
      { key: 'open_ends',        kind: 'boolean', label: 'Open end-links' },
      { key: 'graduated',        kind: 'boolean', label: 'Graduated (links scale from centre)' },
      { key: 'clasp_style', kind: 'select', label: 'Clasp style (optional)', options: [
        { value: '', label: 'None' },
        { value: 'lobster',      label: 'Lobster' },
        { value: 'spring_ring',  label: 'Spring ring' },
        { value: 'toggle',       label: 'Toggle' },
        { value: 'box_clasp',    label: 'Box clasp' },
      ] },
    ],
  },
  {
    op: 'tennis_bracelet',
    label: 'Tennis Bracelet',
    icon: Circle,
    defaults: { stone_diameter_mm: 3.0, stone_count: 20, wire_gauge_mm: 0.8, clasp_style: 'box_clasp' },
    fields: [
      { key: 'stone_diameter_mm', kind: 'number', label: 'Stone dia. (mm)', min: 0.1, step: 0.1 },
      { key: 'stone_count',       kind: 'number', label: 'Stone count',     min: 1, step: 1 },
      { key: 'wire_gauge_mm',     kind: 'number', label: 'Wire gauge (mm)', min: 0.1, step: 0.05 },
      { key: 'clasp_style', kind: 'select', label: 'Clasp style', options: [
        { value: 'box_clasp',   label: 'Box clasp' },
        { value: 'lobster',     label: 'Lobster' },
        { value: 'toggle',      label: 'Toggle' },
        { value: 'spring_ring', label: 'Spring ring' },
      ] },
    ],
  },
  {
    op: 'station_necklace',
    label: 'Station Necklace',
    icon: Layers,
    defaults: { chain_style: 'cable', chain_wire_gauge_mm: 0.8, station_count: 7, station_diameter_mm: 5.0, total_length_mm: 457 },
    fields: [
      { key: 'chain_style', kind: 'select', label: 'Chain style', options: [
        { value: 'cable', label: 'Cable' }, { value: 'curb', label: 'Curb' },
        { value: 'box', label: 'Box' }, { value: 'singapore', label: 'Singapore' },
      ] },
      { key: 'chain_wire_gauge_mm', kind: 'number', label: 'Chain gauge (mm)', min: 0.1, step: 0.05 },
      { key: 'station_count',       kind: 'number', label: 'Station count',    min: 1, step: 1 },
      { key: 'station_diameter_mm', kind: 'number', label: 'Station dia. (mm)', min: 0.1, step: 0.1 },
      { key: 'total_length_mm',     kind: 'number', label: 'Total length (mm)', min: 1, step: 10 },
    ],
  },
  {
    op: 'lariat',
    label: 'Lariat',
    icon: Layers,
    defaults: { chain_style: 'cable', wire_gauge_mm: 0.8, total_length_mm: 914, pendant_diameter_mm: 8.0 },
    fields: [
      { key: 'chain_style', kind: 'select', label: 'Chain style', options: [
        { value: 'cable', label: 'Cable' }, { value: 'rope', label: 'Rope' },
        { value: 'box', label: 'Box' }, { value: 'snake', label: 'Snake' },
      ] },
      { key: 'wire_gauge_mm',      kind: 'number', label: 'Wire gauge (mm)',       min: 0.1, step: 0.05 },
      { key: 'total_length_mm',    kind: 'number', label: 'Total length (mm)',     min: 1, step: 10 },
      { key: 'pendant_diameter_mm',kind: 'number', label: 'End pendant dia. (mm)', min: 0, step: 0.5 },
    ],
  },
  {
    op: 'charm_bracelet',
    label: 'Charm Bracelet',
    icon: Circle,
    defaults: { chain_style: 'cable', wire_gauge_mm: 1.2, total_length_mm: 190, charm_count: 5 },
    fields: [
      { key: 'chain_style', kind: 'select', label: 'Chain style', options: [
        { value: 'cable', label: 'Cable' }, { value: 'curb', label: 'Curb' },
        { value: 'rolo', label: 'Rolo' }, { value: 'box', label: 'Box' },
      ] },
      { key: 'wire_gauge_mm',  kind: 'number', label: 'Wire gauge (mm)',  min: 0.1, step: 0.1 },
      { key: 'total_length_mm',kind: 'number', label: 'Length (mm)',      min: 1, step: 5 },
      { key: 'charm_count',    kind: 'number', label: 'Charm attach slots', min: 0, step: 1 },
    ],
  },
  {
    op: 'multi_strand',
    label: 'Multi-Strand',
    icon: Layers,
    defaults: { strand_count: 3, chain_style: 'cable', wire_gauge_mm: 0.8, total_length_mm: 457, clasp_style: 'box_clasp' },
    fields: [
      { key: 'strand_count', kind: 'number', label: 'Strand count', min: 2, step: 1 },
      { key: 'chain_style', kind: 'select', label: 'Chain style', options: [
        { value: 'cable', label: 'Cable' }, { value: 'box', label: 'Box' },
        { value: 'rolo', label: 'Rolo' }, { value: 'snake', label: 'Snake' },
      ] },
      { key: 'wire_gauge_mm',   kind: 'number', label: 'Wire gauge (mm)',  min: 0.1, step: 0.05 },
      { key: 'total_length_mm', kind: 'number', label: 'Length (mm)',      min: 1, step: 10 },
      { key: 'clasp_style', kind: 'select', label: 'Clasp style', options: [
        { value: 'box_clasp', label: 'Box clasp' }, { value: 'toggle', label: 'Toggle' },
        { value: 'lobster', label: 'Lobster' },
      ] },
    ],
  },
  {
    op: 'extender_chain',
    label: 'Extender Chain',
    icon: Layers,
    defaults: { chain_style: 'cable', wire_gauge_mm: 0.6, length_mm: 50 },
    fields: [
      { key: 'chain_style', kind: 'select', label: 'Chain style', options: [
        { value: 'cable', label: 'Cable' }, { value: 'box', label: 'Box' }, { value: 'curb', label: 'Curb' },
      ] },
      { key: 'wire_gauge_mm', kind: 'number', label: 'Wire gauge (mm)', min: 0.1, step: 0.05 },
      { key: 'length_mm',     kind: 'number', label: 'Length (mm)',     min: 1, step: 5 },
    ],
  },

  // ── Findings ─────────────────────────────────────────────────────────────

  {
    op: 'finding',
    label: 'Finding',
    icon: Plus,
    defaults: { family: 'jump_ring', kind: 'round', wire_gauge_mm: 1.0, inner_diameter_mm: 5.0 },
    caption: 'Jewelry finding: jump ring, bail, ear finding, pin finding, end cap, or clasp.',
    fields: [
      { key: 'family', kind: 'select', label: 'Family', options: [
        { value: 'jump_ring',   label: 'Jump ring' },
        { value: 'bail',        label: 'Bail' },
        { value: 'ear_finding', label: 'Ear finding' },
        { value: 'pin_finding', label: 'Pin finding' },
        { value: 'end_cap',     label: 'End cap' },
        { value: 'clasp',       label: 'Clasp' },
      ] },
      { key: 'kind',           kind: 'text',   label: 'Kind (see jewelry_list_findings)' },
      { key: 'wire_gauge_mm',  kind: 'number', label: 'Wire gauge (mm)', min: 0.1, step: 0.05 },
      { key: 'inner_diameter_mm', kind: 'number', label: 'Inner dia. (mm)', min: 0.1, step: 0.1 },
      { key: 'body_length_mm', kind: 'number', label: 'Body length (mm)', min: 0.1, step: 0.5 },
      { key: 'hook_length_mm', kind: 'number', label: 'Hook length (mm)', min: 0.1, step: 0.5 },
      { key: 'post_length_mm', kind: 'number', label: 'Post length (mm)', min: 0.1, step: 0.5 },
    ],
  },

  // ── Whole pieces: pendant, earrings, brooch, cufflink, bangle ────────────

  {
    op: 'pendant',
    label: 'Pendant',
    icon: Disc,
    defaults: { style: 'solitaire_drop', outline_shape: 'teardrop', width_mm: 12.0, height_mm: 18.0, thickness_mm: 1.5, bail_type: 'loop', bail_wire_gauge_mm: 1.0, centre_stone_diameter_mm: 6.0, halo_stone_count: 0 },
    fields: [
      { key: 'style', kind: 'select', label: 'Pendant style', options: [
        { value: 'solitaire_drop', label: 'Solitaire drop' },
        { value: 'halo',           label: 'Halo' },
        { value: 'cluster',        label: 'Cluster' },
        { value: 'locket',         label: 'Locket' },
        { value: 'charm',          label: 'Charm' },
      ] },
      { key: 'outline_shape', kind: 'select', label: 'Frame shape', options: [
        { value: 'round',     label: 'Round' },   { value: 'oval',    label: 'Oval' },
        { value: 'teardrop',  label: 'Teardrop' },{ value: 'square',  label: 'Square' },
        { value: 'rectangle', label: 'Rectangle' },{ value: 'hexagon', label: 'Hexagon' },
        { value: 'heart',     label: 'Heart' },   { value: 'free_form', label: 'Free form' },
      ] },
      { key: 'width_mm',     kind: 'number', label: 'Frame width (mm)',   min: 0.1, step: 0.5 },
      { key: 'height_mm',    kind: 'number', label: 'Frame height (mm)',  min: 0.1, step: 0.5 },
      { key: 'thickness_mm', kind: 'number', label: 'Thickness (mm)',     min: 0.1, step: 0.1 },
      { key: 'bail_type', kind: 'select', label: 'Bail type', options: [
        { value: 'loop',  label: 'Loop' }, { value: 'pinch', label: 'Pinch' },
        { value: 'snap',  label: 'Snap' }, { value: 'tube',  label: 'Tube' },
      ] },
      { key: 'bail_wire_gauge_mm',       kind: 'number', label: 'Bail gauge (mm)',        min: 0.1, step: 0.05 },
      { key: 'centre_stone_diameter_mm', kind: 'number', label: 'Centre stone dia. (mm)', min: 0, step: 0.1 },
      { key: 'halo_stone_diameter_mm',   kind: 'number', label: 'Halo stone dia. (mm)',   min: 0, step: 0.1 },
      { key: 'halo_stone_count',         kind: 'number', label: 'Halo stone count',       min: 0, step: 1 },
    ],
  },
  {
    op: 'earrings',
    label: 'Earrings',
    icon: Circle,
    defaults: { style: 'stud', face_diameter_mm: 8.0, face_thickness_mm: 1.2, wire_gauge_mm: 0.8, post_length_mm: 10.0, hoop_inner_diameter_mm: 16.0, drop_length_mm: 20.0, stone_diameter_mm: 5.0, stone_count: 1 },
    caption: 'Parametric matched earring pair (left + right). Styles: stud, drop, hoop, huggie, chandelier.',
    fields: [
      { key: 'style', kind: 'select', label: 'Style', options: [
        { value: 'stud',       label: 'Stud' },
        { value: 'drop',       label: 'Drop' },
        { value: 'hoop',       label: 'Hoop' },
        { value: 'huggie',     label: 'Huggie' },
        { value: 'chandelier', label: 'Chandelier' },
      ] },
      { key: 'face_diameter_mm',      kind: 'number', label: 'Face dia. (mm)',         min: 0.1, step: 0.5 },
      { key: 'face_thickness_mm',     kind: 'number', label: 'Face thickness (mm)',    min: 0.1, step: 0.1 },
      { key: 'wire_gauge_mm',         kind: 'number', label: 'Wire / post gauge (mm)', min: 0.1, step: 0.05 },
      { key: 'post_length_mm',        kind: 'number', label: 'Post length (mm)', min: 0.1, step: 0.5,
        showWhen: (n) => n.style === 'stud' || n.style === 'huggie' },
      { key: 'hoop_inner_diameter_mm',kind: 'number', label: 'Hoop inner dia. (mm)', min: 0.1, step: 1,
        showWhen: (n) => n.style === 'hoop' || n.style === 'huggie' },
      { key: 'drop_length_mm',        kind: 'number', label: 'Drop length (mm)', min: 0.1, step: 1,
        showWhen: (n) => n.style === 'drop' || n.style === 'chandelier' },
      { key: 'stone_diameter_mm', kind: 'number', label: 'Stone dia. (mm)', min: 0, step: 0.1 },
      { key: 'stone_count',       kind: 'number', label: 'Stone count',     min: 1, step: 1 },
    ],
  },
  {
    op: 'brooch',
    label: 'Brooch',
    icon: Disc,
    defaults: { shape: 'oval', width_mm: 30.0, height_mm: 20.0, thickness_mm: 2.0, stone_diameter_mm: 0, stone_count: 0 },
    fields: [
      { key: 'shape', kind: 'select', label: 'Frame shape', options: [
        { value: 'round',       label: 'Round' },
        { value: 'oval',        label: 'Oval' },
        { value: 'square',      label: 'Square' },
        { value: 'rectangular', label: 'Rectangular' },
        { value: 'freeform',    label: 'Freeform' },
        { value: 'floral',      label: 'Floral' },
        { value: 'geometric',   label: 'Geometric' },
      ] },
      { key: 'width_mm',           kind: 'number', label: 'Width (mm)',        min: 0.1, step: 1 },
      { key: 'height_mm',          kind: 'number', label: 'Height (mm)',       min: 0.1, step: 1 },
      { key: 'thickness_mm',       kind: 'number', label: 'Thickness (mm)',    min: 0.1, step: 0.1 },
      { key: 'stone_diameter_mm',  kind: 'number', label: 'Stone dia. (mm, 0=none)', min: 0, step: 0.1 },
      { key: 'stone_count',        kind: 'number', label: 'Stone count',       min: 0, step: 1 },
    ],
  },
  {
    op: 'cufflink',
    label: 'Cufflink',
    icon: Disc,
    defaults: { face_width_mm: 14.0, face_height_mm: 10.0, face_thickness_mm: 3.0, back_style: 'toggle', post_length_mm: 8.0 },
    fields: [
      { key: 'face_width_mm',    kind: 'number', label: 'Face width (mm)',    min: 0.1, step: 0.5 },
      { key: 'face_height_mm',   kind: 'number', label: 'Face height (mm)',   min: 0.1, step: 0.5 },
      { key: 'face_thickness_mm',kind: 'number', label: 'Face thickness (mm)', min: 0.1, step: 0.1 },
      { key: 'back_style', kind: 'select', label: 'Back style', options: [
        { value: 'toggle',     label: 'Toggle' },
        { value: 't_bar',      label: 'T-bar' },
        { value: 'chain',      label: 'Chain' },
        { value: 'bullet',     label: 'Bullet' },
        { value: 'whale_back', label: 'Whale-back' },
      ] },
      { key: 'post_length_mm',   kind: 'number', label: 'Post length (mm)', min: 0.1, step: 0.5 },
      { key: 'stone_diameter_mm',kind: 'number', label: 'Stone dia. (mm, 0=none)', min: 0, step: 0.1 },
    ],
  },
  {
    op: 'bangle',
    label: 'Bangle',
    icon: Circle,
    defaults: { form: 'closed', wrist_size: 165, wrist_size_system: 'mm', cross_section: 'round', wire_gauge_mm: 3.0, band_width_mm: 5.0, thickness_mm: 2.0 },
    fields: [
      { key: 'form', kind: 'select', label: 'Form', options: [
        { value: 'closed',    label: 'Closed bangle' },
        { value: 'open_cuff', label: 'Open cuff' },
      ] },
      { key: 'wrist_size',         kind: 'number', label: 'Wrist size',      min: 0.1 },
      { key: 'wrist_size_system', kind: 'select', label: 'Size system', options: [
        { value: 'mm',     label: 'Circumference (mm)' },
        { value: 'inches', label: 'Circumference (in)' },
        { value: 'us',     label: 'US bangle size' },
      ] },
      { key: 'cross_section', kind: 'select', label: 'Cross-section', options: [
        { value: 'round',      label: 'Round' },
        { value: 'oval',       label: 'Oval' },
        { value: 'flat',       label: 'Flat' },
        { value: 'half_round', label: 'Half round' },
        { value: 'square',     label: 'Square' },
      ] },
      { key: 'wire_gauge_mm', kind: 'number', label: 'Wire gauge (mm)', min: 0.1, step: 0.1 },
      { key: 'band_width_mm', kind: 'number', label: 'Band width (mm)', min: 0.1, step: 0.5 },
      { key: 'thickness_mm',  kind: 'number', label: 'Thickness (mm)',  min: 0.1, step: 0.1 },
    ],
  },

  // ── Decorative ops ───────────────────────────────────────────────────────

  {
    op: 'decorative_apply',
    label: 'Decorative',
    icon: Waves,
    defaults: { feature: 'milgrain', target_ref: '', bead_diameter_mm: 0.6, pitch_mm: 0.7 },
    caption: 'Decorative surface / edge treatment. feature selects the treatment kind.',
    fields: [
      { key: 'feature', kind: 'select', label: 'Treatment', options: [
        { value: 'milgrain',        label: 'Milgrain (bead row)' },
        { value: 'beading',         label: 'Beading' },
        { value: 'filigree',        label: 'Filigree wire-work' },
        { value: 'twisted_wire',    label: 'Twisted wire' },
        { value: 'scrollwork',      label: 'Scrollwork' },
        { value: 'surface_texture', label: 'Surface texture' },
      ] },
      { key: 'target_ref',      kind: 'feature_picker', label: 'Target edge / face' },
      { key: 'bead_diameter_mm',kind: 'number', label: 'Bead / unit dia. (mm)', min: 0.1, step: 0.05 },
      { key: 'pitch_mm',        kind: 'number', label: 'Pitch / spacing (mm)',  min: 0.05, step: 0.05 },
      { key: 'offset_mm',       kind: 'number', label: 'Edge offset (mm)',      min: -5, max: 5, step: 0.05 },
    ],
  },

  // T-1 Sheet metal — folded flange primitive.
  // Unfold (T-2), flat-pattern (T-3), and bend table (T-4) are follow-ups.
  {
    op: 'sheet_metal_flange',
    label: 'Sheet Flange',
    icon: Layers,
    defaults: {
      base_width: 100,
      base_depth: 80,
      thickness: 1.5,
      edge_ref: 'top-front',
      flange_length: 25,
      bend_angle_deg: 90,
      bend_radius: 2,
      k_factor: 0.44,
    },
    caption: (
      'Folded sheet-metal flange: base plate + bent wall along a chosen top edge. ' +
      'k_factor (0 < k < 1) stores the neutral-axis offset for unfold (T-2, not yet shipped). ' +
      'Edge ref: top-front | top-back | top-left | top-right.'
    ),
    fields: [
      { key: 'base_width',      kind: 'number',  label: 'Base width (mm)',        min: 0.1, step: 1 },
      { key: 'base_depth',      kind: 'number',  label: 'Base depth (mm)',         min: 0.1, step: 1 },
      { key: 'thickness',       kind: 'number',  label: 'Sheet thickness (mm)',    min: 0.1, step: 0.1 },
      { key: 'edge_ref',        kind: 'select',  label: 'Fold edge', options: [
        { value: 'top-front',  label: 'Top front' },
        { value: 'top-back',   label: 'Top back' },
        { value: 'top-left',   label: 'Top left' },
        { value: 'top-right',  label: 'Top right' },
      ] },
      { key: 'flange_length',   kind: 'number',  label: 'Flange length (mm)',      min: 0.1, step: 1 },
      { key: 'bend_angle_deg',  kind: 'number',  label: 'Bend angle (°)',          min: 0.1, max: 180, step: 1 },
      { key: 'bend_radius',     kind: 'number',  label: 'Inside bend radius (mm)', min: 0,   step: 0.5 },
      { key: 'k_factor',        kind: 'number',  label: 'K-factor (0–1)',          min: 0.01, max: 0.99, step: 0.01 },
    ],
  },

  // ── GK-P45: SubD/mesh authoring ops ────────────────────────────────────────

  // subd_poke — centroid fan on a SubD cage face (GK-P20)
  {
    op: 'subd_poke',
    label: 'SubD Poke',
    icon: GitBranch,
    caption: 'Poke a SubD cage face: insert a centroid vertex and fan the n-gon into n triangles.',
    defaults: { target_id: '', face_id: 0 },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'SubD cage' },
      { key: 'face_id',   kind: 'number',          label: 'Face index', min: 0, step: 1 },
    ],
  },

  // subd_extrude_along — extrude SubD face along polyline (GK-P21)
  {
    op: 'subd_extrude_along',
    label: 'SubD Extrude Along',
    icon: Layers,
    caption: 'Sweep a SubD cage face along a polyline spine. Side walls become quad faces.',
    defaults: { target_id: '', face_id: 0, curve_pts: [[0,0,0],[0,0,10]] },
    fields: [
      { key: 'target_id',  kind: 'feature_picker', label: 'SubD cage' },
      { key: 'face_id',    kind: 'number',          label: 'Face index', min: 0, step: 1 },
    ],
  },

  // sculpt_brush — sculpt-brush stroke (grab/smooth/inflate) (GK-P27)
  {
    op: 'sculpt_brush',
    label: 'Sculpt Brush',
    icon: Move,
    caption: 'Apply a sculpt-brush stroke to a SubD cage. Grab, smooth, or inflate vertices within the brush radius.',
    defaults: {
      target_id: '',
      center: [0, 0, 0],
      radius: 5.0,
      falloff: 2.0,
      strength: 0.5,
      mode: 'grab',
      direction: [0, 0, 1],
    },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'SubD cage' },
      { key: 'center[0]', kind: 'number', label: 'Brush centre X (mm)' },
      { key: 'center[1]', kind: 'number', label: 'Brush centre Y (mm)' },
      { key: 'center[2]', kind: 'number', label: 'Brush centre Z (mm)' },
      { key: 'radius',    kind: 'number', label: 'Radius (mm)', min: 0.001 },
      { key: 'falloff',   kind: 'number', label: 'Falloff exponent', min: 0.5, max: 8, step: 0.1 },
      { key: 'strength',  kind: 'number', label: 'Strength', min: 0, max: 1, step: 0.05 },
      { key: 'mode', kind: 'select', label: 'Mode', options: [
        { value: 'grab',    label: 'Grab (translate)' },
        { value: 'smooth',  label: 'Smooth (laplacian)' },
        { value: 'inflate', label: 'Inflate (along normal)' },
      ] },
      { key: 'direction[0]', kind: 'number', label: 'Grab dir X', showWhen: (n) => n.mode === 'grab' },
      { key: 'direction[1]', kind: 'number', label: 'Grab dir Y', showWhen: (n) => n.mode === 'grab' },
      { key: 'direction[2]', kind: 'number', label: 'Grab dir Z', showWhen: (n) => n.mode === 'grab' },
    ],
  },

  // multires_evaluate — MultiresStack evaluate + serialise (GK-P26)
  {
    op: 'multires_evaluate',
    label: 'MultiRes Evaluate',
    icon: Layers3,
    caption: 'Evaluate a MultiresStack at a subdivision level, applying per-vertex displacement maps for sculpting.',
    defaults: { target_id: '', level: 2, max_levels: 2, displacements: {} },
    fields: [
      { key: 'target_id',   kind: 'feature_picker', label: 'Base SubD cage' },
      { key: 'level',       kind: 'number', label: 'Evaluate at level', min: 0, max: 6, step: 1 },
      { key: 'max_levels',  kind: 'number', label: 'Max levels in stack', min: 1, max: 6, step: 1 },
    ],
  },

  // ── GK-P46: mesh/implicit ops ───────────────────────────────────────────────

  // sdf_csg — SDF CSG + marching cubes (GK-P22)
  {
    op: 'sdf_csg',
    label: 'SDF CSG',
    icon: Combine,
    caption: 'Compose SDF primitives (sphere/box/cylinder) with CSG operators and extract a triangulated mesh via marching cubes.',
    defaults: {
      primitives: [{ type: 'sphere', id: 'a', cx: 0, cy: 0, cz: 0, r: 5 }],
      operations: [],
      bounds: [-10, -10, -10, 10, 10, 10],
      resolution: 32,
      isovalue: 0.0,
    },
    fields: [
      { key: 'resolution', kind: 'number', label: 'Resolution (per axis)', min: 4, max: 128, step: 4 },
      { key: 'isovalue',   kind: 'number', label: 'Iso-value', step: 0.01 },
    ],
  },

  // uv_unwrap — LSCM UV unwrap (GK-P24)
  {
    op: 'uv_unwrap',
    label: 'UV Unwrap',
    icon: LayoutGrid,
    caption: 'LSCM UV unwrap — computes a low-distortion (conformal) UV parametrization for a triangle mesh or SubD cage.',
    defaults: { target_id: '', fixed_pins: [] },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Mesh / SubD cage' },
    ],
  },

  // isotropic_remesh — Botsch-Kobbelt isotropic remesh (GK-P23)
  {
    op: 'isotropic_remesh',
    label: 'Isotropic Remesh',
    icon: Grid3x3,
    caption: 'Botsch-Kobbelt isotropic remesh: split, collapse, flip, and smooth toward a uniform target edge length.',
    defaults: { target_id: '', target_edge_length: 1.0, iterations: 5 },
    fields: [
      { key: 'target_id',          kind: 'feature_picker', label: 'Mesh / SubD cage' },
      { key: 'target_edge_length', kind: 'number',         label: 'Target edge length (mm)', min: 0.001 },
      { key: 'iterations',         kind: 'number',         label: 'Iterations', min: 1, max: 20, step: 1 },
    ],
  },

  // retopo_snap — snap retopo cage to reference mesh (GK-P25)
  {
    op: 'retopo_snap',
    label: 'Retopo Snap',
    icon: Crosshair,
    caption: 'Snap a retopo cage to the nearest-point surface of a reference mesh. Draw a coarse cage then snap it to conform.',
    defaults: { retopo_cage_id: '', source_mesh_id: '' },
    fields: [
      { key: 'retopo_cage_id',  kind: 'feature_picker', label: 'Retopo cage' },
      { key: 'source_mesh_id', kind: 'feature_picker', label: 'Reference mesh / scan' },
    ],
  },

  // ── GK-P47: surfacing additions ─────────────────────────────────────────────

  // isophote_analysis — read-only isophote continuity analyser (GK-P11)
  {
    op: 'isophote_analysis',
    label: 'Isophote Analysis',
    icon: Aperture,
    caption: (
      'Read-only isophote / environment-map continuity analysis. ' +
      'Detects G1 (tangent) discontinuities as isophote breaks. ' +
      'Does NOT append a geometry node — analysis only.'
    ),
    defaults: { target_id: '', uv_grid: [48, 48], sphere_map_res: 16, light_dir: [0, 0, 1] },
    fields: [
      { key: 'target_id',      kind: 'feature_picker', label: 'NURBS surface node' },
      { key: 'uv_grid[0]',     kind: 'number', label: 'UV grid U', min: 3, max: 200, step: 1 },
      { key: 'uv_grid[1]',     kind: 'number', label: 'UV grid V', min: 3, max: 200, step: 1 },
      { key: 'sphere_map_res', kind: 'number', label: 'Sphere-map bands', min: 2, max: 64, step: 1 },
      { key: 'light_dir[0]',   kind: 'number', label: 'Light dir X', step: 0.1 },
      { key: 'light_dir[1]',   kind: 'number', label: 'Light dir Y', step: 0.1 },
      { key: 'light_dir[2]',   kind: 'number', label: 'Light dir Z', step: 0.1 },
    ],
  },

  // ── GK-P48: construction verbs ──────────────────────────────────────────────

  // hem_sheet — 180° hem fold (GK-P17)
  {
    op: 'hem_sheet',
    label: 'Hem Sheet',
    icon: Layers,
    caption: '180° hem fold on a bent sheet-metal body (closed/open/teardrop). Stiffens edges and removes raw-cut burrs.',
    defaults: { target_id: '', style: 'closed', gap: 0, k_factor: 0.44 },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Bent sheet body' },
      { key: 'style', kind: 'select', label: 'Hem style', options: [
        { value: 'closed',   label: 'Closed (flat, gap=0)' },
        { value: 'open',     label: 'Open (gap > 0)' },
        { value: 'teardrop', label: 'Teardrop' },
      ] },
      { key: 'gap',      kind: 'number', label: 'Gap (mm)', min: 0, step: 0.1, showWhen: (n) => n.style !== 'closed' },
      { key: 'radius',   kind: 'number', label: 'Hem radius (mm)', min: 0.001, step: 0.1 },
      { key: 'k_factor', kind: 'number', label: 'K-factor', min: 0.01, max: 0.99, step: 0.01 },
    ],
  },

  // jog_sheet — Z-offset jog (GK-P17)
  {
    op: 'jog_sheet',
    label: 'Jog Sheet',
    icon: SlidersHorizontal,
    caption: 'Z-offset jog (two opposing bends) on a sheet-metal body. Shifts one panel up/down while keeping both panels parallel.',
    defaults: { target_id: '', offset: 5.0, jog_angle_rad: 1.5708, radius: 1.0, k_factor: 0.44 },
    fields: [
      { key: 'target_id',     kind: 'feature_picker', label: 'Sheet-metal body' },
      { key: 'offset',        kind: 'number', label: 'Z offset (mm)' },
      { key: 'jog_angle_rad', kind: 'number', label: 'Jog angle (rad)', min: 0.01, max: 1.5708, step: 0.01 },
      { key: 'radius',        kind: 'number', label: 'Bend radius (mm)', min: 0.001, step: 0.1 },
      { key: 'k_factor',      kind: 'number', label: 'K-factor', min: 0.01, max: 0.99, step: 0.01 },
    ],
  },

  // multi_flange — sequence of bends (GK-P17)
  {
    op: 'multi_flange',
    label: 'Multi-Flange',
    icon: Repeat,
    caption: 'Apply a sequence of sheet-metal bends in one call. Each bend spec provides bend_line, angle_rad, and radius.',
    defaults: {
      target_id: '',
      bend_specs: [{ bend_line: 20, angle_rad: 1.5708, radius: 1.0, k_factor: 0.4 }],
    },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Sheet-metal body' },
    ],
  },

  // delete_face — remove a face (GK-P18)
  {
    op: 'delete_face',
    label: 'Delete Face',
    icon: Trash2,
    caption: 'Remove a face from a body and heal the result. For planar bodies this always produces a closed solid.',
    defaults: { target_id: '', face_id: 0, heal: true },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Body' },
      { key: 'face_id',   kind: 'number',          label: 'Face index', min: 0, step: 1 },
      { key: 'heal',      kind: 'boolean',          label: 'Attempt heal' },
    ],
  },

  // push_pull — push/pull non-planar face (GK-P18)
  // Note: the existing 'push_pull' op in 'modify' category is the basic version;
  // this one is tagged as a first-class feature node with target_id + face_id.
  {
    op: 'push_pull',
    label: 'Push/Pull Face',
    icon: Move,
    caption: 'Offset a face along its outward normal. Positive = outward (add material), negative = inward (remove). Supports non-planar faces (GK-P18).',
    defaults: { target_id: '', face_id: 0, distance: 5.0 },
    fields: [
      { key: 'target_id', kind: 'feature_picker', label: 'Body' },
      { key: 'face_id',   kind: 'number',          label: 'Face index', min: 0, step: 1 },
      { key: 'distance',  kind: 'number',           label: 'Distance (mm)', step: 0.5 },
    ],
  },

  // gusset_plate — weldment gusset (GK-P19)
  {
    op: 'gusset_plate',
    label: 'Gusset Plate',
    icon: GitBranch,
    caption: 'Insert a gusset-plate stiffener at a weldment joint vertex (triangle / rect / trapezoidal).',
    defaults: {
      target_id: '',
      vertex_pos: [0, 0, 0],
      thickness_mm: 6,
      width_mm: 100,
      height_mm: 100,
      shape: 'triangle',
      fillet_mm: 0,
      material: 'steel',
    },
    fields: [
      { key: 'target_id',    kind: 'feature_picker', label: 'Weldment frame' },
      { key: 'vertex_pos[0]', kind: 'number', label: 'Vertex X (mm)' },
      { key: 'vertex_pos[1]', kind: 'number', label: 'Vertex Y (mm)' },
      { key: 'vertex_pos[2]', kind: 'number', label: 'Vertex Z (mm)' },
      { key: 'thickness_mm', kind: 'number', label: 'Plate thickness (mm)', min: 0.1, step: 1 },
      { key: 'width_mm',     kind: 'number', label: 'Width (mm)', min: 0.1, step: 5 },
      { key: 'height_mm',    kind: 'number', label: 'Height (mm)', min: 0.1, step: 5 },
      { key: 'shape', kind: 'select', label: 'Shape', options: [
        { value: 'triangle',    label: 'Triangle (right-triangle)' },
        { value: 'rect',        label: 'Rectangle' },
        { value: 'trapezoidal', label: 'Trapezoidal' },
      ] },
      { key: 'fillet_mm', kind: 'number', label: 'Corner fillet (mm)', min: 0, step: 1 },
    ],
  },

  // cope_notch — weldment cope / notch end-treatment (GK-P19)
  {
    op: 'cope_notch',
    label: 'Cope / Notch',
    icon: Scissors,
    caption: 'Cope or notch end-treatment on a weldment member end. Cope = cut for passing member; notch = V/square corner cut.',
    defaults: {
      target_id: '',
      member_index: 0,
      end: 'start',
      cope_style: 'none',
      cope_depth_mm: 0,
      cope_width_mm: 0,
      notch_style: 'none',
      notch_depth_mm: 0,
      notch_width_mm: 0,
      notch_angle_deg: 45,
    },
    fields: [
      { key: 'target_id',    kind: 'feature_picker', label: 'Weldment frame' },
      { key: 'member_index', kind: 'number', label: 'Member index', min: 0, step: 1 },
      { key: 'end', kind: 'select', label: 'End', options: [
        { value: 'start', label: 'Start end' },
        { value: 'end',   label: 'End end' },
      ] },
      { key: 'cope_style', kind: 'select', label: 'Cope style', options: [
        { value: 'none',   label: 'None' },
        { value: 'square', label: 'Square' },
        { value: 'radius', label: 'Radius (radiused corner)' },
      ] },
      { key: 'cope_depth_mm',  kind: 'number', label: 'Cope depth (mm)', min: 0, step: 1, showWhen: (n) => n.cope_style !== 'none' },
      { key: 'cope_width_mm',  kind: 'number', label: 'Cope width (mm)', min: 0, step: 1, showWhen: (n) => n.cope_style !== 'none' },
      { key: 'cope_radius_mm', kind: 'number', label: 'Cope radius (mm)', min: 0, step: 0.5, showWhen: (n) => n.cope_style === 'radius' },
      { key: 'notch_style', kind: 'select', label: 'Notch style', options: [
        { value: 'none',   label: 'None' },
        { value: 'square', label: 'Square' },
        { value: 'angle',  label: 'V-notch' },
      ] },
      { key: 'notch_depth_mm', kind: 'number', label: 'Notch depth (mm)', min: 0, step: 1, showWhen: (n) => n.notch_style !== 'none' },
      { key: 'notch_width_mm', kind: 'number', label: 'Notch width (mm)', min: 0, step: 1, showWhen: (n) => n.notch_style !== 'none' },
      { key: 'notch_angle_deg', kind: 'number', label: 'V-notch angle (°)', min: 5, max: 170, step: 5, showWhen: (n) => n.notch_style === 'angle' },
    ],
  },

  // ── Construction helpers ──────────────────────────────────────────────────

  // rib — parametric reinforcement rib wall (feature_rib, kerf-imports)
  {
    op: 'rib',
    label: 'Rib',
    icon: AlignLeft,
    caption: (
      'Parametric reinforcement rib wall. Offsets a closed sketch profile and sweeps ' +
      'it into a solid wall for mold release or structural reinforcement. ' +
      'both_sides extrudes symmetrically; midplane centres on sketch plane.'
    ),
    defaults: {
      sketch_path: '',
      thickness_mm: 3.0,
      both_sides: false,
      midplane: false,
      draft_angle_deg: 0,
    },
    fields: [
      { key: 'sketch_path',     kind: 'sketch_picker', label: 'Closed profile sketch' },
      { key: 'thickness_mm',    kind: 'number', label: 'Wall thickness (mm)', min: 0.1, step: 0.5 },
      { key: 'both_sides',      kind: 'boolean', label: 'Both sides (symmetric extrude)' },
      { key: 'midplane',        kind: 'boolean', label: 'Midplane (centred on sketch)', showWhen: (n) => !n.both_sides },
      { key: 'draft_angle_deg', kind: 'number', label: 'Draft angle (°)', min: 0, max: 30, step: 0.5 },
    ],
  },

  // helix — parametric helix curve node (feature_helix, kerf-imports)
  {
    op: 'helix',
    label: 'Helix',
    icon: Activity,
    caption: (
      'Parametric helix / coil curve. Returns a polyline tracing a cylindrical or ' +
      'conical helix. Use as path_sketch for Sweep1 to produce springs, threads, ' +
      'or coiled tubing. direction: right (CCW, standard) / left (CW).'
    ),
    defaults: {
      pitch: 5.0,
      height: 30.0,
      radius: 10.0,
      direction: 'right',
      cone_angle: 0,
      segments: 64,
    },
    fields: [
      { key: 'pitch',       kind: 'number', label: 'Pitch — axial/turn (mm)', min: 0.01, step: 0.5 },
      { key: 'height',      kind: 'number', label: 'Total height (mm)',        min: 0.01, step: 1 },
      { key: 'radius',      kind: 'number', label: 'Base radius (mm)',          min: 0.01, step: 0.5 },
      { key: 'direction', kind: 'select', label: 'Handedness', options: [
        { value: 'right', label: 'Right-hand (CCW from above)' },
        { value: 'left',  label: 'Left-hand (CW from above)' },
      ] },
      { key: 'cone_angle',  kind: 'number', label: 'Cone half-angle (°, 0=cylindrical)', min: 0, max: 89, step: 0.5 },
      { key: 'segments',    kind: 'number', label: 'Segments / turn',  min: 8, max: 256, step: 8 },
    ],
  },

  // multi_transform — composited pattern (linear × polar × mirror) (kerf-imports)
  {
    op: 'multi_transform',
    label: 'Multi-Transform',
    icon: Repeat,
    caption: (
      'Compose up to 4 pattern operations (linear, polar, mirror) on one feature. ' +
      'Transforms are applied in order; the result is the Cartesian product of all instances. ' +
      'Useful for bolt circles combined with a mirror, or a polar array of a ribbed pattern.'
    ),
    defaults: {
      source_feature_id: '',
      transforms: [
        { kind: 'linear', direction: 'x', count: 3, spacing: 10 },
      ],
    },
    fields: [
      { key: 'source_feature_id', kind: 'feature_picker', label: 'Source feature' },
      // transforms is a complex nested list; LLM drives via JSON; inspector shows count only
    ],
  },

  // ── Surface quality analysis (read-only analysis nodes) ─────────────────

  // zebra_analysis — G0/G1/G2 stripe-break analysis (surfacing.py GK-38)
  {
    op: 'zebra_analysis',
    label: 'Zebra Analysis',
    icon: Eye,
    caption: (
      'Read-only zebra / reflection-line continuity analysis on the shared edge between ' +
      'two NURBS surfaces. Returns G0/G1/G2 stripe-break flags and reflection-line data. ' +
      'Use after blend_srf or blend_srf_g3 to verify join quality. Does NOT modify geometry.'
    ),
    defaults: {
      surface_a_ref: '',
      surface_b_ref: '',
      shared_edge_pts: [[0,0,0],[1,0,0]],
      num_samples: 32,
      stripe_width: 0.05,
    },
    fields: [
      { key: 'surface_a_ref',  kind: 'feature_picker', label: 'Surface A' },
      { key: 'surface_b_ref',  kind: 'feature_picker', label: 'Surface B' },
      { key: 'num_samples',    kind: 'number', label: 'Sample count', min: 4, max: 256, step: 4 },
      { key: 'stripe_width',   kind: 'number', label: 'Stripe width (fraction)', min: 0.01, max: 0.5, step: 0.01 },
    ],
  },

  // class_a_check — Class-A acceptance harness (surfacing.py GK-64)
  {
    op: 'class_a_check',
    label: 'Class-A Check',
    icon: Shield,
    caption: (
      'Class-A acceptance harness on the shared edge between two NURBS surfaces. ' +
      'Runs three passes: (1) curvature combs, (2) zebra/reflection-line, ' +
      '(3) G0/G1/G2/G3 gate. Optionally runs leading hot-spot detection on each surface. ' +
      'Read-only analysis node — does not modify geometry.'
    ),
    defaults: {
      surface_a_ref: '',
      surface_b_ref: '',
      shared_edge_pts: [[0,0,0],[1,0,0]],
      target_grade: 'G2',
      run_leading: false,
    },
    fields: [
      { key: 'surface_a_ref',  kind: 'feature_picker', label: 'Surface A' },
      { key: 'surface_b_ref',  kind: 'feature_picker', label: 'Surface B' },
      { key: 'target_grade', kind: 'select', label: 'Target grade', options: [
        { value: 'G0', label: 'G0 (positional)' },
        { value: 'G1', label: 'G1 (tangent)' },
        { value: 'G2', label: 'G2 (curvature)' },
        { value: 'G3', label: 'G3 (curvature-rate)' },
      ] },
      { key: 'run_leading', kind: 'boolean', label: 'Run leading hot-spot detection' },
    ],
  },

  // global_continuity_audit — walk every shared edge in a body (surfacing.py GK-138)
  {
    op: 'global_continuity_audit',
    label: 'Global Continuity Audit',
    icon: Shield,
    caption: (
      'Walk every shared edge in a feature body and classify each as G0/G1/G2/G3 or ' +
      'below_G0 for positional gaps. Returns a per-edge continuity report + summary ' +
      'count by grade. Read-only analysis node — does not modify geometry.'
    ),
    defaults: { target_id: '', tolerance: 1e-4 },
    fields: [
      { key: 'target_id',  kind: 'feature_picker', label: 'Surface body to audit' },
      { key: 'tolerance',  kind: 'number', label: 'Positional tolerance (mm)', min: 1e-9, step: 1e-4 },
    ],
  },

  // blend_srf_g3 — G3 degree-7 Bézier blend strip (surfacing.py GK-62)
  {
    op: 'blend_srf_g3',
    label: 'BlendSrf G3',
    icon: Waves,
    caption: (
      'G3 (curvature-rate-continuous) degree-7 Bézier blend strip between two NURBS surfaces. ' +
      'Highest analytic continuity class (G3); required for automotive Class-A and fine jewellery. ' +
      'Set trim_and_sew=true to also trim support surfaces and sew all three into a closed Body.'
    ),
    defaults: {
      target_id: '',
      edge1_id: -1,
      edge2_id: -1,
      blend_dist: 2.0,
      samples: 24,
      trim_and_sew: false,
    },
    fields: [
      { key: 'target_id',    kind: 'feature_picker', label: 'Host body' },
      { key: 'edge1_id',     kind: 'number', label: 'Edge 1 id', step: 1 },
      { key: 'edge2_id',     kind: 'number', label: 'Edge 2 id', step: 1 },
      { key: 'blend_dist',   kind: 'number', label: 'Blend distance (mm)', min: 0.001 },
      { key: 'samples',      kind: 'number', label: 'Seam sample count', min: 8, max: 128, step: 4 },
      { key: 'trim_and_sew', kind: 'boolean', label: 'Trim + sew into closed Body' },
    ],
  },

  // g3_chain_blend — multi-edge G3 chain blend (surfacing.py GK-P50)
  {
    op: 'g3_chain_blend',
    label: 'G3 Chain Blend',
    icon: Waves,
    caption: (
      'Multi-edge G3 chain blend: propagates a G3 continuity constraint along a ' +
      'chain of surface edges. Produces a single blend strip covering all edges in the chain.'
    ),
    defaults: {
      target_id: '',
      edge_chain: [],
      blend_dist: 2.0,
      samples: 24,
    },
    fields: [
      { key: 'target_id',  kind: 'feature_picker', label: 'Host body' },
      { key: 'blend_dist', kind: 'number', label: 'Blend distance (mm)', min: 0.001 },
      { key: 'samples',    kind: 'number', label: 'Sample count', min: 8, max: 256, step: 4 },
    ],
  },

  // fit_surface — fit NURBS surface to point cloud or mesh (surfacing.py)
  {
    op: 'fit_surface',
    label: 'Fit Surface',
    icon: Zap,
    caption: (
      'Fit a NURBS surface to a point cloud, mesh, or scan data. ' +
      'degree_u/v controls the polynomial degree; u_knots/v_knots controls knot count. ' +
      'Useful for reverse-engineering scanned geometry.'
    ),
    defaults: {
      source_ref: '',
      degree_u: 3,
      degree_v: 3,
      u_knots: 8,
      v_knots: 8,
      tolerance: 0.01,
    },
    fields: [
      { key: 'source_ref', kind: 'feature_picker', label: 'Source mesh / point cloud' },
      { key: 'degree_u',   kind: 'number', label: 'Degree U', min: 1, max: 9, step: 1 },
      { key: 'degree_v',   kind: 'number', label: 'Degree V', min: 1, max: 9, step: 1 },
      { key: 'u_knots',    kind: 'number', label: 'U knot count', min: 2, max: 50, step: 1 },
      { key: 'v_knots',    kind: 'number', label: 'V knot count', min: 2, max: 50, step: 1 },
      { key: 'tolerance',  kind: 'number', label: 'Fit tolerance (mm)', min: 1e-6, step: 0.001 },
    ],
  },
]

const KIND_BY_OP = Object.fromEntries(FEATURE_KINDS.map((k) => [k.op, k]))

// Named exports for unit tests and external consumers.
export { FEATURE_KINDS, FEATURE_CATEGORIES }

const FEATURE_CATEGORIES = [
  { id: 'sketch',   label: 'Sketch-based',  ops: ['pad', 'boss_with_draft', 'pocket', 'cut_from_sketch', 'revolve', 'hole', 'hole_pattern', 'rib', 'helix'] },
  { id: 'modify',   label: 'Modify',        ops: ['fillet', 'chamfer', 'shell', 'push_pull', 'variable_radius_fillet', 'to_solid', 'boolean', 'section', 'quad_remesh', 'delete_face', 'isotropic_remesh'] },
  { id: 'pattern',  label: 'Pattern',       ops: ['linear_pattern', 'polar_pattern', 'mirror_pattern', 'multi_transform'] },
  { id: 'surface',  label: 'Surfacing',     ops: ['sweep1', 'sweep2', 'loft', 'network_srf', 'blend_srf', 'blend_srf_g3', 'g3_chain_blend', 'fit_surface', 'surface_boolean', 'trim_by_curve', 'surface_curvature_combs', 'isophote_analysis', 'uv_unwrap'] },
  { id: 'analysis', label: 'Analysis',      ops: ['zebra_analysis', 'class_a_check', 'global_continuity_audit'] },
  { id: 'jewelry',  label: 'Jewelry',       ops: [
    // Gemstones
    'gemstone',
    // Settings v1–v4
    'jewelry_prong_head', 'jewelry_bezel', 'jewelry_channel', 'jewelry_pave',
    'jewelry_tension', 'jewelry_flush', 'jewelry_halo', 'jewelry_three_stone',
    'jewelry_cluster', 'jewelry_bar', 'jewelry_bead_grain', 'jewelry_gypsy_pave',
    'jewelry_illusion', 'jewelry_invisible',
    'jewelry_prong_variant', 'jewelry_head_gallery', 'jewelry_under_bezel',
    'jewelry_peg_setting', 'jewelry_coronet', 'jewelry_suspension_mount',
    'jewelry_vtip_protector', 'jewelry_bombe_cluster', 'jewelry_patterned_bezel',
    'jewelry_trellis_prong', 'jewelry_bar_channel_graduated',
    // Gem seat types
    'gem_seat', 'channel_seat', 'bezel_seat', 'fishtail_seat',
    // Ring ops
    'ring_shank', 'eternity_band', 'signet_ring', 'stacking_band_set',
    'contoured_band', 'solitaire_ring', 'mens_band', 'wedding_set',
    'cocktail_ring', 'bypass_ring',
    // Chain + composed pieces
    'chain_assembly', 'tennis_bracelet', 'station_necklace', 'lariat',
    'charm_bracelet', 'multi_strand', 'extender_chain',
    // Findings
    'finding',
    // Whole pieces
    'pendant', 'earrings', 'brooch', 'cufflink', 'bangle',
    // Decorative
    'decorative_apply',
  ] },
  { id: 'sheetmetal', label: 'Sheet Metal', ops: ['sheet_metal_flange', 'hem_sheet', 'jog_sheet', 'multi_flange'] },
  { id: 'subd',      label: 'SubD / Mesh',  ops: ['subd_poke', 'subd_extrude_along', 'sculpt_brush', 'multires_evaluate', 'sdf_csg', 'retopo_snap'] },
  { id: 'weldment',  label: 'Weldment',     ops: ['gusset_plate', 'cope_notch'] },
]

const DEBOUNCE_MS = 300

// Click-outside + Escape dismiss for popovers. Mirrors the pattern in
// ChatPanel.jsx so behaviour is consistent across the app.
function useClickOutside(ref, onOutside, enabled) {
  useEffect(() => {
    if (!enabled) return
    function handle(e) {
      if (ref.current && !ref.current.contains(e.target)) onOutside()
    }
    function escListener(e) { if (e.key === 'Escape') onOutside() }
    document.addEventListener('mousedown', handle)
    document.addEventListener('keydown', escListener)
    return () => {
      document.removeEventListener('mousedown', handle)
      document.removeEventListener('keydown', escListener)
    }
  }, [ref, onOutside, enabled])
}


// Long-press hook for touch devices. Returns pointer-event handlers that
// fire `onLongPress` after `delay` ms of continuous contact. Cancels on
// move or early release.
function useLongPress(onLongPress, delay = 500) {
  const timerRef = useRef(null)
  const cancel = useCallback(() => {
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null }
  }, [])
  const onPointerDown = useCallback((e) => {
    if (e.pointerType !== 'touch') return
    timerRef.current = setTimeout(() => { onLongPress(e) }, delay)
  }, [onLongPress, delay])
  const onPointerUp = cancel
  const onPointerCancel = cancel
  const onPointerMove = cancel
  useEffect(() => cancel, [cancel])
  return { onPointerDown, onPointerUp, onPointerCancel, onPointerMove }
}
// ---------------------------------------------------------------------------
// Component.

export default function FeatureView({
  parsedFeature,            // current FeatureTree (from store.currentFeature)
  files,                    // file rows for the project (sketch picker)
  onChangeTree,             // (nextTree) => void
  loadSketchContent,        // (path: string) => Promise<string>; returns sketch JSON
}) {
  const tree = parsedFeature?.features || []
  const fileName = parsedFeature?.name || 'Feature'
  const currentFile = useWorkspace((s) => s.currentFile)
  const currentFileId = useWorkspace((s) => s.currentFileId)

  // Selection / pick mode lives in the workspace store so other UI (chat,
  // future tools) can read it. We wire two-way binding here.
  const featureSelection = useWorkspace((s) => s.featureSelection)
  const featurePickMode = useWorkspace((s) => s.featurePickMode)
  const featurePickTarget = useWorkspace((s) => s.featurePickTarget)
  const setFeatureSelection = useWorkspace((s) => s.setFeatureSelection)
  const setFeaturePickMode = useWorkspace((s) => s.setFeaturePickMode)
  const clearFeatureSelection = useWorkspace((s) => s.clearFeatureSelection)
  const createSketchOnFace = useWorkspace((s) => s.createSketchOnFace)
  const selectFile = useWorkspace((s) => s.selectFile)

  // Inspector drawer open state — on narrow viewports (< md) the inspector
  // slides in as an overlay; on ≥ md it is always visible as the right pane.
  const [inspectorOpen, setInspectorOpen] = useState(false)

  // Selected feature in the timeline (by id).
  const [selectedId, setSelectedId] = useState(null)
  useEffect(() => {
    if (!selectedId && tree.length > 0) setSelectedId(tree[tree.length - 1]?.id)
  }, [tree, selectedId])

  // Roving-tabindex index for the feature timeline (keyboard nav).
  // Points to the chip that currently owns tabIndex=0. Defaults to the last
  // chip (same as selectedId initialisation above). Clamped on tree change.
  const [rovingIdx, setRovingIdx] = useState(0)
  useEffect(() => {
    if (tree.length === 0) return
    setRovingIdx((prev) => Math.min(prev, tree.length - 1))
  }, [tree.length])

  // Ref to the timeline container so we can focus individual chips.
  const timelineRef = useRef(null)

  const handleTimelineKeyDown = useCallback((e) => {
    if (tree.length === 0) return
    let next = rovingIdx
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault()
      next = Math.min(rovingIdx + 1, tree.length - 1)
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault()
      next = Math.max(rovingIdx - 1, 0)
    } else if (e.key === 'Home') {
      e.preventDefault()
      next = 0
    } else if (e.key === 'End') {
      e.preventDefault()
      next = tree.length - 1
    } else {
      return
    }
    setRovingIdx(next)
    // Move DOM focus to the newly-roving chip button.
    const chipBtns = timelineRef.current?.querySelectorAll('[data-chip-btn]')
    if (chipBtns?.[next]) chipBtns[next].focus()
  }, [rovingIdx, tree.length])

  // Cached evaluation results — survive across debounced re-runs so a brief
  // error doesn't wipe the viewport.
  const [meshes, setMeshes] = useState([])
  const [evalState, setEvalState] = useState({ loading: false, error: null, ms: null })
  const lastGoodMeshesRef = useRef([])

  const sketchCacheRef = useRef(new Map())
  useEffect(() => { sketchCacheRef.current = new Map() }, [files])

  // Track the structural fingerprint of the tree (op kinds + ids in order) so
  // we can clear selection only when topology actually changes — pure
  // parameter tweaks (e.g. tweaking a height) preserve face/edge ids and
  // keep selections valid.
  const lastStructuralKeyRef = useRef('')
  useEffect(() => {
    const key = tree.map((n) => `${n.op}:${n.id}`).join('|')
    if (key !== lastStructuralKeyRef.current) {
      if (lastStructuralKeyRef.current !== '') {
        // Avoid clearing on the very first render — only on subsequent edits.
        clearFeatureSelection()
      }
      lastStructuralKeyRef.current = key
    }
  }, [tree, clearFeatureSelection])

  // Debounced re-evaluation pipeline.
  const debounceRef = useRef(null)
  const seqRef = useRef(0)

  const triggerEvaluate = useCallback(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    const seq = ++seqRef.current
    debounceRef.current = setTimeout(async () => {
      const referenced = new Set()
      for (const node of tree) {
        if (node.sketch_path) referenced.add(node.sketch_path)
      }
      const sketches = {}
      for (const path of referenced) {
        try {
          if (sketchCacheRef.current.has(path)) {
            sketches[path] = sketchCacheRef.current.get(path)
            continue
          }
          const content = loadSketchContent
            ? await loadSketchContent(path)
            : null
          sketches[path] = content || ''
          sketchCacheRef.current.set(path, content || '')
        } catch (err) {
          sketches[path] = ''
        }
      }
      // For face-anchored sketches whose anchor is on the *current* feature
      // file, resolve the face's world frame before dispatch. We need a
      // partial evaluation up to the anchor feature node — the worker's
      // requestFaceOutline does that for us.
      for (const path of Object.keys(sketches)) {
        try {
          const obj = sketches[path] ? JSON.parse(sketches[path]) : null
          const plane = obj?.plane
          if (plane?.type === 'face' && plane.face_id != null && (plane.file_id == null || plane.file_id === currentFileId)) {
            // Slice the tree up to (and including) the anchor feature node so
            // the face id resolves against the body that produced it. If
            // feature_node_id is missing we just use the whole tree.
            let sliced = tree
            if (plane.feature_node_id) {
              const idx = tree.findIndex((n) => n.id === plane.feature_node_id)
              if (idx >= 0) sliced = tree.slice(0, idx + 1)
            }
            const result = await requestFaceOutline(sliced, sketches, plane.face_id)
            if (result && result.ok && result.frame) {
              const baked = { ...obj, plane: { ...plane, frame: result.frame } }
              sketches[path] = JSON.stringify(baked)
            }
          }
        } catch { /* tolerate */ }
      }
      setEvalState((s) => ({ ...s, loading: true, error: null }))
      const t0 = performance.now()
      const result = await runFeatures(tree, sketches)
      const ms = Math.round(performance.now() - t0)
      if (seq !== seqRef.current) return
      if (result.stale) return
      if (result.error) {
        setEvalState({ loading: false, error: result.error, ms })
        if (result.partial) {
          const fallback = [{ id: 'partial', mesh: result.partial }]
          setMeshes(fallback)
        }
        return
      }
      const next = (result.meshes || []).map((m, i) => ({
        id: m.id || `body-${i}`,
        mesh: m,
      }))
      lastGoodMeshesRef.current = next
      setMeshes(next)
      setEvalState({ loading: false, error: null, ms })
    }, DEBOUNCE_MS)
  }, [tree, loadSketchContent])

  useEffect(() => { prewarmOcct() }, [])

  useEffect(() => {
    triggerEvaluate()
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [parsedFeature, triggerEvaluate])

  // ---- Tree mutations ----
  const updateTree = useCallback((mutator) => {
    const nextFeatures = mutator(tree)
    onChangeTree?.({
      ...parsedFeature,
      features: Array.isArray(nextFeatures) ? nextFeatures : [],
    })
  }, [tree, parsedFeature, onChangeTree])

  const addFeature = useCallback((op) => {
    const kind = KIND_BY_OP[op]
    if (!kind) return
    const id = newFeatureId(op)
    const node = { id, op, ...kind.defaults }
    if (['pocket', 'fillet', 'chamfer', 'shell', 'hole'].includes(op)) {
      const lastBody = [...tree].reverse().find((n) => n.op === 'pad' || n.op === 'revolve')
      if (lastBody) node.target_id = lastBody.id
    }
    updateTree((arr) => [...arr, node])
    setSelectedId(id)
  }, [tree, updateTree])

  const removeFeature = useCallback((id) => {
    updateTree((arr) => arr.filter((n) => n.id !== id))
    if (selectedId === id) setSelectedId(null)
  }, [updateTree, selectedId])

  const moveFeature = useCallback((id, dir) => {
    updateTree((arr) => {
      const idx = arr.findIndex((n) => n.id === id)
      if (idx < 0) return arr
      const j = dir === 'up' ? idx - 1 : idx + 1
      if (j < 0 || j >= arr.length) return arr
      const out = arr.slice()
      const tmp = out[idx]; out[idx] = out[j]; out[j] = tmp
      return out
    })
  }, [updateTree])

  const patchFeature = useCallback((id, patch) => {
    updateTree((arr) => arr.map((n) => n.id === id ? { ...n, ...patch } : n))
  }, [updateTree])

  // ---- Push/pull commit: append a push_pull feature node ----
  const onPushPullCommit = useCallback(({ partId, faceId, faceName, distance }) => {
    if (Math.abs(distance) < 0.05) return
    void partId
    const id = newFeatureId('push_pull')
    // T5: dual-write face_name (persistent) + face_id (legacy fallback).
    const node = { id, op: 'push_pull', face_id: faceId, distance }
    if (faceName) node.face_name = faceName
    updateTree((arr) => [...arr, node])
    setSelectedId(id)
    setFeaturePickMode(null)
  }, [updateTree, setFeaturePickMode])

  // ---- Sketch-on-face: handle a one-shot face pick that creates a sketch ----
  // T5: onFacePicked now receives { id, name, partId } from FeatureRenderer
  // (name is the persistent face name, id is the integer id).
  const onFacePicked = useCallback(async (pickArg, legacyPartId) => {
    // Support both legacy (faceId, partId) and new ({ id, name, partId }) shapes.
    let faceId, faceName, partId
    if (pickArg && typeof pickArg === 'object' && 'id' in pickArg) {
      faceId   = pickArg.id
      faceName = pickArg.name || ''
      partId   = pickArg.partId
    } else {
      faceId   = pickArg
      faceName = ''
      partId   = legacyPartId
    }
    void partId
    const mode = featurePickMode
    const target = featurePickTarget
    if (mode === 'sketch_on_face') {
      // Find the parent feature node that produced this body. v1 just uses
      // the latest pad/revolve as the anchor — multi-body trees aren't a v1
      // goal anyway.
      const anchor = [...tree].reverse().find((n) => n.op === 'pad' || n.op === 'revolve')
      const name = window.prompt('Sketch name', 'sketch-on-face.sketch')
      if (!name) {
        setFeaturePickMode(null)
        return
      }
      const created = await createSketchOnFace({
        parentId: currentFile?.parent_id || null,
        name: name.endsWith('.sketch') ? name : `${name}.sketch`,
        featureFileId: currentFileId,
        featureNodeId: anchor?.id || null,
        faceId,
      })
      setFeaturePickMode(null)
      if (created) await selectFile(created.id)
      return
    }
    if (mode === 'one_shot_face' && target) {
      // Fill the target field on the target feature with the picked face id.
      // T5: also dual-write the persistent name into a companion _name field
      // (e.g. target_face_id → target_face_name, face_id → face_name).
      if (target.accept === 'face_multi') {
        patchFeature(target.featureId, {
          [target.fieldKey]: Array.from(new Set([...(_arrayField(tree, target.featureId, target.fieldKey)), faceId])),
        })
      } else {
        const patch = { [target.fieldKey]: faceId }
        // Derive companion name key: target_face_id → target_face_name, face_id → face_name
        const nameKey = target.fieldKey.replace(/_id$/, '_name')
        if (faceName && nameKey !== target.fieldKey) patch[nameKey] = faceName
        patchFeature(target.featureId, patch)
      }
      setFeaturePickMode(null)
    }
    if (mode === 'one_shot_axis' || mode === 'one_shot_plane') {
      // Treat axis/plane picks: fill with the face id (numeric) for plane,
      // and reject for axis (the user should pick an edge for axis).
      if (mode === 'one_shot_plane' && target) {
        const patch = { [target.fieldKey]: faceId }
        // T6: dual-write plane_face_name when picking a face as the mirror plane.
        if (faceName && target.fieldKey === 'plane') patch.plane_face_name = faceName
        patchFeature(target.featureId, patch)
        setFeaturePickMode(null)
      }
    }
  }, [featurePickMode, featurePickTarget, tree, createSketchOnFace, currentFile, currentFileId, patchFeature, setFeaturePickMode, selectFile])

  // ---- Watch selection updates: if the active inspector has a one-shot pick
  // armed for an edge or edge_multi field, write the picked id back. ----
  useEffect(() => {
    if (!featurePickMode || !featurePickTarget) return
    if (featurePickMode === 'one_shot_edge') {
      // Take the most recently added edge id from the selection set.
      const list = Array.from(featureSelection.edgeIds || []).map((k) => Number(k.split('|')[1]))
      if (list.length === 0) return
      const newest = list[list.length - 1]
      const t = featurePickTarget
      if (t.accept === 'edge_multi') {
        patchFeature(t.featureId, (prev) => prev) // noop, we update via callback
        const nodeIdx = tree.findIndex((n) => n.id === t.featureId)
        if (nodeIdx >= 0) {
          const cur = tree[nodeIdx]
          const ids = Array.isArray(cur.edge_ids) ? cur.edge_ids : []
          if (!ids.includes(newest)) {
            patchFeature(t.featureId, { edge_ids: [...ids, newest], edge_filter: 'manual' })
          }
        }
      } else {
        patchFeature(t.featureId, { [t.fieldKey]: newest })
      }
      setFeaturePickMode(null)
    }
    if (featurePickMode === 'one_shot_axis') {
      const list = Array.from(featureSelection.edgeIds || []).map((k) => Number(k.split('|')[1]))
      if (list.length === 0) return
      const newest = list[list.length - 1]
      patchFeature(featurePickTarget.featureId, { [featurePickTarget.fieldKey]: newest })
      setFeaturePickMode(null)
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [featureSelection])

  // ---- Auto-sync selection → active feature's edge/face fields when in
  //      multi-pick (face / edge) mode. ----
  useEffect(() => {
    if (featurePickMode !== 'edge' && featurePickMode !== 'face') return
    const active = tree.find((n) => n.id === selectedId)
    if (!active) return
    if (featurePickMode === 'edge' && (active.op === 'fillet' || active.op === 'chamfer')) {
      const ids = Array.from(featureSelection.edgeIds || []).map((k) => Number(k.split('|')[1]))
      // Only update if the array actually changed.
      const cur = Array.isArray(active.edge_ids) ? active.edge_ids : []
      if (cur.length !== ids.length || cur.some((v, i) => v !== ids[i])) {
        patchFeature(active.id, { edge_ids: ids, edge_filter: 'manual' })
      }
    } else if (featurePickMode === 'face' && active.op === 'shell') {
      const ids = Array.from(featureSelection.faceIds || []).map((k) => Number(k.split('|')[1]))
      const cur = Array.isArray(active.face_ids) ? active.face_ids : []
      if (cur.length !== ids.length || cur.some((v, i) => v !== ids[i])) {
        patchFeature(active.id, { face_ids: ids })
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [featureSelection, featurePickMode, selectedId])

  // ---- Derived UI state ----
  const sketchFiles = useMemo(() => {
    return (files || []).filter((f) => {
      if (!f) return false
      if (f.kind === 'sketch') return true
      const n = (f.name || '').toLowerCase()
      return n.endsWith('.sketch')
    })
  }, [files])

  const sketchPaths = useMemo(() => {
    const byId = new Map((files || []).map((f) => [f.id, f]))
    function pathOf(f) {
      const parts = []
      let cur = f
      let safety = 0
      while (cur && safety++ < 64) {
        parts.unshift(cur.name)
        if (!cur.parent_id) break
        cur = byId.get(cur.parent_id)
      }
      return '/' + parts.join('/')
    }
    return sketchFiles.map((f) => ({ id: f.id, path: pathOf(f), name: f.name }))
  }, [files, sketchFiles])

  const selectedFeature = useMemo(
    () => tree.find((n) => n.id === selectedId) || null,
    [tree, selectedId],
  )

  const vertexCount = useMemo(() => {
    let n = 0
    for (const m of meshes) {
      const v = m?.mesh?.vertices
      if (v) n += v.length / 3
    }
    return n
  }, [meshes])

  // ---- Render ----
  const selCount = featureSelection.faceIds.size + featureSelection.edgeIds.size
  return (
    <div className="flex-1 min-h-0 flex flex-col bg-ink-950 text-ink-100">
      {/* Unified toolbar — add-feature popover + file name + timeline chips
          on the left; pick-mode controls + inspector toggle on the right. */}
      <div className="border-b border-ink-800 bg-ink-900 px-3 h-11 flex items-center gap-2">
        <AddFeaturePopover onPick={(op) => addFeature(op)} />

        <span className="w-px h-5 bg-ink-800 mx-0.5 flex-shrink-0" aria-hidden="true" />

        <span
          className="text-xs text-ink-400 truncate max-w-[120px] sm:max-w-[160px] flex-shrink-0"
          title={fileName}
        >
          {fileName}
        </span>

        {/* Timeline — scroll horizontally if it gets long.
            role="tree" + role="treeitem" for a11y even though it is a flat
            timeline (aria-level="1" throughout).
            Keyboard: ArrowLeft/Right move between chips (roving tabindex). */}
        <div
          ref={timelineRef}
          role="tree"
          aria-label="Feature timeline"
          className="flex-1 min-w-0 flex items-center gap-1 overflow-x-auto scrollbar-thin"
          title={tree.length > 1 ? 'Selections may reset after structural changes.' : undefined}
          onKeyDown={handleTimelineKeyDown}
        >
          {tree.length === 0 ? (
            <span className="text-xs text-ink-500 italic">
              No features yet — click <span className="text-ink-300">Add feature</span> to start.
            </span>
          ) : (
            tree.map((node, idx) => {
              const kind = KIND_BY_OP[node.op]
              const Icon = kind?.icon || Box
              const isSel = node.id === selectedId
              return (
                <FeatureTimelineChip
                  key={node.id}
                  node={node}
                  kind={kind}
                  Icon={Icon}
                  idx={idx}
                  isSel={isSel}
                  rovingTabIndex={idx === rovingIdx ? 0 : -1}
                  onSelect={() => { setSelectedId(node.id); setRovingIdx(idx); setInspectorOpen(true) }}
                  onDelete={() => { if (confirm(`Delete ${kind?.label || node.op} '${node.id}'?`)) removeFeature(node.id) }}
                />
              )
            })
          )}
        </div>

        {/* Pick-mode controls (right side). */}
        <div className="flex items-center gap-1 flex-shrink-0">
          <ModeBtn
            active={featurePickMode === 'face'}
            onClick={() => setFeaturePickMode(featurePickMode === 'face' ? null : 'face')}
            icon={Pointer}
            label="Faces"
            title="Click faces to select. Shift-click to add. Drives Shell/face_ids of the active feature."
          />
          <ModeBtn
            active={featurePickMode === 'edge'}
            onClick={() => setFeaturePickMode(featurePickMode === 'edge' ? null : 'edge')}
            icon={Pointer}
            label="Edges"
            title="Click edges to select. Shift-click to add. Drives Fillet/Chamfer manual edge_ids."
          />
          <span className="w-px h-5 bg-ink-800 mx-1" aria-hidden="true" />
          <ModeBtn
            active={featurePickMode === 'pushpull'}
            onClick={() => setFeaturePickMode(featurePickMode === 'pushpull' ? null : 'pushpull')}
            icon={Move}
            label="Push/Pull"
            title="Drag a face along its normal. Release to commit a Pad/Pocket."
          />
          <ModeBtn
            active={featurePickMode === 'sketch_on_face'}
            onClick={() => setFeaturePickMode(featurePickMode === 'sketch_on_face' ? null : 'sketch_on_face')}
            icon={PencilLine}
            label="Sketch on face"
            title="Click a planar face to create a new sketch on it."
          />
          {/* Inspector toggle — only visible on narrow viewports (< md). */}
          <button
            type="button"
            onClick={() => setInspectorOpen((v) => !v)}
            aria-label={inspectorOpen ? 'Close inspector' : 'Open inspector'}
            aria-expanded={inspectorOpen}
            aria-controls="feature-inspector-panel"
            className={`md:hidden inline-flex items-center justify-center w-7 h-7 rounded-md border text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60
              ${inspectorOpen
                ? 'border-kerf-300/60 bg-kerf-300/15 text-kerf-100'
                : 'border-ink-700 bg-transparent text-ink-300 hover:bg-ink-800'}`}
          >
            <SlidersHorizontal size={13} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Main: viewport + inspector.
          ≥ md: side-by-side grid (1fr 280px), inspector always visible.
          < md: stacked; inspector is an off-canvas overlay anchored to the
                bottom (slides up, covers ~60% of height). */}
      <div className="flex-1 min-h-0 relative md:grid" style={{ gridTemplateColumns: '1fr 280px' }}>
        <main className="relative min-h-0 min-w-0 h-full">
          <FeatureRenderer
            meshes={meshes}
            selection={featureSelection}
            pickMode={featurePickMode}
            onSelectionChange={setFeatureSelection}
            onFacePick={onFacePicked}
            onPushPullCommit={onPushPullCommit}
            className="w-full h-full"
          />
          {evalState.loading && (
            <div className="absolute top-3 left-3 inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-ink-900/85 backdrop-blur border border-ink-700 text-[11px] text-ink-200 shadow-lg shadow-black/30">
              <Loader2 size={11} className="animate-spin text-kerf-300" aria-hidden="true" />
              <span>Evaluating</span>
            </div>
          )}
          {featurePickMode && (
            <div className="absolute top-3 right-3 inline-flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-md bg-kerf-300/15 backdrop-blur border border-kerf-300/40 text-[11px] text-kerf-100 shadow-lg shadow-black/30">
              <Crosshair size={11} aria-hidden="true" />
              <span>
                {featurePickMode === 'pushpull' && 'Push/Pull · drag a face'}
                {featurePickMode === 'sketch_on_face' && 'Click a planar face'}
                {featurePickMode === 'face' && 'Click faces · shift to add'}
                {featurePickMode === 'edge' && 'Click edges · shift to add'}
                {featurePickMode === 'one_shot_face' && 'Pick a face'}
                {featurePickMode === 'one_shot_edge' && 'Pick an edge'}
                {featurePickMode === 'one_shot_axis' && 'Pick an edge for axis'}
                {featurePickMode === 'one_shot_plane' && 'Pick a face for plane'}
              </span>
              <button
                type="button"
                onClick={() => setFeaturePickMode(null)}
                aria-label="Cancel pick mode"
                className="ml-0.5 inline-flex items-center justify-center w-4 h-4 rounded text-kerf-200 hover:text-white hover:bg-kerf-300/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60"
                title="Cancel pick"
              >
                <X size={10} aria-hidden="true" />
              </button>
            </div>
          )}
        </main>

        {/* Right: inspector — always visible at ≥ md; drawer overlay at < md. */}
        {/* Backdrop for the mobile drawer */}
        {inspectorOpen && (
          <div
            className="md:hidden fixed inset-0 z-30 bg-black/40"
            aria-hidden="true"
            onClick={() => setInspectorOpen(false)}
          />
        )}
        <aside
          id="feature-inspector-panel"
          aria-label="Feature inspector"
          className={`
            md:border-l md:border-ink-800 md:bg-ink-900/60 md:min-h-0 md:overflow-y-auto md:static md:translate-y-0 md:z-auto md:block md:shadow-none
            fixed bottom-0 left-0 right-0 z-40 max-h-[65vh] overflow-y-auto rounded-t-xl border-t border-ink-700 bg-ink-900 shadow-2xl shadow-black/60 transition-transform duration-200
            ${inspectorOpen ? 'translate-y-0' : 'translate-y-full md:translate-y-0'}
          `}
        >
          {/* Mobile handle — tap to close */}
          <button
            type="button"
            className="md:hidden flex justify-center py-2 w-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60 rounded-t-xl"
            onClick={() => setInspectorOpen(false)}
            aria-label="Close inspector"
          >
            <span className="w-8 h-1 rounded-full bg-ink-600" aria-hidden="true" />
          </button>
          {!selectedFeature ? (
            <div className="p-4 text-xs text-ink-500 italic">
              Select a feature in the timeline to edit its parameters.
            </div>
          ) : (
            <FeatureInspector
              feature={selectedFeature}
              tree={tree}
              sketchPaths={sketchPaths}
              selection={featureSelection}
              pickMode={featurePickMode}
              setFeaturePickMode={setFeaturePickMode}
              setFeatureSelection={setFeatureSelection}
              onPatch={(patch) => patchFeature(selectedFeature.id, patch)}
              onMoveUp={() => moveFeature(selectedFeature.id, 'up')}
              onMoveDown={() => moveFeature(selectedFeature.id, 'down')}
              onDelete={() => removeFeature(selectedFeature.id)}
            />
          )}
        </aside>
      </div>

      {/* Bottom: status bar — eval/error left, selection summary middle,
          re-evaluate right. */}
      <div className="flex items-center gap-3 px-3 h-7 border-t border-ink-800 bg-ink-900 text-[11px] font-mono text-ink-500 flex-shrink-0">
        {evalState.error ? (
          <span className="inline-flex items-center gap-1.5 text-red-400 min-w-0">
            <AlertTriangle size={11} className="flex-shrink-0" aria-hidden="true" />
            <span className="truncate" title={evalState.error}>{evalState.error}</span>
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5">
            <span className="text-ink-300">{vertexCount.toLocaleString()}</span>
            <span className="text-ink-500">vertices</span>
            <span className="text-ink-700" aria-hidden="true">·</span>
            <span className="text-ink-300">{meshes.length}</span>
            <span className="text-ink-500">{meshes.length === 1 ? 'body' : 'bodies'}</span>
            {evalState.ms != null && (
              <>
                <span className="text-ink-700" aria-hidden="true">·</span>
                <span>{evalState.ms}ms</span>
              </>
            )}
          </span>
        )}
        <div className="flex-1" />
        {selCount > 0 && (
          <>
            <span className="inline-flex items-center gap-1.5">
              <span className="text-ink-500">Sel</span>
              <span className="text-ink-300">{featureSelection.faceIds.size}</span>
              <span className="text-ink-500">{featureSelection.faceIds.size === 1 ? 'face' : 'faces'}</span>
              <span className="text-ink-700" aria-hidden="true">·</span>
              <span className="text-ink-300">{featureSelection.edgeIds.size}</span>
              <span className="text-ink-500">{featureSelection.edgeIds.size === 1 ? 'edge' : 'edges'}</span>
            </span>
            <button
              type="button"
              onClick={() => clearFeatureSelection()}
              aria-label="Clear viewport selection"
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-ink-400 hover:text-kerf-300 hover:bg-ink-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60"
              title="Clear viewport selection"
            >
              clear
            </button>
            <span className="w-px h-4 bg-ink-800" aria-hidden="true" />
          </>
        )}
        <button
          type="button"
          onClick={() => triggerEvaluate()}
          aria-label="Force re-evaluation"
          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-ink-300 hover:text-kerf-300 hover:bg-ink-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60"
          title="Force re-evaluation"
        >
          <Play size={10} aria-hidden="true" />
          <span>Re-evaluate</span>
        </button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// FeatureTimelineChip — a single chip in the horizontal timeline. Handles
// pointer-unified interactions:
//   - pointer (mouse/stylus): hover shows X delete button; right-click deletes.
//   - touch: long-press opens a small dot-menu (⋯) popover with Delete.
//   - keyboard: Enter/Space selects; Delete key deletes.

function FeatureTimelineChip({ node, kind, Icon, idx, isSel, rovingTabIndex = 0, onSelect, onDelete }) {
  const [dotMenuOpen, setDotMenuOpen] = useState(false)
  const wrapRef = useRef(null)
  useClickOutside(wrapRef, () => setDotMenuOpen(false), dotMenuOpen)
  const longPress = useLongPress(useCallback(() => setDotMenuOpen(true), []))

  const label = kind?.label || node.op

  function handleKeyDown(e) {
    // Enter/Space selects. Delete removes. Arrow keys bubble up to the
    // tree container's roving-tabindex handler.
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect() }
    if (e.key === 'Delete') onDelete()
  }

  return (
    <div ref={wrapRef} role="treeitem" aria-selected={isSel} aria-level={1} className="flex items-center gap-1 flex-shrink-0 relative">
      {idx > 0 && <ChevronRight size={11} className="text-ink-600" aria-hidden="true" />}
      <button
        type="button"
        data-chip-btn=""
        tabIndex={rovingTabIndex}
        onClick={onSelect}
        onKeyDown={handleKeyDown}
        onContextMenu={(ev) => { ev.preventDefault(); onDelete() }}
        {...longPress}
        aria-label={`${label}, feature ${idx + 1}${isSel ? ', selected' : ''}`}
        className={`group relative inline-flex items-center gap-1.5 pl-1.5 pr-2 py-1 rounded-md border text-xs transition-colors
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60
          ${isSel
            ? 'border-kerf-300/60 bg-kerf-300/10 text-kerf-100 shadow-[0_0_0_1px_rgba(255,214,51,0.15)]'
            : 'border-ink-800 bg-ink-850 text-ink-200 hover:border-ink-600 hover:bg-ink-800'}`}
        title={`${label} · right-click or long-press to delete`}
      >
        <span
          aria-hidden="true"
          className={`inline-flex items-center justify-center w-4 h-4 rounded text-[10px] font-mono leading-none flex-shrink-0
            ${isSel ? 'bg-kerf-300/30 text-kerf-100' : 'bg-ink-800 text-ink-400'}`}
        >
          {idx + 1}
        </span>
        <Icon size={12} aria-hidden="true" className={isSel ? 'text-kerf-200' : 'text-ink-300'} />
        {/* Label truncates at narrow viewport */}
        <span className="truncate max-w-[6rem] sm:max-w-[8rem]">{label}</span>
        {/* Desktop: show X delete button when selected */}
        {isSel && (
          <button
            type="button"
            aria-label={`Delete ${label}`}
            onClick={(ev) => { ev.stopPropagation(); onDelete() }}
            className="ml-0.5 -mr-0.5 inline-flex items-center justify-center w-4 h-4 rounded text-ink-400 hover:text-red-300 hover:bg-red-900/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/60"
          >
            <X size={10} aria-hidden="true" />
          </button>
        )}
      </button>
      {/* Dot-menu — always accessible; on touch long-press opens it automatically. */}
      <button
        type="button"
        aria-label={`Actions for ${label}`}
        aria-expanded={dotMenuOpen}
        aria-haspopup="menu"
        onClick={(e) => { e.stopPropagation(); setDotMenuOpen((v) => !v) }}
        className={`inline-flex items-center justify-center w-5 h-5 rounded text-ink-500 hover:text-ink-200 hover:bg-ink-700 transition-colors flex-shrink-0
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60
          ${dotMenuOpen ? 'text-ink-200 bg-ink-700' : ''}`}
        title="Feature actions"
      >
        <MoreHorizontal size={12} aria-hidden="true" />
      </button>
      {dotMenuOpen && (
        <div
          role="menu"
          className="absolute top-full left-0 mt-1 z-50 min-w-[130px] rounded-md border border-ink-700 bg-ink-900 shadow-xl shadow-black/50 py-0.5"
        >
          <button
            role="menuitem"
            type="button"
            onClick={() => { setDotMenuOpen(false); onDelete() }}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-xs text-red-300 hover:bg-red-900/25 focus-visible:outline-none focus-visible:bg-red-900/25"
          >
            <Trash2 size={11} aria-hidden="true" />
            Delete feature
          </button>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Add-feature popover. Single button replaces the 14-icon kitchen-sink; opens
// a panel with FEATURE_CATEGORIES groups and a 3-column grid of icon tiles.
//
// Keyboard:
//   Enter/Space on trigger  → open + focus first item
//   Arrow keys              → move through items (3-col grid: Left/Right wrap
//                             within row; Up/Down move by column)
//   Escape                  → close + return focus to trigger
//   Enter/Space on item     → pick + close + return focus to trigger

function AddFeaturePopover({ onPick }) {
  const [open, setOpen] = useState(false)
  const wrapRef = useRef(null)
  const triggerRef = useRef(null)
  const menuRef = useRef(null)
  useClickOutside(wrapRef, () => setOpen(false), open)

  // Flatten all valid ops across categories for sequential focus.
  const allOps = useMemo(
    () => FEATURE_CATEGORIES.flatMap((cat) => cat.ops.filter((op) => KIND_BY_OP[op])),
    [],
  )
  const COLS = 3

  const closeAndReturnFocus = useCallback(() => {
    setOpen(false)
    // Defer so the menu has unmounted before we attempt focus.
    requestAnimationFrame(() => triggerRef.current?.focus())
  }, [])

  // When the popover opens, focus the first menu item.
  useEffect(() => {
    if (!open) return
    requestAnimationFrame(() => {
      const first = menuRef.current?.querySelector('[role="menuitem"]')
      first?.focus()
    })
  }, [open])

  function handleMenuKeyDown(e) {
    const items = Array.from(menuRef.current?.querySelectorAll('[role="menuitem"]') ?? [])
    if (!items.length) return
    const focused = document.activeElement
    const idx = items.indexOf(focused)

    if (e.key === 'Escape') {
      e.preventDefault()
      closeAndReturnFocus()
    } else if (e.key === 'ArrowRight') {
      e.preventDefault()
      const next = (idx + 1) % items.length
      items[next]?.focus()
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault()
      const next = (idx - 1 + items.length) % items.length
      items[next]?.focus()
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      const next = Math.min(idx + COLS, items.length - 1)
      items[next]?.focus()
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      const next = Math.max(idx - COLS, 0)
      items[next]?.focus()
    } else if (e.key === 'Home') {
      e.preventDefault()
      items[0]?.focus()
    } else if (e.key === 'End') {
      e.preventDefault()
      items[items.length - 1]?.focus()
    } else if (e.key === 'Tab') {
      // Trap focus: cycle within menu or close on Shift+Tab from first.
      if (e.shiftKey && idx === 0) {
        e.preventDefault()
        closeAndReturnFocus()
      } else if (!e.shiftKey && idx === items.length - 1) {
        e.preventDefault()
        items[0]?.focus()
      }
    }
  }

  return (
    <div ref={wrapRef} className="relative flex-shrink-0">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Add feature to timeline"
        aria-expanded={open}
        aria-haspopup="menu"
        className={`inline-flex items-center gap-1.5 pl-2 pr-2.5 py-1.5 rounded-md border text-xs font-medium transition-colors
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60
          ${open
            ? 'border-kerf-300/60 bg-kerf-300/15 text-kerf-100'
            : 'border-ink-700 bg-ink-850 text-ink-100 hover:bg-ink-800 hover:border-ink-600'}`}
        title="Add a feature to the timeline"
      >
        <Plus size={13} aria-hidden="true" className={open ? 'text-kerf-200' : 'text-kerf-300'} />
        <span>Add feature</span>
        <ChevronDown
          size={11}
          aria-hidden="true"
          className={`text-ink-400 transition-transform ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div
          ref={menuRef}
          className="absolute top-full left-0 mt-1.5 z-30 w-[min(420px,calc(100vw-2rem))] rounded-lg border border-ink-700 bg-ink-900 shadow-2xl shadow-black/60 overflow-hidden"
          role="menu"
          aria-label="Add feature"
          onKeyDown={handleMenuKeyDown}
        >
          <div className="max-h-[70vh] overflow-y-auto py-1.5">
            {FEATURE_CATEGORIES.map((cat, ci) => (
              <div key={cat.id} className={ci > 0 ? 'border-t border-ink-800 mt-1.5 pt-1.5' : ''}>
                <div className="px-3 pt-1.5 pb-1 text-[10px] uppercase tracking-wider text-ink-500 font-medium">
                  {cat.label}
                </div>
                <div className="grid grid-cols-3 gap-0.5 px-1.5 pb-1.5">
                  {cat.ops.map((op) => {
                    const k = KIND_BY_OP[op]
                    if (!k) return null
                    const Icon = k.icon
                    return (
                      <button
                        key={op}
                        type="button"
                        role="menuitem"
                        tabIndex={-1}
                        onClick={() => { onPick(op); closeAndReturnFocus() }}
                        aria-label={`Add ${k.label}`}
                        className="group flex flex-col items-center gap-1 px-2 py-2.5 rounded-md text-ink-200 hover:bg-ink-800 hover:text-kerf-200 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60"
                        title={`Add ${k.label}`}
                      >
                        <Icon size={18} aria-hidden="true" className="text-ink-300 group-hover:text-kerf-300" />
                        <span className="text-[11px] leading-none">{k.label}</span>
                      </button>
                    )
                  })}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Right-pane inspector. Renders the field schema for the feature's op.

function FeatureInspector({
  feature,
  tree,
  sketchPaths,
  selection,
  pickMode,
  setFeaturePickMode,
  setFeatureSelection,
  onPatch,
  onMoveUp,
  onMoveDown,
  onDelete,
}) {
  const kind = KIND_BY_OP[feature.op]
  const bodyFeatures = useMemo(() => {
    const idx = tree.findIndex((n) => n.id === feature.id)
    if (idx < 0) return []
    return tree.slice(0, idx).filter((n) => n.op === 'pad' || n.op === 'revolve' || n.op === 'pocket' || n.op === 'fillet' || n.op === 'chamfer' || n.op === 'shell' || n.op === 'hole' || n.op === 'push_pull' || n.op === 'linear_pattern' || n.op === 'polar_pattern' || n.op === 'mirror_pattern')
  }, [tree, feature.id])

  if (!kind) {
    return (
      <div className="p-4 text-xs text-ink-500 italic">
        Unknown op: {feature.op}
      </div>
    )
  }
  const Icon = kind.icon

  // Shared input/select classes — h-8 px-2 text-sm matches Editor.jsx baseline.
  const inputCls = 'w-full h-8 px-2 text-sm bg-ink-900 border border-ink-800 rounded ' +
    'focus:outline-none focus:border-kerf-300/50 focus-visible:ring-2 focus-visible:ring-kerf-300/40 ' +
    'text-ink-100 font-mono'
  const selectCls = 'w-full h-8 px-2 text-sm bg-ink-900 border border-ink-800 rounded ' +
    'focus:outline-none focus:border-kerf-300/50 focus-visible:ring-2 focus-visible:ring-kerf-300/40 ' +
    'text-ink-100'

  return (
    <div className="flex flex-col">
      {/* Header — feature name + reorder + delete. */}
      <div className="sticky top-0 z-10 px-3 py-2.5 bg-ink-900 border-b border-ink-800 flex items-center gap-2">
        <span className="inline-flex items-center justify-center w-6 h-6 rounded bg-kerf-300/15 border border-kerf-300/30 flex-shrink-0" aria-hidden="true">
          <Icon size={13} className="text-kerf-200" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium text-ink-100 leading-tight">{kind.label}</div>
          <div className="text-[10px] text-ink-500 font-mono truncate" title={feature.id}>
            {feature.id}
          </div>
        </div>
        <div className="flex items-center gap-0.5 flex-shrink-0" role="group" aria-label="Feature actions">
          <button
            type="button"
            onClick={onMoveUp}
            aria-label="Move feature up in timeline"
            className="inline-flex items-center justify-center w-6 h-6 rounded text-ink-400 hover:text-kerf-300 hover:bg-ink-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60"
            title="Move up in timeline"
          >
            <ChevronUp size={13} aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={onMoveDown}
            aria-label="Move feature down in timeline"
            className="inline-flex items-center justify-center w-6 h-6 rounded text-ink-400 hover:text-kerf-300 hover:bg-ink-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60"
            title="Move down in timeline"
          >
            <ChevronDown size={13} aria-hidden="true" />
          </button>
          <button
            type="button"
            onClick={onDelete}
            aria-label={`Delete ${kind.label} feature`}
            className="inline-flex items-center justify-center w-6 h-6 rounded text-ink-400 hover:text-red-300 hover:bg-red-900/25 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/60"
            title="Delete this feature"
          >
            <Trash2 size={12} aria-hidden="true" />
          </button>
        </div>
      </div>

      {/* Body — field list. */}
      <div className="px-3 py-3 space-y-3">
      {kind.fields.map((field) => {
        if (field.showWhen && !field.showWhen(feature)) return null
        const fieldId = `inspector-${feature.id}-${field.key}`
        const complexKinds = ['edge_picker','face_picker','face_picker_single','axis_picker','plane_picker','sketch_path_list','edge_radius_list']
        return (
          <div key={field.key} className="space-y-1.5">
            <label
              htmlFor={complexKinds.includes(field.kind) ? undefined : fieldId}
              className="block text-[11px] font-medium text-ink-300"
            >
              {field.label}
            </label>
            {field.kind === 'number' && (
              <input
                id={fieldId}
                type="number"
                value={feature[field.key] ?? ''}
                onChange={(ev) => {
                  const v = ev.target.value === '' ? '' : Number(ev.target.value)
                  onPatch({ [field.key]: v })
                }}
                min={field.min}
                max={field.max}
                step={field.step ?? 'any'}
                aria-label={field.label}
                className={inputCls}
              />
            )}
            {field.kind === 'text' && (
              <input
                id={fieldId}
                type="text"
                value={feature[field.key] ?? ''}
                onChange={(ev) => onPatch({ [field.key]: ev.target.value })}
                aria-label={field.label}
                className={inputCls}
              />
            )}
            {field.kind === 'select' && (
              <select
                id={fieldId}
                value={feature[field.key] ?? field.options?.[0]?.value}
                onChange={(ev) => onPatch({ [field.key]: ev.target.value })}
                aria-label={field.label}
                className={selectCls}
              >
                {(field.options || []).map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            )}
            {field.kind === 'sketch_picker' && (
              <select
                id={fieldId}
                value={feature[field.key] ?? ''}
                onChange={(ev) => onPatch({ [field.key]: ev.target.value })}
                aria-label={field.label}
                className={selectCls + ' font-mono'}
              >
                <option value="">— pick a sketch —</option>
                {sketchPaths.map((s) => (
                  <option key={s.id} value={s.path}>{s.path}</option>
                ))}
              </select>
            )}
            {field.kind === 'feature_picker' && (
              <select
                id={fieldId}
                value={feature[field.key] ?? ''}
                onChange={(ev) => onPatch({ [field.key]: ev.target.value })}
                aria-label={field.label}
                className={selectCls + ' font-mono'}
              >
                <option value="">— pick a feature —</option>
                {bodyFeatures.map((n) => (
                  <option key={n.id} value={n.id}>{n.id} ({n.op})</option>
                ))}
              </select>
            )}
            {field.kind === 'edge_picker' && (
              <EdgeIdsField
                value={feature[field.key] || []}
                onChange={(ids) => onPatch({ [field.key]: ids, edge_filter: 'manual' })}
                pickArmed={pickMode === 'edge'}
                onArmPick={() => setFeaturePickMode(pickMode === 'edge' ? null : 'edge')}
                selection={selection}
                setSelection={setFeatureSelection}
              />
            )}
            {field.kind === 'face_picker' && (
              <FaceIdsField
                value={feature[field.key] || []}
                onChange={(ids) => onPatch({ [field.key]: ids })}
                pickArmed={pickMode === 'face'}
                onArmPick={() => setFeaturePickMode(pickMode === 'face' ? null : 'face')}
                selection={selection}
                setSelection={setFeatureSelection}
              />
            )}
            {field.kind === 'face_picker_single' && (
              <SingleFaceIdField
                value={feature[field.key]}
                onChange={(id) => onPatch({ [field.key]: id })}
                onArmPick={() => setFeaturePickMode('one_shot_face', { featureId: feature.id, fieldKey: field.key, accept: 'face' })}
              />
            )}
            {field.kind === 'axis_picker' && (
              <AxisField
                value={feature[field.key]}
                onChange={(v) => onPatch({ [field.key]: v })}
                onArmPick={() => setFeaturePickMode('one_shot_axis', { featureId: feature.id, fieldKey: field.key, accept: 'edge' })}
              />
            )}
            {field.kind === 'plane_picker' && (
              <PlaneField
                value={feature[field.key]}
                onChange={(v) => onPatch({ [field.key]: v })}
                onArmPick={() => setFeaturePickMode('one_shot_plane', { featureId: feature.id, fieldKey: field.key, accept: 'face' })}
              />
            )}
            {(field.kind === 'bool' || field.kind === 'boolean') && (
              <label className="flex items-center gap-2 h-8 px-2 bg-ink-900 border border-ink-800 rounded text-sm cursor-pointer hover:border-ink-700">
                <input
                  type="checkbox"
                  id={fieldId}
                  checked={feature[field.key] === true}
                  onChange={(ev) => onPatch({ [field.key]: ev.target.checked })}
                  className="w-3.5 h-3.5 accent-kerf-300"
                  aria-label={field.label}
                />
                <span className="text-ink-300 text-sm">{feature[field.key] === true ? 'on' : 'off'}</span>
              </label>
            )}
            {field.kind === 'sketch_path_list' && (
              <SketchPathListField
                value={feature[field.key] || []}
                onChange={(v) => onPatch({ [field.key]: v })}
                sketchPaths={sketchPaths}
              />
            )}
            {field.kind === 'edge_radius_list' && (
              <EdgeRadiusListField
                value={feature[field.key] || []}
                onChange={(v) => onPatch({ [field.key]: v })}
                pickArmed={pickMode === 'edge'}
                onArmPick={() => setFeaturePickMode(pickMode === 'edge' ? null : 'edge')}
                selection={selection}
                setSelection={setFeatureSelection}
              />
            )}
          </div>
        )
      })}
      {/* Caption — optional explanatory note for ops that benefit from one (e.g. surface_boolean). */}
      {kind.caption && (
        <div className="mx-3 mb-3 px-2 py-2 rounded bg-ink-800/60 border border-ink-700/50 text-[10px] text-ink-400 leading-relaxed">
          {kind.caption}
        </div>
      )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Selection-driven field components.

// SketchPathListField — ordered list of sketch paths (loft profiles, etc.).
// Add via the dropdown at the bottom; remove via the X on each row; reorder
// with the up/down arrows.
function SketchPathListField({ value, onChange, sketchPaths }) {
  const list = Array.isArray(value) ? value : []
  const remaining = sketchPaths.filter((s) => !list.includes(s.path))
  return (
    <div className="space-y-1">
      {list.length === 0 ? (
        <div className="text-[11px] text-ink-500 italic">No profiles yet — pick at least 2.</div>
      ) : (
        <div className="space-y-0.5">
          {list.map((p, i) => (
            <div key={`${p}-${i}`} className="flex items-center gap-1 px-1.5 py-1 bg-ink-900 border border-ink-800 rounded text-xs font-mono">
              <span className="text-ink-500 w-4 text-right flex-shrink-0">{i + 1}.</span>
              <span className="flex-1 truncate text-ink-200 min-w-0">{p}</span>
              <button type="button" disabled={i === 0}
                aria-label="Move profile up"
                className="text-ink-500 hover:text-kerf-300 disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60 flex-shrink-0"
                onClick={() => {
                  const next = [...list]; ;[next[i - 1], next[i]] = [next[i], next[i - 1]]; onChange(next)
                }}>
                <ChevronUp size={12} aria-hidden="true" />
              </button>
              <button type="button" disabled={i === list.length - 1}
                aria-label="Move profile down"
                className="text-ink-500 hover:text-kerf-300 disabled:opacity-30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60 flex-shrink-0"
                onClick={() => {
                  const next = [...list]; ;[next[i + 1], next[i]] = [next[i], next[i + 1]]; onChange(next)
                }}>
                <ChevronDown size={12} aria-hidden="true" />
              </button>
              <button type="button"
                aria-label={`Remove profile ${p}`}
                className="text-ink-500 hover:text-red-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/60 flex-shrink-0"
                onClick={() => onChange(list.filter((_, j) => j !== i))}>
                <Trash2 size={12} aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>
      )}
      {remaining.length > 0 && (
        <select
          value=""
          onChange={(ev) => { if (ev.target.value) onChange([...list, ev.target.value]) }}
          aria-label="Add profile sketch"
          className="w-full h-8 px-2 text-sm bg-ink-900 border border-ink-800 rounded font-mono text-ink-100
                     focus:outline-none focus:border-kerf-300/50 focus-visible:ring-2 focus-visible:ring-kerf-300/40"
        >
          <option value="">— add a profile sketch —</option>
          {remaining.map((s) => (
            <option key={s.id} value={s.path}>{s.path}</option>
          ))}
        </select>
      )}
    </div>
  )
}

// EdgeRadiusListField — list of {edge_id, start_radius, end_radius} for the
// variable-radius fillet. v1 keeps it simple: each picked edge gets a start
// radius and an end radius (the worker fans these out into a 2-point param
// table at .at=0 and .at=1). Richer per-vertex point editing is a follow-up.
function EdgeRadiusListField({ value, onChange, pickArmed, onArmPick, selection }) {
  const rows = Array.isArray(value) ? value : []
  // Sync any newly-picked edges into the rows with default radii.
  const pickedSet = selection?.edges instanceof Set ? selection.edges : new Set()
  useEffect(() => {
    if (!pickArmed) return
    const known = new Set(rows.map((r) => r.edge_id))
    const additions = []
    for (const eid of pickedSet) {
      if (!known.has(eid)) additions.push({ edge_id: eid, radii: [{ at: 0, radius: 1 }, { at: 1, radius: 1 }] })
    }
    if (additions.length > 0) onChange([...rows, ...additions])
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickedSet.size, pickArmed])
  return (
    <div className="space-y-1">
      {rows.length === 0 ? (
        <div className="text-[11px] text-ink-500 italic">Arm pick + click edges in viewport, or use the toggle below.</div>
      ) : (
        <div className="space-y-0.5">
          {rows.map((row, i) => {
            const start = row.radii?.[0]?.radius ?? 1
            const end = row.radii?.[row.radii.length - 1]?.radius ?? start
            return (
              <div key={row.edge_id} className="flex items-center gap-1 px-1.5 py-1 bg-ink-900 border border-ink-800 rounded text-[11px] font-mono">
                <span className="text-ink-500 w-12 flex-shrink-0">edge {row.edge_id}</span>
                <input
                  type="number"
                  value={start}
                  step={0.1}
                  min={0.001}
                  aria-label={`Start radius for edge ${row.edge_id}`}
                  onChange={(ev) => {
                    const v = Number(ev.target.value)
                    const next = [...rows]
                    next[i] = { ...row, radii: [{ at: 0, radius: v }, { at: 1, radius: end }] }
                    onChange(next)
                  }}
                  className="w-14 h-6 px-1 bg-ink-800 border border-ink-700 rounded text-ink-100 focus:outline-none focus:border-kerf-300/50"
                />
                <span className="text-ink-500" aria-hidden="true">→</span>
                <input
                  type="number"
                  value={end}
                  step={0.1}
                  min={0.001}
                  aria-label={`End radius for edge ${row.edge_id}`}
                  onChange={(ev) => {
                    const v = Number(ev.target.value)
                    const next = [...rows]
                    next[i] = { ...row, radii: [{ at: 0, radius: start }, { at: 1, radius: v }] }
                    onChange(next)
                  }}
                  className="w-14 h-6 px-1 bg-ink-800 border border-ink-700 rounded text-ink-100 focus:outline-none focus:border-kerf-300/50"
                />
                <button type="button"
                  aria-label={`Remove edge ${row.edge_id}`}
                  className="text-ink-500 hover:text-red-400 ml-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/60"
                  onClick={() => onChange(rows.filter((_, j) => j !== i))}>
                  <Trash2 size={11} aria-hidden="true" />
                </button>
              </div>
            )
          })}
        </div>
      )}
      <button
        type="button"
        onClick={onArmPick}
        aria-label={pickArmed ? 'Stop picking edges' : 'Pick edges in viewport'}
        aria-pressed={pickArmed}
        className={`w-full px-2 h-8 rounded text-sm border transition-colors
          focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60
          ${pickArmed
            ? 'bg-kerf-300/15 border-kerf-300/40 text-kerf-200'
            : 'bg-ink-900 border-ink-800 text-ink-400 hover:text-kerf-300'}`}
      >
        {pickArmed ? 'Click edges in viewport (Esc to stop)' : 'Pick edges'}
      </button>
    </div>
  )
}

function EdgeIdsField({ value, onChange, pickArmed, onArmPick, selection, setSelection }) {
  const ids = Array.isArray(value) ? value : []
  // Sync selection set to the displayed ids when the user is actively picking.
  // (FeatureView already pushes selection into the feature; this is the reverse
  // direction — useful when the user clicks "remove" on a chip.)
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onArmPick}
          aria-label={pickArmed ? 'Stop picking edges' : 'Pick edges in viewport'}
          aria-pressed={pickArmed}
          className={`inline-flex items-center gap-1 px-2 h-7 rounded text-[11px] border
            focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60
            ${pickArmed
              ? 'bg-kerf-300/15 border-kerf-300/50 text-kerf-200'
              : 'bg-ink-800 border-ink-700 text-ink-300 hover:border-ink-500'}`}
          title={pickArmed ? 'Stop picking edges' : 'Click in the viewport to pick edges'}
        >
          <Crosshair size={11} aria-hidden="true" />
          <span>{pickArmed ? 'Picking…' : 'Pick edges'}</span>
        </button>
        <span className="text-[11px] text-ink-500">{ids.length} selected</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {ids.map((id) => (
          <button
            key={id}
            type="button"
            onClick={() => {
              const next = ids.filter((x) => x !== id)
              onChange(next)
              // Also update the viewport selection so the highlight removes.
              const filteredEdges = new Set(
                Array.from(selection?.edgeIds || []).filter((k) => Number(k.split('|')[1]) !== id)
              )
              setSelection({ faceIds: selection?.faceIds || new Set(), edgeIds: filteredEdges })
            }}
            aria-label={`Remove edge ${id}`}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-ink-800 border border-ink-700 text-[11px] font-mono text-ink-200 hover:bg-red-900/30 hover:border-red-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/60"
            title={`Remove edge ${id}`}
          >
            <span>e{id}</span>
            <span aria-hidden="true" className="text-ink-500">×</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function FaceIdsField({ value, onChange, pickArmed, onArmPick, selection, setSelection }) {
  const ids = Array.isArray(value) ? value : []
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={onArmPick}
          className={`inline-flex items-center gap-1 px-2 py-1 rounded text-[11px] border
            ${pickArmed
              ? 'bg-kerf-300/15 border-kerf-300/50 text-kerf-200'
              : 'bg-ink-800 border-ink-700 text-ink-300 hover:border-ink-500'}`}
          title={pickArmed ? 'Stop picking faces' : 'Click in the viewport to pick faces'}
        >
          <Crosshair size={11} />
          <span>{pickArmed ? 'Picking…' : 'Pick faces'}</span>
        </button>
        <span className="text-[11px] text-ink-500">{ids.length} selected</span>
      </div>
      <div className="flex flex-wrap gap-1">
        {ids.map((id) => (
          <button
            key={id}
            type="button"
            onClick={() => {
              const next = ids.filter((x) => x !== id)
              onChange(next)
              const filteredFaces = new Set(
                Array.from(selection?.faceIds || []).filter((k) => Number(k.split('|')[1]) !== id)
              )
              setSelection({ edgeIds: selection?.edgeIds || new Set(), faceIds: filteredFaces })
            }}
            aria-label={`Remove face ${id}`}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-ink-800 border border-ink-700 text-[11px] font-mono text-ink-200 hover:bg-red-900/30 hover:border-red-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-red-400/60"
            title={`Remove face ${id}`}
          >
            <span>f{id}</span>
            <span aria-hidden="true" className="text-ink-500">×</span>
          </button>
        ))}
      </div>
    </div>
  )
}

function SingleFaceIdField({ value, onChange, onArmPick }) {
  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        onClick={onArmPick}
        aria-label="Pick face in viewport"
        className="inline-flex items-center gap-1 px-2 h-8 rounded text-[11px] border bg-ink-800 border-ink-700 text-ink-300 hover:border-ink-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60 flex-shrink-0"
      >
        <Crosshair size={11} aria-hidden="true" />
        <span>Pick face</span>
      </button>
      <input
        type="number"
        value={value ?? ''}
        onChange={(ev) => onChange(ev.target.value === '' ? '' : Number(ev.target.value))}
        aria-label="Face ID"
        className="flex-1 h-8 px-2 bg-ink-900 border border-ink-800 rounded text-sm font-mono text-ink-100
                   focus:outline-none focus:border-kerf-300/50 focus-visible:ring-2 focus-visible:ring-kerf-300/40"
        placeholder="face id"
      />
    </div>
  )
}

function AxisField({ value, onChange, onArmPick }) {
  // value can be 'x'|'y'|'z' (string) or a numeric edge id.
  const isEdge = typeof value === 'number'
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1">
        <select
          value={isEdge ? '_edge' : (value || 'x')}
          onChange={(ev) => {
            if (ev.target.value === '_edge') return // user must arm pick
            onChange(ev.target.value)
          }}
          aria-label="Axis"
          className="flex-1 h-8 px-2 text-sm bg-ink-900 border border-ink-800 rounded text-ink-100
                     focus:outline-none focus:border-kerf-300/50 focus-visible:ring-2 focus-visible:ring-kerf-300/40"
        >
          <option value="x">X</option>
          <option value="y">Y</option>
          <option value="z">Z</option>
          <option value="_edge">{isEdge ? `Edge ${value}` : 'Pick edge…'}</option>
        </select>
        <button
          type="button"
          onClick={onArmPick}
          aria-label="Pick an edge in the viewport for axis"
          className="inline-flex items-center gap-1 px-2 h-8 rounded text-[11px] border bg-ink-800 border-ink-700 text-ink-300 hover:border-ink-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60 flex-shrink-0"
          title="Pick an edge in the viewport"
        >
          <Crosshair size={11} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}

function PlaneField({ value, onChange, onArmPick }) {
  // value can be 'xy'|'xz'|'yz' (string) or a numeric face id.
  const isFace = typeof value === 'number'
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1">
        <select
          value={isFace ? '_face' : (value || 'xy')}
          onChange={(ev) => {
            if (ev.target.value === '_face') return
            onChange(ev.target.value)
          }}
          aria-label="Plane"
          className="flex-1 h-8 px-2 text-sm bg-ink-900 border border-ink-800 rounded text-ink-100
                     focus:outline-none focus:border-kerf-300/50 focus-visible:ring-2 focus-visible:ring-kerf-300/40"
        >
          <option value="xy">XY</option>
          <option value="xz">XZ</option>
          <option value="yz">YZ</option>
          <option value="_face">{isFace ? `Face ${value}` : 'Pick face…'}</option>
        </select>
        <button
          type="button"
          onClick={onArmPick}
          aria-label="Pick a planar face in the viewport for plane"
          className="inline-flex items-center gap-1 px-2 h-8 rounded text-[11px] border bg-ink-800 border-ink-700 text-ink-300 hover:border-ink-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60 flex-shrink-0"
          title="Pick a planar face in the viewport"
        >
          <Crosshair size={11} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}

// Shared toolbar mode-button. Active state uses kerf-300 background +
// brighter text so it reads as "armed", not just "highlighted".
function ModeBtn({ active, onClick, icon: Icon, label, title }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={label}
      aria-pressed={active}
      className={`inline-flex items-center gap-1.5 px-2 py-1.5 rounded-md border text-[11px] transition-colors flex-shrink-0
        focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-kerf-300/60
        ${active
          ? 'border-kerf-300/60 bg-kerf-300/20 text-kerf-100 shadow-[0_0_0_1px_rgba(255,214,51,0.2)]'
          : 'border-transparent bg-transparent text-ink-300 hover:bg-ink-800 hover:text-ink-100'}`}
    >
      <Icon size={12} aria-hidden="true" />
      <span>{label}</span>
    </button>
  )
}

// Helper: read an array-valued field on a feature node by id (for sketch-on-
// face and one-shot pick path). Tolerant of missing nodes.
function _arrayField(tree, featureId, fieldKey) {
  const n = tree.find((x) => x.id === featureId)
  return Array.isArray(n?.[fieldKey]) ? n[fieldKey] : []
}
