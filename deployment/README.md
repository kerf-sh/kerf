# Kerf deployment guides

Kerf ships as a **single Docker image** — the compiled Vite SPA plus
FastAPI backend plus the chosen plugin persona — built from the root
`Dockerfile`. The same image runs everywhere.

> **Production runs on Koyeb.** That's what powers `kerf.sh`. The other
> guides in this directory (GCP, AWS, Azure, DigitalOcean) are **reference
> configurations** for users self-hosting Kerf on a cloud they already
> use. We don't operate Kerf on those platforms — but the Docker image
> + env-var contract is identical everywhere, so the configurations are
> known-working starting points. If you don't have a strong reason to
> pick something else, use [koyeb.md](./koyeb.md).

## Provider comparison

| Provider | Best for | Cost @ 1k users | SA region | S3-compatible storage | Workers |
|---|---|---|---|---|---|
| **Koyeb** | GPU workloads, hosted tier, Frankfurt presence | ~$60-90/mo | no (closest: `fra`) | Tigris (any host) | separate service |
| **GCP Cloud Run** | Serverless scale-to-zero, existing GCP shop | ~$50-80/mo | yes (`africa-south1`) | Cloud Storage (S3 interop) | Cloud Run Jobs / second service |
| **AWS ECS Fargate** | Compliance-heavy, GovCloud, S3-native | ~$120-150/mo | yes (`af-south-1`) | S3 (native) | separate task |
| **Azure Container Apps** | Microsoft shop, SSO via Entra ID | ~$100-130/mo | yes (`southafricanorth`) | Blob + MinIO facade (not native — see caveat) | separate revision |
| **DigitalOcean App Platform** | Simplest setup, lowest friction | ~$60-80/mo | no (closest: `lon1`) | DO Spaces (S3 interop) | Worker component |

## Which provider to choose

**Koyeb** is the hosted-tier default. It provides a full GPU ladder
(L4 / L40S / A100 / H100) for rendering and FEM workloads, scale-to-zero
GPU billing, and a Frankfurt (`fra`) presence that meets GDPR
data-residency requirements. See [koyeb.md](./koyeb.md).

**GCP Cloud Run** makes sense if you are already on GCP (Workspace,
BigQuery, etc.) or want serverless scale-to-zero with a $0 floor when
idle. `africa-south1` (Johannesburg) covers SA users well. See
[gcp.md](./gcp.md) and [gcs.md](./gcs.md).

**AWS ECS Fargate** is the choice for compliance-heavy deployments (SOC
2, GovCloud, FedRAMP), teams already deep in AWS (RDS, IAM, CloudWatch),
or when you need the full breadth of AWS services alongside Kerf. S3 is
the canonical storage backend — no interop layer needed. Note: AWS has
the highest egress costs of the five providers. See [aws.md](./aws.md)
and [s3.md](./s3.md).

**Azure Container Apps** fits organisations that are already in
Microsoft's ecosystem — Entra ID for SSO, Teams integration, Azure
DevOps pipelines. `southafricanorth` (Johannesburg) has SA presence.
**Important caveat**: Azure Blob Storage is not S3-compatible, so
storage requires either a MinIO facade or cross-cloud S3. See
[azure.md](./azure.md) and [azure-blob.md](./azure-blob.md) for the
full discussion before deploying.

**DigitalOcean App Platform** has the lowest operational friction for
solo developers and small teams. Spaces is S3-compatible and costs a
flat $5/mo for 250 GB. The downside: no SA region. Users in South Africa
see ~150-250 ms to `lon1` (London). If SA latency is a hard requirement,
use GCP Cloud Run (`africa-south1`) or AWS Fargate (`af-south-1`) instead.
See [digitalocean.md](./digitalocean.md) and [spaces.md](./spaces.md).

## Storage compatibility quick-reference

| Storage | S3-compatible | Extra setup |
|---|---|---|
| Tigris (`fly.storage.tigris.dev`) | yes | endpoint URL only — works from any host |
| AWS S3 | yes (native) | none |
| GCP Cloud Storage | yes (HMAC interop) | enable interop, create HMAC keys |
| DO Spaces | yes | endpoint URL only |
| Azure Blob Storage | **no** | MinIO facade or cross-cloud S3 (see [azure-blob.md](./azure-blob.md)) |

