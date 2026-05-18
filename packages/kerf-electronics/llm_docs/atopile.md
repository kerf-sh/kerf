# atopile LLM Authoring — Generate `.ato` from a Prompt

Kerf provides a deterministic `.ato` synthesizer that converts a short English
circuit description into a syntactically-valid
[atopile](https://atopile.io) source module.

## When to use

Use `make_atopile` when a user describes a basic passive circuit and you need
to emit ready-to-use `.ato` source code, for example:

- "generate a voltage divider in atopile"
- "create an RC low-pass filter at 1 kHz"
- "write an LED driver circuit for 20 mA"
- "add a 4.7 kΩ pull-up resistor"

## Tool

| Function | Purpose |
|---|---|
| `make_atopile(spec)` | Accepts a plain-English spec string; returns a complete `.ato` module as a string |

## Supported patterns

| Spec pattern | Circuit generated |
|---|---|
| `"voltage divider"` | Two-resistor divider: vin → R1 (10 kΩ) → vout → R2 (10 kΩ) → gnd |
| `"RC low-pass <freq>"` | RC low-pass: R = 10 kΩ, C sized for fc; e.g. `"RC low-pass 10kHz"` |
| `"LED driver <current>"` | LED + current-limit resistor; Ohm's law: R = (5V − 2V) / I; e.g. `"LED driver 20mA"` |
| `"pull-up resistor <value>"` | Single resistor from signal to VCC; e.g. `"pull-up resistor 4.7kΩ"` |

### Frequency suffixes
`Hz`, `kHz`, `MHz` (case-insensitive).  If no suffix is provided, Hz is assumed.

### Resistance suffixes
`Ω`, `ohm`, `ohms`, `kΩ`, `kohm`, `kohms`, `MΩ`, `Mohm`.

### Current suffixes
`mA`, `A`.  If no suffix is provided, A is assumed.

## Example

**User ask:** "Generate an atopile module for an RC low-pass filter at 10 kHz."

```python
from kerf_electronics.atopile.llm import make_atopile

ato_src = make_atopile("RC low-pass 10kHz")
print(ato_src)
```

Output (approximate):

```
# RC low-pass filter  fc = 10kHz  (R=10kΩ, C=1.592nF)
module RCLowPass:
    # cutoff_frequency = "10kHz"

    r1 = new Resistor
    r1.value = "10kΩ"
    r1.footprint = "R_0402"

    c1 = new Capacitor
    c1.value = "1.592nF"
    c1.footprint = "C_0402"

    net vin ~ r1.p1
    net vout ~ r1.p2
    net vout ~ c1.p1
    net gnd ~ c1.p2
```

**User ask:** "Write a 20 mA LED driver circuit."

```python
ato_src = make_atopile("LED driver 20mA")
```

Component sizing: R = (5 V − 2 V) / 0.02 A = **150 Ω**.

## Error handling

`make_atopile` raises `UnknownSpecError` (a subclass of `ValueError`) when the
spec string does not match any supported pattern.  It raises `ValueError` when
a numeric parameter (frequency, resistance, current) cannot be parsed.

```python
from kerf_electronics.atopile.llm import make_atopile, UnknownSpecError

try:
    src = make_atopile("mystery circuit")
except UnknownSpecError as exc:
    print(f"Unknown spec: {exc}")
```

## Validation

Every emitted `.ato` string is validated by a minimal regex grammar that checks
for the presence of a `module`/`component` block, `new` component
instantiations, attribute assignments, and `net` connections.  When the
`kerf_electronics.atopile.parser` module is available (T-194), the output is
also round-tripped through its `parse()` function.
