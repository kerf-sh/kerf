# Kerf Cloud

This directory and the two sibling directories `backend/cloud/` and `src/cloud/`
contain the proprietary code that powers the **hosted** version of Kerf at
kerf.app (or wherever it ends up running). It is **not** covered by the MIT
license that applies to the rest of this repo. See `cloud/LICENSE`.

## What's here vs. there

| Path                  | License     | Purpose                                    |
| --------------------- | ----------- | ------------------------------------------ |
| `LICENSE` (root)      | MIT         | Covers OSS code (everything below)         |
| `backend/**`          | MIT         | Go API server, LLM proxy, file storage     |
| `src/**`              | MIT         | React frontend                             |
| `cloud/LICENSE`       | proprietary | Terms for everything cloud-marked          |
| `backend/cloud/**`    | proprietary | Paystack billing, FX, quotas, usage events |
| `src/cloud/**`        | proprietary | Billing UI, plan selector, usage widget    |

## Why split this way

Kerf is open source so that anyone can self-host it for personal use,
contribute back, or run it in BYO-keys mode without paying us. The cloud/
directory holds the things that turn it into a paid hosted service —
mainly: payments (Paystack), per-user quotas, exchange rates, and usage
metering. None of those need to exist in the OSS build, so they live behind
a Go build tag and a Vite env flag.

## Building the OSS server (no cloud)

```bash
cd backend
go build -o ../kerf-oss ./cmd/server
./kerf-oss --env=local
```

The resulting binary contains zero cloud code. There is no billing, no
quotas, no Paystack — users either configure provider API keys via env
(self-host) or paste their own keys in a settings panel (BYO mode, when
`AUTH_OPTIONAL=true`).

## Building the hosted server (with cloud)

```bash
cd backend
go build -tags=cloud -o ../kerf-cloud ./cmd/server
./kerf-cloud --env=main
```

This adds Paystack handlers, quota middleware, and usage tracking.

## Frontend builds

OSS frontend (no billing UI):
```bash
npm run build           # mode=main, no VITE_CLOUD
```

Cloud frontend (billing UI included):
```bash
VITE_CLOUD=1 npm run build
```

## Migrations

Two independent commands, two independent tracking tables:

```bash
# OSS schema (required first)
go build -o ../kerf-migrate ./cmd/migrate
./kerf-migrate

# Cloud schema (refuses to run unless OSS schema is in place)
go build -tags=cloud -o ../kerf-migrate-cloud ./cloud/cmd/migrate
./kerf-migrate-cloud
```

- OSS migrate embeds `backend/migrations/*.sql`, tracks in `schema_migrations`.
- Cloud migrate embeds `backend/cloud/migrations/*.sql`, tracks in `cloud_schema_migrations`.
- Each binary travels with its own SQL — no runtime file-path lookups,
  works after `brew install` or a curl-installed release.

From the repo root, npm shortcuts: `npm run migrate`, `npm run migrate:cloud`, `npm run migrate:all`.

## Optional: revision-storage backfill (Phase 4)

Phase 4 introduced gzipped + diff-based `file_revisions` storage. The
schema change is applied by the regular OSS migration runner; existing
plaintext rows continue to read correctly (the read path falls back to
the legacy `content` column when `content_gz` is NULL).

A separate, **opt-in** command repacks legacy rows so they no longer
consume their full plaintext size:

```bash
go build -o ../kerf-migrate-revisions ./cmd/migrate-revisions

# Dry run — reports how many rows would be touched.
./kerf-migrate-revisions --dry-run

# Compress every row's content into content_gz, leave the legacy
# `content` column populated as a safety net.
./kerf-migrate-revisions

# Same, but additionally clear the legacy column once the gzip
# roundtrip has been verified for each row. Use only after confirming a
# successful run on a non-prod replica first.
./kerf-migrate-revisions --prune-legacy
```

The command is idempotent — re-running on an up-to-date DB is a no-op
because each row is gated on `content_gz IS NULL`. It does **not** run
on server boot; operators schedule it explicitly. Batches of 500 rows
by default; tune with `--batch=N`.

## Serving blobs through a CDN (bunny.net)

Kerf stores binary assets (user avatars, project thumbnails, STEP files)
through the `Storage` interface. By default the local backend serves
them through the auth-protected `/api/blobs/<key>` route and the s3
backend either presigns or returns a virtual-hosted bucket URL. For
hosted deploys, you almost certainly want a real CDN in front of the
bucket — bunny.net Pull Zones are cheap, fast, and require zero code
on the Kerf side beyond setting one config value.

