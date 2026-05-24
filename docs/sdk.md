# SDK

`kerf-sdk` is a Python package (on PyPI) for automating Kerf from your own
machine. It talks to a running Kerf server over HTTP/JSON-RPC — the server can
be your local install or the hosted cloud at kerf.sh.

The SDK runs on your machine, not inside the server. You need a separate
`pip install kerf-sdk` outside the server's virtualenv.

## Install

```sh
pip install kerf-sdk
```

Requires Python 3.9+. The only runtime dependency is `httpx`.

## Auth

Generate an API token from your workspace settings
(`/w/<slug>/settings` → API Tokens), then export it:

```sh
export KERF_API_TOKEN=kerf_sk_...
export KERF_API_URL=https://kerf.sh   # omit to use the default cloud URL
```

For a local server:

```sh
export KERF_API_TOKEN=kerf_sk_...
export KERF_API_URL=http://localhost:8080
```

## Quickstart

```python
import kerf

k = kerf.from_env()

# List files in a project
files = k.files.list(project_id="<uuid>")
for f in files:
    print(f["name"], f["kind"])

# Read file content
content = k.files.read(project_id="<uuid>", file_id="<uuid>")

# Write file content
k.files.write(project_id="<uuid>", file_id="<uuid>", content='{"version":1}')

# Apply a diff-style edit
k.files.edit(
    project_id="<uuid>",
    file_id="<uuid>",
    old_string='"width": 10',
    new_string='"width": 20',
)

# Search code across a project
results = k.files.search(project_id="<uuid>", query="extrude")

# Read equations
eqs = k.equations.read(project_id="<uuid>", file_id="<uuid>")

# Set an equation
k.equations.set(project_id="<uuid>", file_id="<uuid>", name="width", expression="25")

# List revision history for a file
revisions = k.revisions.list(project_id="<uuid>", file_id="<uuid>")

# Restore a previous revision
k.revisions.restore(project_id="<uuid>", file_id="<uuid>", revision_id="<rev-uuid>")

# Search Kerf docs
results = k.docs.search(query="how to add a fillet")
```

## connect() vs from_env()

```python
# From environment variables (recommended)
k = kerf.from_env()

# Explicit token + URL
k = kerf.connect(token="kerf_sk_...", base_url="http://localhost:8080")
```

The client is a synchronous context manager:

```python
with kerf.from_env() as k:
    files = k.files.list(project_id="...")
```

## Available namespaces

| Namespace | Methods |
|-----------|---------|
| `k.files` | `list`, `read`, `write`, `edit`, `create`, `delete`, `search` |
| `k.equations` | `read`, `set` |
| `k.configurations` | `add`, `set_active` |
| `k.revisions` | `list`, `restore` |
| `k.docs` | `search` |

## Low-level invoke

All namespace methods are thin wrappers around `k.invoke()`. Call it directly
for methods not yet wrapped:

```python
result = k.invoke("files.list", {"project_id": "..."})
result = k.invoke("import_step", {"project_id": "...", "file_id": "..."})
```

## The JSON-RPC wire protocol

All calls go through `POST /v1/rpc` (provided by the `kerf-v1` plugin) as
JSON-RPC 2.0 envelopes:

```json
{
  "jsonrpc": "2.0",
  "method": "files.list",
  "params": {"project_id": "..."},
  "id": "<uuid>"
}
```

Successful response:

```json
{
  "jsonrpc": "2.0",
  "result": [...],
  "id": "<uuid>"
}
```

Error response:

```json
{
  "jsonrpc": "2.0",
  "error": {"code": -32600, "message": "..."},
  "id": "<uuid>"
}
```

`kerf.KerfError` is raised when the server returns a JSON-RPC error object.
`httpx.HTTPStatusError` is raised on non-2xx HTTP status.

The full method reference is in [v1-rpc.md](./v1-rpc.md).

## Method reference

| Method | Description |
|--------|-------------|
| `files.list` | List all files in a project (flat array of paths + metadata) |
| `files.read` | Read file content |
| `files.write` | Overwrite file content |
| `files.edit` | Apply an exact-string replacement edit |
| `files.create` | Create a new file or folder |
| `files.delete` | Delete a file (soft-delete, revision history preserved) |
| `files.search` | Search code across all files in a project |
| `import_step` | Import a STEP file (requires `kerf-cad-core` on the server) |
| `equations.read` | Read a project's equation file |
| `equations.set` | Add or update a named equation |
| `configurations.add` | Add a configuration variant to a file |
| `configurations.set_active` | Switch the active configuration |
| `revisions.list` | List revision history for a file |
| `revisions.restore` | Restore a previous revision (creates a new undo entry) |
| `docs.search` | Search the embedded LLM-docs corpus |

Heavy-compute methods (FEM solve, topology optimisation, CAM toolpath) are not
yet available over `/v1/rpc`. For those, use the REST endpoints under `/api/`
directly.

## SDK packages in other languages

Community and first-party SDKs in other languages are available:

| Kerf SDK | Language | Source |
|----------|----------|--------|
| `kerf-sdk` on PyPI | Python | `packages/kerf-sdk/` in this repo |
| `kerf-sdk-rs` on crates.io | Rust | separate repo |
| `kerf-sdk-go` on pkg.go.dev | Go | separate repo |
| `kerf-sdk-lua` on LuaRocks | Lua | separate repo |
| _(planned)_ | TypeScript | — |

All language SDKs target the same `/v1/rpc` JSON-RPC surface. The wire
protocol is identical; see [v1-rpc.md](./v1-rpc.md) for the full spec.

## OSS vs cloud

The SDK works against both OSS self-hosted instances and the hosted cloud at
kerf.sh. The only difference is the `KERF_API_URL`:

- Cloud: `https://kerf.sh` (default when `KERF_API_URL` is unset)
- Local: `http://localhost:8080`
- Self-hosted: your server's URL

Cloud-only methods (Workshop, git, billing) return a JSON-RPC error when
called against an OSS server that does not have those plugins installed.

## See also

- [v1-rpc.md](./v1-rpc.md) — full JSON-RPC wire protocol reference
- [getting-started.md](./getting-started.md) — running a local server to point the SDK at
- [local-install.md](./local-install.md) — API token generation
