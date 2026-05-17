# Troubleshooting

Common errors and their resolutions, accurate to the fixes that landed in the
`refactor` branch.

---

## Event-loop error in tests under Python 3.12+

**Symptom**

```
RuntimeError: There is no current event loop in thread 'MainThread'.
```

Tests that call `asyncio.get_event_loop().run_until_complete(...)` raise this
on Python 3.12+ because the implicit loop auto-create was removed.

**Root cause**

The ~110 test files written before the monorepo split used the legacy pattern.
Python 3.12 no longer creates a default event loop on first access in the main
thread.

**Fix (already landed)**

`conftest.py` at the repo root installs a compatibility shim that restores
pre-3.10 semantics for the test process only:

```python
# conftest.py — section (3)
_orig_get_event_loop = asyncio.get_event_loop

def _get_event_loop_compat():
    try:
        return _orig_get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

asyncio.get_event_loop = _get_event_loop_compat
```

Production code is not affected — `conftest.py` is only loaded by pytest.

If you add a new test file and see the error, ensure you are running pytest
from the repo root (not from inside a plugin directory), so the root
`conftest.py` is picked up.

---

## Migration collision on `files.kind` enum

**Symptom**

```
ERROR: invalid input value for enum files_kind: "circuit"
```

or

```
duplicate key value violates unique constraint on migrations
```

**Root cause**

Each migration adds new values to the `files.kind` CHECK constraint (or an
enum-like column). Running migrations out of order or applying them twice
produces constraint violations.

**Fix**

Migrations are applied by `kerf-server --migrate` (or `npm run migrate`),
which records applied migrations in a `schema_migrations` table and skips
already-applied ones. Do not apply SQL files by hand.

If your DB is ahead of the migration runner (e.g., from a manual hot-fix),
manually insert the skipped migration IDs:

```sql
INSERT INTO schema_migrations (version) VALUES ('025_api_tokens');
```

Then re-run `npm run migrate`.

If you need a clean slate in development: `npm run migrate:reset` drops and
re-creates the schema from scratch.

---

## `conftest.py` plugin name clash

**Symptom**

```
ImportError: cannot import name 'X' from 'tools'
```

or a module resolves to the wrong plugin's implementation.

**Root cause**

The root `conftest.py` installs a `tools.*` shim that maps legacy test imports
(`tools.routing`, `tools.render`, …) to their canonical plugin modules. If two
plugins register under the same short name, or the mapping table in
`conftest.py` is stale, imports resolve incorrectly.

**Fix**

Check the `mapping` dict in the `_install_tools_shim()` function in
`conftest.py`. Each entry has the form:

```python
"tools.<short_name>": "kerf_<plugin>.tools.<module>",
```

If a module moved to a new plugin during a refactor, update the mapping. The
existing table covers all known moves from the pre-plugin-split layout.

When adding a new plugin, add entries for any `tools.*` imports your tests
use. The shim uses `importlib.import_module` with a `try/except ImportError`
so missing heavy-dep plugins are silently skipped (tests that need them will
`pytest.importorskip` at the top of the file).

---

## `kerf-server` script not found after backend retirement

**Symptom**

```
zsh: command not found: kerf-server
```

or the server starts but `npm run dev` can't connect.

**Root cause**

Before the monorepo split (`refactor` branch), the entry point was defined in
`backend/pyproject.toml`. After migration the entry point lives in
`packages/kerf-core/pyproject.toml`:

```toml
[project.scripts]
kerf-server = "kerf_core.app:run"
```

Running `pip install -e .` against the old `backend/` path no longer installs
this script.

**Fix**

Re-install from the repo root:

```sh
pip install -e .[full]
```

This installs `kerf-core` (and all other persona plugins) from `packages/` and
registers the `kerf-server` entry point correctly. Verify:

```sh
which kerf-server          # should point into your venv
kerf-server --help
```

---

## `tools.X` ImportError after moving a module to a new plugin

**Symptom**

