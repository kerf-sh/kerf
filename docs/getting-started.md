# Getting started

From a fresh clone to a running Kerf server in about five minutes.

## Prerequisites

| Tool | Minimum version |
|------|-----------------|
| Python | 3.11 |
| Node.js | 22 |
| Postgres | 14 |
| npm | 10 (ships with Node 22) |

## 1. Clone the repo

```sh
git clone https://github.com/kerf-sh/kerf
cd kerf
```

## 2. Create the database

```sh
# Postgres must already be running locally.
createdb kerf
```

If your local Postgres role differs from your system username (e.g. you connect
as `pc` not `postgres`), set the URL before proceeding:

```sh
export DATABASE_URL=postgres://pc@localhost:5432/kerf?sslmode=disable
```

## 3. Install Python dependencies

Choose the smallest persona that covers your work. `mech` is a good default for
mechanical CAD; use `full` if you want everything:

```sh
pip install -e .[mech]      # mechanical CAD stack (CAD, FEM, CAM, topology, mates)
# or
pip install -e .[full]      # everything: mech + electronics + bim + cloud plugins
```

See [persona-bundles.md](./persona-bundles.md) for the full menu and what each persona installs.

## 4. Install Node dependencies

```sh
npm install
```

## 5. Initialise configuration

```sh
npm run init    # writes kerf.toml from kerf.example.toml (skip if it already exists)
```

Open `kerf.toml` and set at least one LLM API key:

```toml
[llm.anthropic]
api_key = "sk-ant-..."   # or [llm.openai], [llm.moonshot], [llm.gemini]
```

The config defaults (`local_mode = true`, `storage.backend = "local"`) are
correct for a local dev run — you do not need to change anything else.

## 6. Run database migrations

```sh
kerf-server --migrate
# or equivalently:
npm run migrate
```

This applies every SQL migration under
`packages/kerf-core/src/kerf_core/db/migrations/` in order.

## 7. Start the server

**Development mode** (Vite dev server on `:5173` + kerf-server on `:8080`,
both with hot-reload):

```sh
npm run dev
```

Open <http://localhost:5173>.

**Production / single-binary mode** (serves the pre-built SPA from `:8080`):

```sh
npm run build      # compile the Vite SPA into dist/
kerf-server        # serves dist/ + API on http://localhost:8080
```

On first load `local_mode = true` auto-creates a singleton user and signs you
in without a login screen.

## Verifying the server is healthy

```sh
curl http://localhost:8080/healthz
# → {"status":"ok"}

curl http://localhost:8080/health/capabilities
# → {"plugins":[...], "capabilities":["api.rest","cad.brep-mesh",...]}
```

The capabilities endpoint shows every loaded plugin and its provided tags.

## Configuration quick reference

The full schema is in `kerf.example.toml`. The most useful knobs for local dev:

| Setting | Default | Notes |
|---------|---------|-------|
| `[server].local_mode` | `true` | Auto-login; no register/login screen |
| `[server].port` | `8080` | HTTP port |
| `[database].url` | `postgres://postgres:postgres@localhost:5432/kerf` | Override via `DATABASE_URL` env var |
| `[llm.anthropic].api_key` | _(empty)_ | Set this to activate the default model |
| `[storage].backend` | `"local"` | `"local"` / `"s3"` / `"filesystem"` |
| `[limits].file_revisions_max` | `200` | Per-file undo history cap |

Config is read from the first file found in this order:
`--config` flag → `KERF_CONFIG` env → `./kerf.toml` → `~/.config/kerf/config.toml` → `/etc/kerf/config.toml`.

## CLI flags

```
kerf-server [--config PATH] [--host HOST] [--port PORT] [--reload] [--workers N]
```

| Flag | Default | Env override |
|------|---------|-------------|
| `--config` | `""` (uses search order above) | `KERF_CONFIG` |
| `--host` | `0.0.0.0` | `KERF_HOST` |
| `--port` | `8080` | `KERF_PORT` |
| `--reload` | off | — |
| `--workers` | `1` | — |

## Next steps

- Persona bundles explained — [persona-bundles.md](./persona-bundles.md)
- Local self-hosting in depth — [local-install.md](./local-install.md)
- Config file schema — [configuration.md](./configuration.md)
- Docker / production deployment — [deployment.md](./deployment.md)
- Writing a plugin — [plugins-development.md](./plugins-development.md)
- Scripting with the Python SDK — [sdk.md](./sdk.md)
