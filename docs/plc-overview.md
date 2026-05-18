---
title: "Industrial controls in Kerf"
group: reference
order: 53
---

# Industrial controls in Kerf

The `kerf-plc` package adds a full IEC 61131-3 Structured Text (ST) authoring and validation workflow to Kerf. Write ladder logic and ST programs, lint them against the MATIEC parser, simulate a soft-PLC scan cycle, and generate HMI data-binding from variable declarations — all from inside a Kerf project.

---

## What is kerf-plc?

`kerf-plc` is an MIT-licensed plugin that ships:

| Component | What it provides |
|-----------|-----------------|
| **ST editor** | Monaco IDE with the `iec61131-st` custom language grammar — syntax highlighting, bracket matching, folding |
| **MATIEC lint** | Parses `.plc.st` files via the `iec2c` subprocess; returns structured per-location diagnostics |
| **Soft-PLC simulator** | In-process scan-cycle runner for logic testing without hardware |
| **HMI generator** | Reads `VAR_GLOBAL` / `VAR_INPUT` / `VAR_OUTPUT` declarations and produces an HMI data-binding schema |
| **File kind** | `plc_st` for `.plc.st` files — revision history, LLM-editable, project tree integration |

---

## IEC 61131-3 primer

IEC 61131-3 defines five programming languages for PLCs. Kerf focuses on **Structured Text (ST)** and conceptually maps **Ladder Diagram (LD)** logic onto ST when importing.

### The five IEC 61131-3 languages

| Language | Abbreviation | Style | Kerf support |
|----------|-------------|-------|--------------|
| Structured Text | ST | Pascal-like textual | Full — native `.plc.st` |
| Ladder Diagram | LD | Relay-rung graphical | Import-only (converted to ST) |
| Function Block Diagram | FBD | Data-flow boxes | Planned |
| Sequential Function Chart | SFC | State-machine flowchart | Planned |
| Instruction List | IL | Assembly-style | Deprecated in IEC 61131-3:2013; not supported |

### Program Organisation Units (POUs)

Everything in a PLC program lives inside a POU:

| POU | Keyword | Memory | Returns |
|-----|---------|--------|---------|
| Function | `FUNCTION … END_FUNCTION` | None — stateless | One value |
| Function Block | `FUNCTION_BLOCK … END_FUNCTION_BLOCK` | Instance state | Via VAR_OUTPUT |
| Program | `PROGRAM … END_PROGRAM` | Scan-cycle root | — |

### Variable sections at a glance

```st
VAR                 (* Local to this POU *)
VAR_INPUT           (* Caller provides; read-only inside POU *)
VAR_OUTPUT          (* POU writes; caller reads *)
VAR_IN_OUT          (* Caller and POU both read and write *)
VAR_GLOBAL          (* Global scope — visible everywhere *)
VAR_EXTERNAL        (* Declare a VAR_GLOBAL for use here *)
VAR_TEMP            (* Temporary — not retained across scan *)
END_VAR
```

### Standard data types

| Category | Types |
|----------|-------|
| Boolean | `BOOL` |
| Integer (signed) | `SINT` (8-bit), `INT` (16-bit), `DINT` (32-bit), `LINT` (64-bit) |
| Integer (unsigned) | `USINT`, `UINT`, `UDINT`, `ULINT` |
| Floating-point | `REAL` (32-bit), `LREAL` (64-bit) |
| Time | `TIME`, `DATE`, `TIME_OF_DAY` (`TOD`), `DATE_AND_TIME` (`DT`) |
| String | `STRING`, `WSTRING` |
| Bit string | `BYTE`, `WORD`, `DWORD`, `LWORD` |
| Arrays | `ARRAY [lo..hi] OF type` |
| Structures | `TYPE name : STRUCT … END_STRUCT END_TYPE` |
| Enumerations | `TYPE name : (val1, val2, …) END_TYPE` |

### Control flow

```st
(* Conditional *)
IF motor_on AND NOT fault THEN
  output := 1;
ELSIF standby THEN
  output := 0;
ELSE
  output := last_output;
END_IF

(* Case *)
CASE mode OF
  0: run_normal();
  1: run_diagnostic();
ELSE
  run_safe_state();
END_CASE

(* FOR loop *)
FOR i := 1 TO 10 BY 1 DO
  accumulator := accumulator + data[i];
END_FOR

(* WHILE loop *)
WHILE NOT buffer_empty DO
  process_next();
END_WHILE
```

### Standard function blocks (IEC stdlib)

| Block | Purpose | Key vars |
|-------|---------|----------|
| `TON` | On-delay timer | `IN`, `PT` (preset time) → `Q` (output), `ET` (elapsed) |
| `TOF` | Off-delay timer | `IN`, `PT` → `Q`, `ET` |
| `TP` | Pulse timer | `IN`, `PT` → `Q`, `ET` |
| `SR` | Set-Reset flip-flop | `S1`, `R` → `Q1` |
| `RS` | Reset-Set flip-flop | `S`, `R1` → `Q1` |
| `CTU` | Up counter | `CU`, `R`, `PV` → `Q`, `CV` |
| `CTD` | Down counter | `CD`, `LD`, `PV` → `Q`, `CV` |
| `CTUD` | Up/Down counter | `CU`, `CD`, `R`, `LD`, `PV` → `QU`, `QD`, `CV` |
| `R_TRIG` | Rising-edge detector | `CLK` → `Q` (pulses one scan) |
| `F_TRIG` | Falling-edge detector | `CLK` → `Q` (pulses one scan) |

