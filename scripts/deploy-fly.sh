#!/usr/bin/env bash
#
# Deploy Kerf to fly.io.
#
# Reads secrets from .env.production (gitignored), pushes them to the
# fly app + worker app, then runs `flyctl deploy` against both.
#
# Usage:
#   ./scripts/deploy-fly.sh                # full deploy: secrets + apps
#   ./scripts/deploy-fly.sh --secrets-only # just push secrets, no deploy
#   ./scripts/deploy-fly.sh --app-only     # deploy app, skip worker
#   ./scripts/deploy-fly.sh --staging      # use .env.staging instead
#
# Prereqs:
#   - flyctl installed and logged in (flyctl auth login)
#   - .env.production exists (copy from .env.production.example)
#   - fly apps created: `flyctl apps create kerf` + `flyctl apps create kerf-workers`

set -euo pipefail

# ── Argument parsing ─────────────────────────────────────────────────────────
SECRETS_ONLY=false
APP_ONLY=false
ENV_FILE=".env.production"
APP_NAME="kerf"
WORKER_APP_NAME="kerf-workers"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --secrets-only) SECRETS_ONLY=true; shift ;;
    --app-only)     APP_ONLY=true; shift ;;
    --staging)
      ENV_FILE=".env.staging"
      APP_NAME="kerf-staging"
      WORKER_APP_NAME="kerf-staging-workers"
      shift
      ;;
    -h|--help)
      sed -n '3,20p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1"; exit 1 ;;
  esac
done

# ── Sanity checks ────────────────────────────────────────────────────────────
if ! command -v flyctl >/dev/null 2>&1; then
  echo "error: flyctl not installed. brew install flyctl"
  exit 1
fi

if ! flyctl auth whoami >/dev/null 2>&1; then
  echo "error: not logged in to fly.io. Run: flyctl auth login"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found"
  echo "Copy .env.production.example to $ENV_FILE and fill in values."
  exit 1
fi

# ── Load env file ────────────────────────────────────────────────────────────
# `set -a` exports every variable assigned after it; `set +a` turns it off.
# This way the env file's KEY=VALUE lines are all picked up.
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# ── Validate required vars ───────────────────────────────────────────────────
REQUIRED_VARS=(
  DATABASE_URL
  JWT_SECRET
  KERF_STORAGE_S3_BUCKET
  KERF_STORAGE_S3_ACCESS_KEY
  KERF_STORAGE_S3_SECRET_KEY
  KERF_STORAGE_S3_ENDPOINT
  LLM_ANTHROPIC_API_KEY
  CLOUD_ENABLED
  KERF_LOCAL_MODE
)

MISSING=()
for var in "${REQUIRED_VARS[@]}"; do
  if [[ -z "${!var:-}" ]]; then
    MISSING+=("$var")
  fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
  echo "error: required vars missing from $ENV_FILE:"
  printf '  %s\n' "${MISSING[@]}"
  exit 1
fi

# ── Collect all KERF_* / LLM_* / CLOUD_* / etc. vars from the env file ──────
# We push every non-empty var defined in the env file to fly secrets. The
# parse below grabs `KEY=` lines (ignoring comments + blanks).
SECRET_KEYS=$(grep -E '^[A-Z_][A-Z0-9_]*=' "$ENV_FILE" | sed 's/=.*//' | sort -u)

# ── Push secrets to both apps ────────────────────────────────────────────────
push_secrets() {
  local app="$1"
  echo "▸ pushing secrets to $app"

  local args=()
  for key in $SECRET_KEYS; do
    local val="${!key:-}"
    if [[ -n "$val" ]]; then
      args+=("$key=$val")
    fi
  done

  if [[ ${#args[@]} -eq 0 ]]; then
    echo "  (no secrets to set)"
    return
  fi

  # --stage queues the secrets without restarting the app; the subsequent
  # flyctl deploy picks them up.
  flyctl secrets set --app "$app" --stage "${args[@]}"
  echo "  ✓ ${#args[@]} secrets staged on $app"
}

push_secrets "$APP_NAME"
if [[ "$APP_ONLY" != "true" ]]; then
  push_secrets "$WORKER_APP_NAME"
fi

if [[ "$SECRETS_ONLY" == "true" ]]; then
  echo "▸ --secrets-only set; skipping deploy"
  exit 0
fi

# ── Deploy ───────────────────────────────────────────────────────────────────
echo "▸ deploying app: $APP_NAME"
flyctl deploy --config fly.toml --app "$APP_NAME" --remote-only

if [[ "$APP_ONLY" != "true" ]]; then
  echo "▸ deploying workers: $WORKER_APP_NAME"
  flyctl deploy --config fly.worker.toml --app "$WORKER_APP_NAME" --remote-only
fi

# ── Run migrations ───────────────────────────────────────────────────────────
echo "▸ running database migrations"
flyctl ssh console --app "$APP_NAME" \
  -C "python -m kerf_core.db.migrations.runner $DATABASE_URL"

echo ""
echo "✓ deploy complete."
echo "  app:    https://$(flyctl info --app "$APP_NAME" --json | python -c 'import json,sys;print(json.load(sys.stdin)["Hostname"])')"
echo "  status: flyctl status --app $APP_NAME"
echo "  logs:   flyctl logs --app $APP_NAME"
