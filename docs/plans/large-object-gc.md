# Large-object GC — decision record (T-136)

> **Status:** design only — no implementation exists yet.
> **Depends on:** T-134 (blob object ledger schema).
> **Related:** T-135 (dedup billing), T-124/T-125 (git-as-substrate, not yet built).

---

## 1. Context

Every project file larger than the inline threshold (default 1 MiB, or any
non-UTF-8 content) is content-addressed and stored in Tigris S3 under
`blobs/{sha256[:2]}/{sha256}`.  The T-134 ledger provides two tables:

```
blob_objects(
  oid              text primary key,          -- sha256 hex of content
  size_bytes       bigint not null,
  first_workspace_id uuid references workspaces(id) on delete set null,
  created_at       timestamptz not null default now()
)

blob_refs(
  oid              text references blob_objects(oid) on delete cascade,
  project_id       uuid references projects(id) on delete cascade,
  path             text not null,
  created_at       timestamptz not null default now(),
  primary key (oid, project_id, path)
)
```

An oid may be shared across many projects (content-addressed dedup).
`blob_refs` tracks which (project, path) combinations currently point to each
oid.  `drop_ref` removes a row; if that was the last row for a given oid the
ref-count falls to zero.

The problem: a zero-ref oid does **not** automatically mean the content is
unreachable.  A blob committed to a project's git history is reachable from
every git commit that ever pointed to it — including commits in forks, branches
that were "deleted" at the UI level, and the reflog.  Deleting such an object
from Tigris would corrupt any checkout or clone that tries to resolve that
commit.

---

## 2. What is (and is not) collected

### Collected (eligible for physical deletion)

An oid is eligible for GC if and only if **both** of the following hold:

1. **Zero live refs** — no row exists in `blob_refs` for this oid.
2. **Git-unreachable** — no live git commit in any project's repository
   references this oid (see §3 for the exact reachability predicate).
3. **Past the grace window** — at least 72 hours have elapsed since the oid's
   `blob_objects.created_at` and since the last `blob_refs` row for this oid
   was deleted (see §4).

### Not collected — ever

- Any oid with at least one row in `blob_refs`.
- Any oid reachable from any project's git history (historical commits,
  all branches, all tags, all forks).
- Any oid still within the 72-hour grace window, even if currently zero-ref.
- Any oid that cannot be positively confirmed as git-unreachable because the
  git-as-substrate layer (T-124/T-125) is not yet implemented (see §3.3).

---

## 3. Reachability predicate

### 3.1 Definition

Let `R(oid)` be the reachability predicate:

> `R(oid)` is **true** if there exists at least one live git commit object, in
> any project repository managed by Kerf, whose tree (directly or transitively)
> contains a blob entry pointing to this oid.

In terms of the git object model: walk every repository's reachable commit
graph (starting from all refs: heads, tags, stash) and collect all blob SHA-256
values encountered.  If `oid` appears in that set, `R(oid) = true`.

An oid is **git-unreachable** if `R(oid) = false` across all repositories.

### 3.2 How this maps to Kerf's storage model

Large files committed via the T-124 flow are represented in git as pointer
stubs (`.kerf-ptr` files).  The pointer content encodes the oid:

```
kerf-ptr v1
sha256: <oid>
size: <n>
```

The git blob whose content is the pointer stub has a different SHA (git uses
SHA-1/SHA-256 over the pointer text), but the oid embedded inside that pointer
blob is the Tigris object key.  Therefore:

> A Tigris oid `X` is git-reachable from repository `repo` if any blob in any
> commit reachable from `repo`'s refs contains a pointer stub with `sha256: X`.

This is a parse + grep over pointer-blob contents, not a hash comparison.

### 3.3 Contract for the future git layer (T-124/T-125)

The git-as-substrate layer is not yet built.  Until it exists, the GC worker
**must treat every oid as git-reachable** (i.e., skip physical deletion of any
oid, even if it has zero `blob_refs` rows), unless an explicit reachability
oracle is registered.

The future git layer must satisfy the following contract to enable GC:

```
Interface: GitReachabilityOracle

  is_oid_reachable(oid: str) -> bool
    Returns True if the given sha256 oid appears in any pointer blob
    in any commit reachable from any ref (branches, tags, stash) of any
    project repository.  Must be a conservative over-approximation:
    false negatives (saying "unreachable" for a reachable oid) are
    forbidden; false positives (saying "reachable" for an unreachable
    oid) are safe (they cause delayed GC, not data loss).

  last_unreachable_at(oid: str) -> datetime | None
    Returns the timestamp at which the oid became git-unreachable (i.e.,
    when the last pointer blob referencing it was garbage-collected from
    all repositories), or None if it is currently reachable or if the
    implementation cannot determine this.
```

Until `GitReachabilityOracle` is registered, the sweep worker logs:

```
blob_gc_tick git_oracle_absent skip_all_oids=True
```

and does **not** delete any object.

### 3.4 Conservative default during transition

Because T-124/T-125 are not yet built:

- The initial deployment of the GC worker is **dry-run only** (§6.2).
- No physical Tigris deletes occur until a `GitReachabilityOracle`
  implementation is wired in and the dry-run metrics have been reviewed.
- This means early storage cost will grow unbounded until the oracle lands —
  this is acceptable given the "never delete reachable" safety invariant
  outweighs operational cost during the build phase.

---

## 4. Grace window

**Chosen value: 72 hours.**

Rationale:

- A user can delete all live refs for a file (e.g., delete the project) and
  then immediately restore it from a backup or re-upload within hours.
  72 hours covers a weekend without on-call intervention.
- A git rebase / force-push can transiently orphan a blob between the time the
  old ref is removed and the new commit is pushed; 72 hours covers any
  reasonable network/cache lag in the git layer.
- Billing attribution (T-135) recomputes on a 24-hour cadence; 72 hours ensures
  a deleted-and-recreated oid is never mis-billed as "new storage" due to a GC
  race.
- 72 hours is well within Tigris's eventual-consistency window for list
  operations.

The grace window is measured from `MAX(blob_objects.created_at, last_drop_ref_at)`,
where `last_drop_ref_at` is recorded in a `blob_objects.last_unref_at` column
that the `drop_ref` query updates when the ref-count transitions to zero.
(This column is added to the T-134 baseline by the implementing task; it is
noted here as a design requirement.)

---

## 5. Sweep worker

### 5.1 Worker shape

The `BlobGCWorker` follows the same `run(ctx) / stop()` timer-loop shape as
`PricingRefreshWorker` (in `packages/kerf-pricing/src/kerf_pricing/worker.py`)
and `BillingResetWorker` (in `packages/kerf-billing/src/kerf_billing/scheduler.py`):

```python
class BlobGCWorker:
    name = "blob_gc"

    def __init__(self, pool, *, interval_seconds: float, dry_run: bool = True) -> None: ...

    async def run(self, ctx = None) -> None:
        await self._tick()
        while not self._shutdown:
            await asyncio.sleep(self.interval)
            if self._shutdown:
                break
            await self._tick()

    def stop(self) -> None:
        self._shutdown = True

    async def _tick(self) -> None: ...
```

No inheritance from `BaseWorker` (which is job-table-driven); this is a pure
timer worker.

### 5.2 Registration

The worker is cloud-gated and registered via a plugin's `register()` function
(e.g., `kerf-cloud`) into `ctx.workers` using `workers_registry.register(name,
factory)`, exactly as `PricingRefreshWorker` is registered in
`packages/kerf-pricing/src/kerf_pricing/plugin.py`.

Activation requires:
- `KERF_INPROCESS_WORKERS=true` (or `1` / `yes`) — the env flag that gates
  `_maybe_start_inprocess_workers` in `packages/kerf-core/src/kerf_core/app.py`.
- `CLOUD_ENABLED=true` — the worker is a no-op in local/self-hosted mode.
- `BLOB_GC_DRY_RUN` defaults to `true`; must be explicitly set to `false` to
  enable physical deletes.

### 5.3 Cadence

- **Interval:** every 6 hours.
- **On boot:** one tick executes immediately (like `PricingRefreshWorker`).
- Missed ticks (process restart, deployment) are harmless — the sweep is
  fully idempotent.

### 5.4 Sweep algorithm (one tick)

```
1. Identify candidate oids:
   SELECT o.oid, o.size_bytes, o.last_unref_at
   FROM blob_objects o
   WHERE NOT EXISTS (SELECT 1 FROM blob_refs r WHERE r.oid = o.oid)
     AND o.last_unref_at IS NOT NULL
     AND o.last_unref_at < now() - interval '72 hours'
     AND o.created_at < now() - interval '72 hours'
   LIMIT 500  -- process in bounded batches; loop until no rows remain

2. For each candidate oid:
   a. Re-check blob_refs in the same transaction (MVCC race guard):
      IF EXISTS (SELECT 1 FROM blob_refs WHERE oid = candidate.oid) THEN
        skip (another ref was added concurrently)
      END IF
   b. Call GitReachabilityOracle.is_oid_reachable(oid):
      IF reachable OR oracle absent THEN skip
   c. DRY-RUN check: if BLOB_GC_DRY_RUN is set, log and skip delete.
   d. Delete from Tigris S3: DELETE key blobs/{oid[:2]}/{oid}
   e. On Tigris delete success: DELETE FROM blob_objects WHERE oid = ?
      (blob_refs cascade-deletes, but should be empty at this point)
   f. Emit metric: blob_gc_deleted_bytes += size_bytes; blob_gc_deleted_count += 1

3. Emit per-tick summary metric regardless of deletes (see §6.1).
```