## Guide index

| Guide | Content |
|---|---|
| [koyeb.md](./koyeb.md) | Koyeb — hosted-tier canonical target, GPU ladder, Frankfurt |
| [tigris.md](./tigris.md) | Tigris object storage (works from any host) |
| [gcp.md](./gcp.md) | GCP Cloud Run — deploy, workers, custom domain, cost |
| [gcs.md](./gcs.md) | Google Cloud Storage — HMAC keys, interop, lifecycle |
| [aws.md](./aws.md) | AWS ECS Fargate — deploy, ALB, workers, multi-region |
| [s3.md](./s3.md) | AWS S3 — bucket policy, lifecycle, KMS, VPC endpoint |
| [azure.md](./azure.md) | Azure Container Apps — deploy, workers, AKS alternative |
| [azure-blob.md](./azure-blob.md) | Azure Blob — S3 adapter gap, MinIO facade, future native adapter |
| [digitalocean.md](./digitalocean.md) | DO App Platform — deploy, workers, DOKS alternative |
| [spaces.md](./spaces.md) | DO Spaces — S3 interop, CDN, lifecycle |

## Common env vars (all providers)

The following env vars are required on every provider regardless of
where you deploy. Set secrets via your provider's secret manager (Secret
Manager, Secrets Manager, Key Vault, App Platform secrets).

| Env var | Notes |
|---|---|
| `DATABASE_URL` | Postgres connection string with `sslmode=require` |
| `JWT_SECRET` | Random 32-byte hex; generate with `openssl rand -hex 32` |
| `STORAGE_BACKEND` | Always `s3` on current supported providers |
| `KERF_STORAGE_S3_BUCKET` | Bucket/space name |
| `KERF_STORAGE_S3_REGION` | Provider-specific region string |
| `KERF_STORAGE_S3_ENDPOINT` | Omit for native AWS S3; set for all others |
| `KERF_STORAGE_S3_ACCESS_KEY` | Omit when using ECS task role (AWS) |
| `KERF_STORAGE_S3_SECRET_KEY` | Omit when using ECS task role (AWS) |
| `LLM_ANTHROPIC_API_KEY` | Anthropic API key for AI features |
| `CLOUD_PAYSTACK_SECRET_KEY` | Paystack billing (hosted deployments) |
| `CLOUD_PAYSTACK_PUBLIC_KEY` | Paystack billing (hosted deployments) |
| `CLOUD_ENABLED` | Set to `true` for hosted deployments |
| `KERF_LOCAL_MODE` | Set to `false` for hosted deployments |

## Migrations

Migrations are **not automatic** on any provider. After each deploy that
ships schema changes, run:

```sh
python -m kerf_core.db.migrations.runner $DATABASE_URL
```

The method to exec this command differs per provider:

| Provider | How to run migrations |
|---|---|
| Koyeb | `koyeb service exec kerf -- python -m kerf_core.db.migrations.runner $DATABASE_URL` |
| GCP | `gcloud run jobs execute kerf-migrate --region=africa-south1 --wait` |
| AWS | `aws ecs execute-command --cluster kerf --interactive --command "python -m kerf_core.db.migrations.runner $DATABASE_URL"` |
| Azure | `az containerapp exec --name kerf --resource-group kerf-rg --command "python -m kerf_core.db.migrations.runner"` |
| DigitalOcean | `doctl apps console ${APP_ID} --component web -- python -m kerf_core.db.migrations.runner` |

## Dockerfile and image personas

The `Dockerfile` takes a `KERF_PERSONA` build arg:

| Persona | Use |
|---|---|
| `full` | All plugins — use for the web service |
| `compute-only` | FEM, topo, autoroute only — use for worker services |
| `api-only` | Stateless API gateway — for edge/CDN nodes |

Workers should use `compute-only` to keep the image smaller and avoid
loading unnecessary plugins at startup.
