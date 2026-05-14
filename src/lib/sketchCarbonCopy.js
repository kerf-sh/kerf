// sketchCarbonCopy.js — Carbon-copy (driven reference) geometry from a source
// sketch into a target sketch. Copied entities are marked `is_reference: true`
// and are read-only: they participate in constraints but are not extruded.
//
// Public API:
//   carbonCopy({sourceSketch, targetSketch, entityIds?, transform?})
//     → updated targetSketch with copied entities marked is_reference: true.
//   findCarbonCopyChain(targetSketch)
//     → list of source sketch ids the target references (direct + transitive).
//   refreshCarbonCopies({targetSketch, sourceById})
//     → re-sync reference entities from the current source geometry; preserve
//       user-added constraints that reference those entities.

// ---------------------------------------------------------------------------
// Helpers

function applyTransform(x, y, transform) {
  if (!transform) return { x, y }
  const tx = typeof transform.x === 'number' ? transform.x : 0
  const ty = typeof transform.y === 'number' ? transform.y : 0
  const deg = typeof transform.rotation_deg === 'number' ? transform.rotation_deg : 0
  const rad = (deg * Math.PI) / 180
  const cos = Math.cos(rad)
  const sin = Math.sin(rad)
  return {
    x: (x * cos - y * sin) + tx,
    y: (x * sin + y * cos) + ty,
  }
}

// Return the source_id for a reference entity (stored on the entity itself).
function sourceId(ent) {
  return ent?.source_id || null
}

// Collect all entity ids that belong to a given source sketch reference (keyed
// by `cc_source`).
function refEntitiesForSource(sketch, ccSourceId) {
  return (sketch.entities || []).filter(
    (e) => e.is_reference && e.cc_source === ccSourceId,
  )
}

// Deep-copy a single entity from source into target coordinate space. Appends
// auxiliary point entities for lines/arcs/circles that need them.
// Returns an array of entities (points + the edge entity).
function copyEntity(ent, sourceEntById, transform, prefix) {
  const id = (raw) => `${prefix}${raw}`
  const result = []

  if (ent.type === 'point') {
    const { x, y } = applyTransform(ent.x || 0, ent.y || 0, transform)
    result.push({
      id: id(ent.id),
      type: 'point',
      x,
      y,
      is_reference: true,
      source_id: ent.id,
      cc_source: prefix.replace(/_$/, ''),
      construction: true,
    })
  } else if (ent.type === 'line') {
    const p1Src = sourceEntById.get(ent.p1)
    const p2Src = sourceEntById.get(ent.p2)
    if (!p1Src || !p2Src) return result
    const np1 = applyTransform(p1Src.x || 0, p1Src.y || 0, transform)
    const np2 = applyTransform(p2Src.x || 0, p2Src.y || 0, transform)
    result.push({
      id: id(ent.p1), type: 'point', x: np1.x, y: np1.y,
      is_reference: true, source_id: ent.p1,
      cc_source: prefix.replace(/_$/, ''), construction: true,
    })
    result.push({
      id: id(ent.p2), type: 'point', x: np2.x, y: np2.y,
      is_reference: true, source_id: ent.p2,
      cc_source: prefix.replace(/_$/, ''), construction: true,
    })
    result.push({
      id: id(ent.id), type: 'line',
      p1: id(ent.p1), p2: id(ent.p2),
      is_reference: true, source_id: ent.id,
      cc_source: prefix.replace(/_$/, ''), construction: true,
    })
  } else if (ent.type === 'circle') {
    const cSrc = sourceEntById.get(ent.center)
    if (!cSrc) return result
    const nc = applyTransform(cSrc.x || 0, cSrc.y || 0, transform)
    result.push({
      id: id(ent.center), type: 'point', x: nc.x, y: nc.y,
      is_reference: true, source_id: ent.center,
      cc_source: prefix.replace(/_$/, ''), construction: true,
    })
    result.push({
      id: id(ent.id), type: 'circle',
      center: id(ent.center), radius: ent.radius || 0,
      is_reference: true, source_id: ent.id,
      cc_source: prefix.replace(/_$/, ''), construction: true,
    })
  } else if (ent.type === 'arc') {
    const cSrc = sourceEntById.get(ent.center)
    const sSrc = sourceEntById.get(ent.start)
    const eSrc = sourceEntById.get(ent.end)
    if (!cSrc || !sSrc || !eSrc) return result
    const nc = applyTransform(cSrc.x || 0, cSrc.y || 0, transform)
    const ns = applyTransform(sSrc.x || 0, sSrc.y || 0, transform)
    const ne = applyTransform(eSrc.x || 0, eSrc.y || 0, transform)
    result.push({
      id: id(ent.center), type: 'point', x: nc.x, y: nc.y,
      is_reference: true, source_id: ent.center,
      cc_source: prefix.replace(/_$/, ''), construction: true,
    })
    result.push({
      id: id(ent.start), type: 'point', x: ns.x, y: ns.y,
      is_reference: true, source_id: ent.start,
      cc_source: prefix.replace(/_$/, ''), construction: true,
    })
    result.push({
      id: id(ent.end), type: 'point', x: ne.x, y: ne.y,
      is_reference: true, source_id: ent.end,
      cc_source: prefix.replace(/_$/, ''), construction: true,
    })
    result.push({
      id: id(ent.id), type: 'arc',
      center: id(ent.center), start: id(ent.start), end: id(ent.end),
      sweep_ccw: !!ent.sweep_ccw,
      is_reference: true, source_id: ent.id,
      cc_source: prefix.replace(/_$/, ''), construction: true,
    })
  }
  return result
}