---

## Workflow

### 1. Create a PLC file

```
New file → PLC Program (Structured Text)
```

Or ask the LLM:

> "Create a START/STOP motor latch program in Structured Text."

`plc_scaffold` writes a `.plc.st` file with VAR declarations and a stub program body. The file opens in Monaco with full ST syntax highlighting.

### 2. Write and lint

Edit in Monaco directly, or via the assistant. After saving, Kerf automatically runs `run_plc_lint` — structured diagnostics appear in the Monaco editor gutter:

```json
{
  "diagnostics": [
    { "severity": "error", "line": 12, "column": 5,
      "message": "Undeclared variable 'pressure_raw'", "source": "matiec" }
  ],
  "warnings": []
}
```

Diagnostics map to red/yellow squiggles in the editor and show in the Problems panel.

### 3. Simulate

Run the soft-PLC simulator for logic testing:

```
"Simulate 5 scan cycles with start_pb=TRUE and stop_pb=FALSE."
```

`plc_simulate` compiles the ST program to an in-process execution model, runs the specified number of scan cycles with the given input values, and returns a scan-by-scan trace of all variable values. No hardware required.

### 4. Generate HMI data binding

From your variable declarations, generate an HMI schema:

```
"Generate an HMI data-binding schema from the motor control program."
```

`plc_generate_hmi` reads `VAR_INPUT`, `VAR_OUTPUT`, and `VAR_GLOBAL` declarations and produces a JSON data-binding schema your HMI tool can consume. The schema includes variable name, type, address hint, and read/write direction.

---

## Classic patterns

### START/STOP latch (the PLC "hello world")

```st
PROGRAM StartStopLatch

VAR_INPUT
  start_pb  : BOOL;   (* Momentary push-button NO *)
  stop_pb   : BOOL;   (* Momentary push-button NC, inverted *)
  fault     : BOOL;   (* Overload relay contact *)
END_VAR

VAR_OUTPUT
  motor_run : BOOL;   (* Contactor coil *)
END_VAR

IF (start_pb AND NOT stop_pb AND NOT fault) THEN
  motor_run := TRUE;
END_IF

IF (stop_pb OR fault) THEN
  motor_run := FALSE;
END_IF

END_PROGRAM
```

### On-delay timer — spray nozzle purge

```st
PROGRAM NozzlePurge

VAR
  purge_timer : TON;
END_VAR
VAR_INPUT
  enable_purge : BOOL;
END_VAR
VAR_OUTPUT
  nozzle_open : BOOL;
END_VAR

purge_timer(IN := enable_purge, PT := T#3s);
nozzle_open := purge_timer.Q;

END_PROGRAM
```

### Counter — batch fill

```st
PROGRAM BatchFill

VAR
  fill_count : CTU;
END_VAR
VAR_INPUT
  sensor_pulse : BOOL;   (* Rising edge = one unit filled *)
  reset_batch  : BOOL;
END_VAR
VAR_OUTPUT
  batch_complete : BOOL;
END_VAR

fill_count(CU := sensor_pulse, R := reset_batch, PV := 100);
batch_complete := fill_count.Q;

END_PROGRAM
```

---

## LLM tool summary

| Tool | Read/Write | What it does |
|------|-----------|--------------|
| `plc_scaffold` | write | Create a starter `.plc.st` file for a described program |
| `run_plc_lint` | read | Lint a `.plc.st` source via MATIEC; return structured diagnostics |
| `plc_simulate` | write | Simulate scan cycles with given inputs; return variable traces |
| `plc_generate_hmi` | read | Generate HMI data-binding schema from variable declarations |
| `plc_read_vars` | read | List all declared variables and their types |
| `plc_explain_fb` | read | Explain how a standard function block behaves |

---

## MATIEC install

MATIEC (`iec2c`) is a GPLv3 IEC 61131-3 compiler. Kerf invokes it as a subprocess — no in-process linking, so the Kerf binary stays MIT-licensed.

```bash
# Debian / Ubuntu
apt install matiec

# Build from source
git clone https://github.com/thiagoralves/OpenPLC_v3.git
cd OpenPLC_v3/utils/matiec_src
make
sudo cp iec2c /usr/local/bin/
```

If `iec2c` is not found on `$PATH`, lint calls return `warnings: ["MATIEC not installed — lint unavailable"]` and zero diagnostics. The editor still works; only the lint squiggles are absent.

Override the timeout: `MATIEC_TIMEOUT=10` (seconds, default 5).

---

## Capability tags

| Tag | What it enables |
|-----|----------------|
| `plc.st` | ST editor + file kind (always available) |
| `plc.lint` | MATIEC lint (needs `iec2c` on `$PATH`) |
| `plc.simulate` | Soft-PLC scan-cycle simulator |
| `plc.hmi` | HMI data-binding generator |

---

## Example prompts

```
"Create a Structured Text program for a conveyor belt with two photoelectric sensors."
"Lint the program and explain each error."
"Simulate 10 scan cycles with the start button pressed."
"Add a 2-second on-delay before the motor starts."
"Generate an HMI schema from the variable declarations."
"Explain how the TON timer works and show me an example."
```

---

## See also

- [llm-tools-catalogue.md](./llm-tools-catalogue.md) — full LLM tool index
- [file-types.md](./file-types.md) — extension registry including `.plc.st`
- [electronics.md](./electronics.md) — PCB + schematic workflows
