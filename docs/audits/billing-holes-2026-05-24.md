# Billing-hole audit — 2026-05-24

> **Status update — 2026-05-24 (same day).** All 6 **P0** holes plugged via
> T-402 fan-out (4 parallel Sonnet worktree agents, integrated by SHA):
>
> * R4 (Gemini cheap-tier unification) → `0d5f0682`
> * R3 (monthly storage debit scheduler) → `0eb5ea4b`
> * R1+R2+R8 (render charging + `user_id` threading + `record_storage` helper) → `f6d35c85`
> * R5+R6 (render-gate bypass close + workshop-publish auth) → `b70cc6eb`
> * Test-fixture integration patch (`_FAKE_AUTH` sub must be a UUID) → `573cd8b2`
>
> Full scoped pytest suite is back to the 10-failure pre-existing baseline
> (`test_file_kinds`, `test_routes_ota` inter-test pollution, `test_byo_blender`
> Docker daemon) — none caused by these fixes. JS suite green at 9534/9534.
> The remaining **P1** and **P2** findings below are queued for T-402b
> follow-ups (separate commits, smaller blast radius).

**Context.** Pre-Koyeb-cutover audit ([T-401 in `tasks.md`](../../tasks.md),
[ROADMAP § 7.1](../../ROADMAP.md#71--flyio--koyeb-p0-2026-05-24)).

Three Sonnet sub-agents read non-overlapping slices of the billing
surface in parallel:

* **Agent 1 — spend paths.** Every place chat / render / storage / compute
  COGS is incurred. Find paths that mutate billable state but don't call
  `kerf_billing.spend.commit_spend`, `render_meter.meter_render_job`, or
  `cloud_debit_balance`.
* **Agent 2 — quotas and abuse vectors.** Free-tier (`kerf_free`) bypass,
  cheap-tier masquerading, retry storms, rate-limit gaps.
* **Agent 3 — egress, storage, and BYO leaks.** Unbilled outbound
  bandwidth, untracked storage growth, BYO-key paths that hit our LLM
  keys.

Findings are deduplicated below. Several P0s were found independently by
two agents — those are the highest-confidence holes.

## Findings — by severity

### P0 — must fix before Koyeb cutover (revenue loss today)

| # | File:line | Hole | Found by |
|---|---|---|---|
| **R1** | `packages/kerf-render/src/kerf_render/queue_worker.py:151-165` | `CyclesQueueWorker.run_one()` calls `mark_complete()` but **never calls `meter_render_job()` / `charge_render()`** after a successful render. Both functions exist and are tested but have **zero production callers**. Every GPU render that completes through the async queue generates $0 revenue. | Agents 1, 2 |
| **R2** | `packages/kerf-render/src/kerf_render/routes.py:434` | `_enqueue_render` inserts `user_id = NULL` into `render_jobs` despite the JWT user being available at the route. The worker therefore has no identity to debit even if R1 is fixed. | Agents 1, 3 |
| **R3** | `packages/kerf-cloud/src/kerf_cloud/usage.py:90` + `packages/kerf-billing/src/kerf_billing/scheduler.py` | `monthly_storage_debit()` is fully implemented + tested but has no production caller. `BillingResetWorker` only resets API-token daily caps and free-tier quotas; storage debit is never invoked. Storage above the 50 MB free tier grows unbilled forever. | Agents 1, 3 |
| **R4** | `packages/kerf-chat/src/kerf_chat/llm.py:308-312` + `packages/kerf-pricing/src/kerf_pricing/cheap_tier.py:21-28` | Catalogue registers Gemini models under provider `"gemini"`; cheap-tier allowlist uses `"google"`/`"vertex_ai"`. `is_cheap_tier('gemini', 'gemini-3-flash-preview')` returns `False`. Free-tier users cannot use Gemini Flash even though it is intended cheap-tier — AND the two lists drift silently if either side is "fixed" independently. | Agent 2 |
| **R5** | `packages/kerf-render/src/kerf_render/routes.py:87-103` | `_run_billing_gate` calls `_optional_user_id` (returns `None` when no `Authorization` header). When user_id is `None`, the gate is silently skipped and the render proceeds without billing. Internal service calls or proxied requests with stripped headers bypass the gate entirely. | Agent 2 |
| **R6** | `packages/kerf-api/src/kerf_api/routes.py:6228-6229` | `_generate_project_cover` (called from `POST /workshop/publish`) dispatches a Blender Cycles render via `httpx` to `/run-render` **with no Authorization header**. R5 above causes the gate to be skipped, so every workshop publish triggers an unmetered GPU render at full COGS to the platform. | Agent 2 |

### P1 — fix in the same sprint

| # | File:line | Hole | Found by |
|---|---|---|---|
| **R7** | `packages/kerf-api/src/kerf_api/routes.py:3246` and `:3662` | LLM token markup hardcoded as `* 1.20` in both `post_message` and `chat_stream`. `Settings.cloud_pricing_token_markup_pct` defaults to 20 but is never read here. Any ops change is silently ignored. GPU markup was lifted to 35% in `pricing_meter.py`; token markup must follow the settings field for consistency. | Agent 1 |
| **R8** | `packages/kerf-api/src/kerf_api/routes.py:4569` and `:4596` | `usage_queries.record_storage(conn, uid, pid, size)` calls a non-existent function on `kerf_core.db.queries.usage_events`. Every STEP-file upload silently raises `AttributeError` swallowed by the outer `try/except`. No storage growth events are recorded — so even if R3 is fixed, the bytes attribution is empty. | Agent 1 |
| **R9** | `packages/kerf-api/src/kerf_api/routes.py:3670-3671` and `:3260` | Streaming chat swallows `commit_spend` exceptions silently (`except Exception: pass`). The non-streaming path catches `ApiTokenDailyCapExceeded` with a `_logger.warning` and continues. Any transient Postgres error during billing → model call proceeds with no debit. | Agent 2 |
| **R10** | `packages/kerf-api/src/kerf_api/routes.py:3204-3278` and `:3543-3740` | Multi-iteration agent loop (`_MAX_AGENT_ITERATIONS`) calls `pick_bucket` **once** before the loop and re-uses the snapshot for every iteration. A free-tier user whose quota drains during iteration 1 still debits `KerfFree` for iterations 2..N because the snapshot is stale. `_commit_free` clamps via `GREATEST(0, ...)`, so the column floors at zero, but the model calls still proceed. | Agent 2 |
| **R11** | `packages/kerf-billing/src/kerf_billing/render_meter.py:344-360` | `_try_consume_free_quota` seeds the `render_free_quota` row on first call using the **caller-supplied `user_tier` string**. Any caller that passes `user_tier="studio"` (whether the user is actually on Studio or not) gets 3 free hero renders. Tier must come from a verified DB column. | Agent 2 |
| **R12** | `packages/kerf-api/src/kerf_api/routes.py:486-520` | `_make_byo_provider` falls back to Kerf's server-side provider on **decryption failure** of the user's BYO key. The bucket selector has already decided `Byo` → `commit_spend` records `payer=byo_*` and charges $0, but the HTTP call goes out on Kerf's API key. Kerf eats the provider bill on a "BYO" request. | Agent 3 |
| **R13** | `packages/kerf-api/src/kerf_api/routes.py` — BYO save path absent | No write-side route was found for `user_provider_keys`, so BYO-key save validation is moot in the current build — but when the save endpoint lands, it must validate the key against the provider before storage (a 1-token test prompt) and reject 422 on failure. Note this for the eventual BYO save-path PR. | Agent 3 |
| **R14** | `packages/kerf-api/src/kerf_api/routes.py:4925-5004` | `export_project` (ZIP export) has a 500 MB cap but no per-user rate limit and no egress meter. A user can repeatedly export 400 MB STEP/GLB projects with no throttle; nothing lands in `usage_events`. | Agent 3 |
| **R15** | `packages/kerf-api/src/kerf_api/routes.py:5236-5294` | `serve_project_blob` streams public-project content-addressed objects through the app with no per-user / per-IP rate limit. Hammering a public project's STEP file creates unbounded outbound bandwidth we absorb 100%. | Agent 3 |

### P2 — fix when convenient

| # | File:line | Hole | Found by |
|---|---|---|---|
| **R16** | `packages/kerf-chat/src/kerf_chat/llm.py:295-313` | Expensive models in the catalogue (`gpt-4o`, `o3-mini`, etc.) have no explicit `paid_only` flag. UI relies entirely on the backend gate to block free-tier; a frontend bug or a direct API call routes through `pick_bucket` unsafely. Add an explicit `paid_only: bool` so the UI can disable them client-side. | Agent 2 |
| **R17** | `packages/kerf-auth/src/kerf_auth/routes.py:396-416` | `/auth/forgot-password` has no rate limit. Compare `/register` (5/hr) and `/login` (10/min). Anonymous high-throughput endpoint that triggers transactional email cost. | Agent 2 |
| **R18** | `packages/kerf-api/src/kerf_api/routes.py:3000, :3351` | Chat endpoints rate-limit `key_prefix="api:messages"` — confirm this keys off `user_id` (JWT sub) for authenticated requests, not just IP. Shared NAT / rotating IPs otherwise game the limit. | Agent 2 |
| **R19** | `packages/kerf-render/src/kerf_render/cycles_worker.py:173-187` | Render output writes to local filesystem (`/tmp/kerf_render_cache`) and the "signed URL" is a local path. On Koyeb the file is lost on restart; serving via the app proxy means every render download is outbound bandwidth we pay for. | Agent 3 |
| **R20** | `packages/kerf-cloud/src/kerf_cloud/usage.py:58-76` | `record_storage_event` writes the event row but the matching `cloud_debit_balance` call is not in the same transaction (compare `record_token_event` at :27). A crash between INSERT and debit leaves the event recorded but the balance untouched. | Agent 3 |
| **R21** | `packages/kerf-billing/src/kerf_billing/blob_gc.py:305-308` | `BlobGCWorker` defaults to `dry_run=True` from env. Without `BLOB_GC_DRY_RUN=false` explicitly set, deleted blobs are never physically removed from Tigris. Combined with R3 this means physical storage grows even when bytes are GC-eligible. Ops setting. | Agent 3 |
| **R22** | `packages/kerf-api/src/kerf_api/routes.py:2963-2991, :6316-6337, :6421-6436` | Auto-title (`_auto_title_thread`), `workshop_publish` README-gen, and `workshop_regenerate_readme` call Anthropic using the server key with no `commit_spend` call. Operator-cost LLM (haiku, low rate) but unbounded across workshop publish volume and invisible on the spend ledger. | Agent 1 |

### Areas explicitly checked clean

* `kerf_billing.spend.commit_spend` — correctly wired into non-streaming
  and streaming chat paths for all three buckets; atomic txn per bucket.
* `gate_render_job` itself — correctly called pre-dispatch, fails closed
  on error, skips for `usage_enabled=False`. *(The bypasses R5 and R6
  are in the caller, not the gate.)*
* `monthly_storage_debit` internal logic — correctly attributes by
  workspace, applies free-tier deduction, atomic. *(The bug is solely
  that it's never invoked — R3.)*
* `BillingResetWorker` registration — correctly wired when
  `cloud_enabled=True and not local_mode`.
* `kerf_render.pricing_meter.meter_render_job` and
  `kerf_billing.render_meter.charge_render` — both correct
  implementations, but dead code with no production callers (R1).

## Recommended order of attack (T-402)

Group by file / blast-radius so each fix is a small commit. Stop the
bleeding before adding new features.

1. **Plug R1+R2+R8 in one PR** (`packages/kerf-render/` +
   `packages/kerf-api/`). Wire `meter_render_job` into
   `CyclesQueueWorker.run_one`, thread `user_id` into `_enqueue_render`,
   add the missing `record_storage` helper. Unblocks GPU + storage
   revenue at one stroke.
2. **R3 — schedule `monthly_storage_debit`** in `BillingResetWorker` or
   as a new `StorageBillingWorker`. Idempotent monthly tick.
3. **R5+R6 — close render gate bypass.** Reuse the verified
   `user_id` inside `_run_billing_gate` and fix the internal `httpx`
   call in `_generate_project_cover` to pass auth.
4. **R4 — unify Gemini provider key.** Pick `"gemini"` everywhere or
   rename the catalogue entries to `"google"`. Add a snapshot test
   ensuring `is_cheap_tier(provider, model_id)` agrees with the
   catalogue's `cheap_tier_eligible` flag for every catalogue entry.
5. **R7 — read markup from settings.** Replace literal `1.20` with
   `(1.0 + settings.cloud_pricing_token_markup_pct / 100.0)` in both
   chat paths.
6. **R9, R10, R11 — billing-failure handling** in chat. Stop swallowing
   `commit_spend` exceptions; re-snapshot the bucket per iteration; pin
   `user_tier` to a verified DB column.
7. **R12 — BYO decryption failure** must 402, not fall back.
8. **R14, R15, R19 — egress controls.** Per-user rate-limit on export
   and blob-serve; switch render output to Tigris presigned URLs.
9. **R16, R17, R18, R20, R21, R22 — clean-up sprint** once the bleeding
   is stopped.

## Break-even impact

Pre-fix, the hosted tier's only realised revenue path is chat tokens
(when commit_spend is reached and not swallowed) and Studio/Pro
subscriptions. GPU renders and storage growth are both $0 revenue
today, even though Cycles already runs in production. Fixing R1–R3
moves the hosted tier from "subscription-revenue only" to "subscription
+ per-render + per-GB" — directly improving the break-even target in
[ROADMAP § 7.1](../../ROADMAP.md#71--flyio--koyeb-p0-2026-05-24).

## Methodology

Three parallel Sonnet agents, prompted with non-overlapping slices, no
code edits, full repo read access. Each returned a short markdown
report; this doc deduplicates and re-orders by severity. Raw agent
transcripts are not preserved here — the file:line citations are
authoritative.
