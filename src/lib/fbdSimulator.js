// fbdSimulator.js — Pure-JS scan-cycle simulator for an FBD network.
//
// Consumes the {blocks, signals} network produced by fbdCanvas.js (T-225c-1)
// and drives outputs from inputs, mirroring the IEC 61131-3 §6 semantics
// implemented in the Python function_blocks.py (T-223).
//
// Public API
// ----------
//   simulateFbdTick(network, inputs, prevState) -> { outputs, newState }
//   runFbdFor(network, inputProvider, duration_ms, tick_ms)  -> trace
//
// Network shape (from fbdCanvas.js):
//   network.blocks  — [{ id, type, params, inputs: [{name, signal_id}], outputs: [{name, signal_id}] }]
//   network.signals — [{ id, source_block_id, source_pin, dest_block_id, dest_pin }]
//
// Supported block types:
//   Combinational: AND, OR, NOT
//   Sequential:    TON, TOF, CTU
//   I/O:           INPUT, OUTPUT, CONSTANT

// ── Topo-sort ─────────────────────────────────────────────────────────────────

/**
 * Kahn's algorithm on block-level DAG derived from signal edges.
 *
 * @param {object} network
 * @returns {string[]} block ids in evaluation order (sources first)
 * @throws {{ code: 'CYCLE', blocks: string[] }} if a cycle is detected
 */
export function topoSort(network) {
  const blockIds = network.blocks.map(b => b.id)

  // in-degree: how many signal edges point INTO this block
  const inDeg = new Map(blockIds.map(id => [id, 0]))
  // adjacency: source_block_id → [dest_block_id]
  const adj = new Map(blockIds.map(id => [id, []]))

  for (const sig of network.signals) {
    const src = sig.source_block_id
    const dst = sig.dest_block_id
    if (!adj.has(src) || !inDeg.has(dst)) continue
    adj.get(src).push(dst)
    inDeg.set(dst, inDeg.get(dst) + 1)
  }

  // Start with zero-in-degree nodes
  const queue = blockIds.filter(id => inDeg.get(id) === 0)
  const order = []

  while (queue.length > 0) {
    const node = queue.shift()
    order.push(node)
    for (const neighbour of adj.get(node) ?? []) {
      const d = inDeg.get(neighbour) - 1
      inDeg.set(neighbour, d)
      if (d === 0) queue.push(neighbour)
    }
  }

  if (order.length !== blockIds.length) {
    // At least one cycle: collect the un-emitted nodes
    const remaining = blockIds.filter(id => !order.includes(id))
    const err = new Error(`FBD cycle detected involving block(s): ${remaining.join(', ')}`)
    err.code = 'CYCLE'
    err.blocks = remaining
    throw err
  }

  return order
}

// ── Combinational evaluators ──────────────────────────────────────────────────

function evalAND(pinValues) {
  // All connected inputs must be true (unconnected pins default false)
  const in1 = Boolean(pinValues['IN1'] ?? false)
  const in2 = Boolean(pinValues['IN2'] ?? false)
  return { OUT: in1 && in2 }
}

function evalOR(pinValues) {
  const in1 = Boolean(pinValues['IN1'] ?? false)
  const in2 = Boolean(pinValues['IN2'] ?? false)
  return { OUT: in1 || in2 }
}

function evalNOT(pinValues) {
  return { OUT: !Boolean(pinValues['IN'] ?? false) }
}

// ── Sequential evaluators (read/write blockState keyed by block id) ───────────

function evalTON(block, pinValues, blockState, tick_ms) {
  const inVal = Boolean(pinValues['IN'] ?? false)
  // PT can come from a connected signal pin or from block.params.PT (ms)
  const pt = Number(pinValues['PT'] ?? block.params?.PT ?? 0)

  let et = blockState.et ?? 0

  if (inVal) {
    et = Math.min(et + tick_ms, pt)
  } else {
    et = 0
  }

  const q = inVal && et >= pt && pt > 0
  return {
    pinOut: { Q: q, ET: et },
    blockState: { et },
  }
}

function evalTOF(block, pinValues, blockState, tick_ms) {
  const inVal = Boolean(pinValues['IN'] ?? false)
  const pt = Number(pinValues['PT'] ?? block.params?.PT ?? 0)

  let et = blockState.et ?? 0
  let prevIn = blockState.prevIn ?? false
  let timing = blockState.timing ?? false

  if (inVal) {
    // Rising or sustained: reset timer, output on
    et = 0
    timing = false
  } else {
    if (prevIn) {
      // Falling edge: start timing
      timing = true
    }
    if (timing) {
      et = Math.min(et + tick_ms, pt)
    }
  }

  const q = inVal || (timing && et < pt)
  return {
    pinOut: { Q: q, ET: et },
    blockState: { et, prevIn: inVal, timing },
  }
}

function evalCTU(block, pinValues, blockState, tick_ms) {
  const cuVal = Boolean(pinValues['CU'] ?? false)
  const rVal = Boolean(pinValues['R'] ?? false)
  const pv = Number(pinValues['PV'] ?? block.params?.PV ?? 0)

  let cv = blockState.cv ?? 0
  let prevCu = blockState.prevCu ?? false

  if (rVal) {
    cv = 0
  } else if (cuVal && !prevCu) {
    // Rising edge of CU
    cv += 1
  }

  return {
    pinOut: { Q: cv >= pv, CV: cv },
    blockState: { cv, prevCu: cuVal },
  }
}

