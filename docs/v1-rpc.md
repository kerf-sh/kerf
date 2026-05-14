# Kerf v1 JSON-RPC API

## Overview

The v1 JSON-RPC endpoint provides a unified RPC interface for all Kerf operations. Use this endpoint when you need to:

- Perform file operations (list, read, write, edit, delete, search)
- Manage equations, configurations, and revisions
- Search documentation
- Import STEP files

For simple REST operations on projects, users, and billing, use the standard REST endpoints under `/api/*`.

**Endpoint:** `POST /v1/rpc`

## Authentication

All requests require a Bearer token in the `Authorization` header:

```
Authorization: Bearer <token>
```

### Getting a Token

**Email/Password** — `POST /auth/login`

```json
{"email": "user@example.com", "password": "password"}
```

Response:
```json
{
  "access_token": "eyJ...",
  "refresh_token": "...",
  "user": {...},
  "default_workspace": {...}
}
```

**API Token** — Generate from the Settings page, then use as Bearer token directly.

## Request Format

```json
{
  "jsonrpc": "2.0",
  "method": "files.list",
  "params": {
    "project_id": "550e8400-e29b-41d4-a716-446655440000"
  },
  "id": 1
}
```

## Response Format

**Success:**
```json
{
  "jsonrpc": "2.0",
  "result": {...},
  "id": 1
}
```

**Error:**
```json
{
  "jsonrpc": "2.0",
  "error": {
    "code": -32601,
    "message": "method not found: files.list"
  },
  "id": 1
}
```

## Standard Error Codes

| Code | Meaning |
|------|---------|
| -32700 | Parse error — invalid JSON |
| -32600 | Invalid request — malformed envelope |
| -32601 | Method not found — unknown method |
| -32602 | Invalid params — missing or malformed parameters |
| -32603 | Internal error — server-side failure |

## Supported Methods

### files.list
List all files in a project.
```json
{"method": "files.list", "params": {"project_id": "..."}}
```
Result: `[{file_id, name, kind, parent_id, created_at, ...}]`

### files.read
Read a file's content.
```json
{"method": "files.read", "params": {"project_id": "...", "file_id": "..."}}
```
Result: `{content, id, name, kind, ...}`

### files.write
Overwrite a file's content.
```json
{"method": "files.write", "params": {"project_id": "...", "file_id": "...", "content": "..."}}
```
Result: `{ok: true}`

### files.edit
Replace a string within a file (atomic find-replace).
```json
{"method": "files.edit", "params": {"project_id": "...", "file_id": "...", "old_str": "...", "new_str": "..."}}
```
Result: `{ok: true}`

### files.create
Create a new file.
```json
{"method": "files.create", "params": {"project_id": "...", "name": "new_file.py", "kind": "source", "parent_id": "..."}}
```
Result: `{id, name, kind, parent_id, ...}`

### files.delete
Delete a file.
```json
{"method": "files.delete", "params": {"project_id": "...", "file_id": "..."}}
```
Result: `{ok: true}`

### files.search
Search file contents.
```json
{"method": "files.search", "params": {"project_id": "...", "query": "search term"}}
```
Result: `[{file_id, snippet, line_number, ...}]`

### import_step
Import a STEP CAD file.
```json
{"method": "import_step", "params": {"project_id": "...", "name": "part.step", "content": "<base64>"}}
```
Result: `{id, name, kind, ...}`

### equations.read
Read equations for a file.
```json
{"method": "equations.read", "params": {"project_id": "...", "file_id": "..."}}
```
Result: `{equations: [...]}`

### equations.set
Set an equation value.
```json
{"method": "equations.set", "params": {"project_id": "...", "file_id": "...", "name": "x", "value": "10"}}
```
Result: `{ok: true}`

### configurations.add
Add a configuration.
```json
{"method": "configurations.add", "params": {"project_id": "...", "name": "Config 1"}}
```
Result: `{id, name, is_active, ...}`

### configurations.set_active
Set the active configuration.
```json
{"method": "configurations.set_active", "params": {"project_id": "...", "config_id": "..."}}
```
Result: `{ok: true}`

### revisions.list
List revisions for a file (or all files if file_id omitted).
```json
{"method": "revisions.list", "params": {"project_id": "...", "file_id": "..."}}
```
Result: `[{revision_id, file_id, created_at, ...}]`

### revisions.restore
Restore a file to a specific revision.
```json
{"method": "revisions.restore", "params": {"project_id": "...", "revision_id": "..."}}
```
Result: `{ok: true}`

### docs.search
Search Kerf documentation.
```json
{"method": "docs.search", "params": {"query": "assemblies"}}
```
Result: `[{title, snippet, url}]`

## GET /v1/tools

Returns available tools for the authenticated user (filtered by role).

**Endpoint:** `GET /v1/tools`

Response:
```json
{
  "tools": [
    {"name": "list_files", "description": "...", ...},
    ...
  ]
}
```

## Full Examples

### cURL — List Files

```bash
curl -X POST http://localhost:8080/v1/rpc \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "files.list",
    "params": {"project_id": "550e8400-e29b-41d4-a716-446655440000"},
    "id": 1
  }'
```

### Python — Full Example

```python
import requests

BASE_URL = "http://localhost:8080"

# 1. Get a token
resp = requests.post(f"{BASE_URL}/auth/login", json={
    "email": "user@example.com",
    "password": "secret"
})
resp.raise_for_status()
token = resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 2. List files
resp = requests.post(f"{BASE_URL}/v1/rpc", headers=headers, json={
    "jsonrpc": "2.0",
    "method": "files.list",
    "params": {"project_id": "550e8400-e29b-41d4-a716-446655440000"},
    "id": 1
})
resp.raise_for_status()
data = resp.json()
if "result" in data:
    print("Files:", data["result"])
else:
    print("Error:", data["error"])

# 3. Read a file
resp = requests.post(f"{BASE_URL}/v1/rpc", headers=headers, json={
    "jsonrpc": "2.0",
    "method": "files.read",
    "params": {"project_id": "...", "file_id": "..."},
    "id": 2
})

# 4. Write a file
resp = requests.post(f"{BASE_URL}/v1/rpc", headers=headers, json={
    "jsonrpc": "2.0",
    "method": "files.write",
    "params": {"project_id": "...", "file_id": "...", "content": "new content"},
    "id": 3
})

# 5. Search docs
resp = requests.post(f"{BASE_URL}/v1/rpc", headers=headers, json={
    "jsonrpc": "2.0",
    "method": "docs.search",
    "params": {"query": "assemblies"},
    "id": 4
})
```
