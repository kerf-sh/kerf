# GCP Cloud Run deployment

Kerf deploys to Google Cloud Platform as a **single container image** on
Cloud Run. The same image that runs on Fly.io works here unchanged — the
frontend SPA is embedded in the image and served as static files by
FastAPI.

Heavy workers (FEM, topology opt, autoroute) run as a second Cloud Run
service with `min-instances=1`, or as Cloud Run Jobs for one-shot
workloads. See [Workers](#workers-cloud-run-jobs--second-service) below.

## Prerequisites

- `gcloud` CLI installed: `brew install google-cloud-sdk`
- Authenticated: `gcloud auth login && gcloud auth configure-docker`
- A GCP project created and billing enabled
- APIs enabled:

  ```sh
  gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    storage.googleapis.com \
    cloudresourcemanager.googleapis.com
  ```

- Cloud Storage bucket: see [gcs.md](./gcs.md)
- Cloud SQL Postgres instance: see [Postgres](#postgres-cloud-sql) below

## Image registry (Artifact Registry)

Create a Docker repository once per project:

```sh
gcloud artifacts repositories create kerf \
  --repository-format=docker \
  --location=africa-south1 \
  --description="Kerf container images"
```

Image path: `africa-south1-docker.pkg.dev/<PROJECT_ID>/kerf/kerf:<tag>`

Build and push:

```sh
PROJECT_ID=$(gcloud config get-value project)
IMAGE="africa-south1-docker.pkg.dev/${PROJECT_ID}/kerf/kerf:latest"

docker build --build-arg KERF_PERSONA=full -t "${IMAGE}" .
docker push "${IMAGE}"
```

For EU deployments, replace `africa-south1` with `europe-west3`.

## Postgres (Cloud SQL)

Create a Cloud SQL for PostgreSQL 16 instance:

```sh
gcloud sql instances create kerf-pg \
  --database-version=POSTGRES_16 \
  --tier=db-perf-optimized-N-2 \
  --region=africa-south1 \
  --storage-size=10GB \
  --storage-auto-increase \
  --backup-start-time=02:00 \
  --availability-type=REGIONAL
```

`db-perf-optimized-N-2` is the recommended production tier (2 vCPU,
16 GB RAM). For lower cost at small scale, start with `db-g1-small`
(shared core, fine for early users) and resize when you need it.

Create the database and a dedicated user:

```sh
gcloud sql databases create kerf --instance=kerf-pg
gcloud sql users create kerf_app --instance=kerf-pg --password="CHANGE_ME"
```

Connection string for Cloud SQL Auth Proxy (recommended — avoids
exposing the instance to the public internet):

```
postgres://kerf_app:CHANGE_ME@localhost:5432/kerf?sslmode=disable
```

When deploying to Cloud Run, use the Cloud SQL connection name instead
of localhost — Cloud Run connects via the Cloud SQL Auth Proxy socket
automatically when you supply `--add-cloudsql-instances`:

```
DATABASE_URL=postgres://kerf_app:CHANGE_ME@/kerf?host=/cloudsql/<PROJECT>:africa-south1:kerf-pg
```

## Secrets (Secret Manager)

Store sensitive values in Secret Manager rather than env vars:

```sh
printf "postgres://kerf_app:CHANGE_ME@/kerf?host=/cloudsql/<PROJECT>:africa-south1:kerf-pg" \
  | gcloud secrets create kerf-database-url --data-file=-

printf "$(openssl rand -hex 32)" \
  | gcloud secrets create kerf-jwt-secret --data-file=-

# Repeat for each secret (see deployment/README.md env var table)
```

Create a service account for Cloud Run:

```sh
gcloud iam service-accounts create kerf-api \
  --display-name="Kerf API service account"

SA="kerf-api@${PROJECT_ID}.iam.gserviceaccount.com"

# Grant access to secrets
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA}" \
  --role="roles/secretmanager.secretAccessor"

# Grant Cloud SQL Client (for proxy socket)
gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
  --member="serviceAccount:${SA}" \
  --role="roles/cloudsql.client"

# Grant Storage Object Admin for the Kerf bucket
gsutil iam ch "serviceAccount:${SA}:objectAdmin" gs://kerf-blobs-<PROJECT_ID>
```

## First deploy

The `deployment/cloudrun.yaml` manifest is the declarative version of
what the commands below do. You can use either approach.

**Imperative (quickest for first-time):**

```sh
gcloud run deploy kerf \
  --image="${IMAGE}" \
  --region=africa-south1 \
  --platform=managed \
  --service-account="${SA}" \
  --add-cloudsql-instances="${PROJECT_ID}:africa-south1:kerf-pg" \
  --set-env-vars="ENV=cloud,PORT=8080,STORAGE_BACKEND=s3,CLOUD_ENABLED=true" \
  --set-env-vars="KERF_STORAGE_S3_REGION=africa-south1" \
  --set-env-vars="KERF_STORAGE_S3_ENDPOINT=https://storage.googleapis.com" \
  --set-secrets="DATABASE_URL=kerf-database-url:latest" \
  --set-secrets="JWT_SECRET=kerf-jwt-secret:latest" \
  --set-secrets="KERF_STORAGE_S3_BUCKET=kerf-gcs-bucket:latest" \
  --set-secrets="KERF_STORAGE_S3_ACCESS_KEY=kerf-gcs-hmac-access:latest" \
  --set-secrets="KERF_STORAGE_S3_SECRET_KEY=kerf-gcs-hmac-secret:latest" \
  --set-secrets="LLM_ANTHROPIC_API_KEY=kerf-anthropic-key:latest" \
  --min-instances=1 \
  --max-instances=10 \
  --concurrency=80 \
  --cpu=2 \
  --memory=2Gi \
  --port=8080 \
  --timeout=300 \
  --allow-unauthenticated
```

**Declarative (recommended for production):**

Edit `deployment/cloudrun.yaml` to replace `PROJECT` with your project
ID, then:

```sh
gcloud run services replace deployment/cloudrun.yaml \
  --region=africa-south1
```

Run migrations after the first deploy:

```sh
gcloud run jobs create kerf-migrate \
  --image="${IMAGE}" \
  --region=africa-south1 \
  --service-account="${SA}" \
  --add-cloudsql-instances="${PROJECT_ID}:africa-south1:kerf-pg" \
  --set-secrets="DATABASE_URL=kerf-database-url:latest" \
  --command="python" \
  --args="-m,kerf_core.db.migrations.runner"

gcloud run jobs execute kerf-migrate --region=africa-south1 --wait
```

## Subsequent deploys

```sh
docker build --build-arg KERF_PERSONA=full -t "${IMAGE}" .
docker push "${IMAGE}"
gcloud run services update kerf --image="${IMAGE}" --region=africa-south1
```

Or let Cloud Build handle it:

```sh
gcloud builds submit --tag="${IMAGE}" .
gcloud run services update kerf --image="${IMAGE}" --region=africa-south1
```

## Scaling

```sh
# Horizontal: set instance range
gcloud run services update kerf \
  --min-instances=1 \
  --max-instances=20 \
  --region=africa-south1

# Vertical: more CPU + memory
gcloud run services update kerf \
  --cpu=4 \
  --memory=4Gi \
  --region=africa-south1
```

Cloud Run scales to zero by default when `--min-instances=0`. For
production, keep `--min-instances=1` to avoid cold-start latency on the
first request. Cold starts with this image take 5-15 seconds.

## Workers (Cloud Run Jobs / second service)

**Option A — Cloud Run Jobs** (one-shot heavy compute):

```sh
gcloud run jobs create kerf-worker \
  --image="${IMAGE}" \
  --region=africa-south1 \
  --service-account="${SA}" \
  --add-cloudsql-instances="${PROJECT_ID}:africa-south1:kerf-pg" \
  --set-env-vars="KERF_WORKERS_ONLY=true,STORAGE_BACKEND=s3,CLOUD_ENABLED=true" \
  --set-secrets="DATABASE_URL=kerf-database-url:latest" \
  --set-secrets="KERF_STORAGE_S3_BUCKET=kerf-gcs-bucket:latest" \
  --set-secrets="KERF_STORAGE_S3_ACCESS_KEY=kerf-gcs-hmac-access:latest" \
  --set-secrets="KERF_STORAGE_S3_SECRET_KEY=kerf-gcs-hmac-secret:latest" \
  --command="kerf-server" \
  --args="--workers-only" \
  --cpu=4 \
  --memory=8Gi \
  --task-timeout=3600

# Trigger a job manually (or call from the API with Workload Identity)
gcloud run jobs execute kerf-worker --region=africa-south1
```

**Option B — second Cloud Run service** (persistent, picks up queue):

```sh
gcloud run deploy kerf-workers \
  --image="${IMAGE}" \
  --region=africa-south1 \
  --service-account="${SA}" \
  --add-cloudsql-instances="${PROJECT_ID}:africa-south1:kerf-pg" \
  --set-env-vars="KERF_WORKERS_ONLY=true,STORAGE_BACKEND=s3,CLOUD_ENABLED=true" \
  --set-secrets="DATABASE_URL=kerf-database-url:latest" \
  --min-instances=1 \
  --no-allow-unauthenticated \
  --ingress=internal \
  --command="kerf-server" \
  --args="--host,0.0.0.0,--port,8080,--workers-only"
```

The worker service has `--ingress=internal` — it is not reachable from
the internet. The main app calls it via internal VPC.

## Multi-region

Cloud Run services are regional. For EU users, deploy the same image to
`europe-west3` (Frankfurt) and route with a global load balancer:

```sh
# Deploy the same image to Frankfurt
gcloud run deploy kerf \
  --image="${IMAGE}" \
  --region=europe-west3 \
  [... same flags as africa-south1 ...]

# Set up a global HTTP(S) load balancer with Cloud Run NEGs in both regions
# See: https://cloud.google.com/run/docs/multiple-regions
```

## Observability

- **Logs**: Cloud Logging — `gcloud logging read 'resource.type=cloud_run_revision'`
- **Metrics**: Cloud Monitoring dashboards (request count, latency, memory)
- **Error tracking**: Error Reporting groups exceptions automatically
- **Console**: Cloud Run → select service → Logs tab
- **Alerting**: set a Cloud Monitoring alert policy on error rate > 1%

The app writes structured JSON logs; Cloud Logging parses them as-is.

## Custom domain

```sh
gcloud run domain-mappings create \
  --service=kerf \
  --domain=kerf.example.com \
  --region=africa-south1
```

Cloud Run issues a Google-managed TLS certificate automatically and
shows DNS records to add. Cert provisioning takes 1-15 minutes after DNS
propagates.

For a naked domain (`example.com`) you need a Cloud Load Balancer
in front of Cloud Run — Cloud Run domain mappings don't support naked
domains directly.

## Cost (rough, mid-2026)

| Resource | Spec | Monthly |
|---|---|---|
| Cloud Run (app) | 2 vCPU / 2 GiB, ~20% utilisation, min-1 | ~$25-35 |
| Cloud Run (workers) | 4 vCPU / 8 GiB, on-demand | ~$10-20 (depends on jobs) |
| Cloud SQL | `db-g1-small` dev / `db-perf-optimized-N-2` prod | $10 dev / $130 prod |
| Cloud Storage | first 5 GB free, $0.020/GB-mo (standard, JNB) | < $5 at small scale |
| Bandwidth | **$0.085-0.12/GB egress outside region** — this is the gotcha | $0 within region; watch cross-region |
| Artifact Registry | ~$0.10/GB stored | < $2 |
| **Total at small scale** | (1k-5k users) | **~$50-80/mo** |

**Egress warning**: GCP charges $0.085-0.12/GB for data leaving the
region. If your users are in SA and your bucket is in JNB (`africa-south1`),
keep everything in the same region to avoid egress costs. Cross-region
traffic between Cloud Run and Cloud SQL is billed at the internal rate
($0.01/GB), which is much cheaper than internet egress.

Cloud Run pricing: first 2 million requests/month free, then
$0.40/million. CPU charged only when handling requests (unless
`--min-instances` keeps the container warm).

## Rollback

```sh
# List revisions
gcloud run revisions list --service=kerf --region=africa-south1

# Route 100% traffic to a previous revision
gcloud run services update-traffic kerf \
  --to-revisions=kerf-00012-abc=100 \
  --region=africa-south1
```

Cloud Run retains all revisions until you delete them. Traffic splitting
(e.g., 10% canary) is supported with the same `--to-revisions` flag.

## Troubleshooting

- **Container fails to start**: check Cloud Logging for the startup
  errors. Common cause: missing secret (SECRET_NOT_FOUND). Verify all
  `--set-secrets` names match what's in Secret Manager.
- **Cannot connect to Cloud SQL**: ensure the service account has
  `roles/cloudsql.client` and `--add-cloudsql-instances` is set on the
  Cloud Run service.
- **Storage 403**: HMAC key must be for the same service account that
  Cloud Run runs as, and that account needs `storage.objectAdmin` on the
  bucket. See [gcs.md](./gcs.md).
- **Migrations not running**: migrations are NOT automatic. Run the
  `kerf-migrate` Cloud Run Job after each deploy that ships schema
  changes.
- **Cold start latency**: Python + OCCT loads slowly. Use
  `--min-instances=1` in production. If budget is tight, App Engine
  `basic` scaling with a warmup request is an alternative.
