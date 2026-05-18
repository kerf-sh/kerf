#!/usr/bin/env bash
# scripts/entrypoint.sh — Kerf Cycles Worker container startup script
#
# This is the canonical entrypoint for the self-host Docker image built from
# packages/kerf-render/Dockerfile.cycles-worker.  It is copied into the image
# at /usr/local/bin/kerf-cycles-entrypoint.
#
# Environment variables consumed:
#
#   KERF_BLENDER_PATH    Path to a user-supplied Blender binary (BYO mode).
#                        When set, this binary is used instead of the Docker-
#                        bundled /opt/blender/blender.
#                        Examples:
#                          /Applications/Blender.app/Contents/MacOS/Blender
#                          /usr/local/bin/blender
#
#   KERF_API_URL         Base URL of the Kerf API this worker reports to.
#                        Example: https://my-kerf.example.com
#                        Leave unset for standalone / offline test mode.
#
#   KERF_API_TOKEN       Auth token for the Kerf API.  Required when
#                        KERF_API_URL is set.
#
#   KERF_WORKER_CONCURRENCY
#                        Number of render jobs to process in parallel.
#                        Defaults to 1.  GPU boxes: keep at 1 (VRAM
#                        contention).  CPU-only boxes: 2-4 is typical.
#
# Any additional arguments passed to this script are forwarded to
# `python -m kerf_render.cycles_worker`.

set -euo pipefail

# ── Version banner ──────────────────────────────────────────────────────────
KERF_RENDER_VERSION=$(python3 -c "
try:
    from importlib.metadata import version
    print(version('kerf-render'))
except Exception:
    print('dev')
" 2>/dev/null || echo "dev")

echo "========================================================"
echo " Kerf Cycles Worker"
echo " kerf-render version : ${KERF_RENDER_VERSION}"
echo " Python              : $(python3 --version 2>&1)"
echo "========================================================"

# ── Blender path resolution ─────────────────────────────────────────────────
#
# Precedence:
#   1. KERF_BLENDER_PATH (operator-supplied BYO path — volume-mount or host)
#   2. /opt/blender/blender (bundled in the Docker image)
#   3. blender on PATH (fallback for non-Docker / dev environments)
#
if [ -n "${KERF_BLENDER_PATH:-}" ]; then
    if [ ! -x "${KERF_BLENDER_PATH}" ]; then
        echo "ERROR: KERF_BLENDER_PATH='${KERF_BLENDER_PATH}' is not executable." >&2
        echo "       Mount the Blender directory with -v and ensure the binary is" >&2
        echo "       executable inside the container." >&2
        exit 1
    fi
    BLENDER_BIN="${KERF_BLENDER_PATH}"
    echo " Blender (BYO)       : ${BLENDER_BIN}"
elif [ -x "/opt/blender/blender" ]; then
    BLENDER_BIN="/opt/blender/blender"
    echo " Blender (bundled)   : ${BLENDER_BIN}"
else
    # Resolve from PATH; tolerate absence — worker logs it gracefully.
    BLENDER_BIN="$(command -v blender 2>/dev/null || echo 'blender')"
    echo " Blender (PATH)      : ${BLENDER_BIN}"
fi

# Export as KERF_BLENDER_BIN so cycles_worker.resolve_blender_bin() picks it
# up with the highest-priority env var, regardless of KERF_BLENDER_PATH.
export KERF_BLENDER_BIN="${BLENDER_BIN}"

# Print Blender version (non-fatal if the binary is absent — the worker
# handles that with a descriptive error in the job result).
if [ -x "${BLENDER_BIN}" ]; then
    BLENDER_VER="$("${BLENDER_BIN}" --version 2>/dev/null | head -1 || echo 'unknown')"
    echo " Blender version     : ${BLENDER_VER}"
else
    echo " WARNING: Blender binary not found at '${BLENDER_BIN}'." >&2
    echo "          Render jobs will fail until a valid binary is available." >&2
fi

# ── API connectivity ─────────────────────────────────────────────────────────
if [ -n "${KERF_API_URL:-}" ]; then
    echo " API URL             : ${KERF_API_URL}"
else
    echo " API URL             : (not set — standalone / test mode)"
fi

if [ -n "${KERF_API_TOKEN:-}" ]; then
    echo " API token           : (set)"
else
    echo " API token           : (not set)"
fi

echo " Concurrency         : ${KERF_WORKER_CONCURRENCY:-1}"
echo "========================================================"

# ── Launch worker ───────────────────────────────────────────────────────────
# exec replaces the shell process so PID 1 is the Python worker and signals
# (SIGTERM from `docker stop`) are delivered directly to it.
exec python3 -m kerf_render.cycles_worker "$@"
