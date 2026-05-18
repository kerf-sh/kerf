# IEC 61131-3 Ladder Diagram (`.plc.ld`)

Ladder Diagram (LD) is the dominant graphical language for Programmable
Logic Controllers (PLCs) on the factory floor (Siemens, Allen-Bradley, Omron).
It uses a "rungs on a ladder" metaphor: **contacts** (inputs) on the left
rail drive **coils** (outputs) on the right rail, reading left-to-right like
electrical relay logic.

Kerf's `plc_ld` file kind stores LD programs as **JSON** — a structured rung
list that the backend renders as SVG and exports to IEC 61131-3 XML (`.xwl`).

---

## File kind

| Property | Value |
|---|---|
| Extension | `.plc.ld` |
| Kind | `plc_ld` |
| Storage | JSON |
| Viewer | SVG rung diagram (LadderView) + JSON source editor |
| Lint | Structural (always) + MATIEC via LD→ST transpile (graceful degrade) |
| Export | IEC 61131-3 XML (PLCopen TC6) via `export_xml` |

---

## JSON schema

```json
{
  "program": "StartStopLatch",
  "variables": [
    {"name": "start_pb",  "type": "BOOL", "dir": "input",  "comment": "Start pushbutton NO"},
    {"name": "stop_pb",   "type": "BOOL", "dir": "input",  "comment": "Stop pushbutton NC"},
    {"name": "fault",     "type": "BOOL", "dir": "input",  "comment": "Overload fault"},
    {"name": "motor_run", "type": "BOOL", "dir": "output", "comment": "Motor contactor coil"}
  ],
  "rungs": [
    {
      "label": "Rung 0",
      "comment": "Start latch — energise motor",
      "branches": [
        [
          {"type": "contact_no", "var": "start_pb"},
          {"type": "contact_nc", "var": "stop_pb"},
          {"type": "contact_nc", "var": "fault"}
        ]
      ],
      "output": {"type": "coil", "var": "motor_run"}
    }
  ]
}
```

---

## Element types

### Contacts (left-rail elements — inside `branches`)

| Type | Symbol | Meaning |
|---|---|---|
| `contact_no` | -\| \|- | Normally-open contact — passes when variable is TRUE |
| `contact_nc` | -\|/\|- | Normally-closed contact — passes when variable is FALSE |
| `contact_pos` | -\|P\|- | Positive-transition contact — passes on rising edge |
| `contact_neg` | -\|N\|- | Negative-transition contact — passes on falling edge |

Contact elements require a `"var"` key naming the BOOL variable.

### Coils (output elements — in `"output"`)

| Type | Symbol | Meaning |
|---|---|---|
| `coil` | -( )- | Standard output coil — assigns rung result to variable |
| `coil_set` | -(S)- | Set (latch) coil — sets variable to TRUE when rung energised |
| `coil_reset` | -(R)- | Reset (unlatch) coil — sets variable to FALSE when rung energised |
| `coil_pos` | -(P)- | Positive-transition coil — triggers on rising rung edge |
| `coil_neg` | -(N)- | Negative-transition coil — triggers on falling rung edge |

Coil elements require a `"var"` key.

### Function-block calls (output element — in `"output"`)

```json
{
  "type": "fb_call",
  "fb_type": "TON",
  "fb_instance": "Timer1",
  "fb_inputs": {
    "PT": "T#5s"
  }
}
```

| Key | Required | Description |
|---|---|---|
| `fb_type` | yes | Standard FB type: `TON`, `TOF`, `TP`, `CTU`, `CTD`, `CTUD`, `SR`, `RS`, `R_TRIG`, `F_TRIG` |
| `fb_instance` | yes | Instance variable name |
| `fb_inputs` | no | Additional input pin→value/variable mappings |

---

## Rung structure rules

1. **`branches`** — at least one branch (list of contact elements). Multiple
   branches are **parallel paths** (OR logic). Each branch is a list of contact
   elements in series (AND logic).
2. **`output`** — one coil or `fb_call` element. Contacts may NOT appear here;
   coils/FBs may NOT appear inside branches.
3. **`label`** — optional short name shown in the diagram header.
4. **`comment`** — optional comment shown in italics above the rung.

### Logic equivalence

```
Branches (parallel) → OR of branch conditions
Elements in branch  → AND of contact states
Output              → assigned when combined condition is TRUE
```

---

