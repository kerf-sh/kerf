// fbdCanvas.js — IEC 61131-3 §6 Function Block Diagram (FBD) data model + ops.
//
// A network contains:
//   blocks   — functional blocks (AND, OR, NOT, timers, counters, I/O, etc.)
//   signals  — directed wires connecting one block output pin to one block input pin
//
// All operations are immutable: they return a new network object and leave the
// original unchanged.

// ── Block pin definitions ─────────────────────────────────────────────────────

/**
 * Pin descriptor: { name, required }
 * required=true means validateNetwork() flags the block if that input is not
 * driven by a signal.
 */
const BLOCK_PINS = {
  AND:      { inputs: [{ name: 'IN1', required: true }, { name: 'IN2', required: true }], outputs: [{ name: 'OUT' }] },
  OR:       { inputs: [{ name: 'IN1', required: true }, { name: 'IN2', required: true }], outputs: [{ name: 'OUT' }] },
  NOT:      { inputs: [{ name: 'IN',  required: true }],                                 outputs: [{ name: 'OUT' }] },
  TON:      { inputs: [{ name: 'IN',  required: true }, { name: 'PT', required: false }], outputs: [{ name: 'Q' }, { name: 'ET' }] },
  TOF:      { inputs: [{ name: 'IN',  required: true }, { name: 'PT', required: false }], outputs: [{ name: 'Q' }, { name: 'ET' }] },
  CTU:      { inputs: [{ name: 'CU',  required: true }, { name: 'R',  required: false }, { name: 'PV', required: false }], outputs: [{ name: 'Q' }, { name: 'CV' }] },
  INPUT:    { inputs: [],                                                                  outputs: [{ name: 'OUT' }] },
  OUTPUT:   { inputs: [{ name: 'IN',  required: true }],                                 outputs: [] },
  CONSTANT: { inputs: [],                                                                  outputs: [{ name: 'OUT' }] },
}

export const BLOCK_TYPES = Object.keys(BLOCK_PINS)

// ── ID generation ─────────────────────────────────────────────────────────────

let _idCounter = 0

/** Reset the counter — useful in tests to get deterministic IDs. */
export function _resetIdCounter() {
  _idCounter = 0
}

