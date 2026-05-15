# SPICE Model Library (`spice_lib`)

Built-in curated library of generic SPICE device models + two LLM tools to
list and assign them to components in a netlist.

> **Representative values notice** — All parameter values are generic / representative.
> They are NOT extracted from vendor datasheets and are NOT suitable for high-accuracy
> or production simulation. For those cases, replace with manufacturer-supplied `.MODEL`
> or `.SUBCKT` definitions downloaded from the vendor's website.

---

## Tools

### `list_spice_models`

List available models, optionally filtered by device family.

| Input field | Type | Required | Description |
|---|---|---|---|
| `family` | string | no | Filter: `diode`, `bjt`, `mosfet`, `opamp`, `regulator`, `passive` |

**Response:**
```json
{
  "models": [
    { "model_name": "D1N4148", "family": "diode", "description": "…" }
  ],
  "total": 23,
  "disclaimer": "…representative/generic…"
}
```

---

### `assign_spice_model`

Attach one or more models to components (by refdes) in a SPICE netlist.
Returns the updated netlist with required `.MODEL` / `.SUBCKT` blocks
injected — ready to pass directly to `run_simulation` (no other changes needed).

| Input field | Type | Required | Description |
|---|---|---|---|
| `netlist` | string | yes | SPICE `.cir` text |
| `assignments` | object | yes | `{ "D1": "D1N4148", "Q1": "Q2N3904" }` |

**Response:**
```json
{
  "netlist": "…updated netlist text…",
  "injected_models": [
    { "refdes": "D1", "model_name": "D1N4148", "family": "diode", "description": "…" }
  ],
  "disclaimer": "…representative/generic…"
}
```

Pass the returned `netlist` string directly to `run_simulation` — no edits needed.

---

## Workflow: netlist → model assignment → simulation

```
1.  list_spice_models(family="bjt")        # discover model names
2.  assign_spice_model(
        netlist = <circuit .cir text>,
        assignments = {"Q1": "Q2N3904", "D1": "D1N4148"}
    )                                       # injects .MODEL lines
3.  run_simulation(
        circuit_file_id = <id>,             # or pass netlist field directly
        analysis = {"type": "tran", "tstep": "1us", "tstop": "5ms"}
    )                                       # existing sim flow — unchanged
```

`assign_spice_model` is purely additive: it does not fork or replace the
simulator. It prepends model definitions into the netlist string that
`routes_spice.py /run-spice` (or the background `sim_jobs` worker) will
consume unchanged via ngspice batch mode.

---

## Model library

### Diodes

| Model name | Description |
|---|---|
| `D1N4148` | 1N4148 fast switching diode |
| `D1N4001` | 1N4001 rectifier, 50 V |
| `D1N4007` | 1N4007 rectifier, 1000 V |
| `DSCHOTTKY` | Generic Schottky, Vf ≈ 0.3 V at 1 A |
| `DZENER5V1` | 5.1 V Zener |
| `DZENER12V` | 12 V Zener |

### BJTs

| Model name | Description |
|---|---|
| `Q2N3904` | 2N3904 NPN small-signal |
| `Q2N3906` | 2N3906 PNP small-signal |
| `QBC547` | BC547 NPN small-signal |
| `QBC557` | BC557 PNP small-signal |

### MOSFETs

| Model name | Description |
|---|---|
| `M2N7000` | 2N7000 N-ch enhancement, 60 V / 200 mA |
| `M2P7000` | 2P7000 P-ch small-signal |
| `MIRF540` | IRF540-class N-ch power, 100 V / 28 A |
| `MIRF9540` | IRF9540-class P-ch power, -100 V / -23 A |

### Op-amps (subcircuit — pins: IN+ IN- V+ V- OUT)

| Model name | Description |
|---|---|
| `OPAMP_IDEAL` | Ideal op-amp, infinite GBW |
| `OPAMP_GBW1M` | 1 MHz GBW, LM358/LM741 class |
| `OPAMP_GBW10M` | 10 MHz GBW, TL071/TL081 class |

Instantiation example:
```spice
XU1 IN+ IN- VCC GND OUT OPAMP_GBW1M
```

### Regulators (subcircuit — behavioural)

| Model name | Pins | Description |
|---|---|---|
| `LDO_78XX` | IN GND OUT | 78xx 5 V positive LDO |
| `LDO_79XX` | IN GND OUT | 79xx -5 V negative LDO |
| `LDO_ADJ` | IN ADJ OUT | Adjustable LDO, 1.25 V ref (LM317 class) |

### Passives with parasitics (subcircuits — pins: P N)

| Model name | Description |
|---|---|
| `CAP_ELEC_100U` | 100 µF electrolytic, ESR=0.1 Ω, ESL=10 nH |
| `CAP_X7R_100N` | 100 nF ceramic X7R, ESR=0.01 Ω, ESL=1 nH |
| `IND_10U` | 10 µH inductor, DCR=0.05 Ω, SRF=100 MHz |

Passive subcircuit instantiation example:
```spice
XC1 net_a GND CAP_ELEC_100U
XL1 net_b net_c IND_10U
```

---

## SPICE syntax notes

- `.MODEL` devices (diodes, BJTs, MOSFETs) are referenced by their model name
  in the element line, e.g. `D1 anode cathode D1N4148`.
- `.SUBCKT` devices (op-amps, regulators, passives) are instantiated with `X`
  prefix and the subcircuit name last, e.g. `XU1 ... OPAMP_GBW1M`.
- `assign_spice_model` injects definitions after the netlist title line,
  before any element lines, so ngspice resolves them at parse time.
- Duplicate model definitions are suppressed — calling `assign_spice_model`
  on a netlist that already contains a model does not create duplicates.
