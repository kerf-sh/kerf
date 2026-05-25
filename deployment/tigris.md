# Object storage: Cloudflare R2 (hosted tier) and Tigris / S3 alternatives

## Hosted tier — Cloudflare R2

The hosted tier (`kerf.sh`, running on Fly.io) uses **Cloudflare R2** as
the canonical blob store. R2's zero egress cost makes it the cheapest
option at scale — there is no charge for data transferred out of R2 to
the internet. Storage is $0.015/GB-month.

### Provisioning R2

1. Log in to [dash.cloudflare.com](https://dash.cloudflare.com) →
   **R2 Object Storage** → **Create bucket** (e.g. `kerf-blobs-prod`).
2. Under **Manage R2 API tokens** → **Create API token** with
   **Object Read & Write** permission scoped to the bucket.
3. Note your **Account ID** (shown in the URL bar after login:
   `https://dash.cloudflare.com/<ACCOUNT_ID>/r2`).

Map to Kerf env vars / Fly secrets:

| R2 value | Kerf env var |
|---|---|
| Bucket name | `KERF_STORAGE_S3_BUCKET` |
| `https://<ACCOUNT_ID>.r2.cloudflarestorage.com` | `KERF_STORAGE_S3_ENDPOINT` |
| `auto` | `KERF_STORAGE_S3_REGION` |
| Access Key ID | `KERF_STORAGE_S3_ACCESS_KEY` |
| Secret Access Key | `KERF_STORAGE_S3_SECRET_KEY` |

Always set `STORAGE_BACKEND=s3`. The endpoint is the **account-level
host only** — no bucket suffix in the URL. Kerf's storage layer appends
the bucket name.

### Enable versioning (recommended)

```sh
aws --endpoint-url "https://<ACCOUNT_ID>.r2.cloudflarestorage.com" \
  s3api put-bucket-versioning \
  --bucket kerf-blobs-prod \
  --versioning-configuration Status=Enabled
```

### Lifecycle policies

R2 supports S3-compatible lifecycle rules. Useful examples:

- Expire derived mesh tessellations after 30 days unused.
- Expire temporary upload staging objects after 7 days.

```sh
aws --endpoint-url "https://<ACCOUNT_ID>.r2.cloudflarestorage.com" \
  s3api put-bucket-lifecycle-configuration \
  --bucket kerf-blobs-prod \
  --lifecycle-configuration file://lifecycle.json
```

---

## Self-host alternatives — Tigris, S3, B2, and other S3-compatible stores

The `STORAGE_BACKEND=s3` path works with **any S3-compatible endpoint**
— Tigris, Backblaze B2, AWS S3, MinIO, and others. All require the same
four env vars (`KERF_STORAGE_S3_BUCKET`, `KERF_STORAGE_S3_ENDPOINT`,
`KERF_STORAGE_S3_ACCESS_KEY`, `KERF_STORAGE_S3_SECRET_KEY`) plus
`KERF_STORAGE_S3_REGION`.

### Tigris

[Tigris](https://www.tigrisdata.com/) is an S3-compatible object-storage
service with anycast routing and automatic multi-region replication.
It is a valid self-host option — provisioned at
[console.tigris.dev](https://console.tigris.dev):

```sh
# Using the Tigris CLI:
tigris bucket create kerf-blobs

# Output includes:
#   BUCKET_NAME=kerf-blobs
#   AWS_ACCESS_KEY_ID=tid_...
#   AWS_SECRET_ACCESS_KEY=tsec_...
#   AWS_ENDPOINT_URL_S3=https://fly.storage.tigris.dev
```

Map to Kerf env vars:

| Tigris var | Kerf env var |
|---|---|
| `BUCKET_NAME` | `KERF_STORAGE_S3_BUCKET` |
| `AWS_ACCESS_KEY_ID` | `KERF_STORAGE_S3_ACCESS_KEY` |
| `AWS_SECRET_ACCESS_KEY` | `KERF_STORAGE_S3_SECRET_KEY` |
| `AWS_ENDPOINT_URL_S3` | `KERF_STORAGE_S3_ENDPOINT` |
| `auto` | `KERF_STORAGE_S3_REGION` |

> The endpoint `fly.storage.tigris.dev` is Tigris's own public hostname —
> it is S3-compatible and reachable from any host, not just Fly.io.

Pricing: ~$0.02/GB-month storage with standard egress charges. For
zero-egress storage, use R2.

### AWS S3

See [s3.md](./s3.md) for the full S3 guide.

### Backblaze B2

Set `KERF_STORAGE_S3_ENDPOINT=https://s3.<REGION>.backblazeb2.com` and
use B2's S3-compatible application keys. Pricing: $0.006/GB-month storage,
$0.01/GB egress (first 1 GB/day free).

---

## LFS objects

Large binary assets in git-backed projects live on **bunny.net** (see
the Git LFS substrate docs). LFS is independent of the R2/Tigris/S3
blob backend — the two stores serve different purposes and are not
interchangeable.

---

## Local dev

For local dev or testing, point at MinIO:

```sh
STORAGE_BACKEND=s3
KERF_STORAGE_S3_ENDPOINT=http://localhost:9000
KERF_STORAGE_S3_BUCKET=kerf-local
KERF_STORAGE_S3_ACCESS_KEY=minioadmin
KERF_STORAGE_S3_SECRET_KEY=minioadmin
KERF_STORAGE_S3_REGION=us-east-1
```

The `docker-compose.yml` includes a MinIO service for this.

---

## Troubleshooting

- **403 forbidden on upload**: check `KERF_STORAGE_S3_BUCKET` matches
  the exact bucket name. For R2, also confirm the API token has write
  permission on that specific bucket.
- **Endpoint misconfiguration (R2)**: the endpoint must be the
  account-level URL only — `https://<ACCOUNT_ID>.r2.cloudflarestorage.com`.
  Do not append the bucket name or a path.
- **Unexpected egress charges**: if using Tigris or S3, egress is billed
  per GB. R2 has zero egress. Verify `KERF_STORAGE_S3_ENDPOINT` is set
  to the correct provider endpoint.
- **Per-object size limit**: 5 TiB (S3 standard). Kerf uses chunked
  multipart uploads above ~50 MB; all listed providers support S3
  multipart.
