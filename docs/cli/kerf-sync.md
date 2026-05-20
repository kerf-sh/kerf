# kerf sync

Two-way folder mirror between a local directory and a Kerf cloud project.

## Synopsis

```
kerf sync <project-id> <local-dir> [options]
```

## Description

`kerf sync` keeps a local directory and a Kerf project in sync. Run it once
for a one-shot operation, or pass `--watch` to start a foreground daemon that
polls both sides on a configurable interval and propagates changes either way.

## One-shot mode

```bash
kerf sync proj-uuid ./my-project
```

Fetches the current remote file list, walks the local directory, computes a
diff, and applies it (mtime-based, last-write-wins). One HTTP round-trip per
changed file.

## Daemon (watch) mode

```bash
kerf sync proj-uuid ./my-project --watch [--interval 5]
```

Starts a foreground polling loop. Each *tick*:

1. Fetches the remote file manifest.
2. Computes SHA-256 of every local file.
3. Compares both to the *previous tick's* snapshot.
4. Propagates changes:
   - remote changed, local unchanged → **pull** (download)
   - local changed, remote unchanged → **push** (upload)
   - neither changed → skip
   - **both changed** → **OCC conflict** (see below)

Stop the daemon with `Ctrl-C` (exit 0).

## OCC conflict detection

If the same file changes on *both* sides between two ticks, the daemon
immediately **stops** and prints a conflict report. Neither side is modified
— you must resolve the conflict manually, then restart the daemon.

```
OCC CONFLICT — sync stopped. Manual resolution required.
  CONFLICT  design.step
    local  prev=abc123...  now=def456...
    remote prev=abc123...  now=789ghi...
```

Exit code `4` signals a conflict.

## Deletion semantics

`kerf sync` is safe-by-default on deletions:

- A file present locally but absent remotely is **pushed** (treated as new,
  not as a request to delete).
- A file deleted locally is **not** auto-deleted on the server — a warning is
  printed instead.

This avoids accidental data loss when the local directory is incomplete (e.g.
a fresh clone).

## Large files (LFS pointers)

After pulling a file, `kerf sync` inspects the content for Git-LFS-format
pointer stubs and hydrates them in-place via the `kerf hydrate` machinery.
This is transparent and best-effort — the sync completes even if hydration
fails.

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--watch` | off | Run as a foreground daemon |
| `--interval SECS` | `5` | Polling interval in seconds (daemon mode) |
| `--dry-run` | off | Print actions without applying them |
| `--url URL` | `$KERF_API_URL` | Override API endpoint |
| `--token TOKEN` | `$KERF_API_TOKEN` | API token |

## Authentication

`kerf sync` reads credentials from (in order of priority):

1. `--token` flag
2. `KERF_API_TOKEN` environment variable
3. `~/.config/kerf/credentials` (written by `kerf login`)

The `--url` flag (or `KERF_API_URL`) selects the server. Both Kerf cloud
(`https://app.kerf.io`) and self-hosted instances use the same API surface.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success / daemon exited cleanly |
| 1 | One or more files failed to sync |
| 2 | Authentication failure |
| 3 | Project not found or API error |
| 4 | OCC conflict detected (daemon mode) |

## Examples

```bash
# One-shot sync, cloud project → local directory
kerf sync abc-123 ./my-cad-project

# Dry-run: show what would happen without touching any files
kerf sync abc-123 ./my-cad-project --dry-run

# Watch mode: sync every 10 seconds
kerf sync abc-123 ./my-cad-project --watch --interval 10

# Self-hosted server
kerf sync abc-123 ./project \
  --url http://localhost:8080 \
  --token kerf_sk_mytoken

# Use environment variables
export KERF_API_URL=https://app.kerf.io
export KERF_API_TOKEN=kerf_sk_...
kerf sync abc-123 ./project --watch
```

## See also

- [`kerf export`](./kerf-export.md) — download a project as a ZIP archive
- [`kerf import`](./kerf-import.md) — create a project from a ZIP archive
- [`kerf hydrate`](./kerf-hydrate.md) — resolve LFS pointer stubs
- [`kerf login`](./kerf-login.md) — store API credentials