// ── Core scan-cycle ───────────────────────────────────────────────────────────

/**
 * Execute one scan cycle of the FBD network.
 *
 * @param {object} network   — { blocks, signals } from fbdCanvas.js
 * @param {object} inputs    — dict: variable name → boolean/number value
 * @param {object} prevState — opaque state returned by a previous tick (or {})
 * @param {number} [tick_ms=1] — scan cycle duration in milliseconds
 * @returns {{ outputs: object, newState: object }}
 *   outputs  — dict: output variable name → value
 *   newState — carry-forward state for the next tick
 */
export function simulateFbdTick(network, inputs, prevState, tick_ms = 1) {
  if (!network || !Array.isArray(network.blocks) || !Array.isArray(network.signals)) {
    throw new Error('Invalid network: must have blocks[] and signals[]')
  }

  const order = topoSort(network)

  // Build block map for fast access
  const blockMap = new Map(network.blocks.map(b => [b.id, b]))

  // Signal values keyed by "source_block_id:source_pin"
  const signalValues = new Map()

  // Accumulate state per block
  const newState = {}
  const outputs = {}

  // Collect signals into a lookup: dest_block_id:dest_pin → value (populated as we go)
  // We'll fill this lazily as we evaluate each block
  // Pre-index signals by destination for fast lookup
  const sigByDest = new Map()
  for (const sig of network.signals) {
    const key = `${sig.dest_block_id}:${sig.dest_pin}`
    sigByDest.set(key, sig)
  }

  for (const blockId of order) {
    const block = blockMap.get(blockId)
    if (!block) continue

    // Collect pin values for this block's inputs
    const pinValues = {}
    for (const inPin of block.inputs) {
      const key = `${blockId}:${inPin.name}`
      const sig = sigByDest.get(key)
      if (sig) {
        const srcKey = `${sig.source_block_id}:${sig.source_pin}`
        pinValues[inPin.name] = signalValues.get(srcKey) ?? false
      }
      // If no signal drives this input pin, pinValues[inPin.name] remains undefined
      // (evaluators default to false / 0 for missing pins)
    }

    const bState = prevState[blockId] ?? {}
    let outPins = {}

    switch (block.type) {
      case 'INPUT': {
        // Reads from the inputs dict; variable name stored in block.params.name
        const varName = block.params?.name ?? blockId
        const val = inputs[varName] ?? false
        outPins = { OUT: val }
        break
      }

      case 'OUTPUT': {
        // Writes the driven value to the outputs dict
        const varName = block.params?.name ?? blockId
        const val = pinValues['IN'] ?? false
        outputs[varName] = val
        break
      }

      case 'CONSTANT': {
        // Emits a fixed value from block.params.value
        const val = block.params?.value ?? false
        outPins = { OUT: val }
        break
      }

      case 'AND':
        outPins = evalAND(pinValues)
        break

      case 'OR':
        outPins = evalOR(pinValues)
        break

      case 'NOT':
        outPins = evalNOT(pinValues)
        break

      case 'TON': {
        const result = evalTON(block, pinValues, bState, tick_ms)
        outPins = result.pinOut
        newState[blockId] = result.blockState
        break
      }

      case 'TOF': {
        const result = evalTOF(block, pinValues, bState, tick_ms)
        outPins = result.pinOut
        newState[blockId] = result.blockState
        break
      }

      case 'CTU': {
        const result = evalCTU(block, pinValues, bState, tick_ms)
        outPins = result.pinOut
        newState[blockId] = result.blockState
        break
      }

      default:
        // Unknown block type: emit no outputs, carry no state
        break
    }

    // Publish output pin values so downstream blocks can read them
    for (const [pinName, val] of Object.entries(outPins)) {
      signalValues.set(`${blockId}:${pinName}`, val)
    }
  }

  return { outputs, newState }
}

// ── Multi-tick runner ─────────────────────────────────────────────────────────

/**
 * Run the FBD network for a given duration, returning a trace of every tick.
 *
 * @param {object} network
 * @param {function|object} inputProvider
 *   - If a function: called with (tick_index, elapsed_ms) → inputs dict each tick
 *   - If an object: used as constant inputs for all ticks
 * @param {number} duration_ms  — total simulation time in ms
 * @param {number} [tick_ms=1] — scan cycle interval in ms
 * @returns {{ tick: number, elapsed_ms: number, inputs: object, outputs: object }[]}
 */
export function runFbdFor(network, inputProvider, duration_ms, tick_ms = 1) {
  const trace = []
  let state = {}
  let elapsed = 0
  let tickIndex = 0

  const getInputs = typeof inputProvider === 'function'
    ? inputProvider
    : () => inputProvider

  while (elapsed < duration_ms) {
    const inputs = getInputs(tickIndex, elapsed)
    const { outputs, newState } = simulateFbdTick(network, inputs, state, tick_ms)
    trace.push({ tick: tickIndex, elapsed_ms: elapsed, inputs, outputs })
    state = newState
    elapsed += tick_ms
    tickIndex += 1
  }

  return trace
}
