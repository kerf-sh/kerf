#!/usr/bin/env bash
#
# One-time fly.io infra setup for Kerf (idempotent — safe to re-run).
#
# Creates the four apps in the `kerf` org and registers TLS certs for the
# public domains. Region is Frankfurt (fra) — set via primary_region in
# fly.toml / fly.worker.toml and applied on first `deploy-fly.sh`.
#
# Tigris object storage is deliberately NOT handled here — the dev/prod
# buckets are already provisioned (`flyctl storage create -a kerf-dev` /
# `-a kerf-prod`) and their keys live in .env.dev / .env.main. Re-creating
# them would rotate credentials, so storage stays a manual, one-off step.
#
# Usage:
#   ./scripts/setup-fly.sh            # create apps + add both certs
#   ./scripts/setup-fly.sh --no-certs # apps only (add certs after DNS)
#
# Prereqs: flyctl installed + logged in (flyctl auth login), DNS for
# kerf.sh / dev.kerf.sh pointing at fly before certs validate.
#
# After this: fill .env.dev / .env.main, then ./scripts/deploy-fly.sh --dev

set -euo pipefail

ORG="kerf"
ADD_CERTS=true
[[ "${1:-}" == "--no-certs" ]] && ADD_CERTS=false

if ! command -v flyctl >/dev/null 2>&1; then
  echo "error: flyctl not installed — brew install flyctl"; exit 1
fi
if ! flyctl auth whoami >/dev/null 2>&1; then
  echo "error: not logged in — flyctl auth login"; exit 1
fi

# app name : custom domain (empty = no public cert)
APPS=(
  "kerf-prod:kerf.sh"
  "kerf-workers:"
  "kerf-dev:dev.kerf.sh"
  "kerf-dev-workers:"
)

for entry in "${APPS[@]}"; do
  app="${entry%%:*}"
  domain="${entry##*:}"

  if flyctl apps list 2>/dev/null | awk '{print $1}' | grep -qx "$app"; then
    echo "▸ app $app already exists — skip create"
  else
    echo "▸ creating app $app (org $ORG)"
    flyctl apps create "$app" -o "$ORG"
  fi

  if [[ "$ADD_CERTS" == "true" && -n "$domain" ]]; then
    if flyctl certs list -a "$app" 2>/dev/null | grep -q "$domain"; then
      echo "  ✓ cert for $domain already present"
    else
      echo "  ▸ adding cert $domain → $app"
      flyctl certs add "$domain" -a "$app" || \
        echo "  ! cert add failed for $domain (point DNS at $app.fly.dev, re-run)"
    fi
  fi
done

cat <<'EOF'

✔ apps ready (region fra via fly.toml primary_region).
Next:
  1. DNS:  kerf.sh      → kerf-prod  (A/AAAA or flattened CNAME → kerf-prod.fly.dev)
           dev.kerf.sh  → CNAME      → kerf-dev.fly.dev
  2. Postgres: create Neon dev + prod DBs, put URLs in .env.dev / .env.main
  3. Google + GitHub OAuth clients with the dev/prod callback URLs
  4. LLM key(s) into .env.{dev,main}
  5. Deploy:  ./scripts/deploy-fly.sh --dev      (then: no --dev for prod)
EOF
