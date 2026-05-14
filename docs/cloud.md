# Cloud

Kerf's hosted tier — managed Postgres + storage + LLM keys with surfaces the
OSS build doesn't ship.

> **Licensing.** Cloud-tier code lives in two **proprietary plugin packages**:
> `packages/kerf-billing/` and `packages/kerf-cloud/`. See
> [LICENSE-CLOUD](../LICENSE-CLOUD). Every other plugin under `packages/` is
> MIT and runs standalone.

Hands-on build/deploy guide: [cloud-operator.md](./cloud-operator.md).

## Cloud-only vs OSS

| Feature | Plugin | Notes |
|---------|--------|-------|
| Paystack billing | `kerf-billing` | USD UI, ZAR settlement; capability tag `billing.paystack` |
| Workshop sharing | `kerf-cloud` | Publish + fork + like + library submissions; `cloud.workshop` |
| GitHub OAuth + cloud git | `kerf-cloud` | `/auth/github/{start,callback}`, AES-GCM encrypted tokens; `cloud.git` |
| S3 Git Storer | `kerf-cloud` | Stateless bare-repo deploys |
| Distributor live pricing | `kerf-cloud` | 6h sweep; DigiKey/Mouser/LCSC; `cloud.distributors` |
| STEP pre-tessellation | `kerf-tess` | Server-side glTF; capability tag `tess.step-to-glb` |
| Email (Mailer) | `kerf-cloud` | Resend/SES/SMTP |
| Everything else | OSS plugins | Storage abstraction, file-revisions, tool registry, agent loop |

## Enabling cloud

Set `cloud_enabled=true` in `kerf.toml` (or `KERF_CLOUD=1` env). This unlocks
two paths:

1. **Plugin registration** — `kerf-billing` and `kerf-cloud` only register
   their routes / tools / workers when `ctx.cloud_enabled` is true. When false,
   they still load but advertise an empty `provides=[]` list and become
   dormant.
2. **`local_mode` is forced off** — the config validator overrides
   `local_mode=true` whenever cloud is enabled.

Inspect what is actually live at runtime:

```
GET /health/capabilities
```

Look for `billing.paystack`, `cloud.workshop`, `cloud.git`, `cloud.distributors`.

## AES-GCM encryption

`packages/kerf-core/src/kerf_core/utils/encrypt.py` — domain-scoped key derivation:

```
key = SHA-256(b"kerf:enc:<domain>:<jwt_secret>")
```

Used for:
- Distributor credentials (`distributor_credentials` table) — `kerf-cloud`
- GitHub OAuth tokens (`cloud_github_tokens` table, migration 031) — `kerf-cloud`
- Email provider credentials — `kerf-cloud`

Rotating `JWT_SECRET` invalidates every encrypted row — see
[cloud-operator.md#encrypted-secret-storage](./cloud-operator.md).

## S3 Git Storer

`packages/kerf-cloud/src/kerf_cloud/storage/git_storer.py` — `S3GitStorer`
wraps pygit2 bare repos on S3:

- `clone_to_local`: downloads every S3 key under the prefix into a local bare repo.
- `push_from_local`: repacks with `git gc`, uploads pack files → loose objects →
  refs (in that order), writes a sentinel `_marker` object under conditional-put.
  Orphan keys are batch-deleted via `delete_objects`.

Consistency: objects uploaded **before** refs so a concurrent reader never
sees a ref pointing at a missing object. Two simultaneous writers are detected
via the `_marker` ETag — the loser raises `StorerConcurrencyError` and the
caller retries with fresh state.

OSS / local-install: not used. Filesystem-backed git lives directly on disk
and is handled by `pygit2` against the local repo path. The Storer is only
constructed when `STORAGE_BACKEND=s3`.

## Large-file handling (STEP ≥ 5 MB)

Files ≥ 5 MB (`LARGE_STEP_THRESHOLD = 5 * 1024 * 1024`) uploaded as
`kind='step-ref'` (migration 033):

- Binary stored as `blobs/step/<sha256>` in object storage
- DB row holds JSON pointer: `{"hash": "...", "size": N, "original_name": "...", "mime": "model/step"}`
- Download path resolves pointer and streams from blob store

Upload chunk size: `upload_chunk_size` config (default 5 242 880 bytes).
Server-side tessellation (`kerf-tess`) builds a viewport-ready glTF in the
background, recorded in the `step_tessellation_jobs` table.

## Paystack billing

`packages/kerf-billing/`:

- **webhooks** — handle `charge.success`, credit prepaid balance
- **topup** — user-initiated ZAR → prepaid credit
- **balance** — real-time deduction on each tool call; USD→ZAR daily FX rate + spread

Settlement currency: ZAR. FX rates stored in `cloud_fx_rates`, refreshed daily.
Pricing constants live in `packages/kerf-billing/src/kerf_billing/pricing.py`.

## GitHub OAuth

- `/auth/github/start` → redirect to GitHub
- `/auth/github/callback` → encrypts token via AES-GCM, upserts `cloud_github_tokens`
- `DELETE /auth/github` → revokes token

All three routes are registered by `kerf-cloud` under prefix `/auth`.

## Workshop publishing

`POST /api/workshop/publish` (owner-only, idempotent) sets `visibility='public'`.
Triggers a `cloud_email_log` entry for `workshop_published`.

Unlike + fork + library submissions also flow through this surface — they live
in `packages/kerf-cloud/src/kerf_cloud/routes_workshop.py`.

## Build

```sh
pip install -e .[mech]          # OSS-only mech persona
pip install -e .[full]          # everything incl. cloud plugins
npm run build                   # OSS frontend
npm run build:cloud             # frontend with billing UI + workshop
```

Frontend reads cloud flag from `/api/config` at runtime; backend reads
`KERF_CLOUD=1` / `cloud_enabled=true` from `.env`.

Full deploy / migrations / pricing: [cloud-operator.md](./cloud-operator.md).
