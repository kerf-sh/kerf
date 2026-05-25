# Tigris storage

[Tigris](https://www.tigrisdata.com/) is an S3-compatible object-storage
service. Kerf uses it as the object-storage backend for project blobs,
mesh tessellations, project thumbnails, and Workshop content.

Tigris was originally developed as a fly.io-native service but is
accessible via the public endpoint `fly.storage.tigris.dev` from
**any host** — including Koyeb, GCP, and AWS. The endpoint hostname is
the real public hostname; it is not Fly-specific.

## Why Tigris (vs Cloudflare R2 or AWS S3)

- **Anycast network** — low-latency access from any region; from Koyeb
  Frankfurt (`fra`), Tigris Frankfurt-replicated objects are served with
  minimal round-trip (~1–5 ms typical for same-region cache hits).
- **S3-compatible API** — drop-in for the existing `STORAGE_BACKEND=s3`
  path. No code changes.
- **Multi-region by default** — Tigris replicates writes to multiple
  regions automatically.
- **Pricing**: ~$0.02/GB-month storage; egress at standard Tigris rates
  from any host. R2 is $0.015/GB; AWS S3 is $0.023/GB plus $0.09/GB egress.

The model in `billingmodel/projections.py` uses $0.02/GB-mo for Tigris.

## Provisioning

Sign in to [console.tigris.dev](https://console.tigris.dev), create an
organisation (if you haven't already), then create a bucket:

```sh
# Using the Tigris CLI (pip install tigris-cli, or use the web console).
# The CLI prints credentials on bucket creation:
tigris bucket create kerf-blobs

# Output (save these values):
#   BUCKET_NAME=kerf-blobs
#   AWS_ACCESS_KEY_ID=tid_...
#   AWS_SECRET_ACCESS_KEY=tsec_...
#   AWS_ENDPOINT_URL_S3=https://fly.storage.tigris.dev
```

Alternatively, create the bucket and access key from the
[Tigris web console](https://console.tigris.dev) under
**Buckets → Create bucket**, then generate an access key under
**Access Keys → Create key**.

Map these to Kerf's env vars:

| Tigris var | Kerf env var |
|---|---|
| `BUCKET_NAME` | `KERF_STORAGE_S3_BUCKET` |
| `AWS_ACCESS_KEY_ID` | `KERF_STORAGE_S3_ACCESS_KEY` |
| `AWS_SECRET_ACCESS_KEY` | `KERF_STORAGE_S3_SECRET_KEY` |
| `AWS_ENDPOINT_URL_S3` | `KERF_STORAGE_S3_ENDPOINT` |

Inject into your Koyeb service as secrets:

```sh
koyeb secrets create KERF_STORAGE_S3_BUCKET    --value "kerf-blobs"
koyeb secrets create KERF_STORAGE_S3_ACCESS_KEY --value "tid_..."
koyeb secrets create KERF_STORAGE_S3_SECRET_KEY --value "tsec_..."
koyeb secrets create KERF_STORAGE_S3_ENDPOINT   --value "https://fly.storage.tigris.dev"
koyeb secrets create KERF_STORAGE_S3_REGION     --value "auto"
```

Then reference each secret name in your `koyeb.yaml` service env block.

## Versioning (recommended)

Enable bucket versioning so that an accidental delete or overwrite is
recoverable. Run once per bucket using the AWS CLI against the Tigris
endpoint:

```sh
aws --endpoint-url=https://fly.storage.tigris.dev \
  s3api put-bucket-versioning \
  --bucket kerf-blobs-abc123 \
  --versioning-configuration Status=Enabled
```

## Lifecycle policies (optional)

Tigris supports S3-compatible lifecycle rules. Useful examples:

- Expire derived artifacts (mesh tessellations) after 30 days unused.
- Transition project thumbnails older than 90 days to colder storage if
  Tigris adds tiering.

```sh
# Apply a lifecycle.json describing your rules:
aws --endpoint-url=https://fly.storage.tigris.dev \
  s3api put-bucket-lifecycle-configuration \
  --bucket kerf-blobs-abc123 \
  --lifecycle-configuration file://lifecycle.json
```

## Limits worth knowing

- **Per-object size**: 5 TiB (S3 standard).
- **Multipart upload threshold**: Kerf uses chunked uploads above ~50MB
  (see `kerf-api` chunked-upload helpers). Tigris fully supports S3
  multipart.
- **Bucket count**: per Tigris org pricing — check the Tigris dashboard.

## Local dev

For local dev or test, point at MinIO instead:

```sh
# In .env or kerf.toml
STORAGE_BACKEND=s3
KERF_STORAGE_S3_ENDPOINT=http://localhost:9000
KERF_STORAGE_S3_BUCKET=kerf-local
KERF_STORAGE_S3_ACCESS_KEY=minioadmin
KERF_STORAGE_S3_SECRET_KEY=minioadmin
```

The `docker-compose.yml` includes a MinIO service for this.

## Troubleshooting

- **403 forbidden on upload**: check `KERF_STORAGE_S3_BUCKET` matches the
  exact bucket name (it's prefixed with a random suffix).
- **Upload latency**: Tigris uses anycast routing. From Koyeb Frankfurt,
  requests hit Tigris's Frankfurt edge; latency is typically 1–10 ms for
  small objects. For very large uploads, multipart is automatically used
  by the Kerf chunked-upload helpers.
- **Egress charges**: standard Tigris egress rates apply from all hosts.
  If you see unexpected egress, verify `KERF_STORAGE_S3_ENDPOINT` is set to
  `https://fly.storage.tigris.dev`.
