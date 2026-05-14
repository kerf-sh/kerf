# kerf-sdk

Python SDK for [Kerf](https://kerf.app) — automate your CAD/EDA projects over HTTP/JSON-RPC.

## Install

```bash
pip install kerf-sdk
```

## Auth

Generate an API token from your workspace settings (`/w/<slug>/settings` → API Tokens), then:

```bash
export KERF_API_TOKEN=kerf_sk_...
export KERF_API_URL=https://kerf.app   # default; omit for cloud
```

## Quickstart

```python
import kerf

k = kerf.from_env()

# list files in a project
files = k.files.list(project_id="<uuid>")
for f in files:
    print(f["name"], f["kind"])

# read a script file
content = k.files.read(project_id="<uuid>", file_id="<uuid>")

# search code across the project
results = k.files.search(project_id="<uuid>", query="extrude")

# read equations
eqs = k.equations.read(project_id="<uuid>", file_id="<uuid>")
```

## API

All calls go through `POST /v1/rpc` as JSON-RPC 2.0 envelopes. The method names match Kerf's tool registry:

| Method | Description |
|--------|-------------|
| `files.list` | List project files |
| `files.read` | Read file content |
| `files.write` | Overwrite file content |
| `files.edit` | Apply a diff-style edit |
| `files.create` | Create a new file |
| `files.delete` | Delete a file |
| `files.search` | Search code across files |
| `import_step` | Import a STEP file |
| `equations.read` | Read project equations |
| `equations.set` | Set an equation value |
| `configurations.add` | Add a configuration variant |
| `configurations.set_active` | Switch active configuration |
| `revisions.list` | List file revision history |
| `revisions.restore` | Restore a previous revision |
| `docs.search` | Search Kerf documentation |

## Low-level access

```python
result = k.invoke("files.list", {"project_id": "..."})
```

## Source

Part of the [Kerf monorepo](https://github.com/kerf-sh/kerf). SDK lives at `kerf-sdk/`.

## License

MIT
