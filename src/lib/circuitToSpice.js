/**
 * circuitToSpice — pure CircuitJSON → SPICE `.cir` netlist emitter.
 *
 * Phase 1 of the Electronics SPICE roadmap: a hermetic, side-effect-free
 * transform from tscircuit's compiled CircuitJSON array to a SPICE deck
 * string. No engine, no worker, no UI. Engine integration (ngspice-wasm),
 * the `.simulation` file kind, the SimulationView panel, and the
 * `run_simulation` LLM tool are all deferred.
 *
 * Recognised `source_component.ftype` values (verified against
 * `node_modules/@tscircuit/core` + `node_modules/circuit-json`):
 *   simple_resistor, simple_capacitor, simple_inductor,
 *   simple_voltage_source, simple_diode, simple_transistor, simple_mosfet.
 * (tscircuit collapses BJTs into `simple_transistor`; `simple_bjt_transistor`
 * does NOT exist on disk. We honour both spellings just in case.)
 *
 * Net assignment uses union-find over `source_trace.connected_source_port_ids`
 * — every port reachable through a chain of traces collapses into one SPICE
 * net. Net `0` is GND, taken from any component named `GND` (case-insensitive)
 * or whose ftype is `simple_ground`. Other nets are numbered 1…N in order of
 * first appearance.
 *
 * Probe convention (the schematic probe tool isn't built yet, so this is the
 * forward-compatible shape we'll emit from the future tool):
 *   { type: 'simulation_probe', _kerf_probe: true,
 *     name: 'VOUT', kind: 'V'|'I',
 *     source_port_id?: string,        // for V — net is the port's net
 *     source_component_id?: string }  // for I — refdes is the component
 *
 * Returns `{ netlist, probes, warnings, errors }`. If `errors` is non-empty
 * the netlist still contains the header + `.end` but skips analysis cards;
 * callers should refuse to dispatch it to the engine.
 *
 * @param {Array<object>} circuitJson
 * @param {{ analysis?: { type: 'tran'|'dc'|'op', tstep?: string, tstop?: string } }} [opts]
 * @returns {{ netlist: string, probes: Array<{name:string,kind:'V'|'I',netOrComp:string|number}>, warnings: string[], errors: string[] }}
 */