// ---------------------------------------------------------------------------
// Public: carbonCopy

/**
 * Copy entities from sourceSketch into targetSketch as driven reference geometry.
 *
 * @param {object} opts
 * @param {object} opts.sourceSketch  - source sketch JSON object
 * @param {object} opts.targetSketch  - target sketch JSON object
 * @param {string[]} [opts.entityIds] - entity ids to copy (default: all non-point edges)
 * @param {object} [opts.transform]   - { x?, y?, rotation_deg? } applied to coords
 * @param {string} [opts.sourceSketchId] - stable id for the source (used as cc_source key)
 * @returns {object} updated targetSketch
 */
export function carbonCopy({ sourceSketch, targetSketch, entityIds, transform, sourceSketchId }) {
  const srcId = sourceSketchId || 'cc0'
  const prefix = `${srcId}_`

  const srcEntities = sourceSketch.entities || []
  const srcEntById = new Map(srcEntities.map((e) => [e.id, e]))

  // Filter to the requested entity ids; default = all edges (not bare points,
  // those are pulled in as auxiliaries by the edge copier).
  const edgeTypes = new Set(['line', 'circle', 'arc'])
  let toExport = srcEntities.filter((e) => edgeTypes.has(e.type) && !e.is_reference)
  if (Array.isArray(entityIds)) {
    // An explicit (possibly empty) list overrides the default-all behaviour.
    const idSet = new Set(entityIds)
    toExport = toExport.filter((e) => idSet.has(e.id))
  }

  // Build the new reference entities (may include duplicate point entries —
  // deduplicate by id, keeping first).
  const newEnts = []
  const seen = new Set()
  for (const ent of toExport) {
    const copied = copyEntity(ent, srcEntById, transform, prefix)
    for (const ce of copied) {
      if (!seen.has(ce.id)) {
        seen.add(ce.id)
        newEnts.push(ce)
      }
    }
  }

  // Remove any existing reference entities from this same source (replace-on-copy).
  const existing = (targetSketch.entities || []).filter(
    (e) => !(e.is_reference && e.cc_source === srcId),
  )

  // Record the source reference in metadata for chain detection.
  const prevSources = targetSketch.cc_sources || []
  const cc_sources = prevSources.includes(srcId) ? prevSources : [...prevSources, srcId]

  return {
    ...targetSketch,
    entities: [...existing, ...newEnts],
    cc_sources,
  }
}

// ---------------------------------------------------------------------------
// Public: findCarbonCopyChain

/**
 * Return an ordered list of source sketch ids that this target directly
 * references (one level — not recursive). For deeper impact analysis,
 * callers walk the tree themselves.
 *
 * @param {object} targetSketch
 * @returns {string[]}
 */
export function findCarbonCopyChain(targetSketch) {
  // Collect from explicit cc_sources metadata field.
  const fromMeta = Array.isArray(targetSketch.cc_sources) ? [...targetSketch.cc_sources] : []

  // Also scan entities for any cc_source values not yet in the metadata
  // (defensive, in case an older format stored only on entities).
  const fromEnts = new Set()
  for (const e of targetSketch.entities || []) {
    if (e.is_reference && e.cc_source) fromEnts.add(e.cc_source)
  }
  for (const src of fromEnts) {
    if (!fromMeta.includes(src)) fromMeta.push(src)
  }
  return fromMeta
}

// ---------------------------------------------------------------------------
// Public: refreshCarbonCopies

/**
 * Re-sync reference entities in targetSketch from up-to-date source geometry.
 * Constraints in the target that reference the reference entities are preserved
 * (their entity-id references remain valid since ids are stable).
 *
 * @param {object} opts
 * @param {object} opts.targetSketch        - target sketch JSON object
 * @param {object} opts.sourceById          - map of sourceSketchId → sourceSketch
 * @param {object} [opts.transformById]     - map of sourceSketchId → transform (optional)
 * @returns {object} updated targetSketch
 */
export function refreshCarbonCopies({ targetSketch, sourceById, transformById = {} }) {
  const chain = findCarbonCopyChain(targetSketch)
  let updated = targetSketch

  for (const srcId of chain) {
    const source = sourceById[srcId]
    if (!source) {
      // Source missing — mark reference entities as unresolved but keep them.
      updated = {
        ...updated,
        entities: (updated.entities || []).map((e) =>
          e.is_reference && e.cc_source === srcId
            ? { ...e, unresolved: true }
            : e,
        ),
      }
      continue
    }

    // Re-run carbonCopy preserving the same sourceSketchId so ids are stable.
    // Existing constraints referencing these entity ids continue to work.
    updated = carbonCopy({
      sourceSketch: source,
      targetSketch: updated,
      transform: transformById[srcId] || null,
      sourceSketchId: srcId,
    })
  }

  return updated
}