function nextId(prefix) {
  _idCounter += 1
  return `${prefix}_${_idCounter}`
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function cloneNetwork(network) {
  return JSON.parse(JSON.stringify(network))
}

function findBlock(network, block_id) {
  return network.blocks.find(b => b.id === block_id) ?? null
}

function findSignal(network, signal_id) {
  return network.signals.find(s => s.id === signal_id) ?? null
}

/** Returns the pin definition array for a block's side ('inputs' | 'outputs'). */
function pinDefs(block, side) {
  const defs = BLOCK_PINS[block.type]
  if (!defs) return []
  return defs[side] ?? []
}

function hasPin(block, side, pin_name) {
  return pinDefs(block, side).some(p => p.name === pin_name)
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Create an empty FBD network.
 *
 * @returns {{ blocks: [], signals: [] }}
 */
export function createNetwork() {
  return { blocks: [], signals: [] }
}

/**
 * Add a functional block to the network.
 *
 * @param {object} network
 * @param {string} type    — one of BLOCK_TYPES
 * @param {{ x: number, y: number }} position
 * @param {object} [params] — optional block parameters (e.g. preset value for CONSTANT)
 * @returns {object} new network
 * @throws {Error} if type is unknown
 */
export function addBlock(network, type, position, params = {}) {
  if (!BLOCK_PINS[type]) {
    throw new Error(`Unknown block type: ${type}. Valid types: ${BLOCK_TYPES.join(', ')}`)
  }
  const next = cloneNetwork(network)
  const defs = BLOCK_PINS[type]
  const block = {
    id: nextId('blk'),
    type,
    position: { x: position.x, y: position.y },
    inputs:  defs.inputs.map(p  => ({ name: p.name, signal_id: null })),
    outputs: defs.outputs.map(p => ({ name: p.name, signal_id: null })),
    params: { ...params },
  }
  next.blocks.push(block)
  return next
}

/**
 * Add a signal (wire) connecting one block's output pin to another block's
 * input pin.
 *
 * Validation:
 *  - Both blocks must exist.
 *  - src_pin must exist on the source block's outputs.
 *  - dst_pin must exist on the dest block's inputs.
 *  - Source and destination must be different blocks (or different pins on same
 *    block, but self-loops would create a cycle so are rejected outright).
 *  - A destination input pin may only be driven by one signal at a time.
 *
 * @returns {object} new network
 * @throws {Error} on validation failure
 */
export function addSignal(network, src_block_id, src_pin, dst_block_id, dst_pin) {
  const srcBlock = findBlock(network, src_block_id)
  if (!srcBlock) throw new Error(`Source block not found: ${src_block_id}`)

  const dstBlock = findBlock(network, dst_block_id)
  if (!dstBlock) throw new Error(`Destination block not found: ${dst_block_id}`)

  if (src_block_id === dst_block_id) {
    throw new Error('Source and destination block must differ (self-loop not allowed)')
  }

  if (!hasPin(srcBlock, 'outputs', src_pin)) {
    throw new Error(`Pin '${src_pin}' not found on outputs of block '${src_block_id}' (type ${srcBlock.type})`)
  }

  if (!hasPin(dstBlock, 'inputs', dst_pin)) {
    throw new Error(`Pin '${dst_pin}' not found on inputs of block '${dst_block_id}' (type ${dstBlock.type})`)
  }

  // No double-driving: dest input pin already driven?
  const alreadyDriven = network.signals.some(
    s => s.dest_block_id === dst_block_id && s.dest_pin === dst_pin
  )
  if (alreadyDriven) {
    throw new Error(`Input pin '${dst_pin}' of block '${dst_block_id}' is already driven by a signal`)
  }

  const next = cloneNetwork(network)
  const signal = {
    id: nextId('sig'),
    source_block_id: src_block_id,
    source_pin:      src_pin,
    dest_block_id:   dst_block_id,
    dest_pin:        dst_pin,
  }
  next.signals.push(signal)

  // Update block pin signal_id references for quick lookup
  const srcInNext  = next.blocks.find(b => b.id === src_block_id)
  const dstInNext  = next.blocks.find(b => b.id === dst_block_id)
  const srcPinRef  = srcInNext.outputs.find(p => p.name === src_pin)
  const dstPinRef  = dstInNext.inputs.find(p => p.name === dst_pin)
  if (srcPinRef) srcPinRef.signal_id = signal.id
  if (dstPinRef) dstPinRef.signal_id = signal.id

  return next
}

/**
 * Remove a block and all signals connected to it (either as source or dest).
 *
 * @returns {object} new network
 * @throws {Error} if block not found
 */
export function removeBlock(network, block_id) {
  if (!findBlock(network, block_id)) {
    throw new Error(`Block not found: ${block_id}`)
  }
  const next = cloneNetwork(network)

  // Collect signal IDs that touch this block
  const removedSignalIds = new Set(
    next.signals
      .filter(s => s.source_block_id === block_id || s.dest_block_id === block_id)
      .map(s => s.id)
  )

  // Remove affected signals
  next.signals = next.signals.filter(s => !removedSignalIds.has(s.id))

  // Clear signal_id refs on surviving blocks' pins
  for (const block of next.blocks) {
    for (const pin of block.inputs)  if (removedSignalIds.has(pin.signal_id))  pin.signal_id = null
    for (const pin of block.outputs) if (removedSignalIds.has(pin.signal_id))  pin.signal_id = null
  }

  // Remove the block itself
  next.blocks = next.blocks.filter(b => b.id !== block_id)
  return next
}

/**
 * Remove a single signal by id.
 *
 * @returns {object} new network
 * @throws {Error} if signal not found
 */
export function removeSignal(network, signal_id) {
  const signal = findSignal(network, signal_id)
  if (!signal) throw new Error(`Signal not found: ${signal_id}`)

  const next = cloneNetwork(network)
  next.signals = next.signals.filter(s => s.id !== signal_id)

  // Clear pin signal_id refs
  const srcBlock = next.blocks.find(b => b.id === signal.source_block_id)
  const dstBlock = next.blocks.find(b => b.id === signal.dest_block_id)
  if (srcBlock) {
    const pin = srcBlock.outputs.find(p => p.name === signal.source_pin)
    if (pin && pin.signal_id === signal_id) pin.signal_id = null
  }
  if (dstBlock) {
    const pin = dstBlock.inputs.find(p => p.name === signal.dest_pin)
    if (pin && pin.signal_id === signal_id) pin.signal_id = null
  }

  return next
}

/**
 * Move a block to a new position.
 *
 * @returns {object} new network
 * @throws {Error} if block not found
 */
export function moveBlock(network, block_id, new_position) {
  if (!findBlock(network, block_id)) {
    throw new Error(`Block not found: ${block_id}`)
  }
  const next = cloneNetwork(network)
  const block = next.blocks.find(b => b.id === block_id)
  block.position = { x: new_position.x, y: new_position.y }
  return next
}

// ── validateNetwork ───────────────────────────────────────────────────────────

/**
 * Validate the FBD network for structural correctness.
 *
 * Checks:
 *  1. No cycles (DFS-based cycle detection following signal edges).
 *  2. No dangling signals (signal references non-existent block/pin).
 *  3. All required input pins are connected.
 *  4. No double-driven inputs (enforced at addSignal time but double-checked).
 *
 * @returns {{ ok: boolean, errors: string[] }}
 */
export function validateNetwork(network) {
  const errors = []

  if (!network || typeof network !== 'object') {
    return { ok: false, errors: ['network must be an object'] }
  }
  if (!Array.isArray(network.blocks)) {
    return { ok: false, errors: ['network.blocks must be an array'] }
  }
  if (!Array.isArray(network.signals)) {
    return { ok: false, errors: ['network.signals must be an array'] }
  }

  const blockMap = new Map(network.blocks.map(b => [b.id, b]))

  // 1. Dangling signals + double-driven check
  const inputDriveCount = new Map() // "block_id:pin" → count
  for (const sig of network.signals) {
    const src = blockMap.get(sig.source_block_id)
    const dst = blockMap.get(sig.dest_block_id)
    if (!src) {
      errors.push(`Signal ${sig.id}: source block '${sig.source_block_id}' not found`)
      continue
    }
    if (!dst) {
      errors.push(`Signal ${sig.id}: dest block '${sig.dest_block_id}' not found`)
      continue
    }
    if (!hasPin(src, 'outputs', sig.source_pin)) {
      errors.push(`Signal ${sig.id}: pin '${sig.source_pin}' not found on outputs of '${sig.source_block_id}'`)
    }
    if (!hasPin(dst, 'inputs', sig.dest_pin)) {
      errors.push(`Signal ${sig.id}: pin '${sig.dest_pin}' not found on inputs of '${sig.dest_block_id}'`)
    }
    const key = `${sig.dest_block_id}:${sig.dest_pin}`
    inputDriveCount.set(key, (inputDriveCount.get(key) ?? 0) + 1)
  }

  for (const [key, count] of inputDriveCount) {
    if (count > 1) {
      errors.push(`Input pin '${key}' is driven by ${count} signals (double-drive)`)
    }
  }

  // 2. Required inputs connected
  //    Build set of driven dest pins for fast lookup
  const drivenPins = new Set(
    network.signals.map(s => `${s.dest_block_id}:${s.dest_pin}`)
  )
  for (const block of network.blocks) {
    const defs = BLOCK_PINS[block.type]
    if (!defs) {
      errors.push(`Block ${block.id}: unknown type '${block.type}'`)
      continue
    }
    for (const pinDef of defs.inputs) {
      if (pinDef.required && !drivenPins.has(`${block.id}:${pinDef.name}`)) {
        errors.push(`Block ${block.id} (${block.type}): required input pin '${pinDef.name}' is not connected`)
      }
    }
  }

  // 3. Cycle detection via DFS
  //    Build adjacency: block_id → [dest_block_ids] (following signal edges)
  const adj = new Map()
  for (const block of network.blocks) adj.set(block.id, [])
  for (const sig of network.signals) {
    if (blockMap.has(sig.source_block_id) && blockMap.has(sig.dest_block_id)) {
      adj.get(sig.source_block_id).push(sig.dest_block_id)
    }
  }

  // Three-colour DFS: 0=unvisited, 1=in-stack, 2=done
  const colour = new Map()
  for (const id of adj.keys()) colour.set(id, 0)

  const cycleNodes = new Set()

  function dfs(node) {
    colour.set(node, 1)
    for (const neighbour of adj.get(node) ?? []) {
      if (colour.get(neighbour) === 1) {
        // Back edge → cycle
        cycleNodes.add(node)
        cycleNodes.add(neighbour)
        return true
      }
      if (colour.get(neighbour) === 0) {
        if (dfs(neighbour)) {
          cycleNodes.add(node)
        }
      }
    }
    colour.set(node, 2)
    return cycleNodes.has(node)
  }

  for (const id of adj.keys()) {
    if (colour.get(id) === 0) dfs(id)
  }

  if (cycleNodes.size > 0) {
    errors.push(`Cycle detected involving block(s): ${[...cycleNodes].join(', ')}`)
  }

  return { ok: errors.length === 0, errors }
}