### Setup

1. **Bucket as origin.** Create an R2 bucket (or S3 bucket) and point
   `[storage.s3]` at it:

   ```toml
   [storage.s3]
   bucket = "kerf-prod"
   region = "auto"                       # for R2
   access_key_id = "..."
   secret_access_key = "..."
   endpoint = "https://<account>.r2.cloudflarestorage.com"
   public_url_base = ""                  # leave empty — CDN takes precedence
   ```

   For R2: enable the bucket's r2.dev public domain (or attach a custom
   domain) so bunny.net can reach it. For S3: ensure the bucket policy
   allows GetObject from any origin (Pull Zones don't sign).

2. **bunny.net Pull Zone.** In the bunny.net dashboard:
   - Create a Pull Zone.
   - Origin URL = your bucket's public endpoint (e.g.
     `https://kerf-prod.<account>.r2.cloudflarestorage.com` or the
     custom domain you attached).
   - Type: Standard. (Volume tier is fine; geo-replicated is optional
     for global low-latency.)
   - Note the assigned hostname, e.g. `kerf-cdn.b-cdn.net`.

3. **Tell Kerf about it.** Add to `kerf.toml`:

   ```toml
   [storage]
   cdn_base_url = "https://kerf-cdn.b-cdn.net"
   ```

   Restart the server. From this point on, every `Storage.PublicURL`
   call returns `https://kerf-cdn.b-cdn.net/<key>?v=<unix>`. The
   `?v=<unix>` cache-buster is the avatar/thumbnail's
   `*_updated_at` epoch — every upload mints a fresh URL, so edge
   caches don't serve stale content even with long TTLs.

4. **(Optional) Edge cache rules.** In the bunny.net Hostname Edge
   Rules:
   - Set "Cache Control: Override" → `public, max-age=2592000,
     immutable` for `*.jpg`, `*.png`, `*.webp` paths under `users/`
     and `projects/`. With the `?v=` cache-buster, immutable is safe.
   - Optionally set CORS to `*` so future direct-from-CDN fetches
     (e.g. avatar inside Workshop pages) work cross-origin.

### What happens locally?

When `cdn_base_url` is empty (the default for self-hosted / local
dev), `Storage.PublicURL` falls back to `/api/blobs/<key>?v=<unix>`,
which is auth-protected. No external traffic, no CDN dependency. The
single string `cdn_base_url` is the entire knob distinguishing "serve
through my CDN" from "serve through the auth-protected backend."

### Cache invalidation

You generally don't need to purge the bunny.net cache. Every blob
write mints a new public URL with a different `?v=` query parameter,
so stale entries simply stop being referenced. The exception is if
you ever rotate a key in place without bumping `*_updated_at` — for
that case, the bunny.net dashboard's "Purge Single URL" button is the
quickest fix.

## Encrypted-secret storage (JWT secret rotation gotcha)

Two subsystems persist operator/user secrets at rest, both encrypted
via AES-GCM with a key derived from `cfg.JWTSecret`:

| Table                       | What                                       | Domain string                  |
| --------------------------- | ------------------------------------------ | ------------------------------ |
| `cloud_github_tokens`       | Per-user GitHub OAuth access tokens (cloud) | `cloud:github-token`           |
| `distributor_credentials`   | Operator-configured distributor API keys    | `distributor-credentials`      |

