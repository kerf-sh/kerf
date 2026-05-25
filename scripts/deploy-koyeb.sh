#!/usr/bin/env bash
# scripts/deploy-koyeb.sh — drive a Koyeb deployment.
#
# Builds + pushes the engine image, runs migrations as a one-off pre-deploy
# job, then deploys the engine (and optionally workers) service. (ROADMAP §7.1.)
#
# Usage:
#   ./scripts/deploy-koyeb.sh                   # defaults: --env prod
#   ./scripts/deploy-koyeb.sh --env dev         # deploy to kerf-dev
#   ./scripts/deploy-koyeb.sh --env prod --dry-run
#
# Prerequisites (one-time):
#   * koyeb-cli installed and authenticated:
#       brew install koyeb/tap/koyeb-cli && koyeb login
#   * Apps created:
#       koyeb app create kerf-prod
#       koyeb app create kerf-dev
#   * Secrets seeded (one per env):
#       koyeb secrets create database-url       --value "$DATABASE_URL"
#       koyeb secrets create tigris-bucket      --value "$KERF_STORAGE_S3_BUCKET"
#       koyeb secrets create tigris-access-key  --value "$KERF_STORAGE_S3_ACCESS_KEY"
#       koyeb secrets create tigris-secret-key  --value "$KERF_STORAGE_S3_SECRET_KEY"
#       koyeb secrets create paystack-secret-key --value "$CLOUD_PAYSTACK_SECRET_KEY"
#       koyeb secrets create paystack-public-key --value "$CLOUD_PAYSTACK_PUBLIC_KEY"
#       koyeb secrets create llm-anthropic      --value "$LLM_ANTHROPIC_API_KEY"
#       koyeb secrets create llm-openai         --value "$LLM_OPENAI_API_KEY"
#       koyeb secrets create llm-google         --value "$LLM_GOOGLE_API_KEY"
#       koyeb secrets create llm-deepseek       --value "$LLM_DEEPSEEK_API_KEY"
#       koyeb secrets create llm-minimax        --value "$LLM_MINIMAX_API_KEY"
#       koyeb secrets create jwt-secret         --value "$JWT_SECRET"

set -euo pipefail

ENV="prod"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --env)      ENV="$2"; shift 2 ;;
    --dry-run)  DRY_RUN=1; shift ;;
    -h|--help)
      sed -n '2,40p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

APP="kerf-${ENV}"
IMAGE_REPO="registry.koyeb.com/kerf/engine"
IMAGE_TAG="$(git rev-parse --short HEAD)"
IMAGE="${IMAGE_REPO}:${IMAGE_TAG}"

run() {
  echo "+ $*"
  [ "$DRY_RUN" -eq 1 ] || "$@"
}

echo "── Deploying to ${APP} (env=${ENV}, image=${IMAGE}) ─────────────"

# 1. Build the Docker image with the same KERF_PERSONA we used on Fly.
run docker build --platform linux/amd64 \
                 --build-arg KERF_PERSONA=full \
                 -t "${IMAGE}" \
                 -f Dockerfile .

# 2. Push to Koyeb's container registry (or any registry referenced by
#    koyeb.yaml). For private registries, create an image_registry_secret
#    on the service and tag accordingly.
run docker push "${IMAGE}"

# 3. Run the migration release step in a one-off Koyeb job. This must
#    finish before traffic shifts to the new image, so the new revision
#    never boots against an un-migrated schema.
run koyeb job create kerf-migrate-${IMAGE_TAG} \
    --app "${APP}" \
    --docker "${IMAGE}" \
    --docker-command "python -m kerf_core.db.migrations.runner" \
    --wait

# 4. Deploy the engine service. Reads koyeb.yaml and overrides the
#    image with the freshly-built tag.
run koyeb service deploy engine \
    --app "${APP}" \
    --file koyeb.yaml \
    --docker "${IMAGE}"

# 5. (Optional) Deploy the workers service if it has been split out.
if [ -f koyeb.worker.yaml ] && koyeb service describe workers --app "${APP}" >/dev/null 2>&1; then
  run koyeb service deploy workers \
      --app "${APP}" \
      --file koyeb.worker.yaml \
      --docker "${IMAGE}"
fi

# 6. Wait for healthy.
echo ""
echo "── Waiting for engine to become healthy ──"
run koyeb service describe engine --app "${APP}" --output json

echo ""
echo "✓ Deploy complete: ${APP} @ ${IMAGE_TAG}"
