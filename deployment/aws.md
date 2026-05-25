# AWS deployment

Kerf deploys to AWS as a **single container image** using ECS Fargate
(recommended for production) or App Runner (simpler for a first cut).
The same image that runs on Fly.io or Cloud Run works here — frontend
SPA embedded, FastAPI backend, health check on `/healthz`.

S3 is the native storage backend: `STORAGE_BACKEND=s3` requires no
adapter; AWS is what Kerf's storage layer was written against first.

## Prerequisites

- AWS CLI v2 installed and configured: `aws configure`
- `docker` installed (for building and pushing the image)
- An ECR repository, VPC, and IAM roles (see below — one-time setup)
- RDS Postgres instance: see [Postgres (RDS)](#postgres-rds) below
- S3 bucket: see [s3.md](./s3.md)

## Region selection

| Audience | Region |
|---|---|
| South Africa | `af-south-1` (Cape Town) |
| Europe | `eu-central-1` (Frankfurt) |
| US / global | `us-east-1` |

`af-south-1` must be opted in explicitly: AWS Console → Account settings
→ Regions → enable Cape Town. Not all instance types are available in
`af-south-1`; verify Fargate spot availability there before committing.

## Image registry (ECR)

```sh
REGION=af-south-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
REPO="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com/kerf"

# Create the repository (one-time)
aws ecr create-repository --repository-name kerf --region "${REGION}"

# Authenticate Docker to ECR
aws ecr get-login-password --region "${REGION}" \
  | docker login --username AWS --password-stdin "${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"

# Build and push
docker build --build-arg KERF_PERSONA=full -t "${REPO}:latest" .
docker push "${REPO}:latest"
```

Image path: `<account>.dkr.ecr.<region>.amazonaws.com/kerf:<tag>`

## Postgres (RDS)

Create an RDS for PostgreSQL 16 instance. Multi-AZ for production:

```sh
# Create a DB subnet group first (one-time) if you haven't
aws rds create-db-subnet-group \
  --db-subnet-group-name kerf-db-subnet \
  --db-subnet-group-description "Kerf Postgres subnets" \
  --subnet-ids subnet-aaaa subnet-bbbb

# Production: db.m6g.large Multi-AZ
aws rds create-db-instance \
  --db-instance-identifier kerf-pg \
  --db-engine postgres \
  --engine-version 16 \
  --db-instance-class db.m6g.large \
  --allocated-storage 20 \
  --storage-type gp3 \
  --storage-encrypted \
  --multi-az \
  --db-subnet-group-name kerf-db-subnet \
  --vpc-security-group-ids sg-xxxx \
  --db-name kerf \
  --master-username kerf_app \
  --master-user-password "CHANGE_ME" \
  --backup-retention-period 7 \
  --region "${REGION}"
```

For early-stage / low-cost, use `db.t4g.micro` (single-AZ). Resize
when you outgrow it.

The database endpoint appears in `aws rds describe-db-instances` once
the instance is available. Store the connection string in AWS Secrets
Manager (see below).

## Secrets Manager

```sh
# Store all secrets in a single JSON secret
aws secretsmanager create-secret \
  --name kerf/prod \
  --region "${REGION}" \
  --secret-string '{
    "DATABASE_URL": "postgres://kerf_app:CHANGE_ME@kerf-pg.xxx.af-south-1.rds.amazonaws.com:5432/kerf?sslmode=require",
    "JWT_SECRET": "'$(openssl rand -hex 32)'",
    "KERF_STORAGE_S3_BUCKET": "kerf-blobs-prod",
    "LLM_ANTHROPIC_API_KEY": "sk-ant-...",
    "CLOUD_PAYSTACK_SECRET_KEY": "sk_live_...",
    "CLOUD_PAYSTACK_PUBLIC_KEY": "pk_live_..."
  }'
```

ECS task definitions reference individual keys from this secret using
`valueFrom` (see task definition below).

## ECS Fargate (recommended)

### IAM roles (one-time)

```sh
# Task execution role (allows ECS to pull image + read secrets)
aws iam create-role --role-name kerf-ecs-exec \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam attach-role-policy --role-name kerf-ecs-exec \
  --policy-arn arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy

# Also grant SecretsManager read for the kerf/prod secret
aws iam put-role-policy --role-name kerf-ecs-exec \
  --policy-name kerf-secrets-read \
  --policy-document '{
    "Version":"2012-10-17",
    "Statement":[{"Effect":"Allow","Action":["secretsmanager:GetSecretValue"],"Resource":"arn:aws:secretsmanager:'${REGION}':'${ACCOUNT}':secret:kerf/prod-*"}]
  }'

# Task role (what the running container can do — S3 access)
aws iam create-role --role-name kerf-ecs-task \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"ecs-tasks.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

aws iam put-role-policy --role-name kerf-ecs-task \
  --policy-name kerf-s3-access \
  --policy-document '{
    "Version":"2012-10-17",
    "Statement":[{"Effect":"Allow","Action":["s3:GetObject","s3:PutObject","s3:DeleteObject","s3:ListBucket"],"Resource":["arn:aws:s3:::kerf-blobs-prod","arn:aws:s3:::kerf-blobs-prod/*"]}]
  }'
```

### ECS cluster

```sh
aws ecs create-cluster --cluster-name kerf --region "${REGION}"
```

### Task definition

Save the following as `task-definition.json`, replacing placeholders:

```json
{
  "family": "kerf",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "1024",
  "memory": "2048",
  "executionRoleArn": "arn:aws:iam::<ACCOUNT>:role/kerf-ecs-exec",
  "taskRoleArn": "arn:aws:iam::<ACCOUNT>:role/kerf-ecs-task",
  "containerDefinitions": [
    {
      "name": "kerf",
      "image": "<ACCOUNT>.dkr.ecr.af-south-1.amazonaws.com/kerf:latest",
      "portMappings": [{"containerPort": 8080, "protocol": "tcp"}],
      "environment": [
        {"name": "ENV", "value": "cloud"},
        {"name": "PORT", "value": "8080"},
        {"name": "STORAGE_BACKEND", "value": "s3"},
        {"name": "KERF_STORAGE_S3_REGION", "value": "af-south-1"},
        {"name": "CLOUD_ENABLED", "value": "true"}
      ],
      "secrets": [
        {"name": "DATABASE_URL", "valueFrom": "arn:aws:secretsmanager:af-south-1:<ACCOUNT>:secret:kerf/prod:DATABASE_URL::"},
        {"name": "JWT_SECRET", "valueFrom": "arn:aws:secretsmanager:af-south-1:<ACCOUNT>:secret:kerf/prod:JWT_SECRET::"},
        {"name": "KERF_STORAGE_S3_BUCKET", "valueFrom": "arn:aws:secretsmanager:af-south-1:<ACCOUNT>:secret:kerf/prod:KERF_STORAGE_S3_BUCKET::"},
        {"name": "LLM_ANTHROPIC_API_KEY", "valueFrom": "arn:aws:secretsmanager:af-south-1:<ACCOUNT>:secret:kerf/prod:LLM_ANTHROPIC_API_KEY::"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/kerf",
          "awslogs-region": "af-south-1",
          "awslogs-stream-prefix": "ecs"
        }
      },
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8080/healthz || exit 1"],
        "interval": 30,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 10
      }
    }
  ]
}
```

Register it:

```sh
aws ecs register-task-definition \
  --cli-input-json file://task-definition.json \
  --region "${REGION}"

# Create CloudWatch log group
aws logs create-log-group --log-group-name /ecs/kerf --region "${REGION}"
```

### Application Load Balancer + service

```sh
# Create ALB (assumes you have a public subnet and security group)
aws elbv2 create-load-balancer \
  --name kerf-alb \
  --subnets subnet-pub-a subnet-pub-b \
  --security-groups sg-alb-xxxx \
  --region "${REGION}"

# Create target group
aws elbv2 create-target-group \
  --name kerf-tg \
  --protocol HTTP \
  --port 8080 \
  --vpc-id vpc-xxxx \
  --target-type ip \
  --health-check-path /healthz \
  --region "${REGION}"

# Create ECS service (Fargate)
aws ecs create-service \
  --cluster kerf \
  --service-name kerf \
  --task-definition kerf \
  --desired-count 2 \
  --launch-type FARGATE \
  --network-configuration "awsvpcConfiguration={subnets=[subnet-priv-a,subnet-priv-b],securityGroups=[sg-task-xxxx],assignPublicIp=DISABLED}" \
  --load-balancers "targetGroupArn=arn:aws:elasticloadbalancing:...,containerName=kerf,containerPort=8080" \
  --region "${REGION}"
```

Run migrations once the service is running (use ECS Exec):

```sh
aws ecs execute-command \
  --cluster kerf \
  --task <TASK_ARN> \
  --container kerf \
  --interactive \
  --command "python -m kerf_core.db.migrations.runner $DATABASE_URL"
```

## App Runner (simpler v1 option)

App Runner is significantly simpler but has fewer controls. Good for a
first deploy; migrate to Fargate when you need auto-scaling tuning or
internal networking.

```sh
aws apprunner create-service \
  --service-name kerf \
  --source-configuration '{
    "ImageRepository": {
      "ImageIdentifier": "'${REPO}':latest",
      "ImageRepositoryType": "ECR",
      "ImageConfiguration": {
        "Port": "8080",
        "RuntimeEnvironmentVariables": {
          "ENV": "cloud",
          "STORAGE_BACKEND": "s3",
          "KERF_STORAGE_S3_REGION": "af-south-1",
          "CLOUD_ENABLED": "true"
        },
        "RuntimeEnvironmentSecrets": {
          "DATABASE_URL": "arn:aws:secretsmanager:...",
          "JWT_SECRET": "arn:aws:secretsmanager:..."
        }
      }
    },
    "AutoDeploymentsEnabled": false
  }' \
  --instance-configuration '{"Cpu":"1 vCPU","Memory":"2 GB"}' \
  --region "${REGION}"
```

App Runner does not support private VPC-only services in all regions —
the RDS instance needs a security group that allows App Runner's VPC
connector. Follow the App Runner VPC connector docs for private DB access.

## Subsequent deploys

```sh
# Push new image
docker build --build-arg KERF_PERSONA=full -t "${REPO}:latest" .
docker push "${REPO}:latest"

# Register new task definition revision
aws ecs register-task-definition --cli-input-json file://task-definition.json

# Force new deployment (rolls out new task def)
aws ecs update-service \
  --cluster kerf \
  --service kerf \
  --force-new-deployment \
  --region "${REGION}"
```

## Scaling

```sh
# Manual desired count
aws ecs update-service --cluster kerf --service kerf --desired-count 4

# Auto-scaling: register a scalable target
aws application-autoscaling register-scalable-target \
  --service-namespace ecs \
  --scalable-dimension ecs:service:DesiredCount \
  --resource-id service/kerf/kerf \
  --min-capacity 1 \
  --max-capacity 20

# Scale on CPU > 60%
aws application-autoscaling put-scaling-policy \
  --policy-name kerf-cpu-scaling \
  --service-namespace ecs \
  --scalable-dimension ecs:service:DesiredCount \
  --resource-id service/kerf/kerf \
  --policy-type TargetTrackingScaling \
  --target-tracking-scaling-policy-configuration '{
    "TargetValue": 60.0,
    "PredefinedMetricSpecification": {"PredefinedMetricType": "ECSServiceAverageCPUUtilization"}
  }'
```

## Workers (separate task definition)

Create a second task definition (`kerf-workers`) pointing to the same
image with `--workers-only`:

```json
{
  "family": "kerf-workers",
  "cpu": "2048",
  "memory": "8192",
  "containerDefinitions": [
    {
      "name": "kerf-worker",
      "image": "<same ECR image>",
      "command": ["kerf-server", "--host", "0.0.0.0", "--port", "8080", "--workers-only"],
      "environment": [
        {"name": "KERF_WORKERS_ONLY", "value": "true"},
        {"name": "STORAGE_BACKEND", "value": "s3"}
      ]
    }
  ]
}
```

Deploy as a second ECS service with `desired-count=1` and no load
balancer (workers are internal only).

## Multi-region

Deploy the same task definitions to a second cluster in `eu-central-1`.
Use Route 53 latency-based routing to direct users to the closest region:

```sh
aws route53 change-resource-record-sets \
  --hosted-zone-id ZXXXXXXX \
  --change-batch '{
    "Changes": [
      {
        "Action": "CREATE",
        "ResourceRecordSet": {
          "Name": "kerf.example.com",
          "Type": "A",
          "Region": "af-south-1",
          "SetIdentifier": "sa",
          "AliasTarget": {"HostedZoneId": "...", "DNSName": "kerf-alb.af-south-1.elb.amazonaws.com", "EvaluateTargetHealth": true}
        }
      }
    ]
  }'
```

Each region needs its own RDS instance and S3 bucket (or cross-region
replication configured). Keep Postgres in one primary region and use
read replicas if eventual consistency is acceptable.

## Observability

- **Logs**: CloudWatch Logs group `/ecs/kerf` — `aws logs tail /ecs/kerf --follow`
- **Metrics**: ECS service metrics in CloudWatch (CPU, memory, request count via ALB)
- **Tracing**: Enable AWS X-Ray sidecar for distributed tracing
- **Alarms**: set a CloudWatch alarm on ALB 5xx error rate > 1%
- **Container Insights**: enable per-cluster for enhanced memory/disk metrics:
  ```sh
  aws ecs update-cluster-settings --cluster kerf \
    --settings name=containerInsights,value=enabled
  ```

## Custom domain (Route 53 + ACM + ALB)

```sh
# Request a certificate (DNS validation)
aws acm request-certificate \
  --domain-name kerf.example.com \
  --validation-method DNS \
  --region "${REGION}"

# After adding the CNAME validation records, add an HTTPS listener to the ALB
aws elbv2 create-listener \
  --load-balancer-arn arn:aws:elasticloadbalancing:... \
  --protocol HTTPS \
  --port 443 \
  --certificates CertificateArn=arn:aws:acm:... \
  --default-actions Type=forward,TargetGroupArn=arn:aws:elasticloadbalancing:...

# Route 53 alias record pointing to the ALB
aws route53 change-resource-record-sets --hosted-zone-id ZXXXXXXX \
  --change-batch '{
    "Changes": [{"Action":"CREATE","ResourceRecordSet":{
      "Name":"kerf.example.com","Type":"A",
      "AliasTarget":{"HostedZoneId":"ZXXXXXXXX","DNSName":"kerf-alb.af-south-1.elb.amazonaws.com","EvaluateTargetHealth":true}
    }}]
  }'
```

ACM certs auto-renew; no action needed after initial setup.

## Cost (rough, mid-2026)

| Resource | Spec | Monthly |
|---|---|---|
| ECS Fargate (app) | 1 vCPU / 2 GiB, 2 tasks | ~$60 |
| ECS Fargate (workers) | 2 vCPU / 8 GiB, 1 task | ~$50 |
| RDS Postgres | `db.t4g.micro` dev / `db.m6g.large` Multi-AZ prod | $15 dev / $180 prod |
| S3 storage | $0.023/GB-mo (Cape Town) | < $5 at small scale |
| ALB | ~$20/mo fixed + $0.008/LCU | ~$20 |
| Bandwidth | **$0.09/GB egress** — biggest cost driver at scale | $0 within region; watch internet egress |
| ECR | $0.10/GB stored | < $2 |
| **Total at small scale** | (1k-5k users, dev DB) | **~$120-150/mo** |

**Egress warning**: AWS charges $0.09/GB for data leaving the region to
the internet (af-south-1 may be higher — verify on the AWS pricing page).
At 100 GB egress/month that's $9; at 1 TB it's $90. Keep your S3 bucket
and ECS service in the same region to eliminate intra-region S3 costs
($0.00/GB within region).

## Rollback

```sh
# List task definition revisions
aws ecs list-task-definitions --family-prefix kerf

# Update service to use a previous revision
aws ecs update-service \
  --cluster kerf \
  --service kerf \
  --task-definition kerf:12 \
  --region "${REGION}"
```

AWS ECS rolling updates ensure there is always a healthy task running
during the update. If the new task fails its health checks, ECS
automatically stops the rollout and keeps the old tasks running.

## Troubleshooting

- **Task fails to start (essential container exited)**: check CloudWatch
  Logs for the startup error. Common causes: missing secret (secrets
  must be valid ARNs in the same region), execution role lacks
  `secretsmanager:GetSecretValue`.
- **Cannot connect to RDS**: the ECS task security group must have
  outbound port 5432 allowed, and the RDS security group must allow
  inbound 5432 from the ECS task security group.
- **ECR pull fails**: execution role needs `ecr:GetAuthorizationToken`
  and `ecr:BatchGetImage`. The managed policy
  `AmazonECSTaskExecutionRolePolicy` covers this.
- **af-south-1 instance types unavailable**: not all Fargate CPU/memory
  combinations are available in Cape Town. If you hit a capacity error,
  try `eu-central-1` or check AWS availability zone docs.
- **Migrations**: NOT automatic. Run them via ECS Exec or a one-off
  task after each schema-changing deploy.
