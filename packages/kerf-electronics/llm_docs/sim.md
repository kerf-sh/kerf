# kerf-electronics · sim.py

SPICE circuit simulation tools — job submission and status polling.

## LLM tools

### `run_simulation`

Enqueue a SPICE simulation job for a circuit file.

```json
{
  "circuit_file_id": "uuid",
  "analysis": {
    "type": "tran",
    "tstep": "1us",
    "tstop": "10ms"
  }
}
```

Analysis types:

| `type` | Description | Required extra fields |
|---|---|---|
| `tran` | Transient (time-domain) | `tstep`, `tstop` |
| `dc` | DC sweep | `vstart`, `vstop`, `vstep` |
| `ac` | AC frequency sweep | `fstart`, `fstop`, `points` |
| `op` | Operating point | — |

Returns immediately with a job handle:

```json
{
  "job_id": "uuid",
  "status": "queued",
  "message": "Simulation job enqueued. Poll sim_job_status(file_id) for results.",
  "circuit_file_id": "uuid"
}
```

### `sim_job_status`

Poll the status of a running or completed simulation job.

```json
{"file_id": "uuid"}
```

Returns:

```json
{
  "file_id": "uuid",
  "status": "done",
  "result": {
    "waveforms": {
      "time": [...],
      "V(out)": [...],
      "I(R1)": [...]
    }
  }
}
```

Status values: `queued`, `running`, `done`, `error`.

When `status == "error"`, the response includes an `error` key with the
failure message.

## Database schema

Jobs are persisted in the `sim_jobs` table:

```sql
sim_jobs (
  id          uuid PRIMARY KEY,
  file_id     uuid,
  project_id  uuid,
  input_spec  jsonb,       -- analysis spec JSON
  status      text,        -- queued | running | done | error
  result_json jsonb,       -- waveform results when done
  error       text,        -- error message if failed
  created_at  timestamptz,
  started_at  timestamptz,
  finished_at timestamptz
)
```

If a `queued` or `running` job already exists for a `file_id`, `run_simulation`
upserts rather than creating a duplicate.

## Error codes

| Code | Condition |
|---|---|
| `BAD_ARGS` | Missing `circuit_file_id` or `analysis.type` |
| `NOT_FOUND` | No sim job found for `file_id` |
| `ERROR` | Database insert failed |
