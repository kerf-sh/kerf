# backend/ (legacy shared code)

Transitional location. The route layer (auth, api, v1, billing, cloud, llm)
and shared infra (config, db, storage, dependencies) have moved into plugin
packages under `packages/`:

| Old `backend/...`                  | New location                          |
|------------------------------------|---------------------------------------|
| `config.py`                        | `packages/kerf-core/src/kerf_core/config.py` |
| `dependencies.py`                  | `packages/kerf-core/src/kerf_core/dependencies.py` |
| `db/`                              | `packages/kerf-core/src/kerf_core/db/` |
| `storage/`                         | `packages/kerf-core/src/kerf_core/storage/` |
| `routes/auth.py`                   | `packages/kerf-auth/src/kerf_auth/routes.py` |
| `routes/api.py`                    | `packages/kerf-api/src/kerf_api/routes.py` |
| `routes/v1.py`                     | `packages/kerf-v1/src/kerf_v1/routes.py` |
| `routes/billing.py`                | `packages/kerf-billing/src/kerf_billing/routes.py` |
| `routes/cloud.py`                  | `packages/kerf-cloud/src/kerf_cloud/routes.py` |
| `llm.py`                           | `packages/kerf-chat/src/kerf_chat/llm.py` |
| `llm_docs/`                        | `packages/kerf-chat/llm_docs/` |
| `cloud/billing/`                   | `packages/kerf-billing/src/kerf_billing/billing/` |
| `cloud/{email,fx,pricing,quota,usage}.py` | `packages/kerf-cloud/src/kerf_cloud/...` |
| `main.py` / `run.py`               | replaced by `kerf-server` (kerf-core CLI) |

## What remains

Until the next migration pass, the following sub-trees live here because
they are still imported by multiple plugins and have not yet been split:

- `tools/` — shared tool registry (`executor.py`, `registry.py`, `context.py`)
  and a long tail of tool implementations (`file_ops`, `object_ops`,
  `validation`, `scaffold`, `equations`, `configurations`, `revisions`,
  `surfacing`, `feature_draft`, `feature_mirror`, `sim`, `assembly`,
  `tolerance`, `docs`, `material`, `pcb_layer_tools`, `pcb_drc`,
  `project_layers`, `routing`, `sketch`). Imported by kerf-api, kerf-v1,
  kerf-chat, kerf-render, kerf-imports, kerf-bim, etc.
- `workers/` — `tess_worker.py` and `auto_tess_worker.py` (the bigger
  worker zoo has moved into kerf-workers and kerf-fem / kerf-cam plugins).
- `utils/encrypt.py` — used by kerf-cloud routes.
- `geom/` — geometry helpers used by some tool modules.
- `distributors/` — distributor registry, used in cloud lifecycle bootstrap.
- `tests/` — shared backend-level tests (117 passing). Still useful for
  exercising the tools layer.

`conftest.py` at the repo root puts `backend/` on `sys.path` so plugin code
can keep doing `from tools.executor import ...` etc.

## Future work

A subsequent migration pass should split `tools/` into per-plugin tool
modules (e.g. `kerf-fem` gets `tools/fem.py`, `kerf-cam` gets
`tools/cam.py`, etc.) so that `backend/` can be deleted outright.