## Standard function blocks

| Name | Purpose |
|---|---|
| `TON` | On-delay timer (`IN`, `PT` → `Q`, `ET`) |
| `TOF` | Off-delay timer |
| `TP` | Pulse timer |
| `CTU` | Up counter (`CU`, `PV` → `Q`, `CV`) |
| `CTD` | Down counter |
| `CTUD` | Up/down counter |
| `SR` | Set-dominant flip-flop |
| `RS` | Reset-dominant flip-flop |
| `R_TRIG` | Rising-edge detector |
| `F_TRIG` | Falling-edge detector |

---

## Variable directions

| `dir` value | IEC 61131-3 section |
|---|---|
| `input` | `VAR_INPUT` |
| `output` | `VAR_OUTPUT` |
| `in_out` | `VAR_IN_OUT` |
| `global` | `VAR_GLOBAL` |
| `local` (default) | `VAR` |

---

## LLM tool: `create_ladder_rung`

Append a new rung to an existing (or new) ladder program:

```json
{
  "program": {
    "program": "MyLadder",
    "variables": [
      {"name": "sensor_A", "type": "BOOL", "dir": "input"},
      {"name": "valve_1",  "type": "BOOL", "dir": "output"}
    ],
    "rungs": []
  },
  "rung": {
    "label": "Rung 0",
    "comment": "Open valve when sensor active",
    "branches": [
      [{"type": "contact_no", "var": "sensor_A"}]
    ],
    "output": {"type": "coil", "var": "valve_1"}
  }
}
```

Returns:
```json
{
  "program": { "...updated program dict..." },
  "svg": "<svg ...>...</svg>",
  "errors": [],
  "warnings": []
}
```

- `program` — updated `.plc.ld` JSON; write this back to the file.
- `svg` — inline SVG preview of the full updated diagram.
- `errors` — structural validation errors that must be fixed.
- `warnings` — advisory messages (undeclared variables, MATIEC absent, etc.).

---

## Complete example — START/STOP motor latch

```json
{
  "program": "StartStopLatch",
  "variables": [
    {"name": "start_pb",  "type": "BOOL", "dir": "input",  "comment": "Start pushbutton NO"},
    {"name": "stop_pb",   "type": "BOOL", "dir": "input",  "comment": "Stop pushbutton NC"},
    {"name": "fault",     "type": "BOOL", "dir": "input",  "comment": "Overload fault"},
    {"name": "motor_run", "type": "BOOL", "dir": "output", "comment": "Motor contactor coil"}
  ],
  "rungs": [
    {
      "label": "Rung 0",
      "comment": "Start: energise motor when start pressed and not stopped/faulted",
      "branches": [
        [
          {"type": "contact_no", "var": "start_pb"},
          {"type": "contact_nc", "var": "stop_pb"},
          {"type": "contact_nc", "var": "fault"}
        ],
        [
          {"type": "contact_no", "var": "motor_run"},
          {"type": "contact_nc", "var": "stop_pb"},
          {"type": "contact_nc", "var": "fault"}
        ]
      ],
      "output": {"type": "coil", "var": "motor_run"}
    }
  ]
}
```

This encodes the classic IEC 61131-3 latching circuit:
- **Branch 0** (start rung): `start_pb AND NOT stop_pb AND NOT fault`
- **Branch 1** (seal-in rung): `motor_run AND NOT stop_pb AND NOT fault`
- The two parallel branches OR together; the result drives `motor_run`.

---

## Timer rung example

```json
{
  "label": "Rung 1",
  "comment": "5-second on-delay timer",
  "branches": [
    [{"type": "contact_no", "var": "sensor_A"}]
  ],
  "output": {
    "type": "fb_call",
    "fb_type": "TON",
    "fb_instance": "Timer1",
    "fb_inputs": {"PT": "T#5s"}
  }
}
```

---

## Export

Use the backend route `POST /api/projects/:pid/plc/export-ld` to download the
IEC 61131-3 XML (PLCopen TC6 format, `.xwl`) for import into CODESYS, OpenPLC,
or Beremiz.

---

## Lint

Lint runs in two phases:
1. **Structural** — always available, no external tool needed.
   Catches: empty branches, wrong element types, missing outputs, etc.
2. **MATIEC** — transpiles LD→ST then passes to the `iec2c` parser.
   Gracefully degrades when MATIEC is absent (returns a warning, no crash).