The shared helper lives at `backend/internal/auth/encrypt.go` (the
older `backend/cloud/git/encrypt.go` is a thin re-export, kept for
the cloud build's import graph).

**Rotating `JWT_SECRET` invalidates every encrypted row.** This is
intentional — the secret IS the key, and there's no way to re-derive
the old key after the rotation. Practical consequences:

- Existing GitHub OAuth tokens are unreadable; users must re-link
  their GitHub account on the next push/pull.
- Distributor credentials must be re-entered through
  `/admin/distributors`. The Refresh button on Library pages will
  return 502 errors until they are.

If you must rotate, plan a brief window where:

1. Operators are warned to re-enter distributor credentials.
2. Users re-link GitHub on next git operation (the cloud GitHub
   handler returns a "not linked" error and the frontend surfaces
   the OAuth start link).

A real KMS path (Vault, cloud HSM) is the v2 plan; today's "JWT
secret IS the key" is consciously low-tech.

## Pricing model (current)

- **Display currency:** USD everywhere on the UI
- **Settlement currency:** ZAR via Paystack (only currency Paystack ZA supports)
- **FX:** USD→ZAR fetched daily, stored in `cloud_fx_rates`. Charges convert
  USD price → ZAR at charge time using current rate + small spread.
- **Tokens:** raw provider cost × 1.20 (20% markup), per-1M-token rates in
  `backend/cloud/pricing/pricing.go`.
- **Storage:** $0.20/GB-month, billed on max-of-month, 50MB free for everyone.
- **Free tier:** unlimited projects, 50MB storage. No paid tier limits — pure
  metered billing on top of the included free quota.
- **Email:** transactional only, absorbed (not metered).

See `backend/cloud/pricing/pricing.go` for the current numbers.

## Transactional email

The hosted tier sends a small set of system emails: welcome, password
reset (request + completion), top-up receipt, low-balance reminder,
GitHub-link confirmation, and Workshop publish notification. There is
no marketing email; the unsubscribe footer on every template is purely
informational.

### Provider precedence

The Mailer dispatches through the highest-priority enabled provider in
this order:

1. **Resend** (preferred default — simplest config)
2. **AWS SES v2**
3. **SMTP** (any third-party relay or self-hosted MTA)

Multiple providers can be configured at once; the lower-priority ones
sit dormant. Failover-on-error is **not** automatic — retries hit the
same provider with exponential backoff (30s → 2m → 8m, capped at 3
attempts). To switch active providers, the operator disables the higher
one in `/admin/email`.

### Setup

Open `/admin/email` (admin role only) after the server is running.

#### Resend (recommended)

1. Sign up at [resend.com](https://resend.com), verify your sending
   domain (DNS records for SPF + DKIM).
2. Generate an API key under **API Keys** → "Create API Key" with
   sending permission only.
3. Click **Configure** on the Resend row at `/admin/email`. Paste:
   - **API Key:** `re_…`
   - **From email:** `kerf@yourdomain.com` (must be on the verified domain)
   - **From name:** `kerf` (optional)
4. Save. Use the **Send test** button to fire a `welcome` template at
   your own address — should arrive within seconds.

#### AWS SES v2

1. In the AWS console, go to **SES → Verified identities** and verify
   either the from-domain (preferred — DKIM is part of the verification)
   or the specific from-address.
2. Move the account out of the SES sandbox if you want to send to
   addresses you haven't explicitly verified — see "Request production
   access" in the SES console.
3. Click **Configure** on the SES row at `/admin/email`. Paste:
   - **From email:** verified address
   - **From name:** optional
   - **Region:** `us-east-1` (or wherever your SES identities live)
   - **AWS access key id / secret access key:** optional. Leave both
     empty if the server runs with an IAM instance role / ECS task
     role / static `AWS_*` env vars; the SDK's default credential chain
     picks them up automatically.

#### SMTP (third-party relay or self-hosted MTA)

The SMTP path is here for operators who want their email path inside
their own perimeter, or who use a relay that doesn't expose a JSON API
(Postmark/Mailgun/SendGrid all accept SMTP, even if their primary API
is HTTP).

1. Get SMTP credentials from your relay or stand up your own MTA.
2. Click **Configure** on the SMTP row at `/admin/email`. Paste:
   - **From email** + **From name** (optional)
   - **SMTP host** (e.g. `smtp.postmarkapp.com`)
   - **SMTP port** (typically 587 for STARTTLS, 465 for implicit TLS — net/smtp uses STARTTLS-on-PLAIN-auth)
   - **Username** / **Password** as supplied by the relay

If you're running your own MTA, ensure DKIM + SPF are signed/published
for the from-domain — otherwise transactional mail will land in spam
folders or be rejected outright. Resend or SES handle this for you;
SMTP is the "you know what you're doing" path.

### Encryption-at-rest gotcha

Provider credentials are AES-GCM encrypted with a key derived from
`JWT_SECRET` (domain string `cloud:email-credentials`). Rotating
`JWT_SECRET` invalidates every stored credential — the operator must
re-enter every provider's API key/SMTP password after a rotation. This
is the same caveat that applies to `distributor_credentials` and
`cloud_github_tokens`.

### What if no provider is configured?

The Mailer enqueues every send into `cloud_email_log` with `status='queued'`
regardless of provider state. If no provider is configured (or all are
disabled), queued rows pile up but **are not** automatically marked
failed — the operator may be mid-configuration, and a wall of failed
sends after the first valid config would be confusing. Configure a
provider, hit **Refresh** on the log, and the drain catches up within
seconds.

If you want to flush a stuck queue manually:

```sql
update cloud_email_log set status = 'failed', error = 'manually drained'
 where status = 'queued';
```

### Triggers

| Event                                          | Template                  |
| ---------------------------------------------- | ------------------------- |
| `POST /auth/register` succeeds (email/password)| `welcome`                 |
| `POST /auth/password-reset/request`            | `password_reset`          |
| Password reset link consumed                   | `password_reset_complete` |
| Paystack `charge.success` webhook              | `billing_receipt`         |
| Token debit drops balance < $1 (max 1×/24h)    | `low_balance`             |
| `/auth/github/callback` succeeds               | `github_linked`           |
| First `POST /api/workshop/publish` per project | `workshop_published`      |

The Google-OAuth path of `/auth/google/callback` deliberately does NOT
fire `welcome` today — Google sign-in is treated as a returning-user
flow, not a fresh signup. Add a hook there if you want to change that.


## Curated manufacturer libraries (Library Phase 3)

Verified-publisher accounts (Adafruit, SparkFun, Pololu, McMaster,
Misumi, …) get a star badge in the Workshop and their Parts float to
the top of the Workshop parts browse. The flag itself
(`users.is_verified_publisher`) is operator-toggled — there's no
self-serve "request verification" flow.

### Toggling the flag

Open `/admin/publishers` while signed in as an admin
(`account_role='admin'` or `'system'`). The page lists every
non-system user with a `library_count` rollup; flip the toggle on a
row to set `is_verified_publisher`. Backed by:

- `GET /api/admin/publishers?search=&verified_only=&cursor=&limit=`
- `PUT /api/admin/publishers/{user_id}` — `{is_verified_publisher: bool}`

Both endpoints are admin-gated. The Workshop part-browse query
(`GET /api/workshop/parts`) sorts by `is_verified_publisher desc,
files.updated_at desc` so flipping the flag is enough to reorder
the browse — no migration, no cache busting.

### Importing a curated library

The `kerf library-import` command takes a YAML manifest and upserts
a publisher user, a project to hold the Parts, and one Part file per
manifest entry:

```bash
go build -o ../kerf-library-import ./cmd/library-import
./kerf-library-import --manifest ../samples/libraries/adafruit-sensors.yaml
```

Pass `--dry-run` to see the plan without writing. Re-running the
same manifest is idempotent (parts are upserted by `(project_id,
name)` — content updates if changed, stays put otherwise). The
output reports new/updated/unchanged counts:

    imported 7 parts (5 new, 1 updated, 1 unchanged) into project …

Three sample manifests ship in the repo at
`samples/libraries/`:

- `adafruit-sensors.yaml` — 7 popular sensor breakout boards
- `mcmaster-fasteners.yaml` — 10 metric machine screws and nuts
- `pololu-motor-drivers.yaml` — 5 stepper / DC driver carriers

These are real products with real MPNs and URLs verified at the
time of authoring; pricing is intentionally omitted because the
existing distributor sweep refreshes it once a Part lands in the
DB. Hand-baking prices would lock the manifest to a stale snapshot.

### Manifest format

```yaml
publisher_email: "adafruit@kerf.system"
publisher_name: "Adafruit Industries"
publisher_url: "https://www.adafruit.com"
mark_verified: true                # set is_verified_publisher = true on
                                   # create or re-import
library_name: "Adafruit Sensors"
library_description: "…"
library_visibility: "public"        # public | unlisted | private
parts:
  - name: "BMP280 Pressure Sensor Breakout"
    description: "…"
    category: "sensor"
    manufacturer: "Bosch / Adafruit"
    mpn: "BMP280"
    visibility: "public"
    distributors:
      - name: "adafruit"
        sku: "2651"
        url: "https://www.adafruit.com/product/2651"
    metadata: {vcc: "3.3V or 5V", interface: "I2C/SPI"}
```

Strict-keys mode is on — typo'd field names error out with a clear
"unknown key" message rather than silently dropping the value.
Distributor URLs are validated as http(s); pricing/stock are
populated by the distributor sweep, never baked into the manifest.

