// erc.js — Electrical Rules Check for CircuitJSON schematics.
//
// Usage:
//   import { runERC } from './erc.js'
//   const { errors, warnings } = runERC(circuit_json)
//
// circuit_json: flat array of CircuitJSON elements (source_* elements from tscircuit)
// Returns:
//   errors   : Array<{ kind, severity:'error', message, component_id?, port_id?, net_id? }>
//   warnings : Array<{ kind, severity:'warning', message, component_id?, port_id?, net_id? }>

// ---------------------------------------------------------------------------
// Union-Find for net connectivity
// ---------------------------------------------------------------------------
function makeUF() {
  const parent = {}
  function find(x) {
    if (parent[x] === undefined) parent[x] = x
    if (parent[x] !== x) parent[x] = find(parent[x])
    return parent[x]
  }
  function union(a, b) {
    const ra = find(a), rb = find(b)
    if (ra !== rb) parent[ra] = rb
  }
  return { find, union }
}

// ---------------------------------------------------------------------------
// Parse helpers
// ---------------------------------------------------------------------------

function ports(circuit) {
  return circuit.filter((e) => e?.type === 'source_port')
}

function traces(circuit) {
  return circuit.filter((e) => e?.type === 'source_trace')
}

function components(circuit) {
  return circuit.filter((e) => e?.type === 'source_component')
}

function nets(circuit) {
  return circuit.filter((e) => e?.type === 'source_net')
}

// Collect every port id touched by any trace
function touchedPortIds(traceList) {
  const ids = new Set()
  for (const t of traceList) {
    for (const conn of t.connected_source_port_ids ?? t.port_ids ?? []) {
      ids.add(conn)
    }
  }
  return ids
}

// Build net-id -> canonical root via union-find over trace connections
function buildNetUF(traceList) {
  const uf = makeUF()
  for (const t of traceList) {
    const portIds = t.connected_source_port_ids ?? t.port_ids ?? []
    const netIds  = t.connected_source_net_ids   ?? t.net_ids  ?? []
    const all = [...portIds, ...netIds]
    for (let i = 1; i < all.length; i++) uf.union(all[0], all[i])
  }
  return uf
}

// ---------------------------------------------------------------------------
// Check 1: unconnected_pin
//   Every source_port must be touched by at least one source_trace.
// ---------------------------------------------------------------------------
function checkUnconnectedPins(portList, touched) {
  const errors = []
  for (const p of portList) {
    const id = p.source_port_id ?? p.id
    if (id && !touched.has(id)) {
      errors.push({
        kind: 'unconnected_pin',
        severity: 'error',
        message: `Pin "${p.name ?? id}" on component "${p.source_component_id ?? '?'}" is unconnected`,
        component_id: p.source_component_id ?? null,
        port_id: id,
      })
    }
  }
  return errors
}

// ---------------------------------------------------------------------------
// Check 2: duplicate_refdes
//   No two components may share the same reference designator.
// ---------------------------------------------------------------------------
function checkDuplicateRefdes(componentList) {
  const errors = []
  const seen = new Map()
  for (const c of componentList) {
    const ref = c.name ?? c.refdes ?? c.reference_designator ?? null
    const id  = c.source_component_id ?? c.id
    if (!ref) continue
    if (seen.has(ref)) {
      errors.push({
        kind: 'duplicate_refdes',
        severity: 'error',
        message: `Duplicate reference designator "${ref}" (components "${seen.get(ref)}" and "${id}")`,
        component_id: id,
      })
    } else {
      seen.set(ref, id)
    }
  }
  return errors
}

// ---------------------------------------------------------------------------
// Check 3: conflicting_net_label
//   Manually-labelled nets that union-find proves are in different roots
//   after tracing — i.e., two net labels on the same physical wire that
//   disagree, OR two net elements that should be merged but aren't connected.
//
//   Concretely: find net labels that share a trace (same union-find root)
//   but have different net names/labels.
// ---------------------------------------------------------------------------
function checkConflictingNetLabels(netList, traceList) {
  const errors = []
  const uf = buildNetUF(traceList)

  // Map root -> first net name seen at that root
  const rootName = new Map()
  for (const n of netList) {
    const nid = n.source_net_id ?? n.id
    const label = n.name ?? n.net_name ?? nid
    const root = uf.find(nid)
    if (rootName.has(root)) {
      const prev = rootName.get(root)
      if (prev !== label) {
        errors.push({
          kind: 'conflicting_net_label',
          severity: 'error',
          message: `Net labels "${prev}" and "${label}" resolve to the same net but have conflicting names`,
          net_id: nid,
        })
      }
    } else {
      rootName.set(root, label)
    }
  }
  return errors
}

