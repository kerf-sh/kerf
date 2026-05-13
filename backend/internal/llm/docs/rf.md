# RF S-Parameter Analysis

Kerf can run S-parameter analysis on Touchstone (.sNp) files using scikit-rf.
The analysis produces Smith charts, VSWR, return loss, and insertion loss plots.

## Workflow

1. Upload a Touchstone file via `POST /api/projects/{pid}/files` with content_type `application/touchstone` or as raw binary.
2. Call `import_touchstone` with the file UUID and a name to create a `.rf-study` file.
3. Call `run_rf_study` with the `.rf-study` file UUID to queue the analysis.
4. Poll `rf_job_status` with the same file UUID until `status` is `done` or `error`.
5. On `done`, the `result` object contains the full S-parameter analysis.

## `import_touchstone` tool

```
touchstone_file_id   UUID of the uploaded Touchstone file (required)
name                 Name for the new .rf-study file (required)
port_impedance       Reference impedance in ohms (optional, default 50)
```

## `run_rf_study` tool

```
file_id              UUID of the .rf-study file (required)
port_impedance       Reference impedance in ohms for renormalization (optional, default 50)
freq_unit            Frequency unit: "Hz" | "kHz" | "MHz" | "GHz" (optional, default "GHz")
```

### Analysis performed

- **VSWR** — Voltage Standing Wave Ratio at each frequency point
- **Return Loss (dB)** — S11 magnitude in dB
- **Insertion Loss (dB)** — S21 magnitude in dB for 2-port devices
- **Smith Chart** — SVG rendering of S11 on the normalized impedance plane

## `rf_job_status` tool

```
file_id   UUID of the .rf-study file to poll (required)
```

Returns:

```json
{
  "file_id": "<uuid>",
  "status": "queued" | "running" | "done" | "error",
  "result": {
    "status": "done",
    "frequency_range": [1.0, 2.0, 3.0, ...],
    "frequency_unit": "GHz",
    "port_impedance": 50.0,
    "num_ports": 2,
    "num_points": 201,
    "vswr": [1.02, 1.05, 1.10, ...],
    "return_loss_db": [-35.0, -30.0, -25.0, ...],
    "insertion_loss_db": [-0.1, -0.2, -0.3, ...],
    "smith_chart_svg": "<svg>...</svg>",
    "warnings": [],
    "errors": []
  },
  "error": "..." // only when status == "error"
}
```

## `.rf-study` file format

```json
{
  "version": 1,
  "name": "filter",
  "source_file": "filter.s2p",
  "port_impedance": 50.0,
  "frequency_unit": "GHz",
  "touchstone_b64": "<base64-encoded .sNp data>",
  "results": {
    "status": "pending" | "running" | "done" | "error",
    "frequency_range": [...],
    "vswr": [...],
    "return_loss_db": [...],
    "insertion_loss_db": [...],
    "smith_chart_svg": "...",
    "warnings": [],
    "errors": []
  }
}
```

## REST endpoint

```
POST /api/projects/{pid}/files/{fid}/rf
```

Body:

```json
{
  "port_impedance": 50.0,
  "freq_unit": "GHz"
}
```

Response `202 Accepted`:

```json
{"job_id": "<uuid>", "status": "queued"}
```

## Smith chart

The Smith chart SVG is rendered server-side via matplotlib's `skrf` backend.
It shows S11 on the normalized impedance plane with:
- Constant resistance circles (real part)
- Constant reactance arcs
- The unit conductance line
- S11 trajectory colored by frequency

## Notes

- scikit-rf (`skrf`) handles Touchstone parsing, renormalization, and Network operations.
- The pyworker route uses `skrf.Network` to load touchstone data and compute S-parameters.
- Smith chart rendering uses matplotlib with `skrf.plotting` or direct `matplotlib` drawing.
- Frequencies are stored as a list; the number of points matches the original touchstone data.
- For multi-port devices (>2 ports), S11 and S21 are reported; full S-matrix is available in the raw result.
