# DigitalOcean deployment

Kerf deploys to DigitalOcean using **App Platform** — the simplest
managed container hosting DigitalOcean offers. No cluster to manage, no
load balancer to provision; you push a Docker image and App Platform
handles routing, TLS, and scaling.

If you outgrow App Platform (need custom ingress, Istio, PodDisruptionBudgets),
DigitalOcean Kubernetes (DOKS) is the upgrade path. See
[Kubernetes alternative (DOKS)](#kubernetes-alternative-doks) below.

**No SA region**: DigitalOcean does not have a data centre in South
Africa. The closest options are `lon1` (London) and `fra1` (Frankfurt).
Expect 150-250 ms round trips from Johannesburg. For latency-sensitive
SA workloads, Fly.io (`jnb` Johannesburg) is the hosted-tier and
self-host option with the lowest SA latency.

## Prerequisites

- `doctl` installed: `brew install doctl`
- Authenticated: `doctl auth init`
- A DigitalOcean account with a billing method attached
- DO Container Registry: see [Image registry](#image-registry-docr) below
- DO Managed Postgres: see [Postgres](#postgres-managed-databases) below
- DO Spaces bucket: see [spaces.md](./spaces.md)

## Region selection

| Audience | Region | Notes |
|---|---|---|
| SA users | `lon1` (London) | Closest to SA (~150ms) |
| EU users | `fra1` (Frankfurt) or `ams3` (Amsterdam) | |
| US users | `nyc3` (New York) | |

There is no `jnb` or African region on DigitalOcean. If SA latency is a
hard requirement, use Fly.io (`jnb` Johannesburg) instead — see
[fly.md](./fly.md).

## Image registry (DOCR)

```sh
REGION=lon1

# Create a registry (one per DO team — shared across apps)
doctl registry create kerf-registry --subscription-tier basic

# Authenticate Docker
doctl registry login

# Build and push
IMAGE="registry.digitalocean.com/kerf-registry/kerf:latest"
docker build --build-arg KERF_PERSONA=full -t "${IMAGE}" .
docker push "${IMAGE}"
```

Image path: `registry.digitalocean.com/<registry-name>/kerf:<tag>`

App Platform can pull directly from DOCR — no additional auth
configuration needed when the app and registry are in the same DO
account.

## Postgres (Managed Databases)

```sh
doctl databases create kerf-pg \
  --engine pg \
  --version 16 \
  --region "${REGION}" \
  --size db-s-1vcpu-1gb \
  --num-nodes 1
```

`db-s-1vcpu-1gb` ($15/mo) is fine for development and early users.
For production, use `db-s-2vcpu-4gb` ($60/mo) or `db-s-4vcpu-8gb`
($120/mo) with 2 standby nodes for HA.

```sh
# Get connection string
doctl databases connection kerf-pg --format URI
```

Connection string format:
```
postgresql://doadmin:<password>@kerf-pg-do-user-<id>.<region>.db.ondigitalocean.com:25060/defaultdb?sslmode=require
```

Create a dedicated database and user for Kerf:

```sh
doctl databases db create kerf-pg kerf
doctl databases user create kerf-pg kerf_app
```

## Spaces (storage)

See [spaces.md](./spaces.md) for full setup. DO Spaces is S3-compatible;
`STORAGE_BACKEND=s3` works natively.

Quick summary:

```sh
# Create a Space (bucket)
doctl spaces create kerf-blobs --region "${REGION}"

# Create access keys
doctl spaces keys create --name kerf-api --grants "bucket:kerf-blobs:readwrite"
```

Set these env vars on the App:
```
STORAGE_BACKEND=s3
KERF_STORAGE_S3_ENDPOINT=https://<region>.digitaloceanspaces.com
KERF_STORAGE_S3_BUCKET=kerf-blobs
KERF_STORAGE_S3_REGION=<region>
KERF_STORAGE_S3_ACCESS_KEY=<key>
KERF_STORAGE_S3_SECRET_KEY=<secret>
```

## First deploy

App Platform uses a declarative spec file. Save the following as
`deployment/do-app-spec.yaml`, replacing placeholders:

```yaml
name: kerf
region: lon1

services:
  - name: web
    image:
      registry_type: DOCR
      registry: kerf-registry
      repository: kerf
      tag: latest
    instance_size_slug: professional-xs
    instance_count: 1
    http_port: 8080
    routes:
      - path: /
    health_check:
      http_path: /healthz
      initial_delay_seconds: 10
      period_seconds: 30
    envs:
      - key: ENV
        value: cloud
      - key: PORT
        value: "8080"
      - key: STORAGE_BACKEND
        value: s3
      - key: KERF_STORAGE_S3_ENDPOINT
        value: https://lon1.digitaloceanspaces.com
      - key: KERF_STORAGE_S3_REGION
        value: lon1
      - key: CLOUD_ENABLED
        value: "true"
      - key: DATABASE_URL
        value: "postgresql://kerf_app:<password>@..."
        type: SECRET
      - key: JWT_SECRET
        value: REPLACE_ME
        type: SECRET
      - key: KERF_STORAGE_S3_BUCKET
        value: kerf-blobs
      - key: KERF_STORAGE_S3_ACCESS_KEY
        value: REPLACE_ME
        type: SECRET
      - key: KERF_STORAGE_S3_SECRET_KEY
        value: REPLACE_ME
        type: SECRET
      - key: LLM_ANTHROPIC_API_KEY
        value: REPLACE_ME
        type: SECRET
      - key: CLOUD_PAYSTACK_SECRET_KEY
        value: REPLACE_ME
        type: SECRET
      - key: CLOUD_PAYSTACK_PUBLIC_KEY
        value: REPLACE_ME
        type: SECRET

workers:
  - name: worker
    image:
      registry_type: DOCR
      registry: kerf-registry
      repository: kerf
      tag: latest
    instance_size_slug: professional-s
    instance_count: 1
    envs:
      - key: KERF_WORKERS_ONLY
        value: "true"
      - key: STORAGE_BACKEND
        value: s3
      - key: CLOUD_ENABLED
        value: "true"
      - key: DATABASE_URL
        value: "postgresql://kerf_app:<password>@..."
        type: SECRET
      - key: KERF_STORAGE_S3_BUCKET
        value: kerf-blobs
      - key: KERF_STORAGE_S3_ACCESS_KEY
        value: REPLACE_ME
        type: SECRET
      - key: KERF_STORAGE_S3_SECRET_KEY
        value: REPLACE_ME
        type: SECRET
    run_command: kerf-server --host 0.0.0.0 --port 8080 --workers-only
```

Deploy:

```sh
doctl apps create --spec deployment/do-app-spec.yaml
```

Run migrations once the app is running:

```sh
APP_ID=$(doctl apps list --format ID --no-header | head -1)

doctl apps console "${APP_ID}" \
  --component web \
  -- python -m kerf_core.db.migrations.runner
```

## Subsequent deploys

Update the image tag and redeploy:

```sh
docker build --build-arg KERF_PERSONA=full -t "${IMAGE}" .
docker push "${IMAGE}"

# Trigger a deployment of the app
doctl apps create-deployment "${APP_ID}"
```

Or point App Platform at your GitHub repo and let it auto-deploy on push
(set `github` source in the spec instead of `image`).

## Scaling

```sh
# Update instance count for the web service
doctl apps update "${APP_ID}" \
  --spec <(cat deployment/do-app-spec.yaml \
    | python3 -c "import sys,yaml; s=yaml.safe_load(sys.stdin); s['services'][0]['instance_count']=3; print(yaml.dump(s))")
```

Or edit `do-app-spec.yaml` and run `doctl apps update "${APP_ID}" --spec deployment/do-app-spec.yaml`.

App Platform instance size slugs (verify on DO pricing page):

| Slug | vCPU | RAM | Price |
|---|---|---|---|
| `professional-xs` | 1 | 512 MiB | $12/mo |
| `professional-s` | 1 | 1 GiB | $25/mo |
| `professional-m` | 2 | 2 GiB | $50/mo |
| `professional-l` | 4 | 8 GiB | $100/mo |

For a production Kerf web instance, `professional-m` is a good starting
point. Workers benefit from `professional-l` for compute-heavy jobs.

## Workers (Worker component)

The `workers` block in the app spec above deploys a Worker component —
App Platform's name for a background service. Workers:

- Run the same image as the web service
- Have no public HTTP endpoint (no ingress)
- Are managed by App Platform (auto-restarts on crash)
- Scale independently from the web service

The worker receives the same env vars and secrets as the web service.
The `run_command` overrides the Dockerfile `CMD` to pass `--workers-only`.

## Kubernetes alternative (DOKS)

```sh
# Create a DOKS cluster
doctl kubernetes cluster create kerf-k8s \
  --region "${REGION}" \
  --version latest \
  --node-pool "name=default;size=s-2vcpu-4gb;count=2"

# Configure kubectl
doctl kubernetes cluster kubeconfig save kerf-k8s

# Deploy from the existing Kubernetes manifest
kubectl apply -f deployment/kubernetes.yaml
```

`deployment/kubernetes.yaml` uses `gcr.io/PROJECT/kerf-api:latest` by
default — update the image field to point at your DOCR image before
applying.

DOKS adds more flexibility but also more operational overhead. For most
teams using Kerf, App Platform is the right default.

## Observability

- **Logs**: `doctl apps logs "${APP_ID}" --component web --follow`
- **Metrics**: App Platform dashboard in the control panel — request
  count, CPU, memory, HTTP error rate
- **Alerts**: set up an alert policy in the DO control panel on
  CPU > 80% or HTTP 5xx rate > 1%
- **Depth**: App Platform metrics are less granular than Fly.io metrics
  or CloudWatch. For production monitoring, consider exporting metrics to
  an external provider (Datadog, Grafana Cloud) via the App Platform
  metrics endpoint.

## Custom domain

App Platform supports domain attachment with free Let's Encrypt TLS:

```sh
# In the app spec, add:
# domains:
#   - domain: kerf.example.com
#     type: PRIMARY

doctl apps update "${APP_ID}" --spec deployment/do-app-spec.yaml
```

Or via the control panel: App → Settings → Domains → Add Domain. App
Platform provisions a Let's Encrypt cert and renews it automatically.
Add the provided CNAME record to your DNS.

## Cost (rough, mid-2026)

| Resource | Spec | Monthly |
|---|---|---|
| App Platform (web) | `professional-m` (2 vCPU / 2 GiB) | $50 |
| App Platform (worker) | `professional-l` (4 vCPU / 8 GiB) | $100 |
| DO Managed Postgres | `db-s-1vcpu-1gb` dev / `db-s-2vcpu-4gb` prod | $15 dev / $60 prod |
| DO Spaces | $5/mo includes 250 GB + 1 TB bandwidth | $5 |
| Bandwidth | 1 TB included with each app instance; $0.01/GB after | $0 at small scale |
| Container Registry | Basic: $5/mo (5 GB included) | $5 |
| **Total at small scale** | (1k-5k users, dev DB) | **~$60-80/mo** |

DO Spaces includes 1 TB of outbound bandwidth per month in the base
$5/mo price — generous for small-to-medium deployments. After 1 TB,
$0.01/GB which is cheaper than AWS ($0.09/GB) or GCP ($0.085/GB).

App Platform worker costs are high because `professional-l` is always
running. If your workloads are infrequent, use App Platform's Job type
(one-shot runs) instead of a persistent worker to save ~$80/mo.

## Rollback

```sh
# List deployments
doctl apps list-deployments "${APP_ID}"

# Roll back to a previous deployment
doctl apps create-deployment "${APP_ID}" \
  --force-rebuild=false
```

App Platform keeps previous deployment images; you can trigger a
redeployment of any prior deployment from the control panel under
App → Activity → select deployment → Redeploy.

## Troubleshooting

- **Build fails**: App Platform builds from the Dockerfile by default if
  a `Dockerfile` is in the root. Check the build logs:
  `doctl apps logs "${APP_ID}" --component web --type build`.
  Transient npm issues resolve on retry.
- **Container exits immediately**: check runtime logs for startup errors.
  Missing env vars (especially `DATABASE_URL`) are the most common cause.
- **Cannot connect to Postgres**: by default, App Platform services
  connect to Managed Databases over the public network. Enable Trusted
  Sources on the Postgres cluster (allow the App Platform IP ranges) or
  use the private VPC endpoint (requires DO VPC peering).
- **Spaces 403**: double-check the Spaces access key has `readwrite`
  permission on the bucket. Also confirm `KERF_STORAGE_S3_ENDPOINT`
  includes the region: `https://lon1.digitaloceanspaces.com` not
  `https://digitaloceanspaces.com`.
- **Migrations not running**: NOT automatic. Run via `doctl apps console`
  after schema-changing deploys.
- **No SA region**: this is not a configuration error — DO simply has no
  JNB or Cape Town data centre. Users in SA will see ~150-250 ms latency
  to `lon1`. For lower SA latency, use Fly.io (`jnb` Johannesburg) —
  the hosted-tier canonical target. See [fly.md](./fly.md).