export function circuitToSpice(circuitJson, opts = {}) {
  const warnings = []
  const errors = []
  const probes = []

  const records = Array.isArray(circuitJson) ? circuitJson : []

  const components = records
    .filter((r) => r && r.type === 'source_component')
    .slice()
    .sort((a, b) => String(a.source_component_id).localeCompare(String(b.source_component_id)))

  const ports = records.filter((r) => r && r.type === 'source_port')
  const traces = records.filter((r) => r && r.type === 'source_trace')

  const portsByComponent = new Map()
  for (const p of ports) {
    const list = portsByComponent.get(p.source_component_id) || []
    list.push(p)
    portsByComponent.set(p.source_component_id, list)
  }
  for (const list of portsByComponent.values()) {
    list.sort((a, b) => (a.pin_number ?? 0) - (b.pin_number ?? 0))
  }

  // Union-find over port ids: every trace fuses its connected ports into one
  // equivalence class, which becomes one SPICE net.
  const parent = new Map()
  const find = (x) => {
    if (!parent.has(x)) parent.set(x, x)
    let r = x
    while (parent.get(r) !== r) r = parent.get(r)
    let cur = x
    while (parent.get(cur) !== r) {
      const nxt = parent.get(cur)
      parent.set(cur, r)
      cur = nxt
    }
    return r
  }
  const union = (a, b) => {
    const ra = find(a)
    const rb = find(b)
    if (ra !== rb) parent.set(ra, rb)
  }
  for (const p of ports) find(p.source_port_id)
  for (const t of traces) {
    const ids = Array.isArray(t.connected_source_port_ids) ? t.connected_source_port_ids : []
    for (let i = 1; i < ids.length; i++) union(ids[0], ids[i])
  }

  const groundComponentIds = new Set()
  for (const c of components) {
    const nm = String(c.name || '').toLowerCase()
    if (nm === 'gnd' || nm === 'ground' || c.ftype === 'simple_ground' || c.ftype === 'ground') {
      groundComponentIds.add(c.source_component_id)
    }
  }
  const groundRoots = new Set()
  for (const p of ports) {
    if (groundComponentIds.has(p.source_component_id)) groundRoots.add(find(p.source_port_id))
  }

  const netByRoot = new Map()
  for (const r of groundRoots) netByRoot.set(r, 0)
  let nextNet = 1
  const netOf = (portId) => {
    if (!portId) return null
    const r = find(portId)
    if (!netByRoot.has(r)) netByRoot.set(r, nextNet++)
    return netByRoot.get(r)
  }

  const refdesCounters = {}
  const ftypeToPrefix = {
    simple_resistor: 'R',
    simple_capacitor: 'C',
    simple_inductor: 'L',
    simple_voltage_source: 'V',
    simple_diode: 'D',
    simple_transistor: 'Q',
    simple_bjt_transistor: 'Q',
    simple_mosfet: 'M',
  }
  const refdesOf = (c) => {
    const prefix = ftypeToPrefix[c.ftype] || 'X'
    if (c.name && /^[A-Za-z][A-Za-z0-9_]*$/.test(c.name)) return c.name
    refdesCounters[prefix] = (refdesCounters[prefix] || 0) + 1
    return `${prefix}${refdesCounters[prefix]}`
  }

  const isFiniteNum = (v) => typeof v === 'number' && Number.isFinite(v)
  const numeric = (v) => {
    if (isFiniteNum(v)) return v
    if (typeof v === 'string' && v.trim() !== '' && Number.isFinite(Number(v))) return Number(v)
    return null
  }

  const pickPorts = (c, n) => {
    const list = portsByComponent.get(c.source_component_id) || []
    if (list.length < n) return null
    return list.slice(0, n)
  }

  const componentLines = []
  const modelLines = []

  for (const c of components) {
    if (groundComponentIds.has(c.source_component_id)) continue
    const refdes = refdesOf(c)
    const compPorts = portsByComponent.get(c.source_component_id) || []
    for (const p of compPorts) {
      const idsTouching = traces.some((t) =>
        Array.isArray(t.connected_source_port_ids) && t.connected_source_port_ids.includes(p.source_port_id),
      )
      if (!idsTouching) {
        errors.push(`${refdes}: dangling port ${p.source_port_id} (no trace connects it)`)
      }
    }

    switch (c.ftype) {
      case 'simple_resistor': {
        const v = numeric(c.resistance)
        if (v == null) {
          errors.push(`${refdes}: missing or non-numeric resistance`)
          break
        }
        const pp = pickPorts(c, 2)
        if (!pp) { errors.push(`${refdes}: needs 2 ports, found ${compPorts.length}`); break }
        const n1 = netOf(pp[0].source_port_id)
        const n2 = netOf(pp[1].source_port_id)
        componentLines.push(`R${refdes} ${n1} ${n2} ${v}`)
        break
      }
      case 'simple_capacitor': {
        const v = numeric(c.capacitance)
        if (v == null) {
          errors.push(`${refdes}: missing or non-numeric capacitance`)
          break
        }
        const pp = pickPorts(c, 2)
        if (!pp) { errors.push(`${refdes}: needs 2 ports, found ${compPorts.length}`); break }
        const n1 = netOf(pp[0].source_port_id)
        const n2 = netOf(pp[1].source_port_id)
        componentLines.push(`C${refdes} ${n1} ${n2} ${v}`)
        break
      }
      case 'simple_inductor': {
        const v = numeric(c.inductance)
        if (v == null) {
          errors.push(`${refdes}: missing or non-numeric inductance`)
          break
        }
        const pp = pickPorts(c, 2)
        if (!pp) { errors.push(`${refdes}: needs 2 ports, found ${compPorts.length}`); break }
        const n1 = netOf(pp[0].source_port_id)
        const n2 = netOf(pp[1].source_port_id)
        componentLines.push(`L${refdes} ${n1} ${n2} ${v}`)
        break
      }
      case 'simple_voltage_source': {
        const pp = pickPorts(c, 2)
        if (!pp) { errors.push(`${refdes}: needs 2 ports, found ${compPorts.length}`); break }
        const n1 = netOf(pp[0].source_port_id)
        const n2 = netOf(pp[1].source_port_id)
        const dc = numeric(c.voltage ?? c.voltage_source_value)
        const wf = c.waveform
        if (dc == null && (!wf || !wf.type)) {
          errors.push(`${refdes}: voltage source has neither voltage nor waveform`)
          break
        }
        let spec
        if (wf && wf.type === 'sine') {
          const off = numeric(wf.offset) ?? 0
          const amp = numeric(wf.amplitude) ?? 1
          const freq = numeric(wf.frequency) ?? 1000
          spec = `SIN(${off} ${amp} ${freq})`
        } else if (wf && wf.type === 'pulse') {
          const v1 = wf.v1 ?? 0
          const v2 = wf.v2 ?? 5
          const td = wf.td ?? 0
          const tr = wf.tr ?? '1n'
          const tf = wf.tf ?? '1n'
          const pw = wf.pw ?? '1u'
          const per = wf.per ?? '2u'
          spec = `PULSE(${v1} ${v2} ${td} ${tr} ${tf} ${pw} ${per})`
        } else {
          spec = `DC ${dc ?? 0}`
        }
        componentLines.push(`V${refdes} ${n1} ${n2} ${spec}`)
        break
      }
      case 'simple_diode': {
        const pp = pickPorts(c, 2)
        if (!pp) { errors.push(`${refdes}: needs 2 ports, found ${compPorts.length}`); break }
        const a = netOf(pp[0].source_port_id)
        const k = netOf(pp[1].source_port_id)
        const model = `DMOD_${refdes}`
        componentLines.push(`D${refdes} ${a} ${k} ${model}`)
        if (c.spice_model) {
          modelLines.push(`.model ${model} D ${c.spice_model}`)
        } else {
          modelLines.push(`.model ${model} D`)
          warnings.push(`${refdes}: no spice_model prop, using generic D`)
        }
        break
      }
      case 'simple_transistor':
      case 'simple_bjt_transistor': {
        const pp = pickPorts(c, 3)
        if (!pp) { errors.push(`${refdes}: needs 3 ports, found ${compPorts.length}`); break }
        const cN = netOf(pp[0].source_port_id)
        const bN = netOf(pp[1].source_port_id)
        const eN = netOf(pp[2].source_port_id)
        const model = `QMOD_${refdes}`
        componentLines.push(`Q${refdes} ${cN} ${bN} ${eN} ${model}`)
        if (c.spice_model) {
          modelLines.push(`.model ${model} NPN ${c.spice_model}`)
        } else {
          modelLines.push(`.model ${model} NPN`)
          warnings.push(`${refdes}: no spice_model prop, using generic NPN`)
        }
        break
      }
      case 'simple_mosfet': {
        const pp = pickPorts(c, 4)
        if (!pp) { errors.push(`${refdes}: needs 4 ports, found ${compPorts.length}`); break }
        const dN = netOf(pp[0].source_port_id)
        const gN = netOf(pp[1].source_port_id)
        const sN = netOf(pp[2].source_port_id)
        const bN = netOf(pp[3].source_port_id)
        const model = `MMOD_${refdes}`
        componentLines.push(`M${refdes} ${dN} ${gN} ${sN} ${bN} ${model}`)
        if (c.spice_model) {
          modelLines.push(`.model ${model} NMOS ${c.spice_model}`)
        } else {
          modelLines.push(`.model ${model} NMOS`)
          warnings.push(`${refdes}: no spice_model prop, using generic NMOS`)
        }
        break
      }
      default:
        warnings.push(`${c.source_component_id}: unsupported ftype "${c.ftype}", skipped`)
    }
  }

  for (const r of records) {
    if (!r || r._kerf_probe !== true) continue
    const name = r.name || r.probe_name || 'PROBE'
    const kind = r.kind === 'I' ? 'I' : 'V'
    let netOrComp
    if (kind === 'V') {
      const n = netOf(r.source_port_id)
      if (n == null) {
        warnings.push(`probe ${name}: source_port_id not resolvable`)
        continue
      }
      netOrComp = n
    } else {
      const cid = r.source_component_id
      const c = components.find((cc) => cc.source_component_id === cid)
      if (!c) {
        warnings.push(`probe ${name}: source_component_id not found`)
        continue
      }
      netOrComp = refdesOf(c)
    }
    probes.push({ name, kind, netOrComp })
  }

  const lines = []
  lines.push('* Generated by Kerf circuitToSpice — DO NOT EDIT')
  lines.push(...componentLines)
  lines.push(...modelLines)

  if (errors.length === 0) {
    const analysis = opts.analysis
    if (analysis && analysis.type === 'tran') {
      lines.push(`.tran ${analysis.tstep ?? '1u'} ${analysis.tstop ?? '1m'}`)
    } else if (analysis && analysis.type === 'dc') {
      lines.push('.op')
    } else if (analysis && analysis.type === 'op') {
      lines.push('.op')
    }
    for (const pr of probes) {
      const arg = pr.kind === 'V' ? `V(${pr.netOrComp})` : `I(${pr.netOrComp})`
      lines.push(`.print TRAN ${arg}`)
    }
  }

  lines.push('.end')
  const netlist = lines.join('\n') + '\n'

  return { netlist, probes, warnings, errors }
}