// ---------------------------------------------------------------------------
// Check 4: output_to_output
//   Two output ports connected on the same trace.
//   Excludes open-collector / open-drain (electrical_function flag).
// ---------------------------------------------------------------------------
function checkOutputToOutput(portList, traceList) {
  const errors = []
  const portById = new Map()
  for (const p of portList) {
    portById.set(p.source_port_id ?? p.id, p)
  }

  for (const t of traceList) {
    const ids = t.connected_source_port_ids ?? t.port_ids ?? []
    const outputPorts = ids
      .map((id) => portById.get(id))
      .filter((p) => {
        if (!p) return false
        if (p.pin_type !== 'output' && p.port_hints?.includes('output') === false) return false
        // Accept if pin_type/port_hints says 'output'
        const isOutput = p.pin_type === 'output' ||
          (Array.isArray(p.port_hints) && p.port_hints.includes('output'))
        if (!isOutput) return false
        // Exclude open-collector / open-drain
        const ef = p.electrical_function ?? ''
        if (ef === 'open_collector' || ef === 'open_drain') return false
        return true
      })

    if (outputPorts.length >= 2) {
      for (let i = 1; i < outputPorts.length; i++) {
        errors.push({
          kind: 'output_to_output',
          severity: 'error',
          message: `Output pin "${outputPorts[0].name ?? outputPorts[0].source_port_id}" tied to output pin "${outputPorts[i].name ?? outputPorts[i].source_port_id}"`,
          port_id: outputPorts[i].source_port_id ?? outputPorts[i].id,
        })
      }
    }
  }
  return errors
}

// ---------------------------------------------------------------------------
// Check 5: missing_power
//   A net whose name looks like a power net (VCC, GND, VDD, etc.) is
//   referenced by a port with pin_type='power_in' but no port with
//   pin_type='power' / 'power_out' / 'supply' sources it.
// ---------------------------------------------------------------------------
function checkMissingPower(portList, netList) {
  const errors = []

  // Build set of sourced net ids / names
  const sourcedNets = new Set()
  for (const p of portList) {
    const pt = p.pin_type ?? ''
    if (pt === 'power' || pt === 'power_out' || pt === 'supply' ||
        (Array.isArray(p.port_hints) && (p.port_hints.includes('power') || p.port_hints.includes('supply')))) {
      if (p.source_net_id) sourcedNets.add(p.source_net_id)
      if (p.net_name)      sourcedNets.add(p.net_name)
    }
  }

  for (const n of netList) {
    const nid   = n.source_net_id ?? n.id
    const label = n.name ?? n.net_name ?? ''
    const isPower = n.is_power === true ||
      /^(vcc|vdd|vss|gnd|vbat|v\d+v?\d*|pwr)$/i.test(label)
    if (isPower && !sourcedNets.has(nid) && !sourcedNets.has(label)) {
      errors.push({
        kind: 'missing_power',
        severity: 'error',
        message: `Power net "${label || nid}" is referenced but never sourced by a power/supply pin`,
        net_id: nid,
      })
    }
  }
  return errors
}

// ---------------------------------------------------------------------------
// Check 6: pin_direction_mismatch (warning)
//   An input-only port is directly connected to another input-only port
//   with no other drivers on that trace.
// ---------------------------------------------------------------------------
function checkPinDirectionMismatch(portList, traceList) {
  const warnings = []
  const portById = new Map()
  for (const p of portList) {
    portById.set(p.source_port_id ?? p.id, p)
  }

  function isInputOnly(p) {
    if (!p) return false
    if (p.pin_type === 'input') return true
    if (Array.isArray(p.port_hints) && p.port_hints.includes('input') &&
        !p.port_hints.includes('output') && !p.port_hints.includes('bidirectional')) return true
    return false
  }

  function isDriver(p) {
    if (!p) return false
    const pt = p.pin_type ?? ''
    return pt === 'output' || pt === 'power' || pt === 'power_out' || pt === 'passive' ||
      (Array.isArray(p.port_hints) && (p.port_hints.includes('output') || p.port_hints.includes('power')))
  }

  for (const t of traceList) {
    const ids = t.connected_source_port_ids ?? t.port_ids ?? []
    const connPorts = ids.map((id) => portById.get(id)).filter(Boolean)
    const hasDriver = connPorts.some(isDriver)
    if (hasDriver) continue
    const inputPorts = connPorts.filter(isInputOnly)
    if (inputPorts.length >= 2) {
      warnings.push({
        kind: 'pin_direction_mismatch',
        severity: 'warning',
        message: `Input pin "${inputPorts[0].name ?? inputPorts[0].source_port_id}" drives input pin "${inputPorts[1].name ?? inputPorts[1].source_port_id}" with no driver on the net`,
        port_id: inputPorts[0].source_port_id ?? inputPorts[0].id,
      })
    }
  }
  return warnings
}

