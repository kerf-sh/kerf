#!/usr/bin/env bash
#
# Deploy Kerf to fly.io.
#
# Reads secrets from `.env.main` (default) or `.env.dev` (with --dev),
# pushes them to the fly app + worker app, then runs `flyctl deploy`
# against both configs.
#
# Usage:
#   ./scripts/deploy-fly.sh                # deploy MAIN (production)
#   ./scripts/deploy-fly.sh --dev          # deploy DEV
#   ./scripts/deploy-fly.sh --secrets-only # just push secrets, no rebuild
#   ./scripts/deploy-fly.sh --app-only     # skip worker deploy
#
# Combine: `./scripts/deploy-fly.sh --dev --secrets-only`
#
# Prereqs:
#   - flyctl installed and logged in (flyctl auth login)
#   - .env.main exists (cp .env.z.example .env.main) — or .env.dev for --dev
#   - fly apps created (one-time):
#       MAIN: flyctl apps create kerf && flyctl apps create kerf-workers
#       DEV:  flyctl apps create kerf-dev && flyctl apps create kerf-dev-workers

set -euo pipefail

# ── Argument parsing ─────────────────────────────────────────────────────────
ENV_NAME="main"
SECRETS_ONLY=false
APP_ONLY=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dev)          ENV_NAME="dev"; shift ;;
    --main)         ENV_NAME="main"; shift ;;
    --secrets-only) SECRETS_ONLY=true; shift ;;
    --app-only)     APP_ONLY=true; shift ;;
    -h|--help)
      sed -n '3,20p' "$0"
      exit 0
      ;;
    *)
      echo "Unknown arg: $1"; exit 1 ;;
  esac
done

ENV_FILE=".env.${ENV_NAME}"
if [[ "$ENV_NAME" == "main" ]]; then
  # Global app name "kerf" is taken on fly.io; production app is
  # "kerf-prod" (public domain kerf.sh is mapped via flyctl certs).
  APP_NAME="kerf-prod"
  WORKER_APP_NAME="kerf-workers"
else
  APP_NAME="kerf-${ENV_NAME}"
  WORKER_APP_NAME="kerf-${ENV_NAME}-workers"
fi

echo "▸ environment: ${ENV_NAME}"
echo "▸ env file:    ${ENV_FILE}"
echo "▸ app:         ${APP_NAME}"
echo "▸ workers:     ${WORKER_APP_NAME}"
echo ""

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
  echo "Copy .env.z.example to $ENV_FILE and fill in values."
  exit 1
fi

# Refuse to push a file that still has XXX placeholder values.
if grep -qE '^[A-Z_]+=[^=]*XXX' "$ENV_FILE"; then
  echo "error: $ENV_FILE still contains XXX placeholders."
  echo "Replace these values before deploying:"
  grep -nE '^[A-Z_]+=[^=]*XXX' "$ENV_FILE" | head -10
  exit 1
fi

# ── Confirm prod deploys ────────────────────────────────────────────────────
if [[ "$ENV_NAME" == "main" && "$SECRETS_ONLY" != "true" ]]; then
  echo "▸ PRODUCTION deploy to $APP_NAME — continue? (yes/no)"
  read -r confirm
  if [[ "$confirm" != "yes" ]]; then
    echo "aborted"
    exit 1
  fi
fi

# ── Load env file ────────────────────────────────────────────────────────────
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
  CLOUD_ENABLED
  KERF_LOCAL_MODE
)
# LLM provider keys are intentionally NOT required — the app boots without
# them (chat/LLM tools stay dormant until a key is added post-deploy).

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

# ── Collect all KEY= lines from the env file (skip comments + blanks) ──────
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
echo "✓ ${ENV_NAME} deploy complete."
echo "  app:    https://$(flyctl info --app "$APP_NAME" --json | python -c 'import json,sys;print(json.load(sys.stdin)["Hostname"])')"
echo "  status: flyctl status --app $APP_NAME"
echo "  logs:   flyctl logs --app $APP_NAME"