After a refactor that moved, say, `tools.routing` from `kerf-imports` to
`kerf-electronics`, tests that import `tools.routing` either fail or import
the wrong module.

**Root cause**

The `_install_tools_shim()` mapping in root `conftest.py` has not been updated.

**Fix**

Update the entry in `conftest.py`:

```python
# Before (stale):
"tools.routing": "kerf_imports.tools.routing",

# After:
"tools.routing": "kerf_electronics.tools.routing",
```

This is the canonical fix pattern after every plugin refactor. The test that
exposed `c3ffd8c` (`retire backend/ + pyworker/ residuals`) and `a4835f8`
(`migrate routing/sim to kerf-electronics`) both required this update.

---

## Stale `BAD_ARGS` sentinel in tool tests

**Symptom**

A test asserts `result["code"] == "BAD_ARGS"` for an argument value that used
to be invalid, but now the tool accepts it and the test fails.

**Root cause**

A parallel agent or a recent commit made a previously invalid sentinel value
valid (added it to an enum, widened a range check, etc.). The test was written
against the old validation boundary and is now testing stale behaviour.

**Fix**

Update the test to use a value that is still invalid, or change the assertion
to `result["ok"] == True` if the intent was to test the happy path. Do not
revert the tool change — the sentinel being valid is correct.

This is the "parallel-agent shared-enum pitfall": when multiple agents work on
the same enum simultaneously, a test asserting `code==BAD_ARGS` for a
plausible value is nearly always a stale test, not a regression.

---

## Server can't find `kerf.toml`

**Symptom**

```
FileNotFoundError: kerf.toml not found
```

**Fix**

Copy the example config:

```sh
npm run init
```

This copies `kerf.example.toml` → `kerf.toml` idempotently. Then edit
`kerf.toml` to set at least:

```toml
[auth]
optional = true           # disables signup screen for local use

[llm.anthropic]
api_key = "sk-ant-…"
```

Config search order: `--config <path>` → `KERF_CONFIG` env → `./kerf.toml` →
`~/.config/kerf/config.toml` → `/etc/kerf/config.toml`.

---

## Postgres connection error

**Symptom**

```
asyncpg.exceptions.InvalidPasswordError: password authentication failed
```

or

```
could not connect to server: Connection refused
```

**Common causes**

1. Postgres is not running. Start it: `brew services start postgresql@16` (macOS).
2. The `DATABASE_URL` in `kerf.toml` uses the wrong role.
   Local dev with a role named `pc` (not `postgres`):

   ```toml
   [database]
   url = "postgres://pc@localhost:5432/kerf?sslmode=disable"
   ```

3. The database doesn't exist. Create it: `createdb kerf`.

---

## LLM not responding / wrong model error

**Symptom**

```
LLM not configured — set ANTHROPIC_API_KEY
```

or

```
That model isn't available right now.
```

**Fix**

Set at least one provider API key in `kerf.toml`:

```toml
[llm.anthropic]
api_key = "sk-ant-…"

[llm]
default_model = "claude-sonnet-4-20250514"
```

Available model IDs are returned by `GET /api/models`. The `deprecated`
error message from the LLM provider usually means the model ID in config is
outdated — update `default_model` to a current ID.

---

## STEP file appears in the file list but the 3D view is blank

**Symptom**

A `.step` file shows `tessellation_status: null` or `queued` but the viewport
shows nothing.

**Fix**

The tessellation job runs asynchronously in `kerf-tess`. Check the job status:

```
GET /api/projects/{pid}/files/{fid}/fem/status
```

If status is `error`, check server logs for the OCC error. Large STEP files
(> 5 MB) are flagged with `LARGE_STEP_THRESHOLD` and tessellated at lower
quality to keep the initial render fast.

To force a re-tessellation:

```
DELETE /api/projects/{pid}/files/{fid}/tessellate
POST   /api/projects/{pid}/files/{fid}/tessellate
```

---

See also: [contributing.md](./contributing.md) · [architecture.md](./architecture.md) · [getting-started.md](./getting-started.md)