// ---------------------------------------------------------------------------
// Check 7: floating_net (warning)
//   A net that has only one port connected — likely a dangling wire.
// ---------------------------------------------------------------------------
function checkFloatingNet(portList, traceList) {
  const warnings = []
  const uf = buildNetUF(traceList)

  // Count ports per root
  const rootPorts = new Map()
  const portById = new Map()
  for (const p of portList) {
    const id = p.source_port_id ?? p.id
    portById.set(id, p)
  }

  const touched = touchedPortIds(traceList)
  for (const t of traceList) {
    const ids = t.connected_source_port_ids ?? t.port_ids ?? []
    if (ids.length === 0) continue
    const root = uf.find(ids[0])
    if (!rootPorts.has(root)) rootPorts.set(root, new Set())
    for (const id of ids) rootPorts.get(root).add(id)
  }

  for (const [root, portSet] of rootPorts) {
    if (portSet.size === 1) {
      const onlyId = [...portSet][0]
      const p = portById.get(onlyId)
      warnings.push({
        kind: 'floating_net',
        severity: 'warning',
        message: `Net (root "${root}") has only one connected port "${p?.name ?? onlyId}" — possible floating wire`,
        port_id: onlyId,
      })
    }
  }
  return warnings
}

// ---------------------------------------------------------------------------
// Check 8: bidirectional_promiscuity (warning)
//   More than 3 bidirectional ports on one net suggests a bus should be used.
// ---------------------------------------------------------------------------
const BIDIR_THRESHOLD = 3

function checkBidirectionalPromiscuity(portList, traceList) {
  const warnings = []
  const uf = buildNetUF(traceList)
  const portById = new Map()
  for (const p of portList) {
    portById.set(p.source_port_id ?? p.id, p)
  }

  // Count bidir ports per net root
  const rootBidir = new Map()
  const touched = touchedPortIds(traceList)
  for (const [id, p] of portById) {
    if (!touched.has(id)) continue
    const isBidir = p.pin_type === 'bidirectional' ||
      (Array.isArray(p.port_hints) && p.port_hints.includes('bidirectional'))
    if (!isBidir) continue
    const root = uf.find(id)
    rootBidir.set(root, (rootBidir.get(root) ?? 0) + 1)
  }

  for (const [root, count] of rootBidir) {
    if (count > BIDIR_THRESHOLD) {
      warnings.push({
        kind: 'bidirectional_promiscuity',
        severity: 'warning',
        message: `Net (root "${root}") has ${count} bidirectional ports — consider using a bus`,
        net_id: root,
      })
    }
  }
  return warnings
}

// ---------------------------------------------------------------------------
// Main export: runERC
// ---------------------------------------------------------------------------

/**
 * runERC — run all ERC checks on a flat CircuitJSON array.
 *
 * @param {Array} circuit_json  AnyCircuitElement[] (source_* elements)
 * @returns {{ errors: Array, warnings: Array }}
 */
export function runERC(circuit_json) {
  if (!Array.isArray(circuit_json) || circuit_json.length === 0) {
    return { errors: [], warnings: [] }
  }

  const portList      = ports(circuit_json)
  const traceList     = traces(circuit_json)
  const componentList = components(circuit_json)
  const netList       = nets(circuit_json)
  const touched       = touchedPortIds(traceList)

  const errors = [
    ...checkUnconnectedPins(portList, touched),
    ...checkDuplicateRefdes(componentList),
    ...checkConflictingNetLabels(netList, traceList),
    ...checkOutputToOutput(portList, traceList),
    ...checkMissingPower(portList, netList),
  ]

  const warnings = [
    ...checkPinDirectionMismatch(portList, traceList),
    ...checkFloatingNet(portList, traceList),
    ...checkBidirectionalPromiscuity(portList, traceList),
  ]

  return { errors, warnings }
}
