# Project Portability

Kerf guarantees you own your data and can leave at any time.
The `kerf export` / `kerf import` CLI pair makes this concrete: a single
command produces a plain directory tree that any person or tool can read
without the Kerf server.

---

## kerf export

```
kerf export <project-id> --out <dir>
```

Downloads the project from the Kerf server and writes it as a plain
directory tree.

**What gets written:**

```
<dir>/
  <files as authored>          # exact bytes, POSIX sub-directory layout
  .kerf/
    metadata.json              # project name, IDs, description, tags
    manifest.lock              # per-file SHA-256 OIDs + git/workspace info
```

**metadata.json** fields:

| Field | Description |
|---|---|
| `kerf_export_version` | Format version (currently `1`) |
| `project_id` | Source project UUID |
| `name` | Project name |
| `description` | Project description |
| `tags` | List of project tags |
| `created_at` | ISO-8601 creation timestamp |
| `workspace_id_hint` | First 8 hex chars of workspace UUID (anonymised) |

**manifest.lock** fields:

| Field | Description |
|---|---|
| `kerf_lock_version` | Format version (currently `1`) |
| `files[]` | Per-file entries: `path`, `kind`, `oid` (SHA-256), `size` |
| `cloud_git_repo` | Optional: `{ default_branch }` if the project has cloud git history |
| `workspace_id_hint` | Same 8-char hint as metadata.json |

The `oid` for each file is the SHA-256 hex digest of the file's bytes on
disk.  Importers can use this to verify content integrity before uploading.

---

## kerf import

```
kerf import <dir>
```

Reads a directory produced by `kerf export`, creates a new project on the
target Kerf instance, and uploads every file.

- Project name comes from `.kerf/metadata.json` (override with `--name`).
- Each file's SHA-256 is verified against `.kerf/manifest.lock` before
  upload; a mismatch prints a warning but does not abort.
- The `.kerf/` directory itself is never uploaded as a project file.
- On success, prints the new project ID.

---

## Round-trip guarantee

```
kerf export <pid> --out ./snapshot
# ... the Kerf instance could be wiped here ...
kerf import ./snapshot
```

The newly created project has byte-identical file content to the original.
The `manifest.lock` OIDs act as the oracle: if the SHA-256 of every
on-disk file matches the recorded OID, the round-trip is lossless.

---

## Symmetric cloud / self-host

Both commands work identically against:

- **Kerf Cloud** (`https://app.kerf.io`) — set `KERF_API_TOKEN` or run `kerf login`.
- **Self-hosted instance** — pass `--url http://your-server:8080` and set `KERF_API_TOKEN`.

There is no vendor-specific path.  An export from cloud can be imported to a
self-hosted instance and vice versa.

---

## Server API surface used

| Method | Endpoint | Used by |
|---|---|---|
| `GET` | `/api/projects/{pid}/export` | `kerf export` — fetches the server-produced ZIP |
| `POST` | `/api/projects` | `kerf import` — creates the new project |
| `POST` | `/api/projects/{pid}/files` | `kerf import` — uploads each file |

The export ZIP produced by the server (`materialize_project_tree`) already
contains a `kerf-manifest.json`; the CLI extracts it into `.kerf/metadata.json`
and builds `.kerf/manifest.lock` from the on-disk SHA-256 checksums.

---

## Large files and git history

The current CLI does not export cloud git history (commits, branches).
The `manifest.lock` records `cloud_git_repo.default_branch` as a hint for
re-connecting a future git clone; actual history preservation requires a
separate `git clone` of the hosted repo URL (Phase 2: Git LFS substrate).

For large binary files stored as LFS pointer stubs, the bytes are resolved
by the server before writing to the ZIP, so the exported directory always
contains real bytes — not pointers.
