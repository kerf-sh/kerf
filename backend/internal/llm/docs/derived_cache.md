# Derived-artifact cache

A server-side cache for cross-project compiled outputs (PCB → 3D mesh,
PCB → 2D outline sketch, JSCAD source → tessellated mesh). Lets
consumers of `external_ref` short-circuit the compile when the source
file's content hasn't changed since the last cache write.

## Schema

`derived_artifacts` table:

| column                | type    | notes                               |
| --------------------- | ------- | ----------------------------------- |
| `id`                  | uuid pk | `gen_random_uuid()`                 |
| `source_file_id`      | uuid fk | `files(id)` ON DELETE CASCADE       |
| `content_sha256`      | text    | SHA-256 of source content at write  |
| `derived_kind`        | text    | enum below                          |
| `payload`             | bytea   | the compiled artifact, opaque       |
| `payload_size_bytes`  | int     |                                     |
| `created_at`          | tstz    |                                     |
| `last_accessed_at`    | tstz    | bumped on every cache hit           |

UNIQUE INDEX on `(source_file_id, content_sha256, derived_kind)`.
LRU index on `last_accessed_at`.

`derived_kind` enum: `'jscad_mesh'` | `'sketch_geom2'` |
`'circuit_board_3d'`. Validated server-side; unknown values → 400.

## Endpoints

All gated by `requireMember` (caller must be a member of the source
project's workspace). Cross-project caller without membership → 404
(non-leaking).

### Lookup — `POST /api/projects/{pid}/files/{fid}/derived`

Body: `{ "derived_kind": "circuit_board_3d" }`

Hashes the source file's current content, looks up the row, bumps
`last_accessed_at`. Two outcomes:

- **Hit (200)** — `{ "cached": true, "derived_kind": "...",
  "payload_b64": "<base64>" }`
- **Miss (501)** — `{ "cached": false, "derived_kind": "...",
  "error": "compile-on-demand-not-yet-wired" }`

The 501 surface lets the frontend preflight; on miss it falls through
to the existing on-demand recompile path.

### Store — `POST /api/projects/{pid}/files/{fid}/derived/store`

Body: `{ "derived_kind": "...", "payload_b64": "<base64>" }`

Hashes the source's current content, INSERTs / UPSERTs the row.
Idempotent: re-storing at the same `(file, sha, kind)` overwrites
`payload` + `payload_size_bytes` and bumps `last_accessed_at`.

Returns `200 { "stored": true, "derived_kind": "...",
"payload_size_bytes": N }`.

Body cap: 16 MiB on decoded payload (the `MaxBytesReader` cap is set
to 2× to allow for base64 inflation). Violation → 400.

### Purge — `DELETE /api/projects/{pid}/files/{fid}/derived`

Drops every cached row for the file regardless of kind. Returns
`200 { "purged": N }`.

## Frontend lookup

`library.lookupDerivedArtifact({projectId, fileId, derivedKind})` in
`src/cloud/api.js` wraps the lookup endpoint. On 501 it returns
`{cached: false}`; on success it base64-decodes to `Uint8Array`.

`loadExternalParts(ref)` in `src/lib/assembly.js` calls it before
recompiling; the kind mapping is:

| `external_ref.kind`  | `derived_kind`        |
| -------------------- | --------------------- |
| `board_3d`           | `circuit_board_3d`    |
| `board_outline_2d`   | `sketch_geom2`        |
| `mesh`               | `jscad_mesh`          |

## Known limits

- Compile-on-demand is **out of scope** for the autonomous-agent
  surface; the cache layer is bidirectional but population still
  requires a frontend-side compile + an explicit `store` call.
- No global LRU eviction; cache grows until purged.
- 16 MiB payload cap fits typical board meshes / sketches but will
  reject very large STEP-derived JSCAD meshes.