The `LIMIT 500` batch ensures a single tick does not hold the DB connection or
hit Tigris rate limits for unbounded time.  The loop continues until a full
pass finds no candidates.

---

## 6. Safety invariants

### 6.1 Metrics and observability

Every tick emits structured log lines (structlog) with:

| Key | Meaning |
|---|---|
| `blob_gc_candidates` | Count of oids selected as candidates this tick |
| `blob_gc_skipped_live_ref` | Skipped because a live ref re-appeared (MVCC race) |
| `blob_gc_skipped_git_reachable` | Skipped because oracle says reachable |
| `blob_gc_skipped_oracle_absent` | Skipped because oracle not registered |
| `blob_gc_skipped_dry_run` | Would-delete count suppressed by dry-run mode |
| `blob_gc_deleted_count` | Physical deletes performed this tick |
| `blob_gc_deleted_bytes` | Total bytes reclaimed this tick |
| `blob_gc_errors` | Tigris or DB errors (logged, not fatal) |
| `blob_gc_tick_duration_ms` | Wall time for the full tick |

Log level: `INFO` for summary lines; `DEBUG` for per-oid lines.

These keys map directly to future Prometheus/OpenTelemetry gauge/counter
instrument names when a metrics layer is added; the string names are
intentionally stable.

### 6.2 Dry-run mode

`BLOB_GC_DRY_RUN=true` (the default) causes the worker to:
- Identify and evaluate all candidates.
- Log `blob_gc_skipped_dry_run` for each would-be delete.
- **Never** issue a Tigris `DELETE` request or a `DELETE FROM blob_objects` row.

Dry-run mode is the safe deployment default.  To enable real GC:
1. Review the dry-run metrics from at least one full 24-hour window.
2. Confirm `blob_gc_skipped_oracle_absent = 0` (i.e., the git oracle is wired).
3. Set `BLOB_GC_DRY_RUN=false` and redeploy.

### 6.3 Idempotency

- The Tigris delete is a no-op if the key does not exist (S3 `DELETE` is
  idempotent).
- The `DELETE FROM blob_objects WHERE oid = ?` is safe to re-run; it is
  a no-op if the row was already removed.
- A restart mid-sweep leaves any already-deleted oids gone and any
  not-yet-processed oids pending for the next tick — no partial state.

### 6.4 Ordering vs T-135 billing recompute

The T-135 dedup billing attribution query reads `blob_objects.size_bytes` to
compute workspace storage charges.  A GC run that deletes a row from
`blob_objects` while a billing recompute is in flight could produce a
temporarily low storage number.

Safe ordering rule:

> The GC worker **must not delete a `blob_objects` row for any oid whose
> `last_unref_at` falls within the current billing recompute window.**

In practice this is guaranteed by the 72-hour grace window: the billing
recompute cadence is 24 hours, so any oid whose ref was dropped within the
last 3 days is both within the grace window and within the billing window.
No additional locking is required.

If the billing recompute cadence ever increases beyond 72 hours, the grace
window must be increased proportionally (grace ≥ 2 × billing cadence is the
design invariant).

### 6.5 Never-delete guarantee

The formal invariant, to be enforced in code review for any future GC
implementation:

> **A `blob_objects` row may only be deleted if, at the moment of deletion,
> the following conditions all hold in a single database transaction:**
> 1. `SELECT COUNT(*) FROM blob_refs WHERE oid = ?` returns 0.
> 2. `GitReachabilityOracle.is_oid_reachable(oid)` returns `false`.
> 3. `last_unref_at < now() - interval '72 hours'`.
> 4. `created_at < now() - interval '72 hours'`.
> 5. `BLOB_GC_DRY_RUN` is not set to `true`.

Conditions 1 and 3–4 are checked inside a `SELECT … FOR UPDATE` on the
`blob_objects` row to prevent a concurrent `add_ref` from inserting a new ref
between the safety check and the delete.

---

## 7. Future work (out of scope for this record)

- **Git reachability oracle implementation** — depends on T-124/T-125.  Until
  it exists, physical deletes are gated to dry-run.
- **Compacted / squashed history** — if git history is ever rewritten
  (interactive rebase, squash) the oracle must handle the case where a commit
  is no longer in any ref's history but was not explicitly GC'd by git's own
  `git gc`.  A safe default is to retain any oid referenced by any object that
  git's own GC would retain.
- **Orphaned Tigris keys** — objects that exist in Tigris but have no
  corresponding `blob_objects` row (e.g., from a failed write that inserted to
  Tigris but not to the DB).  These are not addressed by this worker; a
  separate reconciler is out of scope.
- **Tigris lifecycle policies** — Tigris S3 supports object lifecycle rules
  (expire after N days).  These are not used because the GC worker needs
  finer-grained control (git reachability check) than a lifecycle rule can
  express.
