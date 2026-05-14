# Wiring (.wiring) — Cable harness diagram file format

A `.wiring` file is a [WireViz](https://github.com/wireviz/WireViz) YAML
harness description.  It compiles to an SVG wiring diagram via the
`run_wireviz` LLM tool or the `POST /run-wireviz` pyworker route.

## LLM tool

```
run_wireviz(source: str, wiring_path?: str) → { svg, warnings, svg_path }
```

- `source` — the full WireViz YAML string.
- `wiring_path` — optional absolute project path (e.g. `/harness/main.wiring`);
  if provided the rendered SVG is stored as a sibling `.wiring.svg` file.

## WireViz YAML schema overview

A harness file has three top-level keys: `connectors`, `cables`, and
`connections`.

### Connectors

```yaml
connectors:
  <name>:
    type: <string>           # e.g. "Molex KK 254"
    subtype: male|female     # optional
    pincount: <int>          # total pin count
    pins: [1, 2, 3, ...]     # optional: explicit pin numbers/names
    notes: <string>          # optional
```

### Cables

```yaml
cables:
  <name>:
    wirecount: <int>         # number of conductors
    gauge: <float>           # wire gauge in mm² (optional)
    length: <float>          # cable length in metres (optional)
    color_code: DIN|IEC|Belden|Panduit  # color scheme (optional)
    colors: [BK, RD, ...]   # explicit colors per wire (optional)
    notes: <string>          # optional
```

Common DIN color codes: `BK` (black), `RD` (red), `BU` (blue), `GN` (green),
`YE` (yellow), `WH` (white), `OG` (orange), `GY` (grey), `PK` (pink),
`VT` (violet).

### Connections

```yaml
connections:
  - - <connector>: [<pin>, ...]
    - <cable>: [<wire_index>, ...]
    - <connector>: [<pin>, ...]
```

Each connection entry is a list of three elements: left connector pins, cable
wires, right connector pins.  Both sides are optional (a cable can be
left-open or right-open by omitting one side).

## Minimal example

One connector → one cable → one connector, two wires:

```yaml
connectors:
  P1:
    type: Molex KK 254
    subtype: female
    pincount: 2
    pins: [1, 2]
  P2:
    type: Molex KK 254
    subtype: male
    pincount: 2
    pins: [1, 2]

cables:
  W1:
    wirecount: 2
    gauge: 0.25
    length: 0.5
    color_code: DIN

connections:
  -
    - P1: [1, 2]
    - W1: [1, 2]
    - P2: [1, 2]
```

## Practical harness with labels and notes

```yaml
connectors:
  ECU:
    type: Bosch EV6
    subtype: female
    pincount: 4
    pins: [GND, 5V, SIG, SHLD]
    notes: Engine ECU side

  SENSOR:
    type: Deutsch DTM04-4P
    subtype: male
    pincount: 4
    pins: [A, B, C, D]
    notes: Crankshaft position sensor

cables:
  HARNESS_1:
    wirecount: 4
    gauge: 0.35
    length: 0.8
    color_code: DIN
    notes: Shielded, 4-core

connections:
  -
    - ECU: [GND, 5V, SIG, SHLD]
    - HARNESS_1: [1, 2, 3, 4]
    - SENSOR: [A, B, C, D]
```

## Licensing note

WireViz is GPLv3+.  Install the optional extra to enable rendering:

```bash
pip install kerf-wiring[wireviz]
```

See `packages/kerf-wiring/README.md` for the full licensing implications.
