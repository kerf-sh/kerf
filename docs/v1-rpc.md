# Scripting Kerf with the HTTP API

All Kerf operations are available over HTTP. The primary interface for
scripting, automation, and third-party tooling is the JSON-RPC endpoint at
`POST /v1/rpc`. A friendlier Python wrapper is the [kerf-sdk](./sdk.md).

This page focuses on **how to use the API** — from getting a token to common
scripting patterns. For a complete method listing see the
[Reference section](#reference) below.

---

## OSS vs Cloud

The v1 RPC endpoint is part of the MIT `kerf-v1` plugin and works on both
self-hosted and cloud instances. The URL is the only thing that changes:

| Kerf install | Base URL |
|--------------|----------|
| Local dev (default) | `http://localhost:8080` |
| Self-hosted server | Your server's URL |
| Kerf Cloud | `https://kerf.sh` |

Cloud-only methods (Workshop, hosted git) return a JSON-RPC error when called
against an OSS server that does not have those plugins installed.

---

## Getting started: authenticate

### Generate an API token (recommended)

1. Open **Settings → API Tokens** in the Kerf UI
   (`/w/<workspace>/settings` or `/settings` on a local install).
2. Click **New token**, give it a name, copy the `kerf_sk_…` value.
3. Export it:

```sh
export KERF_API_TOKEN=kerf_sk_...
```

Use the token as a Bearer header on every request:

```sh
curl -X POST http://localhost:8080/v1/rpc \
  -H "Authorization: Bearer $KERF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"files.list","params":{"project_id":"<uuid>"},"id":1}'
```

### Session token (email + password)

If you need a session token programmatically (e.g. in tests):

```sh
curl -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"secret"}'
# → {"access_token":"eyJ…","refresh_token":"…","user":{…}}
```

Pass the `access_token` as the Bearer value. API tokens are preferred for
automation — session tokens expire.

---

## Common scripting patterns

### List and read files in a project

```python
import os, requests

BASE = os.getenv("KERF_API_URL", "http://localhost:8080")
TOKEN = os.environ["KERF_API_TOKEN"]
headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def rpc(method, params):
    r = requests.post(f"{BASE}/v1/rpc", headers=headers,
                      json={"jsonrpc": "2.0", "method": method, "params": params, "id": 1})
    r.raise_for_status()
    data = r.json()
    if "error" in data:
        raise RuntimeError(data["error"])
    return data["result"]

project_id = "<your-project-uuid>"

files = rpc("files.list", {"project_id": project_id})
for f in files:
    print(f["name"], f["kind"])
```

### Edit a file (find-and-replace)

```python
rpc("files.edit", {
    "project_id": project_id,
    "file_id": "<file-uuid>",
    "old_str": '"width": 10',
    "new_str": '"width": 20',
})
```

### Drive parametric equations

```python
# Read current equations
eqs = rpc("equations.read", {"project_id": project_id, "file_id": "<file-uuid>"})

# Set a dimension
rpc("equations.set", {
    "project_id": project_id,
    "file_id": "<file-uuid>",
    "name": "wall_thickness",
    "value": "3.5",
})
```

### Import a STEP file

```python
import base64, pathlib

step_bytes = pathlib.Path("bracket.step").read_bytes()
rpc("import_step", {
    "project_id": project_id,
    "name": "bracket.step",
    "content": base64.b64encode(step_bytes).decode(),
})
```

### Use revision history for undo

```python
# List revisions for a file
revs = rpc("revisions.list", {"project_id": project_id, "file_id": "<file-uuid>"})
oldest_rev = revs[-1]["revision_id"]

# Restore
rpc("revisions.restore", {
    "project_id": project_id,
    "revision_id": oldest_rev,
})
```

---

## Using the Python SDK instead

For Python scripts the [kerf-sdk](./sdk.md) wraps every method above and
handles auth, base URL, and error raising for you:

```sh
pip install kerf-sdk
export KERF_API_TOKEN=kerf_sk_...
```

```python
import kerf

k = kerf.from_env()
files = k.files.list(project_id="<uuid>")
k.equations.set(project_id="<uuid>", file_id="<uuid>", name="depth", expression="12")
```

---

## Reference

### Endpoint

```
POST /v1/rpc
Authorization: Bearer <token>
Content-Type: application/json
```

Request envelope:

```json
{"jsonrpc": "2.0", "method": "files.list", "params": {…}, "id": 1}
```

Success response:

```json
{"jsonrpc": "2.0", "result": {…}, "id": 1}
```

Error response:

```json
{"jsonrpc": "2.0", "error": {"code": -32601, "message": "method not found"}, "id": 1}
```

### Standard error codes

| Code | Meaning |
|------|---------|
| -32700 | Parse error — invalid JSON |
| -32600 | Invalid request — malformed envelope |
| -32601 | Method not found |
| -32602 | Invalid params |
| -32603 | Internal error |

### Method index

| Kerf method | Params | Returns |
|-------------|--------|---------|
| `files.list` | `project_id` | `[{file_id, name, kind, parent_id, …}]` |
| `files.read` | `project_id`, `file_id` | `{content, id, name, kind, …}` |
| `files.write` | `project_id`, `file_id`, `content` | `{ok: true}` |
| `files.edit` | `project_id`, `file_id`, `old_str`, `new_str` | `{ok: true}` |
| `files.create` | `project_id`, `name`, `kind`, `parent_id?` | `{id, name, kind, …}` |
| `files.delete` | `project_id`, `file_id` | `{ok: true}` |
| `files.search` | `project_id`, `query` | `[{file_id, snippet, line_number, …}]` |
| `import_step` | `project_id`, `name`, `content` (base64) | `{id, name, kind, …}` |
| `equations.read` | `project_id`, `file_id` | `{equations: […]}` |
| `equations.set` | `project_id`, `file_id`, `name`, `value` | `{ok: true}` |
| `configurations.add` | `project_id`, `name` | `{id, name, is_active, …}` |
| `configurations.set_active` | `project_id`, `config_id` | `{ok: true}` |
| `revisions.list` | `project_id`, `file_id?` | `[{revision_id, file_id, created_at, …}]` |
| `revisions.restore` | `project_id`, `revision_id` | `{ok: true}` |
| `docs.search` | `query` | `[{title, snippet, url}]` |

### Available tools endpoint

```
GET /v1/tools
Authorization: Bearer <token>
```

Returns the tool registry filtered to your role:

```json
{"tools": [{"name": "feature_fillet", "description": "…"}, …]}
```

---

## See also

- [sdk.md](./sdk.md) — Python SDK (higher-level wrapper)
- [getting-started.md](./getting-started.md) — run a local server
- [local-install.md](./local-install.md) — API token generation
